"""Complete original legal eight-actual D structural panel; same-pre original B1."""
from collections import Counter, defaultdict
from hashlib import sha1, sha256
from fractions import Fraction
from math import comb
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
    require((len(source),len(native),len(prior),len(bound))==(313,153,564,878),'parent extent')
    for p in bound:
        require(gitblob(ROOT/p)==tree[p],p)
    for p,d in (source|native).items():require(digest(ROOT/p)==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==1035,'runtime extent')
    return {'parent_HEAD':h,'HEAD_byte_bindings':878,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}
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

def digest(p):
    h=sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def gitblob(p):
    h=sha1(b'blob '+str(p.stat().st_size).encode()+b'\0')
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def main():
    start=time.perf_counter();c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    old={n:records(i) for n,i in c['stored'].items()}
    D=[o for t,o in old['catalog'] if t=='DECISION_CONTEXT'];X=[o for t,o in old['catalog'] if t=='CONTROLLER_SITE']
    q={tuple(o['context']):{a:float.fromhex(h) for a,h in o['q_row_hex']} for o in D};alt={tuple(o['context']):o['alternatives'] for o in D}
    bs=next(o['entries'] for t,o in old['basis'] if t=='NATIVE_BASIS');graph={}
    for t,o in old['graph']:
        if t=='NATIVE_LEGAL_EDGE':graph.setdefault(tuple(o['pre']),{})[o['command']]=o['result']
    require((len(D),len(X),len(graph),sum(map(len,graph.values())))==(13824,5904,6254,20588),'full domain')
    require((sum(bool(v) for v in alt.values()),sum(map(len,alt.values())))==(7551,16364),'all original targets')
    oldcells=[o for t,o in old['normalizers'] if t=='COMPLETE_CELL_NORMALIZER']
    require(len(oldcells)==7,'all old Dcells')
    emit('OLD_COMPLETE_NORMALIZERS_READ_ONLY',{'cells':oldcells,'not_recomputed':True,'scientific_measure_adopted':False})
    groups=Counter(a[3:] for a,v in alt.items() if v)
    clustered=sum(comb(n,8) for n in groups.values());M={'clustered':clustered,'distributed':comb(7551,8)-clustered}
    panel=[];scopes=[];nodes=0;terminal_counts=Counter();worldids=set()
    for i,b in enumerate(bs):
        root=(0,2,0,b['kappa'],b['phase'],b['committed'],0);local=Counter();startnodes=nodes
        def visit(n,decl):
            nonlocal nodes
            nodes+=1;require(nodes<=c['guard']['max_query_tree_nodes'],'complete query tree resource guard before native')
            cmd=min(q[n],key=lambda a:(-q[n][a],a))
            for a in [cmd]+(alt[n] if len(decl)<8 else []):
                selected=decl+((n,a),) if a!=cmd else decl;e=graph[n][a]
                if not e['terminal']:visit(tuple(e['post']),selected);continue
                local[len(selected)]+=1;terminal_counts[len(selected)]+=1
                if len(selected)!=8:continue
                require(selected not in worldids,'full8 world distinct across basis');worldids.add(selected)
                S,T=zip(*selected);dm=dict(selected);qm={(addr,t):max(q[addr].values())+(max(q[addr].values())-q[addr][t]) for addr,t in selected}
                pre=predict(root,q,graph,dm,{});require(pre==predict(root,q,graph,{},qm),'independent installers same literal behavior')
                owners=manifestations(pre,q);require(owners==list(S),'all eight selected actual owners')
                app=pre['outcome']!='SUCCESS';posts={};values=[]
                if app:
                    pq=dict(qm)
                    for j,r in enumerate(pre['trace']):
                        addr=tuple(r['pre_state']+[r['z'],r['m']])
                        if addr not in owners:continue
                        g=0.
                        for row in reversed(pre['trace'][j:]):g=float.fromhex(row['reward_hex'])+g
                        entry=(addr,r['a_cmd']);values.append([list(addr),r['a_cmd'],g.hex()])
                        if g==q[addr][r['a_cmd']]:pq.pop(entry,None)
                        else:pq[entry]=g
                    posts={'D_Q':predict(root,q,graph,{},pq),'D_patch':predict(root,q,graph,{},{})}
                shape='clustered' if len({a[3:] for a in S})==1 else 'distributed';mult=[len(alt[a]) for a in S]
                mass=Fraction(1,M[shape])
                for nmult in mult:mass/=nmult
                rec={'id':len(panel),'basis_index':i,'basis':list(root[3:6]),'declarations':[[list(a),t] for a,t in selected],
                    'shape':shape,'original_target_multiplicities':mult,'original_cell_context_subsets':M[shape],
                    'original_unconditioned_candidate_mass':[mass.numerator,mass.denominator],
                    'pre':pre,'all_manifested_owners':[list(a) for a in owners],'full_Oracle_units':[f'Decision_{a[2]}' for a in owners],
                    'reflection_applicable':app,'factual_suffix_targets':values,'posts':posts}
                require(len(panel)<c['guard']['max_native_panel_records'],'complete engineering panel guard before native')
                emit('PREDICTION_BEFORE_ANY_NATIVE',rec);panel.append(rec)
        visit(root,())
        scope={'basis_index':i,'basis':list(root[3:6]),'query_tree_nodes':nodes-startnodes,
            'complete_terminal_counts_by_actual_queries':dict(local),'empty_eight_actual_scope':not local[8],
            'all_outcomes_retained':True,'no_native_lower_k_rerun':True}
        emit('BASIS_SCOPE',scope);scopes.append(scope)
    barrier={'basis_scopes':48,'empty_eight_actual_scopes':sum(s['empty_eight_actual_scope'] for s in scopes),
        'query_tree_nodes':nodes,'complete_terminal_counts_by_actual_queries':dict(terminal_counts),
        'configurations':len(panel),'unique_full_pre_worlds':len(worldids),'installed_k':8,'actual_owners':8,'sentinels_added':0,
        'scope_sha256':sha256(canonical(scopes)).hexdigest(),'prediction_sha256':sha256(canonical(panel)).hexdigest(),
        'full_scientific_k8_support_tested':False,'scientific_measure_adopted':False,'no_result_selected_cases':True}
    require((nodes,len(panel))==(2468096,15927),'prospective structural size unchanged')
    emit('COMPLETE_PANEL_BEFORE_NATIVE',barrier)
    reference=QReferenceView({(K.State(*a[:5]),a[5],a[6]):row for a,row in q.items()},name='v31-stored-nominal-no-DP')
    actual_count=0;actual_digest=sha256(b'[');counts=Counter();changes=Counter();native_rows=0
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
            emit('ACTUAL_COMPLETE_RECORD',a);actual_digest.update((b',' if actual_count else b'')+canonical(a).rstrip(b'\n'));actual_count+=1;counts[arch+':pre:'+p['outcome']]+=1

    actual_digest.update(b']\n');after=bind(c);emit('INPUT_BINDING_AFTER',after);require(after==before,'all source/runtime byte preservation')
    emit('FINAL',{'status':'COMPLETE_ORIGINAL_EIGHT_ACTUAL_D_ONE_TRANSACTION_NOT_SCIENCE',**barrier,
        'actual_records':actual_count,'actual_sha256':actual_digest.hexdigest(),'actual_registry_streamed_without_omission':True,
        'counts':dict(counts),'signed_immediate_changes':dict(changes),'native_raw_rows':native_rows,
        'elapsed_seconds':time.perf_counter()-start,'runtime_inputs':1035,'parent_HEAD_bindings':878,
        'all_inputs_equal':True,'future_training':0,'keys_allocated':0,'new_reference_DP':0,'random_draws':0,
        'collector_executed':False,'scientific_rules_adopted':False,'collection_authorized':False,
        'scientific_PASS':False,'research_complete':False,'mechanism_direction_falsified':False})
def read_ledger(ledger):return json.loads(ledger.canonical())
from rfl_rebuild.method.credit import OracleCreditAdapter
if __name__=='__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode,'derive',side_effect=AssertionError('no keys')), \
         patch.object(training,'train_curve',side_effect=AssertionError('no future training')), \
         patch.object(K.SemanticTape,'sample',side_effect=AssertionError('no sampling')):
        main()
