"""Only original fullsuite five bound classes183; stdlib stored audit, no RFL execution."""
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
    assert OUTPUT_BYTES<=5000000,'output engineering guard'
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

def source_constraint(c,oldproof):
    assert oldproof['source_pins']==c['sources'] and oldproof['all183_original_case_IDs']==c['scoped_case_IDs']
    assert sha256(wire(oldproof)).hexdigest()==c['prior_proof_sha256']
    spec=read(ROOT/c['v20']['input_spec']);frozen=read(ROOT/'experiments/v03r/a96_dense/f0_manifest.json')['sources']
    functions=0;inventory={};selected={};q_calls={}
    def find(tree,key):
        bits=key.split('.');node=tree
        for bit in bits:node=next(n for n in node.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name==bit)
        return node
    for name,pin in c['sources'].items():
        raw=(ROOT/name).read_bytes();tree=ast.parse(raw);h=sha256(raw).hexdigest()
        assert h==pin['sha256'] and ast_functions(tree)==pin['qualified_function_AST_sha256'];functions+=len(pin['qualified_function_AST_sha256'])
        provenance=oldproof['source_provenance'][name]
        assert h==(spec['input_file_hashes'][name] if provenance=='ORIGINAL_FULLSUITE210_BEFORE_AFTER' else frozen[name])
        if Path(name).stem in c['modules']:
            q_calls[name]=[ast.unparse(x) for x in ast.walk(tree) if isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=='QAddress']
            for cl in tree.body:
                if isinstance(cl,ast.ClassDef):
                    for n in cl.body:
                        if isinstance(n,ast.FunctionDef):
                            key=Path(name).stem+'.'+cl.name+'.'+n.name
                            inventory[key]=[ast.unparse(x) for x in ast.walk(n) if isinstance(x,ast.Call) and (isinstance(x.func,ast.Name) and x.func.id=='Edit' or isinstance(x.func,ast.Attribute) and x.func.attr=='apply_transaction')]
        picks={'experiments/v03r/a96_dense/b2_prepare/test_pre_census_source_candidate.py':['PreCensusTests.test_actual_P_Consult_uses_proposal_not_option_in_force'],
               'experiments/v03r/a96_dense/b2_prepare/test_diagnostic_source_candidate.py':c['external_fixture_helpers'],
               'src/rfl_rebuild/learner/store.py':['LearnerPersistentState.__init__','LearnerPersistentState.clone','LearnerPersistentState.apply_transaction'],
               'experiments/v03r/a96_dense/b2_prepare/counterfactual_source_candidate.py':['prepare_owned_l2_source','_checked'],
               'experiments/v03r/a96_dense/b2_prepare/pre_census_source_candidate.py':['_seal']}
        for key in picks.get(name,[]):selected[name+':'+key]=ast.unparse(find(tree,key))
    assert functions==641 and len(inventory)==199
    assert q_calls['experiments/v03r/a96_dense/b2_prepare/test_pre_census_source_candidate.py']==['QAddress(s, 2, 0, K.WAIT)']
    assert q_calls['experiments/v03r/a96_dense/b2_prepare/test_single_map_source_candidate.py']==['QAddress(s, 1, 0, K.WAIT)']
    assert all(not rows for name,rows in q_calls.items() if Path(name).stem not in ('test_pre_census_source_candidate','test_single_map_source_candidate'))
    key='test_pre_census_source_candidate.PreCensusTests.test_actual_P_Consult_uses_proposal_not_option_in_force'
    assert inventory[key]==['state.apply_transaction(edits, q_reference=self.fixture.q)','Edit(PROCESS, 1, 2)','Edit(Q, QAddress(s, 2, 0, K.WAIT), max(self.fixture.q.row(s, 2, 0).values()) + 1.0)']
    body=selected['experiments/v03r/a96_dense/b2_prepare/test_pre_census_source_candidate.py:PreCensusTests.test_actual_P_Consult_uses_proposal_not_option_in_force']
    assert 'edits = [Edit(PROCESS, 1, 2)]' in body and 'edits.append(Edit(Q, QAddress(s, 2, 0, K.WAIT)' in body
    assert body.count('state.apply_transaction(')==1 and body.index('state.apply_transaction(')<body.index('self.fixture.source(state)')
    assert "state.apply_transaction([Edit(PROCESS" not in body
    return {'original_v67_proof_sha256':c['prior_proof_sha256'],'source_files':41,'qualified_AST_pins':functions,
      'original806_case_IDs_retained':oldproof['all806_original_case_IDs'],'scoped183_case_IDs':c['scoped_case_IDs'],
      'all199_explicit_transaction_and_Edit_call_inventory':inventory,'actual_explicit_QAddress_calls':q_calls,
      'complete_selected_constructor_clone_readonly_helper_AST_source':selected,'necessary_constraint':c['necessary_constraint'],
      'complete_branch_reasoning':c['source_reasoning'],'limits':c['limits']}

def capture_index():
    cl=read(HERE/'evidence/claim.json');ex=read(HERE/'evidence/exit.json')
    assert ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items())
    for name,h in cl['inputs'].items():assert digest(HERE/name)==h
    for name,m in ex['files'].items():assert {'bytes':(HERE/'evidence'/name).stat().st_size,'sha256':digest(HERE/'evidence'/name)}==m
    idx={};special={};tags=Counter();path=HERE/'evidence/stdout.log'
    with path.open('rb') as f:
        ln=0
        while True:
            off=f.tell();b=f.readline()
            if not b:break
            ln+=1;assert b.endswith(b'\n');tb,v=b.rstrip(b'\r\n').split(b'=',1);o=json.loads(v)
            assert wire(o).rstrip(b'\n')==v;tag=tb.decode();tags[tag]+=1
            if tag=='EIGHT_INPUT_REFINEMENT':assert o['index'] not in idx;idx[o['index']]=(off,len(b),ln,sha256(b).hexdigest())
            else:assert tag not in special;special[tag]=o
    return path,idx,special,dict(tags)
def main():
    c=read(HERE/'contract.json');before=binding(c,True)
    path,ci,new,tags=capture_index();assert sorted(ci)==c['original_unresolved']
    original={};missing={};old={};reg=sha256();status=Counter();n=0
    # Independent full-EOF original row index, no old witness classification.
    for ln,tag,row,h in records(c['prior']):
        if tag=='FIVE_CLASS_KEY_REF':
            assert row['index']==n;reg.update(wire(row));status[row['status']]+=1
            original[n]=(ln,h,row['v55_line'],row['complete_original_v55_row_sha256'])
            if row['concrete_address_value_witness'] is None:missing[n]=row
            n+=1
        else:assert tag not in old;old[tag]=row
    assert n==279158 and sorted(missing)==c['original_unresolved']
    assert reg.hexdigest()==c['prior_registry_sha256']==old['FINAL']['witness_registry_sha256']
    assert dict(status)==old['FINAL']['status_counts']
    assert old['INPUT_BINDING_BEFORE']==old['INPUT_BINDING_AFTER']
    proof=source_constraint(c,old['BOUND_FIVE_CLASS_CALL_SOURCE_PROOF'])
    assert new['CONDITIONAL_SOURCE_PROOF']==proof
    seen=0;ref=sha256();excluded=[];unresolved=[]
    with path.open('rb') as f:
        for ln,tag,plan,h in records(c['plan']):
            if tag!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
            idx=plan['index'];assert idx==seen;seen+=1
            ol,oh,pl,ph=original.pop(idx);assert pl==ln and ph==h
            if idx not in missing:continue
            offset,sz,cl,ch=ci.pop(idx);f.seek(offset);b=f.read(sz);assert sha256(b).hexdigest()==ch
            row=json.loads(b.rstrip(b'\r\n').split(b'=',1)[1])
            assert row['index']==idx and row['v67_line']==ol and row['complete_original_v67_row_sha256']==oh
            assert row['v55_line']==ln and row['complete_original_v55_row_sha256']==h and row['complete_original_v55_plan']==plan
            raw=plan['full_four_store_entries'];assert set(raw)=={'D','P','Q','X'}
            for channel,entries in raw.items():
                addresses=[tuple(a) if isinstance(a,list) else a for a,v in entries]
                assert len(addresses)==len(set(addresses))
            assert sha256(wire(stores(raw))).hexdigest()==plan['full_store_sha256']
            assert fingerprint(raw)==plan['original_fingerprint']
            z2=None
            for a,v in sorted(raw['Q'],key=lambda x:x[0]):
                if len(a)==8 and a[5]==2:z2=(a,v);break
            p_present=False
            for a,v in raw['P']:
                if a==1 and v==2:p_present=True
            contradiction=z2 is not None and not p_present
            if contradiction:
                a,v=z2;expected={'present_Q_address':a,'captured_Q_value_preserved_not_used_for_selection':v,
                    'required_P_entry':[1,2],'complete_actual_P_entries':raw['P'],
                    'criterion':'Q_Z2_REQUIRES_P1_TO2_IN_ORIGINAL_BOUND_FIVECLASS_BRANCHES'}
                assert row['concrete_presence_absence_witness']==expected
                assert row['compatibility']=='EXCLUDED_CONDITIONAL_Q_P_COOCCURRENCE';excluded.append(idx)
            else:
                assert row['concrete_presence_absence_witness'] is None and row['compatibility']=='UNRESOLVED_Z1_POST_SOURCE_CORRELATION'
                unresolved.append(idx)
            assert row['original_status_unchanged']==missing[idx]['status']
            ref.update(wire(row))
    assert not original and not ci and seen==279158
    assert excluded==c['expected_new_exclusions'] and unresolved==c['expected_still_unresolved']
    final=new['FINAL'];assert final['new_conditional_exclusions']==excluded and final['still_unresolved']==unresolved
    assert final['eight_refinement_registry_sha256']==ref.hexdigest() and final['source_constraint_proof_sha256']==sha256(wire(proof)).hexdigest()
    assert final['saved_v67_exclusions_reused_without_reclassification']==279150 and final['bounded_fiveclass_excluded_total']==279154
    assert final['ALL_pending_unique_keys']==153792 and not final['fiveclass_complete_exclusion'] and not final['ALL_history_closed']
    assert final['new_native_calibration']==0 and not final['scientific_PASS'] and not final['collection_authorized']
    assert new['INPUT_BINDING_BEFORE']==new['INPUT_BINDING_AFTER'] and new['INPUT_BINDING_BEFORE']['distinct_inputs']==2726
    assert tags=={'INPUT_BINDING_BEFORE':1,'CONDITIONAL_SOURCE_PROOF':1,'EIGHT_INPUT_REFINEMENT':8,'INPUT_BINDING_AFTER':1,'FINAL':1}
    assert binding(c,True)==before
    emit('CHECK',{'result':'BOUND_SOURCE_QZ2_REQUIRES_P1TO2_FOUR_EXCLUSIONS_FOUR_PENDING_NOT_SCIENCE',
        'final':final,'complete_candidate_rows':sum(tags.values()),'original_plan_rows_fully_bound':seen,
        'original_v67_rows_and_registry_fully_reused':n,'checker_distinct_inputs':before['distinct_inputs'],
        'independence':'IMPLEMENTATION_ONLY; separate EOF binary offsets/full keyed joins/ordered presence-absence versus candidate list predicate; shared mechanical stdlib byteJSONGitASTsource helper',
        'RFL_candidate_oldchecker_solver_main_imported_or_executed':False})
if __name__=='__main__':main()

