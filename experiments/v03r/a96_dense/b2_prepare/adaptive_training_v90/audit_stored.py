"""Independent stdlib stored TD/state/read audit. No RFL/test/module execution."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]


def address(d):
    s=d['state']
    prefix=(s['x'],s['y'],s['t'],s['kappa'],s['phi'],d['z'],d['m'])
    return prefix+(d['a'],) if 'a' in d else prefix


def values(entries):
    return {address(e['address']):float.fromhex(e['value']['binary64_hex']) for e in entries}


def policy(entries):
    return {address(e['address']):e['value'] for e in entries}


def main():
    c=json.loads((HERE/'contract.json').read_bytes())
    claim=json.loads((HERE/'evidence/claim.json').read_bytes())
    end=json.loads((HERE/'evidence/exit.json').read_bytes())
    assert claim['parent_commit']==c['parent_commit']
    assert end['child_exit_code']==0 and end['input_bytes_unchanged']
    assert claim['input_binding_before']==end['input_binding_after']
    for name,m in end['input_binding_after'].items():
        b=(ROOT/name).read_bytes()
        assert len(b)==m['bytes'] and hashlib.sha256(b).hexdigest()==m['sha256'],name
    for name in ('stdout','stderr'):
        raw=(HERE/'evidence'/f'{name}.log').read_bytes()
        assert len(raw)==end[name]['bytes']
        assert hashlib.sha256(raw).hexdigest()==end[name]['sha256']
    ref={}
    for line in (ROOT/c['reference_input']['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d=json.loads(line.split('=',1)[1])
            for a,v in d['q_row_hex']:
                ref[tuple(d['context'])+(a,)]=float.fromhex(v)
    records=[json.loads(line) for line in (HERE/'evidence/stdout.log').read_text(encoding='utf-8').splitlines()]
    assert records[-1]['tag']=='RESULT'
    result=records[-1]['payload']
    assert (result['tests'],result['failures'],result['errors'],result['skips'])==(11,0,0,0)
    assert result['counts'].get('forbidden',0)==0
    td_count=trace_count=step_count=policy_changes=0

    def trace_check(trace):
        nonlocal trace_count,step_count
        rows=trace['steps'];assert rows and rows[-1]['terminal']
        assert all(not r['terminal'] for r in rows[:-1])
        assert trace['mask']=={'decision':None,'controller':None,'plant':None,'trap':None}
        assert trace['interventions']=={'members':[]}
        assert rows[-1]['outcome']==trace['outcome']
        assert [r['state']['t'] for r in rows]==list(range(1,len(rows)+1))
        trace_count+=1;step_count+=len(rows)

    def evaluate(r):
        trace_check(r['trace'])
        assert r['before']==r['after'] and r['draws']==[] and r['readonly']

    def td(r):
        nonlocal td_count,policy_changes
        trace_check(r['trace'])
        before,after=r['before'],r['after']
        assert before['mode']==after['mode'] and before['immediate']==after['immediate']
        assert before['current']['P']==after['current']['P']
        assert before['current']['X']==after['current']['X']
        assert before['source_label']==after['source_label'] and before['role']==after['role']
        numeric=before['current'] if before['mode']=='dq' else before['learning_values']
        work=values(numeric['Q'])
        def effective(q):return work.get(q,ref[q])
        ep=r['episode'];initial=(1,1,0,ep['kappa'],ep['tape']['phase'])
        state=initial;z=r['trace']['option_in_force'];m=0;order=[];contexts=[]
        for i,row in enumerate(r['trace']['steps']):
            d=r['draws'][i];assert d['i']==i and d['a_cmd']==row['a_cmd']
            context=state+(z,m);q=context+(row['a_cmd'],)
            allowed=sorted(a[-1] for a in ref if a[:-1]==context)
            assert allowed==d['admissible'] and row['a_cmd'] in allowed
            epsilon=r['parameters']['epsilon']['rational']
            explore=ep['coins'][i]*epsilon[1]<epsilon[0]*(1<<64)
            assert explore==d['explore']
            if explore:
                n=len(allowed);limit=(1<<64)-((1<<64)%n)
                accepted=next(v for v in ep['action_draws'][i] if v<limit)
                assert row['a_cmd']==allowed[accepted%n]
            else:
                # Behaviour uses the frozen PRE-EPISODE numeric table, not work.
                pre_values=values(numeric['Q'])
                greedy=min(allowed,key=lambda a:(-pre_values.get(context+(a,),ref[context+(a,)]),a))
                patch=policy(before['current']['D']) if before['mode']!='dq' else {}
                assert row['a_cmd']==patch.get(context,greedy)
            current=effective(q);target=float.fromhex(row['reward']['binary64_hex'])
            s=row['state'];next_state=(s['x'],s['y'],s['t'],s['kappa'],s['phi'])
            nz,nm=row['control']['z'],row['control']['m']
            if not row['terminal']:
                next_actions=[a for a in ref if a[:-1]==next_state+(nz,nm)]
                target+=max(effective(a) for a in next_actions)
            work[q]=current+0.5*(target-current)
            if q not in order:order.append(q)
            contexts.append(context)
            state,z,m=next_state,nz,nm
        edits=r['numeric_edits']
        assert [address(e['address']) for e in edits]==order
        assert all(float.fromhex(e['value']['binary64_hex']).hex()==work[q].hex()
                   for e,q in zip(edits,order))
        canonical={q:v for q,v in work.items() if v!=ref[q]}
        observed=values((after['current'] if after['mode']=='dq' else after['learning_values'])['Q'])
        assert {k:v.hex() for k,v in observed.items()}=={k:v.hex() for k,v in canonical.items()}
        initial_policy=policy(before['current']['D']);final_policy=dict(initial_policy)
        expected=[]
        if before['mode']=='patch-adaptive':
            assert not before['current']['Q'] and not after['current']['Q']
            for context in dict.fromkeys(contexts):
                if context in initial_policy:
                    allowed=[q[-1] for q in ref if q[:-1]==context]
                    action=min(allowed,key=lambda a:(-canonical.get(context+(a,),ref[context+(a,)]),a))
                    final_policy[context]=action;expected.append((context,action))
        assert [(address(e['address']),e['value']) for e in r['policy_improvement_edits']]==expected
        assert policy(after['current']['D'])==final_policy
        policy_changes+=sum(initial_policy[k]!=v for k,v in final_policy.items())
        assert after['completed_episodes']==before['completed_episodes']+1
        td_count+=1

    for row in records[:-1]:
        tag,r=row['tag'],row['payload']
        if tag in ('PATCH_EPISODE','EXPLORATION','WARMUP_EPISODE','ROLE_EPISODE','ZERO_TD_POLICY_DISTINCTION'):
            td(r)
        elif tag in ('INITIAL_FULL_READ','PATCH_CHECKPOINT','READONLY_EVAL'):
            evaluate(r)
        elif tag=='DQ_ORIGINAL_DIFFERENTIAL':
            td(r['revised']);evaluate(r['checkpoint'])
            assert r['original_trace']==r['revised']['trace']
            assert r['original_edits']==r['revised']['numeric_edits']
            assert r['original_full_post']==r['revised']['after']['current']
            assert r['original_checkpoint_trace']==r['checkpoint']['trace']
            trace_check(r['original_trace']);trace_check(r['original_checkpoint_trace'])
        elif tag=='EMPTY_MODE_TRANSFER_NOT_F1':
            td(r['patch']);td(r['dq'])
        elif tag=='PLANNED_PARTIAL':
            assert r['complete_trace'] is None and not r['completed_handle'] and not r['retry']
            assert 'scripted rejection exhausted' in r['traceback']
            assert r['before']['current']==r['after']['current']
            assert r['before']['learning_values']==r['after']['learning_values']
            assert r['after']['completed_episodes']==0
        elif tag not in ('INDEPENDENT_ROLES','ORIGINAL_GUARD_RETAINED','REBINDING_REFUSED'):
            raise AssertionError('unknown record '+tag)
    assert trace_count+1==result['counts']['rollout'] # planned incomplete attempt has zero steps
    assert step_count==result['counts']['step']
    assert td_count==12
    print(json.dumps({'status':'STORED_STDLIB_AUDIT_OK_NOT_SCIENCE','records':len(records),
        'complete_raw_traces':trace_count,'raw_steps':step_count,'audited_revised_TD_episodes':td_count,
        'literal_policy_action_changes':policy_changes,'source_inputs_preserved':len(end['input_binding_after']),
        'scope_limit':'No reconstruction of runtime object identity; no scientific qualification.'}))


if __name__=='__main__':main()
