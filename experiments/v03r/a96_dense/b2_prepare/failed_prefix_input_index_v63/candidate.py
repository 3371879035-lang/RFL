"""Stored v47 original failed-prefix exact input audit. No RFL execution."""
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
    names=['contract.json','candidate.py','execute.py','check_stored.py']
    if checking:names+=['evidence/'+n for n in ('claim.json','exit.json','stdout.log','stderr.log')]
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

def prefix_scope(c,q):
    before=None;pred=None;raws=[];last_tag=None;count=0
    for ln,tag,o,h in records(c['scope']):
        count+=1;last_tag=tag
        if tag=='INPUT_BINDING_BEFORE':before=(ln,o,h)
        if tag=='PREDICTION_BEFORE_ANY_NATIVE' and o['id']==0:pred=(ln,o,h)
        if tag=='RAW_FACTUAL_BEFORE_TRUTH':raws.append((ln,o,h))
    assert count==c['scope']['lines'] and last_tag=='RAW_FACTUAL_BEFORE_TRUTH' and len(raws)==1
    assert before[1]['parent_HEAD']==c['scope']['original_parent'] and len(before[1]['input_sha256'])==1065
    for name,h in before[1]['input_sha256'].items():
        b=subprocess.check_output(['git','show',before[1]['parent_HEAD']+':'+name],cwd=ROOT) if name=='experiments/rebuild_status_current.json' else None
        assert (sha256(b).hexdigest() if b is not None else digest(ROOT/name))==h,name
    for name,pin in c['sources'].items():assert before[1]['input_sha256'][name]==pin['sha256']
    ln,o,h=raws[0];p=pred[1]
    assert ln==count and o['id']==0 and o['installation']=='D_Q' and p['basis']==[0,0,0]
    assert o['payload']==p['pre'] and p['actual_degree']=='0,0' and p['full_units']==[]
    state=stores(o['full_pre_store']);assert fingerprint(state)==o['fingerprint_pre']
    assert state['D']==[] and state['P']==[]
    assert state['Q']==[[[0,2,0,1,0,1,0,4],'0x1.cccccccccccccp-1']]
    assert state['X']==[[[0,2,0,1,0,4],3]]
    trace=o['payload']['trace'];assert len(trace)==4 and trace[0]['pre_state']==[0,2,0,0,0]
    for row in trace:
        n=tuple(row['pre_state']+[row['z'],row['m']])
        effective={a:float.fromhex(hx) for a,hx in q[n].items()}
        for a,hx in state['Q']:
            if tuple(a[:-1])==n:effective[a[-1]]=float.fromhex(hx)
        cmd=min(effective,key=lambda a:(-effective[a],a))
        assert row['a_cmd']==cmd and row['illegal'] is False
        mapping={tuple(a):v for a,v in state['X']}
        assert row['u']==mapping.get(n[:5]+(cmd,),cmd) and row['a_realized']==row['u']
    stderr=(PREP/c['scope']['folder']/'stderr.log').read_text(encoding='utf-8')
    assert 'OracleCreditAdapter.evaluate' in stderr and 'Gamma* is never empty (A67)' in stderr and 'line 196' in stderr
    assert c['actual_requested_input']['scene']==[0,0,0,0,0]
    return {'scope':'ORIGINAL_V47_FAILED___MAIN___ONLY','original_native_child_exit':1,
        'original_capture':c['scope'],'original_binding_reference':{'line':before[0],'row_sha256':before[2],'input_bindings':1065,'missing_after_binding_not_invented':True},
        'original_prediction_reference':{'line':pred[0],'row_sha256':pred[2],'prediction_not_native_truth':True},
        'raw_reference':{'line':ln,'row_sha256':h},'original_raw_record':o,'full_four_store_entries':state,
        'actual_requested_input':c['actual_requested_input'],'native_raw_steps':len(trace),
        'original_native_truth_emitted':False,'original_accepted_record_emitted':False,'original_B1_arms':0,
        'native_kernel_and_provider_source_pins':c['sources'],'all_other_scope_pending':True}

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
    c=read(HERE/'contract.json');before=binding(c);emit('INPUT_BINDING_BEFORE',before)
    emit('SOURCE_CALL_CONTRACT',source_proof(c));scope=prefix_scope(c,reference_rows(c));emit('HISTORICAL_FAILED_PREFIX_INPUT',scope)
    registry=sha256();counts=Counter();n=0;same_store=[]
    for ln,tag,o,h in records(c['plan']):
        if tag!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert o['index']==n and o['complete_descriptor_alias_count']==1
        state=stores(o['full_four_store_entries'])
        assert sha256(wire(state)).hexdigest()==o['full_store_sha256'] and fingerprint(state)==o['original_fingerprint']
        assert o['complete_requested_input']['nominal_Q_reference_sha256']==c['reference_sha256']
        w=mismatch(state,scope,c,o['complete_requested_input']);assert w is not None
        if wire(state)==wire(scope['full_four_store_entries']):same_store.append(n)
        row=plan_row(o,ln,h,w);registry.update(wire(row));counts[row['status']]+=1;emit('PLANNED_FAILED_PREFIX_COMPATIBILITY',row)
        n+=1;assert n<=c['guards']['max_planned']
    assert n==c['expected']['planned'] and len(same_store)==c['expected']['same_store_different_input']
    assert counts=={'EXACT_OLD_v46_v47_REFERENCE_PRESERVED':125366,'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX':153792}
    assert binding(c)==before;emit('INPUT_BINDING_AFTER',before)
    emit('FINAL',summary(c,n,counts,sha256(wire(scope)).hexdigest(),registry.hexdigest(),same_store))
if __name__=='__main__':main()

