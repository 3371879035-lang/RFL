import pytest

from rflnext.metrics import (
    episodes_to_90,
    final_success,
    n_negative_td,
    success_auc,
    visited_state_coverage,
)


def test_success_auc_is_trapezoidal():
    assert success_auc([0.5, 0.5, 0.5], [0, 10, 20]) == pytest.approx(0.5)


def test_success_auc_rising():
    assert success_auc([0.0, 1.0], [0, 10]) == pytest.approx(0.5)


def test_success_auc_single_checkpoint():
    assert success_auc([0.25], [0]) == pytest.approx(0.25)


def test_episodes_to_90_none_when_never_reached():
    assert episodes_to_90([0.1, 0.2, 0.3], [0, 10, 20], threshold=0.9) is None


def test_episodes_to_90_returns_first_crossing():
    assert episodes_to_90([0.1, 0.95, 0.99], [0, 10, 20], threshold=0.9) == 10


def test_final_success():
    assert final_success([0.1, 0.2, 0.7]) == pytest.approx(0.7)


def test_coverage_counts_distinct_states():
    assert visited_state_coverage([(0, 0, 0), (0, 0, 0), (1, 0, 0)]) == 2


def test_n_negative_td_sums_records():
    class R:
        def __init__(self, v):
            self.n_negative_td = v

    assert n_negative_td([R(1), R(0), R(3)]) == 4
