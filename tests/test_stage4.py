import pytest

from rflnext.env import W
from rflnext.gamma import SequenceModel, generate_balanced
from rflnext.stage4 import (
    ARMS,
    NO_CORRECTION,
    _choose_module,
    _to_online_trace,
    _truth_primary,
    make_feedback_stream,
    train_arm,
)

CFG = {
    "environment": {"horizon": 8, "gamma": 1.0, "p_hazard": 0.25},
    "learning": {
        "alpha_low": 0.10, "alpha_high": 0.10, "alpha_diag": 0.10,
        "epsilon_start": 0.30, "epsilon_end": 0.05, "epsilon_decay_fraction": 0.80,
    },
    "experiment": {
        "episodes": 400, "eval_every": 200, "eval_episodes": 30, "p_false": 0.40,
    },
}


@pytest.fixture(scope="module")
def model():
    return SequenceModel().fit(generate_balanced(600, seed=99, horizon=8)[:300])


def test_arm_table_matches_the_plan():
    assert set(ARMS) == {
        "traditional", "positive_only", "direct_feedback", "random_correction",
        "sequence_rfl", "learned_rfl", "oracle_rfl",
        "aux_penalty_rfl", "global_value_rfl",
    }
    assert NO_CORRECTION == {"traditional", "positive_only"}


def test_random_correction_arm_needs_an_rng_and_picks_blindly(model):
    import numpy as np

    rec = _rec(option=0, goal_lane=0, final_x=2, final_y=0)
    with pytest.raises(ValueError):
        _choose_module("random_correction", rec, model, "")
    rng = np.random.default_rng(0)
    picks = {_choose_module("random_correction", rec, model, "", rng=rng)[0] for _ in range(200)}
    assert picks <= {"H", "L", None}
    assert "H" in picks and "L" in picks  # it really is blind to the truth


def test_random_correction_arm_is_reproducible(model):
    a = train_arm(CFG, seed=3, arm="random_correction", model=model)
    b = train_arm(CFG, seed=3, arm="random_correction", model=model)
    assert a.q_hash == b.q_hash
    assert a.collateral == b.collateral


def test_feedback_stream_respects_the_error_rate():
    s = make_feedback_stream(1, 4000, 0.40)
    wrong = sum(1 for v in s if v != "")
    assert abs(wrong / len(s) - 0.40) < 0.03
    assert set(s) <= {"", "H", "L", "E"}


def test_feedback_stream_is_deterministic():
    assert make_feedback_stream(3, 100, 0.4) == make_feedback_stream(3, 100, 0.4)


def _rec(option, goal_lane, final_x, final_y, hazard=0):
    from rflnext.env import TIMEOUT
    from rflnext.labels import causal_labels
    from rflnext.runner import EpisodeRecord

    lab = causal_labels(option=option, goal_lane=goal_lane, final_x=final_x,
                        final_y=final_y, hazard=hazard, terminal=TIMEOUT)
    return EpisodeRecord(
        episode=0, terminal=TIMEOUT, steps=3, return_value=-1.0, option=option,
        goal_lane=goal_lane, hazard=hazard, final_x=final_x, final_y=final_y,
        labels=lab, n_negative_td=0, visited_low=[((0, 0, option, 1), 2)],
        visited_high=[],
    )


def test_oracle_arm_follows_the_scm(model):
    h_err = _rec(option=1, goal_lane=0, final_x=W - 1, final_y=1)
    assert _truth_primary(h_err) == "H"
    assert _choose_module("oracle_rfl", h_err, model, "")[0] == "H"

    l_err = _rec(option=0, goal_lane=0, final_x=2, final_y=0)
    assert _truth_primary(l_err) == "L"
    assert _choose_module("oracle_rfl", l_err, model, "")[0] == "L"


def test_direct_feedback_trusts_the_label_even_when_wrong(model):
    l_err = _rec(option=0, goal_lane=0, final_x=2, final_y=0)  # truth is L
    # A misleading label claiming H is forwarded verbatim.
    assert _choose_module("direct_feedback", l_err, model, "H")[0] == "H"


def test_no_correction_arms_never_correct(model):
    rec = _rec(option=0, goal_lane=0, final_x=2, final_y=0)
    for arm in NO_CORRECTION:
        assert _choose_module(arm, rec, model, "H")[0] is None


def test_sequence_and_learned_arms_produce_a_module(model):
    rec = _rec(option=0, goal_lane=0, final_x=2, final_y=0)
    for arm in ("sequence_rfl", "learned_rfl"):
        module, spent = _choose_module(arm, rec, model, "")
        assert module in {"H", "L", None}
    _, spent = _choose_module("learned_rfl", rec, model, "")
    assert spent <= 1


def test_online_trace_exposes_only_learner_visible_fields(model):
    rec = _rec(option=0, goal_lane=0, final_x=2, final_y=0)
    ot = _to_online_trace(rec)
    assert set(ot.__dataclass_fields__) == {
        "option", "final_x", "final_y", "terminal", "goal_lane", "hazard"
    }


def test_oracle_arm_has_zero_collateral(model):
    res = train_arm(CFG, seed=1, arm="oracle_rfl", model=model)
    assert res.corrections > 0
    assert res.collateral == 0
    assert res.update_precision == pytest.approx(1.0)


def test_direct_feedback_has_high_collateral(model):
    res = train_arm(CFG, seed=1, arm="direct_feedback", model=model)
    assert res.corrections > 0
    assert res.collateral_rate is not None and res.collateral_rate > 0.1


def test_traditional_arm_makes_no_corrections(model):
    res = train_arm(CFG, seed=1, arm="traditional", model=model)
    assert res.corrections == 0
    assert res.update_precision is None


def test_training_is_reproducible(model):
    a = train_arm(CFG, seed=2, arm="learned_rfl", model=model)
    b = train_arm(CFG, seed=2, arm="learned_rfl", model=model)
    assert a.q_hash == b.q_hash
    assert a.success_curve == b.success_curve
