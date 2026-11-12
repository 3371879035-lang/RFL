"""New stdlib streaming audit of the v108 patch-only read-path workload.

Stored records are never reconstructed as runtime sources, pairs, roles, or
handles. Physics, policy, TD, canonicalization, complete banks, raw external
projection, source receipts and input bindings are independently checked.
"""
import ast
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PREVIOUS = HERE.parent / 'dense_resource_workload_v106'
MODES = ('patch-adaptive',)
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
COPIED_HELPERS = ["canonical","digest","meta","value","state","wire_state","addr","storemap","flat","fingerprint","maps_equal","allowed","hazard","check_step","read_reference","edit_key","apply_edits","greedy","check_policy","td","decode_native_float","verify_seal","check_source_pair","kernel_return_source_review","declared_episode","reconstructed_rollout","projected_bank","expected_training_before","verify_receipt","verify_prepared","check_external"]
EXTERNAL_FIELDS = ('future_rewards','future_outcomes','future_trajectories',
                   'future_actions','future_observations')


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



def copied_helpers_review():
    previous=PREVIOUS/'audit_dense_kernel_return_revised.py'
    old_text=previous.read_text(encoding='utf-8')
    new_text=Path(__file__).read_text(encoding='utf-8')
    old,new=ast.parse(old_text),ast.parse(new_text)
    pins=[]
    for name in COPIED_HELPERS:
        a=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name==name)
        b=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name==name)
        old_source,new_source=ast.get_source_segment(old_text,a),ast.get_source_segment(new_text,b)
        assert old_source==new_source and ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False),name
        pins.append({'function':name,'source_sha256':hashlib.sha256(old_source.encode('utf-8')).hexdigest(),
                     'AST_and_source_unchanged':True})
    return {'mechanically_copied_stdlib_helpers':len(COPIED_HELPERS),
            'previous_checker_imported_or_executed':False,'previous_source':meta(previous),
            'actual_function_source_pins':pins}


def read_path_source_review(c):
    previous=HERE.parent/'complete_curve_source_gates_v105/variants/normal'
    functions=[]
    for filename in ('owned_curve.py','external.py'):
        old_text=(previous/filename).read_text(encoding='utf-8')
        new_text=(HERE/filename).read_text(encoding='utf-8')
        old,new=ast.parse(old_text),ast.parse(new_text)
        normalized=deepcopy(new)
        if filename=='owned_curve.py':
            normalized.body[0]=deepcopy(old.body[0])
            normalized.body=[node for node in normalized.body if not
                (isinstance(node,ast.Import) and any(alias.name=='v107_bank' for alias in node.names))]
            original=next(node for node in old.body if isinstance(node,ast.FunctionDef) and node.name=='_evaluate_bank')
            revised=next(node for node in new.body if isinstance(node,ast.FunctionDef) and node.name=='_evaluate_bank')
            expected=ast.parse('def _evaluate_bank(actor, sample):\n    token = B.prepare_bank(actor, sample)\n    return B.run_bank(token)\n').body[0]
            assert ast.dump(revised,include_attributes=False)==ast.dump(expected,include_attributes=False)
            normalized.body=[deepcopy(original) if isinstance(node,ast.FunctionDef) and node.name=='_evaluate_bank'
                             else node for node in normalized.body]
        else:
            for node in normalized.body:
                if isinstance(node,ast.Import):
                    for alias in node.names:
                        if alias.name=='v108_curve': alias.name='v105_normal_curve'
        assert ast.dump(normalized,include_attributes=False)==ast.dump(old,include_attributes=False),filename
        for node in new.body:
            if isinstance(node,ast.FunctionDef):
                old_node=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name==node.name)
                functions.append({'file':filename,'function':node.name,
                    'old_source_sha256':hashlib.sha256(ast.get_source_segment(old_text,old_node).encode('utf-8')).hexdigest(),
                    'new_source_sha256':hashlib.sha256(ast.get_source_segment(new_text,node).encode('utf-8')).hexdigest(),
                    'unchanged':ast.dump(node,include_attributes=False)==ast.dump(old_node,include_attributes=False)})
    bank=ROOT/c['preserved_bank']['path']
    assert meta(bank)['sha256']==c['preserved_bank']['sha256']
    bt=ast.parse(bank.read_text(encoding='utf-8'))
    imports=[n for n in bt.body if isinstance(n,ast.Import)]
    assert any(any(a.name=='v105_normal_learning' and a.asname=='L' for a in n.names) for n in imports)
    functions_by_name={n.name:n for n in bt.body if isinstance(n,ast.FunctionDef)}
    assert set(('prepare_bank','run_bank','audit_bank','_scene_guard','_check_store'))<=set(functions_by_name)
    assert not any(isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                   and node.func.attr in ('train_episode','apply_transaction','setprofile')
                   for node in ast.walk(bt))
    gate=[]
    for role,spec in c['predecessor_gate'].items():
        if role in ('native','stored'):
            actual=meta(ROOT/spec['path']); assert actual['sha256']==spec['sha256']
            gate.append({'role':role,'path':spec['path'],'actual_meta':actual})
    return {'full_curve_AST_only_declared_bank_delta':True,
            'external_AST_only_import_alias_delta':True,
            'source_functions':functions,'readonly_bank':meta(bank),
            'original_learner_and_TD_unchanged':True,
            'recorded_predecessor_gate_pins':gate,
            'runtime_token_identity_reconstructed':False,'scientific_qualification':False}



def kernel_return_source_review():
    path=ROOT/'src/rfl_rebuild/env/kernel.py'
    text=path.read_text(encoding='utf-8')
    tree=ast.parse(text)
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='RolloutTrace')
    getter=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='return_value')
    expected=ast.parse('def return_value(self):\n    return float(sum(s.reward for s in self.steps))\n').body[0].body[0]
    assert ast.dump(getter.body[-1],include_attributes=False)==ast.dump(expected,include_attributes=False)
    assert sys.implementation.name=='cpython' and tuple(sys.version_info[:3])==(3,12,14)
    for mode in MODES:
        claim=json.loads((HERE/'evidence'/mode/'claim.json').read_bytes())
        assert str(Path(claim['command'][0]).resolve()).casefold()==str(Path(sys.executable).resolve()).casefold()
    return {'qualified_method':'RolloutTrace.return_value','physical_source':meta(path),
            'getter_ast_sha256':hashlib.sha256(ast.dump(getter,include_attributes=False).encode('utf-8')).hexdigest(),
            'getter_source_sha256':hashlib.sha256(ast.get_source_segment(text,getter).encode('utf-8')).hexdigest(),
            'getter_start_line':getter.lineno,'getter_return_line':getter.body[-1].lineno,
            'return_operation':'float(sum(step.reward for step in steps))',
            'interpreter':sys.executable,'implementation':sys.implementation.name,
            'runtime_version':sys.version,'native_executable_match':True,
            'ordered_bank_addition_unchanged':True,'chronological_TD_unchanged':True,
            'original_B1_reversed_return_fold_unchanged':True}


def declared_episode(e):
    return {'epoch':e,'kappa':e%2,'proposal':(e//2)%4,
            'tape':{'phase':(e//8)%6,'error_flag':(e//48)%2,'cause_rank':(e//96)%60},
            'coins':[0 if (e+i)%10==0 else M64 for i in range(12)],
            'rejections':[[M64,e*12+i] for i in range(12)]}


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


def projected_bank(traces):
    expected={name:[] for name in EXTERNAL_FIELDS}
    for trace in traces:
        steps=trace['steps']
        expected['future_rewards'].append([s['reward'] for s in steps])
        expected['future_outcomes'].append([s['outcome'] for s in steps])
        expected['future_trajectories'].append([s['state'] for s in steps])
        expected['future_actions'].append([s['a_cmd'] for s in steps])
        expected['future_observations'].append([None for s in steps])
    return {name:digest(expected[name]) for name in EXTERNAL_FIELDS}


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


def verify_prepared(p,source_records,rows,c,mode,healthy):
    b1,pair=check_source_pair(source_records,rows,c,mode)
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
    plan=origin['engineering_plan']; assert plan['grid']==list(range(466))
    assert plan['episodes']==[declared_episode(e) for e in range(465)]
    assert plan['engineering_bank_indices']==list(range(100)) and len(plan['sample'])==100
    cells=[(k,phi,flag,proposal) for k in (0,1) for phi in range(6)
           for flag in (0,1) for proposal in range(4)]
    sample=[]
    for n in range(100):
        q,r=divmod(n,96); k,phi,flag,proposal=cells[r]
        sample.append([k,phi,flag,(7*q+37*r)%60,proposal])
    assert plan['sample']==sample
    assert hashlib.sha256(repr(tuple(tuple(s) for s in sample)).encode('utf-8')).hexdigest()==healthy['evaluation_sample_sha256']
    assert plan['v_pre_hex']==float(healthy['v_pre']).hex()
    assert plan['original_lock_sha256']==healthy['lock_sha256']
    assert not plan['keyed'] and not plan['formal_execution']
    assert plan['parameters']=={'alpha':{'rational':[1,2]},'epsilon':{'rational':[1,10]}}
    future=origin['original_future']
    verify_seal(future)
    template=future['payload']['shared_template']
    assert template['evaluation_units']==plan['sample']
    assert template['evaluation_sha256']==healthy['evaluation_sample_sha256']
    assert template['v_pre_hex']==plan['v_pre_hex'] and template['lock_sha256']==healthy['lock_sha256']
    assert template['grid']==list(range(466)) and template['T']==465 and template['seed'] is None
    assert template['alpha']==[1,2] and template['epsilon']==[1,10]
    initial=origin['initial_composites']; assert initial==p['initial_composites']
    for i,comp in enumerate(initial):
        assert comp['role']==('reference','treatment')[i] and comp['mode']==mode and comp['source_label']==seal
        assert comp['immediate']==comp['current']==b1[i]['full_post']
        assert comp['completed_episodes']==0 and comp['attempted_epochs']==[]
        assert comp['learning_values']==({'D':[],'P':[],'X':[],'Q':[]} if mode=='patch-adaptive' else None)
    return initial,plan


def check_external(view,banks,role,pre):
    assert set(view)=={'fields','episodes','values','pre_level','t_max'}
    assert set(view['fields'])==set(EXTERNAL_FIELDS)
    assert view['episodes']==list(range(466)) and view['t_max']==465
    assert value(view['pre_level']).hex()==pre
    assert view['values']==[{'binary64_hex':banks[(role,e)]['mean_hex']} for e in range(466)]
    for field in EXTERNAL_FIELDS:
        content=view['fields'][field]; assert len(content)==466
        for e,values in enumerate(content):
            assert len(values)==100 and digest(values)==banks[(role,e)]['projection'][field],(role,e,field)


def audit_child(mode,c,rows,pins,healthy):
    folder=HERE/'evidence'/mode
    summary=json.loads((folder/'child_summary.json').read_bytes())
    rawmeta=meta(folder/'raw.jsonl.gz')
    assert rawmeta['bytes']==summary['compressed_bytes'] and summary['mode']==mode
    seq=0; checksum=hashlib.sha256(); size=0; tags=Counter(); counts=Counter()
    source_records=[]; initial=plan=None; states={}; banks={}; current_bank=None
    training=None; pending_train_raw=None; handles=set(); final_composites={}; external=set()
    result=failure=inventory=None; peaks={k:0 for k in ('working_set_bytes','peak_working_set_bytes',
                                                     'private_bytes','peak_commit_bytes')}
    minimum_available=1<<64; diagnostics=Counter(); actual_resources=[]
    source_plan=None
    kernel_return_witness=None
    last_wall=last_cpu=last_compressed=0.0
    budget_boundaries=[]
    last_resource_seq=None
    last_resource_counts=None
    with gzip.open(folder/'raw.jsonl.gz','rb') as stream:
        for line in stream:
            record=json.loads(line)
            assert (canonical(record)+'\n').encode('ascii')==line,seq
            assert record['seq']==seq and record['mode']==mode
            checksum.update(line); size+=len(line); seq+=1
            tag,p=record['tag'],record['payload']; tags[tag]+=1
            role,e,stage=record['role'],record['epoch'],record['stage']
            if stage=='source' and tag in ('ORIGINAL_SOURCE','ORIGINAL_PAIR','BOUND_BEFORE_ARMS','NATIVE_B1_RETURN'):
                source_records.append(record)
            if tag=='RAW_ROLLOUT':
                counts['rollout']+=1; counts['step']+=len(p['trace']['steps'])
                ret=reconstructed_rollout(p)
                if stage=='source':
                    source_records.append(dict(record,payload=p['trace']))
                    assert p['kappa']==c['source_scene'][0] and p['tape']=={'phase':c['source_scene'][1],
                      'error_flag':c['source_scene'][2],'cause_rank':c['source_scene'][3]}
                elif stage=='evaluation':
                    assert current_bank is not None and (role,e)==current_bank['key']
                    i=len(current_bank['traces']); assert i<100
                    scene=current_bank['sample'][i]
                    assert p['kappa']==scene[0] and p['tape']=={'phase':scene[1],
                             'error_flag':scene[2],'cause_rank':scene[3]}
                    assert p['trace']['base_option']==scene[4]
                    comp=current_bank['before']
                    check_policy(p['trace'],storemap(comp['current']),rows,mode,
                                 None if mode=='dq' else storemap(comp['learning_values']))
                    current_bank['traces'].append(p['trace']); current_bank['total']+=ret
                    current_bank['hash'].update((canonical(p['trace'])+'\n').encode('ascii'))
                elif stage=='training':
                    assert training is not None and training['key']==(role,e) and pending_train_raw is None
                    inp=declared_episode(e)
                    assert p['kappa']==inp['kappa'] and p['tape']==inp['tape']
                    assert p['trace']['base_option']==inp['proposal']
                    pending_train_raw=p
                else: raise AssertionError(('unexpected raw stage',stage))
            elif tag=='TX_CALL':
                assert 'tx' not in locals(); tx=p; counts['transaction']+=1
                if counts['transaction']==1:
                    assert source_plan is not None and p['edits']==source_plan['edits']
                    assert storemap(p['before'])=={ch:{} for ch in ('D','P','X','Q')}
            elif tag=='TX_RETURN':
                assert 'tx' in locals()
                assert maps_equal(apply_edits(storemap(tx['before']),tx['edits'],rows),storemap(p['after']))
                del tx
            elif tag=='NATIVE_B1_RETURN': counts['B1']+=1
            elif tag=='REFERENCE':
                assert p=={'digest':c['reference_input']['q_digest'],'rows':13824}
            elif tag=='CURVE_PREPARED':
                assert initial is None
                initial,plan=verify_prepared(p,source_records,rows,c,mode,healthy)
                states={r:deepcopy(x) for r,x in zip(('reference','treatment'),initial)}
            elif tag=='BANK_BEGIN':
                assert initial is not None and current_bank is None and training is None
                key=(role,e); assert key not in banks and p['before']==states[role]
                assert e==states[role]['completed_episodes'] and p['sample']==plan['sample']
                expected=('reference',len(banks)) if len(banks)<466 else ('treatment',len(banks)-466)
                assert key==expected
                current_bank={'key':key,'before':p['before'],'sample':p['sample'],
                              'traces':[],'total':0.0,'hash':hashlib.sha256()}
            elif tag=='BANK_END':
                assert current_bank is not None and current_bank['key']==(role,e)
                assert len(current_bank['traces'])==p['count']==100
                assert p['after']==current_bank['before']==states[role]
                assert (current_bank['total']/100).hex()==p['mean_hex']
                assert current_bank['hash'].hexdigest()==p['ordered_raw_sha256']
                banks[(role,e)]={'mean_hex':p['mean_hex'],'raw_sha256':p['ordered_raw_sha256'],
                                 'projection':projected_bank(current_bank['traces'])}
                current_bank=None
            elif tag=='TRAIN_BEGIN':
                assert training is None and current_bank is None and (role,e) in banks
                assert p['before']==states[role]
                assert p['declared_episode']==declared_episode(e)
                training={'key':(role,e),'before':p['before']}
            elif tag=='CORE_EPISODE':
                assert training is not None and training['key']==(role,e) and pending_train_raw is not None
                assert p['before']==expected_training_before(training['before'],e)
                if kernel_return_witness is None:
                    rewards=[value(step['reward']) for step in p['trace']['steps']]
                    naive=0.0
                    for reward in rewards: naive+=reward
                    builtin=float(sum(rewards))
                    assert p['return_hex']==builtin.hex()
                    if builtin.hex()!=naive.hex():
                        kernel_return_witness={'record_seq':record['seq'],'mode':mode,'role':role,'epoch':e,
                                               'rewards_hex':[x.hex() for x in rewards],
                                               'native_return_hex':p['return_hex'],'original_builtin_sum_hex':builtin.hex(),
                                               'incorrect_incremental_fold_hex':naive.hex(),'actual_difference_preserved':True}
                i=('reference','treatment').index(role)
                states[role],diagnostic=verify_receipt(p,rows,states[role],initial[i],mode,role,e,pending_train_raw)
                diagnostics.update(diagnostic); training=pending_train_raw=None
            elif tag=='HANDLE_CHECKPOINT':
                assert stage=='export' and e==465
                key=(role,p['epoch']); assert key not in handles and key in banks
                assert p['count']==100 and p['mean_hex']==banks[key]['mean_hex']
                assert p['ordered_raw_sha256']==banks[key]['raw_sha256']; handles.add(key)
            elif tag=='FINAL_COMPOSITE':
                assert role not in final_composites and p==states[role] and e==465
                assert all((role,i) in handles for i in range(466)); final_composites[role]=p
            elif tag=='EXTERNAL_VIEW':
                assert role not in external and role in final_composites
                check_external(p,banks,role,plan['v_pre_hex']); external.add(role)
            elif tag in ('ORIGINAL_SOURCE','BOUND_BEFORE_ARMS','ORIGINAL_PAIR'):
                assert stage=='source' and role is None and e is None
                # These collected records are fully validated by verify_prepared.
            elif tag=='ORIGINAL_PAIR_AFTER':
                assert p==next(r['payload'] for r in source_records if r['tag']=='ORIGINAL_PAIR')
            elif tag=='ACTUAL_LOADED_SOURCE_INVENTORY':
                assert inventory is None
                assert all(name in pins and pins[name]['sha256']==sha for name,sha in p.items())
                required={c['preserved_bank']['path'],
                          (HERE/'owned_curve.py').relative_to(ROOT).as_posix(),
                          (HERE/'external.py').relative_to(ROOT).as_posix(),
                          'experiments/v03r/a96_dense/b2_prepare/complete_curve_source_gates_v105/variants/normal/td.py',
                          'experiments/v03r/a96_dense/b2_prepare/complete_curve_source_gates_v105/variants/normal/learning.py'}
                assert required<=set(p), 'actual optimized/unchanged loaded source inventory incomplete'
                inventory=p
            elif tag=='RESOURCE':
                last_resource_seq=record['seq']
                assert p['raw_bytes']==size-len(line)
                wall,cpu=value(p['wall_seconds']),value(p['cpu_seconds'])
                assert math.isfinite(wall) and math.isfinite(cpu)
                assert wall>=last_wall and cpu>=last_cpu
                assert p['compressed_bytes']>=last_compressed
                last_wall,last_cpu,last_compressed=wall,cpu,p['compressed_bytes']
                for k in peaks: peaks[k]=max(peaks[k],p[k])
                minimum_available=min(minimum_available,p['available_physical_bytes'])
                limits=[('working-set cap',p['working_set_bytes'],c['budget']['working_set_bytes_per_child'],False),
                        ('peak working-set cap',p['peak_working_set_bytes'],c['budget']['working_set_bytes_per_child'],False),
                        ('private-commit cap',p['private_bytes'],c['budget']['private_bytes_per_child'],False),
                        ('peak private-commit cap',p['peak_commit_bytes'],c['budget']['private_bytes_per_child'],False),
                        ('host RAM reserve',p['available_physical_bytes'],c['budget']['minimum_available_physical_bytes'],True),
                        ('wall-time cap',wall,c['budget']['seconds_per_child'],False)]
                breaches=[]
                for name,observed,bound,minimum in limits:
                    if (observed<bound if minimum else observed>bound):
                        breaches.append({'assertion':name,'observed':observed,'declared_bound':bound,
                                         'required_relation':'>=' if minimum else '<='})
                if breaches:
                    budget_boundaries.append({'record_seq':record['seq'],'label':p['label'],
                                              'breaches_in_native_assertion_order':breaches})
                assert p['counts'].get('rollout',0)==counts['rollout']
                assert p['counts'].get('step',0)==counts['step']
                assert p['counts'].get('B1',0)==counts['B1']
                assert p['counts'].get('transaction',0)==counts['transaction']
                assert not p['counts'].get('forbidden',0)
                last_resource_counts=deepcopy(p['counts'])
                if summary['completed']:
                    assert not breaches
                    assert p['working_set_bytes']<=c['budget']['working_set_bytes_per_child']
                    assert p['peak_working_set_bytes']<=c['budget']['working_set_bytes_per_child']
                    assert p['private_bytes']<=c['budget']['private_bytes_per_child']
                    assert p['peak_commit_bytes']<=c['budget']['private_bytes_per_child']
                    assert p['available_physical_bytes']>=c['budget']['minimum_available_physical_bytes']
                    assert wall<=c['budget']['seconds_per_child']
                actual_resources.append({'label':p['label'],'wall_seconds':wall,'cpu_seconds':cpu,
                                         'working_set_bytes':p['working_set_bytes'],
                                         'private_bytes':p['private_bytes'],'compressed_bytes':p['compressed_bytes']})
            elif tag=='RESULT':
                assert result is None; result=p
                assert p['raw_records_before_result']==seq-1
            elif tag=='FAILURE':
                assert failure is None; failure=p
            elif tag in ('PENDING_RETURNED_STEPS','INCOMPLETE_ROLLOUT'):
                assert not summary['completed']
            elif tag=='RUN_BEGIN':
                assert p['contract_sha256']==meta(HERE/'contract.json')['sha256']
            elif tag=='SOURCE_INSTALL_PLANNED':
                assert source_plan is None and p['mode']==mode and len(p['edits'])==32
                assert len(p['legality'])==3
                for legal in p['legality']:
                    site=addr(legal['site'],'X'); target=legal['target']
                    serving=[[z,m,list(rows[site[:5]+(z,m)])] for z in range(4) for m in (0,1)
                             if site[-1] in rows[site[:5]+(z,m)]]
                    assert legal['all_serving_contexts']==serving and len(serving)==6
                    assert all(target in actions for z,m,actions in serving)
                source_plan=p
            else: raise AssertionError(('unknown tag',tag))
            if seq%20000==0:
                print(canonical({'tag':'AUDIT_PROGRESS','mode':mode,'records':seq,
                                 'banks':len(banks),'TD_receipts':tags['CORE_EPISODE']}),flush=True)
    assert summary['records']==seq and summary['uncompressed_bytes']==size
    assert summary['canonical_sha256']==checksum.hexdigest()
    assert peaks=={k:summary['peaks'][k] for k in peaks}
    assert minimum_available==summary['peaks']['minimum_available_physical_bytes']
    complete=summary['completed']
    partial_count_evidence=None
    if complete:
        assert result is not None and result['completed'] and failure is None and inventory is not None
        assert not current_bank and not training and pending_train_raw is None and 'tx' not in locals()
        assert counts['rollout']==94131 and counts['B1']==2
        assert tags['CORE_EPISODE']==930 and len(banks)==len(handles)==932
        assert external==set(('reference','treatment')) and len(final_composites)==2
        assert counts['step']==summary['counts']['step']==summary['counts']['step_return']
        assert summary['counts']['rollout']==summary['counts']['rollout_return']==94131
        assert summary['counts']['transaction']==counts['transaction'] and not summary['counts'].get('forbidden',0)
        assert result['counts']==summary['counts'] and result['checkpoint_banks']==932
        assert result['training_episodes']==930 and not result['formal_keyed_stream']
        assert not result['scientific_qualification'] and not result['collection_authorized']
        assert result['source_mode_bound_before_arms']
        for entry in result['roles']:
            role=entry['role']; final=final_composites[role]
            assert entry['ordered_curve']==[{'epoch':e,'mean_hex':banks[(role,e)]['mean_hex']} for e in range(466)]
            assert entry['pre_level_hex']==plan['v_pre_hex'] and entry['t_max']==465
            assert entry['full_composite_sha256']==digest(final)
            assert entry['numeric_entry_count']==len(final['current']['Q'] if mode=='dq' else final['learning_values']['Q'])
            assert entry['decision_entry_count']==len(final['current']['D'])
        assert result['peaks']==summary['peaks']
        assert summary['wall_seconds']>=last_wall and summary['cpu_seconds']>=last_cpu
        assert summary['encode_seconds']>=value(result['capture_encode_seconds'])>=0
        assert summary['write_seconds']>=value(result['capture_write_seconds'])>=0
        assert size<=c['budget']['uncompressed_bytes_per_child'] and rawmeta['bytes']<=c['budget']['compressed_bytes_per_child']
    else:
        assert failure is not None and result is None
        assert failure['counts']==summary['counts']
        native_counts=summary['counts']
        deltas={'rollout_calls_minus_complete_raw':native_counts.get('rollout',0)-counts['rollout'],
                'rollout_returns_minus_complete_raw':native_counts.get('rollout_return',0)-counts['rollout'],
                'step_calls_minus_complete_raw_steps':native_counts.get('step',0)-counts['step'],
                'step_returns_minus_complete_raw_steps':native_counts.get('step_return',0)-counts['step'],
                'B1_calls_minus_return_records':native_counts.get('B1',0)-counts['B1'],
                'transaction_calls_minus_call_records':native_counts.get('transaction',0)-counts['transaction']}
        partial_count_evidence={'native_call_return_counts':native_counts,
                               'completed_raw_and_transaction_records':dict(counts),
                               'signed_counter_deltas':deltas,
                               'pending_return_records':tags['PENDING_RETURNED_STEPS'],
                               'incomplete_rollout_records':tags['INCOMPLETE_ROLLOUT'],
                               'transaction_return_pending':'tx' in locals(),
                               'safe_resource_boundary_exact_counts_verified':False,
                               'general_exception_call_record_distinction_preserved':True}
        if budget_boundaries:
            assert len(budget_boundaries)==1
            boundary=budget_boundaries[0]
            assert boundary['record_seq']==last_resource_seq
            assert boundary['label']==actual_resources[-1]['label']
            assert failure['type']=='AssertionError'
            assert failure['message']==boundary['breaches_in_native_assertion_order'][0]['assertion']
            assert not tags['PENDING_RETURNED_STEPS'] and not tags['INCOMPLETE_ROLLOUT']
            assert 'tx' not in locals() and last_resource_counts==native_counts
            assert not native_counts.get('forbidden',0) and all(delta==0 for delta in deltas.values())
            partial_count_evidence['safe_resource_boundary_exact_counts_verified']=True
    return {'mode':mode,'complete':complete,'native_failure_preserved':failure,
            'records':seq,'uncompressed_bytes':size,'compressed_meta':rawmeta,
            'canonical_sha256':checksum.hexdigest(),'tag_inventory':dict(tags),
            'actual_counts':dict(counts),'complete_banks':len(banks),
            'source_owner_count':7 if initial is not None else None,
            'source_residual_count':3 if initial is not None else None,
            'original_owner_receipts_verified':14 if initial is not None else 0,
            'retained_actual_handle_checkpoint_links':len(handles),
            'external_closed_projections_checked':len(external),'loaded_source_pins':len(inventory or {}),
            'TD_and_policy_diagnostics':dict(diagnostics),'resource_samples':actual_resources,
            'terminal_budget_failure_boundary':budget_boundaries,
            'partial_count_evidence':partial_count_evidence,
            'original_kernel_return_witness':kernel_return_witness,
            'peaks':summary['peaks'],'instrumented_wall_seconds':summary['wall_seconds'],
            'cpu_seconds':summary['cpu_seconds'],'capture_encode_seconds':summary['encode_seconds'],
            'capture_write_seconds':summary['write_seconds'],
            'ordered_curves':None if not complete else result['roles'],
            'runtime_identity_reconstructed':False,'old_checker_RFL_execution':False,
            'scientific_qualification':False,'formal_keyed_domain_proof':False}


def main():
    started=datetime.now(timezone.utc).isoformat()
    c=json.loads((HERE/'contract.json').read_bytes())
    claim=json.loads((HERE/'evidence/claim.json').read_bytes())
    exit_record=json.loads((HERE/'evidence/exit.json').read_bytes())
    pins=claim['input_binding_before']
    assert pins==exit_record['input_binding_after'] and exit_record['input_bytes_unchanged']
    assert not claim['automatic_retry'] and not exit_record['automatic_retry']
    assert claim['serial_children'] and claim['planned_modes']==list(MODES)
    assert claim['parent_commit']==c['parent_commit']
    for receipt in exit_record['child_receipts']:
        folder=HERE/'evidence'/receipt['mode']
        assert receipt==json.loads((folder/'exit.json').read_bytes())
        assert not receipt['automatic_retry']
        for field in ('stdout','stderr'):
            assert meta(folder/(field+'.log'))==receipt[field]
        for field in ('raw.jsonl.gz','child_summary.json'):
            if field in receipt: assert meta(folder/field)==receipt[field]
    assert [r['mode'] for r in exit_record['child_receipts']]==list(MODES)[:len(exit_record['child_receipts'])]
    for name,pin in pins.items(): assert meta(ROOT/name)==pin,name
    helpers=copied_helpers_review()
    kernel_return_review=kernel_return_source_review()
    read_path_review=read_path_source_review(c)
    rows=read_reference(c['reference_input'])
    hs=c['healthy_reference']; hpath=ROOT/hs['path']
    assert meta(hpath)['sha256']==hs['sha256']
    healthy=json.loads(hpath.read_bytes())
    assert healthy['N_eval']==100 and healthy['training_episodes']==0
    assert healthy['q_reference_sha256']==c['reference_input']['q_digest']
    lock=json.loads((ROOT/c['dev_lock']['path']).read_bytes())
    assert meta(ROOT/c['dev_lock']['path'])['sha256']==c['dev_lock']['sha256']==healthy['lock_sha256']
    assert lock['design']['T']==c['t_max']==465 and lock['design']['N_eval']==c['n_eval']==100
    assert lock['design']['grid']==list(range(466))
    summaries=[audit_child(mode,c,rows,pins,healthy) for mode in MODES
               if (HERE/'evidence'/mode/'child_summary.json').is_file()]
    complete=len(summaries)==len(MODES) and all(x['complete'] for x in summaries)
    assert complete==exit_record['completed']
    assert all((r['child_exit_code']==0)==s['complete']
               for r,s in zip(exit_record['child_receipts'],summaries))
    out={'schema':'V108_INDEPENDENT_STDLIB_PATCH_READONLY_FULL_WORKLOAD_STORED_AUDIT',
         'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
         'complete_patch_architecture':complete,'input_binding_pins':len(pins),
         'copied_helpers_source_review':helpers,'kernel_return_source_review':kernel_return_review,
         'read_path_source_review':read_path_review,'children':summaries,
         'native_child_receipts_preserved':exit_record['child_receipts'],
         'total_raw_rollouts':sum(x['actual_counts'].get('rollout',0) for x in summaries),
         'total_steps':sum(x['actual_counts'].get('step',0) for x in summaries),
         'total_chronological_TD_receipts':sum(x['tag_inventory'].get('CORE_EPISODE',0) for x in summaries),
         'total_owner_receipts':sum(x['original_owner_receipts_verified'] for x in summaries),
         'old_checker_RFL_execution':False,
         'runtime_identity_reconstructed':False,'scientific_qualification':False,
         'positive_benefit_required':False,
         'previous_audit_history_retained':{
             'successful_original_auditor':meta(PREVIOUS/'audit_dense_kernel_return_revised.py'),
             'successful_original_result':meta(PREVIOUS/'stored_audit_kernel_return_revised_result.json'),
             'first_failed_original_auditor':meta(PREVIOUS/'audit_dense.py'),
             'first_failed_original_exit':meta(PREVIOUS/'evidence_stored_audit/exit.json'),
             'first_failed_original_stderr':meta(PREVIOUS/'evidence_stored_audit/stderr.log'),
             'second_failed_original_auditor':meta(PREVIOUS/'audit_dense_dispatch_revised.py'),
             'second_failed_original_exit':meta(PREVIOUS/'evidence_stored_audit_dispatch_revised/exit.json'),
             'second_failed_original_stderr':meta(PREVIOUS/'evidence_stored_audit_dispatch_revised/stderr.log'),
             'previous_sources_imported_or_executed':False},
         'audit_source':meta(Path(__file__))}
    with (HERE/'stored_audit_result.json').open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(canonical(out)+'\n')
    print(canonical(out))


if __name__=='__main__':
    main()
