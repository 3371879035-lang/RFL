r"""B2-2 — FutureUtility: the recovery time, and the deficit it integrates.

$$\boxed{\mathrm{RMST}(T_{\max})\ \text{primary}}, \qquad
\boxed{\mathrm{DeficitAUC}\ \text{mandatory}}$$

**Recovery is a run, not a crossing.** A13 §? no — A79 §67.3's definition is a *maintained* one:

$$\tau = \inf\{t : V_{t'} \ge 0.95\,V_{\text{pre}} \ \ \forall t' \in [t, t+K-1]\}, \qquad K = 3$$

and if no such $t$ exists the observation is **right-censored at $T_{\max}$**. The window is what
separates "the effect persists" from "the curve touched the threshold once", which is the whole
reason Retention is a separate dimension rather than a second reading of the same number.

**The grid is not uniform, and that is not a detail.** Checkpoints are a set
$\mathcal G_{\text{ckpt}}$ of **real episode indices**, and a value observed at episode 40 does not
sit one unit after the value observed at episode 10. Both estimators therefore integrate over the
indices they are given:

$$\mathrm{DeficitAUC} = \sum_i \bigl(V_{\text{pre}} - V_{t_i}\bigr)^{+}\,\Delta t_i,
\qquad \Delta t_i = t_{i+1} - t_i$$

An array-position reading would silently rescale every deficit by the checkpoint spacing, and would
be invisible on a uniform fixture — so the gates use a non-uniform one.

**No design number is chosen here.** The horizon $T_{\max}$, the checkpoint grid, $N_{\text{eval}}$
and the pre-update level $V_{\text{pre}}$ are **arguments**. There is deliberately no defaulted
"reasonable" episode count: $N_{\text{train}}$ does not exist yet, and A83 §71.4 keeps $T$,
$\mathcal G_{\text{ckpt}}$, $N_{\text{eval}}$ and every $\Delta_{\min}$ to the development stage.
"""

from __future__ import annotations

from dataclasses import dataclass

from rfl_rebuild.b1.errors import ProtocolError

__all__ = [
    "K_RECOVERY",
    "RECOVERY_FRACTION",
    "FutureUtility",
    "deficit_auc",
    "recovery_time",
]

#: The maintained-recovery window (A79 §67.3): three consecutive checkpoints at or above threshold.
K_RECOVERY = 3

#: The recovery threshold, as a fraction of the pre-update level.
RECOVERY_FRACTION = 0.95


def _require_curve(values, episodes) -> tuple:
    r"""A curve is a sequence of observations at **real episode indices**, strictly increasing.

    Both are required and neither is inferred: a curve whose indices are assumed to be
    $0,1,2,\dots$ is the array-position reading this module exists to refuse.
    """
    values, episodes = tuple(values), tuple(episodes)
    if len(values) != len(episodes):
        raise ProtocolError(
            f"the curve has {len(values)} values and {len(episodes)} episode indices; every "
            "observation belongs to the episode index it was taken at")
    if not values:
        raise ProtocolError("the curve is empty; an empty curve has no recovery and no deficit")
    for i, (v, t) in enumerate(zip(values, episodes)):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ProtocolError(f"the curve value at index {i} is {v!r}, not a real number")
        if isinstance(t, bool) or not isinstance(t, int):
            raise ProtocolError(
                f"the episode index at position {i} is {t!r}, not an integer; a checkpoint grid is "
                "a set of real episode indices")
    for a, b in zip(episodes, episodes[1:]):
        if not a < b:
            raise ProtocolError(
                f"the episode indices must be strictly increasing, got {a} then {b}")
    return values, episodes


def recovery_time(values, episodes, *, pre_level: float, t_max: int) -> int | None:
    r"""$\tau$, or ``None`` for a right-censored observation at $t_{\max}$.

    $$\boxed{\tau = \inf\{t : V_{t'} \ge 0.95\,V_{\text{pre}}\ \forall t' \in [t, t+K-1]\}}$$

    A *maintained* run of $K$ consecutive checkpoints at or above the threshold. One or two
    crossings are not a recovery, and a dip inside a window voids that window rather than being
    averaged away.
    """
    values, episodes = _require_curve(values, episodes)
    if not isinstance(pre_level, (int, float)) or isinstance(pre_level, bool):
        raise ProtocolError(f"the pre-update level {pre_level!r} is not a real number")
    if not isinstance(t_max, int) or isinstance(t_max, bool):
        raise ProtocolError(f"T_max {t_max!r} is not an integer episode index")
    threshold = RECOVERY_FRACTION * float(pre_level)
    at_or_above = [v >= threshold for v in values]
    for i in range(len(values) - K_RECOVERY + 1):
        if all(at_or_above[i:i + K_RECOVERY]):
            return episodes[i]
    return None


def deficit_auc(values, episodes, *, pre_level: float) -> float:
    r"""$\sum_i (V_{\text{pre}} - V_{t_i})^{+}\,\Delta t_i$ over the **real** indices.

    A trapezoid on the left-endpoint deficit, multiplied by the actual spacing. The spacing is
    taken from the episode indices, so a non-uniform grid is integrated correctly rather than
    being rescaled to a unit grid.
    """
    values, episodes = _require_curve(values, episodes)
    if not isinstance(pre_level, (int, float)) or isinstance(pre_level, bool):
        raise ProtocolError(f"the pre-update level {pre_level!r} is not a real number")
    total = 0.0
    for i in range(len(values) - 1):
        deficit = max(0.0, float(pre_level) - float(values[i]))
        total += deficit * (episodes[i + 1] - episodes[i])
    return total


@dataclass(frozen=True, slots=True)
class FutureUtility:
    r"""Both quantities, from one curve, with the censoring flag kept explicit.

    `recovered` is not derivable from `tau` alone once the value may legitimately be ``None``, and
    a caller that had to compare against ``None`` would eventually compare it to a number.
    """

    tau: int | None
    recovered: bool
    rmst: int
    deficit_auc: float
    t_max: int

    @staticmethod
    def from_curve(values, episodes, *, pre_level: float, t_max: int) -> "FutureUtility":
        r"""RMST is $\min(\tau, T_{\max})$: a censored observation contributes the full horizon."""
        tau = recovery_time(values, episodes, pre_level=pre_level, t_max=t_max)
        return FutureUtility(
            tau=tau,
            recovered=tau is not None,
            rmst=t_max if tau is None else tau,
            deficit_auc=deficit_auc(values, episodes, pre_level=pre_level),
            t_max=t_max,
        )
