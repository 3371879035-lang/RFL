"""Independent artifact checks for the v0.2 RFL-CausalChase runs.

These checks deliberately do not call the learner or the oracle.  They inspect
the artifacts emitted by the experiment entry points so a green command exit is
not mistaken for evidence that the prescribed audit trail was produced.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


# 0.2.1 is the first artifact schema that contains protected-probe evidence.
# Readers retain 0.2.0 support only to inspect/label historical evidence; new
# runners always emit 0.2.1.
V02_SCHEMA_VERSION = "0.2.1"
V02_COMPATIBLE_SCHEMA_VERSIONS = frozenset({"0.2.0", V02_SCHEMA_VERSION})
_ARTIFACT_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "schemas" / "v02_artifact.schema.json").read_text(encoding="utf-8")
)
_ARTIFACT_VALIDATOR = Draft202012Validator(_ARTIFACT_SCHEMA)


class OutputIntegrityError(RuntimeError):
    """Raised when a v0.2 result directory cannot support an audit claim."""


def canonical_config_hash(config: dict[str, Any]) -> str:
    """Match the canonical JSON hash written by the v0.2 entry points."""
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prepare_fresh_v02_output_dir(outdir: str | Path, *, project_root: str | Path) -> Path:
    """Create a new, project-local v0.2 output directory without overwriting data."""
    project_root = Path(project_root).resolve()
    outputs_root = (project_root / "outputs").resolve()
    target = Path(outdir).resolve()
    if not target.is_relative_to(outputs_root):
        raise OutputIntegrityError(
            f"output directory must be below {outputs_root}, got {target}"
        )
    if not target.name.startswith("v02_"):
        raise OutputIntegrityError(
            f"new output directory must start with 'v02_': {target.name}"
        )
    if target.exists() and any(target.iterdir()):
        raise OutputIntegrityError(
            f"refusing to append to existing artifacts: {target}"
        )
    target.mkdir(parents=True, exist_ok=True)
    return target


def _fail(context: str, message: str) -> None:
    raise OutputIntegrityError(f"{context}: {message}")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        _fail(str(path), "missing JSON artifact")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(str(path), f"invalid JSON: {exc}")
    if not isinstance(value, dict):
        _fail(str(path), "expected a JSON object")
    return value


def _validate_artifact_schema(value: dict[str, Any], path: Path) -> None:
    """Run the versioned JSON Schema before detailed semantic checks."""
    errors = sorted(_ARTIFACT_VALIDATOR.iter_errors(value), key=lambda error: list(error.path))
    if errors:
        _fail(str(path), f"JSON schema violation: {errors[0].message}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        _fail(str(path), "missing JSONL artifact")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            _fail(str(path), f"blank JSONL line {number}")
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            _fail(str(path), f"invalid JSONL line {number}: {exc}")
        if not isinstance(value, dict):
            _fail(str(path), f"JSONL line {number} is not an object")
        rows.append(value)
    if not rows:
        _fail(str(path), "contains no rows")
    return rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        _fail(str(path), "missing CSV artifact")
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        _fail(str(path), "contains no data rows")
    return rows


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _assert_hash(value: Any, context: str, field: str) -> None:
    if not isinstance(value, str) or len(value) < 7:
        _fail(context, f"{field} is absent or not a usable hash")


def _assert_schema_version(value: Any, context: str) -> None:
    if value not in V02_COMPATIBLE_SCHEMA_VERSIONS:
        _fail(context, f"schema_version must be one of {sorted(V02_COMPATIBLE_SCHEMA_VERSIONS)}")


def _assert_meta(meta: dict[str, Any], cfg: dict[str, Any], *, stage: str, seeds: int, context: str) -> None:
    _assert_schema_version(meta.get("schema_version"), context)
    if meta.get("stage") != stage:
        _fail(context, f"stage must be {stage!r}, got {meta.get('stage')!r}")
    if meta.get("seeds") != seeds:
        _fail(context, f"seeds must be {seeds}, got {meta.get('seeds')!r}")
    expected_hash = canonical_config_hash(cfg)
    if meta.get("config_hash") != expected_hash:
        _fail(context, "config_hash does not match the supplied frozen config")
    _assert_hash(meta.get("git_commit"), context, "git_commit")


def _contains_oracle_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any("oracle" in str(key).lower() or _contains_oracle_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_oracle_key(item) for item in value)
    return False


def _validate_receipt_mass(
    actual_update: Any, receipts: Any, *, context: str,
) -> None:
    if not isinstance(actual_update, dict):
        _fail(context, "actual_update must be a module-to-mass object")
    if not isinstance(receipts, list):
        _fail(context, "applied_updates must be a list")
    actual_total = 0.0
    for module, mass in actual_update.items():
        if module not in {"H", "L", "E"} or not _finite_number(mass) or float(mass) < 0:
            _fail(context, f"invalid actual update mass for module {module!r}")
        actual_total += float(mass)
    receipt_total = 0.0
    for index, receipt in enumerate(receipts):
        if not isinstance(receipt, dict):
            _fail(context, f"receipt {index} is not an object")
        if receipt.get("module") not in {"H", "L"}:
            _fail(context, f"receipt {index} has invalid module")
        delta = receipt.get("delta_q")
        if not _finite_number(delta):
            _fail(context, f"receipt {index} has non-finite delta_q")
        receipt_total += abs(float(delta))
    if not math.isclose(receipt_total, actual_total, rel_tol=0.0, abs_tol=1e-12):
        _fail(
            context,
            f"receipt mass {receipt_total:.16g} differs from actual_update {actual_total:.16g}",
        )


def validate_v02_update_record(record: dict[str, Any], *, context: str = "episode") -> None:
    """Validate the strict v0.2 update-record shape and oracle partition."""
    required = {
        "schema_version", "run_id", "seed", "scenario_id", "experiment", "algorithm",
        "condition", "environment", "factual", "feedback", "learner", "evaluator_only",
        "metrics", "compute",
    }
    if set(record) != required:
        _fail(context, f"top-level fields differ from episode schema: {sorted(set(record) ^ required)}")
    _assert_schema_version(record.get("schema_version"), context)
    if record.get("experiment") != "A-update":
        _fail(context, "expected an A-update record")
    if not isinstance(record.get("algorithm"), str) or not record["algorithm"]:
        _fail(context, "missing algorithm")

    environment = record["environment"]
    factual = record["factual"]
    feedback = record["feedback"]
    learner = record["learner"]
    evaluator = record["evaluator_only"]
    metrics = record["metrics"]
    if not isinstance(environment, dict) or set(environment) != {"noise_tape_hash", "monster_start_lane", "horizon"}:
        _fail(context, "environment namespace is malformed")
    if not isinstance(factual, dict) or set(factual) != {"option", "terminal_type", "discounted_return"}:
        _fail(context, "factual namespace is malformed")
    if not isinstance(feedback, dict) or set(feedback) != {"observed", "is_false"}:
        _fail(context, "feedback namespace is malformed")
    if not isinstance(learner, dict) or not {"q_seq", "q_pre", "responsibility"}.issubset(learner):
        _fail(context, "learner namespace lacks required fields")
    if not isinstance(evaluator, dict) or not {"oracle_primary", "oracle_R"}.issubset(evaluator):
        _fail(context, "evaluator-only namespace lacks oracle labels")
    if not isinstance(metrics, dict):
        _fail(context, "metrics namespace is malformed")

    # Oracle labels are allowed only in evaluator_only.  Oracle-Update is an
    # evaluator upper bound, not permission to silently place R* in learner
    # state; the record must use an empty learner responsibility for it.
    if _contains_oracle_key(learner):
        _fail(context, "learner namespace contains oracle-labelled data")
    if record["algorithm"] == "oracle_update" and learner.get("responsibility") not in ({}, None):
        _fail(context, "Oracle-Update must not store evaluator R* as learner responsibility")
    if record["algorithm"] == "oracle_update" and metrics.get("oracle_update_upper_bound") is not True:
        _fail(context, "Oracle-Update is not explicitly marked as an evaluator upper bound")

    _validate_receipt_mass(
        metrics.get("actual_update"), metrics.get("applied_updates"), context=context,
    )
    for field in (
        "update_precision", "update_recall", "update_f1", "actual_wur",
        "correct_knowledge_damage", "wrong_knowledge_reinforcement",
    ):
        value = metrics.get(field)
        if value is not None and not _finite_number(value):
            _fail(context, f"{field} is not finite")


def _require_meta(outdir: Path, cfg: dict[str, Any], *, stage: str, seeds: int) -> dict[str, Any]:
    meta = _read_json(outdir / "run_meta.json")
    _assert_meta(meta, cfg, stage=stage, seeds=seeds, context=str(outdir / "run_meta.json"))
    return meta


def validate_a_output(
    outdir: str | Path,
    cfg: dict[str, Any],
    *,
    expected_algorithms: Iterable[str] | None = None,
) -> dict[str, int]:
    """Validate both frozen-attribution and new update artifacts for A-v0.2."""
    outdir = Path(outdir)
    exp = cfg["experiment"]
    seeds = int(exp["seeds"])
    algorithms = tuple(expected_algorithms or exp["algorithms"])
    _require_meta(outdir, cfg, stage="all", seeds=seeds)

    attribution_rows = _read_csv(outdir / "attribution" / "seed_metrics.csv")
    expected_attribution_rows = seeds * 2 * 5  # clean/symmetric x frozen v0.1 algorithm set
    if len(attribution_rows) != expected_attribution_rows:
        _fail(
            str(outdir / "attribution" / "seed_metrics.csv"),
            f"expected {expected_attribution_rows} seed rows, got {len(attribution_rows)}",
        )
    frozen_algorithms = {"immediate", "pe_seq", "cf_only", "full_rfl", "oracle_upper"}
    if {row.get("algorithm") for row in attribution_rows} != frozen_algorithms:
        _fail(str(outdir / "attribution" / "seed_metrics.csv"), "frozen attribution algorithm set changed")
    if {row.get("condition") for row in attribution_rows} != {"clean", "symmetric"}:
        _fail(str(outdir / "attribution" / "seed_metrics.csv"), "paired feedback conditions are incomplete")
    _read_jsonl(outdir / "attribution" / "episodes.jsonl")

    update_dir = outdir / "update"
    episode_rows = _read_jsonl(update_dir / "episodes.jsonl")
    summary_rows = _read_jsonl(update_dir / "update_rows.jsonl")
    expected_rows = seeds * 4 * int(exp["update_scenarios_per_type"]) * len(algorithms)
    if len(episode_rows) != expected_rows or len(summary_rows) != expected_rows:
        _fail(
            str(update_dir),
            f"expected {expected_rows} update rows, got episodes={len(episode_rows)}, summaries={len(summary_rows)}",
        )
    observed_algorithms = {str(row.get("algorithm")) for row in episode_rows}
    if observed_algorithms != set(algorithms):
        _fail(str(update_dir / "episodes.jsonl"), "algorithm set differs from frozen config")
    scenario_families = {str(row.get("condition")) for row in episode_rows}
    expected_families = {"high_protection", "low_protection", "environment_mixed", "hl_mixed"}
    if scenario_families != expected_families:
        _fail(str(update_dir / "episodes.jsonl"), "four update scenario families are incomplete")
    for index, row in enumerate(episode_rows):
        validate_v02_update_record(row, context=f"{update_dir / 'episodes.jsonl'}:{index + 1}")
    # Word-specified microbenchmark sanity separation: blindly following the
    # false label must measurably damage the protected item, whereas the
    # evaluator Oracle-Update upper bound should leave it effectively intact.
    def _damage(condition: str, algorithm: str) -> list[float]:
        return [
            float(row["metrics"]["correct_knowledge_damage"])
            for row in episode_rows
            if row["condition"] == condition and row["algorithm"] == algorithm
        ]

    for condition in ("high_protection", "low_protection"):
        immediate_damage = _damage(condition, "immediate")
        oracle_damage = _damage(condition, "oracle_update")
        if not immediate_damage or max(immediate_damage) <= 1e-6:
            _fail(str(update_dir), f"{condition} lacks detectable Immediate CKD")
        # Acceptance permits <=.1 responsibility leakage, so a tiny residual
        # diagnostic write is expected; a 2% normalized margin cap is the
        # declared smoke sanity bound rather than a hypothesis-test threshold.
        if not oracle_damage or max(oracle_damage) > 0.02:
            _fail(str(update_dir), f"{condition} Oracle-Update CKD is not near zero")

    hl_oracle = [
        row for row in episode_rows
        if row["condition"] == "hl_mixed" and row["algorithm"] == "oracle_update"
    ]
    if not hl_oracle or not all(
        float(row["metrics"]["actual_update"].get("H", 0.0)) > 0.0
        and float(row["metrics"]["actual_update"].get("L", 0.0)) > 0.0
        for row in hl_oracle
    ):
        _fail(str(update_dir), "H+L mixed Oracle-Update did not update both internal modules")
    hashes_by_scenario: dict[tuple[Any, Any], list[str]] = {}
    for index, row in enumerate(summary_rows):
        _validate_receipt_mass(
            row.get("actual_update"), row.get("applied_updates"),
            context=f"{update_dir / 'update_rows.jsonl'}:{index + 1}",
        )
        context = f"{update_dir / 'update_rows.jsonl'}:{index + 1}"
        _assert_hash(row.get("q_hash_before"), context, "q_hash_before")
        _assert_hash(row.get("q_hash_after"), str(update_dir / "update_rows.jsonl"), "q_hash_after")
        learner = row.get("learner")
        evaluator = row.get("evaluator_only")
        if not isinstance(learner, dict) or _contains_oracle_key(learner):
            _fail(context, "summary row learner namespace leaks oracle-labelled data")
        if not isinstance(evaluator, dict) or "oracle_R" not in evaluator:
            _fail(context, "summary row lacks evaluator-only oracle responsibility")
        if row.get("algorithm") == "oracle_update" and learner.get("responsibility") not in ({}, None):
            _fail(context, "Oracle-Update summary leaks evaluator responsibility into learner data")
        key = (row.get("seed"), row.get("scenario_id"))
        hashes_by_scenario.setdefault(key, []).append(row["q_hash_before"])
    for key, hashes in hashes_by_scenario.items():
        if len(hashes) != len(algorithms) or len(set(hashes)) != 1:
            _fail(str(update_dir / "update_rows.jsonl"), f"Q clone hashes are not identical for scenario {key!r}")
    metric_rows = _read_csv(update_dir / "update_seed_metrics.csv")
    if len(metric_rows) != seeds * len(algorithms):
        _fail(str(update_dir / "update_seed_metrics.csv"), "seed-level update metric row count is wrong")
    return {
        "attribution_seed_rows": len(attribution_rows),
        "update_rows": len(episode_rows),
        "update_seed_rows": len(metric_rows),
    }


def validate_b_transfer_output(
    outdir: str | Path,
    cfg: dict[str, Any],
    *,
    expected_algorithms: Iterable[str] | None = None,
) -> dict[str, int]:
    """Validate pretrain gates, common checkpoint identity, shocks, and recovery."""
    outdir = Path(outdir)
    exp = cfg["experiment"]
    seeds = int(exp["seeds"])
    algorithms = tuple(expected_algorithms or exp["algorithms"])
    meta = _require_meta(outdir, cfg, stage="transfer", seeds=seeds)
    if meta.get("gate_ok") is not True:
        _fail(str(outdir / "run_meta.json"), "transfer gate is not marked passed")
    seed_files = sorted(outdir.glob("transfer_seed*.json"))
    if len(seed_files) != seeds:
        _fail(str(outdir), f"expected {seeds} transfer seed files, found {len(seed_files)}")

    shock_rows = 0
    required_direction_counts = {
        "h_dominant_false_l": int(exp["shocks"]) // 2,
        "l_dominant_false_h": int(exp["shocks"]) // 2,
    }
    expected_recovery_episodes = list(range(0, int(exp["recovery_episodes"]) + 1, int(exp["recovery_eval_every"])))
    if expected_recovery_episodes[-1] != int(exp["recovery_episodes"]):
        expected_recovery_episodes.append(int(exp["recovery_episodes"]))
    for path in seed_files:
        result = _read_json(path)
        _validate_artifact_schema(result, path)
        if result.get("config_hash") != canonical_config_hash(cfg):
            _fail(str(path), "seed artifact config_hash differs from frozen config")
        _assert_hash(result.get("git_commit"), str(path), "git_commit")
        if result.get("status") != "completed":
            _fail(str(path), f"transfer was not completed: {result.get('status')!r}")
        if result.get("pretrain_gate") is not True:
            _fail(str(path), "pretrain gate failed; shocks must not be interpreted")
        if float(result.get("pre_success", -1.0)) < 0.90 or float(result.get("pre_safe_option", -1.0)) < 0.90:
            _fail(str(path), "pretrain metrics do not meet the .90 gate")
        checkpoint_hash = result.get("common_checkpoint_hash")
        _assert_hash(checkpoint_hash, str(path), "common_checkpoint_hash")
        if result.get("schema_version") == V02_SCHEMA_VERSION:
            for field in ("seed_index", "experiment_seed", "scenario_seed"):
                if field not in result:
                    _fail(str(path), f"missing seed identity field {field}")
            probes = result.get("protected_probes")
            if not isinstance(probes, list) or len(probes) != int(exp["shocks"]):
                _fail(str(path), "missing frozen protected-probe set")
            probe_ids = [probe.get("probe_id") for probe in probes if isinstance(probe, dict)]
            if len(probe_ids) != len(probes) or len(set(probe_ids)) != len(probes):
                _fail(str(path), "protected probe IDs are missing or duplicated")
            observed_directions = {name: 0 for name in required_direction_counts}
            for probe in probes:
                if not isinstance(probe, dict):
                    _fail(str(path), "protected probe is not an object")
                direction = probe.get("direction")
                if direction not in observed_directions:
                    _fail(str(path), f"unexpected protected-probe direction {direction!r}")
                observed_directions[direction] += 1
                if probe.get("module") not in {"H", "L"}:
                    _fail(str(path), "protected probe has invalid module")
                if not _finite_number(probe.get("initial_margin")) or float(probe["initial_margin"]) < float(cfg["knowledge"]["initial_correct_margin"]):
                    _fail(str(path), "protected probe lacks required initial correct margin")
            if observed_directions != required_direction_counts:
                _fail(str(path), f"protected directions differ from frozen schedule: {observed_directions}")
        else:
            probe_ids = []
        results = result.get("algorithms")
        if not isinstance(results, dict) or set(results) != set(algorithms):
            _fail(str(path), "transfer algorithm set differs from frozen config")
        for name, algorithm_result in results.items():
            if algorithm_result.get("pre_shock_hash") != checkpoint_hash:
                _fail(str(path), f"{name} did not start from the common checkpoint")
            if algorithm_result.get("shock_count") != int(exp["shocks"]):
                _fail(str(path), f"{name} has an incomplete shock schedule")
            if probe_ids and algorithm_result.get("probe_ids") != probe_ids:
                _fail(str(path), f"{name} did not use the shared protected-probe IDs")
            recovery = algorithm_result.get("recovery_episode")
            horizon = int(exp["recovery_episodes"])
            if not isinstance(recovery, int) or recovery < 0 or recovery > horizon + 1:
                _fail(str(path), f"{name} has invalid recovery_episode")
            records = algorithm_result.get("recovery_eval_records")
            if not isinstance(records, list) or not records:
                _fail(str(path), f"{name} has no real recovery evaluations")
            observed_recovery_episodes = [row.get("episode") for row in records if isinstance(row, dict)]
            if observed_recovery_episodes != expected_recovery_episodes:
                _fail(str(path), f"{name} recovery cadence differs from frozen schedule")
            shocks = algorithm_result.get("shocks")
            if not isinstance(shocks, list) or len(shocks) != int(exp["shocks"]):
                _fail(str(path), f"{name} has malformed shock receipts")
            for index, shock in enumerate(shocks):
                _validate_receipt_mass(
                    shock.get("actual_update"), shock.get("applied_updates"),
                    context=f"{path.name}:{name}:shock{index}",
                )
                if probe_ids and shock.get("probe_id") not in probe_ids:
                    _fail(str(path), f"{name} shock {index} does not reference a frozen probe")
                shock_rows += 1
            if probe_ids:
                per_probe = algorithm_result.get("knowledge_by_probe")
                if not isinstance(per_probe, list) or {row.get("probe_id") for row in per_probe if isinstance(row, dict)} != set(probe_ids):
                    _fail(str(path), f"{name} lacks complete post-shock protected-probe metrics")
                for metric in ("correct_knowledge_damage", "wrong_knowledge_reinforcement"):
                    if not _finite_number(algorithm_result.get(metric)):
                        _fail(str(path), f"{name} has invalid fixed-probe {metric}")
            if name == "oracle_update":
                for shock in shocks:
                    evaluator = shock.get("evaluator_only")
                    learner = shock.get("learner")
                    if not isinstance(evaluator, dict) or evaluator.get("oracle_update_upper_bound") is not True:
                        _fail(str(path), "Oracle-Update shocks must be explicitly marked evaluator-only")
                    if not isinstance(learner, dict) or learner.get("responsibility") not in ({}, None):
                        _fail(str(path), "Oracle-Update shock stores evaluator R* in learner data")
    return {"transfer_seed_files": len(seed_files), "shock_rows": shock_rows}


def validate_b_online_output(
    outdir: str | Path,
    cfg: dict[str, Any],
    *,
    expected_algorithms: Iterable[str] | None = None,
) -> dict[str, int]:
    """Validate B-online's real Bellman-update evidence and 51/short cadence."""
    outdir = Path(outdir)
    exp = cfg["experiment"]
    seeds = int(exp["seeds"])
    algorithms = tuple(expected_algorithms or exp["algorithms"])
    meta = _require_meta(outdir, cfg, stage="online", seeds=seeds)
    if meta.get("gate_ok") is not True:
        _fail(str(outdir / "run_meta.json"), "online gate is not marked passed")
    seed_files = sorted(outdir.glob("online_seed*.json"))
    if len(seed_files) != seeds:
        _fail(str(outdir), f"expected {seeds} online seed files, found {len(seed_files)}")
    expected_points = list(range(0, int(exp["online_episodes"]) + 1, int(exp["online_eval_every"])))
    if expected_points[-1] != int(exp["online_episodes"]):
        expected_points.append(int(exp["online_episodes"]))
    records = 0
    for path in seed_files:
        payload = _read_json(path)
        _validate_artifact_schema(payload, path)
        if payload.get("status") != "completed" or payload.get("config_hash") != canonical_config_hash(cfg):
            _fail(str(path), "online seed did not complete under the frozen config")
        result = payload.get("algorithms")
        if not isinstance(result, dict) or set(result) != set(algorithms):
            _fail(str(path), "online algorithm set differs from frozen config")
        for name, algorithm in result.items():
            if not isinstance(algorithm, dict):
                _fail(str(path), f"{name} online result is not an object")
            _assert_hash(algorithm.get("q_hash_initial"), str(path), f"{name}.q_hash_initial")
            _assert_hash(algorithm.get("q_hash_final"), str(path), f"{name}.q_hash_final")
            if algorithm["q_hash_initial"] == algorithm["q_hash_final"]:
                _fail(str(path), f"{name} final Q hash did not change")
            if not isinstance(algorithm.get("task_update_count"), int) or algorithm["task_update_count"] <= 0:
                _fail(str(path), f"{name} has no real task updates")
            curve = algorithm.get("eval_records")
            if not isinstance(curve, list) or [row.get("episode") for row in curve if isinstance(row, dict)] != expected_points:
                _fail(str(path), f"{name} online evaluation cadence differs from frozen schedule")
            records += len(curve)
    return {"online_seed_files": len(seed_files), "online_eval_records": records}


def validate_smoke_output(outdir: str | Path, cfg: dict[str, Any]) -> dict[str, int]:
    """Validate the exact A/B artifacts created by the strict smoke runner."""
    outdir = Path(outdir)
    a = validate_a_output(outdir / "a", cfg)
    b = validate_b_transfer_output(outdir / "b", cfg)
    return {**{f"a_{key}": value for key, value in a.items()}, **{f"b_{key}": value for key, value in b.items()}}
