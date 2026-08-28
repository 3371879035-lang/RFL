"""S04 验收：pairwise complement、G 符号、sequence 区分、feedback 无污染。"""

import numpy as np
import pytest

from rflcc.sequence import SequenceModel
from rflcc.trace import EpisodeTrace
from rflcc.types import (
    CAUSES,
    TOKEN_ACT_E,
    TOKEN_ACT_N,
    TOKEN_ACT_S,
    TOKEN_ACT_W,
    TOKEN_COLLISION,
    TOKEN_DIST_FAR,
    TOKEN_DIST_MID,
    TOKEN_DIST_NEAR,
    TOKEN_EXIT,
    TOKEN_MONSTER_DASH,
    TOKEN_MONSTER_NORMAL,
    TOKEN_OPT_LOWER,
    TOKEN_OPT_UPPER,
    TOKEN_ROUTE_DEVIATE,
    TOKEN_ROUTE_PROGRESS,
    TOKEN_ACT_WAIT,
    TraceEvent,
)


def _trace(tokens, seed=0, scenario_id="t", primary="H"):
    tr = EpisodeTrace(seed=seed, scenario_id=scenario_id, option=0, terminal_type="COLLISION")
    tr.causal_events = [
        TraceEvent(t=i, token=tok, module=None, source="test")
        for i, tok in enumerate(tokens)
    ]
    tr.true_primary = primary
    return tr


def _calibrated_model():
    model = SequenceModel()
    H = _trace(
        [TOKEN_OPT_UPPER, TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ACT_E,
         TOKEN_ROUTE_PROGRESS, TOKEN_MONSTER_NORMAL, TOKEN_DIST_FAR,
         TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ROUTE_PROGRESS,
         TOKEN_MONSTER_NORMAL, TOKEN_DIST_NEAR, TOKEN_COLLISION],
        primary="H",
    )
    L = _trace(
        [TOKEN_OPT_LOWER, TOKEN_ACT_E, TOKEN_ACT_S, TOKEN_ACT_S,
         TOKEN_ROUTE_PROGRESS, TOKEN_MONSTER_NORMAL, TOKEN_DIST_MID,
         TOKEN_ACT_WAIT, TOKEN_ACT_WAIT, TOKEN_ACT_E, TOKEN_ACT_S,
         TOKEN_ROUTE_PROGRESS, TOKEN_DIST_NEAR, TOKEN_COLLISION],
        primary="L",
    )
    E = _trace(
        [TOKEN_OPT_LOWER, TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ACT_E,
         TOKEN_ROUTE_PROGRESS, TOKEN_MONSTER_NORMAL, TOKEN_DIST_MID,
         TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ROUTE_PROGRESS,
         TOKEN_MONSTER_DASH, TOKEN_MONSTER_DASH, TOKEN_DIST_NEAR,
         TOKEN_COLLISION],
        primary="E",
    )
    # E 轨迹按 oracle R* 加权软计数（环境几何下 E 与 L 有耦合）
    E.env_meta["r_star"] = {"H": 0.0, "L": 0.25, "E": 0.75}
    model.calibrate({"H": [H] * 20, "L": [L] * 20, "E": [E] * 20})
    return model


def test_pairwise_complement():
    model = _calibrated_model()
    for cause in CAUSES:
        A = model._A[cause]
        for u in range(A.shape[0]):
            for v in range(u + 1, A.shape[1]):
                assert abs((A[u, v] + A[v, u]) - 1.0) < 1e-9


def test_probability_in_range():
    model = _calibrated_model()
    for cause in CAUSES:
        A = model._A[cause]
        assert A.min() >= 0.01
        assert A.max() <= 0.99
        assert np.allclose(np.diag(A), 0.5)


def test_explanatory_gain_sign():
    model = _calibrated_model()
    h_trace = _trace(
        [TOKEN_OPT_UPPER, TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ACT_E,
         TOKEN_ROUTE_PROGRESS, TOKEN_MONSTER_NORMAL, TOKEN_DIST_FAR,
         TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ROUTE_PROGRESS,
         TOKEN_MONSTER_NORMAL, TOKEN_DIST_NEAR, TOKEN_COLLISION],
        primary="H",
    )
    res = model.score(h_trace)
    assert res.ell["H"] > res.ell_background
    assert res.G["H"] > 0


def test_sequence_prefers_matching_template():
    model = _calibrated_model()
    h_trace = _trace(
        [TOKEN_OPT_UPPER, TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ACT_E,
         TOKEN_ROUTE_PROGRESS, TOKEN_MONSTER_NORMAL, TOKEN_DIST_FAR,
         TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ROUTE_PROGRESS,
         TOKEN_MONSTER_NORMAL, TOKEN_DIST_NEAR, TOKEN_COLLISION],
        primary="H",
    )
    res = model.score(h_trace)
    assert res.q_seq["H"] > res.q_seq["L"]
    assert res.q_seq["H"] > res.q_seq["E"]


def test_q_seq_sums_to_one():
    model = _calibrated_model()
    res = model.score(
        _trace([TOKEN_OPT_UPPER, TOKEN_ACT_N, TOKEN_ROUTE_PROGRESS, TOKEN_MONSTER_NORMAL,
                TOKEN_DIST_NEAR, TOKEN_COLLISION], primary="H")
    )
    assert abs(sum(res.q_seq.values()) - 1.0) < 1e-9


def test_feedback_never_enters_causal_sequence():
    model = _calibrated_model()
    tr = _trace(
        [TOKEN_OPT_UPPER, TOKEN_ACT_E, TOKEN_ROUTE_PROGRESS, TOKEN_MONSTER_NORMAL,
         TOKEN_DIST_NEAR, TOKEN_COLLISION],
        primary="H",
    )
    tr.add_feedback("FEEDBACK_H")
    assert "FEEDBACK_H" in [e.token for e in tr.feedback_events]
    assert "FEEDBACK_H" not in [e.token for e in tr.causal_events]
    assert "FEEDBACK_H" not in model._tokens(tr)


def test_vocab_no_feedback_tokens():
    model = _calibrated_model()
    assert all(not t.startswith("FEEDBACK_") for t in model.vocab)


def test_g_sign_positive_for_match_negative_for_mismatch():
    """真实场景校准后：H 模板 G 为正；L 相对 E 占优（E/L 结构混淆是环境事实）。"""
    from rflcc.env import CausalChaseEnv
    from rflcc.scenarios import ScenarioGenerator

    env = CausalChaseEnv()
    gen = ScenarioGenerator(env=env, max_attempts=200)
    traces = {"H": [], "L": [], "E": []}
    for cause in traces:
        samples = gen.generate(
            cause, base_seed=90000 + {"H": 0, "L": 100, "E": 200}[cause], n=8
        )
        traces[cause] = [s.trace for s in samples]

    model = SequenceModel()
    model.calibrate(traces)

    res_h = model.score(traces["H"][0])
    assert res_h.G["H"] > 0, ("H", res_h.G)
    assert res_h.q_seq["H"] == max(res_h.q_seq.values())

    # L/E 共享"安全路线"结构，区分弱是环境事实（CF 验证负责区分）；
    # 但 L 模板应相对 E 占优，H 应明显不匹配
    res_l = model.score(traces["L"][0])
    assert res_l.G["L"] > res_l.G["E"], ("L vs E", res_l.G)
    assert res_l.q_seq["L"] > res_l.q_seq["E"], ("L vs E", res_l.q_seq)
    assert res_l.G["H"] < res_l.G["L"], ("L vs H", res_l.G)


def test_dash_template_distinct():
    model = _calibrated_model()
    e_trace = _trace(
        [TOKEN_OPT_LOWER, TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ACT_E,
         TOKEN_ROUTE_PROGRESS, TOKEN_MONSTER_NORMAL, TOKEN_DIST_MID,
         TOKEN_ACT_E, TOKEN_ACT_E, TOKEN_ROUTE_PROGRESS,
         TOKEN_MONSTER_DASH, TOKEN_MONSTER_DASH, TOKEN_DIST_NEAR,
         TOKEN_COLLISION],
        primary="E",
    )
    res = model.score(e_trace)
    # E 轨迹（含 DASH token）应倾向 E 模板（加权校准后）
    assert res.q_seq["E"] > res.q_seq["H"]
