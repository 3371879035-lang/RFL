"""One finite, exclusive evaluation. Preserve the first failure; no retry."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import time

here = Path(__file__).resolve().parent
started = time.perf_counter()
with (here / 'native.stdout.log').open('xb') as stdout, (here / 'native.stderr.log').open('xb') as stderr:
    child = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', str(here / 'run.py')],
                             cwd=here, stdout=stdout, stderr=stderr)
    try:
        code, interruption = child.wait(timeout=900), None
    except subprocess.TimeoutExpired:
        # This process tree was created here and is the only termination target.
        subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                       stdout=stdout, stderr=stderr, check=False)
        child.wait()
        code, interruption = None, '900 second declared evaluation deadline'
with (here / 'native_exit.json').open('x', encoding='utf-8', newline='\n') as stream:
    json.dump(dict(exit_code=code, interruption=interruption,
                   wall_seconds=time.perf_counter() - started,
                   finished_utc=dt.datetime.now(dt.timezone.utc).isoformat()), stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(exit_code=code, interruption=interruption,
                     wall_seconds=time.perf_counter() - started)))
sys.exit(code if code is not None else 124)
