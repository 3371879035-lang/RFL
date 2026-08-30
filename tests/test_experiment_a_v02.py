import json
from pathlib import Path

import yaml

from scripts.experiment_a_v02 import run_update


def _cfg():
    return yaml.safe_load(Path("configs/v02_smoke.yaml").read_text(encoding="utf-8"))


def test_update_stage_clones_q_and_records_actual_receipts(tmp_path):
    rows = run_update(
        _cfg(), outdir=tmp_path, seeds=1, per_type=1, seed_base=31_000,
        algorithms=("standard", "immediate", "full_rfl", "oracle_update"),
    )
    assert len(rows) == 16  # 4 scenario families x 4 algorithms
    for row in rows:
        assert row["q_hash_before"]
        assert row["q_hash_after"]
        applied_mass = sum(abs(x["delta_q"]) for x in row["applied_updates"])
        assert applied_mass == sum(row["actual_update"].values())
    standard = [r for r in rows if r["algorithm"] == "standard"]
    assert all(sum(r["actual_update"].values()) == 0.0 for r in standard)
    records = [json.loads(x) for x in (tmp_path / "episodes.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == len(rows)
    assert all("oracle_R" in r["evaluator_only"] for r in records)
