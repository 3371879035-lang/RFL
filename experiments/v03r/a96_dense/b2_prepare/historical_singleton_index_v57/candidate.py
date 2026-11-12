"""Source-bound complete historical singleton native input index; stored-only."""
import ast
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
    c=read(HERE/'contract.json');before=binding(c);emit('INPUT_BINDING_BEFORE',before)
    emit('SOURCE_INPUT_CONTRACT',source_proof(c))
    qrows={};dindex={};qcanon=[]
    for line,tag,o,h in records(c['catalog']):
        if tag=='DECISION_CONTEXT':
            a=tuple(o['context']);assert a not in qrows
            dindex[a]=len(dindex);qrows[a]=o['q_row_hex']
            qcanon.append(','.join(map(str,a))+'|'+','.join(str(x)+'='+v for x,v in o['q_row_hex']))
    assert len(qrows)==13824 and sha256('\n'.join(qcanon).encode()).hexdigest()==c['reference_sha256']
    emit('COMPLETE_COMMON_REFERENCE_BINDING',{'catalog':c['catalog'],'rows':len(qrows),
         'full_canonical_reference_sha256':c['reference_sha256'],'new_reference_DP':0})
    native=[];index={};oldx={};outcomes=Counter();rawrows=0;readonly=Counter()
    reg=sha256()
    for spec in c['scope']:
        pred={};raw=None;original_bind=None;source_count=0
        for line,tag,o,h in records(spec):
            if tag=='INPUT_BINDING_BEFORE':
                original_bind=o
                for path,pin in c['sources'].items():
                    if path in o['input_sha256']:assert o['input_sha256'][path]==pin['sha256']
                own=(PREP/spec['source']).relative_to(ROOT).as_posix()
                assert o['input_sha256'][own]==c['sources'][own]['sha256']
                assert o['input_sha256'][(PREP/c['catalog']['folder']/'stdout.log').relative_to(ROOT).as_posix()]==c['catalog']['sha256']
            elif tag=='INPUT_BINDING_AFTER':assert o==original_bind
            elif tag=='CONFIGURATION_PREDICTION_READ_ONLY':pred[o['id']]=o
            elif tag=='RAW_NATIVE_FACTUAL_BEFORE_TRUTH':
                assert raw is None;raw=(line,o,h)
            elif tag=='OLD_NATIVE_PAIR_READ_ONLY':
                old=oldx[(tuple(o['site']),o['target'],o['basis_index'])]
                assert old['original_record']['id']==o['old_id']
                assert old['original_record']['fingerprint_pre']==o['fingerprint']
                assert sha256(wire(old['original_record']['payload'])).hexdigest()==o['old_payload_sha256']
                readonly['v35']+=1;emit('UNCHANGED_OLD_NATIVE_REFERENCE',{'capture':spec['folder'],'line':line,'complete_row_sha256':h,'original_reference':o,'native_record_index':old['index']})
            elif tag==spec['tag']:
                if o.get('source')=='READ_ONLY_EXACT_v25_FACTUAL':
                    assert spec['native_records']==1171 and raw is None
                    readonly['v36']+=1;emit('FORWARDED_v25_SOURCE_AUDIT_PENDING',{'capture':spec['folder'],'line':line,'complete_row_sha256':h,'original_record':o,'new_native_record':False});continue
                assert raw is not None
                for k in ('trace','outcome','return_hex'):assert raw[1][k]==o['payload'][k]
                assert raw[1]['basis_index']==o['basis_index']
                state={ch:[] for ch in ('D','P','Q','X')}
                if spec['native_records']==1171:
                    assert o['source']=='NEW_NATIVE_SINGLETON_FACTUAL'
                    a=pred[o['id']]['address'];target=pred[o['id']]['target']
                    assert raw[1]['id']==o['id'] and raw[1]['architecture']==o['architecture']
                    if o['architecture']=='D_Q':state['Q']=[[a+[target],o['DQ_promoted_value_hex']]]
                    else:assert o['architecture']=='D_patch';state['D']=[[a,target]]
                else:
                    a=o['address'] if 'address' in o else o['site'];target=o['target'];state['X']=[[a,target]]
                state=stores(state)
                assert [len(state[ch]) for ch in ('D','P','X','Q')]==o['all_store_sizes']
                assert fingerprint(state)==o['fingerprint_pre']==o['fingerprint_after_read']
                scene=o['scene'];assert o['basis']==[scene[0],scene[1],scene[4]]
                args=invocation(scene,c);observed=path_payload(o['payload'],dindex,qrows,state,scene)
                item={'index':len(native),'capture':spec['folder'],'line':line,'complete_row_sha256':h,
                    'actual_source':spec['source'],'raw_before_truth_line':raw[0],'raw_before_truth_row_sha256':raw[2],
                    'complete_raw_payload_sha256':sha256(wire(o['payload'])).hexdigest(),
                    'original_record':o,'complete_actual_invocation':args,'full_four_store_entries':state,
                    'source_bound_complete_store_serialization_not_new_measurement':True,'stored_native_observation':observed}
                key=fullkey(args,state);index.setdefault(key,[]).append(item['index'])
                native.append(item);reg.update(wire(item));emit('HISTORICAL_COMPLETE_NATIVE_INPUT',item)
                if spec['native_records']!=1171:oldx[(tuple(a),target,o['basis_index'])]=item
                outcomes[o['payload']['outcome']]+=1;rawrows+=len(o['payload']['trace']);source_count+=1;raw=None
        assert raw is None and source_count==spec['native_records']
    assert len(native)==c['expected']['scope_native'] and rawrows==c['expected']['scope_raw_rows']
    assert readonly==Counter(v35=50,v36=1)
    assert len(native)<=c['guards']['max_native_records']
    emit('HISTORICAL_SCOPE_INDEX_COMPLETE',{'records':len(native),'raw_rows':rawrows,'unique_concrete_inputs':len(index),
        'complete_registry_sha256':reg.hexdigest(),'outcomes':dict(outcomes),'readonly_references':dict(readonly),
        'all_history_closed':False,'no_native_or_fixture_rerun':True})
    counts=Counter();crosslabels=Counter();hits=set();registry=sha256();n=0
    allowed={'P_identity','initial_automaton_memory','initial_committed_option','initial_state','installation',
        'learner_policy','mask_do','nominal_Q_reference_sha256','reference_name','root','scene','training'}
    for line,tag,o,h in records(c['plan']):
        if tag!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert o['index']==n;n+=1;args=o['complete_requested_input'];assert set(args)==allowed
        assert args['root']==[args['scene'][0],args['scene'][1],args['scene'][4]]
        complete=invocation(args['scene'],c)
        for k,v in complete.items():
            if k!='reward_mode':assert args[k]==v
        assert args['installation'] in ('D_Q','D_patch') and args['reference_name']=='v31-stored-nominal-no-DP'
        state=stores(o['full_four_store_entries']);assert fingerprint(state)==o['original_fingerprint']
        assert sha256(wire(state)).hexdigest()==o['full_store_sha256']
        match=index.get(fullkey(complete,state),[])
        for j in match:
            item=native[j];assert wire(item['full_four_store_entries'])==wire(state)
            expect=o['stored_source_expectation_not_measurement'];actual=item['stored_native_observation']
            for k,v in expect.items():
                if v is not None:assert actual[k]==v,('stored expectation mismatch',n-1,j,k)
            hits.add(j);crosslabels[args['installation']]+=1
        prior=o['exact_old_native_v46_v47_reference']
        status='EXACT_OLD_v46_v47_REFERENCE_PRESERVED' if prior is not None else ('EXACT_COMPLETE_OLD_SINGLETON_NATIVE' if match else 'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX')
        counts[status]+=1
        row={'index':o['index'],'v55_capture':c['plan']['folder'],'v55_line':line,'complete_v55_row_sha256':h,
            'original_requested_input':args,'original_descriptor_reference':o['first_descriptor_reference'],
            'original_v46_v47_reference':prior,'scoped_exact_native_record_indices':match,'status':status,
            'all_other_history_audit_pending':True,'native_execution_authorized':False}
        registry.update(wire(row));emit('PRESERVED_PLANNED_INPUT_HISTORY_STATUS',row)
    assert n==c['expected']['planned'] and n<=c['guards']['max_planned_inputs']
    assert counts['EXACT_OLD_v46_v47_REFERENCE_PRESERVED']==c['expected']['old_v46_v47']
    after=binding(c);assert after==before;emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'planned_inputs':n,'status_counts':dict(counts),'matched_scope_native_records':len(hits),
        'matched_planned_installation_labels':dict(crosslabels),'scope_native_records':len(native),'scope_raw_rows':rawrows,
        'scope_unique_concrete_native_inputs':len(index),'scope_registry_sha256':reg.hexdigest(),
        'plan_status_registry_sha256':registry.hexdigest(),'pending_before':c['expected']['pending_before'],
        'pending_after':counts['PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX'],'all_history_closed':False,
        'native_calibration_executed':0,'native_launch_authorized':False,'collection_authorized':False,
        'scientific_PASS':False,'research_complete':False})
if __name__=='__main__':main()
