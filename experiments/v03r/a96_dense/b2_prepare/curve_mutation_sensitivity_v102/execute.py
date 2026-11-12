"""Exclusive bounded runner for V102's read-only mutation sensitivity probes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CONTRACT = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
EVIDENCE = HERE / "evidence"


def pin(path):
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    EVIDENCE.mkdir(exist_ok=False)
    inputs = [HERE / "contract.json", HERE / "selfcheck.py",
              ROOT / "experiments/v03r/a96_dense/b2_prepare/owned_curve_connector_v95/contract.json",
              ROOT / "experiments/v03r/a96_dense/b2_prepare/owned_curve_connector_v95/evidence/stdout.log",
              ROOT / "experiments/v03r/a96_dense/b2_prepare/owned_curve_connector_v95/evidence/exit.json",
              ROOT / "experiments/v03r/a96_dense/b2_prepare/owned_curve_connector_v95/learning.py",
              ROOT / "experiments/v03r/a96_dense/b2_prepare/owned_curve_connector_v95/owned_curve.py"]
    before = {str(p.relative_to(ROOT)).replace("\\", "/"): pin(p) for p in inputs}
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    with (EVIDENCE / "stdout.log").open("xb") as out, (EVIDENCE / "stderr.log").open("xb") as err:
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", str(HERE / "selfcheck.py")],
                                cwd=ROOT, stdout=out, stderr=err, timeout=CONTRACT["budget"]["seconds"],
                                check=False)
    elapsed = time.monotonic() - t0
    after = {str(p.relative_to(ROOT)).replace("\\", "/"): pin(p) for p in inputs}
    unchanged = before == after
    claim = {"schema": "V102_READ_ONLY_STORED_OBSERVATION_MUTATION_SENSITIVITY",
             "parent_commit": CONTRACT["parent_commit"], "contract_sha256": pin(HERE / "contract.json")["sha256"],
             "input_binding_before": before, "input_binding_after": after,
             "before_after_identical": unchanged, "native_RFL_rollout_step_B1_transaction": 0,
             "automatic_retry": False, "actual_child_exit": result.returncode, "seconds": elapsed,
             "started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    (EVIDENCE / "claim.json").write_text(json.dumps(claim, sort_keys=True, separators=(",", ":")) + "\n",
                                          encoding="utf-8", newline="\n")
    receipt = {"schema": "V102_FIRST_CHILD_EXIT_NOT_SCIENCE_GATE", "exit_code": result.returncode,
               "automatic_retry": False, "seconds": elapsed, "started_at_utc": started,
               "completed_at_utc": claim["completed_at_utc"],
               "stdout": pin(EVIDENCE / "stdout.log"), "stderr": pin(EVIDENCE / "stderr.log"),
               "before_after_inputs_identical": unchanged}
    (EVIDENCE / "exit.json").write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
                                           encoding="utf-8", newline="\n")
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return result.returncode if unchanged else 2


if __name__ == "__main__":
    raise SystemExit(main())
