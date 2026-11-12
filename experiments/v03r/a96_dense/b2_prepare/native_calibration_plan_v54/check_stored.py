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
    c=read(HERE/'contract.json');before=bind(c);cats={'D':{},'X':{}};hs={};worlds=[];install_order={};literal_specs={};representatives={}
    for ln,t,o in capture(c['stored']['support']):
        if t=='COMPLETE_LEGAL_DOMAIN':cats[o['channel']][o['index']]=o
        elif t=='PRE_HISTORY':hs[o['index']]=o
        elif t=='FULL_WORLD_OFFPROJECTION_SUPPORT':
            index=len(worlds);r=o['region'];literal=r['full_world_literal_sha256'];spec=(r['D_declarations'],r['X_declarations'])
            if literal not in install_order:install_order[literal]=len(install_order);literal_specs[literal]=(spec,index)
            require(literal_specs[literal][0]==spec,'full literal equality')
            worlds.append(o)
            for ri,hid in enumerate(o['all48_pre_history_indices']):
                h=hs[hid];k,ph,z=h['root'];ds=sorted(d for d in spec[0] if d[0][3:6]==[k,ph,z]);xs=sorted(x for x in spec[1] if x[0][3:5]==[k,ph])
                require(h['relevant_D_declarations']==ds and h['relevant_X_declarations']==xs,'all local declarations incl. unread')
                if hid not in representatives:representatives[hid]=(index,ri,install_order[literal])
        elif t=='FINAL':sf=o
    di={tuple(o['address']):i for i,o in cats['D'].items()};xi={tuple(o['address']):i for i,o in cats['X'].items()}
    path_reads={}
    for hid,h in hs.items():
        reads={'D':{},'X':{}}
        for d,cmd,u,r,post,terminal,outcome in h['complete_path']:
            a=cats['D'][d]['address'];x=xi[tuple(a[:5]+[cmd])]
            require(d not in reads['D'] and x not in reads['X'],'single increasing-time pre reads')
            reads['D'][d]=cmd;reads['X'][x]=u
        path_reads[hid]=reads
    required={}
    for w in worlds:
        r=w['region'];E=r['joint_region_root_mask_hex'];ch=r['projection_channel']
        if E is None:continue
        mask=int(E,16);owners={tuple(a) for a in r['complete_projection_owners']};inc={}
        for ri,hid in enumerate(w['all48_pre_history_indices']):
            for si in path_reads[hid][ch]:inc.setdefault(si,[]).append((ri,hid))
        for si,readers in inc.items():
            if len(cats[ch][si]['full_legal_actions'])<=1 or tuple(cats[ch][si]['address']) in owners or not any(mask>>ri&1 for ri,hid in readers):continue
            for ri,hid in readers:required.setdefault((hid,ch),set()).add(si)
    profiles=[];v52dec=[]
    for ln,t,o in capture(c['stored']['profiles']):
        if t=='ROOT_SITE_ALL_TARGET_PROFILE':profiles.append(o)
        elif t=='FULL_WORLD_PROFILE_DECODER':v52dec.append(sha256(canonical(o)).hexdigest())
        elif t=='FINAL':pf=o
    require(len(required)==len(profiles)==7188,'ALL pre-reader closure independent of candidate masks')
    for p in profiles:
        hid,ch=p['history_index'],p['channel'];sites=sorted(required[hid,ch])
        require(sites==p['required_site_indices'],'every site and outside-E shared reader retained')
        expected=[(si,at,target) for si in sites for at in [path_reads[hid][ch][si]] for target in cats[ch][si]['full_legal_actions'] if target!=at]
        actual=[(v['site_index'],v['actual_pre_action'],v['target']) for v in p['all_legal_target_atoms']]
        require(actual==expected,'ALL legalother no zero/sign/outcome selection')
    v53dec=[]
    for ln,t,o in capture(c['stored']['aggregates']):
        if t=='FULL_WORLD_AGGREGATE_DECODER':v53dec.append(o)
        elif t=='FINAL':af=o
    ac=list(capture(c['stored']['aggregate_check']));require(ac[0][2]['registries']==af['registries'],'old aggregate receipt')
    native,oldstats=native_index(c,di)
    qrows={tuple(o['address']):dict((a,float.fromhex(v)) for a,v in o['nominal_Q_row_hex']) for o in cats['D'].values()}
    stores=[]
    for literal in install_order:
        (ds,xs),first=literal_specs[literal];dq=[]
        for a,target in ds:
            vals=qrows[tuple(a)];maximum=max(vals.values());dq.append([a+[target],(maximum+(maximum-vals[target])).hex()])
        stores.append({'D_Q':{'D':[],'P':[],'Q':sorted(dq),'X':sorted(xs)},'D_patch':{'D':sorted(ds),'P':[],'Q':[],'X':sorted(xs)}})
    def oldmatch(arch,hid,st,want):
        v=native.get((arch,tuple(hs[hid]['root']),fp(st)))
        if v is None:return None
        require(v[0]==sha256(canonical(st)).hexdigest(),'fullstore byte identity not fp alone')
        require(v[1]['outcome']==want['outcome'] and v[1]['return_hex']==want['return_hex'],'exact oldnative value')
        require(want['complete_path'] is None or v[1]['complete_path']==want['complete_path'],'complete old native path')
        return v[2]
    regs={t:sha256(b'[') for t in ('NATIVE_FULL_LITERAL_INSTALLATION','ALL_HISTORY_NATIVE_PRE_DESCRIPTOR','ALL_TARGET_NATIVE_POST_DESCRIPTOR','FULL_WORLD_NATIVE_PLAN_DECODER')};sizes=Counter();counts=Counter()
    plan=c['expected_pre_only_counts'];require(plan=={'world_projections':len(worlds),'full_literal_installations':len(stores),'histories':len(hs),'profiles':len(profiles),'profile_histories':len({p['history_index'] for p in profiles}),'atoms':sum(len(p['all_legal_target_atoms']) for p in profiles),'D_atoms':sum(len(p['all_legal_target_atoms']) for p in profiles if p['channel']=='D'),'X_atoms':sum(len(p['all_legal_target_atoms']) for p in profiles if p['channel']=='X'),'architecture_post_descriptors':144864,'architecture_pre_descriptors':134294},'independent resource counts')
    src=capture(['native_calibration_plan_v54/evidence',read(HERE/'evidence/exit.json')['files']['stdout.log']['sha256']])
    require(next(src)[1:]==('INPUT_BINDING_BEFORE',before),'full candidate input binding')
    tag_plan=next(src);require(tag_plan[1]=='COMPLETE_PRE_ONLY_NATIVE_RESOURCE_PLAN' and tag_plan[2]['plan']==plan and tag_plan[2]['old_index']==oldstats and tag_plan[2]['maximum_prospective_root_rollouts']==279158 and tag_plan[2]['maximum_prospective_raw_steps']==3349896,'before all execution descriptors resource bound')
    for ln,t,o in src:
        if t in regs:
            require(o.get('installation_index',o.get('history_index') if t=='ALL_HISTORY_NATIVE_PRE_DESCRIPTOR' else o.get('profile_index') if t=='ALL_TARGET_NATIVE_POST_DESCRIPTOR' else o.get('world_projection_index'))==sizes[t],'canonical complete descriptor order')
            addhash(regs[t],o,sizes[t]);sizes[t]+=1
        if t=='NATIVE_FULL_LITERAL_INSTALLATION':
            i=o['installation_index'];literal=o['literal_sha256'];require(install_order[literal]==i,'full literal installation order')
            (ds,xs),first=literal_specs[literal]
            require(o['declarations']==[ds,xs] and o['first_world_projection_index']==first and o['all_original_store_bytes_by_architecture']==stores[i],'ALL stores and original sentinels, no local-only install')
            require(o['full_store_sha256_by_architecture']=={a:sha256(canonical(st)).hexdigest() for a,st in stores[i].items()} and o['original_fingerprint_by_architecture']=={a:fp(st) for a,st in stores[i].items()},'complete native store identity')
        elif t=='ALL_HISTORY_NATIVE_PRE_DESCRIPTOR':
            hid=o['history_index'];h=hs[hid];wi,ri,fid=representatives[hid]
            require((o['representative_world_projection_index'],o['representative_root_index'],o['full_literal_installation_index'])==(wi,ri,fid) and o['root']==h['root'] and o['complete_history_sha256']==sha256(canonical(h)).hexdigest(),'lex first complete fullworld representative, not response selection')
            for task,arch in zip(o['native_pre_tasks'],('D_Q','D_patch'),strict=True):
                ref=oldmatch(arch,hid,stores[fid][arch],h)
                require(task=={'installation':arch,'full_literal_installation_index':fid,'exact_old_native_reference':ref,'new_native_required':ref is None},'full oldnative pre matching')
                counts['pre_exact_old_native_reuse' if ref else 'pre_requires_new_measurement']+=1
        elif t=='ALL_TARGET_NATIVE_POST_DESCRIPTOR':
            p=profiles[o['profile_index']];hid=p['history_index'];ch=p['channel'];fid=representatives[hid][2]
            require(o['complete_original_profile_sha256']==sha256(canonical(p)).hexdigest() and (o['history_index'],o['channel'],o['required_site_indices'])==(hid,ch,sorted(required[hid,ch])),'complete original profile')
            require(len(o['all_legal_other_target_descriptors'])==len(p['all_legal_target_atoms']),'ALL targets')
            for atom,original in zip(o['all_legal_other_target_descriptors'],p['all_legal_target_atoms'],strict=True):
                si,target,cur=original['site_index'],original['target'],original['actual_pre_action'];a=cats[ch][si]['address']
                require((atom['site_index'],atom['target'],atom['actual_pre_action'])==(si,target,cur),'each ALL atom identity')
                for task,arch in zip(atom['native_post_tasks'],('D_Q','D_patch'),strict=True):
                    base=stores[fid][arch];maps={k:{tuple(aa) if isinstance(aa,list) else aa:v for aa,v in vs} for k,vs in base.items()}
                    if ch=='D' and arch=='D_Q':
                        values={action:maps['Q'].get(tuple(a+[action]),value.hex()) for action,value in qrows[tuple(a)].items()}
                        actual={action:float.fromhex(v) for action,v in values.items()};maximum=max(actual.values());require(min(actual,key=lambda v:(-actual[v],v))==cur,'strict actual complete row argmax')
                        hx=(maximum+(maximum-actual[target])+1).hex();expected_edit={'store':'Q','address':a+[target],'value_hex':hx};maps['Q'][tuple(a+[target])]=hx
                    elif ch=='D':
                        nominal=min(qrows[tuple(a)],key=lambda v:(-qrows[tuple(a)][v],v));v=None if target==nominal else target;expected_edit={'store':'D','address':a,'value':v}
                        if v is None:maps['D'].pop(tuple(a),None)
                        else:maps['D'][tuple(a)]=v
                    else:
                        v=None if target==a[-1] else target;expected_edit={'store':'X','address':a,'value':v}
                        if v is None:maps['X'].pop(tuple(a),None)
                        else:maps['X'][tuple(a)]=v
                    post={k:sorted([[list(aa) if isinstance(aa,tuple) else aa,v] for aa,v in m.items()]) for k,m in maps.items()};ref=oldmatch(arch,hid,post,original['post'])
                    want={'installation':arch,'full_literal_installation_index':fid,'single_edit':expected_edit,'planned_full_post_store_sha256':sha256(canonical(post)).hexdigest(),'planned_original_post_fingerprint':fp(post),'exact_old_native_reference':ref,'new_native_required':ref is None,'B1_update_law':False}
                    require(task==want and fp(post)!=fp(base),'same actual fullpre one edit, not joint therapy')
                    counts['post_exact_old_native_reuse' if ref else 'post_requires_new_measurement']+=1
        elif t=='FULL_WORLD_NATIVE_PLAN_DECODER':
            i=o['world_projection_index'];w=worlds[i];dec=v53dec[i]
            require(o['full_literal_installation_index']==install_order[w['region']['full_world_literal_sha256']] and o['complete_original_support_row_sha256']==sha256(canonical(w)).hexdigest() and o['complete_v52_decoder_row_sha256']==v52dec[i] and o['complete_v53_aggregate_decoder_row_sha256']==sha256(canonical(dec)).hexdigest(),'all fullworld chain refs')
            require(o['all48_actual_pre_history_indices']==w['all48_pre_history_indices'] and o['all_original_six_support_slices']==w['six_support_slices'] and o['original_entry_status']==w['region']['entry_status'] and o['null_projection_not_zero']==(w['six_support_slices'] is None) and o['original_aggregate_kernel_reference']==dec['ordered_aggregate_kernel_reference'],'ALL48/six/null/entry preserved')
        elif t=='INPUT_BINDING_AFTER':require(o==before==bind(c),'all runtime unchanged')
        elif t=='FINAL':final=o
        else:raise AssertionError('unexpected new native plan output')
    registry={t:endhash(h) for t,h in regs.items()}
    require(dict(sizes)=={'NATIVE_FULL_LITERAL_INSTALLATION':62732,'ALL_HISTORY_NATIVE_PRE_DESCRIPTOR':67147,'ALL_TARGET_NATIVE_POST_DESCRIPTOR':7188,'FULL_WORLD_NATIVE_PLAN_DECODER':68586},'complete ALL native descriptor inventory')
    require(final['plan']==plan and final['counts']==dict(counts) and final['old_index']==oldstats and final['registry_sizes']==dict(sizes) and final['registries']==registry and final['all_inputs_equal'],'complete FINAL fields')
    require(all(final[k]==0 for k in ('actual_new_RFL_kernel_steps','actual_new_learner_rollouts','actual_B1_arms','new_ordered_aggregate_calculations','new_post_predictions','keys_allocated','random_draws','future_training')),'no native/repeat/prediction/key/training execution')
    require(all(final[k] is False for k in ('historical_native_exclusion_complete','native_calibration_certified','scientific_rules_adopted','scientific_PASS','collection_authorized','collector_executed','research_complete','mechanism_direction_falsified')),'no adopted rule/certificate/refutation')
    for node in ast.walk(ast.parse((HERE/'check_stored.py').read_bytes())):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            names=[n.name.split('.')[0] for n in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]]
            require(all(n in {'collections','hashlib','itertools','pathlib','ast','json','subprocess','sys'} for n in names),'stdlib only, no RFL/candidate/checker/solver import')
    emit('CHECK',{'status':'COMPLETE_NATIVE_ACQUISITION_DESCRIPTOR_AUDIT_NOT_EXECUTION','plan':plan,'counts':dict(counts),'old_index':oldstats,'registries':registry,'registry_sizes':dict(sizes),'all_inputs_equal':True,'runtime_inputs':1218,'parent_HEAD_bindings':1061,'distinct_checkout_validation_inputs':1222,'implementation_independence':'PRIMARY_ONLY_NOT_EXPERT','independent_ALL_pre_reader_closure':True,'native_calibration_certified':False,'historical_native_exclusion_complete':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()

