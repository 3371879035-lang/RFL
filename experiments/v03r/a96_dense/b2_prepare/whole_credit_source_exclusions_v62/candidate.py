"""V24 actual-entry necessary literal-support exclusion. No RFL imports/execution."""
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

def source_proof(c):
    functions=0
    for name,pin in c['sources'].items():
        raw=(ROOT/name).read_bytes();assert sha256(raw).hexdigest()==pin['sha256']
        observed=ast_functions(ast.parse(raw))
        assert {k:observed[k] for k in pin['qualified_function_AST_sha256']}==pin['qualified_function_AST_sha256']
        functions+=len(pin['qualified_function_AST_sha256'])
    kt=ast.parse((ROOT/'src/rfl_rebuild/env/kernel.py').read_bytes())
    constants={n.target.id:ast.literal_eval(n.value) for n in kt.body
               if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id in ('START','HORIZON')}
    assert constants=={'START':(0,2),'HORIZON':12}
    expected=[[0,2,t,0,0,1,0,a] for t in range(12) for a in range(5)]
    assert c['family_q_support']['V24_A_SAFE_Q_SUPPORT']==expected
    assert c['family_q_support']['V24_B_EXACT_Q_ADDRESS_SUPPORT']==[[0,2,0,0,0,2,0,3]]
    entry=ast.parse((ROOT/c['scope']['source']).read_bytes())
    funcs={n.name:n for n in entry.body if isinstance(n,ast.FunctionDef)}
    for name in ('complete_credit_check','ruler_check'):
        ct=[n for n in ast.walk(funcs[name]) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='LearnerPersistentState']
        assert len(ct)==1 and not ct[0].args and not ct[0].keywords
    return {'source_count':len(c['sources']),'qualified_function_AST_pins':functions,'sources':c['sources'],
        'family_q_support':c['family_q_support'],'reasoning':c['source_invariant_reasoning'],
        'scope_limits':c['scope_limits'],'proof_kind':'NECESSARY_ADDRESS_SUPPORT_NOT_COMPLETE_RAW_INPUT_INDEX'}

def q_repr_address(text):
    node=ast.parse(text,mode='eval').body
    assert isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='QAddress' and not node.args
    kws={k.arg:k.value for k in node.keywords};assert set(kws)=={'state','z','m','a'}
    s=kws['state'];assert isinstance(s,ast.Call) and isinstance(s.func,ast.Name) and s.func.id=='State' and not s.args
    sk={k.arg:ast.literal_eval(k.value) for k in s.keywords};assert set(sk)=={'x','y','t','kappa','phi'}
    return [sk[k] for k in ('x','y','t','kappa','phi')]+[ast.literal_eval(kws[k]) for k in ('z','m','a')]

def v24_scope(c):
    rows=list(records(c['scope']));bytag={t:(ln,o,h) for ln,t,o,h in rows if t!='STAGE'}
    before=bytag['INPUT_BINDING'][1];assert before['parent_HEAD']==c['scope']['parent_commit']
    pins=before['input_file_sha256'];assert len(pins)==c['scope']['actual_execution_inputs']
    for name,h in pins.items():
        if name=='experiments/rebuild_status_current.json':
            raw=subprocess.check_output(['git','show',before['parent_HEAD']+':'+name],cwd=ROOT)
            assert sha256(raw).hexdigest()==h
        else:assert digest(ROOT/name)==h,name
    for name,pin in c['sources'].items():assert pins[name]==pin['sha256']
    A=bytag['COMPLETE_CREDIT'][1];B=bytag['COMPLETE_RULER'][1];F=bytag['FINAL'][1]
    owners=['DecisionAddress(State(0,2,'+str(t)+',0,0),1,0)' for t in range(7)]
    assert A['installed_override_count']==12 and A['actual_manifestation_count']==A['declared_owner_count']==7
    assert A['complete_owner_sites']==owners and A['ordered_Oracle_credit']==['Decision_'+str(t) for t in range(7)]
    assert A['source_fingerprint_unchanged'] and len(A['full_pre_census'])==5760
    assert len(A['same_tier_pairs'])==2
    for pair in A['same_tier_pairs']:
        assert pair['tier'] in ('L0_FACTUAL','L3_ORACLE') and len(pair['arms'])==2
        for arm in pair['arms']:
            receipts=arm['ledger']['receipts'];assert len(receipts)==7
            assert [x.split('|')[0] for x in receipts]==[','.join(map(str,[0,2,t,0,0,1,0])) for t in range(7)]
            assert arm['transactions']==[] if arm['role']=='reference' else len(arm['transactions'])==1 and arm['transactions'][0]['edit_count']==7
    spill=B['genuine_substrate_spill'];address=q_repr_address(spill['Q_address'])
    assert address==c['family_q_support']['V24_B_EXACT_Q_ADDRESS_SUPPORT'][0]
    assert spill['value_hex']=='-0x1.eb851eb851ec0p-4' and spill['scene']==[0,0,0,0,2]
    assert spill['owner']=='DecisionAddress(State(0,2,0,0,0),2,0)' and spill['applied_action']==4
    assert len(B['full_pre_census'])==5760 and len(B['ordered_predicted_pre_post_measured_pre_post_hex'])==5160
    assert B['source_fingerprint_unchanged'] and len(B['rejected_serial_argument_mutations'])==5
    assert F['before_after_bindings_equal'] and not F['collection_authorized'] and not F['research_complete']
    p=PREP/c['scope']['folder']
    return {'folder':c['scope']['folder'],'source':c['scope']['source'],
        'claim_sha256':digest(p/'claim.json'),'exit_sha256':digest(p/'exit.json'),'capture':read(p/'exit.json')['files'],
        'original_parent':before['parent_HEAD'],'original_execution_input_bindings':len(pins),'canonical_JSON_lines':4,
        'raw_STAGE_lines':2,'complete_record_references':{t:{'line':ln,'complete_original_row_sha256':h} for t,(ln,o,h) in bytag.items()},
        'family_q_support':c['family_q_support'],'captured_spill_address':address,'captured_spill_value_hex':spill['value_hex'],
        'all_original_raw_maps_credit_receipts_preserved':True,'not_reconstructed_unprinted_fullstores':True,
        'unprinted_installation_and_B1_scalars_not_recomputed':True,'no_old_native_execution':True}

def outside(store,support):
    allowed={tuple(a) for a in support}
    for ch in ('D','P','Q','X'):
        for address,value in store[ch]:
            if ch!='Q' or tuple(address) not in allowed:
                return {'channel':ch,'address':address,'captured_value':value}
    raise AssertionError('necessary family could match')

def planned_row(c,ln,o,h,state,witnesses):
    prior=o['exact_old_native_v46_v47_reference']
    status='EXACT_OLD_v46_v47_REFERENCE_PRESERVED' if prior is not None else 'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX'
    return {'index':o['index'],'v55_capture':c['plan']['folder'],'v55_line':ln,'complete_v55_row_sha256':h,
        'original_requested_input':o['complete_requested_input'],'original_descriptor_reference':o['first_descriptor_reference'],
        'original_v46_v47_reference':prior,'full_store_sha256':o['full_store_sha256'],
        'exact_address_exclusion_witnesses':witnesses,'status':status,
        'all_other_history_audit_pending':True,'native_execution_authorized':False}

def summary(c,n,counts,scope,registry):
    return {'planned_inputs':n,'scope_entry_captures':1,'necessary_families':2,'scope_registry_sha256':scope,
        'address_exclusion_registry_sha256':registry,'status_counts':dict(counts),'scope_compatible_planned_inputs':0,
        'pending_before':c['expected']['pending'],'pending_after':c['expected']['pending'],
        'original_unprinted_scalars_and_raw_not_invented':True,'all_history_closed':False,'native_calibration_executed':0,
        'native_launch_authorized':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False}

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

def main():
    c=read(HERE/'contract.json');before=binding(c);emit('INPUT_BINDING_BEFORE',before)
    emit('SOURCE_INVARIANT_PROOF',source_proof(c));scope=v24_scope(c);emit('SCOPED_SOURCE_EXCLUSION',scope)
    registry=sha256();counts=Counter();n=0
    for ln,tag,o,h in records(c['plan']):
        if tag!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert o['index']==n and o['complete_descriptor_alias_count']==1
        state=stores(o['full_four_store_entries'])
        assert sha256(wire(state)).hexdigest()==o['full_store_sha256'] and fingerprint(state)==o['original_fingerprint']
        assert o['complete_requested_input']['nominal_Q_reference_sha256']==c['reference_sha256']
        witnesses={f:outside(state,support) for f,support in c['family_q_support'].items()}
        row=planned_row(c,ln,o,h,state,witnesses);registry.update(wire(row));counts[row['status']]+=1
        emit('PLANNED_SOURCE_EXCLUSION',row);n+=1;assert n<=c['guards']['max_planned']
    assert n==c['expected']['planned']
    assert counts=={'EXACT_OLD_v46_v47_REFERENCE_PRESERVED':c['expected']['old_v46_v47'],'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX':c['expected']['pending']}
    assert binding(c)==before;emit('INPUT_BINDING_AFTER',before)
    emit('FINAL',summary(c,n,counts,sha256(wire(scope)).hexdigest(),registry.hexdigest()))
if __name__=='__main__':main()
