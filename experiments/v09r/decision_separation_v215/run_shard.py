"""Execute only the new readout; old recorded history is imported explicitly."""
from pathlib import Path
from dataclasses import asdict
from datetime import datetime,timezone
import gzip
import hashlib
import json
import sys
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREVIOUS=ROOT/'experiments/v09r/applicability_v214'
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(PREVIOUS))
import torch
from feedback_program_v210.network import Fact,parameter_digest
from feedback_program_v214 import RelationPredictor,state_digest
from feedback_program_v215 import DecisionSeparatedNet
from world import World,specification,tape,CHECKPOINTS


def main(family,seed):
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    assert family in contract['families'] and seed in contract['seeds']
    folder=HERE/'shards'/f'{family}_s{seed:02d}';folder.mkdir(parents=True,exist_ok=True)
    with(folder/'claim.json').open('x',encoding='utf-8') as f:json.dump({'utc':datetime.now(timezone.utc).isoformat()},f)
    pins=lambda:{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in contract['input_sha256']}
    before=pins();assert before==contract['input_sha256']
    torch.set_num_threads(1);rng=torch.get_rng_state().clone();started=time.perf_counter()
    source=PREVIOUS/'shards'/f'{family}_s{seed:02d}'/'raw.jsonl.gz'
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    historical=RelationPredictor((2,)*3,hazard=0.);temporal=RelationPredictor((2,)*3,hazard=.05)
    archive=[];imported=[]
    with gzip.open(source,'rt',encoding='utf-8') as stream:
        for number,line in enumerate(stream,1):
            record=json.loads(line)
            if record['kind']=='start':
                source_spec=record['spec'];assert source_spec==specification(family,seed)
            elif record['kind']=='history':
                d=record['public'];fact=Fact(d['id'],tuple(d['context']),d['action'],d['outcome'],d['propensity'],d['policy_id'])
                assert fact.id==len(archive)
                historical.observe(fact);temporal.observe(fact);archive.append(fact)
                imported.append({'source_record':number,'public':d,'source_slot':record['slot']})
            elif record['kind']=='history_ready':
                assert len(archive)==historical.n==temporal.n==256
                assert state_digest(historical)==record['historical_digest']
                assert state_digest(temporal)==record['temporal_digest']
                break
    assert len(archive)==256
    world=World(source_spec);mode='decision_separated_v215';event_id=256;records=0
    start_arm,start_cpu=time.perf_counter(),time.process_time()
    net=DecisionSeparatedNet(historical,temporal,archive);parameters=parameter_digest(net)
    training=[];evaluations=[]
    with(folder/'raw.jsonl.gz').open('xb') as binary,gzip.GzipFile(fileobj=binary,mode='wb',mtime=0) as raw:
        def emit(kind,**payload):
            nonlocal records
            raw.write((json.dumps({'kind':kind,**payload},sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode());records+=1
        emit('start',family=family,seed=seed,spec=source_spec,mode=mode,input_sha256=before,
             history_source=source.relative_to(ROOT).as_posix(),history_sha256=source_hash,
             history_semantics='Recorded actual V214 prefix, not new native interaction',
             parameters=parameters,torch_version=torch.__version__)
        for d in imported:emit('history_import',**d)
        def evaluate(checkpoint):
            nonlocal event_id
            scenes=[tape(source_spec,'eval',slot,checkpoint) for slot in range(128)]
            state_before=state_digest(net);n_before=(len(net.archive),net.current.n,net.last_id,net.gate.updates)
            with torch.no_grad():pred,mu,share,cache=net.predict([s['context'] for s in scenes])
            outcomes=[]
            for slot,scene in enumerate(scenes):
                behavior=mu[slot].tolist();fact=world.run(scene,'eval',event_id,behavior,mode);event_id+=1
                wire={'prediction':pred[slot].tolist(),'behavior':behavior,'history_share':float(share[slot]),
                      'history_prediction':cache['history'][slot].tolist(),'fresh_prediction':cache['fresh'][slot].tolist(),
                      'decision_scores':cache['decision_scores'][slot].tolist(),
                      'estimated_margin':float(cache['estimated_margin'][slot]),
                      'source_mixture_behavior_not_executed':cache['source_mixture_behavior'][slot].tolist(),
                      'history_share_semantics':'predictive_weight_not_execution_fraction'}
                emit('eval_episode',checkpoint=checkpoint,slot=slot,scene=scene,public=asdict(fact),offer=wire)
                outcomes.append(fact.outcome)
            assert state_before==state_digest(net) and n_before==(len(net.archive),net.current.n,net.last_id,net.gate.updates)
            row={'checkpoint':checkpoint,'successes':sum(outcomes),'episodes':128,'state_unchanged':True,
                 'learned_current_facts':checkpoint}
            evaluations.append(row);emit('eval_end',**row)
        evaluate(0)
        for i in range(256):
            scene=tape(source_spec,'train',i);offer=net.offer(scene['context'],event_id)
            fact=world.run(scene,'train',event_id,offer['behavior'],mode);event_id+=1
            net.observe(offer,fact);training.append(fact.outcome)
            emit('train_episode',slot=i,scene=scene,offer=offer,public=asdict(fact))
            if i+1 in CHECKPOINTS:evaluate(i+1)
        assert len(net.archive)==512 and net.current.n==net.gate.updates==256
        assert parameter_digest(net)==parameters and world.interactions==896
        net.assert_history_unchanged();assert torch.equal(rng,torch.get_rng_state())
        after=pins();assert before==after
        row={'family':family,'seed':seed,'arm':mode,'training_successes':sum(training),
             'first16_successes':sum(training[:16]),'first64_successes':sum(training[:64]),
             'training_interactions':256,'eval_interactions':640,'evaluations':evaluations,
             'archive_facts':512,'recorded_history_facts_imported':256,'new_history_interactions':0,
             'parameters_unchanged':True,'frozen_history_unchanged':True,
             'parameter_scalars':sum(p.numel() for p in net.parameters()),
             'buffer_bytes':sum(b.numel()*b.element_size() for b in net.buffers()),
             'wall_seconds':time.perf_counter()-start_arm,'cpu_seconds':time.process_time()-start_cpu}
        emit('arm_end',**row)
        emit('end',new_actual_interactions=world.interactions,steps=world.interactions,input_unchanged=True,
             recorded_history_facts_imported=256,gradient_updates=0,torch_rng_unchanged=True)
    result={'row':row,'records':records,'new_actual_interactions':world.interactions,'steps':world.interactions,
            'wall_seconds':time.perf_counter()-started,'input_unchanged':True,'source_history_sha256':source_hash,
            'raw_sha256':hashlib.sha256((folder/'raw.jsonl.gz').read_bytes()).hexdigest()}
    with(folder/'native_result.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({'family':family,'seed':seed,'new_actual_interactions':world.interactions,'seconds':result['wall_seconds']}))


if __name__=='__main__':main(sys.argv[1],int(sys.argv[2]))
