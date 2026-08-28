"""Experiment A：Attribution Microbenchmark（S07）。

在不训练 Q 的前提下，对相同因果轨迹注入可控错误的诊断反馈，
比较各算法的归因误差（AE）、错误更新率（WUR）、UpdateCoverage、FFCR。

用法：
    python scripts/experiment_a.py --smoke --seeds 5
    python scripts/experiment_a.py --seeds 12 --outdir outputs/pilot_a
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import yaml

from rflcc.baselines.cf_only import CFOnly
from rflcc.baselines.full_rfl import FullRFL
from rflcc.baselines.immediate import Immediate
from rflcc.baselines.oracle_upper import OracleUpper
from rflcc.baselines.pe_seq import PESeq
from rflcc.counterfactual import CounterfactualRunner
from rflcc.env import CausalChaseEnv
from rflcc.feedback import FeedbackInjector
from rflcc.logging_io import EpisodeLogger, build_episode_record
from rflcc.metrics import compute_attribution_metrics
from rflcc.policies import ScriptedRouteFollower
from rflcc.scenarios import ScenarioGenerator
from rflcc.sequence import SequenceModel
from rflcc.types import CAUSES


ALGORITHMS = {
    "immediate": Immediate,
    "pe_seq": PESeq,
    "cf_only": CFOnly,
    "full_rfl": FullRFL,
    "oracle_upper": OracleUpper,
}


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_sequence_model(cfg: dict, env: CausalChaseEnv, per_cause: int, seed_offset: int):
    seq_cfg = cfg["sequence"]
    sc_cfg = cfg.get("scenarios", {})
    acc = sc_cfg.get("acceptance", {})
    gen = ScenarioGenerator(
        env=env,
        delta_target_pos=acc.get("delta_target_pos", 0.4),
        delta_leak=acc.get("delta_leak", 0.1),
        max_attempts=sc_cfg.get("search_attempts_per_trace", 120),
    )
    traces = {c: [] for c in CAUSES}
    for c in CAUSES:
        base = seed_offset + {"H": 0, "L": 100, "E": 200}[c]
        for s in gen.generate(c, base_seed=base, n=per_cause):
            traces[c].append(s.trace)
    model = SequenceModel(
        beta=seq_cfg.get("beta_prior", 1.0),
        probability_floor=seq_cfg.get("probability_floor", 0.01),
        eta=seq_cfg.get("adjacent_weight_eta", 0.5),
        tau_seq=seq_cfg.get("temperature", 0.5),
    )
    model.calibrate(traces)
    return model, gen


def run_experiment_a(cfg: dict, args) -> None:
    exp = cfg["experiment"]
    env_cfg = cfg["environment"]
    env = CausalChaseEnv(
        horizon=env_cfg["horizon"],
        monster_move_period=env_cfg["monster_move_period"],
        monster_dash_p=env_cfg["monster_dash_p"],
        rewards=env_cfg.get("rewards"),
    )
    cc_cfg = cfg["counterfactual"]
    fb_cfg = cfg["feedback"]
    att_cfg = cfg.get("attribution", {})

    per_cause = args.per_cause or exp.get("per_cause_traces", 30)
    n_seeds = args.seeds or exp.get("seeds", 12)
    seed_base = args.seed_base or exp.get("pilot_seed_base", 500000)
    conditions = exp.get("conditions", ["clean", "symmetric"])
    algos = [a for a in exp.get("algorithms", list(ALGORITHMS)) if a in ALGORITHMS]

    outdir = args.outdir or f"outputs/{exp.get('name', 'experiment_a')}"
    os.makedirs(outdir, exist_ok=True)

    # 1. calibration（独立 seeds）
    cal_offset = cfg.get("scenarios", {}).get("calibration_seed_offset", 1_000_000)
    t0 = time.time()
    seq_model, gen = build_sequence_model(
        cfg, env, per_cause=max(8, min(per_cause, 100)), seed_offset=cal_offset
    )
    print(f"[A] calibration done ({time.time() - t0:.1f}s)")

    def make_runner(option):
        return CounterfactualRunner(
            policy_for=lambda o: ScriptedRouteFollower(o),
            env=env,
            top_k=cc_cfg.get("top_k_causes", 2),
            low_level_window=option,
        )

    runner_rfl = make_runner(cc_cfg.get("low_level_window", 3))
    runner_exhaustive = make_runner(10**6)  # CF-only 全窗口

    log_path = os.path.join(outdir, "episodes.jsonl")
    events_path = os.path.join(outdir, "events.jsonl.gz")
    logger = EpisodeLogger(log_path, events_path)
    run_id = f"A-{exp.get('name', 'experiment_a')}-{time.strftime('%Y%m%d-%H%M%S')}"

    seed_rows = []
    t_start = time.time()
    for seed_idx in range(n_seeds):
        base = seed_base + seed_idx * 10000
        # 2. 生成场景（H/L/E 各 per_cause 条）
        samples = []
        for c in CAUSES:
            samples.extend(gen.generate(c, base_seed=base + {"H": 0, "L": 100, "E": 200}[c], n=per_cause))

        # 3. feedback 条件循环（同一 trace 上配对）
        for cond in conditions:
            p_false = 0.0 if cond == "clean" else exp.get("feedback", {}).get("p_false_symmetric", 0.4)
            mode = "symmetric" if cond != "clean" else "symmetric"
            injector = FeedbackInjector(
                p_false=p_false, mode=mode,
                rng=np.random.RandomState(base + {"clean": 1, "symmetric": 2}[cond]),
            )
            for algo_name in algos:
                algo = ALGORITHMS[algo_name]()
                runner = runner_exhaustive if algo_name == "cf_only" else runner_rfl
                agg = {
                    "ae": [], "wur": [], "coverage": [], "wrong_update": [],
                    "ffcr": [], "cf_transitions": [], "abstention": 0,
                }
                n_false_fb = 0
                for s in samples:
                    trace = s.trace
                    oracle_r = s.oracle.responsibility
                    primary = s.oracle.primary
                    observed = injector.generate(primary)
                    is_false = injector.is_false(observed, primary)
                    outcome = algo.attribute(trace, observed, seq_model, runner)
                    metrics = compute_attribution_metrics(
                        responsibility=outcome.responsibility,
                        oracle_r=oracle_r,
                        proposed_update_mass=outcome.proposed_update_mass,
                        observed_feedback=observed,
                        feedback_is_false=is_false,
                        cf_transitions=outcome.cf_transitions,
                    )
                    if is_false:
                        n_false_fb += 1
                    if metrics.attribution_error is not None:
                        agg["ae"].append(metrics.attribution_error)
                    if metrics.wur is not None:
                        agg["wur"].append(metrics.wur)
                    if metrics.update_coverage is not None:
                        agg["coverage"].append(1.0 if metrics.update_coverage else 0.0)
                    if metrics.wrong_update is not None:
                        agg["wrong_update"].append(1.0 if metrics.wrong_update else 0.0)
                    if metrics.false_feedback_compliance is not None:
                        agg["ffcr"].append(1.0 if metrics.false_feedback_compliance else 0.0)
                    agg["cf_transitions"].append(metrics.cf_transitions)
                    if metrics.abstention:
                        agg["abstention"] += 1

                    learner = {
                        "q_seq": outcome.info.get("q_seq", {}),
                        "G": outcome.info.get("G", {}),
                        "q_pre": outcome.info.get("q_pre", {}),
                        "cf_checked": outcome.info.get("cf_checked", []),
                        "cf_delta": outcome.info.get("cf_delta", {}),
                        "responsibility": outcome.responsibility or {},
                        "rho_high": (
                            -outcome.responsibility["H"] if outcome.responsibility else None
                        ),
                        "rho_low": (
                            -outcome.responsibility["L"] if outcome.responsibility else None
                        ),
                    }
                    rec = build_episode_record(
                        run_id=run_id,
                        schema_version="0.1.0",
                        seed=s.seed,
                        scenario_id=s.scenario_id,
                        experiment="A",
                        algorithm=algo_name,
                        condition=cond,
                        trace=trace,
                        observed_feedback=observed,
                        feedback_is_false=is_false,
                        learner=learner,
                        evaluator_only={
                            "oracle_primary": primary,
                            "oracle_R": oracle_r,
                            "oracle_delta": s.oracle.delta_pos,
                        },
                        metrics={
                            "attribution_l1": metrics.attribution_error,
                            "wur": metrics.wur,
                            "wrong_update": metrics.wrong_update,
                            "update_coverage": metrics.update_coverage,
                            "abstention": metrics.abstention,
                            "false_feedback_compliance": metrics.false_feedback_compliance,
                        },
                        compute={
                            "real_transitions": trace.n_transitions,
                            "cf_transitions": metrics.cf_transitions,
                        },
                    )
                    logger.write_episode(rec)
                    logger.write_events(
                        {"scenario_id": s.scenario_id, "seed": s.seed,
                         "tokens": trace.tokens, "feedback": observed}
                    )

                n = len(samples)
                seed_rows.append({
                    "run_id": run_id,
                    "seed_idx": seed_idx,
                    "condition": cond,
                    "algorithm": algo_name,
                    "n_scenarios": n,
                    "ae_mean": float(np.mean(agg["ae"])) if agg["ae"] else None,
                    "ae_sd": float(np.std(agg["ae"], ddof=1)) if len(agg["ae"]) > 1 else 0.0,
                    "wur_mean": float(np.mean(agg["wur"])) if agg["wur"] else None,
                    "wur_sd": float(np.std(agg["wur"], ddof=1)) if len(agg["wur"]) > 1 else 0.0,
                    "coverage": float(np.mean(agg["coverage"])) if agg["coverage"] else None,
                    "wrong_update_rate": float(np.mean(agg["wrong_update"])) if agg["wrong_update"] else None,
                    "ffcr": float(np.mean(agg["ffcr"])) if agg["ffcr"] else None,
                    "abstention_rate": agg["abstention"] / n,
                    "cf_transitions_mean": float(np.mean(agg["cf_transitions"])),
                    "n_false_feedback": n_false_fb,
                })
        print(f"[A] seed {seed_idx} done ({time.time() - t_start:.1f}s)")

    logger.close()

    import csv
    csv_path = os.path.join(outdir, "seed_metrics.csv")
    new_file = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(seed_rows[0].keys()))
        if new_file:
            w.writeheader()
        w.writerows(seed_rows)
    print(f"[A] appended {len(seed_rows)} seed-rows -> {csv_path}")

    # smoke 验收：AE/WUR 必须真实非零（不允许全部为 0 的伪装）
    if args.smoke:
        assert any(r["ae_mean"] not in (None, 0.0) for r in seed_rows), "AE all zero!"
        assert any(r["wur_mean"] not in (None, 0.0) for r in seed_rows), "WUR all zero!"
    print(f"[A] done in {time.time() - t_start:.1f}s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--config", default="configs/smoke.yaml")
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--per-cause", type=int, default=None)
    ap.add_argument("--seed-base", type=int, default=None)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    run_experiment_a(cfg, args)


if __name__ == "__main__":
    main()
