from rflnext.env import HORIZON
from rflnext.noise import NoiseTape


def test_tape_is_deterministic():
    a = NoiseTape.from_seed(1234, episodes=16, horizon=HORIZON, p_hazard=0.25)
    b = NoiseTape.from_seed(1234, episodes=16, horizon=HORIZON, p_hazard=0.25)
    assert a.digest() == b.digest()


def test_tape_differs_across_seeds():
    a = NoiseTape.from_seed(1, episodes=16, horizon=HORIZON, p_hazard=0.25)
    b = NoiseTape.from_seed(2, episodes=16, horizon=HORIZON, p_hazard=0.25)
    assert a.digest() != b.digest()


def test_shapes_and_ranges():
    t = NoiseTape.from_seed(7, episodes=32, horizon=HORIZON, p_hazard=0.25)
    assert len(t.goal_lane) == 32
    assert len(t.hazard) == 32
    assert len(t.explore_u) == 32
    assert len(t.tie_u) == 32
    assert set(t.goal_lane) <= {0, 1}
    assert set(t.hazard) <= {0, 1}
    # One draw for the high-level decision at t=0, plus one per low-level step.
    for row in t.explore_u:
        assert len(row) == HORIZON + 1
        assert all(0.0 <= v < 1.0 for v in row)
    for row in t.tie_u:
        assert len(row) == HORIZON + 1
        assert all(0.0 <= v < 1.0 for v in row)


def test_explore_and_tie_streams_are_independent():
    t = NoiseTape.from_seed(3, episodes=8, horizon=HORIZON, p_hazard=0.25)
    assert t.explore_u != t.tie_u


def test_hazard_rate_is_close_to_target():
    t = NoiseTape.from_seed(99, episodes=20000, horizon=HORIZON, p_hazard=0.25)
    rate = sum(t.hazard) / len(t.hazard)
    assert abs(rate - 0.25) < 0.02
