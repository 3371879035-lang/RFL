"""First exclusive v99 stdlib-only performance diagnostic, no automatic retry."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def meta(path):
    return {'bytes': path.stat().st_size, 'sha256': sha256(path.read_bytes()).hexdigest()}


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        stream.write('\n')


def main():
    c = json.loads((HERE/'contract.json').read_bytes())
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == c['parent_commit']
    names = set(c['inputs']) | {p.relative_to(ROOT).as_posix() for p in HERE.iterdir() if p.is_file()}
    before = {n: meta(ROOT/n) for n in sorted(names)}
    for n, h in c['inputs'].items():
        assert before[n]['sha256'] == h
    out = HERE/'evidence'
    assert not out.exists(), 'exclusive capture exists; no retry'
    out.mkdir()
    started = datetime.now(timezone.utc).isoformat()
    command = [sys.executable, '-X', 'utf8', '-B', str(HERE/'benchmark.py')]
    save(out/'claim.json', {'started_at_utc': started, 'command': command,
         'input_binding_before': before, 'automatic_retry': False, 'native_execution': False})
    env = dict(os.environ); env['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        with (out/'stdout.log').open('xb') as stdout, (out/'stderr.log').open('xb') as stderr:
            child = subprocess.run(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                   check=False, timeout=c['budget']['seconds']+15)
    except subprocess.TimeoutExpired:
        save(out/'timeout.json', {'observed_at_utc': datetime.now(timezone.utc).isoformat(),
             'native_exit_not_fabricated': True, 'automatic_retry': False})
        raise
    after = {n: meta(ROOT/n) for n in sorted(names)}
    receipt = {'child_exit_code': child.returncode, 'started_at_utc': started,
        'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'automatic_retry': False,
        'input_binding_after': after, 'input_bytes_unchanged': before == after,
        'stdout': meta(out/'stdout.log'), 'stderr': meta(out/'stderr.log'), 'native_execution': False}
    save(out/'exit.json', receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k != 'input_binding_after'}))
    return child.returncode if before == after else 2


if __name__ == '__main__':
    raise SystemExit(main())
