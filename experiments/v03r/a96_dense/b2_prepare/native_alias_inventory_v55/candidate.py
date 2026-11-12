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
    c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    emit('PRE_ONLY_COMPLETE_ALIAS_GUARD',{'maximum_original_descriptors':279158,'maximum_unique_keys':279158,'maximum_prospective_raw_steps_before_reuse':3349896,'guard':c['guard'],'historical_exclusion_not_closed':True,'native_launch_gate':False})
    regs={t:sha256(b'[') for t in ('HISTORICAL_PARENT_FILE_INVENTORY','DESCRIPTOR_EXACT_INPUT_ALIAS','UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY','UNCHANGED_WORLD_DESCRIPTOR_REFERENCE')};sizes=Counter()
    def record(t,o):
        addhash(regs[t],o,sizes[t]);sizes[t]+=1;emit(t,o)
    for row in history_inventory(before):record('HISTORICAL_PARENT_FILE_INVENTORY',row)
    hs,profiles=wants(c);stores=[];prekeys={};keys={};table=[];counts=Counter();worlds=[]
    def task_record(kind,source_name,line,descriptor,slot,task,root,st,want):
        st=all_entries(st);wire=canonical(st);statehash=sha256(wire).hexdigest();input_spec=requested_input(task['installation'],root)
        signature=canonical(input_spec);lookupkey=(signature,statehash)
        ref={'v54_capture':c['stored'][source_name][0],'line':line,'complete_descriptor_sha256':sha256(canonical(descriptor)).hexdigest(),'kind':kind,'task_slot':slot}
        ix=keys.get(lookupkey)
        if ix is None:
            ix=len(table);keys[lookupkey]=ix
            table.append({'index':ix,'input':input_spec,'wire':wire,'store_sha256':statehash,'fingerprint':fp(st),'first_descriptor':ref,'expected':want,'aliases':0,'old_ref':task['exact_old_native_reference']})
        row=table[ix]
        require(row['wire']==wire and canonical(row['input'])==signature,'every full entry and requested input exact, not hash-only')
        require(row['expected']['return_hex']==want['return_hex'] and row['expected']['outcome']==want['outcome'],'same fullinput source value consistent')
        p0,p1=row['expected']['complete_path'],want['complete_path']
        require(p0 is None or p1 is None or p0==p1,'all known source fullpaths exact on aliases')
        if p0 is None and p1 is not None:row['expected']=want
        require((row['old_ref'] is None)==(task['exact_old_native_reference'] is None),'same exact input old46/47 reuse status')
        row['aliases']+=1;counts[kind+'_descriptors']+=1
        counts[kind+('_old_v46_v47_reused_descriptors' if task['exact_old_native_reference'] else '_pending_descriptors')]+=1
        record('DESCRIPTOR_EXACT_INPUT_ALIAS',{'descriptor_index':sizes['DESCRIPTOR_EXACT_INPUT_ALIAS'],'source_descriptor':ref,
                'unique_execution_key_index':ix,'complete_requested_input_sha256':sha256(signature).hexdigest(),'full_store_sha256':statehash,'original_fingerprint':row['fingerprint'],
                'exact_old_native_v46_v47_reference':task['exact_old_native_reference'],'all_history_exclusion_pending':True,'not_native_execution':True})
        return ix
    for source_name,line,t,o in descriptor_rows(c):
        if t=='NATIVE_FULL_LITERAL_INSTALLATION':
            require(o['installation_index']==len(stores),'all original stores order')
            stores.append(o['all_original_store_bytes_by_architecture'])
        elif t=='ALL_HISTORY_NATIVE_PRE_DESCRIPTOR':
            hid=o['history_index'];h=hs[hid];require(o['complete_history_sha256']==sha256(canonical(h)).hexdigest() and o['root']==h['root'],'original complete history')
            want={k:h[k] for k in ('return_hex','outcome','complete_path')}
            indices=[]
            for slot,task in enumerate(o['native_pre_tasks']):
                st=stores[task['full_literal_installation_index']][task['installation']]
                indices.append(task_record('pre',source_name,line,o,[slot],task,o['root'],st,want))
            prekeys[hid]=indices
        elif t=='ALL_TARGET_NATIVE_POST_DESCRIPTOR':
            p=profiles[o['profile_index']];hid=o['history_index'];root=hs[hid]['root']
            require(o['complete_original_profile_sha256']==sha256(canonical(p)).hexdigest() and len(o['all_legal_other_target_descriptors'])==len(p['all_legal_target_atoms']),'ALL original profile atoms')
            for ai,(atom,oldatom) in enumerate(zip(o['all_legal_other_target_descriptors'],p['all_legal_target_atoms'],strict=True)):
                require((atom['site_index'],atom['target'],atom['actual_pre_action'])==(oldatom['site_index'],oldatom['target'],oldatom['actual_pre_action']),'target identity unfiltered')
                for slot,task in enumerate(atom['native_post_tasks']):
                    base=stores[task['full_literal_installation_index']][task['installation']]
                    st={ch:list(vs) for ch,vs in base.items()};edit=task['single_edit'];ch=edit['store'];address=edit['address'];v=edit.get('value_hex',edit.get('value'))
                    st[ch]=[entry for entry in st[ch] if entry[0]!=address]+([] if v is None else [[address,v]])
                    st=all_entries(st);require(sha256(canonical(st)).hexdigest()==task['planned_full_post_store_sha256'] and fp(st)==task['planned_original_post_fingerprint'],'stored single edit exact, no scalar recomputation')
                    task_record('post',source_name,line,o,[ai,slot],task,root,st,{k:oldatom['post'][k] for k in ('return_hex','outcome','complete_path')})
        else:worlds.append((source_name,line,o))
    require(len(table)<=c['guard']['max_unique_fullstate_root_keys'] and sizes['DESCRIPTOR_EXACT_INPUT_ALIAS']==279158<=c['guard']['max_descriptor_aliases'],'ALL279158, no trimming')
    for row in table:
        record('UNIQUE_FULLSTATE_ROOT_EXECUTION_KEY',{'index':row['index'],'complete_requested_input':row['input'],'full_four_store_entries':json.loads(row['wire']),
            'full_store_sha256':row['store_sha256'],'original_fingerprint':row['fingerprint'],'first_descriptor_reference':row['first_descriptor'],
            'complete_descriptor_alias_count':row['aliases'],'exact_old_native_v46_v47_reference':row['old_ref'],
            'stored_source_expectation_not_measurement':row['expected'],'all_history_exclusion_pending':True,'native_execution_authorized':False})
        counts['unique_keys']+=1
        counts['unique_old_v46_v47_keys' if row['old_ref'] else 'unique_pending_all_history_audit_keys']+=1
    for source_name,line,o in worlds:
        hid=o['all48_actual_pre_history_indices']
        record('UNCHANGED_WORLD_DESCRIPTOR_REFERENCE',{'world_projection_index':o['world_projection_index'],'complete_v54_world_decoder_sha256':sha256(canonical(o)).hexdigest(),
            'complete_original_support_row_sha256':o['complete_original_support_row_sha256'],'full_world_literal_sha256':o['full_world_literal_sha256'],
            'all48_actual_pre_history_indices':hid,'all48_representative_pre_execution_key_indices_by_architecture':[[prekeys[i][a] for i in hid] for a in (0,1)],
            'original_entry_status':o['original_entry_status'],'null_projection_not_zero':o['null_projection_not_zero'],
            'complete_original_six_support_slices_sha256':None if o['all_original_six_support_slices'] is None else sha256(canonical(o['all_original_six_support_slices'])).hexdigest(),
            'representative_native_input_is_not_full_world_state_alias':True,'local_declaration_source_factorization_only':True,'outside_E_effects_not_imputed_zero':True})
    require(sizes['HISTORICAL_PARENT_FILE_INVENTORY']==2488 and sizes['UNCHANGED_WORLD_DESCRIPTOR_REFERENCE']==68586 and len(prekeys)==67147,'whole parent/world/history identities')
    after=bind(c);require(before==after,'full parent and runtime bytes unchanged');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'COMPLETE_EXACT_PLAN_INPUT_ALIAS_AND_PARENT_BYTE_INVENTORY_NOT_NATIVE_GATE','counts':dict(counts),'registry_sizes':dict(sizes),'registries':{t:endhash(h) for t,h in regs.items()},
        'planned_fullstate_root_alias_reconciliation_complete':True,'historical_native_exclusion_complete':False,'historical_parent_inventory_complete':True,
        'historical_complete_measurement_source_audit_closed':False,'preserved_untracked_baseline_directories_not_audited':True,
        'original_descriptor_count':279158,'exact_duplicate_descriptors':279158-len(table),'prospective_unique_pending_rollout_upper_bound_not_launch_gate':counts['unique_pending_all_history_audit_keys'],
        'prospective_unique_pending_raw_step_upper_bound_not_science_resource_certificate':12*counts['unique_pending_all_history_audit_keys'],
        'all_inputs_equal':True,'parent_HEAD_bindings':1084,'full_parent_tree_bindings':2488,'runtime_inputs':2492,
        'actual_new_RFL_kernel_steps':0,'actual_new_learner_rollouts':0,'actual_B1_arms':0,'new_predictions':0,'new_ordered_aggregates':0,
        'keys_allocated':0,'random_draws':0,'future_training':0,'collector_executed':False,'collection_authorized':False,'native_calibration_certified':False,
        'scientific_rules_adopted':False,'scientific_PASS':False,'research_complete':False,'mechanism_direction_falsified':False})
if __name__=='__main__':main()

