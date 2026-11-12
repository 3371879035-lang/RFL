from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[2]


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, value):
    with p.open('x', encoding='utf-8') as f: json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)


def main():
    cap = HERE/'capture'; cap.mkdir(exist_ok=False)
    contract = json.loads((HERE/'contract.json').read_text())
    previous_path = ROOT/'experiments/v09r/real_credit_v224/source_binding.json'
    pins = json.loads(previous_path.read_text())['input_and_delivery_sha256']; previous = len(pins)
    for name, digest in pins.items(): assert sha(ROOT/name) == digest, name
    pins[previous_path.relative_to(ROOT).as_posix()] = sha(previous_path)
    for directory in (HERE, ROOT/'src/feedback_program_v225', ROOT/'docs/feedback_math/online_filter_v225'):
        for p in directory.iterdir():
            if p.is_file(): pins[p.relative_to(ROOT).as_posix()] = sha(p)
    save(cap/'claim.json', dict(utc=datetime.now(timezone.utc).isoformat(),
        head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        previous_preserved_inputs=previous, input_sha256=pins, automatic_retries=0))
    start = time.perf_counter(); status = dict(first_run_exit=None, audit_exit=None, timeout=False, automatic_retries=0)
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
    try:
        for file, key in [('probe.py', 'first_run_exit'), ('audit.py', 'audit_exit')]:
            with (cap/(file+'.stdout.txt')).open('x', encoding='utf-8') as out, (cap/(file+'.stderr.txt')).open('x', encoding='utf-8') as err:
                result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(HERE/file)], cwd=ROOT, env=env,
                    stdout=out, stderr=err, timeout=max(1., contract['wall_budget_seconds']-(time.perf_counter()-start)))
            status[key] = result.returncode
            if result.returncode: break
    except subprocess.TimeoutExpired:
        status['timeout'] = True
    finally:
        status.update(wall_seconds=time.perf_counter()-start, input_count=len(pins),
            changed_inputs=[name for name, digest in pins.items() if sha(ROOT/name) != digest], utc=datetime.now(timezone.utc).isoformat())
        save(cap/'exit.json', status); print(json.dumps(status, indent=2))
    return 0 if status['first_run_exit'] == status['audit_exit'] == 0 and not status['timeout'] and not status['changed_inputs'] else 1


if __name__ == '__main__': sys.exit(main())
