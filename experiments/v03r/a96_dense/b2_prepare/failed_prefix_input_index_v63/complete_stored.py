"""Storage-only missing-row completion; original native1 preserved, never rerun."""
import ast
from collections import Counter
from hashlib import sha1, sha256
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
PREP=HERE.parent
def read(p): return json.loads(p.read_bytes())
def wire(o): return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def digest(p):
    h=sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''): h.update(b)
    return h.hexdigest()
OUTPUT_BYTES=0
def emit(tag,obj):
    global OUTPUT_BYTES
    b=tag.encode()+b'='+wire(obj);OUTPUT_BYTES+=len(b)
    assert OUTPUT_BYTES<=750000000,'output engineering guard'
    sys.stdout.buffer.write(b);sys.stdout.buffer.flush()
def binding(c,checking=False):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    assert head==c['parent_commit']
    out={}
    for row in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0'):
        if not row:continue
        meta,name=row.split(b'\t',1);name=name.decode();p=ROOT/name
        h1=sha1(b'blob '+str(p.stat().st_size).encode()+b'\0');h2=sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(8388608),b''):h1.update(b);h2.update(b)
        assert h1.hexdigest()==meta.split()[2].decode(),name
        out[name]=h2.hexdigest()
    assert len(out)==c['parent_tree_paths']
    names=['contract.json','candidate.py','execute.py','check_stored.py','repair_contract.json','complete_stored.py','execute_completion.py','check_stored_completed.py']
    names+=['evidence/'+n for n in ('claim.json','exit.json','stdout.log','stderr.log')]
    if checking:names+=['evidence_completed/'+n for n in ('claim.json','exit.json','stdout.log','stderr.log')]
    for n in names:out[(HERE/n).relative_to(ROOT).as_posix()]=digest(HERE/n)
    return {'parent_HEAD':head,'parent_tree_paths':c['parent_tree_paths'],'distinct_inputs':len(out),'input_sha256':out}

def records(spec):
    p=PREP/spec['folder'];cl=read(p/'claim.json');ex=read(p/'exit.json')
    assert ex['native_child_exit_code']==spec['exit'] and all(ex[k]==v for k,v in cl.items())
    for n,h in cl['inputs'].items():assert digest(p.parent/n)==h,(p,n)
    for n,info in ex['files'].items():
        assert {'bytes':(p/n).stat().st_size,'sha256':digest(p/n)}==info
    if 'files' in spec:assert ex['files']==spec['files']
    if 'sha256' in spec:assert ex['files']['stdout.log']['sha256']==spec['sha256']
    counts=Counter()
    for ln,line in enumerate((p/'stdout.log').open('rb'),1):
        assert line.endswith(b'\n')
        t,v=line.rstrip(b'\r\n').split(b'=',1);tag=t.decode();counts[tag]+=1
        if tag=='STAGE':
            assert v.decode() in spec['stage_values'];obj=v.decode()
        else:
            obj=json.loads(v);kw={'separators':(',',':')} if spec['format']=='compact' else {}
            assert json.dumps(obj,sort_keys=True,ensure_ascii=True,allow_nan=False,**kw).encode()==v,(p,ln)
        yield ln,tag,obj,sha256(line).hexdigest()
    if 'tags' in spec:assert dict(counts)==spec['tags']

def ast_functions(tree,prefix=''):
    result={}
    for node in tree.body:
        if isinstance(node,ast.FunctionDef):
            result[prefix+node.name]=sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()
        elif isinstance(node,ast.ClassDef):result.update(ast_functions(node,prefix+node.name+'.'))
    return result

def stores(o):
    assert set(o)=={'D','P','Q','X'}
    out={}
    for ch,rows in o.items():
        keys=[tuple(a) if isinstance(a,list) else a for a,v in rows]
        assert len(keys)==len(set(keys)),('duplicate address',ch)
        out[ch]=sorted(rows,key=lambda x:tuple(x[0]) if isinstance(x[0],list) else x[0])
    return out
def fingerprint(o):
    parts=[]
    for ch in ('D','P','X','Q'):
        rows=[]
        for a,v in o[ch]:
            if ch=='P':s='P:'+str(a)+','+str(v)
            elif ch=='Q':s='Q:'+','.join(map(str,a))+'|'+v
            else:s=ch+':'+','.join(map(str,a+[v]))
            rows.append(s)
        parts.append('\n'.join(sorted(rows)).encode())
    return sha256(b'\0'.join(parts)).hexdigest()

def mismatch(state,scope,c,requested):
    actual=scope['full_four_store_entries']
    for ch in ('D','P','Q','X'):
        left={tuple(a) if isinstance(a,list) else a:v for a,v in state[ch]}
        right={tuple(a) if isinstance(a,list) else a:v for a,v in actual[ch]}
        for a in sorted(set(left)|set(right)):
            if a not in left or a not in right or wire(left[a])!=wire(right[a]):
                return {'kind':'FULL_STORE_ENTRY_DIFFERENCE','store':ch,'address':list(a) if isinstance(a,tuple) else a,
                    'planned_entry_present':a in left,'actual_entry_present':a in right,
                    'planned_value':left.get(a),'actual_value':right.get(a)}
    for field in c['actual_parameter_fields']:
        if wire(requested[field])!=wire(scope['actual_requested_input'][field]):
            return {'kind':'ACTUAL_PARAMETER_DIFFERENCE','field':field,'planned_value':requested[field],
                'actual_value':scope['actual_requested_input'][field]}
    return None

def plan_row(o,ln,h,w):
    status='EXACT_OLD_v46_v47_REFERENCE_PRESERVED' if o['exact_old_native_v46_v47_reference'] is not None else 'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX'
    return {'planned_index':o['index'],'original_v55_capture_line':ln,'original_v55_row_sha256':h,
        'original_complete_plan_record':o,'failed_prefix_compatible':w is None,'concrete_input_difference':w,
        'status':status,'all_other_history_audit_pending':True,'native_execution_authorized':False}

def summary(c,n,counts,scope_sha,registry,same_store):
    return {'planned_inputs':n,'scope_entry_captures':1,'prefix_native_records':1,'native_raw_steps':4,
        'scope_registry_sha256':scope_sha,'planned_compatibility_registry_sha256':registry,
        'status_counts':dict(counts),'scope_compatible_planned_inputs':0,'same_full_store_different_actual_input_indices':same_store,
        'pending_before':153792,'pending_after':153792,'original_failed_native1_and_missing_truth_retained':True,
        'all_history_closed':False,'native_calibration_executed':0,'native_launch_authorized':False,
        'scientific_PASS':False,'collection_authorized':False,'research_complete':False}


def main():
    c=read(HERE/'contract.json');repair=read(HERE/'repair_contract.json');before=binding(c);emit('COMPLETION_INPUT_BINDING_BEFORE',before)
    original=records({'folder':HERE.relative_to(PREP).as_posix()+'/evidence','exit':1,'format':'compact'})
    _,tag,b0,_=next(original);assert tag=='INPUT_BINDING_BEFORE' and b0['distinct_inputs']==2619
    _,tag,proof,_=next(original);assert tag=='SOURCE_CALL_CONTRACT' and proof['sources']==c['sources']
    _,tag,scope,_=next(original);assert tag=='HISTORICAL_FAILED_PREFIX_INPUT'
    assert sha256(wire(scope)).hexdigest()==repair['original_scope_registry_sha256']
    for path,h in b0['input_sha256'].items():assert digest(ROOT/path)==h,path
    emit('PRESERVED_PREFIX_RECEIPT',{'original_failure':repair['original_failure'],'complete_rows_reused_without_reclassification':276426,
        'prefix_registry_sha256':repair['original_prefix_registry_sha256'],'original_guard_row_computed_but_unprinted_reconstructed_once':True,
        'appended_rows':2732,'all_original_four_sources_and_failure_capture_unchanged':True})
    registry=sha256();prefix=sha256();counts=Counter();n=0;same_store=[];appended=0
    for ln,tag,o,h in records(c['plan']):
        if tag!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert o['index']==n
        if n<repair['original_complete_prefix_planned_rows']:
            _,t,row,_=next(original);assert t=='PLANNED_FAILED_PREFIX_COMPATIBILITY' and row['planned_index']==n
            assert row['original_v55_capture_line']==ln and row['original_v55_row_sha256']==h
            assert wire(row['original_complete_plan_record'])==wire(o)
            prefix.update(wire(row))
            if row['concrete_input_difference']['kind']=='ACTUAL_PARAMETER_DIFFERENCE':same_store.append(n)
        else:
            state=stores(o['full_four_store_entries'])
            assert sha256(wire(state)).hexdigest()==o['full_store_sha256'] and fingerprint(state)==o['original_fingerprint']
            w=mismatch(state,scope,c,o['complete_requested_input']);assert w is not None
            if wire(state)==wire(scope['full_four_store_entries']):same_store.append(n)
            row=plan_row(o,ln,h,w);emit('PLANNED_FAILED_PREFIX_COMPATIBILITY',row);appended+=1
        registry.update(wire(row));counts[row['status']]+=1;n+=1
    assert next(original,None) is None and prefix.hexdigest()==repair['original_prefix_registry_sha256']
    assert n==279158 and appended==2732 and same_store==[114116,114118,114120,114122]
    assert counts=={'EXACT_OLD_v46_v47_REFERENCE_PRESERVED':125366,'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX':153792}
    assert binding(c)==before;emit('COMPLETION_INPUT_BINDING_AFTER',before)
    emit('FINAL',summary(c,n,counts,sha256(wire(scope)).hexdigest(),registry.hexdigest(),same_store))
if __name__=='__main__':main()

