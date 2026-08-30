"""Focused acceptance tests for the v0.2 seed-level reporting path."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.analyze_v02 import (
    AnalysisDataError,
    MetricSource,
    aligned_pairs,
    analyze_directory,
    analyze_sources,
    load_online_results,
    main,
    write_analysis_outputs,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _shock(*, f1: float, ckd: float, cf: float) -> dict:
    return {
        "update_precision": f1,
        "update_recall": f1,
        "update_f1": f1,
        "actual_wur": 1.0 - f1,
        "correct_knowledge_damage": ckd,
        "wrong_knowledge_reinforcement": 0.01,
        "cf_transitions": cf,
    }


def _curve(*points: tuple[int, float]) -> list[dict]:
    return [{"episode": episode, "success": success, "return": success} for episode, success in points]


def _write_complete_panel(root: Path, n_seeds: int = 12) -> None:
    attribution = root / "attribution"
    update = root / "update"
    transfer = root / "transfer"
    online = root / "online"
    for path in (attribution, update, transfer, online):
        path.mkdir(parents=True)
    for path in (root, transfer, online):
        _write_json(path / "run_meta.json", {
            "config_hash": "test-config", "git_commit": "test-commit",
        })

    with (attribution / "seed_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "seed_idx", "condition", "algorithm", "ae_mean", "wur_mean",
            "coverage", "wrong_update_rate", "ffcr", "cf_transitions_mean",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for seed in range(n_seeds):
            for algorithm, ae, cost in (
                ("full_rfl", 0.10 + seed * 0.0002, 12.0),
                ("immediate", 0.30 + seed * 0.0010, 0.0),
                ("cf_only", 0.02, 120.0),
            ):
                writer.writerow({
                    "seed_idx": seed, "condition": "symmetric", "algorithm": algorithm,
                    "ae_mean": ae, "wur_mean": 0.1, "coverage": 1.0,
                    "wrong_update_rate": 0.0, "ffcr": 0.0, "cf_transitions_mean": cost,
                })

    rows = []
    for seed in range(n_seeds):
        for scenario_type in ("high_protection", "low_protection"):
            for algorithm, f1, ckd_h, cost in (
                ("full_rfl", 0.90 + seed * 0.0001, 0.02, 10.0),
                ("immediate", 0.60 + seed * 0.0001, 0.20, 0.0),
                ("cf_only", 0.95, 0.01, 100.0),
            ):
                rows.append({
                    "seed": seed,
                    "algorithm": algorithm,
                    "scenario_id": f"{seed}-{scenario_type}",
                    "scenario_type": scenario_type,
                    "update_precision": f1,
                    "update_recall": f1,
                    "update_f1": f1,
                    "actual_wur": 1.0 - f1,
                    "correct_knowledge_damage": ckd_h,
                    "wrong_knowledge_reinforcement": 0.01,
                    "ckd_h": ckd_h,
                    "ckd_l": 0.0,
                    "wkr_h": 0.01,
                    "wkr_l": 0.0,
                    "cf_transitions": cost,
                })
    (update / "update_rows.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )

    for seed in range(n_seeds):
        algorithms = {}
        for algorithm, recovery, f1, ckd, cost in (
            ("full_rfl", 50 + seed % 3, 0.9, 0.02, 10.0),
            ("immediate", 105 + seed % 3, 0.6, 0.20, 0.0),
            ("cf_only", 45 + seed % 3, 0.95, 0.01, 100.0),
        ):
            curve = (
                _curve((0, 0.50), (250, 0.80), (500, 0.98))
                if algorithm == "full_rfl"
                else _curve((0, 0.20), (250, 0.45), (500, 0.70))
            )
            algorithms[algorithm] = {
                "recovery_episode": recovery,
                "knowledge_margin_pre_shock": 0.6,
                "knowledge_margin_post_shock": 0.5,
                "recovery_eval_records": curve,
                "shocks": [_shock(f1=f1, ckd=ckd, cf=cost), _shock(f1=f1, ckd=ckd, cf=cost)],
            }
        _write_json(transfer / f"transfer_seed{seed}.json", {
            "seed": seed, "status": "completed", "pretrain_gate": True,
            "config_hash": "test-config", "git_commit": "test-commit", "algorithms": algorithms,
        })

        online_algorithms = {
            "full_rfl": {
                "final_success": 0.96 + seed * 0.0001,
                "final_safe_option": 0.96,
                "final_return": 0.9,
                "total_bellman": 100,
                "wall_s": 1.0,
                "eval_records": _curve(
                    (0, 0.10), (1000, 0.91), (2000, 0.92),
                    (3000, 0.95), (4000, 0.96), (5000, 0.96),
                ),
            },
            "standard": {
                "final_success": 0.94 + seed * 0.0001,
                "final_safe_option": 0.94,
                "final_return": 0.8,
                "total_bellman": 100,
                "wall_s": 1.0,
                "eval_records": _curve(
                    (0, 0.10), (1000, 0.50), (2000, 0.80),
                    (3000, 0.90), (4000, 0.91), (5000, 0.92),
                ),
            },
        }
        _write_json(online / f"online_seed{seed}.json", {
            "seed": seed, "episodes": 5000, "config_hash": "test-config",
            "git_commit": "test-commit", "algorithms": online_algorithms,
        })


def _by_id(report: dict) -> dict:
    return {record["comparison_id"]: record for record in report["records"]}


def test_complete_panel_has_seed_level_primary_statistics_and_outputs(tmp_path: Path):
    _write_complete_panel(tmp_path)

    report = analyze_directory(tmp_path, n_permutations=2_000, n_bootstraps=2_000)
    records = _by_id(report)

    for hypothesis in ("H-A", "H-U", "H-K", "H-L"):
        assert records[hypothesis]["status"] == "complete"
        assert records[hypothesis]["n_seeds"] == 12
        assert records[hypothesis]["holm_adjusted_p"] is not None
        assert records[hypothesis]["decision"] == "PASS"
    assert report["primary_gate"] == {"all_available": True, "all_pass": True}
    assert records["H-K"]["source"] == "A_update_high_protection"
    assert records["H-K"]["metric"] == "ckd_h"
    assert records["B-transfer-AUC"]["decision"] == "PASS"
    assert records["B-online-AUC"]["status"] == "complete"
    assert records["B-online-To90"]["left_censored_seeds"] == 0
    assert records["B-online-noninferiority"]["decision"] == "PASS"

    written = write_analysis_outputs(report, tmp_path / "report.json")
    assert all(path.exists() for path in written.values())
    assert json.loads(written["json"].read_text(encoding="utf-8"))["statistical_unit"] == "seed"
    assert "episode-level p-values" in written["markdown"].read_text(encoding="utf-8")


def test_markdown_distinguishes_a_failed_primary_gate_from_an_unavailable_one(tmp_path: Path):
    report = {
        "statistical_unit": "seed",
        "n_permutations": 10,
        "n_bootstraps": 10,
        "holm_family": [],
        "records": [],
        "primary_gate": {"all_available": True, "all_pass": False},
    }
    failed = write_analysis_outputs(report, tmp_path / "failed.json")
    assert "Primary gate: FAIL" in failed["markdown"].read_text(encoding="utf-8")

    report["primary_gate"] = {"all_available": False, "all_pass": False}
    unavailable = write_analysis_outputs(report, tmp_path / "unavailable.json")
    assert "Primary gate: not supported" in unavailable["markdown"].read_text(encoding="utf-8")


def test_aligned_pairs_refuses_to_silently_drop_a_seed():
    source = MetricSource(name="synthetic")
    source.add("metric", "full_rfl", "0", 0.2, origin="test")
    source.add("metric", "full_rfl", "1", 0.3, origin="test")
    source.add("metric", "immediate", "0", 0.4, origin="test")

    with pytest.raises(AnalysisDataError, match="unaligned seeds"):
        aligned_pairs(source, "metric", "full_rfl", "immediate")


def test_analysis_refuses_to_mix_artifacts_from_different_config_or_commit():
    a = MetricSource(name="a", metadata={"config_hash": "config-a", "git_commit": "commit-a"})
    b = MetricSource(name="b", metadata={"config_hash": "config-b", "git_commit": "commit-a"})

    with pytest.raises(AnalysisDataError, match="different config hashes"):
        analyze_sources({"a": a, "b": b}, n_permutations=10, n_bootstraps=10)


def test_online_loader_requires_episode_zero_for_word_auc_but_recomputes_three_checkpoint_to90(tmp_path: Path):
    path = tmp_path / "online_seed0.json"
    _write_json(path, {
        "seed": 0,
        "episodes": 5000,
        "config_hash": "test-config",
        "git_commit": "test-commit",
        "algorithms": {
            "full_rfl": {
                "final_success": 0.95,
                "eval_records": _curve((100, 0.91), (200, 0.92), (300, 0.93), (5000, 0.95)),
            },
            "standard": {
                "final_success": 0.94,
                "eval_records": _curve((100, 0.8), (200, 0.91), (300, 0.92), (400, 0.93), (5000, 0.94)),
            },
        },
    })

    source = load_online_results([path])
    assert "success_auc_0_3000" not in source.metrics
    assert source.metrics["episodes_to_90_3checkpoints"]["full_rfl"]["0"] == 300.0
    assert source.metrics["episodes_to_90_3checkpoints"]["standard"]["0"] == 400.0
    assert source.notes


def test_cli_is_strict_by_default_and_report_only_is_explicit(tmp_path: Path):
    _write_complete_panel(tmp_path)
    metrics_path = tmp_path / "attribution" / "seed_metrics.csv"
    with metrics_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    fieldnames = list(rows[0])
    for row in rows:
        if row["algorithm"] == "full_rfl":
            row["ae_mean"] = "0.90"
    with metrics_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    assert main(["--dir", str(tmp_path), "--n-permutations", "20", "--n-bootstraps", "20"]) == 2
    assert main([
        "--dir", str(tmp_path), "--report-only", "--n-permutations", "20", "--n-bootstraps", "20",
    ]) == 0


def test_cli_returns_invalid_code_for_unusable_source(tmp_path: Path):
    assert main(["--dir", str(tmp_path)]) == 3
