from pathlib import Path

import pytest
import yaml

from rflcc.qtables import QTables
from scripts import experiment_b_v02
from scripts.experiment_b_v02 import run_transfer


def test_transfer_blocks_rather_than_measure_unknown_low_action(tmp_path):
    cfg = yaml.safe_load(Path("configs/v02_smoke.yaml").read_text(encoding="utf-8"))
    cfg["experiment"].update({"pretrain_episodes": 200, "shocks": 2, "recovery_episodes": 10, "recovery_eval_every": 5})
    result = run_transfer(cfg, tmp_path, seed=0, algorithms=("standard", "immediate", "oracle_update"))
    assert result["status"] == "blocked_invalid_knowledge_probe"
    assert result["algorithms"] == {}
    assert result["probe_search"]["h_dominant_false_l"]["accepted"] < 1


def test_transfer_seed_artifact_resumes_without_overwrite(tmp_path):
    cfg = yaml.safe_load(Path("configs/v02_smoke.yaml").read_text(encoding="utf-8"))
    cfg["experiment"].update({"pretrain_episodes": 200, "shocks": 2, "recovery_episodes": 10, "recovery_eval_every": 5})
    first = run_transfer(cfg, tmp_path, seed=17, algorithms=("standard", "immediate"))
    artifact = tmp_path / "transfer_seed17.json"
    before = artifact.read_text(encoding="utf-8")
    second = run_transfer(cfg, tmp_path, seed=17, algorithms=("standard", "immediate"))
    assert first["status"] == second["status"] == "blocked_invalid_knowledge_probe"
    assert artifact.read_text(encoding="utf-8") == before


def test_recovery_continues_frozen_epsilon_schedule(monkeypatch):
    cfg = yaml.safe_load(Path("configs/v02_pilot.yaml").read_text(encoding="utf-8"))
    cfg["experiment"].update({"recovery_episodes": 2, "recovery_eval_every": 1})
    q = QTables()
    q.high[0] = {0: 0.0, 1: 0.60}
    probe = {"module": "H", "state": 0, "correct": 1, "wrong": 0, "initial_margin": 0.60}
    epsilons = []

    def fake_episode(agent, env, seed, epsilon):
        epsilons.append(epsilon)
        return 0.0

    monkeypatch.setattr(experiment_b_v02, "_task_episode", fake_episode)
    experiment_b_v02._recover(q, cfg, seed=11, probes=[probe], pre_shock_margin=0.60)
    assert epsilons == pytest.approx([0.02, 0.02])
