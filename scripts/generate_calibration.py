"""生成 calibration 数据并训练 SequenceModel（S04）。

用法：
    python scripts/generate_calibration.py --smoke --per-cause 10
    python scripts/generate_calibration.py --per-cause 100

输出：outputs/calibration/sequence_{H,L,E,background}.npy + manifest。
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

from rflcc.env import CausalChaseEnv
from rflcc.scenarios import ScenarioGenerator
from rflcc.sequence import SequenceModel
from rflcc.types import CAUSES


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--config", default="configs/smoke.yaml")
    ap.add_argument("--per-cause", type=int, default=100)
    ap.add_argument("--seed-offset", type=int, default=1_000_000)
    ap.add_argument("--outdir", default="outputs/calibration")
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
    seq_cfg = cfg["sequence"]
    model = SequenceModel(
        beta=seq_cfg.get("beta_prior", 1.0),
        probability_floor=seq_cfg.get("probability_floor", 0.01),
        eta=seq_cfg.get("adjacent_weight_eta", 0.5),
        tau_seq=seq_cfg.get("temperature", 0.5),
    )

    traces: dict[str, list] = {c: [] for c in CAUSES}
    t0 = time.time()
    for cause in CAUSES:
        base = args.seed_offset + {"H": 0, "L": 100, "E": 200}[cause]
        samples = gen.generate(cause, base_seed=base, n=args.per_cause)
        for s in samples:
            traces[cause].append(s.trace)

    model.calibrate(traces)
    os.makedirs(args.outdir, exist_ok=True)
    for c in CAUSES:
        np.save(os.path.join(args.outdir, f"sequence_{c}.npy"), model._A[c])
    np.save(os.path.join(args.outdir, "sequence_background.npy"), model._bg_A)
    manifest = [
        {"cause": c, "n": len(traces[c]), "seed_base": args.seed_offset}
        for c in CAUSES
    ]
    with open(os.path.join(args.outdir, "calibration_manifest.csv"), "w") as f:
        f.write("cause,n,seed_base\n")
        for m in manifest:
            f.write(f"{m['cause']},{m['n']},{m['seed_base']}\n")
    print(f"[calibration] {sum(len(v) for v in traces.values())} traces, "
          f"{time.time() - t0:.1f}s -> {args.outdir}")

    # 快速自检：校准后模型应能区分 H/L 模板
    for c in CAUSES:
        s = traces[c][0]
        r = model.score(s)
        top = max(r.q_seq, key=r.q_seq.get)
        print(f"[calibration] cause={c} q_seq={ {k: round(v, 2) for k, v in r.q_seq.items()} } "
              f"top={top} match={top == c}")
        if top != c:
            print(f"[calibration] WARNING: template {c} not self-consistent")


if __name__ == "__main__":
    main()
