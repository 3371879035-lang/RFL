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
from rfl_rebuild.b1.tier import PATCH_SLICE, SliceDescriptor, Tier
from rfl_rebuild.learner.store import LearnerPersistentState, StoreTransactionError

__all__ = ["B1Result", "run_patch_law", "run_patch_law_with_envelope"]


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


def _run(law: "_Law", tier: Tier, pre_state: LearnerPersistentState,
         addresses: Sequence, targets, spec: SliceDescriptor) -> B1Result:
    # ---- the cell decides delivery, not the law and not the outcome ------- #
    targets = spec.deliver(tier, addresses, targets)

    pre_view = spec.view(pre_state)
    fp_pre = fingerprint(pre_state)

    # ---- the law plans BEFORE the transaction, touching nothing ---------- #
    plan = law.plan(addresses, targets)
    _validate_plan(plan, addresses, spec)

    # ---- ONE transaction for the whole scene ----------------------------- #
    edits = plan.edits
    if edits:
        try:
            pre_state.apply_transaction(list(edits))
        except StoreTransactionError as exc:
            raise ProtocolError(
                f"the scenario transaction failed; the whole run is invalid: {exc}"
            ) from exc
    post_view = spec.view(pre_state)
    fp_post = fingerprint(pre_state)

    # ---- statuses, derived from the STORE, never from scalar accounting --- #
    receipts = []
    for p in plan.plans:
        entry = p.edits[0].address if p.edits else p.address
        changed = pre_view.get(entry) != post_view.get(entry)
        if not p.edits and p.status is not None:
            status = p.status          # a declared reason, e.g. NO_VALID_ALTERNATIVE
        else:
            status = APPLIED if changed else EVALUABLE_NOOP
        receipts.append(DecisionWriteReceipt(address=p.address, status=status,
                                             store_changed=changed))

    ledger = UpdateLedger(receipts=tuple(receipts), fingerprint_pre=fp_pre,
                          fingerprint_post=fp_post,
                          scalar_metrics_applicable=spec.scalar,
                          n_scalar=0, sum_abs_delta=0.0, max_abs_delta=0.0)
    ledger.check_fingerprint_invariants()
    return B1Result(ledger=ledger, post_state=pre_state)


def run_patch_law_with_envelope(law, pre_state: LearnerPersistentState,
                                addresses: Sequence, targets,
                                spec: SliceDescriptor = PATCH_SLICE) -> B1Result:
    """Run a law against an already-built address list and target envelope.

    A law whose cell declares no field is unaffected by the envelope: a missing record
    cannot fail an $L_0$ arm. For a law whose cell does declare fields, the envelope is
    structurally validated first — **exact** key set, key/record address agreement,
    action-id validity of both fields, and $a^+$ admissibility — and then projected onto
    the cell's field set, because it is called *verified*.

    Scope of that verification, stated precisely: a structural check cannot detect a
    *legal but false* ``factual_command``, because the check has no trace to compare it
    with. Envelopes for real scenes come from :func:`build_target_envelope`, which sets
    ``factual_command`` from the factual trace and checks each address against that
    trace's context, so $a^+ \\neq a^F$ is grounded there. This entry point exists for a
    law × scene matrix built once per scene, not for hand-authored truth.
    """
    law, tier = _law_contract(law, spec)
    if spec.fields(tier):
        validate_envelope(addresses, targets)
    return _run(law, tier, pre_state, addresses, targets, spec)


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
