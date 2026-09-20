r"""A76 §63.9 / A77 §65.3, §65.8, §65.9 — the $D_{patch}$ arms.

Four registered arms, **three independent treatments**:

| arm | kind | tier |
|---|---|---|
| `NoWrite` | reference | `L0_FACTUAL` |
| `DeleteFactualPatch` | independent operation | `L0_FACTUAL` |
| `SetAlternative` | independent operation | `L1_CORRECTIVE` |
| `LocalOracleRestore` | $L_3$ **alias of `DeleteFactualPatch`** | `L3_ORACLE` |

$$\boxed{\texttt{LocalOracleRestore} \equiv \texttt{DeleteFactualPatch}
\quad\text{on } D_{patch}}$$

so it is an alias and not a second implementation: same transaction, same post-state,
same per-address statuses, same ledger cost, and the alias test asserts ``plan`` is the
*same function object*.

A law plans from the credited addresses and — only for a tier that delivers fields — the
projected envelope, and returns one **address-plan** per credited context:

$$\boxed{\texttt{plan}(addresses,\ targets)\quad\text{— and nothing else}}$$

**A law is handed no store view at all**: not the persistent state, not a snapshot, not a
store mapping. A76 §63.1 lets a primitive read *its own* store; being handed the whole
learner snapshot gave a $D$ law an independent handle on $P_D^L$, $C_P^L$ and $C_X^L$ at
once — A59's shape. A later $D_Q$ law that genuinely needs to read the $D$ store gets a
dedicated decision-only view, never the snapshot back.

The plan structure is A77 §65.9's **address-plan**: one per credited context, carrying
$0..k$ entry edits, and exactly one ledger receipt between them:

$$\boxed{\{\text{Plan}.\text{address}\} = \text{the credited addresses, each exactly once}}$$

On this architecture $k \le 1$, and that is not a special case: two entry edits at one
context would be two edits to the *same* entry address, which the duplicate rule rejects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from rfl_rebuild.b1.contract import NO_VALID_ALTERNATIVE, ProtocolError
from rfl_rebuild.b1.plan import RestoreRow, dq_owner
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.learner.store import (
    CONTROLLER,
    DECISION,
    Q,
    DecisionAddress,
    Edit,
    QAddress,
)

__all__ = [
    "DQ_LAWS",
    "LAWS",
    "AddressPlan",
    "CounterfactualReturnWrite",
    "XId",
    "XLocalOracleRestore",
    "X_LAWS",
    "DQLocalOracleRestore",
    "DeleteFactualPatch",
    "DualReturnWrite",
    "FactualReturnWrite",
    "LawPlan",
    "LocalOracleRestore",
    "NoWrite",
    "NoWriteRef",
    "RestoreRow",
    "dq_owner",
    "SetAlternative",
    "independent_treatment_count",
    "law_metadata",
]


@dataclass(frozen=True, slots=True)
class AddressPlan:
    r"""One credited context's planned outcome (§65.9).

    Exactly one of four shapes is legal:

    | ``edits`` | ``row_op`` | ``status`` | meaning |
    |---|---|---|---|
    | non-empty | ``None`` | ``None`` | entry edits at this context |
    | empty | ``None`` | ``None`` | an ordinary ``EVALUABLE_NOOP`` |
    | empty | ``None`` | ``NO_VALID_ALTERNATIVE`` | a legitimate absence of a target |
    | empty | a ``RestoreRow`` | ``None`` | a row-scoped structural operation |

    Anything else is a :class:`ProtocolError`. The edits field is a *tuple* rather than a
    single edit because A77 §65.9 froze the address-plan as the unit, and on $D_Q$ one
    context carries two entries (`DualReturnWrite`) while still producing one receipt.

    **Either entry edits or one row operation, never both** — §65.9's rule, enforced here
    at construction because it is a property of the plan object and not of who reads it.
    Two row operations are the same rule's other half: the field is not a tuple, so a
    second one cannot be expressed.
    """

    address: object
    edits: tuple[Edit, ...] = ()
    status: str | None = None
    row_op: RestoreRow | None = None

    def __post_init__(self) -> None:
        if self.row_op is not None:
            # NOMINAL closure, the same way `Tier`, `QReferenceView` and the typed domain
            # are closed: "an object with a `.context`" must not be able to grant
            # row-restore capability. Duck typing here would let any stand-in reach
            # `_lower_row_ops` -- which only ever asks for `.context` -- and become a real
            # row restore.
            if type(self.row_op) is not RestoreRow:
                raise ProtocolError(
                    f"the address-plan for {self.address!r} carries row_op="
                    f"{self.row_op!r} of type {type(self.row_op).__name__}; the row "
                    "operation is exactly RestoreRow, and a stand-in exposing a matching "
                    "attribute is not one")
            if self.edits:
                raise ProtocolError(
                    f"the address-plan for {self.address!r} carries both entry edits and "
                    f"{self.row_op!r}; an address-plan contains either entry edits or one "
                    "row operation, never both (A77 §65.9)")
            if self.status is not None:
                raise ProtocolError(
                    f"the address-plan for {self.address!r} carries a row operation and "
                    f"the declared status {self.status!r}; a row operation is always "
                    "evaluable, so a status beside it would be a second, conflicting "
                    "description of the same outcome")
            if self.row_op.context != self.address:
                raise ProtocolError(
                    f"the address-plan for {self.address!r} carries a row operation on "
                    f"{self.row_op.context!r}; the operation must name the context whose "
                    "plan it is, or owner locality would be asserted about a different "
                    "row than the one being restored")


@dataclass(frozen=True, slots=True)
class LawPlan:
    """A law's whole plan for one scene. The runner commits it in ONE transaction."""

    name: str
    plans: tuple[AddressPlan, ...]

    @property
    def edits(self) -> tuple[Edit, ...]:
        return tuple(e for p in self.plans for e in p.edits)


class _Law:
    r"""Base class. Subclasses implement ``plan`` and never see the store itself.

    ``tier`` is the **information tier** (A76 §63.1, A77 §65.1). The base value is the
    sentinel ``None``, meaning **NOT DECLARED**, and the runner accepts only a real
    :class:`~rfl_rebuild.b1.tier.Tier`:

    $$\\boxed{\\texttt{\\_Law.tier = None}}$$

    An earlier base value was ``requires_alternative = False``, so a subclass that forgot
    to declare its tier silently inherited the **lowest** tier — the exact outcome the
    check exists to prevent, and invisible in the ledger. The ``_NoTier`` test looked like
    it covered this but its class did not inherit ``_Law`` at all, so it tripped
    ``hasattr`` and the real case was never exercised.

    The tier decides **delivery**, not merely expectation: a law whose cell declares no
    field is never handed an object at all, and one whose cell is ill-typed cannot be
    declared. Handing an envelope to a law and trusting it not to look would repeat A59's
    lesson: *the method did not read the higher-tier information* does not imply *the
    runner did not first condition it on that information*.

    ``plan`` takes **exactly** ``(addresses, targets)``; the runner enforces the
    signature, so a law cannot re-acquire a store handle by adding a parameter.
    """

    name = "?"
    alias_of: str | None = None
    tier: Tier | None = None                      # None == NOT DECLARED

    def plan(self, addresses: Sequence[DecisionAddress],
             targets: "Mapping[DecisionAddress, Mapping[str, object]] | None") -> LawPlan:
        raise NotImplementedError                # pragma: no cover - abstract

    def __repr__(self) -> str:
        return f"<law {self.name}>"


class NoWriteRef(_Law):
    r"""The same-tier **reference**: propose nothing, whatever the cell delivers.

    A77 §65.3 requires the reference to be an *object in the cell*, not a convention: a
    single law fixed at $L_0$ cannot be the $L_2$ reference, and "the tier is recorded per
    arm" needs something to record it on. All instances therefore share **one** no-op plan
    function object and differ only in the tier they declare:

    $$\boxed{\text{the tier is what makes them distinct; the behaviour is what makes them one}}$$

    They are references and never treatments, so they do not increase
    :func:`independent_treatment_count`. One instance is instantiated per cell that has a
    substantive treatment, which is why the empty $L_1$ cell of a scalar architecture has
    no reference at all.
    """

    name = "NoWrite"
    alias_of = None

    def __init__(self, tier: Tier | None = None) -> None:
        # Omitted means "use the tier this class declares", which is how the registered
        # arm works; passing one declares an instance tier. An instance that ends up with
        # no tier at all keeps the base sentinel and is rejected by the runner.
        if tier is not None:
            self.tier = tier

    def plan(self, addresses, targets) -> LawPlan:
        return LawPlan(self.name, tuple(AddressPlan(a) for a in addresses))


class NoWrite(NoWriteRef):
    r"""The registered reference of this architecture's cell.

    Every credited address is ``EVALUABLE_NOOP`` — not ``APPLIED``: the law ran and
    correctly changed nothing, which is a different statement from a write having been
    committed. This *is* $\texttt{NoWriteRef}(L_0^{\text{factual}})$ on $D_{patch}$; it
    keeps its own name because the arm table and :func:`law_metadata` are part of the
    surface the refactor must not move.
    """

    name = "NoWrite"
    tier = Tier.L0_FACTUAL


class DeleteFactualPatch(_Law):
    r"""$L_0$: delete the factual patch at each credited address.

    A **total** operation. Where a patch exists the transaction changes the store
    (``APPLIED``); where none exists it is a no-op (``EVALUABLE_NOOP``), never an
    evaluability failure — in regime T every address is patchless, so treating that as
    a failure would selectively exclude the whole regime.
    """

    name = "DeleteFactualPatch"
    tier = Tier.L0_FACTUAL

    def plan(self, addresses, targets) -> LawPlan:
        return LawPlan(
            self.name,
            tuple(AddressPlan(a, (Edit(DECISION, a, None),)) for a in addresses),
        )


class SetAlternative(_Law):
    r"""$L_1$: write the verified alternative $a^+$ at each credited address.

    * a valid $a^+$ exists → plan the write; if the patch already holds exactly
      $a^+$ the transaction leaves the store unchanged and the status is
      ``EVALUABLE_NOOP``, derived from the store rather than special-cased here;
    * a **verified** absence of $a^+$ → no edit, status ``NO_VALID_ALTERNATIVE``, and
      the other addresses are unaffected;
    * a **missing** target record, or no envelope at all, is not handled here at all —
      the runner raises :class:`ProtocolError` before any law runs.

    The law reads ``targets[a]["alternative"]``: the cell's declared field set, not the
    evaluator-side record. ``factual_command`` exists for validation and is not delivered
    content.
    """

    name = "SetAlternative"
    tier = Tier.L1_CORRECTIVE

    def plan(self, addresses, targets) -> LawPlan:
        plans = []
        for a in addresses:
            alt = targets[a]["alternative"]
            if alt is None:
                plans.append(AddressPlan(a, (), NO_VALID_ALTERNATIVE))
            else:
                plans.append(AddressPlan(a, (Edit(DECISION, a, alt),)))
        return LawPlan(self.name, tuple(plans))


class LocalOracleRestore(DeleteFactualPatch):
    r"""$L_3$ on $D_{patch}$ — an **alias** of :class:`DeleteFactualPatch`.

    Implemented by *inheritance*, not by a second ``plan``: the operation exists once and
    this class only carries the alias metadata. The earlier version wrote
    ``LocalOracleRestore = DeleteFactualPatch`` and then set ``.name`` on it, which
    mutated the shared class — ``DeleteFactualPatch`` lost its own name, the registry
    contained ``LocalOracleRestore`` twice, and the independent-treatment count came out
    as 2. The alias test asserts ``plan`` is the *same function object*.

    Its tier is $L_3$ while its behaviour is $L_0$'s, and that is not an inconsistency to
    paper over: on a value-free store the healthy referent *is* "no override", so the
    $L_3$ restore canonicalises to a deletion. A77 §65.2 gives this cell
    $\text{fields}=\varnothing$, so the arm is handed nothing — the same delivery as
    $L_0$'s, with a different semantic authorisation.
    """

    name = "LocalOracleRestore"
    alias_of = "DeleteFactualPatch"
    tier = Tier.L3_ORACLE


class DQLocalOracleRestore(_Law):
    r"""$D_Q\times L_3$ — restore the credited context's whole row to $Q_D^\ast$.

    $$\boxed{L_3:\ \text{delete every override in the credited context's row}}$$

    An **independent implementation**, not the $D_{patch}$ alias (A78 §66.7). The alias
    shares `DeleteFactualPatch`'s `plan` function object and emits `DECISION` edits, which
    is correct on a value-free store and impossible here. It may keep the display name, and
    it registers only in the $D_Q$ registry.

    The delivery is empty — $\text{fields}(D_Q,L_3)=\varnothing$ (§65.2) — so the law reads
    nothing: it needs no $a^+$ (which is why its domain is **every** credited address, not
    the ones that happen to have an alternative, A78 §66.3) and no reference, because the
    row returns to $Q_D^\ast$ by deletion rather than by writing its values.

    It emits one symbolic row operation per address and lets the slice lower it. Lowering
    is the runner's pre-commit phase, so the law never sees the pre-state and cannot depend
    on when it is called.
    """

    name = "LocalOracleRestore"
    tier = Tier.L3_ORACLE

    def plan(self, addresses, targets) -> LawPlan:
        return LawPlan(self.name, tuple(AddressPlan(a, row_op=RestoreRow(a))
                                        for a in addresses))


class FactualReturnWrite(_Law):
    r"""$D_Q\times L_0$ — write the factual suffix return at the factual action.

    $$\boxed{Q_D^L(x_t, a_t^F) \leftarrow G_t^F}$$

    $\alpha = 1$ (full backup): B1 studies *target and write semantics*, and an arbitrary
    $\alpha$ would introduce a second, unstudied question. $\alpha < 1$ is a secondary
    sensitivity study and may never pick a winner or rescue a primary result.

    Three things this law is not:

    * **not an oracle.** The target is the *observed* suffix return $G_t^F$, never
      $Q_D^\ast(x_t,a_t^F)$. On a faulted trajectory they differ, and that difference is
      the entire content of the update; substituting the reference would make an $L_0$ law
      silently evaluator-assisted;
    * **not information-wide.** It reads exactly the two fields its cell declares,
      $a_t^F$ and $G_t^F$ (A77 §65.2). Neither $a_t^+$ nor $G_t^{CF}$ is delivered to it,
      and the runner would refuse to deliver them;
    * **not multi-entry.** One credited `DecisionAddress`, one entry
      $Q_D^L(x_t,a_t^F)$, one receipt — under `owner_Q` locality.
    """

    name = "FactualReturnWrite"
    tier = Tier.L0_FACTUAL

    def plan(self, addresses, targets) -> LawPlan:
        plans = []
        for a in addresses:
            rec = targets[a]
            entry = QAddress(state=a.state, z=a.z, m=a.m, a=rec["a_factual"])
            plans.append(AddressPlan(a, (Edit(Q, entry, rec["g_factual"]),)))
        return LawPlan(self.name, tuple(plans))


class CounterfactualReturnWrite(_Law):
    r"""$D_Q\times L_2$ — write the counterfactual return at the verified alternative.

    $$\boxed{Q_D^L(x_t, a_t^+) \leftarrow G_t^{CF}(a_t^+)}$$

    One entry, one address, one receipt. Where no verified alternative exists the address
    carries ``NO_VALID_ALTERNATIVE`` and nothing is written — A76 §63.3's live guard, whose
    three-way distinction exists so that "there was no alternative" is not read as "the
    method chose not to write".
    """

    name = "CounterfactualReturnWrite"
    tier = Tier.L2_COUNTERFACTUAL

    def plan(self, addresses, targets) -> LawPlan:
        plans = []
        for a in addresses:
            rec = targets[a]
            if rec["a_plus"] is None:
                plans.append(AddressPlan(a, (), NO_VALID_ALTERNATIVE))
            else:
                entry = QAddress(state=a.state, z=a.z, m=a.m, a=rec["a_plus"])
                plans.append(AddressPlan(a, (Edit(Q, entry, rec["g_cf"]),)))
        return LawPlan(self.name, tuple(plans))


class DualReturnWrite(_Law):
    r"""$D_Q\times L_2$ — both targets, one addressed context, one transaction.

    $$\boxed{Q_D^L(x_t,a_t^F) \leftarrow G_t^F, \qquad
    Q_D^L(x_t,a_t^+) \leftarrow G_t^{CF}(a_t^+)}$$

    Both targets are computed from the **same pre-update state** and committed together.
    Writing the factual entry first and letting the second target observe the modified
    store is prohibited — that would make this sequential learning rather than a
    comparison of two target semantics, which is the arm's entire content. The
    enforcement is structural: the runner plans before it commits, and a scene commits
    once.

    **It does not degenerate at an address.** Where $a_t^+$ is absent the factual half is
    *not* written either: A76 §63.3 freezes "$a^+$ is required but absent ⇒ no write was
    planned" and adds that a law may not degenerate at the same address — "above all
    `DualReturnWrite` must not commit only its factual half". A half-applied Dual is a
    different treatment wearing its name.

    Two entries, **one** `DecisionAddress` receipt, and
    $N_{\text{scalar}} \le 2$ at that context — the first arm for which that bound says
    anything.
    """

    name = "DualReturnWrite"
    tier = Tier.L2_COUNTERFACTUAL

    def plan(self, addresses, targets) -> LawPlan:
        plans = []
        for a in addresses:
            rec = targets[a]
            if rec["a_plus"] is None:
                plans.append(AddressPlan(a, (), NO_VALID_ALTERNATIVE))
                continue
            factual = QAddress(state=a.state, z=a.z, m=a.m, a=rec["a_factual"])
            alternative = QAddress(state=a.state, z=a.z, m=a.m, a=rec["a_plus"])
            if factual == alternative:
                raise ProtocolError(
                    f"the factual action and the verified alternative coincide at {a!r}; "
                    "an alternative equal to the factual command is not an alternative, "
                    "and writing one entry twice would be order-dependent")
            plans.append(AddressPlan(a, (Edit(Q, factual, rec["g_factual"]),
                                         Edit(Q, alternative, rec["g_cf"]))))
        return LawPlan(self.name, tuple(plans))


class XId(_Law):
    r"""$X\times L_0$ — write the factual command into the controller at each credited site.

    $$\boxed{C_X^L\bigl(\rho_X(\texttt{ControllerSite})\bigr) \leftarrow a^{cmd}}$$

    The law reads exactly the field its cell declares, $\{a^{cmd}\}$ (A77 §65.2, A80 §68.3). The
    option in force, the site's $z$ and $m$, and the check $a^{cmd} \in A_z(m,s)$ all happen
    **before** this is called: they are cell-construction work (A80 §68.4), and a law that could
    read them would hold option geometry it was never granted.

    A healthy scene writes the identity — $C_X$ already maps this site to this command — so the
    store's canonicalisation turns the write into a deletion. That is what makes $L_3$'s restore
    the *same operation* rather than a second implementation that happens to agree.
    """

    name = "X_id"
    tier = Tier.L0_FACTUAL

    def plan(self, addresses, targets) -> LawPlan:
        r"""The identity write, read from the **credited address** rather than the envelope.

        $$oxed{site.cmd = a^{cmd}}$$

        A `ControllerSite` *is* $(s_t, a^{cmd}_t)$ (A76 §63.10's $ho_X$), so the operation's
        identity is carried by the address it is credited at. The $L_0$ envelope still delivers
        $\{a^{cmd}\}$ — the cell's field set is unchanged — and the runner still checks that
        delivery against the address; what this plan does **not** do is depend on it.

        That separation is the whole reason the $L_3$ alias is a real one: with
        $	ext{fields}(X,L_3)=arnothing$ there is no envelope at all, and a plan that read
        `targets[site]` could not run there. Reading the *address* means one function serves both
        cells with no tier branch:

        $$oxed{	ext{credited-address identity} 
eq 	ext{cell information delivery}}$$

        And the write is the restore, on any pre-state, not only a healthy one: the store
        canonicalises $u = site.cmd$ to a deletion, so
        $\texttt{Apply}(S, \texttt{Edit}(X, site, site.cmd)) = \texttt{Apply}(S,
        \texttt{Edit}(X, site, \bot))$ — which is A76 §63.8's frozen
        $\texttt{LocalOracleRestore} = X_{id}$ as an equality of state transformations.
        """
        return LawPlan(self.name, tuple(
            AddressPlan(site, (Edit(CONTROLLER, site, site.cmd),))
            for site in addresses))


class XLocalOracleRestore(XId):
    r"""$X\times L_3$ — the locality-matched restore, an **alias** of `X_id`.

    Implemented by inheritance, not by a second `plan`: $L_3$'s referent on this architecture is
    "no override", and the identity write canonicalises to a deletion, so the $L_0$ operation *is*
    the restore. A77 §65.2's alias precedent, applied: the gate asserts
    `XLocalOracleRestore.plan is XId.plan`, because a second implementation that behaved
    identically would be a different object with the same name.

    It is an **alias, not a treatment**: $\lvert\text{independent treatments}\rvert(X) = 1$.
    """

    name = "LocalOracleRestore"
    alias_of = "X_id"
    tier = Tier.L3_ORACLE


#: The $X$ registry: one treatment and its $L_3$ alias, with a same-tier reference per cell that
#: has a substantive treatment (A77 §65.3). $L_1$/$L_2$ are ill-typed on this row (A76 §63.9), so
#: they get neither a law nor a reference.
X_LAWS = (
    NoWriteRef(Tier.L0_FACTUAL),
    XId,
    NoWriteRef(Tier.L3_ORACLE),
    XLocalOracleRestore,
)


#: Registration order is fixed so arm enumeration is deterministic.
LAWS = (NoWrite, DeleteFactualPatch, SetAlternative, LocalOracleRestore)

#: The $D_Q$ registry, complete for A77 §65.12's order as extended by A78 §66.1: one
#: reference per cell with a substantive treatment (§65.3), plus the treatments themselves.
#: Four independent treatments, the number A76 §63.8 froze.
DQ_LAWS = (
    NoWriteRef(Tier.L0_FACTUAL),
    FactualReturnWrite,
    NoWriteRef(Tier.L2_COUNTERFACTUAL),
    CounterfactualReturnWrite,
    DualReturnWrite,
    NoWriteRef(Tier.L3_ORACLE),
    DQLocalOracleRestore,
)


def _kind(law) -> str:
    """``reference`` / ``operation`` / ``alias`` for a law **class or instance**.

    Instances are needed because A77 §65.3 makes the same-tier reference an *instance* per
    cell — ``NoWriteRef(L0)`` — rather than a single class fixed at the lowest tier.
    """
    if getattr(law, "alias_of", None):
        return "alias"
    if isinstance(law, NoWriteRef) or (isinstance(law, type)
                                       and issubclass(law, NoWriteRef)):
        return "reference"
    return "operation"


def law_metadata(registry=None) -> tuple:
    """``(name, kind, alias_of)`` per registered arm.

    ``kind`` is one of ``reference`` / ``operation`` / ``alias``.
    """
    return tuple((law.name, _kind(law), getattr(law, "alias_of", None))
                 for law in (LAWS if registry is None else registry))


def independent_treatment_count(registry=None) -> int:
    """The number of registered arms that are neither aliases nor references.

    On $D_{patch}$ the default registry answers **three**, and per A76 §63.9 those three
    are ``NoWrite`` + ``DeleteFactualPatch`` + ``SetAlternative`` — i.e. that frozen count
    *includes* the reference. A77 §65.3 says a reference is never a treatment, and that is
    what governs the $D_Q$ registry.

    The two are different questions, so the count is explicit per registry rather than
    inferred from the kind labels, and the frozen number is not re-derived from the newer
    rule.
    """
    if registry is None:
        return 3                                   # frozen by A76 §63.9
    return sum(1 for law in registry if _kind(law) == "operation")
