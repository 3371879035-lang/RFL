"""生成 H/L/E 单原因场景（Experiment A 与 calibration 数据源）。

用法：
    python scripts/generate_scenarios.py --smoke --per-cause 5
    python scripts/generate_scenarios.py --calibration --per-cause 100
    python scripts/generate_scenarios.py --experiment-a --seeds 50 --per-cause 30
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import yaml

from rflcc.env import CausalChaseEnv
from rflcc.scenarios import ScenarioGenerator
from rflcc.types import CAUSES


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--calibration", action="store_true")
    ap.add_argument("--experiment-a", action="store_true")
    ap.add_argument("--config", default="configs/smoke.yaml")
    ap.add_argument("--per-cause", type=int, default=5)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--seed-offset", type=int, default=0)
    ap.add_argument("--outdir", default="outputs/scenarios")
    ap.add_argument("--max-attempts", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    env_cfg = cfg["environment"]
    env = CausalChaseEnv(
        horizon=env_cfg["horizon"],
        monster_move_period=env_cfg["monster_move_period"],
        monster_dash_p=env_cfg["monster_dash_p"],
        rewards=env_cfg.get("rewards"),
    )
    sc = cfg.get("scenarios", {})
    acc = sc.get("acceptance", {})
    gen = ScenarioGenerator(
        env=env,
        delta_target_pos=acc.get("delta_target_pos", 0.4),
        delta_leak=acc.get("delta_leak", 0.1),
        max_attempts=args.max_attempts or sc.get("search_attempts_per_trace", 120),
    )

    os.makedirs(args.outdir, exist_ok=True)
    manifest = []
    total = 0
    t0 = time.time()
    for seed_idx in range(args.seeds):
        base = args.seed_offset + seed_idx * 10000
        for cause in CAUSES:
            base_seed = base + {"H": 0, "L": 100, "E": 200}[cause]
            samples = gen.generate(cause, base_seed=base_seed, n=args.per_cause)
            for s in samples:
                rec = {
                    "cause": cause,
                    "seed": s.seed,
                    "scenario_id": s.scenario_id,
                    "option": s.trace.option,
                    "terminal_type": s.trace.terminal_type,
                    "n_transitions": s.trace.n_transitions,
                    "delta": {k: round(v, 4) for k, v in s.oracle.delta.items()},
                    "delta_pos": {k: round(v, 4) for k, v in s.oracle.delta_pos.items()},
                    "responsibility": (
                        {k: round(v, 4) for k, v in s.oracle.responsibility.items()}
                        if s.oracle.responsibility
                        else None
                    ),
                    "primary": s.oracle.primary,
                    "attempts_used": s.attempts_used,
                    "fault_t": s.trace.fault_t,
                    "fault_action": s.trace.fault_action,
                    "dash_log": s.trace.env_meta.get("dash_log", []),
                }
                manifest.append(rec)
                total += 1
    dt = time.time() - t0
    out = os.path.join(args.outdir, "experiment_a_manifest.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for rec in manifest:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[scenarios] wrote {total} samples -> {out}  ({dt:.1f}s, "
          f"{total / max(dt, 1e-6):.1f} samples/s)")
    from collections import Counter
    print("[scenarios] per-cause:", dict(Counter(r["cause"] for r in manifest)))


if __name__ == "__main__":
    main()
