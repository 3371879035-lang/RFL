"""Independent stdlib audit of the first genuine T empty-projection future.

This program reads complete stored content only. It does not import RFL,
old checkers, sources, or learners, and cannot reconstruct runtime identity.
The factual TRAP route has its own exact step-zero validator; ordinary future
raw alone uses the no-fault physics validator. Empty-owner Collateral remains
not-applicable/null, never an invented zero effect or treatment success.
"""
import ast
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PREVIOUS = HERE.parent / "patch_dense_completion_v108"
MODES = ("dq", "patch-adaptive")
ROLES = ("reference", "treatment")
FIELDS = ("x", "y", "t", "kappa", "phi")
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
EXTERNAL_FIELDS = ("future_rewards","future_outcomes","future_trajectories",
                   "future_actions","future_observations")
COPIED_HELPERS = ["canonical","digest","meta","value","state","wire_state","addr","storemap","flat","fingerprint","maps_equal","allowed","hazard","check_step","read_reference","edit_key","apply_edits","greedy","check_policy","td","decode_native_float","verify_seal","declared_episode","reconstructed_rollout","projected_bank","expected_training_before","verify_receipt"]


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



def copied_helpers_review():
    old_path=PREVIOUS/"audit_stored.py"
    old_text=old_path.read_text(encoding="utf-8")
    new_text=Path(__file__).read_text(encoding="utf-8")
    old,new=ast.parse(old_text),ast.parse(new_text)
    pins=[]
    for name in COPIED_HELPERS:
        a=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name==name)
        b=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name==name)
        old_source,new_source=ast.get_source_segment(old_text,a),ast.get_source_segment(new_text,b)
        assert old_source==new_source and ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False),name
        pins.append({"function":name,"source_sha256":hashlib.sha256(old_source.encode("utf-8")).hexdigest()})
    return {"source":meta(old_path),"exact_copied_functions":pins,
            "old_checker_import_or_execution":False}


def source_review(c):
    path=HERE/"nocredit.py"
    text=path.read_text(encoding="utf-8")
    tree=ast.parse(text)
    functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    required={"run_no_credit_pair","_checked_metadata","prepare_curve","_checked",
              "run_pair_curve","_external_material","_project","build_external","read_external"}
    assert required<=set(functions)
    imports=[alias.name for n in tree.body if isinstance(n,ast.Import) for alias in n.names]
    assert "v107_bank" in imports and "handoff" in imports and "oracle_mainline_v75" in imports
    learning=next(n for n in tree.body if isinstance(n,ast.ImportFrom) and n.module=="v105_normal_learning")
    assert {alias.name for alias in learning.names}=={"CoordinateLearner","EngineeringEpisode","EngineeringPlan"}
    prepare=functions["prepare_curve"]
    calls=[n for n in ast.walk(prepare) if isinstance(n,ast.Call)]
    assert any(isinstance(n.func,ast.Attribute) and n.func.attr=="_template" for n in calls)
    assert not any(isinstance(n.func,ast.Attribute) and n.func.attr in
                   ("prepare_future_inputs","_checked_original_pair","run_patch_law","run_dq_law","apply_transaction")
                   for n in ast.walk(tree) if isinstance(n,ast.Call))
    assert not any(isinstance(n,ast.Name) and n.id in ("FutureTrainingProtocol","KeyedPlan","ExogenousEpisode")
                   for n in ast.walk(tree))
    project=functions["_project"]
    assert not any(isinstance(n,ast.Name) and n.id in ("H","O","A","_FUTURES","_METADATA")
                   for n in ast.walk(project))
    material=functions["_external_material"]
    last=material.body[-1]
    assert isinstance(last,ast.Return) and isinstance(last.value,ast.Tuple) and len(last.value.elts)==3
    kernel=ROOT/"src/rfl_rebuild/env/kernel.py"
    kernel_text=kernel.read_text(encoding="utf-8")
    kt=ast.parse(kernel_text)
    trace_class=next(n for n in kt.body if isinstance(n,ast.ClassDef) and n.name=="RolloutTrace")
    getter=next(n for n in trace_class.body if isinstance(n,ast.FunctionDef) and n.name=="return_value")
    expected=ast.parse("def return_value(self):\n    return float(sum(s.reward for s in self.steps))\n").body[0].body[0]
    assert ast.dump(getter.body[-1],include_attributes=False)==ast.dump(expected,include_attributes=False)
    assert sys.implementation.name=="cpython" and tuple(sys.version_info[:3])==(3,12,14)
    claim=json.loads((HERE/"evidence/claim.json").read_bytes())
    assert str(Path(claim["command"][0]).resolve()).casefold()==str(Path(sys.executable).resolve()).casefold()
    step=next(n for n in kt.body if isinstance(n,ast.FunctionDef) and n.name=="step")
    segment=ast.get_source_segment(kernel_text,step)
    assert "state.t == mask.trap.t" in segment and "Outcome.TRAP" in segment
    return {"entry_source":meta(path),"functions":[{"name":name,
            "source_sha256":hashlib.sha256(ast.get_source_segment(text,functions[name]).encode("utf-8")).hexdigest()}
            for name in sorted(required)],"new_empty_origin_not_old_future_handle":True,
            "ordinary_learner_and_TD_source_unchanged":True,"external_project_reads_only_raw":True,
            "kernel_return_getter_source_sha256":hashlib.sha256(ast.get_source_segment(kernel_text,getter).encode("utf-8")).hexdigest(),
            "kernel_trap_step_source_sha256":hashlib.sha256(segment.encode("utf-8")).hexdigest(),
            "factual_trap_action_step_not_post_clock":True,
            "runtime_identity_reconstructed":False}


def locked_sample(healthy):
    cells=[(k,phi,flag,proposal) for k in (0,1) for phi in range(6)
           for flag in (0,1) for proposal in range(4)]
    sample=[]
    for n in range(100):
        q,r=divmod(n,96)
        k,phi,flag,proposal=cells[r]
        sample.append([k,phi,flag,(7*q+37*r)%60,proposal])
    assert hashlib.sha256(repr(tuple(tuple(s) for s in sample)).encode("utf-8")).hexdigest()==healthy["evaluation_sample_sha256"]
    return sample


def factual_trap(payload,c,rows):
    trace=payload["trace"]
    assert payload["kappa"]==c["source_scene"][0]
    assert payload["tape"]==dict(phase=c["source_scene"][1],error_flag=c["source_scene"][2],cause_rank=c["source_scene"][3])
    assert trace["mask"]=={"decision":None,"controller":None,"plant":None,"trap":{"cell":[1,2],"t":0}}
    assert trace["interventions"]=={"members":[]} and trace["base_option"]==trace["option_in_force"]==0
    assert len(trace["steps"])==1 and trace["outcome"]=="TRAP" and trace["control"]=={"z":0,"m":0}
    s=(0,2,0,0,0)
    assert greedy({ch:{} for ch in ("D","P","X","Q")},rows,s,0,0)==3
    result=trace["steps"][0]
    assert result=={"state":{"x":1,"y":2,"t":1,"kappa":0,"phi":0},"control":{"z":0,"m":0},
                    "a_cmd":3,"u":3,"a_realized":3,"reward":{"binary64_hex":(-1.02).hex()},
                    "terminal":True,"outcome":"TRAP","illegal":False}
    assert result["a_cmd"] in allowed(s,0,0)
    # Original ordering: collision first; (1,2) is not contested, then matching
    # trap cell and the PRE-action clock 0, ahead of goal/timeout.
    assert (1,2)!=(2,2) and trace["mask"]["trap"]["t"]==s[2]
    actual=float(sum(value(step["reward"]) for step in trace["steps"]))
    assert actual.hex()==payload["return_hex"]==(-1.02).hex()
    return actual


def check_original_metadata(records,c,mode,rows):
    one=lambda tag:[record for record in records if record["tag"]==tag]
    assert all(len(one(tag))==1 for tag in
               ("RAW","ORIGINAL_SOURCE","SOURCE_TRUTH_ACTUAL","BOUND_BEFORE_ARMS","ORIGINAL_PAIR","NO_CREDIT_METADATA"))
    raw,source,truth,bound,pair,metadata=(one(tag)[0] for tag in
               ("RAW","ORIGINAL_SOURCE","SOURCE_TRUTH_ACTUAL","BOUND_BEFORE_ARMS","ORIGINAL_PAIR","NO_CREDIT_METADATA"))
    native_trace=raw["payload"]["trace"]
    source_payload=source["payload"]
    assert source_payload["mode"]==mode and flat(source_payload["supplied_pre"])=={ch:[] for ch in ("D","P","X","Q")}
    source_audit=source_payload["audit"]
    verify_seal(source_audit)
    native=source_audit["payload"]["native_source_payload"]
    assert digest(decode_native_float(native))==source_audit["payload"]["native_source_sha256"]
    assert native["regime"]=="T" and native["scene"]==c["source_scene"]
    assert native["full_pre_stores"]=={ch:[] for ch in ("D","P","X","Q")}
    assert native["q_reference_sha256"]==c["reference_input"]["q_digest"]
    assert native["owned_cf_configuration"] is None and native["diagnostic_method_calls"]==0
    expected_truth={"truth_source":"A66_A67_A71_SAME_TRACE_STRUCTURAL_R_MECH_DESCRIPTORS_NOT_J_OR_RESCUE",
                    "R_mech":[{"kind":"rho_U","cell":[1,2],"t":0}],"Gamma_T_star":["Unknown/NoWrite"],
                    "Gamma_P_star":None,"J_L":None,"Z_fire":[False,False,False,False,True]}
    assert native["truth_evaluator_only"]==expected_truth
    assert truth["payload"]=={"truth":expected_truth,"fullpre":{ch:[] for ch in ("D","P","X","Q")},
                              "outcome":"TRAP","return_hex":(-1.02).hex(),"actual_mask":native_trace["mask"],"regime":"T"}
    result=native_trace["steps"][0]
    assert native["raw_factual"]==[{"pre_state":[0,2,0,0,0],"z":0,"m":0,"a_cmd":3,"u":3,"a_realized":3,
                                   "post_state":[1,2,1,0,0],"post_control":[0,0],"reward_hex":(-1.02).hex(),
                                   "terminal":True,"outcome":"TRAP","illegal":False}]
    assert native["fingerprint_pre"]==fingerprint(source_payload["supplied_pre"])
    assert native["trace_metadata"]["outcome"]=="TRAP" and native["trace_metadata"]["base_option"]==0
    assert raw["seq"]<source["seq"]<truth["seq"]<bound["seq"]<pair["seq"]<metadata["seq"]
    bound_payload=bound["payload"]
    # H uses A.digest on its wired bound payload. Only original source seal
    # verification above decodes native float fields; learned Q markers never
    # pass through the native-seal decoder.
    assert digest(bound_payload["payload"])==bound_payload["payload_sha256"]
    assert bound_payload["payload"]["source"]==source_audit
    assert bound_payload["payload"]["decision_mode_before_arms"]==mode
    assert flat(bound_payload["payload"]["full_pre"])==native["full_pre_stores"]
    assert bound_payload["payload"]["reference_digest"]==c["reference_input"]["q_digest"]
    pair_audit=pair["payload"]
    verify_seal(pair_audit)
    older=pair_audit["payload"]["original_v74_pair"]
    verify_seal(older)
    old=older["payload"]
    assert old["route"]=="NO_CREDIT_IN_CELL_NO_FAKE_LEDGER_OR_FUTURE"
    assert old["architecture"]==("D_Q" if mode=="dq" else "D_patch")
    assert old["whole_oracle_units"]==old["residual_units_preserved"]==["Unknown/NoWrite"]
    assert old["cell_units"]==old["all_owner_receipts"]==[]
    assert old["native_B1_arm_calls"]==0 and old["primary_Collateral"] is None and not old["scientific_PASS"]
    assert old["source_sha256"]==source_audit["payload"]["native_source_sha256"]
    assert pair_audit["payload"]["source_sha256"]==source_audit["payload_sha256"]
    declaration=metadata["payload"]["declaration"]
    assert digest(declaration)==metadata["payload"]["declaration_sha256"]
    assert declaration["source"]==source_audit and declaration["original_metadata_pair"]==pair_audit
    assert declaration["bound_source_sha256"]==bound_payload["payload_sha256"]
    assert declaration["decision_mode_before_metadata"]==mode
    h_declaration=declaration["original_bound_pair_declaration"]
    assert digest(h_declaration)==declaration["original_bound_pair_sha256"]
    assert h_declaration["original_pair"]==pair_audit and h_declaration["mode_before_arms"]==mode
    assert h_declaration["bound_source_sha256"]==bound_payload["payload_sha256"]
    for name in ("cell_units","owner_addresses"):
        assert declaration[name]==[]
    assert declaration["whole_units"]==declaration["residual_units"]==["Unknown/NoWrite"]
    for name in ("native_B1_arm_calls","owner_receipts","therapy_transactions"):
        assert declaration[name]==0
    assert declaration["contrast_status"]=="NO_SUBSTANTIVE_UPDATE_CONTRAST"
    assert declaration["collateral_status"]=="NOT_APPLICABLE_EMPTY_OWNER_SET" and declaration["collateral"] is None
    return source_audit,metadata["payload"],bound_payload


def check_future_begin(p,records,c,mode,rows,healthy):
    source,metadata,bound=check_original_metadata(records,c,mode,rows)
    origin=p["origin"]
    assert digest(origin)==p["origin_sha256"]
    assert origin["declaration"]==metadata["declaration"]
    assert origin["metadata_sha256"]==metadata["declaration_sha256"]
    empty={ch:[] for ch in ("D","P","X","Q")}
    assert origin["full_source_pre"]==empty and origin["protected_no_edit_immediate"]==[empty,empty]
    plan=origin["engineering_plan"]
    assert plan["episodes"]==[declared_episode(epoch) for epoch in range(3)]
    assert plan["grid"]==[0,1,2,3] and plan["engineering_bank_indices"]==list(range(100))
    assert plan["sample"]==locked_sample(healthy) and plan["v_pre_hex"]==float(healthy["v_pre"]).hex()
    assert plan["original_lock_sha256"]==healthy["lock_sha256"]
    assert plan["parameters"]=={"alpha":{"rational":[1,2]},"epsilon":{"rational":[1,10]}}
    assert plan["keyed"] is False and plan["formal_execution"] is False
    template=origin["original_locked_template"]
    assert template["alpha"]==[1,2] and template["epsilon"]==[1,10]
    assert template["T"]==465 and template["grid"]==list(range(466)) and template["seed"] is None
    assert template["evaluation_units"]==plan["sample"] and template["evaluation_sha256"]==healthy["evaluation_sample_sha256"]
    assert template["v_pre_hex"]==plan["v_pre_hex"] and template["lock_sha256"]==healthy["lock_sha256"]
    assert template["healthy_sha256"]==source["payload"]["native_source_payload"]["healthy_reference_sha256"]
    initial=origin["initial_composites"]
    assert initial==p["ordered_composites"] and len(initial)==2
    for role,comp in zip(ROLES,initial):
        assert comp["mode"]==mode and comp["role"]==role
        assert comp["source_label"]==metadata["declaration_sha256"]
        assert comp["reference_digest"]==c["reference_input"]["q_digest"]
        assert comp["immediate"]==comp["current"]==empty
        assert comp["learning_values"]==(empty if mode=="patch-adaptive" else None)
        assert comp["completed_episodes"]==0 and comp["attempted_epochs"]==[]
    for part in (p,origin):
        assert part["contrast_status"]=="NO_SUBSTANTIVE_UPDATE_CONTRAST"
        assert part["collateral_status"]=="NOT_APPLICABLE_EMPTY_OWNER_SET" and part["collateral"] is None
    assert p["attempted"] is False and p["completed"] is False and p["progress"]==[]
    return initial,plan,source,p["origin_sha256"],origin


def check_external_short(view,banks,mode,role,pre):
    assert set(view)=={"fields","episodes","values","pre_level","t_max"}
    assert set(view["fields"])==set(EXTERNAL_FIELDS)
    assert view["episodes"]==[0,1,2,3] and view["t_max"]==3
    assert value(view["pre_level"]).hex()==pre
    assert view["values"]==[{"binary64_hex":banks[(mode,role,e)]["mean_hex"]} for e in range(4)]
    for field in EXTERNAL_FIELDS:
        assert len(view["fields"][field])==4
        for e,values in enumerate(view["fields"][field]):
            assert len(values)==100 and digest(values)==banks[(mode,role,e)]["projection"][field]


def check_final(p,mode,states,origins):
    assert p["origin"]==origins[mode]["origin"] and p["origin_sha256"]==origins[mode]["seal"]
    assert p["ordered_composites"]==[states[(mode,role)] for role in ROLES]
    assert p["attempted"] is True and p["completed"] is True
    assert p["contrast_status"]=="NO_SUBSTANTIVE_UPDATE_CONTRAST"
    assert p["collateral_status"]=="NOT_APPLICABLE_EMPTY_OWNER_SET" and p["collateral"] is None
    for role in ROLES:
        comp=states[(mode,role)]
        assert comp["completed_episodes"]==3 and comp["attempted_epochs"]==[0,1,2]
    progress=p["progress"]
    expected=[]
    for role in ROLES:
        for e in range(4):
            expected.extend(({"role":role,"epoch":e,"stage":"evaluation_started"},
                             {"role":role,"epoch":e,"stage":"evaluation_completed"}))
            if e<3:
                expected.extend(({"role":role,"epoch":e,"stage":"training_started"},
                                 {"role":role,"epoch":e,"stage":"training_completed"}))
    assert len(progress)==len(expected)
    for actual,expected_item in zip(progress,expected):
        assert {key:actual[key] for key in expected_item}==expected_item


def audit_records(c,rows,pins,healthy,exit_record):
    folder=HERE/"evidence"
    summary=json.loads((folder/"child_summary.json").read_bytes())
    checksum=hashlib.sha256()
    size=0
    counts=Counter()
    tags=Counter()
    sources={mode:[] for mode in MODES}
    origins={}
    states={}
    banks={}
    complete=set()
    external=set()
    diagnostics=Counter()
    raw_training=None
    train=None
    bank=None
    tx=None
    native_summary=None
    guards=[]
    restores=[]
    equality={}
    partial_records=[]
    seq=0
    with (folder/"raw.jsonl").open("rb") as stream:
        for line in stream:
            record=json.loads(line)
            assert (canonical(record)+"\n").encode("ascii")==line
            assert record["seq"]==seq
            checksum.update(line); size+=len(line); seq+=1
            tag,p=record["tag"],record["payload"]
            tags[tag]+=1
            mode,role,e,stage=record["mode"],record["role"],record["epoch"],record["stage"]
            if tag in ("RAW","ORIGINAL_SOURCE","SOURCE_TRUTH_ACTUAL","BOUND_BEFORE_ARMS","ORIGINAL_PAIR","NO_CREDIT_METADATA") and stage=="source":
                assert mode in MODES and role is None and e is None
                sources[mode].append(record)
            if tag=="CONTRACT":
                assert seq==1 and p["contract"]==c
                assert all(path in pins and pin==pins[path] for path,pin in p["loaded_before"].items())
            elif tag=="REFERENCE":
                assert p=={"digest":c["reference_input"]["q_digest"],"rows":13824}
            elif tag=="RAW":
                counts["rollout"]+=1; counts["step"]+=len(p["trace"]["steps"])
                assert p["actual_step_object_links"] is True and p["returned_steps"]==len(p["trace"]["steps"])
                if stage=="source":
                    factual_trap(p,c,rows)
                elif stage=="evaluation":
                    assert bank is not None and bank["key"]==(mode,role,e)
                    i=len(bank["traces"]); assert i<100
                    scene=bank["sample"][i]
                    assert p["kappa"]==scene[0] and p["tape"]=={"phase":scene[1],"error_flag":scene[2],"cause_rank":scene[3]}
                    assert p["trace"]["base_option"]==scene[4]
                    ret=reconstructed_rollout(p)
                    assert ret.hex()==p["return_hex"]
                    comp=bank["before"]
                    check_policy(p["trace"],storemap(comp["current"]),rows,mode,
                                 None if mode=="dq" else storemap(comp["learning_values"]))
                    bank["total"]+=ret
                    bank["traces"].append(p["trace"])
                    bank["hash"].update((canonical(p["trace"])+"\n").encode("ascii"))
                elif stage=="training":
                    assert train is not None and train["key"]==(mode,role,e) and raw_training is None
                    episode=declared_episode(e)
                    assert p["kappa"]==episode["kappa"] and p["tape"]==episode["tape"]
                    assert p["trace"]["base_option"]==episode["proposal"]
                    assert reconstructed_rollout(p).hex()==p["return_hex"]
                    raw_training=p
                else:
                    raise AssertionError(("unknown raw stage",stage))
            elif tag=="TX_CALL":
                assert tx is None and stage=="training" and train is not None
                tx=p; counts["transaction"]+=1
            elif tag=="TX_RETURN":
                assert tx is not None
                assert maps_equal(apply_edits(storemap(tx["before"]),tx["edits"],rows),storemap(p["after"]))
                assert p["returned_value"] is None and p["not_a_manufactured_receipt"] is True
                tx=None
            elif tag in ("ORIGINAL_SOURCE","SOURCE_TRUTH_ACTUAL","BOUND_BEFORE_ARMS","ORIGINAL_PAIR","NO_CREDIT_METADATA"):
                assert stage=="source"
            elif tag=="FUTURE_BEGIN":
                assert mode not in origins
                initial,plan,source,seal,origin=check_future_begin(p,sources[mode],c,mode,rows,healthy)
                origins[mode]={"initial":initial,"plan":plan,"source":source,"seal":seal,"origin":origin}
                for r,comp in zip(ROLES,initial):
                    states[(mode,r)]=deepcopy(comp)
            elif tag=="BANK_BEGIN":
                assert mode in origins and bank is None and train is None
                key=(mode,role,e)
                assert key not in banks and p["before"]==states[(mode,role)]
                assert e==states[(mode,role)]["completed_episodes"] and p["sample"]==origins[mode]["plan"]["sample"]
                n=sum(key[0]==mode for key in banks)
                assert (role,e)==(("reference",n) if n<4 else ("treatment",n-4))
                bank={"key":key,"before":p["before"],"sample":p["sample"],"traces":[],"total":0.0,"hash":hashlib.sha256()}
            elif tag=="BANK_END":
                assert bank is not None and bank["key"]==(mode,role,e)
                assert len(bank["traces"])==p["traces_count"]==p["captured_raw_count"]==100
                assert p["after"]==bank["before"]==states[(mode,role)]
                assert (bank["total"]/100).hex()==p["orderedmean_hex"]
                assert bank["hash"].hexdigest()==p["raw_sha256"]
                banks[(mode,role,e)]={"mean_hex":p["orderedmean_hex"],"raw_sha256":p["raw_sha256"],
                                    "projection":projected_bank(bank["traces"]),"traces":bank["traces"]}
                bank=None
            elif tag=="TRAIN_BEGIN":
                assert bank is None and train is None and (mode,role,e) in banks
                assert p["before"]==states[(mode,role)] and p["declared_episode"]==declared_episode(e)
                train={"key":(mode,role,e),"before":p["before"]}
            elif tag=="TRAIN_END":
                assert train is not None and train["key"]==(mode,role,e) and raw_training is not None
                initial=origins[mode]["initial"][ROLES.index(role)]
                updated,diagnostic=verify_receipt(p,rows,states[(mode,role)],initial,mode,role,e,raw_training)
                states[(mode,role)]=updated
                diagnostics.update(diagnostic)
                counts["training"]+=1
                train=raw_training=None
            elif tag=="CURVE_COMPLETE":
                role=p["role"]
                assert record["role"]==role and p["actual_role"]==role and (mode,role) not in complete
                assert p["origin_sha256"]==origins[mode]["seal"] and p["training_count"]==3 and p["t_max"]==3
                assert p["v_pre_hex"]==origins[mode]["plan"]["v_pre_hex"]
                assert p["contrast_status"]=="NO_SUBSTANTIVE_UPDATE_CONTRAST"
                assert p["collateral_status"]=="NOT_APPLICABLE_EMPTY_OWNER_SET" and p["collateral"] is None
                assert len(p["checkpoints"])==4
                for epoch,pin in enumerate(p["checkpoints"]):
                    assert pin["epoch"]==epoch and pin["count"]==100
                    observed=banks[(mode,role,epoch)]
                    assert pin["mean_hex"]==pin["actual_orderedmean_hex"]==observed["mean_hex"]
                    assert pin["raw_sha256"]==observed["raw_sha256"]
                check_final(p["full_after"],mode,states,origins)
                complete.add((mode,role))
            elif tag=="EXTERNAL":
                role=p["role"]
                assert record["role"]==role and (mode,role) in complete and (mode,role) not in external
                assert p["origin_sha256"]==origins[mode]["seal"]
                assert p["source_or_truth_or_cost_feature"] is False
                check_external_short(p["projection"],banks,mode,role,origins[mode]["plan"]["v_pre_hex"])
                external.add((mode,role))
            elif tag=="NO_EDIT_ROLE_EQUALITY":
                assert p["mode"]==mode and mode not in equality
                means=[banks[(mode,"reference",epoch)]["mean_hex"] for epoch in range(4)]
                assert p["ordered_means_hex"]==means
                for epoch in range(4):
                    assert banks[(mode,"reference",epoch)]["traces"]==banks[(mode,"treatment",epoch)]["traces"]
                    assert banks[(mode,"reference",epoch)]["mean_hex"]==banks[(mode,"treatment",epoch)]["mean_hex"]
                assert all(p[name] is True for name in ("actual_full_raw_equal","not_independent_samples","not_substantive_treatment_contrast"))
                equality[mode]=means
            elif tag=="GUARD_REJECTION":
                assert p["exception_type"]=="ProtocolError" and p["before_counts"]==p["after_counts"]
                assert type(p["message"]) is str and p["message"]
                guards.append(p["label"])
            elif tag=="GUARDS_RESTORED":
                assert p["source"]==origins[mode]["source"]
                assert p["audit"]["origin"]==origins[mode]["origin"]
                assert p["audit"]["origin_sha256"]==origins[mode]["seal"]
                assert p["audit"]["ordered_composites"]==[states[(mode,r)] for r in ROLES]
                restores.append(mode)
            elif tag=="SUMMARY":
                assert native_summary is None
                native_summary=p
            elif tag in ("TOPLEVEL_FAILURE","FORBIDDEN_CALL","NATIVE_BUDGET_EXCEEDED","INCOMPLETE_RAW","PENDING_STEP_RETURNS"):
                assert exit_record["child_exit_code"]!=0
                partial_records.append(record)
            elif tag=="GUARD_UNEXPECTED_ACCEPTANCE":
                assert exit_record["child_exit_code"]!=0
                partial_records.append(record)
            else:
                raise AssertionError(("unknown tag",tag))
    assert native_summary is not None and summary["records"]==seq and summary["raw_bytes"]==size
    assert summary["canonical_sha256"]==checksum.hexdigest()
    assert {k:v for k,v in summary.items() if k not in ("records","raw_bytes","canonical_sha256")}==native_summary
    native_counts=summary["counts"]
    actual_loaded=summary["loaded_sources"]
    assert all(path in pins and pin==pins[path] for path,pin in actual_loaded.items())
    required_sources={(HERE/"nocredit.py").relative_to(ROOT).as_posix(),
                      "experiments/v03r/a96_dense/b2_prepare/complete_curve_source_gates_v105/variants/normal/learning.py",
                      "experiments/v03r/a96_dense/b2_prepare/complete_curve_source_gates_v105/variants/normal/td.py",
                      "experiments/v03r/a96_dense/b2_prepare/readonly_bank_optimization_v107/bank.py"}
    assert required_sources<=set(actual_loaded)
    complete_native=exit_record["child_exit_code"]==0
    if complete_native:
        assert summary["tests_run"]==4 and summary["failures"]==summary["errors"]==summary["skipped"]==0
        assert len(banks)==16 and counts["training"]==12 and counts["rollout"]==1614 and len(complete)==len(external)==4
        assert native_counts["rollout"]==native_counts["rollout_return"]==counts["rollout"]
        assert native_counts["step"]==native_counts["step_return"]==counts["step"]
        assert native_counts["transaction"]==native_counts["transaction_return"]==counts["transaction"]
        assert native_counts["bank_started"]==native_counts["bank_completed"]==16
        assert native_counts["training_started"]==native_counts["training_completed"]==12
        assert not any(native_counts.get(name,0) for name in ("B1","law_plan","forbidden"))
        assert bank is train is tx is raw_training is None and not partial_records
        assert summary["pending_native_step_returns"]==0 and summary["fresh_original_sources"]==2
        assert summary["profile_was_installed"] is True and summary["profile_restored"] is True
        assert summary["original_function_identities_unchanged"] is True
        assert summary["B1_arm_calls"]==summary["therapy_transactions"]==summary["owner_receipts"]==0
        assert not summary["partial_native_gate_claimed"] and not summary["automatic_retry"]
        assert summary["collateral_status"]=="NOT_APPLICABLE_EMPTY_OWNER_SET" and summary["collateral"] is None
        assert summary["contrast_status"]=="NO_SUBSTANTIVE_UPDATE_CONTRAST"
        assert not summary["scientific_qualification"] and not summary["formal_collection_enabled"]
        expected_labels={"closed_nominal_OwnedNoCreditFuture","closed_nominal_RoleCurve","closed_nominal_ExternalCurveView"}
        for mode in MODES:
            expected_labels|={prefix+mode for prefix in ("wrong_source_mode_","foreign_actual_source_","prepared_once_",
                              "original_metadata_once_","live_role_value_alias_","source_mode_tamper_",
                              "complete_future_once_","external_rejects_origin_")}
        assert set(guards)==expected_labels and len(guards)==len(expected_labels)==19
        assert restores==list(MODES) and set(equality)==set(MODES)
    return {"complete_native_branch":complete_native,"records":seq,"raw_bytes":size,
            "canonical_sha256":checksum.hexdigest(),"tag_inventory":dict(tags),
            "actual_raw_counts":dict(counts),"native_call_return_counts":native_counts,
            "actual_loaded_source_pins":len(actual_loaded),"whole_truth_units_per_source":["Unknown/NoWrite"],
            "cell_owner_count":0,"residual_units_per_source":["Unknown/NoWrite"],
            "B1_calls":0,"owner_receipts":0,"therapy_transactions":0,
            "no_edit_role_equality":equality,"complete_checkpoint_banks":len(banks),
            "complete_role_handles":len(complete),"closed_external_projections":len(external),
            "TD_and_policy_diagnostics":dict(diagnostics),"guard_rejections":guards,
            "partial_records":partial_records,"runtime_identity_reconstructed":False,
            "ordinary_mask_empty_verified_only_for_future_not_factual":True,
            "factual_TRAP_at_pre_action_step_zero_verified":True,
            "collateral_status":"NOT_APPLICABLE_EMPTY_OWNER_SET","collateral":None,
            "not_substantive_feedback_treatment_contrast":True,"not_independent_role_samples":True,
            "scientific_qualification":False,"old_checker_RFL_execution":False}


def main():
    started=datetime.now(timezone.utc).isoformat()
    c=json.loads((HERE/"contract.json").read_bytes())
    folder=HERE/"evidence"
    claim=json.loads((folder/"claim.json").read_bytes())
    exit_record=json.loads((folder/"exit.json").read_bytes())
    assert claim["parent_commit"]==c["parent_commit"]
    assert claim["input_binding_before"]==exit_record["input_binding_after"] and exit_record["input_bytes_unchanged"]
    assert claim["automatic_retry"] is False and exit_record["automatic_retry"] is False
    assert claim["fresh_keys_allocated"]==0 and claim["formal_collection_enabled"] is False
    pins=claim["input_binding_before"]
    for path,pin in pins.items():
        assert meta(ROOT/path)==pin,path
    for name in ("stdout","stderr"):
        assert meta(folder/(name+".log"))==exit_record[name]
    for name in ("raw.jsonl","child_summary.json"):
        assert meta(folder/name)==exit_record[name]
    rows=read_reference(c["reference_input"])
    spec=c["healthy_reference"]
    assert meta(ROOT/spec["path"])["sha256"]==spec["sha256"]
    healthy=json.loads((ROOT/spec["path"]).read_bytes())
    assert healthy["N_eval"]==100 and healthy["training_episodes"]==0
    assert healthy["q_reference_sha256"]==c["reference_input"]["q_digest"]
    lock=json.loads((ROOT/c["dev_lock"]["path"]).read_bytes())
    assert meta(ROOT/c["dev_lock"]["path"])["sha256"]==c["dev_lock"]["sha256"]==healthy["lock_sha256"]
    assert lock["design"]["T"]==465 and lock["design"]["grid"]==list(range(466)) and lock["design"]["N_eval"]==100
    helpers=copied_helpers_review()
    review=source_review(c)
    evidence=audit_records(c,rows,pins,healthy,exit_record)
    out={"schema":"V110_INDEPENDENT_STDLIB_GENUINE_T_NO_CREDIT_FUTURE_STORED_AUDIT",
         "started_at_utc":started,"completed_at_utc":datetime.now(timezone.utc).isoformat(),
         "input_binding_pins":len(pins),"copied_helpers_source_review":helpers,
         "constructor_external_and_kernel_source_review":review,"evidence":evidence,
         "native_receipt_preserved":{key:val for key,val in exit_record.items() if key!="input_binding_after"},
         "old_checker_RFL_execution":False,"runtime_identity_reconstructed":False,
         "scientific_qualification":False,"positive_benefit_required":False,
         "complete_original_confirmatory_study":False,"audit_source":meta(Path(__file__))}
    with (HERE/"stored_audit_result.json").open("x",encoding="utf-8",newline="\n") as stream:
        stream.write(canonical(out)+"\n")
    print(canonical(out))


if __name__=="__main__":
    main()

