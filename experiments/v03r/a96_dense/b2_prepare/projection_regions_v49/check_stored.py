"""Independent source-first mixed event cut audit, no RFL/old fixture execution."""
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

def step(n,a):
    x,y,t,k,phi,z,m=n;dx,dy=((0,-1),(0,1),(-1,0),(1,0),(0,0))[a];nx,ny=x+dx,y+dy;nt=t+1
    outcome='COLLISION' if (nx,ny)==(2,2) and nt%(6,3)[k]==phi%(6,3)[k] else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
    nm=int(bool(m or z==1 and (nx,ny)==(2,1) or z==3 and (nx,ny)==(2,4) or z==2 and (x,y)==(1,2) and t%(6,3)[k]!=phi%(6,3)[k]))
    return {'post':[nx,ny,nt,k,phi,z,nm],'a_cmd':a,'u':a,'a_realized':a,
            'reward_hex':(-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)).hex(),
            'terminal':outcome is not None,'outcome':outcome,'illegal':False}


def filtered(info):
    result={}
    for t,o in capture(info):
        if t=='DECISION_CONTEXT':result.setdefault('D',[]).append(o)
        elif t=='CONTROLLER_SITE':result.setdefault('X',[]).append(o)
        elif t=='NATIVE_LEGAL_EDGE':result.setdefault('edges',[]).append(o)
        elif t=='NATIVE_BASIS':result['basis']=o['entries']
    return result
def main():
    c=read(HERE/'contract.json');binding=bind(c)
    cat=filtered(c['stored']['catalog']);gb=filtered(c['stored']['graph']);bs=filtered(c['stored']['basis'])['basis']
    q={tuple(o['context']):{a:float.fromhex(h) for a,h in o['q_row_hex']} for o in cat['D']}
    cells={(0,2),(4,2)}|{(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)}
    shifts=((0,-1),(0,1),(-1,0),(1,0),(0,0));dist={(4,2):0};queue=deque(dist)
    while queue:
        x,y=queue.popleft()
        for dx,dy in shifts:
            s=(x+dx,y+dy)
            if s in cells and s not in dist:dist[s]=dist[x,y]+1;queue.append(s)
    domain=[(x,y,t,k,p,z,m) for t in range(12) for k in range(2) for p in range(6) for x,y in sorted(cells-{(4,2)}) for z in range(4) for m in range(2)]
    require([tuple(o['context']) for o in cat['D']]==domain,'full ordered D context domain')
    for o in cat['D']:
        n=tuple(o['context']);x,y,t,k,p,z,m=n;legal=[]
        for a,(dx,dy) in enumerate(shifts):
            s=(x+dx,y+dy)
            if s not in cells or z==0 and dist[s]!=dist[x,y]-1 or z in (1,3) and m==0 and s==(4,2) or z==2 and m==0 and s in ((2,2),(4,2)):continue
            legal.append(a)
        require(legal==list(q[n]) and o['alternatives']==[a for a in legal if q[n][a]<max(q[n].values())-1e-12],'all legality/targets')
    graph={}
    for o in gb['edges']:
        n=tuple(o['pre']);require(o['result']==step(n,o['command']),'all native graph direct-step source binding');graph.setdefault(n,{})[o['command']]=o['result']
    roots=[(k,p,z) for k in range(2) for p in range(6) for z in range(4)]
    reach={(0,2,0,*r,0) for r in roots};queue=deque(reach)
    while queue:
        n=queue.popleft();require(set(graph[n])==set(q[n]),'complete legal graph closure')
        for e in graph[n].values():
            v=tuple(e['post'])
            if not e['terminal'] and v not in reach:reach.add(v);queue.append(v)
    require((len(reach),len(graph),len(gb['edges']))==(6254,6254,20588),'all old graph extent')
    scene_bits=[0]*48;slices=[0]*6;scene_count=0
    for k,p,e,r,z in product(range(2),range(6),range(2),range(60),range(4)):
        i=roots.index((k,p,z));bit=1<<scene_count;scene_bits[i]|=bit;scene_count+=1
        flags=(True,p%2==0,p%2==1,r<30,e==0,z!=0)
        for j,v in enumerate(flags):
            if v:slices[j]|=bit
    require(scene_count==5760 and all(v.bit_count()==120 for v in scene_bits),'explicit ALL ordered U2 scene incidence; no scene collapse')
    memo={}
    def direct(root,D,X):
        localD=tuple(sorted((a,t) for a,t in D.items() if a[3:6]==root));localX=tuple(sorted((a,t) for a,t in X.items() if a[3:5]==root[:2]))
        key=(root,localD,localX)
        if key in memo:return memo[key]
        dd=dict(localD);xx=dict(localX);n=(0,2,0,*root,0);rows=[]
        while True:
            cmd=dd.get(n,sorted(q[n],key=lambda a:(-q[n][a],a))[0]);u=xx.get(n[:5]+(cmd,),cmd);require(u in q[n],'each realized action admissible');v=step(n,u)
            rows.append({'pre_state':list(n[:5]),'z':n[5],'m':n[6],'a_cmd':cmd,'u':u,'a_realized':u,'reward_hex':v['reward_hex'],
                         'post_state':v['post'][:5],'post_control':v['post'][5:],'terminal':v['terminal'],'outcome':v['outcome'],'illegal':False})
            if v['terminal']:break
            n=tuple(v['post'])
        value={'trace':rows,'outcome':rows[-1]['outcome'],'return_hex':sum(float.fromhex(v['reward_hex']) for v in rows).hex()}
        memo[key]=value;require(len(memo)<=c['guard']['max_local_pre_histories'],'prospective local engineering guard');return value
    nominal=[direct(r,{}, {}) for r in roots]
    for i,o in enumerate(bs):
        require((o['kappa'],o['phase'],o['committed'])==roots[i],'basis order')
        packed=[[r['pre_state'],r['z'],r['m'],r['a_cmd'],r['u'],r['a_realized'],r['reward_hex'],r['post_state'],r['post_control'],r['terminal'],r['outcome'],r['illegal']] for r in nominal[i]['trace']]
        require(o['payload']['trace']==packed and o['payload']['return_hex']==nominal[i]['return_hex'],'old full278 basis')
    nomH=sum(1<<i for i,v in enumerate(nominal) if v['outcome']=='SUCCESS')
    nomScenes=sum(scene_bits[i] for i,v in enumerate(nominal) if v['outcome']=='SUCCESS')
    output=list(capture(['projection_regions_v49/evidence',read(HERE/'evidence/exit.json')['files']['stdout.log']['sha256']]))
    require(output[0]==('INPUT_BINDING_BEFORE',binding),'full current runtime binding')
    records=iter(o for t,o in output if t=='FULL_WORLD_PROJECTION_REGION')
    digest_rows=sha256(b'[');nrows=0;panels={}
    for name in ('sentinel_D','mixed'):
        stats=Counter();geometry=Counter();sha=sha256(b'[');n=0;seen=set();scopes=[];barrier=None;oldpred={}
        for tag,o in capture(c['stored'][name]):
            if tag=='PREDICTION_BEFORE_ANY_NATIVE':
                oldpred[o['id']]=o;sha.update((b',' if n else b'')+canonical(o).rstrip(b'\n'));n+=1
                if name=='sentinel_D':
                    D={tuple(a):v for a,v in o['declarations']};X={};proj=[('D',o['all_manifested_owners'])];units=o['full_Oracle_units']
                    require(len(D)==8 and len(o['fixed_unread_sentinels'])==5,'all eight original declarations retained')
                else:
                    D={tuple(o['D_declaration'][0]):o['D_declaration'][1]};X={tuple(o['X_declaration'][0]):o['X_declaration'][1]};proj=[(x,o['owners'][x]) for x in ('D','X')];units=o['full_units']
                key=canonical([sorted(D.items()),sorted(X.items())]);seen.add(key)
                pre=[direct(r,D,X) for r in roots];f=pre[o['basis_index']];require(f==o['pre'],'independent full raw before truth source prediction')
                actualD=[r['pre_state']+[r['z'],r['m']] for r in f['trace'] if q[tuple(r['pre_state']+[r['z'],r['m']])][r['a_cmd']]<max(q[tuple(r['pre_state']+[r['z'],r['m']])].values())-1e-12]
                actualX=[r['pre_state']+[r['a_cmd']] for r in f['trace'] if r['u']!=r['a_cmd']]
                require(actualD==proj[0][1] and (name=='sentinel_D' or actualX==proj[1][1]),'complete actual manifestation owners; not installed counts')
                for channel,S in proj:
                    own={tuple(s) for s in S};consult=[];health=[]
                    for i,p in enumerate(pre):
                        health.append(p['outcome']=='SUCCESS')
                        consult.append(any(tuple(r['pre_state']+[r['z'],r['m']]) in own if channel=='D' else tuple(r['pre_state']+[r['a_cmd']]) in own for r in p['trace']))
                    H=sum(1<<i for i,v in enumerate(health) if v);C=sum(1<<i for i,v in enumerate(consult) if v)
                    hs=sum(scene_bits[i] for i,v in enumerate(health) if v);cs=sum(scene_bits[i] for i,v in enumerate(consult) if v)
                    es=hs&~cs if own else None;E=H&~C if own else None
                    status='NO_REFLECTION_SUCCESS' if f['outcome']=='SUCCESS' else 'NO_MANIFESTATION_ORACLE_INAPPLICABLE' if not units else 'EMPTY_ARCHITECTURE_PROJECTION_INAPPLICABLE' if not own else 'NONEMPTY_COMPLETE_PROJECTION_FAILURE'
                    result={'panel':name,'stored_id':o['id'],'basis':o['basis'],'D_declarations':[[list(a),t] for a,t in D.items()],'X_declarations':[[list(a),t] for a,t in X.items()],
                        'full_world_literal_sha256':sha256(key).hexdigest(),'complete_original_Gamma_units':units,'projection_channel':channel,'complete_projection_owners':S,'factual_outcome':f['outcome'],'entry_status':status,
                        'healthy_pre_root_mask_hex':format(H,'012x'),'consult_any_projection_root_mask_hex':format(C,'012x'),'joint_region_root_mask_hex':format(E,'012x') if E is not None else None,
                        'six_refinement_counts':[(es&b).bit_count() for b in slices] if es is not None else None,'no_zero_effect_imputation':True,
                        'nominal_H_same_actual_consult_region_difference_scenes':(es^(nomScenes&~cs)).bit_count() if es is not None else None,'scientific_region_adopted':False,'calibration_or_delta_certified':False}
                    got=next(records);require(got==result,'every full world own-projection original predicate and full5760 scene counts')
                    digest_rows.update((b',' if nrows else b'')+canonical(result).rstrip(b'\n'));nrows+=1;stats[status]+=1;stats['projection_rows']+=1
                    if es is not None:
                        stats['empty_region_counterexamples']+=es==0;stats['nonproper_region_counterexamples']+=es.bit_count()==5760
                        geometry[str(result['six_refinement_counts'][0])]+=1;stats['actual_vs_nominal_H_region_diff_nonzero']+=bool(result['nominal_H_same_actual_consult_region_difference_scenes'])
                        stats['difference_scenes_total_diagnostic_not_weight']+=result['nominal_H_same_actual_consult_region_difference_scenes']
            elif tag=='BASIS_SCOPE':scopes.append(o)
            elif tag=='COMPLETE_PANEL_BEFORE_NATIVE':barrier=o
            elif tag in ('RAW_FACTUAL_BEFORE_TRUTH','ACTUAL_COMPLETE_RECORD'):require(o['payload']==oldpred[o['id']]['pre'],'all stored factual payloads complete binding')
        sha.update(b']\n');require(n==c['panel_sizes'][name] and len(scopes)==48 and sha.hexdigest()==barrier['prediction_sha256'],'complete panels with all empty scopes')
        panels[name]={'world_basis_records':n,'unique_full_world_literals':len(seen),'prediction_sha256':sha.hexdigest(),'all48_scope_sha256':sha256(canonical(scopes)).hexdigest(),'entries':dict(stats),'eligible_all_region_size_counts':dict(geometry)}
    require(next(records,None) is None,'no extra source/capture region rows')
    digest_rows.update(b']\n')
    summaries={o['panel']:{k:v for k,v in o.items() if k!='panel'} for t,o in output if t=='COMPLETE_PANEL_REGION_SUMMARY'}
    final=output[-1][1];require(output[-1][0]=='FINAL' and panels==summaries==final['panels'] and final['registry_sha256']==digest_rows.hexdigest() and final['projection_rows']==nrows,'complete registry final EOF')
    require([o for t,o in output if t=='INPUT_BINDING_AFTER']==[binding] and bind(c)==binding,'all inputs stable')
    for node in ast.walk(ast.parse((HERE/'check_stored.py').read_bytes())):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            ns=[v.name.split('.')[0] for v in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]]
            require(all(v in {'collections','fractions','hashlib','pathlib','itertools','ast','json','subprocess'} for v in ns),'stdlib no RFL/candidate/oldchecker/solver imports')
    emit('CHECK',{'status':'COMPLETE_ACTUAL_WPRE_PROJECTION_REGION_CHECK_NOT_SCIENCE','panels':panels,'registry_sha256':digest_rows.hexdigest(),'projection_rows':nrows,
          'complete_U2_scene_incidence':5760,'six_original_refinements':6,'original_graph_edges':20588,'old_full_basis_rows':278,'independent_direct_step_local_histories':len(memo),
          'runtime_inputs':1108,'parent_HEAD_bindings':951,'all_inputs_equal':True,'implementation_independence':'PRIMARY_ONLY_NOT_EXPERT',
          'scientific_PASS':False,'calibration_or_delta_certified':False,'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()
