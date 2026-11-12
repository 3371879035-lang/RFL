"""Independent ordered literal-support checker, not expert or scientific approval."""
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
def old_records(spec,c=None):
    p=PREP/spec['folder'];cl=read(p/'claim.json');ex=read(p/'exit.json')
    assert ex['native_child_exit_code']==spec['exit'] and all(ex[k]==v for k,v in cl.items())
    for n,h in cl['inputs'].items():assert digest(p.parent/n)==h,(p,n)
    for n,info in ex['files'].items():
        assert {'bytes':(p/n).stat().st_size,'sha256':digest(p/n)}==info
    if 'files' in spec:assert ex['files']==spec['files']
    if 'sha256' in spec:assert ex['files']['stdout.log']['sha256']==spec['sha256']
    tags=Counter();start=None;ends=[];ln=0;states=0
    for ln,line in enumerate((p/'stdout.log').open('rb'),1):
        assert line.endswith(b'\n')
        t,v=line.rstrip(b'\r\n').split(b'=',1);tag=t.decode();tags[tag]+=1
        if tag=='STAGE':
            assert v==b'matched_owned_P_credit_and_independent_installation'
            obj=v.decode()
        else:
            obj=json.loads(v)
            kw={'separators':(',',':')} if spec['format']=='compact' else {}
            assert json.dumps(obj,sort_keys=True,ensure_ascii=True,allow_nan=False,**kw).encode()==v,(p,ln)
            if tag in ('INPUT_BINDING','INPUT_BINDING_BEFORE'):assert start is None;start=obj
            if tag=='INPUT_BINDING_AFTER':ends.append(obj)
            if c is not None and spec['family']=='EMPTY_D_AND_Q':
                stack=[obj]
                while stack:
                    cur=stack.pop()
                    if isinstance(cur,dict):
                        if {'q','decision','process','controller'}<=set(cur):
                            assert cur['q']==cur['decision']==[],(p,ln,'captured nonempty D/Q')
                            states+=1
                        stack.extend(cur.values())
                    elif isinstance(cur,list):stack.extend(cur)
        yield ln,tag,obj,sha256(line).hexdigest()
    if 'tags' in spec:assert dict(tags)==spec['tags']
    if ends:assert ends==[start]
    if c is not None:
        if start is not None:
            pins=start.get('input_sha256',start.get('input_file_sha256',{}))
            for path,pin in c['sources'].items():
                if path.startswith('src/') or path.endswith('factual_event_candidate.py') or path==spec['source']:
                    assert pins[path]==pin['sha256'],(p,path)
        else:
            assert spec['family']=='PRE_MAIN_FAILURE_NO_ROOT' and ln==0
            assert b"has no attribute 'ExogenousEpisode'" in (p/'stderr.log').read_bytes()
        yield None,'AUDIT_SCOPE',{'folder':spec['folder'],'source':spec['source'],'family':spec['family'],
            'claim_sha256':digest(p/'claim.json'),'exit_sha256':digest(p/'exit.json'),'capture':ex['files'],
            'original_native_exit':spec['exit'],'canonical_lines':ln,'tags':dict(tags),
            'complete_captured_snapshots_with_empty_DQ':states,'raw_missing':spec['raw_missing'],
            'no_old_execution':True,'not_complete_raw_input_index':True},None
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

def independent_proof(c):
    functions=0
    for name,pin in c['sources'].items():
        b=(ROOT/name).read_bytes();assert digest(ROOT/name)==pin['sha256']
        nodes=list(ast.walk(ast.parse(b)))
        observed={key:[sha256(ast.dump(x,include_attributes=False).encode()).hexdigest() for x in nodes
            if isinstance(x,ast.FunctionDef) and x.name==key] for key in pin['functions']}
        assert observed==pin['functions'];functions+=sum(len(x) for x in observed.values())
    old=read(PREP/'mechanism_v25/contract.json');o=old['fixed_defect_owner']
    owner=o['state']+[o['z'],o['m']];assert owner==c['v25_owner']
    entry_main=next(x for x in ast.parse((PREP/'mechanism_v25/candidate_corrected.py').read_bytes()).body
              if isinstance(x,ast.FunctionDef) and x.name=='main')
    literal_states=[x for x in ast.walk(entry_main) if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=='State']
    assert len(literal_states)==2
    for call in literal_states:assert [ast.literal_eval(x) for x in call.args]==owner[:5]
    v34=(PREP/'controller_service_v34/candidate.py').read_text(encoding='utf8')
    assert "patch.object(K,'rollout'" in v34 or 'patch.object(K, "rollout"' in v34
    assert "side_effect=AssertionError" in v34 and "no learner episodes" in v34
    return owner,functions
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
def outside_literal_support(store,owner):
    constraints={'EMPTY_D_AND_Q':{'D':[],'Q':[]},
        'V25_D_ONLY':{'D':[owner],'P':[],'Q':[],'X':[]},
        'V25_Q_ONLY':{'D':[],'P':[],'Q':[owner+[i] for i in range(5)],'X':[]}}
    result={}
    for name,allowed in constraints.items():
        candidates=[]
        for channel in ('D','P','Q','X'):
            for address,value in store[channel]:
                if channel in allowed and address not in allowed[channel]:
                    candidates.append({'channel':channel,'address':address,'captured_value':value})
        assert candidates,('old input family not excluded',name)
        result[name]=candidates[0]
    return result
def next_tag(stream,tag):
    ln,t,o,h=next(stream);assert t==tag,(ln,t,tag);return o
def main():
    c=read(HERE/'contract.json');before=binding(c,True)
    owner,functions=independent_proof(c)
    candidate={'folder':HERE.relative_to(PREP).as_posix()+'/evidence','exit':0,'format':'compact'}
    stream=iter(old_records(candidate))
    original=next_tag(stream,'INPUT_BINDING_BEFORE')
    assert original['input_sha256']=={k:v for k,v in before['input_sha256'].items() if not k.startswith(HERE.relative_to(ROOT).as_posix()+'/evidence/')}
    proof=next_tag(stream,'SOURCE_INVARIANT_PROOF')
    assert proof=={'source_count':len(c['sources']),'function_AST_pins':functions,'sources':c['sources'],
        'owner':owner,'reasoning':c['source_invariant_reasoning'],'scope_limits':c['scope_limits'],
        'proof_kind':'NECESSARY_STORE_ADDRESS_SUPPORT_NOT_COMPLETE_OLD_MEASUREMENT_INDEX'}
    scopehash=sha256();snapshots=0
    for spec in c['scope']:
        # Mechanical byte/JSON/receipt parser is copied, semantic snapshot census below is independent.
        oldstream=list(old_records(spec))
        tags=Counter(t for _,t,_,_ in oldstream);assert dict(tags)==spec['tags']
        starts=[o for _,t,o,_ in oldstream if t in ('INPUT_BINDING','INPUT_BINDING_BEFORE')]
        ends=[o for _,t,o,_ in oldstream if t=='INPUT_BINDING_AFTER'];states=0
        if starts:
            assert len(starts)==1
            pins=starts[0].get('input_sha256',starts[0].get('input_file_sha256'))
            for name,pin in c['sources'].items():
                if name.startswith('src/') or name.endswith('factual_event_candidate.py') or name==spec['source']:
                    assert pins[name]==pin['sha256']
            if ends:assert ends==starts
        else:
            assert spec['family']=='PRE_MAIN_FAILURE_NO_ROOT' and not oldstream
            assert b"has no attribute 'ExogenousEpisode'" in (PREP/spec['folder']/'stderr.log').read_bytes()
        if spec['family']=='EMPTY_D_AND_Q':
            def visit(value):
                if isinstance(value,dict):
                    if all(k in value for k in ('q','decision','process','controller')):
                        assert not value['q'] and not value['decision']
                        yield 1
                    for child in value.values():yield from visit(child)
                elif isinstance(value,list):
                    for child in value:yield from visit(child)
            states=sum(sum(visit(o)) for _,_,o,_ in oldstream)
        p=PREP/spec['folder'];obj={'folder':spec['folder'],'source':spec['source'],'family':spec['family'],
            'claim_sha256':digest(p/'claim.json'),'exit_sha256':digest(p/'exit.json'),'capture':read(p/'exit.json')['files'],
            'original_native_exit':spec['exit'],'canonical_lines':len(oldstream),'tags':dict(tags),
            'complete_captured_snapshots_with_empty_DQ':states,'raw_missing':spec['raw_missing'],
            'no_old_execution':True,'not_complete_raw_input_index':True}
        assert next_tag(stream,'SCOPED_SOURCE_EXCLUSION')==obj
        scopehash.update(wire(obj));snapshots+=states
    reg=sha256();counts=Counter();n=0
    for ln,t,o,h in old_records(c['plan']):
        if t!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert o['index']==n and o['complete_descriptor_alias_count']==1
        full=full_entries(o['full_four_store_entries'])
        assert fingerprint(full)==o['original_fingerprint'] and sha256(wire(full)).hexdigest()==o['full_store_sha256']
        assert o['complete_requested_input']['nominal_Q_reference_sha256']==c['reference_sha256']
        status='EXACT_OLD_v46_v47_REFERENCE_PRESERVED' if o['exact_old_native_v46_v47_reference'] is not None else 'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX'
        row={'index':n,'v55_capture':c['plan']['folder'],'v55_line':ln,'complete_v55_row_sha256':h,
            'original_requested_input':o['complete_requested_input'],'original_descriptor_reference':o['first_descriptor_reference'],
            'original_v46_v47_reference':o['exact_old_native_v46_v47_reference'],'full_store_sha256':o['full_store_sha256'],
            'exact_address_exclusion_witnesses':outside_literal_support(full,owner),'status':status,
            'all_other_history_audit_pending':True,'native_execution_authorized':False}
        assert next_tag(stream,'PLANNED_SOURCE_EXCLUSION')==row
        reg.update(wire(row));counts[status]+=1;n+=1;assert n<=c['guards']['max_planned']
    assert n==c['expected']['planned']
    assert counts['EXACT_OLD_v46_v47_REFERENCE_PRESERVED']==c['expected']['old_v46_v47']
    assert counts['PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX']==c['expected']['pending']
    assert next_tag(stream,'INPUT_BINDING_AFTER')==original
    summary={'planned_inputs':n,'scope_entry_captures':len(c['scope']),'captured_DQ_empty_snapshots':snapshots,
        'scope_registry_sha256':scopehash.hexdigest(),'address_exclusion_registry_sha256':reg.hexdigest(),
        'status_counts':dict(counts),'scope_compatible_planned_inputs':0,'pending_before':c['expected']['pending'],
        'pending_after':c['expected']['pending'],'missing_API_failure_raw_preserved':True,
        'all_history_closed':False,'native_calibration_executed':0,'native_launch_authorized':False,
        'scientific_PASS':False,'collection_authorized':False,'research_complete':False}
    assert next_tag(stream,'FINAL')==summary
    assert next(stream,None) is None
    assert binding(c,True)==before
    emit('CHECK',{**summary,'runtime_inputs':before['distinct_inputs'],
        'candidate_capture_bytes':(HERE/'evidence/stdout.log').stat().st_size,
        'independence':'Same main agent independent ordered address-list containment and EOF keyed join; shared mechanical byte/JSON/Git helpers; not expert approval'})
if __name__=='__main__':main()

