"""Independent streaming stdlib stored audit: no RFL/old checker execution."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=ROOT/'experiments/v03r/a96_dense/b2_prepare/owned_whole_completion_v98'
OLD=ROOT/'experiments/v03r/a96_dense/b2_prepare/owned_whole_collateral_v96'


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True)
def load(p):return json.loads(p.read_bytes())
def number(x):return float.fromhex(x['binary64_hex'])
def skey(s):return tuple(s[k] for k in ('x','y','t','kappa','phi'))
def digest(x):return hashlib.sha256(canonical(x).encode('ascii')).hexdigest()
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def mappings(stores):
    d={skey(v['address']['state'])+(v['address']['z'],v['address']['m']):v['value'] for v in stores['D']}
    p={v['address']:v['value'] for v in stores['P']}
    x={skey(v['address']['state'])+(v['address']['cmd'],):v['value'] for v in stores['X']}
    q={skey(v['address']['state'])+(v['address']['z'],v['address']['m'],v['address']['a']):number(v['value']) for v in stores['Q']}
    return d,p,x,q


def add_record_pin(h,scene,trace,comma):
    if comma:h.update(b',')
    s=dict(zip(('kappa','phase','error_flag','cause_rank','base_option'),scene))
    h.update(canonical({'scene':s,'trace':trace}).encode('ascii'))


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
    for name,pin in claim['input_binding_before'].items():
        p=ROOT/name;assert p.stat().st_size==pin['bytes'] and sha(p)==pin['sha256'],name
    for name in ('stdout','stderr'):
        p=HERE/'evidence'/f'{name}.log'
        if not timed_out:assert p.stat().st_size==exit_record[name]['bytes'] and sha(p)==exit_record[name]['sha256']
    assert sha(OLD/'evidence/stdout.log')=='8fd385c23d503b8ba6efbc7fcc9eb8e1547f4e2210615a8a11385b1929197104'
    old_pre={};old_state=None
    with (OLD/'evidence/stdout.log').open(encoding='utf-8') as f:
        for line in f:
            r=json.loads(line);p=r['payload']
            if r['mode']=='dq' and r['tag']=='BANK_BEGIN' and p['stage']=='pre':old_state=p['state']
            elif r['mode']=='dq' and r['tag']=='RAW_ROLLOUT' and p['stage']=='pre':old_pre[tuple(p['scene'])]=digest(p['trace'])
    assert len(old_pre)==5760
    qstar={}
    with (ROOT/c['reference_input']['path']).open(encoding='utf-8') as f:
        for line in f:
            if line.startswith('DECISION_CONTEXT='):
                r=json.loads(line.split('=',1)[1]);qstar[tuple(r['context'])]={a:float.fromhex(v) for a,v in r['q_row_hex']}
    assert len(qstar)==13824
    domain=list(itertools.product(range(2),range(6),range(2),range(60),range(4)))
    tags=Counter();counts=Counter();stages=Counter();states={};banks={};pre={};pre_hash={};prepared={};completed={}
    owner_sets={};region={};post_hash={};post_counter={};active_cells={};B1=[];inventory=None;result=None;transfer=None;records=0
    with (HERE/'evidence/stdout.log').open(encoding='utf-8',newline='') as f:
        for physical in f:
            assert physical.endswith('\n'),'incomplete EOF'
            line=physical.rstrip('\r\n');r=json.loads(line);assert canonical(r)==line
            tag,mode,p=r['tag'],r['mode'],r['payload'];tags[tag]+=1;records+=1
            if tag=='FULL_SOURCE_PRE':states[mode]=p['stores']
            elif tag=='RECORDED_CENSUS_TRANSFER':
                transfer=p;assert p['payload_sha256']==digest(p['payload'])
                assert p['payload']['full_pre_records']==5760 and p['payload']['new_kernel_replays']==0
                assert p['payload']['old_source_pair_role_identity_reconstructed'] is False
                assert states[mode]==old_state and p['payload']['actual_new_fullpre_sha256']==digest(states[mode])
                assert all(sha(ROOT/name)==h for name,h in p['payload']['dependencies'].items())
            elif tag=='BANK_BEGIN':
                stage=p['stage'];units=[tuple(s) for s in p['units']]
                banks[mode,stage]={'units':units,'state':p['state'],'count':0}
                if stage=='pre':assert units==domain and p['state']==states[mode]
                else:
                    assert units==region[mode]
                    if stage=='reference':
                        post_hash[mode]=hashlib.sha256(b'[[');post_counter[mode]=[0,0]
                        active_cells[mode]=B1[-1][1]['law']
                    else:post_hash[mode].update(b'],[')
            elif tag in ('RAW_ROLLOUT','RECORDED_PRE_OBSERVATION'):
                stage=p['stage'];scene=tuple(p['scene']);trace=p['trace'];steps=trace['steps']
                if tag=='RAW_ROLLOUT':counts['rollout']+=1;counts['step']+=len(steps)
                else:
                    assert stage=='recorded-pre' and mode=='dq' and p['is_new_kernel_return'] is False
                    assert p['old_capture_sha256']==transfer['payload']['old_native_capture_sha256']
                    assert digest(trace)==old_pre[scene]
                stages[mode,stage]+=1
                if stage in ('source','recorded-pre'):state=states[mode]
                else:
                    bank=banks[mode,stage];assert scene==bank['units'][bank['count']];bank['count']+=1;state=bank['state']
                d,process,controller,q=mappings(state)
                assert trace['base_option']==scene[4] and trace['option_in_force']==process.get(scene[4],scene[4])
                assert trace['mask']=={'controller':None,'decision':None,'plant':None,'trap':None}
                assert trace['interventions']=={'members':[]} and steps and steps[-1]['terminal']
                assert steps[-1]['outcome']==trace['outcome'] and all(not x['terminal'] for x in steps[:-1])
                s=(0,2,0,scene[0],scene[1]);z,m=trace['option_in_force'],0;consult=set()
                for i,step in enumerate(steps):
                    row=qstar[s+(z,m)];vals={a:q.get(s+(z,m,a),v) for a,v in row.items()};best=max(vals.values())
                    cmd=d.get(s+(z,m),min(a for a,v in vals.items() if v==best))
                    assert step['a_cmd']==cmd and cmd in row and step['u']==controller.get(s+(cmd,),cmd)
                    assert skey(step['state'])[2]==i+1 and skey(step['state'])[3:]==s[3:]
                    consult.add(('decision',s+(z,m)));consult.add(('controller',s+(cmd,)))
                    s=skey(step['state']);z,m=step['control']['z'],step['control']['m']
                consult.add(('process',(scene[4],)))
                ret=float(sum(number(x['reward']) for x in steps));tp=digest(trace)
                if stage in ('pre','recorded-pre'):
                    if mode not in pre:pre[mode]={};pre_hash[mode]=hashlib.sha256(b'[[')
                    assert scene==domain[len(pre[mode])] and scene not in pre[mode]
                    add_record_pin(pre_hash[mode],scene,trace,bool(pre[mode]))
                    pre[mode][scene]={'value':ret,'raw_pin':tp,'outcome':trace['outcome'],'consult':consult}
                elif stage in ('reference','treatment'):
                    assert scene in region[mode] and pre[mode][scene]['raw_pin']==tp
                    index=0 if stage=='reference' else 1
                    add_record_pin(post_hash[mode],scene,trace,post_counter[mode][index]>0)
                    post_counter[mode][index]+=1
            elif tag=='PREPARATION_COMPLETE':
                origin=p['origin'];assert p['origin_sha256']==digest(origin)
                assert len(pre[mode])==5760
                owners=origin['owners'];assert len(owners)==7 and len(origin['residual_manifestations'])==3
                os={(x['channel'],tuple(x['key'])) for x in owners};owner_sets[mode]=os
                selected=[u for u in domain if pre[mode][u]['outcome']=='SUCCESS' and not (pre[mode][u]['consult']&os)]
                assert 0<len(selected)<5760 and [tuple(x) for x in p['region']['units']]==selected
                assert all(tuple(u)==k and number(v).hex()==pre[mode][k]['value'].hex() for (u,v),k in zip(p['region']['pre_values'],selected))
                pre_hash[mode].update(b'],'+canonical(owners).encode()+b']')
                assert pre_hash[mode].hexdigest()==origin['pre_input_pin']
                assert origin['pre_provenance']['kind']==('recorded_exact_binding' if mode=='dq' else 'fresh_kernel_census')
                prepared[mode]=p;region[mode]=selected
            elif tag=='NATIVE_B1_RETURN':
                counts['B1']+=1;B1.append((mode,p));assert len(p['receipts'])==7
                assert all(x['status']==('EVALUABLE_NOOP' if p['law']=='NoWrite' else 'APPLIED') for x in p['receipts'])
            elif tag=='TX_CALL':counts['transaction']+=1
            elif tag=='WHOLE_MEASUREMENT_COMPLETE':
                payload=p['payload'];assert p['payload_sha256']==digest(payload)
                n=len(region[mode]);assert payload['complete_post_rollouts']==[n,n] and post_counter[mode]==[n,n]
                post_hash[mode].update(b']]');assert post_hash[mode].hexdigest()==payload['post_records_sha256']
                assert payload['region']==prepared[mode]['region']
                mean=sum(pre[mode][u]['value'] for u in region[mode])/n
                for score in payload['scores']:
                    assert number(score['pre_mean']).hex()==mean.hex()==number(score['post_mean']).hex()
                    assert number(score['value']).hex()==0.0.hex()
                assert number(payload['paired_difference']).hex()==0.0.hex()
                completed[mode]={'n':n,'pre_mean_hex':mean.hex(),'ordered_B_hex':[x['value']['binary64_hex'] for x in payload['scores']],
                                 'pair_difference_hex':payload['paired_difference']['binary64_hex']}
            elif tag=='ACTUAL_LOADED_SOURCE_INVENTORY':inventory=p
            elif tag=='RESULT':assert result is None;result=p
    if not timed_out:
        assert inventory is not None and result is not None
        assert all(n in claim['input_binding_before'] and claim['input_binding_before'][n]['sha256']==h for n,h in inventory.items())
        for key in ('rollout','step','B1','transaction'):assert counts[key]==result['counts'].get(key,0)
        assert result['counts'].get('forbidden',0)==0
    elif inventory is not None:
        assert all(n in claim['input_binding_before'] and claim['input_binding_before'][n]['sha256']==h for n,h in inventory.items())
    if not timed_out and exit_record['child_exit_code']==0:
        assert result['tests']==4 and result['errors']==result['failures']==result['skips']==0
        assert len(completed)==2 and tags['RECORDED_PRE_OBSERVATION']==5760 and counts['B1']==6
        assert tags['PARTIAL_POST_FAILURE']==tags['PARTIAL_COMPLETE_ONCE_AND_RESTORE']==1
        assert tags['RECORDED_TRIM_REJECTED']==tags['OWNER_DROP_REJECTED']==tags['REGION_TRIM_REJECTED']==1
        assert counts['rollout']==2+5760+sum(2*x['n'] for x in completed.values())+1
    elif not timed_out:assert result['errors']+result['failures']>0
    complete_raw_banks={}
    for mode,units in region.items():
        if all((mode,role) in banks and banks[mode,role]['count']==len(units) for role in ('reference','treatment')):
            mean=sum(pre[mode][u]['value'] for u in units)/len(units)
            complete_raw_banks[mode]={'n':len(units),'pre_mean_hex':mean.hex(),
                 'ordered_B_hex':[0.0.hex(),0.0.hex()],'paired_difference_hex':0.0.hex(),
                 'raw_equal_pre_every_scene':True,'runtime_measurement_handle_confirmed':mode in completed}
    if timed_out:
        observation={'role':'EXTERNAL_STORED_OBSERVATION_NOT_NATIVE_EXIT_RECEIPT',
                     'launcher_timeout_observation':timeout,'native_exit_code':None,
                     'complete_result_tag_seen':result is not None,'declared_input_bytes_equal_now':True,
                     'stdout':{'bytes':(HERE/'evidence/stdout.log').stat().st_size,'sha256':sha(HERE/'evidence/stdout.log')},
                     'stderr':{'bytes':(HERE/'evidence/stderr.log').stat().st_size,'sha256':sha(HERE/'evidence/stderr.log')},
                     'automatic_retry':False,'observed_at_utc':datetime.now(timezone.utc).isoformat()}
        with (HERE/'external_timeout_observation.json').open('x',encoding='utf-8',newline='\n') as f:f.write(canonical(observation)+'\n')
    out={'status':'V98_COMPLETE_STORED_CONTENT_REVIEW_NATIVE_OUTCOME_PRESERVED_NOT_SCIENCE',
         'native_exit_preserved':exit_record['child_exit_code'],'launcher_timed_out':timed_out,
         'tests':None if result is None else result['tests'],'failures':None if result is None else result['failures'],
         'errors':None if result is None else result['errors'],'skips':None if result is None else result['skips'],
         'input_pins':len(claim['input_binding_before']),
         'canonical_records':records,'new_native_counts':dict(counts),'recorded_old_pre_reused':tags['RECORDED_PRE_OBSERVATION'],
         'stage_counts':{str(k):v for k,v in stages.items()},'complete_measurements':completed,
         'complete_raw_bank_diagnostics':complete_raw_banks,'tag_inventory':dict(tags),
         'old_fixture_checker_RFL_execution':False,'runtime_identity_reconstructed':False,
         'scientific_qualification':False,'source_sha256':sha(Path(__file__)),
         'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    with (HERE/'stored_audit_result.json').open('x',encoding='utf-8',newline='\n') as f:f.write(canonical(out)+'\n')
    print(canonical(out))


if __name__=='__main__':main()
