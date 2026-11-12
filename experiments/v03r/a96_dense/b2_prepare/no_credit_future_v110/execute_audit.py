"""Exclusive first stdlib stored-content audit; no RFL import or retry."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def meta(path):
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return {"bytes": size, "sha256": digest.hexdigest()}


def save(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        stream.write("\n")


def binding():
    native = json.loads((HERE / "evidence/claim.json").read_bytes())
    names = set(native["input_binding_before"])
    names |= {path.relative_to(ROOT).as_posix() for path in (HERE / "evidence").iterdir() if path.is_file()}
    names |= {(HERE / filename).relative_to(ROOT).as_posix()
              for filename in ("audit_stored.py", "execute_audit.py")}
    previous = HERE.parent / "patch_dense_completion_v108/audit_stored.py"
    names.add(previous.relative_to(ROOT).as_posix())
    return {name: meta(ROOT / name) for name in sorted(names)}


def main():
    native_exit = json.loads((HERE / "evidence/exit.json").read_bytes())
    if not native_exit["input_bytes_unchanged"]:
        raise RuntimeError("native declared source bytes changed; do not audit as preserved")
    out = HERE / "evidence_stored_audit"
    if out.exists() or (HERE / "stored_audit_result.json").exists():
        raise RuntimeError("exclusive audit capture/result already exists; no automatic retry")
    before = binding()
    out.mkdir()
    command = [sys.executable, "-X", "utf8", "-B", str(HERE / "audit_stored.py")]
    started = datetime.now(timezone.utc).isoformat()
    save(out / "claim.json", {"started_at_utc": started, "command": command,
                             "input_binding_before": before, "automatic_retry": False,
                             "role": "V110_FIRST_STDLIB_STORED_CONTENT_AUDIT",
                             "native_child_exit_preserved": native_exit["child_exit_code"],
                             "RFL_or_old_checker_import_execution": False})
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        with (out / "stdout.log").open("xb") as stdout, (out / "stderr.log").open("xb") as stderr:
            child = subprocess.run(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr,
                                   check=False, timeout=300)
    except subprocess.TimeoutExpired:
        save(out / "timeout.json", {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
                                    "native_exit_not_fabricated": True, "automatic_retry": False})
        raise
    after = binding()
    receipt = {"started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
               "child_exit_code": child.returncode, "stdout": meta(out / "stdout.log"),
               "stderr": meta(out / "stderr.log"), "input_binding_after": after,
               "input_bytes_unchanged": before == after, "automatic_retry": False,
               "native_child_exit_preserved": native_exit["child_exit_code"],
               "RFL_or_old_checker_import_execution": False, "scientific_qualification": False}
    if (HERE / "stored_audit_result.json").is_file():
        receipt["stored_audit_result.json"] = meta(HERE / "stored_audit_result.json")
    save(out / "exit.json", receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != "input_binding_after"}), flush=True)
    return 0 if child.returncode == 0 and before == after else 1


if __name__ == "__main__":
    raise SystemExit(main())
