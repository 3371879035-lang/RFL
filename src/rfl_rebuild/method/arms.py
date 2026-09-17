"""A62 — the four V0.1R arms on the DenseSupport backend.

Arms, with the candidate-space asymmetry FROZEN as a design decision rather than
a bug:

    QueryOnly       H_0 = H_global,      candidates = Q_global,  runner's blind policy
    SeqThenQuery    H_0 = H_rows(I),     candidates = Q_syn(I),  its own greedy choice

V0.1R compares *blind querying without sequence* against *sequence-informed
targeted querying*. What is frozen equal is B_Q = 4, not the candidate set. An
arm that isolates "how much does sequence itself buy" versus "how much does
sequence-informed targeting buy" would be a new factorial arm and is not added
here.

Responses are memoised per (block, query): the greedy score must evaluate every
candidate in Q_t, and |Q_syn| measures ~37 (not the unmeasured "8-14"), so a step
costs up to ~47 response partitions over a rows block. Amortisation is by the
memo, never by shrinking Q_syn.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contract import Prediction
from .registry import first_safe
from .synth import synth_queries


@dataclass
class ResponseMemo:
    """Per-(block, query) legality and response partitions, computed lazily.

    One entry answers both questions the runner needs -- is this query legal for
    every remaining world, and which worlds share each response -- so a query is
    rolled out at most once per block.
    """

    def __init__(self, support, probe):
        self._s = support
        self._p = probe
        self._memo: dict = {}
        self.rollouts = 0

    def _entry(self, bid, q):
        key = (bid, q)
        hit = self._memo.get(key)
        if hit is None:
            members = self._s.block_members(bid)
            legal = []
            parts: dict = {}
            for bit, wid in enumerate(members):
                case = self._p.rebuild(self._s, wid)
                r = self._p.response(case, q)
                self.rollouts += 1
                ok = r is not None
                legal.append(ok)
                if ok:
                    parts.setdefault(r, 0)
                    parts[r] |= (1 << bit)
            hit = (tuple(legal), {k: v for k, v in parts.items()})
            self._memo[key] = hit
        return hit

    def safe(self, belief, q) -> bool:
        for bid, mask in belief.active_blocks.items():
            legal, _ = self._entry(bid, q)
            for bit, ok in enumerate(legal):
                if (mask >> bit) & 1 and not ok:
                    return False
        return True

    def partition(self, belief, q):
        """``[(response, child_belief)]``.

        Returns full child BELIEFS, not summed bitmasks: summing masks across
        blocks loses which block a bit belongs to, which is needed both for the
        target census and for the belief update.
        """
        from .belief import BeliefState
        groups: dict = {}
        for bid, mask in belief.active_blocks.items():
            _legal, parts = self._entry(bid, q)
            for r, pm in parts.items():
                m = mask & pm
                if m:
                    groups.setdefault(r, {})[bid] = m
        return [(r, BeliefState(active_blocks=blocks))
                for r, blocks in groups.items()]


# --------------------------------------------------------------------------- #
# arms
# --------------------------------------------------------------------------- #

def arm_direct_feedback(support, claim) -> Prediction:
    p = tuple(float(int(bool(x))) for x in claim[:5])
    return Prediction(p=(p + (0.0,) * 5)[:5])


def arm_sequence_evidence(support, true_wid) -> Prediction:
    bid = support.field(true_wid, "block_id")
    return Prediction(p=support.marginals(support.rows_prior(bid)))


def arm_query_only(support, registry, memo, *, budget: int, true_wid: int):
    """Global prior; runner's blind policy; responses only. Returns (pred, trace, H)."""
    H = support.global_prior()
    trace = []
    for _ in range(budget):
        i = first_safe(registry, lambda q: memo.safe(H, q))
        if i is None:
            break
        q = registry[i]
        # The blind RULE is a function of (H, registry) only, so the chosen query
        # does not depend on the true world. The RESPONSE does, so the runner
        # takes the child that contains the true world.
        kids = memo.partition(H, q)
        nxt = _child_with(support, kids, true_wid)
        if nxt is None:
            break
        trace.append(i)
        H = nxt
        if not H.active_blocks:
            break
    return Prediction(p=support.marginals(H)), trace, H


def arm_seq_then_query(support, registry, memo, evidence, true_wid, ridx,
                       *, budget: int, option_ids, option_actions):
    """Rows prior; Q_syn(I); greedy A61 score; responses only."""
    bid = support.field(true_wid, "block_id")
    H = support.rows_prior(bid)
    Q_syn = synth_queries(evidence, options=option_ids,
                          option_actions=option_actions, registry_index=ridx)
    asked: set = set()
    trace = []
    for _ in range(budget):
        if len({support.field(w, "fire_code")
                for w in _mask_worlds(support, H)}) <= 1:
            break
        cands = [q for q in Q_syn if q not in asked and memo.safe(H, q)]
        if not cands:
            break
        best, best_score = None, None
        for q in cands:
            kids = memo.partition(H, q)
            if not kids:
                continue
            worst_targets = max(len({support.field(w, "fire_code")
                                     for w in _mask_worlds(support, cb)})
                                for _r, cb in kids)
            worst_children = max(_size(cb) for _r, cb in kids)
            score = (worst_targets, worst_children, ridx[q])
            if best_score is None or score < best_score:
                best, best_score = q, score
        if best is None:
            break
        asked.add(best)
        trace.append(ridx[best])
        nxt = _child_with(support, memo.partition(H, best), true_wid)
        if nxt is None:
            break
        H = nxt
        if not H.active_blocks:
            break
    return Prediction(p=support.marginals(H)), trace, H


def _child_with(support, kids, true_wid):
    for _r, cb in kids:
        if true_wid in _mask_worlds(support, cb):
            return cb
    return None


def _size(belief) -> int:
    return sum(bin(m).count("1") for m in belief.active_blocks.values())


def _mask_worlds(support, belief):
    out = []
    for bid, mask in belief.active_blocks.items():
        for bit, wid in enumerate(support.block_members(bid)):
            if (mask >> bit) & 1:
                out.append(wid)
    return out
