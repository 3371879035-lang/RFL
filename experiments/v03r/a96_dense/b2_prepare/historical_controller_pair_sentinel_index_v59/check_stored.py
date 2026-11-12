"""Complete original controller pair and four-actual/k8-sentinel stored index; no RFL execution."""
import ast
from collections import Counter
from bisect import bisect_left,bisect_right
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
    c=read(HERE/'contract.json');before=binding(c)
    for n in ('claim.json','exit.json','stdout.log','stderr.log'):
        before['input_sha256'][(HERE/'evidence'/n).relative_to(ROOT).as_posix()]=digest(HERE/'evidence'/n)
    before['distinct_inputs']=len(before['input_sha256'])
    proof=source_proof(c);catalog=[]
    for _,t,o,_ in records(c['catalog']):
        if t=='DECISION_CONTEXT':catalog.append(o)
    ordered=sorted(catalog,key=lambda o:(o['context'][2],o['context'][3],o['context'][4],o['context'][0],o['context'][1],o['context'][5],o['context'][6]))
    assert ordered==catalog and len(catalog)==13824
    referent='\n'.join(','.join(map(str,o['context']))+'|'+','.join(str(a)+'='+v for a,v in sorted(o['q_row_hex'])) for o in catalog)
    assert sha256(referent.encode()).hexdigest()==c['reference_sha256']
    qrows={tuple(o['context']):o['q_row_hex'] for o in catalog}
    dindex={tuple(o['context']):i for i,o in enumerate(catalog)}
    original={};counts=Counter();outcomes=Counter();raw_count=0
    # EOF keyed join by complete original source id, independent of streaming raw state.
    for spec in c['scope']:
        source_rows=list(records(spec));pred={};raw={};truth={};complete=[]
        starts=[];ends=[]
        for ln,t,o,h in source_rows:
            if t=='INPUT_BINDING_BEFORE':starts.append(o)
            elif t=='INPUT_BINDING_AFTER':ends.append(o)
            elif t=='PREDICTION_BEFORE_ANY_NATIVE':pred[o['id']]=(ln,o,h)
            elif t in ('RAW_FACTUAL_BEFORE_TRUTH','FULL_ORIGINAL_TRUTH_BEFORE_B1','ACTUAL_COMPLETE_RECORD'):
                key=(o['id'],o.get('architecture'))
                if t=='RAW_FACTUAL_BEFORE_TRUTH':assert key not in raw;raw[key]=(ln,o,h)
                elif t=='FULL_ORIGINAL_TRUTH_BEFORE_B1':assert key not in truth;truth[key]=(ln,o,h)
                else:complete.append((ln,o,h))
        assert len(starts)==len(ends)==1 and starts==ends
        own=(PREP/spec['source']).relative_to(ROOT).as_posix()
        for path,pin in c['sources'].items():
            if path.startswith('src/') or path.endswith('factual_event_candidate.py') or path==own:
                assert starts[0]['input_sha256'][path]==pin['sha256']
        assert starts[0]['input_sha256'][(PREP/c['catalog']['folder']/'stdout.log').relative_to(ROOT).as_posix()]==c['catalog']['sha256']
        scope_n=0;scope_raw=0
        for ln,o,h in complete:
            key=(o['id'],o.get('architecture'));r=raw.pop(key);tr=truth.pop(key);decl=pred[o['id']]
            assert r[0]<tr[0]<ln
            assert r[1]['payload']==o['payload'] and r[1]['full_pre_store']==o['full_pre_store']
            assert r[1]['fingerprint_pre']==o['fingerprint_pre']==o['source_fingerprint_after']
            assert tr[1]['truth']==o['truth'] and tr[1]['units']==o['full_units']
            k,p,z=decl[1]['basis'];scene=[k,p,0,0,z];params=invocation(scene,c)
            members=[(-1,'factual',o['full_pre_store'],o['payload'],o['fingerprint_pre'])]
            assert [a['role'] for a in o['same_tier_arms']]==(['reference','treatment'] if o['reflection_applicable'] else [])
            for slot,arm in enumerate(o['same_tier_arms']):
                assert arm['ledger']['fingerprint_pre']==o['fingerprint_pre']
                if arm['role']=='reference':
                    assert stores(arm['full_post_store'])==stores(o['full_pre_store'])
                    assert arm['payload']==o['payload'] and not arm['transactions']
                members.append((slot,arm['role'],arm['full_post_store'],arm['payload'],arm['ledger']['fingerprint_post']))
            for slot,role,store,payload,fp in members:
                state=stores(store);assert not state['D'] and not state['P'] and not state['Q'] and fingerprint(state)==fp
                assert o.get('architecture') is None
                measured=path_payload(payload,dindex,qrows,state,scene)
                identity=(spec['folder'],ln,slot);assert identity not in original
                original[identity]={'capture':spec['folder'],'line':ln,'complete_record_row_sha256':h,
                    'actual_source':spec['source'],'original_record_id':o['id'],'original_architecture':o.get('architecture'),
                    'role':role,'original_arm_slot':slot,'complete_original_store_entries':store,
                    'full_four_store_entries':state,'complete_actual_invocation':params,
                    'complete_raw_payload_sha256':sha256(wire(payload)).hexdigest(),'stored_native_observation':measured,
                    'original_fingerprint':fp,'raw_factual_before_truth_line':r[0],'raw_factual_before_truth_row_sha256':r[2],
                    'complete_truth_row_sha256':tr[2],'basis_declaration_line':decl[0],'basis_declaration_row_sha256':decl[2],
                    'full_actual_store_was_originally_captured':True,'new_native_execution':False}
                scope_n+=1;scope_raw+=len(payload['trace']);counts[spec['folder']+':'+role]+=1;outcomes[payload['outcome']]+=1
        assert not raw and not truth and scope_n==spec['native_records'] and scope_raw==spec['raw_rows']
        raw_count+=scope_raw
        del source_rows
    assert len(original)==c['expected']['scope_native'] and raw_count==c['expected']['scope_raw_rows']
    native=[];scope_reg=sha256();plan_reg=sha256();statuses=Counter();hits=set();labels=Counter();n=0
    original_plan=(row for row in records(c['plan']) if row[1]=='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY')
    candidate_info={'folder':HERE.relative_to(PREP).as_posix()+'/evidence','sha256':digest(HERE/'evidence/stdout.log')}
    assert (HERE/'evidence/stdout.log').stat().st_size<=c['guards']['max_output_bytes']
    bindings=[];final=None;keys=None;sorted_native=None
    for _,t,o,_ in records(candidate_info):
        if t.startswith('INPUT_BINDING_'):bindings.append(o)
        elif t=='SOURCE_INPUT_CONTRACT':assert o==proof
        elif t=='HISTORICAL_COMPLETE_NATIVE_INPUT':
            expected=original.pop((o['capture'],o['line'],o['original_arm_slot']))
            expected={'index':len(native),**expected};assert expected==o
            native.append(o);scope_reg.update(wire(o))
        elif t=='HISTORICAL_SCOPE_INDEX_COMPLETE':
            assert not original and len(native)==c['expected']['scope_native']
            sorted_native=sorted((wire([x['complete_actual_invocation'],stores(x['full_four_store_entries'])]),x['index']) for x in native)
            keys=[k for k,i in sorted_native]
            assert o=={'records':len(native),'unique_complete_inputs':len(set(keys)),'raw_rows':raw_count,
                'counts':dict(counts),'outcomes':dict(outcomes),'scope_registry_sha256':scope_reg.hexdigest(),
                'all_other_history_pending':True,'native_rerun':False}
        elif t=='PRESERVED_PLANNED_INPUT_HISTORY_STATUS':
            ln,tag,p,h=next(original_plan);assert p['index']==n
            requested=p['complete_requested_input'];params=invocation(requested['scene'],c)
            for k,v in params.items():
                if k!='reward_mode':assert requested[k]==v
            assert requested['root']==[requested['scene'][0],requested['scene'][1],requested['scene'][4]]
            assert requested['installation'] in ('D_Q','D_patch') and requested['reference_name']=='v31-stored-nominal-no-DP'
            state=stores(p['full_four_store_entries'])
            assert fingerprint(state)==p['original_fingerprint'] and sha256(wire(state)).hexdigest()==p['full_store_sha256']
            key=wire([params,state]);lo=bisect_left(keys,key);hi=bisect_right(keys,key)
            match=sorted(i for k,i in sorted_native[lo:hi] if k==key)
            for i in match:
                assert native[i]['full_four_store_entries']==state and native[i]['complete_actual_invocation']==params
                for k,v in p['stored_source_expectation_not_measurement'].items():
                    if v is not None:assert native[i]['stored_native_observation'][k]==v
                hits.add(i);labels[requested['installation']]+=1
            prior=p['exact_old_native_v46_v47_reference']
            status='EXACT_OLD_v46_v47_REFERENCE_PRESERVED' if prior is not None else ('EXACT_COMPLETE_OLD_CONTROLLER_PAIR_SENTINEL_NATIVE' if match else 'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX')
            expected={'index':n,'v55_capture':c['plan']['folder'],'v55_line':ln,'complete_v55_row_sha256':h,
                'original_requested_input':requested,'original_descriptor_reference':p['first_descriptor_reference'],
                'original_v46_v47_reference':prior,'scoped_exact_native_record_indices':match,'status':status,
                'all_other_history_audit_pending':True,'native_execution_authorized':False}
            assert expected==o;statuses[status]+=1;plan_reg.update(wire(o));n+=1
        elif t=='FINAL':assert final is None;final=o
    assert next(original_plan,None) is None and n==279158 and not original and bindings[0]==bindings[1]
    assert all(before['input_sha256'][p]==h for p,h in bindings[0]['input_sha256'].items())
    expected={'planned_inputs':n,'status_counts':dict(statuses),'scope_native_records':len(native),
        'scope_unique_complete_inputs':len(set(keys)),'scope_raw_rows':raw_count,'scope_counts':dict(counts),
        'scope_outcomes':dict(outcomes),'matched_scope_native_records':len(hits),'matched_planned_installation_labels':dict(labels),
        'scope_registry_sha256':scope_reg.hexdigest(),'plan_status_registry_sha256':plan_reg.hexdigest(),
        'pending_before':c['expected']['pending_before'],'pending_after':statuses['PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX'],
        'all_history_closed':False,'native_calibration_executed':0,'native_launch_authorized':False,
        'scientific_PASS':False,'collection_authorized':False,'research_complete':False}
    assert final==expected
    after=binding(c)
    for name in ('claim.json','exit.json','stdout.log','stderr.log'):
        after['input_sha256'][(HERE/'evidence'/name).relative_to(ROOT).as_posix()]=digest(HERE/'evidence'/name)
    after['distinct_inputs']=len(after['input_sha256']);assert after==before
    emit('CHECK',{**expected,'runtime_inputs':before['distinct_inputs'],'candidate_fullcapture_bytes':(HERE/'evidence/stdout.log').stat().st_size,
        'independence':'Same main agent independent EOF keyed join and sorted full-byte bisect, not independent expert'})
if __name__=='__main__':main()

