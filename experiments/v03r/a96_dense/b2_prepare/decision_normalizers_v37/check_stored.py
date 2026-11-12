"""Independent forward weighted counting + exhaustive toy oracle. Stdlib only."""
from collections import defaultdict, deque, Counter
from fractions import Fraction as F
from hashlib import sha1,sha256
from itertools import product
from math import comb
from pathlib import Path
import json, subprocess, time
HERE=Path(__file__).resolve().parent; PREP=HERE.parent; ROOT=HERE.parents[4]
L=8
def canonical(x): return (json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def read(p): return json.loads(p.read_bytes())
def require(ok,why):
    if not ok: raise AssertionError(why)
def packed(xs): return [[x.numerator,x.denominator] for x in xs]
def choose(n,k): return comb(n,k) if 0<=k<=n else 0
def capture(p,info=None,strict=False):
    cl,ex=read(p/'claim.json'),read(p/'exit.json')
    require(ex['native_child_exit_code']==(info['exit'] if info else 0) and all(ex[k]==v for k,v in cl.items()),'native claim exit')
    for n,v in ex['files'].items():
        b=(p/n).read_bytes(); require({'bytes':len(b),'sha256':sha256(b).hexdigest()}==v,'native raw full bytes')
    require(not (p/'stderr.log').read_bytes(),'unexpected stderr')
    if info: require(ex['files']['stdout.log']['sha256']==info['stdout_sha256'],'stored source binding')
    for n,d in ex['inputs'].items(): require(sha256((p.parent/n).read_bytes()).hexdigest()==d,'native source input')
    rows=[]
    for line in (p/'stdout.log').read_bytes().splitlines(keepends=True):
        require(line.endswith(b'\n'),'incomplete raw line')
        if b'=' not in line:
            require(not strict,'untagged new output'); continue
        t,v=line.rstrip(b'\r\n').split(b'=',1)
        if v[:1] not in (b'[',b'{'):
            require(not strict,'invalid new JSON'); continue
        obj=json.loads(v)
        if strict: require(canonical(obj).rstrip(b'\n')==v,'new noncanonical content')
        rows.append((t.decode(),obj))
    return rows,ex

def forward(root,V,alternatives,nominal,edges,order):
    """Topological incoming scalar monomials, then binomial terminal completion."""
    V=set(V); M=len(V); incoming={root:{(0,False,0):F(1)}}; out=[F() for _ in range(L+1)]
    statecount=0
    for node in order:
        bag=incoming.pop(node,{})
        statecount+=len(bag)
        isvar=node in V
        for (v,flag,k),weight in bag.items():
            nv=v+int(isvar); require(nv<=M,'complete variable recurrence')
            choices=[(nominal[node],flag,k,F(1))]
            if isvar and k<L:
                choices += [(a,True,k+1,F(1,len(alternatives[node]))) for a in alternatives[node]]
            for a,nflag,nk,factor in choices:
                edge=edges[node][a]; w=weight*factor
                if edge['terminal']:
                    if edge['outcome']=='SUCCESS' or not nflag:
                        for degree in range(nk,L+1): out[degree]+=w*choose(M-nv,degree-nk)
                else:
                    nxt=tuple(edge['post']) if isinstance(edge['post'],list) else edge['post']
                    key=(nv,nflag,nk); target=incoming.setdefault(nxt,{})
                    target[key]=target.get(key,F())+w
    require(not incoming,'not complete topological graph')
    require(all(F()<=out[k]<=choose(M,k) for k in range(L+1)),'no-trigger count outside support')
    return tuple(out),statecount

def toy_graph(n,version):
    counts=[1+(i+version)%3 for i in range(n)]
    targets={i:list(range(1,counts[i]+1)) for i in range(n)}
    edges={};nom={}
    for i in range(n-2):
        nom[i]=0; edges[i]={}
        for a in range(counts[i]+1):
            dest=i+1+(a%2)
            term=dest>=n-2
            fail=(version==2) if a==0 else (version!=0 and (i+a+version)%3==0)
            edges[i][a]={'post':dest,'terminal':term,'outcome':('FAIL' if fail else 'SUCCESS') if term else None}
    return targets,edges,nom

def assignments(V,alts):
    for values in product(*[[-1]+alts[i] for i in V]):
        d=dict(zip(V,values)); degree=sum(a>=0 for a in values); w=F(1)
        for i,a in d.items():
            if a>=0: w/=len(alts[i])
        yield d,degree,w

def accept(d,edges):
    at=0; manifest=False
    while True:
        a=d.get(at,-1)
        if a>=0: manifest=True
        e=edges[at][max(a,0)]
        if e['terminal']: return e['outcome']=='SUCCESS' or not manifest
        at=e['post']

def oracle(V,alts,edges):
    p=[F() for _ in range(L+1)]; count=0
    for d,k,w in assignments(V,alts):
        if accept(d,edges): p[k]+=w
        count+=1
    return tuple(p),count

def main():
    start=time.perf_counter(); c=read(HERE/'contract.json'); rows,ex=capture(HERE/'evidence',strict=True)
    tags=Counter(t for t,o in rows)
    require(tags==Counter({'INPUT_BINDING_BEFORE':1,'TOY_COMPLETE_ORACLE':60,'FULL_SUPPORT_BINDING':1,
        'COMPLETE_PART_POLYNOMIAL':144,'COMPLETE_CELL_NORMALIZER':7,'GLOBAL_POLYNOMIAL':1,'INPUT_BINDING_AFTER':1,'FINAL':1}),'complete new output language')
    one={t:o for t,o in rows if tags[t]==1}
    before=one['INPUT_BINDING_BEFORE']; require(before==one['INPUT_BINDING_AFTER'],'beforeafter all input bytes')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(head==c['parent_commit']==before['parent_HEAD'],'parent HEAD')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    expected=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require((len(sources),len(native),len(prior),len(bound),len(expected))==(313,153,434,748,905),'complete runtime extent')
    require(set(before['input_sha256'])==expected,'missing/excess input')
    for p in bound:
        b=(ROOT/p).read_bytes(); require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native|before['input_sha256']).items(): require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    toyrows=[o for t,o in rows if t=='TOY_COMPLETE_ORACLE']; idx=0; toyworlds=0
    for n in c['toy_contract']['n_values']:
        for version in c['toy_contract']['variants']:
            al,g,nom=toy_graph(n,version)
            for scope in c['toy_contract']['scopes']:
                V=list(range(n)) if scope=='all' else list(range(int(scope[-1]),n,2))
                expectedpoly,worlds=oracle(V,al,g)
                forwardpoly,states=forward(0,V,al,nom,g,list(range(n-2)))
                rec=toyrows[idx];idx+=1
                require(rec['n']==n and rec['variant']==version and rec['scope']==scope and rec['variables']==V,'prospective toy ordering')
                require(rec['target_multiplicities']==[len(al[i]) for i in range(n)] and rec['graph']==[[i,[[a,e] for a,e in sorted(acts.items())]] for i,acts in sorted(g.items())],'full toy graph definition')
                require(rec['no_trigger']==packed(expectedpoly)==packed(forwardpoly) and rec['complete_assignments']==worlds,'exhaustive complete toy world measure')
                toyworlds+=worlds
    pair=[]
    for version in (1,2):
        al,g,nom=toy_graph(3,version); pair.append((al,g,oracle(list(range(3)),al,g)[0]))
    joint=[F() for _ in range(L+1)]; pairworlds=0
    for d1,k1,w1 in assignments(list(range(3)),pair[0][0]):
        for d2,k2,w2 in assignments(list(range(3)),pair[1][0]):
            if accept(d1,pair[0][1]) and accept(d2,pair[1][1]): joint[k1+k2]+=w1*w2
            pairworlds+=1
    require(tuple(joint)==tuple(sum((pair[0][2][j]*pair[1][2][k-j] for j in range(k+1)),F()) for k in range(L+1)),'disjoint-sector full product oracle')
    old={name:capture(PREP/info['folder'],info)[0] for name,info in c['stored'].items()}
    D=[r for t,r in old['catalog'] if t=='DECISION_CONTEXT']; X=[r for t,r in old['catalog'] if t=='CONTROLLER_SITE']
    q={tuple(r['context']):{a:float.fromhex(h) for a,h in r['q_row_hex']} for r in D}
    cells={(0,2),(4,2)}|{(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)}
    shifts={0:(0,-1),1:(0,1),2:(-1,0),3:(1,0),4:(0,0)}
    dist={(4,2):0};queue=deque(dist)
    while queue:
        p=queue.popleft()
        for dx,dy in shifts.values():
            s=p[0]+dx,p[1]+dy
            if s in cells and s not in dist: dist[s]=dist[p]+1;queue.append(s)
    require(len(D)==len(q)==13824 and len(X)==5904,'all catalogs retained')
    domain=[(x,y,t,k,phi,z,m) for t in range(12) for k in range(2) for phi in range(6)
            for x,y in sorted(cells-{(4,2)}) for z in range(4) for m in range(2)]
    require([tuple(r['context']) for r in D]==domain,'complete ordered original Cartesian domain')
    alt={};nominal={};legal={}
    for r in D:
        node=tuple(r['context']);x,y,t,k,phi,z,m=node
        acts=[]
        for a,(dx,dy) in shifts.items():
            s=x+dx,y+dy
            if s not in cells: continue
            if z==0 and dist[s]!=dist[(x,y)]-1: continue
            if z in (1,3) and m==0 and s==(4,2): continue
            if z==2 and m==0 and s in ((2,2),(4,2)): continue
            acts.append(a)
        require(acts==list(q[node]),'independent legal set')
        b=max(q[node].values());optimal=[a for a,v in q[node].items() if v>=b-1e-12]
        alternatives=[a for a in acts if a not in optimal]
        require(r['optimal_actions']==optimal and r['alternatives']==alternatives and r['group']==list(node[3:]),'all targets and shape groups')
        legal[node]=acts;nominal[node]=min(a for a,v in q[node].items() if v==b)
        if alternatives: alt[node]=alternatives
        for a in alternatives: require(b+(b-q[node][a])>b,'stored strict DQ promotion')
    graph=defaultdict(dict)
    for t,r in old['legal_graph']:
        if t!='NATIVE_LEGAL_EDGE': continue
        node=tuple(r['pre']);a=r['command'];res=r['result']
        require(a not in graph[node],'duplicate legal native edge')
        x,y,t,k,phi,z,m=node;dx,dy=shifts[a];nx,ny=x+dx,y+dy;nt=t+1
        require(a in legal[node],'illegal stored edge')
        outcome='COLLISION' if (nx,ny)==(2,2) and nt%(6,3)[k]==phi%(6,3)[k] else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
        nm=int(bool(m or (z==1 and (nx,ny)==(2,1)) or (z==3 and (nx,ny)==(2,4)) or (z==2 and (x,y)==(1,2) and t%(6,3)[k]!=phi%(6,3)[k])))
        expect={'post':[nx,ny,nt,k,phi,z,nm],'a_cmd':a,'u':a,'a_realized':a,'reward_hex':(-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)).hex(),'terminal':outcome is not None,'outcome':outcome,'illegal':False}
        require(res==expect,'independent step/automaton/terminal/reward/invariant')
        graph[node][a]=res
    reachable={(0,2,0,k,phi,z,0) for k in range(2) for phi in range(6) for z in range(4)};queue=deque(reachable)
    while queue:
        n=queue.popleft();require(set(graph[n])==set(legal[n]),'full legal branch closure')
        for e in graph[n].values():
            post=tuple(e['post'])
            if not e['terminal'] and post not in reachable: reachable.add(post);queue.append(post)
    require(len(reachable)==len(graph)==6254 and sum(map(len,graph.values()))==20588,'old complete native graph')
    bs=next(o['entries'] for t,o in old['basis'] if t=='NATIVE_BASIS');rawcount=0
    require([(b['kappa'],b['phase'],b['committed']) for b in bs]==list(product(range(2),range(6),range(4))),'complete48 old basis')
    for b in bs:
        n=(0,2,0,b['kappa'],b['phase'],b['committed'],0);trace=[]
        while True:
            a=nominal[n];e=graph[n][a]
            trace.append([list(n[:5]),n[5],n[6],a,a,a,e['reward_hex'],e['post'][:5],e['post'][5:],e['terminal'],e['outcome'],False])
            if e['terminal']:break
            n=tuple(e['post'])
        require(trace==b['payload']['trace'] and trace[-1][10]==b['payload']['outcome'] and sum(float.fromhex(r[6]) for r in trace).hex()==b['payload']['return_hex'],'old basis entire raw trace')
        rawcount+=len(trace)
    support=one['FULL_SUPPORT_BINDING']
    require(support=={'all_D':13824,'noneligible_D':6273,'eligible_D':7551,'all_X_retained':5904,'unreachable_D_retained':7570,
        'sector_count':48,'shape_group_count':96,'complete_contexts_sha256':sha256(b''.join(canonical(r) for r in D)).hexdigest(),
        'target_multiplicity_sum':sum(map(len,alt.values())),'full_declared_world_identity_not_collapsed':True},'full support binding')
    groups=defaultdict(list);sectors=defaultdict(list)
    for n in alt: groups[n[3:]].append(n);sectors[n[3:6]].append(n)
    require((len(alt),len(groups),len(sectors),rawcount)==(7551,96,48,278),'full variable partition')
    parts=[o for t,o in rows if t=='COMPLETE_PART_POLYNOMIAL'];pi=0;totalforward=0;pooled=[F(1)]+[F()]*L;cluster=[F()]* (L+1)
    for kind,partition in (('sector',sectors),('group',groups)):
        for key,V in sorted(partition.items()):
            root=(0,2,0,*key[:3],0);order=sorted((n for n in reachable if n[3:6]==key[:3]),key=lambda n:(n[2],n))
            p,states=forward(root,V,alt,nominal,graph,order);totalforward+=states
            rec=parts[pi];pi+=1
            require(rec['kind']==kind and rec['key']==list(key) and rec['contexts']==len(V) and rec['unreachable_contexts_retained']==sum(n not in graph for n in V),'full part support')
            require(rec['no_trigger']==packed(p) and rec['total_weight']==[choose(len(V),j) for j in range(L+1)],'independent full forward count')
            if kind=='sector':
                pooled=[sum((pooled[j]*p[k-j] for j in range(k+1)),F()) for k in range(L+1)]
            else: cluster=[a+b for a,b in zip(cluster,p)]
    glob=one['GLOBAL_POLYNOMIAL']
    require(glob=={'all_no_trigger':packed(pooled),'clustered_no_trigger_degree_ge2':packed(cluster),'all_total_weight':[choose(7551,j) for j in range(L+1)]},'global complement product and full cluster sum')
    cellrows=[o for t,o in rows if t=='COMPLETE_CELL_NORMALIZER']
    syntax=next(o for t,o in old['catalog'] if t=='CATALOG_SUMMARY')['decision_cells']
    for decl,rec in zip(c['cells'],cellrows):
        k=decl['k'];ct=sum(choose(len(V),k) for V in groups.values())
        total=choose(7551,k);A=pooled[k]
        if decl['shape']=='clustered': total,A=ct,cluster[k]
        if decl['shape']=='distributed':total,A=total-ct,A-cluster[k]
        Z=F(total)-A;Z/=total
        oldcount=next(r for r in syntax if r['k']==k and r['shape']==decl['shape'])
        require(rec=={**decl,'context_subsets':total,'target_assigned_worlds_read_only':oldcount['target_assigned_syntax_worlds'],
          'weighted_no_trigger_count':[A.numerator,A.denominator],'normalizer':[Z.numerator,Z.denominator],
          'nontrigger':[(1-Z).numerator,(1-Z).denominator],'conditional_distribution_defined':Z>0,
          'normalizer_float_display_only':float(Z),'statistical_N':None,'scientific_measure_adopted':False},'exact full cell normalizer under original measure')
        require(total==oldcount['context_subsets'],'old cell count unmodified')
    require(cellrows[0]['normalizer']==[85,90612],'old singleton exact compatibility NOT new native rerun')
    final=one['FINAL']
    require(final['cells']==cellrows and final['part_registry_sha256']==sha256(canonical(parts)).hexdigest() and final['toy_registry_sha256']==sha256(canonical(toyrows)).hexdigest(),'full registry hashes')
    require(final['toy_complete_assignments']==toyworlds and final['parts']==144 and final['toy_records']==60,'complete counters')
    require(final['normalizer_DP_executed'] is True and all(final[k]==0 for k in ('new_reference_or_learner_DP','new_native_kernel_steps','new_native_learner_rollouts','B1_arms','future_training','keys_allocated','random_draws')),'execution limits')
    require(all(final[k] is False for k in ('collector_executed','scientific_rules_adopted','scientific_PASS','collection_authorized','research_complete','X_or_mixed_normalizer_closed')),'no science promotion')
    print('CHECK='+canonical({'status':'COMPLETE_FULL_D_NORMALIZER_STORED_CHECK_NOT_SCIENCE','role':'PRIMARY_IMPLEMENTATION_INDEPENDENCE_NOT_EXPERT',
       'sources':313,'old_native':153,'prior_preparation':434,'HEAD_byte_bindings':748,'runtime_inputs':905,
       'all_D_contexts':13824,'eligible_D':7551,'noneligible_D_retained':6273,'unreachable_D_retained':7570,
       'old_native_legal_edges':20588,'old_basis_raw_rows':278,'full_parts':144,'cells':cellrows,
       'toy_records':60,'toy_complete_assignments':toyworlds,'toy_two_sector_joint_assignments':pairworlds,
       'forward_scalar_states':totalforward,'elapsed_seconds':time.perf_counter()-start,
       'no_RFL_candidate_predictor_old_checker_solver_execution':True,'normalizer_DP_executed':True,
       'new_reference_or_learner_DP':0,'new_native_learner_rollouts':0,'B1_arms':0,'future_training':0,'keys_allocated':0,
       'scientific_PASS':False,'collection_authorized':False,'research_complete':False}).decode().rstrip('\n'),flush=True)
if __name__=='__main__':main()

