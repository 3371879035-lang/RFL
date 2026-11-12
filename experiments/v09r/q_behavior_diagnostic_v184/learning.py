"""Own real replay, recurrent Double-Q, factual prediction, and bounded readout."""
import copy
from collections import deque
import hashlib
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from world import DIR, rng_for, seed_for
from repairs import bootstrap_mask, successor, transition_loss

ARMS = ('RL-RP', 'F0', 'F-RP', 'F-R')
SCALARS = 184
CAPACITY = 65536


def continuation_max(q, cooldown):
    masked = q.clone()
    ready = torch.as_tensor(cooldown, dtype=torch.long) == 0
    masked[:, 8:] = torch.where(ready[:, None], masked[:, 8:], -1e9)
    return masked.max(-1).values


class Network(nn.Module):
    def __init__(self, seed, factual, q_enabled):
        super().__init__()
        torch.manual_seed(seed_for(seed, 'common-encoder') % (2**63-1))
        self.conv = nn.Sequential(nn.Conv2d(5, 16, 3, 2), nn.ReLU(),
                                  nn.Conv2d(16, 32, 3, 2), nn.ReLU(), nn.Flatten())
        self.projection = nn.Linear(512+SCALARS, 128)
        self.gru = nn.GRUCell(128, 64)
        if q_enabled:
            torch.manual_seed(seed_for(seed, 'common-Q') % (2**63-1))
            self.q = nn.Linear(64, 16)
        else:
            self.q = None
        if factual:
            heads = []
            for j in range(3):
                torch.manual_seed(seed_for(seed, 'common-fact', j) % (2**63-1))
                heads.append(nn.Sequential(nn.Linear(80, 64), nn.Tanh(), nn.Linear(64, 74)))
            self.heads = nn.ModuleList(heads)
        else:
            self.heads = None

    def embedding(self, images, scalars):
        return torch.tanh(self.projection(torch.cat((self.conv(images), scalars), dim=-1)))

    def unroll(self, images, scalars, resets):
        b, t = images.shape[:2]
        z = self.embedding(images.flatten(0, 1), scalars.flatten(0, 1)).reshape(b, t, 128)
        h, sequence = torch.zeros(b, 64), []
        for k in range(t):
            h = self.gru(z[:, k], h*(1-resets[:, k:k+1]))
            if k == 7:
                h = h.detach()
            sequence.append(h)
        return torch.stack(sequence, dim=1)


class Replay:
    def __init__(self):
        self.n = 0
        self.image = np.zeros((CAPACITY, 5, 21, 21), np.uint8)
        self.scalar = np.zeros((CAPACITY, SCALARS), np.float16)
        self.key = np.zeros((CAPACITY, 28), np.float16)
        self.action = np.zeros(CAPACITY, np.uint8)
        self.reward = np.zeros(CAPACITY, np.float32)
        self.done = np.zeros(CAPACITY, bool)
        self.reset = np.zeros(CAPACITY, bool)
        self.legal = np.zeros((CAPACITY, 16), bool)
        self.target = np.zeros((CAPACITY, 10), np.float32)
        self.target_mask = np.zeros((CAPACITY, 10), np.float32)
        self.forecast = np.zeros(CAPACITY, np.float32)

    def append(self, image, scalar, key, action, reward, fact, target, mask, legal, reset, forecast):
        uid, i = self.n, self.n % CAPACITY
        self.image[i], self.scalar[i], self.key[i] = image, scalar, key
        self.action[i], self.reward[i] = action, reward
        self.done[i], self.reset[i], self.legal[i] = fact.captured or fact.completed, reset, legal
        self.target[i], self.target_mask[i], self.forecast[i] = target, mask, forecast
        self.n += 1
        return uid


class Agent:
    def __init__(self, seed, arm, stage_override=None):
        self.seed, self.arm = seed, arm
        self.factual, self.q_enabled = arm != 'RL-RP', arm != 'F0'
        self.penalty = 1 if arm in ('RL-RP', 'F-RP') else 0
        self.net = Network(seed, self.factual, self.q_enabled)
        self.target_net = copy.deepcopy(self.net) if self.q_enabled else None
        if self.target_net is not None:
            self.target_net.requires_grad_(False)
        self.optimizer = torch.optim.Adam(self.net.parameters(), lr=3e-4)
        self.replay = Replay()
        self.training_steps = 0
        self.stage_override = stage_override
        self.recent_errors = deque(maxlen=512)
        self.replay_rng = rng_for(seed, 'real-replay')
        self.counters = dict(policy=0, retrieval=0, retrieved_records=0, model_edges=0,
                             head_evaluations=0, deep_H4=0, deep_H8=0,
                             Q_updates=0, fact_updates=0, real_replay_labels=0,
                             reward_packets=0, factual_mse_sum=0., factual_brier_sum=0.,
                             factual_predictions=0, factual_action_changes=0,
                             bootstrap_selected_0=0, bootstrap_selected_1=0, bootstrap_selected_2=0,
                             bootstrap_positions=0, transition_weight=0., transition_model_mse_sum=0.,
                             transition_identity_mse_sum=0., transition_value_loss_sum=0.)
        self.reset_episode('train', 0)

    def stage(self):
        if self.stage_override is not None:
            return self.stage_override
        return 0 if self.training_steps < 16384 else 1 if self.training_steps < 65536 else 2

    def reset_episode(self, phase, episode):
        self.h = torch.zeros(1, 64)
        self.atlas = np.full((64, 64), -1, np.int8)
        self.local_t = 0
        self.last_action = self.last_pickup = 0
        self.retrieval_summary = np.zeros(24, np.float32)
        self.nearest = np.empty(0, np.int64)
        self.episode_rows = []
        self.action_uniform = rng_for(self.seed, phase, episode, 'physical-action').random((256, 2))
        self.candidate_uniform = rng_for(self.seed, phase, episode, 'model-candidates').random((256, 3, 16, 8))
        self.deep_window_used = -1
        self.ablation = getattr(self, 'ablation', None)

    def _features(self, obs):
        x, z = obs.hero
        x0, x1, z0, z1 = max(0, x-10), min(64, x+11), max(0, z-10), min(64, z+11)
        self.atlas[z0:z1, x0:x1] = obs.local_roads[z0-z+10:z1-z+10, x0-x+10:x1-x+10]
        scalar = obs.scalar.copy()
        scalar[28:32] = self.last_action/15, self.last_pickup/10, 0, self.stage()/2
        key = scalar[:28].copy()
        if self.stage() >= 1 and self.ablation != 'no_cross_episode_history_retrieval' and self.local_t % 8 == 0:
            n = min(self.replay.n, CAPACITY)
            if n:
                uids = np.linspace(max(0, self.replay.n-CAPACITY), self.replay.n-1,
                                   min(128, n), dtype=np.int64)
                indices = uids % CAPACITY
                # Absolute hero location, map identity, seed and score are not retrieval keys.
                distance = np.mean((self.replay.key[indices, 2:].astype(np.float32)-key[2:])**2, axis=1)
                nearest = indices[np.argsort(distance, kind='stable')[:8]]
                summary = np.zeros(24, np.float32)
                summary[:16] = np.bincount(self.replay.action[nearest], minlength=16)/len(nearest)
                summary[16:18] = self.replay.target[nearest, :2].mean(axis=0)
                summary[18] = self.replay.target[nearest, 6].mean()
                summary[19] = self.replay.target[nearest, 7].mean()
                summary[20:22] = self.replay.target[nearest, :2].std(axis=0)
                summary[22:24] = len(nearest)/8, min(n, CAPACITY)/CAPACITY
                self.retrieval_summary, self.nearest = summary, nearest
                self.counters['retrieval'] += 1
                self.counters['retrieved_records'] += len(nearest)
        known = (self.atlas >= 0).reshape(8, 8, 8, 8).mean(axis=(1, 3))
        roads = (self.atlas == 1).reshape(8, 8, 8, 8).mean(axis=(1, 3))
        features = np.concatenate((scalar, known.ravel(), roads.ravel(), self.retrieval_summary)).astype(np.float32)
        return features, key

    @staticmethod
    def _decode(raw, h):
        output = raw.detach().numpy()
        clipped = np.clip(output[..., 7:10], -20, 20)
        probabilities = 1/(1+np.exp(-clipped))
        pickup = np.logaddexp(0, output[..., 6])
        latent = successor(h, raw[..., 10:])
        return output, probabilities, pickup, latent

    def _root(self, latent, legal, cooldown):
        n = len(legal)
        hs = latent.expand(n, -1)
        acts = F.one_hot(torch.as_tensor(legal, dtype=torch.long), 16).float()
        raw = torch.stack([head(torch.cat((hs, acts), -1)) for head in self.net.heads])
        values = []
        predicted = []
        for j in range(3):
            output, prob, pickup, next_h = self._decode(raw[j], hs)
            if self.q_enabled:
                next_cd = np.maximum(0, np.where(legal >= 8, 32, cooldown)-1)
                tail = continuation_max(self.net.q(next_h), next_cd).numpy()
                score = .015+pickup-self.penalty*prob[:, 0]+.99*(1-prob[:, 0])*tail
            else:
                score = .015+pickup+.015*256*prob[:, 1]+10*prob[:, 2]
            values.append(score)
            predicted.append((output, prob, pickup, next_h))
        # Retrieved empirical facts alter model predictions, never impose global bans.
        if len(self.nearest) and self.ablation != 'no_cross_episode_history_retrieval':
            for k, action in enumerate(legal):
                support = self.nearest[self.replay.action[self.nearest] == action]
                if len(support):
                    w = len(support)/(len(support)+8.)
                    empirical_capture = (1+self.replay.target[support, 7].sum())/(2+len(support))
                    empirical_pickup = self.replay.target[support, 6].mean()
                    for j in range(3):
                        _, prob, pickup, _ = predicted[j]
                        values[j][k] += w*(empirical_pickup-pickup[k]-self.penalty*(empirical_capture-prob[k, 0]))
        self.counters['model_edges'] += n
        self.counters['head_evaluations'] += n*3
        return np.stack(values), predicted

    def _lookahead(self, latent, legal, root_scores, root_predictions, obs):
        n = len(legal)
        hs = [latent.expand(n, -1).clone() for _ in range(3)]
        actions = [legal.copy() for _ in range(3)]
        positions = [np.repeat(np.array(obs.hero)[None, :], n, axis=0) for _ in range(3)]
        active = [np.ones(n, bool) for _ in range(3)]
        live = [np.ones(n) for _ in range(3)]
        total = [np.zeros(n) for _ in range(3)]
        value = root_scores.copy()
        cooldown = [np.full(n, int(round(obs.scalar[3]*32)), np.int16) for _ in range(3)]
        depth_reached = 1
        for depth in range(8):
            count = 0
            for j in range(3):
                act = actions[j]
                if depth == 0:
                    output, prob, pickup, nh = root_predictions[j]
                else:
                    onehot = F.one_hot(torch.as_tensor(act, dtype=torch.long), 16).float()
                    raw = self.net.heads[j](torch.cat((hs[j], onehot), -1))
                    output, prob, pickup, nh = self._decode(raw, hs[j])
                # Prefix computations are real model work, including already-terminated slots.
                count += n if depth else 0
                discount = .99**depth if self.q_enabled else 1.
                total[j] += discount*live[j]*active[j]*(.015+pickup-self.penalty*prob[:, 0])
                next_live = live[j]*(1-prob[:, 0])
                cooldown[j] = np.maximum(0, np.where(act >= 8, 32, cooldown[j])-1)
                if self.q_enabled:
                    tail = continuation_max(self.net.q(nh), cooldown[j]).numpy()
                    value[j] = total[j]+(.99**(depth+1))*next_live*tail
                    proposals = self.net.q(nh).numpy()
                else:
                    tail = .015*256*prob[:, 1]+10*prob[:, 2]
                    value[j] = total[j]+live[j]*tail
                    # Open-loop proposals from the current factual policy; no free 16-way
                    # successor model expansion hidden inside the 128-edge budget.
                    proposals = np.full((n, 16), float(root_scores[j].mean()), np.float32)
                    proposals[:, legal] = root_scores[j]
                displacement = np.rint(np.tanh(output[:, :2])*10).astype(np.int16)
                pp = np.clip(positions[j]+displacement, 0, 63)
                known = self.atlas[pp[:, 1], pp[:, 0]] >= 0
                stopped = ~active[j]
                value[j, stopped] = prior_value[j, stopped] if depth else root_scores[j, stopped]
                active[j] &= known
                positions[j], hs[j], live[j] = pp, nh, next_live
                legal_next = np.ones((n, 16), bool)
                legal_next[:, 8:] = cooldown[j][:, None] == 0
                proposals[~legal_next] = -1e9
                weights = np.exp(np.clip(proposals-proposals.max(-1, keepdims=True), -30, 0))
                weights /= weights.sum(-1, keepdims=True)
                cumulative = weights.cumsum(-1)
                u = self.candidate_uniform[self.local_t, j, :n, min(depth, 7)]
                actions[j] = (u[:, None] > cumulative).sum(-1).clip(0, 15)
            # Each logical trajectory transition has three head evaluations.
            self.counters['head_evaluations'] += count
            self.counters['model_edges'] += n if depth else 0
            prior_value = value.copy()
            if depth == 3:
                depth_reached = 4
                self.counters['deep_H4'] += 1
                if len(set(np.argmax(value, axis=1))) == 1:
                    break
            if depth == 7:
                depth_reached = 8
                self.counters['deep_H8'] += 1
        return value, depth_reached

    @torch.no_grad()
    def act(self, obs, training):
        scalar, key = self._features(obs)
        im = torch.from_numpy(obs.image[None].astype(np.float32))
        sc = torch.from_numpy(scalar[None])
        self.h = self.net.gru(self.net.embedding(im, sc), self.h)
        legal = np.flatnonzero(obs.legal)
        q = self.net.q(self.h).numpy()[0] if self.q_enabled else np.zeros(16, np.float32)
        q[~obs.legal] = -1e9
        old_action = int(q.argmax())
        depth = 0
        forecast = 0.
        scores = q.copy()
        if self.factual and self.ablation != 'Q_only':
            values, predictions = self._root(self.h, legal, int(round(obs.scalar[3]*32)))
            depth = 1
            uncertainty = len(set(np.argmax(values, axis=1))) != 1
            mean_scores = values.mean(0)
            sorted_scores = np.sort(mean_scores)
            margin = sorted_scores[-1]-sorted_scores[-2] if len(sorted_scores)>1 else np.inf
            threshold = np.median(self.recent_errors) if len(self.recent_errors)>=64 else np.inf
            if (self.stage() == 2 and self.ablation != 'H1_only'
                    and self.deep_window_used != self.local_t//8 and (uncertainty or margin <= threshold)):
                values, depth = self._lookahead(self.h, legal, values, predictions, obs)
                self.deep_window_used = self.local_t//8
            scores = np.full(16, -1e9, np.float32)
            scores[legal] = values.mean(0)
            self.last_predictions = predictions
        full_action = int(scores.argmax())
        # Single intervention: physical training behavior uses own Q, not the planner.
        # Still compute all factual predictions and retain their forecast for this action.
        training_q_control = bool(training and self.factual and self.q_enabled)
        chosen = old_action if training_q_control else full_action
        epsilon = max(.1, 1-.9*self.training_steps/65536) if training else 0.
        u, v = self.action_uniform[self.local_t]
        explored = bool(u < epsilon)
        if explored:
            chosen = int(legal[min(int(v*len(legal)), len(legal)-1)])
        forecast = float(scores[chosen])
        self.counters['policy'] += 1
        if self.factual and not explored and chosen != old_action:
            self.counters['factual_action_changes'] += 1
        self.last_input = (obs.image.copy(), scalar, key, obs, chosen, forecast)
        self.last_choice = dict(action=chosen, explored=explored, stage=self.stage(), depth=depth,
                                forecast=forecast, old_action=old_action,
                                full_action=full_action, training_q_control=training_q_control)
        return chosen

    def observe(self, nxt, fact, reward):
        if self.arm == 'F0':
            assert reward is None, 'Pure feedback must never receive RewardPacket'
        else:
            assert reward is not None
            self.counters['reward_packets'] += 1
        image, scalar, key, obs, action, forecast = self.last_input
        target, mask = np.zeros(10, np.float32), np.zeros(10, np.float32)
        target[:2] = (np.array(nxt.hero)-np.array(obs.hero))/10
        mask[:2] = 1
        for m in range(2):
            if obs.monster_visible[m] and nxt.monster_visible[m]:
                target[2+2*m:4+2*m] = (nxt.monster_positions[m]-obs.monster_positions[m])/2
                mask[2+2*m:4+2*m] = 1
        target[6:8], mask[6:8] = [fact.pickup, fact.captured], 1
        if self.factual:
            legal = np.flatnonzero(obs.legal)
            k = int(np.flatnonzero(legal == action)[0])
            pred = np.mean([p[1][k, 0] for p in self.last_predictions])
            pred_pick = np.mean([p[2][k] for p in self.last_predictions])
            self.counters['factual_brier_sum'] += float((pred-fact.captured)**2)
            self.counters['factual_mse_sum'] += float((pred_pick-fact.pickup)**2)
            self.counters['factual_predictions'] += 1
        uid = self.replay.append(image, scalar, key, action, 0. if reward is None else reward,
                                 fact, target, mask, obs.legal, self.local_t == 0, forecast)
        self.episode_rows.append((uid, fact.pickup, fact.captured))
        self.last_action, self.last_pickup = action, fact.pickup
        self.local_t += 1
        self.training_steps += 1
        if fact.captured or fact.completed:
            remaining_pickup = 0
            discounted = 0.
            for remaining_steps, (row_uid, pickup, captured) in enumerate(reversed(self.episode_rows)):
                i = row_uid % CAPACITY
                self.replay.target[i, 8:] = remaining_steps/256, remaining_pickup/10
                self.replay.target_mask[i, 8:] = 1
                step_goal = .015+pickup-self.penalty*captured
                discounted = step_goal+(.99 if self.q_enabled else 1.)*discounted
                self.recent_errors.append(abs(discounted-float(self.replay.forecast[i])))
                remaining_pickup += pickup
        if self.training_steps >= 2048 and self.training_steps % 128 == 0:
            self.learn()
        if self.target_net is not None and self.training_steps % 2048 == 0:
            self.target_net.load_state_dict(self.net.state_dict())

    def learn(self):
        r, length = self.replay, 25
        starts = self.replay_rng.integers(max(0, r.n-CAPACITY), r.n-length+1, size=16)
        indices = (starts[:, None]+np.arange(length)) % CAPACITY
        images = torch.from_numpy(r.image[indices].astype(np.float32))
        scalars = torch.from_numpy(r.scalar[indices].astype(np.float32))
        resets = torch.from_numpy(r.reset[indices].astype(np.float32))
        hidden = self.net.unroll(images, scalars, resets)
        cur, nxt = hidden[:, 8:24], hidden[:, 9:25]
        ii = indices[:, 8:24]
        actions = torch.from_numpy(r.action[ii].astype(np.int64))
        done = torch.from_numpy(r.done[ii].astype(np.float32))
        total_loss = cur.sum()*0
        if self.q_enabled:
            current_q = self.net.q(cur).gather(-1, actions[..., None]).squeeze(-1)
            with torch.no_grad():
                target_h = self.target_net.unroll(images, scalars, resets)[:, 9:25]
                online_next = self.net.q(nxt.detach())
                legal_next = torch.from_numpy(r.legal[indices[:, 9:25]])
                online_next[~legal_next] = -1e9
                best = online_next.argmax(-1)
                target_q = self.target_net.q(target_h).gather(-1, best[..., None]).squeeze(-1)
                y = torch.from_numpy(r.reward[ii])+.99*(1-done)*target_q
            total_loss = total_loss+F.smooth_l1_loss(current_q, y)
            self.counters['Q_updates'] += 1
        if self.factual:
            onehot = F.one_hot(actions, 16).float()
            inputs = torch.cat((cur, onehot), -1)
            targets = torch.from_numpy(r.target[ii])
            masks = torch.from_numpy(r.target_mask[ii])
            for j, head in enumerate(self.net.heads):
                raw = head(inputs)
                prediction = torch.cat((torch.tanh(raw[..., :6]), F.softplus(raw[..., 6:7]),
                                        torch.sigmoid(raw[..., 7:10])), -1)
                boot = torch.from_numpy(bootstrap_mask(starts[:, None]+np.arange(8, 24), j, self.seed))
                self.counters[f'bootstrap_selected_{j}'] += int(boot.sum())
                weights = masks*boot[..., None]
                factual = ((prediction-targets)**2*weights).sum()/weights.sum().clamp_min(1)
                cap_loss = (F.binary_cross_entropy_with_logits(raw[..., 7], targets[..., 7], reduction='none')*boot).sum()/boot.sum().clamp_min(1)
                transition_raw = head(torch.cat((cur.detach(), onehot), -1))
                transition, stats = transition_loss(cur, nxt, transition_raw[..., 10:], 1-done, boot,
                    torch.from_numpy(r.legal[indices[:, 9:25]]), self.net.q)
                self.counters['transition_weight'] += stats['weight']
                self.counters['transition_model_mse_sum'] += stats['model_mse_sum']
                self.counters['transition_identity_mse_sum'] += stats['identity_mse_sum']
                self.counters['transition_value_loss_sum'] += stats['value_loss_sum']
                total_loss = total_loss+(factual+cap_loss+transition)/3
            self.counters['fact_updates'] += 1
            self.counters['bootstrap_positions'] += 16*16
        self.optimizer.zero_grad(set_to_none=True)
        total_loss.backward()
        nn.utils.clip_grad_norm_(self.net.parameters(), 5.)
        self.optimizer.step()
        self.counters['real_replay_labels'] += 16*16
        assert torch.isfinite(total_loss), 'Nonfinite training loss'

    def frozen(self, ablation=None):
        result = copy.deepcopy(self)
        result.ablation = ablation
        result.net.eval()
        return result

    def parameter_hash(self):
        h = hashlib.sha256()
        for p in self.net.state_dict().values():
            h.update(p.detach().numpy().tobytes())
        return h.hexdigest()
