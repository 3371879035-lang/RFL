r"""The persistent learner state, its snapshot, and its transaction.

Four stores make up $W^L = (P_D^L, C_P^L, C_X^L, Q_D^L)$. The fourth arrived with A77
§65.4, and only after its semantics were frozen: an empty ``Q_D^L`` stub placed earlier
would have been mistaken for frozen Q semantics, which is exactly what the previous
revision of this paragraph refused to do.

$Q_D^L$ is a **sparse override table on the injected reference** (A77 §65.4):

$$Q^{\text{eff}}(x,a) = \begin{cases} Q_D^L(x,a), & (x,a) \in Q_D^L\\
Q_D^\ast(x,a), & \text{otherwise}\end{cases}$$

so an absent entry means "no deviation", **not** "the value is zero", and assigning the
reference value canonicalises to a deletion like the other stores' identity assignments.

**The reference is injected, never fetched.** Nothing in this module calls
``solve_reference()``; the caller passes a :class:`~rfl_rebuild.learner.reference.
QReferenceView`, which also supplies the domain oracle a $Q$ edit is checked against. A
store that reached for its own reference would make the persistent state depend on a
global the experiment is supposed to control.

Canonical sparse overrides
--------------------------
Each store holds **only** deviations from the healthy reference, so the healthy state
is the empty state:

$$P_D^L = \varnothing, \qquad P_{\text{override}} = \varnothing, \qquad
X_{\text{override}} = \varnothing$$

$$C_P^L(z) = \begin{cases} P_{\text{override}}[z], & z \in P_{\text{override}}\\
z, & \text{otherwise}\end{cases}
\qquad
C_X^L(\text{site}) = \begin{cases} X_{\text{override}}[\text{site}],
& \text{site} \in X_{\text{override}}\\ \text{site.cmd}, & \text{otherwise}\end{cases}$$

**Assigning identity canonicalises to deletion**, and that is enforced at the
transaction boundary rather than by each caller:

$$C_P^L(z) \leftarrow z \;\Longrightarrow\; P_{\text{override}}.\text{pop}(z),
\qquad
C_X^L(\text{site}) \leftarrow \text{site.cmd} \;\Longrightarrow\;
X_{\text{override}}.\text{pop}(\text{site})$$

The point is not tidiness. A76 freezes
$\texttt{LocalOracleRestore} = P_{id}$ on $P$ and $= X_{id}$ on $X$; with a canonical
store that identity holds at the **backing-state** level, not merely "behaviourally
equivalent while an explicit identity entry lingers".

Snapshot, not live store
------------------------
A rollout reads a :class:`LearnerSnapshot` — an immutable view taken once. Reading a
live mutable mapping invites the episode to observe a write that happened halfway
through it, which would silently break both A76 invariants:

$$\text{all targets from the pre-update snapshot}, \qquad
\text{the future rollout reads the post-update state}$$

Transactions are atomic across all three stores
-----------------------------------------------
$$S_{\text{pre}} \xrightarrow{\text{validate all edits}} S_{\text{candidate}}
\xrightarrow{\text{single commit}} S_{\text{post}}$$

If any edit is illegal, $S_{\text{post}} = S_{\text{pre}}$ — never two applied and one
rejected. Two edits to the same store address in one transaction are **rejected**
rather than resolved last-write-wins, because A76 froze that no result may depend on
iteration or hash order.

:class:`StoreTransactionError` is a substrate typing/atomicity error. It is
**deliberately not** mapped onto A76's ``PROTOCOL_ERROR``: that mapping belongs to the
B1 runner/ledger layer, which does not exist yet.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from rfl_rebuild.env.domain import (
    is_decision_context,
    non_integer_state_fields,
)
from rfl_rebuild.env.kernel import (
    ACTIONS as _ACTIONS,
    Action,
    CommandProvider,
    ControlState,
    ControllerSite,
    LearnerContractViolation,
    ProcessCommitProvider,
    State,
    option_actions,
    option_ids as _option_ids,
    option_name,
)

__all__ = [
    "CONTROLLER",
    "DECISION",
    "PROCESS",
    "Q",
    "DecisionAddress",
    "Edit",
    "LearnerPersistentState",
    "LearnerSnapshot",
    "LearnerStateError",
    "QAddress",
    "ReferenceContractError",
    "StoreTransactionError",
    "is_option_id",
    "owner_Q",
]

DECISION = "decision"
PROCESS = "process"
CONTROLLER = "controller"
Q = "q"
_STORES = (DECISION, PROCESS, CONTROLLER, Q)


class StoreTransactionError(Exception):
    """A transaction is malformed or cannot be applied atomically.

    Substrate-level only. It says nothing about update-law semantics, and it is
    deliberately **not** A76's ``PROTOCOL_ERROR``.
    """


class LearnerStateError(Exception):
    """The persistent state is not a legal state for the architecture being built.

    Raised at **construction** time, before an adapter or an episode exists, and kept
    separate from :class:`StoreTransactionError` for the same reason the kernel keeps
    ``LearnerContractViolation`` separate from ``OptionViolation``: a handler for "this
    transaction was malformed" must not silently swallow "this architecture has no
    composition semantics".

    A77 §65.4: $D_{patch}$ and $D_Q$ are different architecture treatments, no legal
    experiment populates both decision stores, and **no priority between them is
    defined**. Their co-residence is refused rather than resolved.
    """


class ReferenceContractError(Exception):
    r"""The injected reference view is not a legal $D_Q$ reference.

    A substrate **contract** error, not a lookup miss: a missing row or action raises
    this rather than a bare ``KeyError``. The reference is validated once at
    construction, so an incomplete one fails stop at the boundary instead of surfacing
    from inside a rollout as an indexing accident.
    """


@dataclass(frozen=True, slots=True)
class DecisionAddress:
    r"""The typed store key for a decision context.

    This *is* A76's $\rho_D(\texttt{Decision}_t) = (s_t, z_t, m_t)$, given a name so
    that a bare ``(state, z, m)`` triple stops travelling through the codebase where
    it can be reordered by accident.
    """

    state: State
    z: int
    m: int


@dataclass(frozen=True, slots=True)
class QAddress:
    r"""The typed store key for one scalar entry of $Q_D^L$ (A77 §65.4).

    Strictly finer than the credited address, and deliberately a **distinct type**:

    | key | role |
    |---|---|
    | :class:`DecisionAddress` | the credited context, the ledger receipt, the budget unit |
    | :class:`QAddress` | one entry inside that context's row |

    so ``DualReturnWrite`` touching two entries is still **one** addressed context.
    """

    state: State
    z: int
    m: int
    a: int


def owner_Q(address: QAddress) -> DecisionAddress:
    r"""$owner_Q\bigl(\texttt{QAddress}(s,z,m,a)\bigr) = \texttt{DecisionAddress}(s,z,m)$.

    The address projection A77 §65.9's locality rule is stated through. It lives with
    the addresses rather than in the slice layer because it is a fact about the two key
    types, not about any update law.
    """
    return DecisionAddress(state=address.state, z=address.z, m=address.m)


@dataclass(frozen=True, slots=True)
class Edit:
    """One low-level change inside a transaction.

    ``value is None`` means **delete the override**, i.e. restore the healthy
    reference at that address. A non-``None`` value means set it — except that a value
    equal to the identity element is canonicalised to a deletion (see the module
    docstring).

    This is a *substrate* edit, not an update law: it carries no notion of why the
    change is being made.
    """

    store: str
    address: Any
    value: Any = None


class LearnerSnapshot:
    """An immutable read view of the persistent state, taken at one instant."""

    __slots__ = ("_decision", "_process", "_controller", "_q")

    def __init__(self, decision: Mapping, process: Mapping,
                 controller: Mapping, q: Mapping | None = None) -> None:
        self._decision = MappingProxyType(dict(decision))
        self._process = MappingProxyType(dict(process))
        self._controller = MappingProxyType(dict(controller))
        self._q = MappingProxyType(dict(q or {}))

    # -- read views ------------------------------------------------------- #
    @property
    def decision_overrides(self) -> Mapping:
        return self._decision

    @property
    def process_overrides(self) -> Mapping:
        return self._process

    @property
    def controller_overrides(self) -> Mapping:
        return self._controller

    @property
    def q_overrides(self) -> Mapping:
        """The sparse $Q_D^L$ overrides. An absent entry is **not** a zero value."""
        return self._q

    @property
    def healthy(self) -> bool:
        """True iff every store is at its healthy reference."""
        return not (self._decision or self._process or self._controller or self._q)

    def _require_decision_store_exclusive(self) -> None:
        r"""A77 §65.4's construction-time precondition, on **every** entry point.

        $$\boxed{P_D^L \neq \varnothing \;\wedge\; Q_D^L \neq \varnothing
        \;\Longrightarrow\; \texttt{PROTOCOL\_ERROR}}$$

        $D_{patch}$ and $D_Q$ are different architecture treatments and A77 defines **no
        priority** between them. This guard first lived only in the $Q$ adapter, which
        made the rule one-sided in a way that mattered: a co-resident snapshot could
        still be served by ``decision_provider``, which silently ignored $Q_D^L$ — and so
        *implemented* the undefined $P_D^L > Q_D^L$ rule it was supposed to refuse. Both
        adapters call this before returning anything.
        """
        if self._decision and self._q:
            raise LearnerStateError(
                "the persistent state holds both P_D^L and Q_D^L decision overrides; "
                "D_patch and D_Q are different architectures and A77 §65.4 defines no "
                "priority between them, so this state cannot drive either read path. "
                "Refused before the adapter is built, not when an address is visited")

    # -- the three adapters the kernel consumes --------------------------- #
    def decision_provider(self, base_provider: CommandProvider) -> CommandProvider:
        r"""$P_D^L >$ ``base_provider``.

        On a patch hit the base provider is **not called** — the same
        shadowed-channel discipline the kernel applies to ``C_P^L``: a channel that
        has been overridden must not have hidden side effects.

        **This adapter is also where the decision channel's contract is enforced.** It
        is the one place that knows whether an output came from a learner patch or
        from the ordinary base provider, so it can give them different exception
        types without the kernel needing a provenance flag:

        | source | illegal output raises |
        |---|---|
        | $P_D^L$ learner patch | :class:`LearnerContractViolation` |
        | ordinary base provider | ``OptionViolation`` (unchanged, A36) |
        | $do(d_t)$ / $Z_D$ | ``MalformedIntervention`` (unchanged) |

        Shadowing is automatically correct: ``rollout`` resolves
        $do(d_t) > Z_D > \text{command\_provider}$, so a shadowed patch adapter is
        never called and cannot raise early.

        The co-residence guard runs first: a state holding both decision stores is not a
        state this architecture can serve, and serving it would silently pick a winner.
        """
        self._require_decision_store_exclusive()

        def provider(state: State, control: ControlState) -> Action:
            addr = DecisionAddress(state=state, z=control.z, m=control.m)
            if addr in self._decision:
                a = self._decision[addr]
                # The base path is deliberately NOT checked here: a base provider
                # that escapes its option keeps raising OptionViolation.
                if not _is_action(a) or a not in option_actions(control.z, control,
                                                                state):
                    raise LearnerContractViolation(
                        f"a decision patch at {addr!r} holds {_action_name(a)}, which "
                        f"is not an action id inside A_z(m,s) for option "
                        f"{option_name(control.z)} (m={control.m})"
                    )
                return a
            return base_provider(state, control)

        return provider

    def q_decision_provider(self, reference) -> CommandProvider:
        r"""The $D_Q$ architecture's decision read path (A77 §65.4).

        $$a^L(x) = \arg\max_{a \in A_z(m,s)} Q^{\text{eff}}(x,a)
        \quad\text{(lowest action index on ties)}$$

        Four things are deliberate:

        * **no baseline-provider argument.** The healthy referent of this architecture
          *is* $Q_D^\ast$, which the injected view supplies, so the empty store
          reproduces $\pi_D^\ast$ by construction rather than by a fallback branch. A
          second provider would be a second source of the same policy, which is how two
          notions of "the factual action" start;
        * **the tie-break is the frozen one**: ascending action order with a strict
          comparison, matching ``dp.py``'s ``max(row, key=lambda a: (row[a], -a))``;
        * **co-residence is refused through the shared guard**, so this adapter and the
          patch adapter cannot disagree about which states are servable;
        * **the reference must be a real** :class:`~rfl_rebuild.learner.reference.
          QReferenceView`. Duck typing would let a mutable object with the right two
          methods stand in for the frozen, total, read-only view this contract is built
          on, which would leave the guarantees as properties of a helper class rather
          than of the substrate.
        """
        _require_q_reference(reference)
        self._require_decision_store_exclusive()
        overrides = self._q

        def provider(state: State, control: ControlState) -> Action:
            row = reference.row(state, control.z, control.m)
            best_a = None
            best_v = None
            for a in sorted(row):                 # ascending: first wins a tie
                v = overrides.get(QAddress(state=state, z=control.z, m=control.m, a=a),
                                  row[a])
                if best_v is None or v > best_v:
                    best_a, best_v = a, v
            return best_a

        return provider

    def process_commit_provider(self) -> ProcessCommitProvider:
        r"""$C_P^L$: an override when present, otherwise the identity."""

        def provider(z: int) -> int:
            return self._process.get(z, z)

        return provider

    def controller_mapping(self) -> Mapping[ControllerSite, Action]:
        r"""$C_X^L$ as the kernel's ``controller=`` mapping.

        Only overridden sites appear, so every other site falls through to the
        kernel's identity branch. The kernel's own contract check then decides whether
        an override is admissible.
        """
        return self._controller


class LearnerPersistentState:
    """The mutable, cross-episode backing state."""

    __slots__ = ("_decision", "_process", "_controller", "_q")

    def __init__(self) -> None:
        self._decision: dict[DecisionAddress, Action] = {}
        self._process: dict[int, int] = {}
        self._controller: dict[ControllerSite, Action] = {}
        self._q: dict[QAddress, float] = {}

    # -- reads ------------------------------------------------------------ #
    @property
    def decision_overrides(self) -> Mapping:
        return MappingProxyType(self._decision)

    @property
    def process_overrides(self) -> Mapping:
        return MappingProxyType(self._process)

    @property
    def controller_overrides(self) -> Mapping:
        return MappingProxyType(self._controller)

    @property
    def q_overrides(self) -> Mapping:
        r"""$Q_D^L$, sparse. Healthy is $\varnothing$, and $\varnothing$ is not zero."""
        return MappingProxyType(self._q)

    @property
    def healthy(self) -> bool:
        return not (self._decision or self._process or self._controller or self._q)

    def snapshot(self) -> LearnerSnapshot:
        """An immutable view. Later writes to this state do not affect it."""
        return LearnerSnapshot(self._decision, self._process, self._controller, self._q)

    def clone(self) -> "LearnerPersistentState":
        """An independent mutable state.

        A **deep** copy, not ``dict(...)``: the values are immutable scalars today, so a
        shallow copy would happen to be safe, and would stop being safe the moment a
        store value becomes a container.
        """
        other = LearnerPersistentState()
        other._decision = copy.deepcopy(self._decision)
        other._process = copy.deepcopy(self._process)
        other._controller = copy.deepcopy(self._controller)
        other._q = copy.deepcopy(self._q)
        return other

    # -- writing ---------------------------------------------------------- #
    def apply_transaction(self, edits: tuple[Edit, ...] | list[Edit], *,
                          q_reference=None) -> None:
        r"""Validate every edit, then commit once.

        $$\text{one illegal edit} \;\Longrightarrow\; S_{\text{post}} =
        S_{\text{pre}}$$

        Atomic across **all four** stores: one illegal $Q$ edit means an already-planned
        $D/P/X$ edit does not land either.

        Raises :class:`StoreTransactionError` before touching anything if an edit is
        malformed, if an address type does not match its store, if a $Q$ entry is
        outside the injected reference's domain, or if one transaction names the same
        store address twice.

        ``q_reference`` is the injected
        :class:`~rfl_rebuild.learner.reference.QReferenceView`, keyword-only and
        required as soon as a $Q$ edit is present. It supplies both halves of A77
        §65.4/§65.5's write contract:

        $$\operatorname{dom}(Q_D^L) \subseteq \operatorname{dom}(\texttt{QReferenceView}),
        \qquad Q_D^L(e) \leftarrow Q_D^\ast(e) \Longrightarrow \text{delete } e$$
        """
        edits = tuple(edits)

        # ---- validate, changing nothing --------------------------------- #
        # VALIDATE FIRST, then check for duplicate keys. The other order hashes the
        # address before it has been typed, so an unhashable bad address such as
        # `Edit(DECISION, [], RIGHT)` raised `TypeError: unhashable type: 'list'`
        # instead of the StoreTransactionError this method's contract promises --
        # the same "the error path itself crashes" defect as the kernel's old
        # `ACTIONS[u]`. After _validate_edit every surviving address is hashable.
        for e in edits:
            _validate_edit(e)
        _require_q_domain(edits, q_reference)

        seen: set[tuple[str, Any]] = set()
        for e in edits:
            key = (e.store, e.address)
            if key in seen:
                raise StoreTransactionError(
                    f"two edits target {e.store} address {e.address!r} in one "
                    "transaction; last-write-wins would make the result depend on "
                    "edit order, which A76 forbids"
                )
            seen.add(key)

        # ---- build the candidate, then commit once ---------------------- #
        cand_d = dict(self._decision)
        cand_p = dict(self._process)
        cand_c = dict(self._controller)
        cand_q = dict(self._q)
        for e in edits:
            if e.store == DECISION:
                if e.value is None:
                    cand_d.pop(e.address, None)
                else:
                    cand_d[e.address] = e.value
            elif e.store == PROCESS:
                # identity assignment canonicalises to deletion
                if e.value is None or e.value == e.address:
                    cand_p.pop(e.address, None)
                else:
                    cand_p[e.address] = e.value
            elif e.store == CONTROLLER:
                if e.value is None or e.value == e.address.cmd:
                    cand_c.pop(e.address, None)
                else:
                    cand_c[e.address] = e.value
            else:
                # Q: writing the reference value IS the identity assignment, so it
                # canonicalises to deletion for the same reason. A stored entry equal
                # to the reference would make the store non-canonical and, with
                # `float.hex()` accounting, would show up as a changed entry whose
                # delta is zero -- which is exactly what the ledger canary exists to
                # make impossible.
                if e.value is None or float(e.value) == q_reference.value(e.address):
                    cand_q.pop(e.address, None)
                else:
                    cand_q[e.address] = float(e.value)

        self._decision, self._process, self._controller, self._q = (
            cand_d, cand_p, cand_c, cand_q)


def _require_q_reference(reference) -> None:
    r"""The $Q$ boundary accepts the frozen view and nothing that resembles it.

    A77 §65.4 requires the reference to be **injected**; it does not say "injected or
    faked". Duck typing would let a mutable object exposing ``row``/``value``/``__contains__``
    stand in for a view whose guarantees are totality, finiteness and immutability, which
    would leave those guarantees as properties of a helper class rather than of the
    substrate. The same reasoning upgraded the law API from a convention to a fail-stop.

    The import is deferred because :mod:`~rfl_rebuild.learner.reference` imports this
    module for :class:`QAddress` and :class:`ReferenceContractError`.
    """
    from rfl_rebuild.learner.reference import QReferenceView
    if type(reference) is not QReferenceView:
        raise ReferenceContractError(
            f"the Q boundary requires a QReferenceView, got {type(reference).__name__}; "
            "a duck-typed stand-in would carry none of the totality, finiteness or "
            "read-only guarantees the injected reference is validated for (A77 §65.4)")


def _require_q_domain(edits: tuple, q_reference) -> None:
    r"""Domain closure for $Q$ edits (A77 §65.5).

    $$\boxed{\operatorname{dom}(Q_D^L) \subseteq
    \operatorname{dom}(\texttt{QReferenceView})}$$

    An entry that is well-typed but outside the reference domain would change the
    fingerprint and clear ``healthy`` while the read path never consulted it — the $Q$
    version of the ``P_override[99] = 1`` defect the process store already had to be
    closed against. It is rejected here, at the transaction boundary, along with the
    typed-address and duplicate-key checks; the read path is not asked to defend itself.
    """
    q_edits = [e for e in edits if e.store == Q]
    if not q_edits:
        return
    if q_reference is None:
        raise StoreTransactionError(
            "a Q edit requires the injected reference view: it supplies both the domain "
            "the entry must lie in and the value that canonicalises to a deletion "
            "(A77 §65.4). Nothing in the substrate fetches a reference for itself")
    _require_q_reference(q_reference)
    for e in q_edits:
        if e.address not in q_reference:
            raise StoreTransactionError(
                f"the Q entry {e.address!r} is outside the reference domain; a stored "
                "entry the read path can never reach would change the fingerprint and "
                "clear `healthy` while being invisible in behaviour")


def _validate_edit(e: Edit) -> None:
    """Static type and domain check. **Not** an admissibility or locality check.

    The substrate answers "is this a well-typed edit"; it does not answer "should
    this address be written". Reachability and credit locality belong to
    $\\rho_A$/B1, and keeping the two apart is what stops a substrate bug being
    mistaken for a locality bug.
    """
    if e.store not in _STORES:
        raise StoreTransactionError(
            f"unknown store {e.store!r}; expected one of {_STORES}")
    if e.store == DECISION:
        _require_decision_address(e.address)
        if e.value is not None and not _is_action(e.value):
            raise StoreTransactionError(
                f"a decision override must be an action id, got {e.value!r}")
    elif e.store == PROCESS:
        if not is_option_id(e.address):
            raise StoreTransactionError(
                f"the process store is keyed by an option id, got {e.address!r}")
        if e.value is not None and not is_option_id(e.value):
            # Without this the store accepted any int, so `P_override[99] = 1` could
            # never be reached by a legal z^proposal yet still made `healthy` False --
            # a persistent defect invisible in behaviour.
            raise StoreTransactionError(
                f"a process override must be an option id, got {e.value!r}")
    elif e.store == Q:
        _require_q_address(e.address)
        if e.value is not None and not _is_finite_real(e.value):
            # `bool` is an `int` subclass, so without the exclusion `True` would pass
            # for 1.0 and the fingerprint would carry a type the value domain does not
            # have; NaN and infinities would make `fp_pre == fp_post` depend on
            # comparison semantics rather than on content.
            raise StoreTransactionError(
                f"a Q override must be a finite real, got {e.value!r}")
    else:
        _require_controller_site(e.address)
        if e.value is not None and not _is_action(e.value):
            raise StoreTransactionError(
                f"a controller override must be an action id, got {e.value!r}")


def _require_decision_address(addr: object) -> None:
    if not isinstance(addr, DecisionAddress):
        raise StoreTransactionError(
            f"the decision store is keyed by DecisionAddress, got "
            f"{type(addr).__name__}")
    # The dataclass itself validates nothing, so `DecisionAddress(state="oops",
    # z=99, m="x")` is a well-formed instance of the type and would otherwise be
    # stored. Its fields are checked here.
    if not isinstance(addr.state, State):
        raise StoreTransactionError(
            f"DecisionAddress.state must be a State, got {addr.state!r}")
    if not is_option_id(addr.z):
        raise StoreTransactionError(
            f"DecisionAddress.z must be an option id, got {addr.z!r}")
    if not _is_int(addr.m):
        raise StoreTransactionError(
            f"DecisionAddress.m must be an integer, got {addr.m!r}")


def _require_controller_site(site: object) -> None:
    if not isinstance(site, ControllerSite):
        raise StoreTransactionError(
            f"the controller store is keyed by ControllerSite, got "
            f"{type(site).__name__}")
    if not isinstance(site.state, State):
        raise StoreTransactionError(
            f"ControllerSite.state must be a State, got {site.state!r}")
    if not _is_action(site.cmd):
        raise StoreTransactionError(
            f"ControllerSite.cmd must be an action id, got {site.cmd!r}")


def _require_q_address(addr: object) -> None:
    r"""Type the Q key, **including the fields of its** ``State``.

    The first version checked ``isinstance(addr.state, State)`` and stopped there, so
    ``QAddress(state=State(x=1.0, ...), ...)`` was a legal key. It then reached
    ``e.address in q_reference``, whose lookup is a dict comparison — and because Python
    folds ``1.0 == 1`` with equal hashes, the malformed key *hit a legal reference row*
    and the entry persisted. That is the shortest path from a type error to a stored
    value, and it runs through value equality, which is why the domain predicate is
    type-strict (A77 §65.5).
    """
    if not isinstance(addr, QAddress):
        raise StoreTransactionError(
            f"the Q store is keyed by QAddress, got {type(addr).__name__}")
    if type(addr.state) is not State:
        raise StoreTransactionError(
            f"QAddress.state must be a State, got {addr.state!r}")
    bad = non_integer_state_fields(addr.state)
    if bad:
        raise StoreTransactionError(
            f"QAddress.state has non-integer field(s) {bad}: {addr.state!r}. Python "
            "folds 1.0, True and 1 into one dict key, so this address would match a "
            "legal reference row while not being one")
    if not is_decision_context(addr.state, addr.z, addr.m):
        raise StoreTransactionError(
            f"QAddress {addr!r} is not a legal decision context: z and m must be true "
            "integers inside their domains and (x, y, t, kappa, phi) a legal state")
    if type(addr.a) is not int or not 0 <= addr.a < len(_ACTIONS):
        raise StoreTransactionError(
            f"QAddress.a must be a true action id, got {addr.a!r}")


def _is_finite_real(v: object) -> bool:
    """A finite real number. ``bool`` is excluded; so are NaN and both infinities."""
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v))


def _is_int(v: object) -> bool:
    """A true integer id — ``bool`` excluded, echoing the kernel's own guard."""
    return isinstance(v, int) and not isinstance(v, bool)


def is_option_id(v: object) -> bool:
    r"""$\text{true integer} \land v \in \texttt{option\_ids()}$.

    The runtime $C_P^L$ contract still lets an *external* provider return anything
    and have the kernel raise ``LearnerContractViolation``; this predicate is about
    what our own canonical store is willing to persist.
    """
    return _is_int(v) and v in _option_ids()


def _is_action(v: object) -> bool:
    return _is_int(v) and 0 <= v < len(_ACTIONS)


def _action_name(a: object) -> str:
    """Render an action for a message **without** indexing out of range."""
    return _ACTIONS[a] if _is_action(a) else repr(a)
