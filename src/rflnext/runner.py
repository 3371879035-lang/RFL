"""One episode of the two-level causal grid, plus online learning.

Gamma is 1.0 and step reward is 0, so an episode's return equals its terminal
reward, and a failure occurring early cannot be discounted differently from a
late one.  This is what makes the A/B reward comparison causally clean.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .env import (
    HORIZON,
    N_ACTIONS,
    SUCCESS,
    TIMEOUT,
    W,
    step_cell,
    terminal_kind,
)
from .labels import FAMILIES, CausalLabels, causal_labels
from .metrics import episodes_to_90, final_success, success_auc
from .noise import NoiseTape
from .qtables import QTables, linear_epsilon

REWARD_SUCCESS = 1.0
REWARD_FAILURE_A = -1.0
REWARD_FAILURE_B = 0.0
EVAL_SEED_OFFSET = 900_000_000


@dataclass
class EpisodeRecord:
    episode: int
    terminal: str
    steps: int
    return_value: float
    option: int
    goal_lane: int
    hazard: int
    final_x: int
    final_y: int
    labels: CausalLabels | None
    n_negative_td: int = 0
    visited_low: list = field(default_factory=list)
    visited_high: list = field(default_factory=list)


def _failure_reward(mode: str) -> float:
    if mode == "A":
        return REWARD_FAILURE_A
    if mode == "B":
        return REWARD_FAILURE_B
    raise ValueError(f"unknown reward mode {mode!r}")


def _argmax_with_tie(values: list, tie: float) -> int:
    """Argmax, with ties broken deterministically from the tape.

    Breaking ties by lowest index instead would make the all-zero start state
    always pick UP, which is a no-op at (0, 0) and stalls exploration.
    """
    best = max(values)
    candidates = [i for i, v in enumerate(values) if v == best]
    if len(candidates) == 1:
        return candidates[0]
    return candidates[int(tie * len(candidates) * 1000) % len(candidates)]


def _epsilon_greedy(values: list, epsilon: float, explore: float, tie: float) -> int:
    n = len(values)
    if explore < epsilon:
        return int(explore * n * 1000) % n
    return _argmax_with_tie(values, tie)


def run_episode(
    *,
    episode: int,
    tape: NoiseTape,
    q: QTables,
    epsilon: float,
    reward_mode: str,
    alpha_low: float,
    alpha_high: float,
) -> EpisodeRecord:
    """Roll out one episode and apply the online updates in place."""
    goal_lane = int(tape.goal_lane[episode])
    hazard = int(tape.hazard[episode])
    s_h = (goal_lane, hazard)

    explore = tape.explore_u[episode]
    tie = tape.tie_u[episode]
    option = _epsilon_greedy(
        [q.high_get(s_h, o) for o in q.options], epsilon, explore[0], tie[0]
    )

    x, y = 0, 0
    visited_low: list = []
    visited_high: list = [s_h]
    n_negative_td = 0
    terminal = TIMEOUT
    steps = 0
    fail_reward = _failure_reward(reward_mode)
    # Take the horizon from the tape, not from the module constant, so a
    # configured horizon other than the default cannot index past the tape.
    span = int(getattr(tape, "horizon", HORIZON))

    for t in range(1, span + 1):
        # The timestep is part of the low-level state.  With gamma=1 and no
        # step reward, a state without t admits a self-loop action whose TD
        # target is `0 + max_a Q(s,a)` -- its own state value -- so the
        # Bellman equation is satisfied for *any* value and stalling becomes
        # co-optimal with progressing.  Including t makes every transition
        # either terminate or advance t, so the fixed point is unique.
        s_l = (x, y, option, t)
        a = _epsilon_greedy(
            [q.low_get(s_l, k) for k in range(N_ACTIONS)], epsilon, explore[t], tie[t]
        )
        visited_low.append((s_l, a))
        nx, ny = step_cell(x, y, a)
        kind = terminal_kind(nx, ny, goal_lane, hazard)
        steps = t

        if kind == SUCCESS:
            reward, terminal, done = REWARD_SUCCESS, SUCCESS, True
        elif kind is not None:
            reward, terminal, done = fail_reward, kind, True
        elif t == span:
            # Horizon expiry is a failure with exactly the failure reward:
            # no extra hidden timeout value.
            reward, terminal, done = fail_reward, TIMEOUT, True
        else:
            reward, done = 0.0, False

        if done:
            target = reward
        else:
            nxt = (nx, ny, option, t + 1)
            nrow = q.low.get(nxt)
            target = reward + (max(nrow) if nrow else 0.0)
        before = q.low_get(s_l, a)
        delta = alpha_low * (target - before)
        if delta < 0.0:
            n_negative_td += 1
        # Guarded: q.low_update() would otherwise create an all-zero row via
        # setdefault, mutating the table even in read-only evaluation.
        if alpha_low > 0.0:
            q.low_update(s_l, a, target, alpha_low)

        x, y = nx, ny
        if done:
            break

    return_value = REWARD_SUCCESS if terminal == SUCCESS else fail_reward

    if alpha_high > 0.0:
        q.high_update(s_h, option, return_value, alpha_high)

    labels = causal_labels(
        option=option, goal_lane=goal_lane, final_x=x, final_y=y,
        hazard=hazard, terminal=terminal,
    )

    return EpisodeRecord(
        episode=episode,
        terminal=terminal,
        steps=steps,
        return_value=return_value,
        option=option,
        goal_lane=goal_lane,
        hazard=hazard,
        final_x=x,
        final_y=y,
        labels=labels,
        n_negative_td=n_negative_td,
        visited_low=visited_low,
        visited_high=visited_high,
    )


@dataclass
class TrainResult:
    seed: int
    arm: str
    checkpoints: list
    success_curve: list
    family_counts: dict
    n_negative_td_total: int
    q_hash: str
    eval_winnable_fraction: float = 1.0
    records: list = field(default_factory=list)


def evaluate(q: QTables, cfg: dict, *, seed: int, n: int) -> tuple[float, list, float]:
    """Greedy evaluation on a fresh tape.  Never mutates ``q``.

    Returns ``(success_rate, visited_states, winnable_fraction)``.  The third
    value is the realized share of episodes the hazard did *not* make
    unwinnable; it is the only honest ceiling for this eval sample, since a
    finite tape's hazard count is not exactly ``p_hazard``.
    """
    env_cfg = cfg["environment"]
    horizon = int(env_cfg.get("horizon", HORIZON))
    n = int(n)
    tape = NoiseTape.from_seed(
        int(seed) + EVAL_SEED_OFFSET, episodes=n, horizon=horizon,
        p_hazard=float(env_cfg.get("p_hazard", 0.25)),
    )
    wins = 0
    states: list = []
    for ep in range(n):
        rec = run_episode(
            episode=ep, tape=tape, q=q, epsilon=0.0, reward_mode="A",
            alpha_low=0.0, alpha_high=0.0,
        )
        wins += int(rec.terminal == SUCCESS)
        states.extend(state for state, _ in rec.visited_low)
    winnable = 1.0 - (sum(tape.hazard[:n]) / float(n))
    return wins / float(n), states, winnable


def train(cfg: dict, *, seed: int, arm: str) -> TrainResult:
    """Run one arm of Pilot Alpha for one seed."""
    if arm not in ("traditional", "positive_only"):
        raise ValueError(f"unknown arm {arm!r}")
    env_cfg = cfg["environment"]
    learn = cfg["learning"]
    exp = cfg["experiment"]

    episodes = int(exp["episodes"])
    eval_every = int(exp["eval_every"])
    eval_episodes = int(exp["eval_episodes"])
    horizon = int(env_cfg.get("horizon", HORIZON))
    decay_episodes = max(1, int(episodes * float(learn["epsilon_decay_fraction"])))

    tape = NoiseTape.from_seed(
        int(seed), episodes=episodes, horizon=horizon,
        p_hazard=float(env_cfg.get("p_hazard", 0.25)),
    )
    q = QTables(n_actions=N_ACTIONS)
    reward_mode = "A" if arm == "traditional" else "B"

    checkpoints: list = []
    success_curve: list = []
    family_counts: dict = {f: 0 for f in FAMILIES}
    records: list = []
    winnable_fractions: list = []

    def record_checkpoint(episode_index: int) -> None:
        rate, _states, winnable = evaluate(q, cfg, seed=seed, n=eval_episodes)
        checkpoints.append(int(episode_index))
        success_curve.append(float(rate))
        winnable_fractions.append(float(winnable))

    record_checkpoint(0)
    for ep in range(episodes):
        eps = linear_epsilon(
            ep,
            start=float(learn["epsilon_start"]),
            end=float(learn["epsilon_end"]),
            decay_episodes=decay_episodes,
        )
        rec = run_episode(
            episode=ep, tape=tape, q=q, epsilon=eps, reward_mode=reward_mode,
            alpha_low=float(learn["alpha_low"]), alpha_high=float(learn["alpha_high"]),
        )
        records.append(rec)
        if rec.labels is not None:
            family_counts[rec.labels.family] += 1
        if (ep + 1) % eval_every == 0:
            record_checkpoint(ep + 1)

    return TrainResult(
        seed=int(seed),
        arm=arm,
        checkpoints=checkpoints,
        success_curve=success_curve,
        family_counts=family_counts,
        n_negative_td_total=int(sum(r.n_negative_td for r in records)),
        q_hash=q.deep_hash(),
        eval_winnable_fraction=(
            sum(winnable_fractions) / len(winnable_fractions) if winnable_fractions else 1.0
        ),
        records=records,
    )
