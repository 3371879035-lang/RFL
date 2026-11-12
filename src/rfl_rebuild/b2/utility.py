r"""B2-2 — FutureUtility: the recovery time, and the deficit it integrates.

`05` §8.3 froze a **continuous** integral over the whole horizon:

$$\boxed{\mathrm{DeficitAUC} = \frac{1}{T_{\max}}\int_0^{T_{\max}}
\bigl[V_{\text{pre}} - V(t)\bigr]_+\,dt}$$

and A84 (§72) freezes how that integral is realised on a checkpoint grid, because the choice moves
the number and was therefore not the implementation's to make silently:

$$\boxed{\mathrm{DeficitAUC} = \frac{1}{T_{\max}} \sum_i \frac{d_i + d_{i+1}}{2}
\,(t_{i+1} - t_i)}, \qquad d_i = \bigl[V_{\text{pre}} - V_{t_i}\bigr]_+$$

**trapezoidal, and normalised.** Trapezoidal on the real episode grid is the direct numerical
reading of a continuous integral under the minimal assumption — linear interpolation between
adjacent checkpoints — rather than left-hold, which additionally assumes the previous measurement
holds across the whole interval. The calibration is analytic and seedless: on a constant deficit and
on a linear one the rule must reproduce the analytic integral exactly.

**The grid spans the horizon.** `05` §6.2's grid is $\mathcal G_{\text{ckpt}} = \{0, 1, 2, 5,
\dots, T\}$ — it contains both ends — so the curve contract is `episodes[0] == 0`,
`episodes[-1] == T_max`, and every index inside $[0, T_{\max}]$. A curve that stops short is
refused rather than padded: a rule for the unobserved tail would be an estimator chosen silently
inside an estimator, and RMST and DeficitAUC must describe one interval.

**Recovery is a maintained run, not a crossing.** $\tau$ is the first $t$ whose next $K=3$
checkpoints are all at or above $0.95\,V_{\text{pre}}$, right-censored at $T_{\max}$.

**Naming, deliberately.** The per-seed $\min(\tau, T_{\max})$ is **not** RMST: RMST is
$\mathbb E[\min(\tau, T_{\max})]$ across seeds, which is B2-4's aggregation. This module calls
the per-seed quantity `restricted_time` and leaves the name to the estimator that averages.

**No design number is chosen here.** $T_{\max}$, the grid and $V_{\text{pre}}$ are **arguments**,
and $N_{\text{train}}$ does not exist: A83 §71.4 keeps $T$, $\mathcal G_{\text{ckpt}}$,
$N_{\text{eval}}$ and every $\Delta_{\min}$ to the development stage.
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


def _require_real(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError(f"{what} {value!r} is not a real number")
    return float(value)


def _require_horizon(t_max) -> int:
    if isinstance(t_max, bool) or not isinstance(t_max, int):
        raise ProtocolError(
            f"T_max {t_max!r} is not an integer episode index; the horizon is a design quantity "
            "supplied by the caller, never inferred from the curve")
    if t_max <= 0:
        raise ProtocolError(f"T_max {t_max!r} must be a positive episode index")
    return t_max


def _require_curve(values, episodes, t_max: int) -> tuple:
    r"""A curve is a sequence of observations at **real episode indices spanning the horizon**.

    $$\boxed{episodes[0] = 0, \qquad episodes[-1] = T_{\max}, \qquad 0 \le t_i \le T_{\max}}$$
    """
    values, episodes = tuple(values), tuple(episodes)
    if len(values) != len(episodes):
        raise ProtocolError(
            f"the curve has {len(values)} values and {len(episodes)} episode indices; every "
            "observation belongs to the episode index it was taken at")
    if not values:
        raise ProtocolError("the curve is empty; an empty curve has no recovery and no deficit")
    for i, (v, t) in enumerate(zip(values, episodes)):
        _require_real(v, f"the curve value at position {i}")
        if isinstance(t, bool) or not isinstance(t, int):
            raise ProtocolError(
                f"the episode index at position {i} is {t!r}, not an integer; a checkpoint grid is "
                "a set of real episode indices")
        if not 0 <= t <= t_max:
            raise ProtocolError(
                f"the episode index {t} at position {i} lies outside [0, T_max={t_max}]; the curve "
                "describes the horizon and nothing beyond it")
    for a, b in zip(episodes, episodes[1:]):
        if not a < b:
            raise ProtocolError(
                f"the episode indices must be strictly increasing, got {a} then {b}")
    if episodes[0] != 0:
        raise ProtocolError(
            f"the curve starts at episode {episodes[0]} rather than 0; the checkpoint grid contains "
            "the start of the horizon (05 6.2), so a curve missing it would leave the first "
            "interval unobserved")
    if episodes[-1] != t_max:
        raise ProtocolError(
            f"the curve ends at episode {episodes[-1]} but T_max is {t_max}; a curve that stops "
            "short is refused rather than padded, because RMST and DeficitAUC would then describe "
            "different intervals and any tail rule would be an estimator chosen silently")
    return values, episodes


def recovery_time(values, episodes, *, pre_level: float, t_max: int) -> int | None:
    r"""$\tau$, or ``None`` for a right-censored observation at $t_{\max}$.

    $$\boxed{\tau = \inf\{t : V_{t'} \ge 0.95\,V_{\text{pre}}\ \forall t' \in [t, t+K-1]\}}$$

    A *maintained* run of $K$ consecutive checkpoints at or above the threshold. One or two
    crossings are not a recovery, and a dip inside a window voids that window rather than being
    averaged away.
    """
    t_max = _require_horizon(t_max)
    values, episodes = _require_curve(values, episodes, t_max)
    threshold = RECOVERY_FRACTION * _require_real(pre_level, "the pre-update level")
    at_or_above = [v >= threshold for v in values]
    for i in range(len(values) - K_RECOVERY + 1):
        if episodes[i + K_RECOVERY - 1] > t_max:
            continue                      # a window reaching past the horizon cannot qualify
        if all(at_or_above[i:i + K_RECOVERY]):
            return episodes[i]
    return None


def deficit_auc(values, episodes, *, pre_level: float, t_max: int) -> float:
    r"""$\frac{1}{T_{\max}}\int_0^{T_{\max}} [V_{\text{pre}} - V(t)]_+\,dt$, trapezoidally.

    $$\boxed{\frac{1}{T_{\max}} \sum_i \frac{d_i + d_{i+1}}{2}\,(t_{i+1} - t_i)}, \qquad
    d_i = \bigl[V_{\text{pre}} - V_{t_i}\bigr]_+$$

    Both halves matter: the $1/T_{\max}$ is `05` §8.3's normalisation, so the number is a mean
    deficit over the horizon rather than an area that grows with it; and the rule is trapezoidal on
    the real grid (A84 §72), exact on constant and linear deficits.
    """
    t_max = _require_horizon(t_max)
    values, episodes = _require_curve(values, episodes, t_max)
    pre = _require_real(pre_level, "the pre-update level")
    deficits = [max(0.0, pre - v) for v in values]
    total = 0.0
    for i in range(len(values) - 1):
        total += 0.5 * (deficits[i] + deficits[i + 1]) * (episodes[i + 1] - episodes[i])
    return total / t_max


@dataclass(frozen=True, slots=True)
class FutureUtility:
    r"""Both quantities, from one curve, with the censoring flag kept explicit.

    `recovered` is not derivable from `tau` alone once the value may legitimately be ``None``, and
    a caller that had to compare against ``None`` would eventually compare it to a number.
    """

    tau: int | None
    recovered: bool
    restricted_time: int
    deficit_auc: float
    t_max: int

    @staticmethod
    def from_curve(values, episodes, *, pre_level: float, t_max: int) -> "FutureUtility":
        r"""`restricted_time` is $\min(\tau, T_{\max})$ **per seed**.

        It is not RMST: $\mathrm{RMST}(T_{\max}) = \mathbb E[\min(\tau, T_{\max})]$ is the
        cross-seed aggregation and belongs to B2-4. Naming the per-seed number after the population
        summary is how the two get conflated later, so the name is reserved there.
        """
        tau = recovery_time(values, episodes, pre_level=pre_level, t_max=t_max)
        return FutureUtility(
            tau=tau,
            recovered=tau is not None,
            restricted_time=t_max if tau is None else tau,
            deficit_auc=deficit_auc(values, episodes, pre_level=pre_level, t_max=t_max),
            t_max=t_max,
        )
