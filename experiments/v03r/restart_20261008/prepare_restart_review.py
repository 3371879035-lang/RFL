"""Internal source-bound delta review; never approve a scientific outcome or F0."""
import importlib.util
import json
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, digest
from rfl_rebuild.b2.design_lock import publish_new
from rfl_rebuild.b2.f0_stages import GATES, GATE_PATHS, source_inventory, _committed_sources, require, read_json

spec = importlib.util.spec_from_file_location("restart_pipeline", HERE / "continue_pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)

ALLOWED_DELTA = {
    "docs/rebuild/12-AMENDMENTS.md", "docs/rebuild/20-B2-DEV-PROTOCOL-FREEZE.md",
    "docs/rebuild/30-F0-STAGE-RUNNERS.md", "experiments/v03r/smoke_seeds.txt",
    "scripts/f0_manifest_selfcheck.py", "src/rfl_rebuild/b2/f0_stages.py",
    "tests/rebuild/test_b2_f0_stages.py",
}


def xml_counts(path):
    suites = ET.parse(path).getroot().findall("testsuite")
    counts = {key: sum(int(s.get(key, "0")) for s in suites)
              for key in ("tests", "errors", "failures", "skipped")}
    require(counts["tests"] > 0 and counts["errors"] == counts["failures"] == 0,
            "review regression XML is invalid or failing")
    return counts


def main():
    require(not pipeline.REVIEW.exists(), "review already exists; do not overwrite")
    registration = read_json(HERE / "preregistration.json")
    parent = pipeline.verify_parent_preserved()
    sources = source_inventory(ROOT)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(_committed_sources(ROOT, head, tuple(sources)) == sources, "commit restart sources before review")
    old = _committed_sources(ROOT, registration["parent_f0_commit"], tuple(sources))
    changed = {name for name in sources if sources[name] != old[name]}
    require(changed == ALLOWED_DELTA, "unexpected instrument delta: " + repr(sorted(changed)))
    pipeline.run_success("review_full_regression", [sys.executable, "-B", "-X", "utf8", "-m", "pytest",
                                                   "--junitxml", HERE / "review_full_regression.xml"])
    pipeline.run_success("review_controller_checks", [sys.executable, "-B", "-X", "utf8", "-m", "pytest",
                                                      HERE / "test_continue_pipeline.py", "--junitxml",
                                                      HERE / "review_controller_checks.xml"])
    codes = []
    for i, gate in enumerate(GATES, 1):
        code = pipeline.command(f"review_gate_{i}", [sys.executable, "-B", "-X", "utf8", *gate["argv"][1:]])
        require(code == 0, f"review gate {i} failed")
        codes.append(code)
        require(source_inventory(ROOT) == sources, "native gate did not restore restart sources")
    gate_hashes = {name: digest((ROOT / name).read_bytes()) for name in GATE_PATHS}
    checks = {"regression": xml_counts(HERE / "review_full_regression.xml"),
              "controller": xml_counts(HERE / "review_controller_checks.xml"), "native_gate_exit_codes": codes}
    for name in GATE_PATHS:
        artifact = read_json(ROOT / name)
        if "n_mutations" in artifact:
            require(artifact.get("source_restored", True) is True, "mutation source restoration failed")
        if name.endswith("f0_manifest_selfcheck.json"):
            require(artifact.get("verdict") == "PASS" and artifact.get("n_rejected") == 32,
                    "restart F0 contract selfcheck failed")
        if name.endswith("calibration_report.json"):
            require(artifact["summary"]["all_agree"] is True and not artifact["summary"]["failures"],
                    "calibration failed")
    prior = read_json(ROOT / "experiments/v03r/amendment_20260927/source_bound_review.json")
    pipeline.validate_rmst_policy(prior["rmst_policy"])
    require(source_inventory(ROOT) == sources, "restart source drift during review")
    report = {
        "role": "INTERNAL_SOURCE_BOUND_RESTART_DELTA_REVIEW",
        "decision": "VALID", "reviewed_at_utc": pipeline.now(),
        "review_method": "Single-agent implementation and source-bound delta audit with independent mechanical tests. Not an independent agent, external expert or human methodological review.",
        "independent_agent_review_performed": False, "external_review_performed": False,
        "basis": "Prospective user-authorized R1 registration and appended A93; only seven explicitly allowed source/protocol/test files differ from the preserved parent. All scientific mechanism implementation remains byte-identical.",
        "instrument_commit": head, "source_count": len(sources), "sources_digest": digest(canonical_bytes(sources)),
        "delta": {name: {"parent_sha256": old[name], "restart_sha256": sources[name]} for name in sorted(changed)},
        "preregistration_sha256": digest((HERE / "preregistration.json").read_bytes()),
        "parent_preservation": parent, "checks": checks, "gate_artifact_sha256": gate_hashes,
        "rmst_policy": prior["rmst_policy"],
        "prior_method_review_sha256": digest((ROOT / "experiments/v03r/amendment_20260927/source_bound_review.json").read_bytes()),
        "prior_review_does_not_authorize_new_source": True,
        "formal_stages_authorized": [], "scientific_claims_authorized": [],
        "limitations": ["No scientific outcomes were read or compared. This review does not authorize F0 itself.",
                        "Fresh full-envelope current-source timing and all-shard verification remain mandatory.",
                        "The previous interruption cause remains unknown; detached launch is an operational safeguard, not a demonstrated root-cause fix.",
                        "1.5 RMST is only a quantitative benchmark, not practical value, equivalence or zero harm.",
                        "This internal delta review does not imply an independent new reviewer inspected these source bytes."]}
    publish_new(pipeline.REVIEW, report)
    print(json.dumps({"decision": report["decision"], "sources_digest": report["sources_digest"],
                      "checks": checks, "formal_stages_authorized": []}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
