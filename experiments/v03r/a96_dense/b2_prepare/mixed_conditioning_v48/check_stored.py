"""Independent source-first mixed event cut audit, no RFL/old fixture execution."""
from collections import Counter, deque
from fractions import Fraction
from hashlib import sha1, sha256
from pathlib import Path
from itertools import product
import ast,json,subprocess
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]
def read(p):return json.loads(p.read_bytes())

def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()

def emit(t,o):print(t+'='+canonical(o).decode().rstrip('\n'),flush=True)

def require(ok,why):
    if not ok:raise AssertionError(why)

def digest(p,blob=False):
    h=sha1(b'blob '+str(p.stat().st_size).encode()+b'\0') if blob else sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()

def bind(c):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'parentHEAD')
    tree={v.split(b'\t')[1].decode():v.split()[2].decode() for v in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if v}
    source=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources'];a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes'];prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(source)|prior|{'experiments/rebuild_status_current.json'}
    require((len(source),len(native),len(prior),len(bound))==(313,153,622,936),'parent extent')
    for p in bound:require(digest(ROOT/p,True)==tree[p],'HEAD byte '+p)
    for p,h in (source|native).items():require(digest(ROOT/p)==h,'frozen/native '+p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==1093,'runtime extent')
    return {'HEAD':head,'HEAD_bindings':936,'runtime_inputs':1093,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}

def capture(info):
    folder=PREP/info[0];cl=read(folder/'claim.json');ex=read(folder/'exit.json')
    require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items()),'stored claim/exit')
    require(ex['files']['stdout.log']['sha256']==info[1] and (folder/'stderr.log').stat().st_size==0,'stored identity')
    for n,v in ex['files'].items():require({'bytes':(folder/n).stat().st_size,'sha256':digest(folder/n)}==v,'full stored bytes')
    for n,h in ex['inputs'].items():require(digest(folder.parent/n)==h,'executed source immutable')
    with (folder/'stdout.log').open('rb') as f:
        for l in f:
            require(l.endswith(b'\n'),'completeEOF line')
            if b'=' not in l:continue
            t,v=l.rstrip(b'\r\n').split(b'=',1)
            if v[:1] not in (b'{',b'['):continue
            o=json.loads(v)
            if info[0].startswith('mixed_projection'):require(canonical(o).rstrip(b'\n')==v,'full mixed canonical')
            yield t.decode(),o

def rat(v):return [v.numerator,v.denominator]

def step(n,a):
    x,y,t,k,phi,z,m=n;dx,dy=((0,-1),(0,1),(-1,0),(1,0),(0,0))[a];nx,ny=x+dx,y+dy;nt=t+1
    outcome='COLLISION' if (nx,ny)==(2,2) and nt%(6,3)[k]==phi%(6,3)[k] else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
    nm=int(bool(m or z==1 and (nx,ny)==(2,1) or z==3 and (nx,ny)==(2,4) or z==2 and (x,y)==(1,2) and t%(6,3)[k]!=phi%(6,3)[k]))
    return {'post':[nx,ny,nt,k,phi,z,nm],'a_cmd':a,'u':a,'a_realized':a,
            'reward_hex':(-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)).hex(),
            'terminal':outcome is not None,'outcome':outcome,'illegal':False}

def main():
    c=read(HERE/'contract.json');binding=bind(c)
    stored={k:list(capture(v)) for k,v in c['stored'].items()}
    D=[o for t,o in stored['catalog'] if t=='DECISION_CONTEXT'];X=[o for t,o in stored['catalog'] if t=='CONTROLLER_SITE']
    R=[o for t,o in stored['revision'] if t=='REVISED_SITE_NOT_ADOPTED'];q={tuple(o['context']):{a:float.fromhex(h) for a,h in o['q_row_hex']} for o in D}
    cells={(0,2),(4,2)}|{(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)}
    shifts=((0,-1),(0,1),(-1,0),(1,0),(0,0));dist={(4,2):0};queue=deque(dist)
    while queue:
        x,y=queue.popleft()
        for dx,dy in shifts:
            s=(x+dx,y+dy)
            if s in cells and s not in dist:dist[s]=dist[x,y]+1;queue.append(s)
    domain=[(x,y,t,k,p,z,m) for t in range(12) for k in range(2) for p in range(6) for x,y in sorted(cells-{(4,2)}) for z in range(4) for m in range(2)]
    require([tuple(o['context']) for o in D]==domain,'full D enumeration');da={}
    for o in D:
        n=tuple(o['context']);x,y,t,k,p,z,m=n;legal=[]
        for a,(dx,dy) in enumerate(shifts):
            s=(x+dx,y+dy)
            if s not in cells or z==0 and dist[s]!=dist[x,y]-1 or z in (1,3) and m==0 and s==(4,2) or z==2 and m==0 and s in ((2,2),(4,2)):continue
            legal.append(a)
        require(legal==list(q[n]),'complete legal rows');da[n]=[a for a in legal if q[n][a]<max(q[n].values())-1e-12]
        require(da[n]==o['alternatives'],'all nonoptimal targets')
    xa={};oa={};xdomain=[]
    for t in range(12):
        for x,y in sorted(cells-{(4,2)}):
            for k in range(2):
                for p in range(6):
                    rows=[set(q[x,y,t,k,p,z,m]) for z in range(4) for m in range(2)]
                    for cmd in sorted(set.union(*rows)):
                        s=(x,y,t,k,p,cmd);xdomain.append(s);xa[s]=sorted(set.intersection(*(v for v in rows if cmd in v))-{cmd});oa[s]=sorted(set.intersection(*rows)-{cmd})
    require([tuple(o['site']) for o in X]==xdomain==[tuple(o['site']) for o in R],'complete X domains')
    require(all(o['alternatives']==oa[tuple(o['site'])] for o in X) and all(o['targets']==xa[tuple(o['site'])] for o in R),'both full grammars')
    require((sum(bool(v) for v in da.values()),sum(map(len,da.values())),sum(bool(v) for v in xa.values()),sum(map(len,xa.values())),sum(bool(v) for v in oa.values()),sum(map(len,oa.values())))==(7551,16364,4464,8928,3312,3600),'all support preserved')
    graph={}
    for t,o in stored['graph']:
        if t=='NATIVE_LEGAL_EDGE':
            n=tuple(o['pre']);require(o['result']==step(n,o['command']),'complete source/native step binding');graph.setdefault(n,{})[o['command']]=o['result']
    roots=[(0,2,0,k,p,z,0) for k in range(2) for p in range(6) for z in range(4)];reachable=set(roots);queue=deque(roots)
    while queue:
        n=queue.popleft();require(set(graph[n])==set(q[n]),'all legal branch closure')
        for e in graph[n].values():
            post=tuple(e['post']);require(post[2]>n[2] and post[3:6]==n[3:6],'strict time and root invariant')
            if not e['terminal'] and post not in reachable:reachable.add(post);queue.append(post)
    require(len(reachable)==len(graph)==6254 and sum(map(len,graph.values()))==20588,'complete graph extent')
    bs=next(o['entries'] for t,o in stored['basis'] if t=='NATIVE_BASIS');require(len(bs)==48,'all48 basis')
    panel=[o for t,o in stored['mixed'] if t=='PREDICTION_BEFORE_ANY_NATIVE'];barrier=next(o for t,o in stored['mixed'] if t=='COMPLETE_PANEL_BEFORE_NATIVE')
    require(sha256(canonical(panel)).hexdigest()==barrier['prediction_sha256'],'stored full prediction array')
    endings=[];nodes=0;scopes=[]
    for i,root in enumerate(roots):
        require(root[3:6]==(bs[i]['kappa'],bs[i]['phase'],bs[i]['committed']),'basis ordering')
        local=Counter();startnodes=nodes;stack=[(root,None,None,[],False)]
        while stack:
            n,d,x,path,finished=stack.pop()
            if finished:
                rec=panel[len(endings)];degree=f'{int(d is not None)},{int(x is not None)}';local[degree]+=1
                pre={'trace':path,'outcome':path[-1]['outcome'],'return_hex':sum(float.fromhex(r['reward_hex']) for r in path).hex()}
                require(rec['id']==len(endings) and rec['basis_index']==i and rec['actual_degree']==degree and rec['pre']==pre,'every complete history source reconstruction')
                for literal,sl in ((d,'D'),(x,'X')):
                    if literal:require(rec[sl+'_declaration']==[list(literal[0]),literal[1]] and rec['owners'][sl]==[list(literal[0])],'complete manifested literal')
                    else:require(not rec['owners'][sl] and sl in rec['fixed_unread_channels'],'absent actual channel retained')
                if degree=='0,0':
                    packed=[[r['pre_state'],r['z'],r['m'],r['a_cmd'],r['u'],r['a_realized'],r['reward_hex'],r['post_state'],r['post_control'],r['terminal'],r['outcome'],r['illegal']] for r in path]
                    require(packed==bs[i]['payload']['trace'] and pre['return_hex']==bs[i]['payload']['return_hex'],'all old278 basis rows')
                endings.append((d,x,path,rec));continue
            nodes+=1;require(nodes<=c['guard']['max_structural_query_nodes'],'prospective structural guard')
            greedy=sorted(q[n],key=lambda a:(-q[n][a],a))[0];branches=[]
            for cmd in [greedy]+(da[n] if d is None else []):
                dd=(n,cmd) if cmd!=greedy else d;s=n[:5]+(cmd,)
                for u in [cmd]+(xa[s] if x is None else []):
                    xx=(s,u) if u!=cmd else x;e=step(n,u)
                    r={'pre_state':list(n[:5]),'z':n[5],'m':n[6],'a_cmd':cmd,'u':u,'a_realized':u,'reward_hex':e['reward_hex'],
                       'post_state':e['post'][:5],'post_control':e['post'][5:],'terminal':e['terminal'],'outcome':e['outcome'],'illegal':False}
                    branches.append((tuple(e['post']),dd,xx,path+[r],e['terminal']))
            stack.extend(reversed(branches))
        scopes.append({'basis_index':i,'basis':list(root[3:6]),'query_tree_nodes':nodes-startnodes,'complete_terminal_counts_by_actual_degree':dict(local),'empty_mixed_actual_scope':not local['1,1']})
    require(scopes==[o for t,o in stored['mixed'] if t=='BASIS_SCOPE'] and len(endings)==5791 and nodes==23764,'all query scopes')
    require(all(path[-1]['outcome']=='SUCCESS' for d,x,path,rec in endings if d is None and x is not None),'complete firsthit pureX singleton no failing manifestations')
    only=[v for v in endings if v[0] is not None and v[1] is None and v[2][-1]['outcome']!='SUCCESS']
    both=[v for v in endings if v[0] is not None and v[1] is not None and v[2][-1]['outcome']!='SUCCESS']
    require(len(only)==26 and len({d for d,x,path,rec in only})==26 and len(both)==143 and len({(d,x) for d,x,path,rec in both})==143,'true literal union not basis weighting')
    require(all(d[0][3:6]==tuple(rec['basis']) for d,x,path,rec in only+both),'D one root fixes kappa phase z')
    output=list(capture(['mixed_conditioning_v48/evidence',read(HERE/'evidence/exit.json')['files']['stdout.log']['sha256']]))
    for t,o in output:require(t in {'INPUT_BINDING_BEFORE','COMPLETE_ELIGIBLE_X_SITE','COMPLETE_UNREAD_X_FAILURE_CYLINDER','BOTH_ACTUAL_FAILURE_FULL_WORLD','COMPLETE_MIXED_CELL','WEIGHTED_CUT_TOY','INPUT_BINDING_AFTER','FINAL'},'full new capture language')
    require(output[0]==('INPUT_BINDING_BEFORE',binding) and [o for t,o in output if t=='INPUT_BINDING_AFTER']==[binding],'complete runtime before after')
    summaries=[];cutsall=[];site_expected=[]
    for name,grammar in [('old_all8',oa),('domain_command_not_adopted',xa)]:
        M=sum(bool(v) for v in grammar.values());N=sum(map(len,grammar.values()));cuts=[];single=[]
        site_expected += [{'grammar':name,'site':list(s),'targets':v} for s,v in grammar.items() if v]
        for d,x,path,rec in only:
            queried={tuple(r['pre_state']+[r['a_cmd']]) for r in path};visited=[s for s,v in grammar.items() if v and s in queried]
            mass=Fraction(1,7551*len(da[d[0]]))*(1-Fraction(len(visited),M))
            cut={'grammar':name,'stored_id':rec['id'],'basis':rec['basis'],'D_declaration':[list(d[0]),d[1]],
                 'excluded_consulted_eligible_X_sites':[list(s) for s in visited],'unread_X_sites':M-len(visited),
                 'complete_unread_target_assigned_worlds':N-sum(len(grammar[s]) for s in visited),'unconditioned_product_mass':rat(mass)}
            cuts.append(cut)
        for d,x,path,rec in both:
            if x[1] not in grammar[x[0]]:continue
            require(all(list(x[0]) in cut['excluded_consulted_eligible_X_sites'] for cut in cuts if cut['D_declaration']==[list(d[0]),d[1]]),'firsthit full cylinder exclusion no overlap')
            single.append({'grammar':name,'stored_id':rec['id'],'basis':rec['basis'],'D_declaration':[list(d[0]),d[1]],'X_declaration':[list(x[0]),x[1]],
                           'unconditioned_product_mass':rat(Fraction(1,7551)/M/len(da[d[0]])/len(grammar[x[0]]))})
        z=sum((Fraction(*v['unconditioned_product_mass']) for v in cuts+single),Fraction());count=sum(v['complete_unread_target_assigned_worlds'] for v in cuts)+len(single)
        summary={'grammar':name,'eligible_D_contexts':7551,'D_targets':16364,'eligible_X_sites':M,'X_targets':N,'full_site_pair_support':7551*M,'full_target_assigned_world_support':16364*N,
                 'unread_failure_cylinders':26,'both_actual_failure_worlds':len(single),'trigger_full_target_assigned_worlds':count,'nontrigger_full_target_assigned_worlds':16364*N-count,
                 'Z':rat(z),'nontrigger_mass':rat(1-z),'cut_sha256':sha256(canonical(cuts+single)).hexdigest(),'scientific_grammar_adopted':False,'not_uniform_target_world_measure':True}
        require([o for t,o in output if t=='COMPLETE_UNREAD_X_FAILURE_CYLINDER' and o['grammar']==name]==cuts,'all complete cylinder cuts')
        require([o for t,o in output if t=='BOTH_ACTUAL_FAILURE_FULL_WORLD' and o['grammar']==name]==single,'all full singleton worlds')
        summaries.append(summary);cutsall+=cuts+single
    require(site_expected==[o for t,o in output if t=='COMPLETE_ELIGIBLE_X_SITE'],'all ordered target literals retained')
    require(summaries==[o for t,o in output if t=='COMPLETE_MIXED_CELL'],'complete normalized mass/count')
    toys=[o for t,o in output if t=='WEIGHTED_CUT_TOY'];toyworlds=0;unequal=0
    for case,o in enumerate(toys):
        dr=[1+(i+case)%3 for i in range(3+case%3)];xr=[1+(2*i+case)%3 for i in range(5+case%2)]
        cylinders=[] if case==0 else [[0,0,list(range(1+case%3))],[1,0,list(range(2+case%2))]]
        single=[] if case==0 else [[0,0,0,0],[1,0,1,0],[2,0,len(xr)-1,0]]
        require(o['case']==case and o['D_target_counts']==dr and o['X_target_counts']==xr and o['cylinders']==cylinders and o['singletons']==single,'prospective all toy definitions')
        z=Fraction();count=0;total=0
        for d,x in product(range(len(dr)),range(len(xr))):
            for t,u in product(range(dr[d]),range(xr[x])):
                total+=1;hit=any(d==a and t==b and x not in visited for a,b,visited in cylinders) or [d,t,x,u] in single
                if hit:z+=Fraction(1,len(dr)*len(xr)*dr[d]*xr[x]);count+=1
        require(o['Z']==rat(z) and o['trigger_full_target_worlds']==count,'independent full target enumeration toy')
        unequal+=Fraction(count,total)!=z;toyworlds+=total
    require(len(toys)==8,'all toys')
    final=output[-1][1];require(output[-1][0]=='FINAL' and final['cells']==summaries and final['cut_sha256']==sha256(canonical(cutsall)).hexdigest() and final['toy_sha256']==sha256(canonical(toys)).hexdigest(),'full final EOF canonical')
    require(all(final[k]==0 for k in ('new_native_kernel_steps','new_learner_rollouts','B1_arms','reference_DP','learner_DP','keys_allocated','random_draws','future_training')),'no new mechanisms/keys')
    require(all(final[k] is False for k in ('sampler_or_collector_executed','scientific_grammar_or_rules_adopted','scientific_PASS','collection_authorized','research_complete','mechanism_direction_falsified')),'science closed')
    for node in ast.walk(ast.parse((HERE/'check_stored.py').read_bytes())):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            names=[a.name.split('.')[0] for a in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]]
            require(all(n in {'collections','fractions','hashlib','pathlib','itertools','ast','json','subprocess'} for n in names),'stdlib only no old imports')
    require(bind(c)==binding,'checker current inputs unchanged')
    emit('CHECK',{'status':'FULL_SUPPORT_MIXED_CONDITION_MASS_STORED_CHECK_NOT_SCIENCE','cells':summaries,'cut_sha256':final['cut_sha256'],'toy_sha256':final['toy_sha256'],
         'source_query_nodes':nodes,'full_terminal_histories':len(endings),'full_basis':48,'original_graph_edges':20588,'full_D_rows':13824,'full_X_rows':5904,
         'toy_complete_target_worlds':toyworlds,'toys_nonuniform_world_measure_counterexamples':unequal,'runtime_inputs':1093,'parent_HEAD_bindings':936,
         'pure_X_k1_zero_old_evidence_retained_not_new_normalizer_run':True,'all_inputs_equal':True,'no_RFL_candidate_or_old_checker_import_execution':True,
         'implementation_independence':'PRIMARY_ONLY_NOT_EXPERT','scientific_PASS':False,'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()

