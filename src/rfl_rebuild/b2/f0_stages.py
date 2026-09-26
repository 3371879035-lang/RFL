"""F0 manifest contract and serial smoke -> development acquisition stages.

Generating a draft grants no authorization. Immutable manifest identity, full
source/seed inventories and a separate smoke receipt bind all downstream inputs.
"""
from __future__ import annotations

import io
import json
import math
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.acquisition import iter_master_baseline
from rfl_rebuild.b2.baseline_artifact import SCHEMA, canonical_bytes, digest, write_acquisition
from rfl_rebuild.b2.design_lock import CONSTANTS, publish_new
from rfl_rebuild.b2.evalorder import coverage, prefix, prefix_digest
from rfl_rebuild.b2.temporal_initializer import temporal_initializer
from rfl_rebuild.b2.training import BaselineAcquisitionPlan
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.solve.dp import solve_reference

STAGE_SEEDS = {"smoke": tuple(range(5)), "dev_baseline": tuple(range(1000, 1032))}
SEED_PATHS = {"smoke": "experiments/v03r/smoke_seeds.txt", "dev_baseline": "experiments/v03r/dev_seeds.txt"}
GATES = [
    {"argv": ["python", "-m", "pytest", "-q"], "artifact": None},
    {"argv": ["python", "scripts/spec_audit.py"], "artifact": None},
    {"argv": ["python", "scripts/b2_view_gate_selfcheck.py"], "artifact": "experiments/v03r/b2_view_gate_selfcheck.json"},
    {"argv": ["python", "scripts/a91_training_gate_selfcheck.py"], "artifact": "experiments/v03r/a91_training_gate_selfcheck.json"},
    {"argv": ["python", "scripts/run_calibration.py"], "artifact": "experiments/v03r/calibration_report.json"},
    {"argv": ["python", "scripts/f0_manifest_selfcheck.py"], "artifact": "experiments/v03r/f0_manifest_selfcheck.json"},
]
GATE_PATHS = tuple(g["artifact"] for g in GATES if g["artifact"])
SMOKE_PATH = "experiments/v03r/smoke_report.json"
MANIFEST_PATH = "experiments/v03r/f0_manifest.json"
SMOKE_FIELDS = {"stage", "seeds", "tree", "runtime_s", "gate_exit_codes", "artifact_paths", "artifact_digests", "errors", "fallbacks"}
MANIFEST_FIELDS = {"schema", "status", "currently_authorises", "blockers", "instrument_commit", "constants",
                   "sources", "sources_digest", "seed_files", "ordering", "gate_suite", "gate_suite_digest",
                   "expected_gate_artifacts", "calibration_sha256", "artifact_schema", "runtime", "rmst_policy", "review"}
ARTIFACT_SCHEMA = {"schema": SCHEMA, "index": "experiments/v03r/dev_baseline.json",
                   "shard_pattern": "dev_baseline/seed-{seed:06d}.jsonl.gz", "digest_surface": "uncompressed-canonical-jsonl"}


def require(condition, message):
    if not condition:
        raise ProtocolError(message)


def is_hash(value, length=64):
    return type(value) is str and len(value) == length and all(c in "0123456789abcdef" for c in value)


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(Path(path).read_bytes(), object_pairs_hook=unique)
    except (OSError, ValueError) as exc:
        raise ProtocolError(f"cannot read JSON artifact {path}: {exc}") from exc


def ordering():
    return {"algorithm": "balanced-U2-7-37-v1", "whole_digest": prefix_digest(5760),
            "prefixes": [{"n": n, "digest": prefix_digest(n), "coverage": coverage(n)}
                         for n in (100, 256, 512, 1024)]}


def instrument_files(root):
    root = Path(root)
    paths = set()
    for directory in ("src", "scripts", "tests"):
        paths.update(p for p in (root / directory).rglob("*.py"))
    paths.update((root / "docs/rebuild").glob("*.md"))
    for name in ("pyproject.toml", ".gitattributes", ".gitignore", "pytest.ini", "conftest.py",
                 "experiments/v03r/evaluate_smoke_gate.py", *SEED_PATHS.values()):
        if (root / name).is_file():
            paths.add(root / name)
    return tuple(sorted(p.relative_to(root).as_posix() for p in paths))


def source_inventory(root):
    return {name: digest((Path(root) / name).read_bytes()) for name in instrument_files(root)}


def read_seeds(path, stage):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    try:
        seeds = tuple(int(line.strip()) for line in lines if line.strip() and not line.lstrip().startswith("#"))
    except ValueError as exc:
        raise ProtocolError("seed file contains a noninteger") from exc
    require(seeds == STAGE_SEEDS[stage], f"{stage} seed file does not equal the frozen ordered set")
    return seeds


def _committed_sources(root, revision, paths):
    commands = "".join(f"{revision}:{p}\n" for p in paths).encode("utf-8")
    process = subprocess.run(["git", "cat-file", "--batch"], cwd=root, input=commands, capture_output=True)
    require(process.returncode == 0, "cannot inspect the instrument commit")
    stream, result = io.BytesIO(process.stdout), {}
    for path in paths:
        header = stream.readline().split()
        require(len(header) == 3 and header[1] == b"blob", f"instrument source not committed: {path}")
        result[path] = digest(stream.read(int(header[2])))
        require(stream.read(1) == b"\n", "malformed git object stream")
    return result


def validate_contract(manifest, *, require_valid=True):
    """Pure schema/constant checks. No filesystem access, seed draw or self-reference."""
    require(type(manifest) is dict and set(manifest) == MANIFEST_FIELDS, "F0 manifest field set mismatch")
    require(manifest["schema"] == "f0-c3-design-v1", "unsupported F0 schema")
    require(manifest["status"] in ("NOT_VALID", "VALID"), "invalid F0 status")
    auth = manifest["currently_authorises"]
    require(type(auth) is list and all(type(a) is str and a in ("smoke", "dev_baseline", "design_lock") for a in auth)
            and len(set(auth)) == len(auth), "invalid F0 authorizations")
    require(type(manifest["blockers"]) is list and all(type(b) is str for b in manifest["blockers"]), "invalid blocker list")
    if manifest["status"] == "NOT_VALID":
        require(auth == [], "a draft cannot authorize a stage")
    if require_valid:
        require(manifest["status"] == "VALID" and not manifest["blockers"], "F0 is NOT VALID")
    require(is_hash(manifest["instrument_commit"], 40), "invalid instrument revision")
    require(canonical_bytes(manifest["constants"]) == canonical_bytes(CONSTANTS), "F0 constant block mismatch")
    sources = manifest["sources"]
    require(type(sources) is dict and bool(sources) and all(type(k) is str and is_hash(v) for k, v in sources.items()),
            "invalid source inventory")
    require(manifest["sources_digest"] == digest(canonical_bytes(sources)), "source inventory digest mismatch")
    require(manifest["ordering"] == ordering(), "balanced evaluation ordering mismatch")
    require(manifest["gate_suite"] == GATES and manifest["gate_suite_digest"] == digest(canonical_bytes(GATES)),
            "frozen gate list mismatch")
    require(manifest["artifact_schema"] == ARTIFACT_SCHEMA, "baseline shard schema mismatch")
    seed_files = manifest["seed_files"]
    require(type(seed_files) is dict and set(seed_files) == set(SEED_PATHS), "seed file inventory mismatch")
    for stage, name in SEED_PATHS.items():
        item = seed_files[stage]
        require(type(item) is dict and set(item) == {"path", "sha256", "seeds"}
                and item["path"] == name and is_hash(item["sha256"])
                and item["seeds"] == list(STAGE_SEEDS[stage]) and all(type(s) is int for s in item["seeds"]),
                f"{stage} seed metadata mismatch")
    artifacts = manifest["expected_gate_artifacts"]
    require(type(artifacts) is dict and set(artifacts) == set(GATE_PATHS), "gate artifact inventory mismatch")
    require(all(is_hash(h) or (not require_valid and h is None) for h in artifacts.values()), "missing gate artifact hash")
    require(manifest["calibration_sha256"] == artifacts["experiments/v03r/calibration_report.json"], "calibration alias mismatch")
    if require_valid:
        policy, review, runtime = manifest["rmst_policy"], manifest["review"], manifest["runtime"]
        require(type(policy) is dict and policy.get("ratified") is True
                and type(policy.get("value")) in (int, float) and 0 < policy["value"] < math.inf
                and isinstance(policy.get("rationale"), str) and bool(policy["rationale"].strip()),
                "RMST practical threshold not ratified")
        require(type(review) is dict and review.get("decision") == "VALID"
                and review.get("sources_digest") == manifest["sources_digest"]
                and review.get("rmst_policy") == policy, "review is absent or stale")
        validate_runtime(runtime, manifest["sources_digest"])
    return manifest


def validate_runtime(runtime, sources_digest):
    require(type(runtime) is dict and runtime.get("schema") == "f0-runtime-v1"
            and runtime.get("sources_digest") == sources_digest, "runtime evidence absent or stale")
    suite = runtime.get("suite_s")
    require(type(suite) in (float, int) and 0 < suite < math.inf, "invalid measured gate-suite runtime")
    codes = runtime.get("gate_exit_codes")
    require(type(codes) is list and all(type(c) is int for c in codes) and codes == [0] * len(GATES),
            "runtime gate suite was not all green")
    for stage, count in (("smoke", 5), ("dev_baseline", 32)):
        row = runtime.get(stage)
        require(type(row) is dict and row.get("role") == "OPERATIONAL_BENCHMARK"
                and row.get("seed_count") == count and row.get("cap") == 576 and row.get("bank_size") == 1024
                and row.get("records") == count * 577, f"{stage} benchmark shape mismatch")
        keys = row.get("keys")
        require(type(keys) is list and len(keys) == count and all(type(k) is int and k >= 0 for k in keys)
                and len(set(keys)) == count and not set(keys).intersection(range(5))
                and not set(keys).intersection(range(1000, 1032)), "benchmark used statistical seeds")
        seconds = row.get("elapsed_s")
        require(type(seconds) in (int, float) and 0 < seconds < math.inf, "invalid benchmark duration")
        require(row.get("bound_s") == 2 * (suite + 10 * seconds), "runtime bound formula mismatch")


def build_manifest(root, *, runtime=None, review=None, finalize=False):
    root = Path(root)
    sources = source_inventory(root)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    artifacts = {name: digest((root / name).read_bytes()) if (root / name).is_file() else None for name in GATE_PATHS}
    seed_files = {stage: {"path": name, "sha256": digest((root / name).read_bytes()),
                          "seeds": list(read_seeds(root / name, stage))} for stage, name in SEED_PATHS.items()}
    blockers = []
    try:
        require(_committed_sources(root, revision, tuple(sources)) == sources, "instrument differs from commit")
    except ProtocolError:
        blockers.append("INSTRUMENT_NOT_COMMITTED_BYTE_IDENTICALLY")
    if any(v is None for v in artifacts.values()):
        blockers.append("GATE_ARTIFACTS_MISSING")
    sources_digest = digest(canonical_bytes(sources))
    try:
        validate_runtime(runtime, sources_digest)
    except ProtocolError:
        blockers.append("FULL_ENVELOPE_RUNTIME_EVIDENCE_MISSING_OR_STALE")
    policy = review.get("rmst_policy") if type(review) is dict else {"value": 1.5, "ratified": False, "rationale": ""}
    if not (type(review) is dict and review.get("decision") == "VALID" and review.get("sources_digest") == sources_digest
            and type(policy) is dict and policy.get("ratified") is True):
        blockers.append("INDEPENDENT_RMST_POLICY_AND_F0_REVIEW_PENDING")
    if not finalize:
        blockers.append("DRAFT_ONLY")
    manifest = {"schema": "f0-c3-design-v1", "status": "VALID" if finalize and not blockers else "NOT_VALID",
                "currently_authorises": ["smoke", "dev_baseline", "design_lock"] if finalize and not blockers else [],
                "blockers": blockers, "instrument_commit": revision, "constants": CONSTANTS,
                "sources": sources, "sources_digest": sources_digest, "seed_files": seed_files,
                "ordering": ordering(), "gate_suite": GATES, "gate_suite_digest": digest(canonical_bytes(GATES)),
                "expected_gate_artifacts": artifacts,
                "calibration_sha256": artifacts["experiments/v03r/calibration_report.json"],
                "artifact_schema": ARTIFACT_SCHEMA, "runtime": runtime, "rmst_policy": policy, "review": review}
    validate_contract(manifest, require_valid=finalize)
    return manifest


def load_manifest(root, manifest_path, stage):
    root, path = Path(root).resolve(), Path(manifest_path).resolve()
    require(path.is_relative_to(root), "manifest is outside the checkout")
    manifest = validate_contract(read_json(path))
    require(stage in manifest["currently_authorises"], f"F0 has not authorized {stage}")
    try:
        committed = subprocess.check_output(["git", "show", f"HEAD:{path.relative_to(root).as_posix()}"], cwd=root,
                                             stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as exc:
        raise ProtocolError("F0 manifest must be committed before a stage") from exc
    require(committed == path.read_bytes(), "F0 manifest differs from committed bytes")
    sources = source_inventory(root)
    require(sources == manifest["sources"], "instrument source inventory or hash changed")
    require(_committed_sources(root, manifest["instrument_commit"], tuple(sources)) == sources,
            "source bytes do not belong to the instrument revision")
    for stage_name, item in manifest["seed_files"].items():
        require(digest((root / item["path"]).read_bytes()) == item["sha256"], "seed file digest changed")
        read_seeds(root / item["path"], stage_name)
    for name, expected in manifest["expected_gate_artifacts"].items():
        require(digest((root / name).read_bytes()) == expected, f"gate artifact digest changed: {name}")
        read_json(root / name)
    return manifest, digest(path.read_bytes())


def evaluate_smoke(report, manifest, manifest_hash):
    """Pure closed-surface PASS/FAIL; no outcome metric can enter this object."""
    def fail(reason):
        return {"verdict": "FAIL", "reason": reason}
    if type(report) is not dict or set(report) != SMOKE_FIELDS:
        return fail("SMOKE_FIELD_SET")
    if report["stage"] != "smoke" or report["seeds"] != list(STAGE_SEEDS["smoke"]) or any(type(s) is not int for s in report["seeds"]):
        return fail("STAGE_OR_SEEDS")
    expected_tree = {"instrument_commit": manifest["instrument_commit"], "manifest_sha256": manifest_hash}
    if report["tree"] != expected_tree:
        return fail("EXECUTION_IDENTITY")
    codes = report["gate_exit_codes"]
    if type(codes) is not list or any(type(c) is not int for c in codes) or codes != [0] * len(GATES):
        return fail("GATE_EXIT_CODES")
    if report["artifact_paths"] != list(GATE_PATHS) or report["artifact_digests"] != manifest["expected_gate_artifacts"]:
        return fail("GATE_ARTIFACT_DIGESTS")
    if report["errors"] != [] or report["fallbacks"] != []:
        return fail("ERROR_OR_FALLBACK")
    seconds = report["runtime_s"]
    if type(seconds) not in (float, int) or not 0 <= seconds < math.inf:
        return fail("INVALID_RUNTIME")
    if seconds > manifest["runtime"]["smoke"]["bound_s"]:
        return fail("RUNTIME_EXCEEDED")
    return {"verdict": "PASS", "reason": None}


def require_smoke(root, manifest, manifest_hash):
    path = Path(root) / SMOKE_PATH
    result = evaluate_smoke(read_json(path), manifest, manifest_hash)
    require(result["verdict"] == "PASS", f"smoke not PASS: {result['reason']}")
    return digest(path.read_bytes())


def stage_inputs(root, *, manifest_path, seeds_file, stage):
    manifest, identity = load_manifest(root, manifest_path, stage)
    expected = manifest["seed_files"][stage]
    require(Path(seeds_file).resolve() == (Path(root) / expected["path"]).resolve(), "stage seed file is not its frozen path")
    seeds = read_seeds(seeds_file, stage)
    require(digest(Path(seeds_file).read_bytes()) == expected["sha256"], "stage seed file digest mismatch")
    return manifest, identity, seeds


def records_for(manifest, seeds):
    constants = manifest["constants"]
    plan = BaselineAcquisitionPlan(seeds[0], Fraction(*constants["alpha"]), Fraction(*constants["epsilon"]),
                                   constants["acquisition_cap"], prefix(1024))
    reference = reference_view_from(solve_reference())
    return plan, iter_master_baseline(plan, seeds=seeds, q_reference=reference, initializer=temporal_initializer)


def discard_complete(records, seeds, cap):
    iterator, count = iter(records), 0
    for seed in seeds:
        for episode in range(cap + 1):
            try:
                row = next(iterator)
            except StopIteration as exc:
                raise ProtocolError("smoke acquisition ended before its full envelope") from exc
            require((row.seed, row.episode) == (seed, episode), "smoke acquisition axis mismatch")
            count += 1
    sentinel = object()
    require(next(iterator, sentinel) is sentinel, "smoke acquisition exceeded its envelope")
    return count


def run_gate_suite(root):
    codes = []
    for gate in GATES:  # serial: mutation harnesses temporarily edit and restore source files
        result = subprocess.run([sys.executable, *gate["argv"][1:]], cwd=root, capture_output=True, text=True)
        codes.append(result.returncode)
        print(f"gate {len(codes)}/{len(GATES)} exit={result.returncode}: {' '.join(gate['argv'])}", flush=True)
    return codes


def run_smoke(root, *, manifest_path, seeds_file, plan_only=False):
    root = Path(root)
    manifest, identity, seeds = stage_inputs(root, manifest_path=manifest_path, seeds_file=seeds_file, stage="smoke")
    if plan_only:
        return {"status": "PLAN_VALID", "stage": "smoke", "seeds": list(seeds), "written": False, "episodes_run": 0}
    output = root / SMOKE_PATH
    require(not output.exists(), "smoke report already exists; refusing to reuse spent seeds")
    publish_new(root / "experiments/v03r/smoke_attempt.json",
                {"stage": "smoke", "manifest_sha256": identity, "seeds": list(seeds)})
    start = time.perf_counter()
    report = {"stage": "smoke", "seeds": list(seeds),
              "tree": {"instrument_commit": manifest["instrument_commit"], "manifest_sha256": identity},
              "runtime_s": 0., "gate_exit_codes": [], "artifact_paths": list(GATE_PATHS),
              "artifact_digests": {}, "errors": [], "fallbacks": []}
    try:
        report["gate_exit_codes"] = run_gate_suite(root)
        report["artifact_digests"] = {name: digest((root / name).read_bytes()) for name in GATE_PATHS}
        require(report["gate_exit_codes"] == [0] * len(GATES), "smoke gate suite failed")
        require(report["artifact_digests"] == manifest["expected_gate_artifacts"], "smoke gate artifact drift")
        plan, records = records_for(manifest, seeds)
        discard_complete(records, seeds, plan.acquisition_cap)
        _, after = load_manifest(root, manifest_path, "smoke")
        require(after == identity, "manifest changed during smoke")
    except Exception as exc:
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    report["runtime_s"] = time.perf_counter() - start
    publish_new(output, report)
    return {**evaluate_smoke(report, manifest, identity), "written": True, "path": str(output)}


def run_baseline(root, *, manifest_path, seeds_file, plan_only=False):
    root = Path(root)
    manifest, identity, seeds = stage_inputs(root, manifest_path=manifest_path, seeds_file=seeds_file, stage="dev_baseline")
    smoke_identity = require_smoke(root, manifest, identity)
    if plan_only:
        return {"status": "PLAN_VALID", "stage": "dev_baseline", "seeds": list(seeds), "written": False, "episodes_run": 0}
    output = root / ARTIFACT_SCHEMA["index"]
    require(not output.exists() and not output.with_suffix("").exists(), "baseline output exists; no automatic rerun or overwrite")
    start = time.perf_counter()
    plan, records = records_for(manifest, seeds)
    def checked_stream():
        yield from records
        _, after = load_manifest(root, manifest_path, "dev_baseline")
        require(after == identity, "manifest changed during baseline")
        require(require_smoke(root, manifest, identity) == smoke_identity, "smoke receipt changed during baseline")
        require(time.perf_counter() - start <= manifest["runtime"]["dev_baseline"]["bound_s"], "baseline runtime bound exceeded")
    index = write_acquisition(output, plan=plan, seeds=seeds, records=checked_stream(), constants=CONSTANTS,
                              execution={"manifest_sha256": identity, "sources": manifest["sources"],
                                         "head_commit": manifest["instrument_commit"], "smoke_report_sha256": smoke_identity},
                              role="DEVELOPMENT_BASELINE")
    return {"status": "ACQUIRED", "written": True, "path": str(output), "records": index["records"]}
