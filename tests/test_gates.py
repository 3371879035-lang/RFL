from rflnext.gates import GateReport, ceiling_gate, family_gate


def _result(arm, curve, counts):
    class R:
        pass

    r = R()
    r.arm = arm
    r.success_curve = curve
    r.checkpoints = list(range(0, 250 * len(curve), 250))
    r.family_counts = counts
    return r


GOOD = {"H_error": 500, "L_error": 500, "HL_error": 500, "E_failure": 500}


def test_ceiling_gate_flags_flat_auc():
    """Identical curves: the benchmark cannot tell the arms apart."""
    results = {
        "traditional": _result("traditional", [0.5, 0.6, 0.7], GOOD),
        "positive_only": _result("positive_only", [0.5, 0.6, 0.7], GOOD),
    }
    rep = ceiling_gate(results, structural_ceiling=0.75, min_auc_gap=0.005)
    assert isinstance(rep, GateReport)
    assert rep.status == "benchmark_no_discriminating_power"
    assert "auc_gap_below_floor" in rep.reasons
    assert rep.auc_spread == 0.0


def test_ceiling_gate_reports_saturation_but_passes_when_auc_separates():
    """Both arms pinned at the structural ceiling is expected here; the AUC
    gap is what carries the signal, so this must NOT be fatal."""
    results = {
        "traditional": _result("traditional", [0.50, 0.70, 0.75], GOOD),
        "positive_only": _result("positive_only", [0.30, 0.55, 0.75], GOOD),
    }
    rep = ceiling_gate(results, structural_ceiling=0.75, min_auc_gap=0.005)
    assert rep.saturated_at_ceiling is True
    assert rep.auc_spread > 0.005
    assert rep.status == "ok"


def test_ceiling_gate_not_saturated_when_below_ceiling():
    results = {
        "traditional": _result("traditional", [0.20, 0.40, 0.60], GOOD),
        "positive_only": _result("positive_only", [0.10, 0.20, 0.30], GOOD),
    }
    rep = ceiling_gate(results, structural_ceiling=0.75, min_auc_gap=0.005)
    assert rep.status == "ok"
    assert rep.saturated_at_ceiling is False
    assert rep.reasons == []


def test_ceiling_gate_flags_saturated_and_flat_together():
    results = {
        "traditional": _result("traditional", [0.70, 0.75, 0.75], GOOD),
        "positive_only": _result("positive_only", [0.70, 0.75, 0.75], GOOD),
    }
    rep = ceiling_gate(results, structural_ceiling=0.75, min_auc_gap=0.005)
    assert rep.status == "benchmark_no_discriminating_power"
    assert rep.saturated_at_ceiling is True


def test_family_gate_requires_minimum_events():
    results = {
        "traditional": _result("traditional", [0.1, 0.2],
                               {"H_error": 500, "L_error": 10,
                                "HL_error": 500, "E_failure": 500}),
        "positive_only": _result("positive_only", [0.1, 0.2], GOOD),
    }
    rep = family_gate(results, min_family_events=400)
    assert rep.status == "insufficient_family_events"
    assert rep.reasons == ["L_error"]


def test_family_gate_passes_when_all_families_present():
    results = {
        "traditional": _result("traditional", [0.1, 0.2], GOOD),
        "positive_only": _result("positive_only", [0.1, 0.2], GOOD),
    }
    assert family_gate(results, min_family_events=400).status == "ok"
