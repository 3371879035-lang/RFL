"""Independent ordered address-list and EOF keyed-join audit. Not expert approval."""
import ast
import re
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

def full_entries(o):
    assert sorted(o)==['D','P','Q','X']
    result={}
    for channel in ('D','P','Q','X'):
        entries=[]
        for address,value in o[channel]:
            if channel=='P':assert type(address)==int;key=(address,)
            else:
                assert isinstance(address,list) and all(type(x)==int for x in address)
                key=tuple(address);assert len(key)=={'D':7,'Q':8,'X':6}[channel]
            entries.append((key,address,value))
        entries.sort(key=lambda x:x[0])
        for a,b in zip(entries,entries[1:]):assert a[0]!=b[0],('duplicate literal address',channel)
        result[channel]=[[a,v] for _,a,v in entries]
    return result
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


def independent_proof(c):
    count=0
    def visit(nodes,parents=()):
        found={}
        for node in nodes:
            if isinstance(node,ast.ClassDef):found.update(visit(node.body,parents+(node.name,)))
            elif isinstance(node,ast.FunctionDef):
                found['.'.join(parents+(node.name,))]=sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()
        return found
    for name,pin in c['sources'].items():
        data=(ROOT/name).read_bytes();assert digest(ROOT/name)==pin['sha256']
        observed=visit(ast.parse(data).body)
        for name2,h in pin['qualified_function_AST_sha256'].items():assert observed[name2]==h
        count+=len(pin['qualified_function_AST_sha256'])
    kernel=ast.parse((ROOT/'src/rfl_rebuild/env/kernel.py').read_bytes())
    horizon=next(ast.literal_eval(n.value) for n in kernel.body if isinstance(n,ast.AnnAssign) and getattr(n.target,'id',None)=='HORIZON')
    start=next(ast.literal_eval(n.value) for n in kernel.body if isinstance(n,ast.AnnAssign) and getattr(n.target,'id',None)=='START')
    assert horizon==12 and start==(0,2)
    allowedA=[]
    for t in range(horizon):
        for a in range(5):allowedA.append(list(start)+[t,0,0,1,0,a])
    assert c['family_q_support']=={'V24_A_SAFE_Q_SUPPORT':allowedA,'V24_B_EXACT_Q_ADDRESS_SUPPORT':[[0,2,0,0,0,2,0,3]]}
    code=ast.parse((ROOT/c['scope']['source']).read_bytes());functions={n.name:n for n in code.body if isinstance(n,ast.FunctionDef)}
    for fn in ('complete_credit_check','ruler_check'):
        calls=[n for n in ast.walk(functions[fn]) if isinstance(n,ast.Call) and getattr(n.func,'id',None)=='LearnerPersistentState']
        assert len(calls)==1 and calls[0].args==calls[0].keywords==[]
    calls=[n.func.id for n in ast.walk(functions['main']) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
    assert calls.count('complete_credit_check')==calls.count('ruler_check')==1
    return {'source_count':len(c['sources']),'qualified_function_AST_pins':count,'sources':c['sources'],
        'family_q_support':c['family_q_support'],'reasoning':c['source_invariant_reasoning'],
        'scope_limits':c['scope_limits'],'proof_kind':'NECESSARY_ADDRESS_SUPPORT_NOT_COMPLETE_RAW_INPUT_INDEX'}

def independent_scope(c):
    rows=list(records(c['scope']))
    table={tag:(line,o,h) for line,tag,o,h in rows if tag!='STAGE'}
    first=table['INPUT_BINDING'][1];assert first['parent_HEAD']==c['scope']['parent_commit']
    assert len(first['input_file_sha256'])==704
    for name,h in first['input_file_sha256'].items():
        if name=='experiments/rebuild_status_current.json':
            b=subprocess.check_output(['git','show',first['parent_HEAD']+':'+name],cwd=ROOT);assert sha256(b).hexdigest()==h
        else:assert digest(ROOT/name)==h
    for path,pin in c['sources'].items():assert first['input_file_sha256'][path]==pin['sha256']
    credit=table['COMPLETE_CREDIT'][1];ruler=table['COMPLETE_RULER'][1]
    assert credit['installed_override_count']==12
    assert credit['actual_manifestation_count']==credit['declared_owner_count']==7
    assert credit['ordered_Oracle_credit']==['Decision_'+str(i) for i in range(7)]
    for t,owner in enumerate(credit['complete_owner_sites']):assert owner=='DecisionAddress(State(0,2,'+str(t)+',0,0),1,0)'
    assert len(credit['complete_owner_sites'])==7 and credit['source_fingerprint_unchanged']
    assert len(credit['full_pre_census'])==5760 and len(credit['same_tier_pairs'])==2
    for pair in credit['same_tier_pairs']:
        assert len(pair['arms'])==2 and pair['tier'] in ('L0_FACTUAL','L3_ORACLE')
        for arm in pair['arms']:
            assert len(arm['ledger']['receipts'])==7
            for t,rec in enumerate(arm['ledger']['receipts']):assert rec.split('|')[0]==','.join(map(str,[0,2,t,0,0,1,0]))
            if arm['role']=='reference':assert not arm['transactions']
            else:assert len(arm['transactions'])==1 and arm['transactions'][0]['edit_count']==7
    spill=ruler['genuine_substrate_spill']
    expression=r'QAddress\(state=State\(x=(-?\d+), y=(-?\d+), t=(-?\d+), kappa=(-?\d+), phi=(-?\d+)\), z=(-?\d+), m=(-?\d+), a=(-?\d+)\)'
    match=re.fullmatch(expression,spill['Q_address']);assert match
    address=list(map(int,match.groups()));assert address==[0,2,0,0,0,2,0,3]
    assert spill['value_hex']=='-0x1.eb851eb851ec0p-4' and spill['scene']==[0,0,0,0,2]
    assert spill['owner']=='DecisionAddress(State(0,2,0,0,0),2,0)' and spill['applied_action']==4
    assert len(ruler['full_pre_census'])==5760 and len(ruler['ordered_predicted_pre_post_measured_pre_post_hex'])==5160
    assert ruler['source_fingerprint_unchanged'] and len(ruler['rejected_serial_argument_mutations'])==5
    end=table['FINAL'][1];assert end['before_after_bindings_equal'] and not end['collection_authorized'] and not end['research_complete']
    p=PREP/c['scope']['folder']
    return {'folder':c['scope']['folder'],'source':c['scope']['source'],
        'claim_sha256':digest(p/'claim.json'),'exit_sha256':digest(p/'exit.json'),'capture':read(p/'exit.json')['files'],
        'original_parent':first['parent_HEAD'],'original_execution_input_bindings':len(first['input_file_sha256']),'canonical_JSON_lines':4,
        'raw_STAGE_lines':2,'complete_record_references':{t:{'line':ln,'complete_original_row_sha256':h} for t,(ln,o,h) in table.items()},
        'family_q_support':c['family_q_support'],'captured_spill_address':address,'captured_spill_value_hex':spill['value_hex'],
        'all_original_raw_maps_credit_receipts_preserved':True,'not_reconstructed_unprinted_fullstores':True,
        'unprinted_installation_and_B1_scalars_not_recomputed':True,'no_old_native_execution':True}

def independent_witnesses(full,c):
    result={}
    for family,qaddresses in c['family_q_support'].items():
        outside=[]
        for ch in ('D','P','Q','X'):
            for address,value in full[ch]:
                if ch!='Q' or address not in qaddresses:outside.append({'channel':ch,'address':address,'captured_value':value})
        assert outside,('necessary family could match',family)
        result[family]=outside[0]
    return result

def next_tag(stream,tag):
    ln,t,o,h=next(stream);assert t==tag,(ln,t,tag);return o

def main():
    c=read(HERE/'contract.json');before=binding(c,True)
    proof=independent_proof(c);scope=independent_scope(c)
    candidate={'folder':HERE.relative_to(PREP).as_posix()+'/evidence','exit':0,'format':'compact'}
    stream=iter(records(candidate))
    initial=next_tag(stream,'INPUT_BINDING_BEFORE')
    assert initial['input_sha256']=={k:v for k,v in before['input_sha256'].items() if not k.startswith(HERE.relative_to(ROOT).as_posix()+'/evidence/')}
    assert initial['distinct_inputs']==2604 and initial['parent_tree_paths']==2600 and initial['parent_HEAD']==c['parent_commit']
    assert next_tag(stream,'SOURCE_INVARIANT_PROOF')==proof
    assert next_tag(stream,'SCOPED_SOURCE_EXCLUSION')==scope
    registry=sha256();counts=Counter();n=0
    for ln,t,o,h in records(c['plan']):
        if t!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert o['index']==n and o['complete_descriptor_alias_count']==1
        full=full_entries(o['full_four_store_entries'])
        assert sha256(wire(full)).hexdigest()==o['full_store_sha256'] and fingerprint(full)==o['original_fingerprint']
        assert o['complete_requested_input']['nominal_Q_reference_sha256']==c['reference_sha256']
        row=planned_row(c,ln,o,h,full,independent_witnesses(full,c))
        assert next_tag(stream,'PLANNED_SOURCE_EXCLUSION')==row
        registry.update(wire(row));counts[row['status']]+=1;n+=1;assert n<=c['guards']['max_planned']
    assert n==279158 and counts=={'EXACT_OLD_v46_v47_REFERENCE_PRESERVED':125366,'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX':153792}
    assert next_tag(stream,'INPUT_BINDING_AFTER')==initial
    final=summary(c,n,counts,sha256(wire(scope)).hexdigest(),registry.hexdigest())
    assert next_tag(stream,'FINAL')==final and next(stream,None) is None
    assert binding(c,True)==before
    emit('CHECK',{**final,'runtime_inputs':before['distinct_inputs'],'candidate_capture_bytes':(HERE/'evidence/stdout.log').stat().st_size,
        'independence':'Same main agent independent ordered address-list containment, regex captured-address parser and EOF keyed join; mechanical byte/JSON/Git/schema helpers copied; not expert/scientific approval'})
if __name__=='__main__':main()
