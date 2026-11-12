"""New global calibration over RecordedForecasts, never new environment episodes."""
from pathlib import Path
from dataclasses import dataclass
import gzip,hashlib,json,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v218 import IdentityCalibrationHead
from feedback_program_v210.network import parameter_digest


@dataclass(frozen=True)
class RecordedForecast:
    source_sha256:str
    source_line:int
    context:tuple
    prediction:tuple
    action:int
    outcome:int


def main():
    c=json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    folder=HERE/'recorded_global';folder.mkdir(exist_ok=True)
    with(folder/'claim.json').open('x',encoding='utf-8') as f:json.dump({'type':'recorded_forecast_calculation','new_interactions':0},f)
    torch.set_num_threads(1);rng=torch.get_rng_state().clone();started=time.perf_counter();records=updates=0;rows=[]
    for family in c['families']:
        for seed in c['seeds']:
            root=HERE if family=='mixed_reliability' else HERE.parent/'evidence_persistence_v216'
            arm='raw_v216' if family=='mixed_reliability' else 'rate_mixture_v216'
            source=root/'shards'/f'{family}_s{seed:02d}'/'raw.jsonl.gz';digest=hashlib.sha256(source.read_bytes()).hexdigest()
            native=json.loads((source.parent/'native_result.json').read_text(encoding='utf-8'));assert digest==native['raw_sha256']
            head=IdentityCalibrationHead((2,)*3,conditional=False);par=parameter_digest(head);count=train=0;cached={}
            output=folder/f'{family}_s{seed:02d}.jsonl.gz'
            with output.open('xb') as binary,gzip.GzipFile(fileobj=binary,mode='wb',mtime=0) as out:
                def emit(obj):out.write((json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode())
                emit({'kind':'start','family':family,'seed':seed,'source':source.relative_to(ROOT).as_posix(),'source_sha256':digest,'source_arm':arm,
                      'data_kind':'RecordedForecast','new_environment_interactions':0})
                with gzip.open(source,'rt',encoding='utf-8') as inp:
                    for line_number,line in enumerate(inp,1):
                        r=json.loads(line)
                        if r['kind'] not in ['train_episode','eval_episode'] or r['arm']!=arm:continue
                        d=r['public'];base=r['offer']['prediction']
                        packet=RecordedForecast(digest,line_number,tuple(d['context']),tuple(tuple(p) for p in base),d['action'],d['outcome'])
                        key=(packet.context,packet.prediction)
                        if r['kind']=='train_episode' or key not in cached:
                            with torch.no_grad():p,cache=head.predict([packet.context],torch.tensor([base],dtype=torch.float64))
                            cached[key]=(p,cache)
                        p,cache=cached[key];pred=p[0].tolist()
                        best=max(range(2),key=lambda a:pred[a][1]);original=max(range(2),key=lambda a:base[a][1])
                        assert best==original
                        wire={**r['offer'],'base_prediction':base,'prediction':pred,'decision_scores':[v[1] for v in pred],
                              'estimated_margin':abs(pred[0][1]-pred[1][1]),**head.wire(cache,0)}
                        emit({'kind':r['kind'],'slot':r['slot'],'checkpoint':r.get('checkpoint'),'source_line':line_number,'public':d,'offer':wire,
                              'same_recorded_action_not_new_execution':True})
                        count+=1;records+=1
                        if r['kind']=='train_episode':head.observe(cache,packet.action,packet.outcome);train+=1;updates+=1;cached={}
                assert train==head.updates==256 and par==parameter_digest(head)
                emit({'kind':'end','forecast_records':count,'evidence_updates':train,'parameter_updates':0,'parameter_sha256':par,'new_environment_interactions':0})
            rows.append({'family':family,'seed':seed,'records':count,'evidence_updates':train,'source_sha256':digest,'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest()})
    assert records==92160 and updates==24576 and torch.equal(rng,torch.get_rng_state())
    result={'streams':len(rows),'forecast_records':records,'evidence_updates':updates,'new_environment_interactions':0,'gradient_updates':0,
            'rows':rows,'wall_seconds':time.perf_counter()-started,'rng_unchanged':True}
    with(folder/'result.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:result[k] for k in ['streams','forecast_records','new_environment_interactions','wall_seconds']}))

if __name__=='__main__':main()
