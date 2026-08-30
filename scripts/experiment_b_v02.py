"""RFL-CausalChase v0.2 Experiment B.

The transfer path is deliberately strict: one real Standard-HQ checkpoint per
seed, bitwise clones for every algorithm, controlled diagnostic-only shocks,
then real task-reward recovery.  A failed pre-shock gate stops before shocks.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import yaml

# Allow the scripts to be run directly as well as imported by tests.
try:  # pragma: no cover - each branch is exercised in a different entry path
    from .experiment_a import build_sequence_model
    from .experiment_b import run_learning
except ImportError:  # direct script execution
    from experiment_a import build_sequence_model
    from experiment_b import run_learning
from rflcc.baselines.cf_only import CFOnly
from rflcc.baselines.full_rfl import FullRFL
from rflcc.baselines.immediate import Immediate
from rflcc.baselines.pe_seq import PESeq
from rflcc.baselines.standard import StandardHQ
from rflcc.checkpoints import load_checkpoint
from rflcc.counterfactual import CounterfactualRunner
from rflcc.env import CausalChaseEnv
from rflcc.knowledge import (
    InvalidKnowledgeProbe,
    correct_knowledge_damage,
    correct_margin,
    recovery_episode,
    require_initial_correct_margin,
    wrong_knowledge_reinforcement,
)
from rflcc.metrics import compute_update_metrics
from rflcc.policies import ScriptedRouteFollower
from rflcc.qtables import linear_epsilon
from rflcc.router import UpdateRouter
from rflcc.types import TERM_EXIT
from rflcc.scenarios import ScenarioGenerator
from rflcc.update_scenarios import is_high_protection, is_low_protection


PRIMARY_ALGORITHMS = (
    "standard", "immediate", "er5", "pe_seq", "cf_only", "full_rfl",
    "rfl_observe", "oracle_update", "full_rfl_cfcritical",
)

ARTIFACT_SCHEMA_VERSION = "0.2.1"


def _seed32(value: int) -> int:
    """Map composed deterministic seeds into NumPy's accepted range."""
    return int(value % (2**32 - 1))


def load_config(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _config_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _git_commit() -> str:
    return os.popen("git rev-parse HEAD").read().strip()


def _seed_identity(cfg: dict, experiment_seed: int, *, scenario_seed: int | None = None) -> dict:
    """Use the same explicit seed labels in every v0.2 B artifact."""
    return {
        "seed_index": int(experiment_seed) - int(cfg["experiment"].get("seed_base", 0)),
        "experiment_seed": int(experiment_seed),
        "scenario_seed": scenario_seed,
    }


def _load_completed(path: Path, cfg_hash: str, *, status: str | None = None) -> dict | None:
    """Return a finished seed artifact only when it belongs to this config.

    A changed config in the same output directory is an audit error, not a
    reason to overwrite the old seed.  This makes interrupted pilot and
    confirmatory runs safely resumable by seed.
    """
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("config_hash") != cfg_hash:
        raise RuntimeError(f"refusing to overwrite completed artifact with different config: {path}")
    if status is None or payload.get("status") == status:
        return payload
    return None


def _env(cfg: dict, *, dash_p: float | None = None) -> CausalChaseEnv:
    e = cfg["environment"]
    return CausalChaseEnv(
        horizon=e["horizon"], monster_move_period=e["monster_move_period"],
        monster_dash_p=e["monster_dash_p"] if dash_p is None else dash_p,
        rewards=e.get("rewards"),
    )


def _runners(cfg: dict, env: CausalChaseEnv):
    cc = cfg["counterfactual"]
    policy_for = lambda option: ScriptedRouteFollower(option)
    return (
        CounterfactualRunner(policy_for=policy_for, env=env, top_k=cc.get("top_k_causes", 2), low_level_window=cc.get("low_level_window", 3)),
        CounterfactualRunner(policy_for=policy_for, env=env, top_k=3, low_level_window=10**6),
    )


def _responsibility(name, trace, feedback, seq_model, runner, exhaustive, *, oracle_r=None):
    """Learner attribution, except explicit evaluator-only Oracle-Update."""
    if name == "standard":
        return None, 0, {}
    if name in ("immediate", "er5"):
        out = Immediate().attribute(trace, feedback, None, None)
    elif name == "pe_seq":
        out = PESeq().attribute(trace, feedback, seq_model, None)
    elif name == "cf_only":
        out = CFOnly().attribute(trace, feedback, seq_model, exhaustive)
    elif name in ("full_rfl", "rfl_observe", "full_rfl_cfcritical"):
        out = FullRFL().attribute(trace, feedback, seq_model, runner)
    elif name == "oracle_update":
        if oracle_r is None:
            raise RuntimeError("Oracle-Update must be supplied by evaluator assembly")
        return dict(oracle_r), 0, {"evaluator_only_oracle_update": True}
    else:
        raise ValueError(name)
    return out.responsibility, out.cf_transitions, out.info


def _critical_low_site(trace, runner):
    result = runner.verify(trace, candidates=["L"])
    if result.critical_low_t is None:
        return None
    t = trace.transitions[result.critical_low_t]
    return t.state, t.action


def run_checkpoint(cfg: dict, outdir: str | Path, seed: int) -> dict:
    """Train exactly one common scripted-low Standard-HQ checkpoint per seed.

    Scripted low-level execution is the frozen B1 isolation of Q_H; it follows
    the selected option (not a fixed route) and still records Q_L task values
    for later L-module shock/recovery measurements.
    """
    outdir = Path(outdir)
    ckpt_dir = outdir / "checkpoints" / f"seed_{seed}"
    result_path = outdir / f"checkpoint_seed{seed}.json"
    cfg_hash = _config_hash(cfg)
    existing = _load_completed(result_path, cfg_hash)
    if existing is not None:
        # Validate the checkpoint again rather than trusting a stale result
        # JSON after a manual filesystem change.
        load_checkpoint(ckpt_dir, expected_config_hash=cfg_hash)
        return existing
    episodes = int(cfg["experiment"]["pretrain_episodes"])
    result = run_learning(
        cfg, "B4", "standard", seed=seed, episodes=episodes,
        eval_every=max(1, int(cfg["experiment"].get("checkpoint_eval_every", 100))),
        use_scripted_low=True, learn_low_while_scripted=True,
        outdir=str(outdir / "checkpoint_runs"), run_id="B-v02-checkpoint",
        checkpoint_dir=str(ckpt_dir), checkpoint_config_hash=cfg_hash,
    )
    _, meta = load_checkpoint(ckpt_dir, expected_config_hash=cfg_hash)
    gate = result["final_success"] >= 0.90 and result["final_safe_option"] >= 0.90
    output = {
        "schema_version": ARTIFACT_SCHEMA_VERSION, "config_hash": cfg_hash, "git_commit": _git_commit(),
        **_seed_identity(cfg, seed), "status": "completed" if gate else "blocked_pretrain_gate",
        "seed": seed, "checkpoint_dir": str(ckpt_dir), "q_hash": meta["q_hash"],
        "pretrain_episodes": episodes, "pre_success": result["final_success"],
        "pre_safe_option": result["final_safe_option"], "pretrain_gate": gate,
        "pretrain_result": result,
    }
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _row(q, module, state):
    if module == "H":
        return {0: q.high_get(state, 0), 1: q.high_get(state, 1)}
    return {a: q.low_get(state, a) for a in range(q.n_actions)}


def _is_unique_greedy(values: dict, action: int) -> bool:
    """The nominated protected action must be the checkpoint's sole argmax."""
    maximum = max(values.values())
    return values.get(action) == maximum and sum(value == maximum for value in values.values()) == 1


def _probe_for_sample(q, direction: str, sample, *, minimum_margin: float) -> dict | None:
    """Return one direction-specific protected probe, or ``None`` if invalid.

    The former implementation always emitted an H and an L probe, then
    treated a deliberately faulty L last-action as known-correct.  A probe is
    now direction-specific and accepted only when the *common checkpoint*
    already knows its nominated correct action.
    """
    trace = sample.trace
    if direction == "l_dominant_false_h":
        state = int(trace.noise_tape.monster_start_lane)
        correct, wrong, module = 1 - state, state, "H"
    elif direction == "h_dominant_false_l":
        last = trace.transitions[-1]
        state, correct, module = last.state, int(last.action), "L"
        values = _row(q, module, state)
        competitors = {action: value for action, value in values.items() if action != correct}
        wrong = max(competitors, key=competitors.get)
    else:  # pragma: no cover - guarded by the fixed direction table
        raise ValueError(direction)
    values = _row(q, module, state)
    if not _is_unique_greedy(values, correct):
        return None
    try:
        initial_margin = require_initial_correct_margin(
            values, correct, minimum=float(minimum_margin)
        )
    except InvalidKnowledgeProbe:
        return None
    return {
        "module": module,
        "state": state,
        "correct": correct,
        "wrong": wrong,
        "initial_margin": initial_margin,
        "last_action": int(trace.transitions[-1].action),
    }


def _build_protected_probe_plan(cfg: dict, q0, seed: int) -> tuple[list[dict], dict]:
    """Freeze all B probes before *any* algorithm runs.

    Exactly ``shocks / 2`` samples are requested per direction.  Each slot is
    searched at most 300 deterministic candidates.  Failure is evidence that
    the current checkpoint/environment cannot identify the corresponding
    protected knowledge, not permission to change a scenario or denominator.
    """
    n_shocks = int(cfg["experiment"]["shocks"])
    if n_shocks < 2 or n_shocks % 2:
        raise ValueError("shocks must be a positive even number")
    half = n_shocks // 2
    if cfg["experiment"].get("name") in {"v02_pilot", "v02_confirmatory"} and half != 10:
        raise ValueError("pilot and confirmatory B-transfer require exactly 10 probes per direction")
    search_limit = int(cfg.get("scenarios", {}).get("search_attempts_per_trace", 0))
    if search_limit != 300:
        raise ValueError("protected-probe search_attempts_per_trace is frozen at 300")
    minimum_margin = float(cfg.get("knowledge", {}).get("initial_correct_margin", 0.60))
    env = _env(cfg)
    acceptance = cfg.get("scenarios", {}).get("acceptance", {})
    generator = ScenarioGenerator(
        env=env,
        delta_target_pos=float(acceptance.get("delta_target_pos", 0.4)),
        delta_leak=float(acceptance.get("delta_leak", 0.1)),
        max_attempts=search_limit,
    )
    directions = (
        ("h_dominant_false_l", "H", is_low_protection, "L", 101),
        ("l_dominant_false_h", "L", is_high_protection, "H", 202),
    )
    plan: list[dict] = []
    diagnostics: dict[str, dict] = {}
    for direction, cause, predicate, feedback, offset in directions:
        accepted, rejected = 0, 0
        accepted_ids: list[str] = []
        for slot in range(half):
            found = None
            for attempt in range(search_limit):
                scenario_seed = int(seed + offset + slot * 100_003 + attempt * 7_919)
                sample = generator._try_candidate(cause, scenario_seed, attempt)
                if sample is None or not sample.oracle.responsibility or not predicate(sample.oracle.responsibility):
                    rejected += 1
                    continue
                probe = _probe_for_sample(q0, direction, sample, minimum_margin=minimum_margin)
                if probe is None:
                    rejected += 1
                    continue
                found = (sample, probe)
                break
            if found is None:
                break
            sample, probe = found
            probe_id = f"{direction}:{slot:02d}:{sample.scenario_id}"
            probe.update({
                "probe_id": probe_id,
                "direction": direction,
                "source_scenario_id": sample.scenario_id,
                "scenario_seed": int(sample.seed),
            })
            plan.append({
                "shock_type": direction,
                "scenario": SimpleNamespace(
                    scenario_id=sample.scenario_id,
                    trace=sample.trace,
                    oracle_r=dict(sample.oracle.responsibility),
                    feedback=feedback,
                    scenario_seed=int(sample.seed),
                ),
                "probe": probe,
            })
            accepted += 1
            accepted_ids.append(probe_id)
        diagnostics[direction] = {
            "requested": half,
            "accepted": accepted,
            "rejected_candidates": rejected,
            "search_attempts_per_slot": search_limit,
            "probe_ids": accepted_ids,
        }
    if len(plan) != n_shocks:
        return [], diagnostics
    return plan, diagnostics


def _probe_margin(q, probe) -> float:
    values = _row(q, probe["module"], probe["state"])
    return correct_margin(values, probe["correct"])


def _probe_damage(q_before, q_after, probe) -> tuple[float, float]:
    before = _row(q_before, probe["module"], probe["state"])
    after = _row(q_after, probe["module"], probe["state"])
    return (
        correct_knowledge_damage(before, after, probe["correct"]),
        wrong_knowledge_reinforcement(before, after, probe["correct"], probe["wrong"]),
    )


def _task_episode(agent: StandardHQ, env: CausalChaseEnv, seed: int, epsilon: float) -> float:
    obs, _ = env.reset(seed=seed)
    s_h = obs.monster_start_lane
    option = agent.select_option(s_h, epsilon)
    env.set_option(option)
    rewards = []
    while not (env.terminated or env.truncated):
        state = obs.low_state
        action = agent.select_action(state, epsilon)
        obs2, reward, terminated, truncated, _ = env.step(action)
        agent.update_low(state, action, reward, obs2.low_state, terminated or truncated)
        rewards.append(reward)
        obs = obs2
    ret = 0.0
    for reward in reversed(rewards):
        ret = reward + agent.gamma * ret
    agent.update_high(s_h, option, ret)
    return ret


def _evaluate(agent: StandardHQ, env: CausalChaseEnv, *, seed: int, n_eval: int = 50) -> dict:
    before = agent.q.deep_hash()
    successes, safe, returns = 0, 0, []
    for k in range(n_eval):
        obs, _ = env.reset(seed=seed + k)
        lane = obs.monster_start_lane
        option = agent.select_option(lane, 0.0)
        env.set_option(option)
        safe += int(option != lane)
        rewards = []
        while not (env.terminated or env.truncated):
            obs, reward, _, _, _ = env.step(agent.select_action(obs.low_state, 0.0))
            rewards.append(reward)
        successes += int(env.terminal_type == TERM_EXIT)
        ret = 0.0
        for reward in reversed(rewards):
            ret = reward + agent.gamma * ret
        returns.append(ret)
    if agent.q.deep_hash() != before:
        raise AssertionError("evaluation mutated Q")
    return {"success": successes / n_eval, "safe_option": safe / n_eval, "return": float(np.mean(returns))}


def _recover(q, cfg: dict, *, seed: int, probes: list[dict], pre_shock_margin: float) -> dict:
    env = _env(cfg)
    lr = cfg["learning"]
    agent = StandardHQ(
        alpha_low=lr["alpha_low"], alpha_high=lr["alpha_high"], gamma=cfg["environment"]["gamma"],
        rng=np.random.RandomState(_seed32(seed + 700_000)),
    )
    agent.q = q
    horizon = int(cfg["experiment"]["recovery_episodes"])
    interval = int(cfg["experiment"].get("recovery_eval_every", 25))
    post_shock_margin = float(np.mean([_probe_margin(agent.q, p) for p in probes]))
    # The recovery curve starts immediately after the diagnostic shocks.  The
    # explicit episode-0 evaluation is necessary for the preregistered
    # AUC_success,0:500 rather than an implicit 25/10-episode offset.
    records = [{
        "episode": 0,
        **_evaluate(agent, env, seed=_seed32(seed * 10_000_000), n_eval=50),
        "knowledge_margin": post_shock_margin,
    }]
    margins = [post_shock_margin]
    for episode in range(1, horizon + 1):
        # Recovery continues the frozen pretraining schedule.  It must not
        # silently invent a second 0.10 -> 0.02 anneal for the recovery-only
        # phase; at the pilot checkpoint this is the configured 0.02 floor.
        eps = linear_epsilon(
            int(cfg["experiment"]["pretrain_episodes"]) + episode - 1,
            float(lr["epsilon_start"]),
            float(lr["epsilon_end"]),
            int(lr["epsilon_decay_episodes"]),
        )
        _task_episode(agent, env, _seed32(seed * 1_000_000 + episode), eps)
        if episode % interval == 0 or episode == horizon:
            evaluation = _evaluate(agent, env, seed=_seed32(seed * 10_000_000 + episode * 100), n_eval=50)
            margin = float(np.mean([_probe_margin(agent.q, p) for p in probes]))
            margins.append(margin)
            records.append({"episode": episode, **evaluation, "knowledge_margin": margin})
    knowledge_cfg = cfg.get("knowledge", {})
    recovery = recovery_episode(
        margins,
        initial_margin=pre_shock_margin,
        fraction=float(knowledge_cfg.get("recovery_fraction", 0.95)),
        consecutive=int(knowledge_cfg.get("recovery_consecutive_checkpoints", 3)),
        checkpoint_interval=interval,
        horizon=horizon,
    )
    return {"q": agent.q, "eval_records": records, "margins": margins, "recovery_episode": recovery}


def _transfer_algorithm(q0, plan, name, cfg, seq_model, runner, exhaustive) -> dict:
    """Apply the shocks, then compare the fixed protected probes with ``q0``.

    The reported CKD/WKR are deliberately not shock-by-shock averages.  Each
    algorithm is measured against the same common checkpoint after the whole
    frozen shock schedule, avoiding a fabricated near-zero denominator.
    """
    q = q0.copy()
    pre_hash = q.deep_hash()
    alpha_diag = float(cfg["learning"]["alpha_diag"])
    all_probes = [entry["probe"] for entry in plan]
    shock_rows = []
    for index, entry in enumerate(plan):
        shock_type, scenario, probe = entry["shock_type"], entry["scenario"], entry["probe"]
        trace = scenario.trace
        tr = trace.transitions[-1]
        before_hash = q.deep_hash()
        responsibility, cf_cost, info = _responsibility(
            name, trace, scenario.feedback, seq_model, runner, exhaustive,
            oracle_r=(scenario.oracle_r if name == "oracle_update" else None),
        )
        receipts = []
        if name not in ("standard", "rfl_observe") and responsibility is not None:
            critical = _critical_low_site(trace, runner) if name == "full_rfl_cfcritical" else None
            router = UpdateRouter(alpha_diag=alpha_diag, use_cf_critical=(name == "full_rfl_cfcritical"))
            routed = router.route(
                responsibility=responsibility,
                s_h=trace.noise_tape.monster_start_lane,
                option=trace.option,
                last_low=(tr.state, tr.action),
                critical_low=critical,
            )
            receipts = router.apply(q, routed)
        update = compute_update_metrics(receipts, scenario.oracle_r, alpha_diag=alpha_diag)
        # Oracle-Update is intentionally an evaluator-side upper bound.  Its
        # labels may determine the applied update, but those labels must never
        # be serialized as learner output (or passed to a normal learner).
        learner_responsibility = {} if name == "oracle_update" else (responsibility or {})
        shock_rows.append({
            "shock_index": index, "shock_type": shock_type, "scenario_id": scenario.scenario_id,
            "scenario_seed": scenario.scenario_seed, "probe_id": probe["probe_id"],
            "feedback": scenario.feedback,
            "learner": {"responsibility": learner_responsibility, "cf_transitions": cf_cost},
            "evaluator_only": {
                "oracle_R": scenario.oracle_r,
                "oracle_update_upper_bound": bool(name == "oracle_update"),
            },
            "actual_update": update.actual_update_mass,
            "applied_updates": [asdict(r) for r in receipts],
            "update_precision": update.precision, "update_recall": update.recall,
            "update_f1": update.f1, "actual_wur": update.actual_wur,
            "cf_transitions": cf_cost, "q_hash_before_shock": before_hash,
            "q_hash_after_shock": q.deep_hash(),
        })
    per_probe = []
    for probe in all_probes:
        ckd_value, wkr_value = _probe_damage(q0, q, probe)
        per_probe.append({
            "probe_id": probe["probe_id"], "direction": probe["direction"],
            "initial_margin": probe["initial_margin"], "post_shock_margin": _probe_margin(q, probe),
            "correct_knowledge_damage": ckd_value,
            "wrong_knowledge_reinforcement": wkr_value,
        })
    pre_margin = float(np.mean([probe["initial_margin"] for probe in all_probes]))
    post_margin = float(np.mean([_probe_margin(q, probe) for probe in all_probes]))
    post_shock_hash = q.deep_hash()
    recovery = _recover(
        q, cfg, seed=int(plan[0]["scenario"].trace.seed), probes=all_probes,
        pre_shock_margin=pre_margin,
    )
    return {
        "algorithm": name, "pre_shock_hash": pre_hash, "post_shock_hash": post_shock_hash,
        "shock_count": len(shock_rows), "shocks": shock_rows,
        "probe_ids": [probe["probe_id"] for probe in all_probes],
        "knowledge_by_probe": per_probe,
        "correct_knowledge_damage": float(np.mean([row["correct_knowledge_damage"] for row in per_probe])),
        "wrong_knowledge_reinforcement": float(np.mean([row["wrong_knowledge_reinforcement"] for row in per_probe])),
        "knowledge_margin_pre_shock": pre_margin, "knowledge_margin_post_shock": post_margin,
        "recovery_episode": recovery["recovery_episode"],
        "recovery_eval_records": recovery["eval_records"],
        "recovery_margins": recovery["margins"], "q_hash_after_recovery": recovery["q"].deep_hash(),
    }


def run_transfer(cfg: dict, outdir: str | Path, seed: int, algorithms=None) -> dict:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cfg_hash = _config_hash(cfg)
    result_path = outdir / f"transfer_seed{seed}.json"
    existing = _load_completed(result_path, cfg_hash)
    if existing is not None:
        return existing
    checkpoint = run_checkpoint(cfg, outdir, seed)
    if not checkpoint["pretrain_gate"]:
        result = {
            **checkpoint, "schema_version": ARTIFACT_SCHEMA_VERSION, "config_hash": cfg_hash,
            "git_commit": _git_commit(), "status": "blocked_pretrain_gate", "algorithms": {},
        }
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    q0, _ = load_checkpoint(checkpoint["checkpoint_dir"], expected_config_hash=cfg_hash)
    algorithms = tuple(algorithms or cfg["experiment"].get("algorithms", PRIMARY_ALGORITHMS))
    if set(algorithms) - set(PRIMARY_ALGORITHMS):
        raise ValueError("unsupported transfer algorithm")
    plan, probe_search = _build_protected_probe_plan(cfg, q0, seed)
    if not plan:
        result = {
            **checkpoint, "schema_version": ARTIFACT_SCHEMA_VERSION, "config_hash": cfg_hash,
            "git_commit": _git_commit(), "status": "blocked_invalid_knowledge_probe",
            "common_checkpoint_hash": checkpoint["q_hash"], "probe_search": probe_search,
            "protected_probes": [], "algorithms": {},
        }
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    env = _env(cfg)
    seq_model, _ = build_sequence_model(cfg, env, 5, cfg.get("scenarios", {}).get("calibration_seed_offset", 1_000_000))
    runner, exhaustive = _runners(cfg, env)
    results = {}
    for name in algorithms:
        if q0.deep_hash() != checkpoint["q_hash"]:
            raise AssertionError("common checkpoint hash changed before clone")
        result = _transfer_algorithm(q0, plan, name, cfg, seq_model, runner, exhaustive)
        if result["pre_shock_hash"] != checkpoint["q_hash"]:
            raise AssertionError("algorithm clone was not bitwise identical pre-shock")
        results[name] = result
    output = {
        **checkpoint, "schema_version": ARTIFACT_SCHEMA_VERSION, "config_hash": cfg_hash, "git_commit": _git_commit(),
        **_seed_identity(cfg, seed),
        "status": "completed", "common_checkpoint_hash": checkpoint["q_hash"],
        "probe_search": probe_search,
        "protected_probes": [entry["probe"] for entry in plan],
        "algorithms": results,
    }
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _normalized_success_auc(curve: list[dict], horizon: int) -> float | None:
    """Trapezoidal mean success from episode 0 through ``horizon``.

    Curves written by v0.2 have an explicit episode-0 point.  Linear endpoint
    interpolation keeps the measure defined if a future configuration uses an
    evaluation cadence that does not divide the requested horizon.
    """
    if not curve or horizon <= 0:
        return None
    pairs = sorted((float(r["episode"]), float(r["success"])) for r in curve)
    if pairs[0][0] > 0.0:
        return None
    trimmed = [(x, y) for x, y in pairs if x <= horizon]
    if not trimmed:
        return None
    if trimmed[-1][0] < horizon:
        later = next(((x, y) for x, y in pairs if x > horizon), None)
        if later is None:
            return None
        x0, y0 = trimmed[-1]
        x1, y1 = later
        trimmed.append((float(horizon), y0 + (y1 - y0) * (horizon - x0) / (x1 - x0)))
    xs = np.asarray([x for x, _ in trimmed])
    ys = np.asarray([y for _, y in trimmed])
    integral = np.trapezoid(ys, xs) if hasattr(np, "trapezoid") else np.trapz(ys, xs)
    return float(integral / float(horizon))


def _three_checkpoint_to_90(curve: list[dict], *, horizon: int) -> int:
    """First threshold-crossing checkpoint confirmed for three evaluations."""
    ordered = sorted((int(r["episode"]), float(r["success"])) for r in curve)
    for index in range(len(ordered) - 2):
        triple = ordered[index:index + 3]
        if all(success >= 0.90 for _, success in triple):
            return triple[0][0]
    return horizon + 1


def _curve_metrics(raw: dict, episodes: int) -> dict:
    curve = raw.get("eval_records", [])
    # The primary B-online AUC is fixed to 0:3000; a smoke run uses its full
    # (shorter) horizon to exercise the same calculation without inventing
    # unobserved post-training values.
    auc_horizon = min(3_000, episodes)
    return {
        "success_auc": _normalized_success_auc(curve, auc_horizon),
        "success_auc_horizon": auc_horizon,
        "episodes_to_90": _three_checkpoint_to_90(curve, horizon=episodes),
    }


def run_online(cfg: dict, outdir: str | Path, seed: int, algorithms=None) -> dict:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cfg_hash = _config_hash(cfg)
    result_path = outdir / f"online_seed{seed}.json"
    existing = _load_completed(result_path, cfg_hash)
    if existing is not None:
        return existing
    episodes = int(cfg["experiment"]["online_episodes"])
    interval = int(cfg["experiment"].get("online_eval_every", 100))
    algorithms = tuple(algorithms or cfg["experiment"].get("algorithms", PRIMARY_ALGORITHMS))
    result = {}
    for name in algorithms:
        run = run_learning(
            cfg, "B4", name, seed=seed, episodes=episodes, eval_every=interval,
            use_scripted_low=False, outdir=str(outdir / "online_runs"), run_id="B-v02-online",
            include_initial_eval=True,
        )
        raw_path = outdir / "online_runs" / f"B4_{name}_seed{seed}.json"
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        if run["q_hash_initial"] == run["q_hash_final"] or int(run["task_update_count"]) <= 0:
            raise AssertionError(f"B-online {name} did not perform real task Bellman updates")
        result[name] = {**run, **_curve_metrics(raw, episodes), "eval_records": raw.get("eval_records", [])}
    output = {
        "schema_version": ARTIFACT_SCHEMA_VERSION, "config_hash": cfg_hash, "git_commit": _git_commit(),
        **_seed_identity(cfg, seed), "status": "completed", "seed": seed,
        "episodes": episodes, "algorithms": result,
    }
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--stage", choices=("checkpoint", "transfer", "online"), default="transfer")
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--seeds", type=int, default=None)
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    exp = cfg["experiment"]
    seeds = int(args.seeds if args.seeds is not None else exp["seeds"])
    outdir = Path(args.outdir or f"outputs/v02_{exp['name']}_b")
    outdir.mkdir(parents=True, exist_ok=True)
    seed_base = int(exp.get("seed_base", 0))
    run_seeds = [seed_base + seed_index for seed_index in range(seeds)]
    if args.stage == "checkpoint":
        results = [run_checkpoint(cfg, outdir, seed) for seed in run_seeds]
        gate_ok = all(r["pretrain_gate"] for r in results)
    elif args.stage == "transfer":
        results = [run_transfer(cfg, outdir, seed) for seed in run_seeds]
        gate_ok = all(r["status"] == "completed" for r in results)
    else:
        results = [run_online(cfg, outdir, seed) for seed in run_seeds]
        gate_ok = all(
            r.get("status") == "completed"
            and all(
                item.get("q_hash_initial") != item.get("q_hash_final")
                and int(item.get("task_update_count", 0)) > 0
                for item in r.get("algorithms", {}).values()
            )
            for r in results
        )
    meta = {
        "schema_version": ARTIFACT_SCHEMA_VERSION, "stage": args.stage, "seeds": seeds,
        "config_hash": _config_hash(cfg), "git_commit": os.popen("git rev-parse HEAD").read().strip(),
        "gate_ok": gate_ok, "results": results, "timestamp": time.time(),
    }
    (outdir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"stage": args.stage, "seeds": seeds, "gate_ok": gate_ok}, ensure_ascii=False))
    # A pretrain/probe failure is an invalid measurement or runtime gate, not
    # a scientific FAIL.  The unified pipeline reserves 3 for this class.
    return 0 if gate_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
