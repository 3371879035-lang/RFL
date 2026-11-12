"""RFL-Rebuild — the minimal SCM kernel.

This is the **world model and nothing else**. It is the single source of truth
for what happens, and it deliberately contains no learner:

* it does **not** compute ``argmax_a Q_D*(s, z, m, a)`` and does not own
  :math:`\\pi_D^{*}` — that is the exact DP, authorised separately;
* it does **not** train, run RFL, or perform attribution;
* :func:`step` receives an already-decided ``a_cmd``; it never chooses one;
* :func:`rollout` takes an external command provider and refuses to invent a
  reference policy for convenience.

Correction pass A32–A38 is applied throughout; the amendment log
(``docs/rebuild/12-AMENDMENTS.md``) records what each fix was and why.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

__all__ = [
    "State", "ControlState", "StepResult", "Outcome", "RolloutTrace",
    "FaultMask", "DecisionOverride", "ControllerFault", "PlantFault", "Trap",
    "SemanticTape", "TapeKey", "ControllerSite",
    "Intervention", "InterventionSet", "MalformedIntervention", "OptionViolation",
    # A75 §62.11 — the learner baseline interface, part of the public surface.
    "LearnerContractViolation", "ProcessCommitProvider", "CommandProvider",
    "ACTIONS", "Action", "START", "GOAL", "CONTESTED", "WALLS", "OPEN_CELLS",
    "HORIZON", "STEP_COST",
    "step", "rollout", "continue_rollout", "option_actions", "automaton_transition",
    "legal_actions", "hazard_at", "option_ids", "option_name",
    "initial_control", "but_for_relevance",
]

# --------------------------------------------------------------------------- #
# Environment constants — 11-ENVIRONMENT.md §1, §2, §3
# --------------------------------------------------------------------------- #

HORIZON: int = 12
STEP_COST: float = -0.02
REWARD_SUCCESS: float = +1.0
REWARD_FAILURE_A: float = -1.0
REWARD_FAILURE_B: float = 0.0

START: tuple[int, int] = (0, 2)
GOAL: tuple[int, int] = (4, 2)
CONTESTED: tuple[int, int] = (2, 2)

N_COLS = N_ROWS = 5

WALLS: frozenset[tuple[int, int]] = frozenset(
    [(x, y) for x in range(N_COLS) for y in range(N_ROWS)
     if x in (0, 4) or y == 0]
) | {(2, 3)}
WALLS = WALLS - {START, GOAL}
"""The unique wall set, read cell by cell off the map in ``11-ENVIRONMENT.md`` §1.

::

      x=0   x=1   x=2   x=3   x=4
y=0    #     #     #     #     #
y=1    #     .     .     .     #
y=2    S     .     .     .     G
y=3    #     .     #     .     #
y=4    #     .     .     .     #

The outer ring is wall **except** ``START=(0,2)`` and ``GOAL=(4,2)``, which lie on
it and are open. ``(2,3)`` is the only interior wall. ``(2,1)`` is **open** — it is
:math:`z_2`'s waypoint, and walling it would make ``m=1`` unreachable for ``z_2``.
An earlier revision both walled ``(2,1)`` and said so in prose; the prose and the
code were consistently wrong together, and only running a ``z_2`` route exposed it
(A32).
"""

OPEN_CELLS: frozenset[tuple[int, int]] = frozenset(
    (x, y) for x in range(N_COLS) for y in range(N_ROWS)
) - WALLS

CONTEXT_PERIODS: Mapping[int, int] = {0: 6, 1: 3}
PHASE_DOMAIN: tuple[int, ...] = (0, 1, 2, 3, 4, 5)

ACTIONS: tuple[str, ...] = ("UP", "DOWN", "LEFT", "RIGHT", "WAIT")
Action = int


def _is_int_id(v: object) -> bool:
    """Is ``v`` a **true** integer id, not merely something that compares equal to one?

    ``True == 1`` and ``1.0 == 1`` are both true in Python, so a plain
    ``v in option_ids()`` or ``v in ACTIONS`` membership test would let a bool or a
    float through. A75 §62.11's contract is about *action and option ids*, so the
    domain check requires the type as well as the value.
    """
    return isinstance(v, int) and not isinstance(v, bool)


def _action_name(a: object) -> str:
    """Render an action for an error message **without** indexing out of range.

    The first version of the contract check wrote ``ACTIONS[u]`` inline, so an
    out-of-range baseline output raised ``IndexError`` while the intended
    ``LearnerContractViolation`` was still being constructed -- an illegal learner
    input produced a crash instead of the contract violation it is supposed to.
    """
    return ACTIONS[a] if _is_int_id(a) and 0 <= a < len(ACTIONS) else repr(a)

UP, DOWN, LEFT, RIGHT, WAIT = 0, 1, 2, 3, 4
_DELTAS: Mapping[int, tuple[int, int]] = {
    UP: (0, -1), DOWN: (0, +1), LEFT: (-1, 0), RIGHT: (+1, 0), WAIT: (0, 0),
}


def hazard_at(t: int, kappa: int, phi: int) -> bool:
    """Is the hazard on the contested cell at ``t``? (11 §2)"""
    return t % CONTEXT_PERIODS[kappa] == phi % CONTEXT_PERIODS[kappa]


# --------------------------------------------------------------------------- #
# State and control state
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class State:
    """``s = (x, y, t, kappa, phi)`` — 11 §1, A23. Carries **no** learner state."""

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
    """``(z, m)`` — the option and its automaton state. 02 §2.3, A22.

    The learner's own control commitment, held apart from :class:`State`.
    Together with ``obs`` it forms the learner information set ``I_t``
    (``01`` §2.1.1).
    """

    z: int
    m: int


@dataclass(frozen=True, slots=True)
class ControllerSite:
    """``(s, a^cmd)`` — the argument of the controller ``C_X``. 11 §5.1, A35.

    Not a tuple of ints: the earlier code keyed the controller on
    ``(x, y, t, t)``, which repeats ``t``, omits ``kappa`` and ``phi``, and — most
    importantly — omits ``a^cmd``, so two different commands from one state were
    the same site. ``C_X`` is a function **of the command**.
    """

    state: State
    cmd: Action


class Outcome:
    SUCCESS = "SUCCESS"
    COLLISION = "COLLISION"
    TRAP = "TRAP"
    TIMEOUT = "TIMEOUT"


# --------------------------------------------------------------------------- #
# Options and automata — 02-SCM.md §2.4
# --------------------------------------------------------------------------- #

_Z1, _Z2, _Z3, _Z4 = 0, 1, 2, 3
_OPTION_NAMES = ("rush", "detour_upper", "wait_then_cross", "loop_lower")
WAYPOINT_Z2 = (2, 1)
WAYPOINT_Z4 = (2, 4)
HOLD_CELL_Z3 = (1, 2)


def option_ids() -> tuple[int, ...]:
    return (_Z1, _Z2, _Z3, _Z4)


def option_name(z: int) -> str:
    return _OPTION_NAMES[z]


def initial_control(z: int) -> ControlState:
    """``m_0(z) = 0`` (02 §2.4.1)."""
    if z not in option_ids():
        raise ValueError(f"unknown option {z!r}")
    return ControlState(z=z, m=0)


def legal_actions(state: State) -> tuple[Action, ...]:
    """``A_legal(s)``: in-grid and not into a wall (11 §3, 02 §2.4.1)."""
    out = []
    for a in range(len(ACTIONS)):
        dx, dy = _DELTAS[a]
        cell = (state.x + dx, state.y + dy)
        if cell in OPEN_CELLS:
            out.append(a)
    return tuple(out)


def _enter(action: Action, state: State) -> tuple[int, int]:
    dx, dy = _DELTAS[action]
    cell = (state.x + dx, state.y + dy)
    return cell if cell in OPEN_CELLS else (state.x, state.y)


def _bfs_distance_to_goal() -> Mapping[tuple[int, int], int]:
    """``d_G(c)``: static shortest-path distance to ``GOAL`` over open cells.

    Ignores the hazard, ``kappa``, ``phi`` and ``t`` entirely, and never consults
    the DP value. That is the whole point (A39): if this read anything about the
    current situation it would be encoding "where is it safe right now" into the
    option, which is writing the answer into the option rather than defining the
    option's behaviour style.
    """
    from collections import deque

    dist: dict[tuple[int, int], int] = {GOAL: 0}
    queue = deque([GOAL])
    while queue:
        cx, cy = queue.popleft()
        for dx, dy in _DELTAS.values():
            nb = (cx + dx, cy + dy)
            if nb in OPEN_CELLS and nb not in dist:
                dist[nb] = dist[(cx, cy)] + 1
                queue.append(nb)
    return dist


STATIC_DISTANCE_TO_GOAL: Mapping[tuple[int, int], int] = _bfs_distance_to_goal()
"""``d_G``, frozen. Computed once at import from the static open-cell graph."""


def option_actions(z: int, ctrl: ControlState, state: State) -> tuple[Action, ...]:
    """``A_z(m, s)`` — 02 §2.4.2–§2.4.5, transcribed. No recovery logic added."""
    if ctrl.z != z:
        raise ValueError("control state belongs to a different option")
    legal = legal_actions(state)
    m = ctrl.m

    if z == _Z1:
        # A39: `rush` must strictly decrease the STATIC distance to the goal at
        # every step. This makes it a genuine rush rather than the unconstrained
        # optimum, and thereby removes the degeneracy in which `rush` absorbed
        # the abilities of every specialised option.
        here = STATIC_DISTANCE_TO_GOAL.get(state.cell)
        if here is None:
            raise ValueError(f"{state.cell} is not an open cell")
        if here == 0:
            raise ValueError("the goal is terminal and is never a decision point")
        return tuple(
            a for a in legal
            if STATIC_DISTANCE_TO_GOAL.get(_enter(a, state), here) == here - 1
        )

    if z in (_Z2, _Z4):
        if m == 0:
            return tuple(a for a in legal if _enter(a, state) != GOAL)
        return legal

    if z == _Z3:
        if m == 0:
            return tuple(
                a for a in legal if _enter(a, state) not in (CONTESTED, GOAL)
            )
        return legal

    raise ValueError(f"unknown option {z!r}")


def automaton_transition(
    z: int, ctrl: ControlState, state: State, action: Action, nxt: State
) -> ControlState:
    """``delta_z`` — 02 §2.4. Monotone; every obligation is recoverable."""
    if ctrl.z != z:
        raise ValueError("control state belongs to a different option")
    if ctrl.m != 0:
        return ctrl
    if z == _Z2 and nxt.cell == WAYPOINT_Z2:
        return ControlState(z=z, m=1)
    if z == _Z4 and nxt.cell == WAYPOINT_Z4:
        return ControlState(z=z, m=1)
    if z == _Z3 and state.cell == HOLD_CELL_Z3 and not hazard_at(
        state.t, state.kappa, state.phi
    ):
        return ControlState(z=z, m=1)
    return ctrl


# --------------------------------------------------------------------------- #
# The semantic tape — 11 §8.1.1
# --------------------------------------------------------------------------- #

TapeKey = tuple[str, str]
"""``(kind, which)``. Addressed by semantic key, never by draw order (A3).

There is deliberately no ``next_draw()`` / ``random()`` here.
"""

_K_HAZARD: TapeKey = ("hazard", "phase")
_K_ERROR: TapeKey = ("feedback", "error_flag")
_K_RANK: TapeKey = ("feedback", "cause_rank")

P_ERROR: float = 0.4
N_CAUSES = 5
CAUSE_NAMES = ("P", "D", "X", "E", "U")


@dataclass(frozen=True, slots=True)
class SemanticTape:
    """The three frozen keys, their supports, their measure, and the decoder.

    ``P(phi, e, r) = P(phi) P(e) P(r)`` (A30) — independence is not a
    convenience: a correlation between ``error_flag`` and ``phi`` would make
    feedback reliability vary with the hazard schedule and leak ``phi`` beyond
    what ``obs`` carries.
    """

    phase: int
    error_flag: int
    cause_rank: int

    @staticmethod
    def sample(seed: int) -> "SemanticTape":
        import random

        rng = random.Random(seed)
        return SemanticTape(
            phase=rng.choice(PHASE_DOMAIN),
            error_flag=1 if rng.random() < P_ERROR else 0,
            cause_rank=rng.randrange(60),
        )

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
        """Identity of the exogenous assignment (11 §8.2)."""
        return (self.phase, self.error_flag, self.cause_rank)

    def decode_feedback(self, fault_presence: Sequence[int]) -> tuple[int, ...]:
        """The frozen decoder of 11 §8.1.1, returning ``Z-hat^fb in {0,1}^5``.

        **The argument is ``Z^fire``, not ``Z^pres`` (A54).** The channel reports
        what *happened*, so its eligible set is ``{i : Z_i^fire = 1}``. Passing
        presence would let a truthful feedback claim refer to a dormant fault
        that never executed on the trajectory — a claim about the generator's
        private configuration dressed up as a report about the episode.

        **One-hot vector, not a sparse index set.** The spec freezes the type as
        a five-vector; an earlier revision returned ``(idx,)``, and a schema
        mismatch between the spec and the code is exactly what bites at Gate
        signature time (A38).

        ``cause_rank`` spans 60 values because 60 is divisible by 1, 2, 3, 4 and
        5, so the draw is exactly uniform on any non-empty eligible set. A
        five-valued key is uniform only for ``|E| in {1,5}`` (A25).

        The empty eligible set is reachable and yields all zeros rather than
        being resampled: resampling would condition the feedback distribution on
        ``Z``, the outcome-conditioning A2 removed.
        """
        want = 1 - self.error_flag
        eligible = [i for i, zi in enumerate(fault_presence) if zi == want]
        if not eligible:
            return (0,) * N_CAUSES
        out = [0] * N_CAUSES
        out[eligible[self.cause_rank % len(eligible)]] = 1
        return tuple(out)


# --------------------------------------------------------------------------- #
# Fault mask — 11 §6
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class DecisionOverride:
    """A ``Z_D`` injection: the command at one action-step is replaced.

    Admissibility ``a' in A_z(m_t, s_t)`` is checked when applied, against the
    **counterfactual** state. The companion ``a' != pi_D*(s_t, z, m_t)`` needs the
    exact DP and is deliberately left to that stage — hard-coding a "correct
    action" here would be the kernel doing research design.
    """

    t: int
    action: Action


@dataclass(frozen=True, slots=True)
class ControllerFault:
    """A ``Z_X`` injection: ``C_X(s^*, a^cmd)`` is mis-executed (11 §5.1)."""

    state: State
    cmd: Action
    realized: Action


@dataclass(frozen=True, slots=True)
class PlantFault:
    """A ``Z_E`` injection: the plant overrides one step (11 §5.2)."""

    t: int
    realized: Action


@dataclass(frozen=True, slots=True)
class Trap:
    """A ``Z_U`` injection (11 §6.6, A31, A37).

    Entering ``cell`` **on the move made at action-step** ``t`` is an immediate
    terminal failure, with ``t in {0, ..., H-1}``. The domain is the *action step*
    that lands the agent there, not the post-move clock — the earlier code
    compared against ``t+1``, which made ``t = 0`` unreachable and shifted every
    trap by one step.
    """

    cell: tuple[int, int]
    t: int

    def __post_init__(self) -> None:
        if self.cell not in OPEN_CELLS:
            raise ValueError(f"trap cell {self.cell} is not an open cell")
        if self.cell in (START, GOAL):
            raise ValueError("trap cell may not be START or GOAL (11 §6.6)")
        if not (0 <= self.t < HORIZON):
            raise ValueError(f"trap t must be in [0, {HORIZON})")


@dataclass(frozen=True, slots=True)
class FaultMask:
    """Everything ``M`` carries: the fault *parameters*, drawn exogenously.

    Kept here rather than on the tape so that ``|T| = 6 x 2 x 60 = 720`` stays
    enumerable (A18).
    """

    decision: DecisionOverride | None = None
    controller: ControllerFault | None = None
    plant: PlantFault | None = None
    trap: Trap | None = None

    def fault_presence(self) -> tuple[int, ...]:
        """``Z``: which mechanisms are active. ``Z_P`` is supplied separately."""
        return (0, 0, 0, 0, 0)


# --------------------------------------------------------------------------- #
# Interventions — 02 §5, §5.0.1
# --------------------------------------------------------------------------- #

class MalformedIntervention(Exception):
    """A repair candidate is ``MALFORMED`` (02 §5.0.1).

    Not clamped, not skipped, not partially applied: the **entire** candidate is
    invalid, because a partially-applied repair is a different candidate than the
    one the evaluator scored.
    """


class OptionViolation(Exception):
    """A command was issued outside ``A_z(m, s)``.

    Raised for the ordinary policy as well as for ``do`` and faults (A36). An
    option constraint that binds only counterfactuals is not a behavioural
    constraint, and the process/local distinction collapses.
    """


class LearnerContractViolation(Exception):
    """A learner-owned baseline left the domain its channel is contracted to.

    A75 §62.11 / §62.3. **Deliberately not an** :class:`OptionViolation` **subclass**,
    and it must not be added to any ``except (MalformedIntervention,
    OptionViolation)``. Those are caught by the old gates to mean "this candidate is
    an ordinary rejected case"; a learner-baseline contract breach is a new
    **fail-fast protocol violation** and must not be swallowed as routine.

    The contract binds only a baseline that actually **takes control**:

    * ``C_P^L`` — when neither ``do(z=z')``, ``do(C_P=identity)`` nor ``Z_P`` governs,
      it must return an option id in ``option_ids()``;
    * ``C_X^L`` — when neither ``do(C_X)`` nor ``Z_X`` governs, it must return ``u``
      in ``A_z(m, s)``.

    Transient faults keep the **fault privilege** of leaving ``A_z``; that freedom is
    what makes them faults. The check therefore lives *inside* the baseline branch and
    is never applied to the final ``u`` or ``a_realized``.
    """


@dataclass(frozen=True, slots=True)
class Intervention:
    """One element of the intervention lattice ``I`` (02 §5).

    Required fields are validated **per kind** at construction (A37): a
    ``process`` with ``option=None``, a ``decision`` with ``t=None`` or an
    ``execution`` with ``cell=None`` used to be constructible and behaved as
    silent no-ops, which is dangerous for ``R*`` enumeration.
    """

    kind: str
    t: int | None = None
    action: Action | None = None
    option: int | None = None
    site: ControllerSite | None = None

    def __post_init__(self) -> None:
        if self.kind == "process":
            if self.option not in option_ids():
                raise MalformedIntervention("process needs a valid option id")
        elif self.kind == "process_commit":
            # A57: the A55 process repair do(C_P = identity). It takes no
            # parameters -- restoring a faithful commit is a single operation
            # with no argument -- so there is nothing to validate beyond the
            # absence of stray fields.
            if any(x is not None for x in (self.t, self.action, self.option, self.site)):
                raise MalformedIntervention(
                    "process_commit takes no parameters"
                )
        elif self.kind == "decision":
            if self.t is None or self.action is None:
                raise MalformedIntervention("decision needs t and action")
            if not (0 <= self.t < HORIZON):
                raise MalformedIntervention(f"decision t out of range: {self.t}")
            if not (0 <= self.action < len(ACTIONS)):
                raise MalformedIntervention(f"unknown action {self.action}")
        elif self.kind == "execution":
            if self.site is None:
                raise MalformedIntervention("execution needs a ControllerSite")
        else:
            raise MalformedIntervention(f"unknown intervention kind {self.kind!r}")

    def node(self) -> tuple:
        if self.kind == "process":
            return ("process",)
        if self.kind == "process_commit":
            # A57: its OWN structural node, distinct from ("process",), so that
            # {do(z=z'), do(C_P=identity)} composes instead of colliding and so
            # that repair cardinality counts the commit repair like any other
            # member.
            return ("process_commit",)
        if self.kind == "decision":
            return ("decision", self.t)
        return ("execution", self.site)

    @staticmethod
    def process(option: int) -> "Intervention":
        return Intervention(kind="process", option=option)

    @staticmethod
    def commit_identity() -> "Intervention":
        """``do(C_P = identity)`` — the A55 process repair, first-class in A57."""
        return Intervention(kind="process_commit")

    @staticmethod
    def decision(t: int, action: Action) -> "Intervention":
        return Intervention(kind="decision", t=t, action=action)

    @staticmethod
    def execution(site: ControllerSite) -> "Intervention":
        return Intervention(kind="execution", site=site)


@dataclass(frozen=True, slots=True)
class InterventionSet:
    """A candidate repair ``r``, fixed **once** before the rollout (02 §5.0.1)."""

    members: tuple[Intervention, ...] = ()

    def __post_init__(self) -> None:
        nodes = [iv.node() for iv in self.members]
        if len(nodes) != len(set(nodes)):
            raise MalformedIntervention(
                "two interventions target the same structural node; their "
                "composition is undefined (02 §5.0.1)"
            )

    def process(self) -> Intervention | None:
        return next((iv for iv in self.members if iv.kind == "process"), None)

    def process_commit(self) -> Intervention | None:
        """A57: the first-class ``do(C_P = identity)`` member, if present."""
        return next(
            (iv for iv in self.members if iv.kind == "process_commit"), None
        )

    @staticmethod
    def commit_repair() -> "InterventionSet":
        """The size-1 candidate ``{do(C_P = identity)}``."""
        return InterventionSet((Intervention.commit_identity(),))

    def decision_at(self, t: int) -> Intervention | None:
        return next(
            (iv for iv in self.members if iv.kind == "decision" and iv.t == t),
            None,
        )

    def executions(self) -> tuple[Intervention, ...]:
        """**All** execution interventions.

        The earlier code returned only the first, so a joint repair touching two
        controller sites silently lost one of them (A35).
        """
        return tuple(iv for iv in self.members if iv.kind == "execution")

    def site_repairs(self) -> Mapping[ControllerSite, Action]:
        return {iv.site: iv.site.cmd for iv in self.executions()}

    def __len__(self) -> int:
        return len(self.members)


# --------------------------------------------------------------------------- #
# One step — 11-ENVIRONMENT.md §1.1
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


def step(
    state: State,
    control: ControlState,
    a_cmd: Action,
    *,
    tape: SemanticTape,
    mask: FaultMask = FaultMask(),
    controller: Mapping[ControllerSite, Action] | None = None,
    site_repairs: Mapping[ControllerSite, Action] | None = None,
    reward_mode: str = "A",
) -> StepResult:
    """Advance the world one step, in the frozen order of 11 §1.1.

    ::

        (s_t, z, m) -> a^cmd -> u -> a^realized -> (x', y') -> t+1
                    -> hazard check -> terminal/reward -> m'

    ``a_cmd`` is supplied by the caller; this function never chooses one.

    **Controller priority (A35):** ``do(C_X)`` > ``Z_X`` fault > baseline
    controller > identity. The earlier order applied the baseline before the
    fault, so an Oracle execution repair was immediately overwritten by the fault
    it was meant to repair.
    """
    if state.t >= HORIZON:
        raise ValueError("step called past the horizon")

    legal = legal_actions(state)
    illegal = a_cmd not in legal
    a_eff = a_cmd if not illegal else WAIT

    site = ControllerSite(state=state, cmd=a_eff)

    # --- C_X(s, a^cmd) -> u, in priority order ----------------------------- #
    # A75 §62.11 rewrites this as strict top-priority branches rather than a
    # base-then-overwrite cascade, so that the learner contract can bind exactly the
    # channel that takes control:
    #     do(C_X) > Z_X > C_X^L > identity
    if site_repairs is not None and site in site_repairs:
        u = site_repairs[site]                       # evaluator do(C_X)
    elif (mask.controller is not None and mask.controller.state == state
            and mask.controller.cmd == a_eff):
        u = mask.controller.realized                 # transient Z_X keeps fault privilege
    elif controller is not None and site in controller:
        u = controller[site]                         # learner-owned baseline C_X^L
        # Criterion 7 (A75 §62.3): a learner baseline may not expand the behavioural
        # domain of its node. Checked ONLY here -- a uniform check on the final u
        # would delete the fault privilege that Z_X and Z_E exist to exercise.
        #
        # The domain is `u is a true integer id in range` AND `u in A_z(m,s)`. The
        # type half is not pedantry: `True` and `1.0` both compare equal to 1, so a
        # membership test alone would accept them.
        if not _is_int_id(u) or not (0 <= u < len(ACTIONS)) \
                or u not in option_actions(control.z, control, state):
            raise LearnerContractViolation(
                f"at t={state.t}, the learner baseline C_X^L mapped "
                f"{_action_name(a_eff)} to {_action_name(u)}, which is not an action "
                f"id inside A_z(m,s) for option {option_name(control.z)} "
                f"(m={control.m})"
            )
    else:
        u = a_eff                                    # identity

    # --- P(s, u, eps_E) -> a^realized -------------------------------------- #
    a_realized = u
    if mask.plant is not None and mask.plant.t == state.t:
        a_realized = mask.plant.realized

    # --- move, advance t; hazard is checked against the NEW cell ----------- #
    nx, ny = _enter(a_realized, state)
    nxt_t = state.t + 1

    terminal = False
    outcome: str | None = None

    if (nx, ny) == CONTESTED and hazard_at(nxt_t, state.kappa, state.phi):
        terminal, outcome = True, Outcome.COLLISION
    elif mask.trap is not None and (nx, ny) == mask.trap.cell \
            and state.t == mask.trap.t:
        terminal, outcome = True, Outcome.TRAP
    elif (nx, ny) == GOAL:
        terminal, outcome = True, Outcome.SUCCESS
    elif nxt_t >= HORIZON:
        terminal, outcome = True, Outcome.TIMEOUT

    nxt_state = State(x=nx, y=ny, t=nxt_t, kappa=state.kappa, phi=state.phi)

    reward = STEP_COST
    if terminal:
        if outcome == Outcome.SUCCESS:
            reward += REWARD_SUCCESS
        else:
            reward += REWARD_FAILURE_A if reward_mode == "A" else REWARD_FAILURE_B

    # --- automaton updates LAST, and unconditionally (A29, A37) ------------ #
    nxt_control = automaton_transition(
        control.z, control, state, a_eff, nxt_state
    )

    return StepResult(
        state=nxt_state, control=nxt_control, a_cmd=a_cmd, u=u,
        a_realized=a_realized, reward=reward, terminal=terminal,
        outcome=outcome, illegal=illegal,
    )


# --------------------------------------------------------------------------- #
# Rollout — 02 §5.0.1
# --------------------------------------------------------------------------- #

CommandProvider = Callable[[State, ControlState], int]

#: A75 §62.11: the ordinary **learner** baseline for the process/commit layer.
#: Maps ``z^proposal`` to the option it commits. ``None`` means ``C_P^L = identity``.
#: Deliberately a provider and not a store: A75 fixes the *read channel* here and
#: leaves the persistent store representation to the layer above.
ProcessCommitProvider = Callable[[int], int]


def rollout(
    *,
    kappa: int,
    tape: SemanticTape,
    command_provider: CommandProvider,
    base_option: int,
    mask: FaultMask = FaultMask(),
    option_fault: int | None = None,
    interventions: InterventionSet = InterventionSet(),
    controller: Mapping[ControllerSite, Action] | None = None,
    learner_process_commit: ProcessCommitProvider | None = None,
    reward_mode: str = "A",
) -> "RolloutTrace":
    """Run one episode under a fixed intervention set.

    ``base_option`` is the episode's latent option ``z`` — a free variable of
    ``ell`` (``03`` §1). It is **required**, because without it a healthy
    ``z_2``/``z_3``/``z_4`` factual episode cannot be expressed at all: the
    earlier signature could only reach a non-default option by pretending it was
    a ``Z_P`` fault, so ``but_for_relevance(Z_P)`` always removed a fault that
    had never been injected and defaulted to ``z_1`` (A33).

    Option priority:

    ``do(z=z')`` > ``option_fault`` (``Z_P``) > ``base_option``

    Command priority at each step:

    ``do(d_t)`` > ``Z_D`` fault > ``command_provider``

    — ``do`` is an intervention on a structural node and must override the fault
    equation that was there (A34). All four sources must land inside
    ``A_z(m, s)``; a ``do`` or fault that does not is ``MALFORMED``, and a
    *provider* that does not raises :class:`OptionViolation` (A36).
    """
    # A55/A57: this is the process/commit layer in one place.
    #   z^proposal  = base_option
    #   C_P         = identity unless a P fault is present
    #   z^in-force  = z0
    # Priority is FROZEN as
    #   do(z=z')  >  do(C_P=identity)  >  Z_P fault  >  C_P^L(z^proposal)
    # A `do(z = z')` is strategy replay: a downstream root intervention that sets
    # z^in-force outright, bypassing the commit edge. It is NOT a process repair.
    # A `do(C_P = identity)` restores a faithful commit, so it makes z0 the
    # proposal and SHADOWS the fault. When both are present, strategy replay wins
    # and the commit repair is merely shadowed -- that is a legal composition, not
    # MALFORMED, and it is why the two carry distinct structural nodes.
    #
    # A75 §62.11 adds `C_P^L`: the ordinary LEARNER baseline for this layer, which
    # the kernel did not have (both nodes above are evaluator channels). It is
    # written as the lowest-priority BRANCH, not as a base value that gets
    # overwritten, so a shadowed provider is never called and cannot side-effect.
    # `learner_process_commit=None` means C_P^L = identity, so an absent provider
    # reproduces the closed world exactly.
    proc = interventions.process()
    commit = interventions.process_commit()
    if proc is not None:
        z0 = proc.option
    elif commit is not None:
        z0 = base_option
    elif option_fault is not None:
        z0 = option_fault
    elif learner_process_commit is not None:
        z0 = learner_process_commit(base_option)     # learner-owned baseline C_P^L
        # Same domain rule as C_X^L: a true integer id in the option domain. A bool
        # or a float that merely compares equal to an option id is rejected too.
        if not _is_int_id(z0) or z0 not in option_ids():
            raise LearnerContractViolation(
                f"the learner baseline C_P^L mapped the proposal {base_option} to "
                f"{z0!r}, which is not an option id"
            )
    else:
        z0 = base_option                             # C_P^L = identity
    control = initial_control(z0)

    state = State(x=START[0], y=START[1], t=0, kappa=kappa, phi=tape.phase)
    # A87 §75.6 (iii): the episode loop is factored into **one shared core**, so that a
    # continuation and an ordinary rollout are the same code path rather than two implementations
    # that happen to agree. The commit edge above stays *outside* the core: a continuation takes
    # the option as already in force and must not re-execute C_P^L (§75.6 (iv)).
    return continue_rollout(
        state=state, control=control, tape=tape, command_provider=command_provider,
        base_option=base_option, option_in_force=z0, mask=mask,
        interventions=interventions, controller=controller, reward_mode=reward_mode,
    )


def continue_rollout(
    *,
    state: State,
    control: ControlState,
    tape: SemanticTape,
    command_provider: CommandProvider,
    base_option: int,
    option_in_force: int,
    mask: FaultMask = FaultMask(),
    interventions: InterventionSet = InterventionSet(),
    controller: Mapping[ControllerSite, Action] | None = None,
    reward_mode: str = "A",
) -> "RolloutTrace":
    r"""The shared continuation core: steps from a given ``(state, control)`` to terminal or ``H``.

    This is the body of :func:`rollout` after the commit edge has been resolved, and it is the
    **only** implementation of the episode loop in the package.

    $$\boxed{\text{one core} \;\Longrightarrow\; \text{no second simulator to disagree with}}$$

    A87 §75.6 (iv) fixes what it must *not* do: it never re-executes $C_P^{L}$. That is structural
    rather than documented -- the core has no process-commit parameter, so an entry's option is
    already in force by construction, and a caller that wanted to recommit would have to go back
    through :func:`rollout` and step *before* the core.

    ``base_option`` and ``option_in_force`` are carried for the trace's provenance fields. For a
    continuation entered at $(s,z,m)$ there is no proposal distinct from the option in force, so
    both are the entry's $z$; the gates assert the asymmetry on the ordinary side instead, where
    $z^{\text{in-force}} = C_P^{L}(z^{\text{proposal}})$ may differ from the proposal.
    """
    site_repairs = interventions.site_repairs()

    steps: list[StepResult] = []
    while state.t < HORIZON:
        dec = interventions.decision_at(state.t)
        if dec is not None:
            source, a_cmd = "do", dec.action
        elif mask.decision is not None and mask.decision.t == state.t:
            source, a_cmd = "Z_D", mask.decision.action
        else:
            source, a_cmd = "policy", command_provider(state, control)

        allowed = option_actions(control.z, control, state)
        if a_cmd not in allowed:
            msg = (
                f"at t={state.t}, {ACTIONS[a_cmd]} is outside A_z(m,s) for "
                f"option {option_name(control.z)} (m={control.m})"
            )
            if source == "policy":
                raise OptionViolation(msg + " — the policy must obey its option")
            raise MalformedIntervention(msg + f" — {source} may not escape the option")

        res = step(
            state, control, a_cmd, tape=tape, mask=mask, controller=controller,
            site_repairs=site_repairs, reward_mode=reward_mode,
        )
        steps.append(res)
        state, control = res.state, res.control
        if res.terminal:
            break

    return RolloutTrace(
        steps=tuple(steps),
        outcome=steps[-1].outcome if steps else Outcome.TIMEOUT,
        control=control, mask=mask, interventions=interventions,
        base_option=base_option, option_in_force=option_in_force,
    )


@dataclass(frozen=True)
class RolloutTrace:
    steps: tuple[StepResult, ...]
    outcome: str | None
    control: ControlState
    mask: FaultMask
    interventions: InterventionSet
    base_option: int
    option_in_force: int

    @property
    def success(self) -> bool:
        return self.outcome == Outcome.SUCCESS

    @property
    def return_value(self) -> float:
        """``sum_t reward_t`` — **not** a hard-coded ``+-1``.

        The earlier revision returned ``+1 / -1`` and dropped both the per-step
        cost and reward mode B, so a later DP comparison would have reported a
        mismatch that was the trace's fault, not the DP's (A38).
        """
        return float(sum(s.reward for s in self.steps))

    def commands(self) -> tuple[Action, ...]:
        return tuple(s.a_cmd for s in self.steps)

    def realized(self) -> tuple[Action, ...]:
        return tuple(s.a_realized for s in self.steps)

    def execution_deviations(self) -> tuple[int, ...]:
        """Action-steps where the realized action differed from the command.

        Identifies **execution deviation** and nothing more: it says nothing
        about whether the command was a good decision (``01`` §2.3).
        """
        return tuple(s.state.t - 1 for s in self.steps if s.a_realized != s.a_cmd)

    def visited(self) -> tuple[tuple[int, int], ...]:
        return tuple(s.state.cell for s in self.steps)


# --------------------------------------------------------------------------- #
# But-for relevance — 11 §6.1
# --------------------------------------------------------------------------- #

def fired_mechanisms(
    *,
    kappa: int,
    tape: SemanticTape,
    command_provider: CommandProvider,
    base_option: int,
    mask: FaultMask,
    option_fault: int | None = None,
    controller: Mapping[ControllerSite, Action] | None = None,
) -> dict[str, int]:
    """``Z^fire``: which configured mechanisms actually EXECUTED on this rollout.

    A54. Three different objects were previously conflated under ``Z``:

        fault configured/present  !=  fault actually fired
                                  !=  fault was but-for relevant

    ``Z^pres`` is what the generator injected into the latent world; ``B``
    (:func:`but_for_relevance`) is whether removing it changes the outcome; this
    function is the middle one, and it is the one V0.1R asks about, because a
    trap placed at a cell the episode never enters did not *happen*.

    Each mechanism is read off the factual rollout, with no counterfactual:

    ``Z_P``  ``z^in-force != z^proposal`` -- A55: the process/commit layer did
             not faithfully commit what the planner proposed. The chain is
             ``kappa -> z^proposal -> C_P -> z^in-force -> Q_D(s,z,m,.) -> a^cmd``
             and healthy means ``C_P(z^proposal) = z^proposal``. The code
             identifiers map onto it as ``base_option == z^proposal`` and
             ``RolloutTrace.option_in_force == z^in-force``; nothing in the world
             dynamics changed, the two quantities were only given their structure.
             $Z_P$ does **not** mean "the planner chose a bad strategy" (that
             needs a reference for "bad", and using $z^{*}$ would restore the
             solver->generator circularity A19 removed) nor "the strategy is
             unsuited to the context" (a normative/performance relation, not an
             exogenous injection). It is commit/routing integrity, and nothing
             else;
    ``Z_D``  the episode was still alive at the override's timestep, so the
             override was reached and applied;
    ``Z_X``  some step has ``u != a_cmd``   -- the controller emitted something
             other than the command it was given;
    ``Z_E``  some step has ``a_realized != u`` -- the plant did not carry out
             what it received;
    ``Z_U``  the episode terminated in the trap.

    All five are observable facts about one execution, so unlike ``B`` they are
    not counterfactual and no repair primitive is needed to define them.
    """
    keys = ("Z_P", "Z_D", "Z_X", "Z_E", "Z_U")
    try:
        tr = rollout(
            kappa=kappa, tape=tape, command_provider=command_provider,
            base_option=base_option, mask=mask, option_fault=option_fault,
            controller=controller,
        )
    except (MalformedIntervention, OptionViolation):
        return {k: 0 for k in keys}

    out = {k: 0 for k in keys}
    # A55 definition, in full:  Z_P^fire = 1[z^in-force != z^proposal].
    # `rollout` guarantees z^in-force == z^proposal whenever no P fault is
    # present, so this is exactly "the commit layer substituted something".
    if tr.option_in_force != base_option:
        out["Z_P"] = 1
    if mask.decision is not None and len(tr.steps) > mask.decision.t:
        out["Z_D"] = 1
    if any(s.u != s.a_cmd for s in tr.steps):
        out["Z_X"] = 1
    if any(s.a_realized != s.u for s in tr.steps):
        out["Z_E"] = 1
    if tr.outcome == Outcome.TRAP:
        out["Z_U"] = 1
    return out


def but_for_relevance(
    *,
    kappa: int,
    tape: SemanticTape,
    command_provider: CommandProvider,
    base_option: int,
    mask: FaultMask,
    option_fault: int | None = None,
    controller: Mapping[ControllerSite, Action] | None = None,
) -> dict[str, int]:
    """``B``: which active mechanisms were difference-makers on this tape.

    Each fault is removed **individually, with ``omega`` held fixed**, and the
    outcome compared. Resampling the tape would be a different operation and is
    not a but-for test (A26).
    """
    def run(m: FaultMask, opt: int | None) -> str | None:
        return rollout(
            kappa=kappa, tape=tape, command_provider=command_provider,
            base_option=base_option, mask=m, option_fault=opt, controller=controller,
        ).outcome

    try:
        reference = run(mask, option_fault)
    except (MalformedIntervention, OptionViolation):
        return {k: 0 for k in ("Z_P", "Z_D", "Z_X", "Z_E", "Z_U")}

    trials = {
        # A55: the Z_P trial IS the evaluator-side operation do(C_P = identity).
        # Dropping `option_fault` restores z^in-force = z^proposal, i.e. a
        # faithful commit. It remains a but-for CONSTRUCTION and is deliberately
        # NOT in the learner's query set -- adding it would be do(Z_P = off),
        # which certifies B by handing over the operation that defines it (A51).
        # It is a distinct operation from `do(z = z')`: that one is strategy
        # replay ("run option z' for the whole episode"), not process repair.
        "Z_P": (mask, None),
        "Z_D": (dataclasses.replace(mask, decision=None), option_fault),
        "Z_X": (dataclasses.replace(mask, controller=None), option_fault),
        "Z_E": (dataclasses.replace(mask, plant=None), option_fault),
        "Z_U": (dataclasses.replace(mask, trap=None), option_fault),
    }
    out: dict[str, int] = {}
    for name, (m, opt) in trials.items():
        try:
            out[name] = int(run(m, opt) != reference)
        except (MalformedIntervention, OptionViolation):
            out[name] = 0
    return out
