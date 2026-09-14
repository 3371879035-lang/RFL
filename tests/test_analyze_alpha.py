import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_analyze_alpha_emits_paired_table(tmp_path):
    alpha = tmp_path / "alpha"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "pilot_alpha.py"),
         "--config", str(ROOT / "configs" / "alpha.yaml"),
         "--outdir", str(alpha), "--seeds", "2", "--episodes", "400",
         "--eval-every", "200", "--eval-episodes", "40", "--report-only"],
        check=True, cwd=str(ROOT),
    )
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "analyze_alpha.py"),
         "--dir", str(alpha), "--n-perm", "500", "--n-boot", "500"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    table = json.loads((alpha / "analysis.json").read_text(encoding="utf-8"))
    assert table["unit"] == "seed"
    assert table["n_seeds"] == 2
    assert "auc_delta_mean" in table
    assert "auc_delta_ci" in table
    assert len(table["auc_delta_ci"]) == 2
    assert "n_negative_td_by_arm" in table
