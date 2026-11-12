"""Mechanical, prospective source transports and six one-defect test variants.

Run before the exclusive capture. It neither imports nor executes an old test.
The generated normal TD functions have the exact AST of the original functions.
Each mutant is a physical source file, independently loaded under its own name.
"""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
V95 = HERE.parent / 'owned_curve_connector_v95'
VARIANTS = ('normal', 'post_address', 'proposal_option', 'floor_draw',
            'immediate_write', 'remeasure_pre', 'different_stream')


def replace_once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def main():
    assert not (HERE / 'evidence').exists(), 'capture already started'
    original = ROOT / 'src/rfl_rebuild/b2/training.py'
    text = original.read_text(encoding='utf-8')
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    names = ('uniform_action', 'visited_order', 'sweep_edits')
    functions = {n.name: ''.join(lines[n.lineno-1:n.end_lineno])
                 for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names}
    td = ('"""Exact original TD/draw function transport; physical mutation test seam."""\n'
          'from rfl_rebuild.b2.training import (ExogenousEpisode, FutureTrainingProtocol, '
          'ProtocolError, MAX_REJECTION, effective_value)\n'
          'from rfl_rebuild.env.kernel import (Action, START, State, initial_control, option_actions)\n'
          'from rfl_rebuild.learner.store import Q, QAddress, Edit\n\n' +
          '\n\n'.join(functions[n] for n in names) + '\n')
    manifest = {'schema': 'V104_PROSPECTIVE_PHYSICAL_SOURCE_MUTANTS',
                'parent_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'normal_functions_ast_equal_original': {}, 'variants': {}}
    normal_ast = ast.parse(td)
    for name in names:
        old = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        new = next(n for n in normal_ast.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False)
        manifest['normal_functions_ast_equal_original'][name] = True
    for variant in VARIANTS:
        prefix = 'v104_' + variant
        learning = (V95 / 'learning.py').read_text(encoding='utf-8')
        learning = replace_once(learning, 'import adaptive_training as A',
                                'import adaptive_training as A\nimport ' + prefix + '_td as TD')
        learning = learning.replace('T.uniform_action(', 'TD.uniform_action(').replace(
            'T.sweep_edits(', 'TD.sweep_edits(').replace('T.visited_order(', 'TD.visited_order(')
        curve = (V95 / 'owned_curve.py').read_text(encoding='utf-8').replace(
            'from learning import ', 'from ' + prefix + '_learning import ')
        external = (V95 / 'external.py').read_text(encoding='utf-8').replace(
            'import owned_curve\n', 'import ' + prefix + '_curve as owned_curve\n')
        altered_td = td
        if variant == 'post_address':
            altered_td = replace_once(td,
                'q_j = QAddress(state=state_j, z=control_j.z, m=control_j.m, a=result.a_cmd)',
                'q_j = QAddress(state=result.state, z=control_j.z, m=control_j.m, a=result.a_cmd)')
        elif variant == 'proposal_option':
            altered_td = replace_once(td, 'control = initial_control(trace.option_in_force)',
                                      'control = initial_control(trace.base_option)')
        elif variant == 'floor_draw':
            node = next(n for n in ast.parse(td).body if isinstance(n, ast.FunctionDef) and n.name == 'uniform_action')
            src = td.splitlines(keepends=True)
            src[node.lineno-1:node.end_lineno] = [
                'def uniform_action(episode, i, admissible):\n'
                '    ordered = tuple(sorted(admissible))\n'
                '    return ordered[(episode.chi(i, 1, 0) * len(ordered)) >> 64]\n']
            altered_td = ''.join(src)
        elif variant == 'immediate_write':
            learning = replace_once(learning, '        self._completed += 1',
                '        if self.mode == "dq":\n'
                '            self._immediate.apply_transaction(edits, q_reference=self.reference)\n'
                '        elif actor_edits:\n'
                '            self._immediate.apply_transaction(tuple(actor_edits))\n'
                '        self._completed += 1')
        elif variant == 'remeasure_pre':
            curve = replace_once(curve, 'import adaptive_training as A',
                                 'import adaptive_training as A\nfrom rfl_rebuild.b2 import training as T')
            curve = replace_once(curve, '_PROGRESS = WeakKeyDictionary()',
                                 '_PROGRESS = WeakKeyDictionary()\n_ARM_PRE = {}')
            curve = replace_once(curve, '            checkpoints, training = [], []',
                '            _ARM_PRE[(bundle, role)] = T.pre_level(d.plan.evaluation_sample, q_reference=actor.reference)\n'
                '            checkpoints, training = [], []')
            curve = replace_once(curve, 'return checkpoints, d.plan.v_pre, d.plan.t_max',
                                 'return checkpoints, _ARM_PRE[(bundle, role)], d.plan.t_max')
        elif variant == 'different_stream':
            curve = replace_once(curve, 'receipt = actor.train_episode(d.plan.episode(e))',
                'stream = d.plan.episode(e)\n'
                '                    if role == "treatment":\n'
                '                        inp = stream._input\n'
                '                        stream._input = EngineeringEpisode(inp.epoch, inp.kappa, inp.proposal, inp.tape,\n'
                '                            tuple(x ^ 1 for x in inp.coins), inp.rejections)\n'
                '                    receipt = actor.train_episode(stream)')
        folder = HERE / 'variants' / variant
        folder.mkdir(parents=True, exist_ok=False)
        sources = {'td.py': altered_td, 'learning.py': learning, 'owned_curve.py': curve, 'external.py': external}
        pins = {}
        for name, source in sources.items():
            ast.parse(source)  # syntax only, no import/execution
            path = folder / name
            with path.open('x', encoding='utf-8', newline='\n') as stream:
                stream.write(source)
            pins[name] = {'path': path.relative_to(ROOT).as_posix(),
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
        manifest['variants'][variant] = pins
    with (HERE / 'variant_manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
    print(json.dumps({'variants': len(VARIANTS), 'physical_sources': 4*len(VARIANTS),
                      'normal_TD_AST_equal': manifest['normal_functions_ast_equal_original']}))


if __name__ == '__main__':
    main()
