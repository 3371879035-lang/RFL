import pytest

from rflnext.env import BLOCKED, SUCCESS, TIMEOUT, W
from rflnext.gamma import (
    CAUSES,
    average_precision,
    brier_multilabel,
    cf_query,
    generate_balanced,
    make_trace,
    observable_features,
    responsibility_from_cf,
    run_method,
    score_method,
    truth_scores,
    SequenceModel,
)

H = 8


def _trace(**kw):
    base = dict(goal_lane=0, hazard=0, option=0, fault=False, fault_start=1, horizon=H)
    base.update(kw)
    return make_trace("t", **base)


def test_successful_episode_yields_no_trace():
    assert _trace(goal_lane=0, option=0, fault=False) is None


def test_h_error_is_wrong_option_with_good_execution():
    tr = _trace(goal_lane=0, option=1, fault=False)
    assert tr.family == "H_error"
    assert (tr.u_h, tr.u_l) == (1, 0)
    assert tr.terminal == TIMEOUT


def test_l_error_is_right_option_with_stalled_execution():
    tr = _trace(goal_lane=0, option=0, fault=True, fault_start=1)
    assert tr.family == "L_error"
    assert (tr.u_h, tr.u_l) == (0, 1)


def test_hl_error_is_both_wrong():
    tr = _trace(goal_lane=0, option=1, fault=True, fault_start=1)
    assert tr.family == "HL_error"
    assert (tr.u_h, tr.u_l) == (1, 1)


def test_e_failure_is_the_jammed_gate():
    tr = _trace(goal_lane=0, option=0, fault=False, hazard=1)
    assert tr.family == "E_failure"
    assert tr.terminal == BLOCKED
    assert (tr.u_h, tr.u_l) == (0, 0)


def test_diagnoser_cannot_see_latent_scene_variables():
    """The observable features must not leak goal_lane or hazard."""
    reached = _trace(goal_lane=0, option=1, fault=False)
    f = observable_features(reached)
    assert set(f) == {"reached_end", "blocked", "incomplete"}
    assert f["reached_end"] == 1  # completed its own corridor

    stalled = _trace(goal_lane=0, option=0, fault=True, fault_start=1)
    g = observable_features(stalled)
    assert g["reached_end"] == 0 and g["blocked"] == 0 and g["incomplete"] == 1


def test_stalled_and_jammed_are_observationally_identical():
    """The core ambiguity: an execution failure and a jammed gate look the
    same in the action sequence alone."""
    stalled = _trace(goal_lane=0, option=0, fault=True, fault_start=1)
    jammed = _trace(goal_lane=0, option=0, fault=True, fault_start=1, hazard=1)
    assert observable_features(stalled) == observable_features(jammed)
    assert stalled.family != jammed.family


def test_counterfactual_resolves_that_ambiguity():
    stalled = _trace(goal_lane=0, option=0, fault=True, fault_start=1)
    jammed = _trace(goal_lane=0, option=0, fault=True, fault_start=1, hazard=1)
    # Perfect execution wins in the first case and still loses in the second.
    assert cf_query(stalled, "L").outcome == SUCCESS
    assert cf_query(jammed, "L").outcome != SUCCESS


def test_cf_hypothesis_l_responsibility():
    tr = _trace(goal_lane=0, option=0, fault=True, fault_start=1)
    res = {"L": cf_query(tr, "L")}
    assert responsibility_from_cf(res) == {"H": 0.0, "L": 1.0, "E": 0.0, "U": 0.0}


def test_cf_hypothesis_h_responsibility():
    tr = _trace(goal_lane=0, option=1, fault=False)
    res = {"L": cf_query(tr, "L"), "H": cf_query(tr, "H")}
    assert responsibility_from_cf(res) == {"H": 1.0, "L": 0.0, "E": 0.0, "U": 0.0}


def test_cf_both_fail_means_environment():
    tr = _trace(goal_lane=0, option=0, fault=False, hazard=1)
    res = {"L": cf_query(tr, "L"), "H": cf_query(tr, "H")}
    assert responsibility_from_cf(res) == {"H": 0.0, "L": 0.0, "E": 1.0, "U": 0.0}


def test_unknown_family_has_an_explicit_unexplained_channel():
    """Nobody is at fault, the gate is not jammed, yet the episode fails: the
    cause is outside the modelled H/L/E taxonomy."""
    tr = make_trace("u", goal_lane=0, hazard=0, option=0, fault=False,
                    obstruction_at=2, horizon=H)
    assert tr is not None
    assert tr.family == "unknown"
    assert (tr.u_h, tr.u_l) == (0, 0)
    assert tr.p_u == 1.0
    truth = truth_scores(tr)
    assert truth == {"H": 0.0, "L": 0.0, "E": 0.0, "U": 1.0}


def test_counterfactuals_misattribute_the_unknown_family():
    """A documented blind spot, measured rather than hidden: the reference
    re-rollout carries no unmodelled obstruction, so perfect execution looks
    like it would have won and the failure is blamed on the low level."""
    tr = make_trace("u", goal_lane=0, hazard=0, option=0, fault=False,
                    obstruction_at=2, horizon=H)
    res = {"L": cf_query(tr, "L"), "H": cf_query(tr, "H")}
    score = responsibility_from_cf(res)
    assert score["L"] == 1.0          # blamed on L ...
    assert truth_scores(tr)["U"] == 1.0  # ... but the truth is "unexplained"


def test_likelihood_indexing_is_not_inverted():
    """Regression: storing (log p1, log(1-p1)) while indexing with the binary
    feature value reads every feature backwards, which made a jammed gate score
    as an execution failure."""
    traces = generate_balanced(800, seed=8, horizon=H)
    model = SequenceModel().fit(traces[:400])
    blocked = [t for t in traces[400:] if t.terminal == BLOCKED]
    assert blocked
    for tr in blocked[:20]:
        feats = observable_features(tr)
        # P(blocked=1 | E) is positive, P(blocked=1 | L) is zero.
        assert model.log_likelihood["E"]["blocked"][1] > model.log_likelihood["L"]["blocked"][1]
        assert feats["blocked"] == 1
        assert model.score(tr)["E"] == max(model.score(tr).values())


def test_generate_balanced_returns_even_families():
    traces = generate_balanced(400, seed=1, horizon=H)
    counts: dict = {}
    for t in traces:
        counts[t.family] = counts.get(t.family, 0) + 1
    assert set(counts) == {"H_error", "L_error", "HL_error", "E_failure", "unknown"}
    assert len(set(counts.values())) == 1
    assert counts["H_error"] == 80


def test_sequence_model_separates_the_observable_cases():
    traces = generate_balanced(1200, seed=2, horizon=H)
    model = SequenceModel().fit(traces[:600])
    blocked = [t for t in traces[600:] if t.terminal == BLOCKED]
    reached = [t for t in traces[600:] if t.family == "H_error"]
    assert blocked and reached
    # Jammed gate -> environment is the top cause.
    sc_blocked = model.score(blocked[0])
    assert sc_blocked["E"] == max(sc_blocked.values())
    # Completed own corridor but still lost -> high level is the top cause.
    sc_reached = model.score(reached[0])
    assert sc_reached["H"] == max(sc_reached.values())


def test_sequence_model_e_detection_is_limited_by_the_ambiguity():
    """Most E_failures are observationally identical to L_errors, so a
    sequence-only attributor cannot recover them the way the SCM can."""
    traces = generate_balanced(800, seed=3, horizon=H)
    model = SequenceModel().fit(traces[:400])
    test = traces[400:]
    seq = score_method("sequence_only", run_method("sequence_only", test, model), test)
    orc = score_method("oracle", run_method("oracle", test, model), test)
    assert orc["auprc_E"] == pytest.approx(1.0)
    assert seq["auprc_E"] < orc["auprc_E"]
    assert seq["auprc_E"] < 0.95


def test_average_precision_perfect_and_chance():
    assert average_precision([3, 2, 1], [1, 1, 1]) == pytest.approx(1.0)
    assert average_precision([1, 2, 3], [1, 1, 1]) == pytest.approx(1.0)
    assert average_precision([1, 1], [0, 0]) is None


def test_brier_is_zero_for_perfect_scores():
    truths = [{"H": 1.0, "L": 0.0, "E": 0.0}]
    assert brier_multilabel([{"H": 1.0, "L": 0.0, "E": 0.0}], truths) == 0.0


def test_oracle_scores_perfectly():
    traces = generate_balanced(200, seed=4, horizon=H)
    model = SequenceModel().fit(traces[:100])
    test = traces[100:]
    atts = run_method("oracle", test, model)
    sc = score_method("oracle", atts, test)
    assert sc["brier"] == pytest.approx(0.0)
    assert sc["update_precision"] == pytest.approx(1.0)
    assert sc["collateral_rate"] == pytest.approx(0.0)
    assert sc["auprc_H"] == pytest.approx(1.0)


def test_cf_only_k2_beats_sequence_only_on_brier():
    traces = generate_balanced(600, seed=5, horizon=H)
    model = SequenceModel().fit(traces[:300])
    test = traces[300:]
    seq = score_method("sequence_only", run_method("sequence_only", test, model), test)
    cf2 = score_method("cf_only", run_method("cf_only", test, model, k=2), test)
    assert cf2["brier"] < seq["brier"]
    # A successful L query short-circuits, so the mean is below the budget.
    assert 1.0 <= cf2["mean_cf_queries"] <= 2.0
    assert cf2["mean_cf_queries"] < 2.0


def test_budget_is_respected():
    traces = generate_balanced(200, seed=6, horizon=H)
    model = SequenceModel().fit(traces[:100])
    test = traces[100:]
    for name in ("cf_only", "seq_then_cf"):
        for k in (1, 2):
            atts = run_method(name, test, model, k=k)
            assert all(a.cf_queries <= k for a in atts)
            assert any(a.cf_queries > 0 for a in atts)


def test_truths_are_multilabel_for_hl_errors():
    tr = _trace(goal_lane=0, option=1, fault=True, fault_start=1)
    assert tr.u_h == 1 and tr.u_l == 1
    assert tr.p_u == 0.0
    assert set(CAUSES) == {"H", "L", "E", "U"}


def test_new_metrics_are_defined_and_bounded():
    from rflnext.gamma import (
        exact_set_accuracy, expected_calibration_error, hamming_loss, roc_auc,
    )

    truths = [{"H": 1.0, "L": 0.0, "E": 0.0, "U": 0.0},
              {"H": 0.0, "L": 1.0, "E": 0.0, "U": 0.0}]
    scores = [{"H": 0.9, "L": 0.1, "E": 0.0, "U": 0.0},
              {"H": 0.2, "L": 0.8, "E": 0.0, "U": 0.0}]
    assert roc_auc([0.9, 0.2], [1, 0]) == pytest.approx(1.0)
    assert roc_auc([0.5, 0.5], [1, 1]) is None
    assert hamming_loss(scores, truths) == 0.0
    assert exact_set_accuracy(scores, truths) == 1.0
    ece = expected_calibration_error(scores, truths)
    assert 0.0 <= ece <= 1.0
