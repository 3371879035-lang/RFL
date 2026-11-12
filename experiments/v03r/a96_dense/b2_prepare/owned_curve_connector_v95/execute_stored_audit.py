"""Run the new stdlib audit once with exclusive complete output capture."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'owned_curve_connector_v95_stored_audit.py'


def main():
    directory = HERE / 'evidence_stored_audit'
    directory.mkdir(exist_ok=False)
    source_bytes = SOURCE.read_bytes()
    started = datetime.now(timezone.utc).isoformat()
    with (directory / 'stdout.log').open('xb') as stdout, (directory / 'stderr.log').open('xb') as stderr:
        child = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(SOURCE)],
                               stdout=stdout, stderr=stderr, check=False, timeout=60)
    assert SOURCE.read_bytes() == source_bytes
    receipt = {'child_exit_code': child.returncode,
               'started_at_utc': started,
               'completed_at_utc': datetime.now(timezone.utc).isoformat(),
               'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
               'automatic_retry': False, 'RFL_or_old_checker_execution': False}
    for name in ('stdout', 'stderr'):
        content = (directory / f'{name}.log').read_bytes()
        receipt[name] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
    with (directory / 'exit.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(receipt, stream, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        stream.write('\n')
    print(json.dumps(receipt, sort_keys=True))
    return child.returncode


if __name__ == '__main__':
    raise SystemExit(main())
