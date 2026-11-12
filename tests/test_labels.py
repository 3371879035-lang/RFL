import pytest

from rflnext.env import BLOCKED, SUCCESS, TIMEOUT, W
from rflnext.labels import FAMILIES, causal_labels, family_of


def test_success_emits_no_diagnosis():
    assert causal_labels(
        option=0, goal_lane=0, final_x=W - 1, final_y=0, hazard=0, terminal=SUCCESS
    ) is None


def test_h_error():
    lab = causal_labels(
        option=1, goal_lane=0, final_x=W - 1, final_y=1, hazard=0, terminal=TIMEOUT
    )
    assert lab.family == "H_error"
    assert (lab.u_h, lab.u_l) == (1, 0)
    assert (lab.p_h, lab.p_l, lab.p_e) == (1.0, 0.0, 0.0)


def test_l_error():
    lab = causal_labels(
        option=0, goal_lane=0, final_x=2, final_y=0, hazard=0, terminal=TIMEOUT
    )
    assert lab.family == "L_error"
    assert (lab.u_h, lab.u_l) == (0, 1)


def test_hl_error():
    lab = causal_labels(
        option=1, goal_lane=0, final_x=2, final_y=1, hazard=0, terminal=TIMEOUT
    )
    assert lab.family == "HL_error"
    assert (lab.u_h, lab.u_l) == (1, 1)


def test_right_option_but_wrong_lane_is_an_l_error():
    """Regression: reaching column 4 on the wrong lane is an execution error,
    not a plan error.  The old `final_x == 4` rule scored this (True, True) and
    tripped the unreachable-state assertion."""
    lab = causal_labels(
        option=0, goal_lane=0, final_x=W - 1, final_y=1, hazard=0, terminal=TIMEOUT
    )
    assert lab.family == "L_error"
    assert (lab.h_correct, lab.l_correct) == (True, False)
    assert (lab.u_h, lab.u_l) == (0, 1)


def test_e_failure_blames_neither_module():
    lab = causal_labels(
        option=0, goal_lane=0, final_x=W - 1, final_y=0, hazard=1, terminal=BLOCKED
    )
    assert lab.family == "E_failure"
    assert (lab.u_h, lab.u_l) == (0, 0)
    assert lab.p_e == 1.0


def test_e_failure_dominates_even_when_modules_also_erred():
    lab = causal_labels(
        option=1, goal_lane=0, final_x=1, final_y=1, hazard=1, terminal=BLOCKED
    )
    assert lab.family == "E_failure"
    assert (lab.u_h, lab.u_l) == (0, 0)


def test_p_is_multilabel_and_not_normalized():
    lab = causal_labels(
        option=1, goal_lane=0, final_x=2, final_y=1, hazard=0, terminal=TIMEOUT
    )
    assert lab.p_h + lab.p_l + lab.p_e == pytest.approx(2.0)


def test_all_families_covered():
    assert set(FAMILIES) == {"H_error", "L_error", "HL_error", "E_failure"}


def test_family_of_inverts():
    assert family_of(1, 0, 0) == "H_error"
    assert family_of(0, 1, 0) == "L_error"
    assert family_of(1, 1, 0) == "HL_error"
    assert family_of(0, 0, 1) == "E_failure"
