"""Independent sorted-full-byte historical singleton overlap checker; no experiment imports."""
import ast
from bisect import bisect_left, bisect_right
from collections import Counter
from hashlib import sha1, sha256
import json
from pathlib import Path
import subprocess

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
def emit(t,o): print(t+'='+wire(o).decode().rstrip('\n'),flush=True)

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
        assert row['a_cmd']==command
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
    proof=source_proof(c)
    catalog=[]
    for _,tag,o,_ in records(c['catalog']):
        if tag=='DECISION_CONTEXT':catalog.append(o)
    ordered=sorted(catalog,key=lambda o:(o['context'][2],o['context'][3],o['context'][4],o['context'][0],o['context'][1],o['context'][5],o['context'][6]))
    assert ordered==catalog and len(catalog)==13824
    reference='\n'.join(','.join(map(str,o['context']))+'|'+','.join(str(a)+'='+v for a,v in sorted(o['q_row_hex'])) for o in ordered)
    assert sha256(reference.encode()).hexdigest()==c['reference_sha256']
    dindex={tuple(o['context']):i for i,o in enumerate(catalog)}
    qrows={tuple(o['context']):o['q_row_hex'] for o in catalog}
    historical={};read_only={};v33_records={}
    count=Counter();raw_total=0
    # Independent stored join: collect raw/actual/prediction rows by full source identities,
    # then join only after EOF, instead of candidate's streaming pending-raw variable.
    for spec in c['scope']:
        rows=list(records(spec));pred={o['id']:o for _,t,o,_ in rows if t=='CONFIGURATION_PREDICTION_READ_ONLY'}
        raw_by={}
        def identity(o):
            if spec['native_records']==1171:return (o['id'],o['architecture'],o['basis_index'])
            if spec['native_records']==50:return (o['id'],o['basis_index'])
            return (tuple(o['site']),o['target'],o['basis_index'])
        for ln,t,o,h in rows:
            if t=='RAW_NATIVE_FACTUAL_BEFORE_TRUTH':
                key=identity(o);assert key not in raw_by;raw_by[key]=(ln,o,h)
        starts=[o for _,t,o,_ in rows if t=='INPUT_BINDING_BEFORE'];ends=[o for _,t,o,_ in rows if t=='INPUT_BINDING_AFTER']
        assert len(starts)==len(ends)==1 and starts==ends
        for path,pin in c['sources'].items():
            if path in starts[0]['input_sha256']:assert starts[0]['input_sha256'][path]==pin['sha256']
        own=(PREP/spec['source']).relative_to(ROOT).as_posix()
        assert starts[0]['input_sha256'][own]==c['sources'][own]['sha256']
        for ln,t,o,h in rows:
            if t=='OLD_NATIVE_PAIR_READ_ONLY':
                old=v33_records[(tuple(o['site']),o['target'],o['basis_index'])]
                assert o['old_id']==old['id'] and o['fingerprint']==old['fingerprint_pre']
                assert o['old_payload_sha256']==sha256(wire(old['payload'])).hexdigest()
                read_only[(spec['folder'],ln)]={'tag':t,'row':o,'hash':h}
            if t!=spec['tag']:continue
            if o.get('source')=='READ_ONLY_EXACT_v25_FACTUAL':
                assert identity(o) not in raw_by
                read_only[(spec['folder'],ln)]={'tag':'FORWARDED','row':o,'hash':h};continue
            raw=raw_by.pop(identity(o));assert raw[0]<ln
            assert all(raw[1][k]==o['payload'][k] for k in ('trace','return_hex','outcome'))
            for k in ('id','architecture','site','address','target'):
                if k in raw[1]:assert raw[1][k]==o[k]
            # Direct literal decoding of the uniquely sourced single backing-store entry.
            if spec['native_records']==1171:
                declaration=pred[o['id']];a=declaration['address'];target=declaration['target']
                ch='Q' if o['architecture']=='D_Q' else 'D'
                assert o['architecture'] in ('D_Q','D_patch') and o['source']=='NEW_NATIVE_SINGLETON_FACTUAL'
                entry=[a+[target],o['DQ_promoted_value_hex']] if ch=='Q' else [a,target]
            else:
                a=o.get('site',o.get('address'));target=o['target'];ch='X';entry=[a,target]
            state={name:([entry] if name==ch else []) for name in ('D','P','Q','X')}
            assert [len(state[name]) for name in ('D','P','X','Q')]==o['all_store_sizes']
            assert fingerprint(state)==o['fingerprint_pre']==o['fingerprint_after_read']
            scene=o['scene'];assert o['basis']==[scene[0],scene[1],scene[4]]
            params=invocation(scene,c)
            observed=path_payload(o['payload'],dindex,qrows,state,scene)
            historical[(spec['folder'],ln)]={'row':o,'hash':h,'state':state,'params':params,'raw':raw,'observed':observed}
            if spec['native_records']==50:v33_records[(tuple(a),target,o['basis_index'])]=o
            count[spec['folder']]+=1;raw_total+=len(o['payload']['trace'])
        assert not raw_by and count[spec['folder']]==spec['native_records']
    assert len(historical)==1350 and raw_total==11038 and len(read_only)==51
    native=[];scoped_registry=sha256();plan_rows=[];candidate_final=None;candidate_bind=[]
    capture={'folder':HERE.relative_to(PREP).as_posix()+'/evidence','sha256':digest(HERE/'evidence/stdout.log')}
    assert (HERE/'evidence/stdout.log').stat().st_size<=c['guards']['max_output_bytes']
    for ln,t,o,h in records(capture):
        if t.startswith('INPUT_BINDING_'):candidate_bind.append(o)
        elif t=='SOURCE_INPUT_CONTRACT':assert o==proof
        elif t=='HISTORICAL_COMPLETE_NATIVE_INPUT':
            original=historical.pop((o['capture'],o['line']))
            assert o['index']==len(native) and o['original_record']==original['row']
            assert o['complete_row_sha256']==original['hash']
            assert o['full_four_store_entries']==original['state'] and o['complete_actual_invocation']==original['params']
            assert o['stored_native_observation']==original['observed']
            assert o['raw_before_truth_line']==original['raw'][0] and o['raw_before_truth_row_sha256']==original['raw'][2]
            assert o['complete_raw_payload_sha256']==sha256(wire(original['row']['payload'])).hexdigest()
            native.append(o);scoped_registry.update(wire(o))
        elif t=='UNCHANGED_OLD_NATIVE_REFERENCE':
            original=read_only.pop((o['capture'],o['line']))
            assert original['row']==o['original_reference'] and original['hash']==o['complete_row_sha256']
            parent=native[o['native_record_index']]['original_record']
            assert parent['id']==o['original_reference']['old_id']
        elif t=='FORWARDED_v25_SOURCE_AUDIT_PENDING':
            original=read_only.pop((o['capture'],o['line']))
            assert original['row']==o['original_record'] and original['hash']==o['complete_row_sha256'] and not o['new_native_record']
        elif t=='PRESERVED_PLANNED_INPUT_HISTORY_STATUS':plan_rows.append(o)
        elif t=='FINAL':assert candidate_final is None;candidate_final=o
    assert not historical and not read_only and len(native)==1350
    assert candidate_bind[0]==candidate_bind[1]
    assert all(before['input_sha256'][p]==v for p,v in candidate_bind[0]['input_sha256'].items())
    # Full bytes sorted and bisected: never reuse by fingerprint or response.
    sorted_native=sorted((wire([o['complete_actual_invocation'],stores(o['full_four_store_entries'])]),o['index']) for o in native)
    keys=[k for k,i in sorted_native];unique_keys=len(set(keys));hits=set();labels=Counter();statuses=Counter();registry=sha256()
    n=0
    for ln,t,o,h in records(c['plan']):
        if t!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        written=plan_rows[n];assert written['index']==o['index']==n
        assert written['complete_v55_row_sha256']==h and written['v55_line']==ln
        assert written['original_requested_input']==o['complete_requested_input']
        assert written['original_descriptor_reference']==o['first_descriptor_reference']
        assert written['original_v46_v47_reference']==o['exact_old_native_v46_v47_reference']
        args=o['complete_requested_input'];params=invocation(args['scene'],c)
        for k,v in params.items():
            if k!='reward_mode':assert args[k]==v
        state=stores(o['full_four_store_entries']);key=wire([params,state])
        assert fingerprint(state)==o['original_fingerprint'] and sha256(wire(state)).hexdigest()==o['full_store_sha256']
        lo=bisect_left(keys,key);hi=bisect_right(keys,key)
        matched=sorted(i for k,i in sorted_native[lo:hi] if k==key)
        assert matched==written['scoped_exact_native_record_indices']
        for i in matched:
            old=native[i]
            assert old['full_four_store_entries']==state and old['complete_actual_invocation']==params
            for k,v in o['stored_source_expectation_not_measurement'].items():
                if v is not None:assert old['stored_native_observation'][k]==v
            hits.add(i);labels[args['installation']]+=1
        status='EXACT_OLD_v46_v47_REFERENCE_PRESERVED' if o['exact_old_native_v46_v47_reference'] is not None else ('EXACT_COMPLETE_OLD_SINGLETON_NATIVE' if matched else 'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX')
        assert written['status']==status and written['all_other_history_audit_pending'] and not written['native_execution_authorized']
        statuses[status]+=1;registry.update(wire(written));n+=1
    assert n==len(plan_rows)==279158
    assert candidate_final['scope_registry_sha256']==scoped_registry.hexdigest()
    assert candidate_final['plan_status_registry_sha256']==registry.hexdigest()
    assert candidate_final['status_counts']==dict(statuses)
    assert candidate_final['matched_scope_native_records']==len(hits)
    assert candidate_final['matched_planned_installation_labels']==dict(labels)
    assert candidate_final['scope_unique_concrete_native_inputs']==unique_keys
    after=binding(c)
    for name in ('claim.json','exit.json','stdout.log','stderr.log'):
        after['input_sha256'][(HERE/'evidence'/name).relative_to(ROOT).as_posix()]=digest(HERE/'evidence'/name)
    after['distinct_inputs']=len(after['input_sha256']);assert after==before
    emit('CHECK',{'scope_native_records':len(native),'scope_raw_rows':raw_total,'scope_unique_concrete_native_inputs':unique_keys,
        'original_planned_inputs':n,'status_counts':dict(statuses),'matched_scope_native_records':len(hits),
        'matched_planned_installation_labels':dict(labels),'scope_registry_sha256':scoped_registry.hexdigest(),
        'plan_status_registry_sha256':registry.hexdigest(),'runtime_inputs':before['distinct_inputs'],
        'candidate_fullcapture_bytes':(HERE/'evidence/stdout.log').stat().st_size,'all_history_closed':False,
        'independence':'Same main agent independent stored join plus sorted full-byte comparator, not independent expert',
        'new_RFL_execution':0,'native_launch_authorized':False,'collection_authorized':False,'scientific_PASS':False})
if __name__=='__main__':main()
