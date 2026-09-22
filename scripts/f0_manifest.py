"""Generate the $F_0$ manifest: the instrument fingerprint a reviewer checks.

`docs/rebuild/20-B2-DEV-PROTOCOL-FREEZE.md` declares the development protocol; this script records what
the frozen instrument actually *is* at the moment that protocol is proposed, so that the declaration can
be checked against bytes rather than trusted. Nothing here selects, ranks or measures a candidate: it
hashes sources and reads back digests that earlier gates already produced.

Every read is asserted. A missing key, a failed gate summary or a stale closure commit is an error, never
a silently absent field: the manifest is only useful if a wrong tree cannot produce a well-formed one.

Run:  python scripts/f0_manifest.py --out experiments/v03r/f0_manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: The A89 implementation closure: the commit whose tree the instrument was frozen from.
CLOSURE_COMMIT = "a4451cc"

#: Frozen gate artifacts this protocol leans on, with the invariant each must still satisfy.
GATE_ARTIFACTS = {
    "experiments/v03r/calibration_report.json": "A89 synthetic calibration",
    "experiments/v03r/structural_screening.json": "A86 structural screening",
    "experiments/v03r/b2_view_gate_selfcheck.json": "B2 view gate mutation power",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def source_digests() -> dict:
    """Hash every source file of the frozen instrument, plus one combined tree digest."""
    files = sorted(
        p for p in (ROOT / "src" / "rfl_rebuild").rglob("*.py") if p.is_file()
    )
    assert files, "no instrument sources found under src/rfl_rebuild"
    per_file = {}
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        per_file[rel] = sha256_file(path)
    combined = hashlib.sha256()
    for rel in sorted(per_file):
        combined.update(rel.encode("utf-8"))
        combined.update(b"\0")
        combined.update(per_file[rel].encode("ascii"))
        combined.update(b"\n")
    return {"files": per_file, "tree_digest": combined.hexdigest(), "n_files": len(per_file)}


def read_listing(path: Path) -> str:
    """Decode a captured command listing: PowerShell redirection writes UTF-16, pytest writes UTF-8."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise AssertionError(f"could not decode {path}")


def test_inventory(test_list: Path | None) -> dict:
    """The collected-test fingerprint, when a `pytest --collect-only` listing is supplied.

    Two output shapes are accepted, because pytest's `-q` collect listing is a per-file *count* table here
    while the plain listing is node ids. Node ids are preferred: they pin the inventory, not just its size.
    Every node id's file must exist, so a listing from another tree cannot be fingerprinted as if it
    described this one.
    """
    if test_list is None:
        return {"available": False, "test_list": None}
    text = read_listing(test_list)
    nodes = sorted(
        line.split(" ")[0].strip() for line in text.splitlines() if "::" in line
    )
    if nodes:
        missing = sorted({n.split("::")[0] for n in nodes if not (ROOT / n.split("::")[0]).is_file()})
        assert not missing, f"test listing names files that do not exist: {missing[:3]}"
        digest = hashlib.sha256("\n".join(nodes).encode("utf-8")).hexdigest()
        return {
            "available": True,
            "test_list": test_list.name,
            "format": "node_ids",
            "count": len(nodes),
            "node_id_digest": digest,
        }
    counts = {}
    for line in text.splitlines():
        head, sep, tail = line.rpartition(": ")
        if sep and head.strip() and tail.strip().isdigit():
            counts[head.strip()] = int(tail.strip())
    assert counts, f"no collected tests found in {test_list}"
    listing = "\n".join(f"{k}: {counts[k]}" for k in sorted(counts))
    return {
        "available": True,
        "test_list": test_list.name,
        "format": "per_file_counts",
        "count": sum(counts.values()),
        "node_id_digest": hashlib.sha256(listing.encode("utf-8")).hexdigest(),
    }


def gate_summaries() -> dict:
    """Read back the frozen gate artifacts and assert the invariants this protocol cites."""
    out = {}
    for rel, what in GATE_ARTIFACTS.items():
        path = ROOT / rel
        assert path.is_file(), f"frozen gate artifact missing: {rel}"
        digest = sha256_file(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{rel}: expected a JSON object"
        entry = {"what": what, "file_digest": digest}
        if rel.endswith("calibration_report.json"):
            summary = data["summary"]
            assert summary["cells"] == 18, f"calibration cell count changed: {summary['cells']}"
            assert summary["calibrated"] == 18, f"calibration no longer 18/18: {summary}"
            assert summary["all_agree"] is True, f"calibration agreement lost: {summary}"
            assert data["instrument"]["domains"]["U2"] == 5760, "U2 domain size changed"
            entry["summary"] = {
                "cells": summary["cells"],
                "calibrated": summary["calibrated"],
                "worst_abs_gap": summary["worst_abs_gap"],
            }
            entry["reference_artifact_digest"] = data["instrument"]["reference_artifact_digest"]
        elif rel.endswith("structural_screening.json"):
            cells = data["cells"]
            assert len(cells) == 6, f"expected six screening cells, found {len(cells)}"
            non_rejected = [
                c for c in cells if c["status"] not in {"BLIND", "DIRECTION_FAIL"}
            ]
            assert len(non_rejected) == 5, "screening cell statuses changed"
            verdict = data.get("verdict") or data.get("aggregate") or data.get("aggregate_verdict")
            assert verdict is not None, f"{rel}: no aggregate verdict field found"
            entry["summary"] = {
                "cells": len(cells),
                "non_rejected": len(non_rejected),
                "verdict": verdict,
            }
        elif rel.endswith("b2_view_gate_selfcheck.json"):
            # This artifact reports aggregate counters plus one row per mutation, so the invariant is
            # checked on the counters and the row count is tied back to them: a truncated row list could
            # otherwise carry a healthy-looking summary.
            rows = data["results"]
            assert len(rows) == data["n_mutations"], "gate self-check row count disagrees with its counter"
            n = data["n_mutations"]
            assert data["n_gate_is_real"] == n, "a mutation no longer fails its gate"
            for key in ("n_not_a_gate", "n_node_not_found", "n_harness_error",
                        "n_mutation_not_applied", "n_wrong_failure_reason"):
                assert data[key] == 0, f"{rel}: {key} = {data[key]}, expected 0"
            assert data["tree_restored_byte_identical"] is True, "mutation harness left the tree dirty"
            assert data["stale_node_ids"] == [], f"stale mutation anchors: {data['stale_node_ids'][:3]}"
            entry["summary"] = {
                "mutations": n,
                "gate_is_real": data["n_gate_is_real"],
                "distinct_gates": len({r.get("gate") for r in rows}),
                "tree_restored_byte_identical": True,
            }
        out[rel] = entry
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write the F0 instrument manifest.")
    ap.add_argument("--out", default="experiments/v03r/f0_manifest.json")
    ap.add_argument("--test-list", default=None, type=Path,
                    help="file holding `pytest --collect-only -q` output")
    ap.add_argument("--suite-seconds", type=float, default=None)
    ap.add_argument("--calibration-seconds", type=float, default=None)
    args = ap.parse_args(argv)

    head = git("rev-parse", "HEAD")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", CLOSURE_COMMIT, head],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert ancestor.returncode == 0, (
        f"A89 closure commit {CLOSURE_COMMIT} is not an ancestor of HEAD {head}"
    )

    manifest = {
        "what": "F0 DEV_PROTOCOL_FREEZE instrument manifest",
        "status": "PROPOSED -- F0 is a draft; nothing downstream is authorised",
        "protocol_document": "docs/rebuild/20-B2-DEV-PROTOCOL-FREEZE.md",
        "generator": {
            "script": "scripts/f0_manifest.py",
            "script_digest": sha256_file(Path(__file__).resolve()),
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "repo": {
            "head": head,
            "branch": branch,
            "closure_commit": CLOSURE_COMMIT,
            "closure_is_ancestor": True,
            "dirty_paths": sorted(
                line[3:] for line in git("status", "--porcelain").splitlines() if line.strip()
            ),
        },
        "instrument": source_digests(),
        "gates": gate_summaries(),
        "tests": test_inventory(args.test_list),
        "runtime_reference_seconds": {
            "full_suite": args.suite_seconds,
            "calibration": args.calibration_seconds,
        },
        "authorises": ["smoke5"],
        "not_authorised": [
            "dev32 treatment arms",
            "F1 DEV_DESIGN_LOCK",
            "confirmatory stage",
            "V0.4R seed",
            "N_train",
        ],
    }
    assert manifest["tests"]["available"] or args.test_list is None
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out}")
    print(f"  head            {head} ({branch})")
    print(f"  source files    {manifest['instrument']['n_files']}")
    print(f"  source digest   {manifest['instrument']['tree_digest']}")
    print(f"  tests           {manifest['tests'].get('count')}")
    print(f"  test digest     {manifest['tests'].get('node_id_digest')}")
    for rel, entry in sorted(manifest["gates"].items()):
        print(f"  gate            {rel} {entry.get('summary')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
