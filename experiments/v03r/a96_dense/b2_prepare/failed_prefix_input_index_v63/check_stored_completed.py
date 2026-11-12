"""Independent stored-only v47 failed-prefix checker, no candidate/RFL imports."""
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


def source_proof(c):
    n=0
    for name,pin in c['sources'].items():
        b=(ROOT/name).read_bytes();assert sha256(b).hexdigest()==pin['sha256']
        got=ast_functions(ast.parse(b))
        assert {k:got[k] for k in pin['qualified_function_AST_sha256']}==pin['qualified_function_AST_sha256']
        n+=len(pin['qualified_function_AST_sha256'])
    entry=(ROOT/c['scope']['source']).read_text(encoding='utf-8')
    assert "for arch in ('D_Q','D_patch')" in entry
    assert entry.index("emit('RAW_FACTUAL_BEFORE_TRUTH'")<entry.index("oracle=OracleCreditAdapter.evaluate")
    assert entry.index("oracle=OracleCreditAdapter.evaluate")<entry.index("resolve_credited_units(du,trace")
    assert "trace=learned_rollout(pre,kappa=k,tape=scene.tape,base_option=z,q_reference=reference)" in entry
    assert "QReferenceView({(K.State(*a[:5]),a[5],a[6]):row for a,row in q.items()},name='v31-stored-nominal-no-DP')" in entry
    return {'sources':c['sources'],'source_count':len(c['sources']),'qualified_function_AST_pins':n,
        'actual_parameter_fields':c['actual_parameter_fields'],'reasoning':c['source_reasoning'],'limits':c['scope_limits']}

def reference_rows(c):
    q={}
    for ln,tag,o,h in records(c['catalog']):
        if tag!='DECISION_CONTEXT':continue
        n=tuple(o['context']);assert n not in q
        row={a:hx for a,hx in o['q_row_hex']};assert len(row)==len(o['q_row_hex'])
        q[n]=row
    assert len(q)==13824
    ordered=sorted(q,key=lambda n:(n[2],n[3],n[4],n[0],n[1],n[5],n[6]))
    text='\n'.join(','.join(map(str,n))+'|'+','.join(str(a)+'='+hx for a,hx in sorted(q[n].items())) for n in ordered)
    assert sha256(text.encode()).hexdigest()==c['reference_sha256']
    return q

def summary(c,n,counts,scope_sha,registry,same_store):
    return {'planned_inputs':n,'scope_entry_captures':1,'prefix_native_records':1,'native_raw_steps':4,
        'scope_registry_sha256':scope_sha,'planned_compatibility_registry_sha256':registry,
        'status_counts':dict(counts),'scope_compatible_planned_inputs':0,'same_full_store_different_actual_input_indices':same_store,
        'pending_before':153792,'pending_after':153792,'original_failed_native1_and_missing_truth_retained':True,
        'all_history_closed':False,'native_calibration_executed':0,'native_launch_authorized':False,
        'scientific_PASS':False,'collection_authorized':False,'research_complete':False}


def independently_index_prefix(c,q):
    rows=list(records(c['scope']))
    assert len(rows)==11570 and rows[-1][1]=='RAW_FACTUAL_BEFORE_TRUTH'
    kinds=[t for ln,t,o,h in rows];assert kinds.count('RAW_FACTUAL_BEFORE_TRUTH')==1
    assert all(t not in kinds for t in ('ACTUAL_COMPLETE_RECORD','FULL_ORIGINAL_TRUTH_BEFORE_B1','INPUT_BINDING_AFTER','FINAL'))
    bln,bt,before,bh=rows[0];assert bt=='INPUT_BINDING_BEFORE'
    assert before['parent_HEAD']==c['scope']['original_parent'] and len(before['input_sha256'])==1065
    for path,expected in sorted(before['input_sha256'].items()):
        if path=='experiments/rebuild_status_current.json':
            actual=sha256(subprocess.check_output(['git','show',c['scope']['original_parent']+':'+path],cwd=ROOT)).hexdigest()
        else:actual=digest(ROOT/path)
        assert actual==expected,path
    for path,pin in c['sources'].items():assert before['input_sha256'][path]==pin['sha256']
    prediction=next(row for row in rows if row[1]=='PREDICTION_BEFORE_ANY_NATIVE' and row[2]['id']==0)
    ln,t,native,h=rows[-1];p=prediction[2]
    assert (native['id'],native['installation'],p['basis'],p['actual_degree'],p['full_units'])==(0,'D_Q',[0,0,0],'0,0',[])
    assert native['payload']==p['pre'] and native['payload']['trace'][0]['pre_state']==[0,2,0,0,0]
    state=stores(native['full_pre_store']);assert fingerprint(state)==native['fingerprint_pre']
    assert state=={'D':[],'P':[],'Q':[[[0,2,0,1,0,1,0,4],'0x1.cccccccccccccp-1']],'X':[[[0,2,0,1,0,4],3]]}
    trace=native['payload']['trace'];assert len(trace)==4
    for row in trace:
        context=row['pre_state']+[row['z'],row['m']];best=None;value=None
        for action,hx in sorted(q[tuple(context)].items()):
            effective=hx
            for address,override in state['Q']:
                if address==context+[action]:effective=override
            v=float.fromhex(effective)
            if value is None or v>value:best=action;value=v
        assert best==row['a_cmd'] and row['illegal'] is False
        u=best
        for address,override in state['X']:
            if address==row['pre_state']+[best]:u=override
        assert (row['u'],row['a_realized'])==(u,u)
    err=(PREP/c['scope']['folder']/'stderr.log').read_text(encoding='utf-8')
    assert all(text in err for text in ('OracleCreditAdapter.evaluate','Gamma* is never empty (A67)','line 196'))
    return {'scope':'ORIGINAL_V47_FAILED___MAIN___ONLY','original_native_child_exit':1,
        'original_capture':c['scope'],'original_binding_reference':{'line':bln,'row_sha256':bh,'input_bindings':1065,'missing_after_binding_not_invented':True},
        'original_prediction_reference':{'line':prediction[0],'row_sha256':prediction[3],'prediction_not_native_truth':True},
        'raw_reference':{'line':ln,'row_sha256':h},'original_raw_record':native,'full_four_store_entries':state,
        'actual_requested_input':c['actual_requested_input'],'native_raw_steps':len(trace),
        'original_native_truth_emitted':False,'original_accepted_record_emitted':False,'original_B1_arms':0,
        'native_kernel_and_provider_source_pins':c['sources'],'all_other_scope_pending':True}

def check_difference(state,requested,scope,c,w):
    actual=scope['full_four_store_entries']
    full_same=all(len(state[ch])==len(actual[ch]) and
        all(wire(x)==wire(y) for x,y in zip(state[ch],actual[ch])) for ch in ('D','P','Q','X'))
    parameter_same=all(wire(requested[k])==wire(scope['actual_requested_input'][k]) for k in c['actual_parameter_fields'])
    assert not (full_same and parameter_same)
    if w['kind']=='ACTUAL_PARAMETER_DIFFERENCE':
        assert full_same and w['field'] in c['actual_parameter_fields']
        field=w['field'];assert wire(requested[field])!=wire(scope['actual_requested_input'][field])
        assert w=={'kind':'ACTUAL_PARAMETER_DIFFERENCE','field':field,'planned_value':requested[field],'actual_value':scope['actual_requested_input'][field]}
    else:
        assert w['kind']=='FULL_STORE_ENTRY_DIFFERENCE' and not full_same
        ch=w['store'];a=w['address'];left=[v for address,v in state[ch] if wire(address)==wire(a)]
        right=[v for address,v in actual[ch] if wire(address)==wire(a)]
        assert len(left)<=1 and len(right)<=1 and wire(left)!=wire(right)
        assert w['planned_entry_present']==bool(left) and w['actual_entry_present']==bool(right)
        assert w['planned_value']==(left[0] if left else None) and w['actual_value']==(right[0] if right else None)
    return full_same


def combined_records(c):
    repair=read(HERE/'repair_contract.json')
    original=records({'folder':HERE.relative_to(PREP).as_posix()+'/evidence','exit':1,'format':'compact'})
    for row in original:yield row
    completion=records({'folder':HERE.relative_to(PREP).as_posix()+'/evidence_completed','exit':0,'format':'compact'})
    _,tag,before,_=next(completion);assert tag=='COMPLETION_INPUT_BINDING_BEFORE' and before['distinct_inputs']==2627
    _,tag,reuse,_=next(completion);assert tag=='PRESERVED_PREFIX_RECEIPT'
    assert reuse['original_failure']==repair['original_failure'] and reuse['complete_rows_reused_without_reclassification']==276426
    assert reuse['prefix_registry_sha256']==repair['original_prefix_registry_sha256'] and reuse['appended_rows']==2732
    assert reuse['original_guard_row_computed_but_unprinted_reconstructed_once'] is True
    for row in completion:
        ln,tag,obj,h=row
        if tag=='COMPLETION_INPUT_BINDING_AFTER':
            assert obj==before
            for path,expected in obj['input_sha256'].items():assert digest(ROOT/path)==expected,path
            yield ln,'INPUT_BINDING_AFTER',obj,h
        else:yield row

def entry_main():
    c=read(HERE/'contract.json');before=binding(c,True);proof=source_proof(c)
    scope=independently_index_prefix(c,reference_rows(c))
    candidate=combined_records(c)
    _,tag,b0,_=next(candidate);assert tag=='INPUT_BINDING_BEFORE' and b0['distinct_inputs']==2619
    _,tag,v,_=next(candidate);assert tag=='SOURCE_CALL_CONTRACT' and v==proof
    _,tag,v,_=next(candidate);assert tag=='HISTORICAL_FAILED_PREFIX_INPUT' and wire(v)==wire(scope)
    registry=sha256();counts=Counter();n=0;same_store=[]
    for ln,tag,o,h in records(c['plan']):
        if tag!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        _,ctag,row,_=next(candidate);assert ctag=='PLANNED_FAILED_PREFIX_COMPATIBILITY'
        assert o['index']==n and row['planned_index']==n and o['complete_descriptor_alias_count']==1
        assert row['original_v55_capture_line']==ln and row['original_v55_row_sha256']==h
        assert wire(row['original_complete_plan_record'])==wire(o)
        state=stores(o['full_four_store_entries'])
        assert sha256(wire(state)).hexdigest()==o['full_store_sha256'] and fingerprint(state)==o['original_fingerprint']
        assert o['complete_requested_input']['nominal_Q_reference_sha256']==c['reference_sha256']
        if check_difference(state,o['complete_requested_input'],scope,c,row['concrete_input_difference']):same_store.append(n)
        status='EXACT_OLD_v46_v47_REFERENCE_PRESERVED' if o['exact_old_native_v46_v47_reference'] is not None else 'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX'
        assert row['status']==status and row['failed_prefix_compatible'] is False
        assert row['all_other_history_audit_pending'] is True and row['native_execution_authorized'] is False
        assert set(row)=={'planned_index','original_v55_capture_line','original_v55_row_sha256','original_complete_plan_record','failed_prefix_compatible','concrete_input_difference','status','all_other_history_audit_pending','native_execution_authorized'}
        registry.update(wire(row));counts[status]+=1;n+=1
    _,tag,b1,_=next(candidate);assert tag=='INPUT_BINDING_AFTER' and b1['distinct_inputs']==2627
    for name,h in b0['input_sha256'].items():assert digest(ROOT/name)==h,name
    _,tag,final,_=next(candidate);assert tag=='FINAL'
    assert next(candidate,None) is None and n==279158 and len(same_store)==4
    assert counts=={'EXACT_OLD_v46_v47_REFERENCE_PRESERVED':125366,'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX':153792}
    expected=summary(c,n,counts,sha256(wire(scope)).hexdigest(),registry.hexdigest(),same_store);assert final==expected
    assert binding(c,True)==before
    emit('CHECK',{**expected,'runtime_inputs':before['distinct_inputs'],'candidate_capture_bytes':(HERE/'evidence/stdout.log').stat().st_size+(HERE/'evidence_completed/stdout.log').stat().st_size,
        'independence':'Same main agent independent EOF prefix index, explicit ascending read argmax, ordered-entry equality and keyed EOF join; mechanical byte/JSON/Git/source-pin/fingerprint/reference serialization helpers copied; no RFL/candidate/old checker/solver execution; not expert/scientific approval'})
if __name__=='__main__':entry_main()

