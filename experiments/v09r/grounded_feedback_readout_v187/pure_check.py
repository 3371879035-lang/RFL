"""Check neutral residual initialization, detached targets, and unchanged Q core."""
import ast
import hashlib
import json
from pathlib import Path
import traceback
import torch
from learning import Network

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
checks={};error=None
try:
    factual=Network(93001,True,True)
    reference=Network(93001,False,True)
    assert all(torch.equal(value,factual.state_dict()[name]) for name,value in reference.state_dict().items())
    x=torch.linspace(-1,1,160).reshape(2,80)
    assert all(head(x).shape==(2,75) and torch.equal(head(x)[:,74],torch.zeros(2)) for head in factual.heads)
    no_q=Network(93001,True,False)
    assert no_q.q is None and all(head(x).shape==(2,74) for head in no_q.heads)
    checks['neutral_residual_common_initial_core_and_F0_noQ']=True
    tree=ast.parse((HERE/'learning.py').read_text(encoding='utf-8'))
    target=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='residual_target')
    env=dict(y=torch.tensor([2.],requires_grad=True),current_q=torch.tensor([.5],requires_grad=True))
    exec(compile(ast.Module([target],type_ignores=[]),'<actual_target>','exec'),env)
    assert env['residual_target'].item()==1.5 and not env['residual_target'].requires_grad
    checks['actual_residual_target_detached']=True
    base=ast.parse((HERE.parent/'auxiliary_isolation_v185/learning.py').read_text(encoding='utf-8'))
    def method(t,name):
        agent=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name=='Agent')
        return next(n for n in agent.body if isinstance(n,ast.FunctionDef) and n.name==name)
    qblock=lambda t:next(n for n in method(t,'learn').body if isinstance(n,ast.If) and ast.unparse(n.test)=='self.q_enabled')
    clip=lambda t:next(n for n in method(t,'learn').body if isinstance(n,ast.If) and ast.unparse(n.test)=='self.factual and self.q_enabled')
    assert ast.dump(qblock(base))==ast.dump(qblock(tree)) and ast.dump(clip(base))==ast.dump(clip(tree))
    for name in ['_features','observe','stage','reset_episode']:
        assert ast.dump(method(base,name))==ast.dump(method(tree,name))
    checks['Q_update_isolation_and_common_history_unchanged']=True
    for pin in json.loads((HERE/'control_binding.json').read_text(encoding='utf-8'))['files']:
        p=ROOT/pin['path'];assert p.stat().st_size==pin['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']
    checks['all_declared_stored_controls_unchanged']=True
    for name in ['experiment.py','pilot.py']:ast.parse((HERE/name).read_text(encoding='utf-8'))
except BaseException:error=traceback.format_exc()
result=dict(exit_code=int(error is not None),error=error,checks=checks,environment_steps=0,optimizer_steps=0,
    new_synthetic_network_initializations=3,old_native_or_checker_calls=0)
with (HERE/'pure_check_result.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False),flush=True)
raise SystemExit(result['exit_code'])
