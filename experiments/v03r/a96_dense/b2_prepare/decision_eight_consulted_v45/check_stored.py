"""Stdlib independent full stored native semantics, transaction and support check."""
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

def main():
    c=read(HERE/'contract.json');stream=iter(streamed_capture(HERE/'evidence'));tags=Counter()
    def take(expected=None):
        t,o=next(stream);tags[t]+=1
        if expected:require(t==expected,'full stream language '+expected)
        return t,o
    r=[]
    while True:
        pair=take();r.append(pair)
        if pair[0]=='COMPLETE_PANEL_BEFORE_NATIVE':break
        require(pair[0] not in ['RAW_FACTUAL_BEFORE_TRUTH','FULL_ORIGINAL_TRUTH_BEFORE_B1','ACTUAL_COMPLETE_RECORD'],'full predictions before anynative')
    before=r[0][1];require(r[0][0]=='INPUT_BINDING_BEFORE','binding first')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'HEAD')
    tree={v.split(b'\t')[1].decode():v.split()[2].decode() for v in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if v}
    source=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit'];native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')};bound=set(source)|prior|{'experiments/rebuild_status_current.json'}
    extent=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require((len(source),len(native),len(prior),len(bound),len(extent))==(313,153,564,878,1035),'extent')
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
    normalizers={'cells':[o for t,o in old['normalizers'] if t=='COMPLETE_CELL_NORMALIZER'],'not_recomputed':True,'scientific_measure_adopted':False}
    require(len(normalizers['cells'])==7 and next(o for t,o in r if t=='OLD_COMPLETE_NORMALIZERS_READ_ONLY')==normalizers,'old exact D masses retained not rerun')
    groups=Counter(n[3:] for n,v in alt.items() if v);clustered=sum(math.comb(n,8) for n in groups.values())
    M={'clustered':clustered,'distributed':math.comb(7551,8)-clustered}
    panel=[];scopes=[];worldids=set();nodes=0;terminal_counts=Counter()
    for i,b in enumerate(bs):
        root=(0,2,0,b['kappa'],b['phase'],b['committed'],0);nom=rollout(root,q,empty)
        packed=[[v['pre_state'],v['z'],v['m'],v['a_cmd'],v['u'],v['a_realized'],v['reward_hex'],v['post_state'],v['post_control'],v['terminal'],v['outcome'],v['illegal']] for v in nom['trace']]
        require(packed==b['payload']['trace'] and nom['return_hex']==b['payload']['return_hex'],'old48 basis full278raw')
        startnodes=nodes;local=Counter();stack=[('node',root,())]
        # Independently forward explicitstack, no candidate recursive/predictor execution.
        while stack:
            kind,n,decl=stack.pop()
            if kind=='node':
                nodes+=1;require(nodes<=c['guard']['max_query_tree_nodes'],'complete source tree guard')
                cmd=sorted(q[n],key=lambda a:(-q[n][a],a))[0];choices=[cmd]+(alt[n] if len(decl)<8 else [])
                for a in reversed(choices):
                    selected=decl+((n,a),) if a!=cmd else decl;e=step(n,a)
                    stack.append(('terminal' if e['terminal'] else 'node',tuple(e['post']),selected))
                continue
            local[len(decl)]+=1;terminal_counts[len(decl)]+=1
            if len(decl)!=8:continue
            require(decl not in worldids,'fullpre identity unique no behaviorcollapse');worldids.add(decl)
            declarations=[[list(n),a] for n,a in decl];pre=rollout(root,q,expected_store(declarations,'D_patch',q));tr,owners=truth(pre,q)
            require(owners==[list(n) for n,a in decl],'all8 original actualmanifestations')
            app=pre['outcome']!='SUCCESS';posts={};targets=[]
            for arch in ('D_Q','D_patch'):
                st=expected_store(declarations,arch,q);require(rollout(root,q,st)==pre,'independent extensional installation')
                if app:
                    post,values=post_store(st,pre,owners,arch,q);posts[arch]=rollout(root,q,post);targets=values
            shape='clustered' if len({a[3:] for a,t in decl})==1 else 'distributed';mult=[len(alt[a]) for a,t in decl]
            mass=Fraction(1,M[shape])
            for m in mult:mass/=m
            panel.append({'id':len(panel),'basis_index':i,'basis':list(root[3:6]),'declarations':declarations,'shape':shape,
                'original_target_multiplicities':mult,'original_cell_context_subsets':M[shape],
                'original_unconditioned_candidate_mass':[mass.numerator,mass.denominator],
                'pre':pre,'all_manifested_owners':owners,'full_Oracle_units':tr['Gamma_P_star'],
                'reflection_applicable':app,'factual_suffix_targets':targets,'posts':posts})
        scopes.append({'basis_index':i,'basis':list(root[3:6]),'query_tree_nodes':nodes-startnodes,
            'complete_terminal_counts_by_actual_queries':dict(local),'empty_eight_actual_scope':not local[8],
            'all_outcomes_retained':True,'no_native_lower_k_rerun':True})
    require(json.loads(canonical(scopes))==[o for t,o in r if t=='BASIS_SCOPE'],'all48 complete scopes')
    require(panel==[o for t,o in r if t=='PREDICTION_BEFORE_ANY_NATIVE'],'all complete8world measures/pre/post predictions')
    require((nodes,len(panel))==(2468096,15927),'complete structural cardinality')
    barrier={'basis_scopes':48,'empty_eight_actual_scopes':sum(s['empty_eight_actual_scope'] for s in scopes),
        'query_tree_nodes':nodes,'complete_terminal_counts_by_actual_queries':dict(terminal_counts),
        'configurations':len(panel),'unique_full_pre_worlds':len(worldids),'installed_k':8,'actual_owners':8,'sentinels_added':0,
        'scope_sha256':sha256(canonical(scopes)).hexdigest(),'prediction_sha256':sha256(canonical(panel)).hexdigest(),
        'full_scientific_k8_support_tested':False,'scientific_measure_adopted':False,'no_result_selected_cases':True}
    barrier=json.loads(canonical(barrier));require(r[-1][1]==barrier,'full barrier before anynative')
    del r
    counts=Counter();changes=Counter();unconsulted=Counter();rawrows=0;delta_values=[];initial_deltas=[];post_sizes=Counter();shapes=Counter(v['shape'] for v in panel)
    actual_count=0;actual_digest=sha256(b'[')
    for j in range(2*len(panel)):
        raw,truthrow,a=[take(t)[1] for t in ['RAW_FACTUAL_BEFORE_TRUTH','FULL_ORIGINAL_TRUTH_BEFORE_B1','ACTUAL_COMPLETE_RECORD']]
        rec=panel[j//2];arch=('D_Q','D_patch')[j%2];root=(0,2,0,*rec['basis'],0);pre=expected_store(rec['declarations'],arch,q);fp=fingerprint(pre);p=rec['pre'];tr,owners=truth(p,q)
        require(a['id']==rec['id'] and a['architecture']==arch and normal(a['full_pre_store'])==normal(pre),'full pre declarations')
        require(a['fingerprint_pre']==a['source_fingerprint_after']==fp and a['payload']==p and a['truth']==tr and a['all_resolved_owners']==owners and a['full_units']==tr['Gamma_P_star'],'full truth/raw/store fingerprint')
        require(raw=={'id':rec['id'],'architecture':arch,'payload':p,'full_pre_store':a['full_pre_store'],'fingerprint_pre':fp},'raw before truth complete')
        require(truthrow=={'id':rec['id'],'architecture':arch,'truth':tr,'units':tr['Gamma_P_star'],'owners':owners},'truth before transaction')
        initial_deltas.append(float.fromhex(p['return_hex'])-float.fromhex(bs[rec['basis_index']]['payload']['return_hex']))
        if actual_count:actual_digest.update(b',')
        actual_digest.update(canonical(a).rstrip(b'\n'));actual_count+=1
        counts['factual_rollouts']+=1;rawrows+=len(p['trace']);counts[arch+':pre:'+p['outcome']]+=1;unconsulted[arch+':'+str(8-len(owners))]+=1
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
                post_sizes[arch+':'+str(len(post['Q']) if arch=='D_Q' else len(post['D']))]+=1
                counts['treatment_transactions']+=1;counts[arch+':post:'+pp['outcome']]+=1
                delta=float.fromhex(pp['return_hex'])-float.fromhex(p['return_hex']);delta_values.append(delta)
                changes[arch+':'+('positive' if delta>0 else 'negative' if delta<0 else 'zero')]+=1

    actual_digest.update(b']\n')
    after=take('INPUT_BINDING_AFTER')[1];require(after==before,'complete beforeafter inputs')
    final=take('FINAL')[1];require(next(stream,None) is None,'strict full EOF')
    require(final['counts']==dict(counts) and final['signed_immediate_changes']==dict(changes) and final['native_raw_rows']==rawrows,'full native counters')
    require(final['actual_records']==actual_count and final['actual_sha256']==actual_digest.hexdigest(),'full canonical actual array digest')
    require(all(final[k]==v for k,v in barrier.items()),'final barrier')
    require(all(final[k]==0 for k in ['future_training','keys_allocated','new_reference_DP','random_draws']) and all(final[k] is False for k in ['collector_executed','scientific_rules_adopted','collection_authorized','scientific_PASS','research_complete','mechanism_direction_falsified']),'authority')
    require(tags==Counter({'INPUT_BINDING_BEFORE':1,'OLD_COMPLETE_NORMALIZERS_READ_ONLY':1,'BASIS_SCOPE':48,
        'PREDICTION_BEFORE_ANY_NATIVE':len(panel),'COMPLETE_PANEL_BEFORE_NATIVE':1,
        'RAW_FACTUAL_BEFORE_TRUTH':actual_count,'FULL_ORIGINAL_TRUTH_BEFORE_B1':actual_count,'ACTUAL_COMPLETE_RECORD':actual_count,
        'INPUT_BINDING_AFTER':1,'FINAL':1}),'complete language')
    for node in ast.walk(ast.parse((HERE/'check_stored.py').read_bytes())):
        if isinstance(node,ast.Import):require(all(a.name.split('.')[0] not in ['rfl_rebuild','candidate','check_stored'] for a in node.names),'checker imports')
        if isinstance(node,ast.ImportFrom):require(not node.module or node.module.split('.')[0] not in ['rfl_rebuild','candidate','check_stored'],'checker imports')
    print('CHECK='+canonical({'status':'FULL_EIGHT_ACTUAL_D_STORED_CHECK_NOT_SCIENCE','implementation_independence':'PRIMARY_ONLY_NOT_EXPERT',
        **barrier,'runtime_inputs':1035,'parent_HEAD_bindings':878,'sources':313,'old_native':153,'prior_preparation':564,
        'complete_original_D':13824,'complete_old_X_retained':5904,'old_native_graph_edges':20588,'old_basis_rows':278,
        'actual_records':actual_count,'counts':dict(counts),'signed_changes':dict(changes),'native_raw_rows':rawrows,
        'initial_signed_min':min(initial_deltas,default=None),'initial_signed_max':max(initial_deltas,default=None),
        'min_treatment_delta':min(delta_values,default=None),'max_treatment_delta':max(delta_values,default=None),
        'finite_treatment_post_store_sizes':dict(post_sizes),'original_shape_membership':dict(shapes),
        'no_RFL_candidate_old_checker_solver_execution':True,'full_capture_streamed_without_omission':True,
        'scientific_PASS':False,'collection_authorized':False,'research_complete':False}).decode().rstrip('\n'))
if __name__=='__main__':main()
