r"""A88 §76.2/§76.6 — the screening harness's own gates.

$$\boxed{\text{the harness is part of the instrument, so it is gated like one}}$$

Four families, each aimed at a way the screening could be wrong while producing a finished-looking
matrix:

* **the domains** — $U_1 = \mathcal X_D$ and $U_2 = \mathcal K \times \mathcal T \times \mathcal Z$
  enumerated in full and legally, with the frozen tape support rather than a convenient subset;
* **the closed map** — missing units, extra units and non-finite values refused, and no short-circuit
  on a positive: `BLIND` needs $\forall u: \Delta V(u) = 0$, so the extent of the map may not depend
  on what it finds;
* **the frozen status function** — A86 §74.3's four labels as a partition, with `BLIND`'s precedence
  and, in particular, the **zero measured sign**: $\Delta V(u^*) = 0$ with another unit moving is
  `DIRECTION_FAIL`, not an error;
* **the A88 fixture rule** — the strengthened structurally valid set, from which the new X witness
  follows as its least element, and the domain-wide legality that the old fixture lacked.

No seed is drawn and no verdict is produced here: the screened cells are the subject of the run, not
of these gates. What is asserted about them is the *rule*, never the outcome.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2.continuation import continuation, exogenous_lift  # noqa: E402
from rfl_rebuild.b2.environment import learned_rollout  # noqa: E402
from rfl_rebuild.b2.screening import (  # noqa: E402
    ARCHITECTURES,
    DECLARED_DIRECTION,
    STATUS_BLIND,
    STATUS_DIRECTION_FAIL,
    STATUS_DIRECTION_UNRESOLVED,
    STATUS_STRUCTURAL_PASS,
    STATUSES,
    STRUCTURAL_REJECT,
    UNIT_1,
    UNIT_2,
    VERDICT_ALL_REJECTED,
    VERDICT_INCONCLUSIVE,
    VERDICT_SURVIVES,
    WITNESS_STATE,
    WITNESS_SUFFIX_STEP,
    X_SITE,
    _require_closed,
    aggregate_verdict,
    canary_edit,
    cell_status,
    learner_prestate,
    measure_map,
    u1_domain,
    u2_domain,
    witness,
)
from rfl_rebuild.env.domain import is_decision_context  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    START,
    ControlState,
    ControllerSite,
    LearnerContractViolation,
    SemanticTape,
    State,
    option_actions,
    option_ids,
)
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    CONTROLLER,
    PROCESS,
    Q,
    Edit,
    LearnerPersistentState,
    QAddress,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

REFERENCE = reference_view_from(solve_reference())
TAPE = SemanticTape(phase=0, error_flag=0, cause_rank=0)


# --------------------------------------------------------------------------- #
# 1-2. the domains
# --------------------------------------------------------------------------- #

def test_1_the_domains_are_complete_and_legal():
    r"""$|U_1| = 13824$ from the frozen enumerator, $|U_2| = 2 \times 720 \times 4 = 5760$."""
    u1, u2 = u1_domain(), u2_domain()
    assert len(u1) == len(set(u1)) == 13824
    assert len(u2) == len(set(u2)) == 5760
    assert all(is_decision_context(s, z, m) for (s, z, m) in u1)
    tapes = {t for (_k, t, _b) in u2}
    assert len(tapes) == 6 * 2 * 60, "the tape support must be the frozen one, not a subset"
    assert {k for (k, _t, _b) in u2} == {0, 1}
    assert {b for (_k, _t, b) in u2} == set(option_ids())


def test_2_the_witness_images_are_members_of_their_domains():
    r"""$g_U(\xi_A^*) \in U$ for all six cells: coverage's representation clause (A86 §74.3)."""
    for unit in (UNIT_1, UNIT_2):
        domain = u1_domain() if unit == UNIT_1 else u2_domain()
        for arch in ARCHITECTURES:
            assert witness(unit, arch) in domain, (unit, arch)
    assert witness(UNIT_1, "X") == (X_SITE, 1, 0)
    assert witness(UNIT_2, "X") == (0, TAPE, 1)
    assert WITNESS_SUFFIX_STEP == {"D_Q": 0, "X": 2, "P": 0}


# --------------------------------------------------------------------------- #
# 3. the closed nominal map
# --------------------------------------------------------------------------- #

def test_3_missing_extra_and_non_finite_units_are_refused():
    r"""$V_W^{meas} : U \to \mathbb{R}_{\text{finite}}$ — closed in its keys **and** its values."""
    domain = ((1,), (2,))
    with pytest.raises(ProtocolError):
        _require_closed({(1,): 0.5}, domain, UNIT_1)
    with pytest.raises(ProtocolError):
        _require_closed({(1,): 0.5, (2,): 0.5, (3,): 0.5}, domain, UNIT_1)
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ProtocolError):
            _require_closed({(1,): 0.5, (2,): bad}, domain, UNIT_1)
    _require_closed({(1,): 0.5, (2,): -0.02}, domain, UNIT_1)


def test_4_the_map_is_completed_rather_than_short_circuited():
    r"""A positive found early must not shorten the map: `BLIND` needs $\forall u: \Delta V(u) = 0$.

    The $\mathcal C_{D_Q}$ edit moves the very first unit of the ordering, so a short-circuiting
    implementation would return a one-element map here.
    """
    learner = learner_prestate("D_Q", q_reference=REFERENCE)
    measured = measure_map(learner, UNIT_1, q_reference=REFERENCE)
    pre = measure_map(learner_prestate(None, q_reference=REFERENCE), UNIT_1, q_reference=REFERENCE)
    assert len(measured) == len(pre) == 13824
    moved = [i for i, u in enumerate(pre) if measured[u] != pre[u]]
    assert moved, "the D_Q edit must move at least one unit"
    assert len(measured) > moved[0] + 1, (
        "the map stopped near the first difference: BLIND needs forall-u equality, so the map is "
        "completed rather than short-circuited")


# --------------------------------------------------------------------------- #
# 5. the frozen status function
# --------------------------------------------------------------------------- #

def test_5_the_status_function_is_a_partition_with_blinds_precedence():
    r"""A86 §74.3: four mutually exclusive labels, and `BLIND` wins over the direction statuses."""
    seen = set()
    for coverage in (True, False):
        for detection in (True, False):
            for d_A in (+1, -1, STATUS_DIRECTION_UNRESOLVED):
                for measured in (-1, 0, +1):
                    status = cell_status(coverage=coverage, detection=detection, d_A=d_A,
                                         measured=measured)
                    assert status in STATUSES
                    seen.add(status)
                    if not coverage or not detection:
                        assert status == STATUS_BLIND
                    elif d_A == STATUS_DIRECTION_UNRESOLVED:
                        assert status == STATUS_DIRECTION_UNRESOLVED
                    else:
                        expected = (STATUS_STRUCTURAL_PASS if measured == d_A
                                    else STATUS_DIRECTION_FAIL)
                        assert status == expected
    assert seen == set(STATUSES), "every label must be reachable, or the space is not the frozen one"
    assert STATUS_DIRECTION_UNRESOLVED not in STRUCTURAL_REJECT


def test_6_a_zero_measured_sign_is_a_direction_failure_not_an_error():
    r"""The regression that freezes A88 §76.6 (a).

    $$\Delta V(u^*) = 0 \ \land\ \exists u' \neq u^*: \Delta V(u') \neq 0
    \;\Longrightarrow\; \texttt{DIRECTION\_FAIL}$$

    Reading the zero as a protocol error would collapse `DIRECTION_FAIL` into a crash and re-open the
    `BLIND`-versus-`DIRECTION_FAIL` distinction A86 §74.3 exists to keep.
    """
    assert cell_status(coverage=True, detection=True, d_A=+1, measured=0) == STATUS_DIRECTION_FAIL
    assert cell_status(coverage=True, detection=True, d_A=-1, measured=0) == STATUS_DIRECTION_FAIL
    # an unresolved direction has no equality test to fail, so the measured value is not consulted
    assert cell_status(coverage=True, detection=True, d_A=STATUS_DIRECTION_UNRESOLVED,
                       measured=0) == STATUS_DIRECTION_UNRESOLVED
    with pytest.raises(ProtocolError):
        cell_status(coverage=True, detection=True, d_A=+2, measured=+1)


# --------------------------------------------------------------------------- #
# 7. the aggregate rules
# --------------------------------------------------------------------------- #

def _cell(unit, arch, status):
    return type("C", (), {"unit": unit, "arch": arch, "status": status,
                          "rejected": status in STRUCTURAL_REJECT})()


def _matrix(overrides=None):
    """A complete 2 x 3 matrix, all PASS except the pairs named in ``overrides``."""
    overrides = overrides or {}
    return [_cell(u, a, overrides.get((u, a), STATUS_STRUCTURAL_PASS))
            for u in (UNIT_1, UNIT_2) for a in ARCHITECTURES]


def test_7_the_three_aggregate_rules_fire_in_their_frozen_order():
    r"""A86 §74.4's three rules, in their own order, including the third.

    The first rule is **existential in the candidate**: one candidate passing all three architectures
    is enough, so a rejected cell elsewhere does not stop it. That is exactly why the present
    instance's survival route runs through $U_2$ alone, and why the third rule is reachable only when
    no candidate passes everything and none is rejected somewhere either.
    """
    # rule 1: some candidate passes all three
    assert aggregate_verdict(_matrix()) == VERDICT_SURVIVES
    assert aggregate_verdict(_matrix({(UNIT_1, "P"): STATUS_BLIND})) == VERDICT_SURVIVES
    assert aggregate_verdict(_matrix({(UNIT_1, "P"): STATUS_BLIND,
                                      (UNIT_1, "D_Q"): STATUS_DIRECTION_FAIL})) == VERDICT_SURVIVES
    # rule 3: $U_1$ rejected somewhere, $U_2$ unresolved somewhere -- neither rule 1 nor rule 2 fires
    unresolved = _matrix({(UNIT_1, "P"): STATUS_BLIND, (UNIT_2, "P"): STATUS_DIRECTION_UNRESOLVED})
    assert aggregate_verdict(unresolved) == VERDICT_INCONCLUSIVE
    assert any(c.rejected for c in unresolved), "the third rule is not 'nothing was rejected'"
    # rule 2: every candidate is rejected on at least one architecture
    assert aggregate_verdict(_matrix({(UNIT_1, "P"): STATUS_BLIND,
                                      (UNIT_2, "P"): STATUS_DIRECTION_FAIL})) == VERDICT_ALL_REJECTED
    assert aggregate_verdict(_matrix({(UNIT_1, "P"): STATUS_BLIND,
                                      (UNIT_2, "X"): STATUS_BLIND})) == VERDICT_ALL_REJECTED
    # an unresolved cell is not a rejection, so it cannot carry rule 2 on its own
    assert aggregate_verdict(_matrix({(UNIT_1, "P"): STATUS_DIRECTION_UNRESOLVED,
                                      (UNIT_2, "X"): STATUS_BLIND})) == VERDICT_INCONCLUSIVE
    assert DECLARED_DIRECTION == {"D_Q": +1, "X": +1, "P": +1}


def test_7b_the_aggregate_fails_closed_on_an_incomplete_matrix():
    r"""A86's conclusions live on the 2 x 3 matrix, so a subset that looks evaluable earns nothing.

    Same discipline as the closed nominal map, applied to the cells: missing, extra and duplicated
    entries are all refused rather than silently aggregated.
    """
    complete = _matrix()
    with pytest.raises(ProtocolError):
        aggregate_verdict([c for c in complete if c.arch != "P"])              # missing architecture
    with pytest.raises(ProtocolError):
        aggregate_verdict([c for c in complete if c.unit != UNIT_2])           # missing unit
    with pytest.raises(ProtocolError):
        aggregate_verdict(complete[:1])                                        # a single cell
    with pytest.raises(ProtocolError):
        aggregate_verdict(complete + [_cell(UNIT_1, "P", STATUS_BLIND)])       # duplicate pair
    with pytest.raises(ProtocolError):
        aggregate_verdict(complete[:-1] + [_cell(UNIT_3 := "U3", "P", STATUS_BLIND)])  # extra unit
    with pytest.raises(ProtocolError):
        aggregate_verdict(complete[:-1] + [_cell(UNIT_1, "Z", STATUS_BLIND)])  # extra architecture


# --------------------------------------------------------------------------- #
# 8-9. the A88 fixture rule, and the defect it fixes
# --------------------------------------------------------------------------- #

def _healthy_path_contexts():
    r"""The contexts the frozen healthy path acts from, paired with the command it sends from each.

    Entry $0$ is the episode start under the commit edge's own option, and entry $j \geq 1$ is the
    state and control step $j-1$ left behind -- so `trace.steps[j].a_cmd` is the command sent from
    entry $j$, and the pairing is exact rather than reconstructed.
    """
    learner = learner_prestate(None, q_reference=REFERENCE)
    trace = learned_rollout(learner, kappa=0, tape=TAPE, base_option=1, q_reference=REFERENCE)
    contexts = [(WITNESS_STATE, ControlState(z=1, m=0))]
    for step in trace.steps[:-1]:
        contexts.append((step.state, step.control))
    return trace, contexts


def test_8_the_new_X_witness_is_what_the_strengthened_rule_selects():
    r"""A88 §76.2: *canonical = least element of the declared structurally valid set*.

    The rule is strengthened with $\bigcap_{z,m} A_z(m,s) \ni a'$, and the fixture is then what the
    rule implies -- not a friendlier site chosen after a run. The old START witness is excluded by
    the constraint itself, which this gate shows alongside the derivation of the new one.
    """
    trace, contexts = _healthy_path_contexts()
    valid = []
    for index, (state, control) in enumerate(contexts):
        cmd = trace.steps[index].a_cmd
        common = set.intersection(*[set(option_actions(zz, ControlState(z=zz, m=mm), state))
                                    for zz in option_ids() for mm in (0, 1)])
        alternatives = sorted(common - {cmd})
        if alternatives:
            valid.append(((state, control.z, control.m), cmd, alternatives[0]))
    assert valid, "the strengthened rule must admit at least one site"
    # A87's canonical rule is the **lexicographically first** valid element; selecting `valid[0]`
    # would silently rely on path order happening to agree with it.
    selected = min(valid, key=lambda item: (item[0][0].x, item[0][0].y, item[0][0].t,
                                            item[0][0].kappa, item[0][0].phi,
                                            item[1], item[2]))
    assert len(valid) >= 2, "the path must offer more than one valid site, or the rule is untested"
    assert selected == valid[0] or selected[0][0].t < valid[0][0].t
    ((state, z, m), cmd, target) = selected
    assert (state, z, m) == (X_SITE, 1, 0)
    assert (cmd, target) == (3, 1)
    # the old witness is excluded by the rule, not by preference
    start_common = set.intersection(*[set(option_actions(zz, ControlState(z=zz, m=mm), WITNESS_STATE))
                                      for zz in option_ids() for mm in (0, 1)])
    assert sorted(start_common - {3}) == []


def test_9_the_X_edit_is_legal_on_the_whole_frozen_domain():
    r"""The defect A88 fixes, as a regression: no unit may raise `LearnerContractViolation`.

    A87's fixture raised on $2/13824$ $U_1$ units and $120/5760$ $U_2$ scenes because its legality was
    witness-local. A screening must not skip those units -- A86's detection is quantified over $U$ --
    so the fixture has to be legal where it fires, and this gate is what says so.
    """
    learner = learner_prestate("X", q_reference=REFERENCE)
    assert canary_edit("X") == Edit(CONTROLLER, ControllerSite(state=X_SITE, cmd=3), 1)
    for (s, z, m) in u1_domain():
        continuation(learner=learner, state=s, z=z, m=m, kappa=s.kappa,
                     tape=exogenous_lift(s, z, m), q_reference=REFERENCE)
    for (kappa, tape, base) in u2_domain():
        learned_rollout(learner, kappa=kappa, tape=tape, base_option=base, q_reference=REFERENCE)
    # and the other two edits are legal on **both** domains as well, so the defect was X-specific
    for arch in ("D_Q", "P"):
        other = learner_prestate(arch, q_reference=REFERENCE)
        for (s, z, m) in u1_domain():
            continuation(learner=other, state=s, z=z, m=m, kappa=s.kappa,
                         tape=exogenous_lift(s, z, m), q_reference=REFERENCE)
        for (kappa, tape, base) in u2_domain():
            learned_rollout(other, kappa=kappa, tape=tape, base_option=base,
                            q_reference=REFERENCE)


# --------------------------------------------------------------------------- #
# 10. one shared reference artifact
# --------------------------------------------------------------------------- #

def test_10_the_harness_takes_exactly_one_reference_artifact():
    r"""A86 §74.1: the view is a fixed measurement-instrument dependency, so a per-cell reference
    would be a different instrument per cell -- and the difference would read as a candidate effect.
    """
    import inspect
    from rfl_rebuild.b2 import screening
    for name in ("run_screening", "measure_map", "learner_prestate"):
        parameters = inspect.signature(getattr(screening, name)).parameters
        assert "q_reference" in parameters
        assert not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())
        assert not [p for p in parameters if "reference" in p and p != "q_reference"]
    source = pathlib.Path(screening.__file__).read_text(encoding="utf-8")
    assert "solve_reference" not in source, "the harness may not solve its own reference"
