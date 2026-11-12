"""One exclusive local child; no retry and no old experiments invoked."""
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

here = pathlib.Path(__file__).resolve().parent
started = time.perf_counter()
with (here/'native.stdout.log').open('xb') as stdout, (here/'native.stderr.log').open('xb') as stderr:
    try:
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(here/'run.py')],
                                cwd=here, stdout=stdout, stderr=stderr, timeout=600)
        code, interruption = result.returncode, None
    except subprocess.TimeoutExpired:
        code, interruption = None, '600 second declared deadline'
with (here/'native_exit.json').open('x', encoding='utf-8') as stream:
    json.dump(dict(exit_code=code, interruption=interruption, wall_seconds=time.perf_counter()-started,
                   finished_utc=dt.datetime.now(dt.timezone.utc).isoformat()), stream, indent=2)
print(json.dumps(dict(exit_code=code, interruption=interruption, wall_seconds=time.perf_counter()-started)))
sys.exit(code if code is not None else 124)
