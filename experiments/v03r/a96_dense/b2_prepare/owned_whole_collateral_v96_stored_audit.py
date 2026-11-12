"""Streaming independent stdlib review; preserves native failure/partial truth.

No RFL, ruler, instrument, old test or checker import/execution. Full raw records
are processed, not a tail/sample. No runtime ownership is rebuilt from bytes.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=ROOT/'experiments/v03r/a96_dense/b2_prepare/owned_whole_collateral_v96'


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(1<<20),b''): h.update(part)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_bytes())


def number(wire):
    return float.fromhex(wire['binary64_hex'])


def skey(s):
    return tuple(s[x] for x in ('x','y','t','kappa','phi'))


def addr(x,numeric=False):
    s=x['state']; result=skey(s)+(x['z'],x['m'])
    return result+(x['a'],) if numeric else result


def mappings(stores):
    q={addr(x['address'],True):number(x['value']) for x in stores['Q']}
    d={addr(x['address']):x['value'] for x in stores['D']}
    p={x['address']:x['value'] for x in stores['P']}
    x={skey(v['address']['state'])+(v['address']['cmd'],):v['value'] for v in stores['X']}
    return d,p,x,q


def main():
    started=datetime.now(timezone.utc).isoformat()
    contract=load(HERE/'contract.json'); claim=load(HERE/'evidence/claim.json'); receipt=load(HERE/'evidence/exit.json')
    assert claim['input_binding_before']==receipt['input_binding_after']
    for name,pin in claim['input_binding_before'].items():
        p=ROOT/name
        assert p.stat().st_size==pin['bytes'] and sha(p)==pin['sha256'],name
    for name in ('stdout','stderr'):
        p=HERE/'evidence'/f'{name}.log'
        assert p.stat().st_size==receipt[name]['bytes'] and sha(p)==receipt[name]['sha256']
    qstar={}
    with (ROOT/contract['reference_input']['path']).open(encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('DECISION_CONTEXT='):
                x=json.loads(line.split('=',1)[1]);qstar[tuple(x['context'])]={a:float.fromhex(v) for a,v in x['q_row_hex']}
    assert len(qstar)==13824
    domain=list(itertools.product(range(2),range(6),range(2),range(60),range(4)))
    tags=Counter(); stages=Counter(); counts=Counter(); mode_states={}; banks={}; pre={}; selected={}; owners={}
    source_raw={}; source_data={}; preparations={}; complete={}; native_b1=[]; tx_calls=[]; tx_returns=[]
    result=None; inventory=None; record_count=0; pre_hash={}; pre_counts=Counter(); census_means={}; census_results={}
    with (HERE/'evidence/stdout.log').open(encoding='utf-8',newline='') as stream:
        for physical in stream:
            assert physical.endswith('\n'),'incomplete JSONL EOF'
            line=physical.rstrip('\r\n');record=json.loads(line)
            assert canonical(record)==line,'noncanonical raw record'
            tag=record['tag'];mode=record['mode'];p=record['payload'];tags[tag]+=1;record_count+=1
            if tag=='FULL_SOURCE_PRE':mode_states[mode]=p['stores']
            elif tag=='ORIGINAL_SOURCE':source_data[mode]=p
            elif tag=='BANK_BEGIN':
                stage=p['stage']; units=[tuple(x) for x in p['units']]
                if stage=='pre':
                    assert units==domain
                    owners[mode]=p['sanitized_owners'];assert len(owners[mode])==7
                    assert p['state']==mode_states[mode]
                    pre[mode]={};selected[mode]=[];pre_hash[mode]=hashlib.sha256(b'[[')
                    census_results[mode]=Counter()
                banks[mode,stage]={'units':units,'count':0,'state':p['state']}
            elif tag=='RAW_ROLLOUT':
                stage=p['stage'];scene=tuple(p['scene']);trace=p['trace'];steps=trace['steps']
                stages[mode,stage]+=1;counts['rollout']+=1;counts['step']+=len(steps)
                assert steps and steps[-1]['terminal'] and steps[-1]['outcome']==trace['outcome']
                assert all(not s['terminal'] for s in steps[:-1])
                assert trace['base_option']==scene[4] and not trace['interventions']['members']
                if stage=='source':state=mode_states[mode]
                else:
                    bank=banks[mode,stage];assert scene==bank['units'][bank['count']];bank['count']+=1
                    state=bank['state']
                d,process,controller,q=mappings(state)
                assert trace['option_in_force']==process.get(scene[4],scene[4])
                s=(0,2,0,scene[0],scene[1]);z,m=trace['option_in_force'],0;walk=[]
                for i,step in enumerate(steps):
                    row=qstar[s+(z,m)]; effective={a:q.get(s+(z,m,a),v) for a,v in row.items()}
                    best=max(effective.values());expected=d.get(s+(z,m),min(a for a,v in effective.items() if v==best))
                    assert step['a_cmd']==expected and expected in row
                    assert step['u']==controller.get(s+(expected,),expected)
                    assert skey(step['state'])[2]==i+1 and skey(step['state'])[3:]==s[3:]
                    walk.append((s,z,m,step['a_cmd']))
                    s=skey(step['state']);z,m=step['control']['z'],step['control']['m']
                ret=float(sum(number(step['reward']) for step in steps))
                raw_pin=hashlib.sha256(canonical(trace).encode()).hexdigest()
                if stage=='source':source_raw[mode]=(scene,raw_pin,trace,walk)
                elif stage=='pre':
                    assert scene not in pre[mode]
                    consulted=set(('decision',s+(z,m)) for s,z,m,_a in walk)
                    consulted.update(('controller',s+(a,)) for s,_z,_m,a in walk)
                    consulted.add(('process',(scene[4],)))
                    hit=any((c['channel'],tuple(c['key'])) in consulted for c in owners[mode])
                    eligible=trace['outcome']=='SUCCESS' and not hit
                    pre[mode][scene]=(ret,raw_pin,eligible);census_results[mode][trace['outcome']]+=1
                    if eligible:selected[mode].append(scene)
                    if pre_counts[mode]:pre_hash[mode].update(b',')
                    scene_dict=dict(zip(('kappa','phase','error_flag','cause_rank','base_option'),scene))
                    pre_hash[mode].update(canonical({'scene':scene_dict,'trace':trace}).encode())
                    pre_counts[mode]+=1
                elif stage in ('reference','treatment'):
                    assert scene in pre[mode] and pre[mode][scene][2]
                    assert raw_pin==pre[mode][scene][1],'source-local unaffected behavior changed'
                else:raise AssertionError('unknown raw stage '+stage)
            elif tag=='PREPARATION_COMPLETE':
                assert pre_counts[mode]==5760 and list(pre[mode])==domain
                pre_hash[mode].update(b'],'+canonical(owners[mode]).encode()+b']')
                assert pre_hash[mode].hexdigest()==p['origin']['pre_input_pin']
                assert p['origin']['owners']==owners[mode]
                assert [tuple(x) for x in p['region']['units']]==selected[mode]
                assert 0<len(selected[mode])<5760
                assert all(tuple(u)==scene and number(v).hex()==pre[mode][scene][0].hex()
                           for (u,v),scene in zip(p['region']['pre_values'],selected[mode]))
                preparations[mode]=p
            elif tag=='NATIVE_B1_RETURN':native_b1.append((mode,p));counts['B1']+=1
            elif tag=='TX_CALL':tx_calls.append((mode,p));counts['transaction']+=1
            elif tag=='TX_RETURN':tx_returns.append((mode,p))
            elif tag=='WHOLE_MEASUREMENT_COMPLETE':
                payload=p['payload'];n=len(selected[mode]);assert payload['complete_post_rollouts']==[n,n]
                assert payload['region']==preparations[mode]['region']
                pre_mean=sum(pre[mode][u][0] for u in selected[mode])/n
                for score in payload['scores']:
                    assert number(score['pre_mean']).hex()==pre_mean.hex()
                    assert number(score['post_mean']).hex()==pre_mean.hex()
                    assert number(score['value']).hex()==(pre_mean-pre_mean).hex()
                assert number(payload['paired_difference']).hex()==0.0.hex()
                complete[mode]={'selected_scenes':n,'pre_mean_hex':pre_mean.hex(),
                               'ordered_score_hex':[x['value']['binary64_hex'] for x in payload['scores']],
                               'paired_difference_hex':payload['paired_difference']['binary64_hex']}
            elif tag=='RESULT':assert result is None;result=p
            elif tag=='ACTUAL_LOADED_SOURCE_INVENTORY':inventory=p
    assert result is not None and inventory is not None
    assert all(n in claim['input_binding_before'] and claim['input_binding_before'][n]['sha256']==h for n,h in inventory.items())
    assert result['counts'].get('forbidden',0)==0
    for k in ('rollout','step','B1','transaction'):assert result['counts'].get(k,0)==counts[k],k
    assert len(tx_calls)==len(tx_returns)
    assert set(source_raw)=={'dq','patch-adaptive'} and source_raw['dq'][0]==tuple(contract['new_scene'])
    assert source_raw['dq'][1]==source_raw['patch-adaptive'][1]
    for mode,(scene,pin,trace,walk) in source_raw.items():
        native=source_data[mode]['payload']['native_source_payload']
        assert native['regime']=='P' and native['scene']==list(scene) and native['full_pre_stores']
    for mode,records in pre.items():
        if len(records)==5760:
            units=selected[mode];n=len(units);mean=sum(records[u][0] for u in units)/n if n else None
            census_means[mode]={'full_pre_scenes':len(records),'selected_scenes_independently_derived':n,
                'outcome_counts':dict(census_results[mode]),'candidate_pre_mean_hex':None if mean is None else mean.hex(),
                'measurement_handle_issued':mode in complete}
    stderr=(HERE/'evidence/stderr.log').read_text(encoding='utf-8')
    if receipt['child_exit_code']==0:
        assert result['tests']==4 and result['failures']==result['errors']==result['skips']==0
        assert len(complete)==2 and len(preparations)==2 and counts['B1']==6
        assert tags['PARTIAL_POST_FAILURE']==1 and tags['PARTIAL_COMPLETE_ONCE_AND_RESTORE']==1
    else:
        assert result['failures']+result['errors']>0
    out={'status':'V96_FULL_STORED_RAW_REVIEW_NATIVE_OUTCOME_PRESERVED_NOT_SCIENCE',
         'native_exit_preserved':receipt['child_exit_code'],'tests':result['tests'],
         'failures':result['failures'],'errors':result['errors'],'skips':result['skips'],
         'inputs':len(claim['input_binding_before']),'canonical_records':record_count,
         'counts':dict(counts),'stage_inventory':{str(k):v for k,v in stages.items()},
         'tag_inventory':dict(tags),'full_pre_census_diagnostics':census_means,'complete_whole_measurements':complete,
         'first_TypeError_not_JSON_serializable_in_native_stderr':'TypeError:' in stderr and 'not JSON serializable' in stderr,
         'actual_loaded_sources_bound':True,'old_checker_or_RFL_execution':False,
         'runtime_identity_reconstructed':False,'scientific_qualification':False,
         'source_sha256':sha(Path(__file__)),'started_at_utc':started,
         'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    with (HERE/'stored_audit_result.json').open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(canonical(out)+'\n')
    print(canonical(out))


if __name__=='__main__':main()
