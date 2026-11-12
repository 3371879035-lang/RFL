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

def independent_source_proof(c):
    import re
    functions=0
    for name,pin in c['sources'].items():
        raw=(ROOT/name).read_bytes();assert sha256(raw).hexdigest()==pin['sha256']
        tree=ast.parse(raw);got=ast_functions(tree)
        assert {key:got[key] for key in pin['qualified_function_AST_sha256']}==pin['qualified_function_AST_sha256']
        functions+=len(pin['qualified_function_AST_sha256'])
    a=(ROOT/c['v20']['initial_source']).read_text(encoding='utf8')
    b=(ROOT/c['v20']['corrected_source']).read_text(encoding='utf8')
    assert a.replace('cls.run','cls.diagnostic_run').replace('self.run','self.diagnostic_run')==b
    assert subprocess.check_output(['git','show',c['v20']['historical_commit']+':'+c['v20']['initial_source']],cwd=ROOT)==(ROOT/c['v20']['initial_source']).read_bytes()
    tree=ast.parse(b);cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='WholeCellTests')
    methods=[x.name for x in cls.body if isinstance(x,ast.FunctionDef) and x.name.startswith('test_')]
    constructors=[x for x in ast.walk(cls) if isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=='LearnerPersistentState']
    assert len(constructors)==1 and constructors[0].args==[] and constructors[0].keywords==[]
    assert len(methods)==26
    rawfixture=(PREP/'test_diagnostic_source_candidate.py').read_text(encoding='utf8')
    assert 'for t in range(K.HORIZON)' in rawfixture
    assert 'K.State(*K.START, t, 0, 0)' in rawfixture
    fixture_tree=ast.parse(rawfixture)
    fixture_class=next(x for x in fixture_tree.body if isinstance(x,ast.ClassDef) and x.name=='DiagnosticSourceTests')
    waiting=next(x for x in fixture_class.body if isinstance(x,ast.FunctionDef) and x.name=='waiting')
    q_calls=[x for x in ast.walk(waiting) if isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id=='QAddress']
    assert len(q_calls)==1 and len(q_calls[0].args)==4 and not q_calls[0].keywords
    assert [ast.literal_eval(x) for x in q_calls[0].args[1:3]]==[1,0]
    assert ast.unparse(q_calls[0].args[3])=='K.WAIT'
    kt=ast.parse((ROOT/'src/rfl_rebuild/env/kernel.py').read_bytes())
    constants={x.target.id:ast.literal_eval(x.value) for x in kt.body if isinstance(x,ast.AnnAssign)
        and isinstance(x.target,ast.Name) and x.target.id in ('START','HORIZON')}
    assert constants=={'START':(0,2),'HORIZON':12}
    ordered=[]
    for t in range(constants['HORIZON']):
        owner=[constants['START'][0],constants['START'][1],t,0,0,1,0]
        ordered.extend([owner+[a] for a in range(5)])
    assert ordered==c['family_q_support']
    assert read(PREP/'whole_credit_source_exclusions_v62/contract.json')['family_q_support'][c['original_v62_family']]==ordered
    return {'source_count':len(c['sources']),'qualified_function_AST_pins':functions,'sources':c['sources'],
        'all_26_scoped_test_methods':methods,'family_q_support':ordered,
        'reasoning':c['source_invariant_reasoning'],'limits':c['scope_limits'],
        'kind':'BOUND_CALL_SOURCE_NECESSARY_FAMILY_NOT_COMPLETE_NATIVE_INPUT_RAW_INDEX'}

def independent_join(n,old_ln,old,old_hash,plan_ln,plan,plan_hash,c):
    assert old['index']==plan['index']==n
    assert old['v55_line']==plan_ln and old['complete_v55_row_sha256']==plan_hash
    pairs=[('original_requested_input','complete_requested_input'),('original_descriptor_reference','first_descriptor_reference'),
           ('original_v46_v47_reference','exact_old_native_v46_v47_reference'),('full_store_sha256','full_store_sha256')]
    assert all(old[k]==plan[v] for k,v in pairs)
    store=stores(plan['full_four_store_entries'])
    assert sha256(wire(store)).hexdigest()==plan['full_store_sha256'] and fingerprint(store)==plan['original_fingerprint']
    witness=old['exact_address_exclusion_witnesses'][c['original_v62_family']]
    actual_entries=[(channel,address,value) for channel in ('D','P','Q','X') for address,value in store[channel]]
    assert any(channel==witness['channel'] and address==witness['address'] and value==witness['captured_value']
               for channel,address,value in actual_entries)
    if witness['channel']=='Q':assert all(witness['address']!=a for a in c['family_q_support'])
    assert plan['complete_requested_input']['nominal_Q_reference_sha256']==c['reference_sha256']
    return {'index':n,'v62_line':old_ln,'complete_original_v62_row_sha256':old_hash,
        'v55_line':plan_ln,'complete_original_v55_row_sha256':plan_hash,'status':old['status'],
        'reuse':'COMPLETE_ORIGINAL_V62_A_ACTUAL_ADDRESS_VALUE_WITNESS_IDENTICAL_NECESSARY_SUPPORT',
        'scope':'ONLY_BOUND_FULLSUITE_WHOLECELL_CALLS_INITIAL_TARGETED_BINDING_AND_ALL_OTHER_HISTORY_PENDING'}

def entry_main():
    c=read(HERE/'contract.json');before=binding(c,checking=True)
    spec={'folder':HERE.relative_to(PREP).as_posix()+'/evidence_corrected','exit':0,'format':'compact'}
    bytag={};keyrefs={};tags=Counter()
    for ln,tag,obj,h in records(spec):
        tags[tag]+=1
        if tag=='REUSED_KEY_ADDRESS_WITNESS_REF':
            index=obj['index'];assert index not in keyrefs;keyrefs[index]=obj
        else:assert tag not in bytag;bytag[tag]=obj
    assert tags=={'INPUT_BINDING_BEFORE':1,'PRESERVED_COMPLETED_SOURCE_PROOF':1,'V20_CAPTURE_AND_PENDING_SCOPE':1,
                 'REUSED_KEY_ADDRESS_WITNESS_REF':c['expected']['planned'],'INPUT_BINDING_AFTER':1,'FINAL':1}
    assert bytag['INPUT_BINDING_BEFORE']==bytag['INPUT_BINDING_AFTER']==binding(c)
    proof=independent_source_proof(c);scope=v20_scope(c)
    preserved=preserved_completed_proof(c);assert preserved['complete_original_proof']==proof
    assert bytag['PRESERVED_COMPLETED_SOURCE_PROOF']==preserved and bytag['V20_CAPTURE_AND_PENDING_SCOPE']==scope
    prior={};old_tags=Counter()
    for ln,tag,obj,h in records(c['reuse']):
        old_tags[tag]+=1
        if tag=='PLANNED_SOURCE_EXCLUSION':
            index=obj['index'];assert index not in prior;prior[index]=(ln,obj,h)
    assert len(prior)==c['expected']['planned']
    # EOF index complete before joining complete v55 rows; no old executable imported or called.
    registry=sha256();counts=Counter();n=0
    for ln,tag,obj,h in records(c['plan']):
        if tag!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
        assert obj['index']==n and obj['complete_descriptor_alias_count']==1
        old_ln,old,old_hash=prior.pop(n)
        row=independent_join(n,old_ln,old,old_hash,ln,obj,h,c)
        assert keyrefs.pop(n)==row;registry.update(wire(row));counts[row['status']]+=1;n+=1
    assert n==c['expected']['planned'] and not prior and not keyrefs
    final={'planned_inputs':n,'exact_stored_witness_reuse_registry_sha256':registry.hexdigest(),
        'source_proof_registry_sha256':sha256(wire(proof)).hexdigest(),'scope_registry_sha256':sha256(wire(scope)).hexdigest(),
        'scoped_fullsuite_class_cases':26,'other_fullsuite_methods_pending':780,
        'initial_and_corrected_targeted_runtime_binding_pending':True,'status_counts':dict(counts),
        'bound_source_family_compatible_planned_inputs':0,'original_v62_classification_reexecuted':False,
        'pending_before':c['expected']['pending'],'pending_after':c['expected']['pending'],
        'all_history_closed':False,'native_calibration_executed':0,'scientific_PASS':False,
        'collection_authorized':False,'research_complete':False}
    assert bytag['FINAL']==final and binding(c,checking=True)==before
    emit('CHECK',{'result':'STORED_BYTE_JSON_SOURCE_AND_EOF_KEYED_JOIN_CHECKED_NOT_SCIENTIFIC_PASS',
        'candidate_implementation':'simultaneous complete old v62 witness/v55 stream join',
        'checker_implementation':'candidate EOF index plus separate original v62 EOF index then complete v55 keyed join',
        'shared_helpers':'stdlib byte/JSON/Git/AST/fingerprint and complete v20 schema parser only; no RFL or old/new candidate/checker imports/execution',
        'original_v20_stored_log_files_checked':8,'original_full_v20_stdout_JSON_rows_checked':15,
        'source_count':len(c['sources']),'qualified_function_AST_pins':sum(len(p['qualified_function_AST_sha256']) for p in c['sources'].values()),
        'full806_case_IDs_retained':806,'scoped26_methods':26,'other780_method_contracts_pending':True,
        'initial_failed_setup_not_discarded_and_missing_runtime_bindings_not_invented':True,
        'parser_repair':'only two original exact space-delimited JSON markers; preserve all15 full records and immutable failed capture',
        'new_candidate_complete_JSON_rows':sum(tags.values()),'distinct_checker_inputs':before['distinct_inputs'],
        'final':final})
if __name__=='__main__':entry_main()
