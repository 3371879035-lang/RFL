"""Mixed persistent D/X structural fulltruth and original own-slice updates only."""
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
from rfl_rebuild.learner.store import Q, DECISION, CONTROLLER, Edit, QAddress, DecisionAddress, LearnerPersistentState

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
    require((len(source),len(native),len(prior),len(bound))==(313,153,594,908),'parent extent')
    for p in bound:
        require(gitblob(ROOT/p)==tree[p],p)
    for p,d in (source|native).items():require(digest(ROOT/p)==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==1065,'runtime extent')
    return {'parent_HEAD':h,'HEAD_byte_bindings':908,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}
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

from rfl_rebuild.b1.controller import resolve_controller_sites
from rfl_rebuild.b1.laws import XId
from rfl_rebuild.b1.runner import run_controller_law
from rfl_rebuild.method.credit import OracleCreditAdapter

def daddr(a):return DecisionAddress(K.State(*a[:5]),a[5],a[6])
def xaddr(a):return K.ControllerSite(K.State(*a[:5]),a[5])
def dlit(a):return [a.state.x,a.state.y,a.state.t,a.state.kappa,a.state.phi,a.z,a.m]
def xlit(a):return [a.state.x,a.state.y,a.state.t,a.state.kappa,a.state.phi,a.cmd]
def stores(s):
    return {'D':sorted([[dlit(a),v] for a,v in s.decision_overrides.items()]),
        'Q':sorted([[dlit(a)+[a.a],float(v).hex()] for a,v in s.q_overrides.items()]),
        'P':sorted([[a,v] for a,v in s.process_overrides.items()]),
        'X':sorted([[xlit(a),v] for a,v in s.controller_overrides.items()])}
def initial(rec,arch,q):
    a,t=rec['D_declaration'];x,u=rec['X_declaration'];n=tuple(a)
    st={'D':[],'Q':[],'P':[],'X':[[x,u]]}
    if arch=='D_Q':
        b=max(q[n].values());st['Q']=[[a+[t],(b+(b-q[n][t])).hex()]]
    else:st['D']=[[a,t]]
    return st
def predict(root,q,graph,st):
    dm={tuple(a):v for a,v in st['D']};qm={tuple(a):float.fromhex(h) for a,h in st['Q']};xm={tuple(a):v for a,v in st['X']};raw=[];n=root
    while True:
        row={a:qm.get(n+(a,),v) for a,v in q[n].items()};cmd=dm.get(n,min(row,key=lambda a:(-row[a],a)))
        u=xm.get(n[:5]+(cmd,),cmd);e=graph[n][u]
        raw.append({'pre_state':list(n[:5]),'z':n[5],'m':n[6],'a_cmd':cmd,'u':u,'a_realized':u,
            'reward_hex':e['reward_hex'],'post_state':e['post'][:5],'post_control':e['post'][5:],
            'terminal':e['terminal'],'outcome':e['outcome'],'illegal':False})
        if e['terminal']:break
        n=tuple(e['post'])
    return {'trace':raw,'outcome':raw[-1]['outcome'],'return_hex':sum(float.fromhex(v['reward_hex']) for v in raw).hex()}
def owners(p,q):
    D=[];X=[]
    for r in p['trace']:
        n=tuple(r['pre_state']+[r['z'],r['m']])
        if q[n][r['a_cmd']]<max(q[n].values())-1e-12:D.append(list(n))
        if r['u']!=r['a_cmd']:X.append(r['pre_state']+[r['a_cmd']])
    return {'D':D,'X':X}
def unitX(a):return f'ControllerSite_{a[0]}_{a[1]}_{a[2]}_{a[5]}'
def units_of(own):return [f'Decision_{a[2]}' for a in own['D']]+[unitX(a) for a in own['X']]
def post_prediction(st,p,own,arch,slice_name,q):
    out={k:list(v) for k,v in st.items()}
    if slice_name=='X':out['X']=[v for v in out['X'] if v[0] not in own['X']]
    elif arch=='D_patch':out['D']=[v for v in out['D'] if v[0] not in own['D']]
    else:
        for j,r in enumerate(p['trace']):
            a=r['pre_state']+[r['z'],r['m']]
            if a not in own['D']:continue
            v=0.
            for rr in reversed(p['trace'][j:]):v=float.fromhex(rr['reward_hex'])+v
            e=a+[r['a_cmd']];out['Q']=[w for w in out['Q'] if w[0]!=e]
            if v!=q[tuple(a)][r['a_cmd']]:out['Q'].append([e,v.hex()])
    return {k:sorted(v) for k,v in out.items()}
def native_install(rec,arch,q,reference):
    a,t=rec['D_declaration'];x,u=rec['X_declaration'];state=LearnerPersistentState()
    if arch=='D_Q':
        b=max(q[tuple(a)].values());d=Edit(Q,QAddress(K.State(*a[:5]),a[5],a[6],t),b+(b-q[tuple(a)][t]))
    else:d=Edit(DECISION,daddr(a),t)
    state.apply_transaction([d,Edit(CONTROLLER,xaddr(x),u)],q_reference=reference)
    require(stores(state)==initial(rec,arch,q),'independent complete installation')
    return state
def payload(trace,scene):return {'trace':factual._trace_payload(trace,scene),'outcome':trace.outcome,'return_hex':trace.return_value.hex()}

def main():
    start=time.perf_counter();c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    old={k:records(v) for k,v in c['stored'].items()}
    D=[o for t,o in old['catalog'] if t=='DECISION_CONTEXT'];X=[o for t,o in old['catalog'] if t=='CONTROLLER_SITE']
    R=[o for t,o in old['revision'] if t=='REVISED_SITE_NOT_ADOPTED']
    q={tuple(o['context']):{a:float.fromhex(h) for a,h in o['q_row_hex']} for o in D}
    da={tuple(o['context']):o['alternatives'] for o in D};xa={tuple(o['site']):o['targets'] for o in R};oa={tuple(o['site']):o['alternatives'] for o in X}
    bs=next(o['entries'] for t,o in old['basis'] if t=='NATIVE_BASIS');graph={}
    for t,o in old['graph']:
        if t=='NATIVE_LEGAL_EDGE':graph.setdefault(tuple(o['pre']),{})[o['command']]=o['result']
    require((len(D),len(X),len(R),len(graph),sum(map(len,graph.values())))==(13824,5904,5904,6254,20588),'full originalsupport')
    require((sum(bool(v) for v in da.values()),sum(map(len,da.values())),sum(bool(v) for v in xa.values()),sum(map(len,xa.values())))==(7551,16364,4464,8928),'complete original/candidate targets')
    fixedD={k:next((tuple(o['context']),min(o['alternatives'])) for o in D if o['context'][3]!=k and o['alternatives']) for k in range(2)}
    fixedX={k:next((tuple(o['site']),min(o['alternatives'])) for o in X if o['site'][3]!=k and o['alternatives']) for k in range(2)}
    panel=[];scopes=[];worlds=[];worldids={};nodes=0;terminal=Counter()
    for i,b in enumerate(bs):
        root=(0,2,0,b['kappa'],b['phase'],b['committed'],0);local=Counter();startnodes=nodes
        def visit(n,dd,xx):
            nonlocal nodes
            nodes+=1;require(nodes<=c['guard']['max_query_tree_nodes'],'prospective treeguard')
            nominal=min(q[n],key=lambda a:(-q[n][a],a))
            for cmd in [nominal]+(da[n] if dd is None else []):
                dn=(n,cmd) if cmd!=nominal else dd;s=n[:5]+(cmd,)
                for u in [cmd]+(xa[s] if xx is None else []):
                    xn=(s,u) if u!=cmd else xx;e=graph[n][u]
                    if not e['terminal']:visit(tuple(e['post']),dn,xn);continue
                    degree=f'{int(dn is not None)},{int(xn is not None)}';local[degree]+=1;terminal[degree]+=1
                    d=dn or fixedD[root[3]];x=xn or fixedX[root[3]];identity=(d,x)
                    if identity not in worldids:
                        wid=len(worlds);worldids[identity]=wid
                        mass=Fraction(1,7551*4464*len(da[d[0]])*len(xa[x[0]]))
                        oldmass=Fraction(1,7551*3312*len(da[d[0]])*len(oa[x[0]])) if x[1] in oa[x[0]] else None
                        worlds.append({'world_id':wid,'D_declaration':[list(d[0]),d[1]],'X_declaration':[list(x[0]),x[1]],
                            'domain_command_mass':[mass.numerator,mass.denominator],
                            'old_all8_mass':[oldmass.numerator,oldmass.denominator] if oldmass else None})
                    rec={'id':len(panel),'world_id':worldids[identity],'basis_index':i,'basis':list(root[3:6]),
                        'D_declaration':[list(d[0]),d[1]],'X_declaration':[list(x[0]),x[1]],'actual_degree':degree,
                        'fixed_unread_channels':[k for k,v in [('D',dn),('X',xn)] if v is None]}
                    pre=predict(root,q,graph,initial(rec,'D_patch',q));own=owners(pre,q)
                    require((len(own['D']),len(own['X']))==(int(dn is not None),int(xn is not None)),'completeactualtruth')
                    rec.update({'pre':pre,'owners':own,'full_units':units_of(own),'reflection_applicable':pre['outcome']!='SUCCESS','posts':{}})
                    for arch in ('D_Q','D_patch'):
                        st=initial(rec,arch,q);require(predict(root,q,graph,st)==pre,'independent extensional world')
                        rec['posts'][arch]={sl:predict(root,q,graph,post_prediction(st,pre,own,arch,sl,q)) for sl in ('D','X') if rec['reflection_applicable'] and own[sl]}
                    panel.append(rec);require(len(panel)<=c['guard']['max_native_panel_records'],'prospective panelguard')
        visit(root,None,None)
        sc={'basis_index':i,'basis':list(root[3:6]),'query_tree_nodes':nodes-startnodes,'complete_terminal_counts_by_actual_degree':dict(local),'empty_mixed_actual_scope':not local['1,1']}
        scopes.append(sc);emit('BASIS_SCOPE',sc)
    for w in worlds:emit('FULL_PRE_WORLD_BEFORE_NATIVE',w)
    for rec in panel:emit('PREDICTION_BEFORE_ANY_NATIVE',rec)
    barrier={'basis_scopes':48,'query_tree_nodes':nodes,'complete_terminal_counts_by_actual_degree':dict(terminal),
        'basis_world_records':len(panel),'unique_full_pre_worlds':len(worlds),'empty_mixed_actual_scopes':sum(s['empty_mixed_actual_scope'] for s in scopes),
        'scope_sha256':sha256(canonical(scopes)).hexdigest(),'world_sha256':sha256(canonical(worlds)).hexdigest(),'prediction_sha256':sha256(canonical(panel)).hexdigest(),
        'mixed_product_scientific_grammar_adopted':False,'complete_mixed_normalizer':None,'cross_store_hybrid_treatment':False,'no_outcome_filter':True}
    emit('COMPLETE_PANEL_BEFORE_NATIVE',barrier)
    reference=QReferenceView({(K.State(*a[:5]),a[5],a[6]):row for a,row in q.items()},name='v31-stored-nominal-no-DP')
    counts=Counter();changes=Counter();rawrows=0;actual_count=0;ad=sha256(b'[')
    for rec in panel:
        k,phi,z=rec['basis'];scene=EvaluationScene(k,phi,0,0,z)
        for arch in ('D_Q','D_patch'):
            pre=native_install(rec,arch,q,reference);fp=fingerprint(pre);st=stores(pre)
            trace=learned_rollout(pre,kappa=k,tape=scene.tape,base_option=z,q_reference=reference);p=payload(trace,scene)
            emit('RAW_FACTUAL_BEFORE_TRUTH',{'id':rec['id'],'installation':arch,'payload':p,'full_pre_store':st,'fingerprint_pre':fp})
            require(p==rec['pre'] and fingerprint(pre)==fp,'nativefactual prediction')
            truth=factual._persistent_truth(trace,scene,reference);oracle=OracleCreditAdapter.evaluate(truth['Gamma_P_star'])
            units=rec['full_units'];require(set(units)==oracle and len(units)==len(oracle),'full originalOracle no trimming')
            du=[u for u in units if u.startswith('Decision_')];xu=[u for u in units if u.startswith('ControllerSite_')]
            require(du+xu==units,'complete exact familypartition')
            d=resolve_credited_units(du,trace,k,phi);x=resolve_controller_sites(xu,trace,k,phi)
            require({'D':[dlit(a) for a in d],'X':[xlit(a) for a in x]}==rec['owners'],'all originalrho')
            projection={'D':{'units':du,'off_slice_units':xu,'owners':[dlit(a) for a in d]},'X':{'units':xu,'off_slice_units':du,'owners':[xlit(a) for a in x]}}
            emit('FULL_ORIGINAL_TRUTH_BEFORE_B1',{'id':rec['id'],'installation':arch,'truth':truth,'full_units':units,'projections':projection})
            comparisons={};counts['factual_rollouts']+=1;rawrows+=len(p['trace']);counts[arch+':pre:'+p['outcome']]+=1;counts['degree:'+rec['actual_degree']]+=1
            for sl,own in [('D',d),('X',x)]:
                status='SUCCESS_REFLECTION_INAPPLICABLE' if not rec['reflection_applicable'] else 'EMPTY_ARCHITECTURE_PROJECTION' if not own else 'ORIGINAL_SAME_TIER_COMPARISON'
                arms=[];counts[arch+':'+sl+':'+status]+=1
                if status=='ORIGINAL_SAME_TIER_COMPARISON':
                    treatment=XId if sl=='X' else FactualReturnWrite if arch=='D_Q' else DeleteFactualPatch
                    for role,law in [('reference',NoWriteRef(Tier.L0_FACTUAL)),('treatment',treatment)]:
                        clone=pre.clone();tx=[];native_apply=LearnerPersistentState.apply_transaction
                        def apply(state,edits,**kwargs):
                            es=tuple(edits);tx.append({'on_this_clone':state is clone,'fingerprint_pre':fingerprint(state),'entry_edits':len(es),'stores':[e.store for e in es]})
                            return native_apply(state,es,**kwargs)
                        with patch.object(LearnerPersistentState,'apply_transaction',new=apply):
                            if sl=='X':result=run_controller_law(law,clone,own,learner_rows(trace,k,phi))
                            elif arch=='D_Q':result=run_dq_law(law,clone,own,learner_rows(trace,k,phi),reference)
                            else:result=run_patch_law(law,clone,du,trace,k,phi,None)
                        require(tuple(v.address for v in result.ledger.receipts)==own,'all ownprojectionreceipts')
                        want=[] if role=='reference' else [{'on_this_clone':True,'fingerprint_pre':fp,'entry_edits':len(own),'stores':[CONTROLLER if sl=='X' else Q if arch=='D_Q' else DECISION]*len(own)}]
                        require(tx==want,'original ownslice once fullpretransaction no hybrid')
                        pst=st if role=='reference' else post_prediction(st,p,rec['owners'],arch,sl,q)
                        require(stores(clone)==pst and fingerprint(pre)==fp,'completepoststore/offslice preserved')
                        post=learned_rollout(clone,kappa=k,tape=scene.tape,base_option=z,q_reference=reference);pp=payload(post,scene)
                        require(pp==(p if role=='reference' else rec['posts'][arch][sl]) and fingerprint(clone)==result.ledger.fingerprint_post,'postprediction/fingerprint')
                        arms.append({'role':role,'law':law.name,'tier':Tier.L0_FACTUAL.name,'ledger':json.loads(result.ledger.canonical()),'transactions':tx,'full_post_store':stores(clone),'payload':pp})
                        counts['B1_arms']+=1;counts['post_rollouts']+=1;rawrows+=len(pp['trace'])
                        if role=='treatment':
                            counts['treatment_transactions']+=len(tx);counts[arch+':'+sl+':post:'+pp['outcome']]+=1
                            delta=float.fromhex(pp['return_hex'])-float.fromhex(p['return_hex']);changes[arch+':'+sl+':'+('positive' if delta>0 else 'negative' if delta<0 else 'zero')]+=1
                comparisons[sl]={'status':status,'same_tier_arms':arms,'effect_not_imputed':status!='ORIGINAL_SAME_TIER_COMPARISON'}
            row={'id':rec['id'],'world_id':rec['world_id'],'installation':arch,'full_pre_store':st,'fingerprint_pre':fp,'source_fingerprint_after':fingerprint(pre),
                'payload':p,'truth':truth,'full_units':units,'projections':projection,'comparisons':comparisons}
            emit('ACTUAL_COMPLETE_RECORD',row);ad.update((b',' if actual_count else b'')+canonical(row).rstrip(b'\n'));actual_count+=1
    ad.update(b']\n');after=bind(c);emit('INPUT_BINDING_AFTER',after);require(after==before,'allinputdrift')
    emit('FINAL',{'status':'COMPLETE_MIXED_PERSISTENT_ORIGINAL_OWN_SLICE_PROJECTIONS_NOT_HYBRID_OR_SCIENCE',**barrier,
        'actual_records':actual_count,'actual_sha256':ad.hexdigest(),'counts':dict(counts),'signed_immediate_changes':dict(changes),'native_raw_rows':rawrows,
        'runtime_inputs':1065,'parent_HEAD_bindings':908,'elapsed_seconds':time.perf_counter()-start,'all_inputs_equal':True,
        'new_reference_DP':0,'keys_allocated':0,'future_training':0,'random_draws':0,'collector_executed':False,'scientific_rules_adopted':False,
        'collection_authorized':False,'scientific_PASS':False,'research_complete':False,'mechanism_direction_falsified':False})
if __name__=='__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode,'derive',side_effect=AssertionError('no keys')), \
         patch.object(training,'train_curve',side_effect=AssertionError('no futuretraining')), \
         patch.object(K.SemanticTape,'sample',side_effect=AssertionError('no randomdraw')):
        main()

