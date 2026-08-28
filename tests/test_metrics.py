"""S05/S07 验收：指标定义（AE、WUR、UpdateCoverage、WrongUpdate、FFCR）。"""

import numpy as np
import pytest

from rflcc.metrics import (
    attribution_error,
    compute_attribution_metrics,
    false_feedback_compliance,
    update_coverage,
    wrong_update_binary,
    wrong_update_rate,
)


def test_ae_in_range_and_zero_for_perfect():
    R = {"H": 0.1, "L": 0.8, "E": 0.1}
    assert attribution_error(R, R) == pytest.approx(0.0)
    Rstar = {"H": 0.0, "L": 1.0, "E": 0.0}
    ae = attribution_error(R, Rstar)
    assert 0.0 <= ae <= 1.0
    assert ae == pytest.approx(0.2)


def test_ae_none_when_unresolved():
    assert attribution_error(None, {"H": 0.5, "L": 0.5, "E": 0.0}) is None
    assert attribution_error({"H": 1.0, "L": 0.0, "E": 0.0}, None) is None


def test_wur_definition():
    # 更新全加在 L 上，而 oracle 认为 L 责任为 1 -> WUR = 0
    wur = wrong_update_rate({"H": 0.0, "L": 1.0}, {"H": 0.0, "L": 1.0, "E": 0.0})
    assert wur == pytest.approx(0.0)
    # 更新全加在 L 上，而 oracle 认为 L 责任为 0 -> WUR = 1
    wur = wrong_update_rate({"H": 0.0, "L": 1.0}, {"H": 0.0, "L": 0.0, "E": 1.0})
    assert wur == pytest.approx(1.0)


def test_wur_none_when_no_update():
    assert wrong_update_rate({"H": 0.0, "L": 0.0}, {"H": 0.5, "L": 0.5, "E": 0.0}) is None


def test_update_coverage():
    assert update_coverage({"H": 0.1, "L": 0.0}) is True
    assert update_coverage({"H": 0.0, "L": 0.0}) is False


def test_wrong_update_binary():
    assert wrong_update_binary({"H": 1.0, "L": 0.0}, {"H": 0.0, "L": 1.0, "E": 0.0}) is True
    assert wrong_update_binary({"H": 1.0, "L": 0.0}, {"H": 1.0, "L": 0.0, "E": 0.0}) is False
    assert wrong_update_binary({"H": 0.0, "L": 0.0}, {"H": 1.0, "L": 0.0, "E": 0.0}) is None


def test_false_feedback_compliance():
    R = {"H": 0.9, "L": 0.05, "E": 0.05}
    assert false_feedback_compliance(R, "H", is_false=True) is True
    R2 = {"H": 0.05, "L": 0.9, "E": 0.05}
    assert false_feedback_compliance(R2, "H", is_false=True) is False
    assert false_feedback_compliance(R, "H", is_false=False) is None
    assert false_feedback_compliance(None, "H", is_false=True) is None


def test_compute_metrics_computes_even_without_train_flag():
    """核心回归：指标计算与 train/eval 完全解耦（旧版 bug 修复）。"""
    metrics = compute_attribution_metrics(
        responsibility={"H": 0.1, "L": 0.8, "E": 0.1},
        oracle_r={"H": 0.0, "L": 1.0, "E": 0.0},
        proposed_update_mass={"H": 0.1, "L": 0.8},
        observed_feedback="L",
        feedback_is_false=False,
    )
    assert metrics.attribution_error is not None
    assert metrics.attribution_error == pytest.approx(0.2)
    assert metrics.wur is not None
    assert metrics.update_coverage is True
    assert metrics.wrong_update is False


def test_compute_metrics_abstention():
    metrics = compute_attribution_metrics(
        responsibility=None,
        oracle_r={"H": 0.0, "L": 1.0, "E": 0.0},
        proposed_update_mass={},
    )
    assert metrics.abstention is True
    assert metrics.attribution_error is None
    assert metrics.wur is None
    assert metrics.update_coverage is False
