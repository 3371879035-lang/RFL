from scripts.experiment_b_v02 import _curve_metrics


def test_online_curve_metrics_starts_at_zero_and_requires_three_checkpoints():
    raw = {
        "eval_records": [
            {"episode": 0, "success": 0.0},
            {"episode": 100, "success": 0.9},
            {"episode": 200, "success": 0.91},
            {"episode": 300, "success": 0.92},
        ]
    }
    result = _curve_metrics(raw, 300)
    assert result["success_auc_horizon"] == 300
    assert result["success_auc"] is not None
    # The episode-100 crossing is only reported once the 100/200/300 triple
    # confirms it.
    assert result["episodes_to_90"] == 100


def test_online_curve_metrics_right_censors_unconfirmed_threshold():
    raw = {
        "eval_records": [
            {"episode": 0, "success": 0.0},
            {"episode": 100, "success": 0.95},
            {"episode": 200, "success": 0.70},
            {"episode": 300, "success": 0.95},
        ]
    }
    assert _curve_metrics(raw, 300)["episodes_to_90"] == 301
