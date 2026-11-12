"""Separate stdlib stored review of the new v129 capture; no old checker imports."""
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





def check_greedy(payload,trace,kappa,rows,phi):
    cur=stores(payload['current']);numeric=cur if payload['mode']=='dq' else stores(payload['learning_values'])
    at=(0,2,0,kappa,phi);z,m=1,0
    for x in trace['steps']:
        key=at+(z,m);row={a:numeric['Q'].get(key+(a,),v) for a,v in rows[key].items()}
        cmd=cur['D'][key] if payload['mode']=='patch-adaptive' and key in cur['D'] else min(a for a,v in row.items() if v==max(row.values()))
        assert x['a_cmd']==cmd and x['a_realized']==cmd
        at=state(x['state']);z,m=x['control']['z'],x['control']['m']
    assert trace['steps'][-1]['terminal'] and trace['outcome']==trace['steps'][-1]['outcome']
    assert trace['option_in_force']==1


def conditional_key(mode,terminal,trace,action):
    key=local_key(mode,terminal,trace,action)
    if not action.startswith('single:'):return key+('global',)
    rows=[];x,y=0,2
    for step in trace['steps']:
        rows.append((x,y,step['a_cmd']));x,y=step['state']['x'],step['state']['y']
    i=int(action.split(':')[1]);lo=hi=i
    while lo>0 and rows[lo-1]==rows[i]:lo-=1
    while hi+1<len(rows) and rows[hi+1]==rows[i]:hi+=1
    return key+('repeated-run' if hi>lo else 'single-step',)


def memory_snapshot(samples):
    return [[list(k),len(v),{'binary64_hex':(sum(v)/len(v)).hex()}] for k,v in sorted(samples.items())]


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
    steps=0;probe_steps=0;ordinary=0;diag_writes=0;unknown=[];banks=defaultdict(list);initial={};streams=[];parents=[];practice_tx=None;branch_ready={};practice_events=defaultdict(list);active_practice=None;completed_practice={};practice_steps=0;memories=defaultdict(lambda:defaultdict(list));memory_lookups={};memory_updates=[];contested=defaultdict(set);conflict_updates=[];needs_retest=defaultdict(set);pending_recall={};reviews=[];monitors=[];retests=[]
    for r in rs:
        tag,p,c=r['tag'],r['payload'],r['context'];tags[tag]+=1;k=context_key(c)
        if tag=='FROZEN_MODELS':
            assert p['ordinal']==frozen and p['evidence']==model
        elif tag=='SOURCE_SETUP':
            assert all(not x for x in stores(p['before']).values())
            assert len(p['edits'])==2*sum(12-d['prefix'] for d in contract['sources'])+2+2*len(contract['prefix_wait_source']['times'])
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
                item={'kappa':parent['episode']['kappa'],'phi':parent['episode']['tape']['phase'],'trap':False};expected_mask=parent['mask']
            else:
                assert c['phase']=='stream';item=contract['schedule'][e]
                expected_mask={'decision':None,'controller':None,'plant':None,'trap':{'cell':[1,2],'t':0} if item['trap'] else None}
                assert task is None
            assert e==len(tasks[k]) and p['episode']['epoch']==e
            assert p['episode']['kappa']==item['kappa'] and p['episode']['tape']=={'phase':item['phi'],'error_flag':0,'cause_rank':12}
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
            check_greedy(task['before'],trace,task['episode']['kappa'],rows,task['episode']['tape']['phase'])
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
            assert c['arm'] in ('FreshPractice','NaiveMemory','FailureRefresh','AwareMemory')
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
            if c['arm'] in ('FreshPractice','NaiveMemory','FailureRefresh','AwareMemory'):
                eligible=[a for a in actions if a.startswith('single:') and base.startswith('single:') and a in scores and scores[a]==max(scores.values()) and keys[a]==keys[base]]
                token=(mode,c['arm'],task['epoch'])
                if token in memory_lookups:assert memory_lookups[token]['actions']==['keep']+eligible[:2]
                recalled=memory_lookups.get(token)
                if recalled is not None and recalled['selected'] is not None:
                    expected=recalled['selected']
                    assert p['decision']['practice_status']=='memory-hit' and p['decision']['frozen_choice']==base
                    assert p['decision']['eligible']==eligible and p['decision']['memory_info']==recalled['info']
                    assert p['decision']['memory_actions']==recalled['actions']
                elif token in completed_practice:
                    event=completed_practice[token];expected=event['selected']
                    assert p['decision']['practice_status']=='completed' and p['decision']['frozen_choice']==base
                    assert p['decision']['practice_actions']==event['actions'] and p['decision']['eligible']==eligible
                    assert {a:number(v) for a,v in p['decision']['practice_means'].items()}==event['means']
                else:
                    status='no-ambiguity' if len(eligible)<2 else 'budget-exhausted'
                    assert p['decision']['practice_status']==status and p['decision']['eligible']==eligible
                    if status=='budget-exhausted':assert len(practice_events[mode,c['arm']])==contract['practice']['event_cap']
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
        elif tag=='PREDICTION_REVIEW':
            assert c['arm']=='FailureRefresh' and c['phase']=='stream' and task['diag_calls']==1
            mk=(c['mode'],c['arm']);pending=pending_recall[mk]
            assert pending is not None and p['pending']==pending and p['epoch']==task['epoch']
            context=[task['episode']['kappa'],task['episode']['tape']['phase']]
            terminal=task['raw']['trace']['outcome']
            expected=(terminal in ('COLLISION','TRAP','TIMEOUT') and task['epoch']==pending['epoch']+1 and context==pending['context'])
            assert p['context']==context and p['terminal']==terminal and p['requires_retest']==expected
            assert p['before']==[list(k) for k in sorted(needs_retest[mk])]
            if expected:needs_retest[mk].add(tuple(pending['key']))
            assert p['after']==[list(k) for k in sorted(needs_retest[mk])]
            assert p['memory_unchanged']==memory_snapshot(memories[mk])
            reviews.append({'mode':c['mode'],**p})
        elif tag=='RETEST_COMPLETED':
            assert c['arm']=='FailureRefresh' and c['phase']=='stream' and task['diag_calls']==1
            mk=(c['mode'],c['arm']);event=completed_practice[c['mode'],c['arm'],task['epoch']]
            expected={conditional_key(c['mode'],task['raw']['trace']['outcome'],task['raw']['trace'],a) for a in event['actions']}
            assert p['epoch']==task['epoch'] and p['before']==[list(k) for k in sorted(needs_retest[mk])]
            assert p['tested_keys']==[list(k) for k in sorted(expected)]
            needs_retest[mk].difference_update(expected)
            assert p['after']==[list(k) for k in sorted(needs_retest[mk])]
            retests.append({'mode':c['mode'],**p})
        elif tag=='RECALL_MONITOR':
            assert c['arm']=='FailureRefresh' and c['phase']=='stream' and task is None
            mk=(c['mode'],c['arm']);receipt=tasks[k][-1];e=len(tasks[k])-1
            assert p['epoch']==e and p['terminal']==receipt['terminal'] and p['before']==pending_recall.get(mk)
            lookup=memory_lookups.get((c['mode'],c['arm'],e));expected=None
            if lookup is not None and lookup['selected'] is not None:
                selected=lookup['selected'];info=lookup['info']
                assert receipt['counters']['diagnostic_transactions']==int(selected!='keep')
                expected={'epoch':e,'context':[contract['schedule'][e]['kappa'],contract['schedule'][e]['phi']],
                          'candidate':selected,'key':info['keys'][selected],'predicted_mean':info['scores'][selected]}
            assert p['after']==expected and p['needs_retest']==[list(k) for k in sorted(needs_retest[mk])]
            assert p['diagnostic_memory']==memory_snapshot(memories[mk])
            pending_recall[mk]=expected;monitors.append({'mode':c['mode'],**p})
        elif tag=='MEMORY_LOOKUP':
            assert c['phase']=='stream' and c['arm'] in ('NaiveMemory','FailureRefresh','AwareMemory') and task['diag_calls']==1
            assert p['epoch']==task['epoch'] and p['table']==memory_snapshot(memories[c['mode'],c['arm']])
            actions=p['actions'];mode=c['mode'];terminal=task['raw']['trace']['outcome']
            keys={a:conditional_key(mode,terminal,task['raw']['trace'],a) for a in actions}
            lookup={key:sum(v)/len(v) for key,v in memories[mode,c['arm']].items()}
            supported=all(key in lookup for key in keys.values())
            assert p['info']['keys']=={a:list(key) for a,key in keys.items()} and p['info']['supported']==supported
            selected=None
            if supported:
                scores={a:lookup[key] for a,key in keys.items()}
                costs={a:len(proposal_from_visible(mode,task,a)['edits']) for a in actions}
                selected=min(actions,key=lambda a:(-scores[a],costs[a],actions.index(a)))
                assert {a:number(v) for a,v in p['info']['scores'].items()}==scores
            assert p['raw_selected']==selected and p['contested_keys']==[list(k) for k in sorted(contested[mode,c['arm']])]
            assert p['needs_retest']==[list(k) for k in sorted(needs_retest[mode,c['arm']])]
            status='naive-covered' if selected is not None else 'unsupported'
            if c['arm']=='AwareMemory' and selected is not None:
                if any(key in contested[mode,c['arm']] for key in keys.values()):selected=None;status='contested-key'
                else:
                    same=[a for a in actions if scores[a]==scores[selected] and keys[a]==keys[selected]]
                    if len(same)>1:selected=None;status='duplicate-best-key'
                    else:status='supported-unique'
            if c['arm']=='FailureRefresh' and selected is not None and any(key in needs_retest[mode,c['arm']] for key in keys.values()):
                selected=None;status='observed-failure-review'
            assert p['selected']==selected and p['status']==status
            memory_lookups[mode,c['arm'],task['epoch']]={'actions':actions,'selected':selected,'raw_selected':p['raw_selected'],'status':status,'info':p['info']}
        elif tag=='MEMORY_UPDATE':
            assert c['phase']=='stream' and c['arm'] in ('NaiveMemory','FailureRefresh','AwareMemory') and task['diag_calls']==1
            token=(c['mode'],c['arm'],task['epoch']);event=completed_practice[token]
            assert p['epoch']==task['epoch'] and p['before']==memory_snapshot(memories[c['mode'],c['arm']])
            assert len(p['samples'])==len(event['actions'])
            for action,item in zip(event['actions'],p['samples']):
                key=conditional_key(c['mode'],task['raw']['trace']['outcome'],task['raw']['trace'],action)
                vals=event['returns'][action]
                assert item['key']==list(key) and [number(v) for v in item['returns']]==vals
                memories[c['mode'],c['arm']][key].extend(vals)
            assert p['after']==memory_snapshot(memories[c['mode'],c['arm']])
            memory_updates.append({'mode':c['mode'],'epoch':task['epoch'],'new_table':p['after']})
        elif tag=='MEMORY_CONFLICT_UPDATE':
            assert c['arm']=='AwareMemory' and c['phase']=='stream' and task['diag_calls']==1
            token=(c['mode'],c['arm'],task['epoch']);event=completed_practice[token]
            assert p['epoch']==task['epoch'] and p['before']==[list(k) for k in sorted(contested[c['mode'],c['arm']])]
            grouped=defaultdict(list)
            for action,vals in event['returns'].items():
                key=conditional_key(c['mode'],task['raw']['trace']['outcome'],task['raw']['trace'],action)
                grouped[key].append((action,sum(vals)/len(vals)))
            conflicts={k:v for k,v in grouped.items() if len({mean.hex() for a,mean in v})>1}
            expected=[{'key':list(k),'action_means':[[a,{'binary64_hex':mean.hex()}] for a,mean in v]} for k,v in sorted(conflicts.items())]
            assert p['conflicts']==expected
            contested[c['mode'],c['arm']].update(conflicts)
            assert p['after']==[list(k) for k in sorted(contested[c['mode'],c['arm']])]
            conflict_updates.append({'mode':c['mode'],'epoch':task['epoch'],'conflicts':expected,'contested_keys':p['after']})
        elif tag=='PRACTICE_BEGIN':
            assert c['phase']=='stream' and c['arm'] in ('FreshPractice','NaiveMemory','FailureRefresh','AwareMemory') and task['diag_calls']==1 and active_practice is None
            assert p['before']==task['ordinary'] and p['parent_epoch']==task['epoch']
            d=p['frozen_decision'];chosen=p['frozen_choice'];scores={a:number(v) for a,v in d['scores'].items()}
            eligible=sorted((a for a in scores if a.startswith('single:') and scores[a]==max(scores.values()) and d['keys'][a]==d['keys'][chosen]),key=lambda a:int(a.split(':')[1]))
            assert len(eligible)>=2 and p['eligible']==eligible and p['actions']==['keep']+eligible[:2]
            events=practice_events[c['mode'],c['arm']];assert p['event_number']==len(events)+1<=contract['practice']['event_cap']
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
            assert [{f:x[f] for f in ('kappa','phi')} for x in p['results']]==contract['retention_scenes']
            stepcount=0;measured=[]
            for result in p['results']:
                tr=result['trace'];check_greedy(p['before'],tr,result['kappa'],rows,result['phi'])
                assert all(v is None for v in tr['mask'].values())
                value=sum(number(x['reward']) for x in tr['steps'])
                assert value.hex()==result['return_hex'];stepcount+=len(tr['steps'])
                measured.append({'kappa':result['kappa'],'phi':result['phi'],'outcome':tr['outcome'],'return':value})
            assert p['native_delta']=={'rollout':len(contract['retention_scenes']),'step':stepcount,'transaction':0}
            probe_steps+=stepcount;banks[k].append({'completed_tasks':n,'results':measured})
        elif tag=='STREAM_ARM':
            receipts=tasks[k];assert len(receipts)==len(contract['schedule'])==32
            assert p['initial_state_sha256']==digest(receipts[0]['before']['current'])
            values=[return_value(x) for x in receipts]
            assert [number(v) for v in p['returns']]==values and p['outcomes']==[x['terminal'] for x in receipts]
            assert number(p['total_return']).hex()==sum(values).hex() and number(p['mean_return']).hex()==(sum(values)/32).hex()
            assert p['successes']==sum(x['terminal']=='SUCCESS' for x in receipts)
            assert p['practice_events']==len(practice_events[c['mode'],c['arm']])
            assert p['diagnostic_memory']==memory_snapshot(memories[c['mode'],c['arm']])
            assert p['contested_keys']==[list(k) for k in sorted(contested[c['mode'],c['arm']])]
            assert p['memory_hits']==sum(v['selected'] is not None for token,v in memory_lookups.items() if token[:2]==(c['mode'],c['arm']))
            for output,field in [('diagnostic_calls','diagnostic_calls'),('diagnostic_transactions','diagnostic_transactions'),('diagnostic_edit_attempts','diagnostic_edit_addresses')]:
                assert p[output]==sum(x['counters'][field] for x in receipts)
            assert p['ordinary_updates']==32
            assert p['needs_retest']==[list(k) for k in sorted(needs_retest[c['mode'],c['arm']])]
            assert p['pending_recall']==(pending_recall.get((c['mode'],c['arm'])) if c['arm']=='FailureRefresh' else None) and p['final_state']==receipts[-1]['after']
            assert [b['completed_tasks'] for b in banks[k]]==contract['retention_checkpoints_completed_tasks']
            # Full-store ordinary/edit checks also cover these explicit unread sentinels.
            final_store=stores(p['final_state']['current']);origin=stores(initial[c['mode']])
            ch='Q' if c['mode']=='dq' else 'D'
            for address_,v in origin[ch].items():
                if address_[3:5]==(0,4):assert final_store[ch][address_]==v
            assert final_store['P']==origin['P'] and final_store['X']==origin['X']
            streams.append(p)
        elif tag=='RESULT':
            assert p['ordinal_model']==frozen and p['evidence_model']==model
            assert p['streams']==streams and p['parameter_updates']==0;result=p
    final=rs[-1]['payload'];assert rs[-1]['tag']=='FINAL' and final['complete'] and final['profile_restored']
    assert task is None and tx is None and source is None and not parents and active_practice is None and practice_tx is None
    stream_tasks=sum(len(v) for k,v in tasks.items() if k[0]=='stream');practice_tasks=sum(len(v) for k,v in tasks.items() if k[0]=='practice')
    assert stream_tasks==256 and practice_tasks==6*tags['PRACTICE_BEGIN']<=144
    assert tags['TASK_RAW']==tags['TASK_COMPLETE']==ordinary==stream_tasks+practice_tasks
    assert tags['RETENTION_BANK']==32 and final['counts']['rollout']==ordinary+len(contract['retention_scenes'])*tags['RETENTION_BANK']
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
                'successes':r['successes'],'tasks':32,'outcomes':r['outcomes'],'returns':[number(v) for v in r['returns']],
                'diagnostic_calls':r['diagnostic_calls'],'diagnostic_transactions':r['diagnostic_transactions'],
                'diagnostic_edit_attempts':r['diagnostic_edit_attempts'],'practice_events':r['practice_events'],'practice_rollouts':6*r['practice_events'],
                'memory_hits':r['memory_hits'],'needs_retest':r['needs_retest'],'pending_recall':r['pending_recall'],'final_diagnostic_memory':r['diagnostic_memory'],'contested_keys':r['contested_keys'],'retention_banks':banks[key]}
        metrics.append({'mode':mode,'arms':arms})
    assert len(monitors)==64
    events=[{'mode':k[0],'arm':k[1],'epoch':k[2],**v} for k,v in completed_practice.items()]
    lookups=[{'mode':k[0],'arm':k[1],'epoch':k[2],**v} for k,v in memory_lookups.items()]
    root_matches=[]
    for record in lookups:
        if record['raw_selected'] is None:continue
        mode=record['mode'];e=record['epoch'];arm=record['arm']
        own=tasks['stream',mode,None,arm,None][e];other=tasks['stream',mode,None,'AwareMemory',None][e]
        equal=all(own['ordinary_after'][f]==other['ordinary_after'][f] for f in ('current','learning_values','immediate'))
        root_matches.append({'mode':mode,'arm':arm,'epoch':e,'same_post_TD_R_L_I_as_preventative_aware':equal})
    output={'schema':'V129_STDLIB_MIXED_MEMORY_QUALITY_COST_REVIEW','complete':True,'native_first_exit':0,
        'native_counts':final['counts'],'records':len(rs),'declared_input_pins':len(claim['input_binding_before']),
        'ordinary_full_R_L_updates_verified':ordinary,'stream_tasks':stream_tasks,'practice_tasks':practice_tasks,'read_only_probe_rollouts':96,
        'probe_steps':probe_steps,'practice_steps':practice_steps,'stream_steps':steps-practice_steps,'base_frozen_parameter_updates':0,
        'observed_prediction_reviews':reviews,'recall_monitors':monitors,'actual_retests':retests,'online_memory_updates':memory_updates,'memory_lookups':lookups,'memory_conflict_updates':conflict_updates,'recall_root_comparisons':root_matches,
        'historical_base_training_probe_cost':196,'actual_practice_events':events,'practice_candidate_transactions':tags['PRACTICE_TX_END'],
        'online_diagnostic_edit_attempts':diag_writes,'success_diagnostics':0,'stream_metrics':metrics,'raw_file':meta(HERE/'evidence/raw.jsonl'),
        'scientific_qualification':False,'old_checker_or_native_reruns':0,
        'notes':'New3context mixed stream with prospectively declared phase metrics and same3event practicecap allarms. FreshPractice retains ordinary state but no diagnosticM. Post-failure review has no numeric memory penalty: only a finite investigation trigger. No automatic rollback or extra repair menu. Prospective targeted adverse key-alias case, not blind population inference. Naive/Aware memory both learn actual intervention returns; aware rule declines non-identifying same-key ties, and records locally conflicting outcomes as contested. Not calibrated statistical uncertainty or general safety guarantee.'}
    save(HERE/'stored_audit_result.json',output)
    save(out/'exit.json',{'complete':True,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'result':meta(HERE/'stored_audit_result.json')})
    print(json.dumps({'complete':True,'native_counts':output['native_counts'],'records':len(rs),'memory_lookups':lookups,'actual_practice_events':events,'memory_conflicts':conflict_updates,
      'stream_metrics':[{**m,'arms':{arm:{k:v for k,v in r.items() if k not in ('retention_banks','final_diagnostic_memory')} for arm,r in m['arms'].items()}} for m in metrics]},sort_keys=True))

if __name__=='__main__':main()
