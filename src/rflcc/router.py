"""UpdateRouter：诊断 auxiliary update 的路由（S09）。

- rho_H = -R_H, rho_L = -R_L（环境责任 R_E 不直接惩罚内部模块）
- 主分析（B-Core）：所有方法低层 aux 更新使用同一个预注册 last-action routing
- CF-critical routing 是 secondary flag（默认关闭），允许 Full-RFL 用
  t_L* = argmax_t Delta_L(t) 作为真正 update site
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AppliedUpdate:
    """Receipt for one diagnostic Q-table write.

    ``delta_q`` is the *actual* post-write change, not the requested target.
    Keeping the before/after values makes update metrics independent of the
    router implementation and catches accidental extra scaling.
    """

    module: str
    site: Any = None
    action_or_option: int | None = None
    q_before: float = 0.0
    q_after: float = 0.0
    delta_q: float = 0.0

    @property
    def state(self):
        """Alias used by reports that call the update site ``state``."""
        return self.site


@dataclass
class RoutedUpdate:
    high: dict | None = None  # (s_h, option) -> rho_H
    low: dict | None = None  # (state, action) -> rho_L
    update_mass: dict[str, float] = None  # {"H": u_H, "L": u_L}


def responsibility_to_rho(R: dict[str, float]) -> tuple[float, float]:
    """B 矩阵映射：rho_H = -R_H, rho_L = -R_L。"""
    return -R.get("H", 0.0), -R.get("L", 0.0)


class UpdateRouter:
    def __init__(self, *, alpha_diag: float = 0.10, use_cf_critical: bool = False):
        self.alpha_diag = alpha_diag
        self.use_cf_critical = use_cf_critical

    def route(
        self,
        *,
        responsibility: dict[str, float] | None,
        s_h: int,
        option: int,
        last_low: tuple | None,  # (state, action) 最后低层决策
        critical_low: tuple | None = None,  # CF-critical site（secondary）
    ) -> RoutedUpdate:
        """把责任映射为施加到 Q 表上的辅助更新。"""
        if responsibility is None:
            return RoutedUpdate(high=None, low=None, update_mass={"H": 0.0, "L": 0.0})
        rho_h, rho_l = responsibility_to_rho(responsibility)
        u_h = self.alpha_diag * abs(rho_h)
        u_l = self.alpha_diag * abs(rho_l)
        site = critical_low if (self.use_cf_critical and critical_low is not None) else last_low
        return RoutedUpdate(
            # Keep the routed rho unscaled for backwards-compatible
            # inspection; ``apply`` is the single place where alpha_diag is
            # materialised into an actual Q-table delta.
            high=(s_h, option, rho_h),
            low=(site[0], site[1], rho_l) if site is not None else None,
            update_mass={"H": u_h, "L": u_l},
        )

    def apply(self, q_tables, routed: RoutedUpdate) -> list[AppliedUpdate]:
        receipts: list[AppliedUpdate] = []
        if routed.high is not None:
            s_h, option, rho = routed.high
            delta = self.alpha_diag * rho
            if abs(delta) > 0.0:
                before = q_tables.high_get(s_h, option)
                q_tables.high_update(s_h, option, before + delta, 1.0)
                after = q_tables.high_get(s_h, option)
                receipts.append(AppliedUpdate("H", s_h, option, before, after, after - before))
        if routed.low is not None:
            state, action, rho = routed.low
            delta = self.alpha_diag * rho
            if abs(delta) > 0.0:
                before = q_tables.low_get(state, action)
                q_tables.low_update(state, action, before + delta, 1.0)
                after = q_tables.low_get(state, action)
                receipts.append(AppliedUpdate("L", state, action, before, after, after - before))
        return receipts
