"""Single-use test-only engineering capture; never overwrite receipts or retry."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

folder = Path(__file__).resolve().parent
root = folder.parents[4]
output = folder / 'evidence_corrected'
output.mkdir(exist_ok=False)
command = [sys.executable, '-X', 'utf8', '-B', str(folder/'candidate_corrected.py')]
claim = {'role': 'SINGLE_USE_TEST_ONLY_ENGINEERING_NOT_SCIENTIFIC_COLLECTION',
         'command': command, 'start_utc': datetime.now(timezone.utc).isoformat(), 'cwd': str(root),
         'inputs': {p.name: sha256(p.read_bytes()).hexdigest() for p in
                    (folder/'candidate_corrected.py', folder/'contract.json', folder/'repair_contract.json', Path(__file__))}}
with (output/'claim.json').open('x', encoding='utf8') as stream:
    json.dump(claim, stream, ensure_ascii=True, indent=2)
with (output/'stdout.log').open('xb') as stdout, (output/'stderr.log').open('xb') as stderr:
    process = subprocess.Popen(command, cwd=root, stdout=stdout, stderr=stderr)
    print(json.dumps({'child_pid': process.pid, 'command': command, 'start_utc': claim['start_utc']}), flush=True)
    code = process.wait()
receipt = {**claim, 'finish_utc': datetime.now(timezone.utc).isoformat(), 'native_child_exit_code': code,
           'files': {p.name: {'bytes': p.stat().st_size, 'sha256': sha256(p.read_bytes()).hexdigest()}
                     for p in (output/'stdout.log', output/'stderr.log')},
           'scientific_PASS': False, 'collection_authorized': False, 'research_complete': False}
with (output/'exit.json').open('x', encoding='utf8') as stream:
    json.dump(receipt, stream, ensure_ascii=True, indent=2)
print(json.dumps(receipt, sort_keys=True), flush=True)
sys.exit(code)
