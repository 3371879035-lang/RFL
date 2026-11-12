"""Source-bound necessary store-address exclusions. No RFL imports or execution."""
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
def source_proof(c):
    total=0
    for path,pin in c['sources'].items():
        raw=(ROOT/path).read_bytes();assert sha256(raw).hexdigest()==pin['sha256']
        found={}
        for node in ast.walk(ast.parse(raw)):
            if isinstance(node,ast.FunctionDef) and node.name in pin['functions']:
                found.setdefault(node.name,[]).append(sha256(ast.dump(node,include_attributes=False).encode()).hexdigest())
        assert found==pin['functions'],path
        total+=sum(map(len,found.values()))
    old=read(PREP/'mechanism_v25/contract.json')['fixed_defect_owner']
    owner=old['state']+[old['z'],old['m']];assert owner==c['v25_owner']
    tree=ast.parse((PREP/'mechanism_v25/candidate_corrected.py').read_bytes())
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='State']
    assert all([ast.literal_eval(a) for a in n.args]==owner[:5] for n in calls)
    tree=ast.parse((PREP/'controller_service_v34/candidate.py').read_bytes())
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='learned_rollout' for n in ast.walk(tree))
    return {'source_count':len(c['sources']),'function_AST_pins':total,'sources':c['sources'],
        'owner':owner,'reasoning':c['source_invariant_reasoning'],'scope_limits':c['scope_limits'],
        'proof_kind':'NECESSARY_STORE_ADDRESS_SUPPORT_NOT_COMPLETE_OLD_MEASUREMENT_INDEX'}
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
def forbidden(store,family,owner):
    for ch in ('D','P','Q','X'):
        for a,v in store[ch]:
            key=tuple(a) if isinstance(a,list) else a
            allowed=(family=='EMPTY_D_AND_Q' and ch in {'P','X'}) or (
                family=='V25_D_ONLY' and ch=='D' and key==tuple(owner)) or (
                family=='V25_Q_ONLY' and ch=='Q' and key in {tuple(owner)+(i,) for i in range(5)})
            if not allowed:return {'channel':ch,'address':a,'captured_value':v}
    raise AssertionError(('necessary family could match',family))
def main():
    c=read(HERE/'contract.json');before=binding(c);emit('INPUT_BINDING_BEFORE',before)
    emit('SOURCE_INVARIANT_PROOF',source_proof(c));scope=sha256();snapshots=0
    for spec in c['scope']:
        for ln,tag,obj,h in old_records(spec,c):
            if tag=='AUDIT_SCOPE':
                scope.update(wire(obj));snapshots+=obj['complete_captured_snapshots_with_empty_DQ'];emit('SCOPED_SOURCE_EXCLUSION',obj)
    registry=sha256();counts=Counter();n=0
    for ln,tag,o,h in old_records(c['plan']):
        if tag!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert o['index']==n and o['complete_descriptor_alias_count']==1
        state=stores(o['full_four_store_entries'])
        assert sha256(wire(state)).hexdigest()==o['full_store_sha256']
        assert fingerprint(state)==o['original_fingerprint']
        requested=o['complete_requested_input'];assert requested['nominal_Q_reference_sha256']==c['reference_sha256']
        witnesses={f:forbidden(state,f,c['v25_owner']) for f in ('EMPTY_D_AND_Q','V25_D_ONLY','V25_Q_ONLY')}
        prior=o['exact_old_native_v46_v47_reference']
        status='EXACT_OLD_v46_v47_REFERENCE_PRESERVED' if prior is not None else 'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX'
        row={'index':n,'v55_capture':c['plan']['folder'],'v55_line':ln,'complete_v55_row_sha256':h,
            'original_requested_input':requested,'original_descriptor_reference':o['first_descriptor_reference'],
            'original_v46_v47_reference':prior,'full_store_sha256':o['full_store_sha256'],
            'exact_address_exclusion_witnesses':witnesses,'status':status,
            'all_other_history_audit_pending':True,'native_execution_authorized':False}
        registry.update(wire(row));counts[status]+=1;emit('PLANNED_SOURCE_EXCLUSION',row);n+=1
        assert n<=c['guards']['max_planned']
    assert n==c['expected']['planned']
    assert counts['EXACT_OLD_v46_v47_REFERENCE_PRESERVED']==c['expected']['old_v46_v47']
    assert counts['PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX']==c['expected']['pending']
    after=binding(c);assert after==before;emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'planned_inputs':n,'scope_entry_captures':len(c['scope']),'captured_DQ_empty_snapshots':snapshots,
        'scope_registry_sha256':scope.hexdigest(),'address_exclusion_registry_sha256':registry.hexdigest(),
        'status_counts':dict(counts),'scope_compatible_planned_inputs':0,'pending_before':c['expected']['pending'],
        'pending_after':c['expected']['pending'],'missing_API_failure_raw_preserved':True,
        'all_history_closed':False,'native_calibration_executed':0,'native_launch_authorized':False,
        'scientific_PASS':False,'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()

