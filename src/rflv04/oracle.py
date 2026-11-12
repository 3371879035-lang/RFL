"""Intervention-defined failure taxonomy and oracle repair enumeration.

The plan's strongest anti-cheating rule is that a scene must not be labelled
``decision_error`` and then have that label treated as truth.  A scene is only
allowed to *count* as a family if an intervention proves it:

    Plan        do(o = o') at t = 0 suffices, and there is no execution deviation
    Decision    plan is correct, no execution deviation, some t* where
                do(a_t* = a') flips the outcome, and a plan fix is NOT the repair
    Execution   intent == reference and realized != intent, and repairing the
                actuator (realized := intent) restores success
    WholeProcess no single intervention suffices, but a small joint repair does
                (minimal sufficient set size in {2, 3})
    Unknown     no intervention in the learner's known space suffices

``V_true`` and the regret are evaluator-only.  They are computed by applying a
repair as a *rule* and evaluating it on freshly drawn episodes, so a repair that
merely patches the observed timestep is scored by how badly it generalises --
which is exactly the distinction a scene-specific notion of "sufficient" cannot
see.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from .env import (
    ACT,
    ACT_ACTIONS,
    HORIZON,
    PLAN,
    SUCCESS,
    WAIT,
    Scene,
    Trace,
    reference_action,
    rollout,
    rollout_intervened,
)

PLAN_FAILURE_UNUSED = None  # kept only so the removed alias is greppable
FAMILIES = ("Plan", "Decision", "Execution", "WholeProcess", "Unknown")
MAX_JOINT = 3


@dataclass(frozen=True)
class Repair:
    """One candidate correction."""

    primitives: frozenset
    source: str = "oracle"

    @property
    def size(self) -> int:
        return len(self.primitives)

    @property
    def site(self) -> str:
        if not self.primitives:
            return "KEEP"
        kinds = {p[0] for p in self.primitives}
        if kinds == {"plan"}:
            return "PLAN"
        if kinds == {"exec"}:
            return "EXECUTION"
        if kinds == {"unstick"}:
            return "DECISION"
        return "JOINT"

    def describe(self) -> str:
        return "+".join(sorted(f"{p[0]}:{p[1:]}" for p in self.primitives))


@dataclass
class OracleResult:
    scene_id: str
    family: str
    sufficient: list = field(default_factory=list)
    minimal_size: int | None = None
    best: Repair | None = None
    best_value: float | None = None
    n_enumerated: int = 0


# --------------------------------------------------------------------------
# Intervention enumeration
# --------------------------------------------------------------------------


def single_interventions(scene: Scene) -> list:
    """All size-1 interventions worth trying."""
    out = []
    for lane in (0, 1):
        if lane != scene.plan:
            out.append(frozenset({("plan", lane)}))
    if scene.decision_fault_at is not None:
        out.append(frozenset({("unstick", scene.decision_fault_at)}))
    if scene.execution_fault_at is not None:
        out.append(frozenset({("exec", scene.execution_fault_at)}))
    return out


def joint_interventions(scene: Scene, size: int = 2) -> list:
    """All size-``size`` interventions built from the available primitives."""
    prims = []
    for lane in (0, 1):
        if lane != scene.plan:
            prims.append(("plan", lane))
    if scene.decision_fault_at is not None:
        prims.append(("unstick", scene.decision_fault_at))
    if scene.execution_fault_at is not None:
        prims.append(("exec", scene.execution_fault_at))
    out = []
    for combo in combinations(prims, size):
        out.append(frozenset(combo))
    return out


def suffices(scene: Scene, intervention: frozenset) -> bool:
    return rollout_intervened(scene, intervention).terminal == SUCCESS


def enumerate_sufficient(scene: Scene) -> tuple[list, int]:
    """Every sufficient intervention up to ``MAX_JOINT``, and how many were tried."""
    tried = 0
    sufficient: list = []
    singles = single_interventions(scene)
    tried += len(singles)
    for iv in singles:
        if suffices(scene, iv):
            sufficient.append(Repair(iv))
    if sufficient:
        return sufficient, tried
    for size in (2, MAX_JOINT):
        for iv in joint_interventions(scene, size):
            tried += 1
            if suffices(scene, iv):
                sufficient.append(Repair(iv))
        if sufficient:
            break
    return sufficient, tried


def scene_from_trace(trace) -> Scene:
    """Reconstruct the oracle's view of what actually happened.

    Faults must be classified from the trace the agent *produced*, not from the
    generator's intentions: the plan is always the agent's own choice, and the
    critical decision is the first timestep where its realized action left the
    reference path.
    """
    scene = trace.scene
    act = [s for s in trace.steps if s.state[4] == ACT and s.intent >= 0]
    critical_t = None
    for step in act:
        ref = reference_action(step.state[1], step.state[2], step.state[3])
        if step.realized != ref:
            critical_t = step.t
            break
    return Scene(
        scene_id=scene.scene_id,
        g=scene.g,
        plan=trace.steps[0].next_state[3],      # what the agent actually chose
        decision_fault_at=critical_t,
        decision_fault_action=(next((s.realized for s in act if s.t == critical_t), WAIT)
                               if critical_t is not None else WAIT),
        execution_fault_at=scene.execution_fault_at,
        execution_fault_action=scene.execution_fault_action,
        horizon=scene.horizon,
    )


def classify(scene: Scene, trace: Trace | None = None) -> OracleResult:
    """Decide the family by intervention, not by the injection kind."""
    trace = trace or rollout(scene)
    result = OracleResult(scene_id=scene.scene_id, family="Unknown")
    if trace.success:
        result.family = "CLEAN"
        return result

    sufficient, tried = enumerate_sufficient(scene)
    result.sufficient = sufficient
    result.n_enumerated = tried
    if not sufficient:
        result.family = "Unknown"
        return result

    result.minimal_size = min(r.size for r in sufficient)
    minimal = [r for r in sufficient if r.size == result.minimal_size]

    plan_fix = [r for r in minimal if r.site == "PLAN"]
    exec_fix = [r for r in minimal if r.site == "EXECUTION"]
    decision_fix = [r for r in minimal if r.site == "DECISION"]

    if plan_fix and not trace.has_execution_deviation():
        result.family = "Plan"
    elif exec_fix and trace.has_execution_deviation():
        result.family = "Execution"
    elif decision_fix and not trace.has_execution_deviation():
        result.family = "Decision"
    elif result.minimal_size > 1:
        result.family = "WholeProcess"
    else:
        result.family = "Unknown"
    return result


# --------------------------------------------------------------------------
# Long-term value (evaluator only)
# --------------------------------------------------------------------------


def repair_value(scene: Scene, repair: Repair, *, n_samples: int = 64) -> float:
    """``V_true(c) = E[G | do(c)]`` over the context distribution.

    Evaluator-only; never handed to a learner.  The repair is applied as a
    **rule** on freshly drawn contexts, which is what separates a plan repair
    (``plan := context``, generalises) from an execution or decision repair
    (keeps the original plan, so it inherits that plan's errors).
    """
    has_plan = any(p[0] == "plan" for p in repair.primitives)
    has_unstick = any(p[0] == "unstick" for p in repair.primitives)
    has_exec = any(p[0] == "exec" for p in repair.primitives)

    total = 0.0
    for i in range(n_samples):
        g = i % 2
        fresh = Scene(
            f"V{i}", g, g if has_plan else scene.plan,
            decision_fault_at=(None if has_unstick else scene.decision_fault_at),
            decision_fault_action=scene.decision_fault_action,
            execution_fault_at=(None if has_exec else scene.execution_fault_at),
            execution_fault_action=scene.execution_fault_action,
            horizon=scene.horizon,
        )
        total += rollout(fresh).return_value
    return total / n_samples


def _clean_value(scene: Scene, *, n_samples: int = 64) -> float:
    total = 0.0
    for i in range(n_samples):
        g = i % 2
        total += rollout(Scene(f"C{i}", g, g, horizon=scene.horizon)).return_value
    return total / n_samples


def oracle_repair_set(scene: Scene, *, n_samples: int = 64) -> OracleResult:
    """All sufficient repairs plus the one with the highest long-term value."""
    result = classify(scene)
    if not result.sufficient:
        return result
    scored = [(repair_value(scene, r, n_samples=n_samples), r) for r in result.sufficient]
    scored.sort(key=lambda pair: (-pair[0], pair[1].describe()))
    result.best_value, result.best = scored[0]
    return result


def repair_regret(scene: Scene, selected: Repair | None, *, n_samples: int = 64) -> float | None:
    """``V_true(c*) - V_true(c_selected)``.

    ``None`` when either side is undefined, rather than a fabricated number.
    """
    res = oracle_repair_set(scene, n_samples=n_samples)
    if res.best is None:
        return None
    if selected is None or not selected.primitives:
        chosen = repair_value(scene, Repair(frozenset()), n_samples=n_samples)
    else:
        chosen = repair_value(scene, selected, n_samples=n_samples)
    return float(res.best_value - chosen)
