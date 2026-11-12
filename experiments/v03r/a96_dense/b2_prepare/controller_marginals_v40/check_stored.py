"""Independent stdlib forward messages and full common-world toy oracle."""
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
def step(n,a):
    x,y,t,k,phi,z,m=n;dx,dy=((0,-1),(0,1),(-1,0),(1,0),(0,0))[a];nx,ny=x+dx,y+dy;nt=t+1
    outcome='COLLISION' if (nx,ny)==(2,2) and nt%(6,3)[k]==phi%(6,3)[k] else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
    nm=int(bool(m or z==1 and (nx,ny)==(2,1) or z==3 and (nx,ny)==(2,4) or z==2 and (x,y)==(1,2) and t%(6,3)[k]!=phi%(6,3)[k]))
    return {'post':[nx,ny,nt,k,phi,z,nm],'a_cmd':a,'u':a,'a_realized':a,
            'reward_hex':(-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)).hex(),
            'terminal':outcome is not None,'outcome':outcome,'illegal':False}
def forward(root,M,targets,nom,sites,g,horizon):
    current={(root,0,0,False):F(1)};result=[F() for _ in range(DEG+1)];states=0
    for tick in range(horizon):
        nextlayer=defaultdict(F)
        for (n,v,j,mf),w in sorted(current.items()):
            states+=1;al=targets.get(sites[n],());nv=v+int(bool(al))
            for a,selected in [(nom[n],False)]+[(a,True) for a in al]:
                nj=j+int(selected)
                if nj>DEG:continue
                flag=mf or selected;mass=w/(len(al) if selected else 1);e=g[n][a]
                if e['terminal']:
                    if e['outcome']!='SUCCESS' and flag:
                        for k in range(nj,DEG+1):result[k]+=mass*choose(M-nv,k-nj)
                else:nextlayer[(tuple(e['post']),nv,nj,flag)]+=mass
        current=dict(nextlayer)
    require(not current,'incomplete topological sweep')
    return tuple(result),states
def toy(n,var):
    al={i:list(range(1,2+(i+var)%3)) for i in range(n)};nom={};sites={};g={}
    for z,t,b in product(range(2),range(3),range(2)):
        v=(z,t,b);site=0 if t==0 else 1+b if t==1 else 3
        sites[v]=site;nom[v]=0;g[v]={}
        for a in [0]+al[site]:
            nb=(a+b)%2
            if var==0:bad=a!=0 and z==0
            elif var==1:bad=nb==z
            elif var==2:bad=a!=0 and (a+b+z)%2==0
            else:bad=nb==1
            g[v][a]={'post':[z,t+1,nb],'terminal':t==2,'outcome':('FAIL' if bad else 'SUCCESS') if t==2 else None}
    return al,nom,sites,g
def full_enum(n,al,sites,g):
    marg=[[F()]*9 for _ in range(2)];u=[F()]*9;count=0
    for values in product(*(tuple([-1]+al[i]) for i in range(n))):
        selected={i:a for i,a in enumerate(values) if a!=-1};degree=len(selected);mass=F(1)
        for i in selected:mass*=F(1,len(al[i]))
        bad=[]
        for z in range(2):
            node=(z,0,0);mf=False;seen=[]
            while True:
                site=sites[node];require(site not in seen,'toy query repeated');seen.append(site)
                a=selected.get(site,0);mf=mf or site in selected;e=g[node][a]
                if e['terminal']:break
                node=tuple(e['post'])
            fail=mf and e['outcome']!='SUCCESS';bad.append(fail)
            if fail:marg[z][degree]+=mass
        if any(bad):u[degree]+=mass
        count+=1
    return marg,u,count
def main():
    c=read(HERE/'contract.json');r=capture(HERE/'evidence',strict=True);tag=Counter(t for t,o in r);before=r[0][1]
    require(r[0][0]=='INPUT_BINDING_BEFORE' and before==next(o for t,o in r if t=='INPUT_BINDING_AFTER'),'beforeafter')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'HEAD')
    tree={v.split(b'\t')[1].decode():v.split()[2].decode() for v in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if v}
    src=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources'];audit=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=audit['fixed_native_file_hashes']|audit['post_controller_commit_native_tail_hashes'];prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(src)|prior|{'experiments/rebuild_status_current.json'};inputs=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('candidate.py','check_stored.py','execute.py','contract.json')}
    require((len(src),len(native),len(prior),len(bound),len(inputs))==(313,153,479,793,950) and set(before['input_sha256'])==inputs,'extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,h in (src|native|before['input_sha256']).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==h,p)
    for n in ['candidate.py','check_stored.py']:
        for node in ast.walk(ast.parse((HERE/n).read_bytes())):
            if isinstance(node,ast.Import):require(all(a.name.split('.')[0] not in ['rfl_rebuild','candidate','check_stored'] for a in node.names),'forbidden import')
            if isinstance(node,ast.ImportFrom):require(not node.module or node.module.split('.')[0] not in ['rfl_rebuild','candidate','check_stored'],'forbidden from')
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
    for t,k,phi,xy in product(range(12),range(2),range(6),sorted(cells-{(4,2)})):
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
    output=r
    require(audits==[o for t,o in output if t=='COMPLETE_SHARED_SITE'],'full site audit')
    toyrows=[o for t,o in output if t=='SHARED_TOY_FULL_ENUMERATION'];toybuilt=[];toycount=0;product_counterexamples=0;forwardstates=0
    for n in c['toys']['n_values']:
        for var in c['toys']['variants']:
            al,nm,ss,gg=toy(n,var);m,u,count=full_enum(n,al,ss,gg);ps=[]
            for z in range(2):
                p,s=forward((z,0,0),n,al,nm,ss,gg,3);forwardstates+=s;require(list(p)==m[z],'complete toy marginal');ps.append(p)
            rec={'n':n,'variant':var,'target_lists':[[i,al[i]] for i in al],
                 'sites':[[list(a),v] for a,v in ss.items()],
                 'graph':[[list(a),[[v,e] for v,e in acts.items()]] for a,acts in gg.items()],
                 'marginals':[pack(p) for p in ps],'exact_shared_world_union':pack(u),'full_assignments':count}
            require(rec==toyrows[len(toybuilt)],'all prospective toys');toybuilt.append(rec);toycount+=count
            for k in range(n+1):
                support=choose(n,k);require(max(p[k] for p in ps)<=u[k]<=min(F(support),sum(p[k] for p in ps)),'exact toy union bound')
                falseproduct=1-(1-ps[0][k]/support)*(1-ps[1][k]/support)
                product_counterexamples+=falseproduct!=u[k]/support
    rows=[o for t,o in output if t=='COMPLETE_MARGINAL_POLYNOMIAL'];built=[];bounds=[]
    for gi,grammar in enumerate(c['grammars']):
        tar=targets[gi];M=len(tar);require(M==grammar['eligible_sites'] and sum(map(len,tar.values()))==grammar['target_assignments_singleton'],'all eligible measure support')
        syntax=[1]+[0]*8
        for alternatives in tar.values():
            syntax=[syntax[k]+(syntax[k-1]*len(alternatives) if k else 0) for k in range(9)]
        ps=[]
        for i,b in enumerate(bs):
            root=(0,2,0,b['kappa'],b['phase'],b['committed'],0);p,s=forward(root,M,tar,nom,sites,graph,12);forwardstates+=s;ps.append(p)
            row=rows[len(built)];expect={'grammar':grammar['name'],'basis_index':i,'basis':[b['kappa'],b['phase'],b['committed']],'eligible_sites_global':M,'failure_manifestation_weight':pack(p),'full_world_unread_declarations_retained':True}
            require({k:v for k,v in row.items() if k!='backward_states'}==expect,'all exact marginal coefficients');built.append(row)
        for k in c['k_values']:
            support=choose(M,k);ms=[p[k]/support for p in ps];lo=max(ms);hi=min(F(1),sum(ms,F()))
            bounds.append({'grammar':grammar['name'],'k':k,'shape':'no-shape','context_subsets':support,'target_assigned_syntax_worlds':syntax[k],
               'marginal_masses':pack(ms),'trigger_union_lower':pack([lo])[0],'trigger_union_upper':pack([hi])[0],
               'exact_trigger_normalizer':pack([lo])[0] if lo==hi else None,'conditional_distribution_proved_defined':lo>0,
               'conditional_distribution_proved_undefined':hi==0,'joint_normalizer_closed':lo==hi,
               'not_defect_times_scene_mass':True,'scientific_grammar_measure_adopted':False,'statistical_N':None})
    require(bounds==[o for t,o in output if t=='COMPLETE_CELL_UNION_BOUNDS'],'all cell bounds')
    final=output[-1][1];require(output[-1][0]=='FINAL' and final['cells']==bounds,'final')
    require(final['marginal_registry_sha256']==sha256(canonical(built)).hexdigest() and final['site_registry_sha256']==sha256(canonical(audits)).hexdigest() and final['toy_registry_sha256']==sha256(canonical(toybuilt)).hexdigest(),'full ordered registries')
    require(final['toys']==len(toybuilt)==12 and final['toy_full_assignments']==toycount and final['marginals']==len(built)==96,'counters')
    require(final['backward_states']==sum(o['backward_states'] for o in built),'backward counter')
    require(tag==Counter({'INPUT_BINDING_BEFORE':1,'SHARED_TOY_FULL_ENUMERATION':12,'COMPLETE_SHARED_SITE':5904,'COMPLETE_MARGINAL_POLYNOMIAL':96,'COMPLETE_CELL_UNION_BOUNDS':8,'INPUT_BINDING_AFTER':1,'FINAL':1}),'complete language')
    require(all(final[k]==0 for k in ['new_reference_learner_DP','new_native_kernel_steps','new_native_learner_rollouts','B1_arms','keys_allocated','random_draws','future_training']) and all(final[k] is False for k in ['collector_executed','scientific_PASS','scientific_rules_adopted','collection_authorized','mechanism_direction_falsified','research_complete','mixed_or_joint_B2_totality_closed']),'scope')
    print('CHECK='+canonical({'status':'FULL_STORED_PURE_X_MARGINAL_AND_UNION_BOUND_CHECK_NOT_SCIENCE','implementation_independence':'PRIMARY_ONLY_NOT_EXPERT',
      'complete_D':13824,'complete_X':5904,'old_graph_edges':20588,'old_basis_rows':278,'marginals':96,'cells':8,
      'toys':12,'toy_full_assignments':toycount,'false_product_toy_counterexamples':product_counterexamples,
      'forward_scalar_states':forwardstates,'runtime_inputs':950,'parent_HEAD_bindings':793,
      'no_RFL_candidate_old_checker_solver_execution':True,'scientific_PASS':False,'collection_authorized':False,'research_complete':False}).decode().rstrip('\n'))
if __name__=='__main__':main()

