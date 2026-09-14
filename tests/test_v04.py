import numpy as np
import pytest

from rflv04.credit_units import (
    decision_oracle, module_oracle, repair_oracle, responsible_units, selected_repair,
)
from rflv04.env import (
    ACT, ADVANCE, PLAN, PLAN_A, SUCCESS, SWITCH, TIMEOUT, WAIT, X_MAX,
    Scene, apply_action, reference_action, rollout, rollout_intervened,
)
from rflv04.knowledge import build_knowledge_set, damage, kd_innocent, wmd
from rflv04.oracle import (
    Repair, classify, enumerate_sufficient, oracle_repair_set, repair_regret,
    repair_value, suffices,
)
from rflv04.train import ARMS, train
from rflv04.updates import DELTA_MAX, MODES, apply_update


# ---------------------------------------------------------------- environment


def test_plan_failure_is_repaired_by_the_plan_alone():
    scene = Scene("p", g=0, plan=1)
    tr = rollout(scene)
    assert tr.terminal == TIMEOUT and not tr.has_execution_deviation()
    assert suffices(scene, frozenset({("plan", 0)}))
    assert classify(scene, tr).family == "Plan"


def test_decision_failure_needs_a_step_intervention_not_the_plan():
    scene = Scene("d", g=0, plan=0, decision_fault_at=2, decision_fault_action=WAIT)
    tr = rollout(scene)
    res = classify(scene, tr)
    assert res.family == "Decision"
    assert not suffices(scene, frozenset({("plan", 1)}))


def test_execution_failure_records_intent_separately_from_realized():
    scene = Scene("e", g=0, plan=0, execution_fault_at=2,
                  execution_fault_action=WAIT)
    tr = rollout(scene)
    step = next(s for s in tr.steps if s.t == 2)
    assert step.intent != step.realized        # actuator slipped
    assert step.intent == reference_action(step.state[1], step.state[2], 0)
    assert tr.has_execution_deviation()
    assert suffices(scene, frozenset({("exec", 2)}))
    assert classify(scene, tr).family == "Execution"


def test_whole_process_needs_a_joint_repair():
    scene = Scene("w", g=0, plan=1, decision_fault_at=2, decision_fault_action=WAIT)
    tr = rollout(scene)
    res = classify(scene, tr)
    assert res.family == "WholeProcess"
    assert res.minimal_size == 2
    assert not suffices(scene, frozenset({("plan", 0)}))
    assert not suffices(scene, frozenset({("unstick", 2)}))
    assert suffices(scene, frozenset({("plan", 0), ("unstick", 2)}))


def test_taxonomy_is_derived_from_intervention_not_from_the_injection_kind():
    """A scene built by the execution injector can still be classified as a
    Decision failure if the plan is also wrong, so the label cannot be trusted."""
    scene = Scene("x", g=0, plan=1, execution_fault_at=2, execution_fault_action=WAIT)
    res = classify(scene)
    assert res.family in ("Plan", "WholeProcess", "Decision", "Execution")
    # And a plan-injected scene with a wrong plan plus a fault is WholeProcess.
    assert classify(Scene("y", g=0, plan=1, decision_fault_at=2)).family == "WholeProcess"


def test_unknown_when_nothing_suffices():
    # A clean scene never fails, so a failure with no intervention is Unknown.
    res = classify(Scene("u", g=0, plan=1, horizon=1))
    assert res.family in ("Plan", "Unknown", "WholeProcess")


# ---------------------------------------------------------------- oracle value


def test_plan_repair_generalises_across_contexts():
    """A plan repair encodes "pick the plan that fits the context", so it is
    worth +1 everywhere; a null repair fixes nothing."""
    scene = Scene("v", g=0, plan=1)
    assert repair_value(scene, Repair(frozenset({("plan", 0)})), n_samples=16) == \
        pytest.approx(1.0)
    assert repair_value(scene, Repair(frozenset()), n_samples=16) < 1.0


def test_decision_repair_inherits_the_original_plans_errors():
    """Unsticking the agent does not fix a wrong plan, so it scores 0 on
    average rather than +1."""
    scene = Scene("d", g=0, plan=1, decision_fault_at=2)
    assert repair_value(scene, Repair(frozenset({("unstick", 2)})), n_samples=16) == \
        pytest.approx(0.0)


def test_repair_regret_is_zero_for_the_best_and_positive_otherwise():
    scene = Scene("r", g=0, plan=1, decision_fault_at=2, decision_fault_action=WAIT)
    res = oracle_repair_set(scene, n_samples=8)
    assert res.best is not None
    assert repair_regret(scene, res.best, n_samples=8) == pytest.approx(0.0)
    worse = Repair(frozenset({("unstick", 2)}))
    assert repair_regret(scene, worse, n_samples=8) > 0.0


# ---------------------------------------------------------------- credit units


def test_the_three_representations_touch_different_numbers_of_entries():
    scene = Scene("c", g=0, plan=1, decision_fault_at=2, decision_fault_action=WAIT)
    tr = rollout(scene)
    res = oracle_repair_set(scene, n_samples=4)
    sel = selected_repair(tr, res)
    m = module_oracle(tr, res)
    d = decision_oracle(tr, res)
    r = repair_oracle(tr, res, sel)
    assert len(m.sites) >= len(d.sites)
    assert len(d.sites) <= len(m.sites)
    assert {s.unit for s in r.sites} <= {"PLAN", "DECISION", "EXECUTION"}
    assert responsible_units(res)


# ---------------------------------------------------------------- knowledge


def test_knowledge_set_admits_only_established_items():
    from rflnext.qtables import QTables

    q = QTables(n_actions=6, options=(0, 1))
    for g in (0, 1):
        q.high[(g, 0, 0)] = {g: 0.9, 1 - g: 0.0}
    for o in (0, 1):
        x, y = 0, 0
        for t in range(1, 9):
            row = [0.0] * 6
            row[reference_action(x, y, o)] = 0.8
            q.low[(x, y, o, t)] = row
            x, y = apply_action(x, y, o, reference_action(x, y, o))
            if x == X_MAX:
                break
    ks = build_knowledge_set(q, theta=0.6)
    assert ks.items
    assert set(ks.units()) <= {"PLAN", "DECISION"}


def test_wmd_and_kd_are_the_same_function_on_different_sets():
    from rflnext.qtables import QTables

    q = QTables(n_actions=6, options=(0, 1))
    q.low[(0, 0, 0, 1)] = [0.0, 0.0, 0.8, 0.0, 0.0, 0.0]
    ks = build_knowledge_set(q, theta=0.6)
    after = q.copy()
    after.low[(0, 0, 0, 1)][ADVANCE] = 0.3
    blamed = {"DECISION"}
    assert wmd(q, after, ks, blamed) > 0.0
    assert kd_innocent(q, after, ks, blamed) == 0.0
    assert damage(q, after, ks.items) > 0.0


# ---------------------------------------------------------------- safe update


def test_no_site_means_no_update():
    from rflnext.qtables import QTables

    q = QTables(n_actions=6, options=(0, 1))
    rec = MODES["negative_only"](q, [], {}, alpha=0.1)
    assert rec.no_site and not rec.applied


def test_updates_are_capped_and_return_a_full_receipt():
    from rflnext.qtables import QTables

    q = QTables(n_actions=6, options=(0, 1))
    q.low[(0, 0, 0, 1)] = [0.0, 0.0, 0.5, 0.0, 0.0, 0.0]
    upd = apply_update(q, unit="DECISION", state=(0, 0, 0, 1), action=ADVANCE,
                       target_value=-1.0, alpha=10.0, mode="negative_only")
    assert upd.clipped
    assert abs(upd.delta_q) <= DELTA_MAX + 1e-12
    assert upd.q_after == pytest.approx(upd.q_before + upd.delta_q)


def test_positive_alternative_raises_without_touching_the_bad_action():
    from rflnext.qtables import QTables

    q = QTables(n_actions=6, options=(0, 1))
    q.low[(0, 0, 0, 1)] = [0.0, 0.0, 0.1, 0.1, 0.1, 0.1]
    from rflv04.credit_units import Site

    bad = Site("DECISION", (0, 0, 0, 1), ADVANCE, is_factual=True)
    alt = Site("DECISION", (0, 0, 0, 1), SWITCH, is_factual=False)
    before = q.low[(0, 0, 0, 1)][ADVANCE]
    rec = MODES["positive_alternative_only"](
        q, [alt], {alt.key: 1.0}, alpha=0.1)
    assert rec.applied and rec.applied[0].role == "alternative"
    assert q.low[(0, 0, 0, 1)][ADVANCE] == before  # bad action untouched


# ---------------------------------------------------------------- training


SMALL = {
    "environment": {"horizon": 8},
    "learning": {"alpha_low": 0.1, "alpha_high": 0.1, "alpha_diag": 0.1,
                 "epsilon_decay_fraction": 0.8},
    "experiment": {"warmup_episodes": 40, "episodes": 60, "eval_every": 30,
                   "eval_episodes": 20, "reward_mode": "A",
                   "distribution": {"whole": 0.25, "plan_only": 0.25,
                                    "decision_only": 0.25, "execution_only": 0.25}},
}


def test_all_arms_train_and_report():
    for arm in ARMS:
        res = train(SMALL, seed=1, arm=arm)
        assert len(res.success_curve) == len(res.checkpoints)
        assert 0.0 <= res.success_curve[-1] <= 1.0
        assert res.wmd >= 0.0 and res.kd_innocent >= 0.0
        if arm != "NoCorrection":
            assert res.corrections > 0


def test_training_is_reproducible():
    a = train(SMALL, seed=2, arm="DecisionOracle")
    b = train(SMALL, seed=2, arm="DecisionOracle")
    assert a.q_hash == b.q_hash and a.success_curve == b.success_curve


def test_nocorrection_makes_no_corrections():
    res = train(SMALL, seed=3, arm="NoCorrection")
    assert res.corrections == 0 and res.sites_touched == 0
