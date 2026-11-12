"""Queue one six-hour continuation after the intact twelve-hour run finishes."""
import ctypes
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent/'overnight_five_arm_v198'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def parent_status(native, analysis):
    if native is None:
        return 'WAITING'
    if native['exit_code'] != 0 or native['interruption'] is not None:
        return 'FAILED'
    if analysis is None:
        return 'WAITING'
    return 'READY' if analysis['exit_code'] == 0 else 'FAILED'


def main():
    awake = ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    write(HERE/'queue_claim.json', dict(queued_utc=now(), parent=str(PARENT),
          additional_wall_seconds=21600, maximum_dependency_wait_seconds=7200,
          process_scoped_system_awake=bool(awake), display_forced_on=False,
          automation_created=False, policy='Wait for parent success; no retry, reset or performance selection.'))
    waiting = time.perf_counter()
    while True:
        np = PARENT/'native_long_exit.json'
        ap = PARENT/'analysis_long_exit.json'
        native = read(np) if np.exists() else None
        analysis = read(ap) if ap.exists() else None
        status = parent_status(native, analysis)
        if status == 'READY':
            break
        if status == 'FAILED' or time.perf_counter()-waiting > 7200:
            write(HERE/'dependency_exit.json', dict(status=status, finished_utc=now(),
                  reason='Parent failed or dependency wait expired; extension NOT started.'))
            return 1
        time.sleep(30)
    start = time.perf_counter()
    command = [sys.executable, '-X', 'utf8', '-B', str(HERE/'continue_run.py')]
    write(HERE/'launch.json', dict(started_utc=now(), command=command, wall_budget_seconds=21600,
          dependency_wait_seconds=start-waiting, process_scoped_system_awake=bool(awake),
          display_forced_on=False))
    peak = disk = 0
    checked_at = 0.
    reason = None
    with (HERE/'native.stdout.log').open('xb') as stdout, (HERE/'native.stderr.log').open('xb') as stderr:
        child = subprocess.Popen(command, cwd=HERE, stdout=stdout, stderr=stderr,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        while child.poll() is None:
            try:
                root = psutil.Process(child.pid)
                tree = [root]+root.children(recursive=True)
            except psutil.NoSuchProcess:
                tree = []
            ram = 0
            for proc in tree:
                try:
                    ram += proc.memory_info().rss
                except psutil.NoSuchProcess:
                    pass
            peak = max(peak, ram)
            elapsed = time.perf_counter()-start
            if elapsed-checked_at >= 60:
                disk = sum(p.stat().st_size for p in (HERE/'evidence').rglob('*') if p.is_file())
                checked_at = elapsed
            if elapsed > 21600:
                reason = 'WALL_BUDGET'
            elif ram > 25769803776:
                reason = 'RAM_BUDGET'
            elif disk > 34359738368:
                reason = 'ARTIFACT_BUDGET'
            if reason:
                for proc in reversed(tree):
                    try:
                        proc.kill()
                    except psutil.NoSuchProcess:
                        pass
                if child.poll() is None:
                    child.kill()
                break
            time.sleep(5)
        code = child.wait()
    receipt = dict(exit_code=code, interruption=reason, wall_seconds=time.perf_counter()-start,
                   peak_tree_rss=peak, last_artifact_bytes=disk, finished_utc=now())
    write(HERE/'native_exit.json', receipt)
    remaining = 21600-(time.perf_counter()-start)
    if remaining <= 0:
        write(HERE/'analysis_exit.json', dict(exit_code=None, reason='No remaining wall budget'))
        return 1
    with (HERE/'analysis.stdout.log').open('xb') as out, (HERE/'analysis.stderr.log').open('xb') as err:
        try:
            done = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(HERE/'finish_report.py')],
                                  cwd=HERE, stdout=out, stderr=err,
                                  timeout=min(600, remaining), creationflags=subprocess.CREATE_NO_WINDOW)
            analysis_result = dict(exit_code=done.returncode)
        except subprocess.TimeoutExpired:
            analysis_result = dict(exit_code=None, reason='Analysis time budget')
    write(HERE/'analysis_exit.json', dict(**analysis_result, finished_utc=now(),
                                         total_extension_wall_seconds=time.perf_counter()-start))
    return 0 if code == 0 and reason is None and analysis_result['exit_code'] == 0 else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
