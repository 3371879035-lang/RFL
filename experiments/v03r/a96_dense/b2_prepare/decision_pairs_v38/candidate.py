"""Prospective complete nominal-path pair panel; original multi-owner B1 only."""
from collections import Counter
from hashlib import sha1, sha256
from itertools import combinations, product
from pathlib import Path
import json, subprocess, sys, time
from unittest.mock import patch
HERE=Path(__file__).resolve().parent; PREP=HERE.parent; ROOT=HERE.parents[4]
sys.path.insert(0,str(PREP)); sys.path.insert(0,str(ROOT/'src'))
import factual_event_candidate as factual
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b1.laws import NoWriteRef, FactualReturnWrite, DeleteFactualPatch
from rfl_rebuild.b1.runner import run_dq_law, run_patch_law
from rfl_rebuild.b1.targets import resolve_credited_units
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import Q, DECISION, Edit, QAddress, DecisionAddress, LearnerPersistentState

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
    require((len(source),len(native),len(prior),len(bound))==(313,153,449,763),'parent extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (source|native).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==920,'runtime extent')
    return {'parent_HEAD':h,'HEAD_byte_bindings':763,'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}
def context(a):return DecisionAddress(K.State(*a[:5]),a[5],a[6])
def store_payload(state):
    return {'D':[[[a.state.x,a.state.y,a.state.t,a.state.kappa,a.state.phi,a.z,a.m],v] for a,v in sorted(state.decision_overrides.items(),key=lambda x:repr(x[0]))],
            'Q':[[[a.state.x,a.state.y,a.state.t,a.state.kappa,a.state.phi,a.z,a.m,a.a],float(v).hex()] for a,v in sorted(state.q_overrides.items(),key=lambda x:repr(x[0]))],
            'P':[[a,v] for a,v in sorted(state.process_overrides.items())],
            'X':[[str(a),v] for a,v in sorted(state.controller_overrides.items(),key=lambda x:repr(x[0]))]}
def payload(trace,scene):
    return {'trace':factual._trace_payload(trace,scene),'outcome':trace.outcome,'return_hex':trace.return_value.hex()}
def predict(root,q,graph,D,Qv):
    n=root;raw=[]
    while True:
        row=dict(q[n]);row.update({a:v for (owner,a),v in Qv.items() if owner==n})
        a=D.get(n,min(row,key=lambda a:(-row[a],a)));e=graph[n][a]
        raw.append({'pre_state':list(n[:5]),'z':n[5],'m':n[6],'a_cmd':a,'u':a,'a_realized':a,
                    'reward_hex':e['reward_hex'],'post_state':e['post'][:5],'post_control':e['post'][5:],
                    'terminal':e['terminal'],'outcome':e['outcome'],'illegal':False})
        if e['terminal']:break
        n=tuple(e['post'])
    return {'trace':raw,'outcome':raw[-1]['outcome'],'return_hex':sum(float.fromhex(r['reward_hex']) for r in raw).hex()}
def manifestations(p,q):
    return [tuple(r['pre_state']+[r['z'],r['m']]) for r in p['trace']
            if q[tuple(r['pre_state']+[r['z'],r['m']])][r['a_cmd']]<max(q[tuple(r['pre_state']+[r['z'],r['m']])].values())-1e-12]
def main():
    start=time.perf_counter();c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    old={n:records(i) for n,i in c['stored'].items()}
    D=[o for t,o in old['catalog'] if t=='DECISION_CONTEXT'];q={tuple(o['context']):{a:float.fromhex(h) for a,h in o['q_row_hex']} for o in D}
    alt={tuple(o['context']):o['alternatives'] for o in D}
    bs=next(o['entries'] for t,o in old['basis'] if t=='NATIVE_BASIS')
    graph={}
    for t,r in old['graph']:
        if t=='NATIVE_LEGAL_EDGE':graph.setdefault(tuple(r['pre']),{})[r['command']]=r['result']
    require((len(D),len(graph),sum(map(len,graph.values())))==(13824,6254,20588),'complete bound domain')
    panel=[];subsets=0
    for i,b in enumerate(bs):
        v=[tuple(r[0]+[r[1],r[2]]) for r in b['payload']['trace'] if alt[tuple(r[0]+[r[1],r[2]])]]
        emit('BASIS_SCOPE',{'basis_index':i,'basis':[b['kappa'],b['phase'],b['committed']],'eligible_contexts':[list(a) for a in v]})
        root=(0,2,0,b['kappa'],b['phase'],b['committed'],0)
        for S in combinations(v,2):
            subsets+=1
            for T in product(*(alt[a] for a in S)):
                dm=dict(zip(S,T)); qm={(a,t):max(q[a].values())+(max(q[a].values())-q[a][t]) for a,t in zip(S,T)}
                pre=predict(root,q,graph,dm,{})
                require(pre==predict(root,q,graph,{},qm),'independent extensional installers differ')
                owners=manifestations(pre,q);units=[f'Decision_{a[2]}' for a in owners]
                applicable=pre['outcome']!='SUCCESS' and bool(owners)
                posts={};values=[]
                if applicable:
                    pd={a:t for a,t in dm.items() if a not in owners};pq=dict(qm)
                    for j,r in enumerate(pre['trace']):
                        a=tuple(r['pre_state']+[r['z'],r['m']])
                        if a not in owners:continue
                        g=0.
                        for h in reversed(pre['trace'][j:]):g=float.fromhex(h['reward_hex'])+g
                        entry=(a,r['a_cmd']);values.append([list(a),r['a_cmd'],g.hex()])
                        if g==q[a][r['a_cmd']]:pq.pop(entry,None)
                        else:pq[entry]=g
                    posts={'D_patch':predict(root,q,graph,pd,{}),'D_Q':predict(root,q,graph,{},pq)}
                rec={'id':len(panel),'basis_index':i,'basis':[b['kappa'],b['phase'],b['committed']],
                     'declarations':[[list(a),t] for a,t in zip(S,T)],'shape':'clustered' if S[0][3:]==S[1][3:] else 'distributed',
                     'original_target_multiplicities':[len(alt[a]) for a in S],
                     'original_cell_context_subsets':388724 if S[0][3:]==S[1][3:] else 28116301,
                     'pre':pre,'all_manifested_owners':[list(a) for a in owners],'full_Oracle_units':units,
                     'reflection_applicable':applicable,'factual_suffix_targets':values,'posts':posts}
                emit('PREDICTION_BEFORE_ANY_NATIVE',rec);panel.append(rec)
    require((subsets,len(panel))==(624,3968),'prospective panel extent')
    emit('COMPLETE_PANEL_BEFORE_NATIVE',{'subsets':subsets,'configurations':len(panel),'prediction_sha256':sha256(canonical(panel)).hexdigest(),
         'all_full_support_bound':13824,'scientific_measure_adopted':False,'no_result_selected_cases':True})
    reference=QReferenceView({(K.State(*a[:5]),a[5],a[6]):row for a,row in q.items()},name='v31-stored-nominal-no-DP')
    actual=[];counts=Counter();changes=Counter();native_rows=0
    for rec in panel:
        k,phi,z=rec['basis'];scene=EvaluationScene(k,phi,0,0,z)
        for arch in ('D_Q','D_patch'):
            pre=LearnerPersistentState();edits=[]
            for a,t in rec['declarations']:
                owner=context(a)
                if arch=='D_Q':
                    row=reference.row(owner.state,owner.z,owner.m);b=max(row.values());v=b+(b-row[t])
                    require(v>b,'fixed DQ amplitude');edits.append(Edit(Q,QAddress(owner.state,owner.z,owner.m,t),v))
                else:edits.append(Edit(DECISION,owner,t))
            pre.apply_transaction(edits,q_reference=reference);fp=fingerprint(pre);prestore=store_payload(pre)
            trace=learned_rollout(pre,kappa=k,tape=scene.tape,base_option=z,q_reference=reference)
            p=payload(trace,scene);counts['factual_rollouts']+=1;native_rows+=len(p['trace'])
            emit('RAW_FACTUAL_BEFORE_TRUTH',{'id':rec['id'],'architecture':arch,'payload':p,'full_pre_store':prestore,'fingerprint_pre':fp})
            require(p==rec['pre'] and fingerprint(pre)==fp,'native factual or source drift')
            truth=factual._persistent_truth(trace,scene,reference)
            oracle=OracleCreditAdapter.evaluate(truth['Gamma_P_star'])
            units=tuple(sorted(oracle,key=lambda a:int(a.split('_')[1])))
            owners=resolve_credited_units(units,trace,k,phi)
            require(list(units)==rec['full_Oracle_units'] and [list((a.state.x,a.state.y,a.state.t,a.state.kappa,a.state.phi,a.z,a.m)) for a in owners]==rec['all_manifested_owners'],'full original credit/rho mismatch')
            emit('FULL_ORIGINAL_TRUTH_BEFORE_B1',{'id':rec['id'],'architecture':arch,'truth':truth,'units':list(units),'owners':rec['all_manifested_owners']})
            arms=[]
            if rec['reflection_applicable']:
                counts['failing_records']+=1;counts['manifestations_'+str(len(owners))]+=1
                for role,law in (('reference',NoWriteRef(Tier.L0_FACTUAL)),('treatment',FactualReturnWrite if arch=='D_Q' else DeleteFactualPatch)):
                    clone=pre.clone();tx=[];native_apply=LearnerPersistentState.apply_transaction
                    def apply(state,edits,**kwargs):
                        tx.append({'on_this_clone':state is clone,'fingerprint_pre':fingerprint(state),'entry_edits':len(edits)})
                        return native_apply(state,edits,**kwargs)
                    with patch.object(LearnerPersistentState,'apply_transaction',new=apply):
                        result=run_dq_law(law,clone,owners,learner_rows(trace,k,phi),reference) if arch=='D_Q' else run_patch_law(law,clone,units,trace,k,phi,None)
                    require(tuple(r.address for r in result.ledger.receipts)==owners,'ledger trimmed credit')
                    require((not tx) if role=='reference' else (len(tx)==1 and tx[0]=={'on_this_clone':True,'fingerprint_pre':fp,'entry_edits':len(owners)}),'not one same-pre complete transaction')
                    post=learned_rollout(clone,kappa=k,tape=scene.tape,base_option=z,q_reference=reference);pp=payload(post,scene)
                    counts['B1_arms']+=1;counts['post_rollouts']+=1;native_rows+=len(pp['trace'])
                    require(pp==(p if role=='reference' else rec['posts'][arch]),'native post differs from prospective semantic prediction')
                    require(fingerprint(clone)==result.ledger.fingerprint_post and fingerprint(pre)==fp,'post/source drift')
                    arms.append({'role':role,'law':law.name,'tier':Tier.L0_FACTUAL.name,'ledger':read_ledger(result.ledger),
                                 'transactions':tx,'full_post_store':store_payload(clone),'payload':pp})
                    if role=='treatment':
                        counts['treatment_transactions']+=len(tx)
                        delta=float.fromhex(pp['return_hex'])-float.fromhex(p['return_hex'])
                        changes[arch+':'+('positive' if delta>0 else 'negative' if delta<0 else 'zero')]+=1
                        counts[arch+':post:'+pp['outcome']]+=1
            else:counts['reflection_inapplicable_'+p['outcome']]+=1
            a={'id':rec['id'],'architecture':arch,'full_pre_store':prestore,'fingerprint_pre':fp,
               'payload':p,'truth':truth,'all_resolved_owners':rec['all_manifested_owners'],'full_units':list(units),
               'reflection_applicable':rec['reflection_applicable'],'same_tier_arms':arms,'source_fingerprint_after':fingerprint(pre)}
            emit('ACTUAL_COMPLETE_RECORD',a);actual.append(a);counts[arch+':pre:'+p['outcome']]+=1
    after=bind(c);emit('INPUT_BINDING_AFTER',after);require(after==before,'complete runtime drift')
    emit('FINAL',{'status':'COMPLETE_ORIGINAL_PAIR_B1_ENGINEERING_NOT_SCIENCE','configurations':3968,'actual_records':len(actual),
         'prediction_sha256':sha256(canonical(panel)).hexdigest(),'actual_sha256':sha256(canonical(actual)).hexdigest(),
         'counts':dict(counts),'signed_immediate_changes':dict(changes),'native_raw_rows':native_rows,'elapsed_seconds':time.perf_counter()-start,
         'all_inputs_equal':True,'full_scientific_pair_support_tested':False,'future_training':0,'keys_allocated':0,'new_reference_DP':0,
         'random_draws':0,'collector_executed':False,'scientific_rules_adopted':False,'collection_authorized':False,
         'scientific_PASS':False,'research_complete':False,'mechanism_direction_falsified':False})
def read_ledger(ledger):return json.loads(ledger.canonical())
from rfl_rebuild.method.credit import OracleCreditAdapter
if __name__=='__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode,'derive',side_effect=AssertionError('no keys')), \
         patch.object(training,'train_curve',side_effect=AssertionError('no future training')), \
         patch.object(K.SemanticTape,'sample',side_effect=AssertionError('no sampling')):
        main()
