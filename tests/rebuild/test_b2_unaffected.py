r"""A89 §77.3--§77.6 — the $U_2$-native ontology: Foundation, Gate C and Gate D.

$$\boxed{\text{defined} \;\neq\; \text{good enough}}$$

What is gated here is the instrument's *definability*, not its quality: scenes are typed keys, the
domain is complete, eligibility reads only what §77.4 allows, the set object is closed and proper, the
six refinements are intersections of one eligibility layer, the credited domains have executable
extents, and every refinement is non-empty at every credited unit -- all of it seedlessly, with no arm
and no measured value anywhere in the path. Whether a non-empty region is wide enough to report is the
development-stage question and is deliberately not asked here.

Each family also carries a hostile mutation, because a gate that cannot go red is not a gate.
"""

from __future__ import annotations

import inspect
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2 import assert_modules_are_closed  # noqa: E402
from rfl_rebuild.b2.environment import (  # noqa: E402
    PRODUCTION_MODULES,
    audited_modules,
)
from rfl_rebuild.b2.unaffected import (  # noqa: E402
    CHANNELS,
    REFINEMENTS,
    CreditedSite,
    EvaluationScene,
    UnaffectedSet,
    build_unaffected,
    credited_domain,
    eligibility,
    pre_update_traces,
    refinement,
    require_refinement_totality,
    scene_domain,
)
from rfl_rebuild.env.domain import decision_contexts  # noqa: E402
from rfl_rebuild.env.kernel import ControllerSite, State, option_ids  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

REFERENCE = reference_view_from(solve_reference())


@pytest.fixture(scope="module")
def traces():
    return pre_update_traces(q_reference=REFERENCE)


# --------------------------------------------------------------------------- #
# Foundation
# --------------------------------------------------------------------------- #

def test_1_scenes_are_strictly_typed_keys():
    r"""`True`, `1.0` and `1` fold into one key, so a scene that merely looks like a member is not one."""
    for bad in (dict(kappa=True, phase=0, error_flag=0, cause_rank=0, base_option=1),
                dict(kappa=0, phase=0.0, error_flag=0, cause_rank=0, base_option=1),
                dict(kappa=0, phase=0, error_flag=0, cause_rank=0.5, base_option=1)):
        with pytest.raises(ProtocolError):
            EvaluationScene(**bad)
    for bad in (dict(kappa=2, phase=0, error_flag=0, cause_rank=0, base_option=1),
                dict(kappa=0, phase=9, error_flag=0, cause_rank=0, base_option=1),
                dict(kappa=0, phase=0, error_flag=2, cause_rank=0, base_option=1),
                dict(kappa=0, phase=0, error_flag=0, cause_rank=60, base_option=1),
                dict(kappa=0, phase=0, error_flag=0, cause_rank=0, base_option=9)):
        with pytest.raises(ProtocolError):
            EvaluationScene(**bad)


def test_2_the_domain_is_complete_unique_and_ordered():
    r"""$U_2 = \mathcal K \times \mathcal T \times \mathcal Z$: $2 \times 720 \times 4 = 5760$."""
    domain = scene_domain()
    assert len(domain) == len(set(domain)) == 5760
    assert tuple(sorted(domain, key=lambda s: s.key)) == domain
    assert {s.kappa for s in domain} == {0, 1}
    assert {s.phase for s in domain} == set(range(6))
    assert {s.error_flag for s in domain} == {0, 1}
    assert {s.cause_rank for s in domain} == set(range(60))
    assert {s.base_option for s in domain} == set(option_ids())


def test_3_eligibility_reads_only_the_credited_unit_and_the_unedited_trajectory(traces):
    r"""§77.4's admissible input surface, as a signature rather than a promise.

    There is no learner, no update, no arm and no canary parameter: eligibility cannot read what it is
    not handed, and the trajectory it does read is the $W_{\text{pre}}$ one by construction.
    """
    parameters = list(inspect.signature(eligibility).parameters)
    assert parameters == ["site", "traces", "domain"]
    assert inspect.signature(eligibility).parameters["domain"].kind is inspect.Parameter.KEYWORD_ONLY
    for forbidden in ("learner", "update", "arm", "delta", "canary", "post"):
        assert not any(forbidden in p for p in parameters)
    site = CreditedSite("P", 0)
    once = eligibility(site, traces)
    assert once == eligibility(site, traces), "eligibility must be deterministic"
    assert set(once) <= set(scene_domain())


def test_4_the_unaffected_set_is_closed_nonempty_proper_and_ordered(traces):
    r"""One object is the set, and it refuses the two ways a region stops being one."""
    site = CreditedSite("P", 0)
    units = refinement(site, traces, "eligible_all")
    assert units
    built = build_unaffected(site, traces, "eligible_all")
    assert built.units == units and built.size == len(units)
    assert built.construction.startswith("E1(c=") and built.construction.endswith("@eligible_all")
    with pytest.raises(ProtocolError):
        UnaffectedSet(units=(), construction="empty")
    with pytest.raises(ProtocolError):
        UnaffectedSet(units=units + (units[0],), construction="duplicate")
    with pytest.raises(ProtocolError):
        UnaffectedSet(units=scene_domain(), construction="the whole domain")
    with pytest.raises(ProtocolError):
        UnaffectedSet(units=tuple(reversed(units)), construction="unordered")


def test_5_the_six_refinements_are_intersections_of_one_eligibility_layer(traces):
    r"""$C_i(c) = E(c) \cap S_i$, and the even/odd pair partitions $E(c)$ -- not $U_2$."""
    site = CreditedSite("P", 0)
    base = eligibility(site, traces)
    for name in REFINEMENTS:
        assert set(refinement(site, traces, name)) <= set(base), name
    even = set(refinement(site, traces, "eligible_phase_even"))
    odd = set(refinement(site, traces, "eligible_phase_odd"))
    assert even.isdisjoint(odd)
    assert even | odd == set(base)
    assert len(base) < len(scene_domain())
    with pytest.raises(ProtocolError):
        refinement(site, traces, "eligible_whatever")


# --------------------------------------------------------------------------- #
# Gate C -- production credited-domain completeness
# --------------------------------------------------------------------------- #

def _recompute_x_extent(traces) -> set:
    r"""An independent re-derivation of $\mathcal D^{\text{credit}}_X$ from the traces."""
    out = set()
    for scene in scene_domain():
        for state, _control, step in traces.walk(scene):
            out.add(ControllerSite(state=state, cmd=step.u))
    return out


def test_gate_c_the_credited_domains_have_executable_extents(traces):
    r"""$\forall c$ without an enumerator is prose: each channel's population is named and finite."""
    dq = credited_domain("D_Q", traces)
    p = credited_domain("P", traces)
    x = credited_domain("X", traces)
    assert len(dq) == len(decision_contexts()) == 13824
    assert [c.address for c in p] == list(option_ids())
    assert x, "the X extent is not empty"
    assert {c.address for c in x} == _recompute_x_extent(traces), (
        "the X extent must be exactly the sites the unedited episodes construct, not a subset")
    for channel, domain in (("D_Q", dq), ("X", x), ("P", p)):
        assert len({c.render() for c in domain}) == len(domain), f"{channel}: duplicates"
        assert all(c.channel == channel for c in domain)
    assert CHANNELS == ("D_Q", "X", "P")


def test_gate_c_mutation_a_dropped_credited_site_reddens(traces):
    r"""A shortened enumerator must fail the completeness gate, or "$\forall c$" narrows silently."""
    x = credited_domain("X", traces)
    assert len(x) > 1
    shortened = x[:-1]
    assert {c.address for c in shortened} != _recompute_x_extent(traces)
    assert {c.address for c in x} == _recompute_x_extent(traces)


# --------------------------------------------------------------------------- #
# Gate D -- refinement-level totality
# --------------------------------------------------------------------------- #

def test_gate_d_refinement_totality_holds_over_the_credited_domains(traces):
    r"""$\forall c, i:\ C_i(c) \neq \varnothing$ — executed, not inferred from $E(c) \neq \varnothing$."""
    for channel in CHANNELS:
        sizes = require_refinement_totality(channel, traces)
        assert set(sizes) == set(REFINEMENTS)
        for name, per_site in sizes.items():
            assert per_site, (channel, name)
            assert all(size > 0 for size in per_site.values()), (channel, name)


def test_gate_d_mutation_an_impossible_slice_reddens(traces, monkeypatch):
    r"""A refinement that is empty somewhere is inadmissible now, not a coverage statistic later."""
    from rfl_rebuild.b2 import unaffected as module

    real = module._slice
    monkeypatch.setattr(module, "_slice",
                        lambda name, scene: False if name == "eligible_phase_odd" else real(name, scene))
    with pytest.raises(ProtocolError):
        require_refinement_totality("P", traces)
    monkeypatch.setattr(module, "_slice", real)
    assert require_refinement_totality("P", traces)


def test_gate_d_totality_is_asked_of_every_registered_channel(traces):
    r"""The three channels are not interchangeable: $P$'s extent is 4 units, $X$'s is the site set."""
    counts = {}
    for channel in CHANNELS:
        domain = credited_domain(channel, traces)
        counts[channel] = len(domain)
        site = domain[0]
        base = eligibility(site, traces)
        assert base, channel
        for name in REFINEMENTS:
            assert refinement(site, traces, name), (channel, site.render(), name)
    assert counts["P"] == 4 and counts["D_Q"] == 13824 and 0 < counts["X"] < 5760


# --------------------------------------------------------------------------- #
# The audit
# --------------------------------------------------------------------------- #

def test_10_the_ontology_is_inside_the_audited_production_chain():
    assert "rfl_rebuild/b2/unaffected.py" in PRODUCTION_MODULES
    assert_modules_are_closed(audited_modules(ROOT / "src"))
    source = pathlib.Path(ROOT / "src" / "rfl_rebuild" / "b2" / "unaffected.py").read_text(
        encoding="utf-8")
    for forbidden in ("learned_rollout(", "behavioral_collateral", "measured", "post_update"):
        if forbidden == "learned_rollout(":
            assert source.count(forbidden) == 1, "only the pre-update trace builder may roll out"
        else:
            assert forbidden not in source, f"eligibility may not touch {forbidden}"
