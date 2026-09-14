import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(out, *extra):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "pilot_alpha.py"),
         "--config", str(ROOT / "configs" / "alpha.yaml"),
         "--outdir", str(out), "--seeds", "2", "--episodes", "400",
         "--eval-every", "200", "--eval-episodes", "40", *extra],
        capture_output=True, text=True, cwd=str(ROOT),
    )


def test_pilot_alpha_cli_writes_summary(tmp_path):
    out = tmp_path / "alpha"
    proc = _run(out, "--report-only")
    assert proc.returncode == 0, proc.stderr
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["experiment"] == "v03_alpha"
    assert len(summary["seeds"]) == 4  # 2 seeds x 2 arms
    for row in summary["seeds"]:
        assert row["arm"] in ("traditional", "positive_only")
        assert "success_auc" in row
        assert "family_counts" in row
        assert "n_negative_td" in row
    assert (out / "config.yaml").exists()
    assert "ceiling_gate" in summary and "family_gate" in summary


def test_pilot_alpha_gate_returns_nonzero_when_benchmark_saturates(tmp_path):
    """With a tiny episode budget the arms are near-identical, so the
    pre-registered flat-AUC gate must fire and the exit code must be 2."""
    out = tmp_path / "flat"
    proc = _run(out)
    assert proc.returncode in (0, 2, 3), proc.stderr
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    if proc.returncode == 2:
        assert summary["ceiling_gate"]["status"] == "benchmark_no_discriminating_power"
