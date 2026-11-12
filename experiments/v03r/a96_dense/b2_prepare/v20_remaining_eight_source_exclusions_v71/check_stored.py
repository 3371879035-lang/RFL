"""Only original fullsuite remaining eight330 actual calls; stdlib stored audit."""
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
    assert OUTPUT_BYTES<=1200000000,'output engineering guard'
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


def original_v70(c):
    p=PREP/c['v70']['folder'];cl=read(p/'claim.json');ex=read(p/'exit.json')
    assert ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items())
    assert ex['files']['stdout.log']['sha256']==c['v70']['sha256']
    for name,h in cl['inputs'].items():assert digest(p.parent/name)==h
    for name,m in ex['files'].items():assert {'bytes':(p/name).stat().st_size,'sha256':digest(p/name)}==m
    with (p/'stdout.log').open('rb') as f:
        first=f.readline();second=f.readline()
        t,j=second.rstrip(b'\r\n').split(b'=',1);assert t==b'BOUND_THREE_MODULE94_SOURCE_PROOF'
        oldproof=json.loads(j);assert second==t+b'='+wire(oldproof)
        f.seek(max(0,f.seek(0,2)-10000));tail=f.read()
    finals=[json.loads(x.split(b'=',1)[1]) for x in tail.splitlines() if x.startswith(b'FINAL=')]
    assert len(finals)==1 and finals[0]['bound_fullsuite_methods_now']==476 and finals[0]['ALL_history_closed'] is False
    return {'proof':oldproof,'reference':{'claim':cl,'receipt':ex,'first_binding_row_sha256':sha256(first).hexdigest(),'complete_source_proof_row_sha256':sha256(second).hexdigest(),'source_proof_canonical_JSON_LF_sha256':sha256(wire(oldproof)).hexdigest(),'complete_prior_FINAL':finals[0],'prior94_exclusion_rows_not_reclassified_or_rerun':True}}

def source_proof(c):
    spec=read(ROOT/c['v20']['input_spec'])
    frozen=read(ROOT/'experiments/v03r/a96_dense/f0_manifest.json')['sources']
    allpins={};provenance={};inventory={};bodies={};selected={};constructors=[];edits=[];counts={}
    P='experiments/v03r/a96_dense/b2_prepare/'
    picks=c['selected_AST']
    fullmodules=list(c['whole_source_paths'])
    whole_sources={}
    for name,pin in c['sources'].items():
        raw=(ROOT/name).read_bytes();tree=ast.parse(raw);fs=ast_functions(tree)
        assert sha256(raw).hexdigest()==pin['sha256']
        assert len(fs)==pin['qualified_AST_count'] and sha256(wire(fs)).hexdigest()==pin['qualified_AST_map_sha256']
        assert pin['sha256']==spec['input_file_hashes'].get(name,frozen.get(name))
        allpins[name]=fs
        provenance[name]='ORIGINAL_FULLSUITE210' if name in spec['input_file_hashes'] else 'ORIGINAL313_FROZEN_LOAD_PARENT'
        if name in fullmodules:whole_sources[name]=raw.decode('utf8')
        if Path(name).stem in c['modules']:
            module=Path(name).stem;counts[module]=0
            for key in fs:
                node=find(tree,key);full=module+'.'+key
                calls=sorted((x for x in ast.walk(node) if isinstance(x,ast.Call)),key=lambda x:(x.lineno,x.col_offset))
                bodies[full]=ast.unparse(node);inventory[full]=[ast.unparse(x) for x in calls]
                if key.split('.')[-1].startswith('test_'):counts[module]+=1
                for call in calls:
                    if isinstance(call.func,ast.Name) and call.func.id=='LearnerPersistentState':
                        constructors.append({'function':full,'call':ast.unparse(call)})
                    if isinstance(call.func,ast.Name) and call.func.id=='Edit':
                        edits.append({'function':full,'call':ast.unparse(call)})
        for key in picks.get(name,[]):selected[name+':'+key]=ast.unparse(find(tree,key))
    assert len(allpins)==65 and sum(map(len,allpins.values()))==c['qualified_AST_count']
    assert counts==c['modules'] and len(inventory)==c['method_helper_count']
    assert constructors==[{'function':'test_future_inputs_candidate.FutureInputsTests.test_success_skip_no_arm_template_clone_seed_or_record','call':'LearnerPersistentState()'}]
    assert [x['call'] for x in edits]==['Edit(PROCESS, 0, 1)','Edit(PROCESS, 0, 1)','Edit(PROCESS, 0, None)']
    external={}
    for name,keys in c['external_helpers'].items():
        tree=ast.parse((ROOT/name).read_bytes())
        for key in keys:
            node=find(tree,key);full=Path(name).stem+'.'+key
            external[full]={'complete_AST_source':ast.unparse(node),'full_call_expressions':[ast.unparse(x) for x in sorted((x for x in ast.walk(node) if isinstance(x,ast.Call)),key=lambda x:(x.lineno,x.col_offset))]}
    assert len(external)==4
    setup=external['test_single_map_source_candidate.SingleMapTests.setUpClass']['complete_AST_source']
    transient=external['test_diagnostic_source_candidate.DiagnosticSourceTests.transient']['complete_AST_source']
    assert 'cls.source = cls.fixture.transient()' in setup and "registered_pair('X', Tier.L0_FACTUAL, 'X_id')" in setup
    assert "self.source(LearnerPersistentState(), regime='T'" in transient
    assert 'actual_apply(*args, **kw)' in setup and 'actual_map(state, units, **kw)' in setup and 'actual_census(**kw)' in setup
    assert 'fixture_module.SingleMapTests.setUpClass()' in bodies['test_future_inputs_candidate.FutureInputsTests.setUpClass']
    assert 'return actual_clone(*args, **kw)' in bodies['test_future_inputs_candidate.FutureInputsTests.setUpClass']
    assert 'Edit(CONTROLLER, site, site.cmd)' in selected['src/rfl_rebuild/b1/laws.py:XId.plan']
    assert 'run_controller_law(arm.law, clone' in selected['src/rfl_rebuild/b2/runner.py:PairedRunner._apply']
    prior=original_v70(c);old806=prior['proof']['original806_complete_case_IDs']
    actualcases=[];case_rows=[];stderr=(ROOT/c['v20']['full_stderr']).read_bytes()
    for i,line in enumerate(stderr.splitlines(keepends=True),1):
        match=re.search(rb'\((test_[^()]+)\) \.\.\. ok',line)
        if match:
            case=match.group(1).decode('utf8');actualcases.append(case)
            if case in c['scoped_case_IDs']:
                case_rows.append({'case_ID':case,'stderr_line':i,'complete_actual_case_receipt_line':line.decode('utf8'),'row_sha256':sha256(line).hexdigest()})
    assert actualcases==old806 and len(set(actualcases))==806
    assert sorted(x['case_ID'] for x in case_rows)==sorted(c['scoped_case_IDs']) and len(case_rows)==330
    payloads=[];suite=None
    for ln,line in enumerate((ROOT/c['v20']['full_stdout']).open('rb'),1):
        stripped=line.rstrip(b'\r\n')
        if stripped.startswith((b'SEEDLESS_ENGINEERING_SUMMARY ',b'SEEDLESS_FACTUAL_ROUTING_SUMMARY ')):
            marker,j=stripped.split(b' ',1)
        else:marker,j=stripped.split(b'=',1)
        o=json.loads(j);payloads.append({'line':ln,'marker':marker.decode(),'row_sha256':sha256(line).hexdigest(),'full_original_JSON_payload':o})
        if marker==b'FULL_PREPARATION_SUITE_V20':suite=o
    assert len(payloads)==15 and suite['tests_run']==806 and suite['failures']==suite['errors']==suite['skipped']==0
    assert suite['input_hashes_before']==suite['input_hashes_after']==spec['input_file_hashes']
    logbytes=c['v20']['actual_native_log_bytes']
    for m in logbytes:
        p=ROOT/m['path'];assert {'bytes':p.stat().st_size,'sha256':digest(p)}=={k:m[k] for k in ('bytes','sha256')}
    full=next(x for x in read(ROOT/c['v20']['command_observations'])['commands'] if x['label']=='whole_cell_full_preparation')
    assert full['captured_native_exit_code']==full['completion']['native_exit_code']==0
    return {'original65_source_pins':c['sources'],'all1240_qualified_AST_pins':allpins,'source_provenance':provenance,
      'complete_eight_test_and_required_callee_source_bytes_UTF8':whole_sources,
      'all358_complete_actual_method_setup_helper_AST_source':bodies,'all358_full_actual_call_expression_inventory':inventory,
      'external_and_native_complete_selected_AST_source':selected,'all4_exact_external_helper_complete_AST_and_calls':external,'prior_v70_boundary_capture_proof_reference':prior['reference'],'all_explicit_learner_constructors':constructors,'all_explicit_Edit_calls':edits,
      'original806_complete_case_IDs':old806,'scoped330_complete_case_IDs':c['scoped_case_IDs'],'scoped330_complete_actual_case_receipt_rows':case_rows,
      'original_fullsuite210_before_after_binding':suite,'all15_complete_original_stdout_JSON_payloads':payloads,
      'all8_original_log_byte_bindings':logbytes,'original_fullsuite_command_receipt':full,
      'necessary_input_constraint':c['necessary_constraint'],'source_reasoning':c['source_reasoning'],'limits':c['limits'],
      'no_original_scalar_return_metric_aggregate_recomputed':True,'unprinted_raw_fullstores_not_reconstructed':True,
      'scope_not_arbitrary_caller_or_ALL_history':True}

def final_result(c,proof,registry,counts):
    return {'bound_eight_module330_necessary_input_exclusions':279158,'bound_source_family_compatibility_exclusion_closed':True,
      'witness_channel_counts':dict(counts),'registry_sha256':registry,'source_proof_sha256':sha256(wire(proof)).hexdigest(),
      'prior476_method_family_results_preserved_not_rerun':True,'bound_fullsuite_methods_now':806,
      'v20_all21_modules806_actual_call_source_contract_closed':True,'remaining_fullsuite_modules':{},'remaining_fullsuite_methods':0,
      'v20_initialfailed_targeted26_runtime_fullraw_gap_pending':True,
      'four_postnative_mutated_object_fullstore_compatibility_UNRESOLVED':[114714,114716,114718,114720],
      'ALL_history_closed':False,'ALL_complete_old_raw_fullinput_index_closed':False,
      'old125366_exactrefs_unchanged':True,'ALL_pending_unique_keys':153792,
      'new_native_calibration':0,'scientific_PASS':False,'collection_authorized':False,'research_complete':False,
      'new_RFL_kernel_B1_DP_scalar_metric_aggregate_key_RNG_training_collector_acquisition':0}


def main():
    c=read(HERE/'contract.json');before=binding(c,True);proof=source_proof(c);ph=sha256(wire(proof)).hexdigest()
    path=HERE/'evidence/stdout.log';positions={};special={};reg=sha256();counts=Counter()
    # Full fresh EOF index, actual offsets/lengths; no candidate execution or predicate.
    with path.open('rb') as stream:
        nlines=0
        while True:
            off=stream.tell();line=stream.readline()
            if not line:break
            nlines+=1;t,j=line.rstrip(b'\r\n').split(b'=',1);tag=t.decode();o=json.loads(j)
            assert line==t+b'='+wire(o)
            if tag=='BOUND_EIGHT_MODULE330_SOURCE_EXCLUSION':
                idx=o['index'];assert idx==len(positions)
                positions[idx]=(off,len(line),nlines,sha256(line).hexdigest());reg.update(wire(o))
                counts[o['necessary_DQ_empty_concrete_entry_witness']['channel']]+=1
            else:assert tag not in special;special[tag]=o
    assert len(positions)==279158 and nlines==279162
    assert special['INPUT_BINDING_BEFORE']==special['INPUT_BINDING_AFTER']
    assert special['BOUND_EIGHT_MODULE330_SOURCE_PROOF']==proof
    assert special['FINAL']==final_result(c,proof,reg.hexdigest(),counts)
    priorpath=PREP/c['prior']['folder'];cl=read(priorpath/'claim.json');ex=read(priorpath/'exit.json')
    assert ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items())
    assert ex['files']['stdout.log']['sha256']==c['prior']['sha256']
    for name,h in cl['inputs'].items():assert digest(priorpath.parent/name)==h
    for name,m in ex['files'].items():assert {'bytes':(priorpath/name).stat().st_size,'sha256':digest(priorpath/name)}==m
    oldpositions={}
    with (priorpath/'stdout.log').open('rb') as stream:
        ln=0
        while True:
            off=stream.tell();line=stream.readline()
            if not line:break
            ln+=1;t,j=line.rstrip(b'\r\n').split(b'=',1);o=json.loads(j);assert line==t+b'='+wire(o)
            if t==b'PLANNED_SOURCE_EXCLUSION':
                idx=o['index'];assert idx==len(oldpositions)
                oldpositions[idx]=(off,len(line),ln,sha256(line).hexdigest())
    assert len(oldpositions)==279158
    n=0
    with path.open('rb') as fresh,(priorpath/'stdout.log').open('rb') as oldstream:
        for pln,tag,plan,h in records(c['plan']):
            if tag!='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':continue
            assert plan['index']==n
            off,length,rowln,rh=positions[n];fresh.seek(off);line=fresh.read(length)
            assert sha256(line).hexdigest()==rh;row=json.loads(line.split(b'=',1)[1])
            poff,plen,oln,oh=oldpositions[n];oldstream.seek(poff);oldline=oldstream.read(plen)
            assert sha256(oldline).hexdigest()==oh;prev=json.loads(oldline.split(b'=',1)[1])
            assert prev['v55_line']==pln and prev['complete_v55_row_sha256']==h
            assert prev['original_requested_input']==plan['complete_requested_input']
            assert prev['original_v46_v47_reference']==plan['exact_old_native_v46_v47_reference']
            assert row['index']==n and row['v55_line']==pln and row['complete_original_v55_row_sha256']==h
            assert row['v61_line']==oln and row['complete_original_v61_row_sha256']==oh
            assert row['complete_original_plan']==plan and row['source_proof_sha256']==ph
            w=prev['exact_address_exclusion_witnesses']['EMPTY_D_AND_Q']
            assert row['necessary_DQ_empty_concrete_entry_witness']==w and w['channel'] in ('D','Q')
            # Independent complete ordered original entry scan; no copied candidate membership predicate.
            found=0
            for channel in ('D','P','Q','X'):
                seen=set()
                for address,value in plan['full_four_store_entries'][channel]:
                    key=json.dumps(address);assert key not in seen;seen.add(key)
                    if channel==w['channel'] and address==w['address'] and value==w['captured_value']:found+=1
            assert found==1 and row['compatibility']=='EXCLUDED_CONCRETE_ENTRY_VS_BOUND_NATIVE_DQ_EMPTY'
            assert row['original_oldrefs_and_ALL_pending_status_unchanged'] is True
            n+=1
    assert n==279158 and binding(c,True)==before
    cl=read(HERE/'evidence/claim.json');ex=read(HERE/'evidence/exit.json')
    assert ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items())
    for name,h in cl['inputs'].items():assert digest(HERE/name)==h
    for name,m in ex['files'].items():assert {'bytes':(HERE/'evidence'/name).stat().st_size,'sha256':digest(HERE/'evidence'/name)}==m
    emit('CHECK',{'result':'BOUND_EIGHT_MODULE330_SOURCE_INPUT_EXCLUSIONS_NOT_ALL_HISTORY_OR_NATIVE_CALIBRATION',
      'complete_candidate_rows':nlines,'complete_original_v61_EOF_index_rows':len(oldpositions),
      'complete_original_v55_EOF_keyed_ordered_entry_checks':n,'checker_distinct_inputs':before['distinct_inputs'],
      'final':special['FINAL'],'implementation_independence':'binary actual tell/readline EOF indexes and keyed full ordered-entry comparison vs candidate streaming witness reuse; mechanical sourceproof shared, not expert/sciencePASS',
      'RFL_candidate_oldchecker_main_solver_imported_or_executed':False})
if __name__=='__main__':main()
