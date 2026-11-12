"""Independent stdlib full stored native X raw/truth/store/transaction check."""
from collections import Counter,defaultdict,deque
from fractions import Fraction as F
from hashlib import sha1,sha256
from itertools import product
from math import comb
from pathlib import Path
import ast,json,subprocess
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4];DEG=8
def read(p):return json.loads(p.read_bytes())
def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def require(x,s):
    if not x:raise AssertionError(s)
def pack(p):return [[x.numerator,x.denominator] for x in p]
def choose(n,k):return comb(n,k) if 0<=k<=n else 0
def capture(p,info=None,strict=False):
    cl,ex=read(p/'claim.json'),read(p/'exit.json');require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items()),'claim exit')
    for n,h in ex['files'].items():
        b=(p/n).read_bytes();require(h=={'bytes':len(b),'sha256':sha256(b).hexdigest()},'full bytes')
    require(not (p/'stderr.log').read_bytes(),'stderr')
    for n,h in ex['inputs'].items():require(sha256((p.parent/n).read_bytes()).hexdigest()==h,'stored executed inputs')
    if info:require(ex['files']['stdout.log']['sha256']==info['stdout_sha256'],'stored capture identity')
    out=[]
    for l in (p/'stdout.log').read_bytes().splitlines(keepends=True):
        require(l.endswith(b'\n'),'incomplete line')
        if b'=' not in l:
            require(not strict,'untagged line');continue
        t,v=l.rstrip(b'\r\n').split(b'=',1)
        if v[:1] not in (b'[',b'{'):
            require(not strict,'nonJSON');continue
        o=json.loads(v)
        if strict:require(canonical(o).rstrip(b'\n')==v,'new canonical')
        out.append((t.decode(),o))
    return out
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
def step(n,a):
    x,y,t,k,phi,z,m=n;dx,dy=((0,-1),(0,1),(-1,0),(1,0),(0,0))[a];nx,ny=x+dx,y+dy;nt=t+1
    outcome='COLLISION' if (nx,ny)==(2,2) and nt%(6,3)[k]==phi%(6,3)[k] else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
    nm=int(bool(m or z==1 and (nx,ny)==(2,1) or z==3 and (nx,ny)==(2,4) or z==2 and (x,y)==(1,2) and t%(6,3)[k]!=phi%(6,3)[k]))
    return {'post':[nx,ny,nt,k,phi,z,nm],'a_cmd':a,'u':a,'a_realized':a,
            'reward_hex':(-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)).hex(),
            'terminal':outcome is not None,'outcome':outcome,'illegal':False}


def store(declarations):return {'D':[],'P':[],'Q':[],'X':sorted(declarations)}
def fp(st):
    require(not st['D'] and not st['P'] and not st['Q'],'all nonX stores empty')
    return sha256(b'\0\0'+('\n'.join(sorted('X:'+','.join(map(str,a+[v])) for a,v in st['X']))).encode()+b'\0').hexdigest()
def rollout(root,q,st):
    assigned={tuple(a):v for a,v in st['X']};n=root;raw=[]
    while True:
        cmd=sorted(q[n],key=lambda a:(-q[n][a],a))[0];u=assigned.get(n[:5]+(cmd,),cmd);e=step(n,u)
        require(u in q[n],'full serving context output admissible')
        raw.append({'pre_state':list(n[:5]),'z':n[5],'m':n[6],'a_cmd':cmd,'u':u,'a_realized':u,
            'reward_hex':e['reward_hex'],'post_state':e['post'][:5],'post_control':e['post'][5:],
            'terminal':e['terminal'],'outcome':e['outcome'],'illegal':False})
        if e['terminal']:break
        n=tuple(e['post'])
    return {'trace':raw,'outcome':raw[-1]['outcome'],'return_hex':sum(float.fromhex(v['reward_hex']) for v in raw).hex()}
def original_truth(p,q):
    rows=[];owners=[];decisions=[]
    for r in p['trace']:
        n=tuple(r['pre_state']+[r['z'],r['m']]);best=max(q[n].values());opt=sorted(a for a,v in q[n].items() if v>=best-1e-12)
        rows.append({'pre_state':r['pre_state'],'z':r['z'],'m':r['m'],'a_learner':r['a_cmd'],'u_learner':r['u'],'optimal_actions':opt})
        if r['a_cmd'] not in opt:decisions.append(n[2])
        if r['u']!=r['a_cmd']:owners.append(r['pre_state']+[r['a_cmd']])
    require(not decisions,'pureX original truth must not be trimmed')
    units=[f'ControllerSite_{a[0]}_{a[1]}_{a[2]}_{a[5]}' for a in owners]
    return {'truth_source':'A75_LEARNER_BASELINE_MANIFESTATIONS_NOT_R_MECH','J_L':[False,False,bool(owners)],
        'manifested_process_proposals':[],'manifested_decision_timesteps':[],'manifested_controller_sites':owners,
        'Gamma_P_star':units,'Gamma_T_star':None,'R_mech':None,'whole_optimal_set_tolerance':1e-12,
        'source_separated_baseline_rows':rows},owners
def expected_ledger(pre,post,owners,role):
    rec=[','.join(map(str,a[:5]))+'|'+str(a[5])+'|'+('APPLIED|1' if role=='treatment' else 'EVALUABLE_NOOP|0') for a in owners]
    return {'receipts':sorted(rec),'fingerprint_pre':fp(pre),'fingerprint_post':fp(post),
        'scalar_metrics_applicable':False,'n_scalar':0,'sum_abs_delta':0.,'max_abs_delta':0.}
def main():
    c=read(HERE/'contract.json');stream=iter(streamed_capture(HERE/'evidence'));tag=Counter()
    def take(expected=None):
        t,o=next(stream);tag[t]+=1
        if expected:require(t==expected,'complete stream language order: '+str(expected))
        return t,o
    r=[]
    while True:
        pair=take();r.append(pair)
        if pair[0]=='COMPLETE_PANEL_BEFORE_NATIVE':break
        require(pair[0] not in ['RAW_FACTUAL_BEFORE_TRUTH','FULL_ORIGINAL_TRUTH_BEFORE_B1','ACTUAL_COMPLETE_RECORD'],'all predictions before native')
    before=r[0][1];require(r[0][0]=='INPUT_BINDING_BEFORE','first binding')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'HEAD')
    tree={v.split(b'\t')[1].decode():v.split()[2].decode() for v in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if v}
    src=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources'];audit=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=audit['fixed_native_file_hashes']|audit['post_controller_commit_native_tail_hashes'];prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(src)|prior|{'experiments/rebuild_status_current.json'};inputs=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('candidate.py','check_stored.py','execute.py','contract.json')}
    require((len(src),len(native),len(prior),len(bound),len(inputs))==(313,153,549,863,1020) and set(before['input_sha256'])==inputs,'extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,h in (src|native|before['input_sha256']).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==h,p)
    old={n:capture(PREP/i['folder'],i) for n,i in c['stored'].items()}
    D=[o for t,o in old['catalog'] if t=='DECISION_CONTEXT'];X=[o for t,o in old['catalog'] if t=='CONTROLLER_SITE'];R=[o for t,o in old['revision'] if t=='REVISED_SITE_NOT_ADOPTED']
    q={tuple(o['context']):{a:float.fromhex(h) for a,h in o['q_row_hex']} for o in D};nom={n:sorted(row,key=lambda a:(-row[a],a))[0] for n,row in q.items()};sites={n:n[:5]+(nom[n],) for n in q}
    cells={(0,2),(4,2)}|{(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)};shifts=((0,-1),(0,1),(-1,0),(1,0),(0,0));dist={(4,2):0};queue=deque(dist)
    while queue:
        x,y=queue.popleft()
        for dx,dy in shifts:
            n=x+dx,y+dy
            if n in cells and n not in dist:dist[n]=dist[(x,y)]+1;queue.append(n)
    domain=[(x,y,t,k,phi,z,m) for t in range(12) for k in range(2) for phi in range(6) for x,y in sorted(cells-{(4,2)}) for z in range(4) for m in range(2)]
    require([tuple(o['context']) for o in D]==domain and len(X)==len(R)==5904,'complete support')
    for o in D:
        n=tuple(o['context']);x,y,t,k,phi,z,m=n;legal=[]
        for a,(dx,dy) in enumerate(shifts):
            s=(x+dx,y+dy)
            if s not in cells or z==0 and dist[s]!=dist[(x,y)]-1 or z in (1,3) and m==0 and s==(4,2) or z==2 and m==0 and s in ((2,2),(4,2)):continue
            legal.append(a)
        require(legal==list(q[n]),'all legal sets');b=max(q[n].values());require(o['alternatives']==[a for a in legal if q[n][a]<b-1e-12],'all D alternatives retained')
    graph={}
    for t,o in old['graph']:
        if t=='NATIVE_LEGAL_EDGE':
            n=tuple(o['pre']);require(o['result']==step(n,o['command']),'independent full step semantics');graph.setdefault(n,{})[o['command']]=o['result']
    reachable={(0,2,0,k,phi,z,0) for k in range(2) for phi in range(6) for z in range(4)};queue=deque(reachable)
    while queue:
        n=queue.popleft();require(set(graph[n])==set(q[n]),'all branch closure')
        for e in graph[n].values():
            p=tuple(e['post'])
            if not e['terminal'] and p not in reachable:reachable.add(p);queue.append(p)
    require(len(graph)==len(reachable)==6254 and sum(map(len,graph.values()))==20588,'graph extent')
    bs=next(o['entries'] for t,o in old['basis'] if t=='NATIVE_BASIS');consult=defaultdict(list)
    for i,b in enumerate(bs):
        n=(0,2,0,b['kappa'],b['phase'],b['committed'],0);raw=[]
        while True:
            a=nom[n];e=step(n,a);consult[sites[n]].append(i);raw.append([list(n[:5]),n[5],n[6],a,a,a,e['reward_hex'],e['post'][:5],e['post'][5:],e['terminal'],e['outcome'],False])
            if e['terminal']:break
            n=tuple(e['post'])
        require(raw==b['payload']['trace'] and sum(float.fromhex(v[6]) for v in raw).hex()==b['payload']['return_hex'],'all 278 old basis raw rows')
    audits=[];targets=[{},{}];siteorder=[]
    for t,xy,k,phi in product(range(12),sorted(cells-{(4,2)}),range(2),range(6)):
        x,y=xy;rows=[q[(x,y,t,k,phi,z,m)] for z in range(4) for m in range(2)]
        for cmd in sorted(set().union(*(set(row) for row in rows))):siteorder.append((x,y,t,k,phi,cmd))
    require([tuple(x['site']) for x in X]==siteorder,'all union legal site order')
    for x,revision in zip(X,R):
        s=tuple(x['site']);require(s==tuple(revision['site']),'revised original order')
        allsets=[set(q[s[:5]+(z,m)]) for z,m in product(range(4),range(2))]
        domainservice=[[z,m] for z,m in product(range(4),range(2)) if s[5] in q[s[:5]+(z,m)]]
        reachservice=[[z,m] for z,m in domainservice if s[:5]+(z,m) in graph]
        oldtargets=sorted(set.intersection(*allsets)-{s[5]});newtargets=sorted(set.intersection(*(set(q[s[:5]+tuple(v)]) for v in domainservice))-{s[5]})
        require(x['alternatives']==oldtargets and x['all8_common_legal']==sorted(set.intersection(*allsets)),'old exact grammar')
        require(revision['targets']==newtargets and revision['domain_service']==domainservice and revision['reachable_service']==reachservice,'full-domain command grammar')
        if oldtargets:targets[0][s]=oldtargets
        if newtargets:targets[1][s]=newtargets
        audits.append({'site':list(s),'old_targets':oldtargets,'revised_targets':newtargets,'domain_service':domainservice,'reachable_service':reachservice,'old_basis_consultations':consult.get(s,[])})


    require((len(targets[0]),sum(map(len,targets[0].values())),len(targets[1]),sum(map(len,targets[1].values())))==(3312,3600,4464,8928),'all target multiplicities')
    normalizers=next(o for t,o in r if t=='OLD_COMPLETE_NORMALIZERS_READ_ONLY')
    require(normalizers=={'cells':[o for t,o in old['joint'] if t=='COMPLETE_EXACT_CELL_NORMALIZER'],
        'not_recomputed':True,'scientific_grammar_adopted':False},'complete old zero/positive masses preserved')
    emitted_scopes=[o for t,o in r if t=='BASIS_SCOPE'];scopes=[];worlds=[];world_index={};predicted=[]
    alt={tuple(v['site']):v['targets'] for v in R};oldalt={tuple(v['site']):v['alternatives'] for v in X}
    nodes=0;terminal_counts=Counter()
    # Independent iterative forward query-prefix enumeration, not candidate recursion.
    for i,b in enumerate(bs):
        root=(0,2,0,b['kappa'],b['phase'],b['committed'],0);local=Counter();startnodes=nodes
        stack=[('node',root,())]
        while stack:
            kind,n,selected=stack.pop()
            if kind=='node':
                nodes+=1;require(nodes<=c['structural_guard']['max_query_tree_nodes'],'full source tree guard')
                cmd=nom[n];addr=sites[n];choices=[cmd]+(alt[addr] if len(selected)<8 else [])
                for a in reversed(choices):
                    declarations=selected+((addr,a),) if a!=cmd else selected;e=step(n,a)
                    stack.append(('terminal' if e['terminal'] else 'node',tuple(e['post']),declarations))
                continue
            local[len(selected)]+=1;terminal_counts[len(selected)]+=1
            if len(selected)!=8:continue
            full=selected
            if full not in world_index:
                wid=len(worlds);world_index[full]=wid;masses={}
                for name,M,ts in [('domain_command',4464,alt),('old_all8',3312,oldalt)]:
                    mass=F(1,comb(M,8))
                    for addr,a in full:
                        if a not in ts[addr]:mass=None;break
                        mass/=len(ts[addr])
                    masses[name]=[mass.numerator,mass.denominator] if mass is not None else None
                worlds.append({'world_id':wid,'declarations':[[list(s),a] for s,a in full],
                    'unconditioned_world_mass':masses,'not_panel_uniform_or_basis_mass':True})
            wid=world_index[full];p=rollout(root,q,store(worlds[wid]['declarations']));tr,owners=original_truth(p,q)
            require(owners==[list(s) for s,a in selected],'all actual eight')
            app=p['outcome']!='SUCCESS'
            predicted.append({'id':len(predicted),'world_id':wid,'basis_index':i,'basis':list(root[3:6]),
                'declarations':worlds[wid]['declarations'],'actual_declarations':[[list(s),a] for s,a in selected],
                'pre':p,
                'all_manifested_owners':owners,'full_Oracle_units':tr['Gamma_P_star'],
                'reflection_applicable':app,'post':rollout(root,q,store([])) if app else None})
        scopes.append({'basis_index':i,'basis':list(root[3:6]),'query_tree_nodes':nodes-startnodes,
            'complete_terminal_counts_by_actual_queries':dict(local),'all_outcomes_retained':True,
            'empty_eight_actual_scope':not local[8],'no_native_lower_k_rerun':True})
    require(json.loads(canonical(scopes))==emitted_scopes,'all48 full forward query scopes')
    require(worlds==[o for t,o in r if t=='FULL_PRE_WORLD'],'complete literal8-world identities/measures')
    require(predicted==[o for t,o in r if t=='PREDICTION_BEFORE_ANY_NATIVE'],'all forward query-prefix pre/post predictions')
    require(len(set((p['world_id'],p['basis_index']) for p in predicted))==len(predicted),'no repeated world/basis')
    barrier={'basis_scopes':len(scopes),'empty_eight_actual_scopes':sum(s['empty_eight_actual_scope'] for s in scopes),
        'query_tree_nodes':nodes,'complete_terminal_counts_by_actual_queries':dict(terminal_counts),
        'selected_actual_queries':8,'installed_k':8,'untouched_sentinels':0,
        'unique_full_pre_worlds':len(worlds),'basis_world_records':len(predicted),
        'scope_sha256':sha256(canonical(scopes)).hexdigest(),'world_sha256':sha256(canonical(worlds)).hexdigest(),
        'prediction_sha256':sha256(canonical(predicted)).hexdigest(),'no_outcome_selected_targets':True,
        'full_scientific_k8_support_tested':False,'eight_actual_coverage':True}
    barrier=json.loads(canonical(barrier))
    pos=next(i for i,(t,o) in enumerate(r) if t=='COMPLETE_PANEL_BEFORE_NATIVE')
    require(r[pos][1]==barrier and all(t not in ['RAW_FACTUAL_BEFORE_TRUTH','FULL_ORIGINAL_TRUTH_BEFORE_B1','ACTUAL_COMPLETE_RECORD'] for t,o in r[:pos]),'barrier before all native')
    del r
    actual_count=0;actual_digest=sha256(b'[');counts=Counter();changes=Counter();rawrows=0;initial_deltas=[];treatment_deltas=[];shared=Counter()
    for i,rec in enumerate(predicted):
        root=(0,2,0,*rec['basis'],0);pre=store(rec['declarations']);p=rollout(root,q,pre);tr,owners=original_truth(p,q);f=fp(pre)
        raw,truthrow,a=[take(t)[1] for t in ['RAW_FACTUAL_BEFORE_TRUTH','FULL_ORIGINAL_TRUTH_BEFORE_B1','ACTUAL_COMPLETE_RECORD']]
        require(raw=={'id':i,'payload':p,'full_pre_store':pre,'fingerprint_pre':f},'all initial raw/full fingerprint')
        require(truthrow=={'id':i,'truth':tr,'units':tr['Gamma_P_star'],'owners':owners},'all original A75 truth/rho')
        expected={'id':i,'world_id':rec['world_id'],'basis_index':rec['basis_index'],'full_pre_store':pre,'fingerprint_pre':f,
            'source_fingerprint_after':f,'payload':p,'truth':tr,'all_resolved_owners':owners,'full_units':tr['Gamma_P_star'],
            'reflection_applicable':rec['reflection_applicable'],'same_tier_arms':a['same_tier_arms']}
        require(a==expected,'complete actual source/store/truth')
        initial_deltas.append(float.fromhex(p['return_hex'])-float.fromhex(bs[rec['basis_index']]['payload']['return_hex']))
        shared[rec['world_id']]+=1;counts['factual_rollouts']+=1;counts['pre_'+p['outcome']]+=1;rawrows+=len(p['trace'])
        if rec['reflection_applicable']:
            require(len(a['same_tier_arms'])==2,'full same-tier pair');counts['failing_records']+=1;counts['actual_owners_'+str(len(owners))]+=1
            for role,arm in zip(['reference','treatment'],a['same_tier_arms']):
                post=pre if role=='reference' else store([[addr,v] for addr,v in pre['X'] if addr not in owners]);pp=rollout(root,q,post)
                require(role=='reference' or post==store([]),'all eight actual declarations canonical identity deletion')
                tx=[] if role=='reference' else [{'on_this_clone':True,'fingerprint_pre':f,'entry_edits':len(owners),
                    'stores':['controller']*len(owners),'addresses':owners,'values':[addr[5] for addr in owners]}]
                require(arm=={'role':role,'law':'NoWrite' if role=='reference' else 'X_id','tier':'L0_FACTUAL','transactions':tx,
                    'ledger':expected_ledger(pre,post,owners,role),'full_post_store':post,'payload':pp},'all full original transaction/receipt/store/canonical/post')
                counts['B1_arms']+=1;counts['post_rollouts']+=1;rawrows+=len(pp['trace'])
                if role=='treatment':
                    counts['treatment_transactions']+=1;counts['post_'+pp['outcome']]+=1
                    d=float.fromhex(pp['return_hex'])-float.fromhex(p['return_hex']);treatment_deltas.append(d)
                    changes['positive' if d>0 else 'negative' if d<0 else 'zero']+=1
        else:
            require(not a['same_tier_arms'],'success reflection must be inapplicable not zero effect');counts['reflection_inapplicable_'+p['outcome']]+=1
        if actual_count:actual_digest.update(b',')
        actual_digest.update(canonical(a).rstrip(b'\n'));actual_count+=1
    actual_digest.update(b']\n')
    after=take('INPUT_BINDING_AFTER')[1];require(after==before,'full beforeafter inputs')
    final=take('FINAL')[1];require(all(final[k]==v for k,v in barrier.items()),'final full panel')
    require(next(stream,None) is None,'full EOF no extra records')
    require(final['counts']==dict(counts) and final['signed_immediate_changes']==dict(changes) and final['native_raw_rows']==rawrows,'all actual counters')
    require(final['actual_records']==actual_count and final['actual_sha256']==actual_digest.hexdigest() and final['actual_registry_hash_streamed_without_payload_omission'] is True,'full ordered actual registry')
    require(tag==Counter({'INPUT_BINDING_BEFORE':1,'OLD_COMPLETE_NORMALIZERS_READ_ONLY':1,'BASIS_SCOPE':48,
        'FULL_PRE_WORLD':len(worlds),'PREDICTION_BEFORE_ANY_NATIVE':len(predicted),
        'COMPLETE_PANEL_BEFORE_NATIVE':1,'RAW_FACTUAL_BEFORE_TRUTH':actual_count,'FULL_ORIGINAL_TRUTH_BEFORE_B1':actual_count,
        'ACTUAL_COMPLETE_RECORD':actual_count,'INPUT_BINDING_AFTER':1,'FINAL':1}),'complete native output language')
    require(all(final[k]==0 for k in ['new_reference_DP','keys_allocated','random_draws','future_training']) and
        all(final[k] is False for k in ['collector_executed','scientific_rules_adopted','scientific_PASS','collection_authorized','mechanism_direction_falsified','research_complete']),'execution authority')
    for node in ast.walk(ast.parse((HERE/'check_stored.py').read_bytes())):
        if isinstance(node,ast.Import):require(all(a.name.split('.')[0] not in ['rfl_rebuild','candidate','check_stored'] for a in node.names),'checker imports')
        if isinstance(node,ast.ImportFrom):require(not node.module or node.module.split('.')[0] not in ['rfl_rebuild','candidate','check_stored'],'checker import from')
    emitcheck={'status':'FULL_NATIVE_EIGHT_ACTUAL_X_STORED_CHECK_NOT_SCIENCE','implementation_independence':'PRIMARY_ONLY_NOT_EXPERT',
        'full_D':13824,'full_X':5904,'old_graph_edges':20588,'old_basis_rows':278,'runtime_inputs':1020,'parent_HEAD_bindings':863,
        **barrier,'counts':dict(counts),'signed_changes':dict(changes),'native_raw_rows':rawrows,
        'initial_signed_min':min(initial_deltas,default=None),'initial_signed_max':max(initial_deltas,default=None),
        'treatment_signed_min':min(treatment_deltas,default=None),'treatment_signed_max':max(treatment_deltas,default=None),
        'world_basis_multiplicities':dict(Counter(shared.values())),'no_RFL_candidate_old_checker_solver_execution':True,'full_capture_streamed_without_payload_omission':True,
        'scientific_PASS':False,'collection_authorized':False,'research_complete':False}
    print('CHECK='+canonical(emitcheck).decode().rstrip('\n'))
if __name__=='__main__':main()
