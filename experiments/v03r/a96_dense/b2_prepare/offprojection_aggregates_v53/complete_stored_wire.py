"""Full support ordered aggregation of stored root profiles; not native calibration."""
from collections import Counter
from fractions import Fraction
from hashlib import sha1,sha256
from itertools import product
from pathlib import Path
import json,subprocess,sys
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]
OUT_BYTES=0
def read(p):return json.loads(p.read_bytes())
def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def require(ok,why):
    if not ok:raise AssertionError(why)
def emit(t,o):
    global OUT_BYTES
    b=t+'='+canonical(o).decode().rstrip('\n');OUT_BYTES+=len(b.encode())+2
    require(OUT_BYTES<=3000000000,'prospective complete output byte guard; no trimming')
    print(b,flush=True)
def digest(p,blob=False):
    h=sha1(b'blob '+str(p.stat().st_size).encode()+b'\0') if blob else sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def bind(c):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'parentHEAD')
    tree={v.split(b'\t')[1].decode():v.split()[2].decode() for v in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if v}
    source=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources'];a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes'];prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(source)|prior|{'experiments/rebuild_status_current.json'}
    require((len(source),len(native),len(prior),len(bound))==(313,153,708,1022),'parent extent')
    for p in bound:require(digest(ROOT/p,True)==tree[p],'HEAD byte '+p)
    for p,h in (source|native).items():require(digest(ROOT/p)==h,'frozen/native '+p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    names|={(HERE/n).relative_to(ROOT).as_posix() for n in ('repair_contract.json','complete_stored.py','execute_completion.py','check_stored_corrected.py','evidence/claim.json','evidence/exit.json','evidence/stdout.log','evidence/stderr.log')}
    names|={(HERE/n).relative_to(ROOT).as_posix() for n in ('normalization_contract.json','complete_stored_canonical.py','execute_completion_canonical.py','check_stored_canonical.py','evidence_completed/claim.json','evidence_completed/exit.json','evidence_completed/stdout.log','evidence_completed/stderr.log')}
    names|={(HERE/n).relative_to(ROOT).as_posix() for n in ('wire_contract.json','complete_stored_wire.py','execute_completion_wire.py','check_stored_wire.py','evidence_final/claim.json','evidence_final/exit.json','evidence_final/stdout.log','evidence_final/stderr.log')}
    require(len(names)==1203,'runtime extent')
    return {'HEAD':head,'HEAD_bindings':1022,'runtime_inputs':1203,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}
def capture(info,expected_exit=0):
    folder=PREP/info[0];cl=read(folder/'claim.json');ex=read(folder/'exit.json')
    require(ex['native_child_exit_code']==expected_exit and all(ex[k]==v for k,v in cl.items()),'stored claim/exit')
    require(ex['files']['stdout.log']['sha256']==info[1] and (expected_exit!=0 or (folder/'stderr.log').stat().st_size==0),'stored identity')
    for n,v in ex['files'].items():require({'bytes':(folder/n).stat().st_size,'sha256':digest(folder/n)}==v,'full stored bytes')
    for n,h in ex['inputs'].items():require(digest(folder.parent/n)==h,'executed source immutable')
    with (folder/'stdout.log').open('rb') as f:
        for l in f:
            require(l.endswith(b'\n'),'complete EOF line');t,v=l.rstrip(b'\r\n').split(b'=',1);o=json.loads(v)
            require(canonical(o).rstrip(b'\n')==v,'full canonical JSON')
            yield t.decode(),o
def addhash(h,o,i):h.update((b',' if i else b'')+canonical(o).rstrip(b'\n'))
def endhash(h):h.update(b']\n');return h.hexdigest()

ROOTS=list(product(range(2),range(6),range(4)))
REFS=['eligible_all','eligible_phase_even','eligible_phase_odd','eligible_cause_rank_lower','eligible_error_absent','eligible_base_option_nonzero']
def mask_for(E,j):return sum(1<<i for i,(k,p,z) in enumerate(ROOTS) if E>>i&1 and (True,p%2==0,p%2==1,True,True,z!=0)[j])
def arithmetic_key(pre,post,mask,repeat):
    vals=tuple(pre[i] if mask>>i&1 else None for i in range(48));changes=tuple((i,post[i]) for i in range(48) if mask>>i&1 and post[i]!=pre[i])
    return mask,repeat,vals,changes
def main():
    c=read(HERE/'contract.json');rc=read(HERE/'repair_contract.json');nc=read(HERE/'normalization_contract.json');wc=read(HERE/'wire_contract.json');require(digest(HERE/'contract.json')==rc['original_contract_sha256'],'original contract bytes')
    before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    second_completion=list(capture(wc['second_completion_failed_capture'],1));require(len(second_completion)==1 and second_completion[0][0]=='INPUT_BINDING_BEFORE','second failed completion did no decoder/arithmetic')
    require(read(HERE/'evidence_final/exit.json')['files']['stderr.log']==wc['second_completion_stderr'],'preserve second completion failure')
    require(all(before['input_sha256'][p]==h for p,h in second_completion[0][1]['input_sha256'].items()),'all second completion runtime unchanged')
    first_completion=list(capture(nc['first_completion_failed_capture'],1));require(len(first_completion)==1 and first_completion[0][0]=='INPUT_BINDING_BEFORE','incomplete first completion did no decoder/arithmetic')
    require(read(HERE/'evidence_completed/exit.json')['files']['stderr.log']==nc['first_completion_stderr'],'preserve first completion failure bytes')
    require(all(before['input_sha256'][p]==h for p,h in first_completion[0][1]['input_sha256'].items()),'ALL first completion runtime bytes unchanged')
    checks={}
    for n in ('support_check','profiles_check','values_check'):
        data=list(capture(c['stored'][n]));require(len(data)==1 and data[0][0]=='CHECK','old independent stored checker')
        checks[n]=data[0][1]
    ws=[];hs=[];lookup={};descriptors=[];supporthash=sha256(b'[');ns=0
    for t,o in capture(c['stored']['support']):
        if t=='PRE_HISTORY':require(o['index']==len(hs),'full history order');hs.append(o)
        elif t=='FULL_WORLD_OFFPROJECTION_SUPPORT':
            addhash(supporthash,o,ns);ns+=1;r=o['region'];E=r['joint_region_root_mask_hex'];ki=None;ids=o['all48_pre_history_indices']
            if E is None:require(o['six_support_slices'] is None,'null support is null, never zero aggregate')
            else:
                mask=int(E,16);key=(r['projection_channel'],mask,tuple(h if mask>>i&1 else None for i,h in enumerate(ids)))
                if key not in lookup:lookup[key]=len(descriptors);descriptors.append(json.loads(canonical(list(key))))
                ki=lookup[key]
            ws.append({'original':o,'sha':sha256(canonical(o)).hexdigest(),'kernel':ki})
        elif t=='FINAL':sf=o
    require(len(ws)==68586 and endhash(supporthash)==sf['registry_sha256']==checks['support_check']['registry_sha256'],'ALL support exact')
    decoders=[];ph=sha256(b'[');dh=sha256(b'[');np=nd=0
    for t,o in capture(c['stored']['profiles']):
        if t=='ROOT_SITE_ALL_TARGET_PROFILE':addhash(ph,o,np);np+=1
        elif t=='FULL_WORLD_PROFILE_DECODER':
            require(o['world_projection_index']==nd and o['complete_original_support_row_sha256']==ws[nd]['sha'],'every stored decoder binding')
            addhash(dh,o,nd);decoders.append(sha256(canonical(o)).hexdigest());nd+=1
        elif t=='FINAL':pf=o
    require(np==7188 and nd==68586 and endhash(ph)==pf['profile_registry_sha256']==checks['profiles_check']['profile_registry_sha256'] and endhash(dh)==pf['world_decoder_registry_sha256']==checks['profiles_check']['world_decoder_registry_sha256'],'full old profile registries')
    oldkeys=set();vh=sha256(b'[');nr=nt=nz=0
    for t,o in capture(c['stored']['values']):
        if t!='ACTUAL_PRE_VALUE_AND_CALIBRATION_BATTERY':continue
        w=ws[nr]['original'];require(o['region']==w['region'] and sha256(canonical(o)).hexdigest()==w['complete_old_value_battery_row_sha256'],'every old fixed battery row')
        pre=o['actual_pre_root_return_hex'];require(pre==[hs[h]['return_hex'] for h in w['all48_pre_history_indices']],'full actualpre')
        for j,b in enumerate(o['calibration_batteries']):
            nz+=b['status']=='ALL_TARGETS_ZERO_UNCERTIFIED';E=int(o['region']['joint_region_root_mask_hex'],16)
            for target in b['targets']:
                nt+=1;post=list(pre)
                for i,h,out in target['post_root_replacements']:post[i]=h
                oldkeys.add(arithmetic_key(pre,post,mask_for(E,j),60 if j in (3,4) else 120))
        addhash(vh,o,nr);nr+=1
    require(nr==68586 and nt==467314 and nz==2988 and endhash(vh)==sf['source_v50_registry_sha256']==checks['values_check']['registry_sha256'],'ALL old fixed values retained, no arithmetic recomputation')
    regs={t:sha256(b'[') for t in ('ORDERED_PRE_VALUE_VECTOR','ORDERED_AGGREGATE_ARITHMETIC','COMPLETE_READ_TARGET_AGGREGATION_KERNEL','FULL_WORLD_AGGREGATE_DECODER')};sizes=Counter();tags=Counter();stats=Counter();examples={};vecs=[];sequences=set();premean_keys=set();arithmetic=[]
    original_binding=None;plan=None
    for t,o in capture(rc['original_failed_capture'],1):
        tags[t]+=1
        if t in regs:addhash(regs[t],o,sizes[t]);sizes[t]+=1
        if t=='INPUT_BINDING_BEFORE':
            original_binding=o;require(o['runtime_inputs']==1179 and o['HEAD_bindings']==1022 and o['HEAD']==before['HEAD'] and len(o['input_sha256'])==1179 and all(before['input_sha256'][p]==h for p,h in o['input_sha256'].items()),'ALL original runtime bytes unchanged after failed child')
        elif t=='AGGREGATION_PLAN_BEFORE_ARITHMETIC':
            require(o['plan']==c['pre_only_plan'] and canonical(o['all_kernel_descriptors'])==canonical(descriptors),'original complete pre-only plan untouched');plan=o['plan']
        elif t=='ORDERED_PRE_VALUE_VECTOR':require(o['index']==len(vecs),'full stored vector order');vecs.append(o)
        elif t=='ORDERED_AGGREGATE_ARITHMETIC':
            require(o['index']==len(arithmetic),'full completed arithmetic order');arithmetic.append(o)
            key=(int(vecs[o['pre_value_vector_reference']]['root_mask_hex'],16),o['original_root_order_repetitions_per_phase']);sequences.add(key)
            if o['role']=='EXACT_OLD_FIXED_ORDERED_ARITHMETIC_REUSED':stats['old_arithmetic_records_reused']+=1
            elif o['role']=='NEW_ORDERED_ARITHMETIC_FROM_STORED_PROFILES':stats['new_arithmetic_records']+=1;premean_keys.add((o['pre_value_vector_reference'],o['original_root_order_repetitions_per_phase']))
            else:raise AssertionError('unknown stored arithmetic role')
        elif t=='COMPLETE_READ_TARGET_AGGREGATION_KERNEL':
            require(o['index']==sizes[t]-1 and o['pre_only_descriptor']==descriptors[o['index']],'full complete original kernel')
            for k,v in o['kernel_counts'].items():stats['world_'+k]+=v*o['full_world_record_multiplicity_for_computation_only']
            stats['kernel_targets']+=len(o['all_legal_E_read_target_rows'])
            if 'first_nonzero_local_exact_aggregate_cancellation' not in examples:
                for site,cur,target,refs in o['all_legal_E_read_target_rows']:
                    for j,ai in enumerate(refs):
                        if arithmetic[ai]['nonzero_root_changes_cancel_exactly']:
                            examples['first_nonzero_local_exact_aggregate_cancellation']={'first_world_projection_index':o['first_world_projection_index'],'kernel_index':o['index'],'channel':o['pre_only_descriptor'][0],'site_index':site,'actual_pre_action':cur,'target':target,'refinement':REFS[j],'arithmetic_reference':ai};break
                    if examples:break
        else:raise AssertionError('failed prefix must contain no decoder/after-binding/FINAL')
    require(dict(tags)==rc['original_completed_tags'] and original_binding is not None and plan is not None,'complete original failed prefix retained')
    ex=read(HERE/'evidence/exit.json');require(ex['files']['stderr.log']==rc['original_stderr'] and ex['native_child_exit_code']==1,'true original failure retained')
    emit('PRESERVED_PARTIAL_COMPONENT_CHAIN',{'original_native_child_exit_code':1,'original_stdout':ex['files']['stdout.log'],'original_stderr':ex['files']['stderr.log'],'original_completed_tag_counts':dict(tags),'original_runtime_inputs':1179,'original_executed_sources_unchanged':True,'completed_arithmetic_recomputed':0,'completed_kernels_recomputed':0,'original_checker_never_executed':True,'null_support_policy':'DEFINED_ONLY_COUNT_NULL_RETAINED_NOT_ZERO'})
    unread=0
    for wi,w in enumerate(ws):
        o=w['original']
        if w['kernel'] is not None:unread+=sum(s['unread_legal_targets_retained'] for s in o['six_support_slices'])
        record={'world_projection_index':wi,'complete_v51_support_row_sha256':w['sha'],'complete_v52_decoder_row_sha256':decoders[wi],'full_world_literal_sha256':o['region']['full_world_literal_sha256'],'all48_actual_pre_history_indices':o['all48_pre_history_indices'],'ordered_aggregate_kernel_reference':w['kernel'],'six_original_support_slices':o['six_support_slices'],'all_old_fixed_battery_bindings':o['prior_fixed_battery_bindings'],'entry_status':o['region']['entry_status'],'null_projection_not_zero':w['kernel'] is None,'outside_E_effects_not_imputed_zero':True,'native_calibration_certified':False}
        emit('FULL_WORLD_AGGREGATE_DECODER',record);addhash(regs['FULL_WORLD_AGGREGATE_DECODER'],record,sizes['FULL_WORLD_AGGREGATE_DECODER']);sizes['FULL_WORLD_AGGREGATE_DECODER']+=1
    stats['world_unread_target_slices_identity_zero']=unread
    require(stats['world_read_target_slices']==195724060 and unread==9429324920,'ALL complete defined read/unread support, null retained')
    after=bind(c);require(before==after,'all original+repair runtime bytes unchanged');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'COMPLETE_ALL_SUPPORT_ORDERED_SOURCE_AGGREGATES_NOT_NATIVE_CALIBRATION','plan':plan,'counts':dict(stats),'registries':{t:endhash(h) for t,h in regs.items()},'registry_sizes':dict(sizes),'examples':examples,'old_counts_retained':sf['counts'],'source_profile_registry_sha256':pf['profile_registry_sha256'],'source_world_decoder_registry_sha256':pf['world_decoder_registry_sha256'],'source_support_registry_sha256':sf['registry_sha256'],'source_v50_registry_sha256':sf['source_v50_registry_sha256'],'old_arithmetic_descriptors_available':len(oldkeys),'ordered_sequence_cache_entries':len(sequences),'ordered_pre_mean_cache_entries':len(premean_keys),'runtime_inputs':1203,'parent_HEAD_bindings':1022,'original_component_runtime_inputs':1179,'original_native_exit':1,'storage_completion_only':True,'first_storage_completion_native_exit':1,'canonical_plan_normalization_only':True,'second_storage_completion_native_exit':1,'deep_kernel_wire_normalization_only':True,'completed_arithmetic_recomputed':0,'completed_kernels_recomputed':0,'all_inputs_equal':True,'new_root_predictions':0,'new_RFL_kernel_steps':0,'new_learner_rollouts':0,'B1_arms':0,'reference_DP':0,'learner_DP':0,'keys_allocated':0,'random_draws':0,'future_training':0,'collector_executed':False,'native_calibration_certified':False,'scientific_rules_adopted':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False,'mechanism_direction_falsified':False})
if __name__=='__main__':main()

