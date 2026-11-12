"""Complete source root response profiles, no RFL/native calibration or science adoption."""
from collections import Counter, deque
from fractions import Fraction
from hashlib import sha1, sha256
from pathlib import Path
from itertools import product
import ast,json,subprocess
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
    require((len(source),len(native),len(prior),len(bound))==(313,153,693,1007),'parent extent')
    for p in bound:require(digest(ROOT/p,True)==tree[p],'HEAD byte '+p)
    for p,h in (source|native).items():require(digest(ROOT/p)==h,'frozen/native '+p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==1164,'runtime extent')
    return {'HEAD':head,'HEAD_bindings':1007,'runtime_inputs':1164,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}

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
            if info[0].startswith(('mixed_projection','projection_regions','projection_calibration','offprojection')):require(canonical(o).rstrip(b'\n')==v,'full mixed canonical')
            yield t.decode(),o


def step(n,a):
    x,y,t,k,phi,z,m=n;dx,dy=((0,-1),(0,1),(-1,0),(1,0),(0,0))[a];nx,ny=x+dx,y+dy;nt=t+1
    outcome='COLLISION' if (nx,ny)==(2,2) and nt%(6,3)[k]==phi%(6,3)[k] else 'SUCCESS' if (nx,ny)==(4,2) else 'TIMEOUT' if nt==12 else None
    nm=int(bool(m or z==1 and (nx,ny)==(2,1) or z==3 and (nx,ny)==(2,4) or z==2 and (x,y)==(1,2) and t%(6,3)[k]!=phi%(6,3)[k]))
    return {'post':[nx,ny,nt,k,phi,z,nm],'a_cmd':a,'u':a,'a_realized':a,
            'reward_hex':(-.02+(1. if outcome=='SUCCESS' else -1. if outcome else 0.)).hex(),
            'terminal':outcome is not None,'outcome':outcome,'illegal':False}


def argmax(row):
    best=None;value=None
    for a in sorted(row):
        if value is None or row[a]>value:best=a;value=row[a]
    return best
def pushhash(h,o,i):h.update((b',' if i else b'')+canonical(o).rstrip(b'\n'))
def finishhash(h):h.update(b']\n');return h.hexdigest()
def main():
    c=read(HERE/'contract.json');binding=bind(c);cat={'D':{},'X':{}};hs=[];worlds=[];oldchecks={}
    for name in ('support_check','values_check'):
        rows=list(capture(c['stored'][name]));require(len(rows)==1 and rows[0][0]=='CHECK','immutable old checker full capture');oldchecks[name]=rows[0][1]
    hashes={t:sha256(b'[') for t in ('COMPLETE_LEGAL_DOMAIN','PRE_HISTORY','FULL_WORLD_OFFPROJECTION_SUPPORT')};n=Counter()
    for tag,o in capture(c['stored']['support']):
        if tag in hashes:pushhash(hashes[tag],o,n[tag]);n[tag]+=1
        if tag=='COMPLETE_LEGAL_DOMAIN':cat[o['channel']][o['index']]=o
        elif tag=='PRE_HISTORY':require(o['index']==len(hs),'full history order');hs.append(o)
        elif tag=='FULL_WORLD_OFFPROJECTION_SUPPORT':
            worlds.append({'old_sha':sha256(canonical(o)).hexdigest(),'value_sha':o['complete_old_value_battery_row_sha256'],
               'region':o['region'],'ids':o['all48_pre_history_indices'],'incidence':o['all_pre_consulted_site_root_masks'],'slices':o['six_support_slices']})
        elif tag=='FINAL':oldfinal=o
    digests={t:finishhash(h) for t,h in hashes.items()}
    require(n=={'COMPLETE_LEGAL_DOMAIN':19728,'PRE_HISTORY':67147,'FULL_WORLD_OFFPROJECTION_SUPPORT':68586},'every old complete support record')
    require(digests['COMPLETE_LEGAL_DOMAIN']==oldfinal['catalog_sha256']==oldchecks['support_check']['catalog_sha256']
      and digests['PRE_HISTORY']==oldfinal['history_registry_sha256']==oldchecks['support_check']['history_registry_sha256']
      and digests['FULL_WORLD_OFFPROJECTION_SUPPORT']==oldfinal['registry_sha256']==oldchecks['support_check']['registry_sha256'],'full old registries not old fixture rerun')
    address={ch:{tuple(v['address']):i for i,v in cat[ch].items()} for ch in ('D','X')}
    # Independent required-support construction from complete pre paths, not stored reader masks.
    reads=[]
    for h in hs:
        d={};x={}
        for v in h['complete_path']:
            d[v[0]]=v[1];site=tuple(cat['D'][v[0]]['address'][:5])+(v[1],);x[address['X'][site]]=v[2]
        reads.append({'D':d,'X':x})
    needed=set()
    for w in worlds:
        ch=w['region']['projection_channel'];ids=w['ids'];E=w['region']['joint_region_root_mask_hex']
        if E is None:continue
        mask=int(E,16);chosen=set();own={tuple(a) for a in w['region']['complete_projection_owners']}
        for i,hid in enumerate(ids):
            if mask>>i&1:
                for site,cur in reads[hid][ch].items():
                    require(tuple(cat[ch][site]['address']) not in own,'actual E excludes every S consultation')
                    if len(cat[ch][site]['full_legal_actions'])>1:chosen.add(site)
        for hid in ids:
            for site in chosen&reads[hid][ch].keys():needed.add((hid,ch,site))
    scopes=sorted(needed);groups={}
    for hid,ch,site in scopes:groups.setdefault((hid,ch),[]).append(site)
    plan={'site_scopes':len(scopes),'D_site_scopes':sum(ch=='D' for hid,ch,site in scopes),
      'X_site_scopes':sum(ch=='X' for hid,ch,site in scopes),
      'target_atoms':sum(len(cat[ch][site]['full_legal_actions'])-1 for hid,ch,site in scopes),
      'history_channel_profiles':len(groups),'scope_sha256':sha256(canonical(scopes)).hexdigest()}
    require(plan==c['pre_only_scope_probe'] and len(scopes)<=c['guard']['max_site_scopes']
      and plan['target_atoms']<=c['guard']['max_target_atoms'] and len(groups)<=c['guard']['max_history_channel_profiles'],'complete predeclared scope and guard')
    # Original complete legal/domain service and old edges verified directly, no RFL execution.
    cells={(0,2),(4,2)}|{(x,y) for x in (1,2,3) for y in (1,2,3,4) if (x,y)!=(2,3)}
    shifts=((0,-1),(0,1),(-1,0),(1,0),(0,0));dist={(4,2):0};queue=deque(dist)
    while queue:
        x,y=queue.popleft()
        for dx,dy in shifts:
            s=(x+dx,y+dy)
            if s in cells and s not in dist:dist[s]=dist[x,y]+1;queue.append(s)
    domain=[(x,y,t,k,p,z,m) for t in range(12) for k in range(2) for p in range(6) for x,y in sorted(cells-{(4,2)}) for z in range(4) for m in range(2)]
    require([tuple(v['address']) for v in cat['D'].values()]==domain,'full13824 original ordered addresses')
    q={};services={}
    for nD in domain:
        x,y,t,k,p,z,m=nD;legal=[]
        for a,(dx,dy) in enumerate(shifts):
            s=(x+dx,y+dy)
            if s not in cells or z==0 and dist[s]!=dist[x,y]-1 or z in (1,3) and m==0 and s==(4,2) or z==2 and m==0 and s in ((2,2),(4,2)):continue
            legal.append(a)
        record=cat['D'][address['D'][nD]];require(record['full_legal_actions']==legal,'each complete legal row')
        q[nD]={a:float.fromhex(h) for a,h in record['nominal_Q_row_hex']}
        require(list(q[nD])==legal and argmax(q[nD])==record['default_effective_pre_action'],'nominal full Q row strict argmax')
        for cmd in legal:services.setdefault(nD[:5]+(cmd,),[]).append(set(legal))
    service={s:set.intersection(*v) for s,v in services.items()}
    require([tuple(v['address']) for v in cat['X'].values()]==sorted(service,key=lambda s:(s[2],s[0],s[1],*s[3:])),'full5904 ordered Xsite domain')
    for s,i in address['X'].items():require(cat['X'][i]['full_legal_actions']==sorted(service[s]),'EVERY full-domain serving(z,m) output intersection')
    graph={}
    for tag,o in capture(c['stored']['graph']):
        if tag=='NATIVE_LEGAL_EDGE':
            require(o['result']==step(tuple(o['pre']),o['command']),'ALL20588 old edges independent direct step')
            graph.setdefault(tuple(o['pre']),{})[o['command']]=o['result']
    roots=list(product(range(2),range(6),range(4)));reach={(0,2,0,*r,0) for r in roots};queue=deque(reach)
    while queue:
        node=queue.popleft();require(set(graph[node])==set(q[node]),'full legal closure')
        for result in graph[node].values():
            child=tuple(result['post'])
            if not result['terminal'] and child not in reach:reach.add(child);queue.append(child)
    require(len(reach)==len(graph)==6254 and sum(map(len,graph.values()))==20588,'complete old graph extent')
    for tag,o in capture(c['stored']['basis']):
        if tag=='NATIVE_BASIS':basis=o['entries']
    rawcount=0
    for i,r in enumerate(roots):
        node=(0,2,0,*r,0);packed=[]
        while True:
            a=argmax(q[node]);result=step(node,a)
            packed.append([list(node[:5]),node[5],node[6],a,a,a,result['reward_hex'],result['post'][:5],result['post'][5:],result['terminal'],result['outcome'],False])
            if result['terminal']:break
            node=tuple(result['post'])
        require(basis[i]['payload']['trace']==packed and basis[i]['payload']['return_hex']==sum(float.fromhex(v[6]) for v in packed).hex(),'full48 old basis raw')
        rawcount+=len(packed)
    require(rawcount==278,'complete old basis extent')
    known={};v50hash=sha256(b'[');oldtarget=0;oldzero=0;rownum=0
    for tag,o in capture(c['stored']['values']):
        if tag!='ACTUAL_PRE_VALUE_AND_CALIBRATION_BATTERY':continue
        w=worlds[rownum];require(w['region']==o['region'] and w['value_sha']==sha256(canonical(o)).hexdigest(),'full old value support row exact')
        ch=w['region']['projection_channel']
        for battery in o['calibration_batteries']:
            oldzero+=battery['status']=='ALL_TARGETS_ZERO_UNCERTIFIED';site=address[ch][tuple(battery['address'])]
            for target in battery['targets']:
                oldtarget+=1;values=list(zip(o['actual_pre_root_return_hex'],o['actual_pre_root_outcomes']))
                for i,val,outcome in target['post_root_replacements']:values[i]=(val,outcome)
                for i,hid in enumerate(w['ids']):
                    if site in reads[hid][ch] and (hid,ch,site) in needed:
                        key=(hid,ch,site,target['target'])
                        record={'return_hex':values[i][0],'outcome':values[i][1],
                          'old_target_reference':[rownum,battery['refinement'],target['target'],sha256(canonical(target)).hexdigest()]}
                        if key in known:require((known[key]['return_hex'],known[key]['outcome'])==values[i],'exact old value atom consistency')
                        else:known[key]=record
        pushhash(v50hash,o,rownum);rownum+=1
    require(rownum==68586 and oldtarget==467314 and oldzero==2988 and finishhash(v50hash)==oldfinal['source_v50_registry_sha256']==oldchecks['values_check']['registry_sha256'],'ALL old fixed response values/zeros unchanged')
    output=capture(['offprojection_profiles_v52/evidence',read(HERE/'evidence/exit.json')['files']['stdout.log']['sha256']])
    require(next(output)==('INPUT_BINDING_BEFORE',binding),'full component runtime inputs')
    tag,got=next(output)
    require(tag=='PROFILE_PLAN_BEFORE_NEW_EFFECTS' and got=={'plan':plan,'complete_required_site_scopes':[list(s) for s in scopes],
       'support_registry_sha256':digests['FULL_WORLD_OFFPROJECTION_SUPPORT'],'old_counts':oldfinal['counts'],
       'full_old_domain':oldfinal['domain'],'full_history_registry_sha256':digests['PRE_HISTORY'],'native_calibration_certified':False},'all scopes before new response values')
    def direct_profile(h,ch,site,target,patch):
        D={tuple(a):t for a,t in h['relevant_D_declarations']};X={tuple(a):t for a,t in h['relevant_X_declarations']}
        edited=tuple(cat[ch][site]['address']);node=(0,2,0,*h['root'],0);path=[]
        # Retain all initial promoted scalars, then change exactly one scalar at selected owner.
        override={}
        for a,t in D.items():
            row=q[a];b=max(row.values());require(row[t]<b,'original nonoptimal initial assignment')
            override[a,t]=b+(b-row[t])
        if ch=='D':
            row={a:override.get((edited,a),v) for a,v in q[edited].items()};b=max(row.values())
            override[edited,target]=b+(b-row[target])+1.
            if target==argmax(q[edited]):D.pop(edited,None)
            else:D[edited]=target
        else:
            if target==edited[-1]:X.pop(edited,None)
            else:X[edited]=target
        while True:
            row={a:override.get((node,a),v) for a,v in q[node].items()}
            cmd=D.get(node,argmax(q[node])) if patch else argmax(row)
            xs=node[:5]+(cmd,);u=X.get(xs,cmd)
            require(cmd in q[node] and u in q[node] and u in service[xs],'actual full legal D/X provider')
            v=step(node,u);path.append([address['D'][node],cmd,u,v['reward_hex'],v['post'],v['terminal'],v['outcome']])
            if v['terminal']:break
            node=tuple(v['post'])
        return {'complete_path':path,'return_hex':sum(float.fromhex(v[3]) for v in path).hex(),'outcome':path[-1][-1]}
    registry=sha256(b'[');stats=Counter();profiles={};np=0
    for (hid,ch),sites in sorted(groups.items()):
        tag,got=next(output);h=hs[hid];expected=[]
        for site in sites:
            cur=reads[hid][ch][site]
            for target in cat[ch][site]['full_legal_actions']:
                if target==cur:continue
                key=(hid,ch,site,target)
                if key in known:
                    post={**known[key],'complete_path':None};role='EXACT_OLD_FIXED_TARGET_VALUE_REUSED_NOT_NEW_PREDICTION';stats['old_atom_values_reused']+=1
                else:
                    post=direct_profile(h,ch,site,target,False)
                    require(post==direct_profile(h,ch,site,target,True),'full scalar Q strict argmax vs separate literal patch complete direct path')
                    role='NEW_SOURCE_GRAPH_ROOT_PREDICTION_NOT_NATIVE';stats['new_root_predictions']+=1
                delta=float.fromhex(h['return_hex'])-float.fromhex(post['return_hex']);sign='positive' if delta>0 else 'negative' if delta<0 else 'zero'
                stats['local_return_'+sign]+=1;stats[ch+'_atoms']+=1
                expected.append({'site_index':site,'actual_pre_action':cur,'target':target,'role':role,'post':post,'local_pre_minus_post_sign':sign})
        record={'profile_index':np,'history_index':hid,'channel':ch,'complete_pre_history_sha256':sha256(canonical(h)).hexdigest(),
          'required_site_indices':sites,'all_legal_target_atoms':expected,'native_calibration_certified':False}
        require(tag=='ROOT_SITE_ALL_TARGET_PROFILE' and got==record,'ALL newly computed profiles full paths, exact old atom values/no old post rerun')
        pushhash(registry,got,np);profiles[hid,ch]=np;np+=1
    require(stats['D_atoms']+stats['X_atoms']==plan['target_atoms'],'ALL targets no zero/outcome filtering')
    whash=sha256(b'[')
    for i,w in enumerate(worlds):
        ch=w['region']['projection_channel'];E=w['region']['joint_region_root_mask_hex'];refs=[profiles.get((hid,ch)) for hid in w['ids']] if E is not None else None
        if E is not None:
            mask=int(E,16);chosen={site for j,hid in enumerate(w['ids']) if mask>>j&1 for site in reads[hid][ch] if len(cat[ch][site]['full_legal_actions'])>1}
            for hid in w['ids']:
                for site in chosen&reads[hid][ch].keys():require((hid,ch,site) in needed,'complete multi-reader closure covers outside E')
        expected={'world_projection_index':i,'complete_original_support_row_sha256':w['old_sha'],
          'full_world_literal_sha256':w['region']['full_world_literal_sha256'],'projection_channel':ch,
          'entry_status':w['region']['entry_status'],'all48_actual_pre_history_indices':w['ids'],
          'all48_channel_profile_references':refs,'six_original_support_slices':w['slices'],
          'full_original_region_Gamma_declarations_decoder':'exact bound v51 row at world_projection_index, no fullworld quotient',
          'no_E_reader_region_values_equal_actual_pre':E is not None,
          'outside_E_effects_for_no_E_reader_sites_not_computed_or_imputed':True,
          'native_calibration_certified':False}
        tag,got=next(output);require(tag=='FULL_WORLD_PROFILE_DECODER' and got==expected,'every world literal/complete old decoder/full S/Gamma/scene/refinement identity')
        pushhash(whash,got,i)
    require(next(output)==('INPUT_BINDING_AFTER',binding) and bind(c)==binding,'full runtime beforeafter')
    tag,final=next(output);require(tag=='FINAL' and next(output,None) is None,'complete FINAL EOF')
    require(final['plan']==plan and final['counts']==dict(stats) and final['profile_registry_sha256']==finishhash(registry)
      and final['world_decoder_registry_sha256']==finishhash(whash) and final['old_counts_retained']==oldfinal['counts']
      and final['source_support_registry_sha256']==digests['FULL_WORLD_OFFPROJECTION_SUPPORT']
      and final['source_v50_registry_sha256']==oldfinal['source_v50_registry_sha256'],'complete profile/world registry and preserved counts')
    require(final['complete_projection_rows']==68586 and final['full_pre_histories_retained']==67147 and final['all_inputs_equal']
      and final['runtime_inputs']==1164 and final['parent_HEAD_bindings']==1007,'complete source binding')
    for key in ('new_RFL_kernel_steps','new_learner_rollouts','B1_arms','reference_DP','learner_DP','keys_allocated','random_draws','future_training'):require(final[key]==0,'no prohibited execution '+key)
    for key in ('new_world_refinement_aggregate_responses_computed','collector_executed','native_calibration_certified','scientific_rules_adopted','scientific_PASS','collection_authorized','research_complete','mechanism_direction_falsified'):require(final[key] is False,'bounded source profile not science '+key)
    for node in ast.walk(ast.parse((HERE/'check_stored.py').read_bytes())):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            ns=[v.name.split('.')[0] for v in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]]
            require(all(v in {'collections','fractions','hashlib','pathlib','itertools','ast','json','subprocess'} for v in ns),'stdlib only no RFL/candidate/oldchecker/main/solver imports')
    emit('CHECK',{'status':'COMPLETE_NEW_ROOT_PROFILE_DIRECTSTEP_STRICT_Q_PATCH_AUDIT_NOT_NATIVE_CALIBRATION',
      'plan':plan,'counts':dict(stats),'profile_registry_sha256':final['profile_registry_sha256'],'world_decoder_registry_sha256':final['world_decoder_registry_sha256'],
      'source_support_registry_sha256':digests['FULL_WORLD_OFFPROJECTION_SUPPORT'],'source_v50_registry_sha256':oldfinal['source_v50_registry_sha256'],
      'complete_projection_rows':68586,'full_pre_histories_retained':67147,'old_counts_retained':oldfinal['counts'],
      'full_old_graph_edges':20588,'old_basis_raw_rows':278,'runtime_inputs':1164,'parent_HEAD_bindings':1007,
      'distinct_checkout_validation_inputs':1168,'all_inputs_equal':True,'implementation_independence':'PRIMARY_ONLY_NOT_EXPERT',
      'native_calibration_certified':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()
