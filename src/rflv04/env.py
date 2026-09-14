"""CausalRepairGrid-v04.

The v0.3 grid hard-coded H/L as the ontology of failure.  This environment does
not.  It exposes a small, fully enumerable tabular SCM in which four failure
kinds are **operationally distinguishable by intervention**, and in which
`intent` and `realized` actions are recorded separately so that an execution
fault can never be confused with a bad decision.

Structure
---------
State is ``(g, x, y, o, phase)``:

    g      in {0,1}          which lane holds the exit (episode context)
    x      in {0..X_MAX}     process position; the exit is at x = X_MAX
    y      in {0,1}          current lane
    o      in {0,1,-1}       the plan once chosen, -1 while in PLAN
    phase  in {PLAN, ACT, ABSORB}

Actions share one integer space and are masked per phase:

    PLAN phase   {PLAN_A, PLAN_B}
    ACT phase    {ADVANCE, SWITCH, WAIT, RECOVER}

Success requires reaching ``x = X_MAX`` on lane ``g``.  Every terminal enters
ABSORB and occupies the remaining steps to the fixed horizon, so early and late
outcomes settle at the same step (`gamma = 1`, no step reward, no timeout
penalty of its own).

The four injected fault kinds are *not* the taxonomy.  They only generate
candidate scenes; `oracle.py` then decides -- by enumerating interventions --
which family a scene actually belongs to.
"""

from __future__ import annotations

from dataclasses import dataclass, field

X_MAX = 3
"""Corridor length, as the plan specifies.

The blocking parameter turned out to be the horizon, not the corridor.  With
``H = 8`` against a 4-step path there are 4-5 spare steps, so a delay-heavy
policy is *also* optimal; the "correct action" is then not policy-independent,
the Knowledge Set is empty or circular, and no induced damage can persist.  See
``HORIZON`` below.
"""

SCENE_FAULT_NOTE = """\
Structural flaw found while calibrating, and it is the reason Alpha cannot
discriminate at any difficulty:

    A decision or execution fault is implemented as the environment OVERRIDING
    the agent's action from t* onward.  The bad choice is therefore exogenous
    to the agent's policy -- there is nothing for the agent to learn, and no
    credit representation can improve task success.  That is exactly the
    pattern the smoke shows: every arm lands on an identical success curve
    while collateral and site counts differ.

    The plan intends a decision failure to be a bad DECISION BY THE AGENT
    ("system already decided a_t but the execution differs" is reserved for
    Execution).  To make that real, a decision fault must corrupt the agent's
    own value estimate at the critical state so the greedy action is genuinely
    bad, and the diagnostic update must then be able to repair it.  Overriding
    the action cannot be repaired, so it cannot be measured.

    Fixing this is a change to the fault injector, not to any arm, and it must
    be re-validated on the NoCorrection baseline before Alpha results mean
    anything.
"""
LANES = 2
HORIZON = 4
"""Episode horizon, set so the long path has *zero* slack.

The long path (lane differs from the plan) costs exactly ``X_MAX + 1 = 4``
steps.  At ``H = 4`` no step can be wasted, so the correct action is uniquely
determined at every state and ``WAIT`` is never free.  The plan suggests
``H = 8`` with stress horizons 6 and 10; at that ratio the task admits delay
policies, which is what made the Knowledge Set unestablishable.

The short path (lane already matches the plan) still has one spare step, which
is recorded rather than hidden: ``KI`` margins for those states are weaker, and
the calibration script reports them separately.
"""

PLAN, ACT, ABSORB = 0, 1, 2
PHASE_NAMES = ("PLAN", "ACT", "ABSORB")

PLAN_A, PLAN_B, ADVANCE, SWITCH, WAIT, RECOVER = 0, 1, 2, 3, 4, 5
N_ACTIONS = 6
PLAN_ACTIONS = (PLAN_A, PLAN_B)
ACT_ACTIONS = (ADVANCE, SWITCH, WAIT, RECOVER)
ACTION_NAMES = ("PLAN_A", "PLAN_B", "ADVANCE", "SWITCH", "WAIT", "RECOVER")

SUCCESS = "SUCCESS"
TIMEOUT = "TIMEOUT"


def valid_actions(phase: int) -> tuple[int, ...]:
    """Action mask by phase.  A PLAN-phase state cannot emit an ACT action."""
    if phase == PLAN:
        return PLAN_ACTIONS
    if phase == ACT:
        return ACT_ACTIONS
    return ()


def reference_action(x: int, y: int, o: int) -> int:
    """The correct ACT-phase action for the chosen plan ``o``."""
    if y != o:
        return SWITCH
    if x < X_MAX:
        return ADVANCE
    return WAIT


def apply_action(x: int, y: int, o: int, action: int) -> tuple[int, int]:
    """Realized transition.  Deterministic; the only randomness is in the scene."""
    if action == ADVANCE:
        return min(x + 1, X_MAX), y
    if action == SWITCH:
        return x, 1 - y
    if action == RECOVER:
        return x, o
    if action == WAIT:
        return x, y
    return x, y


@dataclass(frozen=True)
class Scene:
    """A candidate episode configuration.  Family is *not* asserted here."""

    scene_id: str
    g: int
    plan: int
    decision_fault_at: int | None = None
    decision_fault_action: int = WAIT
    execution_fault_at: int | None = None
    execution_fault_action: int = WAIT
    horizon: int = HORIZON

    @property
    def plan_is_correct(self) -> bool:
        return self.plan == self.g


@dataclass
class Step:
    t: int
    state: tuple
    intent: int
    realized: int
    next_state: tuple
    q_row_before: list = field(default_factory=list)
    q_row_after: list = field(default_factory=list)
    oracle_critical: bool = False
    selected_for_update: bool = False
    update_target: float | None = None
    delta_q: float = 0.0
    provenance: str = "FACTUAL"

    @property
    def intent_matches_realized(self) -> bool:
        return self.intent == self.realized


@dataclass
class Trace:
    scene: Scene
    steps: list = field(default_factory=list)
    terminal: str = TIMEOUT
    return_value: float = -1.0

    @property
    def success(self) -> bool:
        return self.terminal == SUCCESS

    @property
    def act_steps(self) -> list:
        return [s for s in self.steps if s.state[4] == ACT]

    def has_execution_deviation(self) -> bool:
        """A realized action that differs from the agent's own intent."""
        return any(not s.intent_matches_realized for s in self.act_steps)


def rollout(scene: Scene, *, reward_mode: str = "A") -> Trace:
    """Execute one scene.  Randomness enters only through the scene itself."""
    g, o = scene.g, -1
    x, y = 0, 0
    trace = Trace(scene=scene)
    terminal = TIMEOUT
    absorbing = False

    for t in range(0, scene.horizon + 1):
        if t == 0:
            o = scene.plan
            step = Step(t=0, state=(g, x, y, -1, PLAN), intent=PLAN_A + o,
                        realized=PLAN_A + o, next_state=(g, x, y, o, ACT))
            trace.steps.append(step)
            continue

        if absorbing:
            trace.steps.append(Step(t=t, state=(g, x, y, o, ABSORB),
                                    intent=-1, realized=-1,
                                    next_state=(g, x, y, o, ABSORB)))
            continue

        ref = reference_action(x, y, o)
        intent = realized = ref
        if scene.decision_fault_at is not None and t >= scene.decision_fault_at:
            # The agent itself stops choosing well, and keeps not choosing well.
            # A one-step slip would be absorbed by the horizon slack: with a
            # 4-cell corridor and H=8 there are 4-5 spare steps, so a single
            # wasted step is never fatal and a single-step repair is never
            # sufficient.  Sustaining the fault is what makes both real.
            intent = realized = scene.decision_fault_action
        if scene.execution_fault_at is not None and t >= scene.execution_fault_at:
            # The agent intends the reference action; the actuator realizes
            # something else, and keeps doing so.
            realized = scene.execution_fault_action

        nx, ny = apply_action(x, y, o, realized)
        trace.steps.append(Step(t=t, state=(g, x, y, o, ACT), intent=intent,
                                realized=realized, next_state=(g, nx, ny, o, ACT)))
        x, y = nx, ny

        if x == X_MAX and y == g:
            terminal = SUCCESS
        elif t == scene.horizon:
            terminal = TIMEOUT
        if terminal != TIMEOUT or t == scene.horizon:
            absorbing = True

    trace.terminal = terminal
    trace.return_value = 1.0 if terminal == SUCCESS else (-1.0 if reward_mode == "A" else 0.0)
    return trace


# --------------------------------------------------------------------------
# Interventions
# --------------------------------------------------------------------------

# An intervention is a frozenset of primitives:
#   ("plan", lane)        re-choose the plan
#   ("step", t, action)   force the realized action at t
#   ("exec", t)           repair the actuator at t (realized := intent)
PlanFix = tuple  # ("plan", lane)
StepFix = tuple  # ("step", t, action)
ExecFix = tuple  # ("exec", t)


def rollout_intervened(scene: Scene, intervention: frozenset, *, reward_mode: str = "A") -> Trace:
    """Re-execute the scene under an intervention.

    The latent scene variables are held fixed -- this is the common-random-
    numbers discipline that makes the counterfactual causal rather than just
    a luckier re-run.
    """
    if not intervention:
        return rollout(scene, reward_mode=reward_mode)

    plan_override = None
    step_overrides: dict = {}
    exec_repairs: set = set()
    unstick_at: int | None = None
    exec_from: int | None = None
    for prim in intervention:
        if prim[0] == "plan":
            plan_override = prim[1]
        elif prim[0] == "unstick":
            unstick_at = prim[1] if unstick_at is None else min(unstick_at, prim[1])
        elif prim[0] == "exec":
            exec_repairs.add(prim[1])
            exec_from = prim[1] if exec_from is None else min(exec_from, prim[1])
        elif prim[0] == "step":
            step_overrides[prim[1]] = prim[2]
        else:
            raise ValueError(f"unknown intervention primitive {prim!r}")

    g = scene.g
    o = plan_override if plan_override is not None else scene.plan
    x, y = 0, 0
    trace = Trace(scene=scene)
    terminal = TIMEOUT
    absorbing = False

    for t in range(0, scene.horizon + 1):
        if t == 0:
            trace.steps.append(Step(t=0, state=(g, x, y, -1, PLAN),
                                    intent=PLAN_A + o, realized=PLAN_A + o,
                                    next_state=(g, x, y, o, ACT)))
            continue
        if absorbing:
            trace.steps.append(Step(t=t, state=(g, x, y, o, ABSORB), intent=-1,
                                    realized=-1, next_state=(g, x, y, o, ABSORB)))
            continue

        ref = reference_action(x, y, o)
        intent = realized = ref
        if scene.decision_fault_at is not None and t >= scene.decision_fault_at:
            if unstick_at is None or t < unstick_at:
                intent = realized = scene.decision_fault_action
        if scene.execution_fault_at is not None and t >= scene.execution_fault_at:
            if exec_from is None or t < exec_from:
                realized = scene.execution_fault_action
        if t in exec_repairs:
            realized = intent           # actuator repaired at this step
        if t in step_overrides:
            intent = realized = step_overrides[t]

        nx, ny = apply_action(x, y, o, realized)
        trace.steps.append(Step(t=t, state=(g, x, y, o, ACT), intent=intent,
                                realized=realized, next_state=(g, nx, ny, o, ACT),
                                provenance="CF_VALIDATED"))
        x, y = nx, ny
        if x == X_MAX and y == g:
            terminal = SUCCESS
        elif t == scene.horizon:
            terminal = TIMEOUT
        if terminal != TIMEOUT or t == scene.horizon:
            absorbing = True

    trace.terminal = terminal
    trace.return_value = 1.0 if terminal == SUCCESS else (-1.0 if reward_mode == "A" else 0.0)
    return trace


def make_scene(scene_id: str, *, kind: str, g: int, rng, horizon: int = HORIZON) -> Scene:
    """Draw a *candidate* scene of a requested injection kind.

    ``kind`` selects which fault is injected, but it is only a proposal: the
    scene's true family is decided later by intervention enumeration.
    """
    plan_correct = kind in ("plan_ok",)
    wrong_plan = 1 - g
    fault_t = int(rng.integers(1, min(4, horizon)))
    if kind == "plan_only":
        return Scene(scene_id, g, wrong_plan, horizon=horizon)
    if kind == "decision_only":
        return Scene(scene_id, g, g, decision_fault_at=fault_t,
                     decision_fault_action=WAIT, horizon=horizon)
    if kind == "execution_only":
        return Scene(scene_id, g, g, execution_fault_at=fault_t,
                     execution_fault_action=WAIT, horizon=horizon)
    if kind == "whole":
        return Scene(scene_id, g, wrong_plan, decision_fault_at=fault_t,
                     decision_fault_action=WAIT, horizon=horizon)
    if kind == "clean":
        return Scene(scene_id, g, g, horizon=horizon)
    raise ValueError(kind)
