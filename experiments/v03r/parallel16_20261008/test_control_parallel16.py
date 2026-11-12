"""Preparation and switch refusal tests; never stop a real process."""
import importlib.util
from pathlib import Path
import pytest

PATH = Path(__file__).with_name("control_parallel16.py")
SPEC = importlib.util.spec_from_file_location("p16_control_fixture", PATH)
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


def test_profile_is_explicit_and_sixteen():
    registration = control.p.read_json(PATH.with_name("preregistration.json"))
    assert registration["execution_profile"] == control.EXECUTION_PROFILE
    assert len(registration["fresh_smoke_seeds"]) == 5
    assert set(registration["construction_test_keys"]).isdisjoint(registration["fresh_smoke_seeds"])


def test_repeat_preparation_refuses_before_parent_or_draw(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "HERE", tmp_path)
    (tmp_path / "control_claim.json").write_text("{}")
    monkeypatch.setattr(control, "parent_snapshot", lambda: pytest.fail("repeat preparation inspected parent"))
    with pytest.raises(control.p.ProtocolError, match="already reserved"):
        control.validate_preparation()


def test_parent_spent_reservation_refuses_before_native_stop(monkeypatch):
    def spent():
        raise control.p.ProtocolError("parent scientific reservation exists")
    monkeypatch.setattr(control, "parent_snapshot", spent)
    monkeypatch.setattr(control.subprocess, "run", lambda *a, **k: pytest.fail("native stop after spent reservation"))
    with pytest.raises(control.p.ProtocolError, match="reservation exists"):
        control.controlled_switch()


def test_review_failure_never_switches(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "HERE", tmp_path)
    monkeypatch.setattr(control, "validate_preparation", lambda: ({}, "a"*40, {}, set()))
    def fail(*args):
        raise control.p.ProtocolError("review failed")
    monkeypatch.setattr(control, "prepare_review", fail)
    monkeypatch.setattr(control, "controlled_switch", lambda: pytest.fail("switch after failed review"))
    # Main also binds operational scripts. Supply their bytes only in this temp fixture.
    (tmp_path / "control_parallel16.py").write_text("fixture")
    (tmp_path / "continue_pipeline.py").write_text("fixture")
    assert control.main() == 2
    assert control.p.read_json(tmp_path / "pipeline_failure.json")["parent_switch_recorded"] is False


def test_legacy_runtime_is_not_accepted():
    from rfl_rebuild.b2.f0_stages import validate_runtime
    with pytest.raises(control.p.ProtocolError, match="execution profile"):
        validate_runtime({"schema":"f0-runtime-v1", "sources_digest":"a"*64}, "a"*64)
