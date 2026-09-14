"""Tests for the requirements completed in the final pass."""

import numpy as np
import pytest

from rflnext.env import SUCCESS, TIMEOUT
from rflnext.noise import NoiseTape
from rflnext.qtables import QTables
from rflnext.runner import run_episode
from rflnext.stats_ext import (
    holm_correct,
    probability_of_improvement,
    summary_contrast,
    wilcoxon_signed_rank,
)


def _tape(seed=0, episodes=2, horizon=8, p_hazard=0.25):
    return NoiseTape.from_seed(seed, episodes=episodes, horizon=horizon,
                               p_hazard=p_hazard)


# ---------------------------------------------------------------- absorbing


def test_absorbing_runs_to_the_horizon_but_returns_the_same():
    """The plan's A/B fairness rule, implemented literally.  With gamma=1 and
    no step reward the return must be identical either way -- asserted, not
    assumed, because the whole A/B comparison rests on it."""
    tape = _tape(seed=4, episodes=4, p_hazard=0.0)
    for ep in range(4):
        q_a, q_b = QTables(n_actions=4), QTables(n_actions=4)
        a = run_episode(episode=ep, tape=tape, q=q_a, epsilon=0.0, reward_mode="A",
                        alpha_low=0.0, alpha_high=0.0, absorb=False)
        b = run_episode(episode=ep, tape=tape, q=q_b, epsilon=0.0, reward_mode="A",
                        alpha_low=0.0, alpha_high=0.0, absorb=True)
        assert a.return_value == b.return_value
        assert a.terminal == b.terminal
        assert b.steps == tape.horizon if b.terminal != SUCCESS else b.steps <= tape.horizon


def test_absorbing_does_not_add_decisions():
    tape = _tape(seed=6, episodes=1, p_hazard=0.0)
    rec = run_episode(episode=0, tape=tape, q=QTables(n_actions=4), epsilon=0.0,
                      reward_mode="A", alpha_low=0.0, alpha_high=0.0, absorb=True)
    ts = [s[3] for s, _ in rec.visited_low]
    assert ts == list(range(1, len(ts) + 1))  # contiguous, no absorbing rows


def test_absorbing_does_not_change_learning():
    tape = _tape(seed=7, episodes=8, p_hazard=0.25)
    qa, qb = QTables(n_actions=4), QTables(n_actions=4)
    for ep in range(8):
        run_episode(episode=ep, tape=tape, q=qa, epsilon=0.3, reward_mode="A",
                    alpha_low=0.1, alpha_high=0.1, absorb=False)
        run_episode(episode=ep, tape=tape, q=qb, epsilon=0.3, reward_mode="A",
                    alpha_low=0.1, alpha_high=0.1, absorb=True)
    assert qa.deep_hash() == qb.deep_hash()


# ------------------------------------------------------- naive vs replay


def test_naive_revision_cells_exist_and_are_labelled():
    from rflnext.timing import CELLS, NAIVE_REVISION, REVISABLE

    assert NAIVE_REVISION <= set(CELLS)
    assert NAIVE_REVISION <= REVISABLE
    assert "immediate_revisable_naive" in CELLS


def test_naive_patch_diverges_from_a_true_replay():
    """The plan's warning, made measurable: subtracting dQ_old leaves later
    bootstrap targets untouched, so it lands somewhere the replay does not."""
    from rflnext.timing import run_cell

    cfg = {
        "environment": {"horizon": 8, "gamma": 1.0},
        "learning": {"alpha_high": 0.10, "alpha_diag": 0.10},
        "protocol": {"warmup_episodes": 60, "lucky_episodes": 40,
                     "contradiction_episodes": 12, "unlucky_every": 4,
                     "checkpoint_every": 10},
    }
    replay = run_cell(cfg, seed=2, cell="immediate_revisable")
    naive = run_cell(cfg, seed=2, cell="immediate_revisable_naive")
    assert replay.revisions > 0 and naive.revisions > 0
    assert naive.correct_credit_after_contradiction != replay.correct_credit_after_contradiction
    assert {r.mode for r in naive.revision_records} == {"naive_patch"}
    assert {r.mode for r in replay.revision_records} == {"replay"}


def test_revision_ledger_records_old_and_new_interpretation():
    from rflnext.timing import run_cell

    cfg = {
        "environment": {"horizon": 8, "gamma": 1.0},
        "learning": {"alpha_high": 0.10, "alpha_diag": 0.10},
        "protocol": {"warmup_episodes": 40, "lucky_episodes": 30,
                     "contradiction_episodes": 8, "unlucky_every": 4,
                     "checkpoint_every": 10},
    }
    res = run_cell(cfg, seed=1, cell="immediate_revisable")
    assert res.revision_records
    rec = res.revision_records[0]
    assert (rec.old_u_h, rec.new_u_h) == (0, 1)
    assert rec.trigger_type in ("contradiction", "unlucky_failure")
    assert rec.target_episodes


# ------------------------------------------------------------- statistics


def test_wilcoxon_is_defined_for_a_real_difference():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.zeros(5)
    p = wilcoxon_signed_rank(x, y)
    assert p is not None and 0.0 <= p <= 1.0


def test_wilcoxon_is_none_when_there_is_no_difference():
    assert wilcoxon_signed_rank(np.ones(5), np.ones(5)) is None


def test_probability_of_improvement_bounds():
    rng = np.random.RandomState(0)
    assert probability_of_improvement(np.ones(20), np.zeros(20), n_boot=200, rng=rng) == 1.0
    assert probability_of_improvement(np.zeros(20), np.ones(20), n_boot=200, rng=rng) == 0.0
    assert probability_of_improvement(
        np.zeros(20), np.zeros(20), n_boot=200, rng=rng
    ) == 0.0


def test_summary_contrast_reports_everything_the_plan_asks_for():
    rng = np.random.RandomState(0)
    x = np.array([0.5, 0.6, 0.7, 0.8, 0.9])
    y = np.array([0.1, 0.2, 0.3, 0.2, 0.1])
    out = summary_contrast(x, y, n_perm=500, n_boot=500, rng=rng)
    for key in ("mean", "median", "ci", "cohens_dz", "p_sign_flip",
                "p_wilcoxon", "probability_of_improvement"):
        assert key in out
    assert out["probability_of_improvement"] == 1.0


def test_holm_correction_is_monotone_and_capped():
    adj = holm_correct([0.001, 0.02, 0.5])
    assert all(0.0 <= a <= 1.0 for a in adj)
    assert adj[0] <= adj[1] <= adj[2]


# ------------------------------------------------------------ architectures


def test_architecture_arms_are_declared():
    from rflnext.stage4 import ALWAYS_BOTH, ARMS

    assert {"aux_penalty_rfl", "global_value_rfl"} <= set(ARMS)
    assert ALWAYS_BOTH == {"aux_penalty_rfl"}


def test_aux_penalty_corrects_both_modules():
    from rflnext.gamma import SequenceModel, generate_balanced
    from rflnext.stage4 import _choose_module
    from tests.test_stage4 import _rec

    model = SequenceModel().fit(generate_balanced(400, seed=11, horizon=8)[:200])
    rec = _rec(option=0, goal_lane=0, final_x=2, final_y=0)
    assert _choose_module("aux_penalty_rfl", rec, model, "")[0] == "BOTH"


def test_option_bonus_shifts_the_high_level_choice():
    tape = _tape(seed=3, episodes=1, p_hazard=0.0)
    gl = int(tape.goal_lane[0])
    q = QTables(n_actions=4)
    plain = run_episode(episode=0, tape=tape, q=q, epsilon=0.0, reward_mode="A",
                        alpha_low=0.0, alpha_high=0.0)
    bonus = {0: 0.0, 1: 0.0}
    bonus[1 - plain.option] = 5.0
    shifted = run_episode(episode=0, tape=tape, q=q, epsilon=0.0, reward_mode="A",
                          alpha_low=0.0, alpha_high=0.0, option_bonus=bonus)
    assert shifted.option == 1 - plain.option
