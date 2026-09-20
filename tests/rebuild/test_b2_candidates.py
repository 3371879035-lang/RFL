r"""B2-3 — Collateral and Retention **candidate machinery**, with synthetic calibration.

Twelve gates over two ideas:

* **`BehavioralCollateral`** on a candidate $U_{\text{unaffected}}$: the constructors see pre-update
  learner-visible material only (truth-blind, arm-blind, pre-update by signature), the metric is
  defined on exactly the set it is given, and a **synthetic injected spillover** is detected — the
  instrument calibration A79 67.4 asks for, which is not a development seed;
* **Retention candidates**: both eligible forms are defined for **every** seed including one that
  never recovers, the tau-conditioned form is registered as a conditional diagnostic rather than a
  candidate, and no form is selected by default.

Nothing here picks a construction or a form: the choices belong to the development stage (A79
67.4/67.5, A83 71.4), and a candidate that "wins" on a synthetic fixture is not thereby chosen.
"""

from __future__ import annotations

import inspect
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2.collateral import (  # noqa: E402
    CANDIDATE_CONSTRUCTIONS, UnaffectedSet, behavioral_collateral, select_construction,
)
from rfl_rebuild.b2.retention import (  # noqa: E402
    CANDIDATE_FORMS, DIAGNOSTIC_FORMS, LateWindowRetention, RetentionAtH, RetentionRole,
    retention_fraction, select_form,
)
from rfl_rebuild.env.kernel import ControlState, State  # noqa: E402
from rfl_rebuild.env.domain import decision_contexts  # noqa: E402

DOMAIN = tuple(decision_contexts())
VISITED = DOMAIN[:12]


# --------------------------------------------------------------------------- #
# 1. the constructors: blindness by signature, and several of them
# --------------------------------------------------------------------------- #

def test_1_the_constructors_see_only_pre_update_learner_visible_material():
    r"""Truth-blind, arm-blind, pre-update — as properties of the **interface**, since a constructor
    that *can* be told which arm it is in may one day branch on it."""
    forbidden = ("arm", "arm_id", "law", "post_state", "post", "delta_w", "ledger", "outcome",
                 "future", "stratum", "world_id", "block_id", "tau", "true", "truth")
    for name, fn in CANDIDATE_CONSTRUCTIONS.items():
        params = tuple(inspect.signature(fn).parameters)
        assert not (set(params) & set(forbidden)), (name, params)
        assert params[0] == "domain" and params[1] == "visited", (name, params)
    assert len(CANDIDATE_CONSTRUCTIONS) >= 2, "one candidate is a choice made by omission"


def test_2_no_construction_is_selected_by_default():
    r"""The development stage chooses on measurement properties (A79 67.4); until then a caller is
    told to name one, rather than handed a default that would become the decision by inaction."""
    with pytest.raises(ProtocolError) as ei:
        select_construction()
    assert "selected by default" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        select_construction("the_best_one")
    assert "not a candidate construction" in str(ei.value)
    assert select_construction("visited_complement") is CANDIDATE_CONSTRUCTIONS["visited_complement"]
    # a candidate that "wins" on a synthetic fixture is not thereby chosen
    assert set(CANDIDATE_CONSTRUCTIONS) == {"visited_complement", "state_parity"}


def test_3_the_unaffected_set_is_non_empty_and_duplicate_free():
    good = CANDIDATE_CONSTRUCTIONS["visited_complement"](DOMAIN, VISITED)
    assert good.contexts and set(good.contexts).isdisjoint(VISITED)
    assert good.construction == "visited_complement"
    with pytest.raises(ProtocolError) as ei:
        UnaffectedSet(contexts=(), construction="x")
    assert "empty" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        UnaffectedSet(contexts=(DOMAIN[0], DOMAIN[0]), construction="x")
    assert "duplicate" in str(ei.value)
    parity = CANDIDATE_CONSTRUCTIONS["state_parity"](DOMAIN, VISITED, parity=1)
    assert all(getattr(c[0], "x", 0) % 2 == 1 for c in parity.contexts)


# --------------------------------------------------------------------------- #
# 2. the metric: defined on exactly its set, blind, and calibrated
# --------------------------------------------------------------------------- #

def test_4_the_metric_is_defined_on_exactly_the_set_it_is_given():
    unaffected = CANDIDATE_CONSTRUCTIONS["visited_complement"](DOMAIN, VISITED)
    pre = {c: 1.0 for c in unaffected.contexts}
    post = dict(pre)
    assert behavioral_collateral(unaffected, values_pre=pre, values_post=post) == 0.0
    missing = dict(post)
    missing.pop(unaffected.contexts[0])
    with pytest.raises(ProtocolError) as ei:
        behavioral_collateral(unaffected, values_pre=pre, values_post=missing)
    assert "cover" in str(ei.value), "a missing context would shrink the denominator silently"
    extra = dict(post)
    extra[VISITED[0]] = 1.0
    with pytest.raises(ProtocolError):
        behavioral_collateral(unaffected, values_pre=pre, values_post=extra)
    with pytest.raises(ProtocolError) as ei:
        behavioral_collateral({c: 1.0 for c in unaffected.contexts}, values_pre=pre,
                              values_post=post)
    assert "not UnaffectedSet" in str(ei.value)
    bad = dict(post)
    bad[unaffected.contexts[0]] = True
    with pytest.raises(ProtocolError) as ei:
        behavioral_collateral(unaffected, values_pre=pre, values_post=bad)
    assert "not a real number" in str(ei.value)


def test_5_a_synthetic_injected_spillover_is_detected():
    r"""**Instrument calibration, not a development seed.** Damage $k$ contexts of the unaffected
    set by a known $\delta$ and require the metric to report $k\delta/|U|$ — the mean it declares.
    A metric that cannot see injected damage cannot see real collateral either."""
    unaffected = CANDIDATE_CONSTRUCTIONS["visited_complement"](DOMAIN, VISITED)
    n = len(unaffected.contexts)
    pre = {c: 1.0 for c in unaffected.contexts}
    for k in (1, 2, 3):
        post = dict(pre)
        for c in unaffected.contexts[:k]:
            post[c] = 0.25
        assert behavioral_collateral(unaffected, values_pre=pre, values_post=post) == \
            pytest.approx(k * 0.75 / n)
    # damage OUTSIDE the set must not be counted: that is what "unaffected" is for
    post = dict(pre)
    outside = CANDIDATE_CONSTRUCTIONS["visited_complement"](DOMAIN, VISITED[:1]).contexts[0]
    assert behavioral_collateral(unaffected, values_pre=pre, values_post=post) == 0.0
    assert outside not in unaffected.contexts


def test_6_every_candidate_construction_calibrates_on_the_same_fixture():
    r"""Both candidates detect the same injected damage. Which one is *primary* is not decided by
    which reports more — the calibration is about seeing damage at all."""
    for name, fn in CANDIDATE_CONSTRUCTIONS.items():
        unaffected = fn(DOMAIN, VISITED)
        if not unaffected.contexts:                                # pragma: no cover
            continue
        pre = {c: 1.0 for c in unaffected.contexts}
        post = dict(pre)
        for c in unaffected.contexts[:2]:
            post[c] = 0.0
        expected = 2 * 1.0 / len(unaffected.contexts)
        assert behavioral_collateral(unaffected, values_pre=pre,
                                     values_post=post) == pytest.approx(expected), name


# --------------------------------------------------------------------------- #
# 3. Retention: defined for every seed, and the diagnostic stays a diagnostic
# --------------------------------------------------------------------------- #

EPISODES = (0, 1, 2, 5, 10, 20, 40)
NEVER_RECOVERED = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70]
RECOVERED = [0.10, 0.20, 0.96, 0.97, 0.98, 0.99, 1.00]


def test_7_both_eligible_forms_are_defined_for_every_seed_including_never_recovered():
    r"""$$\boxed{\text{the confirmatory primary must be defined for EVERY seed}}$$ (A79 §67.5)

    Including a seed that never recovers: an eligible form may not quietly depend on $\tau$.
    """
    for values in (NEVER_RECOVERED, RECOVERED):
        at_h = RetentionAtH.value(values, EPISODES, H=20)
        late = LateWindowRetention.value(values, EPISODES, H1=10, H2=40)
        assert isinstance(at_h, float) and isinstance(late, float)
    assert RetentionAtH.value(NEVER_RECOVERED, EPISODES, H=20) == 0.60
    assert LateWindowRetention.value(RECOVERED, EPISODES, H1=10, H2=40) == \
        pytest.approx((0.98 + 0.99 + 1.00) / 3)
    assert RetentionAtH.always_defined is True and LateWindowRetention.always_defined is True


def test_8_the_conditional_form_is_a_diagnostic_by_type_and_by_registry():
    r"""`RetentionFraction` divides by the number of post-$\tau$ checkpoints, so it is undefined for
    a never-recovered seed. It is kept — it is a useful descriptive — but it is **not** in the
    candidate registry, and its role marker says so in the type rather than in a comment."""
    with pytest.raises(ProtocolError) as ei:
        retention_fraction(NEVER_RECOVERED, EPISODES, tau=None, pre_level=1.0)
    assert "undefined for a seed that never recovered" in str(ei.value)
    assert retention_fraction(RECOVERED, EPISODES, tau=2, pre_level=1.0) == pytest.approx(1.0)
    assert retention_fraction.role is RetentionRole.CONDITIONAL_DIAGNOSTIC
    assert retention_fraction.always_defined is False
    assert "RetentionFraction" not in CANDIDATE_FORMS
    assert "RetentionFraction" in DIAGNOSTIC_FORMS
    assert set(CANDIDATE_FORMS) == {"RetentionAtH", "LateWindowRetention"}


def test_9_no_form_or_window_is_selected_or_defaulted():
    r"""No default form, no defaulted $H$, $H_1$ or $H_2$: they are development-stage quantities
    (A83 §71.4), and a "reasonable" default in code would be the design decision made by whoever
    typed it."""
    with pytest.raises(ProtocolError) as ei:
        select_form()
    assert "selected by default" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        select_form("RetentionFraction")
    assert "conditional descriptive diagnostic" in str(ei.value)
    assert select_form("RetentionAtH") is CANDIDATE_FORMS["RetentionAtH"]
    for fn in (RetentionAtH.value, LateWindowRetention.value):
        assert inspect.signature(fn).parameters["H" if fn is RetentionAtH.value else "H1"] \
            .default is inspect.Parameter.empty
    with pytest.raises(ProtocolError) as ei:
        RetentionAtH.value(RECOVERED, EPISODES, H=7)
    assert "not a checkpoint" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        LateWindowRetention.value(RECOVERED, EPISODES, H1=20, H2=20)
    assert "empty or inverted" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        LateWindowRetention.value(RECOVERED, EPISODES, H1=11, H2=20)   # only episode 20 inside
    assert "at least two" in str(ei.value)


def test_10_the_machinery_is_in_the_audited_production_chain():
    r"""Collateral and Retention are part of the measurement instrument, so they join the same
    AST/import/dependency audit as the view, the producer and the environment."""
    from rfl_rebuild.b2 import assert_modules_are_closed
    from rfl_rebuild.b2.environment import audited_modules

    modules = audited_modules(ROOT / "src")
    names = {p.name for p in modules}
    assert {"collateral.py", "retention.py"} <= names, names
    assert_modules_are_closed(modules)
