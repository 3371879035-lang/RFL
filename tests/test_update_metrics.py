import pytest

from rflcc.metrics import compute_update_metrics, update_precision, update_recall, update_f1, actual_wrong_update_rate
from rflcc.router import AppliedUpdate


def test_actual_update_fidelity():
    rec = [AppliedUpdate("H", 0, 0, 0.0, -0.1, -0.1)]
    oracle = {"H": 1.0, "L": 0.0, "E": 0.0}
    assert update_precision(rec, oracle) == pytest.approx(1.0)
    assert update_recall(rec, oracle) == pytest.approx(1.0)
    assert update_f1(rec, oracle) == pytest.approx(1.0)
    low = [AppliedUpdate("L", (0,), 1, 0.0, -0.1, -0.1)]
    assert update_precision(low, oracle) == pytest.approx(0.0)


def test_no_internal_update_is_f1_zero_when_oracle_requires_one():
    oracle = {"H": 1.0, "L": 0.0, "E": 0.0}
    metrics = compute_update_metrics([], oracle, alpha_diag=0.1)
    assert metrics.precision is None
    assert metrics.recall == pytest.approx(0.0)
    assert metrics.f1 == pytest.approx(0.0)


def test_e_only_budget_keeps_recall_and_f1_undefined():
    metrics = compute_update_metrics([], {"H": 0.0, "L": 0.0, "E": 1.0}, alpha_diag=0.1)
    assert metrics.precision is None
    assert metrics.recall is None
    assert metrics.f1 is None
