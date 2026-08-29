"""v0.2 Experiment A: attribution and actual-update microbenchmarks."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import yaml

from experiment_a import build_sequence_model, ALGORITHMS
from rflcc.counterfactual import CounterfactualRunner
from rflcc.env import CausalChaseEnv
from rflcc.knowledge import correct_knowledge_damage, wrong_knowledge_reinforcement, correct_margin
from rflcc.metrics import compute_attribution_metrics, compute_update_metrics
from rflcc.logging_io import EpisodeLogger, build_episode_record
from rflcc.policies import ScriptedRouteFollower
from rflcc.router import UpdateRouter
from rflcc.update_scenarios import make_high_protection, make_low_protection, make_environment_mixed, make_hl_mixed


def load_config(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _runner(env, cfg):
    cc = cfg.get("counterfactual", {})
    return CounterfactualRunner(policy_for=lambda o: ScriptedRouteFollower(o), env=env, top_k=cc.get("top_k_causes", 2), low_level_window=cc.get("low_level_window", 3))


def run_update(cfg: dict, *, outdir: str, seeds: int, per_type: int, seed_base: int) -> list[dict]:
    os.makedirs(outdir, exist_ok=True)
    logger = EpisodeLogger(str(Path(outdir) / "episodes.jsonl"))
    env = CausalChaseEnv(**{k: cfg["environment"][k] for k in ("horizon", "monster_move_period", "monster_dash_p")})
    seq_model, _ = build_sequence_model(cfg, env, max(5, per_type), cfg.get("scenarios", {}).get("calibration_seed_offset", 1_000_000))
    runner = _runner(env, cfg)
    router = UpdateRouter(alpha_diag=cfg.get("learning", {}).get("alpha_diag", 0.10), use_cf_critical=False)
    makers = {"high_protection": make_high_protection, "low_protection": make_low_protection, "environment_mixed": make_environment_mixed, "hl_mixed": make_hl_mixed}
    rows = []
    for seed_idx in range(seeds):
        for kind, maker in makers.items():
            kind_offset = {"high_protection": 0, "low_protection": 100, "environment_mixed": 200, "hl_mixed": 300}[kind]
            scenarios = maker(per_type, seed=seed_base + seed_idx * 10000 + kind_offset, max_attempts=300)
            for scenario in scenarios:
                trace = scenario.trace
                observed = scenario.feedback
                algo = ALGORITHMS["immediate"]()
                outcome = algo.attribute(trace, observed, seq_model, runner)
                q = scenario.q_snapshot.copy()
                before_high = dict(q.high.get(0, {}))
                tr_last = trace.transitions[-1]
                before_low = list(q.low.get(tr_last.state, [0.0] * q.n_actions))
                routed = router.route(responsibility=outcome.responsibility, s_h=0, option=trace.option, last_low=(tr_last.state, tr_last.action))
                receipts = router.apply(q, routed)
                um = compute_update_metrics(receipts, scenario.oracle_r, alpha_diag=router.alpha_diag)
                after_high = dict(q.high.get(0, {}))
                after_low = list(q.low.get(tr_last.state, before_low))
                margins_before = {"H": correct_margin(before_high, trace.option), "L": correct_margin({i: v for i, v in enumerate(before_low)}, tr_last.action)}
                margins_after = {"H": correct_margin(after_high, trace.option), "L": correct_margin({i: v for i, v in enumerate(after_low)}, tr_last.action)}
                learner = {"q_seq": outcome.info.get("q_seq", {}), "G": outcome.info.get("G", {}), "q_pre": outcome.info.get("q_pre", {}), "cf_checked": outcome.info.get("cf_checked", []), "cf_delta": outcome.info.get("cf_delta", {}), "responsibility": outcome.responsibility or {}, "rho_high": -float((outcome.responsibility or {}).get("H", 0.0)), "rho_low": -float((outcome.responsibility or {}).get("L", 0.0)), "q_margin_before": min(margins_before.values()), "q_margin_after": min(margins_after.values()), "actual_update": um.actual_update_mass, "update_precision": um.precision, "update_recall": um.recall, "update_f1": um.f1, "correct_knowledge_damage": max(correct_knowledge_damage(before_high, after_high, trace.option), 0.0), "wrong_knowledge_reinforcement": 0.0, "recovery_episode": None}
                logger.write_episode(build_episode_record(run_id="A-v02", schema_version="0.2.0", seed=trace.seed, scenario_id=scenario.scenario_id, experiment="A-update", algorithm="immediate", condition=kind, trace=trace, observed_feedback=observed, feedback_is_false=(observed != trace.true_primary), learner=learner, evaluator_only={"oracle_primary": None, "oracle_R": scenario.oracle_r, "oracle_delta": {}}, metrics={"actual_update": um.actual_update_mass, "update_precision": um.precision, "update_recall": um.recall, "update_f1": um.f1, "actual_wur": um.actual_wur, "correct_knowledge_damage": learner["correct_knowledge_damage"]}, compute={"real_transitions": trace.n_transitions, "cf_transitions": outcome.cf_transitions}))
                rows.append({"seed": seed_idx, "scenario_id": scenario.scenario_id, "scenario_type": kind, "algorithm": "immediate", "oracle_R": scenario.oracle_r, "responsibility": outcome.responsibility, "actual_update": um.actual_update_mass, "update_precision": um.precision, "update_recall": um.recall, "update_f1": um.f1, "actual_wur": um.actual_wur, "q_margin_before": learner["q_margin_before"], "q_margin_after": learner["q_margin_after"], "correct_knowledge_damage": learner["correct_knowledge_damage"]})
    logger.close()
    with open(Path(outdir) / "update_rows.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--stage", choices=("attribution", "update", "all"), default="all")
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    exp = cfg.get("experiment", {})
    outdir = args.outdir or f"outputs/v02_{exp.get('name', 'run')}_a"
    rows = []
    if args.stage in ("update", "all"):
        rows = run_update(cfg, outdir=outdir, seeds=exp.get("seeds", 2), per_type=exp.get("update_scenarios_per_type", 3), seed_base=exp.get("seed_base", 3000000))
    meta = {"schema_version": "0.2.0", "stage": args.stage, "rows": len(rows), "timestamp": time.time()}
    Path(outdir).mkdir(parents=True, exist_ok=True)
    (Path(outdir) / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta))
    return 0 if (args.stage == "attribution" or rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
