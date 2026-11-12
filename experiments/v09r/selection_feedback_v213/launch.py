"""One exclusive bounded run; preserve every first failure; no auto retries."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    contract = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    before = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in contract['input_sha256']}
    assert before == contract['input_sha256']
    with (HERE/'claim.json').open('x', encoding='utf-8') as f:
        json.dump({'utc': datetime.now(timezone.utc).isoformat(),
                   'contract_sha256': hashlib.sha256((HERE/'contract.json').read_bytes()).hexdigest()}, f)
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    started = time.perf_counter()
    results = []
    for label, program in [('check', 'check_model.py'), ('native', 'experiment.py'), ('review', 'review.py')]:
        begin = datetime.now(timezone.utc).isoformat()
        tick = time.perf_counter()
        with (HERE/f'{label}.stdout.log').open('xb') as out, (HERE/f'{label}.stderr.log').open('xb') as err:
            process = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', str(HERE/program)],
                                       cwd=ROOT, env=env, stdout=out, stderr=err)
            timed_out = False
            try:
                exit_code = process.wait(timeout=max(1., 600.-(time.perf_counter()-started)))
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(); exit_code = None; timed_out = True
        result = {'stage': label, 'started_utc': begin, 'finished_utc': datetime.now(timezone.utc).isoformat(),
                  'exit_code': exit_code, 'timed_out': timed_out, 'wall_seconds': time.perf_counter()-tick}
        results.append(result)
        with (HERE/f'{label}_exit.json').open('x', encoding='utf-8') as f: json.dump(result, f, indent=2)
        print(json.dumps(result), flush=True)
        if exit_code != 0 or timed_out: break
    after = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in before}
    with (HERE/'exit.json').open('x', encoding='utf-8') as f:
        json.dump({'stages': results, 'inputs_unchanged': after == before,
                   'wall_seconds': time.perf_counter()-started}, f, indent=2)
    assert before == after
    return int(len(results) != 3 or any(r['exit_code'] != 0 for r in results))


if __name__ == '__main__': sys.exit(main())
