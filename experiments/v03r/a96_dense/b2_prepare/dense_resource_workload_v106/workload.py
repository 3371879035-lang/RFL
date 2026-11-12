"""Full declared engineering T465/N100 workload on unchanged owned v105 entry."""
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(HERE.parent/'owned_adaptive_handoff_v92'), str(HERE.parent/'adaptive_training_v90'),
               str(HERE.parent), str(ROOT/'src')]
import adaptive_training as A
import handoff as H
import oracle_mainline_v75 as O
import resource_meter as RM
from rfl_rebuild.b2 import training as T
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState, QAddress, DecisionAddress, Edit, Q, DECISION, PROCESS, CONTROLLER

CONTRACT = json.loads((HERE/'contract.json').read_bytes())
MODE = sys.argv[1]
assert MODE in ('dq', 'patch-adaptive')
OUT = HERE/'evidence'/MODE
COUNTS = Counter()
START = time.monotonic()
SCOPE = {'stage':'source', 'role':None, 'epoch':None}
BANK = None
BANK_OBJECTS, BANK_DIGESTS = {}, {}
PENDING = []
PEAK = {'working_set_bytes':0, 'peak_working_set_bytes':0, 'private_bytes':0, 'peak_commit_bytes':0,
        'minimum_available_physical_bytes': 1 << 64}


def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(',', ':'),ensure_ascii=True)


class Capture:
    def __init__(self, path):
        self.file = path.open('xb')
        self.z = gzip.GzipFile(filename='',fileobj=self.file,mode='wb',compresslevel=1,mtime=0)
        self.records = self.raw_bytes = 0
        self.encode_seconds = self.write_seconds = 0.0
        self.canonical_sha = hashlib.sha256()

    def emit(self, tag, data, *, force=False):
        t = time.monotonic()
        payload = A.wire(data)
        record = dict(seq=self.records,mode=MODE,tag=tag,payload=payload,**SCOPE)
        line = (canonical(record)+'\n').encode('ascii')
        self.encode_seconds += time.monotonic()-t
        t = time.monotonic()
        self.z.write(line)
        self.write_seconds += time.monotonic()-t
        self.canonical_sha.update(line)
        self.raw_bytes += len(line); self.records += 1
        if not force and (self.raw_bytes > CONTRACT['budget']['uncompressed_bytes_per_child'] or
                          self.file.tell() > CONTRACT['budget']['compressed_bytes_per_child']):
            raise RuntimeError('prospective capture extent budget exhausted')
        return payload

    def close(self):
        self.z.close(); self.file.close()


LOG = None


def resource(label, *, check=True):
    now = RM.sample()
    for name in ('working_set_bytes','peak_working_set_bytes','private_bytes','peak_commit_bytes'):
        PEAK[name] = max(PEAK[name], now[name])
    PEAK['minimum_available_physical_bytes'] = min(PEAK['minimum_available_physical_bytes'], now['available_physical_bytes'])
    now.update(label=label, wall_seconds=time.monotonic()-START, raw_bytes=LOG.raw_bytes,
               compressed_bytes=LOG.file.tell(), counts=dict(COUNTS))
    LOG.emit('RESOURCE', now, force=not check)
    if check:
        assert now['working_set_bytes'] <= CONTRACT['budget']['working_set_bytes_per_child'], 'working-set cap'
        assert now['peak_working_set_bytes'] <= CONTRACT['budget']['working_set_bytes_per_child'], 'peak working-set cap'
        assert now['private_bytes'] <= CONTRACT['budget']['private_bytes_per_child'], 'private-commit cap'
        assert now['peak_commit_bytes'] <= CONTRACT['budget']['private_bytes_per_child'], 'peak private-commit cap'
        assert now['available_physical_bytes'] >= CONTRACT['budget']['minimum_available_physical_bytes'], 'host RAM reserve'
        assert now['wall_seconds'] <= CONTRACT['budget']['seconds_per_child'], 'wall-time cap'
    return now


def handler(frame,event,arg):
    global SCOPE, BANK, PENDING
    p,n = frame.f_code.co_filename.replace('\\','/'),frame.f_code.co_name
    kernel = p.endswith('rfl_rebuild/env/kernel.py')
    store = p.endswith('rfl_rebuild/learner/store.py')
    native = p.endswith('rfl_rebuild/b1/runner.py') and n in ('run_patch_law','run_dq_law')
    learn = p.endswith('complete_curve_source_gates_v105/variants/normal/learning.py')
    curve = p.endswith('complete_curve_source_gates_v105/variants/normal/owned_curve.py')
    if event == 'call':
        counter = n if kernel and n in ('step','rollout') else 'transaction' if store and n=='apply_transaction' else 'B1' if native else None
        if counter:
            COUNTS[counter] += 1
            assert COUNTS[counter] <= CONTRACT['budget'][counter+'_per_child'], 'native budget '+counter
        if (p.endswith('rfl_rebuild/b2/training.py') and n in ('derive','key','mix','train_curve','pre_level')) or (kernel and n=='sample') or (p.endswith('rfl_rebuild/solve/dp.py') and n=='solve_reference') or (p.endswith('random.py') and n in ('__init__','random','randrange')) or frame.f_code.co_qualname in ('FutureTrainingProtocol.__init__','Curve.__init__'):
            COUNTS['forbidden'] += 1
            raise RuntimeError('ungranted formal/key/RNG/DP path: '+n)
        if curve and n=='_evaluate_bank':
            actor=frame.f_locals['actor']
            SCOPE={'stage':'evaluation','role':actor.role,'epoch':actor._completed}
            BANK={'hash':hashlib.sha256(),'traces':[]}
            LOG.emit('BANK_BEGIN', {'before':actor.payload(),'sample':[list(s.key) for s in frame.f_locals['sample']]})
        elif learn and n=='train_episode':
            actor=frame.f_locals['self']; episode=frame.f_locals['episode']
            SCOPE={'stage':'training','role':actor.role,'epoch':episode.epoch}
            LOG.emit('TRAIN_BEGIN',{'before':actor.payload(),'declared_episode':episode._input})
        elif store and n=='apply_transaction':
            LOG.emit('TX_CALL',{'before':A.stores(frame.f_locals['self']),'edits':frame.f_locals['edits']})
    elif event=='return':
        if kernel and n=='step' and type(arg) is K.StepResult:
            COUNTS['step_return'] += 1
            PENDING.append(arg)
        elif kernel and n=='rollout':
            if type(arg) is K.RolloutTrace:
                assert len(PENDING)==len(arg.steps) and all(x is y for x,y in zip(PENDING,arg.steps)), 'actual step/rollout identity'
                record=LOG.emit('RAW_ROLLOUT', {'trace':arg,'kappa':frame.f_locals['kappa'],'tape':frame.f_locals['tape']})
                COUNTS['rollout_return'] += 1
                if BANK is not None and SCOPE['stage']=='evaluation':
                    BANK['hash'].update((canonical(record['trace'])+'\n').encode('ascii'))
                    BANK['traces'].append(arg)
                PENDING=[]
            else:
                LOG.emit('INCOMPLETE_ROLLOUT',{'returned':arg,'actual_completed_steps':PENDING},force=True)
                PENDING=[]
        elif store and n=='apply_transaction':
            LOG.emit('TX_RETURN',{'after':A.stores(frame.f_locals['self'])})
        elif native and type(arg) is O.base.native_b1.B1Result:
            LOG.emit('NATIVE_B1_RETURN',{'law':frame.f_locals['law'].name,'full_post':A.stores(arg.post_state),
                                       'ledger_canonical':arg.ledger.canonical(),'receipts':arg.ledger.receipts})
        elif curve and n=='_evaluate_bank' and type(arg) is tuple:
            actor=frame.f_locals['actor']
            assert len(BANK['traces'])==len(arg[0]) and all(x is y for x,y in zip(BANK['traces'],arg[0]))
            key=(actor.role,actor._completed)
            assert key not in BANK_OBJECTS
            BANK_OBJECTS[key]=arg[0]; BANK_DIGESTS[key]=BANK['hash'].hexdigest()
            LOG.emit('BANK_END',{'count':len(arg[0]),'mean_hex':arg[1].hex(),'ordered_raw_sha256':BANK_DIGESTS[key],
                                'after':actor.payload()})
            BANK=None
            now=resource('checkpoint')
            if actor._completed % 50==0 or actor._completed==465:
                print(canonical({'tag':'PROGRESS','mode':MODE,'role':actor.role,'checkpoint':actor._completed,
                                 'mean_hex':arg[1].hex(),'resource':now}),flush=True)
        elif learn and n=='train_episode' and isinstance(arg,dict):
            LOG.emit('CORE_EPISODE',arg)


def interesting(code):
    p,n,q=code.co_filename.replace('\\','/'),code.co_name,code.co_qualname
    return ((p.endswith('rfl_rebuild/env/kernel.py') and n in ('step','rollout','sample')) or
            (p.endswith('rfl_rebuild/learner/store.py') and n=='apply_transaction') or
            (p.endswith('rfl_rebuild/b1/runner.py') and n in ('run_patch_law','run_dq_law')) or
            (p.endswith('rfl_rebuild/b2/training.py') and n in ('derive','key','mix','train_curve','pre_level')) or
            (p.endswith('rfl_rebuild/solve/dp.py') and n=='solve_reference') or
            (p.endswith('random.py') and n in ('__init__','random','randrange')) or
            q in ('FutureTrainingProtocol.__init__','Curve.__init__') or
            (p.endswith('complete_curve_source_gates_v105/variants/normal/learning.py') and n=='train_episode') or
            (p.endswith('complete_curve_source_gates_v105/variants/normal/owned_curve.py') and n=='_evaluate_bank'))


DISPATCH={}


def observe(frame,event,arg):
    key=id(frame.f_code)
    item=DISPATCH.get(key)
    if item is None:
        item=(frame.f_code,interesting(frame.f_code)); DISPATCH[key]=item
    if item[1]: handler(frame,event,arg)


def load_modules():
    modules=[]
    folder=HERE.parent/'complete_curve_source_gates_v105/variants/normal'
    for name,file in (('td','td.py'),('learning','learning.py'),('curve','owned_curve.py'),('external','external.py')):
        fullname='v105_normal_'+name
        spec=importlib.util.spec_from_file_location(fullname,folder/file)
        mod=importlib.util.module_from_spec(spec); sys.modules[fullname]=mod; spec.loader.exec_module(mod)
        modules.append(mod)
    return modules


def read_reference():
    spec=CONTRACT['reference_input']; raw=(ROOT/spec['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==spec['sha256']
    rows={}
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('DECISION_CONTEXT='):
            d=json.loads(line.split('=',1)[1]); x,y,t,k,phi,z,m=d['context']
            rows[K.State(x,y,t,k,phi),z,m]={a:float.fromhex(v) for a,v in d['q_row_hex']}
    reference=QReferenceView(rows,name='v106-fixed-original-reference')
    assert reference.digest()==spec['q_digest']
    LOG.emit('REFERENCE',{'digest':reference.digest(),'rows':len(reference)})
    return reference


def make_source(reference):
    contexts=[DecisionAddress(K.State(*K.START,t,0,2),1,m) for t in range(12) for m in (0,1)]
    contexts += [DecisionAddress(K.State(1,2,1,0,2),1,m) for m in (0,1)]
    sentinel=DecisionAddress(K.State(*K.START,0,1,2),1,0); contexts.append(sentinel)
    sites=((K.ControllerSite(K.State(*K.START,0,0,2),K.WAIT),K.RIGHT),
           (K.ControllerSite(K.State(1,2,1,0,2),K.WAIT),K.LEFT),
           (K.ControllerSite(sentinel.state,K.WAIT),K.RIGHT))
    legal=[]
    for site,target in sites:
        service=[(z,m,tuple(reference.row(site.state,z,m))) for z in K.option_ids() for m in (0,1)
                 if site.cmd in reference.row(site.state,z,m)]
        assert service and all(target in row for z,m,row in service)
        legal.append({'site':site,'target':target,'all_serving_contexts':service})
    edits=[Edit(PROCESS,0,1),Edit(PROCESS,3,2)]+[Edit(CONTROLLER,site,target) for site,target in sites]
    for a in contexts:
        row=reference.row(a.state,a.z,a.m); assert K.WAIT in row
        edits.append(Edit(Q,QAddress(a.state,a.z,a.m,K.WAIT),max(row.values())+1.0)
                     if MODE=='dq' else Edit(DECISION,a,K.WAIT))
    assert len(edits)==32
    LOG.emit('SOURCE_INSTALL_PLANNED',{'mode':MODE,'edits':edits,'legality':legal})
    pre=LearnerPersistentState(); pre.apply_transaction(tuple(edits),q_reference=reference)
    healthy_spec=CONTRACT['healthy_reference']; assert type(healthy_spec['path']) is str
    healthy=json.loads((ROOT/healthy_spec['path']).read_bytes())
    source=O.capture_source(pre,scene=EvaluationScene(*CONTRACT['source_scene']),regime='P',
                            q_reference=reference,healthy_reference=healthy,counterfactual=False)
    LOG.emit('ORIGINAL_SOURCE',{'mode':MODE,'audit':O.source_audit(source)})
    bound=H.bind_source(source,mode=MODE); LOG.emit('BOUND_BEFORE_ARMS',H.source_audit(bound))
    pair=H.run_whole_pair(bound,architecture='D_Q' if MODE=='dq' else 'D_patch',tier=Tier.L0_FACTUAL,
                          law_name='FactualReturnWrite' if MODE=='dq' else 'DeleteFactualPatch')
    LOG.emit('ORIGINAL_PAIR',O.pair_audit(pair,source))
    return source,bound,pair


def make_episodes(L):
    result=[]
    for e in range(CONTRACT['t_max']):
        k=e%2; proposal=(e//2)%4; phase=(e//8)%6; flag=(e//48)%2; rank=(e//96)%60
        coins=tuple(0 if (e+i)%10==0 else T.M64 for i in range(12))
        draws=tuple((T.M64,e*12+i) for i in range(12))
        result.append(L.EngineeringEpisode(e,k,proposal,K.SemanticTape(phase,flag,rank),coins,draws))
    return tuple(result)


def confirm_handles(C,E,bundle,handles):
    global SCOPE
    summaries=[]
    for role,handle in zip(('reference','treatment'),handles):
        SCOPE={'stage':'export','role':role,'epoch':465}
        checkpoints,pre,tmax=C._external_material(handle)
        own_bundle,own_role,stored,training=C._ROLE_CURVES[handle]
        assert own_bundle is bundle and own_role==role and checkpoints is stored
        assert tmax==465 and len(checkpoints)==466 and len(training)==465
        for epoch,traces,mean in checkpoints:
            assert traces is BANK_OBJECTS[(role,epoch)] and len(traces)==100
            LOG.emit('HANDLE_CHECKPOINT',{'epoch':epoch,'count':100,'mean_hex':mean.hex(),
                    'ordered_raw_sha256':BANK_DIGESTS[(role,epoch)]})
        assert all(r['epoch']==i for i,r in enumerate(training))
        actor=C._BUNDLES[bundle].actors[('reference','treatment').index(role)]
        LOG.emit('FINAL_COMPOSITE',actor.payload())
        # The actual closed constructor is part of the measured complete path.
        resource('before_external_constructor')
        view=E.build(handle); projected=E.read(view)
        LOG.emit('EXTERNAL_VIEW',dict(projected,fields=dict(projected['fields'])))
        resource('after_external_constructor')
        values=[{'epoch':e,'mean_hex':m.hex()} for e,_traces,m in checkpoints]
        summaries.append({'role':role,'ordered_curve':values,'pre_level_hex':pre.hex(),'t_max':tmax,
                          'full_composite_sha256':A.digest(actor.payload()),
                          'numeric_entry_count':len(actor._current.q_overrides) if MODE=='dq' else len(actor._values.q_overrides),
                          'decision_entry_count':len(actor._current.decision_overrides)})
        del projected,view
    C._checked(bundle)
    return summaries


def main():
    global LOG,SCOPE
    LOG=Capture(OUT/'raw.jsonl.gz')
    source=bound=pair=bundle=None
    succeeded=False
    try:
        LOG.emit('RUN_BEGIN',{'mode':MODE,'started_at_utc':datetime.now(timezone.utc).isoformat(),
                             'contract_sha256':hashlib.sha256((HERE/'contract.json').read_bytes()).hexdigest()})
        resource('startup')
        _td,L,C,E=load_modules()
        sys.setprofile(observe)
        reference=read_reference(); source,bound,pair=make_source(reference)
        stream=make_episodes(L)
        bundle=C.prepare_curve(bound,pair,episodes=stream,evaluation_indices=tuple(range(100)))
        d=C._checked(bundle)
        assert d.plan.grid==tuple(range(466)) and len(d.plan.evaluation_sample)==100 and d.plan.t_max==465
        LOG.emit('CURVE_PREPARED',{'origin':d.origin,'origin_sha256':d.seal,
                                 'initial_composites':[a.payload() for a in d.actors]})
        resource('prepared')
        handles=C.run_pair_curve(bundle)
        assert len(handles)==2
        summaries=confirm_handles(C,E,bundle,handles)
        LOG.emit('ORIGINAL_PAIR_AFTER',O.pair_audit(pair,source))
        assert COUNTS['rollout']==COUNTS['rollout_return']==94131
        assert COUNTS['step']==COUNTS['step_return'] and COUNTS['B1']==2 and not COUNTS['forbidden']
        assert len(BANK_OBJECTS)==932
        loaded={}
        for mod in tuple(sys.modules.values()):
            filename=getattr(mod,'__file__',None)
            if filename:
                p=Path(filename).resolve()
                if p.is_relative_to(ROOT) and p.suffix=='.py':
                    loaded[p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
        pins=json.loads((HERE/'evidence/claim.json').read_bytes())['input_binding_before']
        assert all(n in pins and pins[n]['sha256']==h for n,h in loaded.items())
        LOG.emit('ACTUAL_LOADED_SOURCE_INVENTORY',loaded)
        final_resource=resource('complete')
        LOG.emit('RESULT',{'completed':True,'counts':dict(COUNTS),'roles':summaries,
                          'resources':final_resource,'peaks':PEAK,'checkpoint_banks':932,
                          'training_episodes':930,'raw_records_before_result':LOG.records,
                          'capture_encode_seconds':LOG.encode_seconds,'capture_write_seconds':LOG.write_seconds,
                          'source_mode_bound_before_arms':True,'formal_keyed_stream':False,
                          'scientific_qualification':False,'collection_authorized':False})
        succeeded=True
    except BaseException as exc:
        sys.setprofile(None)
        if PENDING: LOG.emit('PENDING_RETURNED_STEPS',PENDING,force=True)
        failed={'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc(),
                'counts':dict(COUNTS),'complete_handle_issued':False,'peaks':PEAK,
                'bank_partial_count':0 if BANK is None else len(BANK['traces'])}
        if bundle is not None:
            d=C._BUNDLES[bundle]
            failed['curve_attempted']=C._ATTEMPTED[bundle]
            failed['complete_handle_issued']=bundle in C._COMPLETED
            failed['actors']=[{'role':a.role,'completed':a._completed,'attempted':sorted(a._attempted),
                              'immediate':A.stores(a._immediate),'current':A.stores(a._current),
                              'L':None if a._values is None else A.stores(a._values)} for a in d.actors]
        LOG.emit('FAILURE',failed,force=True)
        print(canonical({'tag':'FAILURE','mode':MODE,'error':failed,'resource':RM.sample()}),flush=True)
        traceback.print_exc()
    finally:
        sys.setprofile(None)
        LOG.close()
        summary={'completed':succeeded,'mode':MODE,'counts':dict(COUNTS),'records':LOG.records,
                 'uncompressed_bytes':LOG.raw_bytes,'canonical_sha256':LOG.canonical_sha.hexdigest(),
                 'compressed_bytes':(OUT/'raw.jsonl.gz').stat().st_size,
                 'wall_seconds':time.monotonic()-START,'cpu_seconds':time.process_time(),
                 'encode_seconds':LOG.encode_seconds,'write_seconds':LOG.write_seconds,'peaks':PEAK}
        with (OUT/'child_summary.json').open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(canonical(summary)+'\n')
        print(canonical({'tag':'CHILD_EXIT_SUMMARY',**summary}),flush=True)
    return 0 if succeeded else 1


if __name__=='__main__':
    raise SystemExit(main())
