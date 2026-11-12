"""Actual-pre complete value maps and legal calibration batteries, not measurement."""
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
    require((len(source),len(native),len(prior),len(bound))==(313,153,652,966),'parent extent')
    for p in bound:require(digest(ROOT/p,True)==tree[p],'HEAD byte '+p)
    for p,h in (source|native).items():require(digest(ROOT/p)==h,'frozen/native '+p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==1123,'runtime extent')
    return {'HEAD':head,'HEAD_bindings':966,'runtime_inputs':1123,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}
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
            if info[0].startswith(('mixed_projection','projection_regions','projection_calibration')):require(canonical(o).rstrip(b'\n')==v,'full mixed canonical')
            yield t.decode(),o

def main():
    c=read(HERE/'contract.json');binding=bind(c);emit('INPUT_BINDING_BEFORE',binding)
    q={};graph={};basis=None
    for tag,o in capture(c['stored']['catalog']):
        if tag=='DECISION_CONTEXT':q[tuple(o['context'])]={a:float.fromhex(v) for a,v in o['q_row_hex']}
    for tag,o in capture(c['stored']['graph']):
        if tag=='NATIVE_LEGAL_EDGE':graph.setdefault(tuple(o['pre']),{})[o['command']]=o['result']
    for tag,o in capture(c['stored']['basis']):
        if tag=='NATIVE_BASIS':basis=o['entries']
    require((len(q),len(graph),sum(map(len,graph.values())))==(13824,6254,20588),'full domain/graph')
    roots=[(k,p,z) for k in range(2) for p in range(6) for z in range(4)]
    greedy={n:min(row,key=lambda a:(-row[a],a)) for n,row in q.items()}
    serving={}
    for n,row in q.items():
        for cmd in row:
            site=n[:5]+(cmd,);serving[site]=set(row) if site not in serving else serving[site]&set(row)
    require(len(serving)==5904,'complete full-domain legal X service')
    memo={};means={};seqs={}
    def predict(root,D,X):
        dd=tuple(sorted((a,t) for a,t in D.items() if a[3:6]==root));xx=tuple(sorted((a,t) for a,t in X.items() if a[3:5]==root[:2]));key=(root,dd,xx)
        if key in memo:return memo[key]
        dm=dict(dd);xm=dict(xx);n=(0,2,0,*root,0);rows=[]
        while True:
            cmd=dm.get(n,greedy[n]);site=n[:5]+(cmd,);u=xm.get(site,cmd);v=graph[n][u]
            rows.append({'pre_state':list(n[:5]),'z':n[5],'m':n[6],'a_cmd':cmd,'u':u,'a_realized':u,'reward_hex':v['reward_hex'],
                         'post_state':v['post'][:5],'post_control':v['post'][5:],'terminal':v['terminal'],'outcome':v['outcome'],'illegal':False})
            if v['terminal']:break
            n=tuple(v['post'])
        require(len(memo)<c['guard']['max_local_predictions'],'prospective structural engineering guard')
        memo[key]={'trace':rows,'outcome':rows[-1]['outcome'],'return_hex':sum(float.fromhex(r['reward_hex']) for r in rows).hex()};return memo[key]
    nominal=[predict(r,{}, {}) for r in roots];nomvals=tuple(float.fromhex(p['return_hex']) for p in nominal)
    for i,p in enumerate(nominal):
        b=basis[i];packed=[[r['pre_state'],r['z'],r['m'],r['a_cmd'],r['u'],r['a_realized'],r['reward_hex'],r['post_state'],r['post_control'],r['terminal'],r['outcome'],r['illegal']] for r in p['trace']]
        require((b['kappa'],b['phase'],b['committed'])==roots[i] and b['payload']['trace']==packed and b['payload']['return_hex']==p['return_hex'],'all48 old278 raw source binding')
    scenes=[(k,p,e,r,z) for k in range(2) for p in range(6) for e in range(2) for r in range(60) for z in range(4)]
    rootids={r:i for i,r in enumerate(roots)}
    def sequence(E,j):
        key=(E,j)
        if key not in seqs:
            seqs[key]=tuple(rootids[k,p,z] for k,p,e,r,z in scenes if E>>rootids[k,p,z]&1 and (True,p%2==0,p%2==1,r<30,e==0,z!=0)[j])
        return seqs[key]
    def avg(vals,E,j):
        key=(vals,E,j)
        if key not in means:
            ids=sequence(E,j);means[key]=sum(vals[i] for i in ids)/len(ids) if ids else None
            require(len(means)<=c['guard']['max_ordered_mean_cache'],'ordered mean engineering guard')
        return means[key]
    emit('VALUE_ENCODING',{'roots':[list(r) for r in roots],'scene_key_order':['kappa','phase','error_flag','cause_rank','base_option'],
          'full_scenes':5760,'post_codec':'exact changed root return/outcome replacements; all other roots equal actual pre; each original scene identity retained',
          'six_refinements':c['six_refinements'],'prediction_not_native_measurement':True})
    stats=Counter();registry=sha256(b'[');nrows=0;region_sha=sha256(b'[');diffcache={}
    def paired(pre,post,E,j):
        key=(pre,post,E,j)
        if key in diffcache:return diffcache[key]
        ids=sequence(E,j);d=sum(pre[i]-post[i] for i in ids)/len(ids)
        mult=Counter(ids);exact=sum(((Fraction(pre[i])-Fraction(post[i]))*v for i,v in mult.items()),Fraction(0))/len(ids)
        diffcache[key]=(d,exact);return d,exact
    for tag,o in capture(c['stored']['regions']):
        if tag!='FULL_WORLD_PROJECTION_REGION':continue
        region_sha.update((b',' if nrows else b'')+canonical(o).rstrip(b'\n'))
        D={tuple(a):v for a,v in o['D_declarations']};X={tuple(a):v for a,v in o['X_declarations']}
        pre=[predict(r,D,X) for r in roots];vals=tuple(float.fromhex(p['return_hex']) for p in pre)
        E=int(o['joint_region_root_mask_hex'],16) if o['joint_region_root_mask_hex'] is not None else None
        own={tuple(a) for a in o['complete_projection_owners']};channel=o['projection_channel']
        out={'region':o,'actual_pre_root_return_hex':[p['return_hex'] for p in pre],'actual_pre_root_outcomes':[p['outcome'] for p in pre],
             'pre_nominal_full_scene_value_differences':120*sum(a!=b for a,b in zip(vals,nomvals)),
             'pre_nominal_region_scene_value_differences':120*sum(vals[i]!=nomvals[i] for i in range(48) if E is not None and E>>i&1) if E is not None else None,
             'six_actual_pre_ordered_means_hex':[avg(vals,E,j).hex() if sequence(E,j) else None for j in range(6)] if E is not None else None,
             'calibration_batteries':[],'native_measurement_or_scientific_calibration':False}
        stats['projection_rows']+=1;stats[o['entry_status']]+=1;stats['full_pre_value_non_nominal_records']+=out['pre_nominal_full_scene_value_differences']>0
        if E is None:stats['null_projection_no_calibration']+=1
        else:
            stats['defined_projection_records']+=1;stats['region_pre_value_non_nominal_records']+=out['pre_nominal_region_scene_value_differences']>0
            for j,name in enumerate(c['six_refinements']):
                ids=sequence(E,j);witness=None
                # e/r constraints never change physics but scene identity and ordering stay literal.
                for i in dict.fromkeys(ids):
                    hist=pre[i]['trace'];k,p,z=roots[i]
                    for row in sorted(hist,key=lambda r:(r['pre_state'][2],r['pre_state'][0],r['pre_state'][1],r['pre_state'][3],r['pre_state'][4],r['z'],r['m']) if channel=='D' else (r['pre_state'][2],r['pre_state'][0],r['pre_state'][1],r['pre_state'][3],r['pre_state'][4],r['a_cmd'])):
                        address=tuple(row['pre_state']+[row['z'],row['m']]) if channel=='D' else tuple(row['pre_state']+[row['a_cmd']])
                        current=row['a_cmd'] if channel=='D' else row['u'];targets=sorted((set(q[address]) if channel=='D' else serving[address])-{current})
                        if address not in own and targets:
                            witness=(i,address,current,targets);break
                    if witness is not None:break
                if not ids or witness is None:
                    out['calibration_batteries'].append({'refinement':name,'status':'EMPTY_REGION_UNDEFINED' if not ids else 'NO_LEGAL_SITE_UNCERTIFIED','targets':[]});stats['missing_battery_cells']+=1;continue
                i,address,current,targets=witness;k,p,z=roots[i]
                battery={'refinement':name,'witness_scene':[k,p,0,0,z],'address':list(address),'actual_pre_action':current,'all_legal_other_targets':targets,'targets':[]}
                # All original refinements allow e=0/r=0. This witness is chosen before post prediction.
                if channel=='D':
                    actualrow=dict(q[address])
                    if address in D:
                        old=D[address];b=max(q[address].values());actualrow[old]=b+(b-q[address][old])
                    battery['actual_DQ_row_hex']=[[a,v.hex()] for a,v in actualrow.items()]
                anynonzero=False
                for target in targets:
                    dp=dict(D);xp=dict(X)
                    if channel=='D':dp[address]=target
                    else:xp[address]=target
                    post=[predict(r,dp,xp) for r in roots];pv=tuple(float.fromhex(p['return_hex']) for p in post)
                    pair,exact=paired(vals,pv,E,j);dual=avg(vals,E,j)-avg(pv,E,j);sign='positive' if exact>0 else 'negative' if exact<0 else 'zero'
                    record={'target':target,'post_root_replacements':[[i,p['return_hex'],p['outcome']] for i,p in enumerate(post) if p['return_hex']!=pre[i]['return_hex'] or p['outcome']!=pre[i]['outcome']],
                            'ordered_post_mean_hex':avg(pv,E,j).hex(),'dual_ordered_mean_response_hex':dual.hex(),'paired_ordered_mean_response_hex':pair.hex(),
                            'exact_finite_float_response':[exact.numerator,exact.denominator],'response_sign':sign,'changed_state_not_imputed_effect':True}
                    if channel=='D':
                        b=max(actualrow.values());scalar=b+(b-actualrow[target])+1.;require(scalar>b,'actual entire row promotion')
                        record['DQ_single_scalar_target_hex']=scalar.hex();record['independent_calibration_substrates']=['D_Q','D_patch']
                    else:record['independent_initial_installations']=['D_Q+X','patch+X']
                    battery['targets'].append(record);stats['legal_target_cells']+=1;stats['target_'+sign]+=1;anynonzero|=exact!=0
                    stats['zero_exact_nonzero_float_dual_cells']+=exact==0 and dual!=0
                battery['status']='NONZERO_SOURCE_RESPONSE_NOT_NATIVE_CERTIFIED' if anynonzero else 'ALL_TARGETS_ZERO_UNCERTIFIED'
                stats['battery_cells']+=1;stats['all_targets_zero_battery_cells']+=not anynonzero
                out['calibration_batteries'].append(battery)
        emit('ACTUAL_PRE_VALUE_AND_CALIBRATION_BATTERY',out);registry.update((b',' if nrows else b'')+canonical(out).rstrip(b'\n'));nrows+=1
    registry.update(b']\n');region_sha.update(b']\n');require(nrows==68586 and region_sha.hexdigest()=='cc4b4b5c8538d2a79203c88d7210e05384fed65643fead1835b7d4143eae6c07','all prior rows exact complete')
    after=bind(c);require(binding==after,'all runtime stable');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'FULL_ACTUAL_PRE_SOURCE_CALIBRATION_BATTERIES_NOT_NATIVE_MEASUREMENT','counts':dict(stats),'registry_sha256':registry.hexdigest(),
          'source_region_registry_sha256':region_sha.hexdigest(),'local_source_predictions':len(memo),'ordered_mean_cache_entries':len(means),
          'runtime_inputs':1123,'parent_HEAD_bindings':966,'all_inputs_equal':True,'new_learner_rollouts':0,'new_native_kernel_steps':0,'B1_arms':0,
          'reference_DP':0,'learner_DP':0,'keys_allocated':0,'random_draws':0,'future_training':0,'collector_executed':False,'scientific_rules_adopted':False,
          'scientific_PASS':False,'collection_authorized':False,'research_complete':False,'mechanism_direction_falsified':False})
if __name__=='__main__':main()

