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
    require(len(names)==1179,'runtime extent')
    return {'HEAD':head,'HEAD_bindings':1022,'runtime_inputs':1179,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}
def capture(info):
    folder=PREP/info[0];cl=read(folder/'claim.json');ex=read(folder/'exit.json')
    require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items()),'stored claim/exit')
    require(ex['files']['stdout.log']['sha256']==info[1] and (folder/'stderr.log').stat().st_size==0,'stored identity')
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
    return (mask,repeat,vals,changes)
def main():
    c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    checks={}
    for name in ('support_check','profiles_check','values_check'):
        rows=list(capture(c['stored'][name]));require(len(rows)==1 and rows[0][0]=='CHECK','complete immutable old checker capture');checks[name]=rows[0][1]
    cat={'D':{},'X':{}};hs=[];worlds=[];kernels=[];lookup={};count=Counter();hashes={t:sha256(b'[') for t in ('COMPLETE_LEGAL_DOMAIN','PRE_HISTORY','FULL_WORLD_OFFPROJECTION_SUPPORT')};ns=Counter()
    for t,o in capture(c['stored']['support']):
        if t in hashes:addhash(hashes[t],o,ns[t]);ns[t]+=1
        if t=='COMPLETE_LEGAL_DOMAIN':cat[o['channel']][o['index']]=o
        elif t=='PRE_HISTORY':require(o['index']==len(hs),'all history order');hs.append(o)
        elif t=='FULL_WORLD_OFFPROJECTION_SUPPORT':
            region=o['region'];E=region['joint_region_root_mask_hex'];ch=region['projection_channel'];ids=o['all48_pre_history_indices'];ki=None
            count['worlds']+=1
            if E is None:count['null']+=1
            else:
                mask=int(E,16);key=(ch,mask,tuple(ids[i] if mask>>i&1 else None for i in range(48)))
                if key not in lookup:
                    ki=len(kernels);lookup[key]=ki
                    inc=[(s,cur,int(m,16)&mask) for s,cur,m in o['all_pre_consulted_site_root_masks'] if int(m,16)&mask and len(cat[ch][s]['full_legal_actions'])>1]
                    kernels.append({'key':key,'inc':inc,'first_world':len(worlds),'old_slices':o['six_support_slices'],'members':0})
                ki=lookup[key];kernels[ki]['members']+=1
            worlds.append({'original':o,'old_sha':sha256(canonical(o)).hexdigest(),'kernel':ki})
        elif t=='FINAL':supportfinal=o
    ds={t:endhash(h) for t,h in hashes.items()}
    require(ns=={'COMPLETE_LEGAL_DOMAIN':19728,'PRE_HISTORY':67147,'FULL_WORLD_OFFPROJECTION_SUPPORT':68586},'all original support retained')
    require(ds['COMPLETE_LEGAL_DOMAIN']==supportfinal['catalog_sha256']==checks['support_check']['catalog_sha256'] and ds['PRE_HISTORY']==supportfinal['history_registry_sha256']==checks['support_check']['history_registry_sha256'] and ds['FULL_WORLD_OFFPROJECTION_SUPPORT']==supportfinal['registry_sha256']==checks['support_check']['registry_sha256'],'full source registry bindings')
    sitecounts=[len(k['inc']) for k in kernels];targetcounts=[sum(len(cat[k['key'][0]][s]['full_legal_actions'])-1 for s,cur,m in k['inc']) for k in kernels]
    plan={**dict(count),'kernels':len(kernels),'kernel_site_scopes':sum(sitecounts),'kernel_targets_allE':sum(targetcounts),'max_sites':max(sitecounts),'max_targets':max(targetcounts),'kernel_descriptor_sha256':sha256(canonical([list(k['key']) for k in kernels])).hexdigest()}
    require(plan==c['pre_only_plan'],'full pre-only prospective kernel plan')
    require(len(kernels)<=c['guard']['max_kernels'] and sum(targetcounts)<=c['guard']['max_kernel_targets'],'prospective resource guard before new arithmetic')
    emit('AGGREGATION_PLAN_BEFORE_ARITHMETIC',{'plan':plan,'all_kernel_descriptors':[list(k['key']) for k in kernels],'original_scene_key_order':['kappa','phase','error_flag','cause_rank','base_option'],'original_scene_count':5760,'six_original_refinements':REFS,'complete_support_counts':supportfinal['counts'],'runtime_python':sys.version,'scope_uses_pre_only':True,'scientific_rules_adopted':False})
    # Read stored profiles, never invoke predictor, old checker or RFL.
    atoms={};decoder=[];profilehash=sha256(b'[');worldhash=sha256(b'[');np=0;nd=0
    for t,o in capture(c['stored']['profiles']):
        if t=='ROOT_SITE_ALL_TARGET_PROFILE':
            addhash(profilehash,o,np);np+=1;hid=o['history_index'];ch=o['channel'];require(o['complete_pre_history_sha256']==sha256(canonical(hs[hid])).hexdigest(),'full pre history for stored profile')
            for v in o['all_legal_target_atoms']:atoms[hid,ch,v['site_index'],v['target']]=v['post']['return_hex']
        elif t=='FULL_WORLD_PROFILE_DECODER':
            addhash(worldhash,o,nd);require(o['world_projection_index']==nd and o['complete_original_support_row_sha256']==worlds[nd]['old_sha'],'all complete decoder row bindings')
            decoder.append(sha256(canonical(o)).hexdigest());nd+=1
        elif t=='FINAL':profilefinal=o
    require(np==7188 and nd==68586 and len(atoms)==72432 and endhash(profilehash)==profilefinal['profile_registry_sha256']==checks['profiles_check']['profile_registry_sha256'] and endhash(worldhash)==profilefinal['world_decoder_registry_sha256']==checks['profiles_check']['world_decoder_registry_sha256'],'all stored profiles/zeros/decoder identity')
    # Exact matching prior aggregation values are read-only reused, not recomputed.
    old={};vhash=sha256(b'[');nr=0;nt=0;nz=0
    for t,o in capture(c['stored']['values']):
        if t!='ACTUAL_PRE_VALUE_AND_CALIBRATION_BATTERY':continue
        w=worlds[nr]['original'];require(o['region']==w['region'] and sha256(canonical(o)).hexdigest()==w['complete_old_value_battery_row_sha256'],'all old complete value rows')
        pre=o['actual_pre_root_return_hex'];require(pre==[hs[h]['return_hex'] for h in w['all48_pre_history_indices']],'actual full pre value map')
        if o['calibration_batteries']:
            E=int(o['region']['joint_region_root_mask_hex'],16)
            for j,battery in enumerate(o['calibration_batteries']):
                require(battery['refinement']==REFS[j],'original refinement order');nz+=battery['status']=='ALL_TARGETS_ZERO_UNCERTIFIED';mask=mask_for(E,j);repeat=60 if j in (3,4) else 120
                for target in battery['targets']:
                    nt+=1;post=list(pre)
                    for i,h,out in target['post_root_replacements']:post[i]=h
                    key=arithmetic_key(pre,post,mask,repeat)
                    result={'ordered_pre_mean_hex':o['six_actual_pre_ordered_means_hex'][j],'ordered_post_mean_hex':target['ordered_post_mean_hex'],'dual_ordered_mean_response_hex':target['dual_ordered_mean_response_hex'],'paired_ordered_mean_response_hex':target['paired_ordered_mean_response_hex'],'exact_finite_float_response':target['exact_finite_float_response'],'response_sign':target['response_sign']}
                    if key in old:require(old[key][0]==result,'same ordered arithmetic descriptor old values agree')
                    else:old[key]=(result,[nr,REFS[j],target['target'],sha256(canonical(target)).hexdigest()])
        addhash(vhash,o,nr);nr+=1
    require(nr==68586 and nt==467314 and nz==2988 and endhash(vhash)==supportfinal['source_v50_registry_sha256']==checks['values_check']['registry_sha256'],'ALL old fixed targets/zero batteries remain unchanged')
    vectors={};arithmetic={};records=[];sequences={};premeans={};registry={t:sha256(b'[') for t in ('ORDERED_PRE_VALUE_VECTOR','ORDERED_AGGREGATE_ARITHMETIC','COMPLETE_READ_TARGET_AGGREGATION_KERNEL','FULL_WORLD_AGGREGATE_DECODER')};sizes=Counter();stats=Counter();examples={}
    def publish(tag,o):emit(tag,o);addhash(registry[tag],o,sizes[tag]);sizes[tag]+=1
    def aggregate(pre,post,mask,repeat):
        key=arithmetic_key(pre,post,mask,repeat)
        if key in arithmetic:return arithmetic[key]
        vm=(mask,key[2])
        if vm not in vectors:
            vi=len(vectors);vectors[vm]=vi;publish('ORDERED_PRE_VALUE_VECTOR',{'index':vi,'root_mask_hex':f'{mask:012x}','all48_inside_slice_pre_return_hex':list(key[2])})
            require(len(vectors)<=c['guard']['max_ordered_value_vectors'],'complete pre vector guard, never trim')
        vi=vectors[vm]
        if (mask,repeat) not in sequences:
            sequences[mask,repeat]=tuple(4*(6*k+p)+z for k in range(2) for p in range(6) for tick in range(repeat) for z in range(4) if mask>>(4*(6*k+p)+z)&1)
        seq=sequences[mask,repeat];require(bool(seq),'nonempty original slice')
        if key in old:result,ref=old[key];result=dict(result);role='EXACT_OLD_FIXED_ORDERED_ARITHMETIC_REUSED';stats['old_arithmetic_records_reused']+=1
        else:
            pv=[float.fromhex(h) if h is not None else 0. for h in key[2]];qv=list(pv)
            for i,h in key[3]:qv[i]=float.fromhex(h)
            if (vi,repeat) not in premeans:premeans[vi,repeat]=sum(pv[i] for i in seq)/len(seq)
            a=premeans[vi,repeat];b=sum(qv[i] for i in seq)/len(seq);paired=sum(pv[i]-qv[i] for i in seq)/len(seq)
            mult=Counter(seq);exact=sum(((Fraction(pv[i])-Fraction(qv[i]))*n for i,n in mult.items()),Fraction(0))/len(seq)
            result={'ordered_pre_mean_hex':a.hex(),'ordered_post_mean_hex':b.hex(),'dual_ordered_mean_response_hex':(a-b).hex(),'paired_ordered_mean_response_hex':paired.hex(),'exact_finite_float_response':[exact.numerator,exact.denominator],'response_sign':'positive' if exact>0 else 'negative' if exact<0 else 'zero'}
            ref=None;role='NEW_ORDERED_ARITHMETIC_FROM_STORED_PROFILES';stats['new_arithmetic_records']+=1
        exactzero=result['exact_finite_float_response'][0]==0;dual=float.fromhex(result['dual_ordered_mean_response_hex']);paired=float.fromhex(result['paired_ordered_mean_response_hex']);sign=result['response_sign']
        facts={'all_inside_root_return_differences_zero':not key[3],'nonzero_root_changes_cancel_exactly':exactzero and bool(key[3]),'exact_zero_float_dual_nonzero':exactzero and dual!=0.,'exact_nonzero_float_dual_zero':not exactzero and dual==0.,'dual_sign_differs_from_exact':('positive' if dual>0 else 'negative' if dual<0 else 'zero')!=sign,'paired_sign_differs_from_exact':('positive' if paired>0 else 'negative' if paired<0 else 'zero')!=sign}
        ai=len(arithmetic);arithmetic[key]=ai;record={'index':ai,'pre_value_vector_reference':vi,'original_root_order_repetitions_per_phase':repeat,'scene_count':len(seq),'inside_slice_changed_root_return_hex':[list(v) for v in key[3]],'role':role,'old_target_reference':ref,**result,**facts};records.append(record);publish('ORDERED_AGGREGATE_ARITHMETIC',record)
        require(len(arithmetic)<=c['guard']['max_arithmetic_records'],'complete ordered arithmetic guard, no support pruning')
        return ai
    for ki,k in enumerate(kernels):
        ch,E,ids=k['key'];pre=[hs[h]['return_hex'] if h is not None else None for h in ids];masks=[mask_for(E,j) for j in range(6)];targetrows=[];kst=Counter();anyc=False
        for site,cur,reader in k['inc']:
            for target in cat[ch][site]['full_legal_actions']:
                if target==cur:continue
                post=list(pre)
                for i in range(48):
                    if reader>>i&1:post[i]=atoms[ids[i],ch,site,target]
                refs=[]
                for j,mask in enumerate(masks):
                    ai=aggregate(pre,post,mask,60 if j in (3,4) else 120);refs.append(ai)
                    if reader&mask:
                        r=records[ai];kst['read_target_slices']+=1;kst['read_'+r['response_sign']]+=1
                        for name in ('all_inside_root_return_differences_zero','nonzero_root_changes_cancel_exactly','exact_zero_float_dual_nonzero','exact_nonzero_float_dual_zero','dual_sign_differs_from_exact','paired_sign_differs_from_exact'):kst[name]+=int(r[name])
                        if r['nonzero_root_changes_cancel_exactly'] and not anyc:
                            anyc=True;example={'first_world_projection_index':k['first_world'],'kernel_index':ki,'channel':ch,'site_index':site,'actual_pre_action':cur,'target':target,'refinement':REFS[j],'arithmetic_reference':ai}
                            examples.setdefault('first_nonzero_local_exact_aggregate_cancellation',example)
                targetrows.append([site,cur,target,refs])
        require(len(targetrows)==targetcounts[ki],'ALL targets exactly once')
        for key,v in kst.items():stats['world_'+key]+=v*k['members']
        stats['kernel_targets']+=len(targetrows)
        publish('COMPLETE_READ_TARGET_AGGREGATION_KERNEL',{'index':ki,'pre_only_descriptor':[ch,E,list(ids)],'first_world_projection_index':k['first_world'],'full_world_record_multiplicity_for_computation_only':k['members'],'six_original_slice_root_masks_hex':[f'{m:012x}' for m in masks],'target_row_columns':['site_index','actual_pre_output','target','six_ordered_arithmetic_references'],'all_legal_E_read_target_rows':targetrows,'all_pre_reader_masks_inside_E':[[s,cur,f'{m:012x}'] for s,cur,m in k['inc']],'kernel_counts':dict(kst),'unread_complement_is_per_full_world_not_kernel':True,'native_calibration_certified':False})
    stats['world_unread_target_slices_identity_zero']=sum(s['unread_legal_targets_retained'] for w in worlds for s in w['original']['six_support_slices'])
    require(stats['world_read_target_slices']==195724060 and stats['world_unread_target_slices_identity_zero']==9429324920,'ALL read and unread complete target-slice support')
    for wi,w in enumerate(worlds):
        o=w['original'];publish('FULL_WORLD_AGGREGATE_DECODER',{'world_projection_index':wi,'complete_v51_support_row_sha256':w['old_sha'],'complete_v52_decoder_row_sha256':decoder[wi],'full_world_literal_sha256':o['region']['full_world_literal_sha256'],'all48_actual_pre_history_indices':o['all48_pre_history_indices'],'ordered_aggregate_kernel_reference':w['kernel'],'six_original_support_slices':o['six_support_slices'],'all_old_fixed_battery_bindings':o['prior_fixed_battery_bindings'],'entry_status':o['region']['entry_status'],'null_projection_not_zero':w['kernel'] is None,'outside_E_effects_not_imputed_zero':True,'native_calibration_certified':False})
    after=bind(c);require(before==after,'all complete runtime bytes unchanged');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'COMPLETE_ALL_SUPPORT_ORDERED_SOURCE_AGGREGATES_NOT_NATIVE_CALIBRATION','plan':plan,'counts':dict(stats),'registries':{t:endhash(h) for t,h in registry.items()},'registry_sizes':dict(sizes),'examples':examples,'old_counts_retained':supportfinal['counts'],'source_profile_registry_sha256':profilefinal['profile_registry_sha256'],'source_world_decoder_registry_sha256':profilefinal['world_decoder_registry_sha256'],'source_support_registry_sha256':supportfinal['registry_sha256'],'source_v50_registry_sha256':supportfinal['source_v50_registry_sha256'],'old_arithmetic_descriptors_available':len(old),'ordered_sequence_cache_entries':len(sequences),'ordered_pre_mean_cache_entries':len(premeans),'runtime_inputs':1179,'parent_HEAD_bindings':1022,'all_inputs_equal':True,'new_root_predictions':0,'new_RFL_kernel_steps':0,'new_learner_rollouts':0,'B1_arms':0,'reference_DP':0,'learner_DP':0,'keys_allocated':0,'random_draws':0,'future_training':0,'collector_executed':False,'native_calibration_certified':False,'scientific_rules_adopted':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False,'mechanism_direction_falsified':False})
if __name__=='__main__':main()
