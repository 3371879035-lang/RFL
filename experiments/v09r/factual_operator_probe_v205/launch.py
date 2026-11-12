"""Exclusive, bounded native capture; failure and timeout are not retried."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sources = [HERE / name for name in ('contract.json', 'tasks.py', 'run.py', 'launch.py', 'analyze.py')]
sources += [ROOT / 'src' / 'feedback_program_v205' / name for name in ('__init__.py', 'network.py')]
pins = lambda: {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
before = pins()
with (HERE / 'claim.json').open('x', encoding='utf-8') as f:
    json.dump(dict(start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), inputs=before), f, indent=2)
started = time.perf_counter()
with (HERE / 'native.stdout.log').open('xb') as out, (HERE / 'native.stderr.log').open('xb') as err:
    try:
        run = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(HERE / 'run.py')], cwd=ROOT,
                             stdout=out, stderr=err, timeout=900, creationflags=subprocess.CREATE_NO_WINDOW)
        code, timed_out = run.returncode, False
    except subprocess.TimeoutExpired:
        code, timed_out = None, True
receipt = dict(exit_code=code, timeout=timed_out, wall_seconds=time.perf_counter() - started,
               end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), inputs_before=before,
               inputs_after=pins())
with (HERE / 'native_exit.json').open('x', encoding='utf-8') as f:
    json.dump(receipt, f, indent=2)
print(json.dumps({k: v for k, v in receipt.items() if not k.startswith('inputs')}))
sys.exit(124 if timed_out else code)
