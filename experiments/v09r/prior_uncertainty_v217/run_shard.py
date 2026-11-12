from pathlib import Path
from dataclasses import asdict
from datetime import datetime,timezone
import gzip,hashlib,json,sys,time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OLD=ROOT/'experiments/v09r/applicability_v214'
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(OLD))
import torch
from feedback_program_v210.network import Fact,parameter_digest
from feedback_program_v214 import RelationPredictor,state_digest
from feedback_program_v215 import DecisionSeparatedNet
from feedback_program_v217 import PriorUncertaintyNet
from world import tape,specification


def main(family,seed):
    contract=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    assert family in contract['families'] and seed in contract['seeds']
    returning=family=='selective_return';source_family='selective_change' if returning else family
    spec=specification(source_family,seed)
    checkpoints=[0,16,64,128,144,160,192,256] if returning else [0,16,64,128,256]
    arms=['shared_raw_v217','local_calibrated_v217','shared_calibrated_v217']
    offset=seed%len(arms);arms=arms[offset:]+arms[:offset]
    folder=HERE/'shards'/f'{family}_s{seed:02d}';folder.mkdir(parents=True,exist_ok=True)
    with(folder/'claim.json').open('x',encoding='utf-8') as f:json.dump({'utc':datetime.now(timezone.utc).isoformat()},f)
    pins=lambda:{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in contract['input_sha256']}
    before=pins();assert before==contract['input_sha256']
    torch.set_num_threads(1);rng=torch.get_rng_state().clone();started=time.perf_counter()
    source=OLD/'shards'/f'{source_family}_s{seed:02d}'/'raw.jsonl.gz';source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    h=RelationPredictor((2,)*3,hazard=0.);t=RelationPredictor((2,)*3,hazard=.05);archive=[];imports=[]
    with gzip.open(source,'rt',encoding='utf-8') as stream:
        for n,line in enumerate(stream,1):
            r=json.loads(line)
            if r['kind']=='start':assert r['spec']==spec
            elif r['kind']=='history':
                d=r['public'];f=Fact(d['id'],tuple(d['context']),d['action'],d['outcome'],d['propensity'],d['policy_id'])
                assert f.id==len(archive);h.observe(f);t.observe(f);archive.append(f);imports.append({'source_record':n,'public':d})
            elif r['kind']=='history_ready':
                assert len(archive)==256 and state_digest(h)==r['historical_digest'] and state_digest(t)==r['temporal_digest'];break
    assert len(archive)==256
    events=records=0;rows=[]
    with(folder/'raw.jsonl.gz').open('xb') as binary,gzip.GzipFile(fileobj=binary,mode='wb',mtime=0) as raw:
        def emit(kind,**payload):
            nonlocal records
            raw.write((json.dumps({'kind':kind,**payload},sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode());records+=1
        emit('start',family=family,seed=seed,source_spec=spec,return_after=128 if returning else None,
             checkpoints=checkpoints,arms=arms,history_source=source.relative_to(ROOT).as_posix(),history_sha256=source_hash,
             history_semantics='Recorded actual V214 history, not new native interactions',input_sha256=before)
        for r in imports:emit('history_import',**r)
        for arm in arms:
            net=PriorUncertaintyNet(h,t,archive,shared=arm.startswith('shared'),etas=(0.,) if arm=='shared_raw_v217' else (0.,.25,.5))
            rates=list(net.gate.rate_values)
            par=parameter_digest(net);event_id=256;train=[];evals=[];sw=time.perf_counter();sc=time.process_time()
            emit('arm_start',arm=arm,mode=net.mode,rates=rates,etas=list(net.gate.eta_values),shared=net.gate.shared,parameters=par)
            def execute(scene,current_index,behavior):
                nonlocal events,event_id
                x=scene['context'];a=int(scene['action_u']<behavior[1]);desired=x[spec['payload']]
                if family=='changed_novel':desired^=1
                elif family=='selective_change' or (returning and current_index<128):desired^=x[spec['condition']]
                probability=.5 if family=='noise' else .9 if a==desired else .1
                y=int(scene['outcome_u']<probability);f=Fact(event_id,x,a,y,behavior[a],net.mode)
                event_id+=1;events+=1;return f
            def evaluate(checkpoint):
                scenes=[tape(spec,'eval',i,checkpoint) for i in range(128)]
                bd=state_digest(net);state=(len(net.archive),net.current.n,net.gate.updates,net.last_id)
                with torch.no_grad():pred,mu,share,cache=net.predict([s['context'] for s in scenes])
                outcomes=[]
                for i,scene in enumerate(scenes):
                    rweights=cache['gate']['rate_marginal'][i].tolist()
                    wire={'prediction':pred[i].tolist(),'behavior':mu[i].tolist(),'history_share':float(share[i]),
                          'history_prediction':cache['history'][i].tolist(),'fresh_prediction':cache['fresh'][i].tolist(),
                          'decision_scores':cache['decision_scores'][i].tolist(),'estimated_margin':float(cache['estimated_margin'][i]),
                          'rate_hypotheses':rates,'rate_weights':rweights,'mean_reopening_rate':sum(r*w for r,w in zip(rates,rweights)),
                          'rate_semantics':'predictive_persistence_not_environment_change_probability'}
                    wire.update(net.uncertainty_wire(cache['gate'],i))
                    fact=execute(scene,checkpoint,wire['behavior']);outcomes.append(fact.outcome)
                    emit('eval_episode',arm=arm,checkpoint=checkpoint,slot=i,scene=scene,offer=wire,public=asdict(fact))
                assert bd==state_digest(net) and state==(len(net.archive),net.current.n,net.gate.updates,net.last_id)
                row={'checkpoint':checkpoint,'successes':sum(outcomes),'episodes':128,'state_unchanged':True}
                evals.append(row);emit('eval_end',arm=arm,**row)
            evaluate(0)
            for i in range(256):
                scene=tape(spec,'train',i);wire=net.offer(scene['context'],event_id)
                assert net.gate.prior.logits.requires_grad
                fact=execute(scene,i,wire['behavior']);net.observe(wire,fact);train.append(fact.outcome)
                emit('train_episode',arm=arm,slot=i,scene=scene,offer=wire,public=asdict(fact))
                if i+1 in checkpoints:evaluate(i+1)
            assert net.current.n==net.gate.updates==256 and len(net.archive)==512 and par==parameter_digest(net)
            net.assert_history_unchanged()
            row={'family':family,'seed':seed,'arm':arm,'training_successes':sum(train),'first16_successes':sum(train[:16]),
                 'first64_successes':sum(train[:64]),'second_half_successes':sum(train[128:]),'return_first16_successes':sum(train[128:144]) if returning else None,
                 'training_interactions':256,'evaluation_interactions':len(checkpoints)*128,'evaluations':evals,
                 'archive_facts':512,'parameters_unchanged':True,'history_unchanged':True,
                 'parameter_scalars':sum(p.numel() for p in net.parameters()),'trainable_prior_scalars':sum(p.numel() for p in net.parameters() if p.requires_grad),'buffer_bytes':sum(b.numel()*b.element_size() for b in net.buffers()),
                 'cpu_seconds':time.process_time()-sc,'wall_seconds':time.perf_counter()-sw}
            rows.append(row);emit('arm_end',**row)
        expected=len(arms)*(256+len(checkpoints)*128);assert events==expected and torch.equal(rng,torch.get_rng_state())
        after=pins();assert before==after
        emit('end',new_actual_interactions=events,steps=events,history_imports=256,new_history_interactions=0,
             gradient_updates=0,input_unchanged=True,torch_rng_unchanged=True)
    result={'family':family,'seed':seed,'rows':rows,'records':records,'new_actual_interactions':events,'history_imports':256,
            'wall_seconds':time.perf_counter()-started,'raw_sha256':hashlib.sha256((folder/'raw.jsonl.gz').read_bytes()).hexdigest(),
            'input_unchanged':True}
    with(folder/'native_result.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({'family':family,'seed':seed,'new_actual_interactions':events,'seconds':result['wall_seconds']}))


if __name__=='__main__':main(sys.argv[1],int(sys.argv[2]))
