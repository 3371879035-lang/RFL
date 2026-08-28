"""归因纯函数：Immediate / PE-Seq / 融合 / finalize（S05，本阶段无 counterfactual）。"""

from __future__ import annotations

from .feedback import log_fusion
from .types import CAUSES


def immediate_responsibility(feedback: str) -> dict[str, float] | None:
    """Immediate：直接相信反馈为 one-hot。UNKNOWN -> abstain（返回 None）。"""
    if feedback == "UNKNOWN" or feedback not in CAUSES:
        return None
    return {c: (1.0 if c == feedback else 0.0) for c in CAUSES}


def pe_seq_responsibility(
    q_seq: dict[str, float],
    feedback: str,
    weight: float = 0.5,
) -> dict[str, float]:
    """PE-Seq：sequence surprise + weak feedback -> q_pre -> R = q_pre。"""
    q_pre = log_fusion(q_seq, feedback, weight=weight)
    return q_pre


def cf_only_responsibility(delta_pos: dict[str, float]) -> dict[str, float] | None:
    """CF-only：R ∝ max(delta, 0)；全零 -> UNRESOLVED（None）。"""
    total = sum(delta_pos.values())
    if total <= 0.0:
        return None
    return {c: v / total for c, v in delta_pos.items()}


def finalize_rfl(
    q_pre: dict[str, float],
    cf_delta: dict[str, float] | None,
    *,
    verified: set[str],
    lambda_cf: float = 4.0,
    lambda_reject: float = 2.0,
    delta_reject: float = 0.05,
    tau_r: float = 1.0,
) -> dict[str, float]:
    """Full-RFL final responsibility（S07 数学）。

    dbar = clip(max(0, delta)/2, 0, 1)
    score = log(q_pre+eps) + lambda_cf*dbar - lambda_reject*I[verified & dbar<delta_reject]
    R = softmax(score / tau_r)
    """
    eps = 1e-12
    dbar = {
        c: min(max(max(0.0, (cf_delta or {}).get(c, 0.0)) / 2.0, 0.0), 1.0)
        for c in CAUSES
    }
    scores = {}
    for c in CAUSES:
        s = __import__("math").log(q_pre[c] + eps) + lambda_cf * dbar[c]
        if c in verified and dbar[c] < delta_reject:
            s -= lambda_reject
        scores[c] = s / tau_r
    m = max(scores.values())
    exps = {c: __import__("math").exp(v - m) for c, v in scores.items()}
    total = sum(exps.values())
    return {c: e / total for c, e in exps.items()}
