"""A61 — the four real V0.1R methods, frozen before any development scene is read.

No development data informed this file. Two decisions are explicit rather than
implicit, because both would otherwise be silent:

* **The prior is uniform over feasible worlds, and that is declared, not
  inherited.** The generator's measure over worlds is not specified, so the
  version-space marginal is

      p_i(H) = sum_{l in H} w_l Z^fire_i(l) / sum_{l in H} w_l ,   w_l = 1

  with the uniform weights written out. Using enumeration frequency as if it were
  a prior would smuggle the enumeration's shape into the prediction.

* **``SeqThenQuery`` is a greedy diagnosis algorithm, NOT Gate_fire's optimal DP.**
  Gate_fire computed the minimum-depth tree as a theorem. Reusing it here would
  make the experiment re-run the identifiability result instead of testing a
  method. This one picks, at each step,

      q* = argmin_{q in Q_safe(H)} max_o |{ Z^fire(l) : l in H_o }|

  i.e. it minimises the worst-case number of *surviving distinct targets*, then
  breaks ties by number of child worlds, then by registry order. It stops when the
  targets are already homogeneous or the budget is gone. That is a heuristic, and
  it is allowed to be suboptimal.

``PublicSupport`` is the declared hypothesis space: worlds, their observable
signature, their response map, and their ``Z^fire``. It is public by construction.
The learner does not know which world is true; a version-space learner knowing the
model class is not a truth leak.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .contract import N_CAUSES, Prediction

# FROZEN: the prior. Do not replace with enumeration frequencies.
UNIFORM_OVER_FEASIBLE_WORLDS = "uniform-over-feasible-worlds"
WEIGHT = 1.0


@dataclass(frozen=True, slots=True)
class PublicSupport:
    worlds: tuple
    signature: Mapping          # world -> observable signature (hashable)
    fire: Mapping               # world -> 5-tuple of Z^fire
    response: Mapping           # (world, query) -> learner-facing response
    prior: str = UNIFORM_OVER_FEASIBLE_WORLDS

    def __post_init__(self) -> None:
        if self.prior != UNIFORM_OVER_FEASIBLE_WORLDS:
            raise ValueError(
                "the prior must be the frozen uniform-over-feasible-worlds; "
                "enumeration frequency is not a prior")

    def marginals(self, H: Sequence) -> tuple:
        """``p_i(H)`` with explicit uniform weights."""
        if not H:
            return tuple(0.0 for _ in range(N_CAUSES))
        tot = 0.0
        acc = [0.0] * N_CAUSES
        for w in H:
            tot += WEIGHT
            f = self.fire[w]
            for i in range(N_CAUSES):
                acc[i] += WEIGHT * f[i]
        return tuple(a / tot for a in acc)


class DirectFeedbackMethod:
    """Takes the feedback claim at face value. No evidence, no queries."""

    name = "DirectFeedback"

    def __call__(self, feedback) -> Prediction:
        claim = tuple(float(int(bool(x))) for x in feedback.claim)
        if len(claim) != N_CAUSES:
            claim = (claim + (0.0,) * N_CAUSES)[:N_CAUSES]
        return Prediction(p=claim)


class SequenceEvidenceMethod:
    """Version-space marginals over the worlds consistent with the evidence."""

    name = "SequenceEvidence"

    def __init__(self, support: PublicSupport, sig_of_evidence: Callable):
        self._s = support
        self._sig = sig_of_evidence

    def hypothesis_set(self, evidence) -> tuple:
        key = self._sig(evidence)
        return tuple(w for w in self._s.worlds if self._s.signature[w] == key)

    def __call__(self, evidence) -> Prediction:
        return Prediction(p=self._s.marginals(self.hypothesis_set(evidence)))


class SeqThenQueryMethod(SequenceEvidenceMethod):
    """Same H, then greedy diagnosis on the safe menu, then marginals.

    Query selection is by the FROZEN rule in the module docstring. Deterministic:
    the tie-breaks are (child count, registry order), and nothing consults
    randomness or the true world.
    """

    name = "SeqThenQuery"
    MAX_QUERIES = 4          # == B_Q

    def _children(self, H, q):
        groups: dict = {}
        for w in H:
            groups.setdefault(self._s.response.get((w, q)), []).append(w)
        return [tuple(v) for v in groups.values()]

    def _score(self, H, q, order_index):
        kids = self._children(H, q)
        worst = max((len({self._s.fire[w] for w in k}) for k in kids), default=0)
        return (worst, max(len(k) for k in kids), order_index)

    def __call__(self, evidence, session) -> Prediction:
        H = self.hypothesis_set(evidence)
        asked = 0
        while asked < self.MAX_QUERIES and session.budget >= 1 and len(H) > 1:
            if len({self._s.fire[w] for w in H}) <= 1:
                break                      # targets already homogeneous: stop
            menu = session.menu()
            if not menu:
                break
            order = {q: i for i, q in enumerate(menu)}
            q_star = min(menu, key=lambda q: self._score(H, q, order[q]))
            session.submit(q_star)
            asked += 1
            # tighten H to the worlds whose declared response matches what was
            # actually observed. Nothing here consults the true world.
            obs = session.observations()[-1].response
            H = tuple(w for w in H
                      if _wrap_eq(self._s.response.get((w, q_star)), obs))
        return Prediction(p=self._s.marginals(H))


def _wrap_eq(raw, wrapped) -> bool:
    """Compare a raw support response with a wrapped session observation."""
    if raw is None:
        return False
    if hasattr(wrapped, "proposal"):
        return raw[1] == wrapped.proposal
    if hasattr(wrapped, "u"):
        return raw[1] == wrapped.u
    return raw[0] == tuple((s.x, s.y, s.t, s.kappa, s.phi, s.z, s.m, s.a_cmd,
                            s.a_realized, s.reward) for s in wrapped.steps)


class QueryOnlyMethod:
    """Precomputed ``observation-history -> marginals`` lookup.

    The history it may read contains NO addresses (A59), so the key is the tuple
    of responses only. Built from the public support once, offline.
    """

    name = "QueryOnly"

    def __init__(self, support: PublicSupport, blind_order: Sequence):
        self._s = support
        self._order = tuple(blind_order)
        self._table = self._build()

    def _build(self) -> dict:
        """Enumerate blind-policy runs over every world; key on response tuples."""
        table: dict = {}
        for start in self._s.worlds:
            H = self._s.worlds
            key = []
            for q in self._order:
                kids = {}
                for w in H:
                    r = self._s.response.get((w, q))
                    kids.setdefault(r, []).append(w)
                r_true = self._s.response.get((start, q))
                if r_true is None:
                    break
                key.append(_freeze(r_true))
                H = tuple(kids.get(r_true, ()))
                if not H:
                    break
            table.setdefault(tuple(key), []).append(start)
        return {k: tuple(v) for k, v in table.items()}

    def _build_key(self, observations) -> tuple:
        return tuple(_freeze(_unwrap(o.response)) for o in observations)

    def __call__(self, observations) -> Prediction:
        key = self._build_key(observations)
        H = self._table.get(key)
        if H is None:
            # unseen history: fall back to the whole support, which is the
            # honest thing to do and is recorded rather than hidden
            H = self._s.worlds
        return Prediction(p=self._s.marginals(H))


def _unwrap(resp):
    if hasattr(resp, "proposal"):
        return ("proc_audit", resp.proposal)
    if hasattr(resp, "u"):
        return ("audit", resp.t, resp.u)
    return ("rollout", tuple((s.x, s.y, s.t, s.kappa, s.phi, s.z, s.m, s.a_cmd,
                              s.a_realized, s.reward) for s in resp.steps))


def _freeze(raw):
    try:
        return hash(raw)
    except TypeError:
        return repr(raw)
