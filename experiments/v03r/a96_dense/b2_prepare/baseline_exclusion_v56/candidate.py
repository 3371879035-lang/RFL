"""Keyless source-invariant exclusion for old baseline shards, not a native gate."""
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
    c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    source_pins(c);emit('BOUND_SOURCE_INVARIANT',{'source_pins':c['sources'],'proof':c['proof'],'witness':c['witness_Q_address']})
    witness=None;catalog_counts=Counter()
    for line,tag,o in captured(ROOT/c['catalog_capture'],c['catalog_stdout_sha256']):
        catalog_counts[tag]+=1
        if tag=='DECISION_CONTEXT' and o['context']==c['witness_catalog_context']:witness=o
        if tag=='CATALOG_SUMMARY':assert o['nominal_Q_reference_sha256']=='d9078b5b5b823df56f998e8c28eb6a3e388bd3ae216f41a21acdb5202d2ec05a'
    assert witness is not None and catalog_counts['DECISION_CONTEXT']==13824
    row={a:float.fromhex(v) for a,v in witness['q_row_hex']}
    assert max(row.values())>min(row.values()) and min(a for a,v in row.items() if v==min(row.values()))==c['witness_Q_address'][-1]
    x,y,t,*_=witness['context'];assert t==1 and abs(x)+abs(y-2)>t
    emit('ORIGINAL_REFERENCE_WITNESS',{'complete_catalog_row':witness,'initial_override_nonidentity_by_strict_gap':True,'never_visited_by_any_baseline_episode':True})
    shards=list(baseline_rows(c));assert len(shards)==64<=c['guards']['shards']
    for o in shards:emit('UNCHANGED_BASELINE_SHARD_SOURCE_EXCLUSION',o)
    reg=sha256();reg.update(b'[');counts=Counter();tags=Counter();last=None
    for line,tag,o in captured(ROOT/c['plan_capture'],c['plan_stdout_sha256']):
        tags[tag]+=1;last=tag
        if tag!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert o['index']==counts['keys'] and set(o['full_four_store_entries'])=={'D','P','Q','X'}
        store=o['full_four_store_entries']
        for entries in store.values():assert len({tuple(a) if isinstance(a,list) else a for a,v in entries})==len(entries)
        present=any(a==c['witness_Q_address'] for a,v in store['Q'])
        assert not present,'fixed invariant cannot exclude this key; retain pending, no witness switching'
        row={'key_index':o['index'],'complete_v55_key_row_sha256':sha256(canonical(o)).hexdigest(),
             'witness_Q_address_absent':True,'baseline_fullstore_inequality_proved':True,
             'pending_ALL_other_history_audit':o['exact_old_native_v46_v47_reference'] is None}
        if counts['keys']:reg.update(b',')
        reg.update(canonical(row).rstrip(b'\n'));emit('EVERY_PLANNED_KEY_BASELINE_EXCLUSION',row)
        counts['keys']+=1;counts['pending_ALL_other_history_keys']+=int(row['pending_ALL_other_history_audit'])
    reg.update(b']\n')
    assert last=='FINAL' and tags['UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY']==279158==counts['keys']<=c['guards']['keys']
    assert counts['pending_ALL_other_history_keys']==153792
    after=bind(c);assert before==after;emit('INPUT_BINDING_AFTER',after)
    assert (HERE/'evidence/stdout.log').stat().st_size<=c['guards']['bytes']
    emit('FINAL',{'status':'COMPLETE64_BASELINE_SOURCE_INVARIANT_DISJOINTNESS_NOT_ALL_HISTORY_GATE','counts':dict(counts),
         'baseline_shards':64,'baseline_compressed_bytes':sum(o['compressed_bytes'] for o in shards),'old_baseline_records':36928,
         'exclusion_registry_sha256':reg.hexdigest(),'all64_baseline_source_contract_exclusion_closed':True,
         'ALL279158_original_keys_retained':True,'all_other_history_exclusion_complete':False,'historical_native_exclusion_complete':False,
         'native_launch_gate':False,'native_calibration_executed':False,'new_RFL_kernel_steps':0,'new_learner_rollouts':0,
         'keys_allocated':0,'random_draws':0,'future_training':0,'collector_executed':False,'collection_authorized':False,
         'scientific_rules_adopted':False,'scientific_PASS':False,'research_complete':False})
if __name__=='__main__':main()
