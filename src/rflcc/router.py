"""UpdateRouter：诊断 auxiliary update 的路由（S09）。

- rho_H = -R_H, rho_L = -R_L（环境责任 R_E 不直接惩罚内部模块）
- 主分析（B-Core）：所有方法低层 aux 更新使用同一个预注册 last-action routing
- CF-critical routing 是 secondary flag（默认关闭），允许 Full-RFL 用
  t_L* = argmax_t Delta_L(t) 作为真正 update site
"""

from __future__ import annotations

from dataclasses import dataclass


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
            high=(s_h, option, rho_h),
            low=(site[0], site[1], rho_l) if site is not None else None,
            update_mass={"H": u_h, "L": u_l},
        )

    def apply(self, q_tables, routed: RoutedUpdate) -> None:
        if routed.high is not None:
            s_h, option, rho_h = routed.high
            q_tables.high_update(s_h, option, q_tables.high_get(s_h, option) + rho_h, 1.0)
        if routed.low is not None:
            state, action, rho_l = routed.low
            q_tables.low_update(state, action, q_tables.low_get(state, action) + rho_l, 1.0)
