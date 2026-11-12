"""Independent complete stored key-to-invariant check; no RFL/candidate execution."""
import ast
from collections import Counter
from hashlib import sha1, sha256
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
def read(p): return json.loads(p.read_bytes())
def canonical(o): return (json.dumps(o,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def digest(p):
    h=sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''): h.update(b)
    return h.hexdigest()
def emit(t,o): print(t+'='+canonical(o).decode().rstrip('\n'),flush=True)
def bind(c,checking=False):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    assert head==c['parent_commit']
    names={}
    for row in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0'):
        if row:
            meta,p=row.split(b'\t',1);names[p.decode()]=meta.split()[2].decode()
    assert len(names)==2503
    out={}
    for p,blob in names.items():
        raw=(ROOT/p).read_bytes()
        assert sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==blob,p
        out[p]=sha256(raw).hexdigest()
    for n in ('contract.json','candidate.py','execute.py','check_stored.py'):
        out[(HERE/n).relative_to(ROOT).as_posix()]=digest(HERE/n)
    if checking:
        for n in ('claim.json','exit.json','stdout.log','stderr.log'):
            out[(HERE/'evidence'/n).relative_to(ROOT).as_posix()]=digest(HERE/'evidence'/n)
    for path in c['baseline_indexes']:
        ix=read(ROOT/path)
        for d in ix['shards']:
            p=(ROOT/path).parent/d['path'];out[p.relative_to(ROOT).as_posix()]=digest(p)
    assert len(out)==(2575 if checking else 2571)
    return {'parent_HEAD':head,'parent_tree_paths':len(names),'distinct_inputs':len(out),'input_sha256':out}
def captured(folder,expected):
    claim=read(folder/'claim.json');receipt=read(folder/'exit.json')
    assert receipt['native_child_exit_code']==0 and all(receipt[k]==v for k,v in claim.items())
    for name,d in claim['inputs'].items():assert digest(folder.parent/name)==d
    for n,d in receipt['files'].items():
        assert (folder/n).stat().st_size==d['bytes'] and digest(folder/n)==d['sha256']
    assert receipt['files']['stdout.log']['sha256']==expected and (folder/'stderr.log').read_bytes()==b''
    with (folder/'stdout.log').open('rb') as f:
        for number,line in enumerate(f,1):
            assert line.endswith(b'\n')
            tag,v=line.rstrip(b'\r\n').split(b'=',1);o=json.loads(v)
            assert canonical(o).rstrip(b'\n')==v
            yield number,tag.decode(),o
def source_pins(c):
    for p,pin in c['sources'].items():
        raw=(ROOT/p).read_bytes();assert sha256(raw).hexdigest()==pin['sha256']
        lookup={n.name:n for n in ast.walk(ast.parse(raw)) if isinstance(n,ast.FunctionDef)}
        for n,d in pin['functions'].items():
            assert sha256(ast.dump(lookup[n],include_attributes=False).encode()).hexdigest()==d,(p,n)
    return c['sources']
def baseline_rows(c):
    base=ROOT/'experiments/v03r/a96_dense';audit=read(base/'pipeline/full_f1_complete_external_audit.json')['audit'];verified=read(base/'pipeline/runtime_verified.json')
    for receipt_name in ('development32','full_runtime','full_f1','runtime_full_verification'):
        receipt=read(base/'pipeline'/f'{receipt_name}.receipt.json');assert receipt['native_exit_code']==0
    for path in c['baseline_indexes']:
        ix=read(ROOT/path);development=path==c['baseline_indexes'][0]
        assert ix['episodes']==list(range(577)) and len(ix['shards'])==32 and ix['records']==18464
        assert ix['constants']['initializer']=='c3-temporal-layer-1-v1' and ix['constants']['layer']==1
        for p,pin in c['sources'].items():assert ix['execution']['sources'][p]==pin['sha256']
        assert digest(ROOT/path)==(audit['baseline_index_sha256'] if development else verified['index_sha256'])
        maps=audit['actual_compressed_shard_sha256'] if development else verified['compressed_sha256']
        assert set(maps)=={d['path'] for d in ix['shards']}
        proofs={} if development else {d['seed']:d for d in verified['shards']}
        for d in ix['shards']:
            p=(ROOT/path).parent/d['path'];actual=digest(p);assert actual==maps[d['path']]
            if not development:assert all(proofs[d['seed']][k]==d[k] for k in ('seed','records','pairs','sha256'))
            assert d['records']==577
            yield {'index_path':path,'shard':d,'compressed_bytes':p.stat().st_size,'actual_compressed_sha256':actual,
                   'old_complete_canonical_validation_reused_not_reexecuted':True,'fullstate_invariant_applies_e0_through576':True,
                   'raw_path_or_fullstore_not_fabricated':True}
def main():
    c=read(HERE/'contract.json');before=bind(c,True)
    source_pins(c)
    # Additional structural AST checks on exact old acquisition code, never executed.
    training=ast.parse((ROOT/'src/rfl_rebuild/b2/training.py').read_bytes())
    sweep=next(n for n in training.body if isinstance(n,ast.FunctionDef) and n.name=='sweep_edits')
    calls=[n for n in ast.walk(sweep) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='Edit']
    assert len(calls)==1 and next(k.value.id for k in calls[0].keywords if k.arg=='store')=='Q'
    acquisition=ast.parse((ROOT/'src/rfl_rebuild/b2/acquisition.py').read_bytes())
    acq=next(n for n in acquisition.body if isinstance(n,ast.FunctionDef) and n.name=='iter_master_baseline')
    assert {n.func.attr for n in ast.walk(acq) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}=={'apply_transaction','append'}
    witness=None
    for _,t,o in captured(ROOT/c['catalog_capture'],c['catalog_stdout_sha256']):
        if t=='DECISION_CONTEXT' and o['context']==c['witness_catalog_context']:witness=o
    assert witness is not None
    values=[(a,float.fromhex(v)) for a,v in witness['q_row_hex']]
    minimum=min(v for a,v in values);maximum=max(v for a,v in values)
    assert maximum>minimum and sorted(a for a,v in values if v==minimum)[0]==1
    assert tuple(c['witness_Q_address'])==(1,1,1,0,0,1,0,1) and abs(1-0)+abs(1-2)>1
    stored=iter(captured(HERE/'evidence',read(HERE/'evidence/exit.json')['files']['stdout.log']['sha256']))
    _,tag,binding=next(stored);assert tag=='INPUT_BINDING_BEFORE'
    _,tag,o=next(stored);assert tag=='BOUND_SOURCE_INVARIANT' and o=={'source_pins':c['sources'],'proof':c['proof'],'witness':c['witness_Q_address']}
    _,tag,o=next(stored);assert tag=='ORIGINAL_REFERENCE_WITNESS' and o['complete_catalog_row']==witness
    shards=list(baseline_rows(c))
    for want in shards:
        _,tag,o=next(stored);assert tag=='UNCHANGED_BASELINE_SHARD_SOURCE_EXCLUSION' and o==want
    h=sha256(b'[');n=0;pending=0;original_tags=Counter()
    for _,t,o in captured(ROOT/c['plan_capture'],c['plan_stdout_sha256']):
        original_tags[t]+=1
        if t!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert o['index']==n
        addresses={tuple(a) for a,v in o['full_four_store_entries']['Q']}
        assert tuple(c['witness_Q_address']) not in addresses
        want={'key_index':n,'complete_v55_key_row_sha256':sha256(canonical(o)).hexdigest(),
              'witness_Q_address_absent':True,'baseline_fullstore_inequality_proved':True,
              'pending_ALL_other_history_audit':o['exact_old_native_v46_v47_reference'] is None}
        _,tag,got=next(stored);assert tag=='EVERY_PLANNED_KEY_BASELINE_EXCLUSION' and got==want
        if n:h.update(b',')
        h.update(canonical(got).rstrip(b'\n'));n+=1;pending+=int(want['pending_ALL_other_history_audit'])
    h.update(b']\n');assert (n,pending)==(279158,153792)
    _,tag,after=next(stored);assert tag=='INPUT_BINDING_AFTER' and after==binding
    _,tag,final=next(stored);assert tag=='FINAL'
    assert next(stored,None) is None
    want={'status':'COMPLETE64_BASELINE_SOURCE_INVARIANT_DISJOINTNESS_NOT_ALL_HISTORY_GATE',
          'counts':{'keys':n,'pending_ALL_other_history_keys':pending},'baseline_shards':64,
          'baseline_compressed_bytes':sum(o['compressed_bytes'] for o in shards),'old_baseline_records':36928,
          'exclusion_registry_sha256':h.hexdigest(),'all64_baseline_source_contract_exclusion_closed':True,
          'ALL279158_original_keys_retained':True,'all_other_history_exclusion_complete':False,'historical_native_exclusion_complete':False,
          'native_launch_gate':False,'native_calibration_executed':False,'new_RFL_kernel_steps':0,'new_learner_rollouts':0,
          'keys_allocated':0,'random_draws':0,'future_training':0,'collector_executed':False,'collection_authorized':False,
          'scientific_rules_adopted':False,'scientific_PASS':False,'research_complete':False}
    assert final==want and before==bind(c,True)
    emit('CHECK',{**want,'status':'COMPLETE_INDEPENDENT_STORED64_BASELINE_EXCLUSION_NOT_ALL_HISTORY_GATE',
                  'implementation_independence':'PRIMARY_ONLY_NOT_EXPERT','distinct_inputs':len(before['input_sha256']),
                  'original_plan_tag_counts':dict(original_tags)})
if __name__=='__main__':main()
