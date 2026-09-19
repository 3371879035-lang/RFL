r"""A76 §63.10 / A77 §65.2, §65.9 — the B1 slice pipeline.

$$\text{credited units} \xrightarrow{\rho_D} \texttt{DecisionAddress}
\xrightarrow[\text{build the cell's fields}]{} \text{projected envelope}
\xrightarrow{\text{plan}} \text{address-plans}
\xrightarrow{\text{ONE atomic transaction}} \text{post state}
\xrightarrow{} \texttt{UpdateLedger}$$

Five invariants this module owns, each of which an earlier version got wrong:

**Cell delivery.** The envelope is built **only** for a law whose cell declares fields,
and what the law receives is the **projection onto exactly those fields** (A77 §65.2). A
law whose cell declares none is handed *no object*, and is not affected by the target
generator failing — *the method did not read the higher-tier information* does not imply
*the runner did not first condition it on that information* (A59).

**Law API closure.** A law is handed ``(addresses, targets)`` and nothing else: no store,
no snapshot, no persistent-state view. Removing the snapshot argument only closes the leak
if a law cannot put it back, so the signature is enforced rather than conventional. A76
§63.1 permits a primitive to read *its own* store; it does not permit handing a $D$ law an
independent handle on $P_D^L$, $C_P^L$ and $C_X^L$ at once.

**Address-plan totality.** A plan must name **every** credited address **exactly once**.
A law that omits an address or names one twice is a ``PROTOCOL_ERROR``, otherwise a law
could shrink ``N_addressed`` itself.

**Owner-based locality.** A planned edit is legal only if the credited context *owns* the
entry it writes:

$$\boxed{\forall e \in \text{Plan}(x):\ owner_\alpha(e.\text{address}) = x}$$

On $D_{patch}$ the owner map is the identity, so the earlier rule "credited = plan =
edit" is this rule's special case rather than the rule. Checking only the plan's address
let a plan legitimately name ``A`` while editing ``ROGUE``.

**One transaction.** A scene commits **exactly once**. If ``apply_transaction`` raises, the
whole run is a fail-stop ``PROTOCOL_ERROR``; it is never returned as an ordinary result for
B2 to score.

Everything architecture-specific enters through a
:class:`~rfl_rebuild.b1.tier.SliceDescriptor`, so the totality, locality, atomicity and
receipt logic below exists once.
"""

from __future__ import annotations

import inspect
import math
from dataclasses import dataclass
from typing import Sequence

from rfl_rebuild.b1.contract import (
    APPLIED,
    EVALUABLE_NOOP,
    NO_VALID_ALTERNATIVE,
    DecisionWriteReceipt,
    ProtocolError,
    UpdateLedger,
    fingerprint,
)
from rfl_rebuild.b1.laws import LawPlan, _Law
from rfl_rebuild.b1.targets import (
    build_target_envelope,
    resolve_credited_units,
    validate_envelope,
)
from rfl_rebuild.b1.counterfactual import (
    build_counterfactual_envelope,
    validate_counterfactual_envelope,
)
from rfl_rebuild.b1.factual import (
    build_factual_envelope,
    validate_factual_envelope,
)
from rfl_rebuild.b1.tier import DQ_SLICE, PATCH_SLICE, SliceDescriptor, Tier
from rfl_rebuild.learner.store import (
    LearnerPersistentState,
    ReferenceContractError,
    StoreTransactionError,
    require_q_reference,
)

__all__ = [
    "B1Result",
    "run_dq_law",
    "run_factual_return_law",
    "run_patch_law",
    "run_patch_law_with_envelope",
]

#: Distinguishes "this entry is absent from the store view" from every storable value,
#: including ``None`` (which is not a storable value here, but is a legal *deletion*
#: marker in an :class:`~rfl_rebuild.learner.store.Edit`).
_MISSING = object()


@dataclass(frozen=True, slots=True)
class B1Result:
    """The ledger and the post-state. The law is never handed the store."""

    ledger: UpdateLedger
    post_state: LearnerPersistentState


def _validate_plan(plan: LawPlan, addresses: Sequence, spec: SliceDescriptor) -> None:
    r"""Address-plan shape, totality, and owner locality.

    $$\boxed{\{\text{Plan}.\text{address}\} = \text{the credited addresses},
    \quad\text{each exactly once}}$$

    $$\boxed{\forall e \in \text{Plan}(x):\ owner_\alpha(e.\text{address}) = x}$$

    Two entry edits at one address-plan are rejected as well: they would be two edits to
    the same entry, and last-write-wins would make the result depend on edit order. On
    $D_{patch}$ that rule is also what bounds a plan at one entry, without a special case.
    """
    planned = [p.address for p in plan.plans]
    if len(planned) != len(set(planned)):
        raise ProtocolError(
            f"law {plan.name} planned the same address more than once; a duplicate "
            "would double-count a receipt")
    credited = set(addresses)
    missing = credited - set(planned)
    extra = set(planned) - credited
    if missing:
        raise ProtocolError(
            f"law {plan.name} omitted credited address(es) {sorted(map(repr, missing))}"
            "; every credited address needs exactly one address-plan, or a law could "
            "shrink N_addressed itself")
    if extra:
        raise ProtocolError(
            f"law {plan.name} planned non-credited address(es) "
            f"{sorted(map(repr, extra))}; credit assignment must not be redone inside "
            "a write-law experiment")
    for p in plan.plans:
        entries = [e.address for e in p.edits]
        if len(entries) != len(set(entries)):
            raise ProtocolError(
                f"law {plan.name} planned the same entry twice at {p.address!r}; the "
                "result would depend on edit order, which A76 forbids")
        for e in p.edits:
            if e.store != spec.store:
                raise ProtocolError(
                    f"law {plan.name} planned an edit to the {e.store} store, which is "
                    f"outside the {spec.name} slice")
            if spec.owner(e.address) != p.address:
                raise ProtocolError(
                    f"law {plan.name} planned a write owned by {spec.owner(e.address)!r} "
                    f"under the credited context {p.address!r}; owner_locality requires "
                    f"owner_{spec.name}(edit.address) == plan.address")
        if p.edits:
            if p.status is not None:
                raise ProtocolError(
                    f"law {plan.name} planned both edits and a status "
                    f"({p.status!r}) at {p.address!r}")
        else:
            if p.status not in (None, NO_VALID_ALTERNATIVE):
                raise ProtocolError(
                    f"law {plan.name} declared status {p.status!r} at {p.address!r} "
                    "with no edit; the only legal no-edit status is "
                    f"{NO_VALID_ALTERNATIVE}")


def _tier(law) -> Tier:
    """Read a law's declared information tier, refusing anything but a real ``Tier``.

    The base class declares the sentinel ``None`` (NOT DECLARED), so a subclass that
    forgets its tier arrives here with ``None`` and fails stop. An earlier declaration was
    ``requires_alternative: bool = False``, which let exactly that case fall **silently to
    the lowest tier** — the one outcome this check exists to prevent — and the ``_NoTier``
    gate did not catch it because its class never inherited ``_Law``.

    A77 §65.1: the accepted type is a closed enum, so no integer, no boolean and no
    truthiness inference can pass for a tier.
    """
    tier = getattr(law, "tier", None)
    if type(tier) is not Tier:
        raise ProtocolError(
            f"law {getattr(law, 'name', law)!r} declares tier={tier!r}, which is not a "
            "Tier member; the undeclared sentinel is None, and a law must state which "
            "cell of the information contract it runs in (A77 §65.1)")
    return tier


#: The whole law API. Not a convention: enforced by :func:`_law_contract`.
_LAW_PLAN_PARAMS = ("addresses", "targets")


def _law_contract(law, spec: SliceDescriptor):
    """Instantiate if needed, then enforce the declared parts of the law API.

    Three things are checked, all of which an earlier version left to convention:

    * the tier must be a real :class:`Tier` (:func:`_tier`);
    * the tier's **cell must not be ill-typed** (A77 §65.2) — a law declared where the
      architecture has no substantive treatment is rejected before it runs, which is what
      keeps `PositiveAlternative` retired rather than merely discouraged;
    * ``plan`` must take **exactly** :data:`_LAW_PLAN_PARAMS`.

    The last is the A59-shaped half. Deleting the ``snapshot`` argument from the laws
    closes nothing on its own — a new law could declare
    ``plan(self, addresses, targets, snapshot)`` and re-acquire the handle, and the
    runner's call would raise a bare ``TypeError`` instead of the ``PROTOCOL_ERROR`` the
    contract promises. It fails stop here instead.
    """
    if isinstance(law, type):
        law = law()
    tier = _tier(law)
    spec.fields(tier)                      # ill-typed cells fail stop here
    spec.require_implemented(tier)         # semantically real but unbuilt cells too
    try:
        params = tuple(inspect.signature(law.plan).parameters)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(
            f"law {getattr(law, 'name', law)!r} has no inspectable plan signature: "
            f"{exc}") from exc
    if params != _LAW_PLAN_PARAMS:
        raise ProtocolError(
            f"law {getattr(law, 'name', law)!r} plans with parameters {params}, but the "
            f"law API is exactly {_LAW_PLAN_PARAMS}; a law is not handed the store, a "
            "snapshot or any other learner-state view (A76 §63.1, §63.10)")
    return law, tier


def _entry_key(address) -> tuple:
    r"""The canonical ordering key for an entry: $(x, y, t, \\kappa, \\phi, z, m, a)$."""
    s = address.state
    return (s.x, s.y, s.t, s.kappa, s.phi, address.z, address.m, address.a)


def _scalar_accounting(plan: LawPlan, pre_view: dict, post_view: dict,
                       q_reference) -> tuple:
    r"""A77 §65.10: $N_{\\text{scalar}}$, $\\Sigma$, $\\text{Max}$ over the changed entries.

    $$\\boxed{\\Delta(e)=\\begin{cases}
    \\lvert q_{\\text{post}} - q_{\\text{pre}}\\rvert, & \\text{override} \\to \\text{override}\\\\
    \\lvert q_{\\text{post}} - Q_D^\\ast(e)\\rvert, & \\bot \\to \\text{override}\\\\
    \\lvert Q_D^\\ast(e) - q_{\\text{pre}}\\rvert, & \\text{override} \\to \\bot
    \\end{cases}}$$

    The delta is measured against the **effective** $Q$, not against an arbitrary zero: in
    a sparse store "absent" is $Q_D^\\ast(e)$, not $0$. Measuring a created entry as
    $\\lvert q_{\\text{post}}\\rvert$ would make a nearly-reference-valued write look like a
    huge edit, and would make the numbers depend on where the reward scale happens to
    place zero.

    The reference is required here for the same reason it is required at the transaction
    boundary: without it the created and deleted cases are not defined at all.

    **Order independence.** A76 froze that no result may depend on iteration or hash
    order, and a sequential float accumulation would violate it: $10^{16} + 1 + 1$ and
    $1 + 1 + 10^{16}$ are different bit patterns. Two things give independence here, and
    they are not the same thing:

    * ``math.fsum`` is exactly rounded, so the sum is order-independent by construction.
      (The §65.6 fold prohibition is about *target construction*, which must reproduce the
      DP's path; ledger accounting is a different job.);
    * the entries are **sorted** by a canonical key anyway, so the determinism is visible
      in the code rather than inferred from ``fsum``'s contract.
    """
    if q_reference is None:
        raise ProtocolError(
            "the scalar ledger needs the injected reference view: the created and deleted "
            "deltas are defined against Q_D^*, and an absent entry is not a zero value "
            "(A77 §65.10)")
    changed: list = []
    for p in plan.plans:
        for e in p.edits:
            was = pre_view.get(e.address, _MISSING)
            now = post_view.get(e.address, _MISSING)
            if was == now:
                continue
            if was is _MISSING:
                delta = abs(float(now) - float(q_reference.value(e.address)))
            elif now is _MISSING:
                delta = abs(float(q_reference.value(e.address)) - float(was))
            else:
                delta = abs(float(now) - float(was))
            changed.append((_entry_key(e.address), delta))
    changed.sort(key=lambda pair: pair[0])
    deltas = [d for _key, d in changed]
    return len(deltas), math.fsum(deltas), max(deltas, default=0.0)


def _run(law: "_Law", tier: Tier, pre_state: LearnerPersistentState,
         addresses: Sequence, targets, spec: SliceDescriptor,
         q_reference=None) -> B1Result:
    # ---- the reference boundary, uniform across arms --------------------- #
    #
    # A77 §65.2 requires every law in a cell to be built through the same cell, and the
    # same discipline applies to what the *runner* accepts: a fake reference must be
    # refused before any arm-specific behaviour, so that a reference arm and a treatment
    # arm cannot differ in admissibility.
    #
    # That asymmetry was real. `FactualReturnWrite` writes, so a fake reference was caught
    # by the store's own boundary; `NoWriteRef(L0)` writes nothing, skipped the
    # transaction entirely, and reached only the accounting -- which checked ``is None``.
    # A mutable duck-typed fake therefore *completed* on the reference arm and
    # fail-stopped on the treatment arm of the same cell. The check belongs here, once,
    # ahead of both, and it covers every entry point rather than one of them.
    if spec.scalar:
        try:
            require_q_reference(q_reference)
        except ReferenceContractError as exc:
            # The substrate's own exception type is deliberately separate from B1's
            # ProtocolError, and the runner's contract is that a benchmark-invalidating
            # failure is a ProtocolError -- the same conversion the transaction gets.
            raise ProtocolError(f"the Q reference is not acceptable: {exc}") from exc

    # ---- the cell decides delivery, not the law and not the outcome ------- #
    targets = spec.deliver(tier, addresses, targets)

    pre_view = spec.view(pre_state)
    fp_pre = fingerprint(pre_state)

    # ---- the law plans BEFORE the transaction, touching nothing ---------- #
    #
    # A law reads the fields *its cell declares*, so running it on a slice whose cell
    # declares different ones is a protocol failure — and it used to surface as a bare
    # `TypeError: 'NoneType' object is not subscriptable` from inside the law, which reads
    # like a bug in the law rather than a mismatched (law, slice) pair. The `from exc`
    # keeps the original traceback.
    try:
        plan = law.plan(addresses, targets)
    except (TypeError, KeyError, AttributeError, IndexError) as exc:
        raise ProtocolError(
            f"law {law.name} failed while planning against the {spec.name} slice at tier "
            f"{tier.name}: {type(exc).__name__}: {exc}. The usual cause is a law run on a "
            "slice whose cell does not deliver the fields the law reads"
        ) from exc
    _validate_plan(plan, addresses, spec)

    # ---- ONE transaction for the whole scene ----------------------------- #
    edits = plan.edits
    if edits:
        try:
            pre_state.apply_transaction(list(edits), q_reference=q_reference)
        except StoreTransactionError as exc:
            raise ProtocolError(
                f"the scenario transaction failed; the whole run is invalid: {exc}"
            ) from exc
    post_view = spec.view(pre_state)
    fp_post = fingerprint(pre_state)

    # ---- statuses, derived from the STORE, never from scalar accounting --- #
    #
    # The receipt is per ADDRESS-PLAN, so "changed" must be a property of the whole plan:
    #
    # $$\boxed{\text{changed}(x) = \exists e \in \text{Plan}(x): pre[e] \neq post[e]}$$
    #
    # The first version tested ``p.edits[0]`` only. On $D_{patch}$ that is invisible —
    # the owner map is the identity, so a legal plan has one entry — but the generic
    # structure admits $k>1$, and with a no-op first entry and a changing second one the
    # receipt said "unchanged" while the fingerprint moved, so the ledger invariant
    # killed the run instead of reporting ``APPLIED``. The address-plan is the unit
    # A77 §65.9 froze, and the receipt has to be computed on the same unit.
    receipts = []
    for p in plan.plans:
        changed = any(
            pre_view.get(e.address, _MISSING) != post_view.get(e.address, _MISSING)
            for e in p.edits)
        if not p.edits and p.status is not None:
            status = p.status          # a declared reason, e.g. NO_VALID_ALTERNATIVE
        else:
            status = APPLIED if changed else EVALUABLE_NOOP
        receipts.append(DecisionWriteReceipt(address=p.address, status=status,
                                             store_changed=changed))

    n_scalar, total_delta, largest_delta = (0, 0.0, 0.0)
    if spec.scalar:
        n_scalar, total_delta, largest_delta = _scalar_accounting(
            plan, pre_view, post_view, q_reference)

    ledger = UpdateLedger(receipts=tuple(receipts), fingerprint_pre=fp_pre,
                          fingerprint_post=fp_post,
                          scalar_metrics_applicable=spec.scalar,
                          n_scalar=n_scalar, sum_abs_delta=total_delta,
                          max_abs_delta=largest_delta)
    ledger.check_fingerprint_invariants()
    return B1Result(ledger=ledger, post_state=pre_state)


def run_patch_law_with_envelope(law, pre_state: LearnerPersistentState,
                                addresses: Sequence, targets,
                                spec: SliceDescriptor = PATCH_SLICE,
                                q_reference=None) -> B1Result:
    """Run a law against an already-built address list and target envelope.

    This is the **$D_{patch}$** structural path: its envelope is validated by
    :func:`~rfl_rebuild.b1.targets.validate_envelope` against the patch record schema. A
    slice whose cell declares fields and is *not* the patch slice therefore gets a
    ``PROTOCOL_ERROR`` here rather than silently skipping validation — each architecture
    has its own entry point, because each envelope is verified against its own evidence
    (the scalar slice's against the learner-visible rows).

    A law whose cell declares no field is unaffected by the envelope: a missing record
    cannot fail an $L_0$ patch arm.
    """
    law, tier = _law_contract(law, spec)
    if spec.fields(tier):
        if spec.name != PATCH_SLICE.name:
            raise ProtocolError(
                f"{spec.name} declares fields {sorted(spec.fields(tier))}; a slice with a "
                "non-empty cell has its own entry point, because its envelope is "
                "validated against its own evidence and this one would check it against "
                "the D_patch record schema")
        validate_envelope(addresses, targets)
    return _run(law, tier, pre_state, addresses, targets, spec, q_reference)


def run_dq_law(law, pre_state: LearnerPersistentState,
               addresses: Sequence, rows, q_reference, *,
               sol=None, episode=None,
               spec: SliceDescriptor = DQ_SLICE) -> B1Result:
    r"""The $D_Q$ entry point: build the cell's fields, validate them, run.

    The builder and the validator are **tier-specific**, because each cell's evidence is
    different and neither may be checked against the other's:

    * $L_0$ builds $F_t = f(I^{\text{factual}}_{0:T})$ from the rows alone, and is
      re-derived from those rows bit for bit;
    * $L_2$ additionally needs the shared $a_t^+$ adapter (``sol``, the *same* adapter
      every other arm uses, A76 §63.3) and the factual configuration (``episode``) for the
      full-episode counterfactual replay, and is re-derived from both.

    Handing one tier's evidence where the other's is required fails stop rather than
    silently building a weaker envelope.
    """
    law, tier = _law_contract(law, spec)
    fields = spec.fields(tier)
    if not fields:
        raise ProtocolError(
            f"{spec.name} at tier {tier.name} declares no field, so it has nothing to "
            "build here; an empty cell does not belong on the D_Q path")
    if tier is Tier.L0_FACTUAL:
        envelope = build_factual_envelope(rows, addresses)
        validate_factual_envelope(addresses, envelope, rows)
    elif tier is Tier.L2_COUNTERFACTUAL:
        if sol is None or episode is None:
            raise ProtocolError(
                "the L2 cell needs the shared a^+ adapter (sol) and the factual episode "
                "configuration; without them the counterfactual has no definition and an "
                "envelope could only be faked")
        # ---- the learner continuity binding, BEFORE any target is built ---------- #
        #
        # A76: both targets come from the same pre-update state -- and the "same" that
        # matters is not only "the two targets agree with each other" but "they are the
        # pre-update state of the learner this transaction is about to update". Otherwise
        # the arm observes learner A's experience, computes learner A's target, and trains
        # learner B, which is a different experiment wearing this one's name.
        #
        # Equality of the fingerprint, not object identity: a clone is a legitimate
        # pre-state, and a clone that matches IS the same learner for every purpose this
        # contract can state.
        fp_target = fingerprint(pre_state)
        fp_episode = fingerprint(episode.snapshot_pre)
        if fp_target != fp_episode:
            raise ProtocolError(
                "the counterfactual target would be computed from a different pre-update "
                "learner than the one this transaction updates: the episode's snapshot "
                f"fingerprints {fp_episode} and the target store fingerprints "
                f"{fp_target}. An L2 arm computes both of its targets from the snapshot of "
                "the learner it is training (A76 §63.4)")
        envelope = build_counterfactual_envelope(rows, addresses, sol=sol,
                                                 episode=episode)
        validate_counterfactual_envelope(addresses, envelope, rows, sol=sol,
                                         episode=episode)
    else:
        raise ProtocolError(
            f"{spec.name} at tier {tier.name} has no D_Q builder; this revision "
            "implements L0 and L2 only")
    return _run(law, tier, pre_state, addresses, envelope, spec, q_reference)


def run_factual_return_law(law, pre_state: LearnerPersistentState,
                           addresses: Sequence, rows,
                           q_reference, spec: SliceDescriptor = DQ_SLICE) -> B1Result:
    r"""The $L_0$ entry point, kept under its own name.

    $$\boxed{F_t = f\bigl(I^{\text{factual}}_{0:T}\bigr)}$$

    It is :func:`run_dq_law` restricted to the factual cell, and it *asserts* that
    restriction rather than relying on the dispatch: a caller reaching for this function
    is asking for $F_t$, so handing it an $L_2$ law should be told so.

    The reference view is **required**, not optional: the scalar ledger's created and
    deleted deltas are defined against $Q_D^\ast$, and a run that could not compute them
    would have to report zeros — which is a claim, not a gap.
    """
    law, tier = _law_contract(law, spec)
    if tier is not Tier.L0_FACTUAL:
        raise ProtocolError(
            f"{law.name} declares tier {tier.name}; run_factual_return_law builds the L0 "
            "cell only — use run_dq_law for a law whose cell needs the counterfactual")
    return run_dq_law(law, pre_state, addresses, rows, q_reference, spec=spec)


def run_patch_law(law, pre_state: LearnerPersistentState, credited_units,
                  trace, kappa: int, phi: int, sol,
                  spec: SliceDescriptor = PATCH_SLICE) -> B1Result:
    """Resolve, build the cell's fields **only if it declares any**, plan, commit once."""
    law, tier = _law_contract(law, spec)
    addresses = resolve_credited_units(credited_units, trace, kappa, phi)
    targets = None
    if spec.fields(tier):
        targets = build_target_envelope(sol, addresses, trace, kappa, phi)
    return _run(law, tier, pre_state, addresses, targets, spec)
