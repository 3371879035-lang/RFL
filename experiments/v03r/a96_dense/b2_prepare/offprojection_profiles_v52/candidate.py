"""Complete source root response profiles, no RFL/native calibration or science adoption."""
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


def addhash(h,o,i):
    h.update((b',' if i else b'')+canonical(o).rstrip(b'\n'))
def endhash(h):h.update(b']\n');return h.hexdigest()
def main():
    c=read(HERE/'contract.json');binding=bind(c);emit('INPUT_BINDING_BEFORE',binding)
    oldchecks={}
    for name in ('support_check','values_check'):
        rows=list(capture(c['stored'][name]));require(len(rows)==1 and rows[0][0]=='CHECK','old complete independent stored checker receipt')
        oldchecks[name]=rows[0][1]
    catalogs={'D':{},'X':{}};histories={};worlds=[];needed=set()
    hashes={t:sha256(b'[') for t in ('COMPLETE_LEGAL_DOMAIN','PRE_HISTORY','FULL_WORLD_OFFPROJECTION_SUPPORT')};counts=Counter()
    for tag,o in capture(c['stored']['support']):
        if tag in hashes:addhash(hashes[tag],o,counts[tag]);counts[tag]+=1
        if tag=='COMPLETE_LEGAL_DOMAIN':catalogs[o['channel']][o['index']]=o
        elif tag=='PRE_HISTORY':histories[o['index']]=o
        elif tag=='FULL_WORLD_OFFPROJECTION_SUPPORT':
            region=o['region'];ch=region['projection_channel'];ids=o['all48_pre_history_indices']
            E=int(region['joint_region_root_mask_hex'],16) if region['joint_region_root_mask_hex'] is not None else None
            if E is not None:
                own={tuple(a) for a in region['complete_projection_owners']}
                for site,cur,mask in o['all_pre_consulted_site_root_masks']:
                    m=int(mask,16)
                    if m&E and len(catalogs[ch][site]['full_legal_actions'])>1:
                        require(tuple(catalogs[ch][site]['address']) not in own,'ALL E read sites outside complete S')
                        while m:
                            bit=m&-m;i=bit.bit_length()-1;needed.add((ids[i],ch,site));m-=bit
            worlds.append({'support_row_sha256':sha256(canonical(o)).hexdigest(),'value_row_sha256':o['complete_old_value_battery_row_sha256'],
               'region':region,'ids':ids,'incidence':o['all_pre_consulted_site_root_masks'],'slices':o['six_support_slices']})
        elif tag=='FINAL':oldfinal=o
    digests={t:endhash(h) for t,h in hashes.items()}
    require(counts=={'COMPLETE_LEGAL_DOMAIN':19728,'PRE_HISTORY':67147,'FULL_WORLD_OFFPROJECTION_SUPPORT':68586},'ALL source records retained')
    require(digests['COMPLETE_LEGAL_DOMAIN']==oldfinal['catalog_sha256']==oldchecks['support_check']['catalog_sha256']
       and digests['PRE_HISTORY']==oldfinal['history_registry_sha256']==oldchecks['support_check']['history_registry_sha256']
       and digests['FULL_WORLD_OFFPROJECTION_SUPPORT']==oldfinal['registry_sha256']==oldchecks['support_check']['registry_sha256'],'all immutable support registry hashes')
    scopes=sorted(needed);groups={}
    for hid,ch,site in scopes:groups.setdefault((hid,ch),[]).append(site)
    atom_count=sum(len(catalogs[ch][site]['full_legal_actions'])-1 for hid,ch,site in scopes)
    plan={'site_scopes':len(scopes),'D_site_scopes':sum(ch=='D' for hid,ch,site in scopes),
      'X_site_scopes':sum(ch=='X' for hid,ch,site in scopes),'target_atoms':atom_count,
      'history_channel_profiles':len(groups),'scope_sha256':sha256(canonical(scopes)).hexdigest()}
    require(plan==c['pre_only_scope_probe'],'prospective full pre-only scope identity')
    require(len(scopes)<=c['guard']['max_site_scopes'] and atom_count<=c['guard']['max_target_atoms']
      and len(groups)<=c['guard']['max_history_channel_profiles'],'prospective engineering guard before all new post predictions; never trim scope')
    emit('PROFILE_PLAN_BEFORE_NEW_EFFECTS',{'plan':plan,'complete_required_site_scopes':[list(s) for s in scopes],
       'support_registry_sha256':digests['FULL_WORLD_OFFPROJECTION_SUPPORT'],'old_counts':oldfinal['counts'],
       'full_old_domain':oldfinal['domain'],'full_history_registry_sha256':digests['PRE_HISTORY'],'native_calibration_certified':False})
    # Exact read-only reuse of old completed fixed targets. No completed post prediction rerun.
    known={};old_values_sha=sha256(b'[');rownum=0;oldtargets=0;oldzeros=0
    address_lookup={ch:{tuple(v['address']):i for i,v in catalogs[ch].items()} for ch in ('D','X')}
    for tag,o in capture(c['stored']['values']):
        if tag!='ACTUAL_PRE_VALUE_AND_CALIBRATION_BATTERY':continue
        w=worlds[rownum];require(w['region']==o['region'] and w['value_row_sha256']==sha256(canonical(o)).hexdigest(),'full v50/v51 row binding')
        ids=w['ids'];ch=w['region']['projection_channel'];inc={s:(cur,int(m,16)) for s,cur,m in w['incidence']}
        lookup=address_lookup[ch]
        for b in o['calibration_batteries']:
            oldzeros+=b['status']=='ALL_TARGETS_ZERO_UNCERTIFIED';site=lookup[tuple(b['address'])];cur,mask=inc[site]
            require(cur==b['actual_pre_action'],'old actual output unchanged')
            for target in b['targets']:
                oldtargets+=1;repl={r:(v,outcome) for r,v,outcome in target['post_root_replacements']}
                m=mask
                while m:
                    bit=m&-m;i=bit.bit_length()-1;hid=ids[i];key=(hid,ch,site,target['target'])
                    if (hid,ch,site) in needed:
                        value=repl.get(i,(o['actual_pre_root_return_hex'][i],o['actual_pre_root_outcomes'][i]))
                        record={'return_hex':value[0],'outcome':value[1],
                          'old_target_reference':[rownum,b['refinement'],target['target'],sha256(canonical(target)).hexdigest()]}
                        if key in known:require((known[key]['return_hex'],known[key]['outcome'])==value,'same literal descriptor old values agree')
                        else:known[key]=record
                    m-=bit
        addhash(old_values_sha,o,rownum);rownum+=1
    require(rownum==68586 and oldtargets==467314 and oldzeros==2988 and endhash(old_values_sha)==oldfinal['source_v50_registry_sha256']==oldchecks['values_check']['registry_sha256'],'ALL old fixed targets/zeros/values unchanged')
    graph={};basis=None
    for tag,o in capture(c['stored']['graph']):
        if tag=='NATIVE_LEGAL_EDGE':graph.setdefault(tuple(o['pre']),{})[o['command']]=o['result']
    for tag,o in capture(c['stored']['basis']):
        if tag=='NATIVE_BASIS':basis=o['entries']
    require(len(graph)==6254 and sum(map(len,graph.values()))==20588,'complete old graph closure source')
    q={tuple(o['address']):{a:float.fromhex(h) for a,h in o['nominal_Q_row_hex']} for o in catalogs['D'].values()}
    default={a:min(row,key=lambda v:(-row[v],v)) for a,row in q.items()}
    Dindex={tuple(o['address']):i for i,o in catalogs['D'].items()}
    Xindex={tuple(o['address']):i for i,o in catalogs['X'].items()}
    def predict(h,ch,site,target):
        D={tuple(a):t for a,t in h['relevant_D_declarations']};X={tuple(a):t for a,t in h['relevant_X_declarations']}
        address=tuple(catalogs[ch][site]['address']);(D if ch=='D' else X)[address]=target
        n=(0,2,0,*h['root'],0);path=[]
        while True:
            cmd=D.get(n,default[n]);xs=n[:5]+(cmd,);u=X.get(xs,cmd);require(u in q[n],'complete original output admissibility')
            v=graph[n][u];path.append([Dindex[n],cmd,u,v['reward_hex'],v['post'],v['terminal'],v['outcome']])
            if v['terminal']:break
            n=tuple(v['post'])
        return {'complete_path':path,'return_hex':sum(float.fromhex(v[3]) for v in path).hex(),'outcome':path[-1][-1]}
    profiles={};profile_sha=sha256(b'[');stats=Counter();nprofiles=0
    for (hid,ch),sites in sorted(groups.items()):
        h=histories[hid];current={}
        for row in h['complete_path']:
            a=tuple(catalogs['D'][row[0]]['address']);siteD=row[0];siteX=Xindex[a[:5]+(row[1],)]
            current[siteD if ch=='D' else siteX]=row[1] if ch=='D' else row[2]
        edits=[]
        for site in sites:
            cur=current[site]
            for target in catalogs[ch][site]['full_legal_actions']:
                if target==cur:continue
                key=(hid,ch,site,target)
                if key in known:
                    post={**known[key],'complete_path':None};role='EXACT_OLD_FIXED_TARGET_VALUE_REUSED_NOT_NEW_PREDICTION';stats['old_atom_values_reused']+=1
                else:
                    post=predict(h,ch,site,target);role='NEW_SOURCE_GRAPH_ROOT_PREDICTION_NOT_NATIVE';stats['new_root_predictions']+=1
                delta=float.fromhex(h['return_hex'])-float.fromhex(post['return_hex'])
                sign='positive' if delta>0 else 'negative' if delta<0 else 'zero'
                stats['local_return_'+sign]+=1;stats[ch+'_atoms']+=1
                edits.append({'site_index':site,'actual_pre_action':cur,'target':target,'role':role,'post':post,'local_pre_minus_post_sign':sign})
        record={'profile_index':nprofiles,'history_index':hid,'channel':ch,'complete_pre_history_sha256':sha256(canonical(h)).hexdigest(),
                'required_site_indices':sites,'all_legal_target_atoms':edits,'native_calibration_certified':False}
        emit('ROOT_SITE_ALL_TARGET_PROFILE',record);addhash(profile_sha,record,nprofiles);profiles[hid,ch]=nprofiles;nprofiles+=1
    require(sum(stats[ch+'_atoms'] for ch in ('D','X'))==atom_count,'ALL legal other target atoms exactly once')
    worldsha=sha256(b'[')
    for i,w in enumerate(worlds):
        E=int(w['region']['joint_region_root_mask_hex'],16) if w['region']['joint_region_root_mask_hex'] is not None else None;ch=w['region']['projection_channel']
        refs=[profiles.get((h,ch)) for h in w['ids']] if E is not None else None
        if E is not None:
            for site,cur,m in w['incidence']:
                mask=int(m,16)
                if mask&E and len(catalogs[ch][site]['full_legal_actions'])>1:
                    while mask:
                        bit=mask&-mask;j=bit.bit_length()-1;require((w['ids'][j],ch,site) in needed and refs[j] is not None,'full ALL reader closure including outside E');mask-=bit
        record={'world_projection_index':i,'complete_original_support_row_sha256':w['support_row_sha256'],
          'full_world_literal_sha256':w['region']['full_world_literal_sha256'],'projection_channel':ch,
          'entry_status':w['region']['entry_status'],'all48_actual_pre_history_indices':w['ids'],
          'all48_channel_profile_references':refs,'six_original_support_slices':w['slices'],
          'full_original_region_Gamma_declarations_decoder':'exact bound v51 row at world_projection_index, no fullworld quotient',
          'no_E_reader_region_values_equal_actual_pre':E is not None,
          'outside_E_effects_for_no_E_reader_sites_not_computed_or_imputed':True,
          'native_calibration_certified':False}
        emit('FULL_WORLD_PROFILE_DECODER',record);addhash(worldsha,record,i)
    after=bind(c);require(binding==after,'all complete runtime inputs stable');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'COMPLETE_PREDECLARED_READ_SITE_ROOT_VALUE_PROFILES_NOT_NATIVE_CALIBRATION',
      'plan':plan,'counts':dict(stats),'profile_registry_sha256':endhash(profile_sha),'world_decoder_registry_sha256':endhash(worldsha),
      'complete_projection_rows':len(worlds),'full_pre_histories_retained':len(histories),'old_counts_retained':oldfinal['counts'],
      'source_support_registry_sha256':digests['FULL_WORLD_OFFPROJECTION_SUPPORT'],'source_v50_registry_sha256':oldfinal['source_v50_registry_sha256'],
      'runtime_inputs':1164,'parent_HEAD_bindings':1007,'all_inputs_equal':True,'new_RFL_kernel_steps':0,'new_learner_rollouts':0,
      'B1_arms':0,'reference_DP':0,'learner_DP':0,'keys_allocated':0,'random_draws':0,'future_training':0,'collector_executed':False,
      'new_world_refinement_aggregate_responses_computed':False,'native_calibration_certified':False,
      'scientific_rules_adopted':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False,'mechanism_direction_falsified':False})
if __name__=='__main__':main()
