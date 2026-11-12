"""Exclusive bounded local run. No automatic retry, automation or cloud service."""
import argparse
import ctypes
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--mode', choices=['smoke', 'long'], required=True)
args = parser.parse_args()
mode = args.mode
limit = 900 if mode == 'smoke' else 43200
# Process/thread scoped; do not change global power settings or force the display on.
awake_result = ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
started = time.perf_counter()
command = [sys.executable, '-X', 'utf8', '-B', str(HERE/'run.py'), '--mode', mode]
with (HERE/f'launch_{mode}.json').open('x', encoding='utf-8') as f:
    json.dump(dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   command=command, wall_budget_seconds=limit,
                   process_scoped_system_awake=bool(awake_result), display_forced_on=False), f)
peak = 0
disk_bytes = 0
disk_at = 0.
reason = None
with (HERE/f'native_{mode}.stdout.log').open('xb') as out, (HERE/f'native_{mode}.stderr.log').open('xb') as err:
    process = subprocess.Popen(command, cwd=HERE, stdout=out, stderr=err,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    while process.poll() is None:
        try:
            tree = [psutil.Process(process.pid)]
            tree += tree[0].children(recursive=True)
            ram = 0
            for child in tree:
                try:
                    ram += child.memory_info().rss
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            tree, ram = [], 0
        peak = max(peak, ram)
        elapsed = time.perf_counter()-started
        if elapsed-disk_at >= 60:
            folder = HERE/f'evidence_{mode}'
            disk_bytes = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
            disk_at = elapsed
        if elapsed > limit:
            reason = 'WALL_BUDGET'
        elif ram > 25769803776:
            reason = 'RAM_BUDGET'
        elif disk_bytes > 51539607552:
            reason = 'ARTIFACT_BUDGET'
        if reason:
            for child in reversed(tree):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            if process.poll() is None:
                process.kill()
            break
        time.sleep(5)
    code = process.wait()
row = dict(exit_code=code, interruption=reason, wall_seconds=time.perf_counter()-started,
           peak_tree_rss=peak, last_artifact_bytes=disk_bytes,
           finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
with (HERE/f'native_{mode}_exit.json').open('x', encoding='utf-8') as f:
    json.dump(row, f, indent=2)
print(json.dumps(row), flush=True)
with (HERE/f'analysis_{mode}.stdout.log').open('xb') as out, (HERE/f'analysis_{mode}.stderr.log').open('xb') as err:
    analysis = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(HERE/'finish_report.py'), '--mode', mode],
                              cwd=HERE, stdout=out, stderr=err, timeout=600,
                              creationflags=subprocess.CREATE_NO_WINDOW)
with (HERE/f'analysis_{mode}_exit.json').open('x', encoding='utf-8') as f:
    json.dump(dict(exit_code=analysis.returncode), f)
ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
raise SystemExit((code or analysis.returncode) if reason is None else 1)
