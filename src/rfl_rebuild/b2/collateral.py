r"""B2-3 — `BehavioralCollateral` and the $U_{\text{unaffected}}$ **candidate** constructors.

$$\boxed{\text{BehavioralCollateral} = V_{\text{unaffected,pre}} -
V_{\text{unaffected,post}}}$$

A79 §67.4 froze four properties of the unaffected set, and three of them are mechanical here:

$$\boxed{\text{truth-blind} + \text{arm-blind} + \text{pre-update}}$$

The fourth — **the paired arms share the same constructed object** — is a property of the paired
runner: this module provides the object and the builder contract, and B2-4 must pass *one* instance
to both arms and prove `u_reference is u_treatment`. Nothing here claims that identity, and an
equality check would not be it: two constructions that agree are exactly what a shared object is
not.

**What a constructor may see.** Pre-update, learner-visible material and nothing else. The
signatures carry no arm or law identity, no post-update state, no $\Delta W$, no `UpdateLedger`, no
future outcome, none of $\mathcal H_{\text{forbidden}}$, and no stratum/world/block identifier —
so the blindness is a property of the interface rather than a promise about its use.

**Several candidates, and no choice.** A79 §67.4 leaves the construction to the development stage
*on measurement properties*; this module therefore provides more than one and refuses to pick:
`select_construction` raises, and there is no defaulted candidate anywhere. Choosing because a
candidate reports a larger effect on a synthetic fixture would be choosing the estimator by its
answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from rfl_rebuild.b1.errors import ProtocolError

__all__ = [
    "CANDIDATE_CONSTRUCTIONS",
    "UNAFFECTED_CONSTRUCTIONS",
    "UnaffectedSet",
    "behavioral_collateral",
    "select_construction",
]


@dataclass(frozen=True, slots=True)
class UnaffectedSet:
    r"""One constructed set of pre-update contexts, with the rule that produced it named.

    The `construction` field is diagnostic metadata, not a choice: a report has to say which
    candidate produced the number, and that is a different thing from the development stage
    deciding which candidate is primary.
    """

    contexts: tuple
    construction: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "contexts", tuple(self.contexts))
        if not self.contexts:
            raise ProtocolError(
                "the unaffected set is empty; an empty set has no mean and would make "
                "BehavioralCollateral undefined rather than zero")
        if len(set(map(repr, self.contexts))) != len(self.contexts):
            raise ProtocolError("the unaffected set contains a duplicate context")


def _unaffected_visited_complement(domain, visited) -> UnaffectedSet:
    r"""Candidate 1: the contexts of the **pre-update** domain the episode did not visit.

    The reading it encodes: a write should not move behaviour where the episode never went, so the
    complement is the part of the world the update had no occasion to touch.
    """
    contexts = tuple(c for c in domain if c not in set(visited))
    return UnaffectedSet(contexts=contexts, construction="visited_complement")


def _unaffected_state_parity(domain, visited, *, parity: int = 0) -> UnaffectedSet:
    r"""Candidate 2: the **unvisited** contexts whose state $x$ has a declared parity.

    A second candidate exists so that the development stage has something to choose *between*; its
    rule is declared rather than tuned, and it is a deterministic function of pre-update material
    like the first.
    """
    if parity not in (0, 1):
        raise ProtocolError(f"parity={parity!r} is not 0 or 1")
    allowed = set(visited)
    contexts = tuple(c for c in domain if c not in allowed and getattr(c[0], "x", 0) % 2 == parity)
    return UnaffectedSet(contexts=contexts, construction=f"state_parity_{parity}")


#: The candidate constructions, **all of them frozen as candidates and none of them chosen**.
CANDIDATE_CONSTRUCTIONS: Mapping[str, Callable] = {
    "visited_complement": _unaffected_visited_complement,
    "state_parity": _unaffected_state_parity,
}

#: Kept under the name the docs use.
UNAFFECTED_CONSTRUCTIONS = CANDIDATE_CONSTRUCTIONS


def select_construction(name: str = "") -> Callable:
    r"""$$\boxed{\text{the construction is chosen at the development stage, not here}}$$

    A79 §67.4 leaves the choice to measurement properties gathered under the development protocol,
    and A83 §71.4 keeps that choice open. This function exists so that a caller who wants "the"
    construction is told to say which one, rather than being handed a default that would become the
    decision by inaction.
    """
    if not name:
        raise ProtocolError(
            "no unaffected-set construction is selected by default: A79 67.4 leaves the choice to "
            f"the development stage on measurement properties, and the candidates are "
            f"{sorted(CANDIDATE_CONSTRUCTIONS)}")
    if name not in CANDIDATE_CONSTRUCTIONS:
        raise ProtocolError(
            f"{name!r} is not a candidate construction; the candidates are "
            f"{sorted(CANDIDATE_CONSTRUCTIONS)}")
    return CANDIDATE_CONSTRUCTIONS[name]


def behavioral_collateral(unaffected: UnaffectedSet, *, values_pre: Mapping,
                          values_post: Mapping) -> float:
    r"""$$V_{\text{unaffected,pre}} - V_{\text{unaffected,post}}$$ as a **mean over the set**.

    The aggregate is declared rather than implied: the mean of the per-context values, so that the
    number is comparable across candidate constructions of different sizes and a set cannot inflate
    the effect by being large. Both mappings must cover **exactly** the set — a missing context
    would silently shrink the denominator, and an extra one would import a context the set does not
    contain.
    """
    if type(unaffected) is not UnaffectedSet:
        raise ProtocolError(
            f"the unaffected set {unaffected!r} has type {type(unaffected).__name__}, not "
            "UnaffectedSet; a bare container would carry no construction and no contract")
    expected = set(map(repr, unaffected.contexts))
    for name, values in (("pre", values_pre), ("post", values_post)):
        if not isinstance(values, Mapping):
            raise ProtocolError(f"the {name}-update values are not a mapping")
        got = set(map(repr, values))
        if got != expected:
            extra = sorted(got - expected)
            missing = sorted(expected - got)
            raise ProtocolError(
                f"the {name}-update values cover {len(got)} contexts but the unaffected set has "
                f"{len(expected)} (extra {extra[:3]!r}, missing {missing[:3]!r}); the metric is "
                "defined on exactly the set it was given")
        for context in unaffected.contexts:
            v = values[context]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ProtocolError(
                    f"the {name}-update value at {context!r} is {v!r}, not a real number")
    pre = sum(float(values_pre[c]) for c in unaffected.contexts) / len(unaffected.contexts)
    post = sum(float(values_post[c]) for c in unaffected.contexts) / len(unaffected.contexts)
    return pre - post
