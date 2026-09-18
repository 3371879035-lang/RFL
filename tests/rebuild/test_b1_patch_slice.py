"""A76 §63.9-63.13 — the D_patch vertical slice.

Fourteen gates, including the three that guard against a *plausible* wrong
implementation rather than an obviously broken one: one transaction per scene, a
missing target record that must not masquerade as a verified absence, and a law that
must not be able to write outside its credited addresses.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1 import (  # noqa: E402
    APPLIED, EVALUABLE_NOOP, LAWS, NO_VALID_ALTERNATIVE, PROTOCOL_ERROR,
    DeleteFactualPatch, LocalOracleRestore, NoWrite, ProtocolError,
    SetAlternative, TargetRecord, independent_treatment_count, law_metadata,
    run_patch_law_with_envelope,
)
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import State  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    DECISION, DecisionAddress, Edit, LearnerPersistentState, StoreTransactionError,
)

UP, DOWN, LEFT, RIGHT, WAIT = K.UP, K.DOWN, K.LEFT, K.RIGHT, K.WAIT

A = DecisionAddress(state=State(x=1, y=2, t=1, kappa=0, phi=0), z=1, m=0)
B = DecisionAddress(state=State(x=2, y=2, t=2, kappa=0, phi=0), z=1, m=0)
C = DecisionAddress(state=State(x=3, y=2, t=3, kappa=0, phi=0), z=1, m=0)
ADDRESSES = (A, B, C)


def envelope(*, a_alt=UP, b_alt=None, c_alt=DOWN):
    """A TOTAL envelope: every credited address has a record."""
    return {A: TargetRecord(A, a_alt, RIGHT),
            B: TargetRecord(B, b_alt, RIGHT),
            C: TargetRecord(C, c_alt, RIGHT)}


def state_with(*pairs):
    """``state_with((A, DOWN), (C, UP))`` — addresses are not keyword names."""
    s = LearnerPersistentState()
    edits = [Edit(DECISION, a, v) for a, v in pairs]
    if edits:
        s.apply_transaction(edits)
    return s


def statuses(result):
    return {r.address: r.status for r in result.ledger.receipts}


# --------------------------------------------------------------------------- #
# 1. NoWrite
# --------------------------------------------------------------------------- #

def test_1_nowrite_plans_no_edit_and_every_address_is_evaluable_noop():
    s = state_with((A, DOWN))          # even with a patch present
    plan = NoWrite().plan(ADDRESSES, envelope(), s.snapshot())
    assert plan.edits == (), "NoWrite must create no edit at all"
    res = run_patch_law_with_envelope(NoWrite, s, ADDRESSES, envelope())
    assert set(statuses(res).values()) == {EVALUABLE_NOOP}
    assert res.ledger.n_changed_addresses == 0
    assert res.ledger.fingerprint_pre == res.ledger.fingerprint_post


# --------------------------------------------------------------------------- #
# 2. DeleteFactualPatch
# --------------------------------------------------------------------------- #

def test_2_delete_present_is_applied_absent_is_evaluable_noop():
    s = state_with((A, DOWN))          # a patch exists only at A
    res = run_patch_law_with_envelope(DeleteFactualPatch, s, ADDRESSES, envelope())
    st = statuses(res)
    assert st[A] == APPLIED, "deleting a present patch changes the store"
    assert st[B] == EVALUABLE_NOOP and st[C] == EVALUABLE_NOOP
    assert dict(res.post_state.decision_overrides) == {}


# --------------------------------------------------------------------------- #
# 3. SetAlternative
# --------------------------------------------------------------------------- #

def test_3_set_alternative_new_is_applied_already_equal_is_noop():
    s = state_with((A, UP))            # A already holds the target
    res = run_patch_law_with_envelope(SetAlternative, s, ADDRESSES, envelope())
    st = statuses(res)
    assert st[A] == EVALUABLE_NOOP, "writing the value it already holds is a no-op"
    assert st[C] == APPLIED
    assert dict(res.post_state.decision_overrides)[A] == UP
    assert dict(res.post_state.decision_overrides)[C] == DOWN

    s2 = LearnerPersistentState()
    res2 = run_patch_law_with_envelope(SetAlternative, s2, ADDRESSES, envelope())
    assert statuses(res2)[A] == APPLIED


def test_3b_a_change_of_value_is_applied():
    s = state_with((A, LEFT))
    res = run_patch_law_with_envelope(SetAlternative, s, ADDRESSES, envelope())
    assert statuses(res)[A] == APPLIED
    assert dict(res.post_state.decision_overrides)[A] == UP


# --------------------------------------------------------------------------- #
# 4. verified absence of an alternative
# --------------------------------------------------------------------------- #

def test_4_verified_absence_is_no_valid_alternative_and_deletes_nothing():
    s = state_with((B, LEFT))          # a patch sits at the very address
    res = run_patch_law_with_envelope(SetAlternative, s, ADDRESSES, envelope())
    st = statuses(res)
    assert st[B] == NO_VALID_ALTERNATIVE
    assert dict(res.post_state.decision_overrides)[B] == LEFT, \
        "an unavailable alternative must not delete the existing patch"
    assert B in st, "the address stays in the ledger and in the population"


# --------------------------------------------------------------------------- #
# 5. a MISSING target record is not a verified absence
# --------------------------------------------------------------------------- #

def test_5_missing_target_record_is_a_protocol_error():
    partial = envelope()
    del partial[B]
    with pytest.raises(ProtocolError) as ei:
        run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                    ADDRESSES, partial)
    assert PROTOCOL_ERROR in str(ei.value) or "missing record" in str(ei.value)


def test_5b_missing_record_is_distinguishable_from_a_verified_absence():
    """The two must not collapse: one is a fact, the other is a broken generator."""
    verified = envelope()                       # B has a record with alternative=None
    res = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                      ADDRESSES, verified)
    assert statuses(res)[B] == NO_VALID_ALTERNATIVE
    partial = envelope()
    del partial[B]
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                    ADDRESSES, partial)


# --------------------------------------------------------------------------- #
# 6. one unavailable address does not cancel the others
# --------------------------------------------------------------------------- #

def test_6_an_unavailable_address_does_not_cancel_the_others():
    s = LearnerPersistentState()
    res = run_patch_law_with_envelope(SetAlternative, s, ADDRESSES, envelope())
    st = statuses(res)
    assert st[B] == NO_VALID_ALTERNATIVE
    assert st[A] == APPLIED and st[C] == APPLIED, "A and C still commit"
    assert dict(res.post_state.decision_overrides) == {A: UP, C: DOWN}
    assert res.ledger.n_addressed == 3, "all three addresses remain addressed"


# --------------------------------------------------------------------------- #
# 7. exactly one transaction per scene
# --------------------------------------------------------------------------- #

def test_7_one_scene_commits_in_exactly_one_transaction(monkeypatch):
    calls = []
    original = LearnerPersistentState.apply_transaction

    def spy(self, edits):
        calls.append(tuple(edits))
        return original(self, edits)

    monkeypatch.setattr(LearnerPersistentState, "apply_transaction", spy)
    run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                ADDRESSES, envelope())
    assert len(calls) == 1, f"expected one transaction, got {len(calls)}"
    assert len(calls[0]) == 2, "only A and C form edits; B is skipped"


def test_7b_no_edits_means_no_transaction_at_all(monkeypatch):
    calls = []
    original = LearnerPersistentState.apply_transaction

    def spy(self, edits):
        calls.append(tuple(edits))
        return original(self, edits)

    monkeypatch.setattr(LearnerPersistentState, "apply_transaction", spy)
    run_patch_law_with_envelope(NoWrite, LearnerPersistentState(), ADDRESSES,
                                envelope())
    assert calls == [], "NoWrite must not open a transaction"


# --------------------------------------------------------------------------- #
# 8. locality: a law may not write outside its credited addresses
# --------------------------------------------------------------------------- #

class _OutOfLocalityLaw:
    name = "MaliciousOutOfLocality"
    alias_of = None

    def plan(self, addresses, targets, snapshot):
        from rfl_rebuild.b1.laws import LawPlan, PlannedWrite
        rogue = DecisionAddress(state=State(x=0, y=2, t=0, kappa=0, phi=0), z=0, m=0)
        return LawPlan(self.name, (PlannedWrite(rogue, Edit(DECISION, rogue, UP), None),))


def test_8_a_law_writing_outside_its_credited_addresses_fails_stop():
    s = LearnerPersistentState()
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_OutOfLocalityLaw(), s, ADDRESSES, envelope())
    assert s.healthy, "the rogue write must not have landed"


# --------------------------------------------------------------------------- #
# 9. a failed transaction invalidates the whole run
# --------------------------------------------------------------------------- #

class _DuplicateEditLaw:
    name = "MaliciousDuplicate"
    alias_of = None

    def plan(self, addresses, targets, snapshot):
        from rfl_rebuild.b1.laws import LawPlan, PlannedWrite
        return LawPlan(self.name,
                       (PlannedWrite(A, Edit(DECISION, A, UP), None),
                        PlannedWrite(A, Edit(DECISION, A, DOWN), None)))


def test_9_a_failed_transaction_is_a_fail_stop_with_identical_state():
    s = state_with((C, LEFT))
    fp_before = __import__("rfl_rebuild.b1", fromlist=["x"]).fingerprint(s)
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_DuplicateEditLaw(), s, (A, C), envelope())
    fp_after = __import__("rfl_rebuild.b1", fromlist=["x"]).fingerprint(s)
    assert fp_before == fp_after, "a rejected transaction leaves the store identical"
    assert dict(s.decision_overrides) == {C: LEFT}


def test_9b_protocol_error_is_a_separate_hierarchy():
    from rfl_rebuild.method.credit import ProtocolError as CreditProtocolError
    from rfl_rebuild.learner.store import StoreTransactionError
    assert not issubclass(ProtocolError, CreditProtocolError)
    assert not issubclass(ProtocolError, StoreTransactionError)


# --------------------------------------------------------------------------- #
# 10-11. the L3 alias
# --------------------------------------------------------------------------- #

def test_10_alias_is_indistinguishable_from_its_target():
    s1 = state_with((A, DOWN), (C, UP))
    s2 = state_with((A, DOWN), (C, UP))
    r_plain = run_patch_law_with_envelope(DeleteFactualPatch, s1, ADDRESSES,
                                          envelope())
    r_alias = run_patch_law_with_envelope(LocalOracleRestore, s2, ADDRESSES,
                                          envelope())
    assert dict(r_plain.post_state.decision_overrides) == \
        dict(r_alias.post_state.decision_overrides)
    assert [r.canon() for r in r_plain.ledger.receipts] == \
        [r.canon() for r in r_alias.ledger.receipts]
    assert r_plain.ledger.canonical().replace('"', "") != ""      # sanity
    assert (r_plain.ledger.n_scalar, r_plain.ledger.sum_abs_delta,
            r_plain.ledger.max_abs_delta) == \
        (r_alias.ledger.n_scalar, r_alias.ledger.sum_abs_delta,
         r_alias.ledger.max_abs_delta)
    assert r_plain.ledger.fingerprint_pre == r_alias.ledger.fingerprint_pre
    assert r_plain.ledger.fingerprint_post == r_alias.ledger.fingerprint_post


def test_10b_the_alias_shares_the_implementation():
    assert issubclass(LocalOracleRestore, DeleteFactualPatch)
    assert LocalOracleRestore.plan is DeleteFactualPatch.plan, \
        "the alias must not be a second implementation"
    assert DeleteFactualPatch.name == "DeleteFactualPatch", \
        "registering the alias must not mutate the target"


def test_11_alias_is_not_an_independent_treatment():
    md = dict((n, (kind, target)) for n, kind, target in law_metadata())
    assert md["LocalOracleRestore"] == ("alias", "DeleteFactualPatch")
    assert md["NoWrite"][0] == "reference"
    assert md["DeleteFactualPatch"][0] == "operation"
    assert md["SetAlternative"][0] == "operation"
    assert independent_treatment_count() == 3, "3 independent treatments, not 4"
    assert len(LAWS) == 4, "four registered arms"


# --------------------------------------------------------------------------- #
# 12. the write is actually persistent
# --------------------------------------------------------------------------- #

def test_12_the_next_episode_reads_the_persistent_effect():
    s = LearnerPersistentState()
    run_patch_law_with_envelope(SetAlternative, s, ADDRESSES, envelope())
    # a NEW snapshot, as the next episode would take
    snap = s.snapshot()
    assert snap.decision_overrides[A] == UP
    adapter = snap.decision_provider(lambda st, c: WAIT)
    assert adapter(A.state, K.ControlState(z=A.z, m=A.m)) == UP, \
        "the patch must win over the base provider in the next episode"


def test_12b_a_rolled_back_run_leaves_no_persistent_effect():
    s = LearnerPersistentState()
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_DuplicateEditLaw(), s, (A, C), envelope())
    assert s.snapshot().decision_provider(lambda st, c: WAIT)(
        A.state, K.ControlState(z=A.z, m=A.m)) == WAIT


# --------------------------------------------------------------------------- #
# 13. the law layer cannot see regime, truth or scenario identity
# --------------------------------------------------------------------------- #

_FORBIDDEN = ("regime", "fire_code", "Gamma", "world_id", "block_id", "S_T",
              "S_P", "phase", "kappa")


@pytest.mark.parametrize("law", LAWS)
def test_13_law_plan_signature_has_no_forbidden_parameters(law):
    import inspect
    params = set(inspect.signature(law.plan).parameters)
    assert not (params & set(_FORBIDDEN)), f"{law.name}.plan exposes {params}"


@pytest.mark.parametrize("law", LAWS)
def test_13b_law_objects_carry_no_forbidden_attributes(law):
    for name in _FORBIDDEN:
        assert not hasattr(law, name), f"{law.name} carries {name}"


def test_13c_no_forbidden_identifier_appears_in_the_law_CODE():
    """AST-based, so the docstrings that *forbid* these names do not trip it."""
    path = ROOT / "src" / "rfl_rebuild" / "b1" / "laws.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            seen.add(node.id)
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr)
        elif isinstance(node, ast.arg):
            seen.add(node.arg)
    bad = sorted(n for n in seen if n in _FORBIDDEN)
    assert not bad, f"forbidden identifiers in law code: {bad}"


# --------------------------------------------------------------------------- #
# 14. order independence, including the ledger bytes
# --------------------------------------------------------------------------- #

def test_14_input_order_does_not_change_state_or_ledger_bytes():
    fwd = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                      ADDRESSES, envelope())
    rev = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                      tuple(reversed(ADDRESSES)), envelope())
    assert dict(fwd.post_state.decision_overrides) == \
        dict(rev.post_state.decision_overrides)
    assert fwd.ledger.fingerprint_post == rev.ledger.fingerprint_post
    assert fwd.ledger.canonical() == rev.ledger.canonical(), \
        "the ledger serialization must be order-independent"


def test_14b_a_shuffled_target_mapping_is_irrelevant():
    base = envelope()
    shuffled = dict(reversed(list(base.items())))
    r1 = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                     ADDRESSES, base)
    r2 = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                     ADDRESSES, shuffled)
    assert r1.ledger.canonical() == r2.ledger.canonical()


# --------------------------------------------------------------------------- #
# ledger shape
# --------------------------------------------------------------------------- #

def test_ledger_reports_zero_scalar_metrics_and_marks_them_inapplicable():
    res = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                      ADDRESSES, envelope())
    led = res.ledger
    assert led.scalar_metrics_applicable is False
    assert (led.n_scalar, led.sum_abs_delta, led.max_abs_delta) == (0, 0.0, 0.0)
    assert led.n_addressed == 3
    assert led.n_changed_addresses == 2
    assert led.status_counts[APPLIED] == 2
    assert led.status_counts[NO_VALID_ALTERNATIVE] == 1
    assert led.n_changed_addresses > 0 and led.n_scalar == 0, \
        "APPLIED with zero scalar delta must not read as a no-op"


def test_receipts_carry_no_truth_or_scenario_identity():
    res = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                      ADDRESSES, envelope())
    for r in res.ledger.receipts:
        for name in _FORBIDDEN:
            assert not hasattr(r, name)
        assert not hasattr(r, "gamma_star")
        assert set(r.__slots__) == {"address", "status", "store_changed"}


def test_no_write_run_still_produces_a_full_ledger():
    res = run_patch_law_with_envelope(NoWrite, LearnerPersistentState(),
                                      ADDRESSES, envelope())
    assert res.ledger.n_addressed == 3
    assert res.ledger.status_counts[EVALUABLE_NOOP] == 3
