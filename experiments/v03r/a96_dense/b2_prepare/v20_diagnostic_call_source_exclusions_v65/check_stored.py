"""Only original bound DiagnosticSourceTests35; stdlib stored audit, no RFL execution."""
import ast
from collections import Counter
from hashlib import sha1, sha256
import json
from pathlib import Path
import re
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
    assert OUTPUT_BYTES<=400000000,'output engineering guard'
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
    return {'parent_HEAD':head,'distinct_inputs':len(out),'input_sha256':out}

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
def proof(c):
    spec=read(ROOT/c['v20']['input_spec'])
    frozen=read(ROOT/'experiments/v03r/a96_dense/f0_manifest.json')['sources']
    pars={}
    for ln,line in enumerate((ROOT/c['v20']['full_stdout']).open('rb'),1):
        val=line.rstrip(b'\r\n')
        if val.startswith((b'SEEDLESS_ENGINEERING_SUMMARY ',b'SEEDLESS_FACTUAL_ROUTING_SUMMARY ')):tag,value=val.split(b' ',1)
        else:tag,value=val.split(b'=',1)
        obj=json.loads(value);assert json.dumps(obj,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()==value
        assert tag.decode() not in pars;pars[tag.decode()]=obj
    assert len(pars)==15
    suite=pars['FULL_PREPARATION_SUITE_V20']
    assert suite['input_hashes_before']==suite['input_hashes_after']==spec['input_file_hashes']
    assert len(spec['input_file_hashes'])==210 and suite['tests_run']==806 and len(suite['ordered_test_modules'])==21
    assert suite['failures']==suite['errors']==suite['skipped']==0
    observed=[]
    for line in (ROOT/c['v20']['full_stderr']).read_text(encoding='utf8').splitlines():
        m=re.fullmatch(r'(test_[^ ]+) \(([^)]+)\) \.\.\. ok',line)
        if m:observed.append(m[2])
    assert len(observed)==len(set(observed))==806
    cases=[x for x in observed if x.startswith('test_diagnostic_source_candidate.DiagnosticSourceTests.')]
    assert cases==c['scoped_case_IDs'] and len(cases)==35
    provenance={};functions=0
    for name,pin in c['sources'].items():
        raw=(ROOT/name).read_bytes();h=sha256(raw).hexdigest();assert h==pin['sha256']
        assert ast_functions(ast.parse(raw))==pin['qualified_function_AST_sha256']
        functions+=len(pin['qualified_function_AST_sha256'])
        if name in spec['input_file_hashes']:assert h==spec['input_file_hashes'][name];provenance[name]='ORIGINAL_FULLSUITE210_ACTUAL_BEFORE_AFTER'
        else:assert name in frozen and h==frozen[name];provenance[name]='ORIGINAL313_FREEZE_READY_LOAD_PARENT_BEFORE_AFTER'
    cls=next(x for x in ast.parse((PREP/'test_diagnostic_source_candidate.py').read_bytes()).body if isinstance(x,ast.ClassDef))
    functions_by_name={n.name:n for n in cls.body if isinstance(n,ast.FunctionDef)}
    assert sorted(n for n in functions_by_name if n.startswith('test_'))==sorted(x.split('.')[-1] for x in cases)
    assert c['family_q_support']==[[0,2,t,0,0,1,0,a] for t in range(12) for a in range(5)]
    calls={n:[ast.unparse(x) for x in ast.walk(node) if isinstance(x,ast.Call)] for n,node in functions_by_name.items()}
    return {'source_pins':c['sources'],'source_provenance':provenance,'qualified_AST_pins':functions,
        'all35_original_case_IDs':cases,'all806_original_case_IDs':observed,
        'all_bound_class_helper_and_method_call_expressions':calls,'per_method_scope_notes':c['per_method_scope_notes'],
        'necessary_family':c['necessary_family'],'q_support':c['family_q_support'],
        'source_reasoning':c['actual_context_reasoning'],'limits':c['scope_limits'],
        'kind':'NECESSARY_INPUT_INEQUALITY_ONLY_NOT_RECONSTRUCTED_NATIVE_RAW_OR_ALL_HISTORY'}

def index_capture(spec,tag_wanted):
    # Entire original EOF, with genuine binary tell/readline offsets, no CRLF guessing.
    spec=spec.copy();folder=PREP/spec['folder'];ex=read(folder/'exit.json');cl=read(folder/'claim.json')
    assert ex['native_child_exit_code']==spec['exit'] and all(ex[k]==v for k,v in cl.items())
    for name,h in cl['inputs'].items():assert digest(folder.parent/name)==h
    for name,m in ex['files'].items():assert (folder/name).stat().st_size==m['bytes'] and digest(folder/name)==m['sha256']
    if 'sha256' in spec:assert ex['files']['stdout.log']['sha256']==spec['sha256']
    idx={};counts=Counter();path=folder/'stdout.log'
    with path.open('rb') as f:
        ln=0
        while True:
            offset=f.tell();line=f.readline()
            if not line:break
            ln+=1;assert line.endswith(b'\n');tb,v=line.rstrip(b'\r\n').split(b'=',1)
            tag=tb.decode();obj=json.loads(v);assert wire(obj).rstrip(b'\n')==v
            counts[tag]+=1
            if tag==tag_wanted:
                key=obj['index'];assert key not in idx
                idx[key]=(offset,len(line),ln,sha256(line).hexdigest())
    return path,idx,dict(counts)

def main():
    c=read(HERE/'contract.json');before=binding(c,True)
    # Candidate is read completely to EOF before old v62 indexing, then old v55 keyed join.
    cp,ci,ct=index_capture({'folder':HERE.relative_to(PREP).as_posix()+'/evidence','exit':0},'DIAGNOSTIC_KEY_WITNESS_REF')
    vp,vi,vt=index_capture(c['reuse'],'PLANNED_SOURCE_EXCLUSION')
    p=proof(c);reg=sha256();status=Counter();channels=Counter();n=0
    with cp.open('rb') as cf,vp.open('rb') as vf:
        for lp,tp,plan,hp in records(c['plan']):
            if tp!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
            idx=plan['index'];assert idx==n
            co,sz,lc,hc=ci.pop(idx);cf.seek(co);cb=cf.read(sz);assert sha256(cb).hexdigest()==hc
            row=json.loads(cb.rstrip(b'\r\n').split(b'=',1)[1])
            vo,vsz,lv,hv=vi.pop(idx);vf.seek(vo);vb=vf.read(vsz);assert sha256(vb).hexdigest()==hv
            old=json.loads(vb.rstrip(b'\r\n').split(b'=',1)[1])
            assert row['v62_line']==lv and row['complete_original_v62_row_sha256']==hv
            assert row['v55_line']==lp and row['complete_original_v55_row_sha256']==hp
            assert old['v55_line']==lp and old['complete_v55_row_sha256']==hp and old['index']==idx
            assert old['original_requested_input']==plan['complete_requested_input']
            assert old['original_descriptor_reference']==plan['first_descriptor_reference']
            assert old['original_v46_v47_reference']==plan['exact_old_native_v46_v47_reference']
            entries=plan['full_four_store_entries'];assert set(entries)=={'D','P','Q','X'}
            for ch,es in entries.items():
                addrs=[tuple(a) if isinstance(a,list) else a for a,v in es];assert len(set(addrs))==len(addrs)
            assert sha256(wire(stores(entries))).hexdigest()==old['full_store_sha256']==plan['full_store_sha256']
            assert fingerprint(stores(entries))==plan['original_fingerprint']
            witness=old['exact_address_exclusion_witnesses'][c['original_v62_family']]
            assert row['actual_DQ_witness']==witness
            # Independent ordered-entry witness existence and address predicate, no candidate set/classifier.
            actual=[(ch,a,v) for ch,es in entries.items() for a,v in es if ch==witness['channel'] and a==witness['address'] and v==witness['captured_value']]
            assert len(actual)==1 and witness['channel'] in ('D','Q')
            if witness['channel']=='Q':
                a=witness['address'];assert not (len(a)==8 and a[:2]==[0,2] and 0<=a[2]<12 and a[3:7]==[0,0,1,0] and 0<=a[7]<5)
            assert row['status']==old['status']
            assert plan['complete_requested_input']['nominal_Q_reference_sha256']==c['reference_sha256']
            channels[witness['channel']]+=1;status[row['status']]+=1;reg.update(wire(row));n+=1
    assert not ci and not vi and n==279158
    final=None;proof_seen=None;old_before=None;old_after=None
    for ln,tag,o,h in records({'folder':HERE.relative_to(PREP).as_posix()+'/evidence','exit':0,'format':'compact'}):
        if tag=='FINAL':assert final is None;final=o
        elif tag=='BOUND_DIAGNOSTIC_CALL_SOURCE_PROOF':assert proof_seen is None;proof_seen=o
        elif tag=='INPUT_BINDING_BEFORE':old_before=o
        elif tag=='INPUT_BINDING_AFTER':old_after=o
    assert proof_seen==p and old_before==old_after and old_before['distinct_inputs']==2673
    assert final['source_proof_sha256']==sha256(wire(p)).hexdigest()
    assert final['witness_registry_sha256']==reg.hexdigest() and final['witness_channels']==dict(channels)
    assert final['status_counts']==dict(status) and final['pending_after']==153792
    assert ct=={'INPUT_BINDING_BEFORE':1,'BOUND_DIAGNOSTIC_CALL_SOURCE_PROOF':1,'DIAGNOSTIC_KEY_WITNESS_REF':279158,'INPUT_BINDING_AFTER':1,'FINAL':1}
    assert final['bound_necessary_family_compatible']==0 and final['native_calibration_executed']==0 and final['ALL_history_closed'] is False
    assert binding(c,True)==before
    emit('CHECK',{'result':'FULL_STORED_EOF_KEYED_JOIN_AND_BOUND_SOURCE_CHECKED_NOT_SCIENCE_PASS',
        'final':final,'complete_candidate_rows':sum(ct.values()),'source_files':len(c['sources']),
        'qualified_AST_pins':p['qualified_AST_pins'],'distinct_checker_inputs':before['distinct_inputs'],
        'independence':'IMPLEMENTATION_ONLY_NOT_EXPERT_OR_SCIENCE; shared mechanical byteJSONGitASTproof',
        'old_RFL_candidate_checker_imported_or_executed':False,'all_original806_case_IDs_retained':len(p['all806_original_case_IDs'])})
if __name__=='__main__':main()
