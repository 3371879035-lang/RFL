"""One-shot bounded math/data-flow check, not a performance qualification."""
import gzip
import hashlib
import json
import time
import traceback
import numpy as np
import torch
from torch.nn import functional as F
from core import HERE,ROOT,Environment,Network,packed,tensors,reward,utility,count_parameters,write_json
from runtime import pins

def main():
    cap=HERE/'diagnostic';cap.mkdir(exist_ok=False)
    start=time.time();write_json(cap/'claim.json',dict(time=start,max_real_steps=480,max_optimizer_calls=120,seed=197,retries=0,input_count=pins()))
    try:
        torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.manual_seed(197)
        # Exact shared-linear-context cancellation, contrasted with a direct action-specific path.
        states=torch.randn(5,4);c=torch.randn(3,requires_grad=True)
        l=states@torch.randn(4)+c@torch.randn(3)
        cancellation=float(torch.autograd.grad(l[0]-l[1],c)[0].abs().max())
        assert cancellation==0.
        data=[]; targets=[]; actions=[]; real=0
        with gzip.open(cap/'actual_pair_data.jsonl.gz','xt',encoding='utf-8') as out:
            for i in range(16):
                src=Environment('generic',None,197,'v227-diagnostic',i)
                p=packed(src.observation(),[])
                for a in range(5):
                    env=src.clone(197); total=np.zeros(4,np.float32); raw=[]
                    while not env.done:
                        ob,f,d,result=env.step(a);real+=1;total+=f;raw.append(dict(next=ob[1].tolist(),facts=f.tolist(),terminal=d,result=result))
                    data.append(p);actions.append(a);targets.append(utility('generic',total))
                    out.write(json.dumps(dict(context=i,action=a,source=p[1].tolist(),outcomes=raw))+'\n')
        assert real==480
        net=Network();params=count_parameters(net);b=tensors(data);aa=torch.tensor(actions);ii=torch.arange(len(data));yy=torch.tensor(targets)
        out=net(b);v=b[1].clone().requires_grad_(True)
        probe=net((b[0],v,b[2],b[3],b[4]))['q']
        gradient=float(torch.autograd.grad((probe[:,0]-probe[:,1]).sum(),v)[0].norm())
        assert gradient>0
        initial=float(F.mse_loss(out['q'][ii,aa],yy).detach())
        optimizer=torch.optim.Adam(net.parameters(),lr=.001)
        losses=[]
        for _ in range(120):
            loss=F.mse_loss(net(b)['q'][ii,aa],yy)
            optimizer.zero_grad(set_to_none=True);loss.backward();optimizer.step();losses.append(float(loss.detach()))
        final=float(F.mse_loss(net(b)['q'][ii,aa],yy).detach())
        assert final<initial
        assert reward('generic',np.array([0.,0.,0.,.5]),True,False)==.5
        assert reward('generic',np.array([0.,0.,0.,.5]),True,True)==-.5
        # Deterministic optimizer-step identity / serialization, not a repeat experiment.
        torch.save(net.state_dict(),cap/'network.pt');fresh=Network();fresh.load_state_dict(torch.load(cap/'network.pt',weights_only=True))
        assert all(torch.equal(v,fresh.state_dict()[k]) for k,v in net.state_dict().items())
        write_json(cap/'result.json',dict(status='PASS_BOUNDED_IMPLEMENTATION',real_steps=real,optimizer_calls=120,
          old_linear_common_context_gradient=cancellation,new_action_contrast_input_gradient=gradient,
          observed_target_fitting_initial_mse=initial,observed_target_fitting_final_mse=final,
          fitted_contexts=16,independent_generalization_test=False,losses=losses,parameters=params,
          seconds=time.time()-start,input_count=pins(),retries=0))
    except BaseException:
        write_json(cap/'failure.json',dict(error=traceback.format_exc(),seconds=time.time()-start,retries=0));raise

if __name__=='__main__': main()
