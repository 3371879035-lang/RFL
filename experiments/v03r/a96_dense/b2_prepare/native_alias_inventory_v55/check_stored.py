"""Keyless stored descriptor alias audit; no RFL, prediction or science execution."""
from collections import Counter
from hashlib import sha1,sha256
from pathlib import Path
import ast,json,subprocess,sys
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]
OUT_BYTES=0
def read(p):return json.loads(p.read_bytes())
def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def require(ok,why):
    if not ok:raise AssertionError(why)
def digest(p,blob=False):
    h=sha1(b'blob '+str(p.stat().st_size).encode()+b'\0') if blob else sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def emit(t,o):
    global OUT_BYTES
    b=t+'='+canonical(o).decode().rstrip('\n');OUT_BYTES+=len(b.encode())+2
    require(OUT_BYTES<=1200000000,'whole output guard, no trimming')
    print(b,flush=True)
def addhash(h,o,i):h.update((b',' if i else b'')+canonical(o).rstrip(b'\n'))
def endhash(h):h.update(b']\n');return h.hexdigest()
def tree():
    return {v.split(b'\t')[1].decode():v.split()[2].decode() for v in subprocess.check_output(['git','ls-tree','-r','-z','HEAD'],cwd=ROOT).split(b'\0') if v}
def bind(c):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'exact parent')
    tr=tree();require(len(tr)==2488,'ALL parent tree paths, no selective historical inventory')
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tr if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound))==(313,153,770,1084),'original extent')
    hashes={}
    for p in sorted(tr):
        require(digest(ROOT/p,True)==tr[p],'full parent HEAD bytes '+p);hashes[p]=digest(ROOT/p)
    for p,h in (sources|native).items():require(hashes[p]==h,'source/native unchanged '+p)
    for n in ('contract.json','candidate.py','execute.py','check_stored.py'):
        p=(HERE/n).relative_to(ROOT).as_posix();require(p not in tr,'new isolated source');hashes[p]=digest(ROOT/p)
    require(len(hashes)==2492,'runtime full tree plus four new sources')
    return {'HEAD':head,'parent_HEAD_bindings':1084,'full_parent_tree_bindings':2488,'runtime_inputs':2492,'input_sha256':hashes}
def capture(info,code=0):
    f=PREP/info[0];cl=read(f/'claim.json');ex=read(f/'exit.json')
    require(ex['native_child_exit_code']==code and all(ex[k]==v for k,v in cl.items()),'actual full capture receipt')
    require(ex['files']['stdout.log']['sha256']==info[1],'capture identity')
    for n,v in ex['files'].items():require({'bytes':(f/n).stat().st_size,'sha256':digest(f/n)}==v,'full stored capture bytes')
    for n,h in ex['inputs'].items():require(digest(f.parent/n)==h,'executed source preserved')
    with (f/'stdout.log').open('rb') as s:
        for ln,line in enumerate(s,1):
            require(line.endswith(b'\n'),'whole prefix EOF');t,b=line.rstrip(b'\r\n').split(b'=',1);o=json.loads(b)
            require(canonical(o).rstrip(b'\n')==b,'every stored canonical JSON')
            yield ln,t.decode(),o
def fp(st):
    parts=[]
    for ch in ('D','P','X','Q'):
        if ch=='P':lines=[f'P:{a},{v}' for a,v in st[ch]]
        elif ch=='Q':lines=['Q:'+','.join(map(str,a))+'|'+v for a,v in st[ch]]
        else:lines=[ch+':'+','.join(map(str,a+[v])) for a,v in st[ch]]
        parts.append('\n'.join(sorted(lines)).encode())
    return sha256(b'\0'.join(parts)).hexdigest()
def all_entries(st):
    require(set(st)=={'D','P','Q','X'},'complete four store channels')
    out={}
    for ch,vs in st.items():
        addresses=[tuple(a) if isinstance(a,list) else a for a,v in vs]
        require(len(addresses)==len(set(addresses)),'duplicate address rejected, no discarded entry')
        out[ch]=sorted(vs)
    require(fp(out)==fp(st),'entry-order only normalization')
    return out
def descriptor_rows(c):
    sizes=Counter();regs={t:sha256(b'[') for t in c['v54_registry_sizes']}
    for name,code in [('plan_prefix',1),('plan_completed',0)]:
        for ln,t,o in capture(c['stored'][name],code):
            if t in regs:
                index=o.get('installation_index',o.get('history_index') if t=='ALL_HISTORY_NATIVE_PRE_DESCRIPTOR' else o.get('profile_index') if t=='ALL_TARGET_NATIVE_POST_DESCRIPTOR' else o.get('world_projection_index'))
                require(index==sizes[t],'complete composite v54 descriptor order')
                addhash(regs[t],o,sizes[t]);sizes[t]+=1
                yield name,ln,t,o
            elif t=='FINAL':require(o['registry_sizes']==c['v54_registry_sizes'] and o['registries']==c['v54_registries'],'complete old footer')
    require(dict(sizes)==c['v54_registry_sizes'] and {t:endhash(h) for t,h in regs.items()}==c['v54_registries'],'ALL original v54 registries')
    checks=list(capture(c['stored']['plan_check']))
    require(len(checks)==1 and checks[0][1]=='CHECK' and checks[0][2]['registries']==c['v54_registries'],'old independent checker binding')
def wants(c):
    hs={};posts={}
    for ln,t,o in capture(c['stored']['support']):
        if t=='PRE_HISTORY':hs[o['index']]=o
    for ln,t,o in capture(c['stored']['profiles']):
        if t=='ROOT_SITE_ALL_TARGET_PROFILE':
            posts[o['profile_index']]=o
    require(len(hs)==67147 and len(posts)==7188,'ALL original stored expectations; no new prediction')
    return hs,posts
def requested_input(arch,root):
    return {'installation':arch,'root':root,'scene':[root[0],root[1],0,0,root[2]],'initial_state':[0,2,0,root[0],root[1]],'initial_committed_option':root[2],'initial_automaton_memory':0,'learner_policy':'ORIGINAL_GREEDY_STRICT_ARGMAX_MIN_ACTION','reference_name':'v31-stored-nominal-no-DP','nominal_Q_reference_sha256':'d9078b5b5b823df56f998e8c28eb6a3e388bd3ae216f41a21acdb5202d2ec05a','mask_do':None,'P_identity':True,'training':False}
def history_inventory(before):
    tr=tree()
    for p in sorted(tr):
        f=ROOT/p
        yield {'path':p,'HEAD_blob_sha1':tr[p],'bytes':f.stat().st_size,'sha256':before['input_sha256'][p],
               'historical_exact_native_exclusion_status':'PENDING_SOURCE_CONTRACT_AND_FULL_MEASUREMENT_INDEX',
               'not_native_execution_or_reuse_certificate':True}

def main():
    c=read(HERE/'contract.json');before=bind(c);hs,profiles=wants(c)
    installations={};records=[];worlds=[];pre_desc={}
    def append(kind,sn,ln,d,slot,task,root,st,want):
        normalized={};source_maps={}
        require(set(st)=={'D','P','Q','X'},'all four stores independent')
        for channel,vs in st.items():
            pairs=[(tuple(a) if isinstance(a,list) else a,v) for a,v in vs]
            require(len(dict(pairs))==len(pairs),'duplicate entry forbidden')
            normalized[channel]=[[list(a) if isinstance(a,tuple) else a,v] for a,v in sorted(pairs)]
        wire=canonical(normalized);spec=requested_input(task['installation'],root)
        source_ref={'v54_capture':c['stored'][sn][0],'line':ln,'complete_descriptor_sha256':sha256(canonical(d)).hexdigest(),'kind':kind,'task_slot':slot}
        records.append({'kind':kind,'wire':wire,'input':canonical(spec),'spec':spec,'source':source_ref,'old':task['exact_old_native_reference'],'want':want})
    for sn,ln,t,o in descriptor_rows(c):
        if t=='NATIVE_FULL_LITERAL_INSTALLATION':installations[o['installation_index']]=o['all_original_store_bytes_by_architecture']
        elif t=='ALL_HISTORY_NATIVE_PRE_DESCRIPTOR':
            hid=o['history_index'];h=hs[hid];require(o['complete_history_sha256']==sha256(canonical(h)).hexdigest(),'full original history')
            pre_desc[hid]=[]
            for si,task in enumerate(o['native_pre_tasks']):
                pre_desc[hid].append(len(records));st=installations[task['full_literal_installation_index']][task['installation']]
                append('pre',sn,ln,o,[si],task,o['root'],st,{k:h[k] for k in ('return_hex','outcome','complete_path')})
        elif t=='ALL_TARGET_NATIVE_POST_DESCRIPTOR':
            p=profiles[o['profile_index']];require(o['complete_original_profile_sha256']==sha256(canonical(p)).hexdigest(),'whole original profile')
            for ai,(atom,wantatom) in enumerate(zip(o['all_legal_other_target_descriptors'],p['all_legal_target_atoms'],strict=True)):
                require((atom['site_index'],atom['target'],atom['actual_pre_action'])==(wantatom['site_index'],wantatom['target'],wantatom['actual_pre_action']),'ALL targets unchanged')
                for si,task in enumerate(atom['native_post_tasks']):
                    base=installations[task['full_literal_installation_index']][task['installation']]
                    maps={ch:{tuple(a) if isinstance(a,list) else a:v for a,v in vs} for ch,vs in base.items()}
                    require(all(len(maps[ch])==len(base[ch]) for ch in base),'whole base no duplicate')
                    edit=task['single_edit'];ch=edit['store'];addr=tuple(edit['address']);value=edit['value_hex'] if ch=='Q' else edit['value']
                    if value is None:maps[ch].pop(addr,None)
                    else:maps[ch][addr]=value
                    st={ch:[[list(a) if isinstance(a,tuple) else a,v] for a,v in sorted(m.items())] for ch,m in maps.items()}
                    require(sha256(canonical(st)).hexdigest()==task['planned_full_post_store_sha256'] and fp(st)==task['planned_original_post_fingerprint'],'every planned complete post store')
                    append('post',sn,ln,o,[ai,si],task,hs[o['history_index']]['root'],st,{k:wantatom['post'][k] for k in ('return_hex','outcome','complete_path')})
        else:worlds.append(o)
    require(len(records)==279158 and len(installations)==62732 and len(worlds)==68586 and len(pre_desc)==67147,'ALL original support')
    # Independent full byte sort/group, not candidate hash dictionary or response selection.
    ordered=sorted(range(len(records)),key=lambda i:(records[i]['input'],records[i]['wire'],i));groups=[]
    for i in ordered:
        r=records[i]
        if not groups or (r['input'],r['wire'])!=groups[-1]['signature']:groups.append({'signature':(r['input'],r['wire']),'ids':[]})
        groups[-1]['ids'].append(i)
    groups.sort(key=lambda g:min(g['ids']));alias_map={};counts=Counter();unique=[]
    for ix,g in enumerate(groups):
        ids=g['ids'];first=min(ids);r=records[first];expected=dict(r['want'])
        for i in ids:
            v=records[i];alias_map[i]=ix;require(v['want']['return_hex']==expected['return_hex'] and v['want']['outcome']==expected['outcome'],'independent same-input source consistency')
            oldpath,newpath=expected['complete_path'],v['want']['complete_path']
            require(oldpath is None or newpath is None or oldpath==newpath,'every known path on exact byte aliases')
            if oldpath is None and newpath is not None:expected['complete_path']=newpath
            require((v['old'] is None)==(r['old'] is None),'same complete input old reuse')
            kind=v['kind'];counts[kind+'_descriptors']+=1;counts[kind+('_old_v46_v47_reused_descriptors' if v['old'] else '_pending_descriptors')]+=1
        counts['unique_keys']+=1;counts['unique_old_v46_v47_keys' if r['old'] else 'unique_pending_all_history_audit_keys']+=1
        st=json.loads(r['wire'])
        unique.append({'index':ix,'complete_requested_input':r['spec'],'full_four_store_entries':st,'full_store_sha256':sha256(r['wire']).hexdigest(),'original_fingerprint':fp(st),
          'first_descriptor_reference':r['source'],'complete_descriptor_alias_count':len(ids),'exact_old_native_v46_v47_reference':r['old'],
          'stored_source_expectation_not_measurement':expected,'all_history_exclusion_pending':True,'native_execution_authorized':False})
    expected_inv=list(history_inventory(before));sizes=Counter();regs={t:sha256(b'[') for t in ('HISTORICAL_PARENT_FILE_INVENTORY','DESCRIPTOR_EXACT_INPUT_ALIAS','UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY','UNCHANGED_WORLD_DESCRIPTOR_REFERENCE')}
    final=None
    for ln,t,o in capture(['native_alias_inventory_v55/evidence',read(HERE/'evidence/exit.json')['files']['stdout.log']['sha256']]):
        if t in regs:addhash(regs[t],o,sizes[t]);sizes[t]+=1
        if t=='INPUT_BINDING_BEFORE':require(o==before,'full source before')
        elif t=='PRE_ONLY_COMPLETE_ALIAS_GUARD':require(o=={'maximum_original_descriptors':279158,'maximum_unique_keys':279158,'maximum_prospective_raw_steps_before_reuse':3349896,'guard':c['guard'],'historical_exclusion_not_closed':True,'native_launch_gate':False},'pre-only complete guard before aliases')
        elif t=='HISTORICAL_PARENT_FILE_INVENTORY':require(o==expected_inv[sizes[t]-1],'ALL parent paths and exact whole bytes')
        elif t=='DESCRIPTOR_EXACT_INPUT_ALIAS':
            i=sizes[t]-1;r=records[i];st=json.loads(r['wire'])
            require(o=={'descriptor_index':i,'source_descriptor':r['source'],'unique_execution_key_index':alias_map[i],'complete_requested_input_sha256':sha256(r['input']).hexdigest(),'full_store_sha256':sha256(r['wire']).hexdigest(),'original_fingerprint':fp(st),
                'exact_old_native_v46_v47_reference':r['old'],'all_history_exclusion_pending':True,'not_native_execution':True},'independently sorted complete input alias')
        elif t=='UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':require(o==unique[sizes[t]-1],'all unique complete input and aliases')
        elif t=='UNCHANGED_WORLD_DESCRIPTOR_REFERENCE':
            w=worlds[sizes[t]-1];hid=w['all48_actual_pre_history_indices']
            want={'world_projection_index':w['world_projection_index'],'complete_v54_world_decoder_sha256':sha256(canonical(w)).hexdigest(),'complete_original_support_row_sha256':w['complete_original_support_row_sha256'],'full_world_literal_sha256':w['full_world_literal_sha256'],
                'all48_actual_pre_history_indices':hid,'all48_representative_pre_execution_key_indices_by_architecture':[[alias_map[pre_desc[h][a]] for h in hid] for a in (0,1)],'original_entry_status':w['original_entry_status'],'null_projection_not_zero':w['null_projection_not_zero'],
                'complete_original_six_support_slices_sha256':None if w['all_original_six_support_slices'] is None else sha256(canonical(w['all_original_six_support_slices'])).hexdigest(),
                'representative_native_input_is_not_full_world_state_alias':True,'local_declaration_source_factorization_only':True,'outside_E_effects_not_imputed_zero':True}
            require(o==want,'all unchanged world/48/six/null/entry refs, no scientific quotient')
        elif t=='INPUT_BINDING_AFTER':require(o==before==bind(c),'all runtime beforeafter')
        elif t=='FINAL':final=o
        else:raise AssertionError('unexpected new alias capture tag')
    registry={t:endhash(h) for t,h in regs.items()}
    require(final is not None and final['counts']==dict(counts) and final['registries']==registry and final['registry_sizes']==dict(sizes),'whole counts/registries')
    require(dict(sizes)=={'HISTORICAL_PARENT_FILE_INVENTORY':2488,'DESCRIPTOR_EXACT_INPUT_ALIAS':279158,'UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY':len(groups),'UNCHANGED_WORLD_DESCRIPTOR_REFERENCE':68586},'complete ALL panels')
    require(final['planned_fullstate_root_alias_reconciliation_complete'] and not final['historical_native_exclusion_complete'],'alias closure not historical gate')
    require(final['exact_duplicate_descriptors']==279158-len(groups) and final['prospective_unique_pending_rollout_upper_bound_not_launch_gate']==counts['unique_pending_all_history_audit_keys'],'exact alias counts not native counts')
    require(all(final[k]==0 for k in ('actual_new_RFL_kernel_steps','actual_new_learner_rollouts','actual_B1_arms','new_predictions','new_ordered_aggregates','keys_allocated','random_draws','future_training')),'no native/prediction/repeat/key/training')
    require(all(final[k] is False for k in ('collector_executed','collection_authorized','native_calibration_certified','scientific_rules_adopted','scientific_PASS','research_complete','mechanism_direction_falsified','historical_complete_measurement_source_audit_closed')),'no scientific/gate/refutation adoption')
    for n in ('candidate.py','check_stored.py'):
        for node in ast.walk(ast.parse((HERE/n).read_bytes())):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[v.name.split('.')[0] for v in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]]
                require(all(x in {'collections','hashlib','pathlib','ast','json','subprocess','sys'} for x in names),'stdlib only no old candidate/checker/RFL imports')
    emit('CHECK',{'status':'COMPLETE_INDEPENDENT_FULL_BYTE_SORT_ALIAS_AUDIT_NOT_NATIVE_GATE','counts':dict(counts),'registries':registry,'registry_sizes':dict(sizes),'all_inputs_equal':True,
      'planned_fullstate_root_alias_reconciliation_complete':True,'historical_native_exclusion_complete':False,'parent_HEAD_bindings':1084,'full_parent_tree_bindings':2488,'runtime_inputs':2492,
      'distinct_checkout_validation_inputs':2496,'implementation_independence':'PRIMARY_ONLY_NOT_EXPERT','native_calibration_certified':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False})
if __name__=='__main__':main()

