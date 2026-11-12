"""Exclusive first V210 check; timeout/failed captures are not retried."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


started = datetime.now(timezone.utc).isoformat()
write_new(HERE/'claim.json', {'utc': started, 'pid': os.getpid(), 'mode': 'finite_operator_check_only'})
clock = time.perf_counter()
code, timed_out = None, False
with (HERE/'checks.stdout.log').open('x', encoding='utf-8') as stdout, \
        (HERE/'checks.stderr.log').open('x', encoding='utf-8') as stderr:
    try:
        completed = subprocess.run([sys.executable, '-B', str(HERE/'checks.py')], cwd=ROOT,
                                   env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
                                   stdout=stdout, stderr=stderr, timeout=120, check=False)
        code = completed.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
result = {'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
          'wall_seconds': time.perf_counter()-clock, 'exit_code': code, 'timed_out': timed_out}
write_new(HERE/'checks_exit.json', result)
print(json.dumps(result))
raise SystemExit(124 if timed_out else code)
