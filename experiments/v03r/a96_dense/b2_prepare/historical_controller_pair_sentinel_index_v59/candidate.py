"""Complete original controller pair and four-actual/k8-sentinel stored index; no RFL execution."""
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
def emit(t,o):
    global OUTPUT_BYTES
    raw=t.encode()+b'='+wire(o);OUTPUT_BYTES+=len(raw)
    assert OUTPUT_BYTES<=750000000,'stored output engineering guard'
    sys.stdout.buffer.write(raw);sys.stdout.buffer.flush()

def binding(c):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    assert head==c['parent_commit']
    out={}
    rows=subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0')
    count=0
    for row in rows:
        if not row: continue
        meta,rawpath=row.split(b'\t',1);path=rawpath.decode();p=ROOT/path
        h1=sha1(b'blob '+str(p.stat().st_size).encode()+b'\0');h2=sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(8388608),b''):h1.update(b);h2.update(b)
        assert h1.hexdigest()==meta.split()[2].decode(),path
        out[path]=h2.hexdigest();count+=1
    assert count==c['parent_tree_paths']
    for n in ('contract.json','candidate.py','execute.py','check_stored.py'):
        out[(HERE/n).relative_to(ROOT).as_posix()]=digest(HERE/n)
    return {'parent_HEAD':head,'parent_tree_paths':count,'distinct_inputs':len(out),'input_sha256':out}

def records(info):
    p=PREP/info['folder'];cl=read(p/'claim.json');ex=read(p/'exit.json')
    assert ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items())
    for n,h in cl['inputs'].items():assert digest(p.parent/n)==h,(p,n)
    for n,d in ex['files'].items():
        assert {'bytes':(p/n).stat().st_size,'sha256':digest(p/n)}==d
    assert ex['files']['stdout.log']['sha256']==info['sha256']
    assert (p/'stderr.log').read_bytes()==b''
    with (p/'stdout.log').open('rb') as f:
        for number,line in enumerate(f,1):
            assert line.endswith(b'\n')
            tag,v=line.rstrip(b'\r\n').split(b'=',1);o=json.loads(v)
            assert wire(o).rstrip(b'\n')==v,(p,number)
            yield number,tag.decode(),o,sha256(line).hexdigest()

def source_proof(c):
    for p,pin in c['sources'].items():
        raw=(ROOT/p).read_bytes();assert sha256(raw).hexdigest()==pin['sha256']
        found={}
        for n in ast.walk(ast.parse(raw)):
            if isinstance(n,ast.FunctionDef) and n.name in pin['functions']:
                found.setdefault(n.name,[]).append(sha256(ast.dump(n,include_attributes=False).encode()).hexdigest())
        assert found==pin['functions'],p
    tree=ast.parse((ROOT/'src/rfl_rebuild/b2/environment.py').read_bytes())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='learned_rollout')
    assert [a.arg for a in fn.args.kwonlyargs]==['kappa','tape','base_option','q_reference']
    assert [a.arg for a in fn.args.args]==['state']
    for path,names in [
        ('src/rfl_rebuild/learner/reference.py',{'row','canonical'}),
        ('src/rfl_rebuild/learner/store.py',{'decision_provider','q_decision_provider','controller_mapping','process_commit_provider'}),
        ('src/rfl_rebuild/env/kernel.py',{'rollout','continue_rollout'})]:
        for n in ast.walk(ast.parse((ROOT/path).read_bytes())):
            if isinstance(n,ast.FunctionDef) and n.name in names:
                assert not any(isinstance(a,ast.Attribute) and a.attr in {'name','architecture','installation'} for a in ast.walk(n))
    return {'complete_sources':c['sources'],'installation_labels_preserved_not_runtime_arguments':True,
            'reference_display_names_preserved_common_full_rows':True,'all_history_closed':False}

def stores(o):
    assert set(o)=={'D','P','Q','X'}
    out={}
    for ch,rows in o.items():
        keys=[tuple(a) if isinstance(a,list) else a for a,v in rows]
        assert len(keys)==len(set(keys)),('duplicate store address',ch)
        out[ch]=sorted(rows,key=lambda x:tuple(x[0]) if isinstance(x[0],list) else x[0])
    assert not(out['D'] and out['Q'])
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

def invocation(scene,c):
    k,p,e,r,z=scene
    assert e==r==0
    return {'scene':scene,'initial_state':[0,2,0,k,p],'initial_committed_option':z,
        'initial_automaton_memory':0,'P_identity':True,'learner_policy':'ORIGINAL_GREEDY_STRICT_ARGMAX_MIN_ACTION',
        'mask_do':None,'training':False,'reward_mode':'A','nominal_Q_reference_sha256':c['reference_sha256']}

def fullkey(args,store): return wire([args,store])
def path_payload(payload,dindex,qrows,state,scene):
    rows=payload['trace'];assert rows
    assert rows[0]['pre_state']==[0,2,0,scene[0],scene[1]]
    assert [rows[0]['z'],rows[0]['m']]==[scene[4],0]
    dmap={tuple(a):v for a,v in state['D']};qmap={tuple(a):v for a,v in state['Q']}
    xmap={tuple(a):v for a,v in state['X']};out=[]
    previous=None
    for row in rows:
        assert not row['illegal'] and row['a_realized']==row['u']
        address=tuple(row['pre_state']+[row['z'],row['m']])
        if previous is not None:assert row['pre_state']+[row['z'],row['m']]==previous
        q=qrows[address];best=None;value=None
        for a,v in q:
            now=float.fromhex(qmap.get(address+(a,),v))
            if value is None or now>value:best,value=a,now
        command=dmap.get(address,best)
        assert row['a_cmd']==command and command in dict(q) and row['u'] in dict(q)
        assert row['u']==xmap.get(tuple(row['pre_state']+[command]),command)
        assert row['post_state'][2]==row['pre_state'][2]+1
        assert row['pre_state'][3:]==row['post_state'][3:]==scene[:2]
        assert row['z']==row['post_control'][0]==scene[4]
        previous=row['post_state']+row['post_control']
        out.append([dindex[address],row['a_cmd'],row['u'],row['reward_hex'],previous,row['terminal'],row['outcome']])
    assert rows[-1]['outcome']==payload['outcome'] and rows[-1]['terminal']
    return {'complete_path':out,'return_hex':payload['return_hex'],'outcome':payload['outcome']}


def main():
    c=read(HERE/'contract.json');before=binding(c);emit('INPUT_BINDING_BEFORE',before)
    emit('SOURCE_INPUT_CONTRACT',source_proof(c))
    qrows={};dindex={};canon=[]
    for ln,t,o,h in records(c['catalog']):
        if t=='DECISION_CONTEXT':
            a=tuple(o['context']);assert a not in qrows
            dindex[a]=len(dindex);qrows[a]=o['q_row_hex']
            canon.append(','.join(map(str,a))+'|'+','.join(str(x)+'='+v for x,v in o['q_row_hex']))
    assert len(qrows)==13824 and sha256('\n'.join(canon).encode()).hexdigest()==c['reference_sha256']
    emit('COMPLETE_REFERENCE_BINDING',{'catalog':c['catalog'],'complete_rows':len(qrows),'reference_sha256':c['reference_sha256']})
    index={};native=[];registry=sha256();counts=Counter();outcomes=Counter();rawcount=0
    for spec in c['scope']:
        pred={};pending=None;truth=None;start=None;source_n=0;source_raw=0;accepted=0
        for ln,t,o,h in records(spec):
            if t=='INPUT_BINDING_BEFORE':
                assert start is None;start=o
                own=(PREP/spec['source']).relative_to(ROOT).as_posix()
                for path,pin in c['sources'].items():
                    if path.startswith('src/') or path.endswith('factual_event_candidate.py') or path==own:
                        assert o['input_sha256'][path]==pin['sha256'],path
                assert o['input_sha256'][(PREP/c['catalog']['folder']/'stdout.log').relative_to(ROOT).as_posix()]==c['catalog']['sha256']
            elif t=='INPUT_BINDING_AFTER':assert start==o
            elif t=='PREDICTION_BEFORE_ANY_NATIVE':
                assert o['id'] not in pred
                k,p,z=o['basis'];pred[o['id']]=([k,p,0,0,z],ln,h)
            elif t=='RAW_FACTUAL_BEFORE_TRUTH':
                assert pending is None;pending=(ln,o,h);truth=None
            elif t=='FULL_ORIGINAL_TRUTH_BEFORE_B1':
                assert pending is not None and o['id']==pending[1]['id'] and o.get('architecture')==pending[1].get('architecture')
                assert truth is None;truth=(ln,o,h)
            elif t=='ACTUAL_COMPLETE_RECORD':
                assert pending is not None and truth is not None and pending[0]<truth[0]<ln
                assert pending[1]['id']==o['id'] and pending[1].get('architecture')==o.get('architecture')
                assert pending[1]['payload']==o['payload'] and pending[1]['full_pre_store']==o['full_pre_store']
                assert truth[1]['truth']==o['truth'] and truth[1]['units']==o['full_units']
                assert pending[1]['fingerprint_pre']==o['fingerprint_pre']==o['source_fingerprint_after']
                scene,basis_ln,basis_h=pred[o['id']]
                args=invocation(scene,c);pre=stores(o['full_pre_store'])
                assert not pre['D'] and not pre['P'] and not pre['Q']
                assert fingerprint(pre)==o['fingerprint_pre']
                arch=o.get('architecture');assert arch is None
                arms=o['same_tier_arms']
                assert [a['role'] for a in arms]==(['reference','treatment'] if o['reflection_applicable'] else [])
                members=[('factual',-1,o['full_pre_store'],o['payload'],o['fingerprint_pre'])]
                for slot,a in enumerate(arms):
                    assert a['ledger']['fingerprint_pre']==o['fingerprint_pre']
                    post=stores(a['full_post_store']);assert fingerprint(post)==a['ledger']['fingerprint_post']
                    if a['role']=='reference':assert post==pre and a['payload']==o['payload'] and not a['transactions']
                    members.append((a['role'],slot,a['full_post_store'],a['payload'],a['ledger']['fingerprint_post']))
                for role,slot,original_store,payload,fp in members:
                    state=stores(original_store);assert not state['D'] and not state['P'] and not state['Q']
                    assert fingerprint(state)==fp
                    observed=path_payload(payload,dindex,qrows,state,scene)
                    item={'index':len(native),'capture':spec['folder'],'line':ln,'complete_record_row_sha256':h,
                        'actual_source':spec['source'],'original_record_id':o['id'],'original_architecture':arch,
                        'role':role,'original_arm_slot':slot,'complete_original_store_entries':original_store,
                        'full_four_store_entries':state,'complete_actual_invocation':args,
                        'complete_raw_payload_sha256':sha256(wire(payload)).hexdigest(),
                        'stored_native_observation':observed,'original_fingerprint':fp,
                        'raw_factual_before_truth_line':pending[0],'raw_factual_before_truth_row_sha256':pending[2],
                        'complete_truth_row_sha256':truth[2],'basis_declaration_line':basis_ln,'basis_declaration_row_sha256':basis_h,
                        'full_actual_store_was_originally_captured':True,'new_native_execution':False}
                    k=fullkey(args,state);index.setdefault(k,[]).append(item['index'])
                    native.append(item);registry.update(wire(item));emit('HISTORICAL_COMPLETE_NATIVE_INPUT',item)
                    counts[spec['folder']+':'+role]+=1;outcomes[payload['outcome']]+=1
                    source_n+=1;source_raw+=len(payload['trace'])
                accepted+=1;pending=None;truth=None
        assert pending is None and source_n==spec['native_records'] and source_raw==spec['raw_rows']
        rawcount+=source_raw
    assert len(native)==c['expected']['scope_native'] and rawcount==c['expected']['scope_raw_rows']
    assert len(native)<=c['guards']['max_native_records']
    emit('HISTORICAL_SCOPE_INDEX_COMPLETE',{'records':len(native),'unique_complete_inputs':len(index),
        'raw_rows':rawcount,'counts':dict(counts),'outcomes':dict(outcomes),'scope_registry_sha256':registry.hexdigest(),
        'all_other_history_pending':True,'native_rerun':False})
    status_counts=Counter();hits=set();labels=Counter();planreg=sha256();n=0
    for ln,t,o,h in records(c['plan']):
        if t!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert o['index']==n;n+=1
        requested=o['complete_requested_input'];args=invocation(requested['scene'],c)
        assert requested['root']==[requested['scene'][0],requested['scene'][1],requested['scene'][4]]
        assert requested['installation'] in ('D_Q','D_patch') and requested['reference_name']=='v31-stored-nominal-no-DP'
        for k,v in args.items():
            if k!='reward_mode':assert requested[k]==v
        state=stores(o['full_four_store_entries'])
        assert fingerprint(state)==o['original_fingerprint'] and sha256(wire(state)).hexdigest()==o['full_store_sha256']
        matched=index.get(fullkey(args,state),[])
        for j in matched:
            actual=native[j];assert actual['full_four_store_entries']==state and actual['complete_actual_invocation']==args
            for k,v in o['stored_source_expectation_not_measurement'].items():
                if v is not None:assert actual['stored_native_observation'][k]==v
            hits.add(j);labels[requested['installation']]+=1
        prior=o['exact_old_native_v46_v47_reference']
        status='EXACT_OLD_v46_v47_REFERENCE_PRESERVED' if prior is not None else ('EXACT_COMPLETE_OLD_CONTROLLER_PAIR_SENTINEL_NATIVE' if matched else 'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX')
        row={'index':o['index'],'v55_capture':c['plan']['folder'],'v55_line':ln,'complete_v55_row_sha256':h,
            'original_requested_input':requested,'original_descriptor_reference':o['first_descriptor_reference'],
            'original_v46_v47_reference':prior,'scoped_exact_native_record_indices':matched,'status':status,
            'all_other_history_audit_pending':True,'native_execution_authorized':False}
        status_counts[status]+=1;planreg.update(wire(row));emit('PRESERVED_PLANNED_INPUT_HISTORY_STATUS',row)
    assert n==c['expected']['planned'] and n<=c['guards']['max_planned_inputs']
    assert status_counts['EXACT_OLD_v46_v47_REFERENCE_PRESERVED']==c['expected']['old_v46_v47']
    after=binding(c);assert after==before;emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'planned_inputs':n,'status_counts':dict(status_counts),'scope_native_records':len(native),
        'scope_unique_complete_inputs':len(index),'scope_raw_rows':rawcount,'scope_counts':dict(counts),
        'scope_outcomes':dict(outcomes),'matched_scope_native_records':len(hits),'matched_planned_installation_labels':dict(labels),
        'scope_registry_sha256':registry.hexdigest(),'plan_status_registry_sha256':planreg.hexdigest(),
        'pending_before':c['expected']['pending_before'],'pending_after':status_counts['PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX'],
        'all_history_closed':False,'native_calibration_executed':0,'native_launch_authorized':False,
        'scientific_PASS':False,'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()

