"""Restart-only guards; no scientific draws or live process termination."""
import importlib.util
import json
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("shutdown_restart_fixture_controller", HERE / "resume_after_shutdown.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
from rfl_rebuild.b1.errors import ProtocolError

@pytest.mark.parametrize("name", ["pipeline_exit.json", "parallel_verification.receipt.json",
    "parallel_verification.json", "runtime_completion_verified.json", "pipeline_result.json", "pipeline_failure.json"])
def test_advanced_or_completed_parent_is_refused(tmp_path, name):
    (tmp_path / name).touch()
    with pytest.raises(ProtocolError, match="advanced"): c.reject_native_completion(tmp_path)

def test_empty_interrupted_parent_does_not_claim_completion(tmp_path):
    c.reject_native_completion(tmp_path)

def test_existing_task_refuses_restart():
    with pytest.raises(ProtocolError, match="duplicate"): c.reject_live_tree([{"pid":123}])

def test_no_existing_task_is_allowed():
    c.reject_live_tree([])

def test_preservation_byte_damage_is_refused(tmp_path):
    path = tmp_path / "receipt.json"
    path.write_bytes(b"original")
    saved = {"receipt.json":c.p.digest(path.read_bytes())}
    c.verify_saved(saved, tmp_path)
    path.write_bytes(b"changed")
    with pytest.raises(ProtocolError, match="drift"): c.verify_saved(saved, tmp_path)

def test_preservation_path_escape_refused(tmp_path):
    with pytest.raises(ProtocolError, match="escape"): c.verify_saved({"../bad":"0"*64}, tmp_path)

def test_scientific_population_and_source_identity_not_changed():
    reg = json.loads((HERE / "preregistration.json").read_bytes())
    assert reg["source_count"] == 295 and reg["max_workers"] == 16
    assert reg["acquisition_restart"] is False and reg["scientific_seed_change"] is False
    assert reg["automatic_retry"] is False and reg["instrument_changes"] is False
    assert c.p.digest(c.p.canonical_bytes(c.p.source_inventory(c.ROOT))) == reg["expected_sources_digest"]
    src = (HERE / "resume_after_shutdown.py").read_text(encoding="utf-8")
    assert "Stop-Process" not in src and "benchmark_f0_runtime.py" not in src
    assert "v.continue_science(identity)" in src

def test_new_review_and_f0_paths_are_exclusive():
    assert c.p.REVIEW.parent == HERE and c.p.MANIFEST.parent == HERE
    assert c.p.HERE == HERE and c.PREVIOUS != HERE
    assert not (c.PREVIOUS / c.p.MANIFEST.name).exists()

def test_metadata_commit_not_source_drift():
    assert c.same_inputs({"head":"a","x":1}, {"head":"b","x":1})
    assert not c.same_inputs({"head":"a","x":1}, {"head":"b","x":2})
