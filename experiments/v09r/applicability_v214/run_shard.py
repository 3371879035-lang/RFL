from pathlib import Path
from dataclasses import asdict
from datetime import datetime,timezone
import copy
import gzip
import hashlib
import json
import sys
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v210.network import parameter_digest
from feedback_program_v214 import RelationPredictor,HistoricalFeedbackNet,state_digest
from world import FAMILIES,ARMS,CHECKPOINTS,World,specification,tape


def main(family,seed):
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    assert family in contract['families'] and seed in contract['seeds']
    folder=HERE/'shards'/f'{family}_s{seed:02d}';folder.mkdir(parents=True,exist_ok=True)
    with(folder/'claim.json').open('x',encoding='utf-8') as f:json.dump({'utc':datetime.now(timezone.utc).isoformat()},f)
    before={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in contract['input_sha256']}
    assert before==contract['input_sha256']
    torch.set_num_threads(1);rng=torch.get_rng_state().clone();started=time.perf_counter()
    world=World(specification(family,seed));archive=[]
    historical=RelationPredictor((2,)*3,hazard=0.);temporal=RelationPredictor((2,)*3,hazard=.05)
    original=[parameter_digest(historical),parameter_digest(temporal)]
    rows=[];nrecords=0
    with(folder/'raw.jsonl.gz').open('xb') as binary,gzip.GzipFile(fileobj=binary,mode='wb',mtime=0) as raw:
        def emit(kind,**payload):
            nonlocal nrecords
            raw.write((json.dumps({'kind':kind,**payload},sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode());nrecords+=1
        emit('start',spec=world.spec,input_sha256=before,history_is_real=True,torch_version=torch.__version__)
        for i in range(256):
            scene=tape(world.spec,'history',i);fact=world.run(scene,'history',i,[.5,.5],'history-uniform')
            historical.observe(fact);temporal.observe(fact);archive.append(fact)
            emit('history',slot=i,public=asdict(fact),scene=scene)
        emit('history_ready',historical_digest=state_digest(historical),temporal_digest=state_digest(temporal),
             actual_source_interactions=256,temporal_reinterpretations_of_same_facts=256)
        offset=seed%len(ARMS)
        for mode in ARMS[offset:]+ARMS[:offset]:
            start_wall,start_cpu=time.perf_counter(),time.process_time()
            net=HistoricalFeedbackNet(mode,historical,temporal,archive)
            parameter_before=parameter_digest(net)
            event_id=256;training=[];evaluations=[]
            emit('arm_start',arm=mode,parameters=parameter_before,archive_facts=len(net.archive))
            def evaluate(checkpoint):
                nonlocal event_id
                scenes=[tape(world.spec,'eval',slot,checkpoint) for slot in range(128)]
                state_before=state_digest(net);n_before=(len(net.archive),net.current.n,net.last_id)
                with torch.no_grad():
                    pred,mu,share,cache=net.predict([s['context'] for s in scenes])
                outcomes=[]
                for slot,scene in enumerate(scenes):
                    behavior=mu[slot].tolist();fact=world.run(scene,'eval',event_id,behavior,mode);event_id+=1
                    wire={'prediction':pred[slot].tolist(),'behavior':behavior,
                          'history_share':float(share[slot]) if share is not None else None,
                          'history_prediction':cache['history'][slot].tolist() if cache['history'] is not None else None,
                          'fresh_prediction':cache['fresh'][slot].tolist()}
                    emit('eval_episode',arm=mode,checkpoint=checkpoint,slot=slot,scene=scene,public=asdict(fact),offer=wire)
                    outcomes.append(fact.outcome)
                assert state_before==state_digest(net) and n_before==(len(net.archive),net.current.n,net.last_id)
                row={'checkpoint':checkpoint,'successes':sum(outcomes),'episodes':128,
                     'state_unchanged':True,'learned_current_facts':checkpoint}
                evaluations.append(row);emit('eval_end',arm=mode,**row)
            evaluate(0)
            for i in range(256):
                scene=tape(world.spec,'train',i);offer=net.offer(scene['context'],event_id)
                fact=world.run(scene,'train',event_id,offer['behavior'],mode);event_id+=1
                net.observe(offer,fact);training.append(fact.outcome)
                emit('train_episode',arm=mode,slot=i,scene=scene,offer=offer,public=asdict(fact))
                if i+1 in CHECKPOINTS:evaluate(i+1)
            assert len(net.archive)==512 and parameter_before==parameter_digest(net)
            net.assert_history_unchanged()
            row={'arm':mode,'training_successes':sum(training),'first16_successes':sum(training[:16]),
                 'first64_successes':sum(training[:64]),'training_interactions':256,'eval_interactions':640,
                 'evaluations':evaluations,'archive_facts':len(net.archive),'frozen_history_unchanged':True,
                 'parameters_unchanged':True,'parameter_scalars':sum(p.numel() for p in net.parameters()),
                 'buffer_bytes':sum(b.numel()*b.element_size() for b in net.buffers()),
                 'wall_seconds':time.perf_counter()-start_wall,'cpu_seconds':time.process_time()-start_cpu}
            rows.append(row);emit('arm_end',**row)
        assert world.interactions==4736 and original==[parameter_digest(historical),parameter_digest(temporal)]
        assert torch.equal(rng,torch.get_rng_state())
        after={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in before};assert before==after
        emit('end',interactions=world.interactions,archive_interactions=256,training_interactions=1280,
             evaluation_interactions=3200,steps=world.interactions,input_unchanged=True,gradient_updates=0)
    result={'family':family,'seed':seed,'rows':rows,'records':nrecords,'actual_interactions':world.interactions,
            'steps':world.interactions,'wall_seconds':time.perf_counter()-started,
            'raw_sha256':hashlib.sha256((folder/'raw.jsonl.gz').read_bytes()).hexdigest(),'input_unchanged':True}
    with(folder/'native_result.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({'family':family,'seed':seed,'actual_interactions':world.interactions,'seconds':result['wall_seconds']}),flush=True)


if __name__=='__main__':main(sys.argv[1],int(sys.argv[2]))
