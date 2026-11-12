"""Independent stdlib audit of V102's captured result and input bindings."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def main():
    contract = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
    claim = json.loads((HERE / "evidence/claim.json").read_text(encoding="utf-8"))
    exit_receipt = json.loads((HERE / "evidence/exit.json").read_text(encoding="utf-8"))
    stdout = (HERE / "evidence/stdout.log").read_bytes()
    stderr = (HERE / "evidence/stderr.log").read_bytes()
    assert claim["before_after_identical"] and claim["input_binding_before"] == claim["input_binding_after"]
    assert claim["native_RFL_rollout_step_B1_transaction"] == 0
    assert exit_receipt["exit_code"] == 0 and exit_receipt["automatic_retry"] is False
    assert exit_receipt["stdout"] == {"bytes": len(stdout), "sha256": hashlib.sha256(stdout).hexdigest()}
    assert exit_receipt["stderr"] == {"bytes": len(stderr), "sha256": hashlib.sha256(stderr).hexdigest()}
    lines = [json.loads(line) for line in stdout.decode("utf-8").splitlines()]
    assert len(lines) == 1
    result = lines[0]
    assert result["schema"] == "V102_STORED_OBSERVATION_MUTATION_SENSITIVITY_NOT_SOURCE_MUTATION_GATE"
    assert result["mutations_rejected"] == 6
    assert [x["mutation"] for x in result["results"]] == [x for x in (
        "use_post_state_as_current_q_address", "use_proposal_as_initial_in_force",
        "uniform_action_by_flooring_a_real", "future_training_mutates_collateral_state",
        "remeasure_v_pre_per_arm", "second_arm_uses_different_training_seed")]
    assert result["source_level_mutants_executed"] == 0
    assert result["RFL_imports_or_calls"] == 0
    assert "n=2" in result["results"][2]["reason"] and "n=5" in result["results"][2]["reason"]
    report = {"schema": "V102_INDEPENDENT_STORED_CONTENT_CHECK_NOT_EXPERT_OR_SCIENCE",
              "exit_code": 0, "records": len(lines), "mutations_rejected": 6,
              "input_binding_pins": len(claim["input_binding_before"]),
              "source_level_mutants_executed": 0, "RFL_or_old_checker_executed": False,
              "native_exit_preserved": exit_receipt["exit_code"],
              "uniform_rejection_runtime_gap_found": True,
              "independent_expert_or_science_gate": False}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
