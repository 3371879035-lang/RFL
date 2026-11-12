"""Stdlib complete stored audit using legal equations and old native DAG, no candidate/RFL imports."""
from collections import Counter,deque
from fractions import Fraction
from hashlib import sha1,sha256
from pathlib import Path
import json,subprocess
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]


def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def read(p):return json.loads(p.read_bytes())
def require(ok,why):
    if not ok:raise AssertionError(why)
def frac(f):return [f.numerator,f.denominator]


def records(folder,digest=None):
    cl,ex=read(folder/'claim.json'),read(folder/'exit.json');require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items()),'complete receipt')
    for n,v in ex['files'].items():
        b=(folder/n).read_bytes();require({'bytes':len(b),'sha256':sha256(b).hexdigest()}==v,'raw capture')
    require(not (folder/'stderr.log').read_bytes(),'stderr')
    if digest:require(ex['files']['stdout.log']['sha256']==digest,'stored source changed')
    out=[]
    for line in (folder/'stdout.log').read_bytes().splitlines(keepends=True):
        require(line.endswith(b'\n'),'incomplete line');t,v=line.rstrip(b'\r\n').split(b'=',1);obj=json.loads(v)
        require(canonical(obj).rstrip(b'\n')==v,'canonical raw JSON');out.append((t.decode(),obj))
    return out,ex


def main():
    c=read(HERE/'contract.json');rows,ex=records(HERE/'evidence');singles={t:o for t,o in rows if t in ('INPUT_BINDING_BEFORE','INPUT_BINDING_AFTER','COMPLETE_MEASURE_BEFORE_NATIVE','FINAL')}
    before=singles['INPUT_BINDING_BEFORE'];require(before==singles['INPUT_BINDING_AFTER'],'input drift')
    for n,d in ex['inputs'].items():require(sha256((HERE/n).read_bytes()).hexdigest()==d,'capture input changed')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit']==before['parent_HEAD'],'parent')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources'];a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit'];native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')};bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound),len(before['input_sha256']))==(313,153,404,718,875),'full binding extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native|before['input_sha256']).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    old={name:records(PREP/s['folder'],s['stdout_sha256'])[0] for name,s in c['stored'].items() if isinstance(s,dict)}
    D=[o for t,o in old['catalog'] if t=='DECISION_CONTEXT'];X=[o for t,o in old['catalog'] if t=='CONTROLLER_SITE'];require((len(D),len(X))==(13824,5904),'all domain')
    q={tuple(r['context']):{a:float.fromhex(h) for a,h in r['q_row_hex']} for r in D}
    cells={(0,2),(4,2)}|{(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)}
    delta={0:(0,-1),1:(0,1),2:(-1,0),3:(1,0),4:(0,0)};dist={(4,2):0};queue=deque([(4,2)])
    while queue:
        cell=queue.popleft()
        for dx,dy in delta.values():
            nxt=(cell[0]+dx,cell[1]+dy)
            if nxt in cells and nxt not in dist:dist[nxt]=dist[cell]+1;queue.append(nxt)
    legal={}
    for r in D:
        x,y,t,k,phi,z,m=r['context'];acts=[]
        for action,(dx,dy) in delta.items():
            nxt=(x+dx,y+dy)
            if nxt not in cells:continue
            if z==0 and dist[nxt]!=dist[(x,y)]-1:continue
            if z in (1,3) and m==0 and nxt==(4,2):continue
            if z==2 and m==0 and nxt in ((2,2),(4,2)):continue
            acts.append(action)
        require(acts==list(q[tuple(r['context'])]),'independent full legal row');legal[tuple(r['context'])]=set(acts)
    graph={(tuple(e['pre']),e['command']):e['result'] for t,e in old['service'] if t=='NATIVE_LEGAL_EDGE'}
    require(len(graph)==20588,'bound complete old graph')
    for (node,act),res in graph.items():
        x,y,t,k,phi,z,m=node;require(act in legal[node],'graph legal');dx,dy=delta[act];nx,ny=x+dx,y+dy;nt=t+1
        outcome='COLLISION' if (nx,ny)==(2,2) and nt%(6,3)[k]==phi%(6,3)[k] else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
        nm=1 if m or (z==1 and (nx,ny)==(2,1)) or (z==3 and (nx,ny)==(2,4)) or (z==2 and (x,y)==(1,2) and t%(6,3)[k]!=phi%(6,3)[k]) else 0
        require(res=={'post':[nx,ny,nt,k,phi,z,nm],'a_cmd':act,'u':act,'a_realized':act,'reward_hex':(-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)).hex(),'terminal':outcome is not None,'outcome':outcome,'illegal':False},'independent old graph edge')
    reachable={tuple(n) for t,o in old['service'] if t=='ALL_REACHABLE_NODES' for n in o['nodes']}
    sites=[];targets_by={}
    for xr in X:
        site=tuple(xr['site']);contexts=[site[:5]+(z,m) for z in range(4) for m in range(2)];serving=[n for n in contexts if site[5] in legal[n]]
        require(serving,'union legal site empty');common=set.intersection(*(legal[n] for n in serving));targets=sorted(common-{site[5]})
        old_common=set.intersection(*(legal[n] for n in contexts));old_targets=sorted(old_common-{site[5]});require(old_targets==xr['alternatives'] and set(old_targets)<=set(targets),'old support subset')
        rs=[list(n[5:]) for n in serving if n in reachable];targets_by[site]=targets
        sites.append({'site':list(site),'domain_service':[list(n[5:]) for n in serving],'targets':targets,'old_targets':old_targets,
                      'reachable_service':rs,'status':'REACHABLE_SERVICE' if rs else 'NO_REACHABLE_SERVICE_NOT_DELETED',
                      'eligible':bool(targets),'candidate_site_mass':[1,4464] if targets else None})
    actual_sites=[o for t,o in rows if t=='REVISED_SITE_NOT_ADOPTED'];require(actual_sites==sites,'complete result-independent site syntax')
    require(sum(bool(s['targets']) for s in sites)==4464 and sum(len(s['targets']) for s in sites)==8928,'candidate support extent')
    bs=next(o['entries'] for t,o in old['basis'] if t=='NATIVE_BASIS');keys=[(b['kappa'],b['phase'],b['committed']) for b in bs];require(len(keys)==48,'basis extent')

    def replay(i,site=None,target=None):
        k,phi,z=keys[i];node=(0,2,0,k,phi,z,0);trace=[];gamma=[]
        while True:
            choices=q[node];maxv=max(choices.values());cmd=min(a for a,v in choices.items() if v==maxv);u=target if node[:5]+(cmd,)==site else cmd
            require(cmd in legal[node] and u in legal[node],'future serve output illegal');r=graph[(node,u)]
            if u!=cmd:gamma.append(f'ControllerSite_{node[0]}_{node[1]}_{node[2]}_{cmd}')
            trace.append({'pre_state':list(node[:5]),'z':node[5],'m':node[6],'a_cmd':cmd,'u':u,'a_realized':u,
                 'reward_hex':r['reward_hex'],'post_state':r['post'][:5],'post_control':r['post'][5:],'terminal':r['terminal'],'outcome':r['outcome'],'illegal':False})
            if r['terminal']:break
            node=tuple(r['post'])
        return {'trace':trace,'outcome':trace[-1]['outcome'],'return_hex':sum(float.fromhex(t['reward_hex']) for t in trace).hex(),'Gamma_P_star':gamma}

    consulted={};nominal=[]
    for i,b in enumerate(bs):
        payload=replay(i);nominal.append(payload);require(payload['outcome']==b['payload']['outcome'] and payload['return_hex']==b['payload']['return_hex'],'nominal ordered mean/return')
        require([list(r.values()) for r in payload['trace']]==b['payload']['trace'],'old raw basis replay')
        for r in payload['trace']:consulted.setdefault(tuple(r['pre_state']+[r['a_cmd']]),[]).append(i)
    expected=[]
    for s in sites:
        address=tuple(s['site']);indices=consulted.get(address,[]);require(len(indices)==len(set(indices)),'t recurrence')
        for target in s['targets']:
            preds=[[i,replay(i,address,target)] for i in indices];triggers=[i for i,p in preds if p['outcome']!='SUCCESS' and p['Gamma_P_star']]
            expected.append({'site':s['site'],'target':target,'target_count':len(s['targets']),'candidate_mass':frac(Fraction(1,4464*len(s['targets']))),
                  'old_mass':frac(Fraction(1,3312*len(s['old_targets']))) if target in s['old_targets'] else None,'consulted_basis':indices,
                  'trigger_basis':triggers,'trigger_scene_mass':frac(Fraction(len(triggers),48)),'consulted_predictions':preds})
    registry=[o for t,o in rows if t=='CONFIGURATION_PREDICTION'];require(registry==expected,'all predictions and rational masses')
    Z=sum((Fraction(*r['candidate_mass']) for r in expected if r['trigger_basis']),Fraction());J=sum((Fraction(*r['candidate_mass'])*Fraction(*r['trigger_scene_mass']) for r in expected),Fraction())
    measure={'candidate_total_mass':frac(sum((Fraction(*r['candidate_mass']) for r in expected),Fraction())),
        'old_support_total_old_mass':frac(sum((Fraction(*r['old_mass']) for r in expected if r['old_mass']),Fraction())),
        'old_support_total_under_candidate_mass':frac(sum((Fraction(*r['candidate_mass']) for r in expected if r['old_mass']),Fraction())),
        'triggerable_defect_mass':frac(Z),'nontrigger_defect_mass':frac(1-Z),'joint_defect_scene_failure_mass_NOT_normalizer':frac(J),
        'conditional_distribution_defined':Z>0,'triggerable_configurations':sum(bool(r['trigger_basis']) for r in expected)}
    require(singles['COMPLETE_MEASURE_BEFORE_NATIVE']['measure']==measure and singles['FINAL']['measure']==measure,'independent normalizer')
    old_actual={(tuple(o['address']),o['target'],o['basis_index']):o for t,o in old['old_actual'] if t=='ACTUAL_X_SINGLETON'};require(len(old_actual)==50,'old actual extent')
    new_rows=[o for t,o in rows if t=='ACTUAL_X_SINGLETON'];reuse=[o for t,o in rows if t=='OLD_NATIVE_PAIR_READ_ONLY'];raw=[o for t,o in rows if t=='RAW_NATIVE_FACTUAL_BEFORE_TRUTH']
    expected_new=[];expected_reuse=[];stats=Counter();outcomes=Counter();deltas=[]
    for rec in expected:
        for i,payload in rec['consulted_predictions']:
            site=tuple(rec['site']);target=rec['target'];identity=(site,target,i);fp=sha256(('\0\0X:'+','.join(map(str,site+(target,)))+'\0').encode()).hexdigest()
            if identity in old_actual:
                o=old_actual[identity];require(o['payload']==payload and o['fingerprint_pre']==o['fingerprint_after_read']==fp and o['all_store_sizes']==[0,0,1,0],'old exact native full pre')
                expected_reuse.append({'site':list(site),'target':target,'basis_index':i,'old_id':o['id'],'fingerprint':fp,'old_payload_sha256':sha256(canonical(payload)).hexdigest()});continue
            expected_new.append({'site':list(site),'target':target,'basis_index':i,'basis':list(keys[i]),'scene':[keys[i][0],keys[i][1],0,0,keys[i][2]],'all_store_sizes':[0,0,1,0],
                         'fingerprint_pre':fp,'fingerprint_after_read':fp,'payload':payload})
            diff=float.fromhex(payload['return_hex'])-float.fromhex(nominal[i]['return_hex']);deltas.append(diff);stats['negative' if diff<0 else 'positive' if diff>0 else 'zero']+=1;outcomes[payload['outcome']]+=1
    require(new_rows==expected_new and reuse==expected_reuse and len(reuse)==50,'all actual/reused cases with no omission/reordering')
    require(raw==[{'site':o['site'],'target':o['target'],'basis_index':o['basis_index'],'trace':o['payload']['trace'],'outcome':o['payload']['outcome'],'return_hex':o['payload']['return_hex']} for o in new_rows],'complete raw before truth')
    native_start=min(i for i,(t,o) in enumerate(rows) if t=='RAW_NATIVE_FACTUAL_BEFORE_TRUTH') if raw else len(rows)
    require(max(i for i,(t,o) in enumerate(rows) if t in ('REVISED_SITE_NOT_ADOPTED','CONFIGURATION_PREDICTION','COMPLETE_MEASURE_BEFORE_NATIVE'))<native_start,'prediction/measure after new native')
    raws=[i for i,(t,o) in enumerate(rows) if t=='RAW_NATIVE_FACTUAL_BEFORE_TRUTH'];acts=[i for i,(t,o) in enumerate(rows) if t=='ACTUAL_X_SINGLETON'];require(all(r<a for r,a in zip(raws,acts)),'truth before factual')
    f=singles['FINAL'];require(f['new_native_initial_X_rollouts']==len(new_rows) and f['new_native_raw_rows']==sum(len(o['payload']['trace']) for o in new_rows),'native counts')
    require(f['new_native_outcomes']==dict(outcomes) and f['new_return_changes_vs_nominal']==dict(stats),'signed adverse effects')
    for key,val in (('site_registry_sha256',sites),('prediction_registry_sha256',expected),('actual_registry_sha256',new_rows)):require(f[key]==sha256(canonical(val)).hexdigest(),'registry digest')
    require(Counter(t for t,o in rows)=={'INPUT_BINDING_BEFORE':1,'REVISED_SITE_NOT_ADOPTED':5904,'CONFIGURATION_PREDICTION':8928,'COMPLETE_MEASURE_BEFORE_NATIVE':1,
                'OLD_NATIVE_PAIR_READ_ONLY':50,'RAW_NATIVE_FACTUAL_BEFORE_TRUTH':len(new_rows),'ACTUAL_X_SINGLETON':len(new_rows),'INPUT_BINDING_AFTER':1,'FINAL':1},'all raw tags')
    print(json.dumps({'status':'COMPLETE_REVISED_X_SYNTAX_SINGLETON_STORED_CHECKED_NOT_SCIENCE','role':'PRIMARY_STDLIB_IMPLEMENTATION_INDEPENDENCE_NOT_EXPERT',
         'all_original_sites':5904,'all_original_decision_contexts':13824,'candidate_eligible_sites':4464,'all_candidate_configurations':8928,'old_configurations_retained':3600,
         'measure':measure,'consulted_pairs':sum(len(r['consulted_basis']) for r in expected),'old_native_pairs_read_only':50,'new_native_rollouts':len(new_rows),
         'new_native_raw_rows':sum(len(o['payload']['trace']) for o in new_rows),'new_native_outcomes':dict(outcomes),'new_return_changes':dict(stats),'min_new_return_delta':min(deltas) if deltas else None,
         'unreachable_original_sites_retained':sum(not s['reachable_service'] for s in sites),'bound_old_graph_edges':len(graph),'old_basis_raw_rows':sum(len(b['payload']['trace']) for b in bs),
         'sources':313,'old_native':153,'prior_preparation':404,'parent_HEAD_byte_bindings':718,'runtime_inputs':875,
         'no_RFL_candidate_predictor_old_checker_or_solver_execution':True,'scientific_rules_adopted':False,'candidate_measure_differs_from_old':True,
         'multi_or_mixed_totality':False,'B1_arms':0,'future_training':0,'keys_allocated':0,'scientific_PASS':False,'collection_authorized':False,'independent_expert':False},sort_keys=True))


if __name__=='__main__':main()
