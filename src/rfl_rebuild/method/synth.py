"""A62 — ``Q_syn(I)``: the sequence-informed query synthesis family.

``SeqThenQuery`` is pre-registered as "sequence evidence, then targeted
interventions + audits" (`06-V01R.md` §3), and `14` §2.2 says it "selects its own
queries". So conditioning its candidate queries on `FactualEvidence` is not a
leak -- it is what the arm is for. The distinction that matters is

    hidden conditioning on information the arm never received
  vs
    conditioning on information explicitly given to the arm

dev_v1 was the first. This is the second.

The family is a PURE function of the evidence and the public grammar:

    Q_syn(I) = f(I^factual_{0:T}, grammar)

``synth_queries`` accepts nothing else -- no ``world_id``, no ``block_id``, no
``DenseSupport``, no true scene, no feedback, no ``Z``, no fault parameters, no
evaluator truth. Results are ordered by the GLOBAL registry canonical index, not
by set or ``repr`` order, so the tie-break in the greedy score is deterministic
and seed-independent.

The family is FIXED once the initial evidence is fixed; only
``Q_safe(H_t)`` moves as the belief shrinks (A50). Nothing here invents a new
address in response to a query result.
"""

from __future__ import annotations

import inspect
from typing import Callable, Sequence

from .registry import proc_audit, audit, process, decision, execution, sort_key

__all__ = ["synthesise", "synth_queries", "candidate_set"]


def synth_queries(evidence, *, options: Sequence[int],
                  option_actions: Callable, registry_index: dict) -> tuple:
    """``Q_syn(I)`` as a tuple ordered by global canonical registry index.

    ``evidence`` is :class:`FactualEvidence` and nothing more. ``option_actions``
    is the public option/action grammar; ``registry_index`` maps a query spec to
    its position in ``Q_global``.
    """
    out = {proc_audit()}
    steps = tuple(evidence.steps)
    for s in steps:
        out.add(audit(s.t))
    z_in_force = evidence.z_in_force
    for z in options:
        if z != z_in_force:
            out.add(process(z))
    for s in steps:
        # the state the learner was actually in, rebuilt from its own step
        st = _state(s)
        for a in option_actions(s.z, s.m, st):
            if a != s.a_cmd:
                out.add(decision(s.t, a))
        out.add(execution(s.x, s.y, s.t, s.kappa, s.phi, s.a_cmd))
    missing = [q for q in out if q not in registry_index]
    if missing:
        raise ValueError(f"Q_syn produced queries outside Q_global: {missing[:3]}")
    return tuple(sorted(out, key=lambda q: registry_index[q]))


def _state(s):
    from rfl_rebuild.env.kernel import State
    return State(x=s.x, y=s.y, t=s.t, kappa=s.kappa, phi=s.phi)


def candidate_set(Q_syn: Sequence[tuple], belief, safe: Callable,
                  asked: Sequence[tuple]) -> tuple:
    """``Q_t = Q_syn & Q_safe(H_t) \\ Q_asked``, in Q_syn order."""
    asked = set(map(tuple, asked))
    return tuple(q for q in Q_syn if q not in asked and safe(belief, q))


def synthesise(*args, **kwargs):        # pragma: no cover - alias
    return synth_queries(*args, **kwargs)


def signature_accepts_only_evidence_and_grammar() -> bool:
    """Mechanical check for acceptance test 2."""
    params = set(inspect.signature(synth_queries).parameters)
    forbidden = {"world_id", "block_id", "support", "true_world", "scene",
                 "feedback", "Z", "fire", "params", "fault"}
    return not (params & forbidden) and params == {"evidence", "options",
                                                   "option_actions",
                                                   "registry_index"}
