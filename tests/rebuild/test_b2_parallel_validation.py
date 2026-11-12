"""Engineering fixtures only: same frozen parser, full checks, no scientific draws."""
import copy
from dataclasses import replace
from fractions import Fraction
import gzip
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
from rfl_rebuild.b2 import parallel_validation as pv
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
