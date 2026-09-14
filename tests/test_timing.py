import pytest

from rflnext.env import BLOCKED, SUCCESS, TIMEOUT, W
from rflnext.timing import CELLS, IMMEDIATE, REVISABLE, _rollout, run_cell

CFG = {
    "environment": {"horizon": 8, "gamma": 1.0},
    "learning": {"alpha_high": 0.10, "alpha_diag": 0.10},
    "protocol": {
        "warmup_episodes": 60,
        "lucky_episodes": 40,
        "contradiction_episodes": 12,
        "unlucky_every": 4,
        "checkpoint_every": 10,
    },
}


def test_cells_table_is_the_full_2x2():
    assert set(CELLS) == {
        "immediate_fixed", "immediate_revisable",
        "deferred_fixed", "deferred_revisable",
    }
    assert IMMEDIATE | {"deferred_fixed", "deferred_revisable"} == set(CELLS)
    assert len(REVISABLE) == 2


def test_lucky_shortcut_lets_a_wrong_plan_succeed():
    # wrong option, lucky -> SUCCESS; wrong option, no luck -> failure.
    assert _rollout(goal_lane=0, hazard=0, lucky=1, option=1, horizon=8) == SUCCESS
    assert _rollout(goal_lane=0, hazard=0, lucky=0, option=1, horizon=8) == TIMEOUT


def test_unlucky_failure_blocks_a_correct_plan():
    assert _rollout(goal_lane=0, hazard=1, lucky=0, option=0, horizon=8) == BLOCKED


def test_terminal_kind_defaults_keep_old_behaviour():
    from rflnext.env import terminal_kind

    assert terminal_kind(4, 1, goal_lane=1, hazard=0) == SUCCESS
    assert terminal_kind(4, 1, goal_lane=1, hazard=1) == BLOCKED
    assert terminal_kind(4, 0, goal_lane=1, hazard=0) is None


def test_lucky_successes_do_inflate_overcredit_under_fixed_credit():
    res = run_cell(CFG, seed=1, cell="immediate_fixed")
    # The wrong plan earned +1 many times, so it is credited.
    assert res.overcredit_after_lucky > 0.5


def test_revisable_credit_does_not_reduce_residual_overcredit():
    """The task RL drives the wrong plan's value down on its own, faster than
    the revision can help, so fixed and revisable agree on overcredit."""
    fixed = run_cell(CFG, seed=2, cell="immediate_fixed")
    rev = run_cell(CFG, seed=2, cell="immediate_revisable")
    assert rev.revisions > 0
    assert rev.overcredit_after_contradiction == pytest.approx(
        fixed.overcredit_after_contradiction
    )


def test_revisable_credit_destroys_credit_that_was_genuinely_earned():
    """The blind contradiction rule withdraws evidence from every earlier
    success of the same plan -- including the ones that were correct -- so the
    right plan loses the credit it deserved."""
    fixed = run_cell(CFG, seed=2, cell="immediate_fixed")
    rev = run_cell(CFG, seed=2, cell="immediate_revisable")
    assert rev.correct_credit_after_contradiction < fixed.correct_credit_after_contradiction
    assert rev.false_reversals > rev.true_revisions
    assert rev.revision_precision is not None and rev.revision_precision < 0.5


def test_deferred_cell_diagnoses_less_eagerly_than_immediate():
    imm = run_cell(CFG, seed=3, cell="immediate_fixed")
    dfr = run_cell(CFG, seed=3, cell="deferred_fixed")
    assert dfr.n_diagnosis <= imm.n_diagnosis


def test_unlucky_failures_produce_false_reversals_in_revisable_cells():
    res = run_cell(CFG, seed=4, cell="immediate_revisable")
    assert res.false_reversals > 0
    assert res.revision_precision is not None
    assert 0.0 < res.revision_precision < 1.0


def test_fixed_cells_never_revise():
    for cell in ("immediate_fixed", "deferred_fixed"):
        res = run_cell(CFG, seed=5, cell=cell)
        assert res.revisions == 0
        assert res.revision_precision is None


def test_run_is_deterministic():
    a = run_cell(CFG, seed=6, cell="immediate_revisable")
    b = run_cell(CFG, seed=6, cell="immediate_revisable")
    assert (a.overcredit_after_contradiction, a.revisions, a.false_reversals) == (
        b.overcredit_after_contradiction, b.revisions, b.false_reversals
    )


def test_recovery_is_recorded_for_every_cell():
    for cell in CELLS:
        res = run_cell(CFG, seed=7, cell=cell)
        assert res.recovery_episodes is None or res.recovery_episodes >= 1
