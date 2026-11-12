"""Static bound source check; no checkpoint loading or environment execution."""
import ast
import hashlib
import json
from pathlib import Path
import traceback

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
error=None
checks={}
try:
    base=HERE.parent/'auxiliary_isolation_v185'
    source=(base/'learning.py').read_text(encoding='utf-8')
    expected=source.replace("if len(self.nearest) and self.ablation != 'no_cross_episode_history_retrieval':",
        "if len(self.nearest) and self.ablation not in ('no_cross_episode_history_retrieval', 'no_empirical_override', 'H1_no_empirical_override'):")
    expected=expected.replace("self.stage() == 2 and self.ablation != 'H1_only'",
        "self.stage() == 2 and self.ablation not in ('H1_only', 'H1_no_empirical_override')")
    assert ast.dump(ast.parse(expected))==ast.dump(ast.parse((HERE/'learning.py').read_text(encoding='utf-8')))
    checks['only_two_declared_readout_switches']=True
    old=ast.parse((base/'experiment.py').read_text(encoding='utf-8'))
    new=ast.parse((HERE/'evaluation.py').read_text(encoding='utf-8'))
    for name in ['Capture','evaluate','write_json','utc']:
        get=lambda tree:next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name)
        assert ast.dump(get(old))==ast.dump(get(new))
    checks['capture_and_frozen_evaluation_AST_identical']=True
    for pin in json.loads((HERE/'control_binding.json').read_text(encoding='utf-8'))['files']:
        p=ROOT/pin['path'];assert p.stat().st_size==pin['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']
    checks['closed_sources_match']=True
    ast.parse((HERE/'run.py').read_text(encoding='utf-8'))
except BaseException:error=traceback.format_exc()
result=dict(exit_code=int(error is not None),error=error,checks=checks,environment_steps=0,training_steps=0)
with (HERE/'pure_check_result.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps(result,ensure_ascii=False),flush=True)
raise SystemExit(result['exit_code'])
