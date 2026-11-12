"""Capture the new stdlib stored audit once, after native receipts are closed."""
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
    digest = hashlib.sha256()
    length = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            length += len(block)
            digest.update(block)
    return {'bytes': length, 'sha256': digest.hexdigest()}


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
        stream.write('\n')


def inputs():
    selected = [HERE / 'audit_stored.py', HERE / 'execute_audit.py', HERE / 'contract.json']
    selected += sorted(p for p in (HERE / 'evidence').rglob('*') if p.is_file())
    previous = HERE.parent / 'dense_resource_workload_v106'
    selected += [previous / name for name in (
        'audit_dense_kernel_return_revised.py', 'stored_audit_kernel_return_revised_result.json',
        'audit_dense.py', 'evidence_stored_audit/exit.json', 'evidence_stored_audit/stderr.log',
        'audit_dense_dispatch_revised.py', 'evidence_stored_audit_dispatch_revised/exit.json',
        'evidence_stored_audit_dispatch_revised/stderr.log')]
    selected += [HERE / 'owned_curve.py', HERE / 'external.py',
                 HERE.parent / 'readonly_bank_optimization_v107/bank.py']
    normal = HERE.parent / 'complete_curve_source_gates_v105/variants/normal'
    selected += [normal / name for name in ('owned_curve.py', 'external.py')]
    contract = json.loads((HERE / 'contract.json').read_bytes())
    selected += [ROOT / contract['predecessor_gate'][role]['path'] for role in ('native', 'stored')]
    return {p.relative_to(ROOT).as_posix(): meta(p) for p in selected}


def main():
    # A closed parent receipt is required; this does not repair or retry native work.
    receipt = json.loads((HERE / 'evidence/exit.json').read_bytes())
    assert receipt['input_bytes_unchanged'] is True
    before = inputs()
    capture = HERE / 'evidence_stored_audit'
    assert not capture.exists(), 'stored audit capture already exists; no retry'
    capture.mkdir()
    command = [sys.executable, '-X', 'utf8', '-B', str(HERE / 'audit_stored.py')]
    started = datetime.now(timezone.utc).isoformat()
    save(capture / 'claim.json', {'started_at_utc': started, 'command': command,
         'input_binding_before': before, 'automatic_retry': False,
         'role': 'INDEPENDENT_STDLIB_STORED_CONTENT_REVIEW_NOT_SCIENCE_GATE'})
    clock = time.monotonic()
    env = dict(os.environ)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        with (capture / 'stdout.log').open('xb') as stdout, (capture / 'stderr.log').open('xb') as stderr:
            native = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                    check=False, timeout=900)
    except subprocess.TimeoutExpired:
        save(capture / 'timeout.json', {'observed_at_utc': datetime.now(timezone.utc).isoformat(),
             'native_exit_not_fabricated': True, 'automatic_retry': False})
        raise
    after = inputs()
    result = {'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'elapsed_seconds': time.monotonic() - clock, 'native_exit_code': native.returncode,
              'input_bytes_unchanged': before == after, 'input_binding_after': after,
              'stdout': meta(capture / 'stdout.log'), 'stderr': meta(capture / 'stderr.log'),
              'automatic_retry': False, 'scientific_qualification': False}
    if (HERE / 'stored_audit_result.json').exists():
        result['stored_audit_result'] = meta(HERE / 'stored_audit_result.json')
    save(capture / 'exit.json', result)
    print(json.dumps({k: v for k, v in result.items() if k != 'input_binding_after'},
                     ensure_ascii=True, sort_keys=True, separators=(',', ':')), flush=True)
    return 0 if native.returncode == 0 and before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
