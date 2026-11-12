r"""$F_0$ §3's approved baseline initializer and the *logic* of its five-part construction gate.

Two things are gated here and one deliberately is not. Gated: the initializer's identity (it really is
$W^{\varnothing} + \Delta W^{\text{cal}}_{D_Q}$ and nothing else), the gate's proposition logic on synthetic
evidence, and the repair arithmetic that the frozen $\alpha$ and the store's canonicalisation rule imply.
**Not** asserted: the measured verdict of the pre-specified gate on $\mathcal B^{\text{op}}_{\text{dev}}$ ---
that run's result is evidence (`experiments/v03r/f0_initializer_gate.json`), and pinning it as an expectation
would freeze a failure that is awaiting a ruling rather than a fix.
"""

from __future__ import annotations

import pathlib
import sys
from types import MappingProxyType

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fractions import Fraction  # noqa: E402

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2.evalorder import prefix  # noqa: E402
from rfl_rebuild.b2.initializer import (  # noqa: E402
    BaselineGateEvidence,
    baseline_gate,
    baseline_initializer,
    canary_address,
    canary_override_present,
)
from rfl_rebuild.b2.training import BaselineAcquisitionPlan, FutureTrainingProtocol  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import Edit, Q, QAddress, LearnerPersistentState  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

REFERENCE = reference_view_from(solve_reference())
KEY = 900001
BANK = prefix(8)


def _plan(**overrides) -> BaselineAcquisitionPlan:
    fields = dict(seed=KEY, alpha=Fraction(1, 2), epsilon=Fraction(1, 10), acquisition_cap=2,
                  evaluation_bank=BANK)
    fields.update(overrides)
    return BaselineAcquisitionPlan(**fields)


def _evidence(flags, curves, visited=None, q_states=None) -> BaselineGateEvidence:
    if q_states is None:
        q_states = {k: tuple(MappingProxyType({canary_address(): -0.14} if present else {})
                             for present in values) for k, values in flags.items()}
    return BaselineGateEvidence(
        keys=tuple(flags), cap=len(next(iter(flags.values()))) - 1, bank_size=1,
        overrides_by_episode=MappingProxyType(flags), curves=MappingProxyType(curves),
        canary_visited=MappingProxyType(visited or {k: (False,) for k in flags}),
        q_overrides_by_episode=MappingProxyType(q_states))


# --- the initializer --------------------------------------------------------------------------------

def test_1_the_initializer_is_the_frozen_canary_and_nothing_else():
    address = canary_address()
    assert type(address) is QAddress and address.state.x == 0 and address.state.y == 2
    assert (address.state.t, address.state.kappa, address.state.phi) == (0, 0, 0)
    assert (address.z, address.m, address.a) == (1, 0, 3)          # A87 §75.2, pinned
    learner = baseline_initializer(q_reference=REFERENCE)
    assert learner.healthy is False
    assert dict(learner.q_overrides) == {address: -0.14}
    assert canary_override_present(learner) is True
    assert REFERENCE.value(address) == 0.8799999999999999          # the value the repair must reach


def test_2_the_canary_must_stay_a_q_store_write():
    r"""Its whole justification is A91 §79.4: ordinary training writes $Q_D^{L}$ only."""
    from rfl_rebuild.b2 import screening

    edit = screening.canary_edit("D_Q")
    assert edit.store == Q and edit.value == -0.14
    for arch in ("X", "P"):
        assert screening.canary_edit(arch).store != Q, (
            f"{arch}'s canary is not a Q write, so ordinary training cannot repair it")


def test_3_the_override_test_refuses_anything_that_is_not_a_learner_state():
    with pytest.raises(ProtocolError, match="LearnerPersistentState"):
        canary_override_present({})


# --- the gate's logic -------------------------------------------------------------------------------

def test_4_all_five_propositions_admit():
    evidence = _evidence({KEY: (True, False), 900002: (True, False)},
                         {KEY: (1.0, 2.0), 900002: (1.0, 2.5)},
                         {KEY: (True,), 900002: (True,)})
    assert evidence.failures() == ()
    assert evidence.admissible() is True
    assert evidence.witnesses() == {"moved_at": {KEY: 1, 900002: 1},
                                    "repaired_at": {KEY: 1, 900002: 1}}
    assert evidence.canary_ever_visited() == 2


def test_5_each_proposition_has_its_own_failure_name():
    base = {"flags": {KEY: (True, True)}, "curves": {KEY: (1.0, 2.0)}}
    variants = {
        "a_canary_at_entry": _evidence({KEY: (False, False)}, {KEY: (1.0, 2.0)}),
        "a_prime_left_the_fixed_point": _evidence({KEY: (True, True)}, {KEY: (1.0, 2.0)}),
        "b1_curve_moves": _evidence({KEY: (True, False)}, {KEY: (1.0, 1.0)}),
        "b2_curves_separate": _evidence({KEY: (True, False)}, {KEY: (1.0, 2.0)}),
        "c_repaired_within_cap": _evidence({KEY: (True, True)}, {KEY: (1.0, 2.0)}),
    }
    for name, evidence in variants.items():
        assert name in evidence.failures(), name
    assert variants["b2_curves_separate"].curves_separate() is False
    # and (b2) is satisfied by two keys whose curves differ at any episode
    split = _evidence({KEY: (True, False), 900002: (True, True)}, {KEY: (1.0, 2.0), 900002: (1.0, 2.5)})
    assert split.curves_separate() is True
    assert base  # the shape the variants are cut from stays readable


def test_6_a_repair_needs_one_key_and_the_diagnostic_never_decides():
    repaired = _evidence({KEY: (True, False), 900002: (True, True)}, {KEY: (1.0, 2.0), 900002: (1.0, 2.0)},
                         {KEY: (True,), 900002: (False,)})
    assert repaired.repaired_within_cap() is True
    assert repaired.witnesses()["repaired_at"] == {KEY: 1}
    assert repaired.canary_ever_visited() == 1
    assert "canary_ever_visited" not in repaired.failures()
    never = _evidence({KEY: (True, False)}, {KEY: (1.0, 2.0)}, {KEY: (False,)})
    assert never.canary_ever_visited() == 0 and never.repaired_within_cap() is True


def test_7_the_gate_refuses_a_workload_it_cannot_interpret():
    with pytest.raises(ProtocolError, match="pre-F1 envelope"):
        baseline_gate(FutureTrainingProtocol(seed=KEY, alpha=Fraction(1, 2), epsilon=Fraction(1, 10),
                                             t_max=2, grid=(0, 1, 2), evaluation_sample=BANK, v_pre=0.5),
                      keys=(KEY,), q_reference=REFERENCE)
    with pytest.raises(ProtocolError, match="at least one operational key"):
        baseline_gate(_plan(), keys=(), q_reference=REFERENCE)
    with pytest.raises(ProtocolError, match="true integers"):
        baseline_gate(_plan(), keys=(True,), q_reference=REFERENCE)


def test_8_the_gate_runs_the_envelope_and_records_the_frozen_object():
    evidence = baseline_gate(_plan(), keys=(KEY,), q_reference=REFERENCE)
    assert evidence.cap == 2 and evidence.bank_size == len(BANK)
    assert evidence.keys == (KEY,)
    flags = evidence.overrides_by_episode[KEY]
    assert len(flags) == 3 and flags[0] is True, "(a): the canary is there at e = 0"
    assert len(evidence.curves[KEY]) == 3 and len(evidence.canary_visited[KEY]) == 2
    assert isinstance(evidence.left_the_fixed_point(), bool)


def test_9_repair_arithmetic_the_frozen_alpha_implies_fifty_four_visits():
    r"""**Why a single-address defect cannot pass (c).**

    The store canonicalises an override away only on **bit-exact** equality with the reference
    (`float(value) == q_reference.value(address)`), and the sweep is `v <- v + alpha (Q* - v)`. With the
    frozen $\alpha = 1/2$ that is a geometric contraction, so the canary's $-0.14$ needs this many visits
    before the override disappears at all --- while each visit needs the exploration coin to pick one exact
    action at one exact context. The count is a property of the frozen rule, not of a run.
    """
    address = canary_address()
    target = REFERENCE.value(address)
    value, visits = -0.14, 0
    while value != target and visits < 1000:
        value = value + 0.5 * (target - value)
        visits += 1
    assert visits == 54 and value == target
    exact, steps = -0.14, 0
    while exact != target and steps < 1000:      # alpha = 1 is inside A91's frozen domain too
        exact = exact + 1.0 * (target - exact)
        steps += 1
    assert steps < visits, "a larger step size would need fewer visits; alpha is what sets the count"


@pytest.mark.parametrize("repair_episode", [1, 2, 40])
def test_repair_at_any_episode_including_the_cap_is_accepted(repair_episode):
    flags = (True,) * repair_episode + (False,) * (41 - repair_episode)
    evidence = _evidence({KEY: flags}, {KEY: (1.0,) * 41})
    assert evidence.repaired_within_cap() is True
    assert evidence.witnesses()["repaired_at"] == {KEY: repair_episode}


def test_repair_is_existential_even_if_the_defect_returns():
    evidence = _evidence({KEY: (True, True, False, True)}, {KEY: (1.0,) * 4})
    assert evidence.repaired_within_cap() is True
    assert evidence.witnesses()["repaired_at"] == {KEY: 2}


def test_q_value_movement_is_not_override_removal():
    address = canary_address()
    evidence = _evidence({KEY: (True, True)}, {KEY: (1.0, 1.0)},
                         q_states={KEY: ({address: -0.14}, {address: 0.37})})
    assert evidence.left_the_fixed_point() is True
    assert evidence.repaired_within_cap() is False
    assert evidence.witnesses() == {"moved_at": {KEY: 1}, "repaired_at": {}}


def test_gate_collects_independent_full_q_snapshots(monkeypatch):
    from rfl_rebuild.b2 import initializer

    # Controlled writes exercise collection through the real transaction boundary.
    # The second write changes another Q address while the canary stays present.
    from dataclasses import replace

    address = canary_address()
    other = next(replace(address, a=a)
                 for a in REFERENCE.rows[(address.state, address.z, address.m)] if a != address.a)
    edits = iter([(Edit(Q, address, 0.37),), (Edit(Q, other, -0.5),)])
    monkeypatch.setattr(initializer, "sweep_edits", lambda *a, **kw: next(edits))
    evidence = baseline_gate(_plan(), keys=(KEY,), q_reference=REFERENCE)
    snapshots = evidence.q_overrides_by_episode[KEY]
    assert evidence.overrides_by_episode[KEY] == (True, True, True)
    assert snapshots[0] == {address: -0.14}
    assert snapshots[1] == {address: 0.37}
    assert snapshots[2] == {address: 0.37, other: -0.5}
    assert evidence.left_the_fixed_point() is True
    assert evidence.repaired_within_cap() is False
    assert evidence.witnesses()["moved_at"] == {KEY: 1}
    with pytest.raises(TypeError):
        snapshots[0][address] = 0.0
