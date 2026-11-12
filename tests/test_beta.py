import pytest

from rflnext.beta import CONDITIONS, INNOCENT, apply_diagnostic, probe_sites, train_beta
from rflnext.env import DOWN, RIGHT, TIMEOUT, W
from rflnext.labels import causal_labels
from rflnext.qtables import QTables
from rflnext.runner import EpisodeRecord


def _rec(*, option, goal_lane, final_x, final_y, hazard=0, terminal=TIMEOUT):
    lab = causal_labels(
        option=option, goal_lane=goal_lane, final_x=final_x, final_y=final_y,
        hazard=hazard, terminal=terminal,
    )
    # The chosen first action must match the option, otherwise the fixture
    # describes an execution that never happened and the probe margin at s_L0
    # is between two actions neither of which the correction touches.
    first = RIGHT if option == 0 else DOWN
    return EpisodeRecord(
        episode=0, terminal=terminal, steps=3, return_value=-1.0,
        option=option, goal_lane=goal_lane, hazard=hazard,
        final_x=final_x, final_y=final_y, labels=lab, n_negative_td=0,
        visited_low=[((0, 0, option, 1), first), ((1, 0, option, 2), RIGHT)],
        visited_high=[],
    )


def _q_with_h_margin(goal_lane, hazard, margin=0.5):
    q = QTables(n_actions=4)
    q.high[(goal_lane, hazard)] = {goal_lane: margin, 1 - goal_lane: 0.0}
    return q


def test_conditions_table_is_complete():
    assert set(CONDITIONS) == {
        "traditional", "positive_only", "traditional_oracle",
        "positive_only_oracle", "h_only", "l_only", "hl",
    }
    assert CONDITIONS["traditional"] == ("A", "none")
    assert CONDITIONS["positive_only"] == ("B", "none")
    assert CONDITIONS["traditional_oracle"] == ("A", "oracle")
    assert CONDITIONS["hl"] == ("A", "hl")


def test_probe_sites_track_the_option():
    assert probe_sites(_rec(option=0, goal_lane=0, final_x=2, final_y=0)).l_correct == RIGHT
    assert probe_sites(_rec(option=1, goal_lane=1, final_x=2, final_y=1)).l_correct == DOWN


def test_l_error_under_learner_h_only_damages_the_innocent_h_module():
    rec = _rec(option=0, goal_lane=0, final_x=2, final_y=0)  # L is responsible
    assert rec.labels.family == "L_error"

    q = _q_with_h_margin(goal_lane=0, hazard=0, margin=0.5)
    diag = apply_diagnostic(q, rec, condition="h_only", alpha_diag=0.1)
    assert diag.corrected_h is True
    assert diag.kd_h == pytest.approx(0.1)
    assert diag.innocent == "H"


def test_l_error_under_oracle_leaves_the_innocent_h_module_untouched():
    rec = _rec(option=0, goal_lane=0, final_x=2, final_y=0)
    q = _q_with_h_margin(goal_lane=0, hazard=0, margin=0.5)
    diag = apply_diagnostic(q, rec, condition="traditional_oracle", alpha_diag=0.1)
    assert diag.corrected_h is False
    assert diag.corrected_l is True
    assert diag.kd_h == 0.0
    assert q.high_get((0, 0), 0) == pytest.approx(0.5)


def test_h_error_under_oracle_corrects_the_option_that_was_wrong():
    rec = _rec(option=1, goal_lane=0, final_x=W - 1, final_y=1)  # H is responsible
    assert rec.labels.family == "H_error"
    q = _q_with_h_margin(goal_lane=0, hazard=0, margin=0.5)
    diag = apply_diagnostic(q, rec, condition="traditional_oracle", alpha_diag=0.1)
    assert diag.corrected_h is True
    # The chosen (wrong) option is pushed down, so the correct margin grows.
    assert q.high_get((0, 0), 1) == pytest.approx(-0.1)
    assert diag.kd_h == 0.0


def test_h_error_under_l_only_damages_the_innocent_l_module():
    rec = _rec(option=1, goal_lane=0, final_x=W - 1, final_y=1)
    q = QTables(n_actions=4)
    # For option 1 the correct first action is DOWN (=1); WAIT (=3) is the
    # nominated wrong action.  Give the correct one a 0.5 margin to lose.
    q.low[(0, 0, 1, 1)] = [0.0, 0.5, 0.0, 0.0]
    diag = apply_diagnostic(q, rec, condition="l_only", alpha_diag=0.1)
    assert diag.corrected_l is True
    assert diag.innocent == "L"
    assert diag.margin_l_before == pytest.approx(0.5)
    assert diag.kd_l == pytest.approx(0.1)


def test_no_correction_arm_never_damages_anything():
    for option, goal, fx, fy in ((0, 0, 2, 0), (1, 0, W - 1, 1)):
        rec = _rec(option=option, goal_lane=goal, final_x=fx, final_y=fy)
        q = _q_with_h_margin(goal_lane=goal, hazard=0, margin=0.5)
        before = q.deep_hash()
        diag = apply_diagnostic(q, rec, condition="traditional", alpha_diag=0.1)
        assert diag.kd_h == 0.0
        assert diag.kd_l == 0.0
        assert q.deep_hash() == before


def test_successful_episode_produces_no_diagnostic():
    from rflnext.env import SUCCESS

    rec = _rec(option=0, goal_lane=0, final_x=W - 1, final_y=0, terminal=SUCCESS)
    assert rec.labels is None
    q = QTables(n_actions=4)
    assert apply_diagnostic(q, rec, condition="hl", alpha_diag=0.1) is None


BETA_CFG = {
    "environment": {"horizon": 8, "gamma": 1.0, "p_hazard": 0.25},
    "learning": {
        "alpha_low": 0.10, "alpha_high": 0.10, "alpha_diag": 0.10,
        "epsilon_start": 0.30, "epsilon_end": 0.05, "epsilon_decay_fraction": 0.80,
    },
    "experiment": {"episodes": 300, "eval_every": 150, "eval_episodes": 40},
}


def test_train_beta_produces_diagnostics_and_is_reproducible():
    a = train_beta(BETA_CFG, seed=11, condition="traditional_oracle")
    b = train_beta(BETA_CFG, seed=11, condition="traditional_oracle")
    assert a.q_hash == b.q_hash
    assert a.success_curve == b.success_curve
    assert len(a.diagnostics) == sum(a.family_counts.values())
    assert set(a.family_counts) == set(INNOCENT)


def test_blunt_rule_touches_both_modules_oracle_does_not():
    oracle = train_beta(BETA_CFG, seed=12, condition="traditional_oracle")
    blunt = train_beta(BETA_CFG, seed=12, condition="hl")
    o_l = [d for d in oracle.diagnostics if d.family == "L_error"]
    b_l = [d for d in blunt.diagnostics if d.family == "L_error"]
    assert o_l and b_l
    # In L_error the H module is innocent: Oracle must leave it alone, hl must not.
    assert all(d.corrected_h is False for d in o_l)
    assert all(d.corrected_h is True for d in b_l)
