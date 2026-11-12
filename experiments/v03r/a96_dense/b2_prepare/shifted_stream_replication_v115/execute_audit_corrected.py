"""Run the explicitly corrected v115 stored audit once, without native rerun."""
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


def main():
    old = json.loads((HERE / 'evidence/exit.json').read_bytes())
    assert old['completed'] is True and old['input_bytes_unchanged'] is True
    assert old['automatic_retry'] is False
    capture = HERE / 'evidence_stored_audit_corrected'
    assert not capture.exists(), 'corrected audit capture already exists; no retry'
    capture.mkdir()
    started = datetime.now(timezone.utc).isoformat()
    command = [sys.executable, '-X', 'utf8', '-B', str(HERE / 'audit_stored_corrected.py')]
    save(capture / 'claim.json', {
        'started_at_utc': started, 'command': command,
        'first_audit_preserved_as_harness_error': True,
        'correction': "engineering_n_eval -> evaluation_scenes only",
        'native_workloads_rerun': False, 'old_checker_import_or_execution': False,
        'automatic_retry': False, 'scientific_qualification': False,
    })
    before = meta(HERE / 'stored_audit_result_corrected.json') if (HERE / 'stored_audit_result_corrected.json').exists() else None
    assert before is None
    env = dict(os.environ)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    clock = time.monotonic()
    with (capture / 'stdout.log').open('xb') as stdout, (capture / 'stderr.log').open('xb') as stderr:
        child = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                               check=False, timeout=900)
    after = meta(HERE / 'stored_audit_result_corrected.json') if (HERE / 'stored_audit_result_corrected.json').exists() else None
    result = {
        'started_at_utc': started,
        'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds': time.monotonic() - clock,
        'corrected_audit_exit_code': child.returncode,
        'stored_audit_result_corrected': after,
        'stdout': meta(capture / 'stdout.log'),
        'stderr': meta(capture / 'stderr.log'),
        'native_workloads_rerun': False,
        'old_checker_import_or_execution': False,
        'first_audit_failure_preserved': True,
        'automatic_retry': False,
        'scientific_qualification': False,
    }
    save(capture / 'exit.json', result)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(',', ':')), flush=True)
    return 0 if child.returncode == 0 and after is not None else 1


if __name__ == '__main__':
    raise SystemExit(main())
