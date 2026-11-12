"""One independent stdlib audit of the preserved v104 setup failure."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def meta(path):
    h = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            size += len(block)
            h.update(block)
    return {'bytes': size, 'sha256': h.hexdigest()}


def main():
    c = json.loads((HERE/'contract.json').read_bytes())
    claim = json.loads((HERE/'evidence/claim.json').read_bytes())
    receipt = json.loads((HERE/'evidence/exit.json').read_bytes())
    pins = claim['input_binding_before']
    assert pins == receipt['input_binding_after'] and receipt['input_bytes_unchanged']
    assert receipt['child_exit_code'] == 1 and not receipt['automatic_retry']
    for name, pin in pins.items():
        assert meta(ROOT/name) == pin, name
    for name in ('stdout', 'stderr'):
        assert meta(HERE/'evidence'/f'{name}.log') == receipt[name]
    records = []
    with (HERE/'evidence/stdout.log').open(encoding='utf-8') as stream:
        for line in stream:
            item = json.loads(line)
            assert json.dumps(item, sort_keys=True, separators=(',', ':'), ensure_ascii=True) == line.rstrip('\n')
            records.append(item)
    assert records == [{'case':'setup', 'stage':'setup', 'tag':'REFERENCE',
                        'payload':{'digest':c['reference_input']['q_digest'], 'rows':13824}}]
    error = (HERE/'evidence/stderr.log').read_text(encoding='utf-8')
    assert "ROOT / CONTRACT['healthy_reference']" in error
    assert "TypeError: unsupported operand type(s) for /: 'WindowsPath' and 'dict'" in error
    out = {'schema':'V104_INDEPENDENT_STORED_SETUP_FAILURE_AUDIT',
           'native_exit_preserved':1, 'records':len(records), 'input_binding_pins':len(pins),
           'failure_before_fresh_source_or_kernel':True,
           'rollout':0, 'step':0, 'B1':0, 'transaction':0, 'source_level_mutant_cases':0,
           'Q_reference_construction_rows':13824, 'automatic_retry':False,
           'RFL_or_old_checker_execution':False, 'runtime_identity_reconstructed':False,
           'scientific_qualification':False, 'audit_source':meta(Path(__file__)),
           'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    with (HERE/'stored_audit_result.json').open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(out,stream,sort_keys=True,separators=(',',':'),ensure_ascii=True)
        stream.write('\n')
    print(json.dumps(out,sort_keys=True,separators=(',',':'),ensure_ascii=True))


if __name__ == '__main__':
    main()
