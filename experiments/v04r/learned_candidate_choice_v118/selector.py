"""Two-action tabular candidate value learning from actual branch returns.

The representation and candidate grammar are fixed before execution. No cause
truth, scenario label, context ID or Q* target enters the feature map. This is
not a full causal attribution model: it learns consequences of keeping versus
clearing the factual decision entries, under this small declared task family.
"""
from dataclasses import dataclass

from candidate_loop import Proposal
from rfl_rebuild.env.kernel import State
from rfl_rebuild.learner.store import Q, DECISION, QAddress, DecisionAddress, Edit

ACTIONS = ('keep', 'clear_factual')

def feature(mode, terminal, evidence):
    return (mode, terminal, any(s.a_cmd != s.a_realized for s in evidence.steps))

def candidate(mode, evidence, action):
    if action == 'keep':
        return Proposal()
    if action != 'clear_factual':
        raise ValueError('unknown candidate')
    edits=[];seen=set()
    for s in evidence.steps:
        st=State(s.x,s.y,s.t,s.kappa,s.phi)
        address=QAddress(st,s.z,s.m,s.a_cmd) if mode=='dq' else DecisionAddress(st,s.z,s.m)
        if address not in seen:
            edits.append(Edit(Q if mode=='dq' else DECISION,address,None))
            seen.add(address)
    return Proposal('apply',tuple(edits))

class ValueTrainer:
    def __init__(self):
        self.samples={}

    def observe(self, key, action, returns):
        if action not in ACTIONS or not returns:
            raise ValueError('candidate and actual continuation returns required')
        self.samples.setdefault((key,action),[]).extend(float(x) for x in returns)

    def freeze(self):
        return FrozenValueSelector(tuple((key,action,len(values),sum(values)/len(values))
                    for (key,action),values in sorted(self.samples.items())))

@dataclass(frozen=True, slots=True)
class FrozenValueSelector:
    table: tuple

    def choose(self, mode, terminal, evidence):
        key=feature(mode,terminal,evidence)
        scores={action:mean for k,action,count,mean in self.table if k==key and count>0}
        # Missing coverage is explicitly unknown, not an invented value. Ties
        # choose keep. No fitted significance margin or effect-based tuning.
        if set(scores)!=set(ACTIONS):
            return 'keep',{'feature':key,'scores':scores,'unknown':True}
        action='clear_factual' if scores['clear_factual']>scores['keep'] else 'keep'
        return action,{'feature':key,'scores':scores,'unknown':False}
