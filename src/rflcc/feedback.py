"""外部诊断反馈：注入器（evaluation-only）与 likelihood 融合（S05）。

核心原则：DiagnosticFeedback = WeakEvidence，不是 Ground Truth。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .types import CAUSES, FEEDBACK_CAUSES

_EPS = 1e-12

MATCH_LIKELIHOOD = 0.6
MISMATCH_LIKELIHOOD = 0.2
UNKNOWN_LIKELIHOOD = 1.0 / 3.0
FEEDBACK_WEIGHT = 0.5


def feedback_likelihood(d: str, k: str) -> float:
    """P(observed=d | true cause=k) 的弱 likelihood。"""
    if d == "UNKNOWN":
        return UNKNOWN_LIKELIHOOD
    return MATCH_LIKELIHOOD if d == k else MISMATCH_LIKELIHOOD


def log_fusion(
    q_seq: dict[str, float],
    feedback: str,
    weight: float = FEEDBACK_WEIGHT,
) -> dict[str, float]:
    """log-space Bayes-style 加权融合：q_pre = softmax(log q_seq + w log L_feedback)。

    禁止在 probability space 直接 softmax(q_seq * likelihood)。
    """
    logits = {}
    for c in CAUSES:
        logits[c] = math.log(q_seq[c] + _EPS) + weight * math.log(
            feedback_likelihood(feedback, c) + _EPS
        )
    m = max(logits.values())
    exps = {c: math.exp(v - m) for c, v in logits.items()}
    s = sum(exps.values())
    return {c: e / s for c, e in exps.items()}


@dataclass
class FeedbackInjector:
    """生成 observed diagnostic feedback。

    mode:
      - clean: p_false=0，总是返回真实主因
      - symmetric: 以 p_false 概率随机替换为另外两类之一
      - adversarial_planning_blame: 真实主因非 H 时以 p_false 输出 H
    p_missing: 以该概率返回 UNKNOWN（secondary 条件）。
    """

    p_false: float = 0.0
    mode: str = "symmetric"
    p_missing: float = 0.0
    rng: np.random.RandomState | None = None

    def __post_init__(self) -> None:
        if self.rng is None:
            self.rng = np.random.RandomState(0)
        assert 0.0 <= self.p_false <= 1.0
        assert 0.0 <= self.p_missing <= 1.0

    def generate(self, true_primary: str | None) -> str:
        """true_primary=None（UNRESOLVED）时反馈 UNKNOWN。"""
        if true_primary is None:
            return "UNKNOWN"
        if self.rng.random() < self.p_missing:
            return "UNKNOWN"
        if self.mode == "adversarial_planning_blame":
            if true_primary != "H" and self.rng.random() < self.p_false:
                return "H"
            return true_primary
        # symmetric
        if self.rng.random() < self.p_false:
            others = [c for c in ("H", "L", "E") if c != true_primary]
            return others[int(self.rng.randint(0, len(others)))]
        return true_primary

    def is_false(self, observed: str, true_primary: str | None) -> bool:
        if observed == "UNKNOWN" or true_primary is None:
            return False
        return observed != true_primary
