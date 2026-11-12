"""Complete pre-only offprojection support, no post effects or native measurement."""
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

def main():
    c=read(HERE/'contract.json');binding=bind(c);emit('INPUT_BINDING_BEFORE',binding)
    q={};graph={};basis=None
    for tag,o in capture(c['stored']['catalog']):
        if tag=='DECISION_CONTEXT':q[tuple(o['context'])]={a:float.fromhex(v) for a,v in o['q_row_hex']}
    for tag,o in capture(c['stored']['graph']):
        if tag=='NATIVE_LEGAL_EDGE':graph.setdefault(tuple(o['pre']),{})[o['command']]=o['result']
    for tag,o in capture(c['stored']['basis']):
        if tag=='NATIVE_BASIS':basis=o['entries']
    require((len(q),len(graph),sum(map(len,graph.values())))==(13824,6254,20588),'full domain graph')
    roots=[(k,p,z) for k in range(2) for p in range(6) for z in range(4)]
    greedy={n:min(row,key=lambda a:(-row[a],a)) for n,row in q.items()}
    serving={};readable=set()
    for n,row in q.items():
        for cmd in row:
            site=n[:5]+(cmd,);serving[site]=set(row) if site not in serving else serving[site]&set(row)
            if n in graph:readable.add(site)
    domains={'D':list(q),'X':sorted(serving,key=lambda s:(s[2],s[0],s[1],*s[3:]))}
    indices={ch:{s:i for i,s in enumerate(v)} for ch,v in domains.items()}
    legal={'D':{a:set(v) for a,v in q.items()},'X':serving}
    defaults={'D':greedy,'X':{s:s[-1] for s in serving}}
    base={ch:{'domain_sites':len(v),'legal_sites':sum(len(legal[ch][a])>1 for a in v),
              'legal_targets':sum(len(legal[ch][a])-1 for a in v),
              'structurally_unreachable_sites':sum(a not in (graph if ch=='D' else readable) for a in v),
              'unreachable_legal_sites':sum(a not in (graph if ch=='D' else readable) and len(legal[ch][a])>1 for a in v),
              'unreachable_legal_targets':sum(len(legal[ch][a])-1 for a in v if a not in (graph if ch=='D' else readable))}
          for ch,v in domains.items()}
    catsha=sha256(b'[');nc=0
    for ch in ('D','X'):
        for i,a in enumerate(domains[ch]):
            record={'channel':ch,'index':i,'address':list(a),'full_legal_actions':sorted(legal[ch][a]),
                    'default_effective_pre_action':defaults[ch][a],
                    'pre_only_other_target_count':len(legal[ch][a])-1,
                    'structurally_reachable':a in (graph if ch=='D' else readable)}
            if ch=='D':record['nominal_Q_row_hex']=[[v,h.hex()] for v,h in q[a].items()]
            emit('COMPLETE_LEGAL_DOMAIN',record);catsha.update((b',' if nc else b'')+canonical(record).rstrip(b'\n'));nc+=1
    catsha.update(b']\n')
    emit('SUPPORT_ENCODING',{'roots':[list(r) for r in roots],'full_scenes':5760,'scene_order':['kappa','phase','error','cause_rank','base_option'],
          'six_refinements':c['six_refinements'],'domain':base,'catalog_sha256':catsha.hexdigest(),
          'full_target_decoder':'for every catalog address outside full S: all legal actions minus current full-pre exception or catalog default, including unread sites',
          'history_references':'cache only; full-world identity/S/declarations retained per record; root readers never independent N',
          'unread_first_hit_not_measured_effect':True})
    memo={};historysha=sha256(b'[')
    def history(root,D,X,announce=True):
        dd=tuple(sorted((a,t) for a,t in D.items() if a[3:6]==root));xx=tuple(sorted((a,t) for a,t in X.items() if a[3:5]==root[:2]));key=(root,dd,xx)
        if key in memo:return memo[key]
        dm=dict(dd);xm=dict(xx);n=(0,2,0,*root,0);path=[];reads={'D':{},'X':{}}
        while True:
            cmd=dm.get(n,greedy[n]);site=n[:5]+(cmd,);u=xm.get(site,cmd);v=graph[n][u]
            path.append([indices['D'][n],cmd,u,v['reward_hex'],v['post'],v['terminal'],v['outcome']])
            reads['D'][indices['D'][n]]=cmd;reads['X'][indices['X'][site]]=u
            if v['terminal']:break
            n=tuple(v['post'])
        i=len(memo);require(i<c['guard']['max_local_histories'],'predeclared engineering history guard')
        record={'index':i,'root':list(root),'relevant_D_declarations':[[list(a),t] for a,t in dd],
                'relevant_X_declarations':[[list(a),t] for a,t in xx],'complete_path':path,
                'return_hex':sum(float.fromhex(v[3]) for v in path).hex(),'outcome':path[-1][-1]}
        if announce:emit('PRE_HISTORY',record);historysha.update((b',' if i else b'')+canonical(record).rstrip(b'\n'))
        memo[key]=(record,reads);return memo[key]
    # Old basis source binding without new native execution.
    for i,r in enumerate(roots):
        n=(0,2,0,*r,0);packed=[]
        while True:
            a=greedy[n];v=graph[n][a];packed.append([list(n[:5]),n[5],n[6],a,a,a,v['reward_hex'],v['post'][:5],v['post'][5:],v['terminal'],v['outcome'],False])
            if v['terminal']:break
            n=tuple(v['post'])
        require(basis[i]['payload']['trace']==packed and basis[i]['payload']['return_hex']==sum(float.fromhex(v[6]) for v in packed).hex(),'all48 old basis278raw')
    reg=sha256(b'[');oldreg=sha256(b'[');stats=Counter();nrows=0
    for tag,v50 in capture(c['stored']['values']):
        if tag!='ACTUAL_PRE_VALUE_AND_CALIBRATION_BATTERY':continue
        oldreg.update((b',' if nrows else b'')+canonical(v50).rstrip(b'\n'))
        o=v50['region'];D={tuple(a):t for a,t in o['D_declarations']};X={tuple(a):t for a,t in o['X_declarations']}
        hs=[history(r,D,X) for r in roots]
        require([v[0]['return_hex'] for v in hs]==v50['actual_pre_root_return_hex'] and [v[0]['outcome'] for v in hs]==v50['actual_pre_root_outcomes'],'pre history binding to old values')
        ch=o['projection_channel'];own={indices[ch][tuple(a)] for a in o['complete_projection_owners']}
        incidence={}
        for i,(_,reads) in enumerate(hs):
            for a,current in reads[ch].items():
                if a not in incidence:incidence[a]=[current,0]
                require(incidence[a][0]==current,'same literal pre output for all readers')
                incidence[a][1]|=1<<i
        current=D if ch=='D' else X
        exceptions=[[indices[ch][a],t] for a,t in sorted(current.items(),key=lambda v:indices[ch][v[0]])]
        for a,t in current.items():require(t in legal[ch][a],'full domain pre exception legal')
        support_base={**base[ch],'offprojection_domain_sites':len(domains[ch])-len(own),
                      'offprojection_legal_sites':base[ch]['legal_sites']-sum(len(legal[ch][domains[ch][a]])>1 for a in own),
                      'offprojection_legal_targets':base[ch]['legal_targets']-sum(len(legal[ch][domains[ch][a]])-1 for a in own)}
        oldb=[{'refinement':b['refinement'],'address':b.get('address'),'actual_pre_action':b.get('actual_pre_action'),
               'all_legal_other_targets':b.get('all_legal_other_targets',[]),'status':b['status'],
               'complete_old_battery_sha256':sha256(canonical(b)).hexdigest()} for b in v50['calibration_batteries']]
        result={'region':o,'complete_old_value_battery_row_sha256':sha256(canonical(v50)).hexdigest(),
                'all48_pre_history_indices':[v[0]['index'] for v in hs],
                'all_actual_pre_mapping_exceptions':exceptions,
                'full_domain_support':support_base,
                'all_pre_consulted_site_root_masks':[[a,cur,format(mask,'012x')] for a,(cur,mask) in sorted(incidence.items())],
                'prior_fixed_battery_bindings':oldb,'six_support_slices':None,
                'sensitivity_certified':False,'post_effects_computed':False}
        stats['projection_rows']+=1;stats[o['entry_status']]+=1;stats['prior_fixed_batteries_bound']+=len(oldb)
        stats['prior_fixed_target_responses_bound']+=sum(len(b['targets']) for b in v50['calibration_batteries'])
        for b in oldb:
            if b['status']=='ALL_TARGETS_ZERO_UNCERTIFIED':
                stats['old_all_zero_batteries_retained']+=1
                stats['old_failure_all_zero_retained']+=o['entry_status']=='NONEMPTY_COMPLETE_PROJECTION_FAILURE'
        E=int(o['joint_region_root_mask_hex'],16) if o['joint_region_root_mask_hex'] is not None else None
        if E is None:stats['null_projection_support_not_imputed']+=1
        else:
            stats['defined_projection_records']+=1;slices=[]
            for j,name in enumerate(c['six_refinements']):
                mask=E
                if j in (1,2,5):mask &= sum(1<<i for i,(_,p,z) in enumerate(roots) if (p%2==0 if j==1 else p%2==1 if j==2 else z!=0))
                weight=60 if j in (3,4) else 120
                read=[a for a,(_,m) in incidence.items() if a not in own and m&mask and len(legal[ch][domains[ch][a]])>1]
                rt=sum(len(legal[ch][domains[ch][a]])-1 for a in read)
                s={'refinement':name,'region_root_mask_hex':format(mask,'012x'),'scene_count':mask.bit_count()*weight,
                   'read_legal_sites':len(read),'read_legal_targets':rt,
                   'unread_legal_sites_retained':support_base['offprojection_legal_sites']-len(read),
                   'unread_legal_targets_retained':support_base['offprojection_legal_targets']-rt,
                   'read_site_scene_incidence':sum((incidence[a][1]&mask).bit_count()*weight for a in read),
                   'multi_root_shared_read_sites':sum((incidence[a][1]&mask).bit_count()>1 for a in read),
                   'unread_first_hit_behavior_unchanged_source_only':True,'read_does_not_certify_nonzero_response':True}
                require(s['scene_count']==o['six_refinement_counts'][j],'all original slice identities')
                slices.append(s);stats['support_slice_records']+=1
                for k in ('read_legal_sites','read_legal_targets','unread_legal_sites_retained','unread_legal_targets_retained','multi_root_shared_read_sites'):stats[k+'_sum']+=s[k]
                stats['total_site_target_slice_literals']+=rt+s['unread_legal_targets_retained']
            result['six_support_slices']=slices
        emit('FULL_WORLD_OFFPROJECTION_SUPPORT',result);reg.update((b',' if nrows else b'')+canonical(result).rstrip(b'\n'));nrows+=1
    reg.update(b']\n');oldreg.update(b']\n');historysha.update(b']\n')
    require(nrows==68586 and oldreg.hexdigest()=='b2aea023905308ad616df31cbc0e694968285ce5ad50dfaadf85f308d9d5b1b3','complete old calibration rows binding')
    require(stats['old_all_zero_batteries_retained']==2988 and stats['old_failure_all_zero_retained']==145,'all old zeros retained without selection')
    after=bind(c);require(binding==after,'all runtime inputs stable');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'COMPLETE_PRE_ONLY_OFFPROJECTION_SUPPORT_NOT_SENSITIVITY_CERTIFIED','counts':dict(stats),
          'domain':base,'catalog_sha256':catsha.hexdigest(),'history_registry_sha256':historysha.hexdigest(),
          'registry_sha256':reg.hexdigest(),'source_v50_registry_sha256':oldreg.hexdigest(),'source_local_histories':len(memo),
          'runtime_inputs':1141,'parent_HEAD_bindings':984,'all_inputs_equal':True,
          'new_native_kernel_steps':0,'new_learner_rollouts':0,'post_effect_predictions':0,'B1_arms':0,'reference_DP':0,'learner_DP':0,
          'keys_allocated':0,'random_draws':0,'future_training':0,'collector_executed':False,'scientific_rules_adopted':False,
          'scientific_PASS':False,'collection_authorized':False,'research_complete':False,'mechanism_direction_falsified':False})
if __name__=='__main__':main()
