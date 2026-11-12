"""Full consulted X singleton native coverage; preserves zero trigger mass instead of tuning."""
from collections import Counter
from fractions import Fraction
from hashlib import sha1,sha256
from pathlib import Path
import json,subprocess,sys
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]
sys.path.insert(0,str(PREP));sys.path.insert(0,str(ROOT/'src'))
import factual_event_candidate as factual
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import CONTROLLER,Edit,LearnerPersistentState


def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def emit(t,o):print(t+'='+canonical(o).decode().rstrip('\n'),flush=True)
def read(p):return json.loads(p.read_bytes())
def require(ok,why):
    if not ok:raise AssertionError(why)
def frac(f):return [f.numerator,f.denominator]


def records(folder,exit_code,expected):
    claim,ex=read(folder/'claim.json'),read(folder/'exit.json')
    require(ex['native_child_exit_code']==exit_code and all(ex[k]==v for k,v in claim.items()),'native receipt')
    for n,v in ex['files'].items():
        b=(folder/n).read_bytes();require(len(b)==v['bytes'] and sha256(b).hexdigest()==v['sha256'],'native raw')
    require(ex['files']['stdout.log']['sha256']==expected,'stdout changed')
    out=[]
    for line in (folder/'stdout.log').read_bytes().splitlines():
        if b'=' in line:
            t,v=line.split(b'=',1)
            if v[:1] in (b'{',b'['):out.append((t.decode(),json.loads(v)))
    return out


def bind(c):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'parent')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')};bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound))==(313,153,365,679),'extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','predictor.py','candidate.py','execute.py','check_stored.py','zero_mass_contract.json','confirm_zero_mass.py','check_zero_mass.py','execute_zero_mass.py')}
    names|={(HERE/'evidence'/n).relative_to(ROOT).as_posix() for n in ('claim.json','exit.json','stdout.log','stderr.log')}
    require(len(names)==845,'runtime extent')
    for n,d in c['binding']['initial_failure_source_SHA256'].items():require(sha256((HERE/n).read_bytes()).hexdigest()==d,'initial source changed')
    return {'parent_HEAD':head,'HEAD_byte_bindings':679,'input_sha256':{n:sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(names)}}


def main():
    c=read(HERE/'zero_mass_contract.json');original=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    initial=records(HERE/'evidence',1,c['initial_attempt']['stdout_sha256']);require('singleton candidate has zero triggerable mass' in (HERE/'evidence/stderr.log').read_text(encoding='utf8'),'failure cause')
    require(not any(t in ('RAW_NATIVE_FACTUAL_BEFORE_TRUTH','ACTUAL_FACTUAL') for t,o in initial),'initial native observations present')
    registry=[o for t,o in initial if t=='CONFIGURATION_PREDICTION'];require(len(registry)==19964,'initial prediction extent')
    X=[r for r in registry if r['architecture']=='X'];require(len(X)==3600 and all(not r['trigger_basis'] for r in X),'not complete zero trigger X')
    cat=records(PREP/original['stored_catalog']['folder'],0,original['stored_catalog']['stdout_sha256'])
    d=[o for t,o in cat if t=='DECISION_CONTEXT'];xs=[o for t,o in cat if t=='CONTROLLER_SITE']
    q={tuple(r['context']):{a:float.fromhex(v) for a,v in r['q_row_hex']} for r in d}
    br=records(PREP/original['stored_basis']['folder'],0,original['stored_basis']['stdout_sha256']);basis=next(o['entries'] for t,o in br if t=='NATIVE_BASIS');keys=[(b['kappa'],b['phase'],b['committed']) for b in basis]
    summaries={}
    for arch in ('D','X'):
        rows=[r for r in registry if r['architecture']==arch];Z=sum((Fraction(*r['original_mass']) for r in rows if r['trigger_basis']),Fraction());J=sum((Fraction(*r['original_mass'])*Fraction(*r['trigger_scene_mass']) for r in rows),Fraction())
        summaries[arch]={'eligible_positions':len({r['eligible_position'] for r in rows}),'assigned_configurations':len(rows),
                         'original_mass_sum':frac(sum((Fraction(*r['original_mass']) for r in rows),Fraction())),
                         'triggerable_mass':frac(Z),'nontrigger_mass':frac(1-Z),'joint_defect_scene_failure_mass_NOT_defect_normalizer':frac(J),
                         'conditional_defect_distribution_defined':Z>0}
    anchor=[1,2,1,0,2,0];anchor_row=next(r for r in xs if r['site']==anchor)
    require(not anchor_row['alternatives'] and not anchor_row['all8_common_legal'],'old v26 UP->RIGHT mechanism site unexpectedly included')
    emit('COMPLETE_ZERO_MASS_AUDIT_BEFORE_NATIVE',{'normalizers':summaries,'prediction_registry_sha256':sha256(canonical(registry)).hexdigest(),
         'all_original_X_support_retained':True,'old_v26_controller_site':anchor,'old_v26_target':3,'old_v26_site_catalog':anchor_row,
         'all_consulted_native_cases_to_check':sum(len(r['consulted_basis']) for r in X),'no_failed_candidate_rerun':True})
    reference=QReferenceView({(K.State(*s[:5]),s[5],s[6]):row for s,row in q.items()},name='v31-stored-nominal')
    actual=[];raw_count=0;outcomes=Counter()
    for rec in X:
        if not rec['consulted_basis']:continue
        address=rec['address'];site=K.ControllerSite(K.State(*address[:5]),address[5]);pre=LearnerPersistentState()
        pre.apply_transaction([Edit(CONTROLLER,site,rec['target'])]);fp=fingerprint(pre)
        sizes=[len(pre.snapshot().decision_overrides),len(pre.snapshot().process_overrides),len(pre.snapshot().controller_overrides),len(pre.snapshot().q_overrides)]
        require(sizes==[0,0,1,0],'not sole X pre')
        for bindex in rec['consulted_basis']:
            k,phi,z=keys[bindex];scene=EvaluationScene(k,phi,0,0,z)
            trace=learned_rollout(pre,kappa=k,tape=scene.tape,base_option=z,q_reference=reference)
            raw=factual._trace_payload(trace,scene);emit('RAW_NATIVE_FACTUAL_BEFORE_TRUTH',{'id':rec['id'],'basis_index':bindex,'trace':raw,'outcome':trace.outcome,'return_hex':trace.return_value.hex()})
            truth=factual._persistent_truth(trace,scene,reference);payload={'trace':raw,'outcome':trace.outcome,'return_hex':trace.return_value.hex(),'Gamma_P_star':truth['Gamma_P_star']}
            row={'id':rec['id'],'basis_index':bindex,'basis':list(keys[bindex]),'scene':list(scene.key),'address':address,'target':rec['target'],
                 'all_store_sizes':sizes,'fingerprint_pre':fp,'fingerprint_after_read':fingerprint(pre),'payload':payload}
            emit('ACTUAL_X_SINGLETON',row);actual.append(row);raw_count+=len(raw);outcomes[trace.outcome]+=1
            require(fingerprint(pre)==fp,'native read changed state')
            require(payload==dict(rec['consulted_predictions'])[bindex],'full native/prediction mismatch; no tuning')
            require(trace.outcome=='SUCCESS','zero-mass forecast refuted; preserve result')
    after=bind(c);emit('INPUT_BINDING_AFTER',after);require(before==after,'inputs changed')
    emit('FINAL',{'status':'X_SINGLETON_ZERO_TRIGGER_MASS_CONFIRMED_UNADOPTED_DESIGN_BLOCKED_NOT_MECHANISM_STOP',
         'normalizers':summaries,'actual_registry_sha256':sha256(canonical(actual)).hexdigest(),
         'new_native_initial_X_rollouts':len(actual),'new_native_raw_rows':raw_count,'all_observed_outcomes':dict(outcomes),
         'all_inputs_equal':True,'failed_candidate_rerun':False,'B1_arms':0,'new_DP_execution':False,'future_training':0,'keys_allocated':0,
         'collector_executed':False,'scientific_rules_adopted':False,'population_reduced':False,'scientific_PASS':False,
         'mechanism_direction_falsified':False,'joint_calibration_totality':False,'delta_joint':None,
         'collection_authorized':False,'valid_current_scientific_STOP':False,'research_complete':False})


if __name__=='__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode,'derive',side_effect=AssertionError('no keys')), \
         patch.object(training,'train_curve',side_effect=AssertionError('no future training')), \
         patch.object(K.SemanticTape,'sample',side_effect=AssertionError('no sampling')):
        main()
