"""Strict seed-level analysis for RFL-CausalChase v0.2 artifacts.

The v0.2 Word plan fixes the statistical unit as *seed*. This module first
reduces raw shocks/checkpoints inside each seed, then performs paired tests
only across aligned seeds. It intentionally refuses to silently intersect
seed sets, merge appended reruns, or use episode-level p-values.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rflcc.stats import cohens_dz, holm_correct, paired_bootstrap_ci, paired_sign_flip_test


DEFAULT_N_PERMUTATIONS = 10_000
DEFAULT_N_BOOTSTRAPS = 10_000
FULL_RFL = "full_rfl"
IMMEDIATE = "immediate"
STANDARD = "standard"
CF_ONLY = "cf_only"


class AnalysisDataError(ValueError):
    """Available data cannot support an auditable seed-level comparison."""


@dataclass
class MetricSource:
    """One source's values in `metric -> algorithm -> seed -> value` form."""

    name: str
    metrics: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    scenario_ids: dict[tuple[str, str], frozenset[str]] = field(default_factory=dict)
    metric_scenario_ids: dict[tuple[str, str, str], frozenset[str]] = field(default_factory=dict)
    defined_counts: dict[tuple[str, str, str], int] = field(default_factory=dict)
    censoring: dict[tuple[str, str, str], bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    def add(
        self,
        metric: str,
        algorithm: str,
        seed: str,
        value: Any,
        *,
        origin: str,
        censored: bool | None = None,
    ) -> None:
        number = _finite(value, f"{origin}: {metric} ({algorithm}, seed={seed})")
        target = self.metrics.setdefault(metric, {}).setdefault(algorithm, {})
        if seed in target:
            raise AnalysisDataError(
                f"{self.name}: duplicate seed-level {metric} for {algorithm}, seed={seed}; "
                "do not merge reruns or appended files."
            )
        target[seed] = number
        if censored is not None:
            self.censoring[(metric, algorithm, seed)] = censored


def _finite(value: Any, context: str) -> float:
    if value is None or value == "":
        raise AnalysisDataError(f"missing numeric value: {context}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AnalysisDataError(f"non-numeric value: {context}") from exc
    if not math.isfinite(number):
        raise AnalysisDataError(f"non-finite value: {context}")
    return number


def _seed_key(value: Any) -> str:
    """Pair `1`, `1.0`, and `"1"` as one seed, but reject booleans."""
    if value is None or isinstance(value, bool):
        raise AnalysisDataError(f"invalid seed value: {value!r}")
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, float):
        if not value.is_integer():
            raise AnalysisDataError(f"seed must be integral: {value!r}")
        return str(int(value))
    text = str(value).strip()
    if not text:
        raise AnalysisDataError("blank seed value")
    try:
        return str(int(text))
    except ValueError:
        return text


def _seed_sort_key(seed: str) -> tuple[int, int | str]:
    try:
        return (0, int(seed))
    except ValueError:
        return (1, seed)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnalysisDataError(f"cannot read JSON {path}: {exc}") from exc


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AnalysisDataError(f"cannot read JSONL {path}: {exc}") from exc
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AnalysisDataError(f"invalid JSONL at {path}:{line_no}") from exc
        if not isinstance(row, dict):
            raise AnalysisDataError(f"JSONL row must be an object at {path}:{line_no}")
        rows.append(row)
    if not rows:
        raise AnalysisDataError(f"empty JSONL source: {path}")
    return rows


def _run_metadata_for(artifact: Path) -> dict[str, str]:
    """Require the nearby v0.2 run metadata for A's non-per-seed rows."""
    candidates = (artifact.parent / "run_meta.json", artifact.parent.parent / "run_meta.json")
    for candidate in candidates:
        if not candidate.exists():
            continue
        payload = _read_json(candidate)
        if not isinstance(payload, dict):
            raise AnalysisDataError(f"run metadata is not an object: {candidate}")
        config_hash, git_commit = payload.get("config_hash"), payload.get("git_commit")
        if not config_hash or not git_commit:
            raise AnalysisDataError(f"run metadata lacks config_hash/git_commit: {candidate}")
        return {
            "run_meta": str(candidate),
            "config_hash": str(config_hash),
            "git_commit": str(git_commit),
        }
    raise AnalysisDataError(f"no run_meta.json with config_hash/git_commit near {artifact}")


def _per_seed_metadata(payload: dict[str, Any], path: Path) -> tuple[str, str]:
    config_hash, git_commit = payload.get("config_hash"), payload.get("git_commit")
    if not config_hash or not git_commit:
        raise AnalysisDataError(f"per-seed artifact lacks config_hash/git_commit: {path}")
    return str(config_hash), str(git_commit)


def _value(row: dict[str, Any], key: str) -> Any:
    """Read current v0.2 fields and tolerate the earlier flat smoke layout."""
    if key in row:
        return row[key]
    for container in ("metrics", "learner"):
        nested = row.get(container)
        if isinstance(nested, dict) and key in nested:
            return nested[key]
    return None


def _mean(values: Iterable[Any], context: str) -> float:
    numbers = [_finite(value, context) for value in values]
    if not numbers:
        raise AnalysisDataError(f"no numeric observations: {context}")
    return float(np.mean(numbers))


def _aggregate_update(
    name: str,
    grouped: dict[tuple[str, str], list[dict[str, Any]]],
    path: Path,
) -> MetricSource:
    source = MetricSource(name=name, files=[str(path)])
    metrics = (
        "attribution_error",
        "wur",
        "update_precision",
        "update_recall",
        "update_f1",
        "actual_wur",
        "correct_knowledge_damage",
        "wrong_knowledge_reinforcement",
        "ckd_h",
        "ckd_l",
        "wkr_h",
        "wkr_l",
        "cf_transitions",
    )
    for (seed, algorithm), rows in grouped.items():
        ids = [str(_value(row, "scenario_id")) for row in rows]
        if any(not scenario_id or scenario_id == "None" for scenario_id in ids):
            raise AnalysisDataError(f"{path}: blank scenario ID for seed={seed}, algorithm={algorithm}")
        if len(ids) != len(set(ids)):
            raise AnalysisDataError(
                f"{path}: repeated scenario ID for seed={seed}, algorithm={algorithm}; "
                "a repeated shock cannot receive extra weight."
            )
        source.scenario_ids[(algorithm, seed)] = frozenset(ids)
        for metric in metrics:
            selected = [
                (row, _value(row, metric)) for row in rows
                if _value(row, metric) is not None and _value(row, metric) != ""
            ]
            if not selected:
                continue
            # Some precision-style metrics are deliberately undefined for an
            # E-only no-update shock.  Their defined shock subset is retained
            # and must be identical between paired algorithms below; this is
            # safer than either assigning a fabricated zero or throwing away
            # the entire A-update panel because of a supporting metric.
            values = [value for _, value in selected]
            source.add(metric, algorithm, seed, _mean(values, f"{path}: {metric}"), origin=str(path))
            source.metric_scenario_ids[(metric, algorithm, seed)] = frozenset(
                str(_value(row, "scenario_id")) for row, _ in selected
            )
            source.defined_counts[(metric, algorithm, seed)] = len(selected)
    return source


def load_update_rows(path: str | Path) -> dict[str, MetricSource]:
    """Load A-update raw JSONL, including H-K's high-protection-only panel."""
    path = Path(path)
    all_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    high_protection_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for line_no, row in enumerate(_read_jsonl(path), start=1):
        seed = _value(row, "seed")
        algorithm = _value(row, "algorithm")
        scenario_id = _value(row, "scenario_id")
        if seed is None or algorithm is None or scenario_id is None:
            raise AnalysisDataError(f"{path}:{line_no}: A-update needs seed, algorithm, scenario_id")
        key = (_seed_key(seed), str(algorithm))
        all_rows.setdefault(key, []).append(row)
        if _value(row, "scenario_type") == "high_protection":
            high_protection_rows.setdefault(key, []).append(row)
    metadata = _run_metadata_for(path)
    sources = {"A_update": _aggregate_update("A_update", all_rows, path)}
    sources["A_update"].metadata = dict(metadata)
    if high_protection_rows:
        sources["A_update_high_protection"] = _aggregate_update(
            "A_update_high_protection", high_protection_rows, path
        )
        sources["A_update_high_protection"].metadata = dict(metadata)
    return sources


def load_attribution_seed_metrics(path: str | Path) -> dict[str, MetricSource]:
    """Load frozen A-attribution seed summaries and keep feedback conditions apart."""
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        raise AnalysisDataError(f"cannot read attribution CSV {path}: {exc}") from exc
    if not rows:
        raise AnalysisDataError(f"empty attribution CSV: {path}")
    metadata = _run_metadata_for(path)
    sources: dict[str, MetricSource] = {}
    metrics = ("ae_mean", "wur_mean", "coverage", "wrong_update_rate", "ffcr", "cf_transitions_mean")
    for row_no, row in enumerate(rows, start=2):
        condition, algorithm = row.get("condition"), row.get("algorithm")
        seed_value = row.get("seed_idx", row.get("seed"))
        if condition is None or algorithm is None or seed_value is None:
            raise AnalysisDataError(f"{path}:{row_no}: missing condition, algorithm, or seed_idx")
        source = sources.setdefault(
            f"A_attribution_{condition}",
            MetricSource(name=f"A_attribution_{condition}", files=[str(path)]),
        )
        source.metadata = dict(metadata)
        seed = _seed_key(seed_value)
        for metric in metrics:
            value = row.get(metric)
            if value is not None and value != "":
                source.add(metric, str(algorithm), seed, value, origin=f"{path}:{row_no}")
    return sources


def _nested_mean(rows: list[dict[str, Any]], metric: str, context: str) -> float | None:
    raw = [row.get(metric) for row in rows]
    values = [value for value in raw if value is not None and value != ""]
    if not values:
        return None
    if len(values) != len(raw):
        raise AnalysisDataError(f"partial {metric}: {context}")
    return _mean(values, f"{context}: {metric}")


def _curve_index(records: Any, context: str) -> dict[int, dict[str, Any]]:
    if not isinstance(records, list) or not records:
        raise AnalysisDataError(f"missing evaluation curve: {context}")
    by_episode: dict[int, dict[str, Any]] = {}
    for row in records:
        if not isinstance(row, dict) or "episode" not in row:
            raise AnalysisDataError(f"invalid evaluation row: {context}")
        episode = int(_finite(row["episode"], f"{context}: episode"))
        if episode in by_episode:
            raise AnalysisDataError(f"duplicate evaluation episode {episode}: {context}")
        by_episode[episode] = row
    return by_episode


def _auc_at_horizon(records: Any, horizon: int, context: str) -> float | None:
    """AUC_success,0:horizon; return None rather than inventing episode zero."""
    by_episode = _curve_index(records, context)
    if 0 not in by_episode or horizon not in by_episode:
        return None
    points = sorted(
        (episode, _finite(row.get("success"), f"{context}: success"))
        for episode, row in by_episode.items() if 0 <= episode <= horizon
    )
    if len(points) < 2:
        return None
    xs = np.asarray([point[0] for point in points], dtype=float)
    ys = np.asarray([point[1] for point in points], dtype=float)
    area = np.trapezoid(ys, xs) if hasattr(np, "trapezoid") else np.trapz(ys, xs)
    return float(area / horizon)


def _to90_three_checkpoints(records: Any, horizon: int, context: str) -> tuple[float, bool]:
    by_episode = _curve_index(records, context)
    consecutive = 0
    for episode in sorted(by_episode):
        success = _finite(by_episode[episode].get("success"), f"{context}: success")
        consecutive = consecutive + 1 if success >= 0.90 else 0
        if consecutive >= 3:
            return float(episode), False
    return float(horizon + 1), True


def load_transfer_results(paths: Iterable[str | Path]) -> MetricSource:
    """Reduce B-transfer shocks and recovery data to one value per seed."""
    paths = [Path(path) for path in paths]
    source = MetricSource(name="B_transfer", files=[str(path) for path in paths])
    seen_seeds: set[str] = set()
    config_hashes: set[str] = set()
    git_commits: set[str] = set()
    for path in paths:
        status_path = path.parent / "STATUS.json"
        if status_path.exists():
            status = _read_json(status_path)
            if status.get("primary_gate_status") in {"invalid_measurement", "invalid_probe_semantics"}:
                raise AnalysisDataError(
                    f"{path.parent}: historical transfer is marked invalid_probe_semantics; H-L is unavailable"
                )
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise AnalysisDataError(f"transfer output must be a JSON object: {path}")
        config_hash, git_commit = _per_seed_metadata(payload, path)
        config_hashes.add(config_hash)
        git_commits.add(git_commit)
        seed = _seed_key(payload.get("seed"))
        if seed in seen_seeds:
            raise AnalysisDataError(f"duplicate B-transfer seed {seed}; refuse to merge reruns")
        seen_seeds.add(seed)
        if payload.get("status") == "blocked_invalid_knowledge_probe":
            raise AnalysisDataError(
                f"B-transfer seed {seed} is blocked_invalid_knowledge_probe; H-L is unavailable"
            )
        if payload.get("status") != "completed" or not bool(payload.get("pretrain_gate")):
            raise AnalysisDataError(
                f"B-transfer seed {seed} failed/never passed its pretrain gate; downstream inference is blocked"
            )
        algorithms = payload.get("algorithms")
        if not isinstance(algorithms, dict) or not algorithms:
            raise AnalysisDataError(f"B-transfer seed {seed} has no algorithms")
        for algorithm, result in algorithms.items():
            if not isinstance(result, dict):
                raise AnalysisDataError(f"B-transfer seed {seed}, {algorithm}: invalid result")
            curve = result.get("recovery_eval_records")
            curve_index = _curve_index(curve, f"{path}, seed={seed}, algorithm={algorithm}")
            recovery = result.get("recovery_episode")
            horizon = max(curve_index)
            source.add(
                "recovery_episode", str(algorithm), seed, recovery, origin=str(path),
                censored=_finite(recovery, f"{path}: recovery_episode") > horizon,
            )
            for metric in ("knowledge_margin_pre_shock", "knowledge_margin_post_shock"):
                if result.get(metric) is not None:
                    source.add(metric, str(algorithm), seed, result[metric], origin=str(path))
            auc = _auc_at_horizon(curve, 500, f"{path}, seed={seed}, algorithm={algorithm}")
            if auc is not None:
                source.add("recovery_success_auc_0_500", str(algorithm), seed, auc, origin=str(path))
            elif horizon >= 500:
                source.notes.append(
                    f"{path.name} ({algorithm}, seed={seed}) lacks episode=0 success; "
                    "AUC_success,0:500 is intentionally unavailable."
                )
            if result.get("correct_knowledge_damage") is not None:
                source.add(
                    "correct_knowledge_damage", str(algorithm), seed,
                    result["correct_knowledge_damage"], origin=str(path),
                )
            if result.get("wrong_knowledge_reinforcement") is not None:
                source.add(
                    "wrong_knowledge_reinforcement", str(algorithm), seed,
                    result["wrong_knowledge_reinforcement"], origin=str(path),
                )
            shocks = result.get("shocks")
            if not isinstance(shocks, list) or not shocks:
                raise AnalysisDataError(f"B-transfer seed {seed}, {algorithm}: missing shocks")
            for metric in (
                "update_precision", "update_recall", "update_f1", "actual_wur",
                "cf_transitions",
            ):
                value = _nested_mean(shocks, metric, f"{path}, seed={seed}, algorithm={algorithm}")
                if value is not None:
                    source.add(metric, str(algorithm), seed, value, origin=str(path))
    if len(config_hashes) != 1 or len(git_commits) != 1:
        raise AnalysisDataError("B-transfer seed artifacts disagree on config_hash or git_commit")
    source.metadata = {
        "config_hash": next(iter(config_hashes)),
        "git_commit": next(iter(git_commits)),
    }
    return source


def load_online_results(paths: Iterable[str | Path]) -> MetricSource:
    """Reduce B-online runs and recompute Word-defined curve endpoints."""
    paths = [Path(path) for path in paths]
    source = MetricSource(name="B_online", files=[str(path) for path in paths])
    seen_seeds: set[str] = set()
    config_hashes: set[str] = set()
    git_commits: set[str] = set()
    for path in paths:
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise AnalysisDataError(f"online output must be a JSON object: {path}")
        config_hash, git_commit = _per_seed_metadata(payload, path)
        config_hashes.add(config_hash)
        git_commits.add(git_commit)
        seed = _seed_key(payload.get("seed"))
        if seed in seen_seeds:
            raise AnalysisDataError(f"duplicate B-online seed {seed}; refuse to merge reruns")
        seen_seeds.add(seed)
        horizon = int(_finite(payload.get("episodes"), f"{path}: episodes"))
        algorithms = payload.get("algorithms")
        if not isinstance(algorithms, dict) or not algorithms:
            raise AnalysisDataError(f"B-online seed {seed} has no algorithms")
        for algorithm, result in algorithms.items():
            if not isinstance(result, dict):
                raise AnalysisDataError(f"B-online seed {seed}, {algorithm}: invalid result")
            name = str(algorithm)
            for metric in ("final_success", "final_safe_option", "final_return", "total_bellman", "wall_s"):
                if result.get(metric) is not None:
                    source.add(metric, name, seed, result[metric], origin=str(path))
            curve = result.get("eval_records")
            to90, censored = _to90_three_checkpoints(curve, horizon, f"{path}, seed={seed}, algorithm={name}")
            source.add("episodes_to_90_3checkpoints", name, seed, to90, origin=str(path), censored=censored)
            auc = _auc_at_horizon(curve, 3000, f"{path}, seed={seed}, algorithm={name}")
            if auc is not None:
                source.add("success_auc_0_3000", name, seed, auc, origin=str(path))
            elif horizon >= 3000:
                source.notes.append(
                    f"{path.name} ({name}, seed={seed}) lacks episode=0 success; "
                    "AUC_success,0:3000 is intentionally unavailable."
                )
    if len(config_hashes) != 1 or len(git_commits) != 1:
        raise AnalysisDataError("B-online seed artifacts disagree on config_hash or git_commit")
    source.metadata = {
        "config_hash": next(iter(config_hashes)),
        "git_commit": next(iter(git_commits)),
    }
    return source


def _one_or_none(paths: list[Path], label: str) -> Path | None:
    if not paths:
        return None
    if len(paths) > 1:
        raise AnalysisDataError(
            f"ambiguous {label} inputs: {', '.join(str(path) for path in paths)}; pass a narrower --dir"
        )
    return paths[0]


def discover_sources(path: str | Path) -> dict[str, MetricSource]:
    """Discover one coherent v0.2 analysis panel without mixing separate reruns."""
    root = Path(path)
    if not root.exists():
        raise AnalysisDataError(f"input does not exist: {root}")
    if root.is_file():
        if root.name == "update_rows.jsonl":
            return load_update_rows(root)
        if root.name == "seed_metrics.csv" and root.parent.name == "attribution":
            return load_attribution_seed_metrics(root)
        if root.name.startswith("transfer_seed") and root.suffix == ".json":
            return {"B_transfer": load_transfer_results([root])}
        if root.name.startswith("online_seed") and root.suffix == ".json":
            return {"B_online": load_online_results([root])}
        raise AnalysisDataError(f"unsupported v0.2 analysis file: {root}")
    sources: dict[str, MetricSource] = {}
    update = _one_or_none(sorted(root.rglob("update_rows.jsonl")), "A-update")
    attribution = _one_or_none(
        sorted(item for item in root.rglob("seed_metrics.csv") if item.parent.name == "attribution"),
        "A-attribution",
    )
    transfer = sorted(root.rglob("transfer_seed*.json"))
    online = sorted(root.rglob("online_seed*.json"))
    if update is not None:
        sources.update(load_update_rows(update))
    if attribution is not None:
        sources.update(load_attribution_seed_metrics(attribution))
    if transfer:
        sources["B_transfer"] = load_transfer_results(transfer)
    if online:
        sources["B_online"] = load_online_results(online)
    if not sources:
        raise AnalysisDataError(
            f"no v0.2 outputs beneath {root}; expected A update/attribution or B transfer/online artifacts"
        )
    return sources


def _rng(comparison_id: str, kind: str) -> np.random.RandomState:
    digest = hashlib.sha256(f"{comparison_id}:{kind}".encode("utf-8")).digest()
    return np.random.RandomState(int.from_bytes(digest[:4], "big"))


def aligned_pairs(
    source: MetricSource,
    metric: str,
    left_algorithm: str,
    right_algorithm: str,
    *,
    right_scale: float = 1.0,
) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Return paired vectors only if all seeds (and A shocks) are identical."""
    values = source.metrics.get(metric)
    if values is None:
        raise AnalysisDataError(f"{source.name}: metric unavailable: {metric}")
    left, right = values.get(left_algorithm), values.get(right_algorithm)
    if not left or not right:
        missing = [name for name, value in ((left_algorithm, left), (right_algorithm, right)) if not value]
        raise AnalysisDataError(f"{source.name}: {metric} missing for {', '.join(missing)}")
    left_seeds, right_seeds = set(left), set(right)
    if left_seeds != right_seeds:
        raise AnalysisDataError(
            f"{source.name}: unaligned seeds for {metric}; "
            f"left-only={sorted(left_seeds - right_seeds, key=_seed_sort_key)}, "
            f"right-only={sorted(right_seeds - left_seeds, key=_seed_sort_key)}"
        )
    seeds = sorted(left_seeds, key=_seed_sort_key)
    for seed in seeds:
        left_scenarios = source.metric_scenario_ids.get(
            (metric, left_algorithm, seed), source.scenario_ids.get((left_algorithm, seed))
        )
        right_scenarios = source.metric_scenario_ids.get(
            (metric, right_algorithm, seed), source.scenario_ids.get((right_algorithm, seed))
        )
        if left_scenarios is not None or right_scenarios is not None:
            if left_scenarios != right_scenarios:
                raise AnalysisDataError(
                    f"{source.name}: unaligned shock scenarios for seed={seed}, "
                    f"{left_algorithm} vs {right_algorithm}"
                )
    return (
        seeds,
        np.asarray([left[seed] for seed in seeds], dtype=float),
        np.asarray([right[seed] * right_scale for seed in seeds], dtype=float),
    )


def paired_comparison(
    *,
    comparison_id: str,
    source: MetricSource,
    metric: str,
    left_algorithm: str,
    right_algorithm: str,
    n_permutations: int = DEFAULT_N_PERMUTATIONS,
    n_bootstraps: int = DEFAULT_N_BOOTSTRAPS,
    right_scale: float = 1.0,
    primary: bool = False,
    endpoint: str | None = None,
    threshold: float | None = None,
    rule: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Compute one auditable paired comparison from a fully aligned panel."""
    record: dict[str, Any] = {
        "comparison_id": comparison_id,
        "endpoint": endpoint or metric,
        "source": source.name,
        "metric": metric,
        "left_algorithm": left_algorithm,
        "right_algorithm": right_algorithm,
        "right_scale": right_scale,
        "statistical_unit": "seed",
        "primary": primary,
        "threshold": threshold,
        "rule": rule,
        "note": note,
        "status": "complete",
        "decision": "not_assessed",
        "holm_adjusted_p": None,
    }
    seeds, x, y = aligned_pairs(source, metric, left_algorithm, right_algorithm, right_scale=right_scale)
    record.update({
        "n_seeds": len(seeds),
        "seeds": seeds,
        "mean_left": float(x.mean()),
        "mean_right": float(y.mean()),
        "mean_difference": float((x - y).mean()),
        "left_censored_seeds": sum(source.censoring.get((metric, left_algorithm, seed), False) for seed in seeds),
        "right_censored_seeds": sum(source.censoring.get((metric, right_algorithm, seed), False) for seed in seeds),
        "defined_count_left": sum(source.defined_counts.get((metric, left_algorithm, seed), 1) for seed in seeds),
        "defined_count_right": sum(source.defined_counts.get((metric, right_algorithm, seed), 1) for seed in seeds),
    })
    if right_scale != 1.0:
        raw_right = np.asarray([source.metrics[metric][right_algorithm][seed] for seed in seeds], dtype=float)
        record["mean_right_unscaled"] = float(raw_right.mean())
        record["mean_ratio_left_to_right_unscaled"] = (
            float(np.mean(x / raw_right)) if np.all(raw_right != 0.0) else None
        )
    if len(seeds) < 2:
        record.update({
            "status": "insufficient_seeds",
            "reason": "paired inference requires at least two aligned seeds",
            "p_sign_flip": None,
            "bootstrap_ci_95": None,
            "cohens_dz": None,
        })
        return record
    ci_low, ci_high = paired_bootstrap_ci(
        x, y, n_resample=n_bootstraps, rng=_rng(comparison_id, "bootstrap")
    )
    record.update({
        "p_sign_flip": paired_sign_flip_test(
            x, y, n_perm=n_permutations, rng=_rng(comparison_id, "sign_flip")
        ),
        "bootstrap_ci_95": [ci_low, ci_high],
        "cohens_dz": cohens_dz(x - y),
    })
    return record


def _unavailable(
    comparison_id: str,
    endpoint: str,
    source: str,
    metric: str,
    *,
    primary: bool,
    reason: str,
    threshold: float | None = None,
    rule: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "comparison_id": comparison_id,
        "endpoint": endpoint,
        "source": source,
        "metric": metric,
        "statistical_unit": "seed",
        "primary": primary,
        "threshold": threshold,
        "rule": rule,
        "note": note,
        "status": "unavailable",
        "reason": reason,
        "n_seeds": 0,
        "seeds": [],
        "mean_left": None,
        "mean_right": None,
        "mean_difference": None,
        "p_sign_flip": None,
        "holm_adjusted_p": None,
        "bootstrap_ci_95": None,
        "cohens_dz": None,
        "decision": "not_assessed",
    }


def _compare(
    sources: dict[str, MetricSource],
    *,
    comparison_id: str,
    endpoint: str,
    source_name: str,
    metric: str,
    left: str,
    right: str,
    n_permutations: int,
    n_bootstraps: int,
    primary: bool = False,
    right_scale: float = 1.0,
    threshold: float | None = None,
    rule: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    source = sources.get(source_name)
    if source is None:
        return _unavailable(
            comparison_id, endpoint, source_name, metric, primary=primary,
            reason=f"source not supplied: {source_name}", threshold=threshold, rule=rule, note=note,
        )
    try:
        return paired_comparison(
            comparison_id=comparison_id, source=source, metric=metric,
            left_algorithm=left, right_algorithm=right,
            n_permutations=n_permutations, n_bootstraps=n_bootstraps,
            right_scale=right_scale, primary=primary, endpoint=endpoint,
            threshold=threshold, rule=rule, note=note,
        )
    except AnalysisDataError as exc:
        record = _unavailable(
            comparison_id, endpoint, source_name, metric, primary=primary,
            reason=str(exc), threshold=threshold, rule=rule, note=note,
        )
        record["status"] = "invalid_input"
        return record


def _apply_holm_and_decisions(records: list[dict[str, Any]]) -> None:
    primary_indices = [
        index for index, record in enumerate(records)
        if record["primary"] and record["status"] == "complete" and record.get("p_sign_flip") is not None
    ]
    if primary_indices:
        adjusted = holm_correct([records[index]["p_sign_flip"] for index in primary_indices])
        for index, value in zip(primary_indices, adjusted):
            records[index]["holm_adjusted_p"] = value
    for record in records:
        if record["status"] != "complete":
            continue
        ci = record.get("bootstrap_ci_95")
        if ci is None:
            continue
        low, high = ci
        rule = record.get("rule")
        if rule == "lower":
            passed = record["mean_difference"] <= float(record["threshold"]) and high < 0.0
        elif rule == "higher":
            passed = record["mean_difference"] >= float(record["threshold"]) and low > 0.0
        elif rule == "noninferior":
            passed = low > float(record["threshold"])
        elif rule == "recovery_20pct":
            passed = record["mean_difference"] <= 0.0 and high < 0.0
        else:
            record["decision"] = "descriptive"
            continue
        if record["primary"]:
            passed = passed and record.get("holm_adjusted_p") is not None and record["holm_adjusted_p"] < 0.05
        record["decision"] = "PASS" if passed else "FAIL"


def analyze_sources(
    sources: dict[str, MetricSource],
    *,
    n_permutations: int = DEFAULT_N_PERMUTATIONS,
    n_bootstraps: int = DEFAULT_N_BOOTSTRAPS,
) -> dict[str, Any]:
    """Produce frozen endpoints plus supporting diagnostics."""
    if n_permutations <= 0 or n_bootstraps <= 0:
        raise ValueError("n_permutations and n_bootstraps must be positive")
    config_hashes = {source.metadata.get("config_hash") for source in sources.values() if source.metadata.get("config_hash")}
    git_commits = {source.metadata.get("git_commit") for source in sources.values() if source.metadata.get("git_commit")}
    if len(config_hashes) > 1 or len(git_commits) > 1:
        raise AnalysisDataError(
            "refusing to combine v0.2 artifacts from different config hashes or git commits"
        )
    records = [
        _compare(
            sources, comparison_id="H-A", endpoint="ΔAE", source_name="A_attribution_symmetric",
            metric="ae_mean", left=FULL_RFL, right=IMMEDIATE, n_permutations=n_permutations,
            n_bootstraps=n_bootstraps, primary=True, threshold=-0.08, rule="lower",
            note="PASS: ΔAE <= -0.08 and paired 95% CI < 0",
        ),
        _compare(
            sources, comparison_id="H-U", endpoint="ΔF1U", source_name="A_update",
            metric="update_f1", left=FULL_RFL, right=IMMEDIATE, n_permutations=n_permutations,
            n_bootstraps=n_bootstraps, primary=True, threshold=0.10, rule="higher",
            note="PASS: ΔF1U >= +0.10 and paired 95% CI > 0",
        ),
        _compare(
            sources, comparison_id="H-K", endpoint="ΔCKD (high protection, H module)",
            source_name="A_update_high_protection", metric="ckd_h", left=FULL_RFL,
            right=IMMEDIATE, n_permutations=n_permutations, n_bootstraps=n_bootstraps,
            primary=True, threshold=-0.10, rule="lower",
            note="PASS: high-level CKD Δ <= -0.10 and paired 95% CI < 0",
        ),
        _compare(
            sources, comparison_id="H-L", endpoint="RecoveryEpisodes (Full - 0.8×Immediate)",
            source_name="B_transfer", metric="recovery_episode", left=FULL_RFL,
            right=IMMEDIATE, n_permutations=n_permutations, n_bootstraps=n_bootstraps,
            primary=True, right_scale=0.8, threshold=0.0, rule="recovery_20pct",
            note="PASS: Full-RFL is at least 20% faster and the paired CI supports that direction",
        ),
        _compare(sources, comparison_id="A-attribution-WUR", endpoint="WUR", source_name="A_attribution_symmetric",
                 metric="wur_mean", left=FULL_RFL, right=IMMEDIATE, n_permutations=n_permutations, n_bootstraps=n_bootstraps),
        _compare(sources, comparison_id="A-attribution-CF-cost", endpoint="CF cost", source_name="A_attribution_symmetric",
                 metric="cf_transitions_mean", left=FULL_RFL, right=CF_ONLY, n_permutations=n_permutations, n_bootstraps=n_bootstraps),
        _compare(sources, comparison_id="A-update-precision", endpoint="Update precision", source_name="A_update",
                 metric="update_precision", left=FULL_RFL, right=IMMEDIATE, n_permutations=n_permutations, n_bootstraps=n_bootstraps),
        _compare(sources, comparison_id="A-update-recall", endpoint="Update recall", source_name="A_update",
                 metric="update_recall", left=FULL_RFL, right=IMMEDIATE, n_permutations=n_permutations, n_bootstraps=n_bootstraps),
        _compare(sources, comparison_id="A-update-WKR", endpoint="WKR", source_name="A_update",
                 metric="wrong_knowledge_reinforcement", left=FULL_RFL, right=IMMEDIATE, n_permutations=n_permutations, n_bootstraps=n_bootstraps),
        _compare(sources, comparison_id="A-update-CF-cost", endpoint="CF cost", source_name="A_update",
                 metric="cf_transitions", left=FULL_RFL, right=CF_ONLY, n_permutations=n_permutations, n_bootstraps=n_bootstraps),
        _compare(sources, comparison_id="B-transfer-F1U", endpoint="Update F1", source_name="B_transfer",
                 metric="update_f1", left=FULL_RFL, right=IMMEDIATE, n_permutations=n_permutations, n_bootstraps=n_bootstraps),
        _compare(sources, comparison_id="B-transfer-CKD", endpoint="CKD", source_name="B_transfer",
                 metric="correct_knowledge_damage", left=FULL_RFL, right=IMMEDIATE, n_permutations=n_permutations, n_bootstraps=n_bootstraps),
        _compare(sources, comparison_id="B-transfer-WKR", endpoint="WKR", source_name="B_transfer",
                 metric="wrong_knowledge_reinforcement", left=FULL_RFL, right=IMMEDIATE, n_permutations=n_permutations, n_bootstraps=n_bootstraps),
        _compare(sources, comparison_id="B-transfer-CF-cost", endpoint="CF cost", source_name="B_transfer",
                 metric="cf_transitions", left=FULL_RFL, right=CF_ONLY, n_permutations=n_permutations, n_bootstraps=n_bootstraps),
        _compare(
            sources, comparison_id="B-transfer-AUC", endpoint="AUC_success,0:500", source_name="B_transfer",
            metric="recovery_success_auc_0_500", left=FULL_RFL, right=IMMEDIATE,
            n_permutations=n_permutations, n_bootstraps=n_bootstraps, threshold=0.03, rule="higher",
            note="Supporting H-L endpoint; unavailable until recovery logs contain episode=0 success.",
        ),
        _compare(
            sources, comparison_id="B-online-AUC", endpoint="AUC_success,0:3000", source_name="B_online",
            metric="success_auc_0_3000", left=FULL_RFL, right=STANDARD,
            n_permutations=n_permutations, n_bootstraps=n_bootstraps,
            note="Supporting online learning endpoint; recomputed from raw seed curves.",
        ),
        _compare(
            sources, comparison_id="B-online-To90", endpoint="EpisodesTo90 (3 checkpoints)", source_name="B_online",
            metric="episodes_to_90_3checkpoints", left=FULL_RFL, right=STANDARD,
            n_permutations=n_permutations, n_bootstraps=n_bootstraps,
            note="Supporting right-censored endpoint; censor counts are reported.",
        ),
        _compare(
            sources, comparison_id="B-online-noninferiority", endpoint="FinalSuccess non-inferiority",
            source_name="B_online", metric="final_success", left=FULL_RFL, right=STANDARD,
            n_permutations=n_permutations, n_bootstraps=n_bootstraps, threshold=-0.05,
            rule="noninferior", note="PASS: lower paired 95% CI exceeds -0.05.",
        ),
    ]
    _apply_holm_and_decisions(records)
    primary = [record for record in records if record["primary"]]
    return {
        "analysis_schema_version": "0.2.1",
        "statistical_unit": "seed",
        "n_permutations": n_permutations,
        "n_bootstraps": n_bootstraps,
        "holm_family": [record["comparison_id"] for record in primary if record["status"] == "complete"],
        "source_files": {name: source.files for name, source in sorted(sources.items())},
        "source_metadata": {name: source.metadata for name, source in sorted(sources.items())},
        "analysis_git_commit": os.popen("git rev-parse HEAD").read().strip() or "unavailable",
        "source_notes": {name: source.notes for name, source in sorted(sources.items()) if source.notes},
        "records": records,
        "primary_gate": {
            "all_available": all(record["status"] == "complete" for record in primary),
            "all_pass": bool(primary) and all(record["decision"] == "PASS" for record in primary),
        },
    }


def analyze_directory(
    path: str | Path,
    *,
    n_permutations: int = DEFAULT_N_PERMUTATIONS,
    n_bootstraps: int = DEFAULT_N_BOOTSTRAPS,
) -> dict[str, Any]:
    return analyze_sources(
        discover_sources(path), n_permutations=n_permutations, n_bootstraps=n_bootstraps
    )


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (list, dict)) else str(value)


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# RFL-CausalChase v0.2 seed-level analysis",
        "",
        f"- Statistical unit: `{report['statistical_unit']}`; no episode-level p-values.",
        f"- Paired sign-flip permutations: `{report['n_permutations']}`.",
        f"- Paired bootstrap resamples: `{report['n_bootstraps']}`.",
        f"- Holm family: `{', '.join(report['holm_family']) or 'none available'}`.",
        "",
        "| Endpoint | n seeds | Mean Δ | 95% paired CI | sign-flip p | Holm p | d_z | Decision |",
        "|---|---:|---:|---|---:|---:|---:|---|",
    ]
    for record in report["records"]:
        ci = record.get("bootstrap_ci_95")
        ci_text = "" if ci is None else f"[{ci[0]:.4g}, {ci[1]:.4g}]"
        p = record.get("p_sign_flip")
        holm = record.get("holm_adjusted_p")
        dz = record.get("cohens_dz")
        decision = record["decision"] if record["status"] == "complete" else record["status"]
        lines.append(
            "| {endpoint} | {n} | {delta} | {ci} | {p} | {holm} | {dz} | {decision} |".format(
                endpoint=str(record["endpoint"]).replace("|", "\\|"),
                n=record["n_seeds"],
                delta="" if record["mean_difference"] is None else f"{record['mean_difference']:.4g}",
                ci=ci_text,
                p="" if p is None else f"{p:.4g}",
                holm="" if holm is None else f"{holm:.4g}",
                dz="" if dz is None else f"{dz:.4g}",
                decision=decision,
            )
        )
    primary_gate = report["primary_gate"]
    gate_text = (
        "PASS"
        if primary_gate["all_pass"]
        else "FAIL"
        if primary_gate["all_available"]
        else "not supported"
    )
    lines.extend([
        "",
        "Primary gate: " + gate_text,
        "",
        "Unavailable/invalid rows are not null results. Their exact data-integrity reason is in `analysis_v02.json`.",
    ])
    return "\n".join(lines) + "\n"


def write_analysis_outputs(report: dict[str, Any], output: str | Path) -> dict[str, Path]:
    """Write a JSON report, flat CSV table, and concise Markdown table."""
    output = Path(output)
    if output.suffix:
        json_path = output
        base = output.with_suffix("")
        csv_path, markdown_path = base.with_suffix(".csv"), base.with_suffix(".md")
    else:
        json_path = output / "analysis_v02.json"
        csv_path = output / "analysis_v02.csv"
        markdown_path = output / "analysis_v02.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = (
        "comparison_id", "endpoint", "source", "metric", "left_algorithm", "right_algorithm",
        "right_scale", "statistical_unit", "primary", "status", "reason", "n_seeds", "seeds",
        "mean_left", "mean_right", "mean_right_unscaled", "mean_ratio_left_to_right_unscaled",
        "mean_difference", "left_censored_seeds", "right_censored_seeds",
        "defined_count_left", "defined_count_right", "bootstrap_ci_95",
        "p_sign_flip", "holm_adjusted_p", "cohens_dz", "threshold", "rule", "decision", "note",
    )
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in report["records"]:
            writer.writerow({field: _csv_value(record.get(field)) for field in fields})
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "markdown": markdown_path}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strict seed-level RFL-CausalChase v0.2 analysis")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--dir", help="v0.2 output directory")
    selector.add_argument("--input", help="one supported artifact file; compatibility with the old CLI")
    parser.add_argument("--output", default=None, help="JSON output path; CSV/Markdown siblings are written")
    parser.add_argument("--n-permutations", type=int, default=DEFAULT_N_PERMUTATIONS)
    parser.add_argument("--n-bootstraps", type=int, default=DEFAULT_N_BOOTSTRAPS)
    parser.add_argument(
        "--report-only", action="store_true",
        help="write a descriptive report but return 0 even when a valid primary gate fails",
    )
    args = parser.parse_args(argv)
    input_path = Path(args.dir or args.input)
    try:
        report = analyze_directory(
            input_path, n_permutations=args.n_permutations, n_bootstraps=args.n_bootstraps
        )
        output = (
            Path(args.output) if args.output else
            (input_path / "analysis_v02.json" if input_path.is_dir() else input_path.parent / "analysis_v02.json")
        )
        written = write_analysis_outputs(report, output)
    except (AnalysisDataError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 3
    print(json.dumps({
        "primary_gate": report["primary_gate"],
        "outputs": {name: str(path) for name, path in written.items()},
    }, ensure_ascii=False))
    return 0 if args.report_only or report["primary_gate"]["all_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
