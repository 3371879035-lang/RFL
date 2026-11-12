"""Complete mixed initial grammar mass by full unread cylinders, not science."""
from collections import Counter
from fractions import Fraction
from hashlib import sha1, sha256
from pathlib import Path
import json, subprocess
HERE=Path(__file__).resolve().parent; PREP=HERE.parent; ROOT=HERE.parents[4]
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
    require((len(source),len(native),len(prior),len(bound))==(313,153,637,951),'parent extent')
    for p in bound:require(digest(ROOT/p,True)==tree[p],'HEAD byte '+p)
    for p,h in (source|native).items():require(digest(ROOT/p)==h,'frozen/native '+p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==1108,'runtime extent')
    return {'HEAD':head,'HEAD_bindings':951,'runtime_inputs':1108,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}
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

def select(info):
    result={}
    for t,o in capture(info):
        if t=='DECISION_CONTEXT':result.setdefault('D',[]).append(o)
        elif t=='CONTROLLER_SITE':result.setdefault('X',[]).append(o)
        elif t=='NATIVE_LEGAL_EDGE':result.setdefault('edges',[]).append(o)
        elif t=='NATIVE_BASIS':result['basis']=o['entries']
    return result
def mask(indices):return sum(1<<i for i in indices)
def counts(bits,roots):
    return [sum((120,120*(p%2==0),120*(p%2==1),60,60,120*(z!=0))[j] for i,(k,p,z) in enumerate(roots) if bits>>i&1) for j in range(6)]
def main():
    c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    d=select(c['stored']['catalog']);g=select(c['stored']['graph']);b=select(c['stored']['basis'])['basis']
    q={tuple(o['context']):{a:float.fromhex(v) for a,v in o['q_row_hex']} for o in d['D']}
    require((len(q),len(d['X']))==(13824,5904),'complete domain')
    graph={}
    for o in g['edges']:graph.setdefault(tuple(o['pre']),{})[o['command']]=o['result']
    require((len(graph),sum(map(len,graph.values())))==(6254,20588),'complete legal graph')
    roots=[(k,p,z) for k in range(2) for p in range(6) for z in range(4)]
    require([(x['kappa'],x['phase'],x['committed']) for x in b]==roots,'full48 basis order')
    greedy={n:min(row,key=lambda a:(-row[a],a)) for n,row in q.items()}
    memo={}
    def predict(root,D,X):
        dd=tuple(sorted((a,t) for a,t in D.items() if a[3:6]==root));xx=tuple(sorted((a,t) for a,t in X.items() if a[3:5]==root[:2]))
        key=(root,dd,xx)
        if key in memo:return memo[key]
        dm=dict(dd);xm=dict(xx);n=(0,2,0,*root,0);trace=[]
        while True:
            cmd=dm.get(n,greedy[n]);s=n[:5]+(cmd,);u=xm.get(s,cmd);e=graph[n][u]
            trace.append({'pre_state':list(n[:5]),'z':n[5],'m':n[6],'a_cmd':cmd,'u':u,'a_realized':u,'reward_hex':e['reward_hex'],
                          'post_state':e['post'][:5],'post_control':e['post'][5:],'terminal':e['terminal'],'outcome':e['outcome'],'illegal':False})
            if e['terminal']:break
            n=tuple(e['post'])
        require(len(trace)<=12 and len(memo)<c['guard']['max_local_pre_histories'],'predeclared engineering guard')
        p={'trace':trace,'outcome':trace[-1]['outcome'],'return_hex':sum(float.fromhex(r['reward_hex']) for r in trace).hex()}
        hitsD={tuple(r['pre_state']+[r['z'],r['m']]) for r in trace};hitsX={tuple(r['pre_state']+[r['a_cmd']]) for r in trace}
        memo[key]=(p,hitsD,hitsX);return memo[key]
    nominal=[predict(r,{}, {}) for r in roots];nominalH=mask(i for i,p in enumerate(nominal) if p[0]['outcome']=='SUCCESS')
    for i,x in enumerate(b):
        packed=[[r['pre_state'],r['z'],r['m'],r['a_cmd'],r['u'],r['a_realized'],r['reward_hex'],r['post_state'],r['post_control'],r['terminal'],r['outcome'],r['illegal']] for r in nominal[i][0]['trace']]
        require(x['payload']['trace']==packed and x['payload']['return_hex']==nominal[i][0]['return_hex'],'complete old278 raw basis')
    emit('BASIS_SCENE_EXPANSION',{'roots':[list(r) for r in roots],'scenes_per_root':120,'full_U2_scenes':5760,'scene_key_order':['kappa','phase','error_flag','cause_rank','base_option'],
          'scene_root':'(kappa,phase,base_option); P identity, no masks/do; error_flag/cause_rank never read by command/physics',
          'nominal_healthy_root_mask_hex':format(nominalH,'012x'),'six_refinement_order':c['six_refinements'],'nominal_healthy_counts':counts(nominalH,roots)})
    totals={};registry=sha256(b'[');number=0
    for panelname in ('sentinel_D','mixed'):
        info=c['stored'][panelname];predsha=sha256(b'[');np=0;scopes=[];barrier=None;stats=Counter();geometries=Counter();seen=set();pred={}
        for t,o in capture(info):
            if t=='PREDICTION_BEFORE_ANY_NATIVE':
                predsha.update((b',' if np else b'')+canonical(o).rstrip(b'\n'));np+=1;pred[o['id']]=o
                if panelname=='sentinel_D':
                    D={tuple(a):v for a,v in o['declarations']};X={};projections=[('D',o['all_manifested_owners'])]
                    require(len(D)==8 and len(o['fixed_unread_sentinels'])==5 and len(projections[0][1])==3,'complete3plus5 support')
                else:
                    D={tuple(o['D_declaration'][0]):o['D_declaration'][1]};X={tuple(o['X_declaration'][0]):o['X_declaration'][1]}
                    projections=[(v,o['owners'][v]) for v in ('D','X')]
                for a,target in D.items():
                    row=q[a];require(target in row and row[target]<max(row.values())-1e-12 and max(row.values())+(max(row.values())-row[target])>max(row.values()),'independent fixed DQ promotion extensional pre')
                fullkey=canonical([sorted(D.items()),sorted(X.items())]);seen.add(fullkey)
                histories=[predict(r,D,X) for r in roots];require(histories[o['basis_index']][0]==o['pre'],'full stored factual root prediction')
                H=mask(i for i,p in enumerate(histories) if p[0]['outcome']=='SUCCESS')
                for channel,S in projections:
                    sites={tuple(a) for a in S};C=mask(i for i,p in enumerate(histories) if sites.intersection(p[1 if channel=='D' else 2]))
                    E=(H&~C) if sites else None
                    units=o['full_Oracle_units'] if panelname=='sentinel_D' else o['full_units']
                    status='NO_REFLECTION_SUCCESS' if o['pre']['outcome']=='SUCCESS' else 'NO_MANIFESTATION_ORACLE_INAPPLICABLE' if not units else 'EMPTY_ARCHITECTURE_PROJECTION_INAPPLICABLE' if not sites else 'NONEMPTY_COMPLETE_PROJECTION_FAILURE'
                    row={'panel':panelname,'stored_id':o['id'],'basis':o['basis'],'D_declarations':[[list(a),t] for a,t in D.items()],
                         'X_declarations':[[list(a),t] for a,t in X.items()],'full_world_literal_sha256':sha256(fullkey).hexdigest(),
                         'complete_original_Gamma_units':units,'projection_channel':channel,'complete_projection_owners':S,'factual_outcome':o['pre']['outcome'],
                         'entry_status':status,'healthy_pre_root_mask_hex':format(H,'012x'),'consult_any_projection_root_mask_hex':format(C,'012x'),
                         'joint_region_root_mask_hex':format(E,'012x') if E is not None else None,
                         'six_refinement_counts':counts(E,roots) if E is not None else None,'no_zero_effect_imputation':True,
                         'nominal_H_same_actual_consult_region_difference_scenes':120*((E^ (nominalH&~C)).bit_count()) if E is not None else None,
                         'scientific_region_adopted':False,'calibration_or_delta_certified':False}
                    if E is not None:
                        stats['empty_region_counterexamples']+=E==0
                        stats['nonproper_region_counterexamples']+=E.bit_count()==48
                        geometries[str(row['six_refinement_counts'][0])]+=1
                        stats['actual_vs_nominal_H_region_diff_nonzero']+=bool(row['nominal_H_same_actual_consult_region_difference_scenes'])
                        stats['difference_scenes_total_diagnostic_not_weight']+=row['nominal_H_same_actual_consult_region_difference_scenes']
                    stats[status]+=1;stats['projection_rows']+=1
                    emit('FULL_WORLD_PROJECTION_REGION',row);registry.update((b',' if number else b'')+canonical(row).rstrip(b'\n'));number+=1
            elif t=='BASIS_SCOPE':scopes.append(o)
            elif t=='COMPLETE_PANEL_BEFORE_NATIVE':barrier=o
            elif t=='RAW_FACTUAL_BEFORE_TRUTH':
                require(o['payload']==pred[o['id']]['pre'],'all stored independent installation factual raw')
            elif t=='ACTUAL_COMPLETE_RECORD':
                require(o['payload']==pred[o['id']]['pre'],'complete accepted factual binding')
        predsha.update(b']\n');require(np==c['panel_sizes'][panelname] and len(scopes)==48 and barrier['prediction_sha256']==predsha.hexdigest(),'complete panel and empty scopes retained')
        totals[panelname]={'world_basis_records':np,'unique_full_world_literals':len(seen),'prediction_sha256':predsha.hexdigest(),'all48_scope_sha256':sha256(canonical(scopes)).hexdigest(),'entries':dict(stats),'eligible_all_region_size_counts':dict(geometries)}
        emit('COMPLETE_PANEL_REGION_SUMMARY',{'panel':panelname,**totals[panelname]})
    registry.update(b']\n');after=bind(c);require(before==after,'all runtime stable');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'FULL_STORED_PROJECTION_PRE_REGION_GEOMETRY_NOT_SCIENCE','panels':totals,'projection_rows':number,'registry_sha256':registry.hexdigest(),
          'source_factored_local_pre_histories':len(memo),'runtime_inputs':1108,'parent_HEAD_bindings':951,'all_inputs_equal':True,
          'new_native_kernel_steps':0,'new_learner_rollouts':0,'B1_arms':0,'reference_DP':0,'learner_DP':0,'keys_allocated':0,'random_draws':0,'future_training':0,
          'sampler_or_collector_executed':False,'scientific_rules_adopted':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False,'mechanism_direction_falsified':False})
if __name__=='__main__':main()
