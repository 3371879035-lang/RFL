"""Exclusive one-shot new owned-handoff child, not any historical fixture."""
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
    return {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def save(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        stream.write('\n')


def binding(c):
    frozen = json.loads((ROOT/c['frozen_manifest']).read_bytes())['sources']
    for name, expected in frozen.items():
        if meta(ROOT/name)['sha256'] != expected:
            raise RuntimeError('frozen source drift '+name)
    for field, pin in (('unchanged_core', 'unchanged_core_sha256'), ('healthy_reference', 'healthy_reference_sha256')):
        if meta(ROOT/c[field])['sha256'] != c[pin]:
            raise RuntimeError('preserved core/reference drift '+field)
    if meta(ROOT/c['reference_input']['path'])['sha256'] != c['reference_input']['sha256']:
        raise RuntimeError('stored reference drift')
    names = set(frozen) | {c['frozen_manifest'], c['unchanged_core'], c['healthy_reference'], c['reference_input']['path']}
    names |= {str((HERE.parent/name).relative_to(ROOT)).replace('\\', '/') for name in c['unchanged_libraries']}
    for namespace in c['preserve_previous_namespaces']:
        names |= {str(p.relative_to(ROOT)).replace('\\', '/') for p in (HERE.parent/namespace).rglob('*') if p.is_file()}
    names.add(str((HERE.parent/c['preserve_previous_audit']).relative_to(ROOT)).replace('\\', '/'))
    names |= {str(p.relative_to(ROOT)).replace('\\', '/') for p in HERE.iterdir() if p.is_file()}
    return {name: meta(ROOT/name) for name in sorted(names)}


def main():
    c = json.loads((HERE/'contract.json').read_bytes())
    parent = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if parent != c['parent_commit']:
        raise RuntimeError('wrong parent; no child')
    out = HERE/'evidence'
    if out.exists():
        raise RuntimeError('exclusive capture exists; no retry')
    before = binding(c)
    out.mkdir()
    start = datetime.now(timezone.utc).isoformat()
    command = [sys.executable, '-X', 'utf8', '-B', str(HERE/'test_handoff.py')]
    save(out/'claim.json', {'parent_commit': parent, 'command': command, 'started_at_utc': start,
                          'input_binding_before': before, 'automatic_retry': False,
                          'role': 'NEW_REAL_OWNED_WHOLE_B1_HANDOFF_NOT_HISTORICAL_RERUN'})
    env = dict(os.environ)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        with (out/'stdout.log').open('xb') as stdout, (out/'stderr.log').open('xb') as stderr:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                    check=False, timeout=c['budget']['seconds']+30)
    except subprocess.TimeoutExpired:
        save(out/'timeout.json', {'observed_at_utc': datetime.now(timezone.utc).isoformat(),
                                 'native_exit_not_fabricated': True, 'automatic_retry': False})
        raise
    after = binding(c)
    receipt = {'child_exit_code': result.returncode, 'started_at_utc': start,
               'completed_at_utc': datetime.now(timezone.utc).isoformat(),
               'stdout': meta(out/'stdout.log'), 'stderr': meta(out/'stderr.log'),
               'input_binding_after': after, 'input_bytes_unchanged': before == after,
               'automatic_retry': False, 'scientific_qualification': False}
    receipt['capture_budget_met'] = receipt['stdout']['bytes'] <= c['budget']['stdout_bytes'] and receipt['stderr']['bytes'] <= c['budget']['stderr_bytes']
    save(out/'exit.json', receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k != 'input_binding_after'}))
    return result.returncode if before == after and receipt['capture_budget_met'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
