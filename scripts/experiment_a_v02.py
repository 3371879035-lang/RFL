"""RFL-CausalChase v0.2 Experiment A.

``attribution`` delegates to the frozen v0.1 replication path.  ``update``
is a separate single-diagnostic-write microbenchmark: every algorithm receives
the same cloned Q snapshot; task Q-learning is disabled during shocks.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import yaml

# Support both ``python scripts/experiment_a_v02.py`` and importing the
# module from the test suite.  The former has ``scripts`` on ``sys.path``;
# the latter resolves it as a namespace package.
try:  # pragma: no cover - each branch is exercised in a different entry path
    from .experiment_a import build_sequence_model, run_experiment_a
except ImportError:  # direct script execution
    from experiment_a import build_sequence_model, run_experiment_a
from rflcc.baselines.cf_only import CFOnly
from rflcc.baselines.full_rfl import FullRFL
from rflcc.baselines.immediate import Immediate
from rflcc.baselines.pe_seq import PESeq
from rflcc.counterfactual import CounterfactualRunner
from rflcc.env import CausalChaseEnv
from rflcc.knowledge import correct_knowledge_damage, wrong_knowledge_reinforcement
from rflcc.logging_io import EpisodeLogger, build_episode_record
from rflcc.metrics import compute_attribution_metrics, compute_update_metrics
from rflcc.policies import ScriptedRouteFollower
from rflcc.router import UpdateRouter
from rflcc.update_scenarios import (
    make_environment_mixed,
    make_high_protection,
    make_hl_mixed,
    make_low_protection,
)


ALL_ALGORITHMS = (
    "standard", "immediate", "er5", "pe_seq", "cf_only", "full_rfl",
    "rfl_observe", "oracle_update", "full_rfl_cfcritical",
)

ARTIFACT_SCHEMA_VERSION = "0.2.1"


def load_config(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _config_hash(cfg: dict) -> str:
    payload = json.dumps(cfg, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _environment(cfg: dict) -> CausalChaseEnv:
    env = cfg["environment"]
    return CausalChaseEnv(
        horizon=env["horizon"],
        monster_move_period=env["monster_move_period"],
        monster_dash_p=env["monster_dash_p"],
        rewards=env.get("rewards"),
    )


def _runners(cfg: dict, env: CausalChaseEnv) -> tuple[CounterfactualRunner, CounterfactualRunner]:
    cc = cfg["counterfactual"]
    policy_for = lambda option: ScriptedRouteFollower(option)
    return (
        CounterfactualRunner(
            policy_for=policy_for, env=env,
            top_k=cc.get("top_k_causes", 2),
            low_level_window=cc.get("low_level_window", 3),
        ),
        CounterfactualRunner(policy_for=policy_for, env=env, top_k=3, low_level_window=10**6),
    )


def _algorithm_outcome(name, trace, feedback, seq_model, runner, exhaustive_runner):
    """Learner-side attribution; oracle labels are deliberately absent."""
    if name == "standard":
        return None
    if name in ("immediate", "er5"):
        return Immediate().attribute(trace, feedback, None, None)
    if name == "pe_seq":
        return PESeq().attribute(trace, feedback, seq_model, None)
    if name == "cf_only":
        return CFOnly().attribute(trace, feedback, seq_model, exhaustive_runner)
    if name in ("full_rfl", "rfl_observe", "full_rfl_cfcritical"):
        return FullRFL().attribute(trace, feedback, seq_model, runner)
    raise ValueError(f"unsupported learner algorithm: {name}")


def _critical_low_site(trace, runner: CounterfactualRunner) -> tuple | None:
    checked = runner.verify(trace, candidates=["L"])
    if checked.critical_low_t is None:
        return None
    tr = trace.transitions[checked.critical_low_t]
    return tr.state, tr.action


def _scenario_batches(per_type: int, seed: int):
    makers = {
        "high_protection": make_high_protection,
        "low_protection": make_low_protection,
        "environment_mixed": make_environment_mixed,
        "hl_mixed": make_hl_mixed,
    }
    offsets = {"high_protection": 0, "low_protection": 100, "environment_mixed": 200, "hl_mixed": 300}
    for name, maker in makers.items():
        for scenario in maker(per_type, seed=seed + offsets[name], max_attempts=300):
            yield name, scenario


def _knowledge(before_h, after_h, before_l, after_l, scenario, scenario_type: str) -> dict[str, float]:
    """Measure the protected item declared by the accepted scenario.

    High-protection shocks have a known-good high option as their primary
    endpoint; low-protection shocks analogously protect the declared low
    action.  Mixed shocks retain both components, weighted by the evaluator's
    *internal* H/L mass.  This avoids diluting a high-protection effect with an
    unrelated faulty L action merely because both tables are present.
    """
    high_correct = scenario.correct_items["H"][1]
    high_wrong = scenario.wrong_items["H"][1]
    low_correct = scenario.correct_items["L"][1]
    low_wrong = scenario.wrong_items["L"][1]
    ckd_h = correct_knowledge_damage(before_h, after_h, high_correct)
    ckd_l = correct_knowledge_damage(before_l, after_l, low_correct)
    wkr_h = wrong_knowledge_reinforcement(before_h, after_h, high_correct, high_wrong)
    wkr_l = wrong_knowledge_reinforcement(before_l, after_l, low_correct, low_wrong)
    if scenario_type == "high_protection":
        weights = {"H": 1.0, "L": 0.0}
        primary_module = "H"
    elif scenario_type == "low_protection":
        weights = {"H": 0.0, "L": 1.0}
        primary_module = "L"
    else:
        internal = scenario.oracle_r.get("H", 0.0) + scenario.oracle_r.get("L", 0.0)
        weights = (
            {"H": scenario.oracle_r.get("H", 0.0) / internal, "L": scenario.oracle_r.get("L", 0.0) / internal}
            if internal > 0.0 else {"H": 0.5, "L": 0.5}
        )
        primary_module = "mixed"
    return {
        "ckd_h": ckd_h, "ckd_l": ckd_l, "wkr_h": wkr_h, "wkr_l": wkr_l,
        "knowledge_weights": weights, "knowledge_primary_module": primary_module,
        "correct_knowledge_damage": weights["H"] * ckd_h + weights["L"] * ckd_l,
        "wrong_knowledge_reinforcement": weights["H"] * wkr_h + weights["L"] * wkr_l,
    }


def _write_seed_summary(rows: list[dict], path: Path) -> None:
    groups: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["seed"], row["algorithm"])].append(row)
    fields = ["seed", "algorithm", "n", "ae_mean", "wur_mean", "f1_mean", "ckd_mean", "wkr_mean", "actual_wur_mean", "cf_transitions_mean"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for (seed, algorithm), values in sorted(groups.items()):
            def avg(key):
                xs = [float(row[key]) for row in values if row.get(key) is not None]
                return sum(xs) / len(xs) if xs else None
            writer.writerow({
                "seed": seed, "algorithm": algorithm, "n": len(values),
                "ae_mean": avg("attribution_error"), "wur_mean": avg("wur"),
                "f1_mean": avg("update_f1"), "ckd_mean": avg("correct_knowledge_damage"),
                "wkr_mean": avg("wrong_knowledge_reinforcement"),
                "actual_wur_mean": avg("actual_wur"), "cf_transitions_mean": avg("cf_transitions"),
            })


def run_update(cfg: dict, *, outdir: str | Path, seeds: int, per_type: int, seed_base: int, algorithms=None) -> list[dict]:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    algorithms = tuple(algorithms or cfg["experiment"].get("algorithms", ALL_ALGORITHMS))
    unknown = set(algorithms) - set(ALL_ALGORITHMS)
    if unknown:
        raise ValueError(f"unsupported algorithms: {sorted(unknown)}")

    env = _environment(cfg)
    seq_model, _ = build_sequence_model(
        cfg, env, max(5, per_type),
        cfg.get("scenarios", {}).get("calibration_seed_offset", 1_000_000),
    )
    runner, exhaustive_runner = _runners(cfg, env)
    alpha_diag = float(cfg["learning"]["alpha_diag"])
    logger = EpisodeLogger(str(outdir / "episodes.jsonl"))
    rows = []

    for seed_idx in range(seeds):
        for scenario_type, scenario in _scenario_batches(per_type, seed_base + seed_idx * 10000):
            trace = scenario.trace
            pre_hash = scenario.q_snapshot.deep_hash()
            tr = trace.transitions[-1]
            for algorithm in algorithms:
                q = scenario.q_snapshot.copy()
                if q.deep_hash() != pre_hash:
                    raise AssertionError("algorithms must receive identical Q snapshots")
                before_h = {0: q.high_get(0, 0), 1: q.high_get(0, 1)}
                before_l = {a: q.low_get(tr.state, a) for a in range(q.n_actions)}
                is_oracle_upper = algorithm == "oracle_update"
                if is_oracle_upper:
                    responsibility, outcome, cf_cost = dict(scenario.oracle_r), None, 0
                else:
                    outcome = _algorithm_outcome(algorithm, trace, scenario.feedback, seq_model, runner, exhaustive_runner)
                    responsibility = None if outcome is None else outcome.responsibility
                    cf_cost = 0 if outcome is None else outcome.cf_transitions

                receipts = []
                if algorithm not in ("standard", "rfl_observe") and responsibility is not None:
                    critical = _critical_low_site(trace, runner) if algorithm == "full_rfl_cfcritical" else None
                    router = UpdateRouter(alpha_diag=alpha_diag, use_cf_critical=(algorithm == "full_rfl_cfcritical"))
                    routed = router.route(
                        responsibility=responsibility, s_h=0, option=trace.option,
                        last_low=(tr.state, tr.action), critical_low=critical,
                    )
                    receipts = router.apply(q, routed)
                after_h = {0: q.high_get(0, 0), 1: q.high_get(0, 1)}
                after_l = {a: q.low_get(tr.state, a) for a in range(q.n_actions)}
                update = compute_update_metrics(receipts, scenario.oracle_r, alpha_diag=alpha_diag)
                attr = compute_attribution_metrics(
                    responsibility=responsibility, oracle_r=scenario.oracle_r,
                    proposed_update_mass=update.actual_update_mass,
                    observed_feedback=scenario.feedback,
                    feedback_is_false=(scenario.feedback != trace.true_primary),
                    cf_transitions=cf_cost,
                )
                knowledge = _knowledge(before_h, after_h, before_l, after_l, scenario, scenario_type)
                applied = [asdict(receipt) for receipt in receipts]
                if abs(sum(abs(x["delta_q"]) for x in applied) - sum(update.actual_update_mass.values())) > 1e-12:
                    raise AssertionError("receipt mass mismatch")
                info = {} if outcome is None else outcome.info
                high_correct, high_wrong = scenario.correct_items["H"][1], scenario.wrong_items["H"][1]
                low_correct, low_wrong = scenario.correct_items["L"][1], scenario.wrong_items["L"][1]
                low_competitors_before = [v for a, v in before_l.items() if a != low_correct]
                low_competitors_after = [v for a, v in after_l.items() if a != low_correct]
                learner_responsibility = {} if is_oracle_upper else (responsibility or {})
                learner = {
                    "q_seq": info.get("q_seq", {}), "G": info.get("G", {}),
                    "q_pre": info.get("q_pre", {}), "cf_checked": info.get("cf_checked", []),
                    "cf_delta": info.get("cf_delta", {}), "responsibility": learner_responsibility,
                    "rho_high": None if is_oracle_upper else -alpha_diag * float((responsibility or {}).get("H", 0.0)),
                    "rho_low": None if is_oracle_upper else -alpha_diag * float((responsibility or {}).get("L", 0.0)),
                    "q_margin_before": (
                        before_h[high_correct] - before_h[high_wrong]
                        if knowledge["knowledge_primary_module"] == "H"
                        else before_l[low_correct] - max(low_competitors_before)
                        if knowledge["knowledge_primary_module"] == "L"
                        else min(before_h[high_correct] - before_h[high_wrong], before_l[low_correct] - max(low_competitors_before))
                    ),
                    "q_margin_after": (
                        after_h[high_correct] - after_h[high_wrong]
                        if knowledge["knowledge_primary_module"] == "H"
                        else after_l[low_correct] - max(low_competitors_after)
                        if knowledge["knowledge_primary_module"] == "L"
                        else min(after_h[high_correct] - after_h[high_wrong], after_l[low_correct] - max(low_competitors_after))
                    ),
                    "actual_update": update.actual_update_mass,
                    "update_precision": update.precision, "update_recall": update.recall,
                    "update_f1": update.f1,
                    "correct_knowledge_damage": knowledge["correct_knowledge_damage"],
                    "wrong_knowledge_reinforcement": knowledge["wrong_knowledge_reinforcement"],
                    "recovery_episode": None,
                }
                metrics = {
                    "attribution_error": attr.attribution_error, "wur": attr.wur,
                    "actual_update": update.actual_update_mass, "applied_updates": applied,
                    "update_precision": update.precision, "update_recall": update.recall,
                    "update_f1": update.f1, "actual_wur": update.actual_wur,
                    **knowledge, "cf_transitions": cf_cost,
                    "q_hash_before": pre_hash, "q_hash_after": q.deep_hash(),
                    "oracle_update_upper_bound": is_oracle_upper,
                }
                logger.write_episode(build_episode_record(
                    run_id="A-v02-update", schema_version=ARTIFACT_SCHEMA_VERSION, seed=trace.seed,
                    scenario_id=scenario.scenario_id, experiment="A-update", algorithm=algorithm,
                    condition=scenario_type, trace=trace, observed_feedback=scenario.feedback,
                    feedback_is_false=(scenario.feedback != trace.true_primary), learner=learner,
                    evaluator_only={"oracle_primary": trace.true_primary, "oracle_R": scenario.oracle_r, "oracle_delta": {}},
                    metrics=metrics,
                    compute={"real_transitions": trace.n_transitions, "cf_transitions": cf_cost},
                ))
                rows.append({
                    "seed": seed_idx, "scenario_id": scenario.scenario_id,
                    "scenario_type": scenario_type, "algorithm": algorithm,
                    "q_hash_before": pre_hash, "q_hash_after": q.deep_hash(),
                    "learner": {"responsibility": learner_responsibility},
                    "evaluator_only": {
                        "oracle_R": scenario.oracle_r,
                        "oracle_update_upper_bound": is_oracle_upper,
                    },
                    "actual_update": update.actual_update_mass, "applied_updates": applied,
                    **metrics,
                })
    logger.close()
    with (outdir / "update_rows.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    _write_seed_summary(rows, outdir / "update_seed_metrics.csv")
    return rows


def run_attribution(cfg: dict, *, outdir: str | Path, seeds: int, per_cause: int, seed_base: int) -> Path:
    """Frozen v0.1 attribution replication written into a v0.2 directory."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    frozen_cfg = copy.deepcopy(cfg)
    frozen_cfg["experiment"].update({
        "name": "v02_attribution", "seeds": seeds, "pilot_seed_base": seed_base,
        "confirmatory_seed_base": seed_base, "per_cause_traces": per_cause,
        "conditions": ["clean", "symmetric"],
        "feedback": {"p_false_symmetric": 0.40},
        "algorithms": ["immediate", "pe_seq", "cf_only", "full_rfl", "oracle_upper"],
    })
    args = SimpleNamespace(
        per_cause=per_cause, seeds=seeds, seed_base=seed_base,
        outdir=str(outdir), seed_index=0, smoke=False,
    )
    run_experiment_a(frozen_cfg, args)
    return outdir / "seed_metrics.csv"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--stage", choices=("attribution", "update", "all"), default="all")
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--seeds", type=int, default=None)
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    exp = cfg["experiment"]
    seeds = int(args.seeds if args.seeds is not None else exp["seeds"])
    outdir = Path(args.outdir or f"outputs/v02_{exp['name']}_a")
    meta = {
        "schema_version": ARTIFACT_SCHEMA_VERSION, "stage": args.stage, "seeds": seeds,
        "config_hash": _config_hash(cfg),
        "git_commit": os.popen("git rev-parse HEAD").read().strip(),
        "timestamp": time.time(),
    }
    if args.stage in ("attribution", "all"):
        run_attribution(cfg, outdir=outdir / "attribution", seeds=seeds,
                        per_cause=int(exp["attribution_per_cause"]), seed_base=int(exp["seed_base"]))
    if args.stage in ("update", "all"):
        rows = run_update(cfg, outdir=outdir / "update", seeds=seeds,
                          per_type=int(exp["update_scenarios_per_type"]), seed_base=int(exp["seed_base"]))
        if not rows:
            raise RuntimeError("update stage emitted no rows")
        meta["update_rows"] = len(rows)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
