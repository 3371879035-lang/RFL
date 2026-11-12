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
    require((len(source),len(native),len(prior),len(bound))==(313,153,479,793),'parent extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (source|native).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==950,'runtime extent')
    return {'parent_HEAD':h,'HEAD_byte_bindings':793,'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}
def marginal(root,M,targets,nominal,sites,edges):
    @lru_cache(None)
    def walk(node,v,mf):
        site=sites[node];al=targets.get(site,());nv=v+bool(al);require(nv<=M,'repeated site')
        def child(a,flag):
            e=edges[node][a]
            if e['terminal']:
                accept=e['outcome']!='SUCCESS' and flag
                return tuple(F(choose(M-nv,j)) if accept else F() for j in range(DEG+1))
            return walk(tuple(e['post']),nv,flag)
        out=list(child(nominal[node],mf))
        for a in al:
            tail=child(a,True)
            for j in range(1,DEG+1):out[j]+=tail[j-1]/len(al)
        return tuple(out)
    p=walk(root,0,False);require(all(0<=p[k]<=choose(M,k) for k in range(DEG+1)),'marginal support')
    return p,walk.cache_info().currsize
def toy(n,variant):
    al={i:list(range(1,2+(i+variant)%3)) for i in range(n)};nom={};sites={};g={}
    for root in range(2):
        for t in range(3):
            for b in range(2):
                node=(root,t,b);nom[node]=0;sites[node]=0 if t==0 else 1+b if t==1 else 3;g[node]={}
                for a in [0]+al[sites[node]]:
                    nb=(b+a)%2;term=t==2
                    fail=(a>0 and root==0) if variant==0 else nb==root if variant==1 else a>0 and (a+b+root)%2==0 if variant==2 else nb==1
                    g[node][a]={'post':(root,t+1,nb),'terminal':term,'outcome':('FAIL' if fail else 'SUCCESS') if term else None}
    return al,nom,sites,g
def toy_enum(n,al,sites,g):
    marg=[[F() for _ in range(DEG+1)] for _ in range(2)];union=[F() for _ in range(DEG+1)];count=0
    for values in product(*[[-1]+al[i] for i in range(n)]):
        k=sum(v!=-1 for v in values);w=F(1)
        for i,v in enumerate(values):
            if v!=-1:w/=len(al[i])
        flags=[]
        for root in range(2):
            node=(root,0,0);mf=False;seen=set()
            while True:
                site=sites[node];require(site not in seen,'toy repeated read');seen.add(site)
                a=values[site];mf|=a!=-1;e=g[node][0 if a==-1 else a]
                if e['terminal']:break
                node=e['post']
            flags.append(mf and e['outcome']!='SUCCESS')
            if flags[-1]:marg[root][k]+=w
        if any(flags):union[k]+=w
        count+=1
    return marg,union,count
def main():
    start=time.perf_counter();c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    toys=[];toyworlds=0
    for n in c['toys']['n_values']:
        for variant in c['toys']['variants']:
            al,nom,sites,g=toy(n,variant);oracle,u,count=toy_enum(n,al,sites,g);ps=[]
            for root in range(2):
                p,states=marginal((root,0,0),n,al,nom,sites,g);require(list(p)==oracle[root],'new full shared toy')
                ps.append(p)
            for k in range(min(n,DEG)+1):require(max(p[k] for p in ps)<=u[k]<=min(F(choose(n,k)),sum(p[k] for p in ps)),'toy union bound')
            rec={'n':n,'variant':variant,'target_lists':[[i,al[i]] for i in al],
                 'sites':[[list(a),v] for a,v in sites.items()],
                 'graph':[[list(a),[[v,e] for v,e in acts.items()]] for a,acts in g.items()],
                 'marginals':[pack(p) for p in ps],'exact_shared_world_union':pack(u),'full_assignments':count}
            emit('SHARED_TOY_FULL_ENUMERATION',rec);toys.append(rec);toyworlds+=count
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
    allrows=[];cells=[];states=0
    for gi,grammar in enumerate(c['grammars']):
        targets=A[gi];M=len(targets);require(M==grammar['eligible_sites'] and sum(map(len,targets.values()))==grammar['target_assignments_singleton'],'all grammar support')
        syntax=[1]+[0]*DEG
        for al in targets.values():
            for k in range(DEG,0,-1):syntax[k]+=syntax[k-1]*len(al)
        ps=[]
        for i,b in enumerate(basis):
            root=(0,2,0,b['kappa'],b['phase'],b['committed'],0)
            p,s=marginal(root,M,targets,nom,sites,graph);states+=s;ps.append(p)
            rec={'grammar':grammar['name'],'basis_index':i,'basis':[b['kappa'],b['phase'],b['committed']],
                 'eligible_sites_global':M,'failure_manifestation_weight':pack(p),'backward_states':s,
                 'full_world_unread_declarations_retained':True}
            emit('COMPLETE_MARGINAL_POLYNOMIAL',rec);allrows.append(rec)
        for k in c['k_values']:
            support=choose(M,k);ms=[p[k]/support for p in ps];lo=max(ms);hi=min(F(1),sum(ms,F()))
            rec={'grammar':grammar['name'],'k':k,'shape':'no-shape','context_subsets':support,
                 'target_assigned_syntax_worlds':syntax[k],'marginal_masses':pack(ms),
                 'trigger_union_lower':pack([lo])[0],'trigger_union_upper':pack([hi])[0],
                 'exact_trigger_normalizer':pack([lo])[0] if lo==hi else None,
                 'conditional_distribution_proved_defined':lo>0,'conditional_distribution_proved_undefined':hi==0,
                 'joint_normalizer_closed':lo==hi,'not_defect_times_scene_mass':True,
                 'scientific_grammar_measure_adopted':False,'statistical_N':None}
            emit('COMPLETE_CELL_UNION_BOUNDS',rec);cells.append(rec)
    after=bind(c);require(after==before,'runtime drift');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'COMPLETE_PURE_X_MARGINAL_POLYNOMIALS_SAFE_SHARED_WORLD_BOUNDS_NOT_SCIENCE',
         'all_inputs_equal':True,'full_D':13824,'full_X':5904,'marginals':len(allrows),'backward_states':states,
         'marginal_registry_sha256':sha256(canonical(allrows)).hexdigest(),'site_registry_sha256':sha256(canonical(audits)).hexdigest(),
         'toy_registry_sha256':sha256(canonical(toys)).hexdigest(),'toys':len(toys),'toy_full_assignments':toyworlds,
         'shared_old_nominal_read_sites':sum(len(set(i//4 for i in a['old_basis_consultations']))==1 and len(set(a['old_basis_consultations']))>1 for a in audits),
         'shared_eligible_nominal_sites_old':sum(bool(a['old_targets']) and len(set(a['old_basis_consultations']))>1 for a in audits),
         'shared_eligible_nominal_sites_revised':sum(bool(a['revised_targets']) and len(set(a['old_basis_consultations']))>1 for a in audits),
         'cells':cells,'elapsed_seconds':time.perf_counter()-start,'new_counting_DP':True,
         'new_reference_learner_DP':0,'new_native_kernel_steps':0,'new_native_learner_rollouts':0,'B1_arms':0,
         'keys_allocated':0,'random_draws':0,'future_training':0,'collector_executed':False,
         'scientific_PASS':False,'scientific_rules_adopted':False,'collection_authorized':False,
         'mechanism_direction_falsified':False,'research_complete':False,'mixed_or_joint_B2_totality_closed':False})
if __name__=='__main__':main()

