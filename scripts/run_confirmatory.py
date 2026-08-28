"""50-seed confirmatory runner（S12）。

- 参数冻结：config hash + git commit hash 记录；工作区 dirty 拒绝运行
- 全新 confirmatory seeds（与 pilot 隔离）
- resume：已完成 seed 跳过，不重复不覆盖
- 输出 raw JSONL + seed-level CSV

用法：
    python scripts/run_confirmatory.py --experiment A
    python scripts/run_confirmatory.py --experiment B --stage B3 --algo full_rfl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def config_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def git_info() -> dict:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip())
    except Exception:
        commit, dirty = "unknown", True
    return {"commit": commit, "dirty": dirty}


def done_seeds(outdir: str, experiment: str, stage: str, algo: str) -> set[int]:
    done = set()
    prefix = f"{experiment}_" if experiment == "A" else f"{stage}_{algo}_seed"
    if not os.path.isdir(outdir):
        return done
    for fn in os.listdir(outdir):
        if fn.startswith(prefix) and fn.endswith(".json"):
            try:
                done.add(int(fn[len(prefix): fn.index(".json")]))
            except ValueError:
                pass
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", choices=["A", "B"], required=True)
    ap.add_argument("--stage", default=None)
    ap.add_argument("--algo", default="full_rfl")
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--force-dirty", action="store_true")
    args = ap.parse_args()

    # 参数冻结与工作区检查
    if args.experiment == "A":
        cfg_path = os.path.join(ROOT, "configs", "confirmatory_a.yaml")
        outdir = os.path.join(ROOT, "outputs", "confirmatory_a")
        seed_base = yaml.safe_load(open(cfg_path))["experiment"]["confirmatory_seed_base"]
    else:
        cfg_path = os.path.join(ROOT, "configs", "confirmatory_b.yaml")
        outdir = os.path.join(ROOT, "outputs", "confirmatory_b")
        seed_base = yaml.safe_load(open(cfg_path))["experiment"]["confirmatory_seed_base"]

    info = git_info()
    if info["dirty"] and not args.force_dirty:
        print("[confirmatory] REFUSE: working tree is dirty (参数冻结要求干净工作区)")
        print("[confirmatory] 使用 --force-dirty 以确认后继续")
        sys.exit(1)

    os.makedirs(outdir, exist_ok=True)
    meta = {
        "experiment": args.experiment,
        "config": cfg_path,
        "config_hash": config_hash(cfg_path),
        "git_commit": info["commit"],
        "seed_base": seed_base,
        "n_seeds": args.seeds,
        "timestamp": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
    }
    meta_path = os.path.join(outdir, "confirmatory_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[confirmatory] meta -> {meta_path}  config_hash={meta['config_hash']}")

    done = done_seeds(outdir, args.experiment, args.stage or "", args.algo)
    py = sys.executable
    for seed_idx in range(args.seeds):
        if seed_idx in done:
            print(f"[confirmatory] seed {seed_idx} already done, skip")
            continue
        env = dict(os.environ)
        if args.experiment == "A":
            cmd = [
                py, os.path.join(ROOT, "scripts", "experiment_a.py"),
                "--seeds", "1", "--per-cause", "30",
                "--seed-base", str(seed_base + seed_idx * 10000),
                "--outdir", outdir,
            ]
        else:
            cmd = [
                py, os.path.join(ROOT, "scripts", "experiment_b.py"),
                "--stage", args.stage, "--pilot",
                "--seeds", "1", "--algo", args.algo,
                "--episodes", str(yaml.safe_load(open(cfg_path))["experiment"]["training_episodes"]),
                "--outdir", outdir,
            ]
        print(f"[confirmatory] seed {seed_idx}: " + " ".join(cmd[-6:]))
        subprocess.run(cmd, cwd=ROOT, env=env, check=True)
        done.add(seed_idx)
    print("[confirmatory] all seeds done")


if __name__ == "__main__":
    main()
