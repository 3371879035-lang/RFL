"""Exclusive first stdlib stored audit; never repairs or retries native work."""
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
    h, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
            size += len(block)
    return {'bytes': size, 'sha256': h.hexdigest()}


def save(path, payload):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        stream.write('\n')


def inputs():
    selected = [HERE / 'audit_stored.py', HERE / 'execute_audit.py', HERE / 'contract.json',
                HERE.parent / 'dense_resource_workload_v106/audit_dense_kernel_return_revised.py']
    selected += sorted(p for p in (HERE / 'evidence').rglob('*') if p.is_file())
    return {p.relative_to(ROOT).as_posix(): meta(p) for p in selected}


def main():
    receipt = json.loads((HERE / 'evidence/exit.json').read_bytes())
    assert receipt['input_bytes_unchanged'] is True
    before = inputs()
    folder = HERE / 'evidence_stored_audit'
    assert not folder.exists(), 'stored capture already exists; no automatic audit retry'
    folder.mkdir()
    command = [sys.executable, '-X', 'utf8', '-B', str(HERE / 'audit_stored.py')]
    started = datetime.now(timezone.utc).isoformat()
    save(folder / 'claim.json', {'started_at_utc': started, 'command': command,
         'input_binding_before': before, 'automatic_retry': False,
         'role': 'INDEPENDENT_STDLIB_STORED_CONTENT_REVIEW_NOT_SCIENCE_GATE'})
    env = dict(os.environ)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    clock = time.monotonic()
    try:
        with (folder / 'stdout.log').open('xb') as stdout, (folder / 'stderr.log').open('xb') as stderr:
            child = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                   check=False, timeout=180)
    except subprocess.TimeoutExpired:
        save(folder / 'timeout.json', {'observed_at_utc': datetime.now(timezone.utc).isoformat(),
             'native_exit_not_fabricated': True, 'automatic_retry': False})
        raise
    after = inputs()
    result = {'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'elapsed_seconds': time.monotonic() - clock, 'native_exit_code': child.returncode,
              'input_binding_after': after, 'input_bytes_unchanged': before == after,
              'stdout': meta(folder / 'stdout.log'), 'stderr': meta(folder / 'stderr.log'),
              'automatic_retry': False, 'scientific_qualification': False}
    if (HERE / 'stored_audit_result.json').exists():
        result['stored_audit_result'] = meta(HERE / 'stored_audit_result.json')
    save(folder / 'exit.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'input_binding_after'},
                     sort_keys=True, separators=(',', ':'), ensure_ascii=True), flush=True)
    return 0 if child.returncode == 0 and before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
