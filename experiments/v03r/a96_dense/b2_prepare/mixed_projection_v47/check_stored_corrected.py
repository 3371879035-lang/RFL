"""Primary independent stdlib complete mixed stored audit, not expert/science gate."""
from collections import Counter, deque
from hashlib import sha1, sha256
from fractions import Fraction
from pathlib import Path
import ast, json, math, subprocess
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

def normal(st):
    return {k:sorted(v) for k,v in st.items()}

def step(n,a):
    x,y,t,k,phi,z,m=n;dx,dy=((0,-1),(0,1),(-1,0),(1,0),(0,0))[a];nx,ny=x+dx,y+dy;nt=t+1
    outcome='COLLISION' if (nx,ny)==(2,2) and nt%(6,3)[k]==phi%(6,3)[k] else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
    nm=int(bool(m or z==1 and (nx,ny)==(2,1) or z==3 and (nx,ny)==(2,4) or z==2 and (x,y)==(1,2) and t%(6,3)[k]!=phi%(6,3)[k]))
    return {'post':[nx,ny,nt,k,phi,z,nm],'a_cmd':a,'u':a,'a_realized':a,
            'reward_hex':(-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)).hex(),
            'terminal':outcome is not None,'outcome':outcome,'illegal':False}

def digest_file(p):
    h=sha256();n=0
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b);n+=len(b)
    return {'bytes':n,'sha256':h.hexdigest()}

def streamed_capture(p):
    cl,ex=read(p/'claim.json'),read(p/'exit.json')
    require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items()),'full streaming claim exit')
    for n,h in ex['files'].items():require(digest_file(p/n)==h,'full streamed bytes')
    require((p/'stderr.log').stat().st_size==0,'complete empty stderr')
    for n,h in ex['inputs'].items():require(digest_file(p.parent/n)['sha256']==h,'full executed source bytes')
    with (p/'stdout.log').open('rb') as f:
        for l in f:
            require(l.endswith(b'\n'),'complete newline')
            t,v=l.rstrip(b'\r\n').split(b'=',1);o=json.loads(v)
            require(canonical(o).rstrip(b'\n')==v,'full new canonical JSON')
            yield t.decode(),o

def gitblob(p):
    h=sha1(b'blob '+str(p.stat().st_size).encode()+b'\0')
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def fingerprint(st):
    parts=['\n'.join(sorted('D:'+','.join(map(str,a+[v])) for a,v in st['D'])),
        '\n'.join(sorted(f'P:{a},{v}' for a,v in st['P'])),
        '\n'.join(sorted('X:'+','.join(map(str,a+[v])) for a,v in st['X'])),
        '\n'.join(sorted('Q:'+','.join(map(str,a))+'|'+h for a,h in st['Q']))]
    return sha256(b'\0'.join(v.encode() for v in parts)).hexdigest()
def rollout(root,q,st):
    dd={tuple(a):v for a,v in st['D']};xx={tuple(a):v for a,v in st['X']};qq={tuple(a):float.fromhex(v) for a,v in st['Q']};n=root;raw=[]
    while True:
        cmd=dd.get(n,sorted(q[n],key=lambda a:(-qq.get(n+(a,),q[n][a]),a))[0]);u=xx.get(n[:5]+(cmd,),cmd)
        require(cmd in q[n] and u in q[n],'command/output admissibility')
        e=step(n,u);raw.append({'pre_state':list(n[:5]),'z':n[5],'m':n[6],'a_cmd':cmd,'u':u,'a_realized':u,
            'reward_hex':e['reward_hex'],'post_state':e['post'][:5],'post_control':e['post'][5:],'terminal':e['terminal'],'outcome':e['outcome'],'illegal':False})
        if e['terminal']:break
        n=tuple(e['post'])
    return {'trace':raw,'outcome':raw[-1]['outcome'],'return_hex':sum(float.fromhex(v['reward_hex']) for v in raw).hex()}
def truth(p,q):
    own={'D':[],'X':[]};rows=[]
    for r in p['trace']:
        n=tuple(r['pre_state']+[r['z'],r['m']]);b=max(q[n].values());optimal=sorted(a for a,v in q[n].items() if v>=b-1e-12)
        rows.append({'pre_state':r['pre_state'],'z':r['z'],'m':r['m'],'a_learner':r['a_cmd'],'u_learner':r['u'],'optimal_actions':optimal})
        if r['a_cmd'] not in optimal:own['D'].append(list(n))
        if r['u']!=r['a_cmd']:own['X'].append(r['pre_state']+[r['a_cmd']])
    gamma=[f'Decision_{a[2]}' for a in own['D']]+[f'ControllerSite_{a[0]}_{a[1]}_{a[2]}_{a[5]}' for a in own['X']]
    return {'truth_source':'A75_LEARNER_BASELINE_MANIFESTATIONS_NOT_R_MECH','J_L':[False,bool(own['D']),bool(own['X'])],
        'manifested_process_proposals':[],'manifested_decision_timesteps':[a[2] for a in own['D']],
        'manifested_controller_sites':own['X'],'Gamma_P_star':gamma,'Gamma_T_star':None,'R_mech':None,'whole_optimal_set_tolerance':1e-12,
        'source_separated_baseline_rows':rows},own
def expected_store(rec,arch,q):
    a,t=rec['D_declaration'];x,u=rec['X_declaration'];st={'D':[],'Q':[],'P':[],'X':[[x,u]]}
    if arch=='D_patch':st['D']=[[a,t]]
    else:
        b=max(q[tuple(a)].values());st['Q']=[[a+[t],(b+(b-q[tuple(a)][t])).hex()]]
    return st
def post_store(st,p,own,arch,sl,q):
    out={k:list(v) for k,v in st.items()}
    if sl=='X':out['X']=[v for v in out['X'] if v[0] not in own['X']]
    elif arch=='D_patch':out['D']=[v for v in out['D'] if v[0] not in own['D']]
    else:
        g=0.;suffix=[]
        for r in reversed(p['trace']):g=float.fromhex(r['reward_hex'])+g;suffix.append(g)
        suffix.reverse()
        for j,r in enumerate(p['trace']):
            a=r['pre_state']+[r['z'],r['m']]
            if a not in own['D']:continue
            entry=a+[r['a_cmd']];out['Q']=[v for v in out['Q'] if v[0]!=entry]
            if suffix[j]!=q[tuple(a)][r['a_cmd']]:out['Q'].append([entry,suffix[j].hex()])
    return normal(out)
def ledger(pre,post,own,arch,sl,role,q):
    scalar=arch=='D_Q' and sl=='D';receipts=[];deltas=[]
    for a in own[sl]:
        label=','.join(map(str,a)) if sl=='D' else ','.join(map(str,a[:5]))+'|'+str(a[5]);changed=role=='treatment'
        receipts.append(label+'|'+('APPLIED|1' if changed else 'EVALUABLE_NOOP|0'))
        if scalar and changed:
            e,h=next((e,h) for e,h in pre['Q'] if e[:7]==a)
            new=next((v for n,v in post['Q'] if n==e),q[tuple(a)][e[7]].hex());deltas.append(abs(float.fromhex(new)-float.fromhex(h)))
    return {'receipts':sorted(receipts),'fingerprint_pre':fingerprint(pre),'fingerprint_post':fingerprint(post),
        'scalar_metrics_applicable':scalar,'n_scalar':len(deltas),'sum_abs_delta':math.fsum(deltas),'max_abs_delta':max(deltas,default=0.)}

def main():
    c=read(HERE/'contract.json');stream=iter(streamed_capture(HERE/'evidence_repaired'));tags=Counter();prefix=[]
    def take(expected=None):
        t,o=next(stream);tags[t]+=1
        if expected:require(t==expected,'full stream language '+expected)
        return t,o
    while True:
        pair=take();prefix.append(pair)
        if pair[0]=='COMPLETE_PANEL_BEFORE_NATIVE':break
        require(pair[0] not in ('RAW_FACTUAL_BEFORE_TRUTH','FULL_ORIGINAL_TRUTH_BEFORE_B1','ACTUAL_COMPLETE_RECORD'),'allpred before anynative')
    require(prefix[0][0]=='INPUT_BINDING_BEFORE','bindingfirst');before=prefix[0][1]
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'HEAD')
    tree={v.split(b'\t')[1].decode():v.split()[2].decode() for v in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if v}
    source=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit'];native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')};bound=set(source)|prior|{'experiments/rebuild_status_current.json'}
    extent=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py','repair_contract.json','candidate_corrected.py','execute_repaired.py','check_stored_corrected.py')}
    extent|={(HERE/'evidence'/n).relative_to(ROOT).as_posix() for n in ('claim.json','exit.json','stdout.log','stderr.log')}
    require((len(source),len(native),len(prior),len(bound),len(extent))==(313,153,594,908,1073),'extent')
    require(set(before['input_sha256'])==extent,'complete inputs')
    for p in bound:
        require(gitblob(ROOT/p)==tree[p],p)
    for p,d in (source|native|before['input_sha256']).items():require(digest_file(ROOT/p)['sha256']==d,p)
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

    require((sum(bool(v) for v in alt.values()),sum(map(len,alt.values())))==(7551,16364),'all original eligible/targets')
    xdomain=[];xa={};oa={}
    for t in range(12):
        for x,y in sorted(cells-{(4,2)}):
            for k in range(2):
                for phi in range(6):
                    rows=[set(q[x,y,t,k,phi,z,m]) for z in range(4) for m in range(2)]
                    union=set.union(*rows);all8=set.intersection(*rows)
                    for cmd in sorted(union):
                        site=(x,y,t,k,phi,cmd);xdomain.append(site)
                        serving=[row for row in rows if cmd in row]
                        xa[site]=sorted(set.intersection(*serving)-{cmd});oa[site]=sorted(all8-{cmd})
    R=[o for t,o in old['revision'] if t=='REVISED_SITE_NOT_ADOPTED']
    require([tuple(o['site']) for o in X]==xdomain==[tuple(o['site']) for o in R],'all5904 original X enumeration')
    require(all(o['alternatives']==oa[tuple(o['site'])] for o in X) and all(o['targets']==xa[tuple(o['site'])] for o in R),'complete two grammars no reachableonly filtering')
    require((sum(bool(v) for v in xa.values()),sum(map(len,xa.values())),sum(bool(v) for v in oa.values()),sum(map(len,oa.values())))==(4464,8928,3312,3600),'completeX support')
    fixedD={k:next((n,min(alt[n])) for n in domain if n[3]!=k and alt[n]) for k in range(2)}
    fixedX={k:next((s,min(oa[s])) for s in xdomain if s[3]!=k and oa[s]) for k in range(2)}
    panel=[];worlds=[];worldids={};scopes=[];nodes=0;terminal=Counter()
    require(len(bs)==48 and [(b['kappa'],b['phase'],b['committed']) for b in bs]==[(k,p,z) for k in range(2) for p in range(6) for z in range(4)],'old48basis sequence')
    for i,b in enumerate(bs):
        root=(0,2,0,b['kappa'],b['phase'],b['committed'],0);nom=rollout(root,q,empty)
        packed=[[v['pre_state'],v['z'],v['m'],v['a_cmd'],v['u'],v['a_realized'],v['reward_hex'],v['post_state'],v['post_control'],v['terminal'],v['outcome'],v['illegal']] for v in nom['trace']]
        require(packed==b['payload']['trace'] and nom['return_hex']==b['payload']['return_hex'],'old full278basis rows')
        local=Counter();startnodes=nodes;stack=[('node',root,None,None)]
        while stack:
            kind,n,d,x=stack.pop()
            if kind=='node':
                nodes+=1;require(nodes<=c['guard']['max_query_tree_nodes'],'fullnodeguard')
                greedy=sorted(q[n],key=lambda a:(-q[n][a],a))[0];branches=[]
                for cmd in [greedy]+(alt[n] if d is None else []):
                    dd=(n,cmd) if cmd!=greedy else d;s=n[:5]+(cmd,)
                    for u in [cmd]+(xa[s] if x is None else []):
                        xx=(s,u) if u!=cmd else x;e=step(n,u)
                        branches.append(('terminal' if e['terminal'] else 'node',tuple(e['post']),dd,xx))
                stack.extend(reversed(branches));continue
            degree=f'{int(d is not None)},{int(x is not None)}';local[degree]+=1;terminal[degree]+=1
            actualD=d;actualX=x;d=d or fixedD[root[3]];x=x or fixedX[root[3]];identity=(d,x)
            if identity not in worldids:
                wid=len(worlds);worldids[identity]=wid
                mass=Fraction(1,7551)/4464/len(alt[d[0]])/len(xa[x[0]])
                oldmass=Fraction(1,7551)/3312/len(alt[d[0]])/len(oa[x[0]]) if x[1] in oa[x[0]] else None
                worlds.append({'world_id':wid,'D_declaration':[list(d[0]),d[1]],'X_declaration':[list(x[0]),x[1]],
                    'domain_command_mass':[mass.numerator,mass.denominator],'old_all8_mass':[oldmass.numerator,oldmass.denominator] if oldmass else None})
            rec={'id':len(panel),'world_id':worldids[identity],'basis_index':i,'basis':list(root[3:6]),'D_declaration':[list(d[0]),d[1]],'X_declaration':[list(x[0]),x[1]],
                'actual_degree':degree,'fixed_unread_channels':[sl for sl,a in [('D',actualD),('X',actualX)] if a is None]}
            pre=rollout(root,q,expected_store(rec,'D_patch',q));tr,own=truth(pre,q)
            require((len(own['D']),len(own['X']))==(int(actualD is not None),int(actualX is not None)),'alltrue manifest sets')
            app=pre['outcome']!='SUCCESS';rec.update({'pre':pre,'owners':own,'full_units':tr['Gamma_P_star'],'reflection_applicable':app,'posts':{}})
            for arch in ('D_Q','D_patch'):
                st=expected_store(rec,arch,q);require(rollout(root,q,st)==pre,'independentpolicy install')
                rec['posts'][arch]={sl:rollout(root,q,post_store(st,pre,own,arch,sl,q)) for sl in ('D','X') if app and own[sl]}
                for sl in ('D','X'):
                    if sl in rec['fixed_unread_channels']:
                        key=rec[sl+'_declaration'][0]
                        allp=[pre]+list(rec['posts'][arch].values())
                        for pp in allp:
                            visited=[v['pre_state']+([v['z'],v['m']] if sl=='D' else [v['a_cmd']]) for v in pp['trace']]
                            require(key not in visited,'complete oppositekappa declaration never consulted')
            panel.append(rec);require(len(panel)<=c['guard']['max_native_panel_records'],'fullpanelguard')
        scopes.append({'basis_index':i,'basis':list(root[3:6]),'query_tree_nodes':nodes-startnodes,'complete_terminal_counts_by_actual_degree':dict(local),'empty_mixed_actual_scope':not local['1,1']})
    require(scopes==[o for t,o in prefix if t=='BASIS_SCOPE'],'all48scopes')
    require(worlds==[o for t,o in prefix if t=='FULL_PRE_WORLD_BEFORE_NATIVE'],'allfullworld measures and identity')
    require(panel==[o for t,o in prefix if t=='PREDICTION_BEFORE_ANY_NATIVE'],'allfullpredictions independentstack')
    barrier={'basis_scopes':48,'query_tree_nodes':nodes,'complete_terminal_counts_by_actual_degree':dict(terminal),'basis_world_records':len(panel),
        'unique_full_pre_worlds':len(worlds),'empty_mixed_actual_scopes':sum(s['empty_mixed_actual_scope'] for s in scopes),'scope_sha256':sha256(canonical(scopes)).hexdigest(),
        'world_sha256':sha256(canonical(worlds)).hexdigest(),'prediction_sha256':sha256(canonical(panel)).hexdigest(),
        'mixed_product_scientific_grammar_adopted':False,'complete_mixed_normalizer':None,'cross_store_hybrid_treatment':False,'no_outcome_filter':True}
    require(prefix[-1][1]==barrier,'completebarrier');del prefix
    rc=read(HERE/'repair_contract.json');require(all(barrier[k]==v for k,v in rc['expected_barrier'].items()),'same original failure full panel')
    original=read(HERE/'evidence/exit.json');require(original==rc['original_failure'] and original['native_child_exit_code']==1,'original native failure preserved')
    for n,v in original['files'].items():require(digest_file(HERE/'evidence'/n)==v,'original full failure capture')
    require((HERE/'evidence/stderr.log').read_text(encoding='utf8')==rc['original_stderr_complete'],'original complete error')
    counts=Counter();changes=Counter();rawrows=0;actual_count=0;ad=sha256(b'[');deltas=[];initiald=[];posttruth=Counter();world_members=Counter('old_and_revised' if w['old_all8_mass'] is not None else 'revised_only' for w in worlds)
    for j in range(2*len(panel)):
        raw,trrow,a=[take(t)[1] for t in ('RAW_FACTUAL_BEFORE_TRUTH','FULL_ORIGINAL_TRUTH_BEFORE_B1','ACTUAL_COMPLETE_RECORD')]
        rec=panel[j//2];arch=('D_Q','D_patch')[j%2];root=(0,2,0,*rec['basis'],0);st=expected_store(rec,arch,q);p=rec['pre'];fp=fingerprint(st);tr,own=truth(p,q)
        units=tr['Gamma_P_star'];du=units[:len(own['D'])];xu=units[len(own['D']):]
        projection={'D':{'units':du,'off_slice_units':xu,'owners':own['D']},'X':{'units':xu,'off_slice_units':du,'owners':own['X']}}
        require(a['id']==rec['id'] and a['world_id']==rec['world_id'] and a['installation']==arch and a['full_pre_store']==st,'completepreworld')
        require(a['fingerprint_pre']==a['source_fingerprint_after']==fp and a['payload']==p and a['truth']==tr and a['full_units']==units and a['projections']==projection and a['oracle_status']==('ORIGINAL_ORACLE_NONEMPTY_CALLED' if units else 'NO_MANIFESTATION_ORACLE_INAPPLICABLE'),'fullraw truth/projections/sourcefingerprint')
        require(raw=={'id':rec['id'],'installation':arch,'payload':p,'full_pre_store':st,'fingerprint_pre':fp},'rawbeforetruth')
        require(trrow=={'id':rec['id'],'installation':arch,'truth':tr,'full_units':units,'projections':projection,'oracle_status':('ORIGINAL_ORACLE_NONEMPTY_CALLED' if units else 'NO_MANIFESTATION_ORACLE_INAPPLICABLE')},'truthbeforeB1')
        counts['factual_rollouts']+=1;rawrows+=len(p['trace']);counts[arch+':pre:'+p['outcome']]+=1;counts['degree:'+rec['actual_degree']]+=1
        initiald.append(float.fromhex(p['return_hex'])-float.fromhex(bs[rec['basis_index']]['payload']['return_hex']))
        for sl in ('D','X'):
            comparison=a['comparisons'][sl];status='SUCCESS_REFLECTION_INAPPLICABLE' if not rec['reflection_applicable'] else 'EMPTY_ARCHITECTURE_PROJECTION' if not own[sl] else 'ORIGINAL_SAME_TIER_COMPARISON'
            counts[arch+':'+sl+':'+status]+=1
            require(comparison['status']==status and comparison['effect_not_imputed']==(status!='ORIGINAL_SAME_TIER_COMPARISON'),'empty/success not0effect')
            arms=comparison['same_tier_arms'];require(len(arms)==(2 if status=='ORIGINAL_SAME_TIER_COMPARISON' else 0),'fullpairedarm count')
            for role,arm in zip(('reference','treatment'),arms):
                pst=st if role=='reference' else post_store(st,p,own,arch,sl,q);pp=rollout(root,q,pst)
                law='NoWrite' if role=='reference' else 'X_id' if sl=='X' else 'FactualReturnWrite' if arch=='D_Q' else 'DeleteFactualPatch'
                require(arm['role']==role and arm['law']==law and arm['tier']=='L0_FACTUAL','original law/tier')
                require(arm['full_post_store']==pst and arm['payload']==pp and arm['ledger']==ledger(st,pst,own,arch,sl,role,q),'fullstore/raw/receipt/scalar/canonical')
                store='controller' if sl=='X' else 'q' if arch=='D_Q' else 'decision'
                tx=[] if role=='reference' else [{'on_this_clone':True,'fingerprint_pre':fp,'entry_edits':len(own[sl]),'stores':[store]*len(own[sl])}]
                require(arm['transactions']==tx,'once ownslice samefullpre no hybrid')
                for field in ('D','Q','P','X'):
                    if field!=('X' if sl=='X' else 'Q' if arch=='D_Q' else 'D'):require(pst[field]==st[field],'offslice/latentdeclarations not repaired')
                counts['B1_arms']+=1;counts['post_rollouts']+=1;rawrows+=len(pp['trace'])
                if role=='treatment':
                    counts['treatment_transactions']+=len(tx);counts[arch+':'+sl+':post:'+pp['outcome']]+=1
                    delta=float.fromhex(pp['return_hex'])-float.fromhex(p['return_hex']);deltas.append(delta)
                    changes[arch+':'+sl+':'+('positive' if delta>0 else 'negative' if delta<0 else 'zero')]+=1
                    _,remaining=truth(pp,q);posttruth[arch+':'+sl+':'+str(len(remaining['D']))+','+str(len(remaining['X']))]+=1
        if actual_count:ad.update(b',')
        ad.update(canonical(a).rstrip(b'\n'));actual_count+=1
    ad.update(b']\n');after=take('INPUT_BINDING_AFTER')[1];require(after==before,'allinputpreservation')
    final=take('FINAL')[1];require(next(stream,None) is None,'fullEOF')
    require(final['counts']==dict(counts) and final['signed_immediate_changes']==dict(changes) and final['native_raw_rows']==rawrows and final['actual_sha256']==ad.hexdigest() and final['actual_records']==actual_count,'completecounters actualcanonicalarray')
    require(all(final[k]==v for k,v in barrier.items()),'barriercarried')
    require(all(final[k]==0 for k in ('new_reference_DP','keys_allocated','future_training','random_draws')) and all(final[k] is False for k in ('collector_executed','scientific_rules_adopted','collection_authorized','scientific_PASS','research_complete','mechanism_direction_falsified')),'authority')
    require(tags==Counter({'INPUT_BINDING_BEFORE':1,'BASIS_SCOPE':48,'FULL_PRE_WORLD_BEFORE_NATIVE':len(worlds),'PREDICTION_BEFORE_ANY_NATIVE':len(panel),'COMPLETE_PANEL_BEFORE_NATIVE':1,
        'RAW_FACTUAL_BEFORE_TRUTH':actual_count,'FULL_ORIGINAL_TRUTH_BEFORE_B1':actual_count,'ACTUAL_COMPLETE_RECORD':actual_count,'INPUT_BINDING_AFTER':1,'FINAL':1}),'fullcapturelanguage')
    for node in ast.walk(ast.parse((HERE/'check_stored_corrected.py').read_bytes())):
        if isinstance(node,ast.Import):require(all(a.name.split('.')[0] not in ('rfl_rebuild','candidate','check_stored') for a in node.names),'stdlibonly')
        if isinstance(node,ast.ImportFrom):require(not node.module or node.module.split('.')[0] not in ('rfl_rebuild','candidate','check_stored'),'stdlibonly')
    print('CHECK='+canonical({'status':'FULL_MIXED_ORIGINAL_OWN_SLICE_STORED_CHECK_NOT_HYBRID_OR_SCIENCE',**barrier,'runtime_inputs':1073,'parent_HEAD_bindings':908,
        'complete_original_D':13824,'complete_X':5904,'old_graph_edges':20588,'old_basis_rows':278,'counts':dict(counts),'signed_changes':dict(changes),'native_raw_rows':rawrows,
        'actual_records':actual_count,'actual_sha256':ad.hexdigest(),'world_membership':dict(world_members),'treatment_post_manifestations':dict(posttruth),
        'initial_signed_min':min(initiald),'initial_signed_max':max(initiald),'treatment_signed_min':min(deltas,default=None),'treatment_signed_max':max(deltas,default=None),
        'no_RFL_candidate_old_checker_solver_execution':True,'implementation_independence':'PRIMARY_ONLY_NOT_EXPERT','full_capture_streamed_without_omission':True,
        'scientific_PASS':False,'collection_authorized':False,'research_complete':False}).decode().rstrip('\n'))
if __name__=='__main__':main()




