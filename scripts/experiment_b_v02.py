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
from rflcc.knowledge import correct_knowledge_damage, correct_margin, recovery_episode, wrong_knowledge_reinforcement
from rflcc.metrics import compute_update_metrics
from rflcc.policies import ScriptedRouteFollower
from rflcc.qtables import linear_epsilon
from rflcc.router import UpdateRouter
from rflcc.types import TERM_EXIT
from rflcc.update_scenarios import make_high_protection, make_low_protection


PRIMARY_ALGORITHMS = (
    "standard", "immediate", "er5", "pe_seq", "cf_only", "full_rfl",
    "rfl_observe", "oracle_update", "full_rfl_cfcritical",
)


def _seed32(value: int) -> int:
    """Map composed deterministic seeds into NumPy's accepted range."""
    return int(value % (2**32 - 1))


def load_config(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _config_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _git_commit() -> str:
    return os.popen("git rev-parse HEAD").read().strip()


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
        "schema_version": "0.2.0", "config_hash": cfg_hash, "git_commit": _git_commit(),
        "status": "completed" if gate else "blocked_pretrain_gate",
        "seed": seed, "checkpoint_dir": str(ckpt_dir), "q_hash": meta["q_hash"],
        "pretrain_episodes": episodes, "pre_success": result["final_success"],
        "pre_safe_option": result["final_safe_option"], "pretrain_gate": gate,
        "pretrain_result": result,
    }
    result_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _shock_scenarios(cfg: dict, seed: int):
    n = int(cfg["experiment"]["shocks"])
    if n < 2 or n % 2:
        raise ValueError("shocks must be a positive even number")
    # low-protection is H-dominant, false L; high-protection is L-dominant,
    # false H.  Thus each half is controlled misleading feedback.
    half = n // 2
    return (
        [("h_dominant_false_l", s) for s in make_low_protection(half, seed=seed + 101, max_attempts=300)]
        + [("l_dominant_false_h", s) for s in make_high_protection(half, seed=seed + 202, max_attempts=300)]
    )


def _row(q, module, state):
    if module == "H":
        return {0: q.high_get(state, 0), 1: q.high_get(state, 1)}
    return {a: q.low_get(state, a) for a in range(q.n_actions)}


def _probes_for_shock(q, trace):
    tr = trace.transitions[-1]
    s_h = trace.noise_tape.monster_start_lane
    return [
        {"module": "H", "state": s_h, "correct": 1 - s_h, "wrong": s_h},
        {"module": "L", "state": tr.state, "correct": tr.action, "wrong": (tr.action + 1) % q.n_actions},
    ]


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
        eps = linear_epsilon(episode - 1, 0.10, 0.02, max(1, horizon))
        _task_episode(agent, env, _seed32(seed * 1_000_000 + episode), eps)
        if episode % interval == 0 or episode == horizon:
            evaluation = _evaluate(agent, env, seed=_seed32(seed * 10_000_000 + episode * 100), n_eval=50)
            margin = float(np.mean([_probe_margin(agent.q, p) for p in probes]))
            margins.append(margin)
            records.append({"episode": episode, **evaluation, "knowledge_margin": margin})
    knowledge_cfg = cfg.get("knowledge", {})
    recovery = recovery_episode(
        margins,
        initial_margin=max(pre_shock_margin, 1e-9),
        fraction=float(knowledge_cfg.get("recovery_fraction", 0.95)),
        consecutive=int(knowledge_cfg.get("recovery_consecutive_checkpoints", 3)),
        checkpoint_interval=interval,
        horizon=horizon,
    )
    return {"q": agent.q, "eval_records": records, "margins": margins, "recovery_episode": recovery}


def _transfer_algorithm(q0, scenarios, name, cfg, seq_model, runner, exhaustive) -> dict:
    q = q0.copy()
    pre_hash = q.deep_hash()
    alpha_diag = float(cfg["learning"]["alpha_diag"])
    all_probes = []
    shock_rows = []
    pre_shock_q = q.copy()
    for index, (shock_type, scenario) in enumerate(scenarios):
        trace = scenario.trace
        tr = trace.transitions[-1]
        before = q.copy()
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
        probes = _probes_for_shock(q, trace)
        all_probes.extend(probes)
        damage = [_probe_damage(before, q, p) for p in probes]
        # Oracle-Update is intentionally an evaluator-side upper bound.  Its
        # labels may determine the applied update, but those labels must never
        # be serialized as learner output (or passed to a normal learner).
        learner_responsibility = {} if name == "oracle_update" else (responsibility or {})
        shock_rows.append({
            "shock_index": index, "shock_type": shock_type, "scenario_id": scenario.scenario_id,
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
            "correct_knowledge_damage": float(np.mean([x[0] for x in damage])),
            "wrong_knowledge_reinforcement": float(np.mean([x[1] for x in damage])),
            "cf_transitions": cf_cost, "q_hash_after_shock": q.deep_hash(),
        })
    pre_margin = float(np.mean([_probe_margin(pre_shock_q, p) for p in all_probes]))
    post_margin = float(np.mean([_probe_margin(q, p) for p in all_probes]))
    post_shock_hash = q.deep_hash()
    recovery = _recover(q, cfg, seed=int(scenarios[0][1].trace.seed), probes=all_probes, pre_shock_margin=pre_margin)
    return {
        "algorithm": name, "pre_shock_hash": pre_hash, "post_shock_hash": post_shock_hash,
        "shock_count": len(shock_rows), "shocks": shock_rows,
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
            **checkpoint, "schema_version": "0.2.0", "config_hash": cfg_hash,
            "git_commit": _git_commit(), "status": "blocked_pretrain_gate", "algorithms": {},
        }
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    q0, _ = load_checkpoint(checkpoint["checkpoint_dir"], expected_config_hash=cfg_hash)
    algorithms = tuple(algorithms or cfg["experiment"].get("algorithms", PRIMARY_ALGORITHMS))
    if set(algorithms) - set(PRIMARY_ALGORITHMS):
        raise ValueError("unsupported transfer algorithm")
    env = _env(cfg)
    seq_model, _ = build_sequence_model(cfg, env, 5, cfg.get("scenarios", {}).get("calibration_seed_offset", 1_000_000))
    runner, exhaustive = _runners(cfg, env)
    scenarios = _shock_scenarios(cfg, seed)
    results = {}
    for name in algorithms:
        if q0.deep_hash() != checkpoint["q_hash"]:
            raise AssertionError("common checkpoint hash changed before clone")
        result = _transfer_algorithm(q0, scenarios, name, cfg, seq_model, runner, exhaustive)
        if result["pre_shock_hash"] != checkpoint["q_hash"]:
            raise AssertionError("algorithm clone was not bitwise identical pre-shock")
        results[name] = result
    output = {
        **checkpoint, "schema_version": "0.2.0", "config_hash": cfg_hash, "git_commit": _git_commit(),
        "status": "completed", "common_checkpoint_hash": checkpoint["q_hash"], "algorithms": results,
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
        result[name] = {**run, **_curve_metrics(raw, episodes), "eval_records": raw.get("eval_records", [])}
    output = {
        "schema_version": "0.2.0", "config_hash": cfg_hash, "git_commit": _git_commit(),
        "status": "completed", "seed": seed, "episodes": episodes, "algorithms": result,
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
        gate_ok = True
    meta = {
        "schema_version": "0.2.0", "stage": args.stage, "seeds": seeds,
        "config_hash": _config_hash(cfg), "git_commit": os.popen("git rev-parse HEAD").read().strip(),
        "gate_ok": gate_ok, "results": results, "timestamp": time.time(),
    }
    (outdir / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"stage": args.stage, "seeds": seeds, "gate_ok": gate_ok}, ensure_ascii=False))
    return 0 if gate_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
