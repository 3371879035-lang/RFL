"""Kernel regression tests — the frozen contract of ``src/rfl_rebuild/env/kernel.py``.

Not the C0–C8 semantic suite (that is a later gate, and it tests the learner).
This is the narrow, mechanical layer: the kernel's *own* frozen claims, so that
the corrections A32–A38 cannot silently regress.

The five most valuable tests here are the ones that would have caught the bugs
found in review, all of which survived a full read of the code:

* :func:`test_z2_waypoint_is_reachable` / :func:`test_z4_waypoint_is_reachable`
  — both waypoints were **inside the wall set**, so ``m=1`` was unreachable;
* :func:`test_decision_fault_changes_the_trajectory` — ``Z_D`` existed but was
  never applied;
* :func:`test_base_option_is_not_always_z1` — a healthy ``z_2`` episode was
  inexpressible;
* :func:`test_execution_repair_overrides_the_fault` — the fault overwrote the
  repair that was meant to fix it;
* :func:`test_policy_cannot_escape_the_option` — the option constraint bound only
  counterfactuals, not behaviour.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerSite, FaultMask, Intervention, InterventionSet,
    MalformedIntervention, OptionViolation, SemanticTape, State, Trap,
    ControllerFault, DecisionOverride, PlantFault,
)

UP, DOWN, LEFT, RIGHT, WAIT = K.UP, K.DOWN, K.LEFT, K.RIGHT, K.WAIT

# --------------------------------------------------------------------------- #
# Hand-written route providers. These live in the *test*, never in the kernel:
# the kernel may not own a reference policy.
# --------------------------------------------------------------------------- #

ROUTE_Z1 = [(0, 2), (1, 2), (2, 2), (3, 2), (4, 2)]
ROUTE_Z2 = [(0, 2), (1, 2), (1, 1), (2, 1), (3, 1), (3, 2), (4, 2)]
ROUTE_Z4 = [(0, 2), (1, 2), (1, 3), (1, 4), (2, 4),
            (3, 4), (3, 3), (3, 2), (4, 2)]


def _step_action(a: tuple[int, int], b: tuple[int, int]) -> int:
    return {(0, -1): UP, (0, 1): DOWN, (-1, 0): LEFT, (1, 0): RIGHT}[(b[0] - a[0], b[1] - a[1])]


def scripted(route: list[tuple[int, int]]):
    def provider(state: State, control: K.ControlState) -> int:
        try:
            i = route.index(state.cell)
        except ValueError:
            return WAIT
        if i + 1 >= len(route):
            return WAIT
        return _step_action(route[i], route[i + 1])

    return provider


def wait_then_cross(state: State, control: K.ControlState) -> int:
    """``z_3``: hold at ``(1,2)`` while ``m=0``, then cross."""
    if state.cell == (1, 2) and control.m == 0:
        return WAIT
    if state.x < 4:
        return RIGHT
    return WAIT


def tape(phi: int = 0, err: int = 0, rank: int = 0) -> SemanticTape:
    return SemanticTape(phase=phi, error_flag=err, cause_rank=rank)


# --------------------------------------------------------------------------- #
# Map — the single source of truth
# --------------------------------------------------------------------------- #

def test_wall_set_matches_the_canonical_map():
    expected_open = {
        (1, 1), (2, 1), (3, 1),
        (0, 2), (1, 2), (2, 2), (3, 2), (4, 2),
        (1, 3), (3, 3),
        (1, 4), (2, 4), (3, 4),
    }
    assert K.OPEN_CELLS == expected_open
    assert K.START in K.OPEN_CELLS and K.GOAL in K.OPEN_CELLS


def test_waypoints_are_open_cells():
    """A32: both automaton waypoints were inside the wall set."""
    assert K.WAYPOINT_Z2 in K.OPEN_CELLS
    assert K.WAYPOINT_Z4 in K.OPEN_CELLS


# --------------------------------------------------------------------------- #
# Routes and automata
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "base, route",
    [(0, ROUTE_Z1), (1, ROUTE_Z2), (3, ROUTE_Z4)],
)
def test_declared_routes_are_walkable(base, route):
    tr = K.rollout(
        kappa=0, tape=tape(), command_provider=scripted(route),
        base_option=base,
    )
    assert tr.outcome == K.Outcome.SUCCESS
    assert tr.visited() == tuple(route[1:])


def test_z2_waypoint_is_reachable():
    tr = K.rollout(kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z2),
                   base_option=1)
    assert K.WAYPOINT_Z2 in tr.visited()
    assert tr.control.m == 1


def test_z4_waypoint_is_reachable():
    tr = K.rollout(kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z4),
                   base_option=3)
    assert K.WAYPOINT_Z4 in tr.visited()
    assert tr.control.m == 1


def test_z2_cannot_enter_the_goal_before_its_waypoint():
    """A_z(m=0) excludes GOAL; this is what makes the option a real constraint."""
    s = State(3, 2, 3, 0, 0)
    assert RIGHT not in K.option_actions(1, K.ControlState(1, 0), s)
    assert RIGHT in K.option_actions(1, K.ControlState(1, 1), s)


def test_z3_completes_under_a_fast_hazard():
    tr = K.rollout(kappa=1, tape=tape(phi=2), command_provider=wait_then_cross,
                   base_option=2)
    assert tr.outcome == K.Outcome.SUCCESS


# --------------------------------------------------------------------------- #
# Hazard and step order
# --------------------------------------------------------------------------- #

def test_hazard_is_checked_at_the_new_cell_and_new_time():
    tr = K.rollout(kappa=1, tape=tape(phi=2), command_provider=scripted(ROUTE_Z1),
                   base_option=0)
    assert tr.outcome == K.Outcome.COLLISION
    assert tr.visited()[-1] == K.CONTESTED
    assert len(tr.steps) == 2  # (1,2) at t=1, then (2,2) at t=2


def test_automaton_updates_on_a_terminal_step():
    """A37: the transition runs last, unconditionally — even when terminal."""
    tr = K.rollout(kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z2),
                   base_option=1)
    assert tr.steps[-1].terminal
    assert tr.control.m == 1


# --------------------------------------------------------------------------- #
# Option constraint binds every command source
# --------------------------------------------------------------------------- #

def test_policy_cannot_escape_the_option():
    """A36: the constraint bound only counterfactuals before this test existed."""
    def cheat(state: State, control: K.ControlState) -> int:
        return RIGHT if state.x < 4 else WAIT

    # z2 reaches (3,2) with m=0 (waypoint not visited); RIGHT would enter GOAL.
    with pytest.raises(OptionViolation):
        K.rollout(kappa=0, tape=tape(), command_provider=cheat, base_option=1)
    # The same provider is fine under z1, which has no obligation.
    K.rollout(kappa=0, tape=tape(), command_provider=cheat, base_option=0)


def test_do_cannot_escape_the_option():
    # Under z2 the walk reaches (3,2) at t=3 with m=0; RIGHT there enters GOAL.
    with pytest.raises(MalformedIntervention):
        K.rollout(
            kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z1),
            base_option=1,
            interventions=InterventionSet((Intervention.decision(3, RIGHT),)),
        )


# --------------------------------------------------------------------------- #
# Faults actually fire
# --------------------------------------------------------------------------- #

def test_decision_fault_changes_the_trajectory():
    """A34: ``mask.decision`` was never read, so Z_D was inert."""
    clean = K.rollout(kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z1),
                      base_option=0)
    faulted = K.rollout(
        kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z1), base_option=0,
        mask=FaultMask(decision=DecisionOverride(t=1, action=WAIT)),
    )
    assert clean.outcome == K.Outcome.SUCCESS
    assert faulted.commands() != clean.commands()
    assert faulted.commands()[1] == WAIT


def test_do_overrides_the_decision_fault():
    """``do(d_t)`` > ``Z_D``: an intervention overrides the fault equation."""
    tr = K.rollout(
        kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z1), base_option=0,
        mask=FaultMask(decision=DecisionOverride(t=1, action=WAIT)),
        interventions=InterventionSet((Intervention.decision(1, RIGHT),)),
    )
    assert tr.outcome == K.Outcome.SUCCESS


def test_base_option_is_not_always_z1():
    """A33: a healthy z2 episode had to be faked as a Z_P fault."""
    tr = K.rollout(kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z2),
                   base_option=1)
    assert tr.base_option == 1
    assert tr.option_in_force == 1
    assert tr.visited() == tuple(ROUTE_Z2[1:])


def test_process_intervention_beats_the_base_option():
    tr = K.rollout(
        kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z2), base_option=0,
        interventions=InterventionSet((Intervention.process(1),)),
    )
    assert tr.option_in_force == 1
    assert tr.control.z == 1
    assert tr.outcome == K.Outcome.SUCCESS


def test_but_for_relevance_of_z_p_is_not_silently_true():
    """Removing a Z_P that was never injected must report 0, not 1."""
    b = K.but_for_relevance(
        kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z1),
        base_option=0, mask=FaultMask(),
    )
    assert b["Z_P"] == 0
    assert all(v == 0 for v in b.values())


# --------------------------------------------------------------------------- #
# Execution / controller
# --------------------------------------------------------------------------- #

def test_controller_is_keyed_on_the_command():
    """A35: the key omitted ``a^cmd``, so two commands were one site."""
    s = State(1, 2, 1, 0, 0)
    assert ControllerSite(s, RIGHT) != ControllerSite(s, WAIT)


def test_execution_fault_and_repair_priority():
    """``do(C_X)`` > ``Z_X`` > baseline controller."""
    site = ControllerSite(State(0, 2, 0, 0, 0), RIGHT)
    fault = FaultMask(controller=ControllerFault(
        state=State(0, 2, 0, 0, 0), cmd=RIGHT, realized=LEFT))

    faulted = K.rollout(kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z1),
                        base_option=0, mask=fault)
    assert LEFT in faulted.realized(), "Z_X did not fire"

    repaired = K.rollout(
        kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z1), base_option=0,
        mask=fault,
        interventions=InterventionSet((Intervention.execution(site),)),
    )
    assert LEFT not in repaired.realized(), "the fault overwrote the repair"
    assert repaired.realized()[0] == RIGHT


def test_all_execution_repairs_are_applied():
    """A35: only the first execution intervention used to be honoured."""
    s0 = State(0, 2, 0, 0, 0)
    s1 = State(1, 2, 1, 0, 0)
    mask = FaultMask(
        controller=ControllerFault(state=s0, cmd=RIGHT, realized=LEFT),
        plant=PlantFault(t=1, realized=LEFT),
    )
    tr = K.rollout(
        kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z1), base_option=0,
        mask=mask,
        interventions=InterventionSet((
            Intervention.execution(ControllerSite(s0, RIGHT)),
            Intervention.execution(ControllerSite(s1, RIGHT)),
        )),
    )
    # Z_X at s0 is repaired; the plant fault at t=1 still fires.
    assert tr.realized()[0] == RIGHT
    assert len(tr.interventions.executions()) == 2


# --------------------------------------------------------------------------- #
# Trap
# --------------------------------------------------------------------------- #

def test_trap_fires_at_action_step_zero():
    """A37: comparing against ``t+1`` made ``t*=0`` unreachable."""
    tr = K.rollout(
        kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z1), base_option=0,
        mask=FaultMask(trap=Trap(cell=(1, 2), t=0)),
    )
    assert tr.outcome == K.Outcome.TRAP
    assert len(tr.steps) == 1


def test_trap_domain_is_validated():
    with pytest.raises(ValueError):
        Trap(cell=K.GOAL, t=0)
    with pytest.raises(ValueError):
        Trap(cell=(2, 3), t=0)          # a wall
    with pytest.raises(ValueError):
        Trap(cell=(1, 2), t=K.HORIZON)  # outside [0, H)


# --------------------------------------------------------------------------- #
# Return value and feedback schema
# --------------------------------------------------------------------------- #

def test_return_value_is_the_reward_sum():
    """A38: it used to be a hard-coded ``+-1``, dropping the step cost."""
    tr = K.rollout(kappa=0, tape=tape(), command_provider=scripted(ROUTE_Z1),
                   base_option=0)
    assert tr.return_value == pytest.approx(sum(s.reward for s in tr.steps))
    assert tr.return_value == pytest.approx(1.0 + 4 * K.STEP_COST)


def test_return_value_honours_reward_mode_b():
    tr = K.rollout(kappa=1, tape=tape(phi=2), command_provider=scripted(ROUTE_Z1),
                   base_option=0, reward_mode="B")
    assert tr.outcome == K.Outcome.COLLISION
    assert tr.return_value == pytest.approx(0.0 + 2 * K.STEP_COST)


def test_feedback_decoder_returns_a_one_hot_vector():
    """A38: the spec freezes a five-vector, not a sparse index set."""
    v = tape(rank=0).decode_feedback([1, 0, 0, 0, 0])
    assert len(v) == 5 and sum(v) == 1 and set(v) <= {0, 1}


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5])
def test_feedback_decoding_is_exactly_uniform(size):
    counts = [0] * size
    for rank in range(60):
        v = tape(rank=rank).decode_feedback([1] * size + [0] * (5 - size))
        counts[v.index(1)] += 1
    assert len(set(counts)) == 1, f"|E|={size} is not uniform: {counts}"
    assert sum(counts) == 60


def test_empty_eligible_set_yields_the_empty_claim():
    assert tape(err=1, rank=7).decode_feedback([1] * 5) == (0,) * 5
    assert tape(err=0, rank=7).decode_feedback([0] * 5) == (0,) * 5


# --------------------------------------------------------------------------- #
# Intervention well-formedness
# --------------------------------------------------------------------------- #

def test_intervention_validates_required_fields_per_kind():
    """A37: incomplete interventions were constructible silent no-ops."""
    with pytest.raises(MalformedIntervention):
        Intervention(kind="process")
    with pytest.raises(MalformedIntervention):
        Intervention(kind="decision", action=RIGHT)
    with pytest.raises(MalformedIntervention):
        Intervention(kind="execution")
    with pytest.raises(MalformedIntervention):
        Intervention(kind="nonsense")


def test_duplicate_structural_node_is_malformed():
    with pytest.raises(MalformedIntervention):
        InterventionSet((
            Intervention.decision(3, UP),
            Intervention.decision(3, DOWN),
        ))


# --------------------------------------------------------------------------- #
# Tape
# --------------------------------------------------------------------------- #

def test_tape_has_no_positional_interface():
    for bad in ("next_draw", "random", "choice", "randrange"):
        assert not hasattr(SemanticTape, bad)


def test_tape_key_set_is_frozen():
    t = tape()
    assert set(t.keys()) == {("hazard", "phase"),
                             ("feedback", "error_flag"),
                             ("feedback", "cause_rank")}
    with pytest.raises(KeyError):
        t.get(("hazard", "occupancy"))


def test_same_tape_gives_the_same_rollout():
    a = K.rollout(kappa=1, tape=tape(phi=2), command_provider=scripted(ROUTE_Z1),
                  base_option=0)
    b = K.rollout(kappa=1, tape=tape(phi=2), command_provider=scripted(ROUTE_Z1),
                  base_option=0)
    assert a.return_value == b.return_value
    assert a.commands() == b.commands()


def test_kernel_owns_no_policy_or_solver():
    """The architectural boundary, asserted rather than reviewed."""
    import inspect

    src = inspect.getsource(K)
    assert "def policy" not in src
    assert "reference_policy" not in src
    assert "import torch" not in src
    assert "import numpy" not in src
    # the only mentions of argmax are docstrings saying it is NOT computed here
    assert src.count("argmax") == src.count("does **not** compute")
