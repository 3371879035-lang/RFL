"""Source-bound P16 adapter for the preserved one-shot R1 stage controller."""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
TEMPLATE = ROOT / "experiments/v03r/restart_20261008/continue_pipeline.py"
spec = importlib.util.spec_from_file_location("p16_preserved_stage_controller", TEMPLATE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
from rfl_rebuild.b2.parallel_acquisition import EXECUTION_PROFILE

base.HERE = HERE
base.BENCHMARK = ROOT / "experiments/v03r/f0_runtime_parallel16_20261008"
base.REVIEW = HERE / "source_bound_parallel_review.json"
base.MANIFEST = HERE / "f0_manifest_parallel16.json"


def verify_parent_preserved():
    registration = base.read_json(HERE / "preregistration.json")
    observation = base.read_json(HERE / "parent_switch_observation.json")
    base.require(observation.get("role") == "EXTERNAL_AUTHORIZED_SWITCH_OBSERVATION"
                 and observation.get("scientific_completion_claimed") is False,
                 "missing honest controlled-switch observation")
    parent = pathlib.Path(registration["preserved_root"])
    claim = base.read_json(parent / "experiments/v03r/restart_20261008/pipeline_claim.json")
    base.require(base.source_inventory(parent) == claim["sources"], "serial R1 source drift")
    for name, expected in observation["preserved_files"].items():
        base.require(base.digest((parent / name).read_bytes()) == expected, "serial R1 evidence changed: " + name)
    for name in base.FORMAL_OUTPUTS:
        base.require(not (parent / "experiments/v03r" / name).exists(), "serial R1 formal population became spent")
    base.require(registration["fresh_smoke_seeds"] == list(base.read_json(
        ROOT / "experiments/v03r/restart_20261008/preregistration.json")["fresh_smoke_seeds"]),
        "P16 scientific population changed")
    return {"observed_at": base.now(), "serial_R1_preserved": True,
            "parent_formal_populations_unspent": True, "new_source_no_evidence_migration": True}


original_validate = base.validate_launch


def validate_launch(root, benchmark, manifest, review):
    result = original_validate(root, benchmark, manifest, review)
    base.require(review.get("execution_profile") == EXECUTION_PROFILE, "P16 review profile mismatch")
    result.update(orchestrator_sha256=base.digest((HERE / "control_parallel16.py").read_bytes()),
                  runner_sha256=base.digest(pathlib.Path(__file__).read_bytes()),
                  stage_template_sha256=base.digest(TEMPLATE.read_bytes()), execution_profile=EXECUTION_PROFILE)
    return result


original_verify_benchmark = base.verify_benchmark


def verify_benchmark(directory, expected_sources):
    frozen = base.read_json(pathlib.Path(directory) / "frozen_inputs.json")
    base.require(frozen.get("execution_profile") == EXECUTION_PROFILE, "P16 frozen execution profile mismatch")
    result = original_verify_benchmark(directory, expected_sources)
    index = base.read_index(pathlib.Path(directory) / "baseline.json")
    base.require(index["execution"].get("execution_profile") == EXECUTION_PROFILE,
                 "P16 index execution profile mismatch")
    return {**result, "execution_profile": EXECUTION_PROFILE}


base.validate_launch = validate_launch
base.verify_parent_preserved = verify_parent_preserved
base.verify_benchmark = verify_benchmark

if __name__ == "__main__":
    raise SystemExit(base.main())
