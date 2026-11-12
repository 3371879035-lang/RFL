"""C2 equivalence and negative controls; no scientific seeds or selector calls."""
from fractions import Fraction
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.training import (BaselineAcquisitionPlan, ExogenousEpisode,
                                     episode_rollout, sweep_edits)
from rfl_rebuild.b2.utility import recovery_time
from rfl_rebuild.b2.zero_baseline_candidate import (PartitionedZeroLearner, envelope,
                                                   zero_initializer)
from rfl_rebuild.env.kernel import SemanticTape
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState, QAddress
from rfl_rebuild.solve.dp import solve_reference

REFERENCE = reference_view_from(solve_reference())


def test_every_legal_q_address_really_starts_at_zero():
    full = zero_initializer(q_reference=REFERENCE)
    for (s, z, m), row in REFERENCE.rows.items():
        for a in row:
            q = QAddress(s, z, m, a)
            assert full.q_overrides.get(q, REFERENCE.value(q)) == 0.0
    assert not full.decision_overrides and not full.process_overrides and not full.controller_overrides
    assert envelope(REFERENCE)["cap"] == 6912


def test_partition_updates_match_full_learner_across_every_cell():
    full = zero_initializer(q_reference=REFERENCE)
    parts = PartitionedZeroLearner(REFERENCE)
    assert parts.materialized_overrides() == dict(full.q_overrides)
    plan = BaselineAcquisitionPlan(123, Fraction(1, 2), Fraction(1, 10), 48, prefix(1))
    # Hand-constructed exogenous cases exhaust cells; this is not an acquired run.
    for e, (kappa, phase, option) in enumerate(parts.parts):
        xi = ExogenousEpisode(123, e, kappa, option, SemanticTape(phase, e % 2, e % 60))
        trace = episode_rollout(full, xi, protocol=plan, q_reference=REFERENCE)
        edits = sweep_edits(full, trace, xi, protocol=plan, q_reference=REFERENCE)
        full.apply_transaction(edits, q_reference=REFERENCE)
        parts.train(xi, protocol=plan)
        assert parts.materialized_overrides() == dict(full.q_overrides)
    bank = prefix(100)
    expected = tuple(learned_rollout(full, kappa=u.kappa, tape=u.tape,
                                    base_option=u.base_option, q_reference=REFERENCE).return_value
                     for u in bank)
    assert parts.bank_values(bank) == expected
    parts.validate_cache(bank)


def test_all_tape_variants_preserve_grouped_evaluation_and_no_learning_is_not_recovery():
    parts = PartitionedZeroLearner(REFERENCE)
    bank = prefix(5760)
    before = parts.materialized_overrides()
    parts.validate_cache(bank)
    healthy = LearnerPersistentState()
    healthy_values = tuple(learned_rollout(healthy, kappa=u.kappa, tape=u.tape,
                                          base_option=u.base_option, q_reference=REFERENCE).return_value
                           for u in bank)
    for n in (100, 256, 512, 1024, 5760):
        level = mean(parts.bank_values(bank[:n]))
        healthy_level = mean(healthy_values[:n])
        assert level < .95 * healthy_level
        assert recovery_time((level,) * 3, (0, 1, 2), pre_level=healthy_level, t_max=2) is None
    assert before == parts.materialized_overrides()


def test_stale_cache_is_rejected():
    parts = PartitionedZeroLearner(REFERENCE)
    first = next(iter(parts._returns))
    parts._returns[first] += 1.0
    with pytest.raises(ProtocolError, match="return cache"):
        parts.validate_cache(prefix(1))


def test_cross_cell_edit_is_rejected_before_write(monkeypatch):
    import rfl_rebuild.b2.zero_baseline_candidate as candidate
    from rfl_rebuild.learner.store import Edit, Q
    parts = PartitionedZeroLearner(REFERENCE)
    before = parts.materialized_overrides()
    a = next(a for a in before if a.state.kappa == 1)
    monkeypatch.setattr(candidate, "sweep_edits", lambda *args, **kw: (Edit(Q, a, 1.0),))
    xi = ExogenousEpisode(123, 0, 0, 0, SemanticTape(0, 0, 0))
    plan = BaselineAcquisitionPlan(123, Fraction(1, 2), Fraction(1, 10), 2, prefix(1))
    with pytest.raises(ProtocolError, match="crossed"):
        parts.train(xi, protocol=plan)
    assert before == parts.materialized_overrides()
