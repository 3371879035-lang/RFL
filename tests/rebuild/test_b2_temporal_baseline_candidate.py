"""C3 structural selector and exact learner/partition equivalence."""
from fractions import Fraction
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from f0_temporal_static import selection, layer_edits
from f0_temporal_construction import TemporalLearner
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.training import BaselineAcquisitionPlan, ExogenousEpisode, episode_rollout, sweep_edits
from rfl_rebuild.env.kernel import SemanticTape
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference

REFERENCE = reference_view_from(solve_reference())


def test_earliest_observable_layer_is_selected_without_a_training_stream(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("seedless selector attempted to draw a training stream")
    monkeypatch.setattr(ExogenousEpisode, "derive", forbidden)
    result = selection(REFERENCE)
    chosen = result["selected_layer"]
    assert chosen is not None
    assert result["layers_inspected"][-1]["observable"]
    assert all(not r["observable"] for r in result["layers_inspected"][:-1])
    assert len(result["layers_inspected"]) == chosen + 1


def test_full_and_partitioned_states_remain_equal_under_repeated_updates():
    layer = selection(REFERENCE)["selected_layer"]
    full = LearnerPersistentState()
    full.apply_transaction(layer_edits(REFERENCE, layer), q_reference=REFERENCE)
    parts = TemporalLearner(REFERENCE, layer=layer)
    assert parts.materialized_overrides() == dict(full.q_overrides)
    protocol = BaselineAcquisitionPlan(123, Fraction(1, 2), Fraction(1, 10), 96, prefix(1))
    for e, cell in enumerate(tuple(parts.parts) * 2):
        kappa, phase, option = cell
        xi = ExogenousEpisode(123, e, kappa, option, SemanticTape(phase, e % 2, e % 60))
        trace = episode_rollout(full, xi, protocol=protocol, q_reference=REFERENCE)
        edits = sweep_edits(full, trace, xi, protocol=protocol, q_reference=REFERENCE)
        full.apply_transaction(edits, q_reference=REFERENCE)
        parts.train(xi, protocol=protocol)
        assert parts.materialized_overrides() == dict(full.q_overrides)
    bank = prefix(1024)
    direct = tuple(learned_rollout(full, kappa=u.kappa, tape=u.tape, base_option=u.base_option,
                                  q_reference=REFERENCE).return_value for u in bank)
    assert parts.bank_values(bank) == direct
    parts.validate_cache(bank)
