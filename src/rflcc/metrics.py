"""Experiment A 指标：AE、WUR、WrongUpdate、UpdateCoverage、Abstention、FFCR（S05/S07）。

注意：指标计算与 train/eval 概念完全解耦——只要给出了 responsibility 与
update mass，就必须计算指标（修复旧版 train=False 时 AE/WUR 伪装成 0 的 bug）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import CAUSES

UPDATE_EPS = 1e-9


@dataclass
class AttributionMetrics:
    attribution_error: float | None = None  # AE = 0.5 * sum(|R - R*|)
    wur: float | None = None  # weighted wrong-update rate
    wrong_update: bool | None = None  # binary：argmax u_m 与 R* 冲突
    update_coverage: bool | None = None  # 是否真正施加了更新
    abstention: bool = False  # 未归因（R 为 None）
    false_feedback_compliance: bool | None = None  # 错误反馈下是否服从错误反馈
    cf_transitions: int = 0
    update_mass: dict[str, float] = field(default_factory=dict)


def attribution_error(R: dict[str, float] | None, R_star: dict[str, float] | None) -> float | None:
    """AE = 0.5 * sum_k |R_k - R*_k|；R* 为 UNRESOLVED 或 R 缺失 -> None。"""
    if R is None or R_star is None:
        return None
    return 0.5 * sum(abs(R[c] - R_star[c]) for c in CAUSES)


def wrong_update_rate(
    update_mass: dict[str, float],
    R_star: dict[str, float] | None,
) -> float | None:
    """WUR = sum_{m in {H,L}} u_m (1 - R*_m) / (sum u_m + eps)。"""
    denom = update_mass.get("H", 0.0) + update_mass.get("L", 0.0)
    if denom <= UPDATE_EPS:
        return None
    if R_star is None:
        return None
    num = 0.0
    for m in ("H", "L"):
        num += update_mass.get(m, 0.0) * (1.0 - R_star.get(m, 0.0))
    return num / denom


def update_coverage(update_mass: dict[str, float], eps_u: float = 1e-6) -> bool:
    return (update_mass.get("H", 0.0) + update_mass.get("L", 0.0)) > eps_u


def wrong_update_binary(
    update_mass: dict[str, float],
    R_star: dict[str, float] | None,
) -> bool | None:
    """binary：施加了更新且 argmax 更新模块的 oracle 责任 < 0.5。"""
    if not update_coverage(update_mass) or R_star is None:
        return None
    u = {"H": update_mass.get("H", 0.0), "L": update_mass.get("L", 0.0)}
    m_max = max(u, key=u.get)
    return R_star.get(m_max, 0.0) < 0.5


def false_feedback_compliance(
    R: dict[str, float] | None,
    observed: str,
    is_false: bool,
) -> bool | None:
    """错误反馈下，算法是否把主要责任给了错误反馈指向的 cause。"""
    if R is None or not is_false or observed not in CAUSES:
        return None
    return R[observed] == max(R.values())


def compute_attribution_metrics(
    *,
    responsibility: dict[str, float] | None,
    oracle_r: dict[str, float] | None,
    proposed_update_mass: dict[str, float] | None = None,
    observed_feedback: str | None = None,
    feedback_is_false: bool = False,
    cf_transitions: int = 0,
    eps_u: float = 1e-6,
) -> AttributionMetrics:
    """统一入口：无论 train 还是 eval，只要给出 R 与 update mass 就计算指标。

    proposed_update_mass：真正施加到内部模块的辅助更新强度
    （Experiment A 中为 proposed rho 幅度；Experiment B 中为 |alpha_diag * rho|）。
    """
    if proposed_update_mass is None:
        proposed_update_mass = {}
    m = AttributionMetrics(
        attribution_error=attribution_error(responsibility, oracle_r),
        cf_transitions=cf_transitions,
        update_mass=dict(proposed_update_mass),
    )
    if responsibility is None:
        m.abstention = True
    m.wur = wrong_update_rate(proposed_update_mass, oracle_r)
    m.wrong_update = wrong_update_binary(proposed_update_mass, oracle_r)
    m.update_coverage = update_coverage(proposed_update_mass, eps_u)
    if observed_feedback is not None:
        m.false_feedback_compliance = false_feedback_compliance(
            responsibility, observed_feedback, feedback_is_false
        )
    return m
