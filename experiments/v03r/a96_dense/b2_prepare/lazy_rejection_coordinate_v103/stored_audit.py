"""Independent stdlib verification of the captured V103 coordinate transcript."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    contract = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
    claim = json.loads((HERE / "evidence/claim.json").read_text(encoding="utf-8"))
    exit_data = json.loads((HERE / "evidence/exit.json").read_text(encoding="utf-8"))
    stdout = (HERE / "evidence/stdout.log").read_bytes()
    stderr = (HERE / "evidence/stderr.log").read_bytes()
    assert exit_data["exit_code"] == 0 and exit_data["automatic_retry"] is False
    assert claim["before_after_identical"] and claim["input_binding_before"] == claim["input_binding_after"]
    assert exit_data["stdout"] == {"bytes": len(stdout), "sha256": hashlib.sha256(stdout).hexdigest()}
    assert exit_data["stderr"] == {"bytes": len(stderr), "sha256": hashlib.sha256(stderr).hexdigest()}
    r = json.loads(stdout.decode("ascii"))
    assert r["admissible_n"] == 5 and r["uint64_max_rejected"] is True
    assert r["exact_lazy_calls"] == [[0, 1, 0, (1 << 64) - 1], [0, 1, 1, 4]]
    assert r["floor_mutant_lazy_calls"] == [[0, 1, 0, (1 << 64) - 1]]
    assert r["exact_action"] == r["floor_mutant_action"] == 4
    assert r["native_rollout_step_B1_transaction"] == 0
    result = {"schema": "V103_STORED_AUDIT_NOT_EXPERT_OR_SCIENCE",
              "exit_code": 0, "actual_adapter_coordinate_calls": len(r["exact_lazy_calls"]),
              "floor_mutant_calls": len(r["floor_mutant_lazy_calls"]),
              "mutant_rejected": r["mutant_rejected_by_coordinate_transcript"],
              "new_native_rollout_step_B1_transaction": 0,
              "RFL_or_old_checker_executed_by_auditor": False,
              "scientific_qualification": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
