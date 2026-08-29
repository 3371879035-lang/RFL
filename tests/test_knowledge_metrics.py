import pytest

from rflcc.knowledge import correct_margin, correct_knowledge_damage, wrong_knowledge_reinforcement, recovery_episode


def test_margin_damage_and_reinforcement():
    before = {"safe": 0.60, "unsafe": 0.0}
    after = {"safe": 0.50, "unsafe": 0.0}
    assert correct_margin(before, "safe") == pytest.approx(0.60)
    assert correct_knowledge_damage(before, after, "safe") == pytest.approx(1 / 6)
    assert wrong_knowledge_reinforcement(before, {"safe": 0.60, "unsafe": 0.10}, "safe", "unsafe") > 0


def test_recovery_is_right_censored():
    assert recovery_episode([0.2, 0.4, 0.55, 0.6, 0.6], initial_margin=0.6, fraction=0.95, consecutive=2, checkpoint_interval=10, horizon=50) == 30
    assert recovery_episode([0.1, 0.2], initial_margin=0.6, fraction=0.95, consecutive=2, checkpoint_interval=10, horizon=50) == 51
