"""Seedless mechanism/routing checks; NO population choice or acquisition.

Explicit WAIT defects and a few transient cells are engineering constructions,
not a scientific family, initialization rule, sample, or future workload.
"""
from dataclasses import fields, replace
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factual_event_candidate as factual
import readiness as ready
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.training import ExogenousEpisode
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.observation import learner_rows, walk_transition
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import (CONTROLLER, DECISION, PROCESS, Q,
    DecisionAddress, Edit, LearnerPersistentState, QAddress)
from rfl_rebuild.method.contract import FactualEvidence, FactualStep
from rfl_rebuild.solve.dp import solve_reference


class FactualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = ready.load_parent()
        cls.reference = ready.read_json(ready.ROOT / ready.FOLDER / "b2_prepare/healthy_reference_candidate.json")
        cls.q = reference_view_from(solve_reference())
        cls.start = K.State(*K.START, 0, 0, 0)

    def call(self, state=None, scene=None, regime="T", **kwargs):
        return factual.prepare_factual_event(LearnerPersistentState() if state is None else state,
            scene=scene or EvaluationScene(0, 0, 0, 0, 0), regime=regime,
            q_reference=self.q, parent=self.parent, reference=self.reference, **kwargs)

    def waiting(self, store=DECISION, *, process=False):
        # Option1 permits WAIT at START. Explicit construction, NOT an SCI rule.
        state = LearnerPersistentState()
        edits = [Edit(PROCESS, 0, 1)] if process else []
        for t in range(K.HORIZON):
            s = K.State(*K.START, t, 0, 0)
            addr = DecisionAddress(s, 1, 0)
            if store == Q:
                edits.append(Edit(Q, QAddress(s, 1, 0, K.WAIT), max(self.q.row(s, 1, 0).values()) + 1.))
            else:
                edits.append(Edit(DECISION, addr, K.WAIT))
        state.apply_transaction(edits, q_reference=self.q)
        return state

    def p_wait(self, **kwargs):
        return self.call(self.waiting(), EvaluationScene(0, 0, 0, 0, 1), "P", **kwargs)

    def reject_before_rollout(self, **kwargs):
        with patch.object(K, "rollout", side_effect=AssertionError("rejected before native rollout")):
            with self.assertRaises(ready.ProtocolError):
                self.call(**kwargs)

    def test_success_does_not_build_any_diagnostic_observation_or_truth(self):
        with patch.object(factual, "learner_rows", side_effect=AssertionError("success observation")), \
             patch.object(factual, "make_evidence", side_effect=AssertionError("success evidence")), \
             patch.object(factual, "_transient_truth", side_effect=AssertionError("success truth")):
            got = self.call()
        self.assertEqual(got["evaluator_audit"]["factual_outcome"], K.Outcome.SUCCESS)
        self.assertEqual(got["evaluator_audit"]["route"], "SUCCESS_NO_REFLECTION")
        self.assertIsNone(got["method_evidence"])
        self.assertIsNone(got["evaluator_audit"]["truth"])

    def test_p_success_even_with_commit_override_never_builds_evidence(self):
        pre = LearnerPersistentState(); pre.apply_transaction([Edit(PROCESS, 0, 1)])
        with patch.object(factual, "make_evidence", side_effect=AssertionError("success evidence")), \
             patch.object(factual, "_persistent_truth", side_effect=AssertionError("success truth")):
            got = self.call(pre, regime="P")
        self.assertEqual(got["evaluator_audit"]["factual_outcome"], K.Outcome.SUCCESS)
        self.assertIsNone(got["method_evidence"])

    def test_success_with_dormant_fault_is_not_reclassified_as_failure(self):
        got = self.call(mask=K.FaultMask(decision=K.DecisionOverride(11, K.WAIT)))
        self.assertEqual(got["evaluator_audit"]["route"], "SUCCESS_NO_REFLECTION")
        self.assertFalse(got["evaluator_audit"]["learner_evidence_constructed"])

    def test_T_success_after_actually_fired_controller_fault_still_builds_no_input(self):
        with patch.object(factual, "learner_rows", side_effect=AssertionError("success observation")), \
             patch.object(factual, "make_evidence", side_effect=AssertionError("success evidence")), \
             patch.object(factual, "_transient_truth", side_effect=AssertionError("success truth")):
            got = self.call(mask=K.FaultMask(controller=K.ControllerFault(self.start, K.RIGHT, K.WAIT)))
        a = got["evaluator_audit"]
        self.assertEqual(a["factual_outcome"], K.Outcome.SUCCESS)
        self.assertNotEqual(a["raw_trace"][0]["u"], a["raw_trace"][0]["a_cmd"])
        self.assertIsNone(got["method_evidence"])

    def test_terminal_observed_failure_before_original_evidence_build(self):
        mask = K.FaultMask(trap=K.Trap((1, 2), 0))
        with patch.object(K, "rollout", wraps=K.rollout) as roll, \
             patch.object(factual, "make_evidence", wraps=factual.make_evidence) as make:
            got = self.call(mask=mask)
        self.assertEqual(roll.call_count, 1); self.assertEqual(make.call_count, 1)
        self.assertEqual(got["evaluator_audit"]["factual_outcome"], K.Outcome.TRAP)
        self.assertIs(type(got["method_evidence"]), FactualEvidence)
        self.assertEqual(got["evaluator_audit"]["truth"]["Gamma_T_star"], ["Unknown/NoWrite"])

    def test_no_supplied_outcome_truth_provider_do_or_seed_interface(self):
        names = inspect.signature(factual.prepare_factual_event).parameters
        for key in ("factual_outcome", "trace", "fire", "Gamma", "seed", "population",
            "interventions", "command_provider", "environment_factory", "method", "train_curve"):
            self.assertNotIn(key, names)
            with self.assertRaises(TypeError): self.call(**{key: object()})

    def test_t_nonhealthy_baseline_rejected(self):
        self.reject_before_rollout(state=self.waiting())

    def test_p_healthy_substitute_rejected(self):
        self.reject_before_rollout(regime="P")

    def test_p_each_transient_channel_and_option_fault_rejected(self):
        for kwargs in ({"mask": K.FaultMask(decision=K.DecisionOverride(0, K.RIGHT))},
            {"mask": K.FaultMask(controller=K.ControllerFault(self.start, K.RIGHT, K.WAIT))},
            {"mask": K.FaultMask(plant=K.PlantFault(0, K.WAIT))},
            {"mask": K.FaultMask(trap=K.Trap((1, 2), 0))}, {"option_fault": 0}):
            self.reject_before_rollout(state=self.waiting(), regime="P", **kwargs)

    def test_unknown_and_pooled_regime_rejected(self):
        for regime in ("I", "TP", "T/P", "P ", True, None): self.reject_before_rollout(regime=regime)

    def test_p_all_manifested_decisions_retained_and_no_T_truth(self):
        got = self.p_wait(); a = got["evaluator_audit"]; truth = a["truth"]
        self.assertEqual(a["factual_outcome"], K.Outcome.TIMEOUT)
        self.assertGreater(len(truth["manifested_decision_timesteps"]), 1)
        self.assertEqual(truth["Gamma_P_star"], [f"Decision_{t}" for t in truth["manifested_decision_timesteps"]])
        self.assertEqual(truth["J_L"], [False, True, False])
        self.assertIsNone(truth["R_mech"]); self.assertIsNone(truth["Gamma_T_star"])

    def test_p_patch_and_Q_same_extensional_defect_have_same_manifestation(self):
        p = self.p_wait()
        q = self.call(self.waiting(Q), EvaluationScene(0, 0, 0, 0, 1), "P")
        self.assertEqual(p["evaluator_audit"]["raw_trace"], q["evaluator_audit"]["raw_trace"])
        self.assertEqual(p["evaluator_audit"]["truth"], q["evaluator_audit"]["truth"])
        self.assertNotEqual(p["evaluator_audit"]["fingerprint_pre"], q["evaluator_audit"]["fingerprint_pre"])

    def test_p_commit_and_multiple_decisions_can_co_manifest(self):
        got = self.call(self.waiting(process=True), regime="P")
        truth = got["evaluator_audit"]["truth"]
        self.assertEqual(truth["J_L"], [True, True, False])
        self.assertEqual(truth["manifested_process_proposals"], [0])
        self.assertEqual(truth["Gamma_P_star"][0], "ProcessCommit")

    def test_p_all_controller_manifestations_keep_full_wire_addresses(self):
        pre = LearnerPersistentState(); edits = []
        for t in range(K.HORIZON):
            s = K.State(*K.START, t, 0, 0)
            for cmd in K.option_actions(1, K.ControlState(1, 0), s):
                if cmd != K.WAIT: edits.append(Edit(CONTROLLER, K.ControllerSite(s, cmd), K.WAIT))
        pre.apply_transaction(edits)
        got = self.call(pre, EvaluationScene(0, 0, 0, 0, 1), "P")
        truth = got["evaluator_audit"]["truth"]
        self.assertEqual(got["evaluator_audit"]["factual_outcome"], K.Outcome.TIMEOUT)
        self.assertGreater(len(truth["manifested_controller_sites"]), 1)
        self.assertEqual(truth["J_L"], [False, False, True])
        for unit, row in zip(truth["Gamma_P_star"], truth["manifested_controller_sites"]):
            self.assertEqual(unit, f"ControllerSite_{row[0]}_{row[1]}_{row[2]}_{row[5]}")

    def test_p_unvisited_deviation_plus_clean_failure_is_not_manifestation(self):
        pre = LearnerPersistentState(); pre.apply_transaction([Edit(PROCESS, 1, 2)])
        with patch.object(factual, "learner_rows", side_effect=AssertionError("no P manifestation")), \
             patch.object(factual, "make_evidence", side_effect=AssertionError("no P manifestation")):
            got = self.call(pre, EvaluationScene(0, 2, 0, 0, 0), "P")
        self.assertEqual(got["evaluator_audit"]["factual_outcome"], K.Outcome.COLLISION)
        self.assertEqual(got["evaluator_audit"]["truth"]["Gamma_P_star"], [])
        self.assertEqual(got["evaluator_audit"]["route"], "P_FAILURE_WITHOUT_MANIFESTATION_NO_REFLECTION")
        self.assertIsNone(got["method_evidence"])

    def test_whole_argmax_includes_non_tie_broken_optimal_actions(self):
        self.assertEqual(factual._optimal_actions({4: .5, 1: .5, 3: .4}), (1, 4))

    def test_original_precheck_membership_tolerance_not_new_tuned_threshold(self):
        self.assertEqual(factual.ARGMAX_MEMBERSHIP_TOLERANCE, 1e-12)
        self.assertEqual(factual._optimal_actions({0: 1., 1: 1. - 5e-13, 2: 1. - 2e-12}), (0, 1))

    def test_actual_tied_optimal_p_patch_has_no_decision_manifestation(self):
        # Seedless structural witness search, not scientific population/design.
        witness = None
        for k in (0, 1):
            for phi in K.PHASE_DOMAIN:
                for z in K.option_ids():
                    scene = EvaluationScene(k, phi, 0, 0, z)
                    tr = learned_rollout(LearnerPersistentState(), kappa=k, tape=scene.tape, base_option=z, q_reference=self.q)
                    for s, zz, m, cmd, _, _ in walk_transition(tr, k, phi, tr.option_in_force):
                        alt = [a for a in factual._optimal_actions(self.q.row(s, zz, m)) if a != cmd]
                        if alt: witness = (scene, DecisionAddress(s, zz, m), alt[0]); break
                    if witness: break
                if witness: break
            if witness: break
        self.assertIsNotNone(witness)
        scene, addr, alternative = witness
        pre = LearnerPersistentState(); pre.apply_transaction([Edit(DECISION, addr, alternative)])
        tr = learned_rollout(pre, kappa=scene.kappa, tape=scene.tape, base_option=scene.base_option, q_reference=self.q)
        # Evaluator predicate can be tested on a success, but production routes
        # that success BEFORE computing this truth or constructing any input.
        truth = factual._persistent_truth(tr, scene, self.q)
        self.assertFalse(truth["J_L"][1]); self.assertEqual(truth["Gamma_P_star"], [])

    def test_T_controller_and_trap_truth_uses_fault_descriptor_not_P_manifestation(self):
        got = self.call(mask=K.FaultMask(controller=K.ControllerFault(self.start, K.RIGHT, K.WAIT),
            trap=K.Trap((1, 2), 1)))
        truth = got["evaluator_audit"]["truth"]
        self.assertEqual(got["evaluator_audit"]["factual_outcome"], K.Outcome.TRAP)
        self.assertEqual(truth["Gamma_T_star"], ["ControllerSite_0_2_0_3", "Unknown/NoWrite"])
        self.assertIsNone(truth["J_L"]); self.assertIsNone(truth["Gamma_P_star"])

    def test_T_dormant_controller_does_not_mint_credit(self):
        site = K.State(3, 4, 11, 0, 0)
        got = self.call(mask=K.FaultMask(controller=K.ControllerFault(site, K.RIGHT, K.WAIT),
            trap=K.Trap((1, 2), 0)))
        self.assertEqual(got["evaluator_audit"]["truth"]["Gamma_T_star"], ["Unknown/NoWrite"])

    def test_T_identity_controller_descriptor_is_presence_not_fire(self):
        got = self.call(mask=K.FaultMask(controller=K.ControllerFault(self.start, K.RIGHT, K.RIGHT),
            trap=K.Trap((1, 2), 0)))
        self.assertEqual(got["evaluator_audit"]["truth"]["Gamma_T_star"], ["Unknown/NoWrite"])

    def test_T_external_plant_and_trap_are_distinct_nonagent_units(self):
        got = self.call(mask=K.FaultMask(plant=K.PlantFault(0, K.WAIT), trap=K.Trap((1, 2), 1)))
        self.assertEqual(got["evaluator_audit"]["factual_outcome"], K.Outcome.TRAP)
        self.assertEqual(got["evaluator_audit"]["truth"]["Gamma_T_star"], ["ExternalPlant", "Unknown/NoWrite"])

    def test_T_reached_decision_descriptor_keeps_t_even_without_value_loss(self):
        got = self.call(mask=K.FaultMask(decision=K.DecisionOverride(0, K.RIGHT), trap=K.Trap((1, 2), 0)))
        truth = got["evaluator_audit"]["truth"]
        self.assertEqual(truth["Gamma_T_star"], ["Decision_0", "Unknown/NoWrite"])
        self.assertEqual(truth["R_mech"][0]["pre_state"], [0, 2, 0, 0, 0])
        self.assertEqual(truth["R_mech"][0]["nominal_action"], K.RIGHT)

    def test_T_unreached_decision_does_not_mint_credit(self):
        got = self.call(mask=K.FaultMask(decision=K.DecisionOverride(11, K.WAIT), trap=K.Trap((1, 2), 0)))
        self.assertEqual(got["evaluator_audit"]["truth"]["Gamma_T_star"], ["Unknown/NoWrite"])

    def test_T_empty_fired_mechanisms_gives_unknown_not_strategy_or_empty(self):
        got = self.call(scene=EvaluationScene(0, 2, 0, 0, 0))
        self.assertEqual(got["evaluator_audit"]["truth"]["Gamma_T_star"], ["Unknown/NoWrite"])
        self.assertEqual(got["evaluator_audit"]["truth"]["R_mech"], [])

    def test_T_process_substitution_failing_clean_trajectory_keeps_commit_descriptor(self):
        got = self.call(scene=EvaluationScene(0, 2, 0, 0, 1), option_fault=0)
        self.assertEqual(got["evaluator_audit"]["factual_outcome"], K.Outcome.COLLISION)
        self.assertEqual(got["evaluator_audit"]["truth"]["Gamma_T_star"], ["ProcessCommit"])

    def test_T_fire_predicates_match_original_native_definition_independently(self):
        # Extra original rollouts here are seedless comparator checks, not
        # anything prepare_factual_event executes, caches or calls a SCI PASS.
        scene = EvaluationScene(0, 0, 0, 0, 0)
        masks = [K.FaultMask(trap=K.Trap((1, 2), 0)),
            K.FaultMask(decision=K.DecisionOverride(0, K.RIGHT), trap=K.Trap((1, 2), 0)),
            K.FaultMask(controller=K.ControllerFault(self.start, K.RIGHT, K.WAIT), trap=K.Trap((1, 2), 1)),
            K.FaultMask(plant=K.PlantFault(0, K.WAIT), trap=K.Trap((1, 2), 1))]
        for mask in masks:
            got = self.call(mask=mask)
            provider, controller = factual.learner_channels(LearnerPersistentState().snapshot(), self.q)
            fire = K.fired_mechanisms(kappa=scene.kappa, tape=scene.tape, base_option=scene.base_option,
                command_provider=provider, controller=controller, mask=mask)
            self.assertEqual(got["evaluator_audit"]["truth"]["Z_fire"],
                [bool(fire[k]) for k in ("Z_P", "Z_D", "Z_X", "Z_E", "Z_U")])

    def test_later_decision_repair_uses_actual_pre_state_not_START(self):
        scene = EvaluationScene(0, 0, 0, 0, 0)
        tr = learned_rollout(LearnerPersistentState(), kappa=0, tape=scene.tape, base_option=0, q_reference=self.q)
        s, z, m, cmd, _, _ = tuple(walk_transition(tr, 0, 0, 0))[1]
        # Keep actual command to expose descriptor/timing without selecting a
        # failure-benefit design. A later actual trap supplies the failure.
        got = self.call(mask=K.FaultMask(decision=K.DecisionOverride(s.t, cmd), trap=K.Trap((2, 2), 1)))
        repair = got["evaluator_audit"]["truth"]["R_mech"][0]
        self.assertEqual(repair["pre_state"], [s.x, s.y, s.t, s.kappa, s.phi])
        self.assertNotEqual(repair["pre_state"], [0, 2, 0, 0, 0])
        self.assertEqual((repair["z"], repair["m"]), (z, m))

    def test_actual_source_mutation_is_protocol_error_not_evidence_or_science_fail(self):
        pre = LearnerPersistentState()
        native = K.rollout
        def mutate(**kwargs):
            tr = native(**kwargs)
            pre.apply_transaction([Edit(PROCESS, 1, 2)])
            return tr
        with patch.object(K, "rollout", side_effect=mutate), \
             patch.object(factual, "make_evidence", side_effect=AssertionError("source mutation")):
            with self.assertRaises(ready.ProtocolError): self.call(pre)

    def test_true_native_option_contract_error_is_not_caught_or_zero_filled(self):
        # UP is not admissible at START; retain native rejection, not a failure.
        with self.assertRaises(K.MalformedIntervention):
            self.call(mask=K.FaultMask(decision=K.DecisionOverride(0, K.UP)))

    def test_method_packet_exact_closed_learner_fields_and_original_rounding(self):
        got = self.p_wait(); evidence = got["method_evidence"]
        self.assertEqual({x.name for x in fields(evidence)}, {"steps", "z_in_force", "kappa", "phi"})
        forbidden = {"outcome", "regime", "J_L", "Gamma_P_star", "R_mech", "u", "z_proposal", "cause_rank"}
        self.assertFalse({x.name for x in fields(evidence)} & forbidden)
        for step in evidence.steps:
            self.assertIs(type(step), FactualStep)
            self.assertFalse({x.name for x in fields(step)} & forbidden)
        original = learned_rollout(self.waiting(), kappa=0, tape=EvaluationScene(0, 0, 0, 0, 1).tape,
            base_option=1, q_reference=self.q)
        expected = factual.make_evidence(learner_rows(original, 0, 0), original.option_in_force, 0, 0)
        self.assertEqual(evidence, expected)

    def test_p_one_snapshot_actual_channels_no_update_future_or_seed(self):
        pre = self.waiting(); before = fingerprint(pre)
        with patch.object(K, "rollout", wraps=K.rollout) as roll, \
             patch.object(factual, "learner_channels", wraps=factual.learner_channels) as channels, \
             patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("no key")), \
             patch("rfl_rebuild.b2.runner.train_curve", side_effect=AssertionError("no future")), \
             patch.object(LearnerPersistentState, "apply_transaction", side_effect=AssertionError("no write")):
            got = self.call(pre, EvaluationScene(0, 0, 0, 0, 1), "P")
        self.assertEqual(roll.call_count, channels.call_count); self.assertEqual(roll.call_count, 1)
        self.assertIs(channels.call_args.args[1], self.q)
        self.assertEqual(fingerprint(pre), before)
        a = got["evaluator_audit"]
        for key in ("environment_seed_draws", "future_training_episodes", "diagnostic_method_calls", "credit_or_B1_write_calls"):
            self.assertEqual(a[key], 0)

    def test_truth_changes_do_not_enter_same_learner_evidence(self):
        # Visible trace same, T descriptor attribution different (A71).
        p0 = self.call(mask=K.FaultMask(trap=K.Trap((1, 2), 0)))
        p1 = self.call(mask=K.FaultMask(decision=K.DecisionOverride(0, K.RIGHT), trap=K.Trap((1, 2), 0)))
        self.assertEqual(p0["method_evidence"], p1["method_evidence"])
        self.assertNotEqual(p0["evaluator_audit"]["truth"], p1["evaluator_audit"]["truth"])

    def test_same_audit_portable_hash_and_false_authority(self):
        a = self.p_wait(); b = self.p_wait()
        self.assertEqual(a["audit_sha256"], b["audit_sha256"])
        self.assertEqual(a["audit_sha256"], factual.bridge.sha(a["evaluator_audit"]))
        for key in ("science_acquisition_origin_authenticated", "fault_grammar_population_membership_authenticated",
            "population_seed_registry_and_collection_gate_authenticated", "collection_authorized",
            "scientific_claim_authorized", "research_complete"):
            self.assertIs(a["evaluator_audit"][key], False)
        print("SEEDLESS_FACTUAL_ROUTING_SUMMARY " + json.dumps({
            "role": a["evaluator_audit"]["role"], "outcome": a["evaluator_audit"]["factual_outcome"],
            "manifested_decision_count": len(a["evaluator_audit"]["truth"]["manifested_decision_timesteps"]),
            "audit_sha256": a["audit_sha256"], "collection_authorized": False,
            "environment_seed_draws": 0, "future_training_episodes": 0}, sort_keys=True))

    def test_dormant_fault_setup_changes_audit_not_evidence_or_route(self):
        a = self.call(); b = self.call(mask=K.FaultMask(decision=K.DecisionOverride(11, K.WAIT)))
        self.assertEqual(a["evaluator_audit"]["raw_trace"], b["evaluator_audit"]["raw_trace"])
        self.assertNotEqual(a["audit_sha256"], b["audit_sha256"])
        self.assertIsNone(b["method_evidence"])

    def test_bad_nominal_types_scene_and_reference_rejected_before_rollout(self):
        self.reject_before_rollout(state=object())
        self.reject_before_rollout(scene=SimpleNamespace(key=(0, 0, 0, 0, 0)))
        with patch.object(K, "rollout", side_effect=AssertionError("reject Q")):
            with self.assertRaises(ready.ProtocolError):
                factual.prepare_factual_event(LearnerPersistentState(), scene=EvaluationScene(0, 0, 0, 0, 0),
                    regime="T", q_reference=object(), parent=self.parent, reference=self.reference)

    def test_changed_reference_digest_rejected_before_rollout(self):
        wrong = dict(self.reference); wrong["q_reference_sha256"] = "b" * 64
        with patch.object(K, "rollout", side_effect=AssertionError("reject binding")):
            with self.assertRaises(ready.ProtocolError):
                factual.prepare_factual_event(LearnerPersistentState(), scene=EvaluationScene(0, 0, 0, 0, 0),
                    regime="T", q_reference=self.q, parent=self.parent, reference=wrong)

    def test_fault_integer_aliases_and_wrong_descriptor_types_rejected(self):
        masks = [object(), K.FaultMask(decision=K.DecisionOverride(True, K.RIGHT)),
            K.FaultMask(decision=K.DecisionOverride(0, 3.)), K.FaultMask(plant=K.PlantFault(0., K.WAIT)),
            K.FaultMask(controller=K.ControllerFault(replace(self.start, x=0.), K.RIGHT, K.WAIT)),
            K.FaultMask(controller=K.ControllerFault(self.start, K.RIGHT, True)),
            K.FaultMask(trap=K.Trap((True, 2), 0)), K.FaultMask(decision=SimpleNamespace(t=0, action=3))]
        for mask in masks: self.reject_before_rollout(mask=mask)
        for opt in (True, 1., 99): self.reject_before_rollout(option_fault=opt)

    def test_protocol_or_incomplete_rollout_not_scientific_negative_result(self):
        for error in (K.LearnerContractViolation("bad baseline"), K.OptionViolation("bad fault")):
            with patch.object(K, "rollout", side_effect=error):
                with self.assertRaises(type(error)): self.call()

    def test_nonterminal_inconsistent_trace_refused_before_evidence(self):
        tr = learned_rollout(LearnerPersistentState(), kappa=0, tape=EvaluationScene(0, 0, 0, 0, 0).tape,
            base_option=0, q_reference=self.q)
        for malformed in (replace(tr, outcome=None), replace(tr, steps=()),
            replace(tr, outcome=K.Outcome.TIMEOUT)):
            with patch.object(K, "rollout", return_value=malformed), \
                 patch.object(factual, "make_evidence", side_effect=AssertionError("reject incomplete")):
                with self.assertRaises(ready.ProtocolError): self.call()


if __name__ == "__main__":
    unittest.main()
