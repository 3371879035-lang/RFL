"""Real C3 acquisition round trip and fail-closed artifact boundary."""
import copy
import gzip
import json
import pathlib
import sys
from fractions import Fraction
from types import MappingProxyType

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.acquisition import MasterBaseline, acquire_master_baseline, iter_master_baseline
from rfl_rebuild.b2.baseline_artifact import (
    canonical_bytes, digest, iter_verified_material, material_from_record, record_from_material,
    verify_acquisition, write_acquisition,
)
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.temporal_initializer import INITIALIZER_ID, layer_edits, temporal_initializer
from rfl_rebuild.b2.training import BaselineAcquisitionPlan, FutureTrainingProtocol, train_curve
from rfl_rebuild.b2.unaffected import CHANNELS, REFINEMENTS
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference

REFERENCE = reference_view_from(solve_reference())
KEY = 940001
PLAN = BaselineAcquisitionPlan(KEY, Fraction(1, 2), Fraction(1, 10), 2, prefix(100))


@pytest.fixture(scope="module")
def acquired():
    return acquire_master_baseline(PLAN, seeds=(KEY,), q_reference=REFERENCE,
                                   initializer=temporal_initializer)


def write(path, acquired, records=None):
    return write_acquisition(path, plan=PLAN, seeds=(KEY,), records=(
        iter(acquired.runs.values()) if records is None else records),
        constants={"initializer": INITIALIZER_ID}, execution={"role": "test_fixture"},
        role="OPERATIONAL_REHEARSAL")


def test_named_initializer_matches_preserved_pre_acquisition_c3_artifact():
    frozen = json.loads((ROOT / "experiments/v03r/c3_construction/seedless.json").read_text())
    expected = {row["address"]: row["value"] for row in frozen["exact_edits"]}
    learner = temporal_initializer(REFERENCE)
    assert {repr(k): v for k, v in learner.q_overrides.items()} == expected
    assert len(expected) == 840
    for store in (learner.decision_overrides, learner.controller_overrides, learner.process_overrides):
        assert not store
    assert temporal_initializer(REFERENCE) is not learner


@pytest.mark.parametrize("layer", [-1, 12, True, 1.0])
def test_invalid_layer_is_refused(layer):
    with pytest.raises(ProtocolError):
        layer_edits(REFERENCE, layer)


def test_real_c3_acquisition_is_a91_curve_not_a_healthy_replacement(acquired):
    protocol = FutureTrainingProtocol(KEY, PLAN.alpha, PLAN.epsilon, 2, (0, 1, 2), PLAN.evaluation_bank, 1.0)
    curve = train_curve(temporal_initializer(REFERENCE), protocol=protocol, q_reference=REFERENCE)
    assert acquired.mean_curve(KEY) == tuple(curve.values)
    assert acquired.mean_curve(KEY)[0] < .95 * .75
    assert len(acquired.domain("D_Q", KEY, 0)) == 13824
    from rfl_rebuild.b2.acquisition import _run_material
    tiny = _run_material(temporal_initializer(REFERENCE), seed=KEY, episode=0,
                         sample=prefix(1), q_reference=REFERENCE)
    assert tiny.domains["X"] == acquired.domain("X", KEY, 0)
    assert len(tiny.domains["X"]) > len(tiny.consulted["X"])


def test_round_trip_preserves_domains_incidence_values_and_cf1_errors(tmp_path, acquired):
    path = tmp_path / "baseline.json"
    index = write(path, acquired)
    assert verify_acquisition(path) == index
    rows = {(r.seed, r.episode): r for r in iter_verified_material(path)}
    restored = MasterBaseline(acquired.seeds, acquired.episodes, acquired.sample, MappingProxyType(rows))
    for key, original in acquired.runs.items():
        run = rows[key]
        assert run == original
        for arch in CHANNELS:
            # Every incidence entry and the complete domain above are equal. Exercise
            # downstream value-based SE on both contacted and uncontacted sites.
            sites = list(original.consulted[arch])[:2]
            sites += [s for s in original.domains[arch] if s not in original.consulted[arch]][:1]
            for site in sites:
                for refinement in REFINEMENTS:
                    assert restored.slice_indices(arch, *key, site, refinement) == acquired.slice_indices(
                        arch, *key, site, refinement)
                    assert restored.error(arch, *key, site, refinement) == acquired.error(
                        arch, *key, site, refinement)


def test_gzip_is_deterministic_and_container_bytes_are_not_the_normative_hash(tmp_path, acquired):
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    a, b = write(one, acquired), write(two, acquired)
    p, q = tmp_path / a["shards"][0]["path"], tmp_path / b["shards"][0]["path"]
    assert p.read_bytes() == q.read_bytes()
    assert p.read_bytes()[4:8] == bytes(4)  # mtime zero
    data = gzip.decompress(p.read_bytes())
    assert digest(data) == a["shards"][0]["sha256"]
    assert digest(p.read_bytes()) != a["shards"][0]["sha256"]
    p.write_bytes(gzip.compress(data, compresslevel=1, mtime=123))
    assert verify_acquisition(one) == a


@pytest.mark.parametrize("damage", ["hash", "truncate", "extra", "noncanonical", "axis", "nan"])
def test_damaged_shard_yields_no_material(tmp_path, acquired, damage):
    path = tmp_path / "baseline.json"
    index = write(path, acquired)
    shard = tmp_path / index["shards"][0]["path"]
    lines = gzip.decompress(shard.read_bytes()).splitlines(keepends=True)
    last = json.loads(lines[-1])
    if damage == "hash":
        last["levels"][0] += .001
        lines[-1] = canonical_bytes(last)
    elif damage == "truncate":
        lines.pop()
    elif damage == "extra":
        lines.append(lines[-1])
    elif damage == "noncanonical":
        lines[-1] = json.dumps(last, indent=1).encode() + b"\n"
    elif damage == "axis":
        last["episode"] = 0
        lines[-1] = canonical_bytes(last)
    elif damage == "nan":
        last["levels"][0] = float("nan")
        lines[-1] = json.dumps(last).encode() + b"\n"
    shard.write_bytes(gzip.compress(b"".join(lines), mtime=0))
    with pytest.raises(ProtocolError):
        next(iter_verified_material(path))


@pytest.mark.parametrize("damage", ["narrow_domain", "index_bounds", "duplicate_indices", "bool_ordinal",
                                     "flag", "success", "duplicate_site", "unknown_field"])
def test_structural_mutations_are_rejected_independently_of_hash(acquired, damage):
    row = copy.deepcopy(record_from_material(acquired.material(KEY, 0)))
    if damage == "narrow_domain":
        row["domains"]["D_Q"].pop()
    elif damage == "index_bounds":
        row["consulted"]["P"][0][1].append(100)
    elif damage == "duplicate_indices":
        row["consulted"]["P"][0][1].append(row["consulted"]["P"][0][1][0])
    elif damage == "bool_ordinal":
        row["consulted"]["P"][0][0] = False
    elif damage == "flag":
        row["uncontacted"]["D_Q"] = not row["uncontacted"]["D_Q"]
    elif damage == "success":
        row["success"][0] = 1
    elif damage == "duplicate_site":
        row["domains"]["X"].append(row["domains"]["X"][0])
    else:
        row["unexpected"] = 0
    with pytest.raises(ProtocolError):
        material_from_record(row, seed=KEY, episode=0, bank_size=100)


def test_later_bad_shard_is_checked_before_first_seed_is_exposed(tmp_path, acquired):
    from dataclasses import replace
    path = tmp_path / "baseline.json"
    records = list(acquired.runs.values())
    # This is an explicit artifact fixture, not acquisition under a second seed.
    records += [replace(r, seed=KEY + 1) for r in records]
    index = write_acquisition(path, plan=PLAN, seeds=(KEY, KEY + 1), records=records,
                              constants={}, execution={}, role="OPERATIONAL_REHEARSAL")
    (tmp_path / index["shards"][-1]["path"]).write_bytes(b"broken")
    with pytest.raises(ProtocolError):
        next(iter_verified_material(path))


def test_partial_stream_never_publishes_index_and_outputs_are_never_overwritten(tmp_path, acquired):
    path = tmp_path / "baseline.json"
    with pytest.raises(ProtocolError, match="ended"):
        write(path, acquired, iter(list(acquired.runs.values())[:1]))
    assert not path.exists()
    with pytest.raises(FileExistsError):
        write(path, acquired)


def test_path_traversal_is_refused_before_opening_a_shard(tmp_path, acquired):
    path = tmp_path / "baseline.json"
    index = write(path, acquired)
    index["shards"][0]["path"] = "../elsewhere.jsonl.gz"
    path.write_bytes(canonical_bytes(index))
    with pytest.raises(ProtocolError, match="path"):
        verify_acquisition(path)


def test_reusing_a_mutable_initializer_across_seeds_is_refused(monkeypatch):
    import rfl_rebuild.b2.acquisition as module
    # No trajectory needed: test the cross-seed ownership boundary alone.
    monkeypatch.setattr(module, "_run_material", lambda *a, **k: k)
    monkeypatch.setattr(module, "episode_rollout", lambda *a, **k: None)
    monkeypatch.setattr(module, "sweep_edits", lambda *a, **k: ())
    reused = LearnerPersistentState()
    with pytest.raises(ProtocolError, match="reused"):
        list(iter_master_baseline(PLAN, seeds=(KEY, KEY + 1), q_reference=REFERENCE,
                                  initializer=lambda ref: reused))


@pytest.mark.parametrize("seeds", [(-1,), (True,), (KEY, KEY)])
def test_invalid_seed_axes_are_rejected(seeds):
    with pytest.raises(ProtocolError):
        next(iter_master_baseline(PLAN, seeds=seeds, q_reference=REFERENCE,
                                  initializer=temporal_initializer))


def test_preflight_refuses_to_promote_an_operational_artifact(tmp_path, acquired):
    sys.path.insert(0, str(ROOT / "scripts"))
    from inspect_dev_baseline import inspect
    path = tmp_path / "baseline.json"
    write(path, acquired)
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    result = inspect(path)
    assert result["artifact_valid"] is True
    assert result["ready_for_design_lock"] is False
    assert "OPERATIONAL_DATA_IS_NOT_DEVELOPMENT_DATA" in result["blockers"]
    assert result["design_metrics_computed"] is False
    assert result["f1_lock_written"] is False
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before


def test_rehearsal_plan_draws_no_episode_and_writes_nothing(monkeypatch, tmp_path, capsys):
    sys.path.insert(0, str(ROOT / "scripts"))
    import f0_acquisition_rehearsal as rehearsal
    def forbidden(*args, **kwargs):
        raise AssertionError("plan mode entered acquisition")
    monkeypatch.setattr(rehearsal, "iter_master_baseline", forbidden)
    monkeypatch.setattr(rehearsal, "OUT", tmp_path / "must-not-exist")
    monkeypatch.setattr(sys, "argv", ["f0_acquisition_rehearsal.py", "--plan"])
    assert rehearsal.main() == 0
    assert not rehearsal.OUT.exists()
    assert json.loads(capsys.readouterr().out)["scientific_seeds"] == []
