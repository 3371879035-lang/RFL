"""External monitor tests; not added to the running instrument's test inventory."""
import copy
import importlib.util
import json
import os
import pathlib
import pytest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("runtime_inspector", HERE / "inspect_runtime_rev5.py")
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)
ProtocolError = inspector.ProtocolError


def test_metadata_only_lower_bound_never_promotes_last_file(tmp_path):
    for i, key in enumerate(range(950006, 950010)):
        path = tmp_path / f"seed-{key}.jsonl.gz"
        path.write_bytes(b"NOT GZIP: metadata scan must not open outcome payload")
        os.utime(path, (1000 + i * 600, 1000 + i * 600))
    report = inspector.scan_progress(tmp_path, list(range(950006, 950038)))
    assert report["completed_dev_runs_lower_bound"] == 3
    assert report["shards_visible"] == 4
    assert report["rough_remaining_dev_seconds"] == 29 * 600
    assert report["hashes_verified"] is False
    assert report["outcome_payloads_opened"] is False
    assert "NOT GZIP" not in json.dumps(report)


def test_empty_or_single_shard_cannot_prove_completion(tmp_path):
    keys = [950006, 950007]
    assert inspector.scan_progress(tmp_path, keys)["completed_dev_runs_lower_bound"] == 0
    (tmp_path / "seed-950006.jsonl.gz").write_bytes(b"growing")
    result = inspector.scan_progress(tmp_path, keys)
    assert result["completed_dev_runs_lower_bound"] == 0
    assert result["rough_remaining_dev_seconds"] is None


@pytest.mark.parametrize("name", ["seed-950007.jsonl.gz", "unexpected.gz"])
def test_gap_or_extra_file_is_refused(tmp_path, name):
    (tmp_path / name).write_bytes(b"x")
    with pytest.raises(ProtocolError):
        inspector.scan_progress(tmp_path, [950006, 950007])


def fixture():
    check_spec = importlib.util.spec_from_file_location("f0_runtime_fixture", inspector.ROOT / "scripts/f0_manifest_selfcheck.py")
    check = importlib.util.module_from_spec(check_spec); check_spec.loader.exec_module(check)
    manifest = check.fixture()
    frozen = {"sources": manifest["sources"], "sources_digest": manifest["sources_digest"],
              "instrument_commit": manifest["instrument_commit"], "constants": manifest["constants"],
              "keys": copy.deepcopy(inspector.EXPECTED_KEYS)}
    runtime = manifest["runtime"]
    for stage, keys in inspector.EXPECTED_KEYS.items():
        runtime[stage]["keys"] = keys.copy()
    gates = manifest["expected_gate_artifacts"]
    runtime.update(instrument_commit=frozen["instrument_commit"], gate_artifact_digests=gates)
    index = {"role": "OPERATIONAL_REHEARSAL", "seeds": frozen["keys"]["dev_baseline"],
             "episodes": list(range(577)), "bank_size": 1024, "constants": frozen["constants"],
             "execution": {"head_commit": frozen["instrument_commit"], "sources": frozen["sources"]},
             "records": 18464}
    return frozen, runtime, index, gates


def test_metadata_agrees_without_approving_f0():
    assert inspector.verify_metadata(*fixture()) is None


@pytest.mark.parametrize("object_index,path,value", [
    (1, ("instrument_commit",), "b" * 40),
    (1, ("gate_artifact_digests",), {}),
    (1, ("smoke", "keys"), list(range(960001, 960006))),
    (1, ("dev_baseline", "bound_s"), 999.),
    (2, ("role",), "DEVELOPMENT_BASELINE"),
    (2, ("records",), 32),
    (2, ("execution", "head_commit"), "b" * 40),
    (2, ("episodes",), [0, 1, 2]),
])
def test_forged_or_mismatched_completion_refused(object_index, path, value):
    data = fixture()
    target = data[object_index]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ProtocolError):
        inspector.verify_metadata(*data)


def test_final_verify_refuses_incomplete_before_full_shard_read(tmp_path, monkeypatch):
    monkeypatch.setattr(inspector, "frozen_inputs", lambda root: fixture()[0])
    monkeypatch.setattr(inspector, "verify_acquisition", lambda path: pytest.fail("incomplete run reached full verifier"))
    with pytest.raises(ProtocolError, match="not complete"):
        inspector.inspect(tmp_path, verify=True)


@pytest.mark.parametrize("mutation", [None, "runtime", "index", "gate"])
def test_verification_orchestration_and_artifact_drift(tmp_path, monkeypatch, mutation):
    """Exercise the wrapper; full shard/schema validation belongs to its verifier.

    Synthetic evidence here is never presented as an actual completed acquisition.
    """
    import rfl_rebuild.b2.baseline_artifact as artifacts
    frozen, runtime, index, _ = fixture()
    directory = tmp_path / "experiments/v03r/f0_runtime_rev5"
    directory.mkdir(parents=True)
    for name in inspector.GATE_PATHS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic gate")
    runtime["gate_artifact_digests"] = {
        name: inspector.digest((tmp_path / name).read_bytes()) for name in inspector.GATE_PATHS}
    (directory / "runtime.json").write_text(json.dumps(runtime), encoding="utf-8")
    (directory / "baseline.json").write_text(json.dumps(index), encoding="utf-8")
    monkeypatch.setattr(inspector, "frozen_inputs", lambda root: frozen)
    monkeypatch.setattr(artifacts, "read_index", lambda path: json.loads(path.read_text(encoding="utf-8")))
    calls = []

    def fake_full_verifier(path):
        calls.append(path)
        if mutation is not None:
            target = {"runtime": directory / "runtime.json", "index": directory / "baseline.json",
                      "gate": tmp_path / inspector.GATE_PATHS[0]}[mutation]
            target.write_bytes(target.read_bytes() + b" ")
        return index

    monkeypatch.setattr(inspector, "verify_acquisition", fake_full_verifier)
    if mutation:
        with pytest.raises(ProtocolError, match="changed during verification"):
            inspector.inspect(tmp_path, verify=True)
    else:
        result = inspector.inspect(tmp_path, verify=True)
        assert result["status"] == "MEASURED_AND_VERIFIED"
        assert result["verified_dev_runs"] == 32
        assert result["all_shards_verified"] is True
        assert result["f0_valid"] is False
        assert result["formal_stage_authorized"] is False
        assert result["metrics_computed"] is False
    assert calls == [directory / "baseline.json"]
