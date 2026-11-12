r"""A89 §77.7/§77.9 — Gate B, Gate E, and the predicted side of Gate A.

$$\boxed{\text{owner}_A(\Delta W^{\text{spill}}_A) = s^{\text{spill}}_{C,A} \neq c^{\text{cal}}_A}$$

Gate B certifies the $D_Q$ chain end to end: the credited site is a `DecisionAddress`, the store key is
an exact `QAddress` whose `owner_Q` projects onto it, and the edit travels through the substrate's own
transaction. Gate E certifies the chain's integrity: deterministic at every arrow, off target at credited
granularity, $\mathcal I_A$ the only source of a target, and `CALIBRATION_FAIL` rather than a relocated
fixture when no unit qualifies. The predicted side of Gate A is checked for provenance here -- it may
read the frozen solver, $C$ and the edit, and nothing the measurement produced -- while the equality with
the **measured** collateral needs the scene-level collateral instrument and is the remaining piece.

Each family carries hostile mutations, because a gate that cannot go red is not a gate.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2 import assert_modules_are_closed  # noqa: E402
from rfl_rebuild.b2.calibration import (  # noqa: E402
    CAL_SITES,
    SpilloverEdit,
    aggregate_reference,
    cal_site,
    predicted_pre_value,
    predicted_spill_value,
    spillover_edit,
)
from rfl_rebuild.b2.collateral import measured_scene_collateral  # noqa: E402
from rfl_rebuild.b2.environment import PRODUCTION_MODULES, audited_modules  # noqa: E402
from rfl_rebuild.b2.unaffected import (  # noqa: E402
    REFINEMENTS,
    CreditedSite,
    pre_update_traces,
    refinement,
)
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControlState,
    ControllerSite,
    State,
    option_actions,
    option_ids,
)
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    CONTROLLER,
    PROCESS,
    Q,
    DecisionAddress,
    Edit,
    LearnerPersistentState,
    QAddress,
    StoreTransactionError,
    owner_Q,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

SOLUTION = solve_reference()
REFERENCE = reference_view_from(SOLUTION)
MODULE = ROOT / "src" / "rfl_rebuild" / "b2" / "calibration.py"


@pytest.fixture(scope="module")
def traces():
    # the calibration world's own W_pre is the healthy empty state, stated rather than minted
    return pre_update_traces(learner=LearnerPersistentState(), q_reference=REFERENCE)


def _walk(traces, scene):
    return traces.walk(scene)


# --------------------------------------------------------------------------- #
# Gate B -- the D_Q store-key and owner chain
# --------------------------------------------------------------------------- #

def test_gate_b_the_dq_chain_is_exact_and_travels_through_the_substrate(traces):
    r"""credited site -> store key -> substrate edit, with no layer left to inference."""
    edit = spillover_edit("D_Q", traces, "eligible_all", solution=SOLUTION)
    assert type(edit.channel_address) is QAddress
    assert type(edit.site.address) is DecisionAddress
    assert owner_Q(edit.channel_address) == edit.site.address == edit.edited_context
    assert edit.site.render() != cal_site("D_Q").render()
    assert edit.substrate_edit.store == Q
    assert type(edit.substrate_edit.address) is QAddress
    assert edit.substrate_edit.address == edit.channel_address

    context = edit.channel_address
    control = ControlState(z=context.z, m=context.m)
    allowed = sorted(option_actions(context.z, control, context.state))
    values = {a: SOLUTION.q_value(context.state, context.z, context.m, a) for a in allowed}
    # the row edited is the one the trajectory's own action uses, and the applied action is the
    # post-edit argmax rather than a number re-derived later
    assert context.a in allowed and len(allowed) >= 2
    assert edit.substrate_edit.value == min(values.values()) - 1.0
    assert edit.applied_action == max((a for a in allowed if a != context.a),
                                      key=lambda a: values[a])

    learner = LearnerPersistentState()
    learner.apply_transaction([edit.substrate_edit], q_reference=REFERENCE)
    assert learner.q_overrides, "the edit must land in the substrate's own store"
    assert learner.healthy is False


def test_gate_b_mutations_redden(traces):
    r"""Three ways to break the chain, each one caught by the assertion that owns it."""
    edit = spillover_edit("D_Q", traces, "eligible_all", solution=SOLUTION)

    # (i) a DecisionAddress where the store requires a QAddress: the substrate refuses the type
    with pytest.raises((StoreTransactionError, ProtocolError)):
        LearnerPersistentState().apply_transaction(
            [Edit(Q, edit.site.address, -0.12)], q_reference=REFERENCE)

    # (ii) the same row's *other* action: the edit is still a legal QAddress and still owned by the
    #      credited site, but it is no longer the row the trajectory uses, so the applied action
    #      derived from it differs -- which is why the chain asserts the action rather than the address
    context = edit.channel_address
    control = ControlState(z=context.z, m=context.m)
    others = [a for a in sorted(option_actions(context.z, control, context.state)) if a != context.a]
    assert others, "the gate needs a row whose action is not the taken one"
    values = {a: SOLUTION.q_value(context.state, context.z, context.m, a)
              for a in option_actions(context.z, control, context.state)}
    wrong = Edit(Q, QAddress(state=context.state, z=context.z, m=context.m, a=others[0]),
                 min(values.values()) - 1.0)
    assert wrong.address != context, "the wrong-action edit must differ from the frozen one"
    wrong_applied = max((a for a in values if a != others[0]), key=lambda a: values[a])
    assert wrong_applied != edit.applied_action

    # (iii) an owner that does not project onto the synthetic credited site: the selection refuses it
    assert owner_Q(edit.channel_address) != cal_site("D_Q").address


def test_gate_b_the_x_and_p_channels_are_owned_by_identity(traces):
    r"""$\text{owner}_X$ and $\text{owner}_P$ are the identity, and the sites still differ from $c^{\text{cal}}$."""
    x = spillover_edit("X", traces, "eligible_all", solution=SOLUTION)
    p = spillover_edit("P", traces, "eligible_all", solution=SOLUTION)
    assert x.site.address == x.channel_address and x.substrate_edit.store == CONTROLLER
    # A88 §76.2's contract-preservation rule: the target is admissible for **every** (z, m)
    common = None
    for z in option_ids():
        for m in (0, 1):
            allowed = set(option_actions(z, ControlState(z=z, m=m), x.site.address.state))
            common = allowed if common is None else (common & allowed)
    assert x.target in common and x.target != x.site.address.cmd
    assert p.site.address == p.channel_address and p.substrate_edit.store == PROCESS
    assert p.target == min(set(option_ids()) - {p.channel_address})
    for channel, edit in (("X", x), ("P", p)):
        assert edit.site.render() != cal_site(channel).render()


# --------------------------------------------------------------------------- #
# Gate E -- calibration chain integrity
# --------------------------------------------------------------------------- #

def test_gate_e_every_arrow_is_deterministic_and_off_target(traces):
    r"""Same inputs, same fixture; and the two sites differ at credited granularity for every cell."""
    for channel in ("D_Q", "X", "P"):
        first = spillover_edit(channel, traces, "eligible_all", solution=SOLUTION)
        again = spillover_edit(channel, traces, "eligible_all", solution=SOLUTION)
        assert first == again
        assert type(first) is SpilloverEdit
        assert first.site.render() != cal_site(channel).render(), (
            "the off-target inequality is a theorem at credited granularity, not a type accident")
        assert first.unit in refinement(cal_site(channel), traces, "eligible_all")


def test_gate_e_mutation_an_unreachable_injection_fails_closed(traces, monkeypatch):
    r"""`CALIBRATION_FAIL` — no relocated site, no substituted target, no narrowed candidate."""
    from rfl_rebuild.b2 import calibration as module

    monkeypatch.setattr(module, "_make_edit", lambda *a, **k: None)
    with pytest.raises(ProtocolError) as excinfo:
        module.spillover_edit("D_Q", traces, "eligible_all", solution=SOLUTION)
    assert module.CALIBRATION_FAIL in str(excinfo.value)
    monkeypatch.undo()
    assert spillover_edit("D_Q", traces, "eligible_all", solution=SOLUTION)


def test_gate_e_mutation_a_next_site_selector_differs_from_the_frozen_one(traces):
    r"""Taking the next candidate when the canonical one is unavailable is not the frozen rule."""
    channel = "D_Q"
    c_cal = cal_site(channel)
    units = refinement(c_cal, traces, "eligible_all")
    from rfl_rebuild.b2.calibration import _consulted_channel_sites, _make_edit, _owner_of

    candidates = []
    for scene in units:
        for address in _consulted_channel_sites(channel, traces, scene):
            if _owner_of(channel, address, SOLUTION).render() == c_cal.render():
                continue
            if _make_edit(channel, SOLUTION, traces, scene, address) is not None:
                candidates.append((scene, address))
    assert len(candidates) >= 2, "the gate needs more than one candidate to be meaningful"
    frozen = spillover_edit(channel, traces, "eligible_all", solution=SOLUTION)
    assert (frozen.unit, frozen.channel_address) == candidates[0]
    hostile_scene, hostile_address = candidates[1]
    made = _make_edit(channel, SOLUTION, traces, hostile_scene, hostile_address)
    assert hostile_address != frozen.channel_address or hostile_scene != frozen.unit
    assert made is not None


def test_gate_e_mutation_a_caller_supplied_target_is_not_the_rule(traces):
    r"""$\mathcal I_A$ is the only source of a target: a caller may not hand one in."""
    import inspect
    parameters = inspect.signature(spillover_edit).parameters
    for forbidden in ("target", "action", "value", "edit"):
        assert forbidden not in parameters, f"{forbidden} must not be callable in"
    x = spillover_edit("X", traces, "eligible_all", solution=SOLUTION)
    # a caller-chosen target outside the common admissible set would violate A88's contract, which
    # the frozen rule cannot produce
    common = None
    for z in option_ids():
        for m in (0, 1):
            allowed = set(option_actions(z, ControlState(z=z, m=m), x.site.address.state))
            common = allowed if common is None else (common & allowed)
    outside = sorted(set(option_ids()) - common)
    if outside:
        assert outside[0] != x.target


# --------------------------------------------------------------------------- #
# The predicted side of Gate A
# --------------------------------------------------------------------------- #

def test_gate_a_the_reference_is_aggregate_and_provenance_restricted(traces):
    r"""$B^{ref}_{C,A}$ is a mean over the candidate, and it may not read what it judges."""
    # Provenance is read off the **code**, not the prose: the module's docstrings legitimately name
    # the measured side it must not touch, so a substring scan would fail on its own documentation.
    import ast
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    calls = {n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    for forbidden in ("behavioral_collateral", "learned_rollout", "apply_transaction",
                      "post_oracle", "LearnerPersistentState"):
        assert forbidden not in names | attributes | calls, f"the prediction may not touch {forbidden}"
    assert "value" in attributes and "q_value" in attributes
    result = aggregate_reference("P", traces, "eligible_all", solution=SOLUTION)
    units = refinement(cal_site("P"), traces, "eligible_all")
    contributions = result["contributions"]
    assert set(contributions) == set(units)
    assert result["size"] == len(units)
    mean = sum(contributions[u] for u in units) / len(units)
    assert result["B_ref"] == pytest.approx(mean)
    assert result["d_ref"] == (1 if result["B_ref"] > 0 else -1)
    # units that do not consult the edited address contribute exactly nothing
    edit = result["edit"]
    untouched = [u for u in units if u.base_option != edit.channel_address]
    assert untouched, "the P edit fires on some but not all units"
    assert all(contributions[u] == pytest.approx(0.0) for u in untouched)
    assert any(contributions[u] != 0.0 for u in units)


def test_gate_a_the_predictions_are_frozen_row_reads_not_simulations(traces):
    r"""$V^{ref}_{\text{pre}}$ is the solver's own entry value, and the spill value agrees where the
    trajectory never meets the edit."""
    for channel in ("X", "P"):
        result = aggregate_reference(channel, traces, "eligible_all", solution=SOLUTION)
        edit = result["edit"]
        entry = State(x=0, y=2, t=0, kappa=edit.unit.kappa, phi=edit.unit.phase)
        pre = predicted_pre_value(channel, edit.unit, solution=SOLUTION)
        assert pre == pytest.approx(SOLUTION.value(entry, edit.unit.base_option, 0))
        spilled = predicted_spill_value(channel, edit.unit, edit, traces=traces, solution=SOLUTION)
        assert spilled != pre, "the fixture's own unit must be one the edit reaches"


def test_gate_a_the_measured_collateral_equals_the_aggregate_prediction(traces):
    r"""Gate A: $\texttt{BehavioralCollateral}^{meas}_{C,A} \approx B^{ref}_{C,A}$, within G5's
    tolerance -- equality with a prediction, not merely non-vanishing.

    The prediction is formed first and the measurement second; the fixture is not re-derived between
    them, and the post state carries exactly the one substrate edit the fixture named.
    """
    from rfl_rebuild.b2.unaffected import build_unaffected

    for channel in ("D_Q", "X", "P"):
        for name in REFINEMENTS:
            predicted = aggregate_reference(channel, traces, name, solution=SOLUTION)
            units = build_unaffected(cal_site(channel), traces, name)
            measured = measured_scene_collateral(units, LearnerPersistentState(), predicted["edit"],
                                                 q_reference=REFERENCE)
            assert measured["value"] == pytest.approx(predicted["B_ref"], rel=1e-6, abs=1e-12), (
                channel, name, measured["value"], predicted["B_ref"])
            assert predicted["B_ref"] != 0.0, "a zero prediction would be CALIBRATION_FAIL"
            diff = measured["override_diff"]
            assert sum(len(v) for v in diff.values()) == 1, "exactly one store changed"
            store, mapping = next(iter(diff.items()))
            assert list(mapping) == [predicted["edit"].substrate_edit.address]
            assert list(mapping.values()) == [predicted["edit"].substrate_edit.value]
            # no post-hoc map editing: the reported number *is* the mean of the measured maps
            raw = sum(measured["values_pre"][u] - measured["values_post"][u]
                      for u in units.units) / units.size
            assert measured["value"] == pytest.approx(raw, rel=1e-12, abs=1e-15)


def test_gate_a_independence_the_prediction_cannot_reach_the_measurement(traces, monkeypatch):
    r"""The `expected := measured` mutation, in the only form that can catch it.

    Setting $B^{ref}$ from the measured collateral would make `measured = expected` true by construction,
    so the defence is structural: the prediction takes no learner, no measured map and no post state, and
    it does not move when the measurement path is broken under it.
    """
    import inspect
    predicted = aggregate_reference("P", traces, "eligible_all", solution=SOLUTION)["B_ref"]
    for function in (aggregate_reference, predicted_spill_value, predicted_pre_value):
        parameters = inspect.signature(function).parameters
        for forbidden in ("learner", "values_pre", "values_post", "measured", "collateral", "post"):
            assert forbidden not in parameters, f"{function.__name__} must not take {forbidden}"
    from rfl_rebuild.b2 import collateral as collateral_module

    def _broken(*args, **kwargs):
        raise AssertionError("the measurement path is broken")

    monkeypatch.setattr(collateral_module, "measure_scene_map", _broken)
    monkeypatch.setattr(collateral_module, "behavioral_collateral_scenes", _broken)
    again = aggregate_reference("P", traces, "eligible_all", solution=SOLUTION)["B_ref"]
    assert again == predicted


def test_gate_a_a_mid_episode_edit_is_predicted_with_its_own_step_reward(traces):
    r"""Regression for the defect this gate caught.

    The first revision of `predicted_spill_value` added the successor's value but not the edited step's
    **own** reward, so it under-predicted every mid-episode edit by exactly that reward -- and reported a
    value-neutral $\mathcal C_{D_Q}$ site that the measurement disagreed with. The decomposition is
    re-derived here independently, from the frozen transition:

    $$V^{ref}_{\text{spill}}(u) = \text{prefix} + r(\text{edited step}) + V^{*}(\text{successor})$$
    """
    from rfl_rebuild.b2.calibration import _successor, _walk

    for channel in ("D_Q", "X"):
        result = aggregate_reference(channel, traces, "eligible_all", solution=SOLUTION)
        edit = result["edit"]
        scene = edit.unit
        walk = _walk(traces, scene)
        index = next(i for i, (state, control, step_result) in enumerate(walk)
                     if (channel == "D_Q" and (state, control.z, control.m, step_result.u) == (
                         edit.channel_address.state, edit.channel_address.z, edit.channel_address.m,
                         edit.channel_address.a))
                     or (channel == "X" and step_result.a_cmd == edit.channel_address.cmd
                         and state == edit.channel_address.state))
        state, control, _step = walk[index]
        prefix = sum(s.reward for s in traces.trace(scene).steps[:index])
        successor_state, successor_control, reward, terminal = _successor(
            state, control, edit.applied_action, scene)
        expected = prefix + reward + (0.0 if terminal else SOLUTION.value(
            successor_state, successor_control.z, successor_control.m))
        assert predicted_spill_value(channel, scene, edit, traces=traces,
                                     solution=SOLUTION) == pytest.approx(expected, rel=1e-12)
        assert predicted_spill_value(channel, scene, edit, traces=traces,
                                     solution=SOLUTION) != predicted_pre_value(
            channel, scene, solution=SOLUTION), "a mid-episode edit must move the value"


def _common_legal_alternative(state, cmd):
    r"""A target legal for **every** $(z, m)$ that can arrive at the site -- A88 §76.2's rule.

    Taking the alternative of one $(z,m)$ is the mistake that fixture defect was about: the mapped
    command then leaves the option's admissible set wherever another option reaches the same site, and
    the kernel raises `LearnerContractViolation` by design.
    """
    common = None
    for z in option_ids():
        for m in (0, 1):
            allowed = set(option_actions(z, ControlState(z=z, m=m), state))
            common = allowed if common is None else (common & allowed)
    alternatives = sorted((common or set()) - {cmd})
    return alternatives[0] if alternatives else None


def _a_remappable_site(walk, *, skip_address=None):
    for state, control, step_result in walk:
        target = _common_legal_alternative(state, step_result.u)
        if target is None:
            continue
        site = ControllerSite(state=state, cmd=step_result.u)
        if skip_address is not None and site == skip_address:
            continue
        return site, target
    return None, None


def test_the_trace_source_is_the_pairs_own_w_pre(traces):
    r"""$$W_{\text{pre}} \to \text{traces} \to E(c)$$

    A pre-update learner may carry persistent defects of its own. If the trace source were a minted
    healthy state, those defects would change nothing -- which is precisely the failure this gate
    exists to catch: a defective $W_{\text{pre}}$ must move what eligibility sees.
    """
    from rfl_rebuild.b2.unaffected import (
        CreditedSite,
        eligibility,
        pre_update_traces,
        scene_domain,
    )
    from rfl_rebuild.env.kernel import ControlState, option_actions
    from rfl_rebuild.learner.store import CONTROLLER, Edit

    healthy = pre_update_traces(learner=LearnerPersistentState(), q_reference=REFERENCE)
    scene = min(scene_domain(), key=lambda s: s.key)
    site, target = _a_remappable_site(healthy.walk(scene))
    if site is None:
        scene = sorted(scene_domain(), key=lambda s: s.key)[1]
        site, target = _a_remappable_site(healthy.walk(scene))
    assert site is not None, "the gate needs a remappable site"
    defective = LearnerPersistentState()
    defective.apply_transaction([Edit(CONTROLLER, site, target)], q_reference=REFERENCE)
    bad = pre_update_traces(learner=defective, q_reference=REFERENCE)

    assert bad.rows(scene) != healthy.rows(scene), "the trace source must be the learner it was given"
    # The *edited step's own* site is the command-keyed lookup site the kernel builds, and a remap may
    # not rewrite the key it was looked up by: the same site is consulted under both learners, and the
    # divergence is downstream -- the controller's return value changes the trajectory, hence the later
    # commands and the later sites. A trace that keyed this site by u instead would report a different
    # site here, which is the defect this assertion exists to catch.
    edited_state, _edited_control, edited_step = next(
        (st, ct, sr) for (st, ct, sr) in healthy.walk(scene)
        if ControllerSite(state=st, cmd=sr.a_cmd) == site)
    edited_site = CreditedSite("X", ControllerSite(state=edited_state, cmd=edited_step.a_cmd))
    assert edited_site.address == site
    assert edited_site in healthy.consulted("X", scene)
    assert edited_site in bad.consulted("X", scene)
    assert set(bad.consulted("X", scene)) != set(healthy.consulted("X", scene))
    moved = [c for c in set(bad.consulted("X", scene)) ^ set(healthy.consulted("X", scene))
             if eligibility(c, bad) != eligibility(c, healthy)]
    assert moved, "a defective W_pre must be able to change E(c) on the channel it moved"
    assert bad.learner is defective and healthy.learner is not defective


def test_an_unrelated_pre_override_survives_the_measurement(traces):
    r"""The measured pair is $W_{\text{pre}} + \Delta W^{\text{spill}}$, not a fresh state plus an edit.

    An override the pre state already carries must still be there afterwards, and the measurement must
    read it: a fresh state with one override would satisfy an override *count* while losing exactly
    this. On an empty pre state the two readings coincide, which is why the calibration fixture alone
    could not tell them apart.
    """
    from rfl_rebuild.b2.collateral import measured_scene_collateral
    from rfl_rebuild.b2.unaffected import build_unaffected, scene_domain
    from rfl_rebuild.env.kernel import ControlState, option_actions
    from rfl_rebuild.learner.store import CONTROLLER, Edit

    healthy = pre_update_traces(learner=LearnerPersistentState(), q_reference=REFERENCE)
    fixture = aggregate_reference("P", traces, "eligible_all", solution=SOLUTION)["edit"]
    site, target = None, None
    for scene in sorted(scene_domain(), key=lambda s: s.key):
        site, target = _a_remappable_site(healthy.walk(scene))
        if site is not None:
            break
    assert site is not None
    carry = LearnerPersistentState()
    carry.apply_transaction([Edit(CONTROLLER, site, target)], q_reference=REFERENCE)
    assert carry.controller_overrides, "the gate needs a pre state that already carries an override"
    assert site != fixture.substrate_edit.address, "the carried override is unrelated to the fixture"

    units = build_unaffected(cal_site("P"), traces, "eligible_all")
    measured = measured_scene_collateral(units, carry, fixture, q_reference=REFERENCE)
    assert measured["override_diff"], "the measurement still changes exactly the fixture's store"
    healthy_map = measured_scene_collateral(units, LearnerPersistentState(), fixture,
                                            q_reference=REFERENCE)
    assert measured["values_pre"] != healthy_map["values_pre"], (
        "the measured side must read the pre state it was handed, not a healthy one")


def test_the_x_prediction_agrees_with_the_controllers_own_semantics(traces):
    r"""One step at the fixture's X site: stepping with the target *as the command* must agree with
    keeping the command and letting the controller remap it. The frozen `automaton_transition` does not
    read the command today, so the two coincide -- this gate is what notices if that ever changes.
    """
    from rfl_rebuild.env.kernel import step

    edit = spillover_edit("X", traces, "eligible_all", solution=SOLUTION)
    site = edit.site.address
    scene = edit.unit
    for state, control, step_result in traces.walk(scene):
        if ControllerSite(state=state, cmd=step_result.u) == site:
            break
    else:                                                    # pragma: no cover - the fixture guarantees it
        raise AssertionError("the fixture's site is not on its own unit's walk")
    as_command = step(state, control, edit.target, tape=scene.tape)
    via_controller = step(state, control, site.cmd, tape=scene.tape, controller={site: edit.target})
    assert (as_command.state, as_command.control, as_command.u, as_command.reward) == (
        via_controller.state, via_controller.control, via_controller.u, via_controller.reward)


def test_gate_a_and_b_and_e_are_registered_in_the_audited_chain():
    assert "rfl_rebuild/b2/calibration.py" in PRODUCTION_MODULES
    assert_modules_are_closed(audited_modules(ROOT / "src"))
