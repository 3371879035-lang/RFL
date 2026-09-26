"""F0 rev-4 selectors, on baseline material only. No acquisition or I/O here.

Grouping identical incidence preserves site multiplicity for spread quantiles;
it never turns the credited-domain population into a population of unique groups.
"""
from __future__ import annotations

import math
from collections import Counter

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.convergence import convergence_time, select_horizon
from rfl_rebuild.b2.numerics import mean, sd, standard_error, left_to_right_sum
from rfl_rebuild.b2.retention import RetentionAtH, LateWindowRetention
from rfl_rebuild.b2.unaffected import CHANNELS, REFINEMENTS, _slice
from rfl_rebuild.b2.utility import FutureUtility

SIZES = (100, 256, 512, 1024)


def _finite(values):
    values = tuple(values)
    if not values or any(type(x) not in (float, int) or not math.isfinite(x) for x in values):
        raise ProtocolError("selector values must be nonempty finite numeric observations")
    return values


class PrefixSelector:
    """f_N maximum over the entire seed/episode envelope, including after T*."""
    def __init__(self):
        self.metrics = dict.fromkeys(SIZES, 0.0)
        self.records = 0

    def update(self, levels):
        levels = _finite(levels)
        if len(levels) != 1024:
            raise ProtocolError("f_N requires all 1024 master-bank values")
        centre, spread = mean(levels), sd(levels)
        for n in SIZES:
            numerator = abs(mean(levels[:n]) - centre)
            term = (0.0 if numerator == 0 else None) if spread == 0 else numerator / max(spread, 1e-9)
            if term is None or self.metrics[n] is None:
                self.metrics[n] = None
            else:
                self.metrics[n] = max(self.metrics[n], term)
        self.records += 1

    def result(self):
        if not self.records:
            raise ProtocolError("f_N cannot select from an empty envelope")
        eligible = [n for n in SIZES if self.metrics[n] is not None and self.metrics[n] <= .25]
        return {"status": "ADMISSIBLE" if eligible else "NO_ADMISSIBLE_N_EVAL",
                "N": min(eligible) if eligible else None,
                "metrics": [{"N": n, "metric": self.metrics[n]} for n in SIZES]}


def grid_templates(horizon):
    if type(horizon) is not int or horizon < 2:
        raise ProtocolError("grid templates require an integer horizon >= 2")
    skeleton = [0, 1, 2, 5, 10, 20, 50, 100, 150, 200, 300, 500]
    while skeleton[-1] < horizon:
        skeleton.append(2 * skeleton[-1])
    medium = tuple(t for t in skeleton if t < horizon) + (horizon,)
    coarse = (0,) + medium[1:-1:2] + (horizon,)
    fine = tuple(sorted(set(medium) | {(a + b) // 2 for a, b in zip(medium, medium[1:]) if b - a > 1}))
    return (coarse, medium, fine)


def _curves_at(curves, horizon):
    if type(horizon) is not int or horizon < 2:
        raise ProtocolError("selector horizon must be an integer >= 2")
    curves = tuple(_finite(c) for c in curves)
    if not curves or any(len(c) <= horizon for c in curves):
        raise ProtocolError("a master curve is missing the requested horizon")
    return curves


def _utility(curve, grid, pre_level):
    return FutureUtility.from_curve(tuple(curve[e] for e in grid), grid,
                                    pre_level=pre_level, t_max=grid[-1])


def select_grid(curves, *, horizon, pre_level):
    curves = _curves_at(curves, horizon)
    _finite((pre_level,))
    full_grid = tuple(range(horizon + 1))
    full = [_utility(c, full_grid, pre_level) for c in curves]
    candidates = []
    for number, grid in enumerate(grid_templates(horizon), 1):
        metrics = []
        for curve, original in zip(curves, full):
            reduced = _utility(curve, grid, pre_level)
            metrics.append(max(abs(reduced.restricted_time - original.restricted_time) / horizon,
                               abs(reduced.deficit_auc - original.deficit_auc)))
        metric = max(metrics)
        candidates.append({"template": number, "grid": list(grid), "metric": metric,
                           "admissible": metric <= .05})
    eligible = [c for c in candidates if c["admissible"]]
    winner = min(eligible, key=lambda c: (len(c["grid"]), c["template"])) if eligible else None
    return {"status": "ADMISSIBLE" if winner else "NO_ADMISSIBLE_GRID",
            "grid": winner["grid"] if winner else None, "candidates": candidates}


def require_calibration(report):
    cells = report.get("cells", [])
    if len(cells) != 18 or {(c.get("channel"), c.get("refinement")) for c in cells} != {
            (a, r) for a in CHANNELS for r in REFINEMENTS}:
        raise ProtocolError("f_C requires the complete eighteen-cell static calibration")
    for c in cells:
        _finite((c["B_ref"], c["measured"]))
        if (c.get("status") != "CALIBRATED" or c.get("agrees_within_tolerance") is not True
                or not math.isclose(c["B_ref"], c["measured"], rel_tol=1e-6, abs_tol=1e-12)):
            raise ProtocolError("static collateral calibration did not pass")


def weighted_quantile(frequencies, numerator=95, denominator=100):
    """Exact nearest rank, without expanding repeated credited sites into RAM."""
    if (not frequencies or type(numerator) is not int or type(denominator) is not int
            or not 0 < numerator <= denominator):
        raise ProtocolError("invalid weighted quantile population")
    for value, count in frequencies.items():
        _finite((value,))
        if type(count) is not int or count <= 0:
            raise ProtocolError("quantile multiplicities must be positive integers")
    n = sum(frequencies.values())
    rank = (numerator * n + denominator - 1) // denominator
    cumulative = 0
    for value, count in sorted(frequencies.items()):
        cumulative += count
        if cumulative >= rank:
            return value
    raise AssertionError("nearest rank escaped its population")


class CollateralSelector:
    """f_C plus the exact weighted spread family for the selected threshold.

    Coverage histograms are descriptors; the original RunMaterial and membership
    rule also recover the per-site descriptor without storing a second huge matrix.
    """
    def __init__(self, sample, *, calibration):
        require_calibration(calibration)
        self.sample = tuple(sample)
        self.slices = {r: tuple(i for i, u in enumerate(sample) if _slice(r, u)) for r in REFINEMENTS}
        self.metrics = dict.fromkeys(REFINEMENTS, 0.0)
        self.spreads = {r: Counter() for r in REFINEMENTS}
        self.coverage = {(a, r): Counter() for a in CHANNELS for r in REFINEMENTS}
        self.records = 0

    def update(self, run):
        if len(run.levels) != len(self.sample) or len(run.success) != len(self.sample):
            raise ProtocolError("collateral material is not aligned with its bank")
        _finite(run.levels)
        cache = {}
        for arch in CHANNELS:
            domain = run.domains[arch]
            rows = run.consulted[arch]
            if len(set(domain)) != len(domain) or not set(rows).issubset(domain):
                raise ProtocolError("incidence is outside the run's credited domain")
            groups = Counter(rows.values())
            absent = len(domain) - len(rows)
            if absent:
                groups[()] += absent
            for excluded, multiplicity in groups.items():
                if excluded not in cache:
                    exclude = set(excluded)
                    stats = {}
                    for r in REFINEMENTS:
                        indices = [i for i in self.slices[r] if run.success[i] and i not in exclude]
                        values = tuple(run.levels[i] for i in indices)
                        stats[r] = (len(values), standard_error(values), sd(values) if values else None)
                    cache[excluded] = stats
                stats = cache[excluded]
                base_count, base_se, _ = stats[REFINEMENTS[0]]
                for r in REFINEMENTS:
                    n, se, spread = stats[r]
                    self.coverage[arch, r][base_count, n] += multiplicity
                    if spread is not None:
                        self.spreads[r][spread] += multiplicity
                    if se is None or base_se is None:
                        ratio = None
                    elif base_se == 0:
                        ratio = 1.0 if se == 0 else None
                    else:
                        ratio = se / base_se
                    if ratio is None or self.metrics[r] is None:
                        self.metrics[r] = None
                    else:
                        self.metrics[r] = max(self.metrics[r], ratio)
        self.records += 1

    def result(self):
        if not self.records:
            raise ProtocolError("f_C cannot select from an empty envelope")
        eligible = [r for r in REFINEMENTS if self.metrics[r] is not None and self.metrics[r] <= 1]
        winner = min(eligible, key=lambda r: (self.metrics[r], REFINEMENTS.index(r))) if eligible else None
        frequencies = self.spreads[winner] if winner else {}
        bound = weighted_quantile(frequencies) if frequencies and any(v > 0 for v in frequencies) else None
        return {"status": "ADMISSIBLE" if winner else "NO_ADMISSIBLE_REFINEMENT", "refinement": winner,
                "metrics": [{"refinement": r, "metric": self.metrics[r]} for r in REFINEMENTS],
                "collateral_bound": bound, "spread_population": sum(frequencies.values()),
                "coverage": [{"channel": a, "refinement": r,
                              "counts": [[base, n, count] for (base, n), count in sorted(hist.items())]}
                             for (a, r), hist in self.coverage.items()]}


def _midranks(values):
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        for index in order[i:j]:
            ranks[index] = (i + 1 + j) / 2
        i = j
    return ranks


def spearman(first, second):
    first, second = _finite(first), _finite(second)
    if len(first) != len(second):
        raise ProtocolError("Spearman needs aligned seed-level series")
    if len(set(first)) == 1 or len(set(second)) == 1:
        return None
    x, y = _midranks(first), _midranks(second)
    mx, my = mean(x), mean(y)
    covariance = left_to_right_sum((a - mx) * (b - my) for a, b in zip(x, y)) / len(x)
    return max(-1.0, min(1.0, covariance / (sd(x) * sd(y))))


def select_retention(curves, *, grid, pre_level):
    grid = tuple(grid)
    if len(grid) < 3 or grid[0] != 0 or any(type(e) is not int for e in grid) or tuple(sorted(set(grid))) != grid:
        raise ProtocolError("Retention selection requires at least three ordered checkpoints")
    curves = _curves_at(curves, grid[-1])
    utility = [_utility(c, grid, pre_level) for c in curves]
    candidates = []
    forms = (("RetentionAtH", RetentionAtH.value, {"H": grid[-1]}),
             ("LateWindowRetention", LateWindowRetention.value, {"H1": grid[-3], "H2": grid[-1]}))
    for name, form, parameters in forms:
        values = [form(tuple(c[e] for e in grid), grid, **parameters) for c in curves]
        stability = (max(values) - min(values)) / (max(abs(v) for v in values) + 1e-9)
        correlations = [spearman(values, [u.restricted_time for u in utility]),
                        spearman(values, [u.deficit_auc for u in utility])]
        redundancy = None if None in correlations else max(abs(r) for r in correlations)
        candidates.append({"form": name, "parameters": parameters, "values": values,
                           "stability": stability, "redundancy": redundancy,
                           "admissible": stability <= .10 and redundancy is not None and redundancy <= .9})
    eligible = [(i, c) for i, c in enumerate(candidates) if c["admissible"]]
    chosen = min(eligible, key=lambda pair: (pair[1]["redundancy"], pair[0]))[1] if eligible else None
    return {"status": "ADMISSIBLE" if chosen else "NO_ADMISSIBLE_RETENTION", "endpoint": chosen,
            "candidates": candidates}


def derive_design(records, *, seeds, cap, sample, pre_level, calibration):
    """Consume a verified master stream once; enforce every seed/episode coordinate.

    The artifact adapter must validate every shard before handing off this iterator.
    No computed selector becomes a published design until all selectors and every
    threshold succeed. This function never publishes or authorizes anything.
    """
    seeds, sample = tuple(seeds), tuple(sample)
    if (not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int or s < 0 for s in seeds)
            or type(cap) is not int or cap < 1 or len(sample) != 1024):
        raise ProtocolError("invalid master design envelope")
    _finite((pre_level,))
    iterator, curves = iter(records), []
    n_selector, c_selector = PrefixSelector(), CollateralSelector(sample, calibration=calibration)
    for seed in seeds:
        curve = []
        for episode in range(cap + 1):
            try:
                run = next(iterator)
            except StopIteration as exc:
                raise ProtocolError("missing master record at design selection") from exc
            if (run.seed, run.episode) != (seed, episode):
                raise ProtocolError("design input seed/episode order mismatch")
            n_selector.update(run.levels)
            c_selector.update(run)
            curve.append(mean(run.levels))
        curves.append(curve)
    sentinel = object()
    if next(iterator, sentinel) is not sentinel:
        raise ProtocolError("extra master record at design selection")
    times = [convergence_time(c, range(cap + 1)) for c in curves]
    horizon = select_horizon(times, acquisition_cap=cap)
    result = {"status": "ADMISSIBLE", "f_T": {**horizon, "convergence_times": times},
              "f_N": n_selector.result(), "f_C": c_selector.result(), "f_G": None, "f_R": None}
    for name in ("f_T", "f_N", "f_C"):
        if result[name]["status"] != "ADMISSIBLE":
            result["status"] = result[name]["status"]
            return result
    result["f_G"] = select_grid(curves, horizon=horizon["T"], pre_level=pre_level)
    if result["f_G"]["status"] != "ADMISSIBLE":
        result["status"] = result["f_G"]["status"]
        return result
    result["f_R"] = select_retention(curves, grid=result["f_G"]["grid"], pre_level=pre_level)
    result["status"] = result["f_R"]["status"]
    return result


def combine_design_and_thresholds(design, *, rmst_policy):
    """One payload or an explicit non-lock result; never a design-only F1 lock."""
    if design["status"] != "ADMISSIBLE":
        return {"status": design["status"], "lock": None}
    if not isinstance(rmst_policy, dict) or rmst_policy.get("ratified") is not True:
        return {"status": "UNRATIFIED_RMST_THRESHOLD", "lock": None}
    value = rmst_policy.get("value")
    _finite((value,))
    if value <= 0 or not isinstance(rmst_policy.get("rationale"), str) or not rmst_policy["rationale"].strip():
        raise ProtocolError("a ratified RMST policy needs a positive value and independent rationale")
    collateral = design["f_C"]["collateral_bound"]
    if collateral is None:
        return {"status": "NO_ADMISSIBLE_COLLATERAL_THRESHOLD", "lock": None}
    retention = design["f_R"]["endpoint"]
    delta = .25 * sd(retention["values"])
    if delta == 0:
        return {"status": "NO_ADMISSIBLE_RETENTION_THRESHOLD", "lock": None}
    configured = {"form": retention["form"], "parameters": retention["parameters"]}
    thresholds = [
        {"regime": "P", "statistic": "RMST", "value": value, "provenance": rmst_policy},
        {"regime": "P", "statistic": "DeficitAUC", "value": .01, "provenance": "inherited"},
        {"regime": "P", "statistic": "BehavioralCollateral", "value": collateral,
         "provenance": "nearest-rank-0.95-all-credited-sites"},
        {"regime": "P", "statistic": "Retention", "endpoint": configured, "value": delta,
         "provenance": "0.25-times-per-seed-population-sd"},
        {"regime": "T", "statistic": "RMST", "value": value, "provenance": "alias:P:RMST"},
        {"regime": "T", "statistic": "DeficitAUC", "value": .01, "provenance": "alias:P:DeficitAUC"},
    ]
    return {"status": "LOCKABLE", "lock": {
        "T": design["f_T"]["T"], "N_eval": design["f_N"]["N"], "grid": design["f_G"]["grid"],
        "refinement": design["f_C"]["refinement"], "retention": configured, "thresholds": thresholds}}
