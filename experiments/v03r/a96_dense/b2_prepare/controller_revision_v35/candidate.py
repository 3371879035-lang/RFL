"""Unadopted full-domain read-service X syntax, exact singleton mass, keyless native coverage."""
from collections import Counter
from fractions import Fraction
from hashlib import sha1,sha256
from pathlib import Path
import importlib.util,json,subprocess,sys
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


def stored(spec):
    p=PREP/spec['folder'];cl,ex=read(p/'claim.json'),read(p/'exit.json')
    require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items()),'old receipt')
    for n,v in ex['files'].items():
        b=(p/n).read_bytes();require(len(b)==v['bytes'] and sha256(b).hexdigest()==v['sha256'],'old raw bytes')
    require(ex['files']['stdout.log']['sha256']==spec['stdout_sha256'] and not (p/'stderr.log').read_bytes(),'stored source digest')
    return [(t.decode(),json.loads(v)) for t,v in (line.split(b'=',1) for line in (p/'stdout.log').read_bytes().splitlines())]


def binding(c):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'parent')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources'];a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit'];native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')};bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound))==(313,153,404,718),'parent extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==875,'runtime extent')
    return {'parent_HEAD':head,'HEAD_byte_bindings':718,'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}


def main():
    c=read(HERE/'contract.json');before=binding(c);emit('INPUT_BINDING_BEFORE',before)
    cat=stored(c['stored']['catalog']);D=[o for t,o in cat if t=='DECISION_CONTEXT'];X=[o for t,o in cat if t=='CONTROLLER_SITE']
    service=[o for t,o in stored(c['stored']['service']) if t=='COMPLETE_SITE_SERVICE'];require((len(D),len(X),len(service))==(13824,5904,5904),'whole domain')
    q={tuple(r['context']):{a:float.fromhex(h) for a,h in r['q_row_hex']} for r in D}
    bs=next(o['entries'] for t,o in stored(c['stored']['basis']) if t=='NATIVE_BASIS');keys=[(b['kappa'],b['phase'],b['committed']) for b in bs]
    spec=importlib.util.spec_from_file_location('stored_v33_singleton_predictor',PREP/c['stored']['predictor']);predictor=importlib.util.module_from_spec(spec);spec.loader.exec_module(predictor)
    for key,b in zip(keys,bs):
        p=predictor.predict(q,key);old=b['payload'];require(p['outcome']==old['outcome'] and p['return_hex']==old['return_hex'],'nominal value')
        require([list(r.values()) for r in p['trace']]==old['trace'] and not p['Gamma_P_star'],'complete old nominal trace')
    consulted={}
    for i,b in enumerate(bs):
        for row in b['payload']['trace']:consulted.setdefault(tuple(row[0]+[row[3]]),[]).append(i)
    oldactual=[o for t,o in stored(c['stored']['old_actual']) if t=='ACTUAL_X_SINGLETON'];old_by={(tuple(o['address']),o['target'],o['basis_index']):o for o in oldactual};require(len(old_by)==len(oldactual)==50,'all old native pairs')
    sites=[];registry=[];M=sum(bool(s['domain_alternatives']) for s in service);require(M==4464,'full eligible extent')
    for old,s in zip(X,service):
        site=s['site'];require(site==old['site'] and s['old_alternatives']==old['alternatives'],'old site binding');targets=s['domain_alternatives']
        require(set(old['alternatives'])<=set(targets),'old support removed')
        row={'site':site,'domain_service':s['domain_service'],'targets':targets,'old_targets':old['alternatives'],
             'reachable_service':s['reachable_service'],'status':s['status'],'eligible':bool(targets),'candidate_site_mass':frac(Fraction(1,M)) if targets else None}
        sites.append(row);emit('REVISED_SITE_NOT_ADOPTED',row)
        for target in targets:
            indices=consulted.get(tuple(site),[]);require(len(indices)==len(set(indices)),'same address reappeared')
            predictions=[[i,predictor.predict(q,keys[i],'X',site,target)] for i in indices]
            triggers=[i for i,p in predictions if p['outcome']!='SUCCESS' and p['Gamma_P_star']]
            rec={'site':site,'target':target,'target_count':len(targets),'candidate_mass':frac(Fraction(1,M*len(targets))),
                 'old_mass':frac(Fraction(1,3312*len(old['alternatives']))) if target in old['alternatives'] else None,
                 'consulted_basis':indices,'trigger_basis':triggers,'trigger_scene_mass':frac(Fraction(len(triggers),48)),
                 'consulted_predictions':predictions}
            registry.append(rec);emit('CONFIGURATION_PREDICTION',rec)
    require(len(registry)==8928,'complete candidate support');Z=sum((Fraction(*r['candidate_mass']) for r in registry if r['trigger_basis']),Fraction());J=sum((Fraction(*r['candidate_mass'])*Fraction(*r['trigger_scene_mass']) for r in registry),Fraction())
    mass={'candidate_total_mass':frac(sum((Fraction(*r['candidate_mass']) for r in registry),Fraction())),
          'old_support_total_old_mass':frac(sum((Fraction(*r['old_mass']) for r in registry if r['old_mass']),Fraction())),
          'old_support_total_under_candidate_mass':frac(sum((Fraction(*r['candidate_mass']) for r in registry if r['old_mass']),Fraction())),
          'triggerable_defect_mass':frac(Z),'nontrigger_defect_mass':frac(1-Z),'joint_defect_scene_failure_mass_NOT_normalizer':frac(J),
          'conditional_distribution_defined':Z>0,'triggerable_configurations':sum(bool(r['trigger_basis']) for r in registry)}
    emit('COMPLETE_MEASURE_BEFORE_NATIVE',{'measure':mass,'site_registry_sha256':sha256(canonical(sites)).hexdigest(),
          'prediction_registry_sha256':sha256(canonical(registry)).hexdigest(),'consulted_pairs':sum(len(r['consulted_basis']) for r in registry),'exact_old_pairs_to_reuse':50})
    reference=QReferenceView({(K.State(*s[:5]),s[5],s[6]):row for s,row in q.items()},name='v31-stored-nominal')
    actual=[];reused=[];outcomes=Counter();raw_count=0;changes=Counter()
    for rec in registry:
        if not rec['consulted_basis']:continue
        site=K.ControllerSite(K.State(*rec['site'][:5]),rec['site'][5]);pre=LearnerPersistentState();pre.apply_transaction([Edit(CONTROLLER,site,rec['target'])]);fp=fingerprint(pre)
        snap=pre.snapshot();sizes=[len(snap.decision_overrides),len(snap.process_overrides),len(snap.controller_overrides),len(snap.q_overrides)];require(sizes==[0,0,1,0],'full pre not sole X')
        for i,pred in rec['consulted_predictions']:
            identity=(tuple(rec['site']),rec['target'],i)
            if identity in old_by:
                old=old_by[identity];require(old['payload']==pred and old['fingerprint_pre']==old['fingerprint_after_read']==fp and old['all_store_sizes']==sizes,'exact old full-pre reuse')
                reused.append(old);emit('OLD_NATIVE_PAIR_READ_ONLY',{'site':rec['site'],'target':rec['target'],'basis_index':i,'old_id':old['id'],'fingerprint':fp,'old_payload_sha256':sha256(canonical(old['payload'])).hexdigest()});continue
            k,phi,z=keys[i];scene=EvaluationScene(k,phi,0,0,z);trace=learned_rollout(pre,kappa=k,tape=scene.tape,base_option=z,q_reference=reference)
            raw=factual._trace_payload(trace,scene);emit('RAW_NATIVE_FACTUAL_BEFORE_TRUTH',{'site':rec['site'],'target':rec['target'],'basis_index':i,'trace':raw,'outcome':trace.outcome,'return_hex':trace.return_value.hex()})
            truth=factual._persistent_truth(trace,scene,reference);payload={'trace':raw,'outcome':trace.outcome,'return_hex':trace.return_value.hex(),'Gamma_P_star':truth['Gamma_P_star']}
            row={'site':rec['site'],'target':rec['target'],'basis_index':i,'basis':list(keys[i]),'scene':list(scene.key),
                 'all_store_sizes':sizes,'fingerprint_pre':fp,'fingerprint_after_read':fingerprint(pre),'payload':payload}
            emit('ACTUAL_X_SINGLETON',row);actual.append(row);raw_count+=len(raw);outcomes[trace.outcome]+=1
            delta=trace.return_value-float.fromhex(bs[i]['payload']['return_hex']);changes['negative' if delta<0 else 'positive' if delta>0 else 'zero']+=1
            require(payload==pred and fingerprint(pre)==fp,'native/prediction mismatch; no retune')
    require(len(reused)==50,'old pair omitted');after=binding(c);emit('INPUT_BINDING_AFTER',after);require(before==after,'inputs drift')
    emit('FINAL',{'status':'UNADOPTED_DOMAIN_SERVICE_X_SINGLETON_COMPONENT_COMPLETE','measure':mass,
         'all_original_sites':5904,'eligible_candidate_sites':4464,'candidate_configurations':8928,'old_support_configurations_retained':3600,
         'site_registry_sha256':sha256(canonical(sites)).hexdigest(),'prediction_registry_sha256':sha256(canonical(registry)).hexdigest(),
         'actual_registry_sha256':sha256(canonical(actual)).hexdigest(),'new_native_initial_X_rollouts':len(actual),'new_native_raw_rows':raw_count,
         'old_native_pairs_read_only':len(reused),'new_native_outcomes':dict(outcomes),'new_return_changes_vs_nominal':dict(changes),
         'runtime_inputs':875,'parent_HEAD_byte_bindings':718,'all_inputs_equal':True,'B1_arms':0,'new_DP_execution':False,'future_training':0,'keys_allocated':0,
         'scientific_rules_adopted':False,'scientific_measure_changed':False,'candidate_measure_differs_from_old':True,'population_reduced':False,
         'collector_executed':False,'scientific_PASS':False,'mechanism_direction_falsified':False,'joint_calibration_totality':False,'delta_joint':None,
         'collection_authorized':False,'valid_current_scientific_STOP':False,'research_complete':False})


if __name__=='__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode,'derive',side_effect=AssertionError('no keys')), \
         patch.object(training,'train_curve',side_effect=AssertionError('no future training')), \
         patch.object(K.SemanticTape,'sample',side_effect=AssertionError('no sampling')):
        main()
