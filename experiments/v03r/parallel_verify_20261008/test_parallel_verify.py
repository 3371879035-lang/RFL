"""Engineering fixtures only: same frozen parser, full checks, no scientific draws."""
import copy
from dataclasses import replace
from fractions import Fraction
import gzip
import json
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
import parallel_verify as pv
import continue_verified as controller
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.acquisition import acquire_master_baseline
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, verify_acquisition, write_acquisition
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.temporal_initializer import temporal_initializer
from rfl_rebuild.b2.training import BaselineAcquisitionPlan
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.solve.dp import solve_reference


@pytest.fixture(scope="module")
def material():
    reference = reference_view_from(solve_reference())
    plan = BaselineAcquisitionPlan(980200, Fraction(1,2), Fraction(1,10), 1, prefix(4))
    data = acquire_master_baseline(plan, seeds=(980200,), q_reference=reference,
                                   initializer=temporal_initializer)
    return plan, list(data.runs.values())


def fixture_index(tmp_path, material, count=2):
    plan, rows = material
    seeds = tuple(range(980200, 980200 + count))
    index_path = tmp_path / "baseline.json"
    index = write_acquisition(index_path, plan=plan, seeds=seeds,
        records=(replace(row, seed=seed) for seed in seeds for row in rows),
        constants={"fixture": True}, execution={"role": "OPERATIONAL_FIXTURE"},
        role="OPERATIONAL_REHEARSAL")
    return index_path, index


def test_parallel_full_pass_is_same_as_original_and_read_only(tmp_path, material):
    path, expected = fixture_index(tmp_path, material)
    before = {str(p): pv.file_digest(p) for p in tmp_path.rglob("*") if p.is_file()}
    assert verify_acquisition(path) == expected
    result = pv.verify_parallel(path)
    assert result["status"] == "ALL_SHARDS_VERIFIED"
    assert result["records"] == expected["records"]
    assert result["pairs"] == expected["pairs"]
    assert [row["seed"] for row in result["shards"]] == expected["seeds"]
    assert [row["sha256"] for row in result["shards"]] == [s["sha256"] for s in expected["shards"]]
    assert before == {str(p): pv.file_digest(p) for p in tmp_path.rglob("*") if p.is_file()}
    assert result["validation_reduced"] is False and result["scientific_metrics_computed"] is False


@pytest.mark.parametrize("damage", ["hash", "truncate", "extra", "axis", "noncanonical",
    "domain", "indices", "success", "flag", "duplicate_site", "unknown", "duplicate_key"])
def test_late_shard_mutations_are_refused_by_both_paths(tmp_path, material, damage):
    path, index = fixture_index(tmp_path, material)
    shard = tmp_path / index["shards"][-1]["path"]
    rows = gzip.decompress(shard.read_bytes()).splitlines(keepends=True)
    last = json.loads(rows[-1])
    if damage == "hash": last["levels"][0] += .001
    elif damage == "axis": last["episode"] = 0
    elif damage == "domain": last["domains"]["D_Q"].pop()
    elif damage == "indices": last["consulted"]["P"][0][1].append(4)
    elif damage == "success": last["success"][0] = 1
    elif damage == "flag": last["uncontacted"]["D_Q"] = not last["uncontacted"]["D_Q"]
    elif damage == "duplicate_site": last["domains"]["X"].append(last["domains"]["X"][0])
    elif damage == "unknown": last["not_allowed"] = 0
    rows[-1] = canonical_bytes(last)
    if damage == "truncate": rows.pop()
    elif damage == "extra": rows.append(rows[-1])
    elif damage == "noncanonical": rows[-1] = json.dumps(last).encode() + b"\n"
    elif damage == "duplicate_key": rows[-1] = b'{"seed":980201,' + rows[-1][1:]
    shard.write_bytes(gzip.compress(b"".join(rows), mtime=0))
    with pytest.raises(ProtocolError): verify_acquisition(path)
    with pytest.raises(ProtocolError): pv.verify_parallel(path, progress_folder=tmp_path / "failed_progress")


@pytest.mark.parametrize("damage", ["escape", "seed_order", "aggregate", "bank"])
def test_bad_index_is_refused_before_starting_workers(tmp_path, material, monkeypatch, damage):
    path, index = fixture_index(tmp_path, material)
    broken = copy.deepcopy(index)
    if damage == "escape": broken["shards"][0]["path"] = "../outside.gz"
    elif damage == "seed_order": broken["seeds"].reverse()
    elif damage == "aggregate": broken["records"] += 1
    elif damage == "bank": broken["bank_digest"] = "0" * 64
    path.write_bytes(canonical_bytes(broken))
    def forbidden(*args, **kwargs): raise AssertionError("invalid index reached spawn")
    monkeypatch.setattr(pv, "ProcessPoolExecutor", forbidden)
    with pytest.raises(ProtocolError): pv.verify_parallel(path)


def test_real_spawn_32_shards_fixed_max16_and_ordered_receipts(tmp_path, material):
    path, index = fixture_index(tmp_path, material, count=32)
    result = pv.verify_parallel(path, progress_folder=tmp_path / "progress")
    assert result["max_workers"] == 16 and result["start_method"] == "spawn"
    assert len({row["pid"] for row in result["shards"]}) >= 2
    assert len({row["pid"] for row in result["shards"]}) <= 16
    assert [row["seed"] for row in result["shards"]] == index["seeds"]
    assert len(list((tmp_path / "progress").glob("*.verified.json"))) == 32
    assert all(row["validator"] == "frozen-_shard_records" for row in result["shards"])


def test_existing_progress_reservation_is_not_reused(tmp_path, material):
    path, _ = fixture_index(tmp_path, material)
    folder = tmp_path / "progress"
    folder.mkdir()
    with pytest.raises(FileExistsError): pv.verify_parallel(path, progress_folder=folder)


def test_index_changed_during_verification_refuses_publication(tmp_path, material, monkeypatch):
    path, _ = fixture_index(tmp_path, material)
    original = pv.file_digest
    calls = 0
    def mutate_after_validation(candidate):
        nonlocal calls
        calls += 1
        if calls == 3: path.write_bytes(path.read_bytes() + b"\n")
        return original(candidate)
    monkeypatch.setattr(pv, "file_digest", mutate_after_validation)
    with pytest.raises(ProtocolError, match="changed"):
        pv.verify_parallel(path)


def test_controller_preregistration_keeps_instrument_and_seed_boundaries():
    reg = json.loads((HERE / "preregistration.json").read_bytes())
    assert reg["source_count"] == 295 and reg["max_workers"] == 16
    assert reg["instrument_changes"] is False and reg["validation_reduction"] is False
    assert reg["scientific_parameter_changes"] is False and reg["automatic_retry"] is False
    assert reg["operational_fixture_exclusions"] == list(range(980200,980232))


def test_instrument_inventory_excludes_only_operational_wrapper_not_science():
    paths = controller.p.source_inventory(ROOT)
    assert len(paths) == 295
    assert controller.p.digest(canonical_bytes(paths)) == "1359a1ae11cf54407a9b976b53219e30134173d255c985908f838cb057171bd2"
    assert "src/rfl_rebuild/b2/baseline_artifact.py" in paths
    assert not any("parallel_verify_20261008" in name for name in paths)


def test_parent_stage_and_full_identity_checks_precede_stop(monkeypatch):
    observed = []
    def refuse(stage, argv):
        observed.append(argv[-1])
        raise ProtocolError("deliberate native no-stop fixture")
    monkeypatch.setattr(controller.p, "run_success", refuse)
    with pytest.raises(ProtocolError, match="fixture"): controller.parent_handover()
    body = observed[0]
    stop = body.index("Stop-Process")
    for guard in ("StartTime.ToUniversalTime().Ticks", "CommandLine -cne", "runtime_completion_verified.json",
                  "smoke_attempt.json", "START full_runtime_integrity", "Parent has a Python child"):
        assert body.index(guard) < stop


def test_science_no_drawing_if_formal_reservation_exists(tmp_path, monkeypatch):
    (tmp_path / "experiments/v03r").mkdir(parents=True)
    (tmp_path / "experiments/v03r/smoke_attempt.json").write_bytes(b"{}")
    monkeypatch.setattr(controller, "ROOT", tmp_path)
    with pytest.raises(ProtocolError, match="reservation"): controller.no_formal()


def test_handover_does_not_relaunch_acquisition_or_modify_frozen_source():
    text = (HERE / "continue_verified.py").read_text(encoding="utf-8")
    assert '"scripts/benchmark_f0_runtime.py"' not in text
    assert "write_text" not in text and "write_bytes" not in text
    assert "EXTERNAL_AUTHENTICATED_READ_ONLY_VERIFICATION_INTERRUPTION" in text
    assert "parent_native_completion_claimed=$false" in text


@pytest.mark.parametrize("exit_code,payload,expected", [
    (0,{"status":"LOCKED","written":True},"F1_LOCKED_REQUIRES_NEXT_STAGE_REVIEW"),
    (3,{"status":"NO_ADMISSIBLE_T","written":False},"VALID_PROTOCOL_STOP_NO_ADMISSIBLE_DESIGN"),
])
def test_frozen_f1_stop_classification_unchanged(exit_code,payload,expected):
    assert controller.p.classify_lock(exit_code,payload) == expected
