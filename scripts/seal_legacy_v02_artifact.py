"""Attach immutable-status metadata to a retained historical v0.2 artifact."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal(path: Path) -> dict:
    raw_files = sorted(
        item for item in path.rglob("*")
        if item.is_file() and item.name not in {"STATUS.json", "ARTIFACT_SHA256.csv"}
    )
    with (path / "ARTIFACT_SHA256.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("relative_path", "sha256", "bytes"))
        writer.writeheader()
        for item in raw_files:
            writer.writerow({
                "relative_path": item.relative_to(path).as_posix(),
                "sha256": _sha256(item),
                "bytes": item.stat().st_size,
            })
    status = {
        "study_version": "0.2",
        "artifact_schema_version": "0.2.1",
        "raw_artifact_commit": "478d38c682371940e2f7093399d59b714dfad223",
        "experiment_software_commit": "7f35c4542bc693f58928644116218150e1e62881",
        "analysis_software_commit": "d77a51207cf16f47496b2e43ce0a99aeca742c8b",
        "config_file_sha256": "a3395769db938fc3f631f89bba274beddac455883359b51c992212d09ec4432e",
        "config_canonical_sha256": "6944ef632b5c61393a71e0d83a055937342efbcc49f0dd8b8b65ccf9dd0dff3d",
        "pilot_execution_status": "completed",
        "primary_gate_status": "invalid_measurement",
        "invalid_primary_endpoint": "H-L",
        "invalid_reason": "invalid_probe_semantics: false low-level last action was treated as correct knowledge",
        "confirmatory_status": "blocked_not_run",
        "claim_status": "full_chain_not_supported",
        "sha256_manifest": "ARTIFACT_SHA256.csv",
        "raw_file_count": len(raw_files),
    }
    (path / "STATUS.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="seal historical v0.2 raw evidence without changing it")
    parser.add_argument("--artifact-dir", required=True)
    args = parser.parse_args(argv)
    path = Path(args.artifact_dir).resolve()
    if not path.is_dir():
        parser.error(f"artifact directory does not exist: {path}")
    print(json.dumps(seal(path), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
