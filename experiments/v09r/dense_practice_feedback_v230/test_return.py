"""New return-label equation check only: zero real rollouts or optimizer calls."""
import json
import numpy as np
import torch
from core import packed,utility
from learning import Agent


torch.set_num_threads(1)
a=Agent('pursuit',269,'dense-random',None)
ob=(np.zeros((5,21,21),np.uint8),np.zeros(40,np.float32),np.ones(16,bool))
source=packed(ob,a.memory_bank.view());rows=[]
first=np.array([1/64,.1,0,0],np.float32)
last=np.array([1/64,0,0,0],np.float32)
a.append_transition(source,0,source,first,False,rows)
assert rows[0].actual_return is None and a.counts['actual_return_labels']==0
a.append_transition(source,1,source,last,True,rows)
assert rows[0].actual_return==utility('pursuit',first+last)
assert rows[1].actual_return==utility('pursuit',last)
assert a.counts['actual_return_labels']==2 and a.steps==0 and a.updates==0
print(json.dumps(dict(status='RETURN_EQUATION_CHECKED',targets=[r.actual_return for r in rows],
                     partial_tail_was_unlabelled=True,real_environment_steps=0,optimizer_calls=0)))
