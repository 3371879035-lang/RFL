"""Explicit query-free candidate algorithms; NOT a selected science family.

Only closed FactualEvidence enters any algorithm. No source handle, reference
Q/policy, fire vector, evaluator truth, terminal outcome, regime, hypothesis
support, B1 tier assistance or query session enters this module. The execution
mismatch rule is a NEW heuristic, not CSL, J_L, or causal identification: a
plant fault can produce the same observations as a controller deviation.
"""
from __future__ import annotations

import math
from rfl_rebuild.method.contract import FactualEvidence, FactualStep, ProtocolError
from rfl_rebuild.method.credit import CausalProposal, TrajectoryProposal


def _input(evidence):
    if type(evidence) is not FactualEvidence or type(evidence.steps) is not tuple or not evidence.steps:
        raise ProtocolError("ordinary candidates require exact closed nonempty factual evidence")
    if any(type(x) is not int for x in (evidence.z_in_force, evidence.kappa, evidence.phi)):
        raise ProtocolError("ordinary context fields must be true integers")
    for s in evidence.steps:
        if type(s) is not FactualStep or any(type(x) is not int for x in
            (s.x, s.y, s.t, s.kappa, s.phi, s.z, s.m, s.a_cmd, s.a_realized)):
            raise ProtocolError("ordinary candidates require closed typed learner steps")
        if type(s.reward) is not float or not math.isfinite(s.reward):
            raise ProtocolError("ordinary factual reward must be finite native float")


def trajectory_credit(evidence):
    """Inherited R_trajectory native {Episode}, before original eta_trajectory.

    The upstream owned router, not this method, establishes observed failure.
    This coarse proposal makes no inference about a particular cause or site.
    """
    _input(evidence)
    return TrajectoryProposal(frozenset({"Episode"}))


def observed_execution_credit(evidence):
    """NEW candidate: credit EVERY observed command/realization mismatch.

    This is an intentionally limited observable heuristic. It cannot separate
    controller and plant, recover the hidden command u, diagnose process commit
    or decide whether a commanded action was optimal. Never call it a complete
    persistent/transient fault model. No 'first' witness or truth-based pruning.
    """
    _input(evidence)
    return CausalProposal(frozenset(f"ControllerSite_{s.x}_{s.y}_{s.t}_{s.a_cmd}"
        for s in evidence.steps if s.a_cmd != s.a_realized))


def abstain_credit(evidence):
    """Explicit empty-credit baseline candidate, NOT Unknown/NoWrite."""
    _input(evidence)
    return CausalProposal(frozenset())
