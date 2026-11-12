"""Stdlib independent full stored native semantics, transaction and support check."""
from collections import Counter, deque
from hashlib import sha1, sha256
from itertools import combinations, product
from pathlib import Path
import json, math, subprocess
HERE=Path(__file__).resolve().parent; PREP=HERE.parent; ROOT=HERE.parents[4]
def read(p):return json.loads(p.read_bytes())
def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def require(ok,why):
    if not ok:raise AssertionError(why)
def capture(folder,info=None,strict=False):
    cl,ex=read(folder/'claim.json'),read(folder/'exit.json')
    require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items()),'claim exit')
    for n,v in ex['files'].items():
        b=(folder/n).read_bytes();require({'bytes':len(b),'sha256':sha256(b).hexdigest()}==v,'complete bytes')
    require(not (folder/'stderr.log').read_bytes(),'native stderr')
    if info:require(ex['files']['stdout.log']['sha256']==info['stdout_sha256'],'stored capture identity')
    for n,h in ex['inputs'].items():require(sha256((folder.parent/n).read_bytes()).hexdigest()==h,'executed source')
    out=[]
    for l in (folder/'stdout.log').read_bytes().splitlines(keepends=True):
        require(l.endswith(b'\n'),'partial capture line')
        if b'=' not in l:
            require(not strict,'untagged new line');continue
        t,v=l.rstrip(b'\r\n').split(b'=',1)
        if v[:1] not in (b'[',b'{'):
            require(not strict,'nonJSON new line');continue
        o=json.loads(v)
        if strict:require(canonical(o).rstrip(b'\n')==v,'noncanonical new JSON')
        out.append((t.decode(),o))
    return out
def fingerprint(st):
    parts=[]
    parts.append('\n'.join(sorted('D:'+','.join(map(str,a+[v])) for a,v in st['D'])))
    parts.append('\n'.join(sorted(f'P:{a},{v}' for a,v in st['P'])))
    require(not st['X'],'expected healthy X')
    parts.append('')
    parts.append('\n'.join(sorted('Q:'+','.join(map(str,a))+'|'+h for a,h in st['Q'])))
    return sha256(b'\0'.join(x.encode() for x in parts)).hexdigest()
def normal(st):
    return {k:sorted(v) for k,v in st.items()}
def step(n,a):
    x,y,t,k,phi,z,m=n;dx,dy=((0,-1),(0,1),(-1,0),(1,0),(0,0))[a];nx,ny=x+dx,y+dy;nt=t+1
    outcome='COLLISION' if (nx,ny)==(2,2) and nt%(6,3)[k]==phi%(6,3)[k] else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
    nm=int(bool(m or z==1 and (nx,ny)==(2,1) or z==3 and (nx,ny)==(2,4) or z==2 and (x,y)==(1,2) and t%(6,3)[k]!=phi%(6,3)[k]))
    return {'post':[nx,ny,nt,k,phi,z,nm],'a_cmd':a,'u':a,'a_realized':a,
            'reward_hex':(-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)).hex(),
            'terminal':outcome is not None,'outcome':outcome,'illegal':False}
def rollout(root,q,st):
    dm={tuple(a):v for a,v in st['D']};qm={tuple(a):float.fromhex(h) for a,h in st['Q']};n=root;raw=[]
    while True:
        row={a:qm.get(n+(a,),v) for a,v in q[n].items()}
        a=dm.get(n,sorted(row,key=lambda a:(-row[a],a))[0]);e=step(n,a)
        raw.append({'pre_state':list(n[:5]),'z':n[5],'m':n[6],'a_cmd':a,'u':a,'a_realized':a,
             'reward_hex':e['reward_hex'],'post_state':e['post'][:5],'post_control':e['post'][5:],
             'terminal':e['terminal'],'outcome':e['outcome'],'illegal':False})
        if e['terminal']:break
        n=tuple(e['post'])
    return {'trace':raw,'outcome':raw[-1]['outcome'],'return_hex':sum(float.fromhex(r['reward_hex']) for r in raw).hex()}
def truth(p,q):
    rows=[];owners=[]
    for r in p['trace']:
        n=tuple(r['pre_state']+[r['z'],r['m']]);b=max(q[n].values());optimal=sorted(a for a,v in q[n].items() if v>=b-1e-12)
        rows.append({'pre_state':r['pre_state'],'z':n[5],'m':n[6],'a_learner':r['a_cmd'],'u_learner':r['u'],'optimal_actions':optimal})
        if r['a_cmd'] not in optimal:owners.append(list(n))
    times=[a[2] for a in owners]
    return {'truth_source':'A75_LEARNER_BASELINE_MANIFESTATIONS_NOT_R_MECH','J_L':[False,bool(owners),False],
       'manifested_process_proposals':[],'manifested_decision_timesteps':times,'manifested_controller_sites':[],
       'Gamma_P_star':[f'Decision_{t}' for t in times],'Gamma_T_star':None,'R_mech':None,'whole_optimal_set_tolerance':1e-12,
       'source_separated_baseline_rows':rows},owners
def expected_store(declarations,arch,q):
    st={'D':[],'Q':[],'P':[],'X':[]}
    for a,t in declarations:
        if arch=='D_patch':st['D'].append([a,t])
        else:
            b=max(q[tuple(a)].values());st['Q'].append([a+[t],(b+(b-q[tuple(a)][t])).hex()])
    return st
def post_store(st,p,owners,arch,q):
    result={k:list(v) for k,v in st.items()};targets=[]
    for j,r in enumerate(p['trace']):
        a=r['pre_state']+[r['z'],r['m']]
        if a not in owners:continue
        value=0.
        for h in reversed(p['trace'][j:]):value=float.fromhex(h['reward_hex'])+value
        targets.append([a,r['a_cmd'],value.hex()])
        if arch=='D_patch':result['D']=[v for v in result['D'] if v[0]!=a]
        else:
            e=a+[r['a_cmd']];result['Q']=[v for v in result['Q'] if v[0]!=e]
            if value!=q[tuple(a)][r['a_cmd']]:result['Q'].append([e,value.hex()])
    return result,targets
def ledger(pre,post,owners,arch,role,q):
    fp1,fp2=fingerprint(pre),fingerprint(post);receipts=[];deltas=[]
    for a in owners:
        changed=role=='treatment'
        receipts.append(','.join(map(str,a))+'|'+('APPLIED|1' if changed else 'EVALUABLE_NOOP|0'))
        if arch=='D_Q' and changed:
            e=next(e for e,h in pre['Q'] if e[:7]==a)
            before=float.fromhex(next(h for v,h in pre['Q'] if v==e))
            after=float.fromhex(next((h for v,h in post['Q'] if v==e),q[tuple(a)][e[7]].hex()))
            deltas.append(abs(after-before))
    return {'receipts':sorted(receipts),'fingerprint_pre':fp1,'fingerprint_post':fp2,'scalar_metrics_applicable':arch=='D_Q',
        'n_scalar':len(deltas),'sum_abs_delta':math.fsum(deltas),'max_abs_delta':max(deltas,default=0.)}
def main():
    c=read(HERE/'contract.json');r=capture(HERE/'evidence',strict=True);tags=Counter(t for t,o in r)
    before=r[0][1];require(r[0][0]=='INPUT_BINDING_BEFORE','binding first')
    require(before==next(o for t,o in r if t=='INPUT_BINDING_AFTER'),'complete beforeafter')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'HEAD')
    tree={v.split(b'\t')[1].decode():v.split()[2].decode() for v in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if v}
    source=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit'];native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')};bound=set(source)|prior|{'experiments/rebuild_status_current.json'}
    extent=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require((len(source),len(native),len(prior),len(bound),len(extent))==(313,153,449,763,920),'extent')
    require(set(before['input_sha256'])==extent,'complete inputs')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (source|native|before['input_sha256']).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    old={n:capture(PREP/i['folder'],i) for n,i in c['stored'].items()}
    D=[o for t,o in old['catalog'] if t=='DECISION_CONTEXT'];X=[o for t,o in old['catalog'] if t=='CONTROLLER_SITE']
    q={tuple(o['context']):{a:float.fromhex(h) for a,h in o['q_row_hex']} for o in D};alt={}
    cells={(0,2),(4,2)}|{(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)}
    shifts=((0,-1),(0,1),(-1,0),(1,0),(0,0));dist={(4,2):0};queue=deque(dist)
    while queue:
        x,y=queue.popleft()
        for dx,dy in shifts:
            s=(x+dx,y+dy)
            if s in cells and s not in dist:dist[s]=dist[(x,y)]+1;queue.append(s)
    domain=[(x,y,t,k,phi,z,m) for t in range(12) for k in range(2) for phi in range(6) for x,y in sorted(cells-{(4,2)}) for z in range(4) for m in range(2)]
    require([tuple(o['context']) for o in D]==domain and len(X)==5904,'full original domain')
    for o in D:
        n=tuple(o['context']);x,y,t,k,phi,z,m=n;legal=[]
        for a,(dx,dy) in enumerate(shifts):
            s=(x+dx,y+dy)
            if s not in cells or z==0 and dist[s]!=dist[(x,y)]-1 or z in (1,3) and m==0 and s==(4,2) or z==2 and m==0 and s in ((2,2),(4,2)):continue
            legal.append(a)
        require(legal==list(q[n]),'independent legal target domain')
        b=max(q[n].values());alternatives=[a for a in legal if q[n][a]<b-1e-12]
        require(o['alternatives']==alternatives,'full alternatives');alt[n]=alternatives
    graph={}
    for t,o in old['graph']:
        if t=='NATIVE_LEGAL_EDGE':
            n=tuple(o['pre']);require(o['result']==step(n,o['command']),'all native step semantics')
            require(o['command'] not in graph.setdefault(n,{}),'duplicate edge');graph[n][o['command']]=o['result']
    reachable={(0,2,0,k,phi,z,0) for k in range(2) for phi in range(6) for z in range(4)};queue=deque(reachable)
    while queue:
        n=queue.popleft();require(set(graph[n])==set(q[n]),'full branch closure')
        for e in graph[n].values():
            post=tuple(e['post'])
            if not e['terminal'] and post not in reachable:reachable.add(post);queue.append(post)
    require(len(reachable)==len(graph)==6254 and sum(map(len,graph.values()))==20588,'full graph')
    bs=next(o['entries'] for t,o in old['basis'] if t=='NATIVE_BASIS');empty={'D':[],'Q':[],'P':[],'X':[]}
    panel=[];subsets=0;scopes=[o for t,o in r if t=='BASIS_SCOPE'];pred=[o for t,o in r if t=='PREDICTION_BEFORE_ANY_NATIVE']
    for i,b in enumerate(bs):
        root=(0,2,0,b['kappa'],b['phase'],b['committed'],0);nom=rollout(root,q,empty)
        packed=[[v['pre_state'],v['z'],v['m'],v['a_cmd'],v['u'],v['a_realized'],v['reward_hex'],v['post_state'],v['post_control'],v['terminal'],v['outcome'],v['illegal']] for v in nom['trace']]
        require(packed==b['payload']['trace'],'old complete basis raw')
        V=[tuple(v['pre_state']+[v['z'],v['m']]) for v in nom['trace'] if alt[tuple(v['pre_state']+[v['z'],v['m']])]]
        require(scopes[i]=={'basis_index':i,'basis':list(root[3:6]),'eligible_contexts':[list(n) for n in V]},'complete empty/nonempty basis scope')
        for S in combinations(V,2):
            subsets+=1
            for T in product(*(alt[n] for n in S)):
                declarations=[[list(n),t] for n,t in zip(S,T)];pre=rollout(root,q,expected_store(declarations,'D_patch',q));tr,owners=truth(pre,q)
                applicable=pre['outcome']!='SUCCESS' and bool(owners);posts={};targets=[]
                for arch in ('D_Q','D_patch'):
                    st=expected_store(declarations,arch,q);require(rollout(root,q,st)==pre,'independent extensional pre')
                    if applicable:
                        post,values=post_store(st,pre,owners,arch,q);posts[arch]=rollout(root,q,post);targets=values
                shape='clustered' if S[0][3:]==S[1][3:] else 'distributed'
                expect={'id':len(panel),'basis_index':i,'basis':list(root[3:6]),'declarations':declarations,'shape':shape,
                    'original_target_multiplicities':[len(alt[n]) for n in S],'original_cell_context_subsets':388724 if shape=='clustered' else 28116301,
                    'pre':pre,'all_manifested_owners':owners,'full_Oracle_units':tr['Gamma_P_star'],'reflection_applicable':applicable,
                    'factual_suffix_targets':targets,'posts':posts}
                require(pred[len(panel)]==expect,'prospective complete prediction');panel.append(expect)
    require((subsets,len(panel))==(624,3968),'structural panel extent')
    barrier=next(j for j,(t,o) in enumerate(r) if t=='COMPLETE_PANEL_BEFORE_NATIVE')
    require(all(t not in ('RAW_FACTUAL_BEFORE_TRUTH','FULL_ORIGINAL_TRUTH_BEFORE_B1','ACTUAL_COMPLETE_RECORD') for t,o in r[:barrier]),'predictions before any native')
    actual=[o for t,o in r if t=='ACTUAL_COMPLETE_RECORD'];raw=[o for t,o in r if t=='RAW_FACTUAL_BEFORE_TRUTH'];truths=[o for t,o in r if t=='FULL_ORIGINAL_TRUTH_BEFORE_B1']
    require(len(actual)==len(raw)==len(truths)==7936,'complete actual extent')
    tail=r[barrier+1:-2];require([t for t,o in tail]==['RAW_FACTUAL_BEFORE_TRUTH','FULL_ORIGINAL_TRUTH_BEFORE_B1','ACTUAL_COMPLETE_RECORD']*7936,'full raw before truth before B1')
    counts=Counter();changes=Counter();unconsulted=Counter();rawrows=0;delta_values=[]
    for j,a in enumerate(actual):
        rec=panel[j//2];arch=('D_Q','D_patch')[j%2];root=(0,2,0,*rec['basis'],0);pre=expected_store(rec['declarations'],arch,q);fp=fingerprint(pre);p=rec['pre'];tr,owners=truth(p,q)
        require(a['id']==rec['id'] and a['architecture']==arch and normal(a['full_pre_store'])==normal(pre),'full pre declarations')
        require(a['fingerprint_pre']==a['source_fingerprint_after']==fp and a['payload']==p and a['truth']==tr and a['all_resolved_owners']==owners and a['full_units']==tr['Gamma_P_star'],'full truth/raw/store fingerprint')
        require(raw[j]=={'id':rec['id'],'architecture':arch,'payload':p,'full_pre_store':a['full_pre_store'],'fingerprint_pre':fp},'raw before truth complete')
        require(truths[j]=={'id':rec['id'],'architecture':arch,'truth':tr,'units':tr['Gamma_P_star'],'owners':owners},'truth before transaction')
        counts['factual_rollouts']+=1;rawrows+=len(p['trace']);counts[arch+':pre:'+p['outcome']]+=1;unconsulted[arch+':'+str(2-len(owners))]+=1
        require(a['reflection_applicable']==rec['reflection_applicable'],'reflection policy')
        if not rec['reflection_applicable']:
            require(a['same_tier_arms']==[],'successful reflected case');counts['reflection_inapplicable_'+p['outcome']]+=1;continue
        counts['failing_records']+=1;counts['manifestations_'+str(len(owners))]+=1
        require(len(a['same_tier_arms'])==2,'same tier pair')
        for role,arm in zip(('reference','treatment'),a['same_tier_arms']):
            post=pre if role=='reference' else post_store(pre,p,owners,arch,q)[0];pp=rollout(root,q,post)
            require(arm['role']==role and arm['tier']=='L0_FACTUAL','tier')
            require(arm['law']==('NoWrite' if role=='reference' else 'FactualReturnWrite' if arch=='D_Q' else 'DeleteFactualPatch'),'original law')
            require(normal(arm['full_post_store'])==normal(post) and arm['payload']==pp,'complete post untouched declarations and behavior')
            require(arm['ledger']==ledger(pre,post,owners,arch,role,q),'full original receipt/scalar accounting')
            expectedtx=[] if role=='reference' else [{'on_this_clone':True,'fingerprint_pre':fp,'entry_edits':len(owners)}]
            require(arm['transactions']==expectedtx,'one transaction all truth')
            counts['B1_arms']+=1;counts['post_rollouts']+=1;rawrows+=len(pp['trace'])
            if role=='treatment':
                counts['treatment_transactions']+=1;counts[arch+':post:'+pp['outcome']]+=1
                delta=float.fromhex(pp['return_hex'])-float.fromhex(p['return_hex']);delta_values.append(delta)
                changes[arch+':'+('positive' if delta>0 else 'negative' if delta<0 else 'zero')]+=1
    final=r[-1][1];require(r[-1][0]=='FINAL','final')
    require(final['counts']==dict(counts) and final['signed_immediate_changes']==dict(changes) and final['native_raw_rows']==rawrows,'complete counters')
    require(final['prediction_sha256']==sha256(canonical(panel)).hexdigest() and final['actual_sha256']==sha256(canonical(actual)).hexdigest(),'complete ordered hashes')
    require(all(final[k]==0 for k in ('future_training','keys_allocated','new_reference_DP','random_draws')) and all(final[k] is False for k in ('collector_executed','scientific_rules_adopted','collection_authorized','scientific_PASS','research_complete','mechanism_direction_falsified')),'scope')
    require(tags==Counter({'INPUT_BINDING_BEFORE':1,'BASIS_SCOPE':48,'PREDICTION_BEFORE_ANY_NATIVE':3968,'COMPLETE_PANEL_BEFORE_NATIVE':1,'RAW_FACTUAL_BEFORE_TRUTH':7936,'FULL_ORIGINAL_TRUTH_BEFORE_B1':7936,'ACTUAL_COMPLETE_RECORD':7936,'INPUT_BINDING_AFTER':1,'FINAL':1}),'complete output language')
    print('CHECK='+canonical({'status':'COMPLETE_NATIVE_PAIR_STORED_CHECK_NOT_SCIENCE','implementation_independence':'PRIMARY_ONLY_NOT_EXPERT',
        'sources':313,'old_native':153,'prior_preparation':449,'HEAD_byte_bindings':763,'runtime_inputs':920,
        'complete_original_D':13824,'complete_old_X_retained':5904,'old_native_graph_edges':20588,'old_basis':48,
        'panel_configurations':3968,'actual_records':7936,'counts':dict(counts),'signed_changes':dict(changes),
        'unconsulted_installed_entries_retained':dict(unconsulted),'native_raw_rows':rawrows,
        'min_treatment_delta':min(delta_values,default=None),'max_treatment_delta':max(delta_values,default=None),
        'no_RFL_candidate_old_checker_solver_execution':True,'scientific_PASS':False,'collection_authorized':False,'research_complete':False}).decode().rstrip('\n'))
if __name__=='__main__':main()
