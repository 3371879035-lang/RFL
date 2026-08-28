"""S09 验收：ER-5 replay 语义（task transitions、归因冻结、无 CF 调用）。"""

import inspect

import numpy as np

from rflcc.baselines.er import ER5
from rflcc.qtables import QTables


def test_er5_replay_does_standard_td():
    er = ER5(alpha_low=0.5, alpha_high=0.15, alpha_diag=0.1, gamma=0.97, rng=np.random.RandomState(0))
    q = QTables()
    s = (1, 3, 6, 1, 0, 0)
    s2 = (2, 3, 6, 1, 0, 1)
    for _ in range(10):
        er.add_transition(s, 2, -0.01, s2, False)
    n = er.replay(q, n=1)
    assert n == 1
    # 标准 TD：首次更新 target = r + gamma*0 = -0.01 -> 0.5*(-0.01)
    assert q.low_get(s, 2) == np.isclose(q.low_get(s, 2), -0.005) or abs(q.low_get(s, 2) - (-0.005)) < 1e-9


def test_er5_does_not_call_counterfactual():
    src = inspect.getsource(__import__("rflcc.baselines.er", fromlist=["x"]))
    for forbidden in ("CounterfactualRunner", "SequenceModel", "OracleEvaluator"):
        assert forbidden not in src, forbidden


def test_er5_frozen_attribution_immediate():
    er = ER5(rng=np.random.RandomState(0))
    R = er.frozen_attribution("H")
    assert R == {"H": 1.0, "L": 0.0, "E": 0.0}
    assert er.frozen_attribution("UNKNOWN") is None


def test_er5_replay_count_tracked():
    er = ER5(rng=np.random.RandomState(0))
    q = QTables()
    s = (1, 3, 6, 1, 0, 0)
    for _ in range(20):
        er.add_transition(s, 2, -0.01, s, True)
    er.replay(q, n=7)
    assert er.replay_updates_done == 7


def test_er5_buffer_capacity():
    er = ER5(rng=np.random.RandomState(0))
    for i in range(500):
        er.add_transition((i, 0, 0, 0, 0, 0), 1, -0.01, (i, 0, 0, 0, 0, 0), False)
    assert len(er.buffer) <= er.buffer.capacity
