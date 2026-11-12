"""Public, non-game control tasks. Hidden dynamics stay in the executor."""
import hashlib
import math
import random
from feedback_program_v225 import FeedbackLayout, View

FAMILIES = ('stable', 'noisy', 'delayed', 'changing')
ACTIONS = ((1.,0.,0.,0.,0.,0.,0.,0.), (-1.,0.,0.,0.,0.,0.,0.,0.),
           (0.,1.,0.,0.,0.,0.,0.,0.), (0.,-1.,0.,0.,0.,0.,0.,0.), (0.,)*8)

def seed_for(*parts):
    return int.from_bytes(hashlib.sha256('|'.join(map(str, parts)).encode()).digest()[:8], 'little')

def layout():
    return FeedbackLayout(('sensor_x', 'sensor_y'), (
        View((('goal_met',0,1.),)), View((('next',0,1.),)),
        View((('next',0,1.),('observation',0,-1.))), View((),1.),
        View((('action_index',0,1.),)), View((('terminal',0,1.),)),
        View((('innovation',0,1.),)), View((('innovation',1,1.),))))

def distance(observation):
    return math.hypot(observation[0]-observation[2], observation[1]-observation[3])

def reward(observation, result, punishment):
    progress = distance(observation)-distance(result['next_observation'])
    positive = max(0., progress)+float(result['goal_met'])
    negative = max(0., -progress)+float(result['terminal'] and not result['goal_met'])
    return positive-negative if punishment else positive

class Task:
    def __init__(self, seed, split, index, horizon=6):
        self.seed=seed; self.split=split; self.index=index; self.horizon=horizon
        self.family=index%4; self.context=(index//4)%4; self.t=0
        rng=random.Random(seed_for(seed, split, index, 'initial'))
        self.x=[rng.uniform(-.4,.4), rng.uniform(-.4,.4)]
        self.target=[rng.choice((-.5,.5)), rng.choice((-.5,.5))]
        self.previous=(0.,0.); self.layout=layout()
        self.goal=tuple(self.target)+(1.,0.,0.,0.,0.,0.)
    def observation(self):
        family=[float(j==self.family) for j in range(4)]
        cue=(float(self.context%2),float(self.context//2))
        return tuple(self.x+self.target)+tuple(family)+cue+tuple(self.previous)+(self.t/self.horizon,1/self.horizon,0.,0.)
    def execute(self, action, branch=0):
        before=self.observation(); rng=random.Random(seed_for(self.seed,self.split,self.index,self.t,branch,'noise'))
        selected=ACTIONS[action][:2]
        u=self.previous if self.family==2 else selected
        angle=self.context*math.pi/2
        ux=round(math.cos(angle))*u[0]-round(math.sin(angle))*u[1]
        uy=round(math.sin(angle))*u[0]+round(math.cos(angle))*u[1]
        sign=-1. if self.family==3 and (self.index//16)%2 else 1.
        sigma=.07 if self.family==1 else .012
        noise=(rng.gauss(0,sigma),rng.gauss(0,sigma))
        self.x=[max(-1.5,min(1.5,self.x[0]+.25*sign*ux+noise[0])),
                max(-1.5,min(1.5,self.x[1]+.25*sign*uy+noise[1]))]
        self.previous=selected; self.t+=1; nxt=self.observation()
        terminal=self.t==self.horizon; met=terminal and distance(nxt)<=.30
        sensor=(self.x[0]+rng.gauss(0,.04),self.x[1]+rng.gauss(0,.04))
        mask=(rng.random()<.8,rng.random()<.8); visible=self.layout.visible_views(mask)
        raw=self.layout.render(nxt,sensor,float(met),float(terminal),before,ACTIONS[action],action)
        return dict(next_observation=nxt,feedback=tuple(v if m else 0. for v,m in zip(raw,visible)),
                    feedback_mask=visible,goal_met=met,terminal=terminal,cost=1.)
