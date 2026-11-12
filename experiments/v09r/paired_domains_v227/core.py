"""Compact, directly trainable action values and actual-event memory."""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'src'))

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj

P = module('pursuit_kernel_v227_import_v198', HERE.parent / 'overnight_five_arm_v198/world.py')
G = module('generic_physics_v227_import_v226', HERE.parent / 'eight_hour_comparison_v226/task.py')
GROUPS = ('RL-plain', 'RL-outer', 'F0', 'F-RP', 'F-R', 'N227')
HORIZONS = (1, 4, 16, 64)
MEMORY = 16
NODE = 101

def seed_for(*parts):
    return int.from_bytes(hashlib.sha256('|'.join(map(str, parts)).encode()).digest()[:8], 'little')

def write_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(path)

def fingerprint(net):
    h = hashlib.sha256()
    for k, v in net.state_dict().items():
        h.update(k.encode()); h.update(v.detach().cpu().numpy().tobytes())
    return h.hexdigest()

class Environment:
    """Only observe/step outputs are passed to learners; private state is executor-owned."""
    def __init__(self, domain, bank, seed, phase, index):
        self.domain = domain
        self.env = P.World(bank, seed, phase, index) if domain == 'pursuit' else G.Task(seed, phase, index)
        self.branch = 0
        self.done = False
        self.steps = 0
        self.pickups = 0
        self.success = False
        self.distance = None

    def observation(self):
        vector = np.zeros(40, np.float32)
        if self.domain == 'pursuit':
            ob = self.env.observe()
            vector[:32] = ob.scalar
            vector[32:36] = (.96, 10., 0., 0.)
            return ob.image.copy(), vector, ob.legal.copy()
        vector[:16] = self.env.observation()
        vector[32:36] = (0., 0., 1., 1.)
        return np.zeros((5,21,21), np.uint8), vector, np.arange(16) < 5

    def step(self, action):
        if self.domain == 'pursuit':
            _, f = self.env.step(action)
            self.done = f.captured or f.completed
            self.success = bool(f.completed)
            self.pickups += f.pickup
            facts = np.array((1/64, f.pickup/10, float(f.completed), 0.), np.float32)
            raw = dict(captured=bool(f.captured), completed=bool(f.completed), pickup=int(f.pickup), buff_pickup=int(f.buff_pickup))
        else:
            f = self.env.execute(action, branch=self.branch)
            self.done = bool(f['terminal']); self.success = bool(f['goal_met'])
            self.distance = G.distance(f['next_observation'])
            quality = 1/(1+self.distance) if self.done else 0.
            facts = np.array((1/64, 0., float(self.success), quality), np.float32)
            raw = dict(success=self.success, terminal=self.done, distance=self.distance,
                       feedback=list(f['feedback']), feedback_mask=list(f['feedback_mask']))
        self.steps += 1
        return self.observation(), facts, self.done, raw

    def result(self):
        return dict(steps=self.steps, success=self.success, score=1.5*self.steps+100*self.pickups if self.domain=='pursuit' else float(self.success),
                    distance=self.distance, pickups=self.pickups)

    def clone(self, noise_key=None):
        new = copy.copy(self)
        if self.domain == 'pursuit':
            new.env = copy.copy(self.env)
            for key in ('hero','treasures','treasure_alive','buffs','buff_ready','monsters'):
                setattr(new.env,key,getattr(self.env,key).copy())
            new.env.trajectory = [p.copy() for p in self.env.trajectory]
            if noise_key is not None:
                new.env.uniform = self.env.uniform.copy()
                new.env.uniform[self.env.t:] = np.random.default_rng(noise_key).random(new.env.uniform[self.env.t:].shape)
        else:
            new.env = copy.deepcopy(self.env)
            if noise_key is not None:
                new.branch = int(noise_key)
        return new

def reward(domain, facts, terminal, punishment):
    positive = .96*float(facts[0])+10*float(facts[1]) if domain=='pursuit' else float(facts[2]+facts[3])
    return positive - float(punishment and terminal and not facts[2])

def utility(domain, facts):
    return float(facts @ np.array((.96,10.,0.,0.) if domain=='pursuit' else (0.,0.,1.,1.)))

def node(ob, action, nxt, facts, done):
    a = np.eye(16,dtype=np.float32)[action]
    return np.concatenate((ob[1],a,nxt[1],facts,np.array([done],np.float32)))

def memory_array(nodes):
    data = np.zeros((MEMORY,NODE),np.float32)
    valid = np.zeros(MEMORY,bool)
    take = nodes[-MEMORY:]
    if take:
        data[-len(take):] = np.stack([x[1] for x in take]); valid[-len(take):] = True
    return data,valid

def packed(ob,nodes):
    mem,mask = memory_array(nodes)
    return (ob[0],ob[1],ob[2],mem,mask)

def tensors(rows):
    return tuple(torch.from_numpy(np.stack([r[i] for r in rows])) for i in range(5))

class Network(nn.Module):
    def __init__(self, width=128):
        super().__init__()
        self.image = nn.Sequential(nn.Conv2d(5,8,3,2),nn.ReLU(),nn.Conv2d(8,16,3,2),nn.ReLU(),nn.Flatten(),nn.Linear(256,width),nn.ReLU())
        self.vector = nn.Sequential(nn.Linear(40,width),nn.ReLU())
        self.current = nn.Sequential(nn.Linear(2*width,width),nn.ReLU())
        self.node_encoder = nn.Sequential(nn.Linear(NODE,width),nn.ReLU(),nn.Linear(width,width))
        self.query = nn.Linear(width,width,bias=False)
        self.key = nn.Linear(width,width,bias=False)
        self.null = nn.Parameter(torch.zeros(1,1,width))
        self.applicability = nn.Sequential(nn.Linear(2*width,width//2),nn.ReLU(),nn.Linear(width//2,1),nn.Sigmoid())
        self.fusion = nn.Sequential(nn.Linear(2*width,width),nn.ReLU(),nn.Linear(width,width),nn.ReLU())
        self.q = nn.Linear(width,16)
        self.action_embedding = nn.Embedding(16,width)
        self.facts = nn.Linear(width,3*len(HORIZONS)*4)
        self.effect = nn.Linear(width,16)

    def encode(self, image, vector, legal, memory, valid):
        current = self.current(torch.cat((self.image(image.float()),self.vector(vector)), -1))
        encoded = self.node_encoder(memory)
        encoded = torch.cat((encoded,self.null.expand(len(current),-1,-1)),1)
        valid = torch.cat((valid,torch.ones((len(current),1),dtype=torch.bool)),1)
        logits = torch.einsum('bd,bmd->bm',self.query(current),self.key(encoded))/current.shape[-1]**.5
        weights = logits.masked_fill(~valid,-1e9).softmax(-1)
        read = torch.einsum('bm,bmd->bd',weights,encoded)
        gate = self.applicability(torch.cat((current,read),-1))
        z = self.fusion(torch.cat((current,gate*read),-1)) + current
        return z,weights,gate

    def forward(self, batch, detach_facts=True):
        z,w,g = self.encode(*batch)
        fact_z = z.detach() if detach_facts else z
        h = F.gelu(fact_z[:,None,:]+self.action_embedding.weight[None])
        m = self.facts(h).reshape(len(z),16,3,len(HORIZONS),4)
        return dict(q=self.q(z),measurements=m,effect=self.effect(z.detach()),attention=w,gate=g)

def action_scores(out, group, vector):
    if group != 'F0':
        return out['q']
    return (out['measurements'].mean(2)[:,:,-1].clamp(0,1)*vector[:,None,32:36]).sum(-1)

def count_parameters(net):
    total = sum(p.numel() for p in net.parameters())
    counts = {prefix:sum(p.numel() for n,p in net.named_parameters() if n.split('.')[0]==prefix)
              for prefix in ('q','facts','effect','action_embedding')}
    # All groups genuinely use the full encoder and memory path.
    inactive = {'RL-plain':counts['facts']+counts['action_embedding']+counts['effect'],
                'RL-outer':counts['facts']+counts['action_embedding']+counts['effect'],
                'F0':counts['q']+counts['effect'], 'F-RP':counts['effect'], 'F-R':counts['effect'], 'N227':0}
    return dict(total=total,output_heads=counts,inactive=inactive,active={g:total-inactive[g] for g in GROUPS})
