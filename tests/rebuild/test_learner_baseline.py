"""A75 §62.11 — the learner baseline read channels and their contract.

Two channels, and nothing else:

* ``C_P^L`` — a new ordinary baseline path for the process/commit layer, supplied
  externally as a ``ProcessCommitProvider``. ``None`` means identity, so an absent
  provider reproduces the closed world exactly.
* ``C_X^L`` — the existing ``controller`` mapping, now required to satisfy
  ``u in A_z(m, s)`` when it is the learner baseline that actually takes control.

Frozen priority, both layers:

    do(z=z') > do(C_P=identity) > Z_P > C_P^L(z^proposal)
    do(C_X)  > Z_X             > C_X^L > identity

**Fault privilege is not a learner privilege.** ``Z_X`` and ``Z_E`` may leave
``A_z`` — that is what makes them faults — while a learner-owned baseline may not.
The contract check therefore sits *inside* the baseline branch, never on the final
``u``: a uniform legality check on ``u`` would delete the fault privilege.

``LearnerContractViolation`` is deliberately **not** an ``OptionViolation`` subclass
and is not added to any ``except (MalformedIntervention, OptionViolation)``: the old
gates treat those as ordinary policy-legality exclusions, and a learner-baseline
contract breach is a new fail-fast protocol violation that must not be swallowed as
a routine rejected case.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerFault, ControllerSite, FaultMask, Intervention, InterventionSet,
    OptionViolation, PlantFault, SemanticTape, State,
)

UP, DOWN, LEFT, RIGHT, WAIT = K.UP, K.DOWN, K.LEFT, K.RIGHT, K.WAIT

TAPE = SemanticTape(phase=0, error_flag=0, cause_rank=0)
START_STATE = State(x=K.START[0], y=K.START[1], t=0, kappa=0, phi=0)
#: ``z=0`` is ``rush``: at START its admissible set is exactly {RIGHT}, while WAIT is
#: physically legal. That gap is the contract test's witness.
RUSH = 0


def go_right(state, ctrl):
    """A trivially valid provider: always RIGHT when admissible, else WAIT."""
    return RIGHT if RIGHT in K.option_actions(ctrl.z, ctrl, state) else WAIT


def run(**kw) -> K.RolloutTrace:
    args = dict(kappa=0, tape=TAPE, command_provider=go_right, base_option=RUSH)
    args.update(kw)
    return K.rollout(**args)


# --------------------------------------------------------------------------- #
# C_P^L — identity, activity, contract
# --------------------------------------------------------------------------- #

def test_process_baseline_absent_is_identity():
    """No provider must reproduce the closed world exactly, bit for bit."""
    absent = run()
    explicit = run(learner_process_commit=lambda z: z)
    assert absent.option_in_force == explicit.option_in_force == RUSH
    assert absent.commands() == explicit.commands()
    assert absent.realized() == explicit.realized()
    assert [s.reward for s in absent.steps] == [s.reward for s in explicit.steps]


def test_process_baseline_can_route_the_proposal_to_another_legal_option():
    """The channel is live: a baseline may commit a different legal option."""
    routed = run(learner_process_commit=lambda z: 2)
    assert routed.option_in_force == 2
    assert routed.option_in_force != RUSH


def test_process_baseline_contract_violation():
    """A baseline that actually takes control must stay in the option domain."""
    with pytest.raises(K.LearnerContractViolation):
        run(learner_process_commit=lambda z: 99)


def test_process_priority_four_step_canary():
    """One canary, four layers, so an accidental code-order cannot pass.

    ``do(z) > do(C_P=id) > Z_P > C_P^L``
    """
    step1 = run(learner_process_commit=lambda z: 1)
    assert step1.option_in_force == 1, "layer 1: C_P^L takes control"

    step2 = run(learner_process_commit=lambda z: 1, option_fault=2)
    assert step2.option_in_force == 2, "layer 2: Z_P shadows C_P^L"

    step3 = run(learner_process_commit=lambda z: 1, option_fault=2,
                interventions=InterventionSet.commit_repair())
    assert step3.option_in_force == RUSH, "layer 3: do(C_P=id) shadows Z_P"

    step4 = run(learner_process_commit=lambda z: 1, option_fault=2,
                interventions=InterventionSet(
                    (Intervention.process(3), Intervention.commit_identity())))
    assert step4.option_in_force == 3, "layer 4: do(z) is highest"


def test_shadowed_process_baseline_is_never_consulted():
    """A shadowed provider must not be called at all, so it cannot side-effect."""
    calls: list[int] = []

    def provider(z: int) -> int:
        calls.append(z)
        return 1

    run(learner_process_commit=provider, option_fault=2)
    assert calls == [], "Z_P holds control, so C_P^L must not run"

    run(learner_process_commit=provider,
        interventions=InterventionSet.commit_repair())
    assert calls == [], "do(C_P=id) holds control, so C_P^L must not run"


def test_process_baseline_legality_is_checked_only_when_it_controls():
    """An illegal baseline is only a violation if it actually takes control."""
    with pytest.raises(K.LearnerContractViolation):
        run(learner_process_commit=lambda z: 99)
    # shadowed by do(C_P=id): the illegal baseline never governs, so no violation
    trace = run(learner_process_commit=lambda z: 99,
                interventions=InterventionSet.commit_repair())
    assert trace.option_in_force == RUSH


# --------------------------------------------------------------------------- #
# C_X^L — activity, contract, and the fault privilege that must survive
# --------------------------------------------------------------------------- #

def test_controller_baseline_may_map_inside_the_option():
    """A learner controller may do a non-identity map as long as it stays in A_z."""
    allowed = K.option_actions(RUSH, K.ControlState(z=RUSH, m=0), START_STATE)
    assert set(allowed) == {RIGHT}, "fixture drift: rush at START must be {RIGHT}"
    trace = run(controller={ControllerSite(state=START_STATE, cmd=RIGHT): RIGHT})
    assert trace.steps[0].u == RIGHT


def test_controller_baseline_outside_the_option_raises():
    """The review's witness: rush at START, RIGHT is admissible, WAIT is not."""
    assert WAIT in K.legal_actions(START_STATE), "WAIT must be physically legal"
    assert WAIT not in K.option_actions(RUSH, K.ControlState(z=RUSH, m=0), START_STATE)
    with pytest.raises(K.LearnerContractViolation):
        run(controller={ControllerSite(state=START_STATE, cmd=RIGHT): WAIT})


def test_zx_keeps_the_fault_privilege():
    """The same deviation via Z_X must NOT raise: that is what a fault is."""
    fault = ControllerFault(state=START_STATE, cmd=RIGHT, realized=WAIT)
    trace = run(mask=FaultMask(controller=fault))
    assert trace.steps[0].u == WAIT, "the fault deviation must be applied"
    assert trace.steps[0].a_realized == WAIT


def test_ze_keeps_the_fault_privilege():
    """Z_E may also leave A_z without a contract violation."""
    trace = run(mask=FaultMask(plant=PlantFault(t=0, realized=WAIT)))
    assert trace.steps[0].a_realized == WAIT


def test_controller_baseline_is_checked_only_when_it_controls():
    """A fault shadows the baseline, so an illegal baseline must not raise."""
    illegal = {ControllerSite(state=START_STATE, cmd=RIGHT): WAIT}
    fault = ControllerFault(state=START_STATE, cmd=RIGHT, realized=RIGHT)
    trace = run(controller=illegal, mask=FaultMask(controller=fault))
    assert trace.steps[0].u == RIGHT, "Z_X holds control; C_X^L never governs"

    repair = InterventionSet((Intervention.execution(
        ControllerSite(state=START_STATE, cmd=RIGHT)),))
    trace = run(controller=illegal, interventions=repair)
    assert trace.steps[0].u == RIGHT, "do(C_X) holds control; C_X^L never governs"


def test_controller_priority_order():
    """``do(C_X) > Z_X > C_X^L > identity``, one layer at a time."""
    site = ControllerSite(state=START_STATE, cmd=RIGHT)
    learner = {site: RIGHT}

    # C_X^L governs and maps RIGHT -> RIGHT (identity-valued, but through the channel)
    assert run(controller=learner).steps[0].u == RIGHT

    # Z_X shadows C_X^L
    zx = FaultMask(controller=ControllerFault(state=START_STATE, cmd=RIGHT,
                                              realized=RIGHT))
    assert run(controller=learner, mask=zx).steps[0].u == RIGHT

    # do(C_X) shadows Z_X: the repair must not be overwritten by the fault
    zx_dev = FaultMask(controller=ControllerFault(state=START_STATE, cmd=RIGHT,
                                                  realized=WAIT))
    repair = InterventionSet((Intervention.execution(site),))
    trace = run(controller=learner, mask=zx_dev, interventions=repair)
    assert trace.steps[0].u == RIGHT, "do(C_X) outranks Z_X"


def test_learner_contract_violation_is_not_an_option_violation():
    """It must not be swallowed by the old gates' exception handling."""
    assert not issubclass(K.LearnerContractViolation, OptionViolation)
