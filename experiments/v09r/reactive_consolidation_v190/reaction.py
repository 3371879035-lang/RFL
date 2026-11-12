"""Observed movement evidence, not predicted outcomes or capture attribution."""
import hashlib
import json


def context_key(obs):
    bits = obs.local_roads[9:12, 9:12].reshape(-1)
    return sum(int(v) << i for i, v in enumerate(bits)) | (int(obs.scalar[4] > 0) << 9)


class ReactionMemory:
    def __init__(self, mode):
        assert mode in ('base', 'wake', 'wake_sleep')
        self.mode = mode
        self.counts = {}
        self.rules = {}
        self.completed = self.failures = 0
        self.reset()

    def reset(self):
        self.episode = {}
        self.anchor = None
        self.failed = 0
        self.streak = 0

    def choose(self, key, hero, legal, scores, proposed, explored):
        anchor = (tuple(hero), key)
        local = self.failed if self.anchor == anchor and self.streak >= 2 else 0
        remembered = self.rules.get(key, 0)
        # An observed counterexample wins over an older compressed rule, also
        # within frozen evaluation (without writing persistent memory).
        for a, flags in self.episode.get(key, {}).items():
            if flags & 1:
                remembered &= ~(1 << a)
        blocked = 0 if self.mode == 'base' else local
        if self.mode == 'wake_sleep':
            blocked |= remembered
        chosen, reason = proposed, 0
        if not explored and proposed < 8 and blocked & (1 << proposed):
            candidates = [a for a, ok in enumerate(legal) if ok and not (blocked & (1 << a))]
            if candidates:
                chosen = max(candidates, key=lambda a: float(scores[a]))
                reason = 2 if self.mode == 'wake_sleep' and remembered & (1 << proposed) else 1
        return chosen, dict(context=key, local_mask=local, memory_mask=remembered,
                            streak_before=self.streak, reason=reason, proposed=proposed)

    def observe(self, key, hero, action, moved):
        anchor = (tuple(hero), key)
        if self.anchor != anchor:
            self.anchor, self.failed = anchor, 0
        if action < 8:
            row = self.episode.setdefault(key, {})
            row[action] = row.get(action, 0) | (1 if moved else 2)
            if not moved:
                self.failed |= 1 << action
        self.streak = 0 if moved else self.streak + 1
        if moved:
            self.anchor, self.failed = None, 0

    def finish(self, captured, persist):
        if not persist:
            return None
        changes = []
        for key, evidence in sorted(self.episode.items()):
            counts = self.counts.setdefault(key, [[0, 0] for _ in range(8)])
            before = self.rules.get(key, 0)
            for a, flags in evidence.items():
                counts[a][0] += int(bool(flags & 1))
                counts[a][1] += int(bool(flags & 2))
                if flags & 1:
                    self.rules[key] = self.rules.get(key, 0) & ~(1 << a)
            # Failure-triggered consolidation; success only contributes ordinary
            # factual experience and removes directly contradicted beliefs.
            if captured:
                alternatives = any(m >= 2 for m, s in counts)
                self.rules[key] = sum(1 << a for a, (m, s) in enumerate(counts)
                                      if alternatives and s >= 2 and m == 0)
            changes.append(dict(context=key, evidence=sorted(evidence.items()),
                                before=before, after=self.rules.get(key, 0)))
        self.completed += 1
        self.failures += int(captured)
        return dict(completed=self.completed, captured=bool(captured), changes=changes)

    def digest(self):
        value = dict(counts=self.counts, rules=self.rules, completed=self.completed, failures=self.failures)
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def summary(self):
        return dict(contexts=len(self.counts), active_contexts=sum(bool(v) for v in self.rules.values()),
                    active_action_rules=sum(v.bit_count() for v in self.rules.values()),
                    completed=self.completed, failure_consolidations=self.failures,
                    bytes=len(json.dumps(dict(counts=self.counts, rules=self.rules))), sha256=self.digest())
