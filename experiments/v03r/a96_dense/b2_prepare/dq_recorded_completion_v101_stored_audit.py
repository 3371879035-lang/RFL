"""V101 independent stdlib stored-content review, no old checker execution.
Shared stdlib geometry/value helper definitions mechanically copied from v100;
its checker/main is NOT imported or executed. No runtime handles reconstructed.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=ROOT/'experiments/v03r/a96_dense/b2_prepare/dq_recorded_completion_v101'
BASE=HERE.parent


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)
def digest(value):return hashlib.sha256(canonical(value).encode('ascii')).hexdigest()
def number(value):return float.fromhex(value['binary64_hex'])
def load(path):return json.loads(path.read_bytes())
def skey(state):return tuple(state[n] for n in ('x','y','t','kappa','phi'))
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def native_truth_tolerance(value):
    # ONLY the native source's documented float tolerance. Q binary64 wire
    # markers and the revised ruler's canonical wire remain unchanged.
    if isinstance(value,list):return [native_truth_tolerance(x) for x in value]
    if isinstance(value,dict):return {k:(number(v) if k=='whole_optimal_set_tolerance'
        else native_truth_tolerance(v)) for k,v in value.items()}
    return value


def mappings(stores):
    d={skey(x['address']['state'])+(x['address']['z'],x['address']['m']):x['value'] for x in stores['D']}
    p={x['address']:x['value'] for x in stores['P']}
    x={skey(v['address']['state'])+(v['address']['cmd'],):v['value'] for v in stores['X']}
    q={skey(v['address']['state'])+(v['address']['z'],v['address']['m'],v['address']['a']):number(v['value']) for v in stores['Q']}
    return d,p,x,q


def compact_store(stores):
    d,p,x,q=mappings(stores)
    return {'D':sorted([[list(k),v] for k,v in d.items()]),'P':sorted([[k,v] for k,v in p.items()]),
            'X':sorted([[list(k),v] for k,v in x.items()]),'Q':sorted([[list(k),v.hex()] for k,v in q.items()])}


def record_pin_update(hasher,scene,trace,comma):
    if comma:hasher.update(b',')
    s=dict(zip(('kappa','phase','error_flag','cause_rank','base_option'),scene))
    hasher.update(canonical({'scene':s,'trace':trace}).encode('ascii'))


OPEN={(x,y) for x in range(5) for y in range(5) if not (x in (0,4) or y==0 or (x,y)==(2,3))}|{(0,2),(4,2)}
DELTAS=((0,-1),(0,1),(-1,0),(1,0),(0,0))


def raw_check(trace,scene,stores,qstar):
    d,p,x,q=mappings(stores)
    assert trace['base_option']==scene[4] and trace['option_in_force']==p.get(scene[4],scene[4])
    assert trace['mask']=={'controller':None,'decision':None,'plant':None,'trap':None}
    assert trace['interventions']=={'members':[]}
    steps=trace['steps'];assert steps and steps[-1]['terminal'] and steps[-1]['outcome']==trace['outcome']
    s=(0,2,0,scene[0],scene[1]);z,m=trace['option_in_force'],0
    consulted={('process',(scene[4],))};nonoptimal=[];controllers=[];rows=[]
    for i,step in enumerate(steps):
        row=qstar[s+(z,m)];vals={a:q.get(s+(z,m,a),v) for a,v in row.items()}
        best=max(vals.values());cmd=d.get(s+(z,m),min(a for a,v in vals.items() if v==best))
        assert step['a_cmd']==cmd and cmd in row and step['u']==x.get(s+(cmd,),cmd)
        assert step['u'] in row and step['a_realized']==step['u'] and not step['illegal']
        a=step['a_realized'];dx,dy=DELTAS[a];cell=(s[0]+dx,s[1]+dy)
        cell=cell if cell in OPEN else s[:2];nt=s[2]+1
        hazard=nt%(6 if s[3]==0 else 3)==s[4]%(6 if s[3]==0 else 3)
        outcome='COLLISION' if cell==(2,2) and hazard else 'SUCCESS' if cell==(4,2) else 'TIMEOUT' if nt>=12 else None
        assert skey(step['state'])==cell+(nt,s[3],s[4]) and step['terminal']==(outcome is not None)
        assert step['outcome']==outcome and step['terminal']==(i==len(steps)-1)
        reward=-.02
        if outcome is not None:reward+=1.0 if outcome=='SUCCESS' else -1.0
        assert number(step['reward']).hex()==reward.hex()
        next_m=m
        if m==0:
            if (z==1 and cell==(2,1)) or (z==3 and cell==(2,4)):next_m=1
            elif z==2 and s[:2]==(1,2) and s[2]%(6 if s[3]==0 else 3)!=s[4]%(6 if s[3]==0 else 3):next_m=1
        assert step['control']=={'z':z,'m':next_m}
        optimal=sorted(a for a,v in row.items() if abs(v-max(row.values()))<=1e-12)
        if cmd not in optimal:nonoptimal.append(i)
        if step['u']!=cmd:controllers.append(list(s+(cmd,)))
        rows.append({'pre_state':list(s),'z':z,'m':m,'a_learner':cmd,'u_learner':step['u'],'optimal_actions':optimal})
        consulted.add(('decision',s+(z,m)));consulted.add(('controller',s+(cmd,)))
        s=skey(step['state']);m=next_m
    assert trace['control']==steps[-1]['control']
    return {'value':float(sum(number(x['reward']) for x in steps)),'raw_pin':digest(trace),
            'outcome':trace['outcome'],'consulted':consulted,'nonoptimal':nonoptimal,
            'controllers':controllers,'rows':rows}



def data_scene(key):
    return dict(zip(('kappa','phase','error_flag','cause_rank','base_option'),key))


def main():
    started=datetime.now(timezone.utc).isoformat()
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json')
    timed_out=not (HERE/'evidence/exit.json').exists()
    if timed_out:
        timeout=load(HERE/'evidence/timeout.json')
        assert timeout['native_exit_not_fabricated'] and not timeout['automatic_retry']
        native_exit={'child_exit_code':None}
    else:
        native_exit=load(HERE/'evidence/exit.json')
        assert claim['input_binding_before']==native_exit['input_binding_after']
        for name in ('stdout','stderr'):
            p=HERE/'evidence'/f'{name}.log'
            assert p.stat().st_size==native_exit[name]['bytes'] and sha(p)==native_exit[name]['sha256']
    for name,pin in claim['input_binding_before'].items():
        p=ROOT/name;assert p.stat().st_size==pin['bytes'] and sha(p)==pin['sha256'],name
    old98=BASE/'owned_whole_completion_v98'
    old96=BASE/'owned_whole_collateral_v96'
    assert sha(old98/'evidence/stdout.log')=='cb8766e9665e1b99ea7045bfaa52381c01b33f83829928234593a9898a53d53d'
    assert sha(old96/'evidence/stdout.log')=='8fd385c23d503b8ba6efbc7fcc9eb8e1547f4e2210615a8a11385b1929197104'
    assert not (old98/'evidence/exit.json').exists()
    qstar={}
    with (ROOT/c['reference_input']['path']).open(encoding='ascii') as stream:
        for line in stream:
            if line.startswith('DECISION_CONTEXT='):
                row=json.loads(line.split('=',1)[1]);qstar[tuple(row['context'])]={a:float.fromhex(v) for a,v in row['q_row_hex']}
    assert len(qstar)==13824
    oldpre={};oldposts={'reference':{},'treatment':{}};oldheaders={};oldb1=[]
    with (old96/'evidence/stdout.log').open(encoding='ascii') as stream:
        for physical in stream:
            r=json.loads(physical);p=r['payload']
            if r['mode']=='dq' and r['tag']=='RAW_ROLLOUT' and p['stage']=='pre':
                oldpre[tuple(p['scene'])]=p['trace']
    with (old98/'evidence/stdout.log').open(encoding='ascii') as stream:
        for physical in stream:
            r=json.loads(physical);p=r['payload']
            if r['mode']=='dq':
                if r['tag']=='NATIVE_B1_RETURN':oldb1.append(p)
                elif r['tag']=='BANK_BEGIN':oldheaders[p['stage']]=p
                elif r['tag']=='RAW_ROLLOUT' and p['stage'] in oldposts:oldposts[p['stage']][tuple(p['scene'])]=p['trace']
    assert len(oldpre)==5760 and len(oldb1)==2 and all(len(x)==5520 for x in oldposts.values())
    domain=list(itertools.product(range(2),range(6),range(2),range(60),range(4)))
    tags=Counter();counts=Counter();current_state=None;source_info=None;source_packets=[];source_index=-1
    prepared={};pre_values={};pre_records=[];nativeB1=[];post_rows={'reference':[],'treatment':[]}
    pre_transfers=[];post_transfer=None;completed=None;partial=None;result=None;inventory=None;lines=0
    with (HERE/'evidence/stdout.log').open(encoding='ascii',newline='') as stream:
        for physical in stream:
            assert physical.endswith('\n'),'incomplete canonical EOF'
            line=physical.rstrip('\r\n');r=json.loads(line);assert canonical(r)==line
            tag,p=r['tag'],r['payload'];assert r['mode']=='dq';tags[tag]+=1;lines+=1
            if tag=='FULL_SOURCE_PRE':
                current_state=p['stores'];source_index+=1
                assert [len(current_state[n]) for n in ('D','P','X','Q')]==[0,2,3,27]
            elif tag=='RAW_ROLLOUT':
                assert p['stage']=='source','NEW native ordinary bank is forbidden'
                scene=tuple(p['scene']);assert scene==tuple(c['new_scenes'][source_index])
                counts['rollout']+=1;counts['step']+=len(p['trace']['steps'])
                source_info=raw_check(p['trace'],scene,current_state,qstar)
            elif tag=='ORIGINAL_SOURCE':
                d=native_truth_tolerance(p['payload'])
                assert p['payload_sha256']==digest(d) and d['native_source_sha256']==digest(d['native_source_payload'])
                t=d['native_source_payload']['truth_evaluator_only']
                assert d['native_source_payload']['full_pre_stores']==compact_store(current_state)
                assert t['manifested_decision_timesteps']==source_info['nonoptimal']
                assert t['manifested_controller_sites']==source_info['controllers']
                assert t['source_separated_baseline_rows']==source_info['rows']
                assert t['manifested_process_proposals']==[0] and t['J_L']==[True]*3
                source_packets.append(p)
            elif tag=='BOUND_BEFORE_ARMS':
                assert p['payload_sha256']==digest(native_truth_tolerance(p['payload']))
                assert p['payload']['source']==source_packets[-1] and p['payload']['full_pre']==current_state
                assert p['payload']['decision_mode_before_arms']=='dq'
            elif tag=='TX_CALL':counts['transaction']+=1
            elif tag=='RECORDED_PRE_TRANSFER':
                assert p['payload_sha256']==digest(p['payload'])
                assert p['payload']['old_native_exit_preserved']==1 and p['payload']['full_pre_records']==5760
                assert p['payload']['new_kernel_replays']==0 and not p['payload']['old_source_pair_role_identity_reconstructed']
                assert p['payload']['actual_new_fullpre_sha256']==digest(current_state)
                assert all(sha(ROOT/n)==h for n,h in p['payload']['dependencies'].items())
                pre_transfers.append(p)
            elif tag=='RECORDED_PRE_OBSERVATION':
                scene=tuple(p['scene']);trace=p['trace']
                assert p['is_new_kernel_return'] is False and p['stage']=='recorded-pre'
                assert scene==domain[len(pre_records)] and trace==oldpre[scene]
                checked=raw_check(trace,scene,current_state,qstar)
                pre_values[scene]=checked;pre_records.append({'scene':data_scene(scene),'trace':trace})
            elif tag=='PREPARATION_COMPLETE':
                idx=p['source_index'];o=p['origin'];assert p['origin_sha256']==digest(o)
                assert len(pre_records)==5760 and o['full_pre']==current_state and len(o['owners'])==7
                assert len(o['residual_manifestations'])==3
                assert o['pre_input_pin']==digest([pre_records,o['owners']])
                assert o['pre_provenance']['kind']=='recorded_exact_binding'
                transfer=o['pre_provenance']['transfer']
                assert transfer['payload_sha256']==digest(transfer['payload'])
                assert transfer['payload']['recorded_rows_sha256']==digest([[x['scene'],x['trace']] for x in pre_records])
                owners={(x['channel'],tuple(x['key'])) for x in o['owners']}
                expected_owners={('decision',tuple(x['pre_state'])+(x['z'],x['m'])) for i,x in enumerate(source_info['rows']) if i in source_info['nonoptimal']}
                assert owners==expected_owners
                region=[u for u in domain if pre_values[u]['outcome']=='SUCCESS' and not pre_values[u]['consulted']&owners]
                assert [tuple(x) for x in p['region']['units']]==region and 0<len(region)<5760
                for (u,v),key in zip(p['region']['pre_values'],region):assert tuple(u)==key and number(v).hex()==pre_values[key]['value'].hex()
                prepared[idx]=p
            elif tag=='NATIVE_B1_RETURN':
                index=len(nativeB1)%2
                assert p==oldb1[index],'complete genuine newB1 post/allreceipts/scalar ledger differs'
                counts['B1']+=1;nativeB1.append(p)
                assert len(p['receipts'])==7 and all(x['status']==('EVALUABLE_NOOP' if index==0 else 'APPLIED') for x in p['receipts'])
            elif tag=='RECORDED_POST_TRANSFER':
                post_transfer=p;assert p['payload_sha256']==digest(p['payload'])
                d=p['payload'];assert d['old_raw_sha256']==sha(old98/'evidence/stdout.log') and d['old_native_exit_preserved'] is None
                assert d['old_launcher_timeout_preserved'] and d['new_post_kernel_replays']==0 and not d['old_source_pair_role_identity_reconstructed']
                assert d['actual_fullposts']==[x['full_post'] for x in nativeB1[-2:]]
                assert d['original_all_receipts']==[x['receipts'] for x in nativeB1[-2:]]
                assert d['owners']==prepared[0]['origin']['owners'] and d['region_sha256']==digest(prepared[0]['region'])
                assert all(sha(ROOT/n)==h for n,h in d['dependencies'].items())
            elif tag=='RECORDED_POST_OBSERVATION':
                role=p['stage'];scene=tuple(p['scene']);trace=p['trace'];index=0 if role=='reference' else 1
                region=[tuple(x) for x in prepared[0]['region']['units']]
                assert role in post_rows and p['is_new_kernel_return'] is False
                assert scene==region[len(post_rows[role])] and trace==oldposts[role][scene]
                assert oldheaders[role]['state']==nativeB1[index]['full_post']
                raw_check(trace,scene,nativeB1[index]['full_post'],qstar)
                post_rows[role].append({'scene':data_scene(scene),'trace':trace})
            elif tag=='WHOLE_MEASUREMENT_COMPLETE':
                d=p['payload'];assert p['payload_sha256']==digest(d) and d['origin_sha256']==prepared[0]['origin_sha256']
                banks=[post_rows[role] for role in ('reference','treatment')]
                assert d['complete_post_records']==[5520,5520] and d['new_post_kernel_rollouts']==0
                assert d['post_records_sha256']==digest(banks) and p['ordered_post_records']==banks
                assert d['recorded_post_provenance']==post_transfer
                assert post_transfer['payload']['rows_sha256']==digest([[[r['scene'],r['trace']] for r in bank] for bank in banks])
                assert d['full_immediate_posts']==[x['full_post'] for x in nativeB1[:2]] and d['region']==prepared[0]['region']
                region=[tuple(x) for x in d['region']['units']]
                mean=sum(pre_values[u]['value'] for u in region)/len(region)
                for score,bank in zip(d['scores'],banks):
                    post_mean=sum(float(sum(number(x['reward']) for x in row['trace']['steps'])) for row in bank)/len(bank)
                    assert number(score['pre_mean']).hex()==mean.hex()
                    assert number(score['post_mean']).hex()==post_mean.hex()
                    assert number(score['value']).hex()==(mean-post_mean).hex()
                delta=number(d['scores'][0]['value'])-number(d['scores'][1]['value'])
                assert number(d['paired_difference']).hex()==delta.hex()
                completed={'n':len(region),'B_hex':[x['value']['binary64_hex'] for x in d['scores']],
                    'paired_difference_hex':d['paired_difference']['binary64_hex'],'payload_sha256':p['payload_sha256']}
            elif tag=='PARTIAL_TRANSFER_FAILURE':
                partial=p['partial'];assert not partial['has_measurement_handle'] and not partial['automatic_retry']
                rd=partial['recorded_partial'];assert not rd['has_recorded_handle'] and not rd['automatic_retry']
                assert [len(x) for x in rd['ordered_rows']]==[1,0]
                assert partial['full_starts']==[x['full_post'] for x in nativeB1[-2:]]
                first=rd['ordered_rows'][0][0];scene=tuple(first[0][k] for k in ('kappa','phase','error_flag','cause_rank','base_option'))
                assert first[1]==oldposts['reference'][scene]
            elif tag=='ACTUAL_LOADED_SOURCE_INVENTORY':inventory=p
            elif tag=='RESULT':assert result is None;result=p
    if not timed_out:
        assert result is not None and inventory is not None
        for n,h in inventory.items():assert n in claim['input_binding_before'] and claim['input_binding_before'][n]['sha256']==h
        for k in ('rollout','step','B1','transaction'):assert counts[k]==result['counts'].get(k,0)
        assert result['counts'].get('forbidden',0)==0 and result['profile_restored'] and result['new_pre_post_native_banks']==0
        if native_exit['child_exit_code']==0:
            assert result['tests']==3 and result['errors']==result['failures']==result['skips']==0
            assert completed is not None and partial is not None and len(prepared)==len(pre_transfers)==2
            assert counts==Counter({'rollout':2,'step':24,'B1':4,'transaction':4})
            for tag in ('WRONG_SOURCE_REJECTED','SWAPPED_ROLE_REJECTED','MISSING_POST_RECORD_REJECTED','IMMEDIATE_ROLE_ALIAS_REJECTED',
                        'TRANSFER_INPUTS_RESTORED','PARTIAL_COMPLETE_ONCE_AND_RESTORE','RECORDED_ENDPOINT_COMPLETE'):
                assert tags[tag]==1,tag
    report={'schema':'V101_FIRST_INDEPENDENT_STORED_CONTENT_CHECK_NOT_RUNTIME_IDENTITY_OR_SCIENCE',
        'native_exit_preserved':native_exit['child_exit_code'],'launcher_timed_out':timed_out,
        'input_pins':len(claim['input_binding_before']),'loaded_source_pins':0 if inventory is None else len(inventory),
        'canonical_records':lines,'actual_new_native_counts':dict(counts),'new_pre_post_native_banks':0,
        'recorded_pre_transfer_count':len(pre_transfers),'old_pre_full_reads':5760*len(pre_transfers),
        'old_post_complete_rows_checked':sum(len(x) for x in post_rows.values()),'old_post_partial_rows_checked':0 if partial is None else 1,
        'complete_measurement':completed,'partial_rows':None if partial is None else [1,0],
        'tests':None if result is None else result['tests'],'failures':None if result is None else result['failures'],
        'errors':None if result is None else result['errors'],'skips':None if result is None else result['skips'],
        'tag_inventory':dict(tags),'old_checker_RFL_execution':False,'runtime_identity_reconstructed':False,
        'independent_expert_science_gate':False,'source_sha256':sha(Path(__file__)),
        'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    with (HERE/'stored_audit_result.json').open('x',encoding='utf-8',newline='\n') as stream:stream.write(canonical(report)+'\n')
    print(canonical(report))


if __name__=='__main__':main()
