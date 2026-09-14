from rflnext.env import (
    BLOCKED, DOWN, HORIZON, N_ACTIONS, RIGHT, SUCCESS, TIMEOUT, UP, WAIT, W,
    step_cell, terminal_kind,
)


def test_action_count_and_width():
    assert N_ACTIONS == 4
    assert W == 5
    assert HORIZON == 8


def test_step_cell_moves():
    assert step_cell(0, 1, UP) == (0, 0)
    assert step_cell(0, 0, DOWN) == (0, 1)
    assert step_cell(0, 0, RIGHT) == (1, 0)
    assert step_cell(0, 0, WAIT) == (0, 0)


def test_right_saturates_at_end():
    assert step_cell(4, 1, RIGHT) == (4, 1)


def test_terminal_success_and_blocked():
    assert terminal_kind(4, 1, goal_lane=1, hazard=0) == SUCCESS
    assert terminal_kind(4, 1, goal_lane=1, hazard=1) == BLOCKED


def test_terminal_none_off_exit():
    assert terminal_kind(3, 1, goal_lane=1, hazard=0) is None
    assert terminal_kind(4, 0, goal_lane=1, hazard=0) is None


def test_timeout_is_not_produced_by_terminal_kind():
    assert TIMEOUT != SUCCESS
