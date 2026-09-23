r"""$F_0$ §4.0's authoritative spread, as the one implementation every rule must use.

$$\boxed{\text{the authoritative object of } \mathrm{sd} \text{ is the set's own values } x_1, \ldots, x_n
\text{, never an algebraic rearrangement of their summary}}$$

Rev 3 claimed the per-set statistics "recover this form exactly", and the construction falsified it: in
`binary64`, $\sum x^2/n - (\sum x/n)^2$ is a difference of two nearly equal numbers, so a set whose values are
equal but not exactly representable comes back with a positive residue instead of zero --- measured at
$7.45 \times 10^{-9}$ for a set of one value. §4.4's zero cases are **exact comparisons** on this quantity, so
a residue would decide a branch. This module therefore implements the rule §4.0 now freezes:

$$\boxed{\bar x = \frac{\text{left-to-right sum}(x_j)}{n}}, \qquad
\boxed{x_1 = \cdots = x_n \;\Longrightarrow\; \mathrm{sd} = 0}$$

$$\boxed{\mathrm{sd} = \sqrt{\frac{1}{n}\,\text{left-to-right sum}\bigl((x_j - \bar x)^2\bigr)}
\quad \text{otherwise}}$$

The constancy test reads the values themselves, is evaluated **first**, and is what closes the constant case
exactly. **The iteration order is frozen with the algorithm** --- ascending bank index of the balanced master
bank --- because a `binary64` left-to-right sum is order-sensitive; callers holding §3's material pass the
values in that order, which is the order the incidence already stores.

"Left-to-right" is the plain accumulation, named in the text because CPython's `sum()` is
Neumaier-compensated and is therefore a *different* algorithm: it agrees with this one on most sets and
differs by an ulp on some, and §4.1's curve is compared against A91's `_mean_return`, which accumulates
naively.
"""

from __future__ import annotations

import math

from rfl_rebuild.b1.errors import ProtocolError

__all__ = ["is_constant", "left_to_right_sum", "mean", "sd", "standard_error", "sufficient_statistics"]


def left_to_right_sum(values) -> float:
    r"""`t = 0.0; for v in values: t += v` --- the accumulation §4.0 freezes, in the caller's order."""
    total = 0.0
    for value in values:
        total += value
    return total


def mean(values) -> float:
    r"""$\bar x$, by the frozen accumulation. An empty set has no mean --- it is refused, not zeroed."""
    values = tuple(values)
    if not values:
        raise ProtocolError("an empty set has no mean; §4.0 never imputes a missing value")
    return left_to_right_sum(values) / len(values)


def is_constant(values) -> bool:
    r"""$x_1 = \cdots = x_n$ on the values themselves --- the test that closes the constant case exactly."""
    values = tuple(values)
    if not values:
        raise ProtocolError("an empty set has no spread")
    return all(value == values[0] for value in values[1:])


def sd(values) -> float:
    r"""§4.0's population `sd`, by the frozen two-pass algorithm, with the constant case closed first."""
    values = tuple(values)
    if not values:
        raise ProtocolError("an empty set has no spread")
    if is_constant(values):                     # evaluated FIRST, and on the values, not on the residues
        return 0.0
    centre = mean(values)
    return math.sqrt(left_to_right_sum((value - centre) ** 2 for value in values) / len(values))


def standard_error(values) -> float | None:
    r"""$SE = \mathrm{sd}/\sqrt{n}$ --- §4.4's quantity, and $n = 1$ gives $0$ rather than undefined.

    `None` means the set is empty: §4.0's "missing values are never imputed" and §4.4's "an empty set has no
    mean", so an empty $C_r(c)$ is inadmissible rather than zero.
    """
    values = tuple(values)
    if not values:
        return None
    return sd(values) / math.sqrt(len(values))


def sufficient_statistics(values) -> tuple:
    r"""$\left(\lvert C\rvert, \sum V, \sum V^2\right)$ --- §3's statistics, as the **derived cache**.

    Admissible as a cache and as a cross-check, never as the authoritative path: computed from this triple,
    $SE$ carries the cancellation §4.0 now forbids relying on. The sums use the frozen accumulation.
    """
    values = tuple(values)
    return (len(values), left_to_right_sum(values), left_to_right_sum(value * value for value in values))
