"""Check the new isolation routes, without environment calls or training runs."""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import traceback
import torch
from torch import nn

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    checks, error = {}, None
    try:
        old = (HERE.parent/'q_behavior_diagnostic_v184/learning.py').read_text(encoding='utf-8')
        expected = old.replace('            inputs = torch.cat((cur, onehot), -1)',
            '            inputs = torch.cat((cur.detach() if self.q_enabled else cur, onehot), -1)')
        expected = expected.replace('        nn.utils.clip_grad_norm_(self.net.parameters(), 5.)',
            "        if self.factual and self.q_enabled:\n"
            "            core = [p for name, p in self.net.named_parameters() if not name.startswith('heads.')]\n"
            "            nn.utils.clip_grad_norm_(core, 5.)\n"
            "            nn.utils.clip_grad_norm_(self.net.heads.parameters(), 5.)\n"
            "        else:\n"
            "            nn.utils.clip_grad_norm_(self.net.parameters(), 5.)")
        tree = ast.parse((HERE/'learning.py').read_text(encoding='utf-8'))
        assert ast.dump(tree) == ast.dump(ast.parse(expected))
        checks['only_declared_detach_and_clipping_changes_in_full_learner_AST'] = True
        agent = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'Agent')
        learn = next(x for x in agent.body if isinstance(x, ast.FunctionDef) and x.name == 'learn')
        inputs = next(x for x in ast.walk(learn) if isinstance(x, ast.Assign)
                      and isinstance(x.targets[0], ast.Name) and x.targets[0].id == 'inputs')
        input_code = compile(ast.Module([inputs], type_ignores=[]), '<actual_inputs>', 'exec')
        for q_enabled in [False, True]:
            cur = torch.ones((2, 64), requires_grad=True)
            env = dict(torch=torch, cur=cur, onehot=torch.ones((2, 16)), self=SimpleNamespace(q_enabled=q_enabled))
            exec(input_code, env)
            weight = torch.ones((80, 1), requires_grad=True)
            (env['inputs'] @ weight).sum().backward()
            assert weight.grad is not None
            assert (cur.grad is None) == q_enabled
        checks['hybrid_fact_gradient_stopped_F0_gradient_retained'] = True
        clip = next(x for x in learn.body if isinstance(x, ast.If)
                    and ast.unparse(x.test) == 'self.factual and self.q_enabled')
        clip_code = compile(ast.Module([clip], type_ignores=[]), '<actual_clip>', 'exec')
        core_gradients = []
        for head_magnitude in [1., 100000.]:
            net = nn.Module()
            net.register_parameter('q', nn.Parameter(torch.zeros(2)))
            net.heads = nn.Linear(2, 1, bias=False)
            net.q.grad = torch.tensor([6., 8.])
            net.heads.weight.grad = torch.full_like(net.heads.weight, head_magnitude)
            exec(clip_code, dict(nn=nn, self=SimpleNamespace(net=net, factual=True, q_enabled=True)))
            core_gradients.append(net.q.grad.clone())
            assert net.heads.weight.grad.norm() <= 5.000001
        assert torch.equal(*core_gradients) and core_gradients[0].norm() <= 5.000001
        checks['actual_core_clip_independent_of_auxiliary_gradient_magnitude'] = True
        for name in ['world.py', 'repairs.py', 'map_binding.json']:
            assert (HERE/name).read_bytes() == (HERE.parent/'q_behavior_diagnostic_v184'/name).read_bytes()
        for pin in json.loads((HERE/'control_binding.json').read_text(encoding='utf-8'))['files']:
            path = ROOT/pin['path']
            assert path.stat().st_size == pin['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest() == pin['sha256']
        checks['all_declared_old_controls_and_common_world_unchanged'] = True
        for name in ['learning.py', 'experiment.py', 'pilot.py']:
            ast.parse((HERE/name).read_text(encoding='utf-8'))
    except BaseException:
        error = traceback.format_exc()
    result = dict(exit_code=int(error is not None), error=error, checks=checks,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        environment_steps=0, optimizer_steps=0, old_native_or_checker_calls=0)
    with (HERE/'pure_check_result.json').open('x', encoding='utf-8', newline='\n') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
