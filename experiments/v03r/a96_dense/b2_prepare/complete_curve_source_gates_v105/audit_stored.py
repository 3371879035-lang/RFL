"""Independent streaming audit of actual bounded source-gate capture.

Only stdlib is imported. Recorded objects remain records; this audit does not
construct native sources, roles, opaque handles, or a keyed training protocol.
"""
import ast
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
VARIANTS = ('normal','post_address','proposal_option','floor_draw',
            'immediate_write','remeasure_pre','different_stream')
MODES = ('dq','patch-adaptive')
FIELDS = ('x','y','t','kappa','phi')
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


def check_rollout(trace,pending):
    assert pending and [p['result'] for p in pending] == trace['steps']
    assert trace['mask'] == {'decision':None,'controller':None,'plant':None,'trap':None}
    assert trace['interventions'] == {'members':[]}
    assert state(pending[0]['pre_state'])[:3] == (0,2,0)
    assert pending[0]['pre_control'] == {'z':trace['option_in_force'],'m':0}
    for i,p in enumerate(pending):
        check_step(p)
        assert p['pre_state']['t'] == i
        if i:
            assert p['pre_state'] == pending[i-1]['result']['state']
            assert p['pre_control'] == pending[i-1]['result']['control']
            assert not pending[i-1]['result']['terminal']
    assert pending[-1]['result']['terminal'] and trace['outcome'] == pending[-1]['result']['outcome']
    assert trace['control'] == pending[-1]['result']['control']


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


def replace_one(src,old,new):
    assert src.count(old) == 1
    return src.replace(old,new)


def source_review(manifest):
    old=ROOT/'src/rfl_rebuild/b2/training.py'
    tree=ast.parse(old.read_text(encoding='utf-8'))
    td=(HERE/'variants/normal/td.py').read_text(encoding='utf-8')
    transported=ast.parse(td)
    for name in ('uniform_action','visited_order','sweep_edits'):
        a=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
        b=next(n for n in transported.body if isinstance(n,ast.FunctionDef) and n.name==name)
        assert ast.dump(a,include_attributes=False) == ast.dump(b,include_attributes=False)
    prefix='v105_normal'
    normal={name:(HERE/'variants/normal'/name).read_text(encoding='utf-8')
            for name in ('td.py','learning.py','owned_curve.py','external.py')}
    old95=HERE.parent/'owned_curve_connector_v95'
    back=normal['learning.py'].replace('\nimport '+prefix+'_td as TD','').replace('TD.','T.')
    assert ast.dump(ast.parse(back),include_attributes=False) == ast.dump(ast.parse((old95/'learning.py').read_text(encoding='utf-8')),include_attributes=False)
    for name,previous in (('owned_curve.py','owned_curve.py'),('external.py','external.py')):
        back=normal[name].replace('from '+prefix+'_learning import ','from learning import ').replace('import '+prefix+'_curve as owned_curve\n','import owned_curve\n')
        assert ast.dump(ast.parse(back),include_attributes=False) == ast.dump(ast.parse((old95/previous).read_text(encoding='utf-8')),include_attributes=False)
    for variant in VARIANTS:
        expected=dict(normal)
        if variant=='post_address':
            expected['td.py']=replace_one(td,'q_j = QAddress(state=state_j, z=control_j.z, m=control_j.m, a=result.a_cmd)',
                                         'q_j = QAddress(state=result.state, z=control_j.z, m=control_j.m, a=result.a_cmd)')
        elif variant=='proposal_option':
            expected['td.py']=replace_one(td,'control = initial_control(trace.option_in_force)','control = initial_control(trace.base_option)')
        elif variant=='floor_draw':
            n=next(n for n in transported.body if isinstance(n,ast.FunctionDef) and n.name=='uniform_action')
            lines=td.splitlines(keepends=True)
            lines[n.lineno-1:n.end_lineno]=['def uniform_action(episode, i, admissible):\n',
                 '    ordered = tuple(sorted(admissible))\n','    return ordered[(episode.chi(i, 1, 0) * len(ordered)) >> 64]\n']
            expected['td.py']=''.join(lines)
        elif variant=='immediate_write':
            expected['learning.py']=replace_one(normal['learning.py'],'        self._completed += 1',
                 '        if self.mode == "dq":\n'
                 '            self._immediate.apply_transaction(edits, q_reference=self.reference)\n'
                 '        elif actor_edits:\n'
                 '            self._immediate.apply_transaction(tuple(actor_edits))\n'
                 '        self._completed += 1')
        elif variant=='remeasure_pre':
            src=replace_one(normal['owned_curve.py'],'import adaptive_training as A',
                            'import adaptive_training as A\nfrom rfl_rebuild.b2 import training as T')
            src=replace_one(src,'_PROGRESS = WeakKeyDictionary()','_PROGRESS = WeakKeyDictionary()\n_ARM_PRE = {}')
            src=replace_one(src,'            checkpoints, training = [], []',
                            '            _ARM_PRE[(bundle, role)] = T.pre_level(d.plan.evaluation_sample, q_reference=actor.reference)\n'
                            '            checkpoints, training = [], []')
            expected['owned_curve.py']=replace_one(src,'return checkpoints, d.plan.v_pre, d.plan.t_max',
                                                   'return checkpoints, _ARM_PRE[(bundle, role)], d.plan.t_max')
        elif variant=='different_stream':
            expected['owned_curve.py']=replace_one(normal['owned_curve.py'],'receipt = actor.train_episode(d.plan.episode(e))',
                 'stream = d.plan.episode(e)\n'
                 '                    if role == "treatment":\n'
                 '                        inp = stream._input\n'
                 '                        stream._input = EngineeringEpisode(inp.epoch, inp.kappa, inp.proposal, inp.tape,\n'
                 '                            tuple(x ^ 1 for x in inp.coins), inp.rejections)\n'
                 '                    receipt = actor.train_episode(stream)')
        for name,pin in manifest['variants'][variant].items():
            path=ROOT/pin['path']; assert meta(path)=={k:pin[k] for k in ('bytes','sha256')}
            got=path.read_text(encoding='utf-8').replace('v105_'+variant,prefix)
            assert got==expected[name], (variant,name,'unexpected extra source change')
    # The successor is a new namespace plus exactly one setup-path repair.
    previous=HERE.parent/'complete_curve_source_gates_v104/test_source_gates.py'
    old=previous.read_text(encoding='utf-8').replace('v104','v105')
    old=replace_one(old,"ROOT / CONTRACT['healthy_reference']","ROOT / CONTRACT['healthy_reference']['path']")
    assert old == (HERE/'test_source_gates.py').read_text(encoding='utf-8')
    return {'original_TD_functions_AST_equal':3,'normal_import_seams_AST_equal':3,
            'physical_variant_files':28,'single_defect_variants':6,'v104_only_path_repair_and_namespace':True}


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


def declared_episode(c,e):
    spec=c['episodes'][e]
    coins=[M64]*12; rejection=[[0] for _ in range(12)]
    if e==0: coins[0]=coins[1]=0; rejection[1]=[M64,4]
    return {'epoch':e,'kappa':spec['kappa'],'proposal':spec['proposal'],
            'tape':{'phase':spec['phase'],'error_flag':spec['error_flag'],'cause_rank':spec['cause_rank']},
            'coins':coins,'rejections':rejection}


def check_receipt(r,rows,c,variant,role):
    before,after=r['before'],r['after']; e=r['epoch']; inp=r['episode']
    declared=declared_episode(c,e); expected_input=deepcopy(declared)
    if variant=='different_stream' and role=='treatment':
        expected_input['coins']=[x^1 for x in expected_input['coins']]
    assert inp==expected_input and r['parameters']=={'alpha':{'rational':[1,2]},'epsilon':{'rational':[1,10]}}
    assert before['completed_episodes']==e and after['completed_episodes']==e+1
    assert before['immediate']==after['immediate'] and before['mode']==after['mode']
    b,a=storemap(before['current']),storemap(after['current'])
    assert b['P']==a['P'] and b['X']==a['X']
    numeric=storemap(before['current'] if before['mode']=='dq' else before['learning_values'])
    calls,draws=check_policy(r['trace'],b,rows,before['mode'],
                           None if before['mode']=='dq' else numeric,inp,variant=='floor_draw')
    assert calls==r['coordinates'] and draws==r['draws']
    edits,sparse,visited,_=td(r['trace'],inp,numeric,rows,variant=='proposal_option')
    assert edits==r['numeric_edits'], (variant,role,e,'actual mutated/normal TD mismatch')
    updated=storemap(after['current'] if before['mode']=='dq' else after['learning_values'])
    assert {q:v.hex() for q,v in sparse.items()}=={q:v.hex() for q,v in updated['Q'].items()}
    expected_policy=[]; desired_d=dict(b['D']); seen=set()
    if before['mode']=='patch-adaptive':
        assert not b['Q'] and not a['Q']
        assert all(not updated[ch] for ch in ('D','P','X'))
        for context in visited:
            if context in b['D'] and context not in seen:
                row=rows[context]; vals={act:sparse.get(context+(act,),v) for act,v in row.items()}
                chosen=min(act for act,v in vals.items() if v==max(vals.values()))
                expected_policy.append({'store':'decision','address':dict(state=wire_state(context[:5]),z=context[5],m=context[6]),'value':chosen})
                desired_d[context]=chosen; seen.add(context)
    assert expected_policy==r['policy_improvement_edits'] and a['D']==desired_d
    correct,_,_,details=td(r['trace'],inp,numeric,rows,False)
    # Desired common stream uses its own exact coordinates, independent of the mutation.
    wanted=[]
    for i,draw in enumerate(r['draws']):
        coin=declared['coins'][i]; wanted.append([i,0,0,coin])
        if coin*10 < (1<<64):
            legal=draw['admissible']; limit=(1<<64)-((1<<64)%len(legal))
            for ci,d in enumerate(declared['rejections'][i]):
                wanted.append([i,1,ci,d])
                if d<limit: break
    ret=0.0
    for step in r['trace']['steps']: ret+=value(step['reward'])
    assert ret.hex()==r['return_hex']
    n5=None
    if e==0:
        d=r['draws'][1]
        assert d['admissible']==[0,1,2,3,4] and d['explore'] and d['a_cmd']==4
        actual=[call for call in calls if call[0]==1]
        if variant=='floor_draw': assert actual==[[1,0,0,0],[1,1,0,M64]]
        else:
            coin=1 if variant=='different_stream' and role=='treatment' else 0
            assert actual==[[1,0,0,coin],[1,1,0,M64],[1,1,1,4]]
        n5={'role':role,'actual_calls':actual,'same_final_action':4}
    return {'correct_TD_matches':correct==r['numeric_edits'],
            'shared_exact_stream_matches':inp==declared and wanted==calls,
            'correct_TD_details':details,'correct_edits':correct,
            'correct_coordinates':wanted,'n5':n5}


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


def check_case(records,rows,c):
    one=lambda tag:[r['payload'] for r in records if r['tag']==tag]
    begin=one('CASE_BEGIN'); assert len(begin)==1
    variant,mode=begin[0]['variant'],begin[0]['mode']
    assert variant in VARIANTS and mode in MODES
    b1,original_pair=check_source_pair(records,rows,c,mode)
    prepared=one('CURVE_PREPARED'); assert len(prepared)==1
    p=prepared[0]; origin=p['origin']; initial=origin['initial_composites']; plan=origin['engineering_plan']
    declaration=origin['declaration']; pair_seal=digest(declaration)
    assert declaration['original_pair']==original_pair and declaration['mode_before_arms']==mode
    bound=one('BOUND_BEFORE_ARMS'); assert len(bound)==1
    bound=bound[0]; bound_raw=deepcopy(bound['payload'])
    tolerance=bound_raw['source']['payload']['native_source_payload']['truth_evaluator_only']['whole_optimal_set_tolerance']
    bound_raw['source']['payload']['native_source_payload']['truth_evaluator_only']['whole_optimal_set_tolerance']=value(tolerance)
    assert digest(bound_raw)==bound['payload_sha256']==declaration['bound_source_sha256']
    assert bound['payload']['source']==one('ORIGINAL_SOURCE')[0]['audit']
    assert bound['payload']['decision_mode_before_arms']==mode
    assert next(i for i,r in enumerate(records) if r['tag']=='BOUND_BEFORE_ARMS') < next(i for i,r in enumerate(records) if r['tag']=='NATIVE_B1_RETURN')
    assert origin['original_pair_seal']==pair_seal and digest(origin)==p['origin_sha256']
    assert plan['grid']==[0,1,2] and plan['episodes']==[declared_episode(c,e) for e in (0,1)]
    assert plan['engineering_bank_indices']==c['evaluation_indices'] and len(plan['sample'])==2
    assert plan['v_pre_hex']==float(c['shared_v_pre']).hex() and not plan['keyed'] and not plan['formal_execution']
    for i,comp in enumerate(initial):
        assert comp['role']==('reference','treatment')[i] and comp['mode']==mode and comp['source_label']==pair_seal
        assert comp['immediate']==comp['current']==b1[i]['full_post']
        assert comp['completed_episodes']==0 and comp['attempted_epochs']==[]
        assert comp['learning_values']==({'D':[],'P':[],'X':[],'Q':[]} if mode=='patch-adaptive' else None)
    raw=[r['payload'] for r in records if r['tag']=='RAW_ROLLOUT']
    raw_hash=Counter(digest(x) for x in raw)
    curves=one('COMPLETE_ROLE_CURVE'); core=one('CORE_EPISODE'); expects=one('INDEPENDENT_EXPECTATION')
    exceptions=one('ACTUAL_TARGET_EXCEPTION'); result=one('CASE_RESULT')
    assert len(result)==1; result=result[0]
    issues=[]; expected_checks=[]; normal_values=[]; n5=[]
    if exceptions:
        assert variant in ('post_address','immediate_write') and len(exceptions)==1 and not curves and not core
        exc=exceptions[0]
        assert exc['attempted'] and not exc['complete_handle_issued'] and exc['sweep_calls']>0
        assert result['complete_role_handles']==0
        if variant=='post_address':
            last=exc['last_source_sweep']; q=addr(last['current_address'],'Q')
            assert q[:5]==state(last['actual_result']['state']) and q[:5]!=state(last['actual_pre_state'])
            assert q[:-1] not in rows or q[-1] not in rows[q[:-1]]
            assert 'reference has no row' in exc['message'] or 'not admissible' in exc['message']
            assert exc['immediate_states']==exc['initial_immediate']
            issues=['actual_post_address_outside_valid_reference']
        else:
            assert 'protected immediate state changed' in exc['message']
            assert exc['immediate_states']!=exc['initial_immediate']
            assert exc['initial_immediate']==[x['full_post'] for x in b1]
            issues=['actual_future_write_changed_protected_immediate']
        assert not one('EXTERNAL_VIEW')
    else:
        assert len(curves)==2 and len(core)==len(expects)==4 and result['complete_role_handles']==2
        for i,curve in enumerate(curves):
            role=('reference','treatment')[i]
            assert curve['role']==role and curve['origin_sha256']==p['origin_sha256']
            assert [x['epoch'] for x in curve['checkpoints']]==[0,1,2]
            assert [x['epoch'] for x in curve['training']]==[0,1]
            assert curve['training']==core[2*i:2*i+2]
            prev=initial[i]; levels=[]
            for e,cp in enumerate(curve['checkpoints']):
                assert len(cp['traces'])==2
                before=prev
                total=0.0
                for j,trace in enumerate(cp['traces']):
                    assert raw_hash[digest(trace)]>0
                    scene=plan['sample'][j]
                    assert trace['base_option']==scene[4] and state(trace['steps'][0]['state'])[3:]==(scene[0],scene[1])
                    check_policy(trace,storemap(before['current']),rows,mode,
                                 None if mode=='dq' else storemap(before['learning_values']))
                    ret=0.0
                    for step in trace['steps']: ret+=value(step['reward'])
                    total+=ret
                mean=total/2; assert mean.hex()==cp['mean_hex']; levels.append(mean.hex())
                if e<2:
                    receipt=curve['training'][e]
                    assert receipt['before']['current']==before['current'] and receipt['before']['learning_values']==before['learning_values']
                    assert receipt['before']['immediate']==initial[i]['immediate']
                    assert raw_hash[digest(receipt['trace'])]>0
                    checked=check_receipt(receipt,rows,c,variant,role); expected_checks.append(checked)
                    expectation=expects[2*i+e]
                    assert expectation['role']==role and expectation['epoch']==e
                    assert expectation['TD']==checked['correct_TD_details'] and expectation['expected_edits']==checked['correct_edits']
                    assert expectation['expected_coordinates']==checked['correct_coordinates']
                    assert expectation['td_matches']==checked['correct_TD_matches']
                    assert expectation['coordinate_matches']==checked['shared_exact_stream_matches']
                    if not checked['correct_TD_matches']: issues.append('chronological_TD')
                    if not checked['shared_exact_stream_matches']: issues.append('exact_coordinate_stream')
                    if checked['n5']: n5.append(checked['n5'])
                    prev=receipt['after']
            ending=curve['full_pair_after']['ordered_composites'][i]
            assert ending==prev and curve['full_pair_after']['completed']
            normal_values.append({'role':role,'ordered_value_hex':levels})
        views=one('EXTERNAL_VIEW'); assert len(views)==2
        for i,(view,curve) in enumerate(zip(views,curves)):
            assert set(view)=={'fields','episodes','values','pre_level','t_max'}
            assert set(view['fields'])=={'future_rewards','future_outcomes','future_trajectories','future_actions','future_observations'}
            assert view['episodes']==[0,1,2] and view['t_max']==2
            expected={k:[] for k in view['fields']}
            for cp in curve['checkpoints']:
                traces=cp['traces']
                expected['future_rewards'].append([[s['reward'] for s in t['steps']] for t in traces])
                expected['future_outcomes'].append([[s['outcome'] for s in t['steps']] for t in traces])
                expected['future_trajectories'].append([[s['state'] for s in t['steps']] for t in traces])
                expected['future_actions'].append([[s['a_cmd'] for s in t['steps']] for t in traces])
                expected['future_observations'].append([[None for s in t['steps']] for t in traces])
            assert view['fields']==expected and view['values']==[{'binary64_hex':cp['mean_hex']} for cp in curve['checkpoints']]
            if variant=='remeasure_pre':
                assert value(view['pre_level']).hex()==one('ACTUAL_PRE_REMEASUREMENT_RETURN')[i]['mean_hex']
                if value(view['pre_level'])!=c['shared_v_pre']: issues.append('shared_pre_level')
            else: assert value(view['pre_level']).hex()==float(c['shared_v_pre']).hex()
    pre_returns=one('ACTUAL_PRE_REMEASUREMENT_RETURN')
    if pre_returns:
        assert variant=='remeasure_pre' and len(pre_returns)==2; issues.append('pre_level_remeasurement')
    issues=sorted(set(issues)); assert issues==result['issues']
    expected={'normal':[], 'post_address':['actual_post_address_outside_valid_reference'],
              'proposal_option':['chronological_TD'], 'floor_draw':['exact_coordinate_stream'],
              'immediate_write':['actual_future_write_changed_protected_immediate'],
              'remeasure_pre':['pre_level_remeasurement','shared_pre_level'],
              'different_stream':['exact_coordinate_stream']}[variant]
    assert issues==expected
    assert result['source_level_mutant_rejected']==(variant!='normal') and result['normal_complete']==(variant=='normal')
    assert not result['automatic_retry']
    counts=Counter(r['tag'] for r in records)
    measured={'rollout':counts['RAW_ROLLOUT'],'step':counts['RAW_STEP'],
              'transaction':counts['TX_CALL'],'B1':counts['NATIVE_B1_RETURN']}
    assert result['actual_counts']==measured
    assert result['source_sweep_calls']==counts['SOURCE_TD_ENTER']
    assert result['actual_pre_measurements']==[x['mean_hex'] for x in pre_returns]
    return {'variant':variant,'mode':mode,'issues':issues,'counts':measured,
            'complete_role_curves':len(curves),'actual_n5':n5,'ordered_curves':normal_values,
            'source_owners':7,'source_residuals':3,'native_owner_receipts':14,
            'protected_original_pair_preserved':True,'partial_no_handle':bool(exceptions)}


def main():
    started=datetime.now(timezone.utc).isoformat()
    c=json.loads((HERE/'contract.json').read_bytes())
    claim=json.loads((HERE/'evidence/claim.json').read_bytes())
    exit_record=json.loads((HERE/'evidence/exit.json').read_bytes())
    pins=claim['input_binding_before']
    assert pins==exit_record['input_binding_after'] and exit_record['input_bytes_unchanged']
    assert not claim['automatic_retry'] and not exit_record['automatic_retry']
    for name,pin in pins.items(): assert meta(ROOT/name)==pin,name
    for name in ('stdout','stderr'): assert meta(HERE/'evidence'/f'{name}.log')==exit_record[name]
    manifest=json.loads((HERE/'variant_manifest.json').read_bytes()); physical=source_review(manifest)
    rows=read_reference(c['reference_input'])
    summaries=[]; inventory=None; final=None; tags=Counter(); pending=[]; tx=None; current=None; current_rows=[]
    record_count=0; global_count=Counter(); active_pre=None; pre_scopes=0
    with (HERE/'evidence/stdout.log').open(encoding='utf-8') as stream:
        for line in stream:
            record_count+=1; record=json.loads(line)
            assert canonical(record)==line.rstrip('\n'),record_count
            tag,payload=record['tag'],record['payload']; tags[tag]+=1
            if tag=='CASE_BEGIN':
                assert not current_rows and not pending and tx is None
                current=record['case']; current_rows=[record]
            elif current is not None:
                assert record['case']==current; current_rows.append(record)
            if tag=='REFERENCE': assert payload=={'digest':c['reference_input']['q_digest'],'rows':13824}
            elif tag=='RAW_STEP':
                pending.append(payload); global_count['step']+=1
            elif tag=='RAW_ROLLOUT':
                check_rollout(payload,pending); pending=[]; global_count['rollout']+=1
                if active_pre is not None: active_pre.append(payload)
            elif tag=='INCOMPLETE_ROLLOUT':
                assert payload is None
            elif tag=='TX_CALL':
                assert tx is None; tx=payload; global_count['transaction']+=1
            elif tag=='TX_RETURN':
                assert tx is not None
                assert maps_equal(apply_edits(storemap(tx['before']),tx['edits'],rows),storemap(payload['after']))
                tx=None
            elif tag=='NATIVE_B1_RETURN': global_count['B1']+=1
            elif tag=='SOURCE_TD_ENTER':
                assert payload['source_sha256']==manifest['variants'][current.split(':')[0]]['td.py']['sha256']
                assert digest(payload['trace']) in {digest(r['payload']) for r in current_rows if r['tag']=='RAW_ROLLOUT'}
            elif tag=='ACTUAL_PRE_REMEASUREMENT_ENTER':
                assert active_pre is None; active_pre=[]
            elif tag=='ACTUAL_PRE_REMEASUREMENT_RETURN':
                assert active_pre is not None and len(active_pre)==2
                total=0.0
                healthy={'D':{},'P':{},'X':{},'Q':{}}
                for trace in active_pre:
                    check_policy(trace,healthy,rows)
                    ret=0.0
                    for s in trace['steps']: ret+=value(s['reward'])
                    total+=ret
                assert (total/2).hex()==payload['mean_hex']; active_pre=None; pre_scopes+=1
            elif tag=='CASE_RESULT':
                assert not pending and tx is None and active_pre is None
                summaries.append(check_case(current_rows,rows,c)); current=None; current_rows=[]
            elif tag=='ACTUAL_LOADED_SOURCE_INVENTORY':
                assert inventory is None; inventory=payload
                assert all(name in pins and pins[name]['sha256']==h for name,h in inventory.items())
            elif tag=='RESULT':
                assert final is None; final=payload
                assert payload['canonical_records_before_result']==record_count-1
    assert not pending and tx is None and active_pre is None
    native_exit=exit_record['child_exit_code']
    if native_exit==0:
        assert not current_rows and final is not None and inventory is not None
        assert [(s['variant'],s['mode']) for s in summaries]==[(v,m) for v in VARIANTS for m in MODES]
        assert len(summaries)==14 and final['counts']==dict(global_count)
        assert len(final['cases'])==14 and final['six_targets_both_architectures']
        assert not final['formal_keyed_stream'] and not final['scientific_qualification'] and not final['collection_authorized']
        assert tags['CORE_EPISODE']==40 and tags['COMPLETE_ROLE_CURVE']==20 and tags['ACTUAL_TARGET_EXCEPTION']==4
        assert global_count['B1']==28 and tags['ORIGINAL_SOURCE']==14 and pre_scopes==4
        assert sum(s['native_owner_receipts'] for s in summaries)==196
    out={'schema':'V105_INDEPENDENT_STREAMING_SOURCE_MUTATION_STORED_CONTENT_AUDIT',
         'native_exit_preserved':native_exit,'input_binding_pins':len(pins),'loaded_source_pins':len(inventory or {}),
         'records':record_count,'tag_inventory':dict(tags),'actual_counts':dict(global_count),
         'physical_source_review':physical,'case_results':summaries,
         'complete_fourteen_case_capture':native_exit==0 and len(summaries)==14,
         'six_targets_both_architectures':native_exit==0 and len(summaries)==14,
         'correct_and_mutated_TD_recomputed':tags['CORE_EPISODE'],
         'actual_per_role_pre_measurement_scopes':pre_scopes,
         'uncompleted_case':current,'uncompleted_record_count':len(current_rows),
         'automatic_retry':False,'old_fixture_checker_RFL_execution':False,
         'runtime_identity_reconstructed':False,'formal_keyed_domain_proof':False,
         'independent_expert_or_science_gate':False,'scientific_qualification':False,
         'audit_source':meta(Path(__file__)),'started_at_utc':started,
         'completed_at_utc':datetime.now(timezone.utc).isoformat()}
    with (HERE/'stored_audit_result.json').open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(canonical(out)+'\n')
    print(canonical(out))


if __name__=='__main__':
    main()
