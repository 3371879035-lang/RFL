r"""A91 §79 — the training-time instrument: the keyed draw generator, the episode, the sweep, the curve.

$$\boxed{\text{kernel step index} \;\neq\; \text{training episode index}}$$

Every test here is written so that the *wrong* implementation fails it, because the two mistakes this
module exists to prevent are both legal Python: reading a `StepResult`'s post-step state as if it were the
context the step acted from, and starting the episode in the **proposal** option instead of the one the
learner's process commit put **in force**. Both are exercised against a fixture that really constructs
$Z_P^{\text{fire}} = 1$ (`trace.option_in_force != trace.base_option`), not against a healthy learner where
the two coincide and the assertion would be vacuous.

The exploration tests check the two properties the frozen integer rules exist for: the coin is an exact
rational comparison, and the action index is *exactly* uniform over an admissible set whose size need not
divide $2^{64}$.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fractions import Fraction  # noqa: E402

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2 import training  # noqa: E402
from rfl_rebuild.b2.training import (  # noqa: E402
    M64,
    TAGS,
    Curve,
    ExogenousEpisode,
    TrainingProtocol,
    effective_value,
    is_explore,
    key,
    mix,
    pre_level,
    sweep_edits,
    train_curve,
    u64,
    uniform_action,
    visited_order,
)
from rfl_rebuild.b2.unaffected import scene_domain  # noqa: E402
from rfl_rebuild.env.kernel import START, State, initial_control, option_ids  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import PROCESS, Q, Edit, LearnerPersistentState, QAddress  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

REFERENCE = reference_view_from(solve_reference())
SAMPLE = scene_domain()[:4]
#: (seed, episode) chosen because its proposal is 0, which the P override below redirects to 1.
SEED, EPISODE = 7, 3


def _protocol(**overrides) -> TrainingProtocol:
    fields = dict(seed=SEED, alpha=Fraction(1, 2), epsilon=Fraction(1, 4), cap=3,
                  grid=(0, 1, 2, 3), evaluation_sample=SAMPLE)
    fields.update(overrides)
    return TrainingProtocol(**fields)


def _p_override_learner() -> LearnerPersistentState:
    r"""A learner whose process store redirects option 0 to option 1, i.e. $C_P^{L}(0) = 1$.

    This is the fixture the review demanded: without it, `initial_control(proposal)` and
    `initial_control(option_in_force)` agree and the frozen reconstruction cannot be told from the bug.
    """
    learner = LearnerPersistentState()
    learner.apply_transaction((Edit(store=PROCESS, address=0, value=1),), q_reference=REFERENCE)
    return learner


# --- the keyed generator ---------------------------------------------------------------------------

def test_1_u64_is_the_mask_not_a_modulus():
    assert u64(M64 + 5) == 4
    assert u64(-1) == M64
    assert all(u64(x) < (1 << 64) for x in (0, 1, M64, 1 << 70))


def test_2_mix_matches_an_independent_transcription_of_splitmix64():
    def reference_finalizer(x: int) -> int:
        z = x & M64
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & M64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & M64
        return (z ^ (z >> 31)) & M64

    assert mix(0) == 0
    for x in (0, 1, 2, 12345, M64, 1 << 40):
        assert mix(x) == reference_finalizer(x), x


def test_3_key_is_deterministic_and_domain_separated_by_tag():
    same = [key(SEED, EPISODE, TAGS["tape"]) for _ in range(3)]
    assert len(set(same)) == 1
    draws = {name: key(SEED, EPISODE, tag) for name, tag in TAGS.items()}
    assert len(set(draws.values())) == len(TAGS), draws
    assert all(0 <= v <= M64 for v in draws.values())


def test_4_an_episode_tuple_is_derived_deterministically_within_the_frozen_domains():
    first = ExogenousEpisode.derive(SEED, EPISODE)
    second = ExogenousEpisode.derive(SEED, EPISODE)
    assert first == second
    assert first.kappa in (0, 1)
    assert first.proposal in option_ids()
    assert first.tape is not None
    with pytest.raises(ProtocolError, match="non-negative"):
        ExogenousEpisode.derive(SEED, -1)


def test_5_a_different_seed_or_episode_moves_the_stream():
    base = ExogenousEpisode.derive(SEED, EPISODE)
    assert ExogenousEpisode.derive(SEED + 1, EPISODE) != base
    assert ExogenousEpisode.derive(SEED, EPISODE + 1) != base


def test_6_chi_is_keyed_by_coordinate_and_rejects_a_bad_coordinate():
    episode = ExogenousEpisode.derive(SEED, EPISODE)
    assert episode.chi(0, 0, 0) != episode.chi(1, 0, 0)
    assert episode.chi(0, 0, 0) != episode.chi(0, 1, 0)
    assert episode.chi(0, 1, 0) != episode.chi(0, 1, 1)
    with pytest.raises(ProtocolError, match="outside the frozen domain"):
        episode.chi(0, 2, 0)


# --- the exploration rules -------------------------------------------------------------------------

def test_7_the_coin_is_an_exact_rational_comparison():
    half = Fraction(1, 2)
    assert is_explore((1 << 63) - 1, half) is True      # (2^63 - 1) * 2 < 2^64
    assert is_explore(1 << 63, half) is False           # exactly on the boundary: strict means no
    assert is_explore(0, Fraction(1, 1)) is True        # eps = 1 is always-explore
    assert is_explore(M64, Fraction(1, 1)) is True


def test_8_the_exploration_probability_must_be_a_rational_in_range():
    with pytest.raises(ProtocolError, match="exact rational"):
        is_explore(1, 0.5)  # a float is not the frozen object
    with pytest.raises(ProtocolError, match="0 < eps"):
        is_explore(1, Fraction(0, 1))
    with pytest.raises(ProtocolError, match="0 < eps"):
        is_explore(1, Fraction(3, 2))


def test_9_uniform_action_demands_the_frozen_ordering_and_a_non_empty_set():
    episode = ExogenousEpisode.derive(SEED, EPISODE)
    with pytest.raises(ProtocolError, match="ascending action-id order"):
        uniform_action(episode, 0, (3, 1))
    with pytest.raises(ProtocolError, match="empty"):
        uniform_action(episode, 0, ())


def test_10_uniform_action_has_exact_pre_images_and_uses_rejection(monkeypatch):
    r"""Exactness is arithmetic plus a consecutive prefix, so it is tested without sampling luck.

    Two facts make the rule exactly uniform: $2^{64}$ is *not* a multiple of $n$ (which is why flooring a
    real draw is biased), and the rejection bound $L = 2^{64} - (2^{64} \bmod n)$ *is*, so every action has
    exactly $L/n$ pre-images. Over a consecutive prefix of $[0, L)$ the counts can therefore differ by at
    most one --- deterministically, not on average.
    """
    episode = ExogenousEpisode.derive(SEED, EPISODE)
    n = 3
    assert (1 << 64) % n != 0, "the bias this rule removes only exists because 2^64 is not a multiple of n"
    limit = (1 << 64) - ((1 << 64) % n)
    assert limit % n == 0 and limit // n * n == limit

    draws = {"value": 0}

    def counting_chi(self, i, j, c):
        assert j == 1, "the index draw is coordinate j = 1"
        assert c == 0, "an accepted first draw must not need a second"
        value = draws["value"]
        draws["value"] += 1
        return value

    monkeypatch.setattr(ExogenousEpisode, "chi", counting_chi)
    counts = {1: 0, 2: 0, 3: 0}
    for _ in range(30000):
        counts[uniform_action(episode, 0, (1, 2, 3))] += 1
    assert max(counts.values()) - min(counts.values()) <= 1, f"the index draw is not balanced: {counts}"
    assert sum(counts.values()) == 30000


def test_10b_rejection_is_used_and_bounded(monkeypatch):
    episode = ExogenousEpisode.derive(SEED, EPISODE)
    n = 3
    limit = (1 << 64) - ((1 << 64) % n)
    seen = []

    def rejecting_chi(self, i, j, c):
        seen.append(c)
        return limit if c == 0 else 0  # the first draw is outside [0, L), the second is inside

    monkeypatch.setattr(ExogenousEpisode, "chi", rejecting_chi)
    assert uniform_action(episode, 0, (1, 2, 3)) == 1  # 0 % 3 -> the first sorted action
    assert seen == [0, 1], "the rejected draw must be retried at the next counter"

    # The frozen bound is 2**32, which no test can exhaust; the *rule* is what is tested, at a bound small
    # enough to reach, so that "fails closed" is observed rather than assumed.
    monkeypatch.setattr(training, "MAX_REJECTION", 3)

    def always_rejected(self, i, j, c):
        return limit

    monkeypatch.setattr(ExogenousEpisode, "chi", always_rejected)
    with pytest.raises(ProtocolError, match="exhausted 2\\*\\*32 draws"):
        uniform_action(episode, 0, (1, 2, 3))


def test_10c_the_real_generator_is_not_detectably_biased():
    """A coarse sanity check on the real keyed stream, with a bound a hash would have to be broken to hit."""
    episode = ExogenousEpisode.derive(SEED, EPISODE)
    counts = {1: 0, 2: 0, 3: 0}
    for i in range(30000):
        counts[uniform_action(episode, i, (1, 2, 3))] += 1
    mean = sum(counts.values()) / 3
    assert all(abs(count - mean) <= 0.02 * mean for count in counts.values()), counts


# --- the pre-step reconstruction -------------------------------------------------------------------

def test_11_the_walk_reconstructs_the_pre_step_context():
    from rfl_rebuild.b2.training import episode_rollout

    episode = ExogenousEpisode.derive(SEED, EPISODE)
    trace = episode_rollout(LearnerPersistentState(), episode, protocol=_protocol(), q_reference=REFERENCE)
    walk = visited_order(trace, kappa=episode.kappa, phi=episode.tape.phase)
    state0, control0, _ = walk[0]
    assert (state0.x, state0.y, state0.t, state0.kappa, state0.phi) == \
        (START[0], START[1], 0, episode.kappa, episode.tape.phase), \
        "the walk must start at the episode's initial context"
    assert control0.z == trace.option_in_force, "the walk must start in the option in force"
    # every later context is the previous step's post-step state/control, never its own
    for previous, current in zip(walk, walk[1:]):
        assert (current[0].x, current[0].y, current[0].t) == \
            (previous[2].state.x, previous[2].state.y, previous[2].state.t), \
            "a context must be the PREVIOUS step's post state"
        assert (current[1].z, current[1].m) == (previous[2].control.z, previous[2].control.m), \
            "a context must be the PREVIOUS step's post control"
    assert visited_order(trace.__class__(steps=(), outcome=None, control=trace.control, mask=trace.mask,
                                         interventions=trace.interventions, base_option=0,
                                         option_in_force=0), kappa=0, phi=0) == ()


def test_12_the_fixture_really_fires_z_p_and_the_walk_follows_the_in_force_option():
    from rfl_rebuild.b2.training import episode_rollout

    episode = ExogenousEpisode.derive(SEED, EPISODE)
    assert episode.proposal == 0, "the fixture depends on this proposal"
    learner = _p_override_learner()
    trace = episode_rollout(learner, episode, protocol=_protocol(), q_reference=REFERENCE)
    assert trace.base_option == 0 and trace.option_in_force == 1, "the fixture did not fire"
    walk = visited_order(trace, kappa=episode.kappa, phi=episode.tape.phase)
    assert (walk[0][1].z, walk[0][1].m) == (1, 0), "the walk must start in the option in force"
    assert walk[0][1].z != trace.base_option, "starting in the proposal is the defect this test kills"


# --- the sweep -------------------------------------------------------------------------------------

def test_13_the_sweep_writes_q_only_and_one_edit_per_visited_address():
    from rfl_rebuild.b2.training import episode_rollout

    episode = ExogenousEpisode.derive(SEED, EPISODE)
    learner = LearnerPersistentState()
    trace = episode_rollout(learner, episode, protocol=_protocol(), q_reference=REFERENCE)
    edits = sweep_edits(learner, trace, episode, protocol=_protocol(), q_reference=REFERENCE)
    assert edits, "a 12-step episode visits addresses"
    assert all(edit.store == Q for edit in edits)
    addresses = [edit.address for edit in edits]
    assert len(set(addresses)) == len(addresses), "one edit per address, never a repeated key"
    assert len(edits) <= len(trace.steps)


def test_14_the_effective_read_falls_back_to_the_reference():
    from rfl_rebuild.b2.training import episode_rollout

    episode = ExogenousEpisode.derive(SEED, EPISODE)
    trace = episode_rollout(LearnerPersistentState(), episode, protocol=_protocol(), q_reference=REFERENCE)
    walk = visited_order(trace, kappa=episode.kappa, phi=episode.tape.phase)
    state0, control0, result0 = walk[0]
    address = QAddress(state=state0, z=control0.z, m=control0.m, a=result0.a_cmd)
    assert effective_value({}, REFERENCE, address) == REFERENCE.value(address)
    assert effective_value({address: 1.5}, REFERENCE, address) == 1.5


# --- the curve -------------------------------------------------------------------------------------

def test_15_a_healthy_learner_neither_moves_nor_gains_overrides():
    """The reference is already the fixed point, so canonicalisation deletes every write-back."""
    learner = LearnerPersistentState()
    curve = train_curve(learner, protocol=_protocol(), q_reference=REFERENCE)
    assert learner.healthy is True
    assert dict(learner.q_overrides) == {}
    assert curve.values[0] == curve.pre_level
    assert all(value == pytest.approx(curve.pre_level) for value in curve.values)


def test_16_a_wrong_override_is_corrected_and_canonicalised_away():
    from rfl_rebuild.b2.training import episode_rollout

    protocol = _protocol(alpha=Fraction(1, 1), epsilon=Fraction(1, 1), cap=3, grid=(0, 1, 2, 3))
    episode = ExogenousEpisode.derive(SEED, 0)
    healthy = LearnerPersistentState()
    trace = episode_rollout(healthy, episode, protocol=protocol, q_reference=REFERENCE)
    walk = visited_order(trace, kappa=episode.kappa, phi=episode.tape.phase)
    state0, control0, result0 = walk[0]
    address = QAddress(state=state0, z=control0.z, m=control0.m, a=result0.a_cmd)

    broken = LearnerPersistentState()
    broken.apply_transaction((Edit(store=Q, address=address, value=-5.0),), q_reference=REFERENCE)
    assert dict(broken.q_overrides) and broken.healthy is False

    train_curve(broken, protocol=protocol, q_reference=REFERENCE)
    assert broken.healthy is True, f"the wrong override survived: {dict(broken.q_overrides)}"


def test_17_the_curve_is_deterministic_and_spans_the_horizon():
    first = train_curve(LearnerPersistentState(), protocol=_protocol(), q_reference=REFERENCE)
    second = train_curve(LearnerPersistentState(), protocol=_protocol(), q_reference=REFERENCE)
    assert first == second
    assert first.episodes[0] == 0 and first.episodes[-1] == first.t_max == 3
    assert len(first.values) == len(first.episodes)


def test_18_evaluation_makes_zero_calls_to_the_training_draw_generator(monkeypatch):
    """A91 §79.6's gate: the read-only path cannot consume the keyed stream, because it never asks."""
    expected = pre_level(SAMPLE, q_reference=REFERENCE)

    def explode(*_args, **_kwargs):  # pragma: no cover - only reached if evaluation draws
        raise AssertionError("the checkpoint evaluation consumed the training draw generator")

    monkeypatch.setattr(ExogenousEpisode, "chi", explode)
    assert pre_level(SAMPLE, q_reference=REFERENCE) == pytest.approx(expected)


def test_19_training_leaves_the_non_q_stores_alone():
    r"""Ordinary training writes $Q_D^{L}$ only, and the observable of that is the process commit.

    Note what is *not* asserted: `healthy`. Training a learner that is not at the reference's fixed point
    legitimately leaves $Q$ overrides behind, so "healthy" would confound a correct $Q$ write with a wrong
    process write. The process store's survival is the claim, and the $P$ commit still firing is how it is
    observed.
    """
    from rfl_rebuild.b2.training import episode_rollout

    learner = _p_override_learner()
    episode = ExogenousEpisode.derive(SEED, EPISODE)
    before = episode_rollout(learner, episode, protocol=_protocol(), q_reference=REFERENCE)
    assert before.option_in_force == 1, "the fixture must fire before training"

    train_curve(learner, protocol=_protocol(), q_reference=REFERENCE)

    after = episode_rollout(learner, episode, protocol=_protocol(), q_reference=REFERENCE)
    assert after.option_in_force == 1 and after.base_option == 0, (
        "the process override did not survive training; ordinary training must write Q only")


# --- the declared inputs ---------------------------------------------------------------------------

def test_20_the_protocol_refuses_constants_outside_the_frozen_domains():
    with pytest.raises(ProtocolError, match="0 < alpha"):
        _protocol(alpha=Fraction(0, 1))
    with pytest.raises(ProtocolError, match="exact rational"):
        _protocol(epsilon=0.25)
    with pytest.raises(ProtocolError, match="0 < eps"):
        _protocol(epsilon=Fraction(0, 1))


def test_21_the_protocol_enforces_the_a84_span_and_the_k_floor():
    with pytest.raises(ProtocolError, match="at least three"):
        _protocol(cap=1, grid=(0, 1))
    with pytest.raises(ProtocolError, match="span the horizon"):
        _protocol(cap=4, grid=(0, 1, 2, 3))
    with pytest.raises(ProtocolError, match="strictly increasing"):
        _protocol(cap=3, grid=(0, 2, 2, 3))
    with pytest.raises(ProtocolError, match="positive integer"):
        _protocol(cap=0, grid=(0,))
    with pytest.raises(ProtocolError, match="evaluation sample is empty"):
        _protocol(evaluation_sample=())


def test_22_a_curve_must_carry_one_value_per_checkpoint_and_span_it():
    with pytest.raises(ProtocolError, match="one value per checkpoint"):
        Curve(values=(1.0,), episodes=(0, 1), pre_level=0.0, t_max=1)
    with pytest.raises(ProtocolError, match="span contract"):
        Curve(values=(1.0, 2.0), episodes=(0, 2), pre_level=0.0, t_max=3)
