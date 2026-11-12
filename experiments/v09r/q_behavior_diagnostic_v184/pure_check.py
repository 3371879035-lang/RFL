"""Verify the one source intervention; no environment, model training, or old tests."""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    checks, error = {}, None
    try:
        old = (HERE.parent/'spatial_feedback_v183/learning.py').read_text(encoding='utf-8')
        expected = old.replace('        chosen = int(scores.argmax())\n',
            '        full_action = int(scores.argmax())\n'
            '        training_q_control = bool(training and self.factual and self.q_enabled)\n'
            '        chosen = old_action if training_q_control else full_action\n')
        expected = expected.replace('forecast=forecast, old_action=old_action)',
            'forecast=forecast, old_action=old_action,\n'
            '                                full_action=full_action, training_q_control=training_q_control)')
        tree = ast.parse((HERE/'learning.py').read_text(encoding='utf-8'))
        assert ast.dump(tree) == ast.dump(ast.parse(expected))
        checks['entire_learner_AST_equals_old_except_declared_action_selection_and_capture_fields'] = True
        agent = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Agent')
        act = next(n for n in agent.body if isinstance(n, ast.FunctionDef) and n.name == 'act')
        assignments = {n.targets[0].id: n.value for n in act.body
                       if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
        control = compile(ast.Expression(assignments['training_q_control']), '<actual_control>', 'eval')
        selector = compile(ast.Expression(assignments['chosen']), '<actual_selector>', 'eval')
        for training in [False, True]:
            for factual, q_enabled in [(True, True), (True, False), (False, True)]:
                self = SimpleNamespace(factual=factual, q_enabled=q_enabled)
                use = eval(control, {'training': training, 'self': self})
                chosen = eval(selector, {'training_q_control': use, 'old_action': 2, 'full_action': 6})
                assert chosen == (2 if training and factual and q_enabled else 6)
        checks['actual_selector_expression_training_only_hybrid_Q'] = True
        for name in ['world.py', 'repairs.py', 'map_binding.json']:
            assert (HERE/name).read_bytes() == (HERE.parent/'spatial_feedback_v183'/name).read_bytes()
        checks['world_repairs_maps_byte_identical'] = True
        for pin in json.loads((HERE/'control_binding.json').read_text(encoding='utf-8'))['files']:
            path = ROOT/pin['path']
            assert path.stat().st_size == pin['bytes']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == pin['sha256']
        checks['all_61_declared_stored_control_files_unchanged'] = True
        for name in ['learning.py', 'repairs.py', 'world.py', 'experiment.py', 'pilot.py']:
            ast.parse((HERE/name).read_text(encoding='utf-8'))
        contract = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))['matrix']
        assert contract['total_new_train_steps'] == 8*131072
        assert contract['total_new_evaluation_episodes'] == 8*(128*3+256+128*4)
        assert contract['new_environment_steps_upper'] == 1048576+9216*256
        checks['syntax_and_finite_budget'] = True
    except BaseException:
        error = traceback.format_exc()
    result = dict(exit_code=int(error is not None), error=error, checks=checks,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        environment_steps=0, optimizer_updates=0, old_native_or_checker_calls=0,
        limit='Static source intervention and expression checks, not an outcome experiment.')
    with (HERE/'pure_check_result.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
