"""Independent stdlib graph closure and service audit; no RFL/candidate imports."""
from collections import Counter,deque
from hashlib import sha1,sha256
from pathlib import Path
import json,subprocess
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]


def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def read(p):return json.loads(p.read_bytes())
def require(ok,why):
    if not ok:raise AssertionError(why)


def records(folder,strict=False):
    c,e=read(folder/'claim.json'),read(folder/'exit.json');require(e['native_child_exit_code']==0 and all(e[k]==v for k,v in c.items()),'native receipt')
    for n,v in e['files'].items():
        b=(folder/n).read_bytes();require(len(b)==v['bytes'] and sha256(b).hexdigest()==v['sha256'],'raw evidence')
    require(not (folder/'stderr.log').read_bytes(),'stderr')
    result=[]
    for line in (folder/'stdout.log').read_bytes().splitlines(keepends=True):
        require(line.endswith(b'\n'),'incomplete raw line');t,v=line.rstrip(b'\r\n').split(b'=',1);o=json.loads(v)
        if strict:require(canonical(o).rstrip(b'\n')==v,'noncanonical JSON')
        result.append((t.decode(),o))
    return result,e


def main():
    c=read(HERE/'contract.json');rows,receipt=records(HERE/'evidence',True)
    for n,d in receipt['inputs'].items():require(sha256((HERE/n).read_bytes()).hexdigest()==d,'capture input')
    scalar={t:o for t,o in rows if t!='NATIVE_LEGAL_EDGE' and t!='COMPLETE_SITE_SERVICE'}
    before=scalar['INPUT_BINDING_BEFORE'];require(before==scalar['INPUT_BINDING_AFTER'],'input drift')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit']==before['parent_HEAD'],'parent')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources'];a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit'];native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')};bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound),len(before['input_sha256']))==(313,153,389,703,860),'binding extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native|before['input_sha256']).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    cat,oldreceipt=records(PREP/c['stored_catalog']['folder']);require(oldreceipt['files']['stdout.log']['sha256']==c['stored_catalog']['stdout_sha256'],'catalog digest')
    D=[o for t,o in cat if t=='DECISION_CONTEXT'];X=[o for t,o in cat if t=='CONTROLLER_SITE'];require((len(D),len(X))==(13824,5904),'whole catalog')
    cells={(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)}|{(0,2),(4,2)}
    delta={0:(0,-1),1:(0,1),2:(-1,0),3:(1,0),4:(0,0)};distance={(4,2):0};q=deque([(4,2)])
    while q:
        cell=q.popleft()
        for dx,dy in delta.values():
            nxt=(cell[0]+dx,cell[1]+dy)
            if nxt in cells and nxt not in distance:distance[nxt]=distance[cell]+1;q.append(nxt)
    legal={}
    for r in D:
        x,y,t,k,phi,z,m=r['context'];acts=[]
        for cmd,(dx,dy) in delta.items():
            nxt=(x+dx,y+dy)
            if nxt not in cells:continue
            if z==0 and distance[nxt]!=distance[(x,y)]-1:continue
            if z in (1,3) and m==0 and nxt==(4,2):continue
            if z==2 and m==0 and nxt in ((2,2),(4,2)):continue
            acts.append(cmd)
        require(acts==[a for a,h in r['q_row_hex']],'independent option/legal equation');legal[tuple(r['context'])]=set(acts)
    roots=[(0,2,0,k,phi,z,0) for k in range(2) for phi in range(6) for z in range(4)]
    require(scalar['ROOTS']['roots']==[list(r) for r in roots],'roots')
    graph={(tuple(e['pre']),e['command']):e for t,e in rows if t=='NATIVE_LEGAL_EDGE'};edges=[e for t,e in rows if t=='NATIVE_LEGAL_EDGE'];require(len(graph)==len(edges),'duplicate edge')
    visited=set(roots);queue=deque(roots);expected_edges=set();paths={r:[] for r in roots}
    while queue:
        node=queue.popleft();x,y,t,k,phi,z,m=node;period=(6,3)[k]
        for cmd in sorted(legal[node]):
            key=(node,cmd);expected_edges.add(key);require(key in graph,'missing legal branch');e=graph[key];r=e['result']
            dx,dy=delta[cmd];nx,ny=x+dx,y+dy;nt=t+1
            outcome='COLLISION' if (nx,ny)==(2,2) and nt%period==phi%period else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
            nm=1 if m or (z==1 and (nx,ny)==(2,1)) or (z==3 and (nx,ny)==(2,4)) or (z==2 and (x,y)==(1,2) and t%period!=phi%period) else 0
            nxt=(nx,ny,nt,k,phi,z,nm);reward=-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)
            expected={'post':list(nxt),'a_cmd':cmd,'u':cmd,'a_realized':cmd,'reward_hex':reward.hex(),'terminal':outcome is not None,'outcome':outcome,'illegal':False}
            require(r==expected,'complete native transition differs')
            if outcome is None and nxt not in visited:visited.add(nxt);paths[nxt]=paths[node]+[cmd];queue.append(nxt)
    require(set(graph)==expected_edges,'extra unreachable/terminal-expanded edges')
    nodes=sorted(visited);require(scalar['ALL_REACHABLE_NODES']['nodes']==[list(n) for n in nodes],'complete reachability closure')
    service=[o for t,o in rows if t=='COMPLETE_SITE_SERVICE'];require(len(service)==len(X),'full site extent');stats=Counter()
    for old,row in zip(X,service):
        site=tuple(old['site']);allctx=[site[:5]+(z,m) for z in range(4) for m in range(2)]
        ds=[n[5:] for n in allctx if site[5] in legal[n]];rs=[zm for zm in ds if site[:5]+zm in visited]
        all8=set.intersection(*(legal[n] for n in allctx));dc=sorted(set.intersection(*(legal[site[:5]+zm] for zm in ds)))
        rc=sorted(set.intersection(*(legal[site[:5]+zm] for zm in rs))) if rs else None
        da=[a for a in dc if a!=site[5]];ra=None if rc is None else [a for a in rc if a!=site[5]]
        require(sorted(all8)==old['all8_common_legal'] and [a for a in sorted(all8) if a!=site[5]]==old['alternatives'],'old all8 grammar')
        expected={'site':list(site),'old_all8_common':old['all8_common_legal'],'old_alternatives':old['alternatives'],
                  'domain_service':[list(zm) for zm in ds],'reachable_service':[list(zm) for zm in rs],
                  'domain_command_common':dc,'reachable_command_common':rc,'domain_alternatives':da,'reachable_alternatives':ra,
                  'status':'REACHABLE_SERVICE' if rs else 'NO_REACHABLE_SERVICE_NOT_DELETED','old_nominal_consulted':old['nominal_basis_consulted']}
        require(row==expected,'whole service intersection differs')
        stats['sites']+=1;stats['old_eligible_sites']+=bool(old['alternatives']);stats['domain_alternative_sites']+=bool(da)
        stats['reachable_sites']+=bool(rs);stats['unreachable_sites_retained']+=not rs;stats['reachable_alternative_sites']+=bool(ra)
        stats['old_assigned_targets']+=len(old['alternatives']);stats['domain_assigned_targets']+=len(da);stats['reachable_assigned_targets']+=len(ra or [])
        stats['old_eligible_but_unreachable']+=bool(old['alternatives']) and not rs
        stats['reachable_new_alternatives_vs_all8']+=len(set(ra or [])-set(old['alternatives']))
    w=c['fixed_counterexample'];node=tuple(w['site'][:5]+[w['serving_option'],w['serving_m']]);p=scalar['FIXED_ADMISSIBILITY_COUNTEREXAMPLE_BEFORE_NATIVE'];rejected=scalar['NATIVE_ADMISSIBILITY_REJECTION']
    require(node in visited and paths[node]==w['prefix_commands'] and w['site'][5] in legal[node] and w['target'] not in legal[node],'independent fixed witness')
    require(p=={'site':w['site'],'target':w['target'],'serving_context':list(node),'root':w['root'],'prefix_commands':paths[node],
                'serving_legal_actions':sorted(legal[node]),'expected_exception':'LearnerContractViolation'},'witness payload')
    require(rejected['witness']==p and rejected['exception']=='LearnerContractViolation' and 'wait_then_cross' in rejected['message'],'native rejection')
    require(next(i for i,(t,o) in enumerate(rows) if t=='FIXED_ADMISSIBILITY_COUNTEREXAMPLE_BEFORE_NATIVE')<next(i for i,(t,o) in enumerate(rows) if t=='NATIVE_ADMISSIBILITY_REJECTION'),'witness prediction order')
    f=scalar['FINAL'];require(f['new_native_identity_kernel_steps']==len(edges) and f['reachable_decision_contexts']==len(nodes) and f['unreachable_decision_contexts_retained']==13824-len(nodes),'graph counts')
    require(f['site_comparison_counts_NOT_adopted_grammar']==dict(stats),'site counts')
    require(f['terminal_edges']==dict(Counter(e['result']['outcome'] for e in edges if e['result']['terminal'])),'terminal counts')
    for key,registry in (('node_registry_sha256',[list(n) for n in nodes]),('edge_registry_sha256',edges),('site_registry_sha256',service)):
        require(f[key]==sha256(canonical(registry)).hexdigest(),'registry hash')
    require(Counter(t for t,o in rows)=={'INPUT_BINDING_BEFORE':1,'ROOTS':1,'NATIVE_LEGAL_EDGE':len(edges),'ALL_REACHABLE_NODES':1,
       'COMPLETE_SITE_SERVICE':5904,'FIXED_ADMISSIBILITY_COUNTEREXAMPLE_BEFORE_NATIVE':1,'NATIVE_ADMISSIBILITY_REJECTION':1,'INPUT_BINDING_AFTER':1,'FINAL':1},'all current raw tags')
    print(json.dumps({'status':'COMPLETE_STORED_LEGAL_GRAPH_AND_SERVICE_CHECKED_NOT_SCIENCE','role':'PRIMARY_STDLIB_IMPLEMENTATION_INDEPENDENCE_NOT_EXPERT',
       'roots':48,'all_original_decision_contexts':13824,'reachable_decision_contexts':len(nodes),'native_identity_kernel_steps':len(edges),
       'native_rejected_controller_steps':1,'all_original_controller_sites':5904,'site_comparison_counts_NOT_adopted_grammar':dict(stats),
       'runtime_inputs_checked':860,'parent_HEAD_byte_bindings':703,'source_count':313,'old_native_count':153,'prior_preparation_count':389,
       'no_RFL_candidate_old_checker_or_solver_execution':True,'keyed_probability_proved':False,'learner_rollouts':0,'B1_arms':0,'future_training':0,
       'keys_allocated':0,'scientific_rules_adopted':False,'population_reduced':False,'scientific_PASS':False,'mechanism_direction_falsified':False,
       'collection_authorized':False,'independent_expert':False},sort_keys=True))


if __name__=='__main__':main()
