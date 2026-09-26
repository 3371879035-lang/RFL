"""Seedless manifest contract mutation self-check; does not read or approve a real F0."""
import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, digest
from rfl_rebuild.b2.design_lock import CONSTANTS
from rfl_rebuild.b2.f0_stages import ARTIFACT_SCHEMA, GATES, GATE_PATHS, SEED_PATHS, STAGE_SEEDS, ordering, validate_contract


def fixture():
    """Synthetic schema fixture only. Its invented source cannot pass live validation."""
    sources = {"fixture-only.py": "a" * 64}
    identity = digest(canonical_bytes(sources))
    policy = {"ratified": True, "value": 1.5, "rationale": "Synthetic test fixture; not a research ratification"}
    runtime = {"schema": "f0-runtime-v1", "sources_digest": identity, "suite_s": 1., "gate_exit_codes": [0] * 6}
    for stage, keys in (("smoke", list(range(950001, 950006))), ("dev_baseline", list(range(950006, 950038)))):
        runtime[stage] = {"role": "OPERATIONAL_BENCHMARK", "seed_count": len(keys), "keys": keys,
                          "cap": 576, "bank_size": 1024, "records": len(keys) * 577,
                          "elapsed_s": 1., "bound_s": 22.}
    return {"schema": "f0-c3-design-v1", "status": "VALID", "currently_authorises": ["smoke", "dev_baseline", "design_lock"],
            "blockers": [], "instrument_commit": "a" * 40, "constants": copy.deepcopy(CONSTANTS),
            "sources": sources, "sources_digest": identity,
            "seed_files": {stage: {"path": name, "sha256": "b" * 64, "seeds": list(STAGE_SEEDS[stage])}
                           for stage, name in SEED_PATHS.items()}, "ordering": ordering(),
            "gate_suite": copy.deepcopy(GATES), "gate_suite_digest": digest(canonical_bytes(GATES)),
            "expected_gate_artifacts": dict.fromkeys(GATE_PATHS, "c" * 64), "calibration_sha256": "c" * 64,
            "artifact_schema": copy.deepcopy(ARTIFACT_SCHEMA), "runtime": runtime, "rmst_policy": policy,
            "review": {"decision": "VALID", "sources_digest": identity, "rmst_policy": copy.deepcopy(policy)}}


CASES = [
    (("schema",), "legacy", "schema"),
    (("constants", "acquisition_cap"), 40, "constant"),
    (("constants", "alpha"), [True, 2], "constant"),
    (("currently_authorises",), ["other"], "authorizations"),
    (("blockers",), ["pending"], "NOT VALID"),
    (("status",), "NOT_VALID", "draft cannot authorize"),
    (("sources_digest",), "0" * 64, "inventory digest"),
    (("ordering", "whole_digest"), "0" * 64, "ordering"),
    (("gate_suite",), list(reversed(GATES)), "gate list"),
    (("gate_suite_digest",), "0" * 64, "gate list"),
    (("seed_files", "smoke", "seeds"), [1, 0, 2, 3, 4], "seed metadata"),
    (("seed_files", "dev_baseline", "sha256"), None, "seed metadata"),
    (("expected_gate_artifacts", GATE_PATHS[0]), None, "artifact hash"),
    (("calibration_sha256",), "0" * 64, "calibration alias"),
    (("artifact_schema", "digest_surface"), "gzip-bytes", "shard schema"),
    (("rmst_policy", "ratified"), False, "not ratified"),
    (("rmst_policy", "rationale"), "", "not ratified"),
    (("review", "sources_digest"), "0" * 64, "review"),
    (("runtime", "sources_digest"), "0" * 64, "runtime evidence"),
    (("runtime", "suite_s"), 0., "gate-suite runtime"),
    (("runtime", "gate_exit_codes"), [False] * 6, "all green"),
    (("runtime", "smoke", "records"), 5, "shape"),
    (("runtime", "dev_baseline", "cap"), 2, "shape"),
    (("runtime", "smoke", "keys"), [0, 1, 2, 3, 4], "statistical seeds"),
    (("runtime", "smoke", "bound_s"), 23., "formula"),
]


def selfcheck():
    base = fixture()
    validate_contract(base)
    rows = []
    for path, value, expected in CASES:
        mutated = copy.deepcopy(base)
        target = mutated
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        caught = False
        try:
            validate_contract(mutated)
        except ProtocolError as exc:
            caught = expected in str(exc)
        rows.append({"path": list(path), "expected": expected, "rejected_as_expected": caught})
    extra = copy.deepcopy(base)
    extra["future_baseline_digest"] = "0" * 64
    try:
        validate_contract(extra)
        extra_rejected = False
    except ProtocolError:
        extra_rejected = True
    passed = all(r["rejected_as_expected"] for r in rows) and extra_rejected
    return {"check": "seedless F0 manifest contract", "control_passed": True,
            "mutations": rows, "future_field_rejected": extra_rejected,
            "n_mutations": len(rows) + 1, "n_rejected": sum(r["rejected_as_expected"] for r in rows) + extra_rejected,
            "scientific_seed_draws": 0, "real_manifest_approved": False, "verdict": "PASS" if passed else "FAIL"}


def main():
    report = selfcheck()
    # Frozen suite artifact: deterministic bytes, deliberately no actual F0 hash
    # inside this report, so its own expected digest can be known before smoke.
    (ROOT / "experiments/v03r/f0_manifest_selfcheck.json").write_bytes(canonical_bytes(report))
    print(json.dumps({k: v for k, v in report.items() if k != "mutations"}, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
