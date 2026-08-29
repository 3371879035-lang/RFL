import pytest

from rflcc.metrics import update_precision, update_recall, update_f1, actual_wrong_update_rate
from rflcc.router import AppliedUpdate


def test_actual_update_fidelity():
    rec = [AppliedUpdate("H", 0, 0, 0.0, -0.1, -0.1)]
    oracle = {"H": 1.0, "L": 0.0, "E": 0.0}
    assert update_precision(rec, oracle) == pytest.approx(1.0)
    assert update_recall(rec, oracle) == pytest.approx(1.0)
    assert update_f1(rec, oracle) == pytest.approx(1.0)
    low = [AppliedUpdate("L", (0,), 1, 0.0, -0.1, -0.1)]
    assert update_precision(low, oracle) == pytest.approx(0.0)
