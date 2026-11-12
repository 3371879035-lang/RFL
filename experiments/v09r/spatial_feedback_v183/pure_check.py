"""Check the two observed defects and their gradient routes without environment calls."""
import ast
import hashlib
import json
from pathlib import Path
import traceback
import numpy as np
import torch
from repairs import bootstrap_mask, successor, transition_loss

HERE=Path(__file__).resolve().parent


def main():
    tests, error = {}, None
    try:
        ids=np.arange(262144, dtype=np.int64)
        masks=[bootstrap_mask(ids,j,93001) for j in range(3)]
        fractions=[float(x.mean()) for x in masks]
        differences=[float(np.mean(masks[i]!=masks[j])) for i,j in [(0,1),(0,2),(1,2)]]
        assert all(.68<x<.75 for x in fractions)
        assert all(.35<x<.46 for x in differences)
        assert np.array_equal(bootstrap_mask(ids[::7],1,93001),masks[1][::7])
        tests['bootstrap']=dict(inclusion=fractions, pairwise_difference=differences, persistent_uid_stable=True)
        h=torch.linspace(-.99,.99,128).reshape(2,64)
        assert torch.equal(successor(h,torch.zeros_like(h)),h)
        assert successor(h,torch.full_like(h,100)).max()<=1
        assert successor(h,torch.full_like(h,-100)).min()>=-1
        tests['zero_delta_identity_and_bounds']=True
        for q_enabled in [False,True]:
            base=torch.linspace(-.5,.5,128).reshape(2,64).requires_grad_()
            target=(base.detach()+.02).clamp(-1,1).requires_grad_()
            delta=torch.zeros_like(base,requires_grad=True)
            q=torch.nn.Linear(64,16) if q_enabled else None
            loss,_=transition_loss(base,target,delta,torch.ones(2),torch.tensor([1.,0.]),torch.ones(2,16,dtype=torch.bool),q)
            loss.backward()
            assert base.grad is None and target.grad is None
            assert delta.grad[0].abs().sum()>0 and delta.grad[1].abs().sum()==0
            if q is not None:assert q.weight.grad is None and q.bias.grad is None
            tests['gradient_route_Q' if q_enabled else 'gradient_route_F0']=True
        old=ast.parse((HERE.parent/'spatial_feedback_v179/learning.py').read_text(encoding='utf-8'))
        new=ast.parse((HERE/'learning.py').read_text(encoding='utf-8'))
        find=lambda t,name:next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name==name)
        assert ast.dump(find(old,'Network'))==ast.dump(find(new,'Network'))
        def q_update(tree):
            a=find(tree,'Agent');f=next(n for n in a.body if isinstance(n,ast.FunctionDef) and n.name=='learn')
            return next(n for n in f.body if isinstance(n,ast.If) and ast.unparse(n.test)=='self.q_enabled')
        assert ast.dump(q_update(old))==ast.dump(q_update(new))
        assert (HERE/'world.py').read_bytes()==(HERE.parent/'spatial_feedback_v179/world.py').read_bytes()
        tests['common_network_Q_update_and_world_unchanged']=True
        for p in [HERE/'learning.py',HERE/'repairs.py',HERE/'experiment.py',HERE/'pilot.py']:
            ast.parse(p.read_text(encoding='utf-8'))
        tests['all_native_sources_parse']=True
    except BaseException:
        error=traceback.format_exc()
    result=dict(exit_code=int(error is not None),error=error,tests=tests,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        new_environment_steps=0, optimizer_updates=0,
        limit='Pure formula/gradient/source checks, not repaired task performance.')
    with (HERE/'pure_check_result.json').open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result['exit_code']


if __name__=='__main__':raise SystemExit(main())
