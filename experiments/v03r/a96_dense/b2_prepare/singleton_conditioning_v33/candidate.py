"""Full finite singleton normalizers; native initial defect observations, not B1 effects."""
from collections import Counter
from fractions import Fraction
from hashlib import sha1,sha256
from pathlib import Path
import json,subprocess,sys
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]
sys.path.insert(0,str(PREP));sys.path.insert(0,str(ROOT/'src'))
import predictor
import factual_event_candidate as factual
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import Q,DECISION,CONTROLLER,Edit,QAddress,DecisionAddress,LearnerPersistentState


def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def emit(t,o):print(t+'='+canonical(o).decode().rstrip('\n'),flush=True)
def require(ok,why):
    if not ok:raise AssertionError(why)
def read(p):return json.loads(p.read_bytes())
def frac(f):return [f.numerator,f.denominator]


def stored(info):
    p=PREP/info['folder'];claim,ex=read(p/'claim.json'),read(p/'exit.json')
    require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in claim.items()),'old receipt')
    for n,v in ex['files'].items():
        b=(p/n).read_bytes();require(len(b)==v['bytes'] and sha256(b).hexdigest()==v['sha256'],'old bytes')
    require(ex['files']['stdout.log']['sha256']==info['stdout_sha256'] and not (p/'stderr.log').read_bytes(),'old evidence')
    out=[]
    for line in (p/'stdout.log').read_bytes().splitlines():
        if b'=' not in line:continue
        t,v=line.split(b'=',1)
        if v[:1] in (b'[',b'{'):out.append((t.decode(),json.loads(v)))
    return out


def bind(c):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(head==c['parent_commit'],'parent changed')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound))==(313,153,365,679),'parent extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','predictor.py','candidate.py','execute.py','check_stored.py')}
    require(len(names)==837,'runtime extent')
    return {'parent_HEAD':head,'HEAD_byte_bindings':len(bound),'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}


def old_payload(p):
    rows=[]
    for r in p['trace']:
        rows.append(dict(zip(('pre_state','z','m','a_cmd','u','a_realized','reward_hex','post_state','post_control','terminal','outcome','illegal'),r)))
    return {'trace':rows,'outcome':p['outcome'],'return_hex':p['return_hex'],'Gamma_P_star':[]}


def main():
    c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    catalog=stored(c['stored_catalog']);D=[o for t,o in catalog if t=='DECISION_CONTEXT'];X=[o for t,o in catalog if t=='CONTROLLER_SITE']
    basis=next(o['entries'] for t,o in stored(c['stored_basis']) if t=='NATIVE_BASIS')
    q={tuple(r['context']):{a:float.fromhex(v) for a,v in r['q_row_hex']} for r in D}
    keys=[(b['kappa'],b['phase'],b['committed']) for b in basis]
    require(len(keys)==len(set(keys))==48,'basis extent')
    nominal=[old_payload(b['payload']) for b in basis]
    for key,p in zip(keys,nominal):require(predictor.predict(q,key)==p,'stored nominal trace/model mismatch')
    emit('NOMINAL_BASIS_BOUND',{'entries':48,'canonical_sha256':sha256(canonical(nominal)).hexdigest(),
                              'new_nominal_rollout':False,'raw_rows':sum(len(p['trace']) for p in nominal)})
    registry=[];predictions={};summaries={}
    for arch,rows,field in (('D',D,'context'),('X',X,'site')):
        eligible=[r for r in rows if r['alternatives']];M=len(eligible);Z=Fraction();joint=Fraction();hist={};worlds=0
        for pos,r in enumerate(eligible):
            address=r[field];visits=[]
            for b,p in enumerate(nominal):
                if any(tuple(t['pre_state']+([t['z'],t['m']] if arch=='D' else [t['a_cmd']]))==tuple(address) for t in p['trace']):visits.append(b)
            require(bool(visits)==r['nominal_basis_consulted'],'catalog consultation mismatch')
            for target in r['alternatives']:
                world_id=f'{arch}:{pos}:{target}';payloads={b:predictor.predict(q,keys[b],arch,address,target) for b in visits}
                triggers=[b for b,p in payloads.items() if p['outcome']!='SUCCESS' and p['Gamma_P_star']]
                mass=Fraction(1,M*len(r['alternatives']));worlds+=1
                if triggers:Z+=mass
                joint+=mass*Fraction(len(triggers),48);hist[len(triggers)]=hist.get(len(triggers),Fraction())+mass
                rec={'id':world_id,'architecture':arch,'eligible_position':pos,'address':address,'target':target,
                     'alternatives':len(r['alternatives']),'original_mass':frac(mass),'consulted_basis':visits,
                     'trigger_basis':triggers,'trigger_scene_mass':frac(Fraction(len(triggers),48)),
                     'consulted_predictions':[[b,p] for b,p in payloads.items()]}
                registry.append(rec);predictions[world_id]=payloads
                emit('CONFIGURATION_PREDICTION',rec)
        require(sum(hist.values(),Fraction())==1,'original measure not normalized')
        require(Z>0,'singleton candidate has zero triggerable mass; retain and report')
        summaries[arch]={'eligible_positions':M,'assigned_configurations':worlds,'triggerable_mass':frac(Z),
                         'nontrigger_mass':frac(1-Z),'joint_defect_scene_failure_mass_NOT_defect_normalizer':frac(joint),
                         'trigger_count_original_mass_histogram':[[n,frac(v)] for n,v in sorted(hist.items())],
                         'conditional_configuration_mass_sum':frac(sum((Fraction(*r['original_mass'])/Z for r in registry if r['architecture']==arch and r['trigger_basis']),Fraction()))}
    prediction_sha=sha256(canonical(registry)).hexdigest()
    emit('ALL_PREDICTIONS_COMPLETE_BEFORE_NATIVE',{'configurations':len(registry),'registry_sha256':prediction_sha,'normalizers':summaries})
    # Stored rows, no new DP call, no reference solver imported/executed.
    reference=QReferenceView({(K.State(*s[:5]),s[5],s[6]):row for s,row in q.items()},name='v31-stored-nominal')
    old_arch=next(o for t,o in stored(c['stored_patch_anchor']) if t=='COMPLETE_ARCHITECTURES')
    old_patch=next(o for o in old_arch if o['architecture']=='D_patch')
    actual=[];new_count=raw_count=reused=0
    for rec in registry:
        if not rec['consulted_basis']:continue
        s=K.State(*rec['address'][:5]);target=rec['target']
        arches=('D_Q','D_patch') if rec['architecture']=='D' else ('X',)
        for arch in arches:
            pre=LearnerPersistentState();amplitude=None
            if arch=='D_Q':
                z,m=rec['address'][5:];row=reference.row(s,z,m);b=max(row.values());amplitude=b+(b-row[target])
                require(amplitude>b,'promoted value did not dominate; no amplitude tuning')
                pre.apply_transaction([Edit(Q,QAddress(s,z,m,target),amplitude)],q_reference=reference)
            elif arch=='D_patch':pre.apply_transaction([Edit(DECISION,DecisionAddress(s,*rec['address'][5:]),target)])
            else:pre.apply_transaction([Edit(CONTROLLER,K.ControllerSite(s,rec['address'][5]),target)])
            fp=fingerprint(pre)
            sizes=[len(pre.snapshot().decision_overrides),len(pre.snapshot().process_overrides),len(pre.snapshot().controller_overrides),len(pre.snapshot().q_overrides)]
            require(sizes==({'D_Q':[0,0,0,1],'D_patch':[1,0,0,0],'X':[0,0,1,0]}[arch]),'not independent singleton full pre')
            for bindex in rec['consulted_basis']:
                k,phi,z=keys[bindex];scene=EvaluationScene(k,phi,0,0,z)
                anchor=c['stored_patch_anchor']
                old=(arch=='D_patch' and rec['address']==anchor['context'] and target==anchor['target'] and list(keys[bindex])==anchor['basis'])
                if old:
                    audit=old_patch['original_owned_audit'];payload={'trace':audit['raw_trace'],'outcome':audit['factual_outcome'],
                         'return_hex':float(sum(float.fromhex(t['reward_hex']) for t in audit['raw_trace'])).hex(),'Gamma_P_star':audit['truth']['Gamma_P_star']}
                    require(fp==old_patch['source_fingerprint'],'old exact pre does not match; no rerun')
                    reused+=1
                else:
                    trace=learned_rollout(pre,kappa=k,tape=scene.tape,base_option=z,q_reference=reference)
                    emit('RAW_NATIVE_FACTUAL_BEFORE_TRUTH',{'id':rec['id'],'architecture':arch,'basis_index':bindex,
                         'trace':factual._trace_payload(trace,scene),'outcome':trace.outcome,'return_hex':trace.return_value.hex()})
                    # Truth is computed through the original A75 baseline manifestation implementation, not forecast labels.
                    truth=factual._persistent_truth(trace,scene,reference)
                    payload={'trace':factual._trace_payload(trace,scene),'outcome':trace.outcome,
                             'return_hex':trace.return_value.hex(),'Gamma_P_star':truth['Gamma_P_star']}
                    new_count+=1;raw_count+=len(payload['trace'])
                row={'id':rec['id'],'architecture':arch,'basis_index':bindex,'basis':list(keys[bindex]),'scene':list(scene.key),
                     'source':'READ_ONLY_EXACT_v25_FACTUAL' if old else 'NEW_NATIVE_SINGLETON_FACTUAL',
                     'DQ_promoted_value_hex':None if amplitude is None else amplitude.hex(),'all_store_sizes':sizes,
                     'fingerprint_pre':fp,'fingerprint_after_read':fingerprint(pre),'payload':payload}
                emit('ACTUAL_FACTUAL',row);actual.append(row)
                require(fingerprint(pre)==fp,'native observation mutated pre')
                require(payload==predictions[rec['id']][bindex],'first-hit singleton forecast mismatch; no tuning')
    after=bind(c);emit('INPUT_BINDING_AFTER',after);require(after==before,'inputs changed')
    emit('FINAL',{'status':'FULL_SINGLETON_INITIAL_DEFECT_CONDITIONING_COMPONENT_COMPLETE_NOT_SCIENCE',
         'normalizers':summaries,'configuration_prediction_registry_sha256':prediction_sha,
         'actual_registry_sha256':sha256(canonical(actual)).hexdigest(),'actual_records':len(actual),
         'new_native_initial_defect_rollouts':new_count,'new_native_raw_rows':raw_count,'old_exact_patch_factual_reused':reused,
         'all_inputs_equal':True,'new_DP_execution':False,'B1_arms':0,'future_training':0,'keys_allocated':0,'random_draws':0,
         'multi_address_or_mixed_normalizer_closed':False,'joint_calibration_totality':False,'delta_joint':None,
         'scientific_rules_adopted':False,'scientific_PASS':False,'collector_executed':False,
         'collection_authorized':False,'research_complete':False,'mechanism_direction_falsified':False})


if __name__=='__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode,'derive',side_effect=AssertionError('no keys')), \
         patch.object(training,'train_curve',side_effect=AssertionError('no future training')), \
         patch.object(K.SemanticTape,'sample',side_effect=AssertionError('no sampling')):
        main()
