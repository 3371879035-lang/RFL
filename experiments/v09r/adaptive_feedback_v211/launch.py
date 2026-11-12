"""One exclusive 24-shard matrix, four child processes, never automatic retry."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def write_new(path, result):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def run_one(job):
    family, seed = job
    folder = HERE/'shards'/f'{family}_s{seed:02d}'
    folder.mkdir(parents=True, exist_ok=True)
    started, timer = datetime.now(timezone.utc).isoformat(), time.perf_counter()
    code, timeout = None, False
    with (folder/'native.stdout.log').open('x', encoding='utf-8') as stdout, \
            (folder/'native.stderr.log').open('x', encoding='utf-8') as stderr:
        try:
            run = subprocess.run([sys.executable, '-B', str(HERE/'run_shard.py'), family, str(seed)],
                                 cwd=HERE.parents[2], env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                                 stdout=stdout, stderr=stderr, timeout=180, check=False)
            code = run.returncode
        except subprocess.TimeoutExpired:
            timeout = True
    result = {'family': family, 'seed': seed, 'started_utc': started,
              'finished_utc': datetime.now(timezone.utc).isoformat(), 'exit_code': code,
              'timed_out': timeout, 'wall_seconds': time.perf_counter()-timer}
    write_new(folder/'exit.json', result)
    print(json.dumps(result), flush=True)
    return result


def main():
    contract = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    started, timer = datetime.now(timezone.utc).isoformat(), time.perf_counter()
    write_new(HERE/'claim.json', {'utc': started, 'pid': os.getpid(), 'workers': 4})
    jobs = [(family, seed) for family in contract['families'] for seed in contract['seeds']]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run_one, jobs))
    result = {'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
              'wall_seconds': time.perf_counter()-timer, 'shards': results,
              'completed': sum(x['exit_code'] == 0 for x in results),
              'failed_or_timed_out': sum(x['exit_code'] != 0 for x in results)}
    write_new(HERE/'native_exit.json', result)
    return int(result['failed_or_timed_out'] > 0)


if __name__ == '__main__':
    raise SystemExit(main())
