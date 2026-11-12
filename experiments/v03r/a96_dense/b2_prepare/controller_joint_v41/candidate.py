"""Pure-X exact full-world marginals; safe shared-world union bounds only."""
from collections import Counter, defaultdict
from fractions import Fraction as F
from functools import lru_cache
from hashlib import sha1, sha256
from itertools import product
from math import comb
from pathlib import Path
import json, subprocess, time
HERE=Path(__file__).resolve().parent; PREP=HERE.parent; ROOT=HERE.parents[4]; DEG=8
def read(p):return json.loads(p.read_bytes())
def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def emit(t,o):print(t+'='+canonical(o).decode().rstrip('\n'),flush=True)
def require(v,s):
    if not v:raise AssertionError(s)
def pack(p):return [[v.numerator,v.denominator] for v in p]
def choose(n,k):return comb(n,k) if 0<=k<=n else 0
def records(i):
    p=PREP/i['folder'];c,e=read(p/'claim.json'),read(p/'exit.json')
    require(e['native_child_exit_code']==i['exit'] and all(e[k]==v for k,v in c.items()),'old receipt')
    for n,v in e['files'].items():
        b=(p/n).read_bytes();require(v=={'bytes':len(b),'sha256':sha256(b).hexdigest()},'complete old bytes')
    require(e['files']['stdout.log']['sha256']==i['stdout_sha256'] and not (p/'stderr.log').read_bytes(),'stored identity')
    out=[]
    for l in (p/'stdout.log').read_bytes().splitlines():
        if b'=' in l:
            t,v=l.split(b'=',1)
            if v[:1] in (b'[',b'{'):out.append((t.decode(),json.loads(v)))
    return out
def bind(c):
    h=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(h==c['parent_commit'],'HEAD')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',h],cwd=ROOT).split(b'\0') if r}
    source=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit'];native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')};bound=set(source)|prior|{'experiments/rebuild_status_current.json'}
    require((len(source),len(native),len(prior),len(bound))==(313,153,501,815),'parent extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (source|native).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==972,'runtime extent')
    return {'parent_HEAD':h,'HEAD_byte_bindings':815,'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}

def joint(roots,M,targets,nom,sites,edges,cap):
    states=0;transitions=0
    @lru_cache(None)
    def walk(nodes,v,mask,budget):
        nonlocal states,transitions
        states+=1;require(states<=cap,'fixed engineering joint state guard')
        live=[n for n in nodes if n is not None]
        if not live:return tuple(F(choose(M-v,j)) if j<=budget else F() for j in range(DEG+1))
        require(len({n[2] for n in live})==1,'synchronous strictly increasing time')
        query=sorted({sites[n] for n in live if targets.get(sites[n])})
        nv=v+len(query);require(nv<=M,'distinct fixed-time eligible count')
        out=[F() for _ in range(DEG+1)]
        for choices in product(*[(-1,)+tuple(targets[s]) for s in query]):
            selected=sum(a!=-1 for a in choices)
            if selected>budget:continue
            assignment=dict(zip(query,choices));weight=F(1)
            for s,a in assignment.items():
                if a!=-1:weight/=len(targets[s])
            nextnodes=[];nm=mask;bad=False;transitions+=1
            for i,n in enumerate(nodes):
                if n is None:nextnodes.append(None);continue
                a=assignment.get(sites[n],-1)
                if a!=-1:nm|=1<<i
                e=edges[n][nom[n] if a==-1 else a]
                if e['terminal']:
                    if e['outcome']!='SUCCESS' and nm&(1<<i):bad=True;break
                    nextnodes.append(None);nm&=~(1<<i)
                else:nextnodes.append(tuple(e['post']))
            if bad:continue
            tail=walk(tuple(nextnodes),nv,nm,budget-selected)
            for j in range(DEG+1-selected):out[j+selected]+=weight*tail[j]
        return tuple(out)
    p=walk(tuple(roots),0,0,DEG)
    require(all(0<=p[j]<=choose(M,j) for j in range(DEG+1)),'sector polynomial support')
    return p,states,transitions
def multiply(a,b):
    return tuple(sum((a[i]*b[j-i] for i in range(j+1)),F()) for j in range(DEG+1))
def toy(n,var):
    targets={i:tuple(range(1,2+(i+var)%2)) for i in range(n)};nom={};sites={};g={}
    for root,t,b in product(range(4),range(3),range(2)):
        node=(root,b,t);site=0 if t==0 else 1+b if t==1 else 3+root%2
        nom[node]=0;sites[node]=site;g[node]={}
        for a in (0,)+targets[site]:
            nb=(b+a+root%2)%2
            term=t==2 or var==2 and t==1 and root==0
            bad=nb==root%2 if var==0 else (a+b+root)%3==0 if var==1 else nb==1
            g[node][a]={'post':(root,nb,t+1),'terminal':term,'outcome':('FAIL' if bad else 'SUCCESS') if term else None}
    return targets,nom,sites,g
def toy_enum(n,targets,nom,sites,g):
    out=[F() for _ in range(DEG+1)];count=0
    for values in product(*[(-1,)+targets[i] for i in range(n)]):
        j=sum(a!=-1 for a in values);weight=F(1)
        for i,a in enumerate(values):
            if a!=-1:weight/=len(targets[i])
        bad=False
        for root in range(4):
            node=(root,0,0);mf=False;seen=set()
            while True:
                s=sites[node];require(s not in seen,'toy repeated address');seen.add(s);a=values[s];mf|=a!=-1
                e=g[node][nom[node] if a==-1 else a]
                if e['terminal']:break
                node=e['post']
            bad|=mf and e['outcome']!='SUCCESS'
        if not bad:out[j]+=weight
        count+=1
    return tuple(out),count
def main():
    start=time.perf_counter();c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    toyrows=[];toycount=0
    for n in c['toys']['n_values']:
        for var in c['toys']['variants']:
            a,nm,ss,g=toy(n,var);expected,count=toy_enum(n,a,nm,ss,g)
            p,states,trans=joint([(r,0,0) for r in range(4)],n,a,nm,ss,g,c['resource_guard']['max_states_per_sector'])
            require(p==expected,'complete new shared4-root toy')
            rec={'n':n,'variant':var,'full_assignments':count,'no_trigger':pack(p),
                 'target_lists':[[i,list(a[i])] for i in a],
                 'sites':[[list(node),s] for node,s in ss.items()],
                 'graph':[[list(node),[[act,e] for act,e in acts.items()]] for node,acts in g.items()],
                 'backward_states':states,'transitions':trans}
            emit('NEW_JOINT_TOY',rec);toyrows.append(rec);toycount+=count
    jointtoy=multiply(tuple(F(n,d) for n,d in toyrows[0]['no_trigger']),
                      tuple(F(n,d) for n,d in toyrows[2]['no_trigger']))
    emit('NEW_TWO_SECTOR_TOY_PRODUCT',{'sectors':[[5,0],[5,2]],'degree0_to8_no_trigger':pack(jointtoy),'all10_variables_preserved':True})
    old={n:records(i) for n,i in c['stored'].items()}
    D=[o for t,o in old['catalog'] if t=='DECISION_CONTEXT'];X=[o for t,o in old['catalog'] if t=='CONTROLLER_SITE']
    R=[o for t,o in old['revision'] if t=='REVISED_SITE_NOT_ADOPTED']
    require(len(D)==13824 and len(X)==len(R)==5904,'full support')
    q={tuple(o['context']):{a:float.fromhex(h) for a,h in o['q_row_hex']} for o in D}
    nom={n:min(row,key=lambda a:(-row[a],a)) for n,row in q.items()};sites={n:n[:5]+(nom[n],) for n in q}
    graph=defaultdict(dict)
    for t,o in old['graph']:
        if t=='NATIVE_LEGAL_EDGE':graph[tuple(o['pre'])][o['command']]=o['result']
    require(len(graph)==6254 and sum(map(len,graph.values()))==20588,'full old legal graph')
    for n,acts in graph.items():
        for e in acts.values():require(e['post'][2]==n[2]+1 and tuple(e['post'][3:6])==n[3:6],'time and sector invariants')
    basis=next(o['entries'] for t,o in old['basis'] if t=='NATIVE_BASIS')
    consult=defaultdict(list)
    for i,b in enumerate(basis):
        n=(0,2,0,b['kappa'],b['phase'],b['committed'],0);raw=[]
        while True:
            a=nom[n];e=graph[n][a];consult[sites[n]].append(i)
            raw.append([list(n[:5]),n[5],n[6],a,a,a,e['reward_hex'],e['post'][:5],e['post'][5:],e['terminal'],e['outcome'],False])
            if e['terminal']:break
            n=tuple(e['post'])
        require(raw==b['payload']['trace'],'all old native basis rows')
    A=[{tuple(o['site']):tuple(o['alternatives']) for o in X if o['alternatives']},
       {tuple(o['site']):tuple(o['targets']) for o in R if o['targets']}]
    audits=[]
    for x,r in zip(X,R):
        site=tuple(x['site']);require(site==tuple(r['site']),'full site order')
        for gram in A:
            for a in gram.get(site,()):
                for z,m in r['domain_service']:require(a in q[site[:5]+(z,m)],'complete domain output admissibility')
        rec={'site':list(site),'old_targets':x['alternatives'],'revised_targets':r['targets'],
             'domain_service':r['domain_service'],'reachable_service':r['reachable_service'],
             'old_basis_consultations':consult.get(site,[])}
        emit('COMPLETE_SHARED_SITE',rec);audits.append(rec)
    sectorrows=[];cells=[];allstates=0;alltrans=0
    bounds={(o['grammar'],o['k']):o for t,o in old['marginals'] if t=='COMPLETE_CELL_UNION_BOUNDS'}
    for gi,grammar in enumerate(c['grammars']):
        targets=A[gi];M=len(targets);require(M==grammar['eligible_sites'],'full grammar support')
        syntax=[1]+[0]*DEG
        for al in targets.values():
            for j in range(DEG,0,-1):syntax[j]+=syntax[j-1]*len(al)
        total=tuple([F(1)]+[F()]*DEG);msum=0
        for kappa,phi in product(range(2),range(6)):
            part={s:a for s,a in targets.items() if s[3:5]==(kappa,phi)};msum+=len(part)
            roots=[(0,2,0,kappa,phi,z,0) for z in range(4)]
            p,s,tr=joint(roots,len(part),part,nom,sites,graph,c['resource_guard']['max_states_per_sector'])
            total=multiply(total,p);allstates+=s;alltrans+=tr
            rec={'grammar':grammar['name'],'sector':[kappa,phi],'sector_eligible_sites':len(part),
                 'roots':[list(n) for n in roots],'no_trigger_polynomial':pack(p),'backward_states':s,
                 'joint_branch_transitions':tr,'shared_assignment_all4_roots':True,'unread_full_pre_declarations_retained':True}
            emit('COMPLETE_SECTOR_JOINT_POLYNOMIAL',rec);sectorrows.append(rec)
        require(msum==M,'all disjoint full variable sectors')
        emit('COMPLETE_GLOBAL_NO_TRIGGER_POLYNOMIAL',{'grammar':grammar['name'],'M':M,'no_trigger':pack(total)})
        for k in c['k_values']:
            support=choose(M,k);z=1-total[k]/support;oldb=bounds[(grammar['name'],k)]
            lo,hi=F(*oldb['trigger_union_lower']),F(*oldb['trigger_union_upper'])
            require(lo<=z<=hi and (z==0 if k==1 else z>0),'prior complete bounds and zero cells')
            rec={'grammar':grammar['name'],'k':k,'shape':'no-shape','context_subsets':support,
                 'target_assigned_syntax_worlds':syntax[k],'exact_trigger_normalizer':pack([z])[0],
                 'no_trigger_mass':pack([1-z])[0],'old_bounds':[oldb['trigger_union_lower'],oldb['trigger_union_upper']],
                 'full_support_joint_normalizer_closed':True,'conditional_distribution_defined':z>0,
                 'scientific_grammar_measure_adopted':False,'statistical_N':None,'not_defect_times_scene_mass':True}
            emit('COMPLETE_EXACT_CELL_NORMALIZER',rec);cells.append(rec)
    after=bind(c);require(after==before,'runtime drift');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'COMPLETE_PURE_X_SHARED4_ROOT_SECTOR_JOINT_NORMALIZERS_NOT_SCIENCE',
       'all_inputs_equal':True,'full_D':13824,'full_X':5904,'joint_sector_polynomials':len(sectorrows),
       'backward_states':allstates,'joint_branch_transitions':alltrans,
       'sector_registry_sha256':sha256(canonical(sectorrows)).hexdigest(),
       'site_registry_sha256':sha256(canonical(audits)).hexdigest(),
       'toy_registry_sha256':sha256(canonical(toyrows)).hexdigest(),'toys':len(toyrows),'toy_full_assignments':toycount,
       'cells':cells,'elapsed_seconds':time.perf_counter()-start,'new_counting_DP':True,
       'new_reference_learner_DP':0,'new_native_kernel_steps':0,'new_native_learner_rollouts':0,'B1_arms':0,
       'keys_allocated':0,'random_draws':0,'future_training':0,'collector_executed':False,'sampler_executed':False,
       'scientific_PASS':False,'scientific_rules_adopted':False,'collection_authorized':False,
       'mechanism_direction_falsified':False,'research_complete':False,'mixed_or_joint_B2_totality_closed':False})
if __name__=='__main__':main()
