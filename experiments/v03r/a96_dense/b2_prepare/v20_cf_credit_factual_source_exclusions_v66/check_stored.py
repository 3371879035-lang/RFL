"""Only original fullsuite three bound classes138; stdlib stored audit, no RFL execution."""
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
    spec=read(ROOT/c['v20']['input_spec']);frozen=read(ROOT/'experiments/v03r/a96_dense/f0_manifest.json')['sources']
    pars={}
    for line in (ROOT/c['v20']['full_stdout']).open('rb'):
        v=line.rstrip(b'\r\n')
        tag,value=v.split(b' ',1) if v.startswith((b'SEEDLESS_ENGINEERING_SUMMARY ',b'SEEDLESS_FACTUAL_ROUTING_SUMMARY ')) else v.split(b'=',1)
        obj=json.loads(value);assert json.dumps(obj,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()==value
        assert tag.decode() not in pars;pars[tag.decode()]=obj
    assert len(pars)==15
    suite=pars['FULL_PREPARATION_SUITE_V20']
    assert suite['input_hashes_before']==suite['input_hashes_after']==spec['input_file_hashes']
    assert len(spec['input_file_hashes'])==210 and suite['tests_run']==806 and len(suite['ordered_test_modules'])==21
    assert suite['failures']==suite['errors']==suite['skipped']==0
    allcases=[]
    for line in (ROOT/c['v20']['full_stderr']).read_text(encoding='utf8').splitlines():
        m=re.fullmatch(r'(test_[^ ]+) \(([^)]+)\) \.\.\. ok',line)
        if m:allcases.append(m[2])
    assert len(allcases)==len(set(allcases))==806
    cases=[x for x in allcases if x.split('.')[0] in c['modules']]
    assert cases==c['scoped_case_IDs'] and len(cases)==138
    provenance={};calls={};functions=0
    for name,pin in c['sources'].items():
        raw=(ROOT/name).read_bytes();h=sha256(raw).hexdigest();tree=ast.parse(raw)
        assert h==pin['sha256'] and ast_functions(tree)==pin['qualified_function_AST_sha256']
        functions+=len(pin['qualified_function_AST_sha256'])
        if name in spec['input_file_hashes']:assert h==spec['input_file_hashes'][name];provenance[name]='ORIGINAL_FULLSUITE210_BEFORE_AFTER'
        else:assert h==frozen[name];provenance[name]='ORIGINAL313_FREEZE_READY_LOAD_PARENT_BEFORE_AFTER'
        if Path(name).stem in c['modules']:
            for cl in tree.body:
                if not isinstance(cl,ast.ClassDef):continue
                for n in cl.body:
                    if isinstance(n,ast.FunctionDef):
                        key=Path(name).stem+'.'+cl.name+'.'+n.name
                        calls[key]=[ast.unparse(x) for x in ast.walk(n) if isinstance(x,ast.Call)]
    assert sorted(x for x in calls if x.split('.')[-1].startswith('test_'))==sorted(cases)
    assert c['family_q_support']==[[0,2,t,0,0,1,0,a] for t in range(12) for a in range(5)]
    assert c['family_d_wait_support']==[[0,2,t,0,0,1,0] for t in range(12)]
    assert c['family_x_support']==[[0,2,t,0,0,cmd] for t in range(12) for cmd in range(5)]
    return {'source_pins':c['sources'],'source_provenance':provenance,'qualified_AST_pins':functions,
        'all138_original_case_IDs':cases,'all806_original_case_IDs':allcases,
        'all_bound_class_setup_helper_method_call_expressions':calls,'per_method_scope_notes':c['per_method_scope_notes'],
        'necessary_family':c['necessary_family'],'source_reasoning':c['actual_context_reasoning'],'limits':c['scope_limits'],
        'kind':'ONLY_BOUND_ORIGINAL3CLASSES138_NECESSARY_INEQUALITY_NOT_FULLRAW_OR_ALL_HISTORY'}

def catalog_rows(c):
    rows={};meta={}
    for ln,tag,o,h in records(c['catalog']):
        if tag=='DECISION_CONTEXT':
            key=tuple(o['context']);assert key not in rows
            rows[key]=(o,ln,h)
        elif tag=='CATALOG_SUMMARY':meta=o
    assert len(rows)==13824 and meta['nominal_Q_reference_sha256']==c['reference_sha256']
    assert sha256(b''.join(wire(o) for o,ln,h in rows.values())).hexdigest()==meta['complete_decision_catalog_canonical_sha256']
    ordered=sorted(rows,key=lambda a:(a[2],a[3],a[4],a[0],a[1],a[5],a[6]))
    canonical='\n'.join(','.join(map(str,a))+'|'+','.join(str(x)+'='+v for x,v in rows[a][0]['q_row_hex']) for a in ordered)
    assert sha256(canonical.encode()).hexdigest()==c['reference_sha256']
    tied={a:set(o['optimal_actions']) for a,(o,ln,h) in rows.items() if len(o['optimal_actions'])>1}
    return rows,tied

def index_capture(c):
    folder=HERE/'evidence';cl=read(folder/'claim.json');ex=read(folder/'exit.json')
    assert ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items())
    for n,h in cl['inputs'].items():assert digest(HERE/n)==h
    for n,m in ex['files'].items():assert (folder/n).stat().st_size==m['bytes'] and digest(folder/n)==m['sha256']
    idx={};tags=Counter();special={};path=folder/'stdout.log'
    with path.open('rb') as f:
        ln=0
        while True:
            offset=f.tell();line=f.readline()
            if not line:break
            ln+=1;assert line.endswith(b'\n');tb,v=line.rstrip(b'\r\n').split(b'=',1)
            tag=tb.decode();obj=json.loads(v);assert wire(obj).rstrip(b'\n')==v;tags[tag]+=1
            if tag=='THREE_CLASS_KEY_REF':
                key=obj['index'];assert key not in idx;idx[key]=(offset,len(line),ln,sha256(line).hexdigest())
            else:assert tag not in special;special[tag]=obj
    return path,idx,dict(tags),special

def main():
    c=read(HERE/'contract.json');before=binding(c,True)
    cp,ci,tags,special=index_capture(c)
    # Reference labels are independently derived from complete captured original hex rows,
    # not from candidate tied support. Only original predicate, no new scientific tolerance.
    qr,_=catalog_rows(c);allowed={}
    for a,(o,ln,h) in qr.items():
        pairs=[(act,float.fromhex(v)) for act,v in o['q_row_hex']]
        best=max(v for act,v in pairs);opt=[act for act,v in pairs if v>=best-1e-12]
        assert opt==o['optimal_actions']
        if len(opt)>1:allowed[a]=opt
    def inside(ch,a,v):
        if ch=='P':return True
        if ch=='Q':return len(a)==8 and a[:2]==[0,2] and 0<=a[2]<12 and a[3:7]==[0,0,1,0] and 0<=a[7]<5
        if ch=='X':return len(a)==6 and a[:2]==[0,2] and 0<=a[2]<12 and a[3:5]==[0,0] and 0<=a[5]<5 and v==4
        wait=len(a)==7 and a[:2]==[0,2] and 0<=a[2]<12 and a[3:]==[0,0,1,0] and v==4
        return wait or v in allowed.get(tuple(a),())
    reg=sha256();channels=Counter();counts=Counter();unresolved=[];n=0
    with cp.open('rb') as cf:
        for lp,tp,plan,hp in records(c['plan']):
            if tp!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
            idx=plan['index'];assert idx==n
            offset,sz,lc,hc=ci.pop(idx);cf.seek(offset);b=cf.read(sz);assert sha256(b).hexdigest()==hc
            row=json.loads(b.rstrip(b'\r\n').split(b'=',1)[1])
            assert row['index']==idx and row['v55_line']==lp and row['complete_original_v55_row_sha256']==hp
            es=plan['full_four_store_entries'];assert set(es)=={'D','P','Q','X'}
            for ch,rs in es.items():
                keys=[tuple(a) if isinstance(a,list) else a for a,v in rs];assert len(keys)==len(set(keys))
            assert sha256(wire(stores(es))).hexdigest()==plan['full_store_sha256']==row['full_store_sha256_representation_only']
            assert fingerprint(stores(es))==plan['original_fingerprint']
            assert plan['complete_requested_input']['nominal_Q_reference_sha256']==c['reference_sha256']
            outs=[(ch,a,v) for ch,rs in es.items() for a,v in rs if not inside(ch,a,v)]
            w=row['concrete_address_value_witness']
            if w is None:assert not outs;unresolved.append(idx)
            else:assert (w['channel'],w['address'],w['captured_value']) in outs;channels[w['channel']]+=1
            assert row['compatibility']==('EXCLUDED_NECESSARY_SUPPORT' if outs else 'UNRESOLVED_NECESSARY_FAMILY_COMPATIBLE')
            status='EXACT_OLD_v46_v47_REFERENCE_PRESERVED' if plan['exact_old_native_v46_v47_reference'] is not None else 'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX'
            assert row['status']==status;counts[status]+=1;reg.update(wire(row));n+=1
    assert not ci and n==279158
    p=proof(c);assert special['BOUND_THREE_CLASS_CALL_SOURCE_PROOF']==p
    final=special['FINAL']
    assert special['INPUT_BINDING_BEFORE']==special['INPUT_BINDING_AFTER'] and special['INPUT_BINDING_BEFORE']['distinct_inputs']==2696
    assert final['source_proof_sha256']==sha256(wire(p)).hexdigest() and final['witness_registry_sha256']==reg.hexdigest()
    assert final['witness_channels']==dict(channels) and final['unresolved_indices']==unresolved and final['necessary_family_compatible_count']==len(unresolved)
    assert final['status_counts']==dict(counts) and final['pending_after']==153792 and final['native_calibration_executed']==0 and not final['ALL_history_closed']
    assert tags=={'INPUT_BINDING_BEFORE':1,'BOUND_THREE_CLASS_CALL_SOURCE_PROOF':1,'CAPTURED_REFERENCE_NECESSARY_TIE_SUPPORT':1,'THREE_CLASS_KEY_REF':279158,'INPUT_BINDING_AFTER':1,'FINAL':1}
    assert binding(c,True)==before
    emit('CHECK',{'result':'ONLY_BOUND3_CLASSES138_FULL_STORED_EOF_KEYEDJOIN_CHECKED_NOT_SCIENCE',
        'final':final,'complete_candidate_rows':sum(tags.values()),'source_files':20,'qualified_AST_pins':p['qualified_AST_pins'],
        'complete_old_reference_contexts_checked':len(qr),'original806_case_IDs_retained':len(p['all806_original_case_IDs']),
        'distinct_checker_inputs':before['distinct_inputs'],'independence':'IMPLEMENTATION_ONLY; candidate set/stream versus EOF binary offset/keyedjoin/ordered entries and original float predicate; shared mechanical stdlib byteJSONGitASTproof',
        'RFL_candidate_oldchecker_solver_main_imported_or_executed':False})
if __name__=='__main__':main()
