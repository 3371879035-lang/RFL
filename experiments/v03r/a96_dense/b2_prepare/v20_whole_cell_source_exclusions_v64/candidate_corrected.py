"""V20 bound WholeCellTests necessary-family audit. No RFL imports/execution."""
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
    assert OUTPUT_BYTES<=250000000,'output engineering guard'
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
    names=['contract.json','candidate.py','execute.py','check_stored.py','repair_contract.json','candidate_corrected.py','execute_corrected.py','check_stored_corrected.py']
    names+=['evidence/'+n for n in ('claim.json','exit.json','stdout.log','stderr.log')]
    if checking:names+=['evidence_corrected/'+n for n in ('claim.json','exit.json','stdout.log','stderr.log')]
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
    count=0
    for name,pin in c['sources'].items():
        raw=(ROOT/name).read_bytes();assert sha256(raw).hexdigest()==pin['sha256']
        observed=ast_functions(ast.parse(raw))
        assert {k:observed[k] for k in pin['qualified_function_AST_sha256']}==pin['qualified_function_AST_sha256']
        count+=len(pin['qualified_function_AST_sha256'])
    initial=(ROOT/c['v20']['initial_source']).read_text(encoding='utf8')
    corrected=(ROOT/c['v20']['corrected_source']).read_text(encoding='utf8')
    assert initial.replace('cls.run','cls.diagnostic_run').replace('self.run','self.diagnostic_run')==corrected
    raw=subprocess.check_output(['git','show',c['v20']['historical_commit']+':'+c['v20']['initial_source']],cwd=ROOT)
    assert raw==(ROOT/c['v20']['initial_source']).read_bytes()
    cls=next(n for n in ast.parse(corrected).body if isinstance(n,ast.ClassDef) and n.name=='WholeCellTests')
    methods=[n.name for n in cls.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
    assert len(methods)==26
    ct=[n for n in ast.walk(cls) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='LearnerPersistentState']
    assert len(ct)==1 and not ct[0].args and not ct[0].keywords
    expected=[[0,2,t,0,0,1,0,a] for t in range(12) for a in range(5)]
    assert c['family_q_support']==expected
    assert read(PREP/'whole_credit_source_exclusions_v62/contract.json')['family_q_support'][c['original_v62_family']]==expected
    return {'source_count':len(c['sources']),'qualified_function_AST_pins':count,'sources':c['sources'],
        'all_26_scoped_test_methods':methods,'family_q_support':expected,
        'reasoning':c['source_invariant_reasoning'],'limits':c['scope_limits'],
        'kind':'BOUND_CALL_SOURCE_NECESSARY_FAMILY_NOT_COMPLETE_NATIVE_INPUT_RAW_INDEX'}

def v20_scope(c):
    import re
    v=c['v20'];obs=read(ROOT/v['command_observations']);spec=read(ROOT/v['input_spec'])
    assert obs['actual_native_log_bytes']==v['actual_native_log_bytes']
    for item in obs['actual_native_log_bytes']:
        p=ROOT/item['path'];assert {'bytes':p.stat().st_size,'sha256':digest(p)}=={k:item[k] for k in ('bytes','sha256')}
    for cmd in obs['commands']:
        assert cmd['completion']['native_exit_code']==cmd['captured_native_exit_code']
    assert [x['captured_native_exit_code'] for x in obs['commands']]==[1,0,0,0]
    initial=(ROOT/v['initial_stderr']).read_text(encoding='utf8')
    assert "TypeError: 'OwnedDiagnosticRun' object is not callable" in initial
    assert not re.search(r'^Ran \d+ tests',initial,re.M)
    parsed={};refs=[];plain=0
    for ln,line in enumerate((ROOT/v['full_stdout']).open('rb'),1):
        assert line.endswith(b'\n')
        b=line.rstrip(b'\r\n')
        if b.startswith((b'SEEDLESS_ENGINEERING_SUMMARY ',b'SEEDLESS_FACTUAL_ROUTING_SUMMARY ')):
            tagb,val=b.split(b' ',1);tag=tagb.decode();plain+=1
        else:tagb,val=b.split(b'=',1);tag=tagb.decode()
        o=json.loads(val)
        assert json.dumps(o,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()==val
        assert tag not in parsed;parsed[tag]=o
        refs.append({'line':ln,'tag':tag,'complete_original_line_sha256':sha256(line).hexdigest(),'JSON_value_sha256':sha256(val).hexdigest()})
    assert len(refs)==v['full_stdout_lines']==15 and plain==2
    suite=parsed['FULL_PREPARATION_SUITE_V20']
    assert len(spec['input_file_hashes'])==spec['input_count']==210
    assert suite['input_hashes_before']==suite['input_hashes_after']==spec['input_file_hashes']
    for name,h in spec['input_file_hashes'].items():assert digest(ROOT/name)==h,name
    assert suite['ordered_test_modules']==v['complete_suite_modules']==spec['complete_preparation_test_modules']
    assert len(suite['ordered_test_modules'])==21 and suite['tests_run']==806
    assert suite['failures']==suite['errors']==suite['skipped']==0
    allcases=[];module_counts={};pending=[]
    stderr=(ROOT/v['full_stderr']).read_text(encoding='utf8')
    for line in stderr.splitlines():
        found=re.fullmatch(r'(test_[^ ]+) \(([^)]+)\) \.\.\. ok',line)
        if found:allcases.append(found.group(2));module=found.group(2).split('.')[0];module_counts[module]=module_counts.get(module,0)+1
    assert len(allcases)==len(set(allcases))==806
    assert re.search(r'^Ran 806 tests in [0-9.]+s$',stderr,re.M) and stderr.rstrip().endswith('OK')
    assert not re.search(r'\.\.\. (FAIL|ERROR|skipped)',stderr)
    targeted_text=(ROOT/v['targeted_stderr']).read_text(encoding='utf8')
    small=re.findall(r'^test_[^\r\n]+ \(([^\r\n]+)\) \.\.\. ok$',targeted_text,re.M)
    scoped=[x for x in allcases if x.startswith('test_whole_cell_source_candidate_v20.WholeCellTests.')]
    assert len(small)==len(scoped)==26 and set(small)==set(scoped)
    for module in suite['ordered_test_modules']:
        tree=ast.parse((PREP/(module+'.py')).read_bytes())
        methods=[(node.name,n.name) for node in tree.body if isinstance(node,ast.ClassDef) for n in node.body
                 if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
        assert len(methods)==module_counts[module]
        if module!='test_whole_cell_source_candidate_v20':
            pending.append({'module':module,'complete_test_method_count':len(methods),'source_sha256':digest(PREP/(module+'.py')),
                'status':'PENDING_ACTUAL_CALL_SOURCE_STORE_CONTRACT_NOT_EXCLUDED_BY_NATIVE0'})
    a=parsed['FULL_WHOLE_CELL_RAW_V20'];payload=a['complete_payload']
    assert sha256(wire(payload).rstrip(b'\n')).hexdigest()==a['complete_payload_sha256']==v['full_payload_sha256']
    assert a['complete_DQ_credited_site_count']==12 and a['native_U2_pre_rollouts']==5760
    assert a['native_scene_map_calls']==36 and a['native_B1_arm_calls']==2 and a['map_scene_rollouts']==190080
    owners=[','.join(map(str,[0,2,t,0,0,1,0])) for t in range(12)]
    pair=payload['whole_native_pair'];cell=payload['whole_cell_with_all_residuals']
    assert pair['cell']==cell and cell['ordered_addresses']==owners and len(cell['residual_predictions'])==16
    assert cell['cell_credited_units']==['Decision_'+str(t) for t in range(12)]
    assert len(cell['all_expanded_units'])==28 and pair['B1_arm_calls']==2
    for i,ledger in enumerate(pair['ordered_arm_ledgers']):
        assert ledger['n_addressed']==12 and [row[0] for row in ledger['ordered_receipts']]==owners
        assert [row[1:] for row in ledger['ordered_receipts']]==[['APPLIED',True] if i else ['EVALUABLE_NOOP',False]]*12
        canonical=json.loads(ledger['native_canonical_ledger'])
        assert len(canonical['receipts'])==12 and canonical['fingerprint_pre']==ledger['fingerprint_pre']
    sites=payload['pre_census']['ordered_sites']
    assert sites==['DecisionAddress(State(0,2,'+str(t)+',0,0),1,0)' for t in range(12)]
    census=parsed['FULL_WHOLE_CELL_PRE_CENSUS_V20']['ordered_rows']
    assert len(census)==5760 and sha256(wire(census).rstrip(b'\n')).hexdigest()==payload['pre_census']['full_census_sha256']
    expected_scenes=[[k,p,e,r,z] for k in range(2) for p in range(6) for e in range(2) for r in range(60) for z in range(4)]
    assert [row[0] for row in census]==expected_scenes
    assert all(type(row[1]) is bool and len(row[2])==12 and all(type(x) is bool for x in row[2]) for row in census)
    for i,site in enumerate(sites):
        units=[row[0] for row in census if row[1] and not row[2][i]]
        maps=[payload['all_pre_maps'][i]]+[row['maps'][i] for row in payload['ordered_post_maps']]
        for mp in maps:
            assert mp['site']==site and mp['ordered_unit_keys']==units and len(mp['values_hex'])==len(units)==5280
            assert all(float.fromhex(x).hex()==x for x in mp['values_hex'])
        assert maps[0]['values_hex']==maps[1]['values_hex']
    for name in ('primary_Collateral_scalar','multi_credit_region','per_site_to_primary_aggregation'):assert payload[name] is None
    for name in ('multi_credit_E_S_defined','singleton_update_attribution_claimed','native_raw_collateral_record_or_future_protocol_fabricated',
                 'portable_security_or_scientific_acquisition_origin_authenticated','full_dense_B2_workload_resources_certified',
                 'collection_authorized','scientific_claim_authorized','research_complete'):assert a[name] is False
    assert a['environment_seed_draws']==a['future_training_episodes']==0
    targeted=(ROOT/v['targeted_stdout']).read_bytes().rstrip(b'\r\n').split(b'=',1)
    assert targeted[0]==b'SEEDLESS_WHOLE_CELL_V20_SUMMARY'
    assert json.loads(targeted[1])['complete_payload_sha256']==a['complete_payload_sha256']
    external=read(ROOT/v['external_stdout']);assert external['full_raw_payload_sha256']==a['complete_payload_sha256']
    assert external['case_ids_sha256']==sha256(wire(allcases).rstrip(b'\n')).hexdigest()
    return {'original_commands':obs['commands'],'original_log_byte_bindings':obs['actual_native_log_bytes'],
        'complete_v20_stdout_row_references':refs,'fullsuite_original_input_bindings':spec['input_file_hashes'],
        'complete806_case_IDs':allcases,'scoped26_case_IDs':scoped,'other20_modules780_methods':pending,
        'full_payload_SHA':a['complete_payload_sha256'],'captured_actual_owners':owners,
        'initial_failed_setup':'ACTUALLY_COMPLETED_BEFORE_CLASS_RUN_SHADOW_TYPEERROR_RAW_FULLSTORE_RUNTIME_BINDING_MISSING',
        'initial_and_corrected_targeted_original_full210_runtime_binding_available':False,
        'initial_and_corrected_scope':'CONDITIONAL_BOUND_SOURCE_FAMILY_NOT_COMPLETE_ACTUAL_INPUT_INDEX',
        'fullsuite_scope':'ONLY_WHOLE_CELL_BOUND_CALL_NECESSARY_ADDRESS_FAMILY_OTHER780_METHODS_PENDING',
        'unprinted_fullstore_scalars_raw_not_reconstructed':True,'original_ordered_means_not_recomputed':True,
        'all_original28_predictions_12_DQ16_residuals_and_maps_preserved':True,'limits':c['scope_limits']}

def reuse_row(index,ln_old,old,h_old,ln_plan,plan,h_plan,c):
    assert old['index']==plan['index']==index
    assert old['v55_line']==ln_plan and old['complete_v55_row_sha256']==h_plan
    assert old['original_requested_input']==plan['complete_requested_input']
    assert old['original_descriptor_reference']==plan['first_descriptor_reference']
    assert old['original_v46_v47_reference']==plan['exact_old_native_v46_v47_reference']
    state=stores(plan['full_four_store_entries'])
    assert sha256(wire(state)).hexdigest()==plan['full_store_sha256']==old['full_store_sha256']
    assert fingerprint(state)==plan['original_fingerprint']
    w=old['exact_address_exclusion_witnesses'][c['original_v62_family']]
    assert [w['address'],w['captured_value']] in state[w['channel']]
    assert w['channel']!='Q' or w['address'] not in c['family_q_support']
    assert plan['complete_requested_input']['nominal_Q_reference_sha256']==c['reference_sha256']
    return {'index':index,'v62_line':ln_old,'complete_original_v62_row_sha256':h_old,
        'v55_line':ln_plan,'complete_original_v55_row_sha256':h_plan,'status':old['status'],
        'reuse':'COMPLETE_ORIGINAL_V62_A_ACTUAL_ADDRESS_VALUE_WITNESS_IDENTICAL_NECESSARY_SUPPORT',
        'scope':'ONLY_BOUND_FULLSUITE_WHOLECELL_CALLS_INITIAL_TARGETED_BINDING_AND_ALL_OTHER_HISTORY_PENDING'}


def preserved_completed_proof(c):
    repair=read(HERE/'repair_contract.json')
    for n,h in repair['original_sources'].items():assert digest(HERE/n)==h
    for n,info in repair['original_capture'].items():
        p=HERE/'evidence'/n;assert {'bytes':p.stat().st_size,'sha256':digest(p)}==info
    rows=list(records({'folder':HERE.relative_to(PREP).as_posix()+'/evidence','exit':1,'format':'compact'}))
    assert [tag for ln,tag,obj,h in rows]==['INPUT_BINDING_BEFORE','BOUND_CALL_SOURCE_PROOF']
    assert rows[1][2]['sources']==c['sources'] and rows[1][2]['family_q_support']==c['family_q_support']
    return {'complete_original_proof':rows[1][2],'failed_original_proof_line':rows[1][0],
        'complete_original_proof_line_sha256':rows[1][3],'original_failed_capture':repair['original_capture'],
        'original_completed_source_proof_reexecuted':False,'old_failed_candidate_and_checker_not_executed':True}

def main():
    c=read(HERE/'contract.json');before=binding(c);emit('INPUT_BINDING_BEFORE',before)
    preserved=preserved_completed_proof(c);proof=preserved['complete_original_proof'];emit('PRESERVED_COMPLETED_SOURCE_PROOF',preserved)
    scope=v20_scope(c);emit('V20_CAPTURE_AND_PENDING_SCOPE',scope)
    oldrows=(x for x in records(c['reuse']) if x[1]=='PLANNED_SOURCE_EXCLUSION')
    plans=(x for x in records(c['plan']) if x[1]=='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY')
    n=0;registry=sha256();counts=Counter()
    for n0,old in enumerate(oldrows):
        ln,tag,p,h=next(plans);lo,to,o,ho=old
        row=reuse_row(n0,lo,o,ho,ln,p,h,c);registry.update(wire(row));counts[row['status']]+=1
        emit('REUSED_KEY_ADDRESS_WITNESS_REF',row);n=n0+1;assert n<=c['guards']['max_planned']
    assert next(plans,None) is None and n==c['expected']['planned']
    assert counts=={'EXACT_OLD_v46_v47_REFERENCE_PRESERVED':c['expected']['old_v46_v47'],
                   'PENDING_OTHER_ALL_HISTORY_SOURCE_RAW_INDEX':c['expected']['pending']}
    assert binding(c)==before;emit('INPUT_BINDING_AFTER',before)
    emit('FINAL',{'planned_inputs':n,'exact_stored_witness_reuse_registry_sha256':registry.hexdigest(),
        'source_proof_registry_sha256':sha256(wire(proof)).hexdigest(),'scope_registry_sha256':sha256(wire(scope)).hexdigest(),
        'scoped_fullsuite_class_cases':26,'other_fullsuite_methods_pending':780,
        'initial_and_corrected_targeted_runtime_binding_pending':True,'status_counts':dict(counts),
        'bound_source_family_compatible_planned_inputs':0,'original_v62_classification_reexecuted':False,
        'pending_before':c['expected']['pending'],'pending_after':c['expected']['pending'],
        'all_history_closed':False,'native_calibration_executed':0,'scientific_PASS':False,
        'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()
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
