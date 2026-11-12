"""Exclusive one-shot new owned active-X response, not v92/old fixture rerun."""
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
        json.dump(data, stream, sort_keys=True, separators=(',', ':'), ensure_ascii=True); stream.write('\n')


def binding(c):
    frozen = json.loads((ROOT/c['frozen_manifest']).read_bytes())['sources']
    for name, pin in frozen.items():
        if meta(ROOT/name)['sha256'] != pin: raise RuntimeError('frozen drift '+name)
    for path, pin in (('unchanged_core', 'unchanged_core_sha256'), ('unchanged_handoff', 'unchanged_handoff_sha256'),
                      ('healthy_reference', 'healthy_reference_sha256')):
        if meta(ROOT/c[path])['sha256'] != c[pin]: raise RuntimeError('preserved source/reference drift '+path)
    if meta(ROOT/c['reference_input']['path'])['sha256'] != c['reference_input']['sha256']:
        raise RuntimeError('stored reference drift')
    names = set(frozen)|{c['frozen_manifest'], c['unchanged_core'], c['unchanged_handoff'], c['healthy_reference'], c['reference_input']['path']}
    names |= {str((HERE.parent/n).relative_to(ROOT)).replace('\\', '/') for n in c['unchanged_libraries']+c['preserve_sibling_sources']}
    for namespace in c['preserve_namespaces']:
        names |= {str(p.relative_to(ROOT)).replace('\\', '/') for p in (HERE.parent/namespace).rglob('*') if p.is_file()}
    names |= {str(p.relative_to(ROOT)).replace('\\', '/') for p in HERE.iterdir() if p.is_file()}
    return {name: meta(ROOT/name) for name in sorted(names)}


def main():
    c = json.loads((HERE/'contract.json').read_bytes())
    parent = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if parent != c['parent_commit']: raise RuntimeError('wrong parent; no child')
    out = HERE/'evidence'
    if out.exists(): raise RuntimeError('exclusive capture exists; no retry')
    before = binding(c); out.mkdir(); started = datetime.now(timezone.utc).isoformat()
    command = [sys.executable, '-X', 'utf8', '-B', str(HERE/'test_owned_response.py')]
    save(out/'claim.json', {'parent_commit': parent, 'command': command, 'started_at_utc': started,
                          'input_binding_before': before, 'automatic_retry': False,
                          'role': 'NEW_REQUIRED_OWNED_ACTIVE_X_VALUE_CONTENT_BRANCH_NOT_V92_RETRY'})
    env = dict(os.environ); env['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        with (out/'stdout.log').open('xb') as stdout, (out/'stderr.log').open('xb') as stderr:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                    check=False, timeout=c['budget']['seconds']+30)
    except subprocess.TimeoutExpired:
        save(out/'timeout.json', {'observed_at_utc': datetime.now(timezone.utc).isoformat(),
                                 'native_exit_not_fabricated': True, 'automatic_retry': False})
        raise
    after = binding(c)
    receipt = {'child_exit_code': result.returncode, 'started_at_utc': started,
               'completed_at_utc': datetime.now(timezone.utc).isoformat(),
               'stdout': meta(out/'stdout.log'), 'stderr': meta(out/'stderr.log'),
               'input_binding_after': after, 'input_bytes_unchanged': before == after,
               'automatic_retry': False, 'scientific_qualification': False}
    receipt['capture_budget_met'] = receipt['stdout']['bytes'] <= c['budget']['stdout_bytes'] and receipt['stderr']['bytes'] <= c['budget']['stderr_bytes']
    save(out/'exit.json', receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k != 'input_binding_after'}))
    return result.returncode if before == after and receipt['capture_budget_met'] else 2


if __name__ == '__main__': raise SystemExit(main())
