"""Throughput calibration, run BEFORE committing to any formal episode budget.

The research plan is explicit: "先跑吞吐率 benchmark，再决定正式 episode 总量",
and warns against promising wall-clock numbers without measuring.  This measures
the real cost of the actual training loop, single-process and across workers,
and then converts that into expected wall-clock for the planned formal budgets.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import yaml

from rflnext.env import HORIZON
from rflnext.noise import NoiseTape
from rflnext.qtables import QTables, linear_epsilon
from rflnext.runner import run_episode

PLANNED = {
    "beta_formal_20_seeds_x_7_cond_x_5000_ep": 20 * 7 * 5000,
    "stage4_formal_30_seeds_x_6_arms_x_5000_ep": 30 * 6 * 5000,
    "stage3_formal_40_seeds_x_4_cells_x_5000_ep": 40 * 4 * 5000,
}


def _worker(args) -> float:
    """Run ``n`` episodes and return episodes/second."""
    seed, n, horizon, p_hazard = args
    tape = NoiseTape.from_seed(seed, episodes=n, horizon=horizon, p_hazard=p_hazard)
    q = QTables(n_actions=4)
    decay = max(1, int(n * 0.8))
    t0 = time.perf_counter()
    for ep in range(n):
        eps = linear_epsilon(ep, start=0.30, end=0.05, decay_episodes=decay)
        run_episode(
            episode=ep, tape=tape, q=q, epsilon=eps, reward_mode="A",
            alpha_low=0.10, alpha_high=0.10,
        )
    return n / (time.perf_counter() - t0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--episodes", type=int, default=10000)
    ap.add_argument("--workers", type=int, default=0, help="0 = cpu_count()-1")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    horizon = int(cfg.get("environment", {}).get("horizon", HORIZON))
    p_hazard = float(cfg.get("environment", {}).get("p_hazard", 0.25))

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # ---- single process -------------------------------------------------
    t0 = time.perf_counter()
    single = _worker((12345, int(args.episodes), horizon, p_hazard))
    single_wall = time.perf_counter() - t0

    # ---- parallel across seeds -----------------------------------------
    workers = int(args.workers) or max(1, (os.cpu_count() or 2) - 1)
    per_worker = max(1, int(args.episodes) // workers)
    parallel = None
    parallel_wall = None
    parallel_error = None
    if workers > 1:
        try:
            from concurrent.futures import ProcessPoolExecutor

            t1 = time.perf_counter()
            with ProcessPoolExecutor(max_workers=workers) as ex:
                rates = list(ex.map(
                    _worker,
                    [(1000 + i, per_worker, horizon, p_hazard) for i in range(workers)],
                ))
            parallel_wall = time.perf_counter() - t1
            # Aggregate throughput is total work over wall time; summing the
            # per-worker rates would overstate it if workers finish unevenly.
            parallel = float(workers * per_worker / max(parallel_wall, 1e-9))
        except Exception as exc:  # pragma: no cover - environment dependent
            parallel_error = f"{type(exc).__name__}: {exc}"

    # The aggregate rate is what matters for budgeting: N episodes cost
    # N / aggregate_rate seconds, not N x per-worker time.
    agg = parallel if parallel else single

    report = {
        "episodes_measured": int(args.episodes),
        "horizon": horizon,
        "p_hazard": p_hazard,
        "single_process_episodes_per_s": float(single),
        "single_process_wall_s": float(single_wall),
        "workers": workers,
        "parallel_aggregate_episodes_per_s": float(parallel) if parallel else None,
        "parallel_wall_s": float(parallel_wall) if parallel_wall else None,
        "parallel_error": parallel_error,
        "speedup": (float(parallel) / float(single)) if parallel else None,
        "aggregate_rate_used_for_budget": float(agg),
        "planned_budgets": {
            name: {
                "episodes": eps,
                "estimated_wall_s": eps / float(agg),
                "estimated_wall_min": eps / float(agg) / 60.0,
            }
            for name, eps in PLANNED.items()
        },
        "note": (
            "Estimates cover TRAINING episodes only, not the greedy evaluation "
            "passes, which are roughly comparable in cost."
        ),
    }
    (outdir / "benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"measured {args.episodes} episodes at horizon={horizon}")
    print(f"  single process : {single:,.0f} episodes/s  ({single_wall:.2f}s)")
    if parallel:
        print(f"  {workers} workers   : {parallel:,.0f} episodes/s aggregate "
              f"({parallel_wall:.2f}s, speedup x{parallel/single:.2f})")
    else:
        print(f"  {workers} workers   : unavailable ({parallel_error})")
    print(f"\nbudget, using {agg:,.0f} episodes/s:")
    for name, info in report["planned_budgets"].items():
        print(f"  {name:<44} {info['episodes']:>10,} ep -> "
              f"{info['estimated_wall_min']:>7.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
