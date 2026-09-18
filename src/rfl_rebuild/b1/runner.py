r"""A76 §63.10 — the B1 slice pipeline.

$$\text{credited units} \xrightarrow{\rho_D} \texttt{DecisionAddress}
\xrightarrow{\text{target envelope}} \text{planned edits}
\xrightarrow{\text{ONE atomic transaction}} \text{post state}
\xrightarrow{} \texttt{UpdateLedger}$$

One scene commits **exactly once**. Three credited addresses, one of which has no
valid alternative, must not become ``apply(a1); skip(a2); apply(a3)`` — that would
destroy multi-address order independence and re-introduce an order-dependent result.

If ``apply_transaction`` itself raises, the whole run is a fail-stop ``PROTOCOL_ERROR``;
it is never returned as an ordinary result for B2 to score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from rfl_rebuild.b1.contract import (
    APPLIED,
    EVALUABLE_NOOP,
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
)
from rfl_rebuild.learner.store import (
    DECISION,
    LearnerPersistentState,
    StoreTransactionError,
)

__all__ = ["B1Result", "run_patch_law", "run_patch_law_with_envelope"]


@dataclass(frozen=True, slots=True)
class B1Result:
    """The ledger and the post-state. The law is not handed the store."""

    ledger: UpdateLedger
    post_state: LearnerPersistentState


def _store_view(state: LearnerPersistentState) -> dict:
    return dict(state.decision_overrides)


def _run(law: "_Law | type[_Law]", pre_state: LearnerPersistentState,
         addresses: Sequence, targets, scalar_note: bool = False) -> B1Result:
    if isinstance(law, type):
        law = law()
    snapshot = pre_state.snapshot()
    pre_view = _store_view(pre_state)
    fp_pre = fingerprint(pre_state)

    # ---- the law plans against the PRE snapshot, touching nothing --------- #
    plan = law.plan(addresses, targets, snapshot)

    # ---- locality: a law may not write outside the credited addresses ----- #
    credited = set(addresses)
    for w in plan.writes:
        if w.address not in credited:
            raise ProtocolError(
                f"law {plan.name} planned a write at {w.address!r}, which is not a "
                "credited address; credit assignment must not be redone inside a "
                "write-law experiment")
        if w.edit is not None:
            if w.edit.store != DECISION:
                raise ProtocolError(
                    f"law {plan.name} planned an edit to the {w.edit.store} store, "
                    "which is outside this slice")

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
            # the law declared a reason for not writing (e.g. NO_VALID_ALTERNATIVE)
            status = w.status
        else:
            # APPLIED iff the store actually differs at this address. This is the
            # architecture-neutral criterion: a patch store is value-free, so
            # neither N_scalar nor any delta could decide it.
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

    The total-envelope rule is enforced here, before the law runs:

    * an address with **no record** → :class:`ProtocolError`;
    * an address whose record carries ``alternative is None`` → a legitimate
      ``NO_VALID_ALTERNATIVE``, handled by the law.

    Conflating those two would let a target generator that dropped a row masquerade as
    the 3,600 genuine empty-alternative addresses.
    """
    for a in addresses:
        if a not in targets:
            raise ProtocolError(
                f"no target record for credited address {a!r}; a missing record is a "
                "protocol failure, not a verified absence of an alternative")
    return _run(law, pre_state, addresses, targets)


def run_patch_law(law, pre_state: LearnerPersistentState, credited_units,
                  trace, kappa: int, phi: int, sol) -> B1Result:
    """Resolve, build targets, plan, and commit in one transaction."""
    addresses = resolve_credited_units(credited_units, trace, kappa, phi)
    targets = build_target_envelope(sol, addresses, trace, kappa, phi)
    return run_patch_law_with_envelope(law, pre_state, addresses, targets)
