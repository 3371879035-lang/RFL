"""Stored-data review and paired report; does not import learner or world code."""
import gzip
import hashlib
import json
from pathlib import Path
import struct
import time
import traceback
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DIR=np.array([(1,0),(1,-1),(0,-1),(-1,-1),(-1,0),(-1,1),(0,1),(1,1)])


def read_binary(path):
    with gzip.open(path,'rb') as f:
        n,=struct.unpack('<I',f.read(4)); header=json.loads(f.read(n)); payload=f.read()
    dtype=np.dtype([(x[0],x[1],tuple(x[2])) if len(x)==3 else tuple(x) for x in header['dtype']])
    return header,np.frombuffer(payload,dtype),hashlib.sha256(payload).hexdigest()


def rows(path):
    with gzip.open(path,'rt',encoding='utf-8') as f: return [json.loads(x) for x in f]


def empty_state(episode):
    return dict(episode=episode,anchor=None,failed=0,streak=0,evidence={},steps=0,pickups=0,
                stationary=0,long_stall=0,corrections=0,memory_corrections=0,moved_after_correction=0)


def review_case(directory, maps):
    r=json.loads((directory/'result.json').read_text())
    assert r['status']=='COMPLETE' and r['additional_training_steps']==16384
    header,raw,h=read_binary(directory/'steps.bin.gz')
    assert h==r['raw_payload_sha256'] and len(raw)==r['raw_records']
    assert (header['seed'],header['arm'],header['variant'])==(r['seed'],r['arm'],r['variant'])
    train=raw['kind']==0; evaluation=raw['kind']==1
    assert train.sum()==16384 and np.all(train|evaluation)
    assert (raw['action']<16).all() and ((raw['action']<8)|(raw['cooldown']==0)).all()
    assert np.isfinite(raw['scores']).all()
    if r['arm']=='F0':
        assert np.isnan(raw['reward']).all() and not r['q_present']
    else:
        expected=(.015+raw['pickup'][train].astype(float)-int(r['arm'] in ('RL-RP','F-RP'))*raw['captured'][train]).astype(np.float32)
        assert np.array_equal(expected,raw['reward'][train]) and r['q_present']
        assert np.isnan(raw['reward'][evaluation]).all()
    assert r['counters']['Q_updates']==(0 if r['arm']=='F0' else 128)
    assert r['counters']['fact_updates']==(0 if r['arm']=='RL-RP' else 128)
    assert r['counters'].get('measurement_updates',0)==(128 if r['arm']=='F0' else 0)
    assert r['counters']['reward_packets']==(0 if r['arm']=='F0' else 16384)
    # Bind every memory key to the visible 3x3 road patch, independently of learner code.
    contexts=np.zeros(len(raw),np.uint16)
    for mid,roads in maps.items():
        ids=np.flatnonzero(raw['map']==mid)
        x,z=raw['before_hero'][ids].astype(int).T
        for bit,(dz,dx) in enumerate(( (dz,dx) for dz in (-1,0,1) for dx in (-1,0,1) )):
            contexts[ids] |= roads[z+dz,x+dx].astype(np.uint16)<<bit
    contexts |= (raw['buff']>0).astype(np.uint16)<<9
    assert np.array_equal(contexts,raw['context'])
    caught=((raw['monsters'][:,:,0]>=0)&(np.abs(raw['monsters'].astype(int)-raw['hero'][:,None,:]).max(-1)<=1)).any(-1)
    assert np.array_equal(caught,raw['captured'].astype(bool))
    assert np.array_equal((raw['step']==256)&~caught,raw['completed'].astype(bool))
    counts={};rules={}; complete=failures=0; tr=None; ev=None
    event_rows=rows(directory/'consolidation.jsonl.gz'); event_i=0
    declared_episodes=rows(directory/'episodes.jsonl.gz')
    expected_episodes={('training' if e['kind']=='training' else e['checkpoint'],e['episode']):e for e in declared_episodes}
    checked_episodes=0; first_moves=0; correction_moves=0
    for a in raw:
        training=a['kind']==0; ep=int(a['episode']); cp=int(a['checkpoint']); key=int(a['context'])
        if training:
            if tr is None or tr['episode']!=ep: tr=empty_state(ep)
            s=tr
        else:
            if ev is None or ev['episode']!=ep or ev['cp']!=cp: ev=empty_state(ep); ev['cp']=cp
            s=ev
        hero=tuple(map(int,a['before_hero'])); nxt=tuple(map(int,a['hero']))
        assert int(a['step'])==s['steps']+1
        if s['steps']: assert hero==s['last_hero']
        anchor=(hero,key)
        local=s['failed'] if s['anchor']==anchor and s['streak']>=2 else 0
        remembered=rules.get(key,0)
        for action,flags in s['evidence'].get(key,{}).items():
            if flags&1: remembered &= ~(1<<action)
        assert (local,remembered,s['streak'])==(int(a['local_mask']),int(a['memory_mask']),int(a['streak_before']))
        blocked=0 if r['variant']=='base' else local
        if r['variant']=='wake_sleep': blocked |= remembered
        proposed=int(a['proposed']); action=proposed; reason=0
        legal=list(range(16 if a['cooldown']==0 else 8))
        if not a['explore'] and proposed<8 and blocked&(1<<proposed):
            candidates=[k for k in legal if not blocked&(1<<k)]
            if candidates:
                action=max(candidates,key=lambda k:float(a['scores'][k]))
                reason=2 if r['variant']=='wake_sleep' and remembered&(1<<proposed) else 1
        assert (action,reason)==(int(a['action']),int(a['reason']))
        if not a['explore']: assert proposed==int(np.argmax(a['scores']))
        if not training: assert not a['explore']
        assert bool(a['training_q_control'])==bool(training and r['arm'] in ('F-RP','F-R'))
        moved=hero!=nxt
        # Independent movement calculation from stored action and visible geometry.
        roads=maps[int(a['map'])]; x,z=hero; dx,dz=map(int,DIR[action%8]); xx,zz=x,z
        if action<8:
            for _ in range(2 if a['buff'] else 1):
                nx,nz=xx+dx,zz+dz
                if not (0<=nx<64 and 0<=nz<64 and roads[nz,nx]): break
                if dx and dz and not (roads[zz,nx] or roads[nz,xx]): break
                xx,zz=nx,nz
        else:
            for k in range(8 if dx and dz else 10,0,-1):
                nx,nz=x+k*dx,z+k*dz
                if 0<=nx<64 and 0<=nz<64 and roads[nz,nx]: xx,zz=nx,nz; break
        assert nxt==(xx,zz)
        if s['anchor']!=anchor: s['anchor']=anchor; s['failed']=0
        if action<8:
            evidence=s['evidence'].setdefault(key,{})
            evidence[action]=evidence.get(action,0)|(1 if moved else 2)
            if not moved: s['failed'] |= 1<<action
        s['streak']=0 if moved else s['streak']+1
        if moved: s['anchor']=None; s['failed']=0
        s['steps']+=1; s['pickups']+=int(a['pickup']); s['last_hero']=nxt
        s['stationary']+=int(not moved);s['long_stall']+=int(s['streak']>=8)
        s['corrections']+=int(reason!=0);s['memory_corrections']+=int(reason==2)
        s['moved_after_correction']+=int(bool(reason) and moved)
        first_moves+=int(bool(reason) and int(a['streak_before'])<2)
        correction_moves+=int(bool(reason) and moved)
        assert float(a['score'])==1.5*s['steps']+100*s['pickups']
        if a['captured'] or a['completed']:
            checked_episodes+=1
            e=expected_episodes[('training' if training else cp,ep)]
            assert e['steps']==s['steps'] and e['treasures']==s['pickups'] and e['score']==float(a['score'])
            if not training:
                for k in ('stationary','long_stall','corrections','memory_corrections','moved_after_correction'): assert e[k]==s[k]
            if training:
                changes=[]
                for context,evidence in sorted(s['evidence'].items()):
                    table=counts.setdefault(context,[[0,0] for _ in range(8)]); old=rules.get(context,0)
                    for act,flags in evidence.items():
                        table[act][0]+=int(bool(flags&1));table[act][1]+=int(bool(flags&2))
                        if flags&1: rules[context]=rules.get(context,0)&~(1<<act)
                    if a['captured']:
                        any_alternative=any(m>=2 for m,st in table)
                        rules[context]=sum(1<<act for act,(m,st) in enumerate(table) if any_alternative and st>=2 and m==0)
                    changes.append(dict(context=context,evidence=[list(p) for p in sorted(evidence.items())],before=old,after=rules.get(context,0)))
                complete+=1;failures+=int(a['captured'])
                event=event_rows[event_i];event_i+=1
                assert event['episode']==ep and event['completed']==complete and event['captured']==bool(a['captured']) and event['changes']==changes
    assert checked_episodes==len(declared_episodes) and event_i==len(event_rows)==complete==r['training_episodes_completed']
    final=json.loads((directory/'memory_final.json').read_text())
    assert final==dict(counts={str(k):v for k,v in counts.items()},rules={str(k):v for k,v in rules.items()},completed=complete,failures=failures)
    payload=json.dumps(dict(counts=counts,rules=rules,completed=complete,failures=failures),sort_keys=True,separators=(',', ':')).encode()
    assert hashlib.sha256(payload).hexdigest()==r['memory']['sha256']
    for b in r['evaluations']:
        es=[e for e in declared_episodes if e['kind']=='evaluation' and e['checkpoint']==b['checkpoint']]
        assert len(es)==b['episodes'] and sum(e['steps'] for e in es)==b['steps']
        assert np.mean([e['score'] for e in es])==b['mean_score']
        for out,field in [('stationary_rate','stationary'),('long_stall_rate','long_stall')]: assert sum(e[field] for e in es)/b['steps']==b[out]
        for k in ('corrections','memory_corrections','moved_after_correction'): assert sum(e[k] for e in es)==b[k]
        assert b['parameters_persistent_memory_replay_frozen']
    _,labels,lh=read_binary(directory/'labels.bin.gz')
    assert lh==r['label_payload_sha256'] and len(labels)==r['labels']
    if r['arm']=='F0':
        t=raw[train];start=np.r_[True,t['episode'][1:]!=t['episode'][:-1]]
        starts=np.maximum.accumulate(np.where(start,np.arange(len(t)),0))
        ends=np.r_[np.flatnonzero(start)[1:]-1,len(t)-1]
        end_by_row=np.repeat(ends,np.diff(np.r_[np.flatnonzero(start),len(t)]))
        cumulative=np.r_[0,np.cumsum(t['pickup'])]
        u=labels['uid']-131072;end=labels['observed_at']-131072;hz=np.array([1,4,16,64])[labels['horizon']]
        assert np.all((0<=u)&(u<len(t))) and np.all((u<=end)&(end<=end_by_row[u]))
        assert np.array_equal(end,np.minimum(u+hz-1,end_by_row[u]))
        assert np.all((end-u+1==hz)|(t['captured'][end]|t['completed'][end]))
        assert np.array_equal(labels['steps'],end-u+1)
        assert np.array_equal(labels['pickups'],cumulative[end+1]-cumulative[u])
        assert np.array_equal(labels['target_steps'],((end-u+1)/hz).astype(np.float32))
        assert np.array_equal(labels['target_pickups'],labels['pickups'].astype(np.float32))
        assert len(np.unique(labels[['uid','horizon']]))==len(labels)
        expected=0
        for horizon in (1,4,16,64):
            expected+=int(np.sum((np.arange(len(t))+horizon-1<=end_by_row)|t['captured'][end_by_row].astype(bool)|t['completed'][end_by_row].astype(bool)))
        assert expected==len(labels)
    else: assert not len(labels)
    return dict(seed=r['seed'],arm=r['arm'],variant=r['variant'],records=len(raw),labels=len(labels),
        completed_episodes=checked_episodes,consolidations=complete,corrections_before_two_stalls=first_moves,
        moved_after_correction=correction_moves)


def main():
    start=time.perf_counter();output=HERE/'analysis';output.mkdir(exist_ok=False)
    error=None;checked=[]
    try:
        summary=json.loads((HERE/'evidence_pilot/result.json').read_text());assert summary['exit']['exit_code']==0
        claim=json.loads((HERE/'evidence_pilot/claim.json').read_text())
        for pin in claim['inputs']:
            p=ROOT/pin['path'];assert p.stat().st_size==pin['bytes'] and hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==pin['sha256']
        maps={mid:np.load(HERE.parent/f'spatial_feedback_v178/evidence_prepare/maps/{mid}.npz')['roads'] for mid in range(90101,90113)}
        results=summary['cases'];assert len(results)==32
        for r in sorted(results,key=lambda r:(r['seed'],r['arm'],r['variant'])):
            d=HERE/'evidence_pilot'/f"seed{r['seed']}"/r['arm']/r['variant']
            checked.append(review_case(d,maps))
        cells=[]
        for arm in ('RL-RP','F0','F-RP','F-R'):
            variants=('base',) if arm=='RL-RP' else ('base','wake','wake_sleep') if arm=='F0' else ('base','wake_sleep')
            for variant in variants:
                rs=sorted([r for r in results if r['arm']==arm and r['variant']==variant],key=lambda r:r['seed'])
                per_seed_curves=[]
                for r in rs:
                    d=HERE/'evidence_pilot'/f"seed{r['seed']}"/arm/variant
                    es=rows(d/'episodes.jsonl.gz')
                    per_seed_curves.append([float(np.mean([e['score'] for e in es if e['kind']=='evaluation' and e['checkpoint']==cp and e['episode']<384])) for cp in (0,8192,16384)])
                curve=np.mean(per_seed_curves,axis=0).tolist()
                cells.append(dict(arm=arm,variant=variant,seeds=[r['seed'] for r in rs],score_curve=curve,
                    per_seed_score_curves=per_seed_curves,per_seed_final=[c[-1] for c in per_seed_curves],
                    mean_final256=float(np.mean([r['evaluations'][-1]['mean_score'] for r in rs])),
                    per_seed_final256=[r['evaluations'][-1]['mean_score'] for r in rs],
                    stationary_rate=float(np.mean([r['evaluations'][-1]['stationary_rate'] for r in rs])),
                    long_stall_rate=float(np.mean([r['evaluations'][-1]['long_stall_rate'] for r in rs])),
                    corrections=sum(r['evaluations'][-1]['corrections'] for r in rs),
                    memory_corrections=sum(r['evaluations'][-1]['memory_corrections'] for r in rs),
                    moved_after_correction=sum(r['evaluations'][-1]['moved_after_correction'] for r in rs),
                    cpu_seconds=sum(r['cpu_seconds'] for r in rs),memory_bytes=[r['memory']['bytes'] for r in rs],
                    mean_curve_score=(curve[0]+2*curve[1]+curve[2])/4))
        comparisons=[]
        for arm in ('F0','F-RP','F-R'):
            variants=('wake','wake_sleep') if arm=='F0' else ('wake_sleep',)
            for variant in variants:
                a=next(c for c in cells if c['arm']==arm and c['variant']==variant)
                b=next(c for c in cells if c['arm']==arm and c['variant']=='base')
                diffs=[x-y for x,y in zip(a['per_seed_final'],b['per_seed_final'])]
                comparisons.append(dict(arm=arm,variant=variant,reference='base',per_seed_final_difference=diffs,
                    final_difference=float(np.mean(diffs)),positive_seeds=sum(d>0 for d in diffs),
                    initial_difference=a['score_curve'][0]-b['score_curve'][0],
                    mean_curve_difference=a['mean_curve_score']-b['mean_curve_score']))
        a=next(c for c in cells if c['arm']=='F0' and c['variant']=='wake_sleep')
        b=next(c for c in cells if c['arm']=='F0' and c['variant']=='wake')
        assert a['score_curve'][0]==b['score_curve'][0]
        comparisons.append(dict(arm='F0',variant='wake_sleep',reference='wake',
            per_seed_final_difference=[x-y for x,y in zip(a['per_seed_final'],b['per_seed_final'])],
            final_difference=a['score_curve'][-1]-b['score_curve'][-1],
            mean_curve_difference=a['mean_curve_score']-b['mean_curve_score']))
        for seed in (93001,93002,93003,93004):
            for arm in ('F0','F-RP','F-R'):
                assert len({r['initial_parameter_hash'] for r in results if r['seed']==seed and r['arm']==arm})==1
        data=dict(cells=cells,comparisons=comparisons,scope='Four known training-seed continuation development comparison, not a new independent confirmation.',
            native=summary['exit'],total_additional_training_steps=sum(r['additional_training_steps'] for r in results),
            total_raw_steps=sum(r['raw_records'] for r in results),total_evaluation_episodes=sum(b['episodes'] for r in results for b in r['evaluations']),
            total_ordinary_optimizer_updates=sum(max(r['counters']['Q_updates'],r['counters']['fact_updates']) for r in results))
        with (output/'result.json').open('x',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
        lines=['# V189：局内纠偏与局后条件经验复用','', '|组|版本|追加0步|8192步|16384步|未移动率|连续静止≥8占比|','|---|---|---:|---:|---:|---:|---:|']
        for c in cells:
            lines.append(f"|{c['arm']}|{c['variant']}|{c['score_curve'][0]:.6f}|{c['score_curve'][1]:.6f}|{c['score_curve'][2]:.6f}|{c['stationary_rate']:.4%}|{c['long_stall_rate']:.4%}|")
        lines+=['','本轮为已有检查点上的有限续训，不是从零新训。主表曲线均取相同128回合；行为比例及另列JSON末点指标用完整256回合。',
            '追加0步的差异属于即时控制规则效果，不能计成新训练收益。外部记忆巩固不是Sleep参数蒸馏，亦不是完整因果归因。',
            '所有主组正常学习，奖励不变；失败触发局后规则构建，成功仅普通事实积累/反例修正。评估持久状态冻结。']
        (output/'result.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    except BaseException: error=traceback.format_exc()
    audit=dict(exit_code=int(error is not None),error=error,wall_seconds=time.perf_counter()-start,cases=len(checked),
        checked=checked,scope='Stored movement/chronology/decision and memory reconstruction, labels, totals and input pins; no neural numerical replay or native rerun.')
    with (HERE/'stored_review.json').open('x',encoding='utf-8') as f: json.dump(audit,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in audit.items() if k!='checked'}))
    return audit['exit_code']


if __name__=='__main__': raise SystemExit(main())
