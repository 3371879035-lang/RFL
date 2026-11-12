"""Full support ordered aggregation of stored root profiles; not native calibration."""
from collections import Counter
from fractions import Fraction
from hashlib import sha1,sha256
from itertools import product,chain
from math import gcd
import ast
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
    require(len(names)==1187,'runtime extent')
    return {'HEAD':head,'HEAD_bindings':1022,'runtime_inputs':1187,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}
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
def slice_mask(E,j):
    mask=0
    for i,r in enumerate(ROOTS):
        if (E>>i)&1 and (j!=1 or r[1]%2==0) and (j!=2 or r[1]%2==1) and (j!=5 or r[2]!=0):mask|=1<<i
    return mask
def descriptor(pre,post,mask,repeat):
    ordered=tuple(h if mask>>i&1 else None for i,h in enumerate(pre))
    changes=tuple((i,h) for i,h in enumerate(post) if mask>>i&1 and h!=pre[i])
    return mask,repeat,ordered,changes
def main():
    c=read(HERE/'contract.json');rc=read(HERE/'repair_contract.json');binding=bind(c);checks={}
    require(digest(HERE/'contract.json')==rc['original_contract_sha256'],'original contract unchanged')
    for name in ('support_check','profiles_check','values_check'):
        data=list(capture(c['stored'][name]));require(len(data)==1 and data[0][0]=='CHECK','old complete independent checker capture')
        checks[name]=data[0][1]
    cat={'D':{},'X':{}};hs=[];ws=[];kernels=[];lookup={};nums=Counter();hsum={t:sha256(b'[') for t in ('COMPLETE_LEGAL_DOMAIN','PRE_HISTORY','FULL_WORLD_OFFPROJECTION_SUPPORT')};entry=Counter()
    addressX={}
    for tag,o in capture(c['stored']['support']):
        if tag in hsum:addhash(hsum[tag],o,nums[tag]);nums[tag]+=1
        if tag=='COMPLETE_LEGAL_DOMAIN':
            cat[o['channel']][o['index']]=o
            if o['channel']=='X':addressX[tuple(o['address'])]=o['index']
        elif tag=='PRE_HISTORY':
            require(o['index']==len(hs),'ALL ordered pre histories')
            reads={'D':{},'X':{}}
            for row in o['complete_path']:
                s=tuple(cat['D'][row[0]]['address'][:5])+(row[1],)
                reads['D'][row[0]]=row[1];reads['X'][addressX[s]]=row[2]
            hs.append({'original':o,'reads':reads})
        elif tag=='FULL_WORLD_OFFPROJECTION_SUPPORT':
            r=o['region'];ch=r['projection_channel'];E=r['joint_region_root_mask_hex'];ids=o['all48_pre_history_indices'];ki=None
            entry['worlds']+=1
            # Independent incidence construction from each complete pre path, not stored masks.
            inc={}
            for i,hid in enumerate(ids):
                require(hs[hid]['original']['root']==list(ROOTS[i]),'all48 full ordered root identities')
                for site,cur in hs[hid]['reads'][ch].items():
                    if site not in inc:inc[site]=[cur,0]
                    require(inc[site][0]==cur,'single mapped output shared across roots')
                    inc[site][1]|=1<<i
            packed=[[s,v[0],f'{v[1]:012x}'] for s,v in sorted(inc.items())]
            require(packed==o['all_pre_consulted_site_root_masks'],'complete independent pre-reader incidence')
            if E is None:entry['null']+=1
            else:
                mask=int(E,16);key=(ch,mask,tuple(h if mask>>i&1 else None for i,h in enumerate(ids)))
                own={tuple(v) for v in r['complete_projection_owners']}
                required=[]
                for site,(cur,m) in sorted(inc.items()):
                    if m&mask and len(cat[ch][site]['full_legal_actions'])>1:
                        require(tuple(cat[ch][site]['address']) not in own,'every E probe is outside all S owners')
                        required.append((site,cur,m&mask))
                if key not in lookup:
                    lookup[key]=len(kernels);kernels.append({'key':key,'required':required,'members':0,'first':len(ws),'slices':o['six_support_slices']})
                ki=lookup[key];kernels[ki]['members']+=1;require(kernels[ki]['required']==required,'identical complete kernel descriptor retains complete required sites')
            ws.append({'original':o,'sha':sha256(canonical(o)).hexdigest(),'kernel':ki})
        elif tag=='FINAL':sf=o
    sourcehash={t:endhash(v) for t,v in hsum.items()}
    require(nums=={'COMPLETE_LEGAL_DOMAIN':19728,'PRE_HISTORY':67147,'FULL_WORLD_OFFPROJECTION_SUPPORT':68586},'all full original records')
    require(sourcehash['COMPLETE_LEGAL_DOMAIN']==sf['catalog_sha256']==checks['support_check']['catalog_sha256'] and sourcehash['PRE_HISTORY']==sf['history_registry_sha256']==checks['support_check']['history_registry_sha256'] and sourcehash['FULL_WORLD_OFFPROJECTION_SUPPORT']==sf['registry_sha256']==checks['support_check']['registry_sha256'],'old full registries')
    targetcounts=[sum(len(cat[k['key'][0]][s]['full_legal_actions'])-1 for s,cur,m in k['required']) for k in kernels]
    plan={**dict(entry),'kernels':len(kernels),'kernel_site_scopes':sum(len(k['required']) for k in kernels),'kernel_targets_allE':sum(targetcounts),'max_sites':max(len(k['required']) for k in kernels),'max_targets':max(targetcounts),'kernel_descriptor_sha256':sha256(canonical([list(k['key']) for k in kernels])).hexdigest()}
    require(plan==c['pre_only_plan'] and len(kernels)<=c['guard']['max_kernels'] and sum(targetcounts)<=c['guard']['max_kernel_targets'],'complete pre-only independent plan/guard')
    atoms={};decoder=[];psum=sha256(b'[');dsum=sha256(b'[');np=nd=0
    for tag,o in capture(c['stored']['profiles']):
        if tag=='ROOT_SITE_ALL_TARGET_PROFILE':
            addhash(psum,o,np);np+=1;hid=o['history_index'];ch=o['channel'];require(o['complete_pre_history_sha256']==sha256(canonical(hs[hid]['original'])).hexdigest(),'each profile complete actualpre')
            for atom in o['all_legal_target_atoms']:
                site=atom['site_index'];cur=hs[hid]['reads'][ch][site]
                require(atom['actual_pre_action']==cur and atom['target'] in cat[ch][site]['full_legal_actions'] and atom['target']!=cur,'all original legal-other atom identity')
                atoms[hid,ch,site,atom['target']]=atom['post']['return_hex']
        elif tag=='FULL_WORLD_PROFILE_DECODER':
            addhash(dsum,o,nd);require(o['world_projection_index']==nd and o['complete_original_support_row_sha256']==ws[nd]['sha'] and o['all48_actual_pre_history_indices']==ws[nd]['original']['all48_pre_history_indices'],'every original world decoder')
            decoder.append(sha256(canonical(o)).hexdigest());nd+=1
        elif tag=='FINAL':pf=o
    require(np==7188 and nd==68586 and len(atoms)==72432 and endhash(psum)==pf['profile_registry_sha256']==checks['profiles_check']['profile_registry_sha256'] and endhash(dsum)==pf['world_decoder_registry_sha256']==checks['profiles_check']['world_decoder_registry_sha256'],'all full profile source values and immutable checks')
    old={};vhash=sha256(b'[');nrows=nt=nz=0
    for tag,o in capture(c['stored']['values']):
        if tag!='ACTUAL_PRE_VALUE_AND_CALIBRATION_BATTERY':continue
        w=ws[nrows]['original'];require(w['region']==o['region'] and w['complete_old_value_battery_row_sha256']==sha256(canonical(o)).hexdigest(),'all old fixed value record binding')
        pre=o['actual_pre_root_return_hex'];require(pre==[hs[hid]['original']['return_hex'] for hid in w['all48_pre_history_indices']],'full literal pre values')
        for j,battery in enumerate(o['calibration_batteries']):
            nz+=battery['status']=='ALL_TARGETS_ZERO_UNCERTIFIED';require(battery['refinement']==REFS[j],'original refinement identity')
            mask=slice_mask(int(o['region']['joint_region_root_mask_hex'],16),j);repeat=60 if j in (3,4) else 120
            for t in battery['targets']:
                nt+=1;post=list(pre)
                for i,val,outcome in t['post_root_replacements']:post[i]=val
                d=descriptor(pre,post,mask,repeat)
                result={'ordered_pre_mean_hex':o['six_actual_pre_ordered_means_hex'][j],'ordered_post_mean_hex':t['ordered_post_mean_hex'],'dual_ordered_mean_response_hex':t['dual_ordered_mean_response_hex'],'paired_ordered_mean_response_hex':t['paired_ordered_mean_response_hex'],'exact_finite_float_response':t['exact_finite_float_response'],'response_sign':t['response_sign']}
                if d in old:require(old[d][0]==result,'ALL duplicate old ordered descriptors equal')
                else:old[d]=(result,[nrows,REFS[j],t['target'],sha256(canonical(t)).hexdigest()])
        addhash(vhash,o,nrows);nrows+=1
    require(nrows==68586 and nt==467314 and nz==2988 and endhash(vhash)==sf['source_v50_registry_sha256']==checks['values_check']['registry_sha256'],'complete old aggregates/targets/zero status untouched')
    source=capture(rc['original_failed_capture'],1)
    tag,original_binding=next(source)
    require(tag=='INPUT_BINDING_BEFORE' and original_binding['HEAD']==binding['HEAD'] and original_binding['runtime_inputs']==1179 and original_binding['HEAD_bindings']==1022 and len(original_binding['input_sha256'])==1179 and all(binding['input_sha256'][p]==h for p,h in original_binding['input_sha256'].items()),'ALL original failed-component runtime bytes remain unchanged')
    failed_exit=read(HERE/'evidence/exit.json');require(failed_exit['native_child_exit_code']==1 and failed_exit['files']['stderr.log']==rc['original_stderr'],'complete genuine original failure')
    expected_plan={'plan':plan,'all_kernel_descriptors':[list(k['key']) for k in kernels],'original_scene_key_order':['kappa','phase','error_flag','cause_rank','base_option'],'original_scene_count':5760,'six_original_refinements':REFS,'complete_support_counts':sf['counts'],'runtime_python':sys.version,'scope_uses_pre_only':True,'scientific_rules_adopted':False}
    require(next(source)==('AGGREGATION_PLAN_BEFORE_ARITHMETIC',expected_plan),'all support and resource plan emitted before any new arithmetic')
    completed=capture(['offprojection_aggregates_v53/evidence_completed',read(HERE/'evidence_completed/exit.json')['files']['stdout.log']['sha256']])
    require(next(completed)==('INPUT_BINDING_BEFORE',binding),'full original+repair storage completion binding')
    expected_chain={'original_native_child_exit_code':1,'original_stdout':failed_exit['files']['stdout.log'],'original_stderr':failed_exit['files']['stderr.log'],'original_completed_tag_counts':rc['original_completed_tags'],'original_runtime_inputs':1179,'original_executed_sources_unchanged':True,'completed_arithmetic_recomputed':0,'completed_kernels_recomputed':0,'original_checker_never_executed':True,'null_support_policy':'DEFINED_ONLY_COUNT_NULL_RETAINED_NOT_ZERO'}
    require(next(completed)==('PRESERVED_PARTIAL_COMPONENT_CHAIN',expected_chain),'storage-only completion retains genuine failure/no arithmetic rerun')
    source=chain(source,completed)
    scenes=list(product(range(2),range(6),range(2),range(60),range(4)));seqs={};vectors=[];arith=[];arithkeys={};stats=Counter();used=set();example={};regs={t:sha256(b'[') for t in ('ORDERED_PRE_VALUE_VECTOR','ORDERED_AGGREGATE_ARITHMETIC','COMPLETE_READ_TARGET_AGGREGATION_KERNEL','FULL_WORLD_AGGREGATE_DECODER')};sizes=Counter();kernel_index=world_index=0;premean={}
    def seq(mask,repeat):
        if (mask,repeat) not in seqs:
            ids=[]
            for k,p,e,r,z in scenes:
                i=24*k+4*p+z
                if mask>>i&1 and (repeat==120 or e==0):ids.append(i)
            seqs[mask,repeat]=ids
        return seqs[mask,repeat]
    def check_arithmetic(o):
        vi=o['pre_value_vector_reference'];mask,pre=vectors[vi];repeat=o['original_root_order_repetitions_per_phase'];require(repeat in (60,120),'original repetitions')
        post=list(pre)
        for i,h in o['inside_slice_changed_root_return_hex']:require(mask>>i&1 and h!=pre[i],'exact sparse root replacement');post[i]=h
        key=descriptor(pre,post,mask,repeat);ids=seq(mask,repeat);require(bool(ids) and len(ids)==o['scene_count'],'full original lex scene count')
        if key in old:result,ref=old[key];role='EXACT_OLD_FIXED_ORDERED_ARITHMETIC_REUSED';stats['old_arithmetic_records_reused']+=1
        else:
            # Independent explicit scene expansion and integer rational audit; never sum root probabilities.
            if (vi,repeat) not in premean:premean[vi,repeat]=sum(float.fromhex(pre[i]) for i in ids)/len(ids)
            a=premean[vi,repeat];postmean=sum(float.fromhex(post[i]) for i in ids)/len(ids)
            differences={i:float.fromhex(pre[i])-float.fromhex(post[i]) for i in set(ids)}
            pair=sum(differences[i] for i in ids)/len(ids)
            ratios={i:(float.fromhex(pre[i]).as_integer_ratio(),float.fromhex(post[i]).as_integer_ratio()) for i in set(ids)}
            den=max(d for values in ratios.values() for n,d in values)
            numerator=sum((ratios[i][0][0]*(den//ratios[i][0][1])-ratios[i][1][0]*(den//ratios[i][1][1])) for i in ids);den*=len(ids);g=gcd(numerator,den);exact=[numerator//g,den//g]
            result={'ordered_pre_mean_hex':a.hex(),'ordered_post_mean_hex':postmean.hex(),'dual_ordered_mean_response_hex':(a-postmean).hex(),'paired_ordered_mean_response_hex':pair.hex(),'exact_finite_float_response':exact,'response_sign':'positive' if numerator>0 else 'negative' if numerator<0 else 'zero'}
            ref=None;role='NEW_ORDERED_ARITHMETIC_FROM_STORED_PROFILES';stats['new_arithmetic_records']+=1
        sign=result['response_sign'];ez=result['exact_finite_float_response'][0]==0;dual=float.fromhex(result['dual_ordered_mean_response_hex']);pair=float.fromhex(result['paired_ordered_mean_response_hex']);changes=key[3]
        facts={'all_inside_root_return_differences_zero':not changes,'nonzero_root_changes_cancel_exactly':ez and bool(changes),'exact_zero_float_dual_nonzero':ez and dual!=0.,'exact_nonzero_float_dual_zero':not ez and dual==0.,'dual_sign_differs_from_exact':('positive' if dual>0 else 'negative' if dual<0 else 'zero')!=sign,'paired_sign_differs_from_exact':('positive' if pair>0 else 'negative' if pair<0 else 'zero')!=sign}
        expected={'index':len(arith),'pre_value_vector_reference':vi,'original_root_order_repetitions_per_phase':repeat,'scene_count':len(ids),'inside_slice_changed_root_return_hex':[list(v) for v in changes],'role':role,'old_target_reference':ref,**result,**facts}
        require(o==expected and key not in arithkeys,'ALL ordered float/paired/exact rational arithmetic, no duplicate computation')
        arithkeys[key]=len(arith);arith.append(o);require(len(arith)<=c['guard']['max_arithmetic_records'],'arithmetic guard')
    for tag,o in source:
        if tag in regs:addhash(regs[tag],o,sizes[tag]);sizes[tag]+=1
        if tag=='ORDERED_PRE_VALUE_VECTOR':
            mask=int(o['root_mask_hex'],16);pre=o['all48_inside_slice_pre_return_hex'];require(o['index']==len(vectors) and len(pre)==48 and all((v is not None)==bool(mask>>i&1) for i,v in enumerate(pre)),'full48 ordered pre vector no outside zero imputation')
            vectors.append((mask,pre));require(len(vectors)<=c['guard']['max_ordered_value_vectors'],'vector guard')
        elif tag=='ORDERED_AGGREGATE_ARITHMETIC':check_arithmetic(o)
        elif tag=='COMPLETE_READ_TARGET_AGGREGATION_KERNEL':
            k=kernels[kernel_index];ch,E,ids=k['key'];pre=[hs[h]['original']['return_hex'] if h is not None else None for h in ids];masks=[slice_mask(E,j) for j in range(6)];targetrows=[];kst=Counter();anyc=False
            for site,cur,reader in k['required']:
                for target in cat[ch][site]['full_legal_actions']:
                    if target==cur:continue
                    post=list(pre)
                    for i in range(48):
                        if reader>>i&1:post[i]=atoms[ids[i],ch,site,target]
                    refs=[]
                    for j,mask in enumerate(masks):
                        key=descriptor(pre,post,mask,60 if j in (3,4) else 120);require(key in arithkeys,'every legal target exact arithmetic descriptor exists');ai=arithkeys[key];refs.append(ai);used.add(ai)
                        if reader&mask:
                            r=arith[ai];kst['read_target_slices']+=1;kst['read_'+r['response_sign']]+=1
                            for name in ('all_inside_root_return_differences_zero','nonzero_root_changes_cancel_exactly','exact_zero_float_dual_nonzero','exact_nonzero_float_dual_zero','dual_sign_differs_from_exact','paired_sign_differs_from_exact'):kst[name]+=int(r[name])
                            if r['nonzero_root_changes_cancel_exactly'] and not anyc:
                                anyc=True;example.setdefault('first_nonzero_local_exact_aggregate_cancellation',{'first_world_projection_index':k['first'],'kernel_index':kernel_index,'channel':ch,'site_index':site,'actual_pre_action':cur,'target':target,'refinement':REFS[j],'arithmetic_reference':ai})
                    targetrows.append([site,cur,target,refs])
            require(len(targetrows)==targetcounts[kernel_index],'all legal other targets retained')
            for key,v in kst.items():stats['world_'+key]+=v*k['members']
            stats['kernel_targets']+=len(targetrows)
            expected={'index':kernel_index,'pre_only_descriptor':[ch,E,list(ids)],'first_world_projection_index':k['first'],'full_world_record_multiplicity_for_computation_only':k['members'],'six_original_slice_root_masks_hex':[f'{m:012x}' for m in masks],'target_row_columns':['site_index','actual_pre_output','target','six_ordered_arithmetic_references'],'all_legal_E_read_target_rows':targetrows,'all_pre_reader_masks_inside_E':[[s,cur,f'{m:012x}'] for s,cur,m in k['required']],'kernel_counts':dict(kst),'unread_complement_is_per_full_world_not_kernel':True,'native_calibration_certified':False}
            require(o==expected,'complete independent kernel rows/refinement support/target refs/no filtering');kernel_index+=1
        elif tag=='FULL_WORLD_AGGREGATE_DECODER':
            w=ws[world_index];orig=w['original']
            expected={'world_projection_index':world_index,'complete_v51_support_row_sha256':w['sha'],'complete_v52_decoder_row_sha256':decoder[world_index],'full_world_literal_sha256':orig['region']['full_world_literal_sha256'],'all48_actual_pre_history_indices':orig['all48_pre_history_indices'],'ordered_aggregate_kernel_reference':w['kernel'],'six_original_support_slices':orig['six_support_slices'],'all_old_fixed_battery_bindings':orig['prior_fixed_battery_bindings'],'entry_status':orig['region']['entry_status'],'null_projection_not_zero':w['kernel'] is None,'outside_E_effects_not_imputed_zero':True,'native_calibration_certified':False}
            require(o==expected,'every fullworld identity/Gamma/S/refinement/sentinel/null entry exactly preserved');world_index+=1
        elif tag=='INPUT_BINDING_AFTER':require(o==binding and bind(c)==binding,'full runtime stable beforeafter')
        elif tag=='FINAL':final=o
        else:raise AssertionError('unexpected output tag '+tag)
    require(kernel_index==3891 and world_index==68586 and used==set(range(len(arith))),'complete kernels/worlds/all arithmetic used')
    stats['world_unread_target_slices_identity_zero']=sum(v['unread_legal_targets_retained'] for w in ws if w['kernel'] is not None for v in w['original']['six_support_slices'])
    require(stats['world_read_target_slices']==195724060 and stats['world_unread_target_slices_identity_zero']==9429324920,'complete read/unread support including all zeros')
    reg={t:endhash(v) for t,v in regs.items()}
    require(final['plan']==plan and final['counts']==dict(stats) and final['registries']==reg and final['registry_sizes']==dict(sizes) and final['examples']==example and final['old_counts_retained']==sf['counts'],'complete FINAL all counts/cancellation/registries')
    require(final['source_profile_registry_sha256']==pf['profile_registry_sha256'] and final['source_world_decoder_registry_sha256']==pf['world_decoder_registry_sha256'] and final['source_support_registry_sha256']==sf['registry_sha256'] and final['source_v50_registry_sha256']==sf['source_v50_registry_sha256'] and final['old_arithmetic_descriptors_available']==len(old),'all stored sources exact')
    require(final['runtime_inputs']==1187 and final['parent_HEAD_bindings']==1022 and final['all_inputs_equal'],'runtime extent')
    require(final['original_component_runtime_inputs']==1179 and final['original_native_exit']==1 and final['storage_completion_only'] is True and final['completed_arithmetic_recomputed']==final['completed_kernels_recomputed']==0,'preserve completed prefix without rerun')
    require(sizes['ORDERED_PRE_VALUE_VECTOR']==747 and sizes['ORDERED_AGGREGATE_ARITHMETIC']==82685 and sizes['COMPLETE_READ_TARGET_AGGREGATION_KERNEL']==3891 and sizes['FULL_WORLD_AGGREGATE_DECODER']==68586,'all original completed prefix and new decoders')
    require(all(w['original']['six_support_slices'] is None for w in ws if w['kernel'] is None),'ALL861 null entries retained not zero')
    for name in ('new_root_predictions','new_RFL_kernel_steps','new_learner_rollouts','B1_arms','reference_DP','learner_DP','keys_allocated','random_draws','future_training'):require(final[name]==0,'no mechanism/training/key execution')
    for name in ('collector_executed','native_calibration_certified','scientific_rules_adopted','scientific_PASS','collection_authorized','research_complete','mechanism_direction_falsified'):require(final[name] is False,'not scientific certification/failure')
    for node in ast.walk(ast.parse((HERE/'check_stored_corrected.py').read_bytes())):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            names=[v.name.split('.')[0] for v in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]]
            require(all(n in {'collections','fractions','hashlib','itertools','math','pathlib','ast','json','subprocess','sys'} for n in names),'stdlib only no RFL/candidate/oldchecker/main/predictor imports')
    emit('CHECK',{'status':'COMPLETE_ALL_WORLD_SLICES_ORDERED_AGGREGATE_AUDIT_NOT_NATIVE_CALIBRATION','plan':plan,'counts':dict(stats),'registries':reg,'registry_sizes':dict(sizes),'examples':example,'old_counts_retained':sf['counts'],'runtime_inputs':1187,'parent_HEAD_bindings':1022,'distinct_checkout_validation_inputs':1191,'all_inputs_equal':True,'implementation_independence':'PRIMARY_ONLY_NOT_EXPERT','original_native_exit':1,'original_checker_never_executed':True,'storage_completion_only':True,'original_completed_arithmetic_recomputed':0,'source_profile_registry_sha256':pf['profile_registry_sha256'],'source_world_decoder_registry_sha256':pf['world_decoder_registry_sha256'],'source_support_registry_sha256':sf['registry_sha256'],'source_v50_registry_sha256':sf['source_v50_registry_sha256'],'native_calibration_certified':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()
