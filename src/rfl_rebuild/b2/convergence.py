"""A91 section 79.7 convergence and the F0 nearest-rank horizon rule.

These pure functions select no input population. A stage must first validate the
development artifact and its provenance; operational curves are not design data.
"""
import math

from rfl_rebuild.b1.errors import ProtocolError


def convergence_time(values, episodes, *, k=3, epsilon_s=1e-3, epsilon_f=0.1):
    """Last checkpoint of the first qualifying K-point window; None is censored."""
    values, episodes = tuple(values), tuple(episodes)
    if type(k) is not int or k < 3:
        raise ProtocolError("convergence requires an integer K >= 3")
    if len(values) != len(episodes) or not episodes:
        raise ProtocolError("convergence needs a nonempty aligned episode axis")
    if (any(type(e) is not int or e < 0 for e in episodes)
            or episodes[0] != 0 or any(b <= a for a, b in zip(episodes, episodes[1:]))):
        raise ProtocolError("convergence needs strictly increasing real episode indices starting at zero")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ProtocolError("convergence values must be finite real numbers")
    for tolerance, upper in ((epsilon_s, None), (epsilon_f, 1)):
        if (type(tolerance) not in (int, float) or not math.isfinite(tolerance)
                or tolerance <= 0 or (upper is not None and tolerance > upper)):
            raise ProtocolError("invalid pre-data convergence tolerance")
    for end in range(k - 1, len(values)):
        start = end - k + 1
        slope = (values[end] - values[start]) / (episodes[end] - episodes[start])
        increments = tuple(values[i + 1] - values[i] for i in range(start, end))
        if all(delta == 0 for delta in increments):
            flip_rate = 0.0
        else:
            pairs = [(a, b) for a, b in zip(increments, increments[1:]) if a != 0 and b != 0]
            if not pairs:
                continue  # nonconstant but undefined denominator: never impute zero
            # Opposite signs implement delta_i*delta_{i-1}<0 without underflow.
            flip_rate = sum((a < 0) != (b < 0) for a, b in pairs) / len(pairs)
        if abs(slope) < epsilon_s and flip_rate < epsilon_f:
            return episodes[end]
    return None


def select_horizon(convergence_times, *, acquisition_cap):
    """A91 censored nearest rank over the ORIGINAL sample; exact 6/5 ceiling.

    None means an observed run was right-censored, not a missing run/record. The
    latter is an artifact validation error and must never reach this function.
    """
    times = tuple(convergence_times)
    if type(acquisition_cap) is not int or acquisition_cap < 1 or not times:
        raise ProtocolError("horizon selection needs a positive cap and a nonempty sample")
    if any(t is not None and (type(t) is not int or not 2 <= t <= acquisition_cap) for t in times):
        raise ProtocolError("invalid observed convergence time")
    rank = (9 * len(times) + 9) // 10
    observed = sorted(t for t in times if t is not None)
    result = {"n": len(times), "rank": rank, "uncensored": len(observed),
              "censored": len(times) - len(observed), "T": None, "status": "NO_ADMISSIBLE_T"}
    if len(observed) < rank:
        return {**result, "reason": "QUANTILE_UNIDENTIFIED"}
    quantile = observed[rank - 1]
    horizon = (6 * quantile + 4) // 5
    if horizon > acquisition_cap:
        return {**result, "quantile": quantile, "reason": "HORIZON_EXCEEDS_CAP"}
    return {**result, "T": horizon, "quantile": quantile, "status": "ADMISSIBLE", "reason": None}
