"""Prospective complete legal first-X-deviation/later-X-site panel; full original B1."""
from collections import Counter
from hashlib import sha1,sha256
from fractions import Fraction
from math import comb
from pathlib import Path
import json,subprocess,sys,time
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]
sys.path.insert(0,str(PREP));sys.path.insert(0,str(ROOT/'src'))
import factual_event_candidate as factual
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b1.controller import resolve_controller_sites
from rfl_rebuild.b1.laws import NoWriteRef,XId
from rfl_rebuild.b1.runner import run_controller_law
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import CONTROLLER,Edit,LearnerPersistentState
from rfl_rebuild.method.credit import OracleCreditAdapter
def read(p): return json.loads(p.read_bytes())
def canonical(o): return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def emit(t,o): print(t+'='+canonical(o).decode().rstrip('\n'),flush=True)
def require(ok,why):
    if not ok: raise AssertionError(why)
def records(info):
    p=PREP/info['folder'];cl,ex=read(p/'claim.json'),read(p/'exit.json')
    require(ex['native_child_exit_code']==info['exit'] and all(ex[k]==v for k,v in cl.items()),'old receipt')
    for n,v in ex['files'].items():
        b=(p/n).read_bytes();require({'bytes':len(b),'sha256':sha256(b).hexdigest()}==v,'old full bytes')
    require(ex['files']['stdout.log']['sha256']==info['stdout_sha256'] and not (p/'stderr.log').read_bytes(),'old capture binding')
    out=[]
    for l in (p/'stdout.log').read_bytes().splitlines():
        if b'=' in l:
            t,v=l.split(b'=',1)
            if v[:1] in (b'[',b'{'):out.append((t.decode(),json.loads(v)))
    return out
def bind(c):
    h=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(h==c['parent_commit'],'HEAD drift')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',h],cwd=ROOT).split(b'\0') if r}
    source=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(source)|prior|{'experiments/rebuild_status_current.json'}
    require((len(source),len(native),len(prior),len(bound))==(313,153,519,833),'parent extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (source|native).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==990,'runtime extent')
    return {'parent_HEAD':h,'HEAD_byte_bindings':833,'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}

def site(a):return K.ControllerSite(K.State(*a[:5]),a[5])
def literal(a):return [a.state.x,a.state.y,a.state.t,a.state.kappa,a.state.phi,a.cmd]
def stores(s):
    require(not s.decision_overrides and not s.process_overrides and not s.q_overrides,'other store must remain empty')
    return {'D':[],'P':[],'Q':[],'X':sorted([[literal(a),v] for a,v in s.controller_overrides.items()])}
def predict(root,q,graph,decl):
    n=root;raw=[]
    while True:
        cmd=min(q[n],key=lambda a:(-q[n][a],a));s=n[:5]+(cmd,);u=decl.get(s,cmd);e=graph[n][u]
        raw.append({'pre_state':list(n[:5]),'z':n[5],'m':n[6],'a_cmd':cmd,'u':u,'a_realized':u,
            'reward_hex':e['reward_hex'],'post_state':e['post'][:5],'post_control':e['post'][5:],
            'terminal':e['terminal'],'outcome':e['outcome'],'illegal':False})
        if e['terminal']:break
        n=tuple(e['post'])
    return {'trace':raw,'outcome':raw[-1]['outcome'],'return_hex':sum(float.fromhex(r['reward_hex']) for r in raw).hex()}
def owners(p):return [r['pre_state']+[r['a_cmd']] for r in p['trace'] if r['u']!=r['a_cmd']]
def unit(a):return f'ControllerSite_{a[0]}_{a[1]}_{a[2]}_{a[5]}'
def main():
    start=time.perf_counter();c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    old={n:records(i) for n,i in c['stored'].items()}
    D=[o for t,o in old['catalog'] if t=='DECISION_CONTEXT'];X=[o for t,o in old['catalog'] if t=='CONTROLLER_SITE']
    R=[o for t,o in old['revision'] if t=='REVISED_SITE_NOT_ADOPTED']
    q={tuple(o['context']):{a:float.fromhex(h) for a,h in o['q_row_hex']} for o in D}
    alt={tuple(o['site']):o['targets'] for o in R};oldalt={tuple(o['site']):o['alternatives'] for o in X}
    bs=next(o['entries'] for t,o in old['basis'] if t=='NATIVE_BASIS');graph={}
    for t,r in old['graph']:
        if t=='NATIVE_LEGAL_EDGE':graph.setdefault(tuple(r['pre']),{})[r['command']]=r['result']
    require((len(D),len(X),len(R),len(graph),sum(map(len,graph.values())))==(13824,5904,5904,6254,20588),'full source domain')
    require((sum(bool(a) for a in alt.values()),sum(map(len,alt.values())))==(4464,8928),'full domain grammar')
    require((sum(bool(a) for a in oldalt.values()),sum(map(len,oldalt.values())))==(3312,3600),'old grammar')
    exact=[o for t,o in old['joint'] if t=='COMPLETE_EXACT_CELL_NORMALIZER']
    emit('OLD_COMPLETE_NORMALIZERS_READ_ONLY',{'cells':exact,'not_recomputed':True,'scientific_grammar_adopted':False})
    scopes=[];panel=[];worldids={};worlds=[];secondscopes=0;seen=set()
    for i,b in enumerate(bs):
        root=(0,2,0,b['kappa'],b['phase'],b['committed'],0)
        eligible=[tuple(r[0]+[r[3]]) for r in b['payload']['trace'] if alt[tuple(r[0]+[r[3]])]]
        emit('BASIS_SCOPE',{'basis_index':i,'basis':list(root[3:6]),'eligible_sites':[list(s) for s in eligible]})
        for first in eligible:
            for target in alt[first]:
                single=predict(root,q,graph,{first:target})
                later=[tuple(r['pre_state']+[r['a_cmd']]) for r in single['trace']
                    if r['pre_state'][2]>first[2] and alt[tuple(r['pre_state']+[r['a_cmd']])]]
                scope={'id':len(scopes),'basis_index':i,'first_declaration':[list(first),target],
                    'source_only_single_deviation_payload':single,'later_eligible_sites':[list(s) for s in later],
                    'later_target_lists':[alt[s] for s in later],'no_native_singleton_rerun':True}
                emit('FIRST_TARGET_SCOPE',scope);scopes.append(scope)
                for second in later:
                    secondscopes+=1
                    for target2 in alt[second]:
                        decl=((first,target),(second,target2));identity=(i,decl)
                        require(identity not in seen,'duplicate basis/full-pre identity');seen.add(identity)
                        if decl not in worldids:
                            wid=len(worlds);worldids[decl]=wid
                            masses={}
                            for name,M,al in [('domain_command',4464,alt),('old_all8',3312,oldalt)]:
                                f=Fraction(1,comb(M,2)*len(al[first])*len(al[second])) if target in al[first] and target2 in al[second] else None
                                masses[name]=[f.numerator,f.denominator] if f is not None else None
                            world={'world_id':wid,'declarations':[[list(s),t] for s,t in decl],
                                'unconditioned_world_mass':masses,'not_panel_uniform_or_basis_mass':True}
                            emit('FULL_PRE_WORLD',world);worlds.append(world)
                        wid=worldids[decl];p=predict(root,q,graph,dict(decl));own=owners(p)
                        require(own==[list(first),list(second)],'structural two actual X owners')
                        app=p['outcome']!='SUCCESS'
                        rec={'id':len(panel),'world_id':wid,'first_target_scope':scope['id'],'basis_index':i,'basis':list(root[3:6]),
                            'declarations':worlds[wid]['declarations'],'pre':p,'all_manifested_owners':own,
                            'full_Oracle_units':[unit(s) for s in own],'reflection_applicable':app,
                            'post':predict(root,q,graph,{}) if app else None}
                        emit('PREDICTION_BEFORE_ANY_NATIVE',rec);panel.append(rec)
    barrier={'first_target_scopes':len(scopes),'empty_first_target_scopes':sum(not s['later_eligible_sites'] for s in scopes),
        'second_site_scopes':secondscopes,'unique_full_pre_worlds':len(worlds),'basis_world_records':len(panel),
        'scope_sha256':sha256(canonical(scopes)).hexdigest(),'world_sha256':sha256(canonical(worlds)).hexdigest(),
        'prediction_sha256':sha256(canonical(panel)).hexdigest(),'no_outcome_selected_targets':True,'full_scientific_k2_support_tested':False}
    emit('COMPLETE_PANEL_BEFORE_NATIVE',barrier)
    reference=QReferenceView({(K.State(*a[:5]),a[5],a[6]):row for a,row in q.items()},name='v31-stored-nominal-no-DP')
    actual=[];counts=Counter();changes=Counter();rawrows=0
    for rec in panel:
        k,phi,z=rec['basis'];scene=EvaluationScene(k,phi,0,0,z);pre=LearnerPersistentState()
        pre.apply_transaction([Edit(CONTROLLER,site(a),t) for a,t in rec['declarations']])
        fp=fingerprint(pre);st=stores(pre);trace=learned_rollout(pre,kappa=k,tape=scene.tape,base_option=z,q_reference=reference)
        p={'trace':factual._trace_payload(trace,scene),'outcome':trace.outcome,'return_hex':trace.return_value.hex()}
        emit('RAW_FACTUAL_BEFORE_TRUTH',{'id':rec['id'],'payload':p,'full_pre_store':st,'fingerprint_pre':fp})
        counts['factual_rollouts']+=1;rawrows+=len(p['trace'])
        require(p==rec['pre'] and fingerprint(pre)==fp,'native factual/prediction/source mismatch')
        truth=factual._persistent_truth(trace,scene,reference);oracle=OracleCreditAdapter.evaluate(truth['Gamma_P_star'])
        units=tuple(sorted(oracle,key=lambda a:int(a.split('_')[3])))
        resolved=resolve_controller_sites(units,trace,k,phi);own=[literal(a) for a in resolved]
        require(list(units)==rec['full_Oracle_units'] and own==rec['all_manifested_owners'],'all actual original truth/rho')
        emit('FULL_ORIGINAL_TRUTH_BEFORE_B1',{'id':rec['id'],'truth':truth,'units':list(units),'owners':own})
        arms=[]
        if rec['reflection_applicable']:
            counts['failing_records']+=1;counts['actual_owners_'+str(len(resolved))]+=1
            for role,law in [('reference',NoWriteRef(Tier.L0_FACTUAL)),('treatment',XId)]:
                clone=pre.clone();tx=[];apply_native=LearnerPersistentState.apply_transaction
                def apply(state,edits,**kwargs):
                    edits=tuple(edits)
                    tx.append({'on_this_clone':state is clone,'fingerprint_pre':fingerprint(state),
                        'entry_edits':len(edits),'stores':[e.store for e in edits],
                        'addresses':[literal(e.address) for e in edits],'values':[e.value for e in edits]})
                    return apply_native(state,edits,**kwargs)
                with patch.object(LearnerPersistentState,'apply_transaction',new=apply):
                    result=run_controller_law(law,clone,resolved,learner_rows(trace,k,phi))
                require(tuple(r.address for r in result.ledger.receipts)==resolved,'full native receipt owners')
                expected=[] if role=='reference' else [{'on_this_clone':True,'fingerprint_pre':fp,'entry_edits':len(own),
                    'stores':[CONTROLLER]*len(own),'addresses':own,'values':[a[5] for a in own]}]
                require(tx==expected,'same pre one complete original transaction')
                post=learned_rollout(clone,kappa=k,tape=scene.tape,base_option=z,q_reference=reference)
                pp={'trace':factual._trace_payload(post,scene),'outcome':post.outcome,'return_hex':post.return_value.hex()}
                counts['B1_arms']+=1;counts['post_rollouts']+=1;rawrows+=len(pp['trace'])
                require(pp==(p if role=='reference' else rec['post']),'native post/prediction mismatch')
                require(fingerprint(clone)==result.ledger.fingerprint_post and fingerprint(pre)==fp,'source/store drift')
                arms.append({'role':role,'law':law.name,'tier':Tier.L0_FACTUAL.name,'transactions':tx,
                    'ledger':json.loads(result.ledger.canonical()),'full_post_store':stores(clone),'payload':pp})
                if role=='treatment':
                    counts['treatment_transactions']+=len(tx);counts['post_'+pp['outcome']]+=1
                    d=post.return_value-trace.return_value;changes['positive' if d>0 else 'negative' if d<0 else 'zero']+=1
        else:counts['reflection_inapplicable_'+p['outcome']]+=1
        counts['pre_'+p['outcome']]+=1
        row={'id':rec['id'],'world_id':rec['world_id'],'basis_index':rec['basis_index'],'full_pre_store':st,
            'fingerprint_pre':fp,'source_fingerprint_after':fingerprint(pre),'payload':p,'truth':truth,
            'all_resolved_owners':own,'full_units':list(units),'reflection_applicable':rec['reflection_applicable'],'same_tier_arms':arms}
        emit('ACTUAL_COMPLETE_RECORD',row);actual.append(row)
    after=bind(c);emit('INPUT_BINDING_AFTER',after);require(after==before,'inputs changed')
    emit('FINAL',{'status':'COMPLETE_NATIVE_LEGAL_TWO_X_FULL_CREDIT_ONE_TRANSACTION_NOT_SCIENCE',**barrier,
        'actual_records':len(actual),'actual_sha256':sha256(canonical(actual)).hexdigest(),'counts':dict(counts),
        'signed_immediate_changes':dict(changes),'native_raw_rows':rawrows,'elapsed_seconds':time.perf_counter()-start,
        'runtime_inputs':990,'parent_HEAD_bindings':833,'all_inputs_equal':True,'new_reference_DP':0,'keys_allocated':0,
        'random_draws':0,'future_training':0,'collector_executed':False,'scientific_rules_adopted':False,
        'scientific_PASS':False,'collection_authorized':False,'mechanism_direction_falsified':False,'research_complete':False})
if __name__=='__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode,'derive',side_effect=AssertionError('no keys')), \
         patch.object(training,'train_curve',side_effect=AssertionError('no future training')), \
         patch.object(K.SemanticTape,'sample',side_effect=AssertionError('no sampling')):
        main()
