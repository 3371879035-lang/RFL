"""Read-only internal draft audit; prints evidence, never publishes F0 or a lock.

This is NOT independent agent/expert review. A successful audit validates only
the bound draft and its test records. It authorizes no scientific data.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PARENT = Path("D:/强化反馈学习/RFL-CausalChase-v0.3-parallel16-20261008")
BASE = "559f53be9a3f5be226e8757a2ddf5a0e4187afcd"
MANIFEST = "experiments/v03r/parallel_verify_restart_20261008/f0_manifest_after_shutdown.json"
EXPECTED_MANIFEST_SHA = "1aea2695a417e52c98fe61bdf8cc2cb7a9485dcd901bee459df4b22c65cbb959"
EXPECTED_SOURCES = "1359a1ae11cf54407a9b976b53219e30134173d255c985908f838cb057171bd2"
PARENT_EVIDENCE = {
    MANIFEST: EXPECTED_MANIFEST_SHA,
    "experiments/v03r/dev_baseline.json": "705fd606911352250ba4e9241782b8a37f778f4ecffeebaa44628eb54df11fc4",
    "experiments/v03r/f1_parallel_design_20261008/f1_execution.json": "9812c23ca2c467ed8a7a61a807e45d3c00adf07d9db8d3921ea833bd48f43b1e",
    "experiments/v03r/f0_runtime_parallel16_resume_20261008/runtime.json": "81d96b18063d1f9a0e0631b0221230f1efd6ee093e3d14f111b10f56197cbb44",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require(condition, explanation):
    if not condition:
        raise RuntimeError(explanation)


def counts(name):
    doc = ET.parse(HERE / name).getroot()
    suites = list(doc.iter("testsuite"))
    return {key: sum(int(s.attrib.get(key, "0")) for s in suites)
            for key in ("tests", "failures", "errors", "skipped")}


def audit():
    require(ROOT.resolve() != PARENT.resolve(), "must not mutate/resume the parent checkout")
    require(sha(ROOT / MANIFEST) == EXPECTED_MANIFEST_SHA, "base manifest drift")
    manifest = read(ROOT / MANIFEST)
    sources = manifest["sources"]
    require(len(sources) == 295 and manifest["sources_digest"] == EXPECTED_SOURCES, "wrong base source inventory")
    for relative, expected in sources.items():
        for checkout in (ROOT, PARENT):
            target = (checkout / relative).resolve()
            require(target.is_relative_to(checkout.resolve()), "source path outside expected root")
            require(sha(target) == expected, f"base source drift: {checkout.name}/{relative}")
    for relative, expected in PARENT_EVIDENCE.items():
        require(sha(PARENT / relative) == expected, f"parent native evidence drift: {relative}")
    base = subprocess.check_output(["git", "merge-base", "HEAD", BASE], cwd=ROOT, text=True).strip()
    require(base == BASE, "wrong draft ancestry")
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    require(branch == "study/v03r-measurement-revision-20261008", "wrong execution branch")
    contract = read(HERE / "contract.json")
    require(contract["ratified"] is False and contract["scientific_execution_authorized"] is False
            and contract["production_dispatch_changed"] is False and contract["scientific_seed_sets"] is None,
            "draft authorization boundary changed")
    require(contract["unchanged"]["acquisition_cap"] == 576
            and contract["unchanged"]["initializer"] == "c3-temporal-layer-1-v1"
            and contract["unchanged"]["retention_stability_limit"] == .10
            and contract["unchanged"]["retention_margin_multiplier"] == .25
            and contract["unchanged"]["maximum_spawn_workers"] == 16, "protected constants changed")
    require(not (ROOT / "experiments/v03r/dev_lock.json").exists()
            and not (PARENT / "experiments/v03r/dev_lock.json").exists(), "unexpected F1 lock")
    require(read(ROOT / "experiments/rebuild_status_current.json")["scientific_result"] == "NO_ADMISSIBLE_RETENTION",
            "parent result was reinterpreted")
    prototype = counts("prototype_tests_final.xml")
    require(prototype == {"tests": 64, "failures": 0, "errors": 0, "skipped": 0}, "prototype tests incomplete")
    regression = counts("regression_tests.xml")
    require(regression == {"tests": 1001, "failures": 0, "errors": 0, "skipped": 1}, "complete base regression not as expected")
    initial = counts("prototype_tests.xml")
    require(initial == {"tests": 64, "failures": 1, "errors": 0, "skipped": 0}, "initial test failure evidence not retained")
    names = ("contract.json", "MEASUREMENT_AMENDMENT_DRAFT.txt", "PRODUCTION_INTEGRATION_CHECKLIST.txt", "measurement_prototype.py",
             "test_measurement_prototype.py", "audit_draft.py", "prototype_tests.xml",
             "prototype_tests_final.xml", "regression_tests.xml")
    return {
        "schema": "rfl-v03r-measurement-draft-internal-audit-v1",
        "role": "BOUND_INTERNAL_DRAFT_AUDIT_NOT_F0_OR_SCIENTIFIC_RECEIPT",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_commit": BASE, "branch": branch,
        "current_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "base_scientific_sources": {"count": 295, "digest": EXPECTED_SOURCES,
                                    "new_and_parent_checkouts_match": True},
        "parent_evidence_sha256": PARENT_EVIDENCE,
        "draft_files_sha256": {name: sha(HERE / name) for name in names},
        "prototype_tests_final": prototype, "base_full_regression": regression,
        "prototype_tests_initial": initial,
        "initial_failure_resolution": "Test assumed an exact tie between checkpoint mean and last value; fixed to honor exact left-to-right arithmetic and declared stability ranking. No prototype threshold or rule changed to force the preferred form.",
        "internal_review_decision": "DRAFT_CONSTRUCTION_CHECKS_PASS_NOT_RATIFICATION",
        "independent_agent_or_expert_review": False,
        "scientific_seeds_used_by_prototype": [], "new_training_runs": 0,
        "old_raw_read_by_prototype": False,
        "new_data_authorized": False, "F1_lock_published": False,
        "new_runtime_or_F0_produced": False, "external_publication": False,
        "remaining": ["exact scientific rule ratification", "production integration and global new seed assignment",
                      "bound production review, fresh full-workload engineering gates and F0",
                      "fresh smoke/development/full F1", "separate B2 collection and final statistics"],
    }


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
