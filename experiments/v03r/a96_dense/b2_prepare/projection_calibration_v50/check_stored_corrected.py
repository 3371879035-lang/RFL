"""Independent actual scalar/map/direct-step calibration audit, no RFL execution."""
from collections import Counter, deque
from fractions import Fraction
from hashlib import sha1, sha256
from pathlib import Path
from itertools import product
import ast,json,subprocess
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]
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

def step(n,a):
    x,y,t,k,phi,z,m=n;dx,dy=((0,-1),(0,1),(-1,0),(1,0),(0,0))[a];nx,ny=x+dx,y+dy;nt=t+1
    outcome='COLLISION' if (nx,ny)==(2,2) and nt%(6,3)[k]==phi%(6,3)[k] else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
    nm=int(bool(m or z==1 and (nx,ny)==(2,1) or z==3 and (nx,ny)==(2,4) or z==2 and (x,y)==(1,2) and t%(6,3)[k]!=phi%(6,3)[k]))
    return {'post':[nx,ny,nt,k,phi,z,nm],'a_cmd':a,'u':a,'a_realized':a,
            'reward_hex':(-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)).hex(),
            'terminal':outcome is not None,'outcome':outcome,'illegal':False}

def main():
    repair=read(HERE/'checker_repair_contract.json')
    for n,h in repair['immutable_original_inputs'].items():require(digest(HERE/n)==h,'original component/capture retained')
    added={n:digest(HERE/n) for n in ('checker_repair_contract.json','check_stored_corrected.py','execute_check_corrected.py')}
    c=read(HERE/'contract.json');binding=bind(c);q={};cat=[];edges=[];basis=None
    for t,o in capture(c['stored']['catalog']):
        if t=='DECISION_CONTEXT':cat.append(o);q[tuple(o['context'])]={a:float.fromhex(h) for a,h in o['q_row_hex']}
    for t,o in capture(c['stored']['graph']):
        if t=='NATIVE_LEGAL_EDGE':edges.append(o)
    for t,o in capture(c['stored']['basis']):
        if t=='NATIVE_BASIS':basis=o['entries']
    cells={(0,2),(4,2)}|{(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)}
    shifts=((0,-1),(0,1),(-1,0),(1,0),(0,0));dist={(4,2):0};queue=deque(dist)
    while queue:
        x,y=queue.popleft()
        for dx,dy in shifts:
            s=(x+dx,y+dy)
            if s in cells and s not in dist:dist[s]=dist[x,y]+1;queue.append(s)
    domain=[(x,y,t,k,p,z,m) for t in range(12) for k in range(2) for p in range(6) for x,y in sorted(cells-{(4,2)}) for z in range(4) for m in range(2)]
    require([tuple(o['context']) for o in cat]==domain,'complete ordered13824 D domain')
    for o in cat:
        x,y,t,k,p,z,m=o['context'];legal=[]
        for a,(dx,dy) in enumerate(shifts):
            s=(x+dx,y+dy)
            if s not in cells or z==0 and dist[s]!=dist[x,y]-1 or z in (1,3) and m==0 and s==(4,2) or z==2 and m==0 and s in ((2,2),(4,2)):continue
            legal.append(a)
        require(legal==list(q[tuple(o['context'])]),'every original legal row')
    graph={}
    for o in edges:
        require(o['result']==step(tuple(o['pre']),o['command']),'ALL20588 old native graph direct-step')
        graph.setdefault(tuple(o['pre']),{})[o['command']]=o['result']
    roots=list(product(range(2),range(6),range(4)));rootids={v:i for i,v in enumerate(roots)}
    reach={(0,2,0,*r,0) for r in roots};queue=deque(reach)
    while queue:
        n=queue.popleft();require(set(graph[n])==set(q[n]),'all legal closure')
        for v in graph[n].values():
            post=tuple(v['post'])
            if not v['terminal'] and post not in reach:reach.add(post);queue.append(post)
    require((len(q),len(reach),len(graph),len(edges))==(13824,6254,6254,20588),'full domain graph')
    services={}
    # Independent full(z,m) grouping, no reachability or observed outcome filtering.
    for n,row in q.items():
        for cmd in row:services.setdefault(n[:5]+(cmd,),[]).append(set(row))
    service={s:set.intersection(*v) for s,v in services.items()};require(len(service)==5904,'full original X site domain')
    memo={}
    def direct(root,D,X,edit=None,patch=False):
        dd=tuple(sorted((a,t) for a,t in D.items() if a[3:6]==root));xx=tuple(sorted((a,t) for a,t in X.items() if a[3:5]==root[:2]))
        relevant=edit if edit is not None and (edit[1][3:6]==root if edit[0]=='D' else edit[1][3:5]==root[:2]) else None
        key=(root,dd,xx,relevant,patch)
        if key in memo:return memo[key]
        dm=dict(dd);xm=dict(xx);n=(0,2,0,*root,0);rows=[]
        while True:
            row=dict(q[n])
            if n in dm:
                a=dm[n];b=max(q[n].values());row[a]=b+(b-q[n][a])
            if relevant is not None and relevant[0]=='D' and n==relevant[1]:row[relevant[2]]=relevant[3]
            cmd=dm[n] if patch and n in dm else sorted(row,key=lambda a:(-row[a],a))[0];site=n[:5]+(cmd,);u=xm.get(site,cmd)
            if relevant is not None and relevant[0]=='X' and site==relevant[1]:u=relevant[2]
            require(cmd in q[n] and u in q[n],'legal actual commands and realized outputs');v=step(n,u)
            rows.append({'pre_state':list(n[:5]),'z':n[5],'m':n[6],'a_cmd':cmd,'u':u,'a_realized':u,'reward_hex':v['reward_hex'],
                         'post_state':v['post'][:5],'post_control':v['post'][5:],'terminal':v['terminal'],'outcome':v['outcome'],'illegal':False})
            if v['terminal']:break
            n=tuple(v['post'])
        result={'trace':rows,'outcome':rows[-1]['outcome'],'return_hex':sum(float.fromhex(v['reward_hex']) for v in rows).hex()}
        memo[key]=result;require(len(memo)<=c['guard']['max_local_predictions'],'fixed structural engineering guard');return result
    nominal=[direct(r,{}, {}) for r in roots];nomval=tuple(float.fromhex(v['return_hex']) for v in nominal)
    for i,o in enumerate(basis):
        rows=nominal[i]['trace'];packed=[[r['pre_state'],r['z'],r['m'],r['a_cmd'],r['u'],r['a_realized'],r['reward_hex'],r['post_state'],r['post_control'],r['terminal'],r['outcome'],r['illegal']] for r in rows]
        require((o['kappa'],o['phase'],o['committed'])==roots[i] and o['payload']['trace']==packed and o['payload']['return_hex']==nominal[i]['return_hex'],'all48 old basis278raw')
    scenes=list(product(range(2),range(6),range(2),range(60),range(4)));sequences={};aggregate={}
    def incidence(E,j):
        if (E,j) not in sequences:
            sequence=[]
            for k,p,e,r,z in scenes:
                i=rootids[k,p,z]
                if E>>i&1 and (True,p%2==0,p%2==1,r<30,e==0,z!=0)[j]:sequence.append(i)
            sequences[E,j]=sequence
        return sequences[E,j]
    def ordered(pre,post,E,j):
        key=(pre,post,E,j)
        if key not in aggregate:
            ids=incidence(E,j);a=sum(pre[i] for i in ids)/len(ids);b=sum(post[i] for i in ids)/len(ids)
            diff=sum(pre[i]-post[i] for i in ids)/len(ids)
            # Rational sum over the explicit full ordered scenes, not a root-event probability.
            unique={i:(Fraction.from_float(pre[i])-Fraction.from_float(post[i])) for i in set(ids)}
            exact=sum((unique[i] for i in ids),Fraction(0))/len(ids)
            aggregate[key]=(a,b,diff,exact)
            require(len(aggregate)<=c['guard']['max_ordered_mean_cache'],'complete aggregate engineering guard')
        return aggregate[key]
    ex=read(HERE/'evidence/exit.json');output=capture(['projection_calibration_v50/evidence',ex['files']['stdout.log']['sha256']]);require(next(output)==('INPUT_BINDING_BEFORE',binding),'new complete input binding')
    tag,enc=next(output);require(tag=='VALUE_ENCODING' and enc['roots']==[list(r) for r in roots] and enc['full_scenes']==5760 and enc['six_refinements']==c['six_refinements'],'full root/scene encoding')
    stats=Counter();regsha=sha256(b'[');inputsha=sha256(b'[');nrows=0
    for t,o in capture(c['stored']['regions']):
        if t!='FULL_WORLD_PROJECTION_REGION':continue
        inputsha.update((b',' if nrows else b'')+canonical(o).rstrip(b'\n'));tag,got=next(output);require(tag=='ACTUAL_PRE_VALUE_AND_CALIBRATION_BATTERY' and got['region']==o,'every full world and Gamma/projection/status preserved')
        D={tuple(a):v for a,v in o['D_declarations']};X={tuple(a):v for a,v in o['X_declarations']};pre=[direct(r,D,X) for r in roots]
        vals=tuple(float.fromhex(v['return_hex']) for v in pre);E=int(o['joint_region_root_mask_hex'],16) if o['joint_region_root_mask_hex'] is not None else None
        own={tuple(a) for a in o['complete_projection_owners']};channel=o['projection_channel']
        H=sum(1<<i for i,p in enumerate(pre) if p['outcome']=='SUCCESS');C=0
        for i,p in enumerate(pre):
            if any(tuple(r['pre_state']+[r['z'],r['m']]) in own if channel=='D' else tuple(r['pre_state']+[r['a_cmd']]) in own for r in p['trace']):C|=1<<i
        require(format(H,'012x')==o['healthy_pre_root_mask_hex'] and format(C,'012x')==o['consult_any_projection_root_mask_hex'] and E==(H&~C if own else None),'actual pre predicates bound, not nominal shortcut')
        result={'region':o,'actual_pre_root_return_hex':[p['return_hex'] for p in pre],'actual_pre_root_outcomes':[p['outcome'] for p in pre],
                'pre_nominal_full_scene_value_differences':120*sum(a!=b for a,b in zip(vals,nomval)),
                'pre_nominal_region_scene_value_differences':120*sum(vals[i]!=nomval[i] for i in range(48) if E is not None and E>>i&1) if E is not None else None,
                'six_actual_pre_ordered_means_hex':[ordered(vals,vals,E,j)[0].hex() if incidence(E,j) else None for j in range(6)] if E is not None else None,
                'calibration_batteries':[],'native_measurement_or_scientific_calibration':False}
        stats['projection_rows']+=1;stats[o['entry_status']]+=1;stats['full_pre_value_non_nominal_records']+=result['pre_nominal_full_scene_value_differences']>0
        if E is None:stats['null_projection_no_calibration']+=1
        else:
            stats['defined_projection_records']+=1;stats['region_pre_value_non_nominal_records']+=result['pre_nominal_region_scene_value_differences']>0
            for j,name in enumerate(c['six_refinements']):
                ids=incidence(E,j);candidates=[]
                for i in set(ids):
                    k,p,z=roots[i];scene=(k,p,0,0,z)
                    for r in pre[i]['trace']:
                        a=tuple(r['pre_state']+[r['z'],r['m']]) if channel=='D' else tuple(r['pre_state']+[r['a_cmd']]);current=r['a_cmd'] if channel=='D' else r['u']
                        targets=sorted((set(q[a]) if channel=='D' else service[a])-{current})
                        if a not in own and targets:
                            order=(a[2],a[0],a[1],*a[3:]);candidates.append((scene,order,i,a,current,targets))
                if not ids or not candidates:
                    result['calibration_batteries'].append({'refinement':name,'status':'EMPTY_REGION_UNDEFINED' if not ids else 'NO_LEGAL_SITE_UNCERTIFIED','targets':[]});stats['missing_battery_cells']+=1;continue
                scene,_,i,address,current,targets=min(candidates);battery={'refinement':name,'witness_scene':list(scene),'address':list(address),'actual_pre_action':current,'all_legal_other_targets':targets,'targets':[]}
                if channel=='D':
                    actualrow=dict(q[address])
                    if address in D:
                        a=D[address];b=max(actualrow.values());actualrow[a]=b+(b-actualrow[a])
                    battery['actual_DQ_row_hex']=[[a,v.hex()] for a,v in actualrow.items()]
                anynonzero=False
                for target in targets:
                    if channel=='D':
                        b=max(actualrow.values());scalar=b+(b-actualrow[target])+1.;edit=('D',address,target,scalar)
                    else:edit=('X',address,target)
                    post=[direct(r,D,X,edit) for r in roots];pv=tuple(float.fromhex(v['return_hex']) for v in post)
                    if channel=='D':
                        # Separate literal-map substrate is equal only in this fixed initial domain.
                        patchD=dict(D)
                        if target==sorted(q[address],key=lambda a:(-q[address][a],a))[0]:patchD.pop(address,None)
                        else:patchD[address]=target
                        require([direct(r,patchD,X,patch=True) for r in roots]==post,'independent Q scalar read vs patch canonical target')
                    a,b,pair,exact=ordered(vals,pv,E,j);sign='positive' if exact>0 else 'negative' if exact<0 else 'zero'
                    record={'target':target,'post_root_replacements':[[i,p['return_hex'],p['outcome']] for i,p in enumerate(post) if p['return_hex']!=pre[i]['return_hex'] or p['outcome']!=pre[i]['outcome']],
                            'ordered_post_mean_hex':b.hex(),'dual_ordered_mean_response_hex':(a-b).hex(),'paired_ordered_mean_response_hex':pair.hex(),
                            'exact_finite_float_response':[exact.numerator,exact.denominator],'response_sign':sign,'changed_state_not_imputed_effect':True}
                    if channel=='D':record['DQ_single_scalar_target_hex']=scalar.hex();record['independent_calibration_substrates']=['D_Q','D_patch']
                    else:record['independent_initial_installations']=['D_Q+X','patch+X']
                    battery['targets'].append(record);stats['legal_target_cells']+=1;stats['target_'+sign]+=1;anynonzero|=exact!=0;stats['zero_exact_nonzero_float_dual_cells']+=exact==0 and a-b!=0
                battery['status']='NONZERO_SOURCE_RESPONSE_NOT_NATIVE_CERTIFIED' if anynonzero else 'ALL_TARGETS_ZERO_UNCERTIFIED';stats['battery_cells']+=1;stats['all_targets_zero_battery_cells']+=not anynonzero
                result['calibration_batteries'].append(battery)
        require(got==result,'all complete pre/post values, fixed legal target battery, full ordered dual/paired/exact results')
        regsha.update((b',' if nrows else b'')+canonical(got).rstrip(b'\n'));nrows+=1
    regsha.update(b']\n');inputsha.update(b']\n');require(next(output)==('INPUT_BINDING_AFTER',binding) and bind(c)==binding,'full runtime beforeafter')
    tag,final=next(output);require(tag=='FINAL' and next(output,None) is None and final['counts']==dict(stats) and final['registry_sha256']==regsha.hexdigest() and final['source_region_registry_sha256']==inputsha.hexdigest() and nrows==68586,'complete fullregistry FINAL EOF')
    for node in ast.walk(ast.parse((HERE/'check_stored_corrected.py').read_bytes())):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            ns=[v.name.split('.')[0] for v in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]]
            require(all(v in {'collections','fractions','hashlib','pathlib','itertools','ast','json','subprocess'} for v in ns),'stdlib no candidate/RFL/oldchecker/solver imports')
    require(added=={n:digest(HERE/n) for n in added},'new repair sources beforeafter')
    emit('CHECK',{'additional_repair_source_sha256':added,'repair_additional_sources':3,'distinct_checkout_validation_inputs':1130,'original_checker_executed':False,'status':'COMPLETE_ACTUAL_PRE_CALIBRATION_SOURCE_CHECK_NOT_NATIVE_MEASUREMENT','counts':dict(stats),'registry_sha256':regsha.hexdigest(),
          'source_region_registry_sha256':inputsha.hexdigest(),'complete_U2_scene_identities':5760,'six_original_refinements':6,'old_graph_edges':20588,'old_basis_raw_rows':278,
          'independent_scalar_directstep_predictions':len(memo),'ordered_aggregate_cache_entries':len(aggregate),'runtime_inputs':1123,'parent_HEAD_bindings':966,
          'all_inputs_equal':True,'implementation_independence':'PRIMARY_ONLY_NOT_EXPERT','native_calibration_certified':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()


