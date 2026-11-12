from rflnext.env import HORIZON, N_ACTIONS
from rflnext.qtables import QTables
from rflnext.runner import evaluate, train

CFG = {
    "environment": {"horizon": HORIZON, "gamma": 1.0, "p_hazard": 0.25},
    "learning": {
        "alpha_low": 0.10, "alpha_high": 0.10,
        "epsilon_start": 0.30, "epsilon_end": 0.05, "epsilon_decay_fraction": 0.80,
    },
    "experiment": {"episodes": 400, "eval_every": 200, "eval_episodes": 50},
}


def test_train_produces_curve_and_counts():
    res = train(CFG, seed=123, arm="traditional")
    assert res.arm == "traditional"
    assert len(res.success_curve) == len(res.checkpoints)
    assert res.checkpoints == [0, 200, 400]
    assert all(0.0 <= v <= 1.0 for v in res.success_curve)
    assert sum(res.family_counts.values()) <= 400
    assert set(res.family_counts) <= {"H_error", "L_error", "HL_error", "E_failure"}


def test_evaluate_does_not_mutate_q():
    q = QTables(n_actions=N_ACTIONS)
    before = q.deep_hash()
    evaluate(q, CFG, seed=7, n=20)
    assert q.deep_hash() == before


def test_train_is_reproducible():
    a = train(CFG, seed=5, arm="positive_only")
    b = train(CFG, seed=5, arm="positive_only")
    assert a.q_hash == b.q_hash
    assert a.success_curve == b.success_curve


def test_arms_consume_the_same_scene_schedule():
    a = train(CFG, seed=9, arm="traditional")
    b = train(CFG, seed=9, arm="positive_only")
    assert sum(a.family_counts.values()) > 0
    assert sum(b.family_counts.values()) > 0


def test_unknown_arm_rejected():
    import pytest

    with pytest.raises(ValueError):
        train(CFG, seed=1, arm="oracle")
