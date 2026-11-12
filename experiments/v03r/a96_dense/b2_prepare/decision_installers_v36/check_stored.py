"""Independent stdlib full content audit: no RFL, candidate, predictor or old checker."""
from collections import Counter,deque
from fractions import Fraction
from hashlib import sha1,sha256
from pathlib import Path
import json,subprocess
HERE=Path(__file__).resolve().parent; PREP=HERE.parent; ROOT=HERE.parents[4]
def canonical(o): return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def read(p): return json.loads(p.read_bytes())
def require(ok,why):
    if not ok: raise AssertionError(why)
def frac(f): return [f.numerator,f.denominator]

def records(folder,expected=None,strict=False):
    cl,ex=read(folder/'claim.json'),read(folder/'exit.json')
    require(ex['native_child_exit_code']==(expected['exit'] if expected else 0) and all(ex[k]==v for k,v in cl.items()),'stored native receipt')
    for n,v in ex['files'].items():
        b=(folder/n).read_bytes(); require({'bytes':len(b),'sha256':sha256(b).hexdigest()}==v,'complete raw byte binding')
    if expected:
        require(ex['files']['stdout.log']['sha256']==expected['stdout_sha256'],'stored stdout')
        if expected['exit']: require(ex['files']['stderr.log']['sha256']==expected['stderr_sha256'],'old failure preserved')
        else: require(not (folder/'stderr.log').read_bytes(),'old stderr')
    else: require(not (folder/'stderr.log').read_bytes(),'new stderr')
    out=[]
    for line in (folder/'stdout.log').read_bytes().splitlines(keepends=True):
        require(line.endswith(b'\n'),'incomplete raw line')
        if b'=' not in line:
            require(not strict,'untagged new raw line'); continue
        t,v=line.rstrip(b'\r\n').split(b'=',1)
        if v[:1] not in (b'[',b'{'):
            require(not strict,'invalid new JSON'); continue
        obj=json.loads(v)
        if strict: require(canonical(obj).rstrip(b'\n')==v,'noncanonical new raw JSON')
        out.append((t.decode(),obj))
    return out,ex

def main():
    c=read(HERE/'contract.json'); rows,ex=records(HERE/'evidence',strict=True)
    singles={t:o for t,o in rows if t in ('INPUT_BINDING_BEFORE','INPUT_BINDING_AFTER','COMPLETE_MEASURE_BEFORE_NATIVE','FINAL')}
    before=singles['INPUT_BINDING_BEFORE']; require(before==singles['INPUT_BINDING_AFTER'],'input drift')
    for n,d in ex['inputs'].items(): require(sha256((HERE/n).read_bytes()).hexdigest()==d,'capture input')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(); require(head==before['parent_HEAD']==c['parent_commit'],'parent HEAD')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound),len(before['input_sha256']))==(313,153,419,733,890),'complete input extent')
    for p in bound:
        b=(ROOT/p).read_bytes(); require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native|before['input_sha256']).items(): require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    old={name:records(PREP/info['folder'],info)[0] for name,info in c['stored'].items()}
    D=[o for t,o in old['catalog'] if t=='DECISION_CONTEXT']; X=[o for t,o in old['catalog'] if t=='CONTROLLER_SITE']
    require((len(D),len(X))==(13824,5904),'full original domain retained')
    q={tuple(r['context']):{a:float.fromhex(h) for a,h in r['q_row_hex']} for r in D}
    require(len(q)==13824,'all unique D rows')
    cells={(0,2),(4,2)}|{(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)}
    delta={0:(0,-1),1:(0,1),2:(-1,0),3:(1,0),4:(0,0)}
    dist={(4,2):0}; queue=deque([(4,2)])
    while queue:
        cell=queue.popleft()
        for dx,dy in delta.values():
            nxt=(cell[0]+dx,cell[1]+dy)
            if nxt in cells and nxt not in dist: dist[nxt]=dist[cell]+1; queue.append(nxt)
    legal={}
    for r in D:
        x,y,t,k,phi,z,m=r['context']; acts=[]
        for act,(dx,dy) in delta.items():
            nxt=(x+dx,y+dy)
            if nxt not in cells: continue
            if z==0 and dist[nxt]!=dist[(x,y)]-1: continue
            if z in (1,3) and m==0 and nxt==(4,2): continue
            if z==2 and m==0 and nxt in ((2,2),(4,2)): continue
            acts.append(act)
        require(acts==list(q[tuple(r['context'])]),'full legal row')
        best=max(q[tuple(r['context'])].values()); optimal=[a for a,v in q[tuple(r['context'])].items() if v>=best-1e-12]
        require(r['optimal_actions']==optimal and r['alternatives']==[a for a in acts if a not in optimal],'complete nonoptimal targets')
        legal[tuple(r['context'])]=set(acts)
    graph={(tuple(e['pre']),e['command']):e['result'] for t,e in old['legal_graph'] if t=='NATIVE_LEGAL_EDGE'}
    require(len(graph)==20588,'complete graph')
    for (node,act),res in graph.items():
        x,y,t,k,phi,z,m=node; require(act in legal[node],'old graph legal')
        dx,dy=delta[act]; nx,ny=x+dx,y+dy; nt=t+1
        outcome='COLLISION' if (nx,ny)==(2,2) and nt%(6,3)[k]==phi%(6,3)[k] else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
        nm=1 if m or (z==1 and (nx,ny)==(2,1)) or (z==3 and (nx,ny)==(2,4)) or (z==2 and (x,y)==(1,2) and t%(6,3)[k]!=phi%(6,3)[k]) else 0
        require(res=={'post':[nx,ny,nt,k,phi,z,nm],'a_cmd':act,'u':act,'a_realized':act,
                     'reward_hex':(-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)).hex(),
                     'terminal':outcome is not None,'outcome':outcome,'illegal':False},'independent move terminal automaton reward')
    reachable={(0,2,0,k,p,z,0) for k in range(2) for p in range(6) for z in range(4)}; queue=deque(reachable)
    while queue:
        node=queue.popleft()
        for act in legal[node]:
            require((node,act) in graph,'missing legal history edge')
            res=graph[(node,act)]
            if not res['terminal'] and tuple(res['post']) not in reachable:
                reachable.add(tuple(res['post'])); queue.append(tuple(res['post']))
    require({n for n,a in graph}==reachable and len(reachable)==6254,'complete reachable graph closure')
    bs=next(o['entries'] for t,o in old['basis'] if t=='NATIVE_BASIS'); keys=[(b['kappa'],b['phase'],b['committed']) for b in bs]
    require(len(keys)==len(set(keys))==48,'old full basis')
    def replay(i,arch=None,address=None,target=None):
        k,phi,z=keys[i]; node=(0,2,0,k,phi,z,0); trace=[]; gamma=[]
        while True:
            row=q[node]; best=max(row.values()); cmd=min(a for a,v in row.items() if v==best)
            if arch=='D' and list(node)==address: cmd=target
            u=target if arch=='X' and list(node[:5]) + [cmd]==address else cmd
            require(cmd in legal[node] and u in legal[node],'sole edit legality')
            res=graph[(node,u)]
            if cmd not in [a for a,v in row.items() if v>=best-1e-12]: gamma.append('Decision_'+str(node[2]))
            if u!=cmd: gamma.append('ControllerSite_'+'_'.join(map(str,node[:3]+(cmd,))))
            trace.append({'pre_state':list(node[:5]),'z':node[5],'m':node[6],'a_cmd':cmd,'u':u,'a_realized':u,
                'reward_hex':res['reward_hex'],'post_state':res['post'][:5],'post_control':res['post'][5:],
                'terminal':res['terminal'],'outcome':res['outcome'],'illegal':False})
            if res['terminal']: break
            node=tuple(res['post'])
        return {'trace':trace,'outcome':trace[-1]['outcome'],'return_hex':sum(float.fromhex(t['reward_hex']) for t in trace).hex(),'Gamma_P_star':gamma}
    nominal=[]
    for i,b in enumerate(bs):
        p=replay(i); nominal.append(p)
        require(p['outcome']==b['payload']['outcome'] and p['return_hex']==b['payload']['return_hex'] and [list(r.values()) for r in p['trace']]==b['payload']['trace'],'complete old basis raw trace')
    complete=[o for t,o in old['prediction'] if t=='CONFIGURATION_PREDICTION']; expected_all=[]
    for arch,catalog,field in (('D',D,'context'),('X',X,'site')):
        eligible=[r for r in catalog if r['alternatives']]
        for pos,r in enumerate(eligible):
            address=r[field]
            visits=[i for i,p in enumerate(nominal) if any(t['pre_state']+([t['z'],t['m']] if arch=='D' else [t['a_cmd']])==address for t in p['trace'])]
            require(bool(visits)==r['nominal_basis_consulted'],'consulted domain metadata')
            for target in r['alternatives']:
                preds=[[i,replay(i,arch,address,target)] for i in visits]
                triggers=[i for i,p in preds if p['outcome']!='SUCCESS' and p['Gamma_P_star']]
                expected_all.append({'id':f'{arch}:{pos}:{target}','architecture':arch,'eligible_position':pos,'address':address,'target':target,
                    'alternatives':len(r['alternatives']),'original_mass':frac(Fraction(1,len(eligible)*len(r['alternatives']))),
                    'consulted_basis':visits,'trigger_basis':triggers,'trigger_scene_mass':frac(Fraction(len(triggers),48)),'consulted_predictions':preds})
    require(complete==expected_all and len(complete)==19964,'old full prediction registry including X preserved')
    registry=[r for r in complete if r['architecture']=='D']
    require([o for t,o in rows if t=='CONFIGURATION_PREDICTION_READ_ONLY']==registry,'D registry complete order')
    Z=sum((Fraction(*r['original_mass']) for r in registry if r['trigger_basis']),Fraction())
    J=sum((Fraction(*r['original_mass'])*Fraction(*r['trigger_scene_mass']) for r in registry),Fraction())
    measure={'original_mass_sum':frac(sum((Fraction(*r['original_mass']) for r in registry),Fraction())),
             'triggerable_defect_mass':frac(Z),'nontrigger_mass':frac(1-Z),'joint_defect_scene_failure_mass_NOT_normalizer':frac(J),
             'conditional_configuration_mass_sum':frac(sum((Fraction(*r['original_mass'])/Z for r in registry if r['trigger_basis']),Fraction()))}
    require(Z==Fraction(85,90612) and J==Fraction(85,4349376) and measure==singles['COMPLETE_MEASURE_BEFORE_NATIVE']['measure']==singles['FINAL']['measure'],'independent exact normalizers')
    oldpatch=next(o for t,os in old['patch_anchor'] if t=='COMPLETE_ARCHITECTURES' for o in os if o['architecture']=='D_patch')
    def fulltruth(p):
        timesteps=[]; baserows=[]
        for r in p['trace']:
            row=q[tuple(r['pre_state']+[r['z'],r['m']])]; b=max(row.values())
            optimal=[a for a,v in row.items() if v>=b-1e-12]
            if r['a_cmd'] not in optimal: timesteps.append(r['pre_state'][2])
            baserows.append({'pre_state':r['pre_state'],'z':r['z'],'m':r['m'],'a_learner':r['a_cmd'],'u_learner':r['u'],'optimal_actions':optimal})
        return {'truth_source':'A75_LEARNER_BASELINE_MANIFESTATIONS_NOT_R_MECH','J_L':[False,bool(timesteps),False],
             'manifested_process_proposals':[],'manifested_decision_timesteps':timesteps,'manifested_controller_sites':[],
             'Gamma_P_star':['Decision_'+str(t) for t in timesteps],'Gamma_T_star':None,'R_mech':None,
             'whole_optimal_set_tolerance':1e-12,'source_separated_baseline_rows':baserows}
    expected=[]; expected_raw=[]; changes=Counter(); outcomes=Counter(); deltas=[]; reused=0
    for r in registry:
        for arch in ('D_Q','D_patch'):
            address=r['address']; target=r['target']; value=None; parts=['','','','']
            if arch=='D_Q':
                row=q[tuple(address)]; b=max(row.values()); value=b+(b-row[target]); require(value>b,'fixed scalar dominance')
                parts[3]='Q:'+','.join(map(str,address+[target]))+'|'+value.hex()
            else: parts[0]='D:'+','.join(map(str,address+[target]))
            fp=sha256('\0'.join(parts).encode()).hexdigest()
            for i,p in r['consulted_predictions']:
                anchor=c['old_patch_anchor']; is_old=arch=='D_patch' and address==anchor['context'] and target==anchor['target'] and list(keys[i])==anchor['basis']
                truth=fulltruth(p)
                if is_old:
                    audit=oldpatch['original_owned_audit']
                    require(fp==oldpatch['source_fingerprint']==audit['fingerprint_pre']==audit['fingerprint_post'] and p['trace']==audit['raw_trace'] and truth==audit['truth'],'complete old exact reuse')
                    reused+=1
                else: expected_raw.append({'id':r['id'],'architecture':arch,'basis_index':i,'trace':p['trace'],'outcome':p['outcome'],'return_hex':p['return_hex']})
                expected.append({'id':r['id'],'architecture':arch,'basis_index':i,'basis':list(keys[i]),'scene':[keys[i][0],keys[i][1],0,0,keys[i][2]],
                    'source':'READ_ONLY_EXACT_v25_FACTUAL' if is_old else 'NEW_NATIVE_SINGLETON_FACTUAL',
                    'DQ_promoted_value_hex':None if value is None else value.hex(),'all_store_sizes':[0,0,0,1] if arch=='D_Q' else [1,0,0,0],
                    'fingerprint_pre':fp,'fingerprint_after_read':fp,'payload':p,'full_original_truth':truth})
                diff=float.fromhex(p['return_hex'])-float.fromhex(nominal[i]['return_hex'])
                deltas.append(diff); outcomes[arch+':'+p['outcome']]+=1
                changes[arch+':'+('negative' if diff<0 else 'positive' if diff>0 else 'zero')]+=1
    actual=[o for t,o in rows if t=='ACTUAL_FACTUAL']; raw=[o for t,o in rows if t=='RAW_NATIVE_FACTUAL_BEFORE_TRUTH']
    require(actual==expected and raw==expected_raw and len(actual)==1172 and len(raw)==1171 and reused==1,'complete native cases order no omission')
    pred_end=max(i for i,(t,o) in enumerate(rows) if t in ('CONFIGURATION_PREDICTION_READ_ONLY','COMPLETE_MEASURE_BEFORE_NATIVE'))
    require(pred_end<min(i for i,(t,o) in enumerate(rows) if t in ('ACTUAL_FACTUAL','RAW_NATIVE_FACTUAL_BEFORE_TRUTH')),'all forecasts before native')
    rawpos={(o['id'],o['architecture'],o['basis_index']):i for i,(t,o) in enumerate(rows) if t=='RAW_NATIVE_FACTUAL_BEFORE_TRUTH'}
    for i,(t,o) in enumerate(rows):
        if t=='ACTUAL_FACTUAL' and o['source']=='NEW_NATIVE_SINGLETON_FACTUAL':
            require(rawpos[(o['id'],o['architecture'],o['basis_index'])]<i,'raw after truth')
    f=singles['FINAL']; rawcount=sum(len(o['trace']) for o in raw)
    require(f['outcomes']==dict(outcomes) and f['signed_return_changes_vs_nominal']==dict(changes) and f['min_return_delta']==min(deltas) and f['max_return_delta']==max(deltas),'all signed adverse/beneficial changes')
    require(f['new_native_rollouts']==1171 and f['actual_records']==1172 and f['new_native_raw_rows']==rawcount and f['old_exact_patch_factual_read_only']==1,'counts')
    for key,value in (('prediction_registry_sha256',registry),('actual_registry_sha256',actual)):
        require(f[key]==sha256(canonical(value)).hexdigest(),'registry digest')
    require(singles['COMPLETE_MEASURE_BEFORE_NATIVE']['old_full_D_X_prediction_sha256']==sha256(canonical(complete)).hexdigest(),'old entire registry digest')
    require(Counter(t for t,o in rows)=={'INPUT_BINDING_BEFORE':1,'CONFIGURATION_PREDICTION_READ_ONLY':16364,'COMPLETE_MEASURE_BEFORE_NATIVE':1,
                'RAW_NATIVE_FACTUAL_BEFORE_TRUTH':1171,'ACTUAL_FACTUAL':1172,'INPUT_BINDING_AFTER':1,'FINAL':1},'all tags')
    print(json.dumps({'status':'COMPLETE_D_INSTALLER_STORED_CONTENT_CHECK_NOT_SCIENCE','role':'PRIMARY_STDLIB_IMPLEMENTATION_INDEPENDENCE_NOT_EXPERT',
          'all_original_D_contexts':13824,'noneligible_D_contexts_retained':6273,'eligible_contexts':7551,'all_D_configurations':16364,
          'all_old_D_X_predictions_checked':19964,'old_X_zero_mass_failure_retained':True,'old_basis_raw_rows':278,'old_legal_graph_edges_checked':20588,
          'normalizer':measure,'consulted_configuration_basis_pairs':586,'triggerable_configurations':26,'actual_architecture_records':1172,
          'new_native_rollouts':1171,'new_native_raw_rows':rawcount,'old_exact_patch_factual_read_only':1,
          'outcomes':dict(outcomes),'signed_return_changes_vs_nominal':dict(changes),'min_return_delta':min(deltas),'max_return_delta':max(deltas),
          'sources':313,'old_native':153,'prior_preparation':419,'HEAD_byte_bindings':733,'runtime_inputs':890,
          'no_RFL_candidate_predictor_old_checker_or_solver_execution':True,'B1_arms':0,'future_training':0,'keys_allocated':0,
          'multi_address_or_mixed_totality':False,'scientific_rules_adopted':False,'collection_authorized':False,'scientific_PASS':False,'independent_expert':False},sort_keys=True))

if __name__=='__main__': main()
