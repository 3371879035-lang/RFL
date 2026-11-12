"""Bounded targeted learning test. Leaves the already-running V227 experiment alone."""
import gzip
import hashlib
import json
from pathlib import Path
import time
import traceback
import numpy as np
import torch
from torch.nn import functional as F
from core import HERE,ROOT,P,MemoryBank,Network,tensors,packed,count_parameters,write_json
from learning import Agent,signed_preference,aggregate_adoption

def verify_inputs():
    pins=json.loads((HERE/'input_pins.json').read_text(encoding='utf-8'))
    changed=[p for p,h in pins.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
    assert not changed,changed
    return len(pins)

def main():
    cap=HERE/'check';cap.mkdir(exist_ok=False);start=time.time()
    write_json(cap/'claim.json',dict(start_unix=start,seed=199,domains=['generic','pursuit'],
      charged_training_steps_per_domain=2048,optimizer_calls_per_domain=64,eval_episodes_per_domain_per_phase=4,
      total_eval_step_cap=4192,input_count=verify_inputs(),automatic_retries=0,
      purpose='Direct fixes: joint gradients, mean-based actual validation, old-event access, real training integration. Not a superiority test.'))
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    try:
        assert aggregate_adoption([.5,-.1])
        assert not aggregate_adoption([-.5,.1])
        assert not aggregate_adoption([0.,0.])
        signed=[]
        for delta in (.2,-.2,0.):
            gap=torch.tensor(0.,requires_grad=True);loss=signed_preference(gap,delta)
            grad=float(torch.autograd.grad(loss,gap)[0]);signed.append(dict(delta=delta,gradient=grad))
        assert signed[0]['gradient']<0 and signed[1]['gradient']>0 and signed[2]['gradient']==0
        results=[]
        for domain in ('generic','pursuit'):
            d=cap/domain;d.mkdir()
            bank=P.MapBank(ROOT/'experiments/v09r/spatial_feedback_v178/evidence_prepare/maps') if domain=='pursuit' else None
            a=Agent(domain,199,'N228',bank)
            initial=a.evaluate(4,0.)
            receipt=a.train_round(d,1,steps=2048,updates=64)
            final=a.evaluate(4,0.)
            assert len(a.memory_bank.nodes)==a.event_index==2048
            # Old real nodes remain visible; looking them up twice does not manufacture another observation.
            view=a.memory_bank.view();nodes,ids=view.arrays()
            assert len(ids)==2048 and ids[0]==a.memory_bank.ids[0]
            before=len(a.memory_bank.nodes)
            a.memory_bank.add(a.memory_bank.ids[0],a.memory_bank.nodes[0])
            assert len(a.memory_bank.nodes)==before
            old_view=a.replay[1].source[3]
            assert old_view.frontier<2048 and all(int(e.rsplit('/',1)[1])<2 for e in old_view.event_ids())
            # Each auxiliary loss individually reaches the actual shared encoder, not just its own head.
            rows=list(a.replay)[-8:];batch=tensors([r.source for r in rows]);ii=torch.arange(8)
            aa=torch.tensor([r.action for r in rows]);labels=torch.from_numpy(np.stack([r.labels for r in rows]))
            mask=torch.from_numpy(np.stack([r.mask for r in rows]))
            out=a.state.net(batch)
            pred=out['measurements'][ii,aa]
            loss=((pred-labels[:,None])**2*mask[:,None,:,None]).sum()
            grad=torch.autograd.grad(loss,a.state.net.current[0].weight)[0]
            factual_gradient=float(grad.norm());assert factual_gradient>0
            assert a.effects,'No actual paired effect reached the finite check'
            pair=a.effects[0];po=a.state.net(tensors([pair['source']]))
            estimate=po['effect'][0,pair['alternative']]-po['effect'][0,pair['baseline']]
            effect_loss=F.smooth_l1_loss(estimate,torch.tensor(pair['delta'],dtype=torch.float32))
            eg=torch.autograd.grad(effect_loss,a.state.net.current[0].weight)[0]
            effect_gradient=float(eg.norm());assert effect_gradient>0
            # Query with all actual history, and check influence from a node older than the former 16-node window.
            b=tensors([packed(a.env.observation(),a.memory_bank.view())]);mem=b[3].clone().requires_grad_(True)
            probe=a.state.net((b[0],b[1],b[2],mem,b[4]))
            mg=torch.autograd.grad(probe['q'][0,0]-probe['q'][0,1],mem)[0]
            old_node_gradient=float(mg[0,0].norm());assert old_node_gradient>0
            seen=set();steps=0;logs=[]
            with gzip.open(d/'round0001_N228.jsonl.gz','rt',encoding='utf-8') as f:
                for line in f:
                    row=json.loads(line)
                    if row.get('kind')=='round_log':logs=row['events'];continue
                    assert row['id'] not in seen and len(row['memory_ids'])==len(set(row['memory_ids']))
                    assert all(e in seen for e in row['memory_ids'])
                    seen.add(row['id']);steps+=1
            assert steps==2048
            assert sum(x['kind']=='optimizer' for x in logs)==64
            assert not any(x['kind']=='full_task_gate' and x['stage']=='teacher' for x in logs)
            torch.save(a.checkpoint(),d/'checkpoint.pt')
            results.append(dict(domain=domain,receipt=receipt,initial=initial,final=final,
                 factual_encoder_gradient=factual_gradient,effect_encoder_gradient=effect_gradient,
                 oldest_actual_node_gradient=old_node_gradient,available_history=len(ids),failed_source_count=len(a.failed_sources),
                 actual_pairs=[x for x in logs if x['kind']=='actual_pair'],actual_final_comparisons=[x for x in logs if x['kind']=='full_task_gate']))
            write_json(d/'result.json',results[-1])
        write_json(cap/'result.json',dict(status='COMPLETED_TARGETED_LEARNING_CHECK',results=results,
           signed_evidence_gradients=signed,mean_positive_with_one_adverse_is_eligible=True,
           parameter_counts=count_parameters(Network()),seconds=time.time()-start,input_count=verify_inputs(),
           three_hour_v227_modified=False,automatic_retries=0,task_superiority_established=False))
    except BaseException:
        write_json(cap/'failure.json',dict(error=traceback.format_exc(),seconds=time.time()-start,automatic_retries=0));raise

if __name__=='__main__':main()
