"""Exclusive first finite v107 native capture; no retry or old fixture calls."""
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
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
            size += len(block)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def save(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        stream.write('\n')


def binding(contract):
    frozen = json.loads((ROOT / contract['frozen_manifest']).read_bytes())['sources']
    for name, pin in frozen.items():
        assert meta(ROOT / name)['sha256'] == pin, 'frozen drift: ' + name
    names = set(frozen) | {contract['frozen_manifest'], 'experiments/rebuild_status_current.json'}
    for key in ('reference_input', 'healthy_reference', 'authorization', 'dev_lock', 'preserved_core', 'preserved_handoff'):
        spec = contract[key]
        assert type(spec['path']) is str and meta(ROOT / spec['path'])['sha256'] == spec['sha256']
        names.add(spec['path'])
    names |= {path.relative_to(ROOT).as_posix() for path in (ROOT / 'src').rglob('*.py')}
    names |= {path.relative_to(ROOT).as_posix() for path in HERE.parent.glob('*.py')}
    for folder in ('adaptive_training_v90', 'owned_adaptive_handoff_v92'):
        names |= {path.relative_to(ROOT).as_posix() for path in (HERE.parent / folder).glob('*.py')}
    names |= {path.relative_to(ROOT).as_posix()
              for path in (HERE.parent / 'complete_curve_source_gates_v105/variants/normal').glob('*.py')}
    names |= {(HERE / name).relative_to(ROOT).as_posix() for name in ('bank.py', 'test_new.py', 'execute.py', 'contract.json')}
    return {name: meta(ROOT / name) for name in sorted(names)}


def main():
    contract = json.loads((HERE / 'contract.json').read_bytes())
    parent = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert parent == contract['parent_commit'], 'actual parent changed'
    assert shutil.disk_usage(ROOT).free >= contract['budget']['minimum_disk_free_bytes'], 'disk reserve'
    out = HERE / 'evidence'
    assert not out.exists(), 'exclusive capture already exists; no native retry'
    before = binding(contract)
    out.mkdir()
    started = datetime.now(timezone.utc).isoformat()
    command = [sys.executable, '-X', 'utf8', '-B', str(HERE / 'test_new.py')]
    save(out / 'claim.json', {'parent_commit': parent, 'started_at_utc': started, 'command': command,
                             'input_binding_before': before, 'automatic_retry': False,
                             'role': 'V107_FIRST_FINITE_NEW_READONLY_BANK_SEMANTIC_AND_COST_VALIDATION'})
    environment = dict(os.environ)
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        with (out / 'stdout.log').open('xb') as stdout, (out / 'stderr.log').open('xb') as stderr:
            child = subprocess.run(command, cwd=ROOT, env=environment, stdout=stdout, stderr=stderr,
                                   check=False, timeout=contract['budget']['seconds'] + 30)
    except subprocess.TimeoutExpired:
        save(out / 'timeout.json', {'observed_at_utc': datetime.now(timezone.utc).isoformat(),
                                   'native_exit_not_fabricated': True, 'automatic_retry': False})
        raise
    after = binding(contract)
    receipt = {'started_at_utc': started, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
               'child_exit_code': child.returncode, 'stdout': meta(out / 'stdout.log'),
               'stderr': meta(out / 'stderr.log'), 'input_binding_after': after,
               'input_bytes_unchanged': before == after, 'automatic_retry': False,
               'scientific_qualification': False}
    for name in ('raw.jsonl', 'child_summary.json'):
        if (out / name).exists():
            receipt[name] = meta(out / name)
    save(out / 'exit.json', receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != 'input_binding_after'}), flush=True)
    return 0 if child.returncode == 0 and before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
