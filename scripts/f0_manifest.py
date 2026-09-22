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


def crlf_artifacts() -> list:
    """Artifacts whose working-tree bytes carry CRLF although `.gitattributes` declares `eol=lf`.

    Recorded, not asserted: these predate this manifest and rewriting them would change working-tree
    bytes that earlier arrows produced. The point of listing them is that a digest taken from such a file
    is a digest of *this checkout* rather than of the committed blob, so nobody quotes one as portable.
    """
    out = []
    for path in sorted((ROOT / "experiments" / "v03r").glob("*.json")):
        if b"\r\n" in path.read_bytes():
            out.append(path.relative_to(ROOT).as_posix())
    return out


def gate_summaries() -> dict:
    """Read back the frozen gate artifacts and assert the invariants this protocol cites."""
    out = {}
    for rel, what in GATE_ARTIFACTS.items():
        path = ROOT / rel
        assert path.is_file(), f"frozen gate artifact missing: {rel}"
        digest = sha256_file(path)
        raw = path.read_bytes()
        assert b"\r\n" not in raw, (
            f"{rel}: the working tree carries CRLF while .gitattributes declares eol=lf, so this digest "
            "would not survive a checkout of the same revision"
        )
        data = json.loads(raw.decode("utf-8"))
        assert isinstance(data, dict), f"{rel}: expected a JSON object"
        entry = {"what": what, "file_digest": digest, "line_endings": "lf"}
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


def dirty_split(out_rel: str, allow_dirty: bool) -> tuple[list, list]:
    """Split the dirty paths into code and evidence, and require the code side to be clean.

    A manifest generated from an uncommitted instrument evidences a working tree, not a revision: the
    reviewer of revision 1 rejected exactly that. Evidence under ``experiments/`` may legitimately be
    regenerated by the gates that produce it, so it is recorded rather than required clean; anything
    else -- sources, scripts, tests, docs -- must be committed, with the single exception of this
    manifest's own output file, which cannot contain the hash of the commit that contains it.

    ``allow_dirty`` exists only so that the mutation self-check can corrupt one input at a time. A
    manifest produced that way is not evidence and says so: it is stamped ``MUTATION-PROBE``, its
    ``execution_revision`` is nulled, and it authorises nothing.
    """
    dirty = sorted(line[3:] for line in git("status", "--porcelain").splitlines() if line.strip())
    code = [p for p in dirty if not p.startswith("experiments/") and p != out_rel]
    evidence = [p for p in dirty if p.startswith("experiments/")]
    if not allow_dirty:
        assert not code, (
            "the instrument is dirty, so this manifest would pin a working tree rather than a revision: "
            f"{code[:5]} -- commit the code, then regenerate"
        )
    return code, evidence


def harness_digests() -> dict:
    """Fingerprint the run harness and the declared seed files, not just the library."""
    groups = {
        "run_scripts": sorted((ROOT / "scripts").glob("run_*.py")),
        "seed_files": sorted((ROOT / "experiments" / "v03r").glob("*_seeds.txt")),
    }
    out = {}
    for name, paths in groups.items():
        files = {}
        for path in paths:
            if path.is_file():
                files[path.relative_to(ROOT).as_posix()] = sha256_file(path)
        combined = hashlib.sha256()
        for rel in sorted(files):
            combined.update(rel.encode("utf-8"))
            combined.update(b"\0")
            combined.update(files[rel].encode("ascii"))
            combined.update(b"\n")
        out[name] = {
            "files": files,
            "tree_digest": combined.hexdigest(),
            "n_files": len(files),
            "digest_scope": "sorted (path, sha256) pairs, so the value is stable across checkouts",
        }
    assert out["run_scripts"]["n_files"] >= 3, (
        "the three run scripts of F0 section 7 are part of the frozen command surface and must exist"
    )
    return out


#: F0 section 2: the N_eval candidate universe. N_max = max(...) is the master sample size.
N_EVAL_CANDIDATES = (100, 256, 512, 1024)


def eval_sample() -> dict:
    """Fingerprint the master evaluation-scene sample of F0 section 3 and assert its frozen order.

    F0 section 3 defines the evaluation sample as the first N_max elements of the frozen U2 enumeration,
    so the claim "the first N scenes" is only well-defined if that enumeration has one order and one
    representation. The instrument carries two -- `scene_domain()` returns typed ``EvaluationScene``s and
    `u2_domain()` returns raw keys -- so this asserts that they agree element-wise and that both are
    monotone in A88 section 76.2's lexicographic order, and records the sample's fingerprint. Without
    this, a re-ordering of either enumerator would silently redefine every N_eval candidate.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from rfl_rebuild.b2.screening import u2_domain  # noqa: PLC0415
    from rfl_rebuild.b2.unaffected import scene_domain  # noqa: PLC0415

    keys = [scene.key for scene in scene_domain()]
    projected = [(k, tape.phase, tape.error_flag, tape.cause_rank, base)
                 for (k, tape, base) in u2_domain()]
    assert len(keys) == len(projected) == 5760, (
        f"U2's size changed: scene_domain={len(keys)}, u2_domain={len(projected)}"
    )
    assert projected == keys, (
        "the two frozen enumerations of U2 disagree element-wise, so 'the first N scenes' would name "
        "different sets depending on which one a stage read"
    )
    assert all(keys[i] < keys[i + 1] for i in range(len(keys) - 1)), (
        "the U2 enumeration is not in A88 section 76.2's frozen lexicographic order"
    )
    n_max = max(N_EVAL_CANDIDATES)
    assert n_max <= len(keys), f"N_eval candidate {n_max} exceeds |U2| = {len(keys)}"
    return {
        "definition": ("F0 section 3: the master evaluation sample is the first N_max elements of the "
                       "frozen U2 enumeration; seeds are sample-generation provenance, not unit identity"),
        "domain_size": len(keys),
        "order": "A88 section 76.2 lexicographic on (kappa, phase, error_flag, cause_rank, z_base)",
        "monotone_in_frozen_order": True,
        "representations_agree_elementwise": True,
        "seed_free": True,
        "candidates": list(N_EVAL_CANDIDATES),
        "n_max": n_max,
        "prefix_boundary_keys": {str(n): list(keys[n - 1]) for n in N_EVAL_CANDIDATES},
        "sample_digest_first_n_max": hashlib.sha256(
            repr(tuple(keys[:n_max])).encode("utf-8")
        ).hexdigest(),
    }


def runtime_benchmark() -> dict:
    r"""Measure the seedless workload and derive $F_0$ §8's bounds from it, rather than asserting them.

    $$\boxed{\text{bound} = \max\left(\text{floor},\ \text{multiple} \times \text{seedless
    benchmark}\right)}$$

    The benchmark is seedless by construction (the evaluation sample is a prefix of the frozen $U_2$
    enumeration), so this is the one runtime number in the protocol that can be measured before any
    authorisation. The floors cover what the benchmark does not: interpreter start, the reference solve,
    and the gate re-checks a stage performs around its workload.
    """
    sys.path.insert(0, str(ROOT / "src"))
    from rfl_rebuild.b2 import devstage  # noqa: PLC0415

    measurement = devstage.benchmark_eval_sample()
    assert measurement["seedless"] is True and measurement["draws_no_seed"] is True, (
        "the runtime benchmark drew a seed, so it cannot measure the frozen instrument")
    assert measurement["writes_artifact"] is False, "the benchmark wrote a stage artifact"
    multiple = 100
    floors = {"smoke": 30.0, "dev_baseline": 300.0}
    bounds = {stage: round(max(floor, multiple * measurement["runtime_s"]), 3)
              for stage, floor in floors.items()}
    assert all(bound >= measurement["runtime_s"] for bound in bounds.values())
    return {
        "rule": "bound = max(floor_seconds, multiple * seedless_benchmark_runtime_s)",
        "measurement": measurement,
        "multiple": multiple,
        "floors_seconds": floors,
        "bounds_seconds": bounds,
        "caveat": ("the bound is a smoke criterion, not a target: exceeding it fails smoke, and a stage "
                   "may not meet it by shrinking the work"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write the F0 instrument manifest.")
    ap.add_argument("--out", default="experiments/v03r/f0_manifest.json")
    ap.add_argument("--test-list", default=None, type=Path,
                    help="file holding `pytest --collect-only -q` output")
    ap.add_argument("--suite-seconds", type=float, default=None)
    ap.add_argument("--calibration-seconds", type=float, default=None)
    ap.add_argument("--allow-dirty", action="store_true",
                    help="mutation self-check only: produce a self-labelled probe, never evidence")
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
    dirty_code, dirty_evidence = dirty_split(args.out, args.allow_dirty)

    manifest = {
        "what": "F0 DEV_PROTOCOL_FREEZE instrument manifest",
        "status": ("MUTATION-PROBE -- generated with --allow-dirty; not evidence and authorises nothing"
                   if args.allow_dirty else
                   "PROPOSED -- F0 is a draft; nothing downstream is authorised"),
        "protocol_document": "docs/rebuild/20-B2-DEV-PROTOCOL-FREEZE.md",
        "generator": {
            "script": "scripts/f0_manifest.py",
            "script_digest": sha256_file(Path(__file__).resolve()),
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "repo": {
            "execution_revision": None if args.allow_dirty else head,
            "head_at_generation": head,
            "branch": branch,
            "code_tree_clean": not args.allow_dirty,
            "dirty_code_paths": dirty_code,
            "dirty_evidence_artifacts": dirty_evidence,
            "closure_commit": CLOSURE_COMMIT,
            "closure_is_ancestor": True,
            "crlf_artifacts_on_disk": crlf_artifacts(),
        },
        "instrument": source_digests(),
        "harness": harness_digests(),
        "eval_sample": eval_sample(),
        "gates": gate_summaries(),
        "tests": test_inventory(args.test_list),
        "runtime_reference_seconds": {
            "full_suite": args.suite_seconds,
            "calibration": args.calibration_seconds,
        },
        "runtime_benchmark": runtime_benchmark(),
        "currently_authorises": [],
        "authorises_on_validity": ["smoke5"],
        "not_authorised": [
            "smoke5 (until a reviewer marks F0 VALID)",
            "dev32",
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
        newline="\n",
    )
    print(f"wrote {args.out}")
    print(f"  execution rev   {head} ({branch}), code tree clean")
    print(f"  dirty evidence  {dirty_evidence}")
    print(f"  source files    {manifest['instrument']['n_files']}")
    print(f"  source digest   {manifest['instrument']['tree_digest']}")
    print(f"  run scripts     {manifest['harness']['run_scripts']['n_files']} "
          f"{manifest['harness']['run_scripts']['tree_digest'][:16]}")
    print(f"  tests           {manifest['tests'].get('count')}")
    print(f"  test digest     {manifest['tests'].get('node_id_digest')}")
    print(f"  eval sample     |U2|={manifest['eval_sample']['domain_size']} "
          f"N_max={manifest['eval_sample']['n_max']} "
          f"{manifest['eval_sample']['sample_digest_first_n_max'][:16]}")
    print(f"  authorises now  {manifest['currently_authorises']}")
    print(f"  on validity     {manifest['authorises_on_validity']}")
    bench = manifest["runtime_benchmark"]
    print(f"  benchmark       {bench['measurement']['n_scenes']} scenes "
          f"{bench['measurement']['runtime_s']} s -> bounds {bench['bounds_seconds']}")
    for rel, entry in sorted(manifest["gates"].items()):
        print(f"  gate            {rel} {entry.get('summary')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
