"""Operational equivalence fixtures only, not formal development or treatment."""
import json
from pathlib import Path
import sys
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(ROOT / "experiments/v03r/parallel_verify_20261008"))
from test_parallel_verify import material, fixture_index
import parallel_f1 as f
import control_f1_parallel as c
from rfl_rebuild.b1.errors import ProtocolError


def test_dispatch_return_exact_serial_and_fresh_every_call(tmp_path,material):
    path,index = fixture_index(tmp_path,material)
    checks=[]
    verifier=f.FreshParallelValidation(tmp_path / "passes",lambda:checks.append(True))
    assert verifier(path) == f.ORIGINAL_VERIFY(path) == index
    assert verifier(path) == index and verifier.calls == 2 and len(checks) == 4
    assert len(list((tmp_path / "passes").glob("pass-*/workers/*.verified.json"))) == 4
    for receipt in (tmp_path / "passes").glob("pass-*/completed.json"):
        assert json.loads(receipt.read_bytes())["validation_reduced"] is False


def test_real_32_shard_adapter_order_receipts_and_input_bytes(tmp_path,material):
    path,index=fixture_index(tmp_path,material,32)
    before={s["path"]:f.pv.file_digest(path.parent / s["path"]) for s in index["shards"]}
    verifier=f.FreshParallelValidation(tmp_path / "passes",lambda:None)
    assert verifier(path) == index
    result=json.loads((tmp_path / "passes/pass-001/completed.json").read_bytes())
    assert result["max_workers"] == 16 and result["start_method"] == "spawn"
    assert 2 <= len({r["pid"] for r in result["shards"]}) <= 16
    assert [r["seed"] for r in result["shards"]] == index["seeds"]
    assert before == {s["path"]:f.pv.file_digest(path.parent / s["path"]) for s in index["shards"]}


@pytest.mark.parametrize("fails",[False,True])
def test_reference_install_restore_even_on_exception(fails):
    validator=lambda path:None
    try:
        with f.validation_dispatch(validator):
            assert f.ba.verify_acquisition is f.dl.verify_acquisition is validator
            assert f.ba.iter_verified_material is f.dl.iter_verified_material is f.ORIGINAL_ITERATOR
            assert f.ba._shard_records is f.pv._shard_records is f.ORIGINAL_SHARD
            if fails: raise ValueError("fixture")
    except ValueError:
        assert fails
    assert f.ba.verify_acquisition is f.dl.verify_acquisition is f.ORIGINAL_VERIFY


def test_original_ordered_iterator_still_revalidates_before_any_yield(tmp_path,material):
    path,index=fixture_index(tmp_path,material)
    verifier=f.FreshParallelValidation(tmp_path / "passes",lambda:None)
    with f.validation_dispatch(verifier):
        rows=list(f.ORIGINAL_ITERATOR(path))
    assert verifier.calls == 1
    assert [(row.seed,row.episode) for row in rows] == [(seed,e) for seed in index["seeds"] for e in index["episodes"]]


@pytest.mark.parametrize("phase",["before","after"])
def test_guard_drift_cannot_publish_full_pass(tmp_path,material,phase):
    path,_=fixture_index(tmp_path,material)
    calls=0
    def guard():
        nonlocal calls
        calls+=1
        if calls == (1 if phase == "before" else 2): raise ProtocolError("bound byte drift")
    verifier=f.FreshParallelValidation(tmp_path / "passes",guard)
    with pytest.raises(ProtocolError,match="drift"): verifier(path)
    assert not list((tmp_path / "passes").glob("pass-*/completed.json"))


def test_no_existing_dispatch_reservation(tmp_path):
    folder=tmp_path / "passes"
    folder.mkdir()
    with pytest.raises(FileExistsError): f.FreshParallelValidation(folder,lambda:None)


def test_unexpected_installed_dispatch_refused(monkeypatch):
    monkeypatch.setattr(f.ba,"verify_acquisition",lambda path:None)
    with pytest.raises(ProtocolError,match="installed"):
        with f.validation_dispatch(lambda path:None): pass


@pytest.mark.parametrize("target",["iterator","worker"])
def test_original_function_drift_refused(monkeypatch,target):
    if target == "iterator": monkeypatch.setattr(f.ba,"iter_verified_material",lambda path:None)
    else: monkeypatch.setattr(f.pv,"_shard_records",lambda *args:None)
    with pytest.raises(ProtocolError,match="changed"):
        with f.validation_dispatch(lambda path:None): pass


@pytest.mark.parametrize("status,code",[("PLAN_VALID",0),("LOCKED",0),("NO_ADMISSIBLE_T",3),("NO_ADMISSIBLE_P",3)])
def test_original_status_codes(status,code):
    assert f.result_code({"status":status}) == code


def test_execute_calls_exact_original_orchestration_args(monkeypatch):
    result={"status":"PLAN_VALID","written":False}
    received=[]
    def original(root,**kwargs):
        received.append((root,kwargs))
        assert f.ba.verify_acquisition is f.dl.verify_acquisition
        return result
    monkeypatch.setattr(f.dl,"run_lock",original)
    assert f.execute(root="root",design_path="dev",manifest_path="f0",output_path="lock",
                     plan_only=True,validator=lambda p:None) is result
    assert received == [("root",{"design_path":"dev","manifest_path":"f0","output_path":"lock","plan_only":True})]


@pytest.mark.parametrize("lines",[[],["F1_RESULT_JSON={}","F1_RESULT_JSON={}"]])
def test_terminal_result_missing_or_duplicate_refused(tmp_path,lines):
    path=tmp_path / "stdout"
    path.write_text("\n".join(lines),encoding="utf-8")
    with pytest.raises(ProtocolError): c.parse_result(path)


def test_progress_not_confused_with_terminal_result(tmp_path):
    path=tmp_path / "stdout"
    path.write_text('VERIFY_COMPLETED seed=980200\nF1_RESULT_JSON={"status":"PLAN_VALID"}\n',encoding="utf-8")
    assert c.parse_result(path) == {"status":"PLAN_VALID"}


def test_handover_guards_precede_only_stop():
    body=(HERE / "handover.ps1").read_text(encoding="utf-8")
    stop=body.index("Stop-Process -InputObject")
    assert body.count("Stop-Process -InputObject") == 1
    for guard in ("StartTime.ToUniversalTime().Ticks","CommandLine -cne","Parent has another Python child",
                  "Original full F1 has started","Fresh source-bound review invalid","Reviewed operational bytes changed"):
        assert body.index(guard) < stop
    assert "pipeline_exit.json" in body[stop:] and "native_exit_code -eq 0" in body[stop:]


def test_registration_truthful_boundary():
    reg=json.loads((HERE / "preregistration.json").read_bytes())
    assert reg["validation_dispatch_changes"] is True
    assert reg["source_count"] == 295 and reg["max_workers"] == 16
    for key in ("frozen_instrument_file_changes","validation_reduction","validation_cache",
                "scientific_parameter_changes","acquisition_restart","scientific_seed_change","automatic_retry"):
        assert reg[key] is False
    assert reg["operational_fixture_exclusions"] == list(range(980200,980232))
    for key in ("index_sha256","manifest_sha256","development_receipt_sha256"):
        assert len(reg[key]) == 64 and all(x in "0123456789abcdef" for x in reg[key])


def test_controller_never_reacquires_or_rewrites_instrument():
    body=(HERE / "control_f1_parallel.py").read_text(encoding="utf-8")
    for forbidden in ("run_dev_baseline.py","benchmark_f0_runtime.py","write_bytes","write_text","finalize_manifest"):
        assert forbidden not in body
    assert "independent_agent_review_performed\":False" in body
    assert "next_stage_automatically_authorized\":False" in body


def test_parser_and_selector_files_same_frozen_sha():
    expected={"src/rfl_rebuild/b2/baseline_artifact.py":"bbc2179dd983eedd4ad2ccaec61149903a31a0a2ec390a72652a372788ae5ad1",
              "src/rfl_rebuild/b2/design_lock.py":"0c86064bc2f7e1b8c6822fc4cd399b3fd8a2337bd808c60b3b08d0d9adea2ead",
              "src/rfl_rebuild/b2/design_selection.py":"ee7e9840a968af1629bf3b4ce4b3face19f4d8ebc6991a0ea7ad1cb38ed166d0"}
    assert all(f.pv.file_digest(ROOT / name) == sha for name,sha in expected.items())


@pytest.mark.parametrize("admissible",[False,True])
def test_original_run_lock_serial_parallel_same_order_status_payload(tmp_path,material,monkeypatch,admissible):
    """Exercise unchanged run_lock with small engineering data, no scientific claim.

    Scientific thresholds are fixture stubs here; ordered consumption, repeated
    input verification, atomic publication and original orchestrator are real.
    """
    path,index=fixture_index(tmp_path,material)
    original_run=f.dl.run_lock
    def fixture_prepare(root,*,design_path,manifest_path):
        f.dl.verify_acquisition(design_path)
        return {"index":index,"manifest":{"rmst_policy":{}},"calibration":{},
                "manifest_sha256":"fixture-f0","index_sha256":f.ba.digest(path.read_bytes())}
    monkeypatch.setattr(f.dl,"prepare_inputs",fixture_prepare)
    monkeypatch.setattr(f.dl,"solve_reference",lambda:None)
    monkeypatch.setattr(f.dl,"reference_view_from",lambda x:None)
    monkeypatch.setattr(f.dl,"prefix",lambda x:())
    monkeypatch.setattr(f.dl,"mean",lambda x:0.)
    observed=[]
    def derive(rows,**kwargs):
        order=[(r.seed,r.episode) for r in rows]
        observed.append(order)
        return {"fixture_order":order}
    monkeypatch.setattr(f.dl,"derive_design",derive)
    monkeypatch.setattr(f.dl,"combine_design_and_thresholds",lambda *args,**kwargs:
        {"lock":{"fixture":True} if admissible else None,"status":"LOCKED" if admissible else "NO_ADMISSIBLE_T"})
    serial=original_run(ROOT,design_path=path,manifest_path="fixture",output_path=tmp_path / "serial.json")
    validator=f.FreshParallelValidation(tmp_path / "passes",lambda:None)
    parallel=f.execute(root=ROOT,design_path=path,manifest_path="fixture",output_path=tmp_path / "parallel.json",
                       plan_only=False,validator=validator)
    assert observed[0] == observed[1] == [(s,e) for s in index["seeds"] for e in index["episodes"]]
    assert serial["status"] == parallel["status"] and serial["written"] == parallel["written"]
    assert validator.calls == (3 if admissible else 2)
    if admissible: assert (tmp_path / "serial.json").read_bytes() == (tmp_path / "parallel.json").read_bytes()
    else: assert serial == parallel and not (tmp_path / "parallel.json").exists()


def test_adapter_error_exit_remains_invalid2(monkeypatch,capsys):
    monkeypatch.setattr(sys,"argv",["parallel_f1.py","--plan"])
    def invalid(): raise ProtocolError("deliberate fixture drift")
    monkeypatch.setattr(c,"context",invalid)
    assert f.main() == 2
    line=capsys.readouterr().out.strip()
    assert json.loads(line.removeprefix("F1_RESULT_JSON="))["status"] == "PROTOCOL_ERROR"
