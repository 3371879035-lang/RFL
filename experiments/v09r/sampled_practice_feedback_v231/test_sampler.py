"""New stochastic-allocation formula only; no environment or optimizer calls."""
import json
import numpy as np
import torch
from learning import proposal_probabilities

torch.set_num_threads(1)
valid=torch.zeros((2,16),dtype=torch.bool);valid[0,:7]=True;valid[1,:15]=True
gain=torch.zeros((2,16))
p=proposal_probabilities(gain,valid).reshape(2,16)
assert np.allclose(p.sum(-1),[.5,.5])
assert np.all(p[valid.numpy()]>0) and np.all(p[~valid.numpy()]==0)
gain[0,0]=1.
new=proposal_probabilities(gain,valid).reshape(2,16)
assert new[0,0]>p[0,0] and np.all(new[valid.numpy()]>0)
print(json.dumps(dict(status='STOCHASTIC_ALLOCATION_EQUATION_CHECKED',
    zero_gain_source_mass=p.sum(-1).tolist(),increased_gain_probability=float(new[0,0]),
    all_legal_candidates_retain_mass=True,environment_steps=0,optimizer_calls=0)))
