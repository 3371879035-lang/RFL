"""Small, reproducible summary for v0.2 JSONL/JSON outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="update_rows.jsonl or a v02 output directory")
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)
    p = Path(args.input)
    rows = []
    files = [p] if p.is_file() else list(p.rglob("update_rows.jsonl"))
    for f in files:
        rows.extend(json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
    summary = {"n_rows": len(rows)}
    if rows:
        for key in ("update_precision", "update_recall", "update_f1", "actual_wur", "correct_knowledge_damage"):
            vals = [float(r[key]) for r in rows if r.get(key) is not None]
            summary[key + "_mean"] = float(np.mean(vals)) if vals else None
        summary["nonzero_actual_updates"] = sum(sum(float(v) for v in r.get("actual_update", {}).values()) > 1e-9 for r in rows)
    out = Path(args.output) if args.output else (p.parent / "analysis_v02.json" if p.is_file() else p / "analysis_v02.json")
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
