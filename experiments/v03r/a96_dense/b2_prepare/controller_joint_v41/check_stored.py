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

def forward_joint(roots,M,targets,nom,sites,g,ticks,cap):
    current={(tuple(roots),0,0,0):F(1)};result=[F()]*9;states=0;branches=0
    for tick in range(ticks):
        nextlayer=defaultdict(F)
        for (nodes,v,j,mask),mass in current.items():
            states+=1;require(states<=cap,'fixed engineering checker state guard')
            active=[(i,n) for i,n in enumerate(nodes) if n is not None]
            require(active and all(n[2]==tick for i,n in active),'all histories synchronous tick')
            shared=sorted(set(sites[n] for i,n in active if sites[n] in targets))
            nv=v+len(shared);require(nv<=M,'unique fixed-time query count')
            options=[(None,)+tuple(targets[s]) for s in shared]
            for values in product(*options):
                chosen={s:a for s,a in zip(shared,values) if a is not None};nj=j+len(chosen)
                if nj>8:continue
                w=mass
                for s in chosen:w*=F(1,len(targets[s]))
                new=list(nodes);nm=mask;rejected=False;branches+=1
                for i,n in active:
                    site=sites[n];a=chosen.get(site,nom[n])
                    if site in chosen:nm|=2**i
                    e=g[n][a]
                    if e['terminal']:
                        if e['outcome']!='SUCCESS' and nm&(2**i):rejected=True;break
                        new[i]=None;nm&=~(2**i)
                    else:new[i]=tuple(e['post'])
                if rejected:continue
                if not any(n is not None for n in new):
                    for k in range(nj,9):result[k]+=w*choose(M-nv,k-nj)
                else:nextlayer[(tuple(new),nv,nj,nm)]+=w
        current=dict(nextlayer)
    require(not current,'all histories terminated, full joint sweep')
    return tuple(result),states,branches
def polynomial_product(polys):
    out=[F(1)]+[F()]*8
    for p in polys:
        new=[F()]*9
        for i,a in enumerate(out):
            for j,b in enumerate(p[:9-i]):new[i+j]+=a*b
        out=new
    return tuple(out)
def toy(n,var):
    al={i:list(range(1,2+(i+var)%2)) for i in range(n)};nom={};sites={};g={}
    for z,t,b in product(range(4),range(3),range(2)):
        node=(z,b,t);site=0 if t==0 else (1 if b==0 else 2) if t==1 else (3 if z%2==0 else 4)
        sites[node]=site;nom[node]=0;g[node]={}
        for a in [0]+al[site]:
            nb=(a+b+z%2)%2;term=t==2 or (var==2 and z==0 and t==1)
            if var==0:bad=nb==z%2
            elif var==1:bad=(a+b+z)%3==0
            else:bad=bool(nb)
            g[node][a]={'post':[z,nb,t+1],'terminal':term,'outcome':('FAIL' if bad else 'SUCCESS') if term else None}
    return al,nom,sites,g
def full_toy_values(n,al,nom,sites,g):
    events=[]
    for vals in product(*[[-1]+al[i] for i in range(n)]):
        selected={i:a for i,a in enumerate(vals) if a!=-1};mass=F(1)
        for i in selected:mass/=len(al[i])
        bad=[]
        for z in range(4):
            node=(z,0,0);mf=False;seen=[]
            while True:
                s=sites[node];require(s not in seen,'fixed site no repeated query');seen.append(s)
                mf|=s in selected;e=g[node][selected.get(s,nom[node])]
                if e['terminal']:break
                node=tuple(e['post'])
            bad.append(mf and e['outcome']!='SUCCESS')
        events.append((len(selected),mass,not any(bad)))
    result=[F()]*9
    for j,w,accepted in events:
        if accepted:result[j]+=w
    return tuple(result),events

def main():
    c=read(HERE/'contract.json');r=capture(HERE/'evidence_run',strict=True);tag=Counter(t for t,o in r);before=r[0][1]
    require(r[0][0]=='INPUT_BINDING_BEFORE' and before==next(o for t,o in r if t=='INPUT_BINDING_AFTER'),'beforeafter')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'HEAD')
    tree={v.split(b'\t')[1].decode():v.split()[2].decode() for v in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if v}
    src=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources'];audit=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=audit['fixed_native_file_hashes']|audit['post_controller_commit_native_tail_hashes'];prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(src)|prior|{'experiments/rebuild_status_current.json'};inputs=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('candidate.py','check_stored.py','execute.py','contract.json')}
    require((len(src),len(native),len(prior),len(bound),len(inputs))==(313,153,501,815,972) and set(before['input_sha256'])==inputs,'extent')
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

    output=r;require(audits==[o for t,o in output if t=='COMPLETE_SHARED_SITE'],'all original literal sites unchanged')
    require(audits==[o for t,o in old['marginals'] if t=='COMPLETE_SHARED_SITE'],'stored v40 complete site compatibility')
    toyrows=[o for t,o in r if t=='NEW_JOINT_TOY'];toybuilt=[];toycount=0;forwardstates=0;twosector_events=[]
    for n in c['toys']['n_values']:
        for var in c['toys']['variants']:
            al,nm,ss,gg=toy(n,var);oracle,events=full_toy_values(n,al,nm,ss,gg)
            p,s,br=forward_joint([(z,0,0) for z in range(4)],n,al,nm,ss,gg,3,c['resource_guard']['max_states_per_sector'])
            forwardstates+=s;require(p==oracle,'all shared4 toy assignments')
            row=toyrows[len(toybuilt)]
            expect={'n':n,'variant':var,'full_assignments':len(events),'no_trigger':pack(p),
                'target_lists':[[i,al[i]] for i in al],'sites':[[list(node),site] for node,site in ss.items()],
                'graph':[[list(node),[[a,e] for a,e in acts.items()]] for node,acts in gg.items()]}
            require({k:v for k,v in row.items() if k not in ['backward_states','transitions']}==expect,'complete new toy payload')
            toybuilt.append(row);toycount+=len(events)
            if n==5 and var in (0,2):twosector_events.append(events)
    fulljoint=[F()]*9;two_count=0
    for (a,wa,oka),(b,wb,okb) in product(*twosector_events):
        if a+b<=8 and oka and okb:fulljoint[a+b]+=wa*wb
        two_count+=1
    productrow=next(o for t,o in r if t=='NEW_TWO_SECTOR_TOY_PRODUCT')
    require(productrow=={'sectors':[[5,0],[5,2]],'degree0_to8_no_trigger':pack(fulljoint),'all10_variables_preserved':True},'complete two variable-sector full enumeration')
    rows=[o for t,o in r if t=='COMPLETE_SECTOR_JOINT_POLYNOMIAL'];built=[];cells=[]
    bounds={(o['grammar'],o['k']):o for t,o in old['marginals'] if t=='COMPLETE_CELL_UNION_BOUNDS'}
    globalsout=[o for t,o in r if t=='COMPLETE_GLOBAL_NO_TRIGGER_POLYNOMIAL']
    for gi,grammar in enumerate(c['grammars']):
        tar=targets[gi];M=len(tar);require(M==grammar['eligible_sites'] and sum(map(len,tar.values()))==grammar['target_assignments_singleton'],'full target multiplicities')
        parts=[];domains=[];syntax=[1]+[0]*8
        for al in tar.values():syntax=[syntax[j]+(syntax[j-1]*len(al) if j else 0) for j in range(9)]
        for k,phi in product(range(2),range(6)):
            part={s:a for s,a in tar.items() if s[3]==k and s[4]==phi};domains.append(set(part))
            roots=[(0,2,0,k,phi,z,0) for z in range(4)]
            p,s,br=forward_joint(roots,len(part),part,nom,sites,graph,12,c['resource_guard']['max_states_per_sector'])
            forwardstates+=s;parts.append(p);row=rows[len(built)]
            expect={'grammar':grammar['name'],'sector':[k,phi],'sector_eligible_sites':len(part),'roots':[list(n) for n in roots],
                'no_trigger_polynomial':pack(p),'shared_assignment_all4_roots':True,'unread_full_pre_declarations_retained':True}
            require({k:v for k,v in row.items() if k not in ['backward_states','joint_branch_transitions']}==expect,'all joint sector coefficients');built.append(row)
        require(sum(map(len,domains))==M and len(set.union(*domains))==M,'literal partition not root independence')
        total=polynomial_product(parts)
        require(globalsout[gi]=={'grammar':grammar['name'],'M':M,'no_trigger':pack(total)},'complete12-sector convolution')
        for k in c['k_values']:
            support=choose(M,k);z=F(support-total[k],support);oldb=bounds[(grammar['name'],k)]
            require(F(*oldb['trigger_union_lower'])<=z<=F(*oldb['trigger_union_upper']),'all old stored marginal bounds')
            cells.append({'grammar':grammar['name'],'k':k,'shape':'no-shape','context_subsets':support,
                 'target_assigned_syntax_worlds':syntax[k],'exact_trigger_normalizer':pack([z])[0],
                 'no_trigger_mass':pack([1-z])[0],'old_bounds':[oldb['trigger_union_lower'],oldb['trigger_union_upper']],
                 'full_support_joint_normalizer_closed':True,'conditional_distribution_defined':z>0,
                 'scientific_grammar_measure_adopted':False,'statistical_N':None,'not_defect_times_scene_mass':True})
    require(cells==[o for t,o in r if t=='COMPLETE_EXACT_CELL_NORMALIZER'],'all8 full domain exact cell normalizers')
    final=r[-1][1];require(r[-1][0]=='FINAL' and final['cells']==cells,'final full result')
    require(final['sector_registry_sha256']==sha256(canonical(built)).hexdigest() and final['site_registry_sha256']==sha256(canonical(audits)).hexdigest() and final['toy_registry_sha256']==sha256(canonical(toybuilt)).hexdigest(),'all ordered registry bytes')
    require(final['backward_states']==sum(o['backward_states'] for o in built) and final['joint_branch_transitions']==sum(o['joint_branch_transitions'] for o in built),'complete counters')
    require(final['joint_sector_polynomials']==len(built)==24 and final['toys']==len(toybuilt)==9 and final['toy_full_assignments']==toycount,'complete counts')
    require(tag==Counter({'INPUT_BINDING_BEFORE':1,'NEW_JOINT_TOY':9,'NEW_TWO_SECTOR_TOY_PRODUCT':1,
        'COMPLETE_SHARED_SITE':5904,'COMPLETE_SECTOR_JOINT_POLYNOMIAL':24,'COMPLETE_GLOBAL_NO_TRIGGER_POLYNOMIAL':2,
        'COMPLETE_EXACT_CELL_NORMALIZER':8,'INPUT_BINDING_AFTER':1,'FINAL':1}),'full exact output language')
    require(all(final[k]==0 for k in ['new_reference_learner_DP','new_native_kernel_steps','new_native_learner_rollouts','B1_arms','keys_allocated','random_draws','future_training']) and all(final[k] is False for k in ['collector_executed','sampler_executed','scientific_PASS','scientific_rules_adopted','collection_authorized','mechanism_direction_falsified','research_complete','mixed_or_joint_B2_totality_closed']),'closed research execution scope')
    print('CHECK='+canonical({'status':'FULL_STORED_PURE_X_COMMON_WORLD_JOINT_NORMALIZER_CHECK_NOT_SCIENCE',
       'implementation_independence':'PRIMARY_ONLY_NOT_EXPERT','full_D':13824,'full_X':5904,'old_graph_edges':20588,'old_basis_rows':278,
       'joint_sector_polynomials':24,'exact_cells':8,'forward_scalar_states':forwardstates,
       'toy_full_assignments':toycount,'two_sector_full_assignments':two_count,'runtime_inputs':972,'parent_HEAD_bindings':815,
       'no_RFL_candidate_old_checker_solver_execution':True,'scientific_PASS':False,'collection_authorized':False,'research_complete':False}).decode().rstrip('\n'))
if __name__=='__main__':main()
