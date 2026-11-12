"""A62 belief backend — a global weighted support with rows-class blocks and a
bitset posterior inside each block.

The problem this solves: the global hypothesis space is ~10^6 worlds, so it
cannot be a ``tuple`` in ``QuerySession.members``; but a class cannot be the
belief atom either, because queries exist precisely to split latent worlds
*inside* a rows class. Whenever

    O(ell_a, q) != O(ell_b, q)     for ell_a, ell_b in the same class,

a class-level atom has nothing to update with.

So the belief is

    H = { (c, M_c) | c in C_active },      M_c subset of the worlds of c

where ``c`` is a **rows-only** factual class (learner-visible sequence, NO
feedback) and ``M_c`` is an ``int`` bitset over that class's worlds. Intersection
becomes integer ``&``: no Python-hash semantics, no set ordering, a few thousand
bits per block.

Three operations, frozen:

    q in Q_safe(H)   iff   for all c:  M_c subset of L_{c,q}
    M'_c = M_c & R_{c,q,o}                          (drop empty blocks)
    p_i(H) = sum_c sum_{l in M_c} w_l Z^fire_i(l) / sum_c sum_{l in M_c} w_l

The safety test is written as a PER-WORLD subset test, never as
``q in class.menu``. That matters: the current environment happens to have
class-constant legality, so the shortcut would pass here and would be exactly the
optimisation that silently drops A50's general case the moment legality becomes
world-dependent again.

Gate's ``build_partition`` is NOT reused as the support constructor. It answers
"given the observation, is this theoretically identifiable?"; this answers "before
the experiment, which worlds does the learner consider possible, and how
probable?". Conflating the two constructors is what produced the dev_v1 leak.

Caches are lazy: a (class, query) entry is computed on first use, and a block
whose legality there is uniform is recorded as ``ALL``/``NONE`` rather than
materialising a bitmask.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

N_TARGETS = 32          # 5-bit Z^fire code
ALL, NONE, MIXED = "ALL", "NONE", "MIXED"


def fire_code(fire: Sequence[int]) -> int:
    """``code(l) = sum_i 2^i Z^fire_i(l)`` in [0, 31]."""
    c = 0
    for i, v in enumerate(fire):
        if v:
            c |= (1 << i)
    return c


def code_to_fire(code: int) -> tuple:
    return tuple((code >> i) & 1 for i in range(5))


@dataclass
class _BlockCache:
    kind: str = NONE
    legal_mask: int = 0
    by_response: dict = field(default_factory=dict)


class GlobalSupportIndex:
    """Immutable global support + lazy per-(class, query) caches.

    Caller supplies, all public (independent of the true world):

    ``worlds``        opaque ids, index == bit position inside its class
    ``class_of``      world -> rows_class_id
    ``weight_of``     world -> P_DGP(ell)
    ``fire_code_of``  world -> int in [0, 31]
    ``legal``         (world, query) -> bool
    ``resp_key``      (world, query) -> canonical hashable response
    """

    def __init__(self, *, worlds, class_of, weight_of, fire_code_of,
                 legal: Callable, resp_key: Callable):
        self.worlds = tuple(worlds)
        self._class_of = dict(class_of)
        self._w = dict(weight_of)
        self._fire = dict(fire_code_of)
        self._legal = legal
        self._resp = resp_key
        self._blocks: dict = {}
        for w in self.worlds:
            self._blocks.setdefault(self._class_of[w], []).append(w)
        self._pos = {}
        for cid, members in self._blocks.items():
            self._pos[cid] = {w: i for i, w in enumerate(members)}
        self._cache: dict = {}

    # ---- structure ------------------------------------------------------- #
    @property
    def class_ids(self) -> tuple:
        return tuple(self._blocks)

    def members(self, cid) -> tuple:
        return tuple(self._blocks[cid])

    def full_mask(self, cid) -> int:
        return (1 << len(self._blocks[cid])) - 1

    def weight(self, cid, bit: int) -> float:
        return float(self._w[self._blocks[cid][bit]])

    def fire_of(self, cid, bit: int) -> int:
        return int(self._fire[self._blocks[cid][bit]])

    def _entry(self, cid, q) -> _BlockCache:
        key = (cid, q)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        ent = _BlockCache()
        legal_mask = 0
        by_resp: dict = {}
        for i, w in enumerate(self._blocks[cid]):
            if self._legal(w, q):
                legal_mask |= (1 << i)
                rk = self._resp(w, q)
                by_resp[rk] = by_resp.get(rk, 0) | (1 << i)
        full = self.full_mask(cid)
        if legal_mask == full:
            ent.kind = ALL
        elif legal_mask == 0:
            ent.kind = NONE
        else:
            ent.kind = MIXED
        ent.legal_mask = legal_mask
        ent.by_response = by_resp
        self._cache[key] = ent
        return ent

    # ---- the three frozen operations ------------------------------------- #
    def safe(self, belief: "BeliefState", q) -> bool:
        """``forall c: M_c subset of L_{c,q}`` — per world, not per class."""
        for cid, mask in belief.active_blocks.items():
            ent = self._entry(cid, q)
            if ent.kind == NONE:
                return False
            if ent.kind == MIXED and (mask & ~ent.legal_mask):
                return False
        return True

    def candidate_queries(self, belief: "BeliefState", registry) -> tuple:
        return tuple(q for q in registry if self.safe(belief, q))

    def update(self, belief: "BeliefState", q, resp_key) -> "BeliefState":
        out = {}
        for cid, mask in belief.active_blocks.items():
            ent = self._entry(cid, q)
            m = mask & ent.by_response.get(resp_key, 0)
            if m:
                out[cid] = m
        return BeliefState(active_blocks=out)

    def marginals(self, belief: "BeliefState") -> tuple:
        acc = [0.0] * 5
        tot = 0.0
        for cid, mask in belief.active_blocks.items():
            n = len(self._blocks[cid])
            for bit in range(n):
                if not (mask >> bit) & 1:
                    continue
                w = self.weight(cid, bit)
                code = self.fire_of(cid, bit)
                tot += w
                for i in range(5):
                    if (code >> i) & 1:
                        acc[i] += w
        if tot <= 0.0:
            return tuple(0.0 for _ in range(5))
        return tuple(a / tot for a in acc)

    def fingerprint(self, belief: "BeliefState") -> str:
        """Opaque, order-independent, PYTHONHASHSEED-independent."""
        parts = sorted(f"{cid}:{mask}" for cid, mask in
                       belief.active_blocks.items())
        return "|".join(parts)

    # ---- convenience priors ---------------------------------------------- #
    def global_prior(self) -> "BeliefState":
        """Every rows block active, every local mask full. True-world agnostic."""
        return BeliefState(active_blocks={cid: self.full_mask(cid)
                                          for cid in self._blocks})

    def rows_prior(self, cid) -> "BeliefState":
        """Sequence arms: activate only the block whose rows match."""
        return BeliefState(active_blocks={cid: self.full_mask(cid)})


@dataclass(frozen=True, slots=True)
class BeliefState:
    """An IMMUTABLE belief. ``update`` returns a new one; the old one never moves.

    A62 closure: ``frozen=True`` alone was cosmetic here, because the field was a
    plain ``dict`` and ``object.__setattr__`` only replaced it with another
    ``dict``. External code could still write ``belief.active_blocks[cid] = ...``,
    which silently breaks "update returns a new belief". Wrapping in
    ``MappingProxyType`` closes it at the point of use.
    """

    active_blocks: Mapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.active_blocks, MappingProxyType):
            object.__setattr__(self, "active_blocks",
                               MappingProxyType(dict(self.active_blocks)))
        for cid, m in self.active_blocks.items():
            if not isinstance(m, int) or isinstance(m, bool) or m <= 0:
                raise ValueError("each local mask must be a positive int bitset")
