"""Exact full-support D-only weighted model counting, not a sampler or B1.""" 
from collections import defaultdict
from fractions import Fraction as F
from functools import lru_cache
from hashlib import sha1, sha256
from itertools import product
from math import comb
from pathlib import Path
import json, subprocess, time
HERE=Path(__file__).resolve().parent; PREP=HERE.parent; ROOT=HERE.parents[4]
DEG=8

def canonical(x):
    return (json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def emit(t,x): print(t+'='+canonical(x).decode().rstrip('\n'),flush=True)
def read(p): return json.loads(p.read_bytes())
def require(ok,why):
    if not ok: raise AssertionError(why)
def packed(p): return [[x.numerator,x.denominator] for x in p]
def choose(n,k): return comb(n,k) if 0<=k<=n else 0
def multiply(a,b):
    return tuple(sum((a[j]*b[k-j] for j in range(k+1)),F()) for k in range(DEG+1))
def records(info):
    p=PREP/info['folder']; cl,ex=read(p/'claim.json'),read(p/'exit.json')
    require(ex['native_child_exit_code']==info['exit'] and all(ex[k]==v for k,v in cl.items()),'stored receipt')
    for n,h in ex['files'].items():
        b=(p/n).read_bytes(); require({'bytes':len(b),'sha256':sha256(b).hexdigest()}==h,'stored complete raw bytes')
    require(ex['files']['stdout.log']['sha256']==info['stdout_sha256'] and not (p/'stderr.log').read_bytes(),'old source-bound capture')
    out=[]
    for line in (p/'stdout.log').read_bytes().splitlines():
        if b'=' in line:
            t,b=line.split(b'=',1)
            if b[:1] in (b'[',b'{'): out.append((t.decode(),json.loads(b)))
    return out
def bind(c):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(head==c['parent_commit'],'parent drift')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound))==(313,153,434,748),'parent extent')
    for p in bound:
        b=(ROOT/p).read_bytes(); require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native).items(): require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==905,'runtime extent')
    return {'parent_HEAD':head,'HEAD_byte_bindings':748,'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}

def backward(root,variables,alternatives,nominal,edges):
    """Each terminal cylinder retains all unread complete declarations."""
    M=len(variables); V=set(variables)
    @lru_cache(None)
    def walk(node,v,manifest):
        selected=node in V
        nv=v+int(selected); require(nv<=M,'variables repeated on path')
        def child(act,flag):
            e=edges[node][act]
            if e['terminal']:
                accept=e['outcome']=='SUCCESS' or not flag
                return tuple(F(choose(M-nv,j)) if accept else F() for j in range(DEG+1))
            return walk(tuple(e['post']) if isinstance(e['post'],list) else e['post'],nv,flag)
        out=list(child(nominal[node],manifest))
        if selected:
            targets=alternatives[node]; require(targets,'eligible variable without targets')
            for a in targets:
                tail=child(a,True)
                for j in range(1,DEG+1): out[j]+=tail[j-1]/len(targets)
        return tuple(out)
    p=walk(root,0,False); states=walk.cache_info().currsize
    require(all(F()<=p[k]<=choose(M,k) for k in range(DEG+1)),'no-trigger polynomial outside complete support')
    return p,states

def toy(n,variant):
    targets={i:list(range(1,2+(i+variant)%3)) for i in range(n)}
    nominal={i:0 for i in range(n-2)}; edges={}
    for i in nominal:
        edges[i]={}
        for a in [0]+targets[i]:
            j=i+1+(a%2 if a else 0); term=j>=n-2
            outcome=('FAIL' if variant==2 else 'SUCCESS') if a==0 else ('FAIL' if variant and (i+a+variant)%3==0 else 'SUCCESS')
            edges[i][a]={'post':j,'terminal':term,'outcome':outcome if term else None}
    return targets,nominal,edges

def enumerate_toy(n,variables,targets,edges):
    out=[F() for _ in range(DEG+1)]; worldcount=0
    for values in product(*[[-1]+targets[i] for i in variables]):
        assignment=dict(zip(variables,values)); k=sum(a!=-1 for a in values)
        weight=F(1)
        for i,a in assignment.items():
            if a!=-1: weight/=len(targets[i])
        node=0; manifest=False
        while True:
            act=assignment.get(node,-1); manifest|=act!=-1
            e=edges[node][0 if act==-1 else act]
            if e['terminal']: break
            node=e['post']
        if e['outcome']=='SUCCESS' or not manifest: out[k]+=weight
        worldcount+=1
    return tuple(out),worldcount

def main():
    start=time.perf_counter(); c=read(HERE/'contract.json'); before=bind(c); emit('INPUT_BINDING_BEFORE',before)
    toyrows=[]; toyworlds=0
    for n in c['toy_contract']['n_values']:
        for variant in c['toy_contract']['variants']:
            al,nom,g=toy(n,variant)
            for scope in c['toy_contract']['scopes']:
                variables=[i for i in range(n) if scope=='all' or i%2==int(scope[-1])]
                p,states=backward(0,variables,al,nom,g)
                oracle,worlds=enumerate_toy(n,variables,al,g); require(p==oracle,'complete toy oracle')
                rec={'n':n,'variant':variant,'scope':scope,'variables':variables,'target_multiplicities':[len(al[i]) for i in range(n)],
                     'graph':[[i,[[a,e] for a,e in sorted(acts.items())]] for i,acts in sorted(g.items())],
                     'no_trigger':packed(p),'complete_assignments':worlds,'backward_states':states}
                toyrows.append(rec); toyworlds+=worlds; emit('TOY_COMPLETE_ORACLE',rec)
    old={name:records(info) for name,info in c['stored'].items()}
    D=[r for t,r in old['catalog'] if t=='DECISION_CONTEXT']; X=[r for t,r in old['catalog'] if t=='CONTROLLER_SITE']
    E=[r for r in D if r['alternatives']]
    require((len(D),len(X),len(E))==(13824,5904,7551),'full original catalog')
    alt={tuple(r['context']):r['alternatives'] for r in E}
    nominal={}
    for r in D:
        q={a:float.fromhex(h) for a,h in r['q_row_hex']}; b=max(q.values())
        nominal[tuple(r['context'])]=min(a for a,v in q.items() if v==b)
        for a in r['alternatives']: require(b+(b-q[a])>b,'fixed installer dominance')
    graph=defaultdict(dict)
    for t,r in old['legal_graph']:
        if t=='NATIVE_LEGAL_EDGE': graph[tuple(r['pre'])][r['command']]=r['result']
    require(sum(map(len,graph.values()))==20588 and len(graph)==6254,'full stored legal DAG')
    bs=next(r['entries'] for t,r in old['basis'] if t=='NATIVE_BASIS')
    for b in bs:
        node=(0,2,0,b['kappa'],b['phase'],b['committed'],0); raw=[]
        while True:
            act=nominal[node]; e=graph[node][act]
            raw.append([list(node[:5]),node[5],node[6],act,act,act,e['reward_hex'],e['post'][:5],e['post'][5:],e['terminal'],e['outcome'],False])
            if e['terminal']: break
            node=tuple(e['post'])
        require(raw==b['payload']['trace'] and sum(float.fromhex(r[6]) for r in raw).hex()==b['payload']['return_hex'],'old48 basis interpretation')
    v36=next(r for t,r in old['installers'] if t=='FINAL')
    require(v36['actual_records']==1172 and v36['new_native_rollouts']==1171,'old native installer interpretation')
    sectors=defaultdict(list); groups=defaultdict(list)
    for r in E:
        address=tuple(r['context']); sectors[address[3:6]].append(address); groups[address[3:]].append(address)
    require(len(sectors)==48 and len(groups)==96,'original structural partition')
    for node,acts in graph.items():
        for e in acts.values():
            require(tuple(e['post'][3:6])==node[3:6] and e['post'][2]==node[2]+1,'sector invariant and monotone time')
    emit('FULL_SUPPORT_BINDING',{'all_D':13824,'noneligible_D':6273,'eligible_D':7551,'all_X_retained':5904,
         'unreachable_D_retained':13824-6254,'sector_count':48,'shape_group_count':96,'complete_contexts_sha256':sha256(b''.join(canonical(r) for r in D)).hexdigest(),
         'target_multiplicity_sum':sum(len(r['alternatives']) for r in E),'full_declared_world_identity_not_collapsed':True})
    rows=[]; totalstates=0; pooled=(F(1),)+(F(),)*DEG; cluster=[F() for _ in range(DEG+1)]
    for kind,parts in (('sector',sectors),('group',groups)):
        for key,V in sorted(parts.items()):
            k,phi,z=key[:3]; root=(0,2,0,k,phi,z,0)
            p,states=backward(root,V,alt,nominal,graph); totalstates+=states
            rec={'kind':kind,'key':list(key),'contexts':len(V),'unreachable_contexts_retained':sum(v not in graph for v in V),
                 'no_trigger':packed(p),'total_weight':[choose(len(V),j) for j in range(DEG+1)],'backward_states':states}
            rows.append(rec); emit('COMPLETE_PART_POLYNOMIAL',rec)
            if kind=='sector': pooled=multiply(pooled,p)
            else:
                for j in range(DEG+1): cluster[j]+=p[j]
    allsizes=[len(V) for V in groups.values()]
    cells=[]
    syntax=next(r for t,r in old['catalog'] if t=='CATALOG_SUMMARY')['decision_cells']
    for cell in c['cells']:
        k,shape=cell['k'],cell['shape']; alltotal=choose(7551,k)
        clusteredtotal=sum(choose(n,k) for n in allsizes)
        if shape=='singleton': M,A=alltotal,pooled[k]
        elif shape=='clustered': M,A=clusteredtotal,cluster[k]
        else: M,A=alltotal-clusteredtotal,pooled[k]-cluster[k]
        oldcount=next(r for r in syntax if r['k']==k and r['shape']==shape)
        require(M==oldcount['context_subsets'] and F()<=A<=M and M>0,'complete cell support')
        Z=1-A/M
        rec={**cell,'context_subsets':M,'target_assigned_worlds_read_only':oldcount['target_assigned_syntax_worlds'],
             'weighted_no_trigger_count':[A.numerator,A.denominator],'normalizer':[Z.numerator,Z.denominator],
             'nontrigger':[ (1-Z).numerator,(1-Z).denominator],'conditional_distribution_defined':Z>0,
             'normalizer_float_display_only':float(Z),'statistical_N':None,'scientific_measure_adopted':False}
        cells.append(rec); emit('COMPLETE_CELL_NORMALIZER',rec)
    require(cells[0]['normalizer']==[85,90612],'singleton independent compatibility NOT rerun')
    emit('GLOBAL_POLYNOMIAL',{'all_no_trigger':packed(pooled),'clustered_no_trigger_degree_ge2':packed(cluster),
         'all_total_weight':[choose(7551,j) for j in range(DEG+1)]})
    after=bind(c); require(before==after,'input drift'); emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'COMPLETE_FULL_D_ONLY_STRUCTURAL_NORMALIZERS_NOT_GENERATOR_OR_SCIENCE','all_inputs_equal':True,
         'cells':cells,'part_registry_sha256':sha256(canonical(rows)).hexdigest(),'toy_registry_sha256':sha256(canonical(toyrows)).hexdigest(),
         'parts':144,'backward_states':totalstates,'toy_records':len(toyrows),'toy_complete_assignments':toyworlds,
         'elapsed_seconds':time.perf_counter()-start,'normalizer_DP_executed':True,'new_reference_or_learner_DP':0,
         'new_native_kernel_steps':0,'new_native_learner_rollouts':0,'B1_arms':0,'future_training':0,'keys_allocated':0,
         'random_draws':0,'collector_executed':False,'scientific_rules_adopted':False,'scientific_PASS':False,
         'collection_authorized':False,'research_complete':False,'X_or_mixed_normalizer_closed':False})
if __name__=='__main__': main()

