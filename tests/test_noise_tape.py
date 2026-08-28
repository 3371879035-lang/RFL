"""S01 验收：NoiseTape 确定性、不可变、intervention overlay。"""

import pickle

from rflcc.noise import NoiseTape
from rflcc.types import InterventionSet, OPTION_UPPER, OPTION_LOWER


def test_same_seed_identical_tape():
    t1 = NoiseTape.from_seed(123, horizon=30)
    t2 = NoiseTape.from_seed(123, horizon=30)
    assert t1 == t2
    assert t1.tie_break_u == t2.tie_break_u
    assert t1.dash_u == t2.dash_u
    assert t1.sha256() == t2.sha256()


def test_different_seed_tape():
    t1 = NoiseTape.from_seed(1, horizon=30)
    t2 = NoiseTape.from_seed(2, horizon=30)
    # 统计上几乎必然不同
    assert (t1.tie_break_u != t2.tie_break_u) or (t1.dash_u != t2.dash_u)


def test_tape_is_immutable():
    t = NoiseTape.from_seed(7, horizon=30)
    try:
        t.dash_u = (0.0,)  # type: ignore[misc]
        raise AssertionError("should have raised")
    except (AttributeError, TypeError):
        pass


def test_tape_picklable():
    t = NoiseTape.from_seed(9, horizon=30)
    t2 = pickle.loads(pickle.dumps(t))
    assert t == t2


def test_lane_domain():
    for seed in range(20):
        t = NoiseTape.from_seed(seed, horizon=30)
        assert t.monster_start_lane in (OPTION_UPPER, OPTION_LOWER)


def test_noise_ranges():
    t = NoiseTape.from_seed(42, horizon=30)
    assert all(0.0 <= u < 1.0 for u in t.tie_break_u)
    assert all(0.0 <= u < 1.0 for u in t.dash_u)
    assert len(t.tie_break_u) == 60  # 2 * horizon
    assert len(t.dash_u) == 30


def test_intervention_does_not_mutate_tape():
    t = NoiseTape.from_seed(100, horizon=30)
    t_before = NoiseTape(
        seed=t.seed,
        monster_start_lane=t.monster_start_lane,
        tie_break_u=t.tie_break_u,
        dash_u=t.dash_u,
        horizon=t.horizon,
    )
    inv = InterventionSet(blocked_dash_indices=frozenset({3}))
    assert inv.blocked_dash_indices == frozenset({3})
    assert t == t_before


def test_intervention_overlay_composition():
    inv = InterventionSet()
    inv = inv.with_dash_blocked(2).with_dash_blocked(5).with_option(1)
    assert inv.blocked_dash_indices == frozenset({2, 5})
    assert inv.option_override == 1
    inv2 = inv.with_action(4, 3)
    assert inv2.action_override == {4: 3}
    # 原对象不变
    assert inv.action_override == {}


def test_tape_hash_deterministic():
    t1 = NoiseTape.from_seed(555, horizon=30)
    t2 = NoiseTape.from_seed(555, horizon=30)
    assert t1.sha256() == t2.sha256()
    assert t1.sha256().startswith("sha256:")
