"""Independent full support bitset/direct-step audit, no post effects or RFL execution."""
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
    require((len(source),len(native),len(prior),len(bound))==(313,153,670,984),'parent extent')
    for p in bound:require(digest(ROOT/p,True)==tree[p],'HEAD byte '+p)
    for p,h in (source|native).items():require(digest(ROOT/p)==h,'frozen/native '+p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==1141,'runtime extent')
    return {'HEAD':head,'HEAD_bindings':984,'runtime_inputs':1141,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}

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
    for n,row in q.items():
        for cmd in row:services.setdefault(n[:5]+(cmd,),[]).append(set(row))
    service={s:set.intersection(*v) for s,v in services.items()}
    Ddomain=domain;Xdomain=sorted(service,key=lambda s:(s[2],s[0],s[1],*s[3:]))
    domains={'D':Ddomain,'X':Xdomain};index={ch:{a:i for i,a in enumerate(v)} for ch,v in domains.items()}
    actions={'D':{a:set(row) for a,row in q.items()},'X':service}
    default={'D':{a:sorted(row,key=lambda v:(-row[v],v))[0] for a,row in q.items()},'X':{a:a[-1] for a in Xdomain}}
    xreach={a[:5]+(cmd,) for a in reach for cmd in q[a]}
    weighted={};eligiblebits={};base={}
    for ch in ('D','X'):
        groups={};unreachable=0;unreachable_sites=0;unreachable_targets=0
        for i,a in enumerate(domains[ch]):
            n=len(actions[ch][a])-1;groups[n]=groups.get(n,0)|(1<<i)
            if a not in (reach if ch=='D' else xreach):unreachable+=1;unreachable_sites+=n>0;unreachable_targets+=n
        weighted[ch]=groups;eligiblebits[ch]=sum(b for n,b in groups.items() if n>0)
        base[ch]={'domain_sites':len(domains[ch]),'legal_sites':eligiblebits[ch].bit_count(),
                  'legal_targets':sum(n*b.bit_count() for n,b in groups.items()),
                  'structurally_unreachable_sites':unreachable,'unreachable_legal_sites':unreachable_sites,'unreachable_legal_targets':unreachable_targets}
    def weight(ch,bits):return sum(n*(bits&b).bit_count() for n,b in weighted[ch].items())
    ex=read(HERE/'evidence/exit.json')
    output=capture(['offprojection_support_v51/evidence',ex['files']['stdout.log']['sha256']])
    require(next(output)==('INPUT_BINDING_BEFORE',binding),'component full runtime binding')
    catsha=sha256(b'[');nc=0
    for ch in ('D','X'):
        for i,a in enumerate(domains[ch]):
            expected={'channel':ch,'index':i,'address':list(a),'full_legal_actions':sorted(actions[ch][a]),
                      'default_effective_pre_action':default[ch][a],
                      'pre_only_other_target_count':len(actions[ch][a])-1,
                      'structurally_reachable':a in (reach if ch=='D' else xreach)}
            if ch=='D':expected['nominal_Q_row_hex']=[[v,h.hex()] for v,h in q[a].items()]
            tag,got=next(output);require(tag=='COMPLETE_LEGAL_DOMAIN' and got==expected,'every full domain address including noneligible unreachable no service')
            catsha.update((b',' if nc else b'')+canonical(got).rstrip(b'\n'));nc+=1
    catsha.update(b']\n');tag,enc=next(output)
    require(tag=='SUPPORT_ENCODING' and enc['roots']==[list(r) for r in roots] and enc['domain']==base and enc['catalog_sha256']==catsha.hexdigest() and enc['six_refinements']==c['six_refinements'] and enc['full_scenes']==5760,'complete support encoding')
    historysha=sha256(b'[');histories={};descriptors={};nh=0
    def read_row():
        nonlocal nh
        while True:
            t,o=next(output)
            if t!='PRE_HISTORY':return t,o
            i=o['index'];root=tuple(o['root']);D={tuple(a):v for a,v in o['relevant_D_declarations']};X={tuple(a):v for a,v in o['relevant_X_declarations']}
            require(i==nh and all(a[3:6]==root for a in D) and all(a[3:5]==root[:2] for a in X),'history descriptor order/full local relevance')
            require(list(o['relevant_D_declarations'])==[[list(a),v] for a,v in sorted(D.items())] and list(o['relevant_X_declarations'])==[[list(a),v] for a,v in sorted(X.items())],'all declared exceptions explicit')
            path=[];n=(0,2,0,*root,0);reads={'D':{},'X':{}}
            while True:
                row=dict(q[n]);cmd=None
                if n in D:
                    a=D[n];b=max(row.values());require(row[a]<b,'original initial target strictly nonoptimal')
                    row[a]=b+(b-row[a]);require(row[a]>b,'original actual promotion')
                # Strict ascending argmax, independently matched to direct patch provider.
                best=-float('inf')
                for a in sorted(row):
                    if row[a]>best:best=row[a];cmd=a
                patchcmd=D.get(n,default['D'][n]);require(cmd==patchcmd,'actual scalar argmax vs separate direct patch literal')
                site=n[:5]+(cmd,);u=X.get(site,cmd);require(u in service[site] and cmd in q[n] and u in q[n],'full domain legal provider')
                v=step(n,u);path.append([index['D'][n],cmd,u,v['reward_hex'],v['post'],v['terminal'],v['outcome']])
                reads['D'][index['D'][n]]=cmd;reads['X'][index['X'][site]]=u
                if v['terminal']:break
                n=tuple(v['post'])
            require(o['complete_path']==path and o['return_hex']==sum(float.fromhex(v[3]) for v in path).hex() and o['outcome']==path[-1][-1],'all new pre history complete direct-step paths')
            descriptor=(root,tuple((a,v) for a,v in sorted(D.items())),tuple((a,v) for a,v in sorted(X.items())))
            require(descriptor not in descriptors,'cache histories never duplicate descriptors')
            histories[i]=(o,reads);descriptors[descriptor]=i
            historysha.update((b',' if nh else b'')+canonical(o).rstrip(b'\n'));nh+=1;require(nh<=c['guard']['max_local_histories'],'prospective engineering history guard')
    scenes=list(product(range(2),range(6),range(2),range(60),range(4)));slice_cache={}
    def slices(E):
        if E not in slice_cache:
            values=[]
            for j in range(6):
                ids=[]
                for k,p,e,r,z in scenes:
                    i=rootids[k,p,z]
                    if E>>i&1 and (True,p%2==0,p%2==1,r<30,e==0,z!=0)[j]:ids.append(i)
                mask=sum(1<<i for i in set(ids));mult=Counter(ids);values.append((mask,len(ids),mult))
            slice_cache[E]=values
        return slice_cache[E]
    # Check all old nominal basis direct paths without executing old fixtures.
    for i,r in enumerate(roots):
        n=(0,2,0,*r,0);packed=[]
        while True:
            a=default['D'][n];v=step(n,a);packed.append([list(n[:5]),n[5],n[6],a,a,a,v['reward_hex'],v['post'][:5],v['post'][5:],v['terminal'],v['outcome'],False])
            if v['terminal']:break
            n=tuple(v['post'])
        require(basis[i]['payload']['trace']==packed and basis[i]['payload']['return_hex']==sum(float.fromhex(v[6]) for v in packed).hex(),'ALL48 old basis278 raw')
    reg=sha256(b'[');oldreg=sha256(b'[');stats=Counter();nrows=0
    for t,oldrow in capture(c['stored']['values']):
        if t!='ACTUAL_PRE_VALUE_AND_CALIBRATION_BATTERY':continue
        oldreg.update((b',' if nrows else b'')+canonical(oldrow).rstrip(b'\n'))
        tag,got=read_row();require(tag=='FULL_WORLD_OFFPROJECTION_SUPPORT','complete record dispatch')
        o=oldrow['region'];D={tuple(a):v for a,v in o['D_declarations']};X={tuple(a):v for a,v in o['X_declarations']}
        require(got['region']==o and got['complete_old_value_battery_row_sha256']==sha256(canonical(oldrow)).hexdigest(),'all old fullworld/Gamma/region/target/response preserved')
        ids=[]
        for root in roots:
            descriptor=(root,tuple((a,v) for a,v in sorted(D.items()) if a[3:6]==root),tuple((a,v) for a,v in sorted(X.items()) if a[3:5]==root[:2]))
            ids.append(descriptors[descriptor])
        require(ids==got['all48_pre_history_indices'],'all full-pre declaration identity references')
        hs=[histories[i] for i in ids]
        require([v[0]['return_hex'] for v in hs]==oldrow['actual_pre_root_return_hex'] and [v[0]['outcome'] for v in hs]==oldrow['actual_pre_root_outcomes'],'complete old actual values source binding')
        ch=o['projection_channel'];ownbits=sum(1<<index[ch][tuple(a)] for a in o['complete_projection_owners']);offbits=eligiblebits[ch]&~ownbits
        incidence={}
        for i,(_,reads) in enumerate(hs):
            for a,cur in reads[ch].items():
                if a not in incidence:incidence[a]=[cur,0]
                require(incidence[a][0]==cur,'shared pre literal output')
                incidence[a][1]|=1<<i
        exceptions=[[index[ch][a],v] for a,v in sorted((D if ch=='D' else X).items(),key=lambda v:index[ch][v[0]])]
        support_base={**base[ch],'offprojection_domain_sites':len(domains[ch])-ownbits.bit_count(),
                      'offprojection_legal_sites':offbits.bit_count(),'offprojection_legal_targets':weight(ch,offbits)}
        oldb=[{'refinement':b['refinement'],'address':b.get('address'),'actual_pre_action':b.get('actual_pre_action'),
               'all_legal_other_targets':b.get('all_legal_other_targets',[]),'status':b['status'],
               'complete_old_battery_sha256':sha256(canonical(b)).hexdigest()} for b in oldrow['calibration_batteries']]
        E=int(o['joint_region_root_mask_hex'],16) if o['joint_region_root_mask_hex'] is not None else None
        stats['projection_rows']+=1;stats[o['entry_status']]+=1;stats['prior_fixed_batteries_bound']+=len(oldb)
        stats['prior_fixed_target_responses_bound']+=sum(len(b['targets']) for b in oldrow['calibration_batteries'])
        for b in oldb:
            if b['status']=='ALL_TARGETS_ZERO_UNCERTIFIED':
                stats['old_all_zero_batteries_retained']+=1;stats['old_failure_all_zero_retained']+=o['entry_status']=='NONEMPTY_COMPLETE_PROJECTION_FAILURE'
        entries=None
        if E is None:stats['null_projection_support_not_imputed']+=1
        else:
            stats['defined_projection_records']+=1
            H=sum(1<<i for i,(_,p) in enumerate(hs) if hs[i][0]['outcome']=='SUCCESS')
            C=sum(1<<i for i,(_,reads) in enumerate(hs) if any(ownbits>>a&1 for a in reads[ch]))
            require(E==H&~C,'actual H and no own consultation, no nominal shortcut')
            entries=[]
            for j,(mask,nscenes,mult) in enumerate(slices(E)):
                readbits=sum(1<<a for a,(_,m) in incidence.items() if m&mask)&offbits
                rt=weight(ch,readbits);readcount=readbits.bit_count()
                rec={'refinement':c['six_refinements'][j],'region_root_mask_hex':format(mask,'012x'),'scene_count':nscenes,
                     'read_legal_sites':readcount,'read_legal_targets':rt,
                     'unread_legal_sites_retained':offbits.bit_count()-readcount,
                     'unread_legal_targets_retained':weight(ch,offbits)-rt,
                     'read_site_scene_incidence':sum(sum(mult[i] for i in mult if m>>i&1) for a,(_,m) in incidence.items() if readbits>>a&1),
                     'multi_root_shared_read_sites':sum((m&mask).bit_count()>1 for a,(_,m) in incidence.items() if readbits>>a&1),
                     'unread_first_hit_behavior_unchanged_source_only':True,'read_does_not_certify_nonzero_response':True}
                require(nscenes==o['six_refinement_counts'][j],'full ordered original scene slice')
                for b in oldb:
                    if b['refinement']==rec['refinement'] and b['address'] is not None:
                        a=index[ch][tuple(b['address'])];cur,m=incidence[a]
                        targets=sorted(actions[ch][tuple(b['address'])]-{cur})
                        require(readbits>>a&1 and cur==b['actual_pre_action'] and targets==b['all_legal_other_targets'],'all prior fixed batteries including zeros stay in consulted support')
                entries.append(rec);stats['support_slice_records']+=1
                for k in ('read_legal_sites','read_legal_targets','unread_legal_sites_retained','unread_legal_targets_retained','multi_root_shared_read_sites'):stats[k+'_sum']+=rec[k]
                stats['total_site_target_slice_literals']+=rt+rec['unread_legal_targets_retained']
        expected={'region':o,'complete_old_value_battery_row_sha256':sha256(canonical(oldrow)).hexdigest(),'all48_pre_history_indices':ids,
                  'all_actual_pre_mapping_exceptions':exceptions,'full_domain_support':support_base,
                  'all_pre_consulted_site_root_masks':[[a,cur,format(m,'012x')] for a,(cur,m) in sorted(incidence.items())],
                  'prior_fixed_battery_bindings':oldb,'six_support_slices':entries,'sensitivity_certified':False,'post_effects_computed':False}
        require(got==expected,'every complete support record/target decoder/read-unread slice')
        reg.update((b',' if nrows else b'')+canonical(got).rstrip(b'\n'));nrows+=1
    reg.update(b']\n');oldreg.update(b']\n');historysha.update(b']\n')
    require(next(output)==('INPUT_BINDING_AFTER',binding) and bind(c)==binding,'complete runtime beforeafter')
    tag,final=next(output);require(tag=='FINAL' and next(output,None) is None and nrows==68586,'full FINAL EOF')
    require(final['counts']==dict(stats) and final['domain']==base and final['catalog_sha256']==catsha.hexdigest() and final['registry_sha256']==reg.hexdigest() and final['source_v50_registry_sha256']==oldreg.hexdigest() and final['history_registry_sha256']==historysha.hexdigest() and final['source_local_histories']==nh,'complete registry identity/counts')
    require(stats['old_all_zero_batteries_retained']==2988 and stats['old_failure_all_zero_retained']==145,'all zero batteries preserved')
    for node in ast.walk(ast.parse((HERE/'check_stored.py').read_bytes())):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            ns=[v.name.split('.')[0] for v in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]]
            require(all(v in {'collections','fractions','hashlib','pathlib','itertools','ast','json','subprocess'} for v in ns),'only stdlib no RFL/candidate/oldchecker/main imports')
    emit('CHECK',{'status':'FULL_PRE_ONLY_SUPPORT_BITSET_DIRECTSTEP_AUDIT_NOT_SENSITIVITY_CERTIFIED','counts':dict(stats),'domain':base,
         'catalog_sha256':catsha.hexdigest(),'history_registry_sha256':historysha.hexdigest(),'registry_sha256':reg.hexdigest(),
         'source_v50_registry_sha256':oldreg.hexdigest(),'complete_local_pre_histories':nh,'full_old_graph_edges':20588,'old_basis_raw_rows':278,
         'runtime_inputs':1141,'parent_HEAD_bindings':984,'distinct_checkout_validation_inputs':1145,
         'all_inputs_equal':True,'complete_scenes':5760,'implementation_independence':'PRIMARY_ONLY_NOT_EXPERT',
         'post_effect_predictions':0,'native_calibration_certified':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()
