"""Stage 4: end-to-end Q-learning with learned attribution in the loop.

Arms, per the research plan:

  traditional      standard RL, no diagnostic correction
  positive_only    failure reward 0, no diagnostic correction
  direct_feedback  trusts the emitted diagnostic label and corrects that module
  sequence_rfl     corrects the module a pretrained sequence model ranks first
  learned_rfl      sequence prior + 1 counterfactual query (Core-RFL)
  oracle_rfl       corrects the module the SCM says was responsible (upper bound)

The environment emits a *diagnostic label* that is wrong with probability
``p_false``.  That is the whole point of the RFL setting: the outcome reward is
never falsified, only the explanation attached to it.  ``direct_feedback``
forwards that label into the update; RFL verifies it first.

Stated simplification
---------------------
The attribution module is pretrained offline on a generated trace corpus and
then frozen; online it is applied to the agent's own episodes.  Learning the
attributor *online without labels* is not attempted here -- a learner has no
access to the SCM truth to supervise itself with.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .env import HORIZON, N_ACTIONS, SUCCESS
from .gamma import SequenceModel, attribute_seq_then_cf, observable_features
from .metrics import final_success, success_auc
from .noise import NoiseTape
from .qtables import QTables, linear_epsilon
from .runner import EpisodeRecord, evaluate, run_episode

ARMS = (
    "traditional",
    "positive_only",
    "direct_feedback",
    "sequence_rfl",
    "learned_rfl",
    "oracle_rfl",
)
NO_CORRECTION = {"traditional", "positive_only"}
FEEDBACK_SEED_OFFSET = 700_000_000


@dataclass(frozen=True)
class OnlineTrace:
    """The subset of a trace an attributor is allowed to see online."""

    option: int
    final_x: int
    final_y: int
    terminal: str
    goal_lane: int
    hazard: int


@dataclass
class Stage4Result:
    arm: str
    seed: int
    checkpoints: list
    success_curve: list
    family_counts: dict
    corrections: int
    collateral: int
    update_precision: float | None
    collateral_rate: float | None
    expected_knowledge_damage: float
    n_cf: int
    q_hash: str
    wall_s: float
    eval_winnable_fraction: float = 1.0


def _to_online_trace(rec: EpisodeRecord) -> OnlineTrace:
    return OnlineTrace(
        option=int(rec.option), final_x=int(rec.final_x), final_y=int(rec.final_y),
        terminal=rec.terminal, goal_lane=int(rec.goal_lane), hazard=int(rec.hazard),
    )


def _truth_primary(rec: EpisodeRecord) -> str:
    if rec.labels is None:
        return "E"
    if rec.labels.u_h:
        return "H"
    if rec.labels.u_l:
        return "L"
    return "E"


def make_feedback_stream(seed: int, episodes: int, p_false: float) -> list[str]:
    """Diagnostic labels, wrong with probability ``p_false``."""
    rng = np.random.default_rng((int(seed) + FEEDBACK_SEED_OFFSET) % (2**32 - 1))
    wrong = rng.random(size=episodes) < float(p_false)
    pick = rng.integers(0, 3, size=episodes)
    return [("H", "L", "E")[int(k)] if w else "" for w, k in zip(wrong, pick)]


def _choose_module(
    arm: str,
    rec: EpisodeRecord,
    model: SequenceModel,
    feedback: str,
) -> tuple[str | None, int]:
    """Return (module to correct, counterfactual queries spent)."""
    if arm in NO_CORRECTION:
        return None, 0
    if arm == "oracle_rfl":
        t = _truth_primary(rec)
        return (None if t == "E" else t), 0
    if arm == "direct_feedback":
        return (None if feedback == "E" else feedback), 0

    ot = _to_online_trace(rec)
    if arm == "sequence_rfl":
        score = model.score(ot)  # type: ignore[arg-type]
        best = max(("H", "L", "E"), key=lambda c: score.get(c, 0.0))
        return (None if best == "E" else best), 0
    if arm == "learned_rfl":
        att = attribute_seq_then_cf(ot, model, 1)  # type: ignore[arg-type]
        best = max(("H", "L", "E"), key=lambda c: att.score.get(c, 0.0))
        return (None if best == "E" else best), att.cf_queries
    raise ValueError(arm)


def train_arm(
    cfg: dict, *, seed: int, arm: str, model: SequenceModel
) -> Stage4Result:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    t0 = time.perf_counter()
    env_cfg = cfg["environment"]
    learn = cfg["learning"]
    exp = cfg["experiment"]

    episodes = int(exp["episodes"])
    eval_every = int(exp["eval_every"])
    eval_episodes = int(exp["eval_episodes"])
    horizon = int(env_cfg.get("horizon", HORIZON))
    p_hazard = float(env_cfg.get("p_hazard", 0.25))
    alpha_diag = float(learn.get("alpha_diag", 0.0))
    decay = max(1, int(episodes * float(learn["epsilon_decay_fraction"])))

    tape = NoiseTape.from_seed(seed, episodes=episodes, horizon=horizon, p_hazard=p_hazard)
    feedback = make_feedback_stream(seed, episodes, float(exp.get("p_false", 0.40)))
    q = QTables(n_actions=N_ACTIONS)
    reward_mode = "B" if arm == "positive_only" else "A"

    checkpoints: list = []
    curve: list = []
    winnable: list = []
    family_counts: dict = {}
    corrections = collateral = n_cf = 0

    def record(index: int) -> None:
        rate, _states, win = evaluate(q, cfg, seed=seed, n=eval_episodes)
        checkpoints.append(int(index))
        curve.append(float(rate))
        winnable.append(float(win))

    record(0)
    for ep in range(episodes):
        eps = linear_epsilon(
            ep, start=float(learn["epsilon_start"]), end=float(learn["epsilon_end"]),
            decay_episodes=decay,
        )
        rec = run_episode(
            episode=ep, tape=tape, q=q, epsilon=eps, reward_mode=reward_mode,
            alpha_low=float(learn["alpha_low"]), alpha_high=float(learn["alpha_high"]),
        )

        if rec.labels is not None:
            family_counts[rec.labels.family] = family_counts.get(rec.labels.family, 0) + 1
            module, spent = _choose_module(arm, rec, model, feedback[ep])
            n_cf += spent
            if module is not None and alpha_diag > 0.0:
                truth = rec.labels.u_h if module == "H" else rec.labels.u_l
                corrections += 1
                if not truth:
                    collateral += 1
                if module == "H":
                    s_h = (rec.goal_lane, rec.hazard)
                    cur = q.high_get(s_h, rec.option)
                    q.high_update(s_h, rec.option, cur - alpha_diag, 1.0)
                else:
                    if rec.visited_low:
                        site, action = rec.visited_low[-1]
                        cur = q.low_get(site, action)
                        q.low_update(site, action, cur - alpha_diag, 1.0)

        if (ep + 1) % eval_every == 0:
            record(ep + 1)

    return Stage4Result(
        arm=arm,
        seed=int(seed),
        checkpoints=checkpoints,
        success_curve=curve,
        family_counts=family_counts,
        corrections=corrections,
        collateral=collateral,
        update_precision=(1.0 - collateral / corrections) if corrections else None,
        collateral_rate=(collateral / corrections) if corrections else None,
        expected_knowledge_damage=alpha_diag * (collateral / corrections if corrections else 0.0),
        n_cf=n_cf,
        q_hash=q.deep_hash(),
        wall_s=time.perf_counter() - t0,
        eval_winnable_fraction=(sum(winnable) / len(winnable)) if winnable else 1.0,
    )
