"""First independent stdlib-only stored review of the new v107 finite capture.

This program never imports experimental modules or old checkers, constructs
native objects or handles, or reruns native data. Copied primitive stdlib helper
functions are AST/source-bound to their physical prior source. Stored content
links are evidence about values and chronology, not recovered runtime identity.
"""
import ast
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
MODES = ('dq', 'patch-adaptive')
FIELDS = ('x', 'y', 't', 'kappa', 'phi')
M64 = (1 << 64) - 1
DELTA = ((0,-1),(0,1),(-1,0),(1,0),(0,0))
START, GOAL = (0,2), (4,2)
OPEN = {(x,y) for x in range(5) for y in range(5)
        if x not in (0,4) and y != 0 and (x,y) != (2,3)} | {START,GOAL}
DIST = {GOAL:0}
queue = deque([GOAL])
while queue:
    x,y = queue.popleft()
    for dx,dy in DELTA:
        cell = (x+dx,y+dy)
        if cell in OPEN and cell not in DIST:
            DIST[cell] = DIST[(x,y)] + 1
            queue.append(cell)
COPIED_HELPERS = ["canonical","digest","meta","value","state","wire_state","addr","storemap","flat","fingerprint","maps_equal","allowed","hazard","check_step","read_reference","edit_key","apply_edits","greedy","check_policy","td","decode_native_float","verify_seal","check_source_pair","reconstructed_rollout","expected_training_before","verify_receipt"]

def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True)


def digest(x):
    return hashlib.sha256(canonical(x).encode('ascii')).hexdigest()


def meta(path):
    h,size = hashlib.sha256(),0
    with path.open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):
            h.update(b); size += len(b)
    return {'bytes':size,'sha256':h.hexdigest()}


def value(x):
    return float.fromhex(x['binary64_hex'])


def state(s):
    return tuple(s[k] for k in FIELDS)


def wire_state(s):
    return dict(zip(FIELDS,s))


def addr(a,channel):
    if channel == 'P':
        return a
    result = state(a['state'])
    return result + ((a['cmd'],) if channel == 'X' else (a['z'],a['m'])) + ((a['a'],) if channel == 'Q' else ())


def storemap(raw):
    return {ch:{addr(x['address'],ch):(value(x['value']) if ch == 'Q' else x['value'])
                for x in raw[ch]} for ch in ('D','P','X','Q')}


def flat(raw):
    maps = storemap(raw)
    return {ch:sorted([[list(k) if isinstance(k,tuple) else k,
                       v.hex() if ch == 'Q' else v] for k,v in m.items()])
            for ch,m in maps.items()}


def fingerprint(raw):
    maps = storemap(raw)
    parts = []
    for ch in ('D','P','X','Q'):
        if ch == 'P':
            lines = [f'P:{k},{v}' for k,v in maps[ch].items()]
        elif ch == 'Q':
            lines = ['Q:'+','.join(map(str,k))+'|'+v.hex() for k,v in maps[ch].items()]
        else:
            lines = [ch+':'+','.join(map(str,k+(v,))) for k,v in maps[ch].items()]
        parts.append('\n'.join(sorted(lines)).encode('utf-8'))
    return hashlib.sha256(b'\0'.join(parts)).hexdigest()


def maps_equal(x,y):
    return all(x[c] == y[c] if c != 'Q' else
               {k:v.hex() for k,v in x[c].items()} == {k:v.hex() for k,v in y[c].items()}
               for c in ('D','P','X','Q'))


def allowed(s,z,m):
    x,y,*_ = s
    legal = [a for a,(dx,dy) in enumerate(DELTA) if (x+dx,y+dy) in OPEN]
    if z == 0:
        return [a for a in legal if DIST[(x+DELTA[a][0],y+DELTA[a][1])] == DIST[(x,y)]-1]
    if z in (1,3) and m == 0:
        return [a for a in legal if (x+DELTA[a][0],y+DELTA[a][1]) != GOAL]
    if z == 2 and m == 0:
        return [a for a in legal if (x+DELTA[a][0],y+DELTA[a][1]) not in ((2,2),GOAL)]
    return legal


def hazard(t,k,phi):
    p = 6 if k == 0 else 3
    return t % p == phi % p


def check_step(p):
    s = state(p['pre_state']); c = p['pre_control']; r = p['result']
    a = p['a_cmd']; assert a == r['a_cmd'] and a in allowed(s,c['z'],c['m'])
    assert not r['illegal'] and r['u'] == r['a_realized']
    dx,dy = DELTA[r['a_realized']]
    cell = (s[0]+dx,s[1]+dy)
    if cell not in OPEN: cell = s[:2]
    ns = cell+(s[2]+1,s[3],s[4])
    assert state(r['state']) == ns
    outcome = ('COLLISION' if cell == (2,2) and hazard(ns[2],s[3],s[4]) else
               'SUCCESS' if cell == GOAL else 'TIMEOUT' if ns[2] >= 12 else None)
    assert r['outcome'] == outcome and r['terminal'] == (outcome is not None)
    reward = -0.02
    if outcome: reward += 1.0 if outcome == 'SUCCESS' else -1.0
    assert value(r['reward']).hex() == reward.hex()
    m = c['m']
    if m == 0 and ((c['z'] == 1 and cell == (2,1)) or
                   (c['z'] == 3 and cell == (2,4)) or
                   (c['z'] == 2 and s[:2] == (1,2) and not hazard(s[2],s[3],s[4]))):
        m = 1
    assert r['control'] == {'z':c['z'],'m':m}


def read_reference(spec):
    path = ROOT/spec['path']; assert meta(path)['sha256'] == spec['sha256']
    rows = {}
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('DECISION_CONTEXT='):
                d=json.loads(line.split('=',1)[1]); key=tuple(d['context'])
                assert key not in rows
                row={a:float.fromhex(v) for a,v in d['q_row_hex']}
                assert sorted(row) == allowed(key[:5],key[5],key[6])
                rows[key] = row
    expected = {(x,y,t,k,phi,z,m) for x,y in OPEN-{GOAL} for t in range(12)
                for k in (0,1) for phi in range(6) for z in range(4) for m in (0,1)}
    assert set(rows) == expected and len(rows) == 13824
    order = sorted(rows,key=lambda k:(k[2],k[3],k[4],k[0],k[1],k[5],k[6]))
    text='\n'.join(','.join(map(str,k))+'|'+','.join(f'{a}={v.hex()}' for a,v in sorted(rows[k].items())) for k in order)
    assert hashlib.sha256(text.encode('utf-8')).hexdigest() == spec['q_digest']
    return rows


def edit_key(e):
    return addr(e['address'],{'decision':'D','process':'P','controller':'X','q':'Q'}[e['store']])


def apply_edits(before,edits,rows):
    out=deepcopy(before); seen=set()
    for e in edits:
        ch={'decision':'D','process':'P','controller':'X','q':'Q'}[e['store']]
        k=edit_key(e); assert (ch,k) not in seen; seen.add((ch,k))
        v=value(e['value']) if ch=='Q' and e['value'] is not None else e['value']
        remove=v is None or (ch=='P' and k==v) or (ch=='X' and k[-1]==v)
        if ch=='Q' and v is not None:
            assert k[:-1] in rows and k[-1] in rows[k[:-1]]
            remove=v == rows[k[:-1]][k[-1]]
        if remove: out[ch].pop(k,None)
        else: out[ch][k]=v
    return out


def greedy(maps,rows,s,z,m,mode='dq',values=None):
    row=rows[s+(z,m)]
    if mode=='patch-adaptive' and s+(z,m) in maps['D']:
        return maps['D'][s+(z,m)]
    numeric=maps['Q'] if values is None else values['Q']
    vals={a:numeric.get(s+(z,m,a),v) for a,v in row.items()}
    best=max(vals.values())
    return min(a for a,v in vals.items() if v==best)


def check_policy(trace,maps,rows,mode='dq',values=None,episode=None,floor=False):
    s=state(trace['steps'][0]['state']); s=(0,2,0,s[3],s[4])
    z,m=trace['option_in_force'],0
    assert z==maps['P'].get(trace['base_option'],trace['base_option'])
    calls,draws=[] ,[]
    for i,r in enumerate(trace['steps']):
        legal=sorted(rows[s+(z,m)]); a=greedy(maps,rows,s,z,m,mode,values)
        explore=False
        if episode:
            coin=episode['coins'][i]; calls.append([i,0,0,coin]); explore=coin*10<(1<<64)
            if explore:
                ds=episode['rejections'][i]
                if floor:
                    calls.append([i,1,0,ds[0]]); a=legal[(ds[0]*len(legal))>>64]
                else:
                    limit=(1<<64)-((1<<64)%len(legal))
                    for c,d in enumerate(ds):
                        calls.append([i,1,c,d])
                        if d<limit: a=legal[d%len(legal)]; break
                    else: raise AssertionError('completed recorded episode exhausts declared coordinates')
        assert r['a_cmd']==a, (i,s,z,m,a,r['a_cmd'])
        site=s+(a,); assert r['u']==maps['X'].get(site,a)
        draws.append({'i':i,'explore':explore,'admissible':legal,'a_cmd':a})
        s=state(r['state']); z,m=r['control']['z'],r['control']['m']
    return calls,draws


def td(trace,episode,numeric,rows,proposal=False):
    work=dict(numeric['Q']); s=(0,2,0,episode['kappa'],episode['tape']['phase'])
    z,m=(trace['base_option'] if proposal else trace['option_in_force']),0
    order,visited,detail=[],[],[]
    for r in trace['steps']:
        q=s+(z,m,r['a_cmd']); old=work.get(q,rows[q[:-1]][q[-1]])
        target=value(r['reward']); ns=state(r['state']); nz,nm=r['control']['z'],r['control']['m']
        if not r['terminal']:
            rr=rows[ns+(nz,nm)]
            target+=max(work.get(ns+(nz,nm,a),v) for a,v in rr.items())
        work[q]=old+0.5*(target-old)
        if q not in order: order.append(q)
        visited.append(s+(z,m)); detail.append({'address':dict(state=wire_state(s),z=z,m=m,a=r['a_cmd']),
           'current_hex':old.hex(),'target_hex':target.hex(),'updated_hex':work[q].hex()})
        s,z,m=ns,nz,nm
    edits=[{'store':'q','address':dict(state=wire_state(q[:5]),z=q[5],m=q[6],a=q[7]),
            'value':{'binary64_hex':work[q].hex()}} for q in order]
    sparse={q:v for q,v in work.items() if v!=rows[q[:-1]][q[-1]]}
    return edits,sparse,visited,detail


def decode_native_float(x):
    if isinstance(x,dict):
        if set(x)=={'binary64_hex'}: return value(x)
        return {k:decode_native_float(v) for k,v in x.items()}
    if isinstance(x,list): return [decode_native_float(v) for v in x]
    return x


def verify_seal(audit):
    assert digest(decode_native_float(audit['payload']))==audit['payload_sha256']


def check_source_pair(records,rows,c,mode):
    one=lambda tag:[r['payload'] for r in records if r['tag']==tag]
    source=one('ORIGINAL_SOURCE'); pair=one('ORIGINAL_PAIR'); b1=one('NATIVE_B1_RETURN')
    assert len(source)==len(pair)==1 and len(b1)==2
    sa=source[0]['audit']; verify_seal(sa); native=sa['payload']['native_source_payload']
    assert source[0]['mode']==mode and native['regime']=='P' and native['scene']==c['source_scene']
    assert native['q_reference_sha256']==c['reference_input']['q_digest']
    assert digest(decode_native_float(native))==sa['payload']['native_source_sha256']
    raw=[r['payload'] for r in records if r['tag']=='RAW_ROLLOUT' and r['stage']=='source']
    assert len(raw)==1
    trace=raw[0]; pre=native['full_pre_stores']
    contexts=[(0,2,t,0,2,1,m) for t in range(12) for m in (0,1)]
    contexts += [(1,2,1,0,2,1,m) for m in (0,1)]+[(0,2,0,1,2,1,0)]
    expected={'D':[],'P':[[0,1],[3,2]],'X':[[[0,2,0,0,2,4],3],[[0,2,0,1,2,4],3],[[1,2,1,0,2,4],2]],'Q':[]}
    if mode=='dq': expected['Q']=sorted([[list(x+(4,)),(max(rows[x].values())+1.0).hex()] for x in contexts])
    else: expected['D']=sorted([[list(x),4] for x in contexts])
    assert pre==expected
    premap={ch:{tuple(k) if isinstance(k,list) else k:float.fromhex(v) if ch=='Q' else v for k,v in pre[ch]} for ch in ('D','P','X','Q')}
    check_policy(trace,premap,rows,mode,{'D':{},'P':{},'X':{},'Q':{}} if mode=='patch-adaptive' else None)
    source_rows=native['raw_factual']; assert len(source_rows)==len(trace['steps'])
    s=(0,2,0,c['source_scene'][0],c['source_scene'][1]); z,m=trace['option_in_force'],0
    owners=[]; gamma=['ProcessCommit'] if trace['option_in_force']!=trace['base_option'] else []
    controller=[]
    for i,(r,captured) in enumerate(zip(trace['steps'],source_rows)):
        row=rows[s+(z,m)]; best=max(row.values()); optimal=[a for a,v in row.items() if abs(v-best)<=1e-12]
        assert captured=={'a_cmd':r['a_cmd'],'a_realized':r['a_realized'],'illegal':r['illegal'],
           'm':m,'outcome':r['outcome'],'post_control':[r['control']['z'],r['control']['m']],
           'post_state':list(state(r['state'])),'pre_state':list(s),'reward_hex':r['reward']['binary64_hex'],
           'terminal':r['terminal'],'u':r['u'],'z':z}
        if r['a_cmd'] not in optimal: owners.append(s+(z,m)); gamma.append('Decision_'+str(i))
        if r['u']!=r['a_cmd']:
            controller.append('ControllerSite_'+str(s[0])+'_'+str(s[1])+'_'+str(s[2])+'_'+str(r['a_cmd']))
        s,z,m=state(r['state']),r['control']['z'],r['control']['m']
    gamma+=controller
    truth=native['truth_evaluator_only']
    assert truth['Gamma_P_star']==gamma and len(owners)==7 and len(gamma)==10
    pa=pair[0]; verify_seal(pa)
    older=pa['payload']['original_v74_pair']; verify_seal(older); pp=older['payload']
    assert pp['whole_oracle_units']==gamma and pp['residual_units_preserved']==['ProcessCommit']+controller
    assert pp['cell_units']==[g for g in gamma if g.startswith('Decision_')]
    assert pp['native_B1_arm_calls']==2 and pp['architecture']==('D_Q' if mode=='dq' else 'D_patch')
    assert pp['source_sha256']==sa['payload']['native_source_sha256'] and pa['payload']['source_sha256']==sa['payload_sha256']
    returns=[]; total=0.0
    for r in reversed(trace['steps']): total=value(r['reward'])+total; returns.append(total)
    returns.reverse()
    target=deepcopy(premap)
    for owner in owners:
        if mode=='dq':
            q=owner+(4,); v=returns[owner[2]]
            if v==rows[owner][4]: target['Q'].pop(q,None)
            else: target['Q'][q]=v
        else: target['D'].pop(owner,None)
    for i,(arm,native_b1) in enumerate(zip(pp['all_owner_receipts'],b1)):
        observed=storemap(native_b1['full_post']); desired=premap if i==0 else target
        assert maps_equal(observed,desired) and flat(native_b1['full_post'])==arm['full_post_stores']
        ledger=json.loads(native_b1['ledger_canonical'])
        assert native_b1['ledger_canonical']==arm['ledger_canonical']
        assert ledger['fingerprint_pre']==native['fingerprint_pre'] and ledger['fingerprint_post']==fingerprint(native_b1['full_post'])
        assert len(native_b1['receipts'])==len(owners)
        assert [addr(r['address'],'D') for r in native_b1['receipts']]==owners
        expected_status='EVALUABLE_NOOP' if i==0 else 'APPLIED'
        receipts=[','.join(map(str,x))+'|'+expected_status+'|'+str(i) for x in owners]
        assert ledger['receipts']==sorted(receipts)
        assert all(r['status']==expected_status and r['store_changed']==bool(i) for r in native_b1['receipts'])
        changes=[]
        if mode=='dq':
            for q in set(premap['Q']) | set(observed['Q']):
                before=premap['Q'].get(q,rows[q[:-1]][q[-1]])
                after=observed['Q'].get(q,rows[q[:-1]][q[-1]])
                if before!=after: changes.append(abs(after-before))
        assert ledger['scalar_metrics_applicable']==(mode=='dq') and ledger['n_scalar']==len(changes)
        assert float(ledger['sum_abs_delta']).hex()==math.fsum(changes).hex()
        assert float(ledger['max_abs_delta']).hex()==max(changes,default=0.0).hex()
    after=one('ORIGINAL_PAIR_AFTER')
    if after: assert after==pair
    return b1,pa


def reconstructed_rollout(payload):
    trace,k,tape=payload['trace'],payload['kappa'],payload['tape']
    assert type(k) is int and k in (0,1) and 0<=tape['phase']<6
    assert 0<=tape['error_flag']<2 and 0<=tape['cause_rank']<60
    assert trace['mask']=={'decision':None,'controller':None,'plant':None,'trap':None}
    assert trace['interventions']=={'members':[]}
    assert trace['base_option'] in range(4) and trace['option_in_force'] in range(4)
    s=(0,2,0,k,tape['phase']); control={'z':trace['option_in_force'],'m':0}
    assert 1<=len(trace['steps'])<=12
    for i,result in enumerate(trace['steps']):
        assert s[2]==i
        check_step({'pre_state':wire_state(s),'pre_control':control,
                    'a_cmd':result['a_cmd'],'result':result})
        assert i==len(trace['steps'])-1 or not result['terminal']
        s,control=state(result['state']),result['control']
    assert trace['steps'][-1]['terminal'] and trace['outcome']==trace['steps'][-1]['outcome']
    assert trace['control']==control
    return float(sum(value(step['reward']) for step in trace['steps']))


def expected_training_before(previous,e):
    result=deepcopy(previous)
    result['attempted_epochs']=list(range(e+1))
    return result


def verify_receipt(r,rows,previous,initial,mode,role,e,raw):
    assert r['epoch']==e and r['episode']==declared_episode(e)
    assert r['parameters']=={'alpha':{'rational':[1,2]},'epsilon':{'rational':[1,10]}}
    before,after=r['before'],r['after']
    assert before==expected_training_before(previous,e)
    assert before['completed_episodes']==e and after['completed_episodes']==e+1
    assert before['attempted_epochs']==after['attempted_epochs']==list(range(e+1))
    for p in (before,after):
        assert p['mode']==mode and p['role']==role
        assert p['immediate']==initial['immediate']
        assert p['source_label']==initial['source_label'] and p['reference_digest']==initial['reference_digest']
        assert p['revision']==initial['revision']
    assert r['trace']==raw['trace'] and raw['kappa']==r['episode']['kappa'] and raw['tape']==r['episode']['tape']
    b,a=storemap(before['current']),storemap(after['current'])
    assert b['P']==a['P'] and b['X']==a['X']
    numeric=storemap(before['current'] if mode=='dq' else before['learning_values'])
    calls,draws=check_policy(r['trace'],b,rows,mode,None if mode=='dq' else numeric,r['episode'])
    assert calls==r['coordinates'] and draws==r['draws']
    edits,sparse,visited,details=td(r['trace'],r['episode'],numeric,rows)
    assert edits==r['numeric_edits']
    updated=storemap(after['current'] if mode=='dq' else after['learning_values'])
    assert {q:v.hex() for q,v in sparse.items()}=={q:v.hex() for q,v in updated['Q'].items()}
    expected_policy=[]; desired_d=dict(b['D']); seen=set()
    if mode=='patch-adaptive':
        assert not b['Q'] and not a['Q'] and all(not updated[ch] for ch in ('D','P','X'))
        for context in visited:
            if context in b['D'] and context not in seen:
                row=rows[context]; vals={act:sparse.get(context+(act,),v) for act,v in row.items()}
                chosen=min(act for act,v in vals.items() if v==max(vals.values()))
                expected_policy.append({'store':'decision','address':dict(state=wire_state(context[:5]),
                                        z=context[5],m=context[6]),'value':chosen})
                desired_d[context]=chosen; seen.add(context)
        assert a['D']==desired_d
        assert set(a['D'])==set(storemap(initial['current'])['D'])
    else:
        assert not a['D'] and after['learning_values'] is None
    assert expected_policy==r['policy_improvement_edits']
    total=float(sum(value(step['reward']) for step in r['trace']['steps']))
    assert total.hex()==r['return_hex']
    changed=not maps_equal(numeric,updated)
    policy_changed=b['D']!=a['D']
    rejection=sum(1 for call in calls if call[1]==1 and call[2]>0)
    return after,{'numeric_changed':changed,'policy_changed':policy_changed,
                  'exploration_steps':sum(d['explore'] for d in draws),
                  'rejection_followup_coordinates':rejection,
                  'TD_addresses':len(edits),'TD_step_details':len(details)}


def declared_episode(e):
    assert e == 0
    return {'epoch':0,'kappa':0,'proposal':0,
            'tape':{'phase':2,'error_flag':0,'cause_rank':0},
            'coins':[M64 for _ in range(12)],
            'rejections':[[M64,i] for i in range(12)]}


def copied_helpers_review():
    previous=HERE.parent/'dense_resource_workload_v106/audit_dense_kernel_return_revised.py'
    oldtext=previous.read_text(encoding='utf-8'); newtext=Path(__file__).read_text(encoding='utf-8')
    old=ast.parse(oldtext); new=ast.parse(newtext)
    pins={}
    for name in COPIED_HELPERS:
        a=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name==name)
        b=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name==name)
        assert ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False),name
        assert ast.get_source_segment(oldtext,a)==ast.get_source_segment(newtext,b),name
        pins[name]=hashlib.sha256(ast.get_source_segment(oldtext,a).encode('utf-8')).hexdigest()
    return {'mechanically_copied_stdlib_functions':len(pins),'source':meta(previous),
            'function_source_sha256':pins,'old_checker_import_or_execution':False}


def kernel_return_review(claim):
    path=ROOT/'src/rfl_rebuild/env/kernel.py'
    text=path.read_text(encoding='utf-8'); tree=ast.parse(text)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RolloutTrace')
    f=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='return_value')
    expected=ast.parse('def return_value(self):\n    return float(sum(s.reward for s in self.steps))\n').body[0].body[0]
    assert ast.dump(f.body[-1],include_attributes=False)==ast.dump(expected,include_attributes=False)
    assert sys.implementation.name=='cpython' and tuple(sys.version_info[:3])==(3,12,14)
    assert str(Path(claim['command'][0]).resolve()).casefold()==str(Path(sys.executable).resolve()).casefold()
    return {'physical_source':meta(path),'method':'RolloutTrace.return_value',
            'source_sha256':hashlib.sha256(ast.get_source_segment(text,f).encode('utf-8')).hexdigest(),
            'runtime':sys.version,'same_native_executable':True,
            'episode_builtin_sum_bank_leftfold_TD_chronological_B1_reversefold_preserved':True}


def sample_of_100():
    cells=[(k,phi,flag,proposal) for k in (0,1) for phi in range(6)
           for flag in (0,1) for proposal in range(4)]
    sample=[]
    for n in range(100):
        q,r=divmod(n,96); k,phi,flag,proposal=cells[r]
        sample.append([k,phi,flag,(7*q+37*r)%60,proposal])
    return sample


def verify_prepared(p,source_records,rows,c,mode,healthy):
    adapted=deepcopy(source_records)
    for record in adapted:
        if record['tag']=='RAW_ROLLOUT':
            record['payload']=record['payload']['trace']
    b1,pair=check_source_pair(adapted,rows,c,mode)
    origin=p['origin']; declaration=origin['declaration']; seal=digest(declaration)
    assert declaration['original_pair']==pair and declaration['mode_before_arms']==mode
    bound=next(r['payload'] for r in source_records if r['tag']=='BOUND_BEFORE_ARMS')
    bound_native=deepcopy(bound['payload'])
    truth=bound_native['source']['payload']['native_source_payload']['truth_evaluator_only']
    truth['whole_optimal_set_tolerance']=value(truth['whole_optimal_set_tolerance'])
    assert digest(bound_native)==bound['payload_sha256']
    assert bound['payload']['source']==next(r['payload']['audit'] for r in source_records if r['tag']=='ORIGINAL_SOURCE')
    assert bound['payload']['decision_mode_before_arms']==mode
    native_source=bound['payload']['source']['payload']['native_source_payload']
    assert flat(bound['payload']['full_pre'])==native_source['full_pre_stores']
    assert bound['payload']['reference_digest']==c['reference_input']['q_digest']
    bound_seq=next(r['seq'] for r in source_records if r['tag']=='BOUND_BEFORE_ARMS')
    source_seq=next(r['seq'] for r in source_records if r['tag']=='ORIGINAL_SOURCE')
    b1_sequences=[r['seq'] for r in source_records if r['tag']=='NATIVE_B1_RETURN']
    pair_seq=next(r['seq'] for r in source_records if r['tag']=='ORIGINAL_PAIR')
    assert source_seq<bound_seq<min(b1_sequences)<=max(b1_sequences)<pair_seq
    assert declaration['bound_source_sha256']==bound['payload_sha256']
    assert origin['original_pair_seal']==seal and digest(origin)==p['origin_sha256']
    plan=origin['engineering_plan']
    assert plan['grid']==[0,1] and plan['episodes']==[declared_episode(0)]
    assert plan['engineering_bank_indices']==list(range(100)) and plan['sample']==sample_of_100()
    assert hashlib.sha256(repr(tuple(tuple(s) for s in plan['sample'])).encode('utf-8')).hexdigest()==healthy['evaluation_sample_sha256']
    assert plan['v_pre_hex']==float(healthy['v_pre']).hex()
    assert plan['original_lock_sha256']==healthy['lock_sha256']
    assert not plan['keyed'] and not plan['formal_execution']
    assert plan['parameters']=={'alpha':{'rational':[1,2]},'epsilon':{'rational':[1,10]}}
    future=origin['original_future']; verify_seal(future)
    template=future['payload']['shared_template']
    assert template['evaluation_units']==plan['sample']
    assert template['evaluation_sha256']==healthy['evaluation_sample_sha256']
    assert template['v_pre_hex']==plan['v_pre_hex'] and template['lock_sha256']==healthy['lock_sha256']
    assert template['grid']==list(range(466)) and template['T']==465 and template['seed'] is None
    assert template['alpha']==[1,2] and template['epsilon']==[1,10]
    initial=origin['initial_composites']; assert initial==p['initial_composites']
    assert len(initial)==2
    for i,comp in enumerate(initial):
        assert comp['role']==('reference','treatment')[i] and comp['mode']==mode and comp['source_label']==seal
        assert comp['immediate']==comp['current']==b1[i]['full_post']
        assert comp['completed_episodes']==0 and comp['attempted_epochs']==[]
        assert comp['learning_values']==({'D':[],'P':[],'X':[],'Q':[]} if mode=='patch-adaptive' else None)
    return {'initial':initial,'plan':plan,'origin':origin,'states':dict(zip(('reference','treatment'),initial))}


def verify_bank_audit(audit,before,sample,attempted,complete,traces):
    assert audit['revision']=='v107-readonly-bank-v105-learner-semantics'
    assert audit['before']==before and audit['mode']==before['mode'] and audit['role']==before['role']
    assert audit['source_label']==before['source_label'] and audit['epoch']==before['completed_episodes']
    assert audit['sample']==sample and audit['attempted'] is attempted and audit['complete'] is complete
    assert audit['completed_scenes']==len(traces) and audit['traces']==traces
    assert audit['scientific_qualification'] is False
    if complete:
        assert len(traces)==100 and audit['failure'] is None
        total=0.0
        for trace in traces:
            total+=float(sum(value(step['reward']) for step in trace['steps']))
        assert audit['mean_hex']==(total/100).hex()
    else:
        assert audit['mean_hex'] is None


def raw_hash(traces):
    h=hashlib.sha256()
    for trace in traces:
        h.update((canonical(trace)+'\n').encode('ascii'))
    return h.hexdigest()


def verify_bank_raw(raw,before,rows,sample):
    assert len(raw)==100
    maps=storemap(before['current'])
    numeric=None if before['mode']=='dq' else storemap(before['learning_values'])
    total=0.0
    for record,scene in zip(raw,sample):
        p=record['payload']; trace=p['trace']; k,phi,flag,rank,proposal=scene
        assert p['kappa']==k and p['tape']=={'phase':phi,'error_flag':flag,'cause_rank':rank}
        assert trace['base_option']==proposal
        total+=reconstructed_rollout(p)
        assert p['step_objects_linked'] is True
        check_policy(trace,maps,rows,before['mode'],numeric)
    traces=[r['payload']['trace'] for r in raw]
    return traces,(total/100).hex(),raw_hash(traces)


def delta_zero(d):
    assert all(type(v) is int and v==0 for v in d.values())


def main():
    started=datetime.now(timezone.utc).isoformat()
    c=json.loads((HERE/'contract.json').read_bytes())
    claim=json.loads((HERE/'evidence/claim.json').read_bytes())
    receipt=json.loads((HERE/'evidence/exit.json').read_bytes())
    summary=json.loads((HERE/'evidence/child_summary.json').read_bytes())
    assert claim['parent_commit']==c['parent_commit']
    assert not claim['automatic_retry'] and not receipt['automatic_retry']
    assert receipt['input_bytes_unchanged'] and claim['input_binding_before']==receipt['input_binding_after']
    pins=claim['input_binding_before']
    for name,pin in pins.items(): assert meta(ROOT/name)==pin,name
    for name in ('stdout','stderr'):
        assert meta(HERE/'evidence'/(name+'.log'))==receipt[name]
    for name in ('raw.jsonl','child_summary.json'):
        assert meta(HERE/'evidence'/name)==receipt[name]
    helpers=copied_helpers_review(); kernel=kernel_return_review(claim)
    rows=read_reference(c['reference_input'])
    healthy=json.loads((ROOT/c['healthy_reference']['path']).read_bytes())
    assert meta(ROOT/c['healthy_reference']['path'])['sha256']==c['healthy_reference']['sha256']
    assert healthy['N_eval']==100 and healthy['training_episodes']==0
    records=[]; tags=Counter(); checksum=hashlib.sha256(); size=0
    with (HERE/'evidence/raw.jsonl').open('rb') as stream:
        for i,line in enumerate(stream):
            assert line.endswith(b'\n')
            record=json.loads(line)
            assert (canonical(record)+'\n').encode('ascii')==line and record['seq']==i
            assert set(record)=={'seq','tag','payload','stage','mode','role','phase','case'}
            records.append(record); tags[record['tag']]+=1; checksum.update(line); size+=len(line)
    assert len(records)==summary['records'] and size==summary['bytes']
    assert checksum.hexdigest()==summary['canonical_sha256'] and not summary['automatic_retry']
    known={'RUN_BEGIN','REFERENCE','SOURCE_INSTALL_PLANNED','TX_CALL','TX_RETURN','RAW_ROLLOUT',
           'ORIGINAL_SOURCE','BOUND_BEFORE_ARMS','NATIVE_B1_RETURN','ORIGINAL_PAIR','CURVE_PREPARED',
           'BANK_TOKEN_PREPARED','COMPARISON','TRAIN_BEGIN','CORE_EPISODE','OWNED_TRAIN_RETURN',
           'ORIGINAL_PAIR_AFTER_DIFFERENTIAL','GUARD_CONSTRUCTOR','PRECALL_CHALLENGE','PRECALL_RESTORED',
           'NOMINAL_CHALLENGES','INDUCED_POSTSCENE_WRITE','POSTSCENE_PARTIAL','POSTSCENE_RESTORED',
           'ORIGINAL_PAIR_FINAL','FINAL_COMPOSITE','ACTUAL_LOADED_SOURCE_INVENTORY','RESULT','TEST_RESULT',
           'FAILURE','INCOMPLETE_ROLLOUT','PENDING_STEP_RETURNS'}
    assert set(tags)<=known,set(tags)-known
    assert tags['RUN_BEGIN']==tags['REFERENCE']==1
    assert records[0]['payload']['contract_sha256']==meta(HERE/'contract.json')['sha256']
    ref=next(r['payload'] for r in records if r['tag']=='REFERENCE')
    assert ref=={'digest':c['reference_input']['q_digest'],'row_count':13824}
    counts=Counter(); tx=None
    for record in records:
        p=record['payload']; tag=record['tag']
        if tag=='RAW_ROLLOUT':
            reconstructed_rollout(p); assert p['step_objects_linked'] is True
            counts['rollout']+=1; counts['step']+=len(p['trace']['steps'])
        elif tag=='TX_CALL':
            assert tx is None
            before=storemap(p['before']); after=apply_edits(before,p['edits'],rows)
            tx=after; counts['transaction']+=1
        elif tag=='TX_RETURN':
            assert tx is not None and maps_equal(tx,storemap(p['after']))
            tx=None
        elif tag=='NATIVE_B1_RETURN': counts['B1']+=1
    assert tx is None
    modes={}
    for mode in MODES:
        group=[r for r in records if r['mode']==mode]
        source=[r for r in group if r['stage']=='source']
        sourceplans=[r['payload'] for r in source if r['tag']=='SOURCE_INSTALL_PLANNED']
        assert len(sourceplans)==1 and len(sourceplans[0]['edits'])==32
        for legal in sourceplans[0]['all_controller_legality']:
            site=addr(legal['site'],'X')
            serving=[[z,m,list(rows[site[:5]+(z,m)])] for z in range(4) for m in (0,1)
                     if site[-1] in rows[site[:5]+(z,m)]]
            assert serving==legal['all_serving_contexts'] and len(serving)==6
            assert all(legal['target'] in row for z,m,row in serving)
        p=next(r['payload'] for r in group if r['tag']=='CURVE_PREPARED')
        modes[mode]=verify_prepared(p,source,rows,c,mode,healthy)
    comparisons=[]; diagnostics=Counter()
    for case in range(8):
        group=[r for r in records if r['case']==case and r['stage'] in
               ('comparison','evaluate_old','evaluate_new','training')]
        cp=[r for r in group if r['tag']=='COMPARISON']
        assert len(cp)==1
        rec=cp[0]; p=rec['payload']; mode,role,phase=rec['mode'],rec['role'],rec['phase']
        current=modes[mode]['states'][role]
        assert p['before']==p['after']==current
        oldraw=[r for r in group if r['tag']=='RAW_ROLLOUT' and r['stage']=='evaluate_old']
        newraw=[r for r in group if r['tag']=='RAW_ROLLOUT' and r['stage']=='evaluate_new']
        sample=modes[mode]['plan']['sample']
        oldtraces,oldmean,oldsha=verify_bank_raw(oldraw,current,rows,sample)
        newtraces,newmean,newsha=verify_bank_raw(newraw,current,rows,sample)
        assert oldtraces==newtraces and p['full_raw_equal'] is True
        assert p['old_count']==p['new_count']==100
        assert p['old_mean_hex']==p['new_mean_hex']==oldmean==newmean
        assert p['old_ordered_raw_sha256']==p['new_ordered_raw_sha256']==oldsha==newsha
        assert p['order']==(['old','new'] if phase=='before_td' else ['new','old'])
        assert min(r['seq'] for r in (oldraw if p['order'][0]=='old' else newraw)) < min(r['seq'] for r in (newraw if p['order'][0]=='old' else oldraw))
        token=next(r['payload'] for r in group if r['tag']=='BANK_TOKEN_PREPARED')
        verify_bank_audit(token,current,sample,False,False,[])
        verify_bank_audit(p['new_bank_audit'],current,sample,True,True,newtraces)
        for name,raw in (('old',oldraw),('new',newraw)):
            timing=p['timings'][name]
            assert value(timing['wall_seconds'])>=0 and value(timing['cpu_seconds'])>=0
            delta=timing['count_delta']; assert delta['rollout']==delta['rollout_return']==100
            assert delta['step']==delta['step_return']==sum(len(r['payload']['trace']['steps']) for r in raw)
            assert not delta.get('transaction',0) and not delta.get('B1',0) and not delta.get('forbidden',0)
        comparisons.append({'mode':mode,'role':role,'phase':phase,'old_wall_seconds':value(p['timings']['old']['wall_seconds']),
                            'new_wall_seconds':value(p['timings']['new']['wall_seconds']),
                            'old_cpu_seconds':value(p['timings']['old']['cpu_seconds']),
                            'new_cpu_seconds':value(p['timings']['new']['cpu_seconds']),
                            'mean_hex':oldmean,'ordered_raw_sha256':oldsha,'all_raw_exact':True})
        core=[r for r in group if r['tag']=='CORE_EPISODE']
        if phase=='before_td':
            assert len(core)==1
            tb=next(r['payload'] for r in group if r['tag']=='TRAIN_BEGIN')
            assert tb=={'before':current,'episode':declared_episode(0)}
            raw=next(r['payload'] for r in group if r['tag']=='RAW_ROLLOUT' and r['stage']=='training')
            initial=modes[mode]['initial'][('reference','treatment').index(role)]
            after,diag=verify_receipt(core[0]['payload'],rows,current,initial,mode,role,0,raw)
            ret=next(r['payload'] for r in group if r['tag']=='OWNED_TRAIN_RETURN')
            assert ret==core[0]['payload']
            modes[mode]['states'][role]=after; diagnostics.update(diag)
        else:
            assert not core and current['completed_episodes']==1
    guard_constructors=[r for r in records if r['tag']=='GUARD_CONSTRUCTOR']
    assert len(guard_constructors)==9
    expected_reference=modes['patch-adaptive']['initial'][0]
    for record in guard_constructors:
        p=record['payload']
        assert p['constructor_kind']=='guard-only nominal constructor; no owned role curve minted'
        assert p['original_pair_seal']==expected_reference['source_label']
        assert p['original_future']==modes['patch-adaptive']['origin']['original_future']
        assert p['actual_immediate_clone']==p['full_reference_I']==expected_reference['immediate']
        assert p['actor']==expected_reference and p['runtime_nonalias'] is True
    names=('immediate','current','learning_values','process','controller','role','shared_plan','primitive_key')
    for name in names:
        pre=next(r['payload'] for r in records if r['tag']=='PRECALL_CHALLENGE' and r['payload']['name']==name)
        restored=next(r['payload'] for r in records if r['tag']=='PRECALL_RESTORED' and r['payload']['name']==name)
        assert pre['error']==restored['error'] and pre['error']['type']=='ProtocolError'
        assert restored['restored_full_composite'] is True
        delta_zero(pre['native_delta']); delta_zero(restored['native_delta'])
        for audit in (pre['audit'],restored['audit']):
            verify_bank_audit(audit,expected_reference,sample_of_100(),True,False,[])
            assert audit['failure'] is not None
    nominal=next(r['payload'] for r in records if r['tag']=='NOMINAL_CHALLENGES')
    assert nominal['count']==7; delta_zero(nominal['native_delta'])
    post=next(r['payload'] for r in records if r['tag']=='POSTSCENE_PARTIAL')
    restored=next(r['payload'] for r in records if r['tag']=='POSTSCENE_RESTORED')
    assert post['error']==restored['error'] and post['error']['type']=='ProtocolError'
    assert post['actual_complete_raw_return_count']==1 and restored['restored_full_composite'] is True
    for p in (post,restored):
        verify_bank_audit(p['audit'],expected_reference,sample_of_100(),True,False,[])
        assert p['audit']['failure'] is not None
        assert p['native_delta']['rollout']==p['native_delta']['rollout_return']==1
        assert not p['native_delta'].get('transaction',0)
    partialraw=[r for r in records if r['tag']=='RAW_ROLLOUT' and r['stage']=='partial_guard']
    assert len(partialraw)==1
    scene=sample_of_100()[0]; p=partialraw[0]['payload']
    assert p['kappa']==scene[0] and p['tape']=={'phase':scene[1],'error_flag':scene[2],'cause_rank':scene[3]}
    assert p['trace']['base_option']==scene[4]
    check_policy(p['trace'],storemap(expected_reference['current']),rows,'patch-adaptive',storemap(expected_reference['learning_values']))
    assert post['native_delta']['step']==post['native_delta']['step_return']==len(p['trace']['steps'])
    induced=next(r['payload'] for r in records if r['tag']=='INDUCED_POSTSCENE_WRITE')
    desired=storemap(expected_reference['current']); desired['P'][0]=2
    assert maps_equal(desired,storemap(induced['current'])) and induced['actual_returned_trace_complete']
    for mode in MODES:
        group=[r for r in records if r['mode']==mode]
        pair=next(r['payload'] for r in group if r['tag']=='ORIGINAL_PAIR')
        assert all(r['payload']==pair for r in group if r['tag']=='ORIGINAL_PAIR_AFTER_DIFFERENTIAL')
        assert sum(r['payload']==pair for r in records if r['tag']=='ORIGINAL_PAIR_FINAL')==1
        finals=[r['payload'] for r in records if r['tag']=='FINAL_COMPOSITE' and r['payload']['mode']==mode]
        assert len(finals)==2 and finals==[modes[mode]['states'][role] for role in ('reference','treatment')]
    inventory=next(r['payload'] for r in records if r['tag']=='ACTUAL_LOADED_SOURCE_INVENTORY')
    assert all(name in pins and pins[name]['sha256']==sha for name,sha in inventory.items())
    result=next(r['payload'] for r in records if r['tag']=='RESULT')
    test=next(r['payload'] for r in records if r['tag']=='TEST_RESULT')
    assert receipt['child_exit_code']==0 and test['tests_run']==4
    assert test['failures']==test['errors']==test['skipped']==0
    assert summary['counts']==test['counts']==result['counts']
    observed=summary['counts']
    assert counts['rollout']==observed['rollout']==observed['rollout_return']==1607
    assert counts['step']==observed['step']==observed['step_return']
    assert counts['transaction']==observed['transaction']<=c['budget']['transaction']
    assert counts['B1']==observed['B1']==4
    assert observed.get('forbidden',0)==0 and tags['CORE_EPISODE']==tags['OWNED_TRAIN_RETURN']==4
    assert tags['COMPARISON']==8 and tags['PRECALL_CHALLENGE']==tags['PRECALL_RESTORED']==8
    assert tags['POSTSCENE_PARTIAL']==tags['POSTSCENE_RESTORED']==1
    assert not tags['FAILURE'] and not tags['PENDING_STEP_RETURNS'] and not tags['INCOMPLETE_ROLLOUT']
    assert result['completed'] and result['differential_states']==8 and result['precall_challenges']==8
    assert result['guard_only_constructor_clones']==9 and result['actual_partial_scene_returns']==1
    assert result['four_actual_owned_roles'] and result['positive_benefit_required'] is False
    assert result['scientific_qualification'] is False and result['formal_training_or_collection'] is False
    assert size<=c['budget']['capture_bytes']
    report={'schema':'V107_INDEPENDENT_STDLIB_STORED_READPATH_REVIEW','started_at_utc':started,
            'completed_at_utc':datetime.now(timezone.utc).isoformat(),'native_child_exit_preserved':receipt['child_exit_code'],
            'native_methods':4,'native_failure_error_skip':0,'input_pins':len(pins),'actual_loaded_source_pins':len(inventory),
            'complete_canonical_records':len(records),'raw_bytes':size,'raw_sha256':checksum.hexdigest(),
            'tag_inventory':dict(tags),'actual_counts':dict(counts),'eight_comparisons':comparisons,
            'TD_diagnostics':dict(diagnostics),'owners_per_source':7,'residual_per_source':3,
            'original_owner_receipts':28,'original_extra_sources':2,'guard_only_constructor_clones':9,
            'eight_precall_rejections_zero_native':True,'postscene_partial_raw_returns':1,
            'postscene_accepted_bank_scenes':0,'partial_has_no_mean':True,
            'helper_source_review':helpers,'kernel_return_review':kernel,
            'temporary_mutation_contents_not_all_serialized':True,
            'runtime_identity_reconstructed':False,'old_checker_RFL_execution':False,
            'scientific_qualification':False,'formal_keyed_domain_proof':False,
            'positive_benefit_required_for_study_completion':False,'audit_source':meta(Path(__file__))}
    with (HERE/'stored_audit_result.json').open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(canonical(report)+'\n')
    print(canonical(report),flush=True)


if __name__=='__main__':
    main()

