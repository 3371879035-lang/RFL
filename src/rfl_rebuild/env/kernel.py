"""RFL-Rebuild — the minimal SCM kernel.

This is the **world model and nothing else**. It is the single source of truth
for what happens, and it deliberately contains no learner:

* it does **not** compute ``argmax_a Q_D*(s, z, m, a)`` and does not own
  :math:`\\pi_D^{*}` — that is the exact DP, authorised separately
  (``docs/rebuild/00-INDEX.md`` §7);
* it does **not** train, run RFL, or perform attribution;
* :func:`step` receives an already-decided ``a_cmd``; it never chooses one;
* :func:`rollout` takes an external command provider and refuses to invent a
  reference policy for convenience.

The specifications implemented here, section by section:

======================================  ==========================================
``01-OBSERVATION-MODEL.md`` §2.1, §2.1.1  what is observable, what the learner holds
``02-SCM.md`` §2.3–§2.4.7               options, automata, ``do(d_t)`` admissibility
``02-SCM.md`` §5.0, §5.0.1, §5.0.2      joint interventions, MALFORMED, ``Z_D``
``11-ENVIRONMENT.md`` §1, §1.1          state, and the order of events in a step
``11-ENVIRONMENT.md`` §2, §3            context lane, phase, actions, legality
``11-ENVIRONMENT.md`` §5.2              the three-channel controller/plant split
``11-ENVIRONMENT.md`` §6.4–§6.6         ``Z_P``, ``do(z=z')``, ``Z_U``
``11-ENVIRONMENT.md`` §8.1.1            the semantic tape: keys, measure, decoder
======================================  ==========================================

Nothing here may be reordered or "improved" without an amendment. In particular
the event order of §1.1 and the write-disjointness of the option automata are
load-bearing and were each the subject of a P0 amendment (A29, A17).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Mapping, Sequence

__all__ = [
    "State", "ControlState", "StepResult", "Outcome",
    "FaultMask", "DecisionOverride", "ControllerFault", "PlantFault", "Trap",
    "SemanticTape", "TapeKey",
    "Intervention", "InterventionSet", "MalformedIntervention",
    "ACTIONS", "Action",
    "START", "GOAL", "CONTESTED", "WALLS", "HORIZON",
    "step", "rollout", "option_actions", "automaton_transition",
    "legal_actions", "hazard_at", "option_ids", "initial_control",
    "but_for_relevance",
]

# --------------------------------------------------------------------------- #
# Environment constants — 11-ENVIRONMENT.md §1, §2, §3
# --------------------------------------------------------------------------- #

HORIZON: int = 12
"""``H``: episode length, fixed (11 §1)."""

STEP_COST: float = -0.02
"""Per-step cost (11 §1). Makes short routes better, which is what gives the
option semantics of 02 §2.3 any content. See A14: with a policy-dependent step
count the two reward modes are *not* affine transforms."""

REWARD_SUCCESS: float = +1.0
REWARD_FAILURE_A: float = -1.0
REWARD_FAILURE_B: float = 0.0

START: tuple[int, int] = (0, 2)
GOAL: tuple[int, int] = (4, 2)
CONTESTED: tuple[int, int] = (2, 2)
"""The cell the hazard patrols (11 §1)."""

WALLS: frozenset[tuple[int, int]] = frozenset(
    [(x, y) for x in range(5) for y in range(5)
     if x in (0, 4) or y in (0, 4) or (x, y) in {(2, 1), (2, 3)}]
) - {START, GOAL}
"""The outer ring is wall, plus ``(2,1)`` and ``(2,3)`` — less start and goal.

``START = (0,2)`` and ``GOAL = (4,2)`` lie *on* the ring and are the two open
cells in it. Failing to subtract them walls off the goal and every route fails;
this was caught on the first run of the smoke suite, not by reading.

``(2,1)``/``(2,3)`` are what force the upper bypass to commit at ``(1,2)`` and
the lower loop at ``(1,3)`` — neither can rejoin the short corridor except at
``(3,2)``. An earlier map walled ``(1,1)``/``(1,3)`` instead, which made
``z_2``'s sidestep physically impossible (A4)."""

N_COLS = N_ROWS = 5
CONTEXT_PERIODS: Mapping[int, int] = {0: 6, 1: 3}
"""``kappa -> hazard period`` (11 §2)."""

PHASE_DOMAIN: tuple[int, ...] = (0, 1, 2, 3, 4, 5)

ACTIONS: tuple[str, ...] = ("UP", "DOWN", "LEFT", "RIGHT", "WAIT")
Action = int

_DELTAS: Mapping[int, tuple[int, int]] = {
    0: (0, -1),   # UP
    1: (0, +1),   # DOWN
    2: (-1, 0),   # LEFT
    3: (+1, 0),   # RIGHT
    4: (0, 0),    # WAIT
}


def hazard_at(t: int, kappa: int, phi: int) -> bool:
    """Is the hazard on the contested cell at ``t``?

    ``11-ENVIRONMENT.md`` §2. A deterministic function of ``(t, kappa, phi)`` —
    which is exactly why ``phi`` lives in :class:`State` (A23): with the phase
    hidden, two episodes could share current occupancy and differ in future
    schedule, and neither tabular Q nor finite-horizon DP would be well posed.
    """
    return t % CONTEXT_PERIODS[kappa] == phi % CONTEXT_PERIODS[kappa]


def legal_actions(state: "State") -> tuple[Action, ...]:
    """``A_legal(s)``: in-grid and not into a wall (11 §3, 02 §2.4.1).

    Illegal actions are never in an admissible set. The environment resolves
    them to ``WAIT`` and records the illegality, but that resolution rule is a
    safety net, not an invitation to offer illegal moves as candidates — offering
    them would give exact DP spurious ties and Q-entries for moves the agent
    cannot make (A20).
    """
    out = []
    for a in range(len(ACTIONS)):
        dx, dy = _DELTAS[a]
        cell = (state.x + dx, state.y + dy)
        if 0 <= cell[0] < N_COLS and 0 <= cell[1] < N_ROWS and cell not in WALLS:
            out.append(a)
    return tuple(out)


def _enter(action: Action, state: "State") -> tuple[int, int]:
    """The cell the agent would occupy. Illegal moves stay put (resolve to WAIT)."""
    dx, dy = _DELTAS[action]
    cell = (state.x + dx, state.y + dy)
    if 0 <= cell[0] < N_COLS and 0 <= cell[1] < N_ROWS and cell not in WALLS:
        return cell
    return (state.x, state.y)


# --------------------------------------------------------------------------- #
# State and control state
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class State:
    """``s = (x, y, t, kappa, phi)`` — 11-ENVIRONMENT.md §1, A23.

    Carries **no** learner state. ``Q``, attribution and reward-learning belong
    to the learner, not to the world.
    """

    x: int
    y: int
    t: int
    kappa: int
    phi: int

    @property
    def cell(self) -> tuple[int, int]:
        return (self.x, self.y)


@dataclass(frozen=True, slots=True)
class ControlState:
    """``(z, m)`` — the option and its automaton state. 02-SCM.md §2.3, A22.

    Held separately from :class:`State` because it is the learner's own control
    commitment, not an environment field. Along with ``obs`` it forms the
    learner's total information set ``I_t`` (``01`` §2.1.1).
    """

    z: int
    m: int


class Outcome:
    SUCCESS = "SUCCESS"
    COLLISION = "COLLISION"
    TRAP = "TRAP"
    TIMEOUT = "TIMEOUT"


# --------------------------------------------------------------------------- #
# Options and automata — 02-SCM.md §2.4, transcription of the frozen tables
# --------------------------------------------------------------------------- #

_Z1, _Z2, _Z3, _Z4 = 0, 1, 2, 3
_OPTION_NAMES = ("rush", "detour_upper", "wait_then_cross", "loop_lower")
_WAYPOINT_Z2 = (2, 1)
_WAYPOINT_Z4 = (2, 4)


def option_ids() -> tuple[int, ...]:
    return (_Z1, _Z2, _Z3, _Z4)


def option_name(z: int) -> str:
    return _OPTION_NAMES[z]


def initial_control(z: int) -> ControlState:
    """``m_0(z) = 0`` for every option (02 §2.4.1)."""
    return ControlState(z=z, m=0)


def option_actions(z: int, ctrl: ControlState, state: State) -> tuple[Action, ...]:
    """``A_z(m, s)`` — the frozen tables of 02-SCM.md §2.4.2–§2.4.5.

    Every admissible set is a subset of ``A_legal(s)`` (A20). There is no
    "clever recovery logic" here: the tables are transcribed, nothing more.
    """
    legal = legal_actions(state)
    m = ctrl.m

    if z == _Z1:
        return legal

    if z == _Z2:
        if m == 0:
            return tuple(a for a in legal if _enter(a, state) != GOAL)
        return legal

    if z == _Z3:
        if m == 0:
            # Not yet cleared: may not enter the contested cell, may not finish.
            return tuple(
                a for a in legal
                if _enter(a, state) not in (CONTESTED, GOAL)
            )
        return legal

    if z == _Z4:
        if m == 0:
            return tuple(a for a in legal if _enter(a, state) != GOAL)
        return legal

    raise ValueError(f"unknown option {z!r}")


def automaton_transition(
    z: int, ctrl: ControlState, state: State, action: Action, nxt: State
) -> ControlState:
    """``delta_z`` — the frozen transitions of 02-SCM.md §2.4.

    Monotone by construction: ``m`` never decreases, and every obligation is
    recoverable (02 §2.4.6). A non-recoverable obligation would make a decision
    fault indistinguishable from a process fault.
    """
    if ctrl.z != z:
        raise ValueError("control state belongs to a different option")

    if z in (_Z2, _Z4) and ctrl.m == 0:
        target = _WAYPOINT_Z2 if z == _Z2 else _WAYPOINT_Z4
        if nxt.cell == target:
            return ControlState(z=z, m=1)

    if z == _Z3 and ctrl.m == 0:
        # Discharged by holding where the hazard can be observed to have left.
        if state.cell == (1, 2) and not hazard_at(state.t, state.kappa, state.phi):
            return ControlState(z=z, m=1)

    return ctrl


# --------------------------------------------------------------------------- #
# The semantic tape — 11-ENVIRONMENT.md §8.1.1
# --------------------------------------------------------------------------- #

TapeKey = tuple[str, str]
"""``(kind, which)``. Addressed by semantic key, **never** by draw order.

There is deliberately no ``next_draw()`` / ``random()`` on this object. Positional
consumption is what makes an intervention that changes trajectory length silently
shift every subsequent random value, so that two rollouts compare different noise
realisations while claiming to hold noise fixed (A3, §8).
"""

_K_HAZARD: TapeKey = ("hazard", "phase")
_K_ERROR: TapeKey = ("feedback", "error_flag")
_K_RANK: TapeKey = ("feedback", "cause_rank")

P_ERROR: float = 0.4
"""``P(error_flag = 1)``. Not implied by the two-point support — a support is not
a measure (A25)."""


@dataclass(frozen=True)
class SemanticTape:
    """The three frozen keys, their supports, their measure, and the decoder.

    The measure factorises: ``P(phi, e, r) = P(phi) P(e) P(r)`` (A30).
    Independence is not a convenience — if ``error_flag`` correlated with
    ``phi``, feedback reliability would vary with the hazard schedule and the
    channel would leak information about ``phi`` beyond what ``obs`` carries.
    """

    phase: int
    error_flag: int
    cause_rank: int

    @staticmethod
    def sample(seed: int) -> "SemanticTape":
        import random

        rng = random.Random(seed)
        phase = rng.choice(PHASE_DOMAIN)
        error_flag = 1 if rng.random() < P_ERROR else 0
        cause_rank = rng.randrange(60)
        return SemanticTape(phase=phase, error_flag=error_flag, cause_rank=cause_rank)

    def get(self, key: TapeKey) -> int:
        if key == _K_HAZARD:
            return self.phase
        if key == _K_ERROR:
            return self.error_flag
        if key == _K_RANK:
            return self.cause_rank
        raise KeyError(f"unknown tape key {key!r} — the key set is frozen (A18)")

    def keys(self) -> tuple[TapeKey, ...]:
        return (_K_HAZARD, _K_ERROR, _K_RANK)

    def fingerprint(self) -> tuple:
        """Identity of the exogenous assignment, for the ``same assignment``
        invariant of 11 §8.2 — not for equality of access logs."""
        return (self.phase, self.error_flag, self.cause_rank)

    def decode_feedback(self, fault_presence: Sequence[int]) -> tuple[int, ...]:
        """The frozen decoder of 11 §8.1.1.

        ``E`` is the active set when ``error_flag = 0`` and the inactive set
        otherwise. The claim is one-hot at ``E[cause_rank mod |E|]``.

        ``cause_rank`` ranges over 60 values, not 5: 60 is divisible by
        1, 2, 3, 4 and 5, so the draw is **exactly uniform on any non-empty
        eligible set**. A five-valued key is uniform only for ``|E| in {1, 5}``
        and silently skews the common cases (A25).

        The empty eligible set is reachable — ``Z = (1,1,1,1,1)`` with
        ``error_flag = 1``, ``Z = (0,0,0,0,0)`` with ``error_flag = 0`` — and
        yields the empty claim rather than being resampled. Resampling would
        condition the feedback distribution on ``Z``, which is the
        outcome-conditioning A2 removed.
        """
        want = 1 - self.error_flag
        eligible = [i for i, zi in enumerate(fault_presence) if zi == want]
        if not eligible:
            return ()
        return (eligible[self.cause_rank % len(eligible)],)


# --------------------------------------------------------------------------- #
# Fault mask — 11-ENVIRONMENT.md §6
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class DecisionOverride:
    """A ``Z_D`` injection: ``d_{t} <- action`` at one timestep.

    Admissibility ``a' in A_z(m_t, s_t)`` is checked when the override is
    applied, against the **counterfactual** state (02 §5.0.1).

    The companion condition ``a' != pi_D*(s_t, z, m_t)`` is **not** checkable
    here: it needs the exact DP. It is deliberately left to that stage rather
    than filled in with a hard-coded "correct action" — inventing one would be
    the kernel doing research design.
    """

    t: int
    action: Action


@dataclass(frozen=True, slots=True)
class ControllerFault:
    """A ``Z_X`` injection: perturbs one controller cell (11 §5.1)."""

    state_key: tuple[int, int, int, int]   # (x, y, o, t) as _q_key sees it
    cmd: Action
    realized: Action


@dataclass(frozen=True, slots=True)
class PlantFault:
    """A ``Z_E`` injection: the plant overrides one command at one step."""

    t: int
    realized: Action


@dataclass(frozen=True, slots=True)
class Trap:
    """A ``Z_U`` injection (11 §6.6, A31).

    Entering ``cell`` at step ``t`` is an **immediate terminal failure**. Terminal
    and immediate, so no later action can undo it — which is what "unmodelled"
    means for repair. Cell- and time-specific, so it is not a rule the agent could
    learn. Evaluation-only, so the learner must express it as ``p_U > 0``.
    """

    cell: tuple[int, int]
    t: int


@dataclass(frozen=True, slots=True)
class FaultMask:
    """Everything ``M`` carries: the fault *parameters*, drawn exogenously.

    These live here rather than on the tape, and that is what keeps
    ``|T| = 6 x 2 x 60 = 720`` enumerable: crossing every fault's activation,
    location and parameter into the tape would have exploded it while the same
    information was already being enumerated in ``M`` (A18).
    """

    decision: DecisionOverride | None = None
    controller: ControllerFault | None = None
    plant: PlantFault | None = None
    trap: Trap | None = None
    option_override: int | None = None
    """``Z_P``: the option the episode is run under (11 §6.4, A28)."""


# --------------------------------------------------------------------------- #
# Interventions — 02-SCM.md §5, §5.0.1
# --------------------------------------------------------------------------- #

class MalformedIntervention(Exception):
    """Raised when a repair candidate is ``MALFORMED`` (02 §5.0.1).

    Not clamped, not skipped, not partially applied: the **entire** candidate is
    invalid. A partially-applied repair is a different candidate than the one the
    evaluator scored.
    """


@dataclass(frozen=True, slots=True)
class Intervention:
    """One element of the intervention lattice ``I`` (02 §5).

    ``kind`` is one of ``"process"``, ``"decision"``, ``"execution"``.
    """

    kind: str
    t: int | None = None
    action: Action | None = None
    option: int | None = None
    cell: tuple[int, int, int, int] | None = None

    def node(self) -> tuple:
        """Identity of the structural node this touches, for conflict detection."""
        if self.kind == "process":
            return ("process",)
        if self.kind == "decision":
            return ("decision", self.t)
        if self.kind == "execution":
            return ("execution", self.cell)
        raise ValueError(f"unknown intervention kind {self.kind!r}")


@dataclass(frozen=True, slots=True)
class InterventionSet:
    """A candidate repair ``r``, fixed **once** before the rollout (02 §5.0.1)."""

    members: tuple[Intervention, ...] = ()

    def __post_init__(self) -> None:
        nodes = [iv.node() for iv in self.members]
        if len(nodes) != len(set(nodes)):
            raise MalformedIntervention(
                "two interventions target the same structural node; "
                "their composition is undefined (02 §5.0.1)"
            )

    def process(self) -> Intervention | None:
        for iv in self.members:
            if iv.kind == "process":
                return iv
        return None

    def decision_at(self, t: int) -> Intervention | None:
        for iv in self.members:
            if iv.kind == "decision" and iv.t == t:
                return iv
        return None

    def execution(self) -> Intervention | None:
        for iv in self.members:
            if iv.kind == "execution":
                return iv
        return None

    def __len__(self) -> int:
        return len(self.members)


# --------------------------------------------------------------------------- #
# One step — 11-ENVIRONMENT.md §1.1, the frozen event order
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class StepResult:
    state: State
    control: ControlState
    a_cmd: Action
    u: Action
    a_realized: Action
    reward: float
    terminal: bool
    outcome: str | None
    illegal: bool = False
    clipped: bool = False


def _trap_cell(mask: FaultMask) -> tuple[int, int] | None:
    return mask.trap.cell if mask.trap is not None else None


def _trap_time(mask: FaultMask) -> int | None:
    return mask.trap.t if mask.trap is not None else None


def step(
    state: State,
    control: ControlState,
    a_cmd: Action,
    *,
    tape: SemanticTape,
    mask: FaultMask = FaultMask(),
    controller: Mapping[tuple[int, int, int, int], Action] | None = None,
    reward_mode: str = "A",
) -> StepResult:
    """Advance the world by one step, in the frozen order of 11 §1.1.

    ::

        (s_t, z, m) -> a^cmd -> u -> a^realized -> (x', y') -> t+1
                    -> hazard check -> terminal/reward -> m'

    The caller supplies ``a_cmd``. **This function never chooses an action** —
    the policy is the learner's, and the DP's, never the world's.

    Three consequences of that order, which are read off it rather than guessed
    (A29):

    1. the hazard is checked against the **newly occupied** cell, after the move;
    2. ``z_3``'s ``clear(s)`` tests the hazard at the *current* step, so "wait
       until clear, then cross" is well defined;
    3. the automaton updates **last**, on ``s_{t+1}``, so an obligation discharged
       by the move just made is available to the next decision.
    """
    if state.t >= HORIZON:
        raise ValueError("step called past the horizon")

    legal = legal_actions(state)
    illegal = a_cmd not in legal
    a_eff = a_cmd if not illegal else 4  # resolve to WAIT (11 §3)

    # --- controller: C_X(s, a^cmd) -> u   (11 §5.1) ------------------------ #
    ctrl_key = (state.x, state.y, state.t, state.t)
    u = a_eff
    if controller is not None and ctrl_key in controller:
        u = controller[ctrl_key]
    if mask.controller is not None and mask.controller.state_key == ctrl_key \
            and mask.controller.cmd == a_eff:
        u = mask.controller.realized

    # --- plant: P(s, u, eps_E) -> a^realized   (11 §5.2) ------------------- #
    a_realized = u
    if mask.plant is not None and mask.plant.t == state.t:
        a_realized = mask.plant.realized

    # --- move, then advance t; the hazard is checked against the NEW cell -- #
    nx, ny = _enter(a_realized, state)
    nxt_t = state.t + 1

    terminal = False
    outcome: str | None = None

    if (nx, ny) == CONTESTED and hazard_at(nxt_t, state.kappa, state.phi):
        terminal, outcome = True, Outcome.COLLISION
    elif (nx, ny) == _trap_cell(mask) and nxt_t == _trap_time(mask):
        terminal, outcome = True, Outcome.TRAP
    elif (nx, ny) == GOAL:
        terminal, outcome = True, Outcome.SUCCESS
    elif nxt_t >= HORIZON:
        terminal, outcome = True, Outcome.TIMEOUT

    nxt_state = State(x=nx, y=ny, t=nxt_t, kappa=state.kappa, phi=state.phi)

    reward = STEP_COST
    if terminal:
        success = outcome == Outcome.SUCCESS
        if success:
            reward += REWARD_SUCCESS
        else:
            reward += REWARD_FAILURE_A if reward_mode == "A" else REWARD_FAILURE_B

    # --- automaton updates LAST (A29) -------------------------------------- #
    nxt_control = (
        control if terminal
        else automaton_transition(control.z, control, state, a_eff, nxt_state)
    )

    return StepResult(
        state=nxt_state, control=nxt_control, a_cmd=a_cmd, u=u,
        a_realized=a_realized, reward=reward, terminal=terminal,
        outcome=outcome, illegal=illegal,
    )


# --------------------------------------------------------------------------- #
# Rollout — 02-SCM.md §5.0.1
# --------------------------------------------------------------------------- #

CommandProvider = Callable[[State, ControlState], int]
"""Supplies ``a^cmd``. The kernel refuses to supply one itself."""


def rollout(
    *,
    kappa: int,
    tape: SemanticTape,
    command_provider: CommandProvider,
    mask: FaultMask = FaultMask(),
    interventions: InterventionSet = InterventionSet(),
    controller: Mapping[tuple[int, int, int, int], Action] | None = None,
    reward_mode: str = "A",
) -> "RolloutTrace":
    """Run one episode under a fixed intervention set.

    ``command_provider`` is the *only* source of ``a^cmd``. There is deliberately
    no default: a convenience reference policy inside the kernel would be the
    kernel computing ``argmax Q_D*``, which is the DP's job and is not
    authorised here.

    **Interventions are fixed before the rollout** and validated online against
    the **counterfactual** trajectory (A24). Checking a second member against the
    *factual* prefix would let it repair a decision that does not exist in the
    counterfactual run. Any failure raises :class:`MalformedIntervention` — the
    whole candidate is invalid.
    """
    proc = interventions.process()
    z0 = proc.option if proc is not None else (
        mask.option_override if mask.option_override is not None else 0
    )
    control = initial_control(z0)          # m <- m_0(z') = 0 (A28)

    state = State(x=START[0], y=START[1], t=0, kappa=kappa, phi=tape.phase)

    executed_controller = dict(controller) if controller else {}

    ex = interventions.execution()
    if ex is not None and ex.cell is not None:
        executed_controller[ex.cell] = ex.cell[1]  # C_X(s,a) <- a

    steps: list[StepResult] = []
    while state.t < HORIZON:
        dec = interventions.decision_at(state.t)
        if dec is not None:
            allowed = option_actions(control.z, control, state)
            if dec.action not in allowed:
                raise MalformedIntervention(
                    f"decision override at t={state.t} uses action "
                    f"{ACTIONS[dec.action]} outside A_z(m,s) for option "
                    f"{option_name(control.z)} — a local intervention may not "
                    f"escape the option obligation (02 §2.4.7)"
                )
            a_cmd = dec.action
        else:
            a_cmd = command_provider(state, control)

        res = step(
            state, control, a_cmd, tape=tape, mask=mask,
            controller=executed_controller, reward_mode=reward_mode,
        )
        steps.append(res)
        state, control = res.state, res.control
        if res.terminal:
            break

    return RolloutTrace(
        steps=tuple(steps), outcome=steps[-1].outcome if steps else Outcome.TIMEOUT,
        control=control, mask=mask, interventions=interventions,
    )


@dataclass(frozen=True)
class RolloutTrace:
    steps: tuple[StepResult, ...]
    outcome: str | None
    control: ControlState
    mask: FaultMask
    interventions: InterventionSet

    @property
    def success(self) -> bool:
        return self.outcome == Outcome.SUCCESS

    @property
    def return_value(self) -> float:
        return 1.0 if self.success else -1.0

    def commands(self) -> tuple[Action, ...]:
        return tuple(s.a_cmd for s in self.steps)

    def realized(self) -> tuple[Action, ...]:
        return tuple(s.a_realized for s in self.steps)

    def decisions(self) -> tuple[int, ...]:
        """The timesteps at which the realized action differed from the command.

        This identifies **execution deviation** and nothing more: observing it
        says nothing about whether the command was a good decision
        (``01`` §2.3)."""
        return tuple(s.state.t - 1 for s in self.steps if s.a_realized != s.a_cmd)


# --------------------------------------------------------------------------- #
# But-for relevance — 11-ENVIRONMENT.md §6.1
# --------------------------------------------------------------------------- #

def but_for_relevance(
    *,
    kappa: int,
    tape: SemanticTape,
    command_provider: CommandProvider,
    mask: FaultMask,
) -> dict[str, int]:
    """``B``: which active mechanisms were difference-makers on this tape.

    Computed by removing one fault at a time and comparing outcomes, **holding
    ``omega`` fixed**. Resampling the tape would be a different operation and is
    not a but-for test (A26).

    Kept in the kernel because it is evaluator truth about the world, not
    learner machinery.
    """
    reference = rollout(
        kappa=kappa, tape=tape, command_provider=command_provider, mask=mask
    )
    parts = {
        "Z_P": dataclasses.replace(mask, option_override=None),
        "Z_D": dataclasses.replace(mask, decision=None),
        "Z_X": dataclasses.replace(mask, controller=None),
        "Z_E": dataclasses.replace(mask, plant=None),
        "Z_U": dataclasses.replace(mask, trap=None),
    }
    out: dict[str, int] = {}
    for name, reduced in parts.items():
        try:
            alt = rollout(
                kappa=kappa, tape=tape, command_provider=command_provider,
                mask=reduced,
            )
            out[name] = int(alt.outcome != reference.outcome)
        except MalformedIntervention:
            out[name] = 0
    return out
