"""Independent complete streaming content review, stdlib only, first execution.

No old checker/fixture or RFL module is imported/executed. Serialised evidence
cannot establish runtime identity; the actual native harness owns those checks.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]


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


def main():
    started=datetime.now(timezone.utc).isoformat()
    c=load(HERE/'contract.json');claim=load(HERE/'evidence/claim.json')
    timed_out=not (HERE/'evidence/exit.json').exists()
    if timed_out:
        timeout=load(HERE/'evidence/timeout.json')
        assert timeout['native_exit_not_fabricated'] and not timeout['automatic_retry']
        exit_record={'child_exit_code':None}
    else:
        exit_record=load(HERE/'evidence/exit.json')
        assert claim['input_binding_before']==exit_record['input_binding_after']
        for n in ('stdout','stderr'):
            path=HERE/'evidence'/f'{n}.log';assert path.stat().st_size==exit_record[n]['bytes'] and sha(path)==exit_record[n]['sha256']
    for n,pin in claim['input_binding_before'].items():
        path=ROOT/n;assert path.stat().st_size==pin['bytes'] and sha(path)==pin['sha256'],n
    qstar={}
    with (ROOT/c['reference_input']['path']).open(encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('DECISION_CONTEXT='):
                row=json.loads(line.split('=',1)[1]);qstar[tuple(row['context'])]={a:float.fromhex(v) for a,v in row['q_row_hex']}
    assert len(qstar)==13824
    tags=Counter();counts=Counter();bank_counts=[];pre={};source_info=None;source_packet=None;source_state=None
    prepared=None;region=None;owners=None;native_B1=[];tx=[];completed=None;partial=None;result=None;inventory=None
    pre_pin=hashlib.sha256(b'[[');post_pin=None;post_count=[0,0];records=0;active_bank=None
    domain=list(itertools.product(range(2),range(6),range(2),range(60),range(4)))
    with (HERE/'evidence/stdout.log').open(encoding='ascii',newline='') as stream:
        for physical in stream:
            assert physical.endswith('\n'),'incomplete canonical EOF'
            line=physical.rstrip('\r\n');r=json.loads(line);assert canonical(r)==line
            tag,p=r['tag'],r['payload'];assert r['mode']=='patch-adaptive';tags[tag]+=1;records+=1
            if tag=='FULL_SOURCE_PRE':
                source_state=p['stores'];assert [len(source_state[n]) for n in ('D','P','X','Q')]==[27,2,3,0]
            elif tag=='ORIGINAL_SOURCE':
                source_packet=p;decoded=native_truth_tolerance(p['payload'])
                assert p['payload_sha256']==digest(decoded)
                assert decoded['native_source_sha256']==digest(decoded['native_source_payload'])
                native=decoded['native_source_payload'];assert native['full_pre_stores']==compact_store(source_state)
                truth=native['truth_evaluator_only'];assert truth['manifested_decision_timesteps']==source_info['nonoptimal']
                assert truth['source_separated_baseline_rows']==source_info['rows']
                assert truth['manifested_controller_sites']==source_info['controllers']
                assert truth['manifested_process_proposals']==[0] and truth['J_L']==[True,True,True]
                assert truth['R_mech'] is None and truth['Gamma_T_star'] is None
                assert truth['Gamma_P_star']==['ProcessCommit']+['Decision_'+str(i) for i in source_info['nonoptimal']]+[
                    'ControllerSite_'+str(x[0])+'_'+str(x[1])+'_'+str(x[2])+'_'+str(x[5]) for x in source_info['controllers']]
            elif tag=='BOUND_BEFORE_ARMS':
                assert p['payload_sha256']==digest(native_truth_tolerance(p['payload']))
                assert p['payload']['decision_mode_before_arms']=='patch-adaptive'
                assert p['payload']['source']==source_packet and p['payload']['full_pre']==source_state
            elif tag=='BANK_BEGIN':
                active_bank={'stage':p['stage'],'units':[tuple(s) for s in p['units']],'state':p['state'],'count':0}
                bank_counts.append(active_bank)
                if p['stage']=='pre':assert active_bank['units']==domain and p['state']==source_state
                else:
                    assert active_bank['units']==region
                    assert p['state']==native_B1[-2 if p['stage']=='reference' else -1]['full_post']
                    if p['stage']=='reference':post_pin=hashlib.sha256(b'[[');post_count=[0,0]
                    else:post_pin.update(b'],[')
            elif tag=='RAW_ROLLOUT':
                scene=tuple(p['scene']);trace=p['trace'];stage=p['stage']
                counts['rollout']+=1;counts['step']+=len(trace['steps'])
                if stage=='source':
                    assert scene==tuple(c['new_scene']);state=source_state
                else:
                    assert stage==active_bank['stage'] and scene==active_bank['units'][active_bank['count']]
                    active_bank['count']+=1;state=active_bank['state']
                checked=raw_check(trace,scene,state,qstar)
                if stage=='source':source_info=checked
                elif stage=='pre':
                    assert scene==domain[len(pre)] and scene not in pre
                    record_pin_update(pre_pin,scene,trace,bool(pre));pre[scene]=checked
                else:
                    assert checked['raw_pin']==pre[scene]['raw_pin']
                    index=0 if stage=='reference' else 1
                    record_pin_update(post_pin,scene,trace,post_count[index]>0);post_count[index]+=1
            elif tag=='PREPARATION_COMPLETE':
                origin=p['origin'];assert p['origin_sha256']==digest(origin)
                assert len(pre)==5760 and origin['full_pre']==source_state
                owners=origin['owners'];assert len(owners)==7 and len(origin['residual_manifestations'])==3
                sset={(x['channel'],tuple(x['key'])) for x in owners}
                expected_owners={('decision',tuple(row['pre_state'])+(row['z'],row['m']))
                    for i,row in enumerate(source_info['rows']) if i in source_info['nonoptimal']}
                assert sset==expected_owners
                region=[u for u in domain if pre[u]['outcome']=='SUCCESS' and not pre[u]['consulted']&sset]
                assert 0<len(region)<5760 and [tuple(x) for x in p['region']['units']]==region
                assert len(p['region']['pre_values'])==len(region)
                for (u,v),key in zip(p['region']['pre_values'],region):assert tuple(u)==key and number(v).hex()==pre[key]['value'].hex()
                pre_pin.update(b'],'+canonical(owners).encode()+b']')
                assert pre_pin.hexdigest()==origin['pre_input_pin']
                assert origin['pre_provenance']=={'kind':'fresh_kernel_census','native_pre_rollouts':5760}
                prepared=p
            elif tag=='NATIVE_B1_RETURN':
                counts['B1']+=1;native_B1.append(p);assert len(p['receipts'])==7
                statuses=[x['status'] for x in p['receipts']]
                expected_status='EVALUABLE_NOOP' if p['law']=='NoWrite' else 'APPLIED'
                assert statuses==[expected_status]*7
                d,proc,x,q=mappings(p['full_post']);od,op,ox,oq=mappings(source_state)
                assert (proc,x,q)==(op,ox,oq)
                expect=od if p['law']=='NoWrite' else {key:value for key,value in od.items() if ('decision',key) not in sset}
                assert d==expect
            elif tag=='TX_CALL':counts['transaction']+=1;tx.append(p)
            elif tag=='WHOLE_MEASUREMENT_COMPLETE':
                payload=p['payload'];assert p['payload_sha256']==digest(payload)
                assert payload['origin_sha256']==prepared['origin_sha256'] and payload['region']==prepared['region']
                assert payload['full_immediate_posts']==[x['full_post'] for x in native_B1[-2:]]
                assert payload['complete_post_rollouts']==[len(region),len(region)] and post_count==[len(region),len(region)]
                post_pin.update(b']]');assert post_pin.hexdigest()==payload['post_records_sha256']
                assert [len(x) for x in p['ordered_post_records']]==[len(region),len(region)]
                mean=sum(pre[u]['value'] for u in region)/len(region)
                for role_records,score in zip(p['ordered_post_records'],payload['scores']):
                    vals=[]
                    for record,key in zip(role_records,region):
                        scene=record['scene'];assert tuple(scene[k] for k in ('kappa','phase','error_flag','cause_rank','base_option'))==key
                        assert digest(record['trace'])==pre[key]['raw_pin']
                        vals.append(float(sum(number(x['reward']) for x in record['trace']['steps'])))
                    post_mean=sum(vals)/len(vals)
                    assert number(score['pre_mean']).hex()==mean.hex() and number(score['post_mean']).hex()==post_mean.hex()
                    assert number(score['value']).hex()==(mean-post_mean).hex()
                delta=number(payload['scores'][0]['value'])-number(payload['scores'][1]['value'])
                assert number(payload['paired_difference']).hex()==delta.hex()
                completed={'n':len(region),'pre_mean_hex':mean.hex(),'B_hex':[s['value']['binary64_hex'] for s in payload['scores']],
                    'pair_difference_hex':payload['paired_difference']['binary64_hex'],'payload_sha256':p['payload_sha256']}
            elif tag=='PARTIAL_POST_FAILURE':
                partial=p['partial'];assert [len(x) for x in partial['ordered_records']]==[1,0]
                assert not partial['has_measurement_handle'] and not partial['automatic_retry']
                assert partial['full_starts']==[x['full_post'] for x in native_B1[-2:]]
            elif tag=='ACTUAL_LOADED_SOURCE_INVENTORY':inventory=p
            elif tag=='RESULT':assert result is None;result=p
    if not timed_out:
        assert result is not None and inventory is not None
        for n,h in inventory.items():assert n in claim['input_binding_before'] and claim['input_binding_before'][n]['sha256']==h
        for key in ('rollout','step','B1','transaction'):assert counts[key]==result['counts'].get(key,0)
        assert result['counts'].get('forbidden',0)==0 and result['profile_restored']
        if exit_record['child_exit_code']==0:
            assert result['tests']==3 and result['failures']==result['errors']==result['skips']==0
            assert completed and partial and counts['B1']==4 and counts['transaction']==3
            assert counts['rollout']==1+5760+2*completed['n']+1
            for tag in ('OWNER_DROP_REJECTED','REGION_TRIM_REJECTED','IMMEDIATE_ROLE_ALIAS_REJECTED',
                        'RESTORED_INPUT_AND_AST_GATE','SPARSE_NATIVE_OBSERVER_CAPTURED','PARTIAL_COMPLETE_ONCE_AND_RESTORE'):
                assert tags[tag]==1,tag
            assert [x['count'] for x in bank_counts]==[5760,completed['n'],completed['n'],1]
            assert len(tx[0]['edits'])==32 and all(len(x['edits'])==7 for x in tx[1:])
    report={'schema':'V100_FIRST_STORED_CONTENT_REVIEW_NOT_RUNTIME_IDENTITY_OR_SCIENCE_GATE',
        'native_exit_preserved':exit_record['child_exit_code'],'launcher_timed_out':timed_out,
        'input_pins':len(claim['input_binding_before']),'actual_loaded_source_pins':0 if inventory is None else len(inventory),
        'canonical_records':records,'native_counts':dict(counts),'complete_measurement':completed,
        'partial_completed_scenes':None if partial is None else [len(x) for x in partial['ordered_records']],
        'tags':dict(tags),'tests':None if result is None else result['tests'],
        'failures':None if result is None else result['failures'],'errors':None if result is None else result['errors'],
        'skips':None if result is None else result['skips'],'original_checker_RFL_execution':False,
        'runtime_identity_reconstructed':False,'independent_expert_scientific_gate':False,
        'source_sha256':sha(Path(__file__)),'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    with (HERE/'stored_audit_result.json').open('x',encoding='utf-8',newline='\n') as stream:stream.write(canonical(report)+'\n')
    print(canonical(report))


if __name__=='__main__':main()
