"""Targeted pure check for future-action masking; zero environment/agent instances."""
import json
from pathlib import Path
import time
import numpy as np
import torch
from learning import continuation_max

start = time.perf_counter()
q = torch.arange(16, dtype=torch.float32).repeat(4, 1)
before = q.clone()
current_cd = np.array([0, 1, 2, 0])
commands = np.array([0, 0, 0, 8])
next_cd = np.maximum(0, np.where(commands >= 8, 32, current_cd)-1)
actual = continuation_max(q, next_cd).tolist()
assert actual == [15., 15., 7., 7.]
assert torch.equal(q, before)
result = dict(exit_code=0, cases=4, actual=actual, next_cooldown=next_cd.tolist(),
              environment_instances=0, rollouts=0, agents=0, experimental_RNG_draws=0,
              wall_seconds=time.perf_counter()-start,
              scope='Actual new helper arithmetic only, not an end-to-end matrix result')
with (Path(__file__).parent/'mask_check_result.json').open('x', encoding='utf-8') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
print(json.dumps(result))
