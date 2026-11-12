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
    names=['contract.json','candidate.py','execute.py','check_stored.py','completion_contract.json','complete_stored.py','execute_completion.py','check_stored_completed.py']
    names+=['evidence/'+n for n in ('claim.json','exit.json','stdout.log','stderr.log')]
    if checking:names+=['evidence_completed/'+n for n in ('claim.json','exit.json','stdout.log','stderr.log')]
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

def supplement(c):
    s=read(HERE/'completion_contract.json')
    for n,m in s['original_manifest'].items():
        p=HERE/n;assert p.stat().st_size==m['bytes'] and digest(p)==m['sha256']
    assert s['family_x_support']==[[0,2,t,0,0,cmd] for t in range(12) for cmd in range(5)]
    assert s['value_X']==4
    return s
def excluded(w,c,s):
    ch=w['channel'];a=w['address'];v=w['captured_value']
    return ch=='D' or (ch=='Q' and a not in c['family_q_support']) or (ch=='X' and (a not in s['family_x_support'] or v!=s['value_X']))
def joined(plan,hp,lp,old,ho,lo,idx):
    assert old['index']==plan['index']==idx and old['v55_line']==lp and old['complete_v55_row_sha256']==hp
    assert old['original_requested_input']==plan['complete_requested_input']
    assert old['original_descriptor_reference']==plan['first_descriptor_reference']
    assert old['original_v46_v47_reference']==plan['exact_old_native_v46_v47_reference']
    es=stores(plan['full_four_store_entries'])
    assert sha256(wire(es)).hexdigest()==old['full_store_sha256']==plan['full_store_sha256'] and fingerprint(es)==plan['original_fingerprint']
    return es

def main():
    c=read(HERE/'contract.json');s=supplement(c);before=binding(c);emit('INPUT_BINDING_BEFORE',before)
    original=(x for x in records({'folder':HERE.relative_to(PREP).as_posix()+'/evidence','exit':1,'format':'compact'}) if x[1]=='BOUND_DIAGNOSTIC_CALL_SOURCE_PROOF')
    ln,t,p,h=next(original);assert ln==s['original_proof']['line'] and h==s['original_proof']['sha256'] and next(original,None) is None
    emit('PRESERVED_COMPLETED_SOURCE_PROOF',{'original_proof':p,'original_line':ln,'original_line_sha256':h,'original_proof_reexecuted':False})
    emit('FINITE_X_SUPPORT_SUPPLEMENT',s)
    prefix=(x for x in records({'folder':HERE.relative_to(PREP).as_posix()+'/evidence','exit':1,'format':'compact'}) if x[1]=='DIAGNOSTIC_KEY_WITNESS_REF')
    oldrows=(x for x in records(c['reuse']) if x[1]=='PLANNED_SOURCE_EXCLUSION')
    plans=(x for x in records(c['plan']) if x[1]=='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY')
    pr=sha256();reg=sha256();channels=Counter();status=Counter();unresolved=[];n=0;newrows=0
    for n,(lo,t,old,ho) in enumerate(oldrows,1):
        idx=n-1;lp,tp,plan,hp=next(plans);es=joined(plan,hp,lp,old,ho,lo,idx)
        assert plan['complete_requested_input']['nominal_Q_reference_sha256']==c['reference_sha256']
        if idx<s['completed_prefix']:
            lc,tc,row,hc=next(prefix);w=row['actual_DQ_witness']
            assert row['index']==idx and row['v62_line']==lo and row['complete_original_v62_row_sha256']==ho
            assert row['v55_line']==lp and row['complete_original_v55_row_sha256']==hp and row['status']==old['status']
            assert w==old['exact_address_exclusion_witnesses'][c['original_v62_family']]
            assert w['channel'] in ('D','Q') and [w['address'],w['captured_value']] in es[w['channel']] and excluded(w,c,s)
            pr.update(wire(row));reg.update(wire(row));channels[w['channel']]+=1
            if n==s['completed_prefix']:
                assert next(prefix,None) is None and pr.hexdigest()==s['prefix_registry_sha256']
                emit('PRESERVED_PREFIX_RECEIPT',{'rows':n,'complete_original_row_registry_sha256':pr.hexdigest(),'reclassified':False})
        else:
            w=old['exact_address_exclusion_witnesses'][c['original_v62_family']]
            reuse=excluded(w,c,s) and [w['address'],w['captured_value']] in es[w['channel']]
            if not reuse:
                w=next(({'channel':ch,'address':a,'captured_value':v} for ch,rs in es.items() for a,v in rs if excluded({'channel':ch,'address':a,'captured_value':v},c,s)),None)
            if w is None:unresolved.append(idx)
            else:channels[w['channel']]+=1
            row={'index':idx,'v62_line':lo,'complete_original_v62_row_sha256':ho,'v55_line':lp,'complete_original_v55_row_sha256':hp,
                 'status':old['status'],'actual_fourstore_witness':w,'exact_old_v62_witness_reused':bool(reuse),
                 'scope':'ONLY_BOUND_DIAGNOSTIC35_FINITE_X_NECESSARY_SUPPORT',
                 'source_compatibility':'EXCLUDED_BY_ACTUAL_ADDRESS_VALUE' if w is not None else 'UNRESOLVED_NECESSARY_FAMILY_COMPATIBLE'}
            reg.update(wire(row));emit('COMPLETED_DIAGNOSTIC_KEY_REF',row);newrows+=1
        status[old['status']]+=1;assert n<=s['guards']['max_planned']
    assert next(plans,None) is None and n==279158 and newrows==164616
    assert status=={'EXACT_OLD_v46_v47_REFERENCE_PRESERVED':125366,'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX':153792}
    assert binding(c)==before;emit('INPUT_BINDING_AFTER',before)
    emit('FINAL',{'planned_inputs':n,'preserved_prefix_rows':114542,'new_completed_rows':newrows,'composite_registry_sha256':reg.hexdigest(),
        'witness_channels':dict(channels),'necessary_family_compatible_count':len(unresolved),'unresolved_indices':unresolved,
        'source_proof_sha256':sha256(wire(p)).hexdigest(),'supplement_sha256':sha256(wire(s)).hexdigest(),
        'scoped_class_methods':35,'other_fullsuite_methods_pending':745,'other_fullsuite_modules_pending':19,
        'status_counts':dict(status),'pending_before':153792,'pending_after':153792,'ALL_history_closed':False,
        'native_calibration_executed':0,'unprinted_fullstore_raw_scalar_reconstructed':False,
        'scientific_PASS':False,'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()
