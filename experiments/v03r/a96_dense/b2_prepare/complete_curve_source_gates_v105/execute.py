"""One exclusive first native capture of serial source-mutation gates."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
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
    frozen = json.loads((ROOT / c['frozen_manifest']).read_bytes())['sources']
    for name, digest in frozen.items():
        if meta(ROOT / name)['sha256'] != digest:
            raise RuntimeError('frozen source drift: ' + name)
    names = set(frozen) | {c['frozen_manifest'], 'experiments/rebuild_status_current.json'}
    for key in ('reference_input', 'authorization', 'healthy_reference', 'preserved_core', 'preserved_handoff'):
        spec = c[key]
        if meta(ROOT / spec['path'])['sha256'] != spec['sha256']:
            raise RuntimeError('declared dependency drift: ' + spec['path'])
        names.add(spec['path'])
    # Transitive loaded implementation sources are declared, without touching unrelated data directories.
    names |= {p.relative_to(ROOT).as_posix() for p in (ROOT/'src').rglob('*.py')}
    names |= {p.relative_to(ROOT).as_posix() for p in HERE.parent.glob('*.py')}
    for namespace in ('adaptive_training_v90', 'owned_adaptive_handoff_v92', 'owned_curve_connector_v95'):
        names |= {p.relative_to(ROOT).as_posix() for p in (HERE.parent / namespace).glob('*.py')}
    names |= {(HERE / n).relative_to(ROOT).as_posix() for n in
              ('build_variants.py', 'test_source_gates.py', 'execute.py', 'contract.json', 'variant_manifest.json')}
    names |= {p.relative_to(ROOT).as_posix() for p in (HERE/'variants').rglob('*.py')}
    return {name: meta(ROOT/name) for name in sorted(names)}


def main():
    c = json.loads((HERE/'contract.json').read_bytes())
    parent = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if parent != c['parent_commit']:
        raise RuntimeError('parent changed before capture')
    if shutil.disk_usage(ROOT).free < c['budget']['min_free_disk_bytes']:
        raise RuntimeError('capture disk reserve unavailable')
    out = HERE/'evidence'
    if out.exists():
        raise RuntimeError('exclusive capture exists; no retry')
    before = binding(c)
    out.mkdir()
    command = [sys.executable, '-X', 'utf8', '-B', str(HERE/'test_source_gates.py')]
    started = datetime.now(timezone.utc).isoformat()
    save(out/'claim.json', {'parent_commit': parent, 'started_at_utc': started, 'command': command,
                          'input_binding_before': before, 'automatic_retry': False,
                          'role': 'V105_NEW_COMPLETE_ENTRY_SERIAL_SOURCE_MUTANTS_NO_SCIENTIFIC_COLLECTION'})
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
               'input_binding_after': after, 'input_bytes_unchanged': before == after,
               'stdout': meta(out/'stdout.log'), 'stderr': meta(out/'stderr.log'),
               'automatic_retry': False, 'scientific_qualification': False}
    receipt['capture_budget_met'] = all(receipt[key]['bytes'] <= c['budget'][key+'_bytes'] for key in ('stdout', 'stderr'))
    save(out/'exit.json', receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != 'input_binding_after'}))
    return result.returncode if before == after and receipt['capture_budget_met'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

