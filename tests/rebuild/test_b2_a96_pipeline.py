"""Native one-use operational interfaces; no scientific seed is drawn."""
import importlib.util
import copy
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import pytest
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2 import protocol_profile as profile, f0_stages as f0
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("a96_pipeline",ROOT/"scripts/run_a96_pipeline.py")
pipeline=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)

@pytest.mark.parametrize("code",[0,3,2])
def test_native_command_receipt_and_allowed_code(tmp_path,monkeypatch,code):
    monkeypatch.setattr(pipeline,"OP",tmp_path)
    monkeypatch.setattr(pipeline,"ROOT",tmp_path)
    argv=[sys.executable,"-X","utf8","-c",f"import sys; print('中文回执'); sys.exit({code})"]
    if code == 2:
        with pytest.raises(ProtocolError,match="native exit 2"):
            pipeline.command("fixture",argv,allowed=(0,3))
    else: assert pipeline.command("fixture",argv,allowed=(0,3)) == code
    receipt=f0.read_json(tmp_path/"fixture.receipt.json")
    assert receipt["native_exit_code"] == code and receipt["receipt_origin"] == "native_subprocess_wait"
    assert "中文回执" in (tmp_path/"fixture.stdout.log").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError): pipeline.command("fixture",argv,allowed=(0,3))

def test_seed_registry_is_exact_disjoint_and_unassigned_future():
    registry=f0.read_json(ROOT/"docs/rebuild/a96_seed_registry.json")
    contract=f0.read_json(ROOT/"docs/rebuild/a96_dense_measurement_contract.json")
    assert contract["ratified"] and not contract["scientific_execution_authorized"]
    assert registry["scientific"]["treatment"] is registry["scientific"]["confirmatory"] is None
    all_keys=[]
    for stage in ("smoke","dev_baseline"):
        assert registry["scientific"][stage] == list(profile.STAGE_SEEDS[stage])
        assert registry["engineering"][stage] == list(profile.ENGINEERING_KEYS[stage])
        all_keys.extend(profile.STAGE_SEEDS[stage]);all_keys.extend(profile.ENGINEERING_KEYS[stage])
    assert len(all_keys) == len(set(all_keys)) == 74
    assert not set(all_keys).intersection(profile.SPENT_SCIENTIFIC_SEEDS)
    for low,high in registry["permanent_exclusions"]["old_engineering_ranges"]+registry["permanent_exclusions"]["operational_fixture_ranges"]:
        assert not any(low <= key <= high for key in all_keys)

def test_inventory_covers_every_new_scientific_and_operational_file():
    files=f0.source_inventory(ROOT)
    expected=[*profile.PROTOCOL_FILES,"scripts/run_a96_pipeline.py","scripts/verify_a96_baseline.py",
              "src/rfl_rebuild/b2/measurement_revision.py","src/rfl_rebuild/b2/parallel_design.py",
              "src/rfl_rebuild/b2/parallel_validation.py","tests/rebuild/test_b2_measurement_revision.py"]
    assert all(name in files for name in expected)
    assert not any("measurement_revision_20261008/measurement_prototype.py" in name for name in files)

@pytest.mark.parametrize("bad",["extra_skip","failure","empty"])
def test_unreviewed_regression_result_refused(tmp_path,bad):
    path=tmp_path/"regression.xml"
    root=ET.Element("testsuites")
    suite=ET.SubElement(root,"testsuite",tests="1067",failures="1" if bad=="failure" else "0",
                        errors="0",skipped="2" if bad=="extra_skip" else "1")
    if bad != "empty":
        case=ET.SubElement(suite,"testcase",classname="tests.rebuild.test_b2_acquisition",
                           name="test_12_a_site_no_episode_consults_shares_the_generic_value[P]")
        ET.SubElement(case,"skipped")
    if bad == "extra_skip":
        case=ET.SubElement(suite,"testcase",classname="bad",name="unreviewed")
        ET.SubElement(case,"skipped")
    ET.ElementTree(root).write(path,encoding="utf-8")
    with pytest.raises(ProtocolError): pipeline.regression_counts(path)

def test_pipeline_is_no_retry_no_external_publish_and_sequential():
    text=(ROOT/"scripts/run_a96_pipeline.py").read_text(encoding="utf-8")
    assert "force-push" not in text and '"git","push"' not in text
    labels=['command("full_runtime"','command("runtime_full_verification"','command("formal_smoke"',
            'command("independent_smoke_evaluator"','command("development32"','command("f1_plan"','command("full_f1"']
    assert [text.index(s) for s in labels] == sorted(text.index(s) for s in labels)
    launcher=(ROOT/"scripts/launch_a96_pipeline.ps1").read_text(encoding="utf-8")
    assert "-WindowStyle Hidden" in launcher and "Stop-Process" not in launcher
    assert "One-shot reservation exists" in launcher and "Another RFL task is running" in launcher
    assert "$env:PYTHONUTF8='1'" in launcher and "$env:PYTHONIOENCODING='utf-8'" in launcher
    attributes=(ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "experiments/v03r/a96_dense/** -text" in attributes


@pytest.mark.parametrize("mutation", ["root", "profile", "retry", "approval", "bypass_f0", "seed", "contract_seed", "future", "collision", "fixture", "branch"])
def test_registration_refuses_each_unsupported_execution(mutation, monkeypatch):
    files={str(pipeline.OP / "preregistration.json"):f0.read_json(pipeline.OP / "preregistration.json"),
           str(ROOT / "docs/rebuild/a96_dense_measurement_contract.json"):f0.read_json(ROOT / "docs/rebuild/a96_dense_measurement_contract.json"),
           str(ROOT / "docs/rebuild/a96_seed_registry.json"):f0.read_json(ROOT / "docs/rebuild/a96_seed_registry.json")}
    registration=files[str(pipeline.OP / "preregistration.json")]
    contract=files[str(ROOT / "docs/rebuild/a96_dense_measurement_contract.json")]
    registry=files[str(ROOT / "docs/rebuild/a96_seed_registry.json")]
    if mutation == "root": registration["root"] = str(ROOT.parent / "wrong")
    elif mutation == "profile": registration["measurement_profile"] = "old"
    elif mutation == "retry": registration["automatic_retry"] = True
    elif mutation == "approval": contract["approval"]["ratified"] = False
    elif mutation == "bypass_f0": contract["scientific_execution_authorized"] = True
    elif mutation == "seed": registry["scientific"]["smoke"][0] = 0
    elif mutation == "contract_seed": contract["scientific_seed_sets"]["smoke"][0] = 0
    elif mutation == "future": registry["scientific"]["treatment"] = [42]
    elif mutation == "collision": registry["permanent_exclusions"]["old_scientific"].append(profile.STAGE_SEEDS["smoke"][0])
    elif mutation == "fixture": registry["permanent_exclusions"]["operational_fixture_ranges"].append([profile.STAGE_SEEDS["smoke"][0]] * 2)
    monkeypatch.setattr(pipeline,"read_json",lambda path:copy.deepcopy(files[str(path)]))
    monkeypatch.setattr(pipeline.subprocess,"check_output",lambda *a,**k:"wrong\n" if mutation=="branch" else registration["branch"]+"\n")
    with pytest.raises(ProtocolError): pipeline.validate_registration()


def test_ratified_registration_passes_without_drawing_or_writing(monkeypatch):
    monkeypatch.setattr(pipeline.subprocess,"check_output",lambda *a,**k:"study/v03r-dense-measurement-20261009\n")
    monkeypatch.setattr(pipeline,"publish_new",lambda *a,**k:pytest.fail("registration wrote execution evidence"))
    pipeline.validate_registration()


def test_gate_commands_and_artifact_paths_share_current_namespace():
    expected={"scripts/b2_view_gate_selfcheck.py":"b2_view_gate_selfcheck.json",
              "scripts/a91_training_gate_selfcheck.py":"a91_training_gate_selfcheck.json",
              "scripts/run_calibration.py":"calibration_report.json",
              "scripts/f0_manifest_selfcheck.py":"f0_manifest_selfcheck.json"}
    for script,artifact in expected.items():
        gate=next(g for g in f0.GATES if g["argv"][-1]==script)
        assert gate["artifact"] == profile.STAGE_ROOT + "/" + artifact
        text=(ROOT/script).read_text(encoding="utf-8")
        assert "a96_dense" in text and "a96_measurement" not in text and "a95_measurement" not in text


def test_result_ledger_protects_other_study_and_is_not_native_completion(tmp_path, monkeypatch):
    path=tmp_path / "experiments/rebuild_status_current.json"
    path.parent.mkdir()
    value=f0.read_json(ROOT / "experiments/rebuild_status_current.json")
    path.write_bytes(f0.canonical_bytes(value))
    before=path.read_bytes()
    monkeypatch.setattr(pipeline,"ROOT",tmp_path)
    with pytest.raises(ProtocolError,match="another study"):
        pipeline.update_result_ledger("anything")
    assert path.read_bytes() == before
    value["root"]=str(tmp_path)
    path.write_bytes(f0.canonical_bytes(value))
    pipeline.update_result_ledger("VALID_STOP",result={"status":"NO_ADMISSIBLE_RETENTION"},native_f1=3)
    ledger=f0.read_json(path)
    assert ledger["native_f1_exit_code"] == 3 and ledger["native_controller_exit_code"] is None
    assert not ledger["research_complete"] and not ledger["current_frozen_protocol_complete"]
    assert ledger["frozen_protocol_state"] == "VALID_NO_ADMISSIBLE_CLOSURE_AUDIT_PENDING"
