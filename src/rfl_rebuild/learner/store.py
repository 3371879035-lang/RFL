r"""The persistent learner state, its snapshot, and its transaction.

Three stores make up :math:`W^L = (P_D^L, C_P^L, C_X^L)`. There is **no** ``Q_D^L``
here: an empty stub would later be mistaken for frozen Q semantics.

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
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from rfl_rebuild.env.kernel import (
    Action,
    CommandProvider,
    ControlState,
    ControllerSite,
    ProcessCommitProvider,
    State,
)

__all__ = [
    "DecisionAddress",
    "Edit",
    "LearnerPersistentState",
    "LearnerSnapshot",
    "StoreTransactionError",
]

DECISION = "decision"
PROCESS = "process"
CONTROLLER = "controller"
_STORES = (DECISION, PROCESS, CONTROLLER)


class StoreTransactionError(Exception):
    """A transaction is malformed or cannot be applied atomically.

    Substrate-level only. It says nothing about update-law semantics, and it is
    deliberately **not** A76's ``PROTOCOL_ERROR``.
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

    __slots__ = ("_decision", "_process", "_controller")

    def __init__(self, decision: Mapping, process: Mapping,
                 controller: Mapping) -> None:
        self._decision = MappingProxyType(dict(decision))
        self._process = MappingProxyType(dict(process))
        self._controller = MappingProxyType(dict(controller))

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
    def healthy(self) -> bool:
        """True iff every store is at its healthy reference."""
        return not (self._decision or self._process or self._controller)

    # -- the three adapters the kernel consumes --------------------------- #
    def decision_provider(self, base_provider: CommandProvider) -> CommandProvider:
        r"""$P_D^L >$ ``base_provider``.

        On a patch hit the base provider is **not called** — the same
        shadowed-channel discipline the kernel now applies to ``C_P^L``: a channel
        that has been overridden must not have hidden side effects.
        """

        def provider(state: State, control: ControlState) -> Action:
            hit = self._decision.get(DecisionAddress(state=state, z=control.z,
                                                     m=control.m))
            if hit is not None:
                return hit
            return base_provider(state, control)

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

    __slots__ = ("_decision", "_process", "_controller")

    def __init__(self) -> None:
        self._decision: dict[DecisionAddress, Action] = {}
        self._process: dict[int, int] = {}
        self._controller: dict[ControllerSite, Action] = {}

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
    def healthy(self) -> bool:
        return not (self._decision or self._process or self._controller)

    def snapshot(self) -> LearnerSnapshot:
        """An immutable view. Later writes to this state do not affect it."""
        return LearnerSnapshot(self._decision, self._process, self._controller)

    def clone(self) -> "LearnerPersistentState":
        """An independent mutable state.

        A **deep** copy, not ``dict(...)``: the values are immutable ints today, so a
        shallow copy would happen to be safe, and would stop being safe the moment a
        store value becomes a container.
        """
        other = LearnerPersistentState()
        other._decision = copy.deepcopy(self._decision)
        other._process = copy.deepcopy(self._process)
        other._controller = copy.deepcopy(self._controller)
        return other

    # -- writing ---------------------------------------------------------- #
    def apply_transaction(self, edits: tuple[Edit, ...] | list[Edit]) -> None:
        r"""Validate every edit, then commit once.

        $$\text{one illegal edit} \;\Longrightarrow\; S_{\text{post}} =
        S_{\text{pre}}$$

        Raises :class:`StoreTransactionError` before touching anything if an edit is
        malformed, if an address type does not match its store, or if one transaction
        names the same store address twice.
        """
        edits = tuple(edits)

        # ---- validate, changing nothing --------------------------------- #
        seen: set[tuple[str, Any]] = set()
        for e in edits:
            if e.store not in _STORES:
                raise StoreTransactionError(
                    f"unknown store {e.store!r}; expected one of {_STORES}")
            key = (e.store, e.address)
            if key in seen:
                raise StoreTransactionError(
                    f"two edits target {e.store} address {e.address!r} in one "
                    "transaction; last-write-wins would make the result depend on "
                    "edit order, which A76 forbids"
                )
            seen.add(key)
            _validate_edit(e)

        # ---- build the candidate, then commit once ---------------------- #
        cand_d = dict(self._decision)
        cand_p = dict(self._process)
        cand_c = dict(self._controller)
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
            else:
                if e.value is None or e.value == e.address.cmd:
                    cand_c.pop(e.address, None)
                else:
                    cand_c[e.address] = e.value

        self._decision, self._process, self._controller = cand_d, cand_p, cand_c


def _validate_edit(e: Edit) -> None:
    if e.store == DECISION:
        if not isinstance(e.address, DecisionAddress):
            raise StoreTransactionError(
                f"the decision store is keyed by DecisionAddress, got "
                f"{type(e.address).__name__}")
        if e.value is not None and not _is_action(e.value):
            raise StoreTransactionError(
                f"a decision override must be an action id, got {e.value!r}")
    elif e.store == PROCESS:
        if not _is_int(e.address):
            raise StoreTransactionError(
                f"the process store is keyed by an option id, got {e.address!r}")
        if e.value is not None and not _is_int(e.value):
            raise StoreTransactionError(
                f"a process override must be an option id, got {e.value!r}")
    else:
        if not isinstance(e.address, ControllerSite):
            raise StoreTransactionError(
                f"the controller store is keyed by ControllerSite, got "
                f"{type(e.address).__name__}")
        if e.value is not None and not _is_action(e.value):
            raise StoreTransactionError(
                f"a controller override must be an action id, got {e.value!r}")


def _is_int(v: object) -> bool:
    """A true integer id — ``bool`` excluded, echoing the kernel's own guard."""
    return isinstance(v, int) and not isinstance(v, bool)


def _is_action(v: object) -> bool:
    from rfl_rebuild.env.kernel import ACTIONS
    return _is_int(v) and 0 <= v < len(ACTIONS)
