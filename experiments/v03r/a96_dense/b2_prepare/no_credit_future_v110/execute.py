"""Exclusive first genuine T empty-projection future capture; no retry."""
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
        if meta(ROOT / name)['sha256'] != pin:
            raise RuntimeError('frozen source drift: ' + name)
    names = set(frozen) | {contract['frozen_manifest'], 'experiments/rebuild_status_current.json'}
    for key in ('reference_input', 'healthy_reference', 'authorization', 'dev_lock', 'preserved_core', 'preserved_handoff'):
        entry = contract[key]
        if meta(ROOT / entry['path'])['sha256'] != entry['sha256']:
            raise RuntimeError('preserved input drift: ' + entry['path'])
        names.add(entry['path'])
    names |= {path.relative_to(ROOT).as_posix() for path in (ROOT / 'src').rglob('*.py')}
    names |= {path.relative_to(ROOT).as_posix() for path in HERE.parent.glob('*.py')}
    for folder in ('adaptive_training_v90', 'owned_adaptive_handoff_v92',
                   'complete_curve_source_gates_v105/variants/normal', 'readonly_bank_optimization_v107'):
        names |= {path.relative_to(ROOT).as_posix() for path in (HERE.parent / folder).glob('*.py')}
    names |= {(HERE / name).relative_to(ROOT).as_posix() for name in ('nocredit.py', 'test_new.py', 'execute.py', 'contract.json')}
    return {name: meta(ROOT / name) for name in sorted(names)}


def main():
    contract = json.loads((HERE / 'contract.json').read_bytes())
    parent = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if parent != contract['parent_commit']:
        raise RuntimeError('actual parent changed')
    if shutil.disk_usage(ROOT).free < contract['budget']['minimum_disk_free_bytes']:
        raise RuntimeError('disk reserve')
    out = HERE / 'evidence'
    if out.exists():
        raise RuntimeError('exclusive capture already exists; no automatic retry')
    before = binding(contract)
    out.mkdir()
    started = datetime.now(timezone.utc).isoformat()
    command = [sys.executable, '-X', 'utf8', '-B', str(HERE / 'test_new.py')]
    save(out / 'claim.json', {'parent_commit': parent, 'started_at_utc': started, 'command': command,
                             'input_binding_before': before, 'automatic_retry': False,
                             'role': 'V110_FIRST_GENUINE_T_NO_CREDIT_ORDINARY_FUTURE',
                             'fresh_keys_allocated': 0, 'formal_collection_enabled': False})
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
               'scientific_qualification': False, 'formal_collection_enabled': False}
    for name in ('raw.jsonl', 'child_summary.json'):
        if (out / name).exists():
            receipt[name] = meta(out / name)
    save(out / 'exit.json', receipt)
    print(json.dumps({key: value for key, value in receipt.items() if key != 'input_binding_after'}), flush=True)
    return 0 if child.returncode == 0 and before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
