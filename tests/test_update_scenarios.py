from rflcc.update_scenarios import make_high_protection, make_low_protection, make_environment_mixed, make_hl_mixed, is_high_protection, is_low_protection, is_environment_mixed, is_hl_mixed
from rflcc.knowledge import correct_margin


def test_acceptance_filtered_families():
    for maker, pred in ((make_high_protection, is_high_protection), (make_low_protection, is_low_protection), (make_environment_mixed, is_environment_mixed), (make_hl_mixed, is_hl_mixed)):
        s = maker(1, seed=7, max_attempts=300)[0]
        assert pred(s.oracle_r)
        assert s.trace.noise_tape is not None
        assert correct_margin(s.q_snapshot.high[0], s.trace.option) == 0.60


def test_hl_mixed_preserves_proportional_responsibility():
    s = make_hl_mixed(1, seed=7, max_attempts=100)[0]
    assert s.oracle_r["H"] > 0.2 and s.oracle_r["L"] > 0.2
    assert s.oracle_r["H"] + s.oracle_r["L"] >= 0.7


def test_update_scenarios_are_seed_deterministic():
    for maker in (make_high_protection, make_low_protection, make_environment_mixed, make_hl_mixed):
        first = maker(2, seed=1234, max_attempts=300)
        second = maker(2, seed=1234, max_attempts=300)
        assert [s.scenario_id for s in first] == [s.scenario_id for s in second]
        assert [s.oracle_r for s in first] == [s.oracle_r for s in second]
        assert [s.q_snapshot.deep_hash() for s in first] == [s.q_snapshot.deep_hash() for s in second]
        assert [s.trace.noise_tape.sha256() for s in first] == [s.trace.noise_tape.sha256() for s in second]
