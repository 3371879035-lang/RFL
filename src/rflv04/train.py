"""v0.4 training loop.

Protocol
--------
1. **Warmup on clean scenes.**  The agent learns the task with no injected
   faults.  The resulting Q snapshot is the *checkpoint*, and the Knowledge Set
   is read off it.  Damage is always measured against this checkpoint, so the
   denominator is established knowledge rather than whatever the agent happens
   to hold after a shock.
2. **Main run on fault scenes.**  Failures are diagnosed by the oracle and the
   arm's credit representation selects which entries may be corrected.

The agent's own epsilon-greedy policy drives the rollouts; injected faults
override the action at their timestep, which is what keeps the family mix under
experimental control while the policy still learns.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from rflnext.qtables import QTables, linear_epsilon

from .credit_units import REPRESENTATIONS, responsible_units, selected_repair
from .env import (
    ABSORB,
    ACT,
    ACT_ACTIONS,
    HORIZON,
    PLAN,
    PLAN_ACTIONS,
    SUCCESS,
    TIMEOUT,
    WAIT,
    X_MAX,
    Scene,
    Step,
    Trace,
    apply_action,
    reference_action,
)
from .knowledge import build_knowledge_set, kd_innocent, wmd
from .oracle import classify, oracle_repair_set, scene_from_trace
from .updates import MODES

ARMS = (
    "NoCorruption",   # clean checkpoint, no correction: the ceiling reference
    "NoCorrection",   # corrupted checkpoint, no correction: the damage reference
    "ModuleOracle",
    "DecisionOracle",
    "RepairOracle",
)

CALIBRATION_NOTE = """\
Measured state of Pilot Alpha after the fault injector was repaired:

    arms now separate on WMD and on sites touched
      ModuleOracle     WMD 0.0506, 4409 sites
      DecisionOracle   WMD 0.0535,  839 sites
      RepairOracle     WMD 0.0535,  839 sites
    but every arm still reaches SuccessAUC 1.0000

    => CEILING_RISK.  Ordinary Q-learning repairs the six corrupted states
    inside the 250-episode evaluation interval, so there is no persistent
    damage for a diagnostic update to add value on.

This is the v0.3 Stage 5 finding reproduced one layer down: the environment
self-repairs faster than update semantics can matter.  Making Alpha
discriminative therefore needs damage that PERSISTS, not a better arm:
corrupt many more states, corrupt states the greedy policy rarely revisits, or
evaluate recovery at a far finer interval than 250 episodes.

Until the baseline shows a non-saturating recovery curve, Alpha numbers are not
interpretable and must not be reported as a result.
"""

# Balanced diagnostic distribution (plan §"Balanced 与 Naturalistic 分布").
BALANCED = {"whole": 0.25, "plan_only": 0.25, "decision_only": 0.25,
            "execution_only": 0.25}


@dataclass
class TrainResult:
    arm: str
    seed: int
    checkpoints: list = field(default_factory=list)
    success_curve: list = field(default_factory=list)
    family_counts: dict = field(default_factory=dict)
    wmd: float = 0.0
    kd_innocent: float = 0.0
    collateral: float = 0.0
    corrections: int = 0
    sites_touched: int = 0
    clippings: int = 0
    wall_s: float = 0.0
    q_hash: str = ""


def _sample_kind(rng, dist: dict) -> str:
    keys = list(dist)
    p = np.array([dist[k] for k in keys], dtype=float)
    p = p / p.sum()
    return str(rng.choice(keys, p=p))


def _masked_epsilon_greedy(values: dict, valid: tuple, epsilon: float, u: float) -> int:
    cand = [a for a in valid if a in values]
    if not cand:
        return valid[0]
    if u < epsilon:
        return int(cand[int(u * len(cand) * 1000) % len(cand)])
    best = max(values[a] for a in cand)
    top = [a for a in cand if values[a] == best]
    return int(top[int(u * len(top) * 1000) % len(top)])


def agent_rollout(q, scene: Scene, *, epsilon: float, rng) -> Trace:
    """Roll out under the agent's policy, with injected faults overriding."""
    g = scene.g
    o = scene.plan
    x, y = 0, 0
    trace = Trace(scene=scene)
    terminal = TIMEOUT
    absorbing = False

    for t in range(0, scene.horizon + 1):
        u = float(rng.random())
        if t == 0:
            vals = {a: q.high_get((g, 0, 0), a) for a in PLAN_ACTIONS}
            o = _masked_epsilon_greedy(vals, PLAN_ACTIONS, epsilon, u)
            trace.steps.append(Step(0, (g, x, y, -1, PLAN), PLAN_ACTIONS[0] + o,
                                    PLAN_ACTIONS[0] + o, (g, x, y, o, ACT)))
            continue
        if absorbing:
            # Absorbing placeholders must NOT be tagged ACT: doing so made them
            # look like decisions, so the task update wrote Q for action -1
            # (which indexes the last action) and picked an absorbing step as
            # the terminal one.
            trace.steps.append(Step(t, (g, x, y, o, ABSORB), -1, -1,
                                    (g, x, y, o, ABSORB)))
            continue

        vals = {a: q.low_get((x, y, o, t), a) for a in ACT_ACTIONS}
        a = _masked_epsilon_greedy(vals, ACT_ACTIONS, epsilon, u)
        intent = realized = a
        if scene.decision_fault_at is not None and t >= scene.decision_fault_at:
            intent = realized = scene.decision_fault_action
        if scene.execution_fault_at is not None and t >= scene.execution_fault_at:
            realized = scene.execution_fault_action

        nx, ny = apply_action(x, y, o, realized)
        trace.steps.append(Step(t, (g, x, y, o, ACT), intent, realized,
                                (g, nx, ny, o, ACT)))
        x, y = nx, ny
        if x == X_MAX and y == g:
            terminal = SUCCESS
        elif t == scene.horizon:
            terminal = TIMEOUT
        if terminal != TIMEOUT or t == scene.horizon:
            absorbing = True

    trace.terminal = terminal
    trace.return_value = 1.0 if terminal == SUCCESS else -1.0
    return trace


def _task_update(q, trace: Trace, *, alpha_low: float, alpha_high: float,
                 reward_mode: str) -> None:
    r = trace.return_value if reward_mode == "A" else (
        1.0 if trace.success else 0.0)
    s0 = trace.steps[0]
    q.high_update((s0.state[0], 0, 0), s0.next_state[3], r, alpha_high)

    terms = [s for s in trace.steps if s.state[4] == ACT and s.intent >= 0]
    for i, step in enumerate(terms):
        terminal = (i == len(terms) - 1)
        state = (step.state[1], step.state[2], step.state[3], step.t)
        if terminal:
            target = r
        else:
            # Bootstrap from the NEXT timestep's low-level state.  The earlier
            # version read (g, nx, ny, o+1), which is not a state the agent can
            # ever occupy, so no value ever propagated and the agent could not
            # learn the task at all.
            nxt_key = (step.next_state[1], step.next_state[2], step.next_state[3],
                       step.t + 1)
            nrow = q.low.get(nxt_key)
            target = 0.0 + (max(nrow) if nrow else 0.0)
        q.low_update(state, step.realized, target, alpha_low)


def evaluate(q, cfg: dict, *, seed: int, n: int) -> float:
    """Greedy success rate on clean scenes (no injected faults)."""
    rng = np.random.default_rng((int(seed) + 900_000_000) % (2**32 - 1))
    horizon = int(cfg.get("environment", {}).get("horizon", HORIZON))
    wins = 0
    for i in range(int(n)):
        g = i % 2
        scene = Scene(f"E{i}", g, g, horizon=horizon)
        tr = agent_rollout(q, scene, epsilon=0.0, rng=rng)
        wins += int(tr.success)
    return wins / float(n)


def train(cfg: dict, *, seed: int, arm: str) -> TrainResult:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}")
    t0 = time.perf_counter()
    env_cfg = cfg.get("environment", {})
    learn = cfg.get("learning", {})
    exp = cfg.get("experiment", {})
    horizon = int(env_cfg.get("horizon", HORIZON))
    alpha_low = float(learn.get("alpha_low", 0.10))
    alpha_high = float(learn.get("alpha_high", 0.10))
    alpha_diag = float(learn.get("alpha_diag", 0.10))
    reward_mode = str(exp.get("reward_mode", "A"))
    warmup = int(exp.get("warmup_episodes", 300))
    episodes = int(exp.get("episodes", 2000))
    eval_every = int(exp.get("eval_every", 250))
    eval_episodes = int(exp.get("eval_episodes", 100))
    dist = dict(exp.get("distribution", BALANCED))
    decay = max(1, int((warmup + episodes) * float(learn.get("epsilon_decay_fraction", 0.8))))

    rng = np.random.default_rng((int(seed) + 4_100_000) % (2**32 - 1))
    q = QTables(n_actions=6, options=(0, 1))
    counts: dict = {}

    # ---- phase 1: warmup on clean scenes -------------------------------
    for ep in range(warmup):
        g = ep % 2
        scene = Scene(f"W{ep}", g, g, horizon=horizon)
        trace = agent_rollout(q, scene, epsilon=linear_epsilon(
            ep, start=0.30, end=0.05, decay_episodes=decay), rng=rng)
        _task_update(q, trace, alpha_low=alpha_low, alpha_high=alpha_high,
                     reward_mode=reward_mode)

    checkpoint = q.copy()
    ks = build_knowledge_set(q, theta=float(exp.get("knowledge_theta", 0.60)),
                             horizon=horizon)

    # ---- induce knowledge corruption (the thing Alpha must repair) ------
    # A decision failure has to be a bad decision BY THE AGENT.  Overriding the
    # action from outside made it exogenous: nothing to learn, and every arm
    # produced an identical curve.  Instead the checkpoint's own value estimate
    # is corrupted at a set of states, so the agent greedily chooses wrongly and
    # a diagnostic update at that site can genuinely repair it.
    corrupted: list = []
    corrupt_delta = float(exp.get("corrupt_delta", 1.0))
    n_corrupt = int(exp.get("corrupt_states", 0))
    if arm != "NoCorruption" and n_corrupt > 0:
        pool = [k for k in ks.items if k.unit == "DECISION"]
        for item in pool[:n_corrupt]:
            row = q.low.get(item.state)
            if row is None:
                continue
            bad = WAIT
            row[bad] = row[item.correct] + corrupt_delta
            corrupted.append((item.state, bad))
        q_hash_after_corruption = q.deep_hash()
    else:
        q_hash_after_corruption = q.deep_hash()

    # ---- phase 2: clean scenes; failures come from the corruption --------
    checkpoints, curve = [], []
    wmd_sum = kd_sum = 0.0
    corrections = sites_touched = clippings = collateral = 0

    def record(ep: int) -> None:
        checkpoints.append(int(ep))
        curve.append(float(evaluate(q, cfg, seed=seed, n=eval_episodes)))

    record(0)
    for ep in range(episodes):
        # Only execution faults remain exogenous; they are the plan's
        # "execution interface" case and must NOT be blamed on the decision.
        exec_fault = (ep % 4 == 3)
        g = int(rng.integers(0, 2)) if exec_fault else (ep % 2)
        if exec_fault:
            ft = int(rng.integers(1, horizon))
            scene = Scene(f"S{ep}", g, g, execution_fault_at=ft, horizon=horizon)
        else:
            scene = Scene(f"S{ep}", g, g, horizon=horizon)

        eps = linear_epsilon(warmup + ep, start=0.30, end=0.05, decay_episodes=decay)
        trace = agent_rollout(q, scene, epsilon=eps, rng=rng)
        _task_update(q, trace, alpha_low=alpha_low, alpha_high=alpha_high,
                     reward_mode=reward_mode)

        if trace.success:
            counts["clean"] = counts.get("clean", 0) + 1
            if (ep + 1) % eval_every == 0:
                record(ep + 1)
            continue

        res = oracle_repair_set(scene_from_trace(trace), n_samples=8)
        counts[res.family] = counts.get(res.family, 0) + 1
        if arm in ("NoCorrection", "NoCorruption") or not res.sufficient:
            if (ep + 1) % eval_every == 0:
                record(ep + 1)
            continue

        sel = selected_repair(trace, res)
        credit = REPRESENTATIONS[arm](trace, res) if arm != "RepairOracle" else \
            REPRESENTATIONS[arm](trace, res, sel)

        before = q.copy()
        targets = {}
        for site in credit.sites:
            targets[site.key] = -1.0 if reward_mode == "A" else 0.0
        rec = MODES["negative_only"](q, credit.sites, targets, alpha=alpha_diag)
        corrections += 1
        sites_touched += len(rec.applied)
        clippings += sum(1 for u in rec.applied if u.clipped)

        # Collateral: an applied update whose unit the oracle did NOT blame.
        responsible = responsible_units(res)
        collateral += sum(1 for u in rec.applied if u.unit not in responsible)

        wmd_sum += wmd(before, q, ks, credit.blamed_units)
        kd_sum += kd_innocent(before, q, ks, credit.blamed_units)

        if (ep + 1) % eval_every == 0:
            record(ep + 1)

    n_corr = max(1, corrections)
    return TrainResult(
        arm=arm, seed=seed, checkpoints=checkpoints, success_curve=curve,
        family_counts=counts, wmd=wmd_sum / n_corr, kd_innocent=kd_sum / n_corr,
        collateral=collateral / max(1, sites_touched), corrections=corrections,
        sites_touched=sites_touched,
        clippings=clippings, wall_s=time.perf_counter() - t0, q_hash=q.deep_hash(),
    )
