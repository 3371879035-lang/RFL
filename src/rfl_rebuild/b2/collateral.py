r"""B2-3 — `BehavioralCollateral` and the $U_{\text{unaffected}}$ **candidate** constructors.

$$\boxed{\text{BehavioralCollateral} = V_{\text{unaffected,pre}} -
V_{\text{unaffected,post}}}$$

**What this module proves, stated narrowly: constructor-local blindness.**

$$\boxed{\text{a constructor cannot be *handed* an arm, a law, a ledger, a truth or a post-outcome}}$$

The signatures take `(domain, visited)` and nothing else, so no argument through which forbidden
material could arrive exists. That is **not** the same as truth-blindness of the set, and the
difference is the whole reason this paragraph exists: a caller can compute `domain = f(Gamma_P*)`
and `visited` from a post-update trajectory, and the constructor would be locally clean while the
set was truth-derived. A signature is not a provenance.

$$\boxed{\text{constructor-local blindness} \neq \text{truth-blind} + \text{pre-update}}$$

The real properties are the **paired runner's**, and B2-4 must gate all three of them:

1. **input provenance** — `domain` and `visited` come from a pre-update learner-visible source, and
   the runner owns that source rather than receiving it;
2. **construction before either arm executes** — and before $\Delta W$ exists at all;
3. **one object** — `u_reference is u_treatment`, an identity rather than an agreement. Two
   constructions that happen to agree are exactly what a shared object is not.

Until then, a candidate set produced here is a *fixture*, not evidence about blindness.

**Several candidates, and no choice.** A79 §67.4 leaves the construction to the development stage
*on measurement properties*; this module therefore provides more than one and refuses to pick:
`select_construction` raises, and there is no defaulted candidate anywhere. Choosing because a
candidate reports a larger effect on a synthetic fixture would be choosing the estimator by its
answer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.unaffected import UnaffectedSet as SceneUnaffectedSet
from rfl_rebuild.learner.store import LearnerPersistentState

__all__ = [
    "CANDIDATE_CONSTRUCTIONS",
    "UNAFFECTED_CONSTRUCTIONS",
    "UnaffectedSet",
    "behavioral_collateral",
    "behavioral_collateral_scenes",
    "measure_scene_map",
    "measured_scene_collateral",
    "scene_collateral",
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


def _unaffected_state_parity(domain, visited, *, parity: int) -> UnaffectedSet:
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
#:
#: `state_parity` is registered as two **fixed** candidates rather than as one parametrised family
#: with a defaulted parity: a family whose unspecified member is "even" carries a choice inside a
#: registry whose whole point is that no choice has been made.
CANDIDATE_CONSTRUCTIONS: Mapping[str, Callable] = {
    "visited_complement": _unaffected_visited_complement,
    "state_parity_even": lambda domain, visited: _unaffected_state_parity(
        domain, visited, parity=0),
    "state_parity_odd": lambda domain, visited: _unaffected_state_parity(
        domain, visited, parity=1),
}

#: Kept under the name the docs use.
UNAFFECTED_CONSTRUCTIONS = CANDIDATE_CONSTRUCTIONS


def select_construction(name: str) -> Callable:
    r"""$$\boxed{\text{the construction is chosen at the development stage, not here}}$$

    A79 §67.4 leaves the choice to measurement properties gathered under the development protocol,
    and A83 §71.4 keeps that choice open. This function exists so that a caller who wants "the"
    construction is told to say which one, rather than being handed a default that would become the
    decision by inaction.
    """
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


# --------------------------------------------------------------------------- #
# A89 §77.8 — the same instrument, re-typed onto the surviving unit
# --------------------------------------------------------------------------- #

def behavioral_collateral_scenes(unaffected, *, values_pre: Mapping,
                                 values_post: Mapping) -> float:
    r"""$V_{\text{unaffected,pre}} - V_{\text{unaffected,post}}$ over **evaluation scenes**.

    A89 §77.8's re-typing, and deliberately the *same* functional as
    :func:`behavioral_collateral`: the mean of the per-unit values over exactly the set that was handed
    in. The measurement's unit changed when the screening gave $U_2$ the survival; the definition of
    the metric did not.

    Both mappings must cover exactly the set -- a missing unit would shrink the denominator silently and
    an extra one would import a unit the set does not contain -- and every value must be a finite real,
    because the contract is $V_W : U \to \mathbb R_{\text{finite}}$.
    """
    if type(unaffected) is not SceneUnaffectedSet:
        raise ProtocolError(
            f"the unaffected set {unaffected!r} has type {type(unaffected).__name__}, not the "
            "evaluation-scene UnaffectedSet; a bare container would carry no construction")
    expected = set(unaffected.units)
    for name, values in (("pre", values_pre), ("post", values_post)):
        if not isinstance(values, Mapping):
            raise ProtocolError(f"the {name}-update values are not a mapping")
        got = set(values)
        if got != expected:
            extra = sorted((e.key for e in got - expected))[:3]
            missing = sorted((e.key for e in expected - got))[:3]
            raise ProtocolError(
                f"the {name}-update values cover {len(got)} units but the unaffected set has "
                f"{len(expected)} (extra {extra!r}, missing {missing!r}); the metric is defined on "
                "exactly the set it was given")
        for unit in unaffected.units:
            v = values[unit]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ProtocolError(f"the {name}-update value at {unit!r} is {v!r}, not a real number")
            if not math.isfinite(float(v)):
                raise ProtocolError(
                    f"the {name}-update value at {unit!r} is {v!r}; the contract is R_finite")
    pre = sum(float(values_pre[u]) for u in unaffected.units) / len(unaffected.units)
    post = sum(float(values_post[u]) for u in unaffected.units) / len(unaffected.units)
    return pre - post


def measure_scene_map(learner, units, *, q_reference) -> dict:
    r"""$V_W^{meas}(u)$ for every unit, through the **audited** environment.

    One rollout per scene, from the learner state it is handed: the measured side of the calibration
    reads the state, and nothing here can substitute an index, a cached value or a post-processed number
    for a measurement.
    """
    if type(learner) is not LearnerPersistentState:
        raise ProtocolError(f"the measurement reads a learner state, got {type(learner).__name__}")
    out = {}
    for unit in units:
        trace = learned_rollout(learner, kappa=unit.kappa, tape=unit.tape,
                                base_option=unit.base_option, q_reference=q_reference)
        out[unit] = float(trace.return_value)
    if set(out) != set(units):
        raise ProtocolError("the measured map is not closed over the unit set")
    return out


def scene_collateral(unaffected, pre_learner, post_learner, *, q_reference) -> dict:
    r"""$V_{\text{unaffected,pre}} - V_{\text{unaffected,post}}$ for a **pair** of learner states.

    The production shape: two states arrive, each is measured over the same unit set through the
    audited environment, and the metric is the same functional. Nothing is cloned and nothing is
    patched here, because both sides already exist.
    """
    values_pre = measure_scene_map(pre_learner, unaffected.units, q_reference=q_reference)
    values_post = measure_scene_map(post_learner, unaffected.units, q_reference=q_reference)
    return {
        "value": behavioral_collateral_scenes(unaffected, values_pre=values_pre,
                                              values_post=values_post),
        "values_pre": values_pre,
        "values_post": values_post,
    }


def _override_diff(pre, post) -> dict:
    """The stores in which ``post`` differs from ``pre``, as ``{kind: {address: value}}``."""
    out = {}
    for name, before, after in (("q", pre.q_overrides, post.q_overrides),
                                ("controller", pre.controller_overrides, post.controller_overrides),
                                ("process", pre.process_overrides, post.process_overrides)):
        added = {k: after[k] for k in after if k not in before or before[k] != after[k]}
        removed = [k for k in before if k not in after]
        if removed:
            raise ProtocolError(
                f"the post state lost {name} overrides the pre state carried ({removed[:3]!r}); a "
                "fresh state would do exactly that, and the pair would no longer be pre + one edit")
        if added:
            out[name] = added
    return out


def measured_scene_collateral(unaffected, learner, edit, *, q_reference) -> dict:
    r"""The measured side of Gate A for one cell, with the edit that was frozen before it ran.

    $$\boxed{W_{\text{post}} = W_{\text{pre}} + \Delta W^{\text{spill}}}$$

    The post state is a **clone** of the pre state plus that one substrate edit, and what the gate
    checks is the **differential** rather than a count: a pre state carrying overrides of its own must
    keep them, and a fresh state with one override would satisfy a count while losing them. On an
    empty pre state the two readings coincide, which is exactly why the calibration fixture alone could
    not tell them apart.
    """
    from rfl_rebuild.learner.store import LearnerPersistentState as _State

    if type(learner) is not _State:
        raise ProtocolError(f"the measured side starts from a learner state, got {type(learner).__name__}")
    post = learner.clone()
    post.apply_transaction([edit.substrate_edit], q_reference=q_reference)
    added = _override_diff(learner, post)
    if added != {_store_name(edit.substrate_edit): {edit.substrate_edit.address:
                                                    edit.substrate_edit.value}}:
        raise ProtocolError(
            f"the post state differs from the pre state by {added!r}, not by exactly the fixture's "
            "edit; the pair must be pre + one edit")
    measured = scene_collateral(unaffected, learner, post, q_reference=q_reference)
    measured["override_diff"] = added
    return measured


def _store_name(edit) -> str:
    from rfl_rebuild.learner.store import CONTROLLER, PROCESS, Q
    return {Q: "q", CONTROLLER: "controller", PROCESS: "process"}[edit.store]
