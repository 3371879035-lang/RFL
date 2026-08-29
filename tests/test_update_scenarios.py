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
