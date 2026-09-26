"""Stage barriers and real short operational streams; no formal seeds are drawn."""
import copy
import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2 import f0_stages as f0
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, digest, verify_acquisition

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("f0_check_fixture", ROOT / "scripts/f0_manifest_selfcheck.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


@pytest.mark.parametrize("path,value,expected", check.CASES)
def test_contract_mutations(path, value, expected):
    manifest = check.fixture()
    target = manifest
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ProtocolError, match=expected):
        f0.validate_contract(manifest)


def report_for(manifest, identity="d" * 64):
    return {"stage": "smoke", "seeds": list(f0.STAGE_SEEDS["smoke"]),
            "tree": {"instrument_commit": manifest["instrument_commit"], "manifest_sha256": identity},
            "runtime_s": 1., "gate_exit_codes": [0] * 6, "artifact_paths": list(f0.GATE_PATHS),
            "artifact_digests": manifest["expected_gate_artifacts"], "errors": [], "fallbacks": []}


@pytest.mark.parametrize("field,value,reason", [
    ("efficacy", .99, "SMOKE_FIELD_SET"), ("seeds", [False, 1, 2, 3, 4], "STAGE_OR_SEEDS"),
    ("tree", {}, "EXECUTION_IDENTITY"), ("gate_exit_codes", [False] * 6, "GATE_EXIT_CODES"),
    ("artifact_digests", {}, "GATE_ARTIFACT_DIGESTS"), ("errors", ["failure"], "ERROR_OR_FALLBACK"),
    ("fallbacks", ["retry"], "ERROR_OR_FALLBACK"), ("runtime_s", float("nan"), "INVALID_RUNTIME"),
    ("runtime_s", 23., "RUNTIME_EXCEEDED"),
])
def test_smoke_closed_report(field, value, reason):
    manifest = check.fixture()
    report = report_for(manifest)
    assert f0.evaluate_smoke(report, manifest, "d" * 64)["verdict"] == "PASS"
    report[field] = value
    assert f0.evaluate_smoke(report, manifest, "d" * 64)["reason"] == reason


def test_seedless_selfcheck_and_duplicate_json(tmp_path):
    assert check.selfcheck()["n_rejected"] == 26
    path = tmp_path / "bad.json"
    path.write_text('{"status": "VALID", "status": "NOT_VALID"}')
    with pytest.raises(ProtocolError, match="duplicate JSON"):
        f0.read_json(path)


def test_draft_refuses_before_source_or_seed_access(tmp_path, monkeypatch):
    manifest = check.fixture()
    manifest.update(status="NOT_VALID", currently_authorises=[], blockers=["review"])
    path = tmp_path / "draft.json"
    path.write_bytes(canonical_bytes(manifest))
    monkeypatch.setattr(f0, "records_for", lambda *a: pytest.fail("seed draw before authorization"))
    for runner in (f0.run_smoke, f0.run_baseline):
        with pytest.raises(ProtocolError, match="NOT VALID"):
            runner(tmp_path, manifest_path=path, seeds_file=tmp_path / "absent", plan_only=True)
    assert list(tmp_path.iterdir()) == [path]


def test_git_blob_identity_checks_raw_bytes(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    path = tmp_path / "instrument.py"
    path.write_bytes(b"original\n")
    subprocess.run(["git", "-c", "core.autocrlf=false", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "test fixture"], cwd=tmp_path, check=True)
    assert f0._committed_sources(tmp_path, "HEAD", (path.name,))[path.name] == digest(b"original\n")
    path.write_bytes(b"changed\n")
    assert f0._committed_sources(tmp_path, "HEAD", (path.name,))[path.name] != digest(path.read_bytes())
    with pytest.raises(ProtocolError, match="not committed"):
        f0._committed_sources(tmp_path, "HEAD", ("missing.py",))


def operational_fixture(tmp_path, monkeypatch):
    """Only pytest bypasses F0 for cap=2 and engineering keys in an empty temp dir."""
    manifest = check.fixture()
    manifest["constants"]["acquisition_cap"] = 2
    for stage in f0.STAGE_SEEDS:
        manifest["runtime"][stage]["bound_s"] = 3600.
    keys = {"smoke": (960001,), "dev_baseline": (960002,)}
    monkeypatch.setattr(f0, "STAGE_SEEDS", keys)
    for name in f0.GATE_PATHS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'{}\n')
    manifest["expected_gate_artifacts"] = {name: digest((tmp_path / name).read_bytes()) for name in f0.GATE_PATHS}
    monkeypatch.setattr(f0, "stage_inputs", lambda root, **kw: (manifest, "d" * 64, keys[kw["stage"]]))
    monkeypatch.setattr(f0, "load_manifest", lambda *a: (manifest, "d" * 64))
    monkeypatch.setattr(f0, "run_gate_suite", lambda *a: [0] * 6)
    return manifest


def test_real_short_stage_stream_and_receipt_binding(tmp_path, monkeypatch):
    manifest = operational_fixture(tmp_path, monkeypatch)
    kwargs = {"manifest_path": tmp_path / "unused", "seeds_file": tmp_path / "unused"}
    result = f0.run_smoke(tmp_path, **kwargs)
    assert result["verdict"] == "PASS"
    report = f0.read_json(tmp_path / f0.SMOKE_PATH)
    assert set(report) == f0.SMOKE_FIELDS  # no outcome values saved by smoke
    result = f0.run_baseline(tmp_path, **kwargs)
    index = verify_acquisition(Path(result["path"]))
    assert index["records"] == 3 and index["seeds"] == [960002]
    assert index["execution"]["smoke_report_sha256"] == digest((tmp_path / f0.SMOKE_PATH).read_bytes())
    with pytest.raises(ProtocolError, match="no automatic rerun"):
        f0.run_baseline(tmp_path, **kwargs)
    with pytest.raises(ProtocolError, match="spent seeds"):
        f0.run_smoke(tmp_path, **kwargs)


def test_failed_gate_and_interrupted_attempt_never_draw(tmp_path, monkeypatch):
    operational_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(f0, "run_gate_suite", lambda *a: [1, 0, 0, 0, 0, 0])
    monkeypatch.setattr(f0, "records_for", lambda *a: pytest.fail("training after failed gate"))
    kwargs = {"manifest_path": tmp_path / "unused", "seeds_file": tmp_path / "unused"}
    assert f0.run_smoke(tmp_path, **kwargs)["verdict"] == "FAIL"
    with pytest.raises(ProtocolError, match="smoke not PASS"):
        f0.run_baseline(tmp_path, **kwargs)
    (tmp_path / f0.SMOKE_PATH).unlink()  # simulate interrupted report, keep spent-attempt reservation
    with pytest.raises(FileExistsError):
        f0.run_smoke(tmp_path, **kwargs)


def test_plan_never_runs_and_baseline_requires_receipt(tmp_path, monkeypatch):
    manifest = operational_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(f0, "records_for", lambda *a: pytest.fail("plan ran training"))
    kwargs = {"manifest_path": tmp_path / "unused", "seeds_file": tmp_path / "unused", "plan_only": True}
    assert f0.run_smoke(tmp_path, **kwargs)["written"] is False
    with pytest.raises(ProtocolError, match="cannot read JSON"):
        f0.run_baseline(tmp_path, **kwargs)
    (tmp_path / f0.SMOKE_PATH).write_bytes(canonical_bytes(report_for(manifest)))
    assert f0.run_baseline(tmp_path, **kwargs)["written"] is False
    assert not (tmp_path / f0.ARTIFACT_SCHEMA["index"]).exists()


def test_incomplete_discard_and_extra_records():
    row = SimpleNamespace(seed=960001, episode=0)
    with pytest.raises(ProtocolError, match="before its full envelope"):
        f0.discard_complete([row], (960001,), 1)
    with pytest.raises(ProtocolError, match="exceeded its envelope"):
        f0.discard_complete([row, row], (960001,), 0)
    with pytest.raises(ProtocolError, match="axis mismatch"):
        f0.discard_complete([row], (960002,), 0)


def test_gate_suite_frozen_serial_order(monkeypatch, tmp_path):
    calls = []
    def run(argv, **kwargs):
        calls.append(argv[1:])
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(f0.subprocess, "run", run)
    assert f0.run_gate_suite(tmp_path) == [0] * 6
    assert calls == [g["argv"][1:] for g in f0.GATES]


def test_live_manifest_committed_inventory_and_drift(tmp_path):
    manifest = check.fixture()
    for stage, name in f0.SEED_PATHS.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("\n".join(map(str, f0.STAGE_SEEDS[stage])) + "\n").encode())
        manifest["seed_files"][stage]["sha256"] = digest(path.read_bytes())
    for name in f0.GATE_PATHS:
        (tmp_path / name).write_bytes(b'{}\n')
        manifest["expected_gate_artifacts"][name] = digest(b'{}\n')
    manifest["calibration_sha256"] = digest(b'{}\n')
    instrument = tmp_path / "src/instrument.py"
    instrument.parent.mkdir()
    instrument.write_bytes(b"# fixture\n")
    sources = f0.source_inventory(tmp_path)
    identity = digest(canonical_bytes(sources))
    manifest.update(sources=sources, sources_digest=identity)
    manifest["runtime"]["sources_digest"] = identity
    manifest["review"]["sources_digest"] = identity
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    def commit():
        subprocess.run(["git", "-c", "core.autocrlf=false", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    commit()
    manifest["instrument_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    path = tmp_path / f0.MANIFEST_PATH
    path.write_bytes(canonical_bytes(manifest))
    with pytest.raises(ProtocolError, match="must be committed"):
        f0.load_manifest(tmp_path, path, "smoke")
    commit()
    assert f0.load_manifest(tmp_path, path, "smoke")[1] == digest(path.read_bytes())
    instrument.write_bytes(b"# modified\n")
    with pytest.raises(ProtocolError, match="inventory or hash changed"):
        f0.load_manifest(tmp_path, path, "smoke")
    instrument.write_bytes(b"# fixture\n")
    (tmp_path / "src/extra.py").write_bytes(b"# added\n")
    with pytest.raises(ProtocolError, match="inventory or hash changed"):
        f0.load_manifest(tmp_path, path, "smoke")


def test_baseline_postcheck_failure_never_publishes_index(tmp_path, monkeypatch):
    manifest = operational_fixture(tmp_path, monkeypatch)
    manifest["constants"]["acquisition_cap"] = 1
    (tmp_path / f0.SMOKE_PATH).write_bytes(canonical_bytes(report_for(manifest)))
    monkeypatch.setattr(f0, "load_manifest", lambda *a: (manifest, "changed"))
    with pytest.raises(ProtocolError, match="manifest changed during baseline"):
        f0.run_baseline(tmp_path, manifest_path=tmp_path / "unused", seeds_file=tmp_path / "unused")
    index = tmp_path / f0.ARTIFACT_SCHEMA["index"]
    assert not index.exists()
    assert index.with_suffix("").is_dir()  # partial evidence kept; no silent retry
