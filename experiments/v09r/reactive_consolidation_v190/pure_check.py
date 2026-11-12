"""Target the actually observed legacy Replay schema mismatch; no world steps."""
import ast
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
from learning import Agent

HERE=Path(__file__).parent
ROOT=HERE.parents[2]


def digest_arrays(replay):
    return {k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in vars(replay).items() if isinstance(v,np.ndarray)}


def main():
    bindings=json.loads((HERE/'checkpoint_binding.json').read_text())['files']; checks=[]
    for arm in ('RL-RP','F0','F-RP'):
        p=next(p for p in bindings if p['seed']==93001 and p['arm']==arm)
        with gzip.open(ROOT/p['path'],'rb') as f: state=torch.load(f,map_location='cpu',weights_only=False)
        a=state['agent']; assert isinstance(a,Agent)
        before=digest_arrays(a.replay); weights=a.parameter_hash(); n=a.replay.n
        a.attach_feedback('base')
        after=digest_arrays(a.replay)
        assert all(after[k]==v for k,v in before.items()) and a.parameter_hash()==weights and a.replay.n==n
        assert set(after)-set(before)==(set() if arm=='F0' else {'future','future_mask'})
        if arm!='F0': assert not a.replay.future.any() and not a.replay.future_mask.any()
        # Exactly the previously failing append, on a disposable synthetic row.
        a.replay.append(np.zeros((5,21,21),np.uint8),np.zeros(184),np.zeros(28),0,0.,
            SimpleNamespace(captured=False,completed=False),np.zeros(10),np.zeros(10),np.ones(16,bool),True,0.)
        assert a.replay.n==n+1 and a.parameter_hash()==weights
        checks.append(dict(arm=arm,old_arrays_unchanged_before_synthetic_append=True,new_slots=list(set(after)-set(before)),synthetic_appends=1))
        del a,state
    old=HERE.parent/'reactive_consolidation_v189'
    for name in ('reaction.py','base_learning.py','world.py','future_facts.py','repairs.py'):
        assert (HERE/name).read_bytes()==(old/name).read_bytes()
    def methods(path):
        tree=ast.parse(path.read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Agent')
        return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef) and n.name!='attach_feedback'}
    assert methods(HERE/'learning.py')==methods(old/'learning.py')
    result=dict(exit_code=0,environment_steps=0,optimizer_updates=0,synthetic_appends=3,
        checks=checks,action_reaction_base_code_unchanged=True,
        previous_reaction_synthetic_checks_reused_not_rerun=True)
    with (HERE/'pure_check_result.json').open('x') as f: json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))


if __name__=='__main__':main()
