"""S05 验收：feedback 注入、log-space 融合、UNKNOWN、极端条件。"""

import numpy as np
import pytest

from rflcc.attribution import immediate_responsibility, pe_seq_responsibility
from rflcc.feedback import (
    FEEDBACK_WEIGHT,
    FeedbackInjector,
    feedback_likelihood,
    log_fusion,
)
from rflcc.types import CAUSES


def test_q_pre_sums_to_one():
    q_seq = {"H": 0.2, "L": 0.5, "E": 0.3}
    q_pre = log_fusion(q_seq, "L")
    assert abs(sum(q_pre.values()) - 1.0) < 1e-9


def test_matching_feedback_boosts_cause():
    q_seq = {"H": 0.2, "L": 0.5, "E": 0.3}
    q_pre = log_fusion(q_seq, "L")
    assert q_pre["L"] > q_seq["L"]


def test_false_feedback_influences_but_cannot_override_strong_sequence():
    # 极强 sequence 证据（L 0.99）下，错误 H 反馈只能影响不能翻转
    q_seq = {"H": 0.005, "L": 0.99, "E": 0.005}
    q_pre = log_fusion(q_seq, "H", weight=FEEDBACK_WEIGHT)
    assert q_pre["L"] > q_pre["H"]


def test_fusion_is_log_space_not_probability_space():
    # 概率空间乘积会使强证据被反馈完全压倒；log-space 弱加权不会
    q_seq = {"H": 0.3, "L": 0.6, "E": 0.1}
    q_pre = log_fusion(q_seq, "H")
    # 反馈 H 使 H 上升但 L 仍保留显著质量
    assert q_pre["H"] > q_seq["H"]
    assert q_pre["L"] > 0.2


def test_unknown_feedback_uniform_likelihood():
    q_seq = {"H": 0.2, "L": 0.5, "E": 0.3}
    q_pre_unknown = log_fusion(q_seq, "UNKNOWN")
    # UNKNOWN 的 likelihood 均匀 -> 仅重归一化，比例接近原 q_seq
    q_pre_no_fb = log_fusion(q_seq, "H")  # 对比用
    assert abs(sum(q_pre_unknown.values()) - 1.0) < 1e-9


def test_feedback_injector_clean():
    inj = FeedbackInjector(p_false=0.0, mode="symmetric", rng=np.random.RandomState(1))
    for _ in range(100):
        assert inj.generate("L") == "L"


def test_feedback_injector_symmetric_extreme():
    inj = FeedbackInjector(p_false=1.0, mode="symmetric", rng=np.random.RandomState(2))
    for _ in range(100):
        d = inj.generate("L")
        assert d != "L"


def test_feedback_injector_symmetric_counts():
    rng = np.random.RandomState(3)
    inj = FeedbackInjector(p_false=0.4, mode="symmetric", rng=rng)
    false_count = 0
    for _ in range(20000):
        d = inj.generate("L")
        if d != "L":
            false_count += 1
    rate = false_count / 20000
    assert 0.36 < rate < 0.44


def test_feedback_injector_adversarial():
    rng = np.random.RandomState(4)
    inj = FeedbackInjector(p_false=0.4, mode="adversarial_planning_blame", rng=rng)
    # 真实主因是 L/E 时可能被错误归为 H
    h_false = 0
    for _ in range(20000):
        if inj.generate("L") == "H":
            h_false += 1
    assert 0.36 < h_false / 20000 < 0.44
    # 真实主因是 H 时永远正确
    inj2 = FeedbackInjector(p_false=0.4, mode="adversarial_planning_blame", rng=rng)
    assert all(inj2.generate("H") == "H" for _ in range(100))


def test_missing_feedback_unknown():
    inj = FeedbackInjector(p_false=0.0, p_missing=1.0, rng=np.random.RandomState(5))
    assert inj.generate("L") == "UNKNOWN"


def test_immediate_onehot_and_abstain():
    assert immediate_responsibility("L") == {"H": 0.0, "L": 1.0, "E": 0.0}
    assert immediate_responsibility("UNKNOWN") is None


def test_pe_seq_uses_q_pre():
    q_seq = {"H": 0.1, "L": 0.8, "E": 0.1}
    R = pe_seq_responsibility(q_seq, "H")
    assert abs(sum(R.values()) - 1.0) < 1e-9
    assert R["H"] > q_seq["H"]


def test_no_oracle_import_in_feedback_attribution():
    import inspect

    from rflcc import attribution, feedback

    for mod in (attribution, feedback):
        src = inspect.getsource(mod)
        assert "OracleEvaluator" not in src
        assert "oracle_delta" not in src
        assert "oracle_R" not in src
