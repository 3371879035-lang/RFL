"""Small equation/dataflow checks; no environment or optimizer calls."""
import json
import numpy as np
import torch
from torch.nn import functional as F
from core import MemoryBank, Network, tensors, packed, count_parameters
from learning import signed_preference, aggregate_adoption


def check():
    torch.manual_seed(269)
    bank=MemoryBank()
    rng=np.random.default_rng(269)
    for i in range(96): bank.add(str(i),rng.normal(size=101).astype(np.float32))
    view=bank.view()
    bank.add('96',np.zeros(101,np.float32))
    bank.add('0',bank.nodes[0])
    assert len(bank.nodes)==97 and len(view)==96
    assert '96' not in view.arrays(None)[1]
    accessible=set()
    for j in range(8): accessible.update(view.arrays(64,j)[1])
    assert '0' in accessible and len(accessible)>64
    obs=(np.ones((5,21,21),np.uint8),rng.normal(size=40).astype(np.float32),np.ones(16,bool))
    net=Network(); b=tensors([packed(obs,view)],read_budget=None)
    gradients={}
    for name in ('measurements','effect'):
        out=net(b)
        loss=(out[name]**2).sum()
        names=['current.0.weight','node_encoder.0.weight','query.weight','applicability.0.weight']
        params=dict(net.named_parameters())
        grads=torch.autograd.grad(loss,[params[n] for n in names])
        gradients[name]={n:float(g.norm()) for n,g in zip(names,grads)}
        assert all(v>0 for v in gradients[name].values())
    mem=b[3].clone().requires_grad_(True)
    out=net((b[0],b[1],b[2],mem,b[4]))
    g=torch.autograd.grad(out['q'][0,0]-out['q'][0,1],mem)[0]
    assert float(g[0,0].norm())>0
    signed=[]
    for delta in (.2,-.2,0.):
        gap=torch.tensor(0.,requires_grad=True)
        signed.append(float(torch.autograd.grad(signed_preference(gap,delta),gap)[0]))
    assert signed[0]<0 and signed[1]>0 and signed[2]==0
    assert aggregate_adoption([.5,-.1]) and not aggregate_adoption([0.,0.])
    assert count_parameters(net)['total']==213329
    return dict(status='EQUATIONS_AND_GRADIENTS_CHECKED_NOT_TASK_SUCCESS',gradients=gradients,
                old_node_gradient=float(g[0,0].norm()),signed_gradients=signed,
                history_nodes=97,eligible_view=96,reachable_sampled_nodes=len(accessible),
                parameter_count=213329,environment_steps=0,optimizer_calls=0)


if __name__=='__main__':
    torch.set_num_threads(1)
    print(json.dumps(check(),allow_nan=False))
