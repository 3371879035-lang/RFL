"""C1 construction only: real transitions, policy/number distinction, negative controls."""
from fractions import Fraction
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.initializer import baseline_initializer, canary_address
from rfl_rebuild.b2.initializer_candidate import optimistic_fixture
from rfl_rebuild.b2.screening import CANARY_TAPE
from rfl_rebuild.b2.training import (BaselineAcquisitionPlan, ExogenousEpisode,
                                     episode_rollout, sweep_edits, is_explore)
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference

REFERENCE = reference_view_from(solve_reference())


def matching_greedy_update(learner, fixture):
    # Hand-constructed Xi, not an acquired seed: isolate two matching greedy visits.
    # An extremely small exact epsilon permits the actual A91 path; assert its coin.
    protocol = BaselineAcquisitionPlan(123, Fraction(1, 2), Fraction(1, 2**64), 2, prefix(1))
    episode = ExogenousEpisode(123, 0, fixture.address.state.kappa,
                               fixture.address.z, CANARY_TAPE)
    assert not is_explore(episode.coin(0), protocol.epsilon)
    trace = episode_rollout(learner, episode, protocol=protocol, q_reference=REFERENCE)
    assert trace.steps[0].a_cmd == fixture.address.a
    edits = sweep_edits(learner, trace, episode, protocol=protocol, q_reference=REFERENCE)
    assert edits[0].value == (learner.q_overrides[fixture.address]
                              + 0.5 * (fixture.target_value - learner.q_overrides[fixture.address]))
    learner.apply_transaction(edits, q_reference=REFERENCE)


def test_c1_preserves_the_calibration_and_original_initializer():
    fixture = optimistic_fixture(q_reference=REFERENCE)
    old = baseline_initializer(q_reference=REFERENCE)
    assert dict(old.q_overrides) == {canary_address(): -0.14}
    candidate = fixture.initialize(q_reference=REFERENCE)
    assert fixture.address.a != canary_address().a
    assert dict(candidate.q_overrides) == {fixture.address: fixture.initial_value}
    assert fixture.action(candidate, q_reference=REFERENCE) == fixture.address.a


def test_c1_actual_sweep_restores_behaviour_within_two_greedy_visits():
    fixture = optimistic_fixture(q_reference=REFERENCE)
    learner = fixture.initialize(q_reference=REFERENCE)
    for _ in range(2):
        if fixture.policy_restored(learner, q_reference=REFERENCE):
            break
        matching_greedy_update(learner, fixture)
    assert fixture.policy_restored(learner, q_reference=REFERENCE)
    # Exact canonicalisation would reject this successfully repaired policy.
    assert fixture.address in learner.q_overrides
    assert learner.q_overrides[fixture.address] != fixture.target_value


def test_c1_repaired_state_matches_healthy_returns_on_entire_u2_support():
    fixture = optimistic_fixture(q_reference=REFERENCE)
    learner = fixture.initialize(q_reference=REFERENCE)
    for _ in range(2):
        if not fixture.policy_restored(learner, q_reference=REFERENCE):
            matching_greedy_update(learner, fixture)
    healthy = LearnerPersistentState()
    bank = prefix(5760)
    assert len(bank) == 5760
    for u in bank:
        args = dict(kappa=u.kappa, tape=u.tape, base_option=u.base_option,
                    q_reference=REFERENCE)
        assert learned_rollout(learner, **args).return_value == learned_rollout(healthy, **args).return_value


@pytest.mark.parametrize("kind", ["healthy", "no_learning"])
def test_c1_negative_controls_cannot_supply_recovery_evidence(kind):
    fixture = optimistic_fixture(q_reference=REFERENCE)
    learner = LearnerPersistentState() if kind == "healthy" else fixture.initialize(q_reference=REFERENCE)
    original = dict(learner.q_overrides)
    u = prefix(96)[2]  # use all 96 below so the defect's own cell is also included
    vectors = []
    for _ in range(2):
        vectors.append(tuple(learned_rollout(learner, kappa=u.kappa, tape=u.tape,
                                             base_option=u.base_option, q_reference=REFERENCE).return_value
                             for u in prefix(96)))
    assert vectors[0] == vectors[1]
    assert dict(learner.q_overrides) == original
    assert fixture.policy_restored(learner, q_reference=REFERENCE) == (kind == "healthy")
