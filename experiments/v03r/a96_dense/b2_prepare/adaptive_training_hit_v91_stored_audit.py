"""Stdlib-only full stored v91 audit; never imports RFL, v90/v91 tests or code.
Verifies numeric TD and typed state contents, not runtime identity or science.
"""
from collections import Counter
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent/'adaptive_training_hit_v91'


def key(d):
    s=d['state'];result=(s['x'],s['y'],s['t'],s['kappa'],s['phi'])
    if 'z' in d:result+=(d['z'],d['m'])
    return result+(d['a'],) if 'a' in d else result


def qmap(items):return {key(v['address']):float.fromhex(v['value']['binary64_hex']) for v in items}
def dmap(items):return {key(v['address']):v['value'] for v in items}
def skey(s):return tuple(s[k] for k in ('x','y','t','kappa','phi'))


def main():
    contract=json.loads((HERE/'contract.json').read_bytes())
    claim=json.loads((HERE/'evidence/claim.json').read_bytes())
    end=json.loads((HERE/'evidence/exit.json').read_bytes())
    assert end['child_exit_code']==0 and end['input_bytes_unchanged'] and end['capture_budget_met']
    assert claim['input_binding_before']==end['input_binding_after']
    assert claim['parent_commit']==contract['parent_commit']
    for name,m in end['input_binding_after'].items():
        raw=(ROOT/name).read_bytes()
        assert len(raw)==m['bytes'] and hashlib.sha256(raw).hexdigest()==m['sha256'],name
    for name in ('stdout','stderr'):
        raw=(HERE/'evidence'/f'{name}.log').read_bytes()
        assert len(raw)==end[name]['bytes'] and hashlib.sha256(raw).hexdigest()==end[name]['sha256']
    ref={};allowed={}
    for line in (ROOT/contract['reference_input']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            row=json.loads(line.split('=',1)[1]);context=tuple(row['context'])
            allowed[context]=[a for a,v in row['q_row_hex']]
            ref.update({context+(a,):float.fromhex(v) for a,v in row['q_row_hex']})
    assert len(allowed)==13824
    rows=[json.loads(line) for line in (HERE/'evidence/stdout.log').read_text(encoding='utf-8').splitlines()]
    assert rows[-1]['tag']=='RESULT'
    result=rows[-1]['payload']
    assert (result['tests'],result['failures'],result['errors'],result['skips'])==(6,0,0,0)
    assert result['counts'].get('forbidden',0)==0
    prefix=[];complete=partial=steps=train=evals=policy_changes=0

    def behavior(r):
        before=r['before'];trace=r['trace'];state=(0,2,0,0,2)
        z,m=trace['option_in_force'],0
        p={v['address']:v['value'] for v in before['current']['P']}
        assert z==p.get(trace['base_option'],trace['base_option'])
        controllers={(skey(v['address']['state']),v['address']['cmd']):v['value'] for v in before['current']['X']}
        for item in trace['steps']:
            assert item['a_cmd'] in allowed[state+(z,m)]
            assert item['u']==controllers.get((state,item['a_cmd']),item['a_cmd'])
            assert item['a_realized']==item['u'] and not item['illegal']
            state=skey(item['state']);z,m=item['control']['z'],item['control']['m']

    def td(r):
        nonlocal train,policy_changes
        behavior(r)
        before,after=r['before'],r['after'];ep=r['episode']
        assert before['mode']==after['mode'] and before['immediate']==after['immediate']
        for k in ('role','source_label','reference_digest'):assert before[k]==after[k]
        for k in ('P','X'):assert before['current'][k]==after['current'][k]
        numeric=before['current'] if before['mode']=='dq' else before['learning_values']
        original=qmap(numeric['Q']);work=dict(original)
        state=(0,2,0,ep['kappa'],ep['tape']['phase']);z=r['trace']['option_in_force'];m=0
        contexts=[];order=[]
        effective=lambda q:work.get(q,ref[q])
        for i,item in enumerate(r['trace']['steps']):
            context=state+(z,m);q=context+(item['a_cmd'],);admissible=allowed[context]
            draw=r['draws'][i];assert draw['i']==i and draw['admissible']==admissible
            assert draw['a_cmd']==item['a_cmd']
            eps=r['parameters']['epsilon']['rational'];explore=ep['coins'][i]*eps[1]<eps[0]*(1<<64)
            assert draw['explore']==explore
            if explore:
                n=len(admissible);limit=(1<<64)-((1<<64)%n)
                accepted=next(v for v in ep['action_draws'][i] if v<limit)
                assert item['a_cmd']==admissible[accepted%n]
            else:
                greedy=min(admissible,key=lambda a:(-original.get(context+(a,),ref[context+(a,)]),a))
                patches=dmap(before['current']['D']) if before['mode']=='patch-adaptive' else {}
                assert item['a_cmd']==patches.get(context,greedy)
            current=effective(q);target=float.fromhex(item['reward']['binary64_hex'])
            nxt=skey(item['state']);nz,nm=item['control']['z'],item['control']['m']
            if not item['terminal']:
                target+=max(effective(nxt+(nz,nm,a)) for a in allowed[nxt+(nz,nm)])
            work[q]=current+0.5*(target-current)
            if q not in order:order.append(q)
            contexts.append(context);state,z,m=nxt,nz,nm
        assert [key(e['address']) for e in r['numeric_edits']]==order
        assert all(float.fromhex(e['value']['binary64_hex']).hex()==work[q].hex()
                   for e,q in zip(r['numeric_edits'],order))
        canonical={q:v for q,v in work.items() if v!=ref[q]}
        observed=qmap((after['current'] if after['mode']=='dq' else after['learning_values'])['Q'])
        assert {q:v.hex() for q,v in canonical.items()}=={q:v.hex() for q,v in observed.items()}
        patches=dmap(before['current']['D']);expected=dict(patches);edits=[]
        if before['mode']=='patch-adaptive':
            assert not before['current']['Q'] and not after['current']['Q']
            for context in dict.fromkeys(contexts):
                if context in patches:
                    action=min(allowed[context],key=lambda a:(-canonical.get(context+(a,),ref[context+(a,)]),a))
                    expected[context]=action;edits.append((context,action))
        assert [(key(e['address']),e['value']) for e in r['policy_improvement_edits']]==edits
        assert dmap(after['current']['D'])==expected
        assert after['completed_episodes']==before['completed_episodes']+1
        policy_changes+=sum(patches[k]!=v for k,v in expected.items());train+=1

    for row in rows[:-1]:
        tag,r=row['tag'],row['payload']
        if tag=='RAW_STEP':
            context=skey(r['pre_state'])+(r['pre_control']['z'],r['pre_control']['m'])
            assert r['a_cmd'] in allowed[context]
            if prefix:
                assert r['pre_state']==prefix[-1]['result']['state']
                assert r['pre_control']==prefix[-1]['result']['control']
            else:assert skey(r['pre_state'])[:3]==(0,2,0)
            prefix.append(r);steps+=1
        elif tag=='RAW_ROLLOUT':
            assert [v['result'] for v in prefix]==r['steps']
            assert r['steps'][-1]['terminal'] and r['steps'][-1]['outcome']==r['outcome']
            assert all(not v['terminal'] for v in r['steps'][:-1])
            assert r['mask']=={'decision':None,'controller':None,'plant':None,'trap':None}
            assert r['interventions']=={'members':[]}
            prefix=[];complete+=1
        elif tag=='INCOMPLETE_ROLLOUT':
            assert len(prefix)==1 and r['complete_trace'] is None
            prefix=[];partial+=1
        elif tag=='TRAIN_RECEIPT':td(r)
        elif tag=='EVAL_RECEIPT':
            behavior(r);assert r['before']==r['after'] and r['draws']==[] and r['readonly'];evals+=1
        elif tag=='DQ_DIFFERENTIAL':
            assert r['original_edits']==r['revised']['numeric_edits']
            assert r['original_post']==r['revised']['after']['current']
        elif tag=='PARTIAL_NO_RETRY':
            assert r['complete_trace'] is None and not r['numeric_or_actor_commit']
            assert r['before']['current']==r['after']['current']
            assert r['before']['learning_values']==r['after']['learning_values']
            assert r['after']['completed_episodes']==0 and 'scripted rejection exhausted' in r['traceback']
        elif tag=='ZERO_TD_LIMIT':
            assert r['numeric_value_changes']==0 and r['policy_improvement_edits']
            assert not r['scientific_qualification']
        elif tag!='NEW_FULL_SOURCE':raise AssertionError('unknown tag '+tag)
    assert not prefix
    assert complete+partial==result['counts']['rollout']==20
    assert steps==result['counts']['step']==124 and train==8 and evals==7 and partial==1
    print(json.dumps({'status':'FULL_STORED_BYTE_RAW_ACTION_TD_POLICY_AUDIT_OK_NOT_SCIENCE',
        'records':len(rows),'complete_raw_rollouts':complete,'partial_prefixes':partial,
        'raw_steps':steps,'complete_revised_episodes':train,'readonly_evaluations':evals,
        'literal_policy_action_changes':policy_changes,'bound_inputs':len(end['input_binding_after']),
        'old_v90_failures_preserved':True,'independent_expert':False,'scientific_qualification':False}))


if __name__=='__main__':main()
