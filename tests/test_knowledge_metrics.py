import pytest

from rflcc.knowledge import (
    InvalidKnowledgeProbe,
    correct_margin,
    correct_knowledge_damage,
    recovery_episode,
    require_initial_correct_margin,
    wrong_knowledge_reinforcement,
)


def test_margin_damage_and_reinforcement():
    before = {"safe": 0.60, "unsafe": 0.0}
    after = {"safe": 0.50, "unsafe": 0.0}
    assert correct_margin(before, "safe") == pytest.approx(0.60)
    assert correct_knowledge_damage(before, after, "safe") == pytest.approx(1 / 6)
    assert wrong_knowledge_reinforcement(before, {"safe": 0.60, "unsafe": 0.10}, "safe", "unsafe") == pytest.approx(1 / 6)


def test_wkr_uses_correct_margin_for_multiaction_row():
    before = {0: 0.80, 1: 0.20, 2: 0.10}
    after = {0: 0.70, 1: 0.50, 2: 0.10}
    # Wrong advantage changes from -0.60 to -0.20.  Its denominator remains
    # the initial correct margin (0.60), not the wrong item's zero advantage.
    assert wrong_knowledge_reinforcement(before, after, 0, 1) == pytest.approx(2 / 3)


@pytest.mark.parametrize("values", [{0: 0.0, 1: 0.0}, {0: -0.2, 1: 0.0}])
def test_nonpositive_or_subthreshold_correct_margin_rejects_probe(values):
    with pytest.raises(InvalidKnowledgeProbe):
        require_initial_correct_margin(values, 0, minimum=0.60)


def test_recovery_is_right_censored():
    assert recovery_episode([0.2, 0.4, 0.55, 0.6, 0.6], initial_margin=0.6, fraction=0.95, consecutive=2, checkpoint_interval=10, horizon=50) == 30
    assert recovery_episode([0.1, 0.2], initial_margin=0.6, fraction=0.95, consecutive=2, checkpoint_interval=10, horizon=50) == 51
