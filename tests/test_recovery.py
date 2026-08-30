from pathlib import Path

import yaml

from scripts.experiment_b_v02 import run_transfer


def test_transfer_uses_common_clone_and_real_recovery(tmp_path):
    cfg = yaml.safe_load(Path("configs/v02_smoke.yaml").read_text(encoding="utf-8"))
    cfg["experiment"].update({"pretrain_episodes": 200, "shocks": 2, "recovery_episodes": 10, "recovery_eval_every": 5})
    result = run_transfer(cfg, tmp_path, seed=0, algorithms=("standard", "immediate", "oracle_update"))
    assert result["status"] == "completed"
    for algorithm, data in result["algorithms"].items():
        assert data["pre_shock_hash"] == result["common_checkpoint_hash"]
        assert data["shock_count"] == 2
        # Includes the post-shock / pre-recovery episode-0 point plus the two
        # configured recovery checkpoints.
        assert len(data["recovery_eval_records"]) == 3
        assert data["recovery_eval_records"][0]["episode"] == 0
        assert data["recovery_episode"] is not None


def test_transfer_seed_artifact_resumes_without_overwrite(tmp_path):
    cfg = yaml.safe_load(Path("configs/v02_smoke.yaml").read_text(encoding="utf-8"))
    cfg["experiment"].update({"pretrain_episodes": 200, "shocks": 2, "recovery_episodes": 10, "recovery_eval_every": 5})
    first = run_transfer(cfg, tmp_path, seed=17, algorithms=("standard", "immediate"))
    artifact = tmp_path / "transfer_seed17.json"
    before = artifact.read_text(encoding="utf-8")
    second = run_transfer(cfg, tmp_path, seed=17, algorithms=("standard", "immediate"))
    assert first["status"] == second["status"] == "completed"
    assert artifact.read_text(encoding="utf-8") == before
