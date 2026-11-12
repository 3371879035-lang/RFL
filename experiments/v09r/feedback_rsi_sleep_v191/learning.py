"""V191: unchanged task policy; learned history allocation and parametric sleep."""
from base_learning import *
from base_learning import Agent as BaseAgent

class Agent(BaseAgent):
    def configure_v191(self, variant):
        from sleep_loop import HistoryPolicy
        self.variant = variant
        self.history_policy = HistoryPolicy()
        self._selected_starts = None
        self._sleep_teacher = None
        self.counters['v191_optimizer_updates'] = 0
        self.counters.setdefault('measurement_updates', 0)
        self.label_events = []
        self.last_distillation = 0.
        self.last_loss = 0.

    def learn(self):
        r, length = self.replay, 25
        starts = self._selected_starts if self._selected_starts is not None else self.replay_rng.integers(max(0, r.n-CAPACITY), r.n-length+1, size=16)
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
            inputs = torch.cat((cur.detach(), onehot), -1)
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
                transition, stats = transition_loss(cur, nxt, transition_raw[..., 10:74], 1-done, boot,
                    torch.from_numpy(r.legal[indices[:, 9:25]]), self.net.q)
                self.counters['transition_weight'] += stats['weight']
                self.counters['transition_model_mse_sum'] += stats['model_mse_sum']
                self.counters['transition_identity_mse_sum'] += stats['identity_mse_sum']
                self.counters['transition_value_loss_sum'] += stats['value_loss_sum']
                residual_loss = raw.sum()*0
                if self.q_enabled:
                    residual_target = y.detach()-current_q.detach()
                    residual_error = F.smooth_l1_loss(raw[..., 74], residual_target, reduction='none')
                    residual_loss = (residual_error*boot).sum()/boot.sum().clamp_min(1)
                total_loss = total_loss+(factual+cap_loss+transition+residual_loss)/3
            self.counters['fact_updates'] += 1
            self.counters['bootstrap_positions'] += 16*16
        if not self.q_enabled:
            target = torch.from_numpy(r.future[ii])
            valid = torch.from_numpy(r.future_mask[ii])
            for j, head in enumerate(self.net.measurements):
                all_actions = head(cur)
                selected = all_actions.gather(-3, actions[...,None,None,None].expand(*actions.shape,1,len(HORIZONS),2)).squeeze(-3)
                boot = torch.from_numpy(bootstrap_mask(starts[:,None]+np.arange(8,24),j,self.seed))
                weight = valid*boot[...,None]
                error = F.smooth_l1_loss(selected,target,reduction='none').mean(-1)
                loss = (error*weight).sum()/weight.sum().clamp_min(1)
                total_loss = total_loss+loss/3
                self.counters['measurement_train_windows'] += int(weight.sum().detach())
                self.counters['measurement_loss_sum'] += float(loss.detach())
            self.counters['measurement_updates'] += 1
        self.last_distillation = 0.
        if self._sleep_teacher is not None:
            from sleep_loop import distillation
            d = distillation(self, hidden, images, scalars, resets, ii, actions)
            self.last_distillation = float(d.detach())
            total_loss = total_loss + .5*d
        self.optimizer.zero_grad(set_to_none=True)
        total_loss.backward()
        if self.factual:
            # The auxiliary heads may learn, but cannot change Q/encoder gradients
            # directly or through a shared global clipping scale.
            core = [p for name, p in self.net.named_parameters() if not name.startswith('heads.')]
            nn.utils.clip_grad_norm_(core, 5.)
            nn.utils.clip_grad_norm_(self.net.heads.parameters(), 5.)
        else:
            nn.utils.clip_grad_norm_(self.net.parameters(), 5.)
        self.optimizer.step()
        self.counters['real_replay_labels'] += 16*16
        self.counters['v191_optimizer_updates'] += 1
        self.last_loss = float(total_loss.detach())
        assert torch.isfinite(total_loss), 'Nonfinite training loss'

