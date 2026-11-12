"""Owned, seedless factual rollout and failure-first routing; NOT collection.

There is no supplied outcome/trace/provider/truth, no sampler, diagnostic call,
credit selection, B1 write or future. T owns a healthy baseline with transient
fault descriptors; P owns the actual persistent baseline with no fault or do.
Only an observed failure (and for P a manifestation) constructs the original
learner-visible FactualEvidence. Evaluator material is a separate object, never
an input to a method in this module. A future full collection/flow gate is owed.
"""
from __future__ import annotations

import readiness as ready
import native_record_candidate as bridge
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b2.environment import learner_channels
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.domain import is_strict_decision_state
from rfl_rebuild.env.observation import learner_rows, walk_transition
from rfl_rebuild.learner.reference import QReferenceView
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.method.runner import make_evidence
from rfl_rebuild.method.public_scm import PublicSCMView

ROLE = "SEEDLESS_OWNED_FACTUAL_ROUTING_NOT_AUTHENTICATED_COLLECTION"
# Existing A75 precheck convention, not a new tuning/search tolerance. The whole
# optimal action set, not a tie-broken best action, defines P's manifestation.
ARGMAX_MEMBERSHIP_TOLERANCE = 1e-12
FAILURES = (K.Outcome.COLLISION, K.Outcome.TRAP, K.Outcome.TIMEOUT)


def _int_id(value, support, label):
    ready.require(type(value) is int and value in support, f"{label}: true integer in frozen support required")


def _strict_mask(mask, option_fault):
    ready.require(type(mask) is K.FaultMask, "exact native fault mask required")
    if option_fault is not None:
        _int_id(option_fault, K.option_ids(), "transient option")
    for obj, expected in ((mask.decision, K.DecisionOverride),
        (mask.controller, K.ControllerFault), (mask.plant, K.PlantFault), (mask.trap, K.Trap)):
        ready.require(obj is None or type(obj) is expected, "nominal fault descriptor required")
    if mask.decision is not None:
        _int_id(mask.decision.t, range(K.HORIZON), "decision action-step")
        _int_id(mask.decision.action, range(len(K.ACTIONS)), "transient decision action")
    if mask.controller is not None:
        f = mask.controller
        ready.require(is_strict_decision_state(f.state) and f.state.cell in K.OPEN_CELLS
            and f.state.cell != K.GOAL, "controller fault needs a strict decision state")
        _int_id(f.state.t, range(K.HORIZON), "controller action-step")
        _int_id(f.state.kappa, K.CONTEXT_PERIODS, "controller context")
        _int_id(f.state.phi, K.PHASE_DOMAIN, "controller phase")
        _int_id(f.cmd, range(len(K.ACTIONS)), "controller command")
        _int_id(f.realized, range(len(K.ACTIONS)), "controller low-level output")
    if mask.plant is not None:
        _int_id(mask.plant.t, range(K.HORIZON), "plant action-step")
        _int_id(mask.plant.realized, range(len(K.ACTIONS)), "plant realization")
    if mask.trap is not None:
        f = mask.trap
        ready.require(type(f.cell) is tuple and len(f.cell) == 2 and
            all(type(x) is int for x in f.cell), "trap cell requires exact integer pair")
        _int_id(f.t, range(K.HORIZON), "trap action-step")
        f.__post_init__()


def _state(s):
    return [s.x, s.y, s.t, s.kappa, s.phi]


def _mask_payload(mask, option_fault):
    return {"option_fault": option_fault,
        "decision": [mask.decision.t, mask.decision.action] if mask.decision else None,
        "controller": (_state(mask.controller.state) + [mask.controller.cmd, mask.controller.realized])
            if mask.controller else None,
        "plant": [mask.plant.t, mask.plant.realized] if mask.plant else None,
        "trap": [list(mask.trap.cell), mask.trap.t] if mask.trap else None}


def _trace_payload(trace, scene):
    return [{"pre_state": _state(s), "z": z, "m": m, "a_cmd": a,
        "u": step.u, "a_realized": realized, "reward_hex": reward.hex(),
        "post_state": _state(step.state), "post_control": [step.control.z, step.control.m],
        "terminal": step.terminal, "outcome": step.outcome, "illegal": step.illegal}
        for (s, z, m, a, realized, reward), step in zip(
            walk_transition(trace, scene.kappa, scene.phase, trace.option_in_force), trace.steps)]


def _optimal_actions(qrow):
    best = max(qrow.values())
    return tuple(sorted(x for x, value in qrow.items()
        if value >= best - ARGMAX_MEMBERSHIP_TOLERANCE))


def _persistent_truth(trace, scene, q_reference):
    """P only: no priority layer shadows a^L, u^L or z^L_commit.

    In this owned no-mask/no-do path, final channels ARE learner baselines by
    the native kernel branches. Do not use this inference on a transient trace.
    Preserve every manifested address, not only the first/canonical witness.
    """
    ready.require(trace.mask == K.FaultMask() and not trace.interventions.members,
                  "P baseline provenance requires no transient faults or evaluator do")
    process = trace.option_in_force != scene.base_option
    decisions, controllers, rows = [], [], []
    for (s, z, m, a, _, _), step in zip(
        walk_transition(trace, scene.kappa, scene.phase, trace.option_in_force), trace.steps):
        qrow = q_reference.row(s, z, m)
        optimal = _optimal_actions(qrow)
        if a not in optimal:
            decisions.append(s.t)
        if step.u != a:
            controllers.append(K.ControllerSite(s, a))
        rows.append({"pre_state": _state(s), "z": z, "m": m,
            "a_learner": a, "u_learner": step.u, "optimal_actions": list(optimal)})
    gamma = (["ProcessCommit"] if process else []) + [f"Decision_{t}" for t in decisions]
    gamma += [PublicSCMView.credit_unit(K.ControllerFault(x.state, x.cmd, x.cmd)) for x in controllers]
    return {"truth_source": "A75_LEARNER_BASELINE_MANIFESTATIONS_NOT_R_MECH",
        "J_L": [process, bool(decisions), bool(controllers)],
        "manifested_process_proposals": [scene.base_option] if process else [],
        "manifested_decision_timesteps": decisions,
        "manifested_controller_sites": [_state(x.state) + [x.cmd] for x in controllers],
        "Gamma_P_star": gamma, "Gamma_T_star": None, "R_mech": None,
        "whole_optimal_set_tolerance": ARGMAX_MEMBERSHIP_TOLERANCE,
        "source_separated_baseline_rows": rows}


def _transient_truth(trace, scene, mask, q_reference):
    """T structural descriptors from this SAME owned trace, not rescue or J.

    A66/A67 firing predicates stay intact. Descriptor addresses are essential:
    a fire bit alone cannot locate Decision_t or ControllerSite_x_y_t_cmd.
    No second rollout, nuisance resampling or hypothetical rescue is used.
    """
    descriptors, repairs = [], []
    if trace.option_in_force != scene.base_option:
        descriptors.append("ProcessCommit")
        repairs.append({"kind": "do_process_commit_identity"})
    transitions = tuple(walk_transition(trace, scene.kappa, scene.phase, trace.option_in_force))
    if mask.decision is not None and len(trace.steps) > mask.decision.t:
        s, z, m, _, _, _ = transitions[mask.decision.t]
        row = q_reference.row(s, z, m)
        # Exact original Q-policy tie break for the mechanism repair target;
        # P's whole-argmax manifestation test is deliberately a different rule.
        nominal = max(row, key=lambda a: (row[a], -a))
        descriptors.append(mask.decision)
        repairs.append({"kind": "do_decision_nominal", "t": s.t,
            "pre_state": _state(s), "z": z, "m": m, "nominal_action": nominal})
    x_fires = [(s, step) for (s, _, _, _, _, _), step in zip(transitions, trace.steps)
        if step.u != step.a_cmd]
    if x_fires:
        ready.require(mask.controller is not None and len(x_fires) == 1,
                      "healthy T mis-execution needs its single controller descriptor")
        s, step = x_fires[0]
        ready.require(K.ControllerSite(s, step.a_cmd) == K.ControllerSite(mask.controller.state, mask.controller.cmd)
            and step.u == mask.controller.realized, "actual T controller firing differs from descriptor address/output")
        descriptors.append(mask.controller)
        repairs.append({"kind": "do_controller_identity",
            "site": _state(mask.controller.state) + [mask.controller.cmd],
            "nominal_u": mask.controller.cmd})
    e_fires = [(s, step) for (s, _, _, _, _, _), step in zip(transitions, trace.steps)
        if step.a_realized != step.u]
    if e_fires:
        ready.require(mask.plant is not None, "T plant firing lacks its descriptor")
        ready.require(len(e_fires) == 1 and e_fires[0][0].t == mask.plant.t and
            e_fires[0][1].a_realized == mask.plant.realized, "actual T plant firing differs from descriptor")
        descriptors.append(mask.plant)
        repairs.append({"kind": "rho_E", "t": mask.plant.t})
    if trace.outcome == K.Outcome.TRAP:
        ready.require(mask.trap is not None, "T trap firing lacks its descriptor")
        descriptors.append(mask.trap)
        repairs.append({"kind": "rho_U", "cell": list(mask.trap.cell), "t": mask.trap.t})
    gamma = list(dict.fromkeys(PublicSCMView.credit_unit(x) for x in descriptors))
    if not gamma:
        gamma = ["Unknown/NoWrite"]
    return {"truth_source": "A66_A67_A71_SAME_TRACE_STRUCTURAL_R_MECH_DESCRIPTORS_NOT_J_OR_RESCUE",
        "R_mech": repairs, "Gamma_T_star": gamma, "Gamma_P_star": None, "J_L": None,
        "Z_fire": [trace.option_in_force != scene.base_option,
            mask.decision is not None and len(trace.steps) > mask.decision.t,
            bool(x_fires), bool(e_fires), trace.outcome == K.Outcome.TRAP]}


def prepare_factual_event(pre_state, *, scene, regime, q_reference, parent, reference,
                          mask=None, option_fault=None):
    """Actual deterministic engineering event, separate learner/evaluator outputs.

    Inputs do NOT include outcome, trace, firing bits, arbitrary providers,
    intervention/do, method, seed or a population. This function only reads one
    snapshot and one original rollout; it allocates no science key and writes no
    learner state. This is NOT a native scientific receipt or a collection gate.
    """
    ready.validate_design(parent["lock"])
    ready.validate_reference(reference, parent)
    ready.require(type(pre_state) is LearnerPersistentState and type(scene) is EvaluationScene
        and type(q_reference) is QReferenceView, "exact native learner/scene/reference required")
    scene.__post_init__()
    ready.require(q_reference.digest() == reference["q_reference_sha256"], "factual Q reference binding differs")
    ready.require(type(regime) is str and regime in ("T", "P"), "only source-separated T/P routing supported")
    mask = K.FaultMask() if mask is None else mask
    _strict_mask(mask, option_fault)
    before = fingerprint(pre_state)
    snapshot = pre_state.snapshot()
    if regime == "T":
        ready.require(snapshot.healthy, "T requires the genuinely healthy persistent baseline")
    else:
        ready.require(not snapshot.healthy, "P requires an actual persistent deviation, not a fresh healthy substitute")
        ready.require(mask == K.FaultMask() and option_fault is None,
            "persistent plus transient is I/composition, not P")
    provider, controller = learner_channels(snapshot, q_reference)
    try:
        trace = K.rollout(kappa=scene.kappa, tape=scene.tape, base_option=scene.base_option,
            command_provider=provider, controller=controller,
            learner_process_commit=snapshot.process_commit_provider(), mask=mask,
            option_fault=option_fault)
    finally:
        ready.require(fingerprint(pre_state) == before, "factual rollout changed the source learner")
    ready.require(type(trace) is K.RolloutTrace and trace.steps and
        trace.steps[-1].terminal is True and trace.steps[-1].outcome == trace.outcome and
        type(trace.outcome) is str and trace.outcome in (K.Outcome.SUCCESS,) + FAILURES and
        trace.base_option == scene.base_option and trace.mask == mask and not trace.interventions.members and
        trace.option_in_force == (option_fault if option_fault is not None
            else snapshot.process_overrides.get(scene.base_option, scene.base_option)),
        "original factual rollout must supply a consistent native terminal outcome")
    audit = {"schema": "a96-b2-owned-factual-event-v1", "role": ROLE, "regime": regime,
        "scene": list(scene.key), "factual_outcome": trace.outcome,
        "parent_sources_digest": parent["sources_digest"], "lock_sha256": parent["lock_sha256"],
        "healthy_reference_canonical_payload_sha256": bridge.sha(reference),
        "q_reference_sha256": q_reference.digest(), "fingerprint_pre": before,
        "fingerprint_post": fingerprint(pre_state), "z_proposal": scene.base_option,
        "z_in_force": trace.option_in_force, "raw_trace": _trace_payload(trace, scene),
        "transient_fault_setup_evaluator_only": _mask_payload(mask, option_fault),
        "truth": None, "learner_evidence_constructed": False,
        "native_rollout_count": 1, "environment_seed_draws": 0, "future_training_episodes": 0,
        "diagnostic_method_calls": 0, "credit_or_B1_write_calls": 0,
        "actual_rollout_owned_by_preparation": True, "science_acquisition_origin_authenticated": False,
        "fault_grammar_population_membership_authenticated": False,
        "population_seed_registry_and_collection_gate_authenticated": False,
        "collection_authorized": False, "scientific_claim_authorized": False, "research_complete": False}
    # Failure-first means before observation/evidence construction, not merely
    # that a later caller decides to throw an already-truth-capable input away.
    if trace.outcome == K.Outcome.SUCCESS:
        audit["route"] = "SUCCESS_NO_REFLECTION"
        return {"method_evidence": None, "evaluator_audit": audit, "audit_sha256": bridge.sha(audit)}
    truth = (_persistent_truth(trace, scene, q_reference) if regime == "P"
             else _transient_truth(trace, scene, mask, q_reference))
    audit["truth"] = truth
    if regime == "P" and not truth["Gamma_P_star"]:
        audit["route"] = "P_FAILURE_WITHOUT_MANIFESTATION_NO_REFLECTION"
        return {"method_evidence": None, "evaluator_audit": audit, "audit_sha256": bridge.sha(audit)}
    evidence = make_evidence(learner_rows(trace, scene.kappa, scene.phase),
        trace.option_in_force, scene.kappa, scene.phase)
    audit["learner_evidence_constructed"] = True
    audit["route"] = "FACTUAL_FAILURE_EVIDENCE_PREPARED_NOT_METHOD_RUN"
    return {"method_evidence": evidence, "evaluator_audit": audit, "audit_sha256": bridge.sha(audit)}
