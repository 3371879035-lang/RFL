"""New one-shot reservation; identical P16 instrument, no historical receipt edits."""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
TEMPLATE = ROOT / "experiments/v03r/restart_20261008/continue_pipeline.py"
spec = importlib.util.spec_from_file_location("p16_resume_stage_template", TEMPLATE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
from rfl_rebuild.b2.parallel_acquisition import EXECUTION_PROFILE

base.HERE = HERE
base.BENCHMARK = ROOT / "experiments/v03r/f0_runtime_parallel16_resume_20261008"
base.REVIEW = HERE / "source_bound_resume_review.json"
base.MANIFEST = HERE / "f0_manifest_parallel16_resume.json"
CONTROL_FILES = ("resume_parallel16.py", "continue_pipeline.py", "launch_detached.ps1",
                 "test_resume_parallel16.py", "preregistration.json")


def control_inventory():
    return {name: base.digest((HERE / name).read_bytes()) for name in CONTROL_FILES}


def verify_parent_preserved():
    registration = base.read_json(HERE / "preregistration.json")
    base.validate_restart_population(registration)
    base.require(pathlib.Path(registration["root"]).resolve() == ROOT.resolve(), "resume root changed")
    base.require(registration["execution_profile"] == EXECUTION_PROFILE, "resume profile changed")
    previous = ROOT / registration["prior_operation_folder"]
    for name, expected in registration["prior_operation_files"].items():
        base.require(base.digest((previous / name).read_bytes()) == expected, "prior P16 evidence changed: " + name)
    incident = base.read_json(ROOT / registration["prior_incident"])
    base.require(incident["present_execution"]["formal_smoke_started"] is False, "prior scientific run was spent")
    base.require(base.read_json(previous / "pipeline_exit.json")["native_exit_code"] == 2,
                 "prior native P16 exit changed")
    inventory = base.read_json(ROOT / registration["r1_inventory"])
    parent = pathlib.Path(registration["preserved_r1_root"])
    base.require(parent.resolve() == pathlib.Path(inventory["root"]).resolve(), "preservation root mismatch")
    actual_names = {path.relative_to(parent).as_posix() for path in parent.rglob("*") if path.is_file()}
    base.require(actual_names == set(inventory["files"]), "R1 file inventory changed")
    for name, evidence in inventory["files"].items():
        base.require(base.digest((parent / name).read_bytes()) == evidence["sha256"], "R1 preserved file changed: " + name)
    for name in base.FORMAL_OUTPUTS:
        base.require(not (parent / "experiments/v03r" / name).exists(), "R1 scientific reservation exists")
    prior = base.read_json(ROOT / registration["exact_prior_instrument_review"])
    base.require(base.digest((ROOT / registration["exact_prior_instrument_review"]).read_bytes())
                 == registration["exact_prior_review_sha256"], "prior exact-source review changed")
    sources = base.source_inventory(ROOT)
    base.require(len(sources) == registration["frozen_source_count"]
                 and base.digest(base.canonical_bytes(sources)) == registration["frozen_sources_digest"]
                 == prior["sources_digest"], "resume changes frozen instrument")
    return {"role": "EXTERNAL_RESUME_PRESERVATION_CHECK_NOT_NATIVE_STOP_RECEIPT",
            "observed_at": base.now(), "r1_files_verified": len(actual_names),
            "prior_p16_files_verified": len(registration["prior_operation_files"]),
            "same_instrument_no_raw_or_timing_migration": True,
            "parent_formal_populations_unspent": True, "no_stop_performed": True}


original_validate = base.validate_launch


def validate_launch(root, benchmark, manifest, review):
    result = original_validate(root, benchmark, manifest, review)
    base.require(review.get("execution_profile") == EXECUTION_PROFILE, "resume review profile mismatch")
    base.require(review.get("operational_control_files") == control_inventory(), "resume controller byte drift")
    base.require(review.get("stage_template_sha256") == base.digest(TEMPLATE.read_bytes()), "stage template drift")
    result.update(orchestrator_sha256=base.digest((HERE / "resume_parallel16.py").read_bytes()),
                  runner_sha256=base.digest(pathlib.Path(__file__).read_bytes()),
                  stage_template_sha256=base.digest(TEMPLATE.read_bytes()),
                  operational_control_files=control_inventory(), execution_profile=EXECUTION_PROFILE)
    return result


original_verify_benchmark = base.verify_benchmark


def verify_benchmark(directory, expected_sources):
    frozen = base.read_json(pathlib.Path(directory) / "frozen_inputs.json")
    base.require(frozen.get("execution_profile") == EXECUTION_PROFILE, "parallel frozen profile mismatch")
    result = original_verify_benchmark(directory, expected_sources)
    index = base.read_index(pathlib.Path(directory) / "baseline.json")
    base.require(index["execution"].get("execution_profile") == EXECUTION_PROFILE, "parallel index profile mismatch")
    return {**result, "execution_profile": EXECUTION_PROFILE}


base.validate_launch = validate_launch
base.verify_parent_preserved = verify_parent_preserved
base.verify_benchmark = verify_benchmark
