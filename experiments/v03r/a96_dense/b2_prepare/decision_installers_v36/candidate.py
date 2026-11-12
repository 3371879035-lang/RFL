"""Complete only v33's never-executed Decision native installer phase."""
from collections import Counter
from fractions import Fraction
from hashlib import sha1, sha256
from pathlib import Path
import json, subprocess, sys
from unittest.mock import patch
HERE=Path(__file__).resolve().parent; PREP=HERE.parent; ROOT=HERE.parents[4]
sys.path.insert(0,str(PREP)); sys.path.insert(0,str(ROOT/'src'))
import factual_event_candidate as factual
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import Q, DECISION, Edit, QAddress, DecisionAddress, LearnerPersistentState

def canonical(o): return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def emit(t,o): print(t+'='+canonical(o).decode().rstrip('\n'),flush=True)
def require(ok,why):
    if not ok: raise AssertionError(why)
def read(p): return json.loads(p.read_bytes())
def frac(f): return [f.numerator,f.denominator]

def records(info):
    p=PREP/info['folder']; cl,ex=read(p/'claim.json'),read(p/'exit.json')
    require(ex['native_child_exit_code']==info['exit'] and all(ex[k]==v for k,v in cl.items()),'stored receipt')
    for n,v in ex['files'].items():
        b=(p/n).read_bytes(); require({'bytes':len(b),'sha256':sha256(b).hexdigest()}==v,'stored raw bytes')
    require(ex['files']['stdout.log']['sha256']==info['stdout_sha256'],'stored stdout binding')
    if info['exit']:
        require(ex['files']['stderr.log']['sha256']==info['stderr_sha256'],'authentic old failure')
    else: require(not (p/'stderr.log').read_bytes(),'stored unexpected stderr')
    out=[]
    for line in (p/'stdout.log').read_bytes().splitlines():
        if b'=' in line:
            t,v=line.split(b'=',1)
            if v[:1] in (b'[',b'{'): out.append((t.decode(),json.loads(v)))
    return out

def bind(c):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(head==c['parent_commit'],'parent drift')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound))==(313,153,419,733),'parent extent')
    for p in bound:
        b=(ROOT/p).read_bytes(); require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native).items(): require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==890,'runtime extent')
    return {'parent_HEAD':head,'HEAD_byte_bindings':733,'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}

def main():
    c=read(HERE/'contract.json'); before=bind(c); emit('INPUT_BINDING_BEFORE',before)
    cat=records(c['stored']['catalog']); D=[o for t,o in cat if t=='DECISION_CONTEXT']
    q={tuple(r['context']):{a:float.fromhex(v) for a,v in r['q_row_hex']} for r in D}
    bs=next(o['entries'] for t,o in records(c['stored']['basis']) if t=='NATIVE_BASIS')
    keys=[(b['kappa'],b['phase'],b['committed']) for b in bs]
    oldpred=records(c['stored']['prediction'])
    complete=[o for t,o in oldpred if t=='CONFIGURATION_PREDICTION']
    require(len(complete)==19964 and sum(r['architecture']=='X' for r in complete)==3600,'old failed full registry retained')
    registry=[r for r in complete if r['architecture']=='D']
    require(len(D)==13824 and len(registry)==16364,'full D support')
    eligible=[r for r in D if r['alternatives']]; expected=[]
    for pos,r in enumerate(eligible):
        for target in r['alternatives']: expected.append((f'D:{pos}:{target}',r['context'],target))
    require([(r['id'],r['address'],r['target']) for r in registry]==expected,'old support order')
    Z=sum((Fraction(*r['original_mass']) for r in registry if r['trigger_basis']),Fraction())
    J=sum((Fraction(*r['original_mass'])*Fraction(*r['trigger_scene_mass']) for r in registry),Fraction())
    measure={'original_mass_sum':frac(sum((Fraction(*r['original_mass']) for r in registry),Fraction())),
             'triggerable_defect_mass':frac(Z),'nontrigger_mass':frac(1-Z),'joint_defect_scene_failure_mass_NOT_normalizer':frac(J),
             'conditional_configuration_mass_sum':frac(sum((Fraction(*r['original_mass'])/Z for r in registry if r['trigger_basis']),Fraction()))}
    require(measure['original_mass_sum']==[1,1] and Z==Fraction(85,90612) and J==Fraction(85,4349376),'old D measure')
    for r in registry: emit('CONFIGURATION_PREDICTION_READ_ONLY',r)
    emit('COMPLETE_MEASURE_BEFORE_NATIVE',{'all_original_D_contexts':13824,'eligible_contexts':7551,'configurations':16364,
         'unconsulted_configurations':sum(not r['consulted_basis'] for r in registry),'consulted_pairs':sum(len(r['consulted_basis']) for r in registry),
         'triggerable_configurations':sum(bool(r['trigger_basis']) for r in registry),'measure':measure,
         'prediction_registry_sha256':sha256(canonical(registry)).hexdigest(),'old_full_D_X_prediction_sha256':sha256(canonical(complete)).hexdigest(),
         'old_X_failure_exit_preserved':1,'scientific_measure_adopted':False})
    reference=QReferenceView({(K.State(*a[:5]),a[5],a[6]):row for a,row in q.items()},name='v31-stored-nominal-no-DP')
    oldpatch=next(o for t,os in records(c['stored']['patch_anchor']) if t=='COMPLETE_ARCHITECTURES' for o in os if o['architecture']=='D_patch')
    actual=[]; count=raw_count=reuse=0; outcomes=Counter(); changes=Counter(); deltas=[]
    for rec in registry:
        if not rec['consulted_basis']: continue
        address=rec['address']; s=K.State(*address[:5]); target=rec['target']; z,m=address[5:]
        for arch in ('D_Q','D_patch'):
            pre=LearnerPersistentState(); value=None
            if arch=='D_Q':
                row=reference.row(s,z,m); b=max(row.values()); value=b+(b-row[target])
                require(value>b,'fixed promotion not strictly dominating; no tuning')
                pre.apply_transaction([Edit(Q,QAddress(s,z,m,target),value)],q_reference=reference)
            else: pre.apply_transaction([Edit(DECISION,DecisionAddress(s,z,m),target)])
            fp=fingerprint(pre); snap=pre.snapshot()
            sizes=[len(snap.decision_overrides),len(snap.process_overrides),len(snap.controller_overrides),len(snap.q_overrides)]
            require(sizes==({'D_Q':[0,0,0,1],'D_patch':[1,0,0,0]}[arch]),'not sole independent store')
            for i in rec['consulted_basis']:
                k,phi,option=keys[i]; scene=EvaluationScene(k,phi,0,0,option); anchor=c['old_patch_anchor']
                old=arch=='D_patch' and address==anchor['context'] and target==anchor['target'] and list(keys[i])==anchor['basis']
                if old:
                    audit=oldpatch['original_owned_audit']; truth=audit['truth']
                    payload={'trace':audit['raw_trace'],'outcome':audit['factual_outcome'],
                             'return_hex':sum(float.fromhex(t['reward_hex']) for t in audit['raw_trace']).hex(),'Gamma_P_star':truth['Gamma_P_star']}
                    require(fp==oldpatch['source_fingerprint']==audit['fingerprint_pre']==audit['fingerprint_post'],'old exact pre identity')
                    reuse+=1
                else:
                    trace=learned_rollout(pre,kappa=k,tape=scene.tape,base_option=option,q_reference=reference)
                    raw=factual._trace_payload(trace,scene)
                    emit('RAW_NATIVE_FACTUAL_BEFORE_TRUTH',{'id':rec['id'],'architecture':arch,'basis_index':i,
                         'trace':raw,'outcome':trace.outcome,'return_hex':trace.return_value.hex()})
                    truth=factual._persistent_truth(trace,scene,reference)
                    payload={'trace':raw,'outcome':trace.outcome,'return_hex':trace.return_value.hex(),'Gamma_P_star':truth['Gamma_P_star']}
                    count+=1; raw_count+=len(raw)
                a={'id':rec['id'],'architecture':arch,'basis_index':i,'basis':list(keys[i]),'scene':list(scene.key),
                   'source':'READ_ONLY_EXACT_v25_FACTUAL' if old else 'NEW_NATIVE_SINGLETON_FACTUAL',
                   'DQ_promoted_value_hex':None if value is None else value.hex(),'all_store_sizes':sizes,
                   'fingerprint_pre':fp,'fingerprint_after_read':fingerprint(pre),'payload':payload,'full_original_truth':truth}
                emit('ACTUAL_FACTUAL',a); actual.append(a)
                require(fingerprint(pre)==fp and payload==dict(rec['consulted_predictions'])[i],'native differs from prior prediction or pre drift; no tuning')
                diff=float.fromhex(payload['return_hex'])-float.fromhex(bs[i]['payload']['return_hex'])
                outcomes[arch+':'+payload['outcome']]+=1
                changes[arch+':'+('negative' if diff<0 else 'positive' if diff>0 else 'zero')]+=1; deltas.append(diff)
    require((len(actual),count,reuse)==(1172,1171,1),'prospective extent not completed')
    after=bind(c); emit('INPUT_BINDING_AFTER',after); require(after==before,'runtime drift')
    emit('FINAL',{'status':'COMPLETE_PREVIOUSLY_UNEXECUTED_D_INSTALLER_COMPONENT_NOT_SCIENCE','measure':measure,
         'all_original_D_contexts':13824,'eligible_contexts':7551,'configurations':16364,
         'unconsulted_configurations':sum(not r['consulted_basis'] for r in registry),'consulted_pairs':586,'triggerable_configurations':26,
         'prediction_registry_sha256':sha256(canonical(registry)).hexdigest(),'actual_registry_sha256':sha256(canonical(actual)).hexdigest(),
         'actual_records':len(actual),'new_native_rollouts':count,'new_native_raw_rows':raw_count,'old_exact_patch_factual_read_only':reuse,
         'outcomes':dict(outcomes),'signed_return_changes_vs_nominal':dict(changes),'min_return_delta':min(deltas),'max_return_delta':max(deltas),
         'all_inputs_equal':True,'old_X_zero_mass_evidence_retained':True,'B1_arms':0,'new_DP_execution':False,'future_training':0,'keys_allocated':0,'random_draws':0,
         'multi_address_or_mixed_totality':False,'joint_calibration_totality':False,'delta_joint':None,'scientific_rules_adopted':False,
         'collector_executed':False,'collection_authorized':False,'scientific_PASS':False,'mechanism_direction_falsified':False,'research_complete':False})

if __name__=='__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode,'derive',side_effect=AssertionError('no keys')), \
         patch.object(training,'train_curve',side_effect=AssertionError('no future training')), \
         patch.object(K.SemanticTape,'sample',side_effect=AssertionError('no sampling')):
        main()
