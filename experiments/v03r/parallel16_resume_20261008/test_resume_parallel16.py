"""Transport and explicit-reservation tests; never stop a real parent process."""
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import pytest

PATH = Path(__file__).with_name("resume_parallel16.py")
SPEC = importlib.util.spec_from_file_location("p16_resume_controller_fixture", PATH)
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


def test_explicit_new_authority_and_unchanged_population():
    registration = control.p.read_json(PATH.with_name("preregistration.json"))
    control.p.validate_restart_population(registration)
    assert registration["execution_profile"] == control.runner.EXECUTION_PROFILE
    assert registration["automatic_retry"] is False
    assert registration["frozen_source_count"] == 295


def test_controller_never_stops_a_parent():
    source = PATH.read_text(encoding="utf-8")
    assert "Stop-Process" not in source
    assert "taskkill" not in source
    assert "text=True, timeout=70" not in source


def test_chinese_native_stdout_is_exact_utf8(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "HERE", tmp_path)
    value = "D:/强化反馈学习/中文回执"
    actual = control.native_observation("unicode", "@{role='READ_ONLY_ENCODING_PROBE';path='"+value+"'} | ConvertTo-Json -Compress")
    assert actual["path"] == value
    assert (tmp_path / "unicode.stdout.bin").read_bytes().decode("utf-8")
    assert control.p.read_json(tmp_path / "unicode.receipt.json")["native_exit_code"] == 0


@pytest.mark.parametrize("raw", [b'\xbb', b'not JSON', b'[]'])
def test_invalid_native_output_preserved_and_not_published(raw, tmp_path, monkeypatch):
    monkeypatch.setattr(control, "HERE", tmp_path)
    def fake(argv, **kwargs):
        assert "text" not in kwargs and "encoding" not in kwargs
        kwargs["stdout"].write(raw)
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(control.subprocess, "run", fake)
    with pytest.raises(control.p.ProtocolError):
        control.native_observation("invalid", "fixture")
    assert (tmp_path / "invalid.stdout.bin").read_bytes() == raw
    assert (tmp_path / "invalid.receipt.json").is_file()
    assert not (tmp_path / "invalid.observation.json").exists()


def test_nonzero_native_output_has_receipt_before_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "HERE", tmp_path)
    def fail(argv, **kwargs):
        kwargs["stderr"].write(b'\xbb native error')
        return subprocess.CompletedProcess(argv, 7)
    monkeypatch.setattr(control.subprocess, "run", fail)
    with pytest.raises(control.p.ProtocolError, match="native observation failed"):
        control.native_observation("failed", "fixture")
    assert control.p.read_json(tmp_path / "failed.receipt.json")["native_exit_code"] == 7
    assert (tmp_path / "failed.stderr.bin").read_bytes() == b'\xbb native error'


def test_timeout_preserves_raw_and_native_timeout_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "HERE", tmp_path)
    def timeout(argv, **kwargs):
        kwargs["stdout"].write(b'partial')
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
    monkeypatch.setattr(control.subprocess, "run", timeout)
    with pytest.raises(control.p.ProtocolError, match="timed out"):
        control.native_observation("timeout", "fixture")
    assert control.p.read_json(tmp_path / "timeout.receipt.json")["timeout"] is True
    assert (tmp_path / "timeout.stdout.bin").read_bytes() == b'partial'


def test_repeat_transport_refuses_before_process(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "HERE", tmp_path)
    (tmp_path / "duplicate.stdout.bin").write_bytes(b'prior')
    monkeypatch.setattr(control.subprocess, "run", lambda *a, **k: pytest.fail("duplicate native process"))
    with pytest.raises(FileExistsError):
        control.native_observation("duplicate", "fixture")
    assert (tmp_path / "duplicate.stdout.bin").read_bytes() == b'prior'


def test_repeat_controller_reservation_refuses_before_parent_check(tmp_path, monkeypatch):
    monkeypatch.setattr(control, "HERE", tmp_path)
    (tmp_path / "control_claim.json").write_text("{}")
    monkeypatch.setattr(control.runner, "verify_parent_preserved", lambda: pytest.fail("duplicate inspected parent"))
    with pytest.raises(control.p.ProtocolError, match="already reserved"):
        control.validate_preparation()


def test_competing_process_refuses_without_stop(monkeypatch):
    monkeypatch.setattr(control, "native_observation", lambda *a: {
        "role":"NATIVE_READ_ONLY_PROCESS_SNAPSHOT", "no_stop_performed":True, "processes":[{"ProcessId":123}]})
    with pytest.raises(control.p.ProtocolError, match="competing"):
        control.require_no_competing_process()


def test_actual_detached_wmi_chinese_roundtrip(tmp_path, monkeypatch):
    """Actual WMI child, exact Chinese JSON bytes; no scientific stream or stop."""
    monkeypatch.setattr(control, "HERE", tmp_path)
    folder = tmp_path / "中文后台传输"
    folder.mkdir()
    output = folder / "原生观察.json"
    # Exercise the SAME Python raw-file transport from a detached WMI process,
    # not merely a PowerShell UTF-8 file writer in the interactive environment.
    native_body = "@{role='REAL_WMI_UTF8_CONSTRUCTION_PROBE';path='强化反馈学习/中文回执';no_scientific_draw=$true;pid=$PID} | ConvertTo-Json -Compress"
    code = ("import importlib.util,json; from pathlib import Path; "
            "s=importlib.util.spec_from_file_location('detached_probe',"+repr(str(PATH))+ "); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "m.HERE=Path("+repr(str(folder))+"); "
            "payload=m.native_observation('detached_transport',"+repr(native_body)+"); "
            "Path("+repr(str(output))+").write_bytes(json.dumps(payload,ensure_ascii=False).encode('utf-8'))")
    script = control.UTF8_PREFIX + "& 'D:\\python\\python.exe' -B -X utf8 -c '"+code.replace("'", "''")+"'; exit $LASTEXITCODE"
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    command = '"'+str(control.PWSH)+'" -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand '+encoded
    body = "$result=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='"+command.replace("'", "''")+"'}; "
    body += "@{role='NATIVE_WMI_FIXTURE_LAUNCH';return_value=$result.ReturnValue;pid=$result.ProcessId} | ConvertTo-Json -Compress"
    launched = control.native_observation("wmi_fixture", body)
    assert launched["return_value"] == 0 and launched["pid"] > 0
    deadline = time.monotonic()+15
    while time.monotonic() < deadline and not output.exists():
        time.sleep(.05)
    assert output.is_file(), "detached fixture did not return output"
    # Wait for handle closure rather than reading a partially written file.
    for attempt in range(100):
        try:
            payload = json.loads(output.read_bytes().decode("utf-8", errors="strict"))
            break
        except (json.JSONDecodeError, PermissionError):
            time.sleep(.05)
    else:
        pytest.fail("detached UTF-8 output incomplete")
    assert payload["path"] == "强化反馈学习/中文回执"
    assert payload["no_scientific_draw"] is True
    assert payload["pid"] > 0
    assert control.p.read_json(folder / "detached_transport.receipt.json")["native_exit_code"] == 0
    assert (folder / "detached_transport.stdout.bin").read_bytes().decode("utf-8", errors="strict")
