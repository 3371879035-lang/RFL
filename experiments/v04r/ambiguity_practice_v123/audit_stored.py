"""Separate stdlib stored review of the new v123 capture; no old checker imports."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
HELPER_NAMES=("number","state","address","stores","identical","maps_equal","ordinary_expected")

def number(x): return float.fromhex(x['binary64_hex'])

def state(x): return tuple(x[k] for k in ('x','y','t','kappa','phi'))

def address(x,ch):
    if ch=='P':return x
    if ch=='X':return state(x['state'])+(x['cmd'],)
    return state(x['state'])+(x['z'],x['m'])+((x['a'],) if ch=='Q' else ())

def stores(x):
    return {ch:{address(e['address'],ch):number(e['value']) if ch=='Q' else e['value']
                for e in x[ch]} for ch in ('D','P','X','Q')}

def identical(a,b):
    return a.keys()==b.keys() and all((v.hex()==b[k].hex() if type(v) is float else v==b[k]) for k,v in a.items())

def maps_equal(a,b):return all(identical(a[ch],b[ch]) for ch in a)

def ordinary_expected(before, raw, rows):
    mode=before['mode'];cur=stores(before['current'])
    numeric=cur if mode=='dq' else stores(before['learning_values'])
    work=dict(numeric['Q']);trace=raw['trace']
    st=(0,2,0,raw['_episode']['kappa'],raw['_episode']['tape']['phase'])
    z,m=trace['option_in_force'],0;visited=[];seen=[]
    for step in trace['steps']:
        key=st+(z,m);q=key+(step['a_cmd'],);old=work.get(q,rows[key][q[-1]])
        target=number(step['reward'])
        if not step['terminal']:
            nxt=state(step['state'])+(step['control']['z'],step['control']['m'])
            target+=max(work.get(nxt+(a,),value) for a,value in rows[nxt].items())
        work[q]=old+0.5*(target-old)
        if q not in seen:seen.append(q)
        visited.append(key)
        st=state(step['state']);z,m=step['control']['z'],step['control']['m']
    qfinal={q:v for q,v in work.items() if v!=rows[q[:-1]][q[-1]]}
    expected=deepcopy(cur);policy=[]
    if mode=='dq':expected['Q']=qfinal;values=None
    else:
        values=deepcopy(numeric);values['Q']=qfinal
        done=set()
        for key in visited:
            if key in cur['D'] and key not in done:
                row={a:qfinal.get(key+(a,),value) for a,value in rows[key].items()}
                expected['D'][key]=min(a for a,v in row.items() if v==max(row.values()))
                policy.append(key);done.add(key)
    return expected,values,seen,policy,visited


def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True)

def digest(x):return hashlib.sha256(canonical(x).encode('ascii')).hexdigest()
def meta(p):
    b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def load(p):return json.loads(p.read_bytes())
def context_key(c):
    return tuple(c.get(x) for x in ('phase','mode','scenario_audit_only','arm','candidate'))
def return_value(receipt):
    return float(sum(number(s['reward']) for s in receipt['trace']['steps']))

def proposal_from_visible(mode, task, action):
    if action=='keep':return {'action':'keep','edits':[]}
    edits=[];seen=set()
    for key,step in zip(task['visited'],task['raw']['trace']['steps']):
        address=dict(state=dict(zip(('x','y','t','kappa','phi'),key[:5])),z=key[5],m=key[6])
        token=key+(step['a_cmd'],) if mode=='dq' else key
        if token in seen:continue
        seen.add(token)
        if mode=='dq':address['a']=step['a_cmd']
        edits.append({'store':'q' if mode=='dq' else 'decision','address':address,'value':None})
    if action.startswith('single:'):
        edits=[edits[int(action.split(':')[1])]]
    return {'action':'apply','edits':edits}

def local_key(mode, terminal, trace, action):
    rows=[];x,y=0,2
    for step in trace['steps']:
        rows.append((x,y,step['a_cmd'],step['a_realized']))
        x,y=step['state']['x'],step['state']['y']
    base=(mode,terminal,any(a!=b for x,y,a,b in rows))
    if action in ('keep','clear_factual'):return base+(action,)
    i=int(action.split(':')[1]);x,y,a,b=rows[i]
    repeated=i>0 and rows[i-1][:3]==(x,y,a)
    relation='end' if i+1==len(rows) else ('stay' if rows[i+1][:2]==(x,y) else 'move')
    return base+('single',a,repeated,relation)





def check_greedy(payload,trace,kappa,rows):
    cur=stores(payload['current']);numeric=cur if payload['mode']=='dq' else stores(payload['learning_values'])
    at=(0,2,0,kappa,2);z,m=1,0
    for x in trace['steps']:
        key=at+(z,m);row={a:numeric['Q'].get(key+(a,),v) for a,v in rows[key].items()}
        cmd=cur['D'][key] if payload['mode']=='patch-adaptive' and key in cur['D'] else min(a for a,v in row.items() if v==max(row.values()))
        assert x['a_cmd']==cmd and x['a_realized']==cmd
        at=state(x['state']);z,m=x['control']['z'],x['control']['m']
    assert trace['steps'][-1]['terminal'] and trace['outcome']==trace['steps'][-1]['outcome']
    assert trace['option_in_force']==1


def main():
    out=HERE/'evidence_audit';assert not out.exists(),'audit already attempted; no retry'
    out.mkdir()
    def save(p,x):
        with p.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(json.dumps(x,sort_keys=True,ensure_ascii=True,indent=2)+'\n')
    save(out/'claim.json',{'audit_source':meta(Path(__file__)),'native_receipt':meta(HERE/'evidence/exit.json'),
                          'automatic_retry':False,'started_at_utc':datetime.now(timezone.utc).isoformat()})
    claim=load(HERE/'evidence/claim.json');ex=load(HERE/'evidence/exit.json')
    assert ex['child_exit_code']==0 and ex['input_bytes_unchanged'] and not ex['automatic_retry']
    assert claim['input_binding_before']==ex['input_binding_after']
    for name,pin in claim['input_binding_before'].items():assert meta(ROOT/name)==pin,name
    assert meta(HERE/'evidence/raw.jsonl')==ex['raw']
    for name in ('stdout','stderr'):assert meta(HERE/('evidence/'+name+'.log'))==ex[name]
    contract=load(HERE/'contract.json');params=load(HERE/'parameters.json')
    for field in ('evidence_source','ordinal_source'):
        pin=params[field];data=(ROOT/pin['path']).read_bytes()
        assert meta(ROOT/pin['path'])=={k:pin[k] for k in ('bytes','sha256')}
        if field=='evidence_source':
            origin=json.loads(data.splitlines()[params['source_seq']])
            assert origin['tag']=='FROZEN_EVIDENCE_MODEL' and origin['payload']['model']==params['evidence_model']
        else:assert json.loads(data)['table']==params['ordinal_model']['table']
    frozen=params['ordinal_model'];model=params['evidence_model']
    rows={};ref=contract['reference'];assert meta(ROOT/ref['path'])['sha256']==ref['sha256']
    for line in (ROOT/ref['path']).read_text(encoding='utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d=json.loads(line.split('=',1)[1]);rows[tuple(d['context'])]={a:float.fromhex(v) for a,v in d['q_row_hex']}
    old=(HERE.parent/'observed_task_loop_v117/audit_stored.py').read_text(encoding='utf-8')
    new=Path(__file__).read_text(encoding='utf-8');ot,nt=ast.parse(old),ast.parse(new)
    for name in HELPER_NAMES:
        a=next(x for x in ot.body if isinstance(x,ast.FunctionDef) and x.name==name)
        b=next(x for x in nt.body if isinstance(x,ast.FunctionDef) and x.name==name)
        assert ast.get_source_segment(old,a)==ast.get_source_segment(new,b)
    rs=[json.loads(line) for line in (HERE/'evidence/raw.jsonl').read_text(encoding='ascii').splitlines()]
    assert [r['seq'] for r in rs]==list(range(len(rs)))
    tags=Counter();tasks=defaultdict(list);details={};evals=[];task=None;tx=None;source=None
    steps=0;probe_steps=0;ordinary=0;diag_writes=0;unknown=[];banks=defaultdict(list);initial={};streams=[];parents=[];practice_tx=None;branch_ready={};practice_events=defaultdict(list);active_practice=None;completed_practice={};practice_steps=0
    for r in rs:
        tag,p,c=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=context_key(c)
        if tag=='FROZEN_MODELS':
            assert p['ordinal']==frozen and p['evidence']==model
        elif tag=='SOURCE_SETUP':
            assert all(not x for x in stores(p['before']).values())
            assert len(p['edits'])==2*sum(12-d['prefix'] for d in contract['sources'])+2
            source={ch:{} for ch in ('D','P','X','Q')}
            for edit in p['edits']:
                ch={'q':'Q','decision':'D','process':'P'}[edit['store']]
                source[ch][address(edit['address'],ch)]=number(edit['value']) if ch=='Q' else edit['value']
        elif tag=='SOURCE_READY':
            assert source is not None and maps_equal(stores(p['stores']),source)
            initial[c['mode']]=p['stores'];source=None
        elif tag=='TASK_BEGIN':
            e=p['epoch']
            if c['phase']=='practice':
                assert active_practice is not None and task is not None and task['diag_calls']==1
                parents.append(task);parent=task
                item={'kappa':parent['episode']['kappa'],'trap':False};expected_mask=parent['mask']
            else:
                assert c['phase']=='stream';item=contract['schedule'][e]
                expected_mask={'decision':None,'controller':None,'plant':None,'trap':{'cell':[1,2],'t':0} if item['trap'] else None}
                assert task is None
            assert e==len(tasks[k]) and p['episode']['epoch']==e
            assert p['episode']['kappa']==item['kappa'] and p['episode']['tape']=={'phase':2,'error_flag':0,'cause_rank':9}
            assert p['environment_mask_audit_only']==expected_mask
            assert p['before']['completed_episodes']==e and p['before']['attempted_epochs']==list(range(e+1))
            if e:
                prev=tasks[k][-1]['after']
                for field in ('current','learning_values','immediate','mode','role','reference_digest','source_label'):assert p['before'][field]==prev[field]
            elif c['phase']=='practice':
                for field in ('current','learning_values','immediate'):assert p['before'][field]==branch_ready[k][field]
            else:assert p['before']['current']==p['before']['immediate']==initial[c['mode']]
            task={'before':p['before'],'episode':p['episode'],'epoch':e,'key':k,'mask':expected_mask,
                  'diag_calls':0,'transactions':0,'writes':0}
        elif tag=='TASK_RAW':
            task['raw']=deepcopy(p);task['raw']['_episode']=task['episode']
            trace=p['trace'];st=trace['steps'];steps+=len(st)
            assert st and st[-1]['terminal'] is True and trace['outcome']==st[-1]['outcome']
            assert trace['outcome'] in ('SUCCESS','COLLISION','TRAP','TIMEOUT') and trace['option_in_force']==1
            assert p['coordinates']==[[i,0,0,(1<<64)-1] for i in range(len(st))]
            assert len(p['draws'])==len(st) and all(not d['explore'] for d in p['draws'])
            assert all(d['a_cmd']==x['a_cmd'] for d,x in zip(p['draws'],st))
            assert sum(number(x['reward']) for x in st).hex()==p['return_hex']
            assert trace['mask']==task['mask']
            check_greedy(task['before'],trace,task['episode']['kappa'],rows)
        elif tag=='ORDINARY_UPDATE':
            expected,values,seen,policy,visited=ordinary_expected(task['before'],task['raw'],rows)
            task['visited']=visited;task['ordinary']=p['after'];ordinary+=1
            assert maps_equal(stores(p['after']['current']),expected)
            if values is None:assert p['after']['learning_values'] is None
            else:assert maps_equal(stores(p['after']['learning_values']),values)
            assert [address(x['address'],'Q') for x in p['numeric_edits']]==seen
            assert [address(x['address'],'D') for x in p['policy_edits']]==policy
            assert p['after']['immediate']==task['before']['immediate']
        elif tag=='DIAGNOSE_BEGIN':
            assert c['phase']=='stream' and c['arm']!='TaskTD' and task['raw']['trace']['outcome']!='SUCCESS'
            assert p['state_before']==task['ordinary'];task['diag_calls']+=1
            assert set(p['evidence'])=={'steps','z_in_force','kappa','phi'}
            assert p['budget']=={'remaining_queries':0,'remaining_writes':12}
            visible=[]
            for key,step in zip(task['visited'],task['raw']['trace']['steps']):
                item=dict(zip(('x','y','t','kappa','phi','z','m'),key))
                item.update(a_cmd=step['a_cmd'],a_realized=step['a_realized'],reward={'binary64_hex':round(number(step['reward']),6).hex()})
                visible.append(item)
            assert p['evidence']['steps']==visible
        elif tag=='SELECTION':
            assert model is not None and c['phase']=='stream'
            mode=c['mode'];terminal=task['raw']['trace']['outcome']
            n=len(proposal_from_visible(mode,task,'clear_factual')['edits'])
            actions=['keep']+['single:'+str(i) for i in range(n)]+['clear_factual']
            costs={a:len(proposal_from_visible(mode,task,a)['edits']) for a in actions}
            if c['arm']=='AlwaysClear':expected='clear_factual'
            else:
                assert c['arm'] in ('EvidenceValue','PracticeValue')
                lookup={tuple(k):number(v) for k,count,v in model['table']}
                keys={a:local_key(mode,terminal,task['raw']['trace'],a) for a in actions}
                scores={a:lookup[k] for a,k in keys.items() if k in lookup}
                missing=[a for a in actions if a not in scores]
                base='keep' if 'keep' not in scores else min(scores,key=lambda a:(-scores[a],costs[a],actions.index(a)))
                expected=base
                assert p['decision']['keys']=={a:list(k) for a,k in keys.items()}
                assert p['decision']['address_costs']==costs and p['decision']['unknown_candidates']==missing
                assert p['decision']['keep_unknown']==('keep' not in scores)
                assert {a:number(v) for a,v in p['decision']['scores'].items()}==scores
                if c['arm']=='PracticeValue':
                    eligible=[a for a in actions if a.startswith('single:') and base.startswith('single:') and a in scores and scores[a]==max(scores.values()) and keys[a]==keys[base]]
                    token=(mode,c['arm'],task['epoch'])
                    if token in completed_practice:
                        event=completed_practice[token];expected=event['selected']
                        assert p['decision']['practice_status']=='completed' and p['decision']['frozen_choice']==base
                        assert p['decision']['practice_actions']==event['actions'] and p['decision']['eligible']==eligible
                        assert {a:number(v) for a,v in p['decision']['practice_means'].items()}==event['means']
                    else:
                        status='no-ambiguity' if len(eligible)<2 else 'budget-exhausted'
                        assert p['decision']['practice_status']==status and p['decision']['eligible']==eligible
                        if status=='budget-exhausted':assert len(practice_events[mode,c['arm']])==2
                unknown.append({'mode':mode,'arm':c['arm'],'epoch':task['epoch'],'terminal':terminal,'unknown_candidates':missing,'keep_unknown':'keep' not in scores})
            assert p['candidate']==expected and p['candidate_count']==len(actions)
            assert p['proposal']==proposal_from_visible(mode,task,expected)
            task['selection']=p
        elif tag=='DIAGNOSTIC_TX_BEGIN':
            assert tx is None and p['before']==task['ordinary']
            assert p['edits']==task['selection']['proposal']['edits'] and 0<len(p['edits'])<=12
            target=deepcopy(stores(p['before']['current']))
            for edit in p['edits']:
                ch='Q' if edit['store']=='q' else 'D';a=address(edit['address'],ch)
                assert (a[:-1] if ch=='Q' else a) in task['visited'] and edit['value'] is None
                target[ch].pop(a,None)
            tx=(target,p['before']);task['writes']+=len(p['edits']);diag_writes+=len(p['edits'])
        elif tag=='DIAGNOSTIC_TX_END':
            assert tx is not None and maps_equal(stores(p['after']['current']),tx[0])
            assert p['after']['learning_values']==tx[1]['learning_values'] and p['after']['immediate']==tx[1]['immediate']
            task['transactions']+=1;tx=None
        elif tag=='TASK_COMPLETE':
            assert task['key']==k and p['trace']==task['raw']['trace']
            assert p['ordinary_after']==task['ordinary'] and p['after']['immediate']==task['before']['immediate']
            assert p['counters']=={'ordinary_updates':1,'diagnostic_calls':task['diag_calls'],'query_calls':0,'diagnostic_transactions':task['transactions'],'diagnostic_edit_addresses':task['writes']}
            assert p['route']['write_spend']==task['writes']
            if p['terminal']=='SUCCESS':assert task['diag_calls']==task['writes']==0
            if not task['transactions']:assert p['after']==task['ordinary']
            assert p['after']['completed_episodes']==task['epoch']+1
            assert task['diag_calls']==(int(p['terminal']!='SUCCESS') if c['phase']=='stream' and c['arm']!='TaskTD' else 0)
            tasks[k].append(p);details[k]=task
            if c['phase']=='practice':
                practice_steps+=len(task['raw']['trace']['steps']);task=parents.pop()
            else:task=None
        elif tag=='PRACTICE_BEGIN':
            assert c['phase']=='stream' and c['arm']=='PracticeValue' and task['diag_calls']==1 and active_practice is None
            assert p['before']==task['ordinary'] and p['parent_epoch']==task['epoch']
            d=p['frozen_decision'];chosen=p['frozen_choice'];scores={a:number(v) for a,v in d['scores'].items()}
            eligible=sorted((a for a in scores if a.startswith('single:') and scores[a]==max(scores.values()) and d['keys'][a]==d['keys'][chosen]),key=lambda a:int(a.split(':')[1]))
            assert len(eligible)>=2 and p['eligible']==eligible and p['actions']==['keep']+eligible[:2]
            events=practice_events[c['mode'],c['arm']];assert p['event_number']==len(events)+1<=2
            active_practice={'begin':p,'samples':{},'costs':{},'key':k,'root':task};events.append(p)
        elif tag=='PRACTICE_BRANCH':
            assert active_practice is not None and task is active_practice['root']
            assert c['candidate'] in active_practice['begin']['actions'] and c['scenario_audit_only']==str(task['epoch'])
            assert p['origin']==task['ordinary'] and p['parent_epoch']==task['epoch']
            assert p['branch_before']['current']==p['origin']['current'] and p['branch_before']['learning_values']==p['origin']['learning_values']
            assert p['branch_before']['completed_episodes']==0 and p['branch_before']['attempted_epochs']==[]
            assert p['branch_before']['immediate']==p['origin']['current']
            assert p['proposal']==proposal_from_visible(c['mode'],task,c['candidate'])
            branch_ready[k]=p['branch_before']
        elif tag=='PRACTICE_TX_BEGIN':
            assert practice_tx is None and p['before']==branch_ready[k]
            expected=proposal_from_visible(c['mode'],active_practice['root'],c['candidate'])
            assert p['edits']==expected['edits'] and len(p['edits'])==1
            target=deepcopy(stores(p['before']['current']))
            for edit in p['edits']:
                ch='Q' if edit['store']=='q' else 'D';assert edit['value'] is None
                target[ch].pop(address(edit['address'],ch),None)
            practice_tx=(target,p['before'])
        elif tag=='PRACTICE_TX_END':
            assert practice_tx is not None and maps_equal(stores(p['after']['current']),practice_tx[0])
            assert p['after']['learning_values']==practice_tx[1]['learning_values'] and p['after']['immediate']==practice_tx[1]['immediate']
            branch_ready[k]=p['after'];practice_tx=None
        elif tag=='PRACTICE_SAMPLE':
            assert len(tasks[k])==2 and p['candidate']==c['candidate'] and task is active_practice['root']
            values=[return_value(r) for r in tasks[k]]
            assert [number(v) for v in p['returns']]==values and p['outcomes']==[r['terminal'] for r in tasks[k]]
            cost=len(proposal_from_visible(c['mode'],task,c['candidate'])['edits']);assert p['cost']==cost
            active_practice['samples'][c['candidate']]=values;active_practice['costs'][c['candidate']]=cost
        elif tag=='PRACTICE_END':
            event=active_practice;assert event is not None and c['phase']=='stream' and k==event['key'] and task is event['root']
            assert p['before']==p['after']==event['begin']['before'] and p['parent_epoch']==task['epoch']
            actions=event['begin']['actions'];assert p['actions']==actions and list(event['samples'])==actions
            assert {a:[number(v) for v in vals] for a,vals in p['returns'].items()}==event['samples']
            means={a:sum(vals)/len(vals) for a,vals in event['samples'].items()}
            costs=event['costs'];assert p['costs']==costs and {a:number(v) for a,v in p['means'].items()}==means
            chosen=min(actions,key=lambda a:(-means[a],costs[a],actions.index(a)));assert p['selected']==chosen
            completed_practice[c['mode'],c['arm'],task['epoch']]={'actions':actions,'means':means,'selected':chosen,'costs':costs,'returns':event['samples']}
            active_practice=None
        elif tag=='RETENTION_BANK':
            assert task is None and tx is None and p['before']==p['after']
            n=p['completed_tasks'];assert n==len(tasks[k]) and n in contract['retention_checkpoints_completed_tasks']
            assert p['before']['completed_episodes']==n
            if n:assert p['before']==tasks[k][-1]['after']
            else:assert p['before']['current']==p['before']['immediate']==initial[c['mode']]
            assert p['draws']==p['TD']==p['diagnostic_calls']==0
            assert [x['kappa'] for x in p['results']]==[0,1]
            stepcount=0;measured=[]
            for result in p['results']:
                tr=result['trace'];check_greedy(p['before'],tr,result['kappa'],rows)
                assert all(v is None for v in tr['mask'].values())
                value=sum(number(x['reward']) for x in tr['steps'])
                assert value.hex()==result['return_hex'];stepcount+=len(tr['steps'])
                measured.append({'kappa':result['kappa'],'outcome':tr['outcome'],'return':value})
            assert p['native_delta']=={'rollout':2,'step':stepcount,'transaction':0}
            probe_steps+=stepcount;banks[k].append({'completed_tasks':n,'results':measured})
        elif tag=='STREAM_ARM':
            receipts=tasks[k];assert len(receipts)==len(contract['schedule'])==16
            assert p['initial_state_sha256']==digest(receipts[0]['before']['current'])
            values=[return_value(x) for x in receipts]
            assert [number(v) for v in p['returns']]==values and p['outcomes']==[x['terminal'] for x in receipts]
            assert number(p['total_return']).hex()==sum(values).hex() and number(p['mean_return']).hex()==(sum(values)/16).hex()
            assert p['successes']==sum(x['terminal']=='SUCCESS' for x in receipts)
            assert p['practice_events']==len(practice_events[c['mode'],c['arm']])
            for output,field in [('diagnostic_calls','diagnostic_calls'),('diagnostic_transactions','diagnostic_transactions'),('diagnostic_edit_attempts','diagnostic_edit_addresses')]:
                assert p[output]==sum(x['counters'][field] for x in receipts)
            assert p['ordinary_updates']==16 and p['final_state']==receipts[-1]['after']
            assert [b['completed_tasks'] for b in banks[k]]==contract['retention_checkpoints_completed_tasks']
            # Full-store ordinary/edit checks also cover these explicit unread sentinels.
            final_store=stores(p['final_state']['current']);origin=stores(initial[c['mode']])
            ch='Q' if c['mode']=='dq' else 'D'
            for address_,v in origin[ch].items():
                if address_[4]==4:assert final_store[ch][address_]==v
            assert final_store['P']==origin['P'] and final_store['X']==origin['X']
            streams.append(p)
        elif tag=='RESULT':
            assert p['ordinal_model']==frozen and p['evidence_model']==model
            assert p['streams']==streams and p['parameter_updates']==0;result=p
    final=rs[-1]['payload'];assert rs[-1]['tag']=='FINAL' and final['complete'] and final['profile_restored']
    assert task is None and tx is None and source is None and not parents and active_practice is None and practice_tx is None
    stream_tasks=sum(len(v) for k,v in tasks.items() if k[0]=='stream');practice_tasks=sum(len(v) for k,v in tasks.items() if k[0]=='practice')
    assert stream_tasks==128 and practice_tasks==6*tags['PRACTICE_BEGIN']<=24
    assert tags['TASK_RAW']==tags['TASK_COMPLETE']==ordinary==stream_tasks+practice_tasks
    assert tags['RETENTION_BANK']==48 and final['counts']['rollout']==ordinary+2*tags['RETENTION_BANK']
    assert steps+probe_steps==final['counts']['step'] and final['counts']==result['counts']
    expected_tx=tags['SOURCE_READY']+ordinary+sum(bool(x['payload']['policy_edits']) for x in rs if x['tag']=='ORDINARY_UPDATE')+tags['DIAGNOSTIC_TX_END']+tags['PRACTICE_TX_END']
    assert expected_tx==final['counts']['transaction'] and len(streams)==8
    metrics=[]
    for mode in contract['modes']:
        rows_mode=[r for r in streams if r['mode']==mode]
        assert len(rows_mode)==4 and len({r['initial_state_sha256'] for r in rows_mode})==1
        arms={}
        for r in rows_mode:
            key=('stream',mode,None,r['arm'],None)
            arms[r['arm']]={'task_return_sum':number(r['total_return']),'task_return_mean':number(r['mean_return']),
                'successes':r['successes'],'tasks':16,'outcomes':r['outcomes'],'returns':[number(v) for v in r['returns']],
                'diagnostic_calls':r['diagnostic_calls'],'diagnostic_transactions':r['diagnostic_transactions'],
                'diagnostic_edit_attempts':r['diagnostic_edit_attempts'],'practice_events':r['practice_events'],'practice_rollouts':6*r['practice_events'],'retention_banks':banks[key]}
        metrics.append({'mode':mode,'arms':arms})
    events=[{'mode':k[0],'arm':k[1],'epoch':k[2],**v} for k,v in completed_practice.items()]
    output={'schema':'V123_STDLIB_ACTUAL_PRACTICE_STREAM_REVIEW','complete':True,'native_first_exit':0,
        'native_counts':final['counts'],'records':len(rs),'declared_input_pins':len(claim['input_binding_before']),
        'ordinary_full_R_L_updates_verified':ordinary,'stream_tasks':stream_tasks,'practice_tasks':practice_tasks,
        'read_only_probe_rollouts':96,'probe_steps':probe_steps,'practice_steps':practice_steps,'stream_steps':steps-practice_steps,
        'read_only_probe_draws_TD_diagnostic_writes':0,'stream_roles':8,'tasks_per_role':16,
        'frozen_parameter_updates':0,'historical_model_training_probe_cost':196,'actual_practice_events':events,
        'practice_candidate_transactions':tags['PRACTICE_TX_END'],'online_diagnostic_edit_attempts':diag_writes,
        'success_diagnostics':0,'diagnostic_support_records':unknown,'stream_metrics':metrics,
        'raw_file':meta(HERE/'evidence/raw.jsonl'),'scientific_qualification':False,'old_checker_or_native_reruns':0,
        'notes':'One separately fixed16task stream per mode/arm, same task schedule not compute matched. Live fullR+L practice branches repeat current conditions under runner-private environment capability, no future schedule supplied. Actual practice costs separate; frozen scorer not retrained. Not full-menu optimality/causal posterior/general population proof.'}
    save(HERE/'stored_audit_result.json',output)
    save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps({'complete':True,'native_counts':output['native_counts'],'records':len(rs),'practice_tasks':practice_tasks,'actual_practice_events':events,
      'stream_metrics':[{**m,'arms':{arm:{k:v for k,v in r.items() if k!='retention_banks'} for arm,r in m['arms'].items()}} for m in metrics]},sort_keys=True))

if __name__=='__main__':main()
