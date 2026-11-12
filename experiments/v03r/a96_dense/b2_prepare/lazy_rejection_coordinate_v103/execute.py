"""Exclusive bounded capture for the V103 component probe."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
EVIDENCE = HERE / "evidence"
CONTRACT = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))


def pin(p):
    b = p.read_bytes()
    return {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}


def main():
    EVIDENCE.mkdir(exist_ok=False)
    rels = [HERE / "contract.json", HERE / "probe.py",
            ROOT / "experiments/v03r/a96_dense/b2_prepare/owned_curve_connector_v95/learning.py",
            ROOT / "experiments/v03r/a96_dense/b2_prepare/adaptive_training_v90/adaptive_training.py",
            ROOT / "src/rfl_rebuild/b2/training.py"]
    before = {p.relative_to(ROOT).as_posix(): pin(p) for p in rels}
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    with (EVIDENCE / "stdout.log").open("xb") as out, (EVIDENCE / "stderr.log").open("xb") as err:
        child = subprocess.run([sys.executable, "-X", "utf8", "-B", str(HERE / "probe.py")],
                               cwd=ROOT, timeout=CONTRACT["budget"]["seconds"],
                               stdout=out, stderr=err, check=False)
    elapsed = time.monotonic() - t0
    after = {p.relative_to(ROOT).as_posix(): pin(p) for p in rels}
    claim = {"schema": "V103_FIRST_ACTUAL_ADAPTER_COMPONENT_CAPTURE", "parent_commit": CONTRACT["parent_commit"],
             "input_binding_before": before, "input_binding_after": after,
             "before_after_identical": before == after, "child_exit_code": child.returncode,
             "automatic_retry": False, "seconds": elapsed,
             "started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat()}
    (EVIDENCE / "claim.json").write_text(json.dumps(claim, sort_keys=True, separators=(",", ":")) + "\n",
                                          encoding="utf-8", newline="\n")
    receipt = {"schema": "V103_FIRST_EXIT_NOT_SCIENCE", "exit_code": child.returncode,
               "automatic_retry": False, "seconds": elapsed, "started_at_utc": started,
               "completed_at_utc": claim["completed_at_utc"], "stdout": pin(EVIDENCE / "stdout.log"),
               "stderr": pin(EVIDENCE / "stderr.log"), "before_after_identical": before == after}
    (EVIDENCE / "exit.json").write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
                                           encoding="utf-8", newline="\n")
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return child.returncode if before == after else 2


if __name__ == "__main__":
    raise SystemExit(main())
