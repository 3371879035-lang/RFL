"""Run the new v115 independent stdlib stored review exactly once.

Native receipts must already be closed. This launcher never imports or reruns
an old auditor, RFL source, fixture, workload, calibration, or collection path.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def meta(path):
    h = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
            size += len(block)
    return {'bytes': size, 'sha256': h.hexdigest()}


def save(path, payload):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
        stream.write('\n')


def inputs():
    native_claim = json.loads((HERE / 'evidence/claim.json').read_bytes())
    selected = {ROOT / name for name in native_claim['input_binding_before']}
    selected.update({HERE / 'audit_stored.py', HERE / 'execute_audit.py', HERE / 'contract.json',
                     HERE.parent / 'recovery_observability_dense_v112/audit_stored.py',
                     HERE.parent / 'recovery_observability_dense_v112/execute_audit.py'})
    selected.update(p for p in (HERE / 'evidence').rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix(): meta(p) for p in sorted(selected)}


def main():
    # A terminal native parent receipt is required, including an honest partial.
    receipt = json.loads((HERE / 'evidence/exit.json').read_bytes())
    assert receipt['input_bytes_unchanged'] is True and not receipt['automatic_retry']
    before = inputs()
    capture = HERE / 'evidence_stored_audit'
    assert not capture.exists(), 'stored review capture already exists; no retry'
    capture.mkdir()
    command = [sys.executable, '-X', 'utf8', '-B', str(HERE / 'audit_stored.py')]
    started = datetime.now(timezone.utc).isoformat()
    save(capture / 'claim.json', {'started_at_utc': started, 'command': command,
         'input_binding_before': before, 'automatic_retry': False,
         'role': 'INDEPENDENT_STDLIB_STORED_CONTENT_REVIEW_NOT_SCIENCE_GATE',
         'native_workloads_rerun': False, 'old_checker_import_or_execution': False})
    clock = time.monotonic()
    env = dict(os.environ)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        with (capture / 'stdout.log').open('xb') as stdout, (capture / 'stderr.log').open('xb') as stderr:
            native = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                    check=False, timeout=900)
    except subprocess.TimeoutExpired:
        save(capture / 'timeout.json', {'observed_at_utc': datetime.now(timezone.utc).isoformat(),
             'native_exit_not_fabricated': True, 'automatic_retry': False,
             'elapsed_seconds': time.monotonic() - clock})
        raise
    after = inputs()
    result = {'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'elapsed_seconds': time.monotonic() - clock, 'native_exit_code': native.returncode,
              'input_bytes_unchanged': before == after, 'input_binding_after': after,
              'stdout': meta(capture / 'stdout.log'), 'stderr': meta(capture / 'stderr.log'),
              'automatic_retry': False, 'scientific_qualification': False,
              'native_workloads_rerun': False, 'old_checker_import_or_execution': False}
    if (HERE / 'stored_audit_result.json').is_file():
        result['stored_audit_result'] = meta(HERE / 'stored_audit_result.json')
    save(capture / 'exit.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'input_binding_after'},
                     ensure_ascii=True, sort_keys=True, separators=(',', ':')), flush=True)
    return 0 if native.returncode == 0 and before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
