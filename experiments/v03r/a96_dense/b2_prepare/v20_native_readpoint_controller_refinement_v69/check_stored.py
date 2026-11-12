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


def find(tree,key):
    node=tree
    for bit in key.split('.'):
        node=next(n for n in node.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name==bit)
    return node

def prior_capture(c):
    special={};eight={};reg=sha256()
    for ln,tag,row,h in records(c['prior']):
        if tag=='EIGHT_INPUT_REFINEMENT':
            assert row['index'] not in eight;eight[row['index']]=(ln,h,row);reg.update(wire(row))
        else:assert tag not in special;special[tag]=row
    assert reg.hexdigest()==c['prior_registry_sha256'] and len(eight)==8
    assert special['INPUT_BINDING_BEFORE']==special['INPUT_BINDING_AFTER']
    assert sha256(wire(special['CONDITIONAL_SOURCE_PROOF'])).hexdigest()==c['prior_proof_sha256']
    assert special['FINAL']['bounded_fiveclass_excluded_total']==279154
    assert special['FINAL']['still_unresolved']==c['original_unresolved']
    return special,eight

def source_readpoint_proof(c,prior):
    spec=read(ROOT/c['v20']['input_spec'])
    frozen=read(ROOT/'experiments/v03r/a96_dense/f0_manifest.json')['sources']
    inventory={};selected={};explicit=[];functions=0;source_provenance={}
    P='experiments/v03r/a96_dense/b2_prepare/'
    picks={P+'test_pair_source_candidate.py':['PairSourceTests.'+n for n in c['mutation_methods']]+['PairSourceTests.pair','PairSourceTests.setup_call','PairSourceTests.audit'],
      P+'test_diagnostic_source_candidate.py':c['external_fixture_helpers'],
      P+'pair_source_candidate.py':['run_owned_b1_pair','_checked_pair','_cell_payload','_ledger_payload','pair_audit','clone_immediate_post'],
      P+'diagnostic_source_candidate.py':['_checked_run','diagnostic_credit','diagnostic_audit','prepare_diagnosed_cell'],
      P+'counterfactual_source_candidate.py':['_checked','prepare_owned_l2_source'],
      P+'credit_delivery_candidate.py':['prepare_cell','validate_credit','_delivery_payload'],
      'src/rfl_rebuild/learner/store.py':['LearnerPersistentState.clone','LearnerPersistentState.apply_transaction'],
      'src/rfl_rebuild/b1/laws.py':['XId.plan','FactualReturnWrite.plan','DualReturnWrite.plan']}
    for name,pin in c['sources'].items():
        raw=(ROOT/name).read_bytes();tree=ast.parse(raw);h=sha256(raw).hexdigest()
        assert h==pin['sha256'] and ast_functions(tree)==pin['qualified_function_AST_sha256']
        functions+=len(pin['qualified_function_AST_sha256'])
        original=spec['input_file_hashes'].get(name,frozen.get(name))
        assert h==original
        source_provenance[name]='ORIGINAL_FULLSUITE210' if name in spec['input_file_hashes'] else 'ORIGINAL313_FROZEN_LOAD_PARENT'
        if Path(name).stem in c['modules']:
            for cl in tree.body:
                if isinstance(cl,ast.ClassDef):
                    for n in cl.body:
                        if isinstance(n,ast.FunctionDef):
                            calls=sorted((x for x in ast.walk(n) if isinstance(x,ast.Call)),key=lambda x:(x.lineno,x.col_offset))
                            inventory[Path(name).stem+'.'+cl.name+'.'+n.name]=[ast.unparse(x) for x in calls]
                            for x in calls:
                                if isinstance(x.func,ast.Name) and x.func.id=='Edit' and ast.unparse(x.args[0])=='CONTROLLER':
                                    explicit.append({'method':cl.name+'.'+n.name,'file':name,'call':ast.unparse(x),'target':ast.unparse(x.args[2])})
        for key in picks.get(name,[]):selected[name+':'+key]=ast.unparse(find(tree,key))
    assert functions==641 and len(inventory)==199
    nonwait=[e for e in explicit if e['target']!='K.WAIT']
    assert [e['method'] for e in nonwait]==['PairSourceTests.'+n for n in c['mutation_methods']]
    assert all(e['call']=='Edit(CONTROLLER, K.ControllerSite(s, K.WAIT), K.RIGHT)' for e in nonwait)
    timelines=[]
    for n in c['mutation_methods']:
        key=P+'test_pair_source_candidate.py:PairSourceTests.'+n;body=selected[key]
        assert body.index('self.pair()')<body.index('apply_transaction(')
        tree=ast.parse(body).body[0]
        transaction=next(x for x in ast.walk(tree) if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=='apply_transaction')
        calls=sorted((x for x in ast.walk(tree) if isinstance(x,ast.Call)),key=lambda x:(x.lineno,x.col_offset))
        timelines.append({'method':'PairSourceTests.'+n,'complete_method_AST_source':body,
          'complete_ordered_call_expressions':[ast.unparse(x) for x in calls],
          'mutation_line_in_saved_AST':transaction.lineno,
          'all_postmutation_call_expressions':[ast.unparse(x) for x in calls if x.lineno>=transaction.lineno],
          'pre_mutation_default_native_pair_preserved':True,'mutated_object_native_reader_dispatch':False,
          'mutated_object_full_Q_store_not_reconstructed':True})
    default=selected[P+'test_pair_source_candidate.py:PairSourceTests.pair']
    assert "architecture='D_Q'" in default and 'tier=Tier.L0_FACTUAL' in default and "law='FactualReturnWrite'" in default
    assert 'PairedRunner._apply(arm, clone, evidence, data.reference)' in selected[P+'pair_source_candidate.py:run_owned_b1_pair']
    assert 'data.pre_state.clone()' in selected[P+'pair_source_candidate.py:run_owned_b1_pair']
    assert 'Tier.L2_COUNTERFACTUAL' in selected[P+'pair_source_candidate.py:_cell_payload']
    for key in [P+'pair_source_candidate.py:pair_audit',P+'pair_source_candidate.py:clone_immediate_post',
                P+'diagnostic_source_candidate.py:_checked_run',P+'counterfactual_source_candidate.py:_checked']:
        assert not any(t in selected[key] for t in ('learned_rollout(', 'pre_update_traces(', 'measure_scene_map(', 'PairedRunner._apply(', 'build_counterfactual_envelope('))
    assert 'ledger.fingerprint_post == fingerprint(clone)' in selected[P+'pair_source_candidate.py:_ledger_payload']
    assert 'fingerprint(data.pre_state) == data.fingerprint_pre' in selected[P+'counterfactual_source_candidate.py:_checked']
    v20bytes=[]
    for m in c['v20']['actual_native_log_bytes']:
        p=ROOT/m['path'];assert p.stat().st_size==m['bytes'] and digest(p)==m['sha256'];v20bytes.append(m)
    suite=None;payloads=[]
    for ln,line in enumerate((ROOT/c['v20']['full_stdout']).open('rb'),1):
        stripped=line.rstrip(b'\r\n')
        if stripped.startswith((b'SEEDLESS_ENGINEERING_SUMMARY ',b'SEEDLESS_FACTUAL_ROUTING_SUMMARY ')):
            marker,j=stripped.split(b' ',1)
        else:marker,j=stripped.split(b'=',1)
        o=json.loads(j);payloads.append({'line':ln,'marker':marker.decode(),'full_row_sha256':sha256(line).hexdigest(),'full_JSON_payload_sha256':sha256(j).hexdigest()})
        if marker==b'FULL_PREPARATION_SUITE_V20':suite=o
    assert len(payloads)==15 and suite['tests_run']==806 and suite['failures']==suite['errors']==suite['skipped']==0
    assert suite['input_hashes_before']==suite['input_hashes_after']==spec['input_file_hashes'] and len(spec['input_file_hashes'])==210
    stderr=(ROOT/c['v20']['full_stderr']).read_bytes();case_rows=[]
    for n in c['mutation_methods']:
        case='test_pair_source_candidate.PairSourceTests.'+n
        matches=[(i,line) for i,line in enumerate(stderr.splitlines(keepends=True),1) if ('('+case+') ... ok').encode() in line]
        assert len(matches)==1
        i,line=matches[0];case_rows.append({'case_ID':case,'stderr_line':i,'complete_case_receipt_line':line.decode('utf8'),'row_sha256':sha256(line).hexdigest()})
        assert case in prior['scoped183_case_IDs']
    commands=read(ROOT/c['v20']['command_observations'])['commands']
    full=next(x for x in commands if x['label']=='whole_cell_full_preparation')
    assert full['captured_native_exit_code']==full['completion']['native_exit_code']==0
    return {'prior_v68_full_source_proof':prior,'original_source_pins':c['sources'],'source_provenance':source_provenance,
      'source_files':41,'qualified_AST_pins':functions,'all199_full_call_expression_inventory':inventory,
      'all_explicit_X_Edit_calls':explicit,'four_complete_mutant_timeline':timelines,
      'complete_selected_original_callgraph_AST_source':selected,'original_full806_case_IDs':prior['original806_case_IDs_retained'],
      'scoped183_case_IDs':c['scoped_case_IDs'],'v20_fullsuite210_before_after_binding':suite,
      'four_original_actual_case_receipt_rows':case_rows,'v20_complete15_payload_line_bindings':payloads,
      'v20_complete8_original_log_byte_bindings':v20bytes,'v20_original_fullsuite_receipt':full,
      'necessary_native_readpoint_constraint':c['necessary_constraint'],'complete_source_reasoning':c['source_reasoning'],
      'limits':c['limits'],'no_original_Q_scalar_return_aggregate_recomputed':True,
      'full_mutant_store_object_compatibility_still_UNRESOLVED':c['original_unresolved'],
      'scope_not_arbitrary_caller_or_ALL_history':True}

def result_final(c,proof,reg):
    return {'prior_bounded_object_source_exclusions_reused_without_reclassification':279154,
      'new_bound_actual_native_readpoint_excluded_indices':c['expected_new_exclusions'],
      'bound_fiveclass_actual_native_input_excluded_total':279158,
      'bound_fiveclass_native_readpoint_exclusion_complete':True,
      'all_mutated_store_object_compatibility_closed':False,
      'mutated_store_object_compatibility_UNRESOLVED':c['original_unresolved'],
      'four_refinement_registry_sha256':reg,'source_readpoint_proof_sha256':sha256(wire(proof)).hexdigest(),
      'old125366_native_refs_unchanged':True,'ALL_pending_unique_keys':153792,
      'other11_modules424_methods_pending':True,'initialfailed_targeted26_runtime_raw_gap_pending':True,
      'ALL_history_closed':False,'ALL_complete_old_raw_fullinput_index_closed':False,'new_native_calibration':0,
      'scientific_PASS':False,'collection_authorized':False,'research_complete':False,
      'old_Q_scalars_returns_aggregates_recomputed':False,'missing_old_raw_restored':False}

def main():
    c=read(HERE/'contract.json');before=binding(c,True)
    special,eight=prior_capture(c);proof=source_readpoint_proof(c,special['CONDITIONAL_SOURCE_PROOF'])
    positions={};candidate_special={};reg=sha256();path=HERE/'evidence/stdout.log'
    # Complete fresh binary EOF with actual tell/readline offsets before old-source keyed join.
    with path.open('rb') as stream:
        ln=0
        while True:
            offset=stream.tell();line=stream.readline()
            if not line:break
            ln+=1;t,j=line.rstrip(b'\r\n').split(b'=',1);tag=t.decode();o=json.loads(j)
            assert line==t+b'='+wire(o)
            if tag=='FOUR_NATIVE_READPOINT_REFINEMENT':
                assert o['index'] not in positions
                positions[o['index']]=(offset,len(line),ln,sha256(line).hexdigest());reg.update(wire(o))
            else:assert tag not in candidate_special;candidate_special[tag]=o
    assert ln==8 and sorted(positions)==c['original_unresolved']
    assert candidate_special['BOUND_NATIVE_READPOINT_SOURCE_PROOF']==proof
    assert candidate_special['INPUT_BINDING_BEFORE']==candidate_special['INPUT_BINDING_AFTER']
    assert candidate_special['FINAL']==result_final(c,proof,reg.hexdigest())
    # Independent full original EOF parse then keyed equality; ordered actual entry comparisons, no candidate predicate.
    n=0;verified=0
    for ln,tag,plan,h in records(c['plan']):
        if tag!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert plan['index']==n;idx=n;n+=1
        if idx not in positions:continue
        off,length,cln,ch=positions[idx]
        with path.open('rb') as stream:stream.seek(off);line=stream.read(length)
        assert len(line)==length and sha256(line).hexdigest()==ch
        row=json.loads(line.split(b'=',1)[1]);pln,ph,prev=eight[idx]
        assert prev['v55_line']==ln and prev['complete_original_v55_row_sha256']==h and prev['complete_original_v55_plan']==plan
        assert row['v68_line']==pln and row['complete_original_v68_row_sha256']==ph and row['v55_line']==ln and row['complete_original_v55_row_sha256']==h
        assert row['complete_original_v55_plan']==plan and row['original_v46_v47_reference_status_unchanged']==prev['original_status_unchanged']
        entries=plan['full_four_store_entries']
        for channel in ('D','P','Q','X'):
            addresses=[a for a,v in entries[channel]]
            assert len(addresses)==len({json.dumps(a) for a in addresses})
        assert any(a==[0,2,0,0,0,4] and v==3 for a,v in entries['X'])
        witness=row['concrete_witness']
        assert witness=={'actual_planned_X_address':[0,2,0,0,0,4],'actual_planned_X_value':3,
          'necessary_native_readpoint_X_nonidentity_value':4,'source_proof_sha256':sha256(wire(proof)).hexdigest(),
          'four_original_post_native_mutants_retained':True}
        assert row['compatibility_at_bound_actual_native_readpoint']=='EXCLUDED_CONCRETE_X_VALUE_AND_ACTUAL_CALL_ORDER'
        assert row['mutated_store_object_compatibility']=='UNRESOLVED_NOT_AN_ACTUAL_NATIVE_DISPATCH'
        verified+=1
    assert n==279158 and verified==4 and binding(c,True)==before
    ex=read(HERE/'evidence/exit.json');cl=read(HERE/'evidence/claim.json')
    assert ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items())
    for name,meta in ex['files'].items():assert {'bytes':(HERE/'evidence'/name).stat().st_size,'sha256':digest(HERE/'evidence'/name)}==meta
    for name,h in cl['inputs'].items():assert digest(HERE/name)==h
    emit('CHECK',{'result':'BOUND_NATIVE_READPOINT_FOUR_X_VALUE_CONTRADICTIONS_NOT_ALL_HISTORY_OR_OBJECT_STORE_COMPATIBILITY',
      'complete_candidate_rows':8,'original_plan_rows_full_EOF':n,'independent_four_keyed_ordered_entry_checks':verified,
      'checker_distinct_inputs':before['distinct_inputs'],'final':candidate_special['FINAL'],
      'independence':'IMPLEMENTATION_ONLY binary EOF offsets and keyed ordered entry checker vs list predicate; shared mechanical byteJSONGitASTsource proof not expert/sciencePASS',
      'RFL_candidate_oldchecker_solver_main_imported_or_executed':False})
if __name__=='__main__':main()

