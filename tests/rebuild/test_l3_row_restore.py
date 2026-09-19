r"""A78 §66 — $D_Q\times L_3$: `LocalOracleRestore`, the row-scoped restore.

$$\boxed{L_3:\ \text{delete every override in the credited context's row, returning it to }
Q_D^\ast}$$

The gates are grouped by the boundaries A78 fixed, because each of them is a way the arm can
silently stop being the arm:

1. **authorisation and registry** — one new step, `NoWriteRef(L3)` named, four treatments,
   $D_{patch}$ untouched;
2. **domain** — every credited address, *not* the subset with an $a^+$;
3. **information** — the empty cell is asserted, and demonstrated with poison evidence;
4. **the row operation** — a B1 object, the substrate does not learn it, the plan-shape rule;
5. **lowering** — one frozen pre-state, and the ledger reads the lowered concrete edits;
6. **behaviour** — row scope, idempotence, the ledger.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1 import (  # noqa: E402
    APPLIED, DQ_LAWS, DQ_SLICE, EVALUABLE_NOOP, NO_VALID_ALTERNATIVE, AddressPlan,
    CounterfactualReturnWrite, DQLocalOracleRestore, DeleteFactualPatch, DualReturnWrite,
    FactualReturnWrite, LawPlan, LocalOracleRestore, NoWriteRef, ProtocolError,
    PATCH_SLICE, RestoreRow, Tier, dq_owner, independent_treatment_count,
    law_metadata, run_patch_law_with_envelope,
    resolve_credited_units, run_dq_law, run_row_restore_law,
)
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.observation import learner_rows  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    Q, DecisionAddress, Edit, LearnerPersistentState, QAddress, State, owner_Q,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

SOL = solve_reference()
VIEW = reference_view_from(SOL)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #

def scene(kappa=0, phi=0, z0=1, overrides=2):
    """A scene whose pre-state carries `overrides` Q entries in the first credited row."""
    trace = K.rollout(kappa=kappa, tape=K.SemanticTape(phase=phi, error_flag=0,
                                                       cause_rank=0),
                      command_provider=lambda s, c: SOL.best_action(s, c.z, c.m),
                      base_option=z0)
    rows = learner_rows(trace, kappa, phi)
    steps = sorted({r[2] for r in rows})
    addrs = resolve_credited_units(tuple(f"Decision_{t}" for t in steps), trace, kappa,
                                   phi)
    target = addrs[0]
    state = LearnerPersistentState()
    allowed = sorted(K.option_actions(target.z, K.ControlState(z=target.z, m=target.m),
                                      target.state))
    written = []
    for a in allowed[:overrides]:
        entry = QAddress(state=target.state, z=target.z, m=target.m, a=a)
        ref = VIEW.value(entry)
        state.apply_transaction([Edit(Q, entry, ref + 1.0 + a)], q_reference=VIEW)
        written.append(entry)
    assert len(written) == overrides
    return rows, addrs, target, state, tuple(written)


# --------------------------------------------------------------------------- #
# 1. authorisation and registry
# --------------------------------------------------------------------------- #

def test_1_the_cell_has_its_reference_and_the_counts_match_a76():
    r"""$$\boxed{\lvert\text{independent treatments}\rvert(D_Q) = 4}$$"""
    names = [law.name for law in DQ_LAWS]
    assert names == ["NoWrite", "FactualReturnWrite", "NoWrite",
                     "CounterfactualReturnWrite", "DualReturnWrite", "NoWrite",
                     "LocalOracleRestore"], names
    kinds = [k for _n, k, _a in law_metadata(DQ_LAWS)]
    assert kinds == ["reference", "operation", "reference", "operation", "operation",
                     "reference", "operation"]
    assert independent_treatment_count(DQ_LAWS) == 4
    assert independent_treatment_count() == 3, "D_patch must not move"


def test_2_the_dq_law_is_an_independent_implementation():
    r"""A78 §66.7: the $D_{patch}$ alias is untouched and shares its `plan` object."""
    assert LocalOracleRestore.plan is DeleteFactualPatch.plan, \
        "the D_patch alias must still share the plan function object"
    assert LocalOracleRestore.alias_of == "DeleteFactualPatch"
    assert DQLocalOracleRestore.plan is not DeleteFactualPatch.plan
    assert getattr(DQLocalOracleRestore, "alias_of", None) is None
    assert DQLocalOracleRestore.tier is Tier.L3_ORACLE
    assert DQLocalOracleRestore not in (LocalOracleRestore,) and \
        not issubclass(DQLocalOracleRestore, DeleteFactualPatch)


def test_3_the_substrate_does_not_learn_the_row_operation():
    r"""A78 §66.5: `owner_Q` keeps taking a `QAddress`; the resolver is in B1."""
    import inspect
    import rfl_rebuild.learner.store as store
    src = inspect.getsource(store.owner_Q)
    assert "RestoreRow" not in src
    assert "RestoreRow" not in inspect.getsource(store)
    entry = QAddress(state=State(x=0, y=2, t=0, kappa=0, phi=0), z=1, m=0, a=0)
    assert dq_owner(entry) == owner_Q(entry)
    context = DecisionAddress(state=entry.state, z=entry.z, m=entry.m)
    assert dq_owner(RestoreRow(context)) == context
    from rfl_rebuild.learner.store import owner_Q as substrate_owner
    with pytest.raises(Exception):
        substrate_owner(RestoreRow(context))


# --------------------------------------------------------------------------- #
# 2. domain: every credited address
# --------------------------------------------------------------------------- #

def test_18_the_reused_patch_plan_is_caught_by_the_operation_kind():
    r"""The semantic witness for "the $D_Q$ law must be its own implementation".

    §66.7's hole is that the $D_Q$ arm might run the $D_{patch}$ implementation, whose plan
    emits `DECISION` edits. Inheriting the class is not that hole -- the subclass's own
    `plan` still wins method resolution -- so it is asserted here directly: this arm emits a
    row operation and **no** entry edits, and a plan built from the patch implementation
    cannot run on this slice.
    """
    rows, addrs, target, state, written = scene(overrides=1)
    plan = DQLocalOracleRestore().plan(addrs, None)
    assert all(p.row_op is not None and type(p.row_op) is RestoreRow
               for p in plan.plans), "the D_Q law emits row operations"
    assert plan.edits == (), "and no entry edits"

    class _ReusedPatchPlan:
        name, alias_of, tier = "ReusedPatchPlan", None, Tier.L3_ORACLE

        def plan(self, addresses, targets):
            return DeleteFactualPatch().plan(addresses, targets)

    with pytest.raises(ProtocolError) as ei:
        run_row_restore_law(_ReusedPatchPlan(), state, addrs, VIEW)
    assert "outside the" in str(ei.value), ei.value
    # and the real arm still works, so the rejection is the operation kind's
    assert run_row_restore_law(DQLocalOracleRestore, state, addrs, VIEW).ledger.n_scalar == 1


def test_4_the_domain_is_every_credited_address():
    r"""A78 §66.3. The healthy support has 246 of 278 addresses with no $a^+$; $L_3$'s
    domain must include them, or its empty cell would be reading $a^+$ availability."""
    rows, addrs, _target, state, _written = scene()
    res = run_row_restore_law(DQLocalOracleRestore, state, addrs, VIEW)
    assert res.ledger.n_addressed == len(addrs), "every credited address, one receipt each"
    statuses = [r.status for r in res.ledger.receipts]
    assert NO_VALID_ALTERNATIVE not in statuses, \
        "L3 must not inherit L2's no-alternative status; it has no alternative to need"


def test_4b_no_a_plus_is_consulted():
    """The law's own plan is built from the addresses alone."""
    rows, addrs, _target, _state, _written = scene()
    plan = DQLocalOracleRestore().plan(addrs, None)
    assert len(plan.plans) == len(addrs)
    assert all(p.row_op is not None for p in plan.plans)


# --------------------------------------------------------------------------- #
# 3. information: the empty cell, asserted and demonstrated
# --------------------------------------------------------------------------- #

def test_5_the_l3_entry_point_cannot_be_handed_evaluator_evidence():
    r"""$$\boxed{\text{no } rows,\ \text{no } sol,\ \text{no } episode}$$"""
    import inspect
    params = set(inspect.signature(run_row_restore_law).parameters)
    assert not (params & {"rows", "sol", "episode", "targets"}), params


def test_6_poison_evidence_does_not_reach_the_l3_path():
    r"""A78 §66.8: the empty cell is demonstrated, not assumed.

    Every evaluator-side argument is a placeholder that raises on *any* attribute access or
    iteration. $L_3$ still runs to completion, which shows the path reads no envelope input
    — while it does read the generic ``q_reference`` for the ledger, so the two are
    separated by evidence rather than by reading the code.
    """
    class Poison:
        def __getattr__(self, name):
            raise AssertionError(f"the L3 path touched evaluator evidence: .{name}")

        def __iter__(self):
            raise AssertionError("the L3 path iterated evaluator evidence")

        def __getitem__(self, k):
            raise AssertionError("the L3 path indexed evaluator evidence")

        def __bool__(self):
            raise AssertionError("the L3 path tested evaluator evidence for truth")

    rows, addrs, _target, state, written = scene(overrides=1)
    poison = Poison()
    res = run_dq_law(DQLocalOracleRestore, state, addrs, poison, VIEW,
                     sol=poison, episode=poison)
    assert res.ledger.n_scalar >= 1
    assert not any(e in state.q_overrides for e in written), "the row was restored"


def test_7_the_empty_cell_is_asserted_not_inherited():
    """A cell that declares a field set must not silently acquire a builder."""
    class _Widened:
        name, alias_of, tier = "WidenedL3", None, Tier.L3_ORACLE

        def plan(self, addresses, targets):
            return LawPlan(self.name, tuple(AddressPlan(a) for a in addresses))

    import rfl_rebuild.b1.runner as runner
    original = DQ_SLICE.cells
    try:
        object.__setattr__(DQ_SLICE, "cells",
                           {**dict(DQ_SLICE.cells),
                            Tier.L3_ORACLE: frozenset({"anything"})})
        with pytest.raises(ProtocolError) as ei:
            run_dq_law(_Widened(), LearnerPersistentState(), [], None, VIEW)
        assert "empty delivery" in str(ei.value)
    finally:
        object.__setattr__(DQ_SLICE, "cells", original)
    assert runner is not None


# --------------------------------------------------------------------------- #
# 4. the row operation and the plan shape
# --------------------------------------------------------------------------- #

def test_8_an_address_plan_is_entry_edits_or_one_row_op_never_both():
    rows, addrs, target, _state, written = scene(overrides=1)
    entry = written[0]
    with pytest.raises(ProtocolError) as ei:
        AddressPlan(target, (Edit(Q, entry, 1.0),), None, RestoreRow(target))
    assert "never both" in str(ei.value)
    with pytest.raises(ProtocolError) as ei2:
        AddressPlan(target, (), NO_VALID_ALTERNATIVE, RestoreRow(target))
    assert "conflicting" in str(ei2.value)
    with pytest.raises(ProtocolError) as ei3:
        AddressPlan(target, (), None,
                    RestoreRow(DecisionAddress(
                        state=State(x=0, y=0, t=0, kappa=0, phi=0), z=1, m=0)))
    assert "must name the context" in str(ei3.value)


def test_9_the_row_op_owner_is_the_credited_context():
    rows, addrs, target, _state, _written = scene()
    plan = DQLocalOracleRestore().plan(addrs, None)
    assert all(dq_owner(p.row_op) == p.address for p in plan.plans)


def test_9b_a_stand_in_row_operation_cannot_grant_row_restore():
    r"""Nominal closure at the plan boundary.

    `_lower_row_ops` only ever asks for `.context`, so an object that has one would become
    a real row restore if the constructor let it through. The type is closed exactly as
    `Tier`, `QReferenceView` and the typed domain are.
    """
    rows, addrs, target, _state, _written = scene(overrides=1)

    class FakeRowOp:
        context = target

    with pytest.raises(ProtocolError) as ei:
        AddressPlan(target, row_op=FakeRowOp())
    assert "is not one" in str(ei.value)

    class Subclassed(RestoreRow):
        pass

    with pytest.raises(ProtocolError) as ei2:
        AddressPlan(target, row_op=Subclassed(target))
    assert "is not one" in str(ei2.value)


def test_9c_a_row_operation_cannot_leak_into_another_architecture():
    r"""The other half of §66.5: the runner must CONSULT the resolver.

    A law registered against $D_{patch}$ can emit a `RestoreRow` -- the plan object is
    shared type-wise -- and before the owner check it reached the lowering, where it
    degenerated into that slice's edit kind. "The result happens to be equivalent" is not a
    contract; the resolver is.
    """
    class PatchL3:
        name, alias_of, tier = "PatchRowRestore", None, Tier.L3_ORACLE

        def plan(self, addresses, targets):
            return LawPlan(self.name, tuple(AddressPlan(a, row_op=RestoreRow(a))
                                            for a in addresses))

    rows, addrs, target, state, _written = scene(overrides=1)
    with pytest.raises(ProtocolError) as ei:
        run_patch_law_with_envelope(PatchL3(), state, addrs, None,
                                    spec=PATCH_SLICE)
    assert "owner_locality" in str(ei.value), ei.value
    # and the D_Q resolver accepts the same plan, so the rejection is the slice's
    assert dq_owner(RestoreRow(target)) == target


def test_9d_a_real_run_depends_on_the_row_owner_resolver():
    r"""`dq_owner(RestoreRow(x)) == x` must be on the execution path, not beside it.

    The isolated assertion in `test_9` shows the function returns the right value. This runs
    the arm, so removing the resolver's row branch fails a *real* L3 run rather than only a
    unit check of the helper.
    """
    rows, addrs, target, state, written = scene(overrides=2)
    res = run_row_restore_law(DQLocalOracleRestore, state, addrs, VIEW)
    assert res.ledger.n_scalar == 2
    assert not any(e in state.q_overrides for e in written)


def test_9e_the_same_tier_reference_actually_writes_nothing():
    r"""A78 §66.2 added `NoWriteRef(L3)`; this runs it.

    The registry test shows the name is there. This shows the arm is the reference and not
    the treatment wearing a different label: overrides present, nothing moves, no scalars,
    every receipt `EVALUABLE_NOOP`, fingerprint unchanged.
    """
    rows, addrs, target, state, written = scene(overrides=2)
    before = dict(state.q_overrides)
    assert before, "the probe needs a non-empty pre-state"
    res = run_row_restore_law(NoWriteRef(Tier.L3_ORACLE), state, addrs, VIEW)
    led = res.ledger
    assert dict(state.q_overrides) == before, "the reference must not restore anything"
    assert led.n_scalar == 0 and led.n_changed_addresses == 0
    assert led.fingerprint_pre == led.fingerprint_post
    assert set(r.status for r in led.receipts) == {EVALUABLE_NOOP}
    assert led.n_addressed == len(addrs)
    led.check_fingerprint_invariants()


# --------------------------------------------------------------------------- #
# 5. lowering
# --------------------------------------------------------------------------- #

def test_10_lowering_uses_the_pre_state_and_the_ledger_reads_its_output():
    r"""A78 §66.6. A row-op-only plan has ``edits=()`` before lowering; if the receipt were
    computed from that, a real deletion would be reported ``EVALUABLE_NOOP``."""
    rows, addrs, target, state, written = scene(overrides=2)
    res = run_row_restore_law(DQLocalOracleRestore, state, addrs, VIEW)
    led = res.ledger
    assert led.n_scalar == 2, "the two present overrides"
    receipt = next(r for r in led.receipts if r.address == target)
    assert receipt.status == APPLIED and receipt.store_changed
    assert led.fingerprint_pre != led.fingerprint_post
    assert not any(e in state.q_overrides for e in written)
    led.check_fingerprint_invariants()
    assert led.sum_abs_delta > 0.0 and led.max_abs_delta <= led.sum_abs_delta
    # the row is gone, and nothing outside it moved
    assert all(k.state == target.state and k.z == target.z and k.m == target.m
               for k in written)


def test_11_idempotence_the_second_run_restores_nothing():
    r"""$$\texttt{RestoreRow}(S) \to \texttt{RestoreRow}(\texttt{RestoreRow}(S))$$

    with $k=0$ and ``EVALUABLE_NOOP`` the second time. Its content is precise: the lowering
    read **its own run's** pre-state rather than a stale or reused result.
    """
    rows, addrs, target, state, _written = scene(overrides=2)
    first = run_row_restore_law(DQLocalOracleRestore, state, addrs, VIEW)
    assert first.ledger.n_scalar == 2
    before = dict(state.q_overrides)
    second = run_row_restore_law(DQLocalOracleRestore, state, addrs, VIEW)
    assert second.ledger.n_scalar == 0
    assert second.ledger.n_changed_addresses == 0
    assert second.ledger.fingerprint_pre == second.ledger.fingerprint_post
    assert dict(state.q_overrides) == before
    assert set(r.status for r in second.ledger.receipts) == {EVALUABLE_NOOP}


def test_11b_the_lowering_is_recomputed_for_each_run():
    r"""A78 §66.8's idempotence clause read at its sharpest.

    The same credited row, two different pre-states: if the lowering were reused from the
    first run, the second would delete the *first* run's entries — which are absent, so
    nothing would change — and the second run's genuine overrides would survive, with the
    ledger reporting zero scalars while the store still held them.
    """
    rows, addrs, target, first_state, first_written = scene(overrides=1)
    run_row_restore_law(DQLocalOracleRestore, first_state, addrs, VIEW)
    assert not any(e in first_state.q_overrides for e in first_written)

    second_state = LearnerPersistentState()
    allowed = sorted(K.option_actions(target.z, K.ControlState(z=target.z, m=target.m),
                                      target.state))
    second_entry = QAddress(state=target.state, z=target.z, m=target.m,
                            a=allowed[-1])
    second_state.apply_transaction(
        [Edit(Q, second_entry, VIEW.value(second_entry) + 3.0)], q_reference=VIEW)
    assert second_entry not in first_written, "a different entry from the first run's"
    res = run_row_restore_law(DQLocalOracleRestore, second_state, addrs, VIEW)
    assert res.ledger.n_scalar == 1, "the second run's own override, not the first's"
    assert second_entry not in second_state.q_overrides


def test_12_a_row_with_no_overrides_is_a_noop_with_an_empty_edit_set():
    rows, addrs, target, state, _written = scene(overrides=0)
    res = run_row_restore_law(DQLocalOracleRestore, state, addrs, VIEW)
    assert res.ledger.n_scalar == 0
    receipt = next(r for r in res.ledger.receipts if r.address == target)
    assert receipt.status == EVALUABLE_NOOP
    assert len(res.ledger.receipts) == len(addrs), "still one receipt per context"


def test_13_a_row_restore_does_not_reach_outside_its_credited_rows():
    r"""Row scope is a statement about **rows**, so the witness must be a foreign row.

    An entry at another *credited* context is legitimately deleted — that row is restored
    too — so the test puts an override at a context that is not among the credited
    addresses at all, and requires it to survive.
    """
    rows, addrs, target, state, written = scene(overrides=2)
    # a context at the same state but a different opt/context index, not credited
    foreign_ctx = None
    for m2 in sorted({0, 1} - {target.m}):
        cand = K.option_actions(target.z, K.ControlState(z=target.z, m=m2),
                                target.state)
        if not cand:
            continue
        foreign_ctx = (m2, sorted(cand)[0])
        break
    if foreign_ctx is None:
        pytest.fail("the probe needs a second legal context at this state")
    m2, a2 = foreign_ctx
    if any(a.z == target.z and a.m == m2 and a.state == target.state for a in addrs):
        pytest.fail("the probe picked a credited context")            # pragma: no cover
    foreign = QAddress(state=target.state, z=target.z, m=m2, a=a2)
    state.apply_transaction([Edit(Q, foreign, VIEW.value(foreign) + 5.0)],
                            q_reference=VIEW)
    assert foreign in state.q_overrides

    res = run_row_restore_law(DQLocalOracleRestore, state, addrs, VIEW)
    assert foreign in state.q_overrides, \
        "an entry outside every credited row must survive a row restore"
    assert res.ledger.n_scalar == 2, "only the two overrides in the credited row"
    assert not any(e in state.q_overrides for e in written)


def test_14_a_law_from_another_cell_is_refused_by_the_l3_entry_point():
    rows, addrs, _target, state, _written = scene()
    with pytest.raises(ProtocolError) as ei:
        run_row_restore_law(FactualReturnWrite, state, addrs, VIEW)
    assert "runs the L3 cell only" in str(ei.value)
    with pytest.raises(ProtocolError):
        run_row_restore_law(CounterfactualReturnWrite, state, addrs, VIEW)


def test_15_the_reference_is_still_the_transactions():
    """§66.4: no *new* entry point, and the existing one is still required."""
    rows, addrs, _target, state, _written = scene(overrides=1)
    with pytest.raises(ProtocolError):
        run_row_restore_law(DQLocalOracleRestore, state, addrs, None)
    class _Fake:
        pass
    with pytest.raises(ProtocolError):
        run_row_restore_law(DQLocalOracleRestore, state, addrs, _Fake())
