"""Prospective native acquisition descriptors; no RFL execution or scientific adoption."""
from collections import Counter
from hashlib import sha1,sha256
from itertools import product
from pathlib import Path
import ast,json,subprocess,sys
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]
OUT_BYTES=0
def read(p):return json.loads(p.read_bytes())
def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def require(ok,why):
    if not ok:raise AssertionError(why)
def emit(t,o):
    global OUT_BYTES
    b=t+'='+canonical(o).decode().rstrip('\n');OUT_BYTES+=len(b.encode())+2
    require(OUT_BYTES<=700000000,'complete plan byte guard; no trimming')
    print(b,flush=True)
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
    require((len(source),len(native),len(prior),len(bound))==(313,153,747,1061),'parent extent')
    for p in bound:require(digest(ROOT/p,True)==tree[p],'HEAD byte '+p)
    for p,h in (source|native).items():require(digest(ROOT/p)==h,'frozen/native '+p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==1218,'runtime extent')
    return {'HEAD':head,'HEAD_bindings':1061,'runtime_inputs':1218,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}
def capture(info):
    folder=PREP/info[0];cl=read(folder/'claim.json');ex=read(folder/'exit.json')
    require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items()),'complete stored receipt')
    require(ex['files']['stdout.log']['sha256']==info[1] and (folder/'stderr.log').stat().st_size==0,'stored identity')
    for n,v in ex['files'].items():require({'bytes':(folder/n).stat().st_size,'sha256':digest(folder/n)}==v,'complete stored bytes')
    for n,h in ex['inputs'].items():require(digest(folder.parent/n)==h,'executed source immutable')
    with (folder/'stdout.log').open('rb') as f:
        for ln,line in enumerate(f,1):
            require(line.endswith(b'\n'),'complete EOF line');t,b=line.rstrip(b'\r\n').split(b'=',1);o=json.loads(b)
            require(canonical(o).rstrip(b'\n')==b,'complete canonical JSON')
            yield ln,t.decode(),o
def addhash(h,o,i):h.update((b',' if i else b'')+canonical(o).rstrip(b'\n'))
def endhash(h):h.update(b']\n');return h.hexdigest()
def fp(st):
    parts=[]
    for ch in ('D','P','X','Q'):
        if ch=='P':lines=[f'P:{a},{v}' for a,v in st[ch]]
        elif ch=='Q':lines=['Q:'+','.join(map(str,a))+'|'+v for a,v in st[ch]]
        else:lines=[ch+':'+','.join(map(str,a+[v])) for a,v in st[ch]]
        parts.append('\n'.join(sorted(lines)).encode())
    return sha256(b'\0'.join(parts)).hexdigest()
def compact(p,dindex):
    path=[]
    for r in p['trace']:
        require(not r['illegal'] and r['a_realized']==r['u'],'native admissible raw')
        a=tuple(r['pre_state']+[r['z'],r['m']]);path.append([dindex[a],r['a_cmd'],r['u'],r['reward_hex'],r['post_state']+r['post_control'],r['terminal'],r['outcome']])
    return {'complete_path':path,'return_hex':p['return_hex'],'outcome':p['outcome']}
def native_index(c,dindex):
    lookup={};measurements=duplicates=0;records=Counter()
    for name in ('native46','native47'):
        for ln,t,o in capture(c['stored'][name]):
            if t!='ACTUAL_COMPLETE_RECORD':continue
            records[name]+=1;arch=o.get('architecture',o.get('installation'));first=o['payload']['trace'][0]
            root=[first['pre_state'][3],first['pre_state'][4],first['z']]
            entries=[('factual',o['full_pre_store'],o['fingerprint_pre'],o['payload'])]
            arms=o.get('same_tier_arms',[]) if name=='native46' else [a for v in o['comparisons'].values() for a in v['same_tier_arms']]
            entries += [(str(i)+':'+a['role'],a['full_post_store'],a['ledger']['fingerprint_post'],a['payload']) for i,a in enumerate(arms)]
            for role,st,storedfp,p in entries:
                require(fp(st)==storedfp,'original fingerprint canonical exact')
                statehash=sha256(canonical(st)).hexdigest();key=(arch,tuple(root),storedfp)
                value=compact(p,dindex)
                ref={'capture':c['stored'][name][0],'line':ln,'record_id':o['id'],'installation':arch,'measurement_role':role,'record_sha256':sha256(canonical(o)).hexdigest(),'full_store_sha256':statehash,'original_fingerprint':storedfp,'payload_sha256':sha256(canonical(p)).hexdigest()}
                if key in lookup:require(lookup[key][0]==statehash and lookup[key][1]==value,'equal native fullstate/root must have exact same path');duplicates+=1
                else:lookup[key]=(statehash,value,ref)
                measurements+=1
    require(records=={'native46':114008,'native47':11582},'ALL complete old native records')
    return lookup,{'complete_native_records':dict(records),'stored_measurements_indexed':measurements,'duplicate_same_fullstate_root_measurements':duplicates,'unique_native_fullstate_root_keys':len(lookup)}
ROOTS=list(product(range(2),range(6),range(4)))

def main():
    c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    cat={'D':[],'X':[]};hist=[];ws=[];full=[];fullids={};reps={};hh=sha256(b'[');sh=sha256(b'[')
    for ln,t,o in capture(c['stored']['support']):
        if t=='COMPLETE_LEGAL_DOMAIN':cat[o['channel']].append(o)
        elif t=='PRE_HISTORY':require(o['index']==len(hist),'complete history order');addhash(hh,o,len(hist));hist.append(o)
        elif t=='FULL_WORLD_OFFPROJECTION_SUPPORT':
            wi=len(ws);addhash(sh,o,wi);r=o['region'];key=r['full_world_literal_sha256'];decl=[r['D_declarations'],r['X_declarations']]
            if key not in fullids:fullids[key]=len(full);full.append({'literal_sha256':key,'declarations':decl,'first_world_projection_index':wi})
            fid=fullids[key];require(full[fid]['declarations']==decl,'same complete literal, no behavioral quotient')
            ws.append((o,fid))
            for i,hid in enumerate(o['all48_pre_history_indices']):
                h=hist[hid];k,p,z=h['root']
                require(h['relevant_D_declarations']==sorted(d for d in decl[0] if d[0][3:6]==[k,p,z]) and h['relevant_X_declarations']==sorted(x for x in decl[1] if x[0][3:5]==[k,p]),'ALL local declarations, including post-new-read, retained')
                reps.setdefault(hid,[wi,i,fid])
        elif t=='FINAL':sf=o
    require((len(cat['D']),len(cat['X']),len(hist),len(ws),len(full),len(reps))==(13824,5904,67147,68586,62732,67147),'complete scope')
    require(endhash(hh)==sf['history_registry_sha256'] and endhash(sh)==sf['registry_sha256'],'complete source histories/worlds')
    di={tuple(o['address']):o['index'] for o in cat['D']};profiles=[];ph=sha256(b'[');v52dec=[]
    for ln,t,o in capture(c['stored']['profiles']):
        if t=='ROOT_SITE_ALL_TARGET_PROFILE':require(o['profile_index']==len(profiles),'ALL profile order');addhash(ph,o,len(profiles));profiles.append(o)
        elif t=='FULL_WORLD_PROFILE_DECODER':v52dec.append(sha256(canonical(o)).hexdigest())
        elif t=='FINAL':pf=o
    require(endhash(ph)==pf['profile_registry_sha256'] and len(profiles)==7188 and len(v52dec)==68586,'ALL profiles, no response chosen')
    v53dec=[]
    for ln,t,o in capture(c['stored']['aggregates']):
        if t=='FULL_WORLD_AGGREGATE_DECODER':require(o['world_projection_index']==len(v53dec),'all original aggregate world order');v53dec.append((sha256(canonical(o)).hexdigest(),o))
        elif t=='FINAL':af=o
    check=list(capture(c['stored']['aggregate_check']));require(len(check)==1 and check[0][1]=='CHECK' and check[0][2]['registries']==af['registries'],'complete v53 checker binding')
    native,oldstats=native_index(c,di)
    q={tuple(o['address']):{a:float.fromhex(h) for a,h in o['nominal_Q_row_hex']} for o in cat['D']}
    allstores=[]
    for f in full:
        ds,xs=f['declarations'];base={'D':sorted(ds),'P':[],'Q':[],'X':sorted(xs)}
        qs={'D':[],'P':[],'Q':[],'X':sorted(xs)}
        for a,target in ds:
            row=q[tuple(a)];b=max(row.values());qs['Q'].append([a+[target],(b+(b-row[target])).hex()])
        qs['Q'].sort();allstores.append({'D_Q':qs,'D_patch':base})
    sizes=Counter();regs={t:sha256(b'[') for t in ('NATIVE_FULL_LITERAL_INSTALLATION','ALL_HISTORY_NATIVE_PRE_DESCRIPTOR','ALL_TARGET_NATIVE_POST_DESCRIPTOR','FULL_WORLD_NATIVE_PLAN_DECODER')};counts=Counter()
    def record(t,o):
        emit(t,o);addhash(regs[t],o,sizes[t]);sizes[t]+=1
    def match(arch,hid,st,want):
        key=(arch,tuple(hist[hid]['root']),fp(st));value=native.get(key)
        if value is None:return None
        require(value[0]==sha256(canonical(st)).hexdigest(),'full canonical store exact, not fingerprint only')
        require(value[1]['return_hex']==want['return_hex'] and value[1]['outcome']==want['outcome'],'stored exact native measurement, no scope adjustment')
        if want['complete_path'] is not None:require(value[1]['complete_path']==want['complete_path'],'complete old native path exact')
        return value[2]
    plan={'world_projections':len(ws),'full_literal_installations':len(full),'histories':len(hist),'profiles':len(profiles),'profile_histories':len({p['history_index'] for p in profiles}),'atoms':sum(len(p['all_legal_target_atoms']) for p in profiles),'D_atoms':sum(len(p['all_legal_target_atoms']) for p in profiles if p['channel']=='D'),'X_atoms':sum(len(p['all_legal_target_atoms']) for p in profiles if p['channel']=='X'),'architecture_post_descriptors':2*sum(len(p['all_legal_target_atoms']) for p in profiles),'architecture_pre_descriptors':2*len(hist)}
    require(plan==c['expected_pre_only_counts'],'prospective entire support resource plan')
    maximum=plan['architecture_post_descriptors']+plan['architecture_pre_descriptors']
    require(maximum<=c['guard']['max_prospective_root_rollouts'] and 12*maximum<=c['guard']['max_prospective_raw_steps'],'no support trimming on resource guard')
    emit('COMPLETE_PRE_ONLY_NATIVE_RESOURCE_PLAN',{'plan':plan,'maximum_prospective_root_rollouts':maximum,'maximum_prospective_raw_steps':12*maximum,'old_index':oldstats,'no_response_filter':True,'native_executed':False,'historical_native_exclusion_complete':False})
    for fid,f in enumerate(full):
        record('NATIVE_FULL_LITERAL_INSTALLATION',{'installation_index':fid,**f,'all_original_store_bytes_by_architecture':allstores[fid],'full_store_sha256_by_architecture':{a:sha256(canonical(st)).hexdigest() for a,st in allstores[fid].items()},'original_fingerprint_by_architecture':{a:fp(st) for a,st in allstores[fid].items()},'off_root_sentinels_not_deleted':True})
    for hid,h in enumerate(hist):
        wi,ri,fid=reps[hid];tasks=[]
        for arch in ('D_Q','D_patch'):
            ref=match(arch,hid,allstores[fid][arch],h);counts['pre_exact_old_native_reuse' if ref else 'pre_requires_new_measurement']+=1
            tasks.append({'installation':arch,'full_literal_installation_index':fid,'exact_old_native_reference':ref,'new_native_required':ref is None})
        record('ALL_HISTORY_NATIVE_PRE_DESCRIPTOR',{'history_index':hid,'complete_history_sha256':sha256(canonical(h)).hexdigest(),'root':h['root'],'representative_world_projection_index':wi,'representative_root_index':ri,'full_literal_installation_index':fid,'same_local_declarations_proved_for_all_aliases':True,'native_pre_tasks':tasks,'not_scientific_world_or_scene_quotient':True})
    for p in profiles:
        hid=p['history_index'];wi,ri,fid=reps[hid];ch=p['channel'];atoms=[]
        require(p['complete_pre_history_sha256']==sha256(canonical(hist[hid])).hexdigest(),'profile history binding')
        for at in p['all_legal_target_atoms']:
            si,target=at['site_index'],at['target'];a=cat[ch][si]['address'];require(target in cat[ch][si]['full_legal_actions'] and target!=at['actual_pre_action'],'EVERY globally legal other target')
            tasks=[]
            for arch in ('D_Q','D_patch'):
                st={k:[list(v) for v in vs] for k,vs in allstores[fid][arch].items()}
                if ch=='D' and arch=='D_Q':
                    row=q[tuple(a)].copy()
                    for aa,hx in st['Q']:
                        if aa[:-1]==a:row[aa[-1]]=float.fromhex(hx)
                    require(min(row,key=lambda v:(-row[v],v))==at['actual_pre_action'],'actual complete Q row, no nominal replacement')
                    b=max(row.values());hx=(b+(b-row[target])+1).hex();edit={'store':'Q','address':a+[target],'value_hex':hx}
                    st['Q']=[v for v in st['Q'] if v[0]!=a+[target]]+[[a+[target],hx]]
                elif ch=='D':
                    nominal=min(q[tuple(a)],key=lambda v:(-q[tuple(a)][v],v));value=None if target==nominal else target
                    edit={'store':'D','address':a,'value':value};st['D']=[v for v in st['D'] if v[0]!=a]+([] if value is None else [[a,value]])
                else:
                    value=None if target==a[-1] else target;edit={'store':'X','address':a,'value':value};st['X']=[v for v in st['X'] if v[0]!=a]+([] if value is None else [[a,value]])
                st={k:sorted(v) for k,v in st.items()};require(fp(st)!=fp(allstores[fid][arch]),'actual fullstate single probe change, not sensitivity claim')
                ref=match(arch,hid,st,at['post']);counts['post_exact_old_native_reuse' if ref else 'post_requires_new_measurement']+=1
                tasks.append({'installation':arch,'full_literal_installation_index':fid,'single_edit':edit,'planned_full_post_store_sha256':sha256(canonical(st)).hexdigest(),'planned_original_post_fingerprint':fp(st),'exact_old_native_reference':ref,'new_native_required':ref is None,'B1_update_law':False})
            atoms.append({'site_index':si,'target':target,'actual_pre_action':at['actual_pre_action'],'native_post_tasks':tasks})
        record('ALL_TARGET_NATIVE_POST_DESCRIPTOR',{'profile_index':p['profile_index'],'complete_original_profile_sha256':sha256(canonical(p)).hexdigest(),'history_index':hid,'channel':ch,'required_site_indices':p['required_site_indices'],'all_legal_other_target_descriptors':atoms,'outside_E_shared_readers_retained':True,'no_response_filter':True})
    for wi,(o,fid) in enumerate(ws):
        decsha,dec=v53dec[wi]
        require(dec['complete_v51_support_row_sha256']==sha256(canonical(o)).hexdigest() and dec['complete_v52_decoder_row_sha256']==v52dec[wi],'every old fullworld decoder exact')
        record('FULL_WORLD_NATIVE_PLAN_DECODER',{'world_projection_index':wi,'full_literal_installation_index':fid,'complete_original_support_row_sha256':sha256(canonical(o)).hexdigest(),'complete_v52_decoder_row_sha256':v52dec[wi],'complete_v53_aggregate_decoder_row_sha256':decsha,'all48_actual_pre_history_indices':o['all48_pre_history_indices'],'full_world_literal_sha256':o['region']['full_world_literal_sha256'],'original_entry_status':o['region']['entry_status'],'all_original_six_support_slices':o['six_support_slices'],'original_aggregate_kernel_reference':dec['ordered_aggregate_kernel_reference'],'null_projection_not_zero':dec['null_projection_not_zero'],'outside_E_effects_not_imputed_zero':True})
    after=bind(c);require(before==after,'all inputs unchanged');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'COMPLETE_NATIVE_ACQUISITION_DESCRIPTORS_NOT_EXECUTED','plan':plan,'old_index':oldstats,'counts':dict(counts),'registries':{t:endhash(h) for t,h in regs.items()},'registry_sizes':dict(sizes),'actual_new_RFL_kernel_steps':0,'actual_new_learner_rollouts':0,'actual_B1_arms':0,'new_ordered_aggregate_calculations':0,'new_post_predictions':0,'maximum_prospective_root_rollouts':maximum,'maximum_prospective_raw_steps':12*maximum,'all_inputs_equal':True,'runtime_inputs':1218,'parent_HEAD_bindings':1061,'historical_native_exclusion_complete':False,'native_calibration_certified':False,'scientific_rules_adopted':False,'scientific_PASS':False,'collection_authorized':False,'keys_allocated':0,'random_draws':0,'future_training':0,'collector_executed':False,'research_complete':False,'mechanism_direction_falsified':False})
if __name__=='__main__':main()

