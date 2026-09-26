"""Verified development-only adapter and one atomic design/threshold publication.

This consumer does not generate or approve an F0 manifest. A committed, valid F0
manifest must authorize design_lock and bind the actual acquisition beforehand.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.baseline_artifact import (
    canonical_bytes, digest, read_index, verify_acquisition, iter_verified_material,
)
from rfl_rebuild.b2.design_selection import derive_design, combine_design_and_thresholds, require_calibration
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.temporal_initializer import INITIALIZER_ID, ACQUISITION_CAP
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference

CONSTANTS = {"initializer": INITIALIZER_ID, "layer": 1, "alpha": [1, 2], "epsilon": [1, 10],
             "acquisition_cap": ACQUISITION_CAP, "K": 3, "epsilon_s": .001, "epsilon_f": .1,
             "theta_N": .25, "theta_G": .05, "theta_C": 1., "theta_R": .10,
             "rho_R": .9, "kappa_R": .25, "epsilon_N": 1e-9, "epsilon_R": 1e-9}


def prepare_inputs(root, *, design_path, manifest_path):
    root, design_path, manifest_path = Path(root).resolve(), Path(design_path).resolve(), Path(manifest_path).resolve()
    if not manifest_path.is_relative_to(root):
        raise ProtocolError("F0 manifest must belong to this checkout")
    if not manifest_path.is_file():
        raise ProtocolError("F0 manifest absent; design_lock is not authorized")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise ProtocolError("F0 manifest must be an object")
    if (manifest.get("schema") != "f0-c3-design-v1" or manifest.get("status") != "VALID"
            or "design_lock" not in manifest.get("currently_authorises", [])):
        raise ProtocolError("F0 has not authorized design_lock")
    if manifest.get("constants") != CONSTANTS:
        raise ProtocolError("F0 constants do not match the implemented frozen selector profile")
    policy = manifest.get("rmst_policy", {})
    if (not isinstance(policy, dict) or policy.get("ratified") is not True or type(policy.get("value")) not in (int, float)
            or not 0 < policy["value"] < float("inf") or not isinstance(policy.get("rationale"), str)
            or not policy["rationale"].strip()):
        raise ProtocolError("independent P RMST threshold is not ratified in F0")
    rel_manifest = manifest_path.relative_to(root).as_posix()
    try:
        committed = subprocess.check_output(["git", "show", f"HEAD:{rel_manifest}"], cwd=root,
                                             stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as exc:
        raise ProtocolError("F0 manifest must be committed before development") from exc
    if committed != manifest_bytes:
        raise ProtocolError("F0 manifest differs from its committed bytes")
    sources = manifest.get("sources", {})
    if not isinstance(sources, dict):
        raise ProtocolError("F0 source inventory must be an object")
    required = {p.relative_to(root).as_posix() for p in (root / "src/rfl_rebuild").rglob("*.py")}
    required |= {"scripts/run_dev_lock.py", "docs/rebuild/05-STATISTICAL-PROTOCOL.md",
                 "docs/rebuild/12-AMENDMENTS.md", "docs/rebuild/20-B2-DEV-PROTOCOL-FREEZE.md",
                 "docs/rebuild/29-F0-DESIGN-SELECTORS.md"}
    if not required.issubset(sources):
        raise ProtocolError("F0 source inventory does not cover the selector instrument")
    for name, expected in sources.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or digest(path.read_bytes()) != expected:
            raise ProtocolError(f"F0 source fingerprint mismatch: {name}")
    index = read_index(design_path)
    if index["role"] != "DEVELOPMENT_BASELINE" or index["seeds"] != list(range(1000, 1032)):
        raise ProtocolError("only the frozen development seed population can select an F1 design")
    if index["bank_size"] != 1024 or index["episodes"] != list(range(ACQUISITION_CAP + 1)):
        raise ProtocolError("development acquisition did not cover the full master envelope")
    if index["constants"] != CONSTANTS:
        raise ProtocolError("development constants disagree with F0")
    if (index["execution"].get("manifest_sha256") != digest(manifest_bytes)
            or index["execution"].get("sources") != sources):
        raise ProtocolError("development provenance does not bind this F0 manifest/instrument")
    calibration_path = root / "experiments/v03r/calibration_report.json"
    calibration_bytes = calibration_path.read_bytes()
    if digest(calibration_bytes) != manifest.get("calibration_sha256"):
        raise ProtocolError("calibration fingerprint differs from F0")
    calibration = json.loads(calibration_bytes)
    require_calibration(calibration)
    verify_acquisition(design_path)  # no design metric has been computed yet
    return {"manifest": manifest, "index": index, "calibration": calibration,
            "manifest_sha256": digest(manifest_bytes), "index_sha256": digest(design_path.read_bytes())}


def publish_new(path, payload):
    """Publish a fully flushed file atomically with no replacement of existing work."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    data = canonical_bytes(payload)
    # The parent must already exist. A temporary inode is hard-linked into its
    # final name only after completion; link() atomically refuses an existing name.
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".f1-", delete=False) as out:
            temp = Path(out.name)
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.link(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def run_lock(root, *, design_path, manifest_path, output_path, plan_only=False):
    inputs = prepare_inputs(root, design_path=design_path, manifest_path=manifest_path)
    if plan_only:
        return {"status": "PLAN_VALID", "index_sha256": inputs["index_sha256"],
                "records": inputs["index"]["records"], "metrics_computed": False, "written": False}
    if Path(output_path).exists():
        raise FileExistsError(output_path)
    reference = reference_view_from(solve_reference())
    sample, healthy = prefix(1024), LearnerPersistentState()
    pre_level = mean(tuple(learned_rollout(healthy, kappa=u.kappa, tape=u.tape, base_option=u.base_option,
                                         q_reference=reference).return_value for u in sample))
    design = derive_design(iter_verified_material(design_path), seeds=inputs["index"]["seeds"],
                           cap=ACQUISITION_CAP, sample=sample, pre_level=pre_level,
                           calibration=inputs["calibration"])
    combined = combine_design_and_thresholds(design, rmst_policy=inputs["manifest"]["rmst_policy"])
    if combined["lock"] is None:
        return {"status": combined["status"], "diagnostics": design, "written": False}
    # No hand edit or file drift is allowed between design and threshold stages.
    rechecked = prepare_inputs(root, design_path=design_path, manifest_path=manifest_path)
    if (rechecked["manifest_sha256"], rechecked["index_sha256"]) != (
            inputs["manifest_sha256"], inputs["index_sha256"]):
        raise ProtocolError("F0 or baseline changed during design selection")
    payload = {"schema": "f1-design-threshold-v1", "status": "LOCKED", "design": combined["lock"],
               "selection_diagnostics": design, "v_pre": pre_level,
               "f0_manifest_sha256": inputs["manifest_sha256"],
               "baseline_index_sha256": inputs["index_sha256"],
               "ordered_shard_digest": inputs["index"]["ordered_shard_digest"]}
    publish_new(output_path, payload)
    return {"status": "LOCKED", "written": True, "path": str(output_path)}
