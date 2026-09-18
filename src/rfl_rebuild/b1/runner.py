r"""A76 §63.10 — the B1 slice pipeline.

$$\text{credited units} \xrightarrow{\rho_D} \texttt{DecisionAddress}
\xrightarrow{\text{target envelope, only if required}} \text{planned edits}
\xrightarrow{\text{ONE atomic transaction}} \text{post state}
\xrightarrow{} \texttt{UpdateLedger}$$

Three invariants this module owns, each of which an earlier version got wrong:

**Information tier.** The target envelope is built **only** for a law that declares
``requires_alternative``. An $L_0$ arm is never handed $a^+$ and is not affected by the
target generator failing — *the method did not read the higher-tier information* does
not imply *the runner did not first condition it on that information* (A59).

**Law API closure.** A law is handed ``(addresses, targets)`` and nothing else: no
store, no snapshot, no persistent-state view. Removing the snapshot argument only
closes the leak if a law cannot put it back, so the signature is enforced rather than
conventional. A76 §63.1 permits a primitive to read *its own* store; it does not permit
handing a $D$ law an independent handle on $P_D^L$, $C_P^L$ and $C_X^L$ at once.

**Plan totality.** A plan must name **every** credited address **exactly once**. A law
that omits an address or names one twice is a ``PROTOCOL_ERROR``, otherwise a law could
shrink ``N_addressed`` itself.

**Locality.** A planned write is legal only if the credited address, the plan's
address and the *edit's own* address all agree. Checking only the plan's address let a
plan legitimately name ``A`` while editing ``ROGUE``.

One scene commits **exactly once**. If ``apply_transaction`` raises, the whole run is a
fail-stop ``PROTOCOL_ERROR``; it is never returned as an ordinary result for B2 to
score.
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
    TargetRecord,
    build_target_envelope,
    resolve_credited_units,
    validate_envelope,
)
from rfl_rebuild.learner.store import (
    DECISION,
    LearnerPersistentState,
    StoreTransactionError,
)

__all__ = ["B1Result", "run_patch_law", "run_patch_law_with_envelope"]


@dataclass(frozen=True, slots=True)
class B1Result:
    """The ledger and the post-state. The law is never handed the store."""

    ledger: UpdateLedger
    post_state: LearnerPersistentState


def _store_view(state: LearnerPersistentState) -> dict:
    return dict(state.decision_overrides)


def _validate_plan(plan: LawPlan, addresses: Sequence) -> None:
    r"""Plan shape and totality.

    $$\{w.\text{address} : w \in \text{plan.writes}\} = \text{credited},
    \quad\text{each exactly once}$$

    and every write is one of the three legal shapes.
    """
    planned = [w.address for w in plan.writes]
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
            "; every credited address needs exactly one write plan, or a law could "
            "shrink N_addressed itself")
    if extra:
        raise ProtocolError(
            f"law {plan.name} planned non-credited address(es) "
            f"{sorted(map(repr, extra))}; credit assignment must not be redone inside "
            "a write-law experiment")
    for w in plan.writes:
        if w.edit is not None:
            if w.status is not None:
                raise ProtocolError(
                    f"law {plan.name} planned both an edit and a status "
                    f"({w.status!r}) at {w.address!r}")
            if w.edit.store != DECISION:
                raise ProtocolError(
                    f"law {plan.name} planned an edit to the {w.edit.store} store, "
                    "which is outside this slice")
            if w.edit.address != w.address:
                raise ProtocolError(
                    f"law {plan.name} planned a write at {w.address!r} but the edit "
                    f"targets {w.edit.address!r}; the credited address, the plan's "
                    "address and the edit's address must all agree")
        else:
            if w.status not in (None, NO_VALID_ALTERNATIVE):
                raise ProtocolError(
                    f"law {plan.name} declared status {w.status!r} at {w.address!r} "
                    "with no edit; the only legal no-edit status is "
                    f"{NO_VALID_ALTERNATIVE}")


def _tier(law) -> bool:
    """Read a law's declared information tier, refusing anything but a real ``bool``.

    The base class declares the sentinel ``None`` (NOT DECLARED), so a subclass that
    forgets its tier arrives here with ``None`` and fails stop. An earlier base value of
    ``False`` let exactly that case fall **silently to the lowest tier** — the one
    outcome this check exists to prevent — and the ``_NoTier`` gate did not catch it
    because its class never inherited ``_Law``.
    """
    tier = getattr(law, "requires_alternative", None)
    if type(tier) is not bool:
        raise ProtocolError(
            f"law {getattr(law, 'name', law)!r} declares "
            f"requires_alternative={tier!r}, which is not a bool; the undeclared "
            "sentinel is None, and a law must state whether it needs the alternative "
            "envelope")
    return tier


#: The whole law API. Not a convention: enforced by :func:`_law_contract`.
_LAW_PLAN_PARAMS = ("addresses", "targets")


def _law_contract(law):
    """Instantiate if needed, then enforce the declared parts of the law API.

    Two things are checked, both of which an earlier version left to convention:

    * the tier must be a real ``bool`` (:func:`_tier`);
    * ``plan`` must take **exactly** :data:`_LAW_PLAN_PARAMS`.

    The second is the A59-shaped half. Deleting the ``snapshot`` argument from the four
    laws closes nothing on its own — a new law could declare
    ``plan(self, addresses, targets, snapshot)`` and re-acquire the handle, and the
    runner's call would raise a bare ``TypeError`` instead of the ``PROTOCOL_ERROR`` the
    contract promises. It fails stop here instead.
    """
    if isinstance(law, type):
        law = law()
    tier = _tier(law)
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


def _run(law: "_Law", tier: bool, pre_state: LearnerPersistentState,
         addresses: Sequence, targets) -> B1Result:
    if tier:
        if targets is None:
            raise ProtocolError(
                f"law {law.name} requires the alternative envelope but none was "
                "provided")
    else:
        # An L0 / reference arm is never delivered L1 corrective content.
        targets = None

    pre_view = _store_view(pre_state)
    fp_pre = fingerprint(pre_state)

    # ---- the law plans BEFORE the transaction, touching nothing ---------- #
    plan = law.plan(addresses, targets)
    _validate_plan(plan, addresses)

    # ---- ONE transaction for the whole scene ----------------------------- #
    edits = plan.edits
    if edits:
        try:
            pre_state.apply_transaction(list(edits))
        except StoreTransactionError as exc:
            raise ProtocolError(
                f"the scenario transaction failed; the whole run is invalid: {exc}"
            ) from exc
    post_view = _store_view(pre_state)
    fp_post = fingerprint(pre_state)

    # ---- statuses, derived from the STORE, never from scalar accounting --- #
    receipts = []
    for w in plan.writes:
        changed = pre_view.get(w.address) != post_view.get(w.address)
        if w.edit is None and w.status is not None:
            status = w.status          # a declared reason, e.g. NO_VALID_ALTERNATIVE
        else:
            status = APPLIED if changed else EVALUABLE_NOOP
        receipts.append(DecisionWriteReceipt(address=w.address, status=status,
                                             store_changed=changed))

    ledger = UpdateLedger(receipts=tuple(receipts), fingerprint_pre=fp_pre,
                          fingerprint_post=fp_post,
                          scalar_metrics_applicable=False,
                          n_scalar=0, sum_abs_delta=0.0, max_abs_delta=0.0)
    ledger.check_fingerprint_invariants()
    return B1Result(ledger=ledger, post_state=pre_state)


def run_patch_law_with_envelope(law, pre_state: LearnerPersistentState,
                                addresses: Sequence,
                                targets) -> B1Result:
    """Run a law against an already-built address list and target envelope.

    A law that does not require the envelope is unaffected by it: a missing record
    cannot fail an $L_0$ arm. For a law that does require it, the envelope is
    structurally validated first — **exact** key set, key/record address agreement,
    action-id validity of both fields, and $a^+$ admissibility — because it is called
    *verified*.

    Scope of that verification, stated precisely: a structural check cannot detect a
    *legal but false* ``factual_command``, because the check has no trace to compare it
    with. Envelopes for real scenes come from :func:`build_target_envelope`, which sets
    ``factual_command`` from the factual trace and checks each address against that
    trace's context, so $a^+ \\neq a^F$ is grounded there. This entry point exists for a
    law × scene matrix built once per scene, not for hand-authored truth.
    """
    law, tier = _law_contract(law)
    if tier:
        validate_envelope(addresses, targets)
    return _run(law, tier, pre_state, addresses, targets)


def run_patch_law(law, pre_state: LearnerPersistentState, credited_units,
                  trace, kappa: int, phi: int, sol) -> B1Result:
    """Resolve, build targets **only if the law needs them**, plan, commit once."""
    law, tier = _law_contract(law)
    addresses = resolve_credited_units(credited_units, trace, kappa, phi)
    targets = None
    if tier:
        targets = build_target_envelope(sol, addresses, trace, kappa, phi)
    return _run(law, tier, pre_state, addresses, targets)
