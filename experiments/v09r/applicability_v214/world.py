"""New one-action contextual environments. Hidden rules never enter learner constructors."""
import random
from feedback_program_v210.network import Fact

FAMILIES=('stable_novel','changed_novel','selective_change','noise')
ARMS=('pooled_history','fresh_only','temporal_v210','global_gate','conditional_gate')
CHECKPOINTS=(0,16,64,128,256)


def specification(family,seed):
    permutation=random.Random(2144000+seed).sample(range(3),3)
    return {'family':family,'seed':seed,'payload':permutation[0],'condition':permutation[1],'nuisance':permutation[2]}


def tape(spec,phase,slot,checkpoint=0):
    family=spec['family'];code=0 if family in FAMILIES[:2] else FAMILIES.index(family)
    phase_number={'history':0,'train':1,'eval':2}[phase]
    number=((code*100+spec['seed'])*3+phase_number)*1000000+checkpoint*1000+slot
    rng=random.Random(214100000000+number)
    x=[rng.randrange(2) for _ in range(3)]
    if family in FAMILIES[:2]:x[spec['condition']]=0 if phase=='history' else 1
    return {'context':tuple(x),'action_u':rng.random(),'outcome_u':rng.random()}


class World:
    def __init__(self,spec):self.spec=spec;self.interactions=0

    def run(self,scene,phase,observation_id,behavior,policy_id):
        # One action/outcome transition; three input fields are not three steps.
        x=scene['context'];a=int(scene['action_u']<behavior[1])
        desired=x[self.spec['payload']]
        if phase!='history':
            if self.spec['family']=='changed_novel':desired^=1
            elif self.spec['family']=='selective_change':desired^=x[self.spec['condition']]
        probability=.5 if self.spec['family']=='noise' else .9 if a==desired else .1
        y=int(scene['outcome_u']<probability)
        self.interactions+=1
        return Fact(observation_id,x,a,y,behavior[a],policy_id)
