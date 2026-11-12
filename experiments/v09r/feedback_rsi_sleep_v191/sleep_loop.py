"""Real history -> learned rehearsal policy -> temporary teacher -> persistent student.

The replay tree contains executed optimization branches, never unobserved game
outcomes. Its loss feedback is meta-training data, not a final evaluation score.
"""
import copy
import hashlib
import numpy as np
import torch
from torch.nn import functional as F
from base_learning import CAPACITY
from world import rng_for


def state_hash(net):
    h = hashlib.sha256()
    for value in net.state_dict().values():
        h.update(value.detach().cpu().numpy().tobytes())
    return h.hexdigest()


class HistoryPolicy:
    """Small learned policy, not an action ban or a hand-coded diagnosis."""
    def __init__(self):
        self.theta = np.zeros(3, np.float64)
        self.history = []

    def proposals(self, rng):
        # Re-evaluate only recorded rehearsal outcomes; no new outcome invented.
        if len(self.history) >= 4:
            x = np.array([[1., *r['theta']] for r in self.history])
            y = np.array([r['relative_gain'] for r in self.history])
            beta = np.linalg.solve(x.T@x + np.eye(4), x.T@y)
            direction = beta[1:]
        else:
            beta, direction = np.zeros(4), np.zeros(3)
        if np.linalg.norm(direction) < 1e-12:
            direction = rng.normal(size=3)
        direction = direction / np.linalg.norm(direction)
        return [self.theta.copy(), self.theta+.75*direction,
                self.theta-.75*direction, np.zeros(3)], beta

    def observe(self, candidates, chosen):
        self.history.extend({k: c[k] for k in ('cycle','branch','theta','relative_gain','probe_loss')}
                            for c in candidates)
        if chosen is not None:
            self.theta = np.array(candidates[chosen]['theta'], np.float64)


def arrays(agent, starts):
    r = agent.replay
    indices = (starts[:, None]+np.arange(25)) % CAPACITY
    return (indices, torch.from_numpy(r.image[indices].astype(np.float32)),
            torch.from_numpy(r.scalar[indices].astype(np.float32)),
            torch.from_numpy(r.reset[indices].astype(np.float32)))


def factual_output(raw):
    return torch.cat((torch.tanh(raw[..., :6]), F.softplus(raw[..., 6:7]),
                      torch.sigmoid(raw[..., 7:10])), -1)


def measurement_action(net, hidden, action):
    out = []
    for head in net.measurements:
        all_actions = head(hidden)
        out.append(all_actions.gather(-3, action[...,None,None,None].expand(
            *action.shape,1,4,2)).squeeze(-3))
    return out


@torch.no_grad()
def proxy(agent, starts, reference, target_reference):
    """Comparable, fixed-target feedback on real records; no imagined rollouts."""
    results = []
    for offset in range(0, len(starts), 16):
        ids, images, scalars, resets = arrays(agent, starts[offset:offset+16])
        ii = ids[:,8:24]
        h = agent.net.unroll(images, scalars, resets)[:,8:24]
        actions = torch.from_numpy(agent.replay.action[ii].astype(np.int64))
        components = []
        if agent.q_enabled:
            ref = reference.unroll(images, scalars, resets)[:,9:25]
            online = reference.q(ref)
            legal_next = torch.from_numpy(agent.replay.legal[ids[:,9:25]])
            online[~legal_next] = -1e9
            best = online.argmax(-1)
            target_h = target_reference.unroll(images, scalars, resets)[:,9:25]
            target_q = target_reference.q(target_h).gather(-1,best[...,None]).squeeze(-1)
            done = torch.from_numpy(agent.replay.done[ii].astype(np.float32))
            y = torch.from_numpy(agent.replay.reward[ii]) + .99*(1-done)*target_q
            pred = agent.net.q(h).gather(-1, actions[...,None]).squeeze(-1)
            components.append(F.smooth_l1_loss(pred,y,reduction='none').mean(-1))
        if agent.factual:
            inputs = torch.cat((h,F.one_hot(actions,16).float()),-1)
            targets = torch.from_numpy(agent.replay.target[ii])
            masks = torch.from_numpy(agent.replay.target_mask[ii])
            losses = []
            for head in agent.net.heads:
                raw = head(inputs)
                error = ((factual_output(raw)-targets)**2*masks).sum((-1,-2))/masks.sum((-1,-2)).clamp_min(1)
                cap = F.binary_cross_entropy_with_logits(raw[...,7],targets[...,7],reduction='none').mean(-1)
                losses.append(error+cap)
            components.append(torch.stack(losses).mean(0))
        if not agent.q_enabled:
            target = torch.from_numpy(agent.replay.future[ii])
            valid = torch.from_numpy(agent.replay.future_mask[ii])
            errors = []
            for pred in measurement_action(agent.net,h,actions):
                e = F.smooth_l1_loss(pred,target,reduction='none').mean(-1)
                errors.append((e*valid).sum((-1,-2))/valid.sum((-1,-2)).clamp_min(1))
            components.append(torch.stack(errors).mean(0))
        results.append(torch.stack(components).mean(0).numpy())
    return np.concatenate(results).astype(np.float64)


def distillation(agent, hidden, images, scalars, resets, ii, actions):
    """Distil only recorded actions and actually observed component extents.

    Soft teacher predictions are separately identified, never written as facts.
    The ordinary real-label objective remains present on the student update.
    """
    teacher = agent._sleep_teacher
    h = hidden[:,8:24]
    with torch.no_grad():
        th = teacher.unroll(images,scalars,resets)[:,8:24]
    losses = []
    if agent.q_enabled:
        pred = agent.net.q(h).gather(-1,actions[...,None]).squeeze(-1)
        with torch.no_grad():
            target = teacher.q(th).gather(-1,actions[...,None]).squeeze(-1)
        losses.append(F.smooth_l1_loss(pred,target))
    if agent.factual:
        onehot = F.one_hot(actions,16).float()
        inputs = torch.cat((h.detach(),onehot),-1)
        masks = torch.from_numpy(agent.replay.target_mask[ii])
        for head, teacher_head in zip(agent.net.heads,teacher.heads):
            with torch.no_grad(): target = factual_output(teacher_head(torch.cat((th,onehot),-1)))
            error = (factual_output(head(inputs))-target)**2
            losses.append((error*masks).sum()/masks.sum().clamp_min(1)/3)
    if not agent.q_enabled:
        valid = torch.from_numpy(agent.replay.future_mask[ii])[...,None]
        with torch.no_grad(): targets = measurement_action(teacher,th,actions)
        for pred,target in zip(measurement_action(agent.net,h,actions),targets):
            losses.append((F.smooth_l1_loss(pred,target,reduction='none')*valid).sum()/
                          (valid.sum()*2).clamp_min(1)/3)
    return sum(losses)


def make_pools(agent, cycle):
    """Disjoint record windows, fixed independently of outcomes.

    These are training-history probe labels, not fresh independent episodes.
    """
    rng = rng_for(agent.seed,'v191-pools',cycle)
    lo, hi = max(0,agent.replay.n-CAPACITY),agent.replay.n-25
    all_starts = np.arange(lo, hi+1, dtype=np.int64)
    pos = all_starts % 1024
    fitting = all_starts[(pos>=280)&(pos<=999)]
    probing = all_starts[pos<=231]
    split = agent.replay.n-4096
    train = np.concatenate([rng.choice(fitting[fitting<split],384,replace=False),
                            rng.choice(fitting[fitting>=split],128,replace=False)])
    probe = np.concatenate([rng.choice(probing[probing<split],32,replace=False),
                            rng.choice(probing[probing>=split],32,replace=False)])
    # Input and label sequence rows never overlap between candidate fit and probe.
    assert not np.intersect1d((train[:,None]+np.arange(25)).ravel(),
                             (probe[:,None]+np.arange(25)).ravel()).size
    return train, probe


def run_sleep(agent, cycle):
    parent = copy.deepcopy(agent.net)
    parent_opt = copy.deepcopy(agent.optimizer.state_dict())
    target = copy.deepcopy(agent.target_net) if agent.target_net is not None else None
    train, probe = make_pools(agent,cycle)
    before_probe = proxy(agent,probe,parent,target)
    surprise = proxy(agent,train,parent,target)
    recency = (train-agent.replay.n)/CAPACITY
    counts = np.bincount(agent.replay.action[(train+8)%CAPACITY],minlength=16)
    rarity = 1/np.sqrt(counts[agent.replay.action[(train+8)%CAPACITY]])
    features = np.stack([surprise,recency,rarity],-1)
    features = (features-features.mean(0))/(features.std(0)+1e-8)
    features = np.clip(features,-4,4)
    rng = rng_for(agent.seed,'v191-sleep',cycle)
    parent_hash = state_hash(parent)
    updates_before = agent.counters['v191_optimizer_updates']
    candidates, states, fitting_log = [], [], []
    previous_theta = agent.history_policy.theta.copy()

    def probabilities(theta):
        logits = features@theta
        p = np.exp(logits-logits.max()); p /= p.sum()
        return .1/len(p)+.9*p

    def update(theta, branch, step):
        p = probabilities(theta)
        chosen = rng.choice(len(train),16,replace=True,p=p)
        agent._selected_starts = train[chosen]
        agent.learn()
        fitting_log.append(dict(branch=branch,step=step,starts=agent._selected_starts.tolist(),
            probabilities=p[chosen].tolist(),loss=agent.last_loss,distillation=agent.last_distillation))

    selected = None
    if agent.variant == 'matched_replay':
        beta = np.zeros(4)
        for step in range(24): update(np.zeros(3),'direct',step)
    else:
        proposals,beta = agent.history_policy.proposals(rng)
        baseline = float(before_probe.mean())
        for b,theta in enumerate(proposals):
            agent.net.load_state_dict(parent.state_dict())
            agent.optimizer.load_state_dict(copy.deepcopy(parent_opt))
            for step in range(4): update(theta,b,step)
            value = proxy(agent,probe,parent,target)
            states.append(copy.deepcopy(agent.net.state_dict()))
            candidates.append(dict(cycle=cycle,branch=b,theta=theta.tolist(),
                probe_loss=float(value.mean()),probe_old=float(value[:32].mean()),
                probe_recent=float(value[32:].mean()),
                relative_gain=(baseline-float(value.mean()))/max(baseline,1e-12),
                parent_hash=parent_hash,teacher_hash=state_hash(agent.net)))
        best = min(range(4),key=lambda i:candidates[i]['probe_loss'])
        selected = best if candidates[best]['probe_loss'] < baseline else None
        agent.history_policy.observe(candidates,selected)
        teacher = copy.deepcopy(parent)
        if selected is not None: teacher.load_state_dict(states[selected])
        teacher.requires_grad_(False)
        agent.net.load_state_dict(parent.state_dict())
        agent.optimizer.load_state_dict(copy.deepcopy(parent_opt))
        agent._sleep_teacher = teacher
        for step in range(8): update(agent.history_policy.theta,'student',step)
        agent._sleep_teacher = None
    agent._selected_starts = None
    after = proxy(agent,probe,parent,target)
    report = dict(cycle=cycle,variant=agent.variant,training_step=agent.training_steps,
        train_windows=train.tolist(),probe_windows=probe.tolist(),
        features=features.tolist(),feature_names=['own_error','recency','action_rarity'],
        before_probe=float(before_probe.mean()),after_probe=float(after.mean()),
        before_old=float(before_probe[:32].mean()),after_old=float(after[:32].mean()),
        before_recent=float(before_probe[32:].mean()),after_recent=float(after[32:].mean()),
        previous_theta=previous_theta.tolist(),next_theta=agent.history_policy.theta.tolist(),
        historical_gain_model=beta.tolist(),candidates=candidates,selected=selected,
        history_records=len(agent.history_policy.history),parent_hash=parent_hash,
        student_hash=agent.parameter_hash(),updates=agent.counters['v191_optimizer_updates']-updates_before,
        fitting_log=fitting_log)
    assert report['updates']==24
    assert agent.parameter_hash()!=parent_hash
    return report,dict(parent=parent.state_dict(),teachers=states,student=copy.deepcopy(agent.net.state_dict()))
