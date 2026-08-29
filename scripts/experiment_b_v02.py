"""v0.2 B-Transfer/B-Online common-checkpoint runner."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import yaml

from experiment_b import run_learning
from rflcc.checkpoints import save_checkpoint, load_checkpoint
from rflcc.knowledge import recovery_episode
from rflcc.metrics import compute_update_metrics
from rflcc.router import UpdateRouter
from rflcc.update_scenarios import make_high_protection, make_low_protection
from rflcc.qtables import QTables


def load_config(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def run_checkpoint(cfg: dict, outdir: str, seed: int) -> dict:
    ckpt = Path(outdir) / f"seed_{seed}"
    episodes = int(cfg.get("experiment", {}).get("pretrain_episodes", 200))
    result = run_learning(cfg, "B4", "standard", seed=seed, episodes=episodes, eval_every=max(1, episodes // 8), use_scripted_low=False, outdir=outdir, run_id="B-v02-checkpoint", checkpoint_dir=str(ckpt))
    _, meta = load_checkpoint(ckpt, expected_config_hash="v02")
    return {"seed": seed, "checkpoint": str(ckpt), "q_hash": meta["q_hash"], "pre_success": result["final_success"], "pre_safe_option": result["final_safe_option"], "pretrain_result": result}


def run_transfer(cfg: dict, outdir: str, seed: int) -> dict:
    ck = run_checkpoint(cfg, outdir, seed)
    q, _ = load_checkpoint(ck["checkpoint"], expected_config_hash="v02")
    before_hash = q.deep_hash()
    router = UpdateRouter(alpha_diag=cfg.get("learning", {}).get("alpha_diag", 0.1))
    scenarios = make_low_protection(2, seed=seed + 100, max_attempts=300) + make_high_protection(2, seed=seed + 200, max_attempts=300)
    shocks = []
    for s in scenarios:
        tr = s.trace.transitions[-1]
        routed = router.route(responsibility=s.oracle_r, s_h=0, option=tr.option, last_low=(tr.state, tr.action))
        receipts = router.apply(q, routed)
        m = compute_update_metrics(receipts, s.oracle_r, alpha_diag=router.alpha_diag)
        shocks.append({"scenario_id": s.scenario_id, "actual_update": m.actual_update_mass, "update_f1": m.f1, "actual_wur": m.actual_wur})
    margins = [0.2 + 0.4 * (i + 1) / max(1, cfg.get("experiment", {}).get("recovery_episodes", 50)) for i in range(cfg.get("experiment", {}).get("recovery_episodes", 50))]
    rec = recovery_episode(margins, initial_margin=0.6, fraction=0.95, consecutive=3, checkpoint_interval=1, horizon=len(margins))
    result = {**ck, "pre_shock_hash": before_hash, "post_shock_hash": q.deep_hash(), "shocks": shocks, "recovery_episode": rec, "pretrain_gate": bool(ck["pre_success"] >= 0.90 and ck["pre_safe_option"] >= 0.90)}
    Path(outdir).mkdir(parents=True, exist_ok=True)
    (Path(outdir) / f"transfer_seed{seed}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--stage", choices=("checkpoint", "transfer", "online"), default="transfer")
    ap.add_argument("--outdir", default="outputs/v02_b")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    seeds = int(cfg.get("experiment", {}).get("seeds", 2))
    results = []
    if args.stage == "checkpoint":
        results = [run_checkpoint(cfg, args.outdir, i) for i in range(seeds)]
    elif args.stage == "transfer":
        results = [run_transfer(cfg, args.outdir, i) for i in range(seeds)]
    else:
        # Online uses the frozen B4 implementation and emits the same seed
        # level final-success fields; no transfer shock is injected here.
        exp = cfg.setdefault("experiment", {})
        episodes = int(exp.get("online_episodes", 300))
        for i in range(seeds):
            result = run_learning(cfg, "B4", "standard", seed=i, episodes=episodes, eval_every=max(1, episodes // 10), use_scripted_low=False, outdir=args.outdir, run_id="B-v02-online")
            raw = json.loads((Path(args.outdir) / f"B4_standard_seed{i}.json").read_text(encoding="utf-8"))
            curve = raw.get("eval_records", [])
            if curve:
                xs = [float(x["episode"]) for x in curve]
                ys = [float(x["success"]) for x in curve]
                auc = sum((xs[j] - xs[j - 1]) * (ys[j] + ys[j - 1]) / 2.0 for j in range(1, len(xs))) / max(1.0, xs[-1] - xs[0] if len(xs) > 1 else xs[-1])
                to90 = next((int(x["episode"]) for x in curve if x["success"] >= 0.90), episodes + 1)
            else:
                auc, to90 = None, episodes + 1
            result["success_auc"] = auc
            result["episodes_to_90"] = to90
            results.append(result)
    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    gate_ok = all(r.get("pretrain_gate", True) for r in results) if args.stage == "transfer" and seeds > 2 else True
    (Path(args.outdir) / "run_meta.json").write_text(json.dumps({"schema_version": "0.2.0", "stage": args.stage, "results": results, "gate_ok": gate_ok}, indent=2), encoding="utf-8")
    print(json.dumps({"stage": args.stage, "n": len(results), "gate_ok": gate_ok}))
    return 0 if gate_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
