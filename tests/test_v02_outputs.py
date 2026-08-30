"""Artifact-level gates for v0.2 experiments.

These tests check emitted files rather than internal return values so a command
cannot pass merely by calculating metrics in memory and then omitting the
auditable result trail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.capture_v02_reproducibility import capture_reproducibility
from scripts.experiment_a_v02 import run_update
from scripts.experiment_b_v02 import main as experiment_b_main
from scripts.v02_integrity import (
    OutputIntegrityError,
    prepare_fresh_v02_output_dir,
    validate_b_transfer_output,
    validate_v02_update_record,
)


ROOT = Path(__file__).resolve().parents[1]


def _smoke_config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "v02_smoke.yaml").read_text(encoding="utf-8"))


def test_update_records_validate_receipt_mass_and_namespace(tmp_path):
    cfg = _smoke_config()
    rows = run_update(
        cfg,
        outdir=tmp_path / "v02_a_update",
        seeds=1,
        per_type=1,
        seed_base=91_000,
        algorithms=("standard", "immediate", "full_rfl"),
    )
    assert rows
    records = [
        json.loads(line)
        for line in (tmp_path / "v02_a_update" / "episodes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == len(rows)
    for index, record in enumerate(records, start=1):
        validate_v02_update_record(record, context=f"record:{index}")


def test_integrity_rejects_oracle_update_in_learner_namespace(tmp_path):
    cfg = _smoke_config()
    run_update(
        cfg,
        outdir=tmp_path / "v02_oracle_partition",
        seeds=1,
        per_type=1,
        seed_base=92_000,
        algorithms=("immediate",),
    )
    record = json.loads((tmp_path / "v02_oracle_partition" / "episodes.jsonl").read_text(encoding="utf-8").splitlines()[0])
    record["algorithm"] = "oracle_update"
    record["learner"]["responsibility"] = {"H": 1.0, "L": 0.0, "E": 0.0}
    with pytest.raises(OutputIntegrityError, match="Oracle-Update"):
        validate_v02_update_record(record)


def test_transfer_artifacts_are_checked_from_written_files(tmp_path):
    cfg = _smoke_config()
    cfg["experiment"].update({
        "seeds": 1,
        "algorithms": ["standard", "immediate"],
        "pretrain_episodes": 200,
        "shocks": 2,
        "recovery_episodes": 10,
        "recovery_eval_every": 5,
    })
    config_path = tmp_path / "v02_transfer.yaml"
    config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    outdir = tmp_path / "v02_transfer"
    assert experiment_b_main([
        "--config", str(config_path), "--stage", "transfer", "--outdir", str(outdir),
    ]) == 0
    report = validate_b_transfer_output(outdir, cfg)
    assert report == {"transfer_seed_files": 1, "shock_rows": 4}


def test_fresh_output_directory_rejects_existing_artifacts(tmp_path):
    project_root = tmp_path / "project"
    target = project_root / "outputs" / "v02_new"
    created = prepare_fresh_v02_output_dir(target, project_root=project_root)
    assert created == target.resolve()
    (target / "artifact.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(OutputIntegrityError, match="refusing to append"):
        prepare_fresh_v02_output_dir(target, project_root=project_root)
    with pytest.raises(OutputIntegrityError, match="start with 'v02_'"):
        prepare_fresh_v02_output_dir(project_root / "outputs" / "legacy", project_root=project_root)


def test_reproducibility_capture_writes_required_envelope(tmp_path):
    outdir = tmp_path / "v02_reproducibility"
    result = capture_reproducibility(
        outdir,
        project_root=ROOT,
        config_paths=[ROOT / "configs" / "v02_smoke.yaml"],
        stages=("A-update", "B-transfer"),
        benchmark={"test": True},
    )
    assert result["configs"] == 1
    required = {
        "environment.txt", "python_version.txt", "dependency_versions.txt", "git_commit.txt",
        "config_hashes.txt", "seed_manifest.csv", "benchmark.json",
    }
    assert required.issubset({path.name for path in outdir.iterdir()})
    manifest = list(__import__("csv").DictReader((outdir / "seed_manifest.csv").open(encoding="utf-8")))
    assert len(manifest) == 2 * _smoke_config()["experiment"]["seeds"]
    assert {row["status"] for row in manifest} == {"planned"}
