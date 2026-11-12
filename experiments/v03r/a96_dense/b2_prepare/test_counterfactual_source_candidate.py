"""Owned L2 seedless engineering fixtures, NOT scientific collection/methods."""
from dataclasses import replace
import inspect
import json
from pathlib import Path
import sys
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import counterfactual_source_candidate as candidate
import credit_delivery_candidate as credit
import factual_event_candidate as factual
import native_record_candidate as bridge
import readiness as ready
from rfl_rebuild.b1.contract import EVALUABLE_NOOP, NO_VALID_ALTERNATIVE, fingerprint
from rfl_rebuild.b1.counterfactual import CfEpisode, CounterfactualUndefined
from rfl_rebuild.b1.factual import factual_return_to_go
from rfl_rebuild.b1.runner import run_dq_law
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.training import ExogenousEpisode
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import DECISION, PROCESS, Q, DecisionAddress, Edit, LearnerPersistentState, QAddress
from rfl_rebuild.method import credit as native
from rfl_rebuild.method.contract import FactualEvidence
from rfl_rebuild.method.runner import make_evidence
from rfl_rebuild.solve.dp import solve_reference

ERRORS = (ready.ProtocolError, native.ProtocolError)


class CounterfactualSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = ready.load_parent()
        cls.reference = ready.read_json(ready.ROOT / ready.FOLDER / "b2_prepare/healthy_reference_candidate.json")
        cls.sol = solve_reference()
        cls.q = reference_view_from(cls.sol)

    def waiting(self):
        # Explicit Q-only WAIT fixture, NOT C3/SCI initialization/population.
        state = LearnerPersistentState()
        edits = [Edit(Q, QAddress(K.State(*K.START, t, 0, 0), 1, 0, K.WAIT),
            max(self.q.row(K.State(*K.START, t, 0, 0), 1, 0).values()) + 1.) for t in range(K.HORIZON)]
        state.apply_transaction(edits, q_reference=self.q)
        return state

    def source(self, state=None, *, regime="P", scene=None, **kw):
        return candidate.prepare_owned_l2_source(self.waiting() if state is None else state,
            scene=scene or EvaluationScene(0, 0, 0, 0, 1), regime=regime,
            solution=self.sol, q_reference=self.q, parent=self.parent, reference=self.reference, **kw)

    def cell(self, source=None, *, units=("Decision_0",), kind="causal", law="CounterfactualReturnWrite"):
        source = self.source() if source is None else source
        prepared = credit.prepare_credit(candidate.method_evidence(source), kind=kind,
            proposal=credit.PROPOSALS[kind](frozenset(units)))
        arms = bridge.registered_pair("D_Q", Tier.L2_COUNTERFACTUAL, law)
        return candidate.prepare_l2_engineering_cell(source, prepared, arms)

    def reject_before_rollout(self, **kwargs):
        with patch.object(K, "rollout", side_effect=AssertionError("must reject before factual rollout")):
            with self.assertRaises(ready.ProtocolError):
                self.source(**kwargs)

    def test_signature_accepts_no_trace_episode_provider_intervention_target_or_method(self):
        self.assertEqual(tuple(inspect.signature(candidate.prepare_owned_l2_source).parameters),
            ("pre_state", "scene", "regime", "solution", "q_reference", "parent", "reference", "mask", "option_fault"))

    def test_nominal_handle_constructor_is_refused(self):
        with self.assertRaises(ready.ProtocolError):
            candidate.OwnedL2Source()

    def test_unissued_nominal_handle_is_not_origin(self):
        fake = object.__new__(candidate.OwnedL2Source)
        with self.assertRaises(ready.ProtocolError):
            candidate.method_evidence(fake)

    def test_dictionary_hash_and_duck_source_are_refused(self):
        for fake in ({"source_sha256": "0" * 64}, SimpleNamespace(evidence=None), None):
            with self.subTest(fake=type(fake).__name__), self.assertRaises(ready.ProtocolError):
                candidate.source_audit(fake)

    def test_factual_is_generated_once_by_configuration_not_supplied_trace(self):
        original = K.rollout
        with patch.object(K, "rollout", wraps=original) as rollout:
            src = self.source()
        self.assertEqual(rollout.call_count, 1)
        data = candidate._ISSUED[src]
        self.assertIs(rollout.call_args.kwargs["command_provider"], data.episode.decision_read_view_pre)
        self.assertIs(rollout.call_args.kwargs["controller"], data.episode.controller_mapping)
        self.assertIs(rollout.call_args.kwargs["learner_process_commit"], data.episode.process_commit_provider)
        self.assertEqual(rollout.call_args.kwargs["mask"], data.episode.mask)
        self.assertEqual(candidate.source_audit(src)["factual_outcome"], K.Outcome.TIMEOUT)

    def test_exact_closed_method_fields_and_no_source_truth_targets(self):
        src = self.source(); evidence = candidate.method_evidence(src)
        self.assertIs(type(evidence), FactualEvidence)
        self.assertEqual(set(evidence.__slots__), {"steps", "z_in_force", "kappa", "phi"})
        self.assertFalse(any(hasattr(evidence, x) for x in ("source", "episode", "sol", "truth", "u", "z_proposal")))

    def test_projection_is_original_observation_of_own_episode(self):
        src = self.source(); d = candidate._ISSUED[src]
        expected = make_evidence(learner_rows(d.episode.factual_trace, d.scene.kappa, d.scene.phase),
            d.episode.factual_trace.option_in_force, d.scene.kappa, d.scene.phase)
        self.assertEqual(candidate._row_payload(candidate.method_evidence(src)), candidate._row_payload(expected))

    def test_success_skips_evidence_truth_credit_and_targets(self):
        with patch.object(candidate, "make_evidence", side_effect=AssertionError("SUCCESS reflection")), \
             patch.object(candidate, "learner_rows", side_effect=AssertionError("SUCCESS evidence")), \
             patch.object(factual, "_transient_truth", side_effect=AssertionError("SUCCESS truth")), \
             patch.object(candidate, "build_counterfactual_envelope", side_effect=AssertionError("SUCCESS CF")):
            src = self.source(LearnerPersistentState(), regime="T", scene=EvaluationScene(0, 0, 0, 0, 0))
            self.assertIsNone(candidate.method_evidence(src))
        self.assertEqual(candidate.source_audit(src)["route"], "SUCCESS_NO_REFLECTION")

    def test_success_with_dormant_fault_does_not_authorize_cf(self):
        src = self.source(LearnerPersistentState(), regime="T", scene=EvaluationScene(0, 0, 0, 0, 0),
            mask=K.FaultMask(decision=K.DecisionOverride(11, K.WAIT)))
        self.assertIsNone(candidate.method_evidence(src))
        with patch.object(candidate, "build_counterfactual_envelope", side_effect=AssertionError("CF must not run")):
            with self.assertRaises(ready.ProtocolError):
                candidate.prepare_l2_engineering_cell(src, None,
                    bridge.registered_pair("D_Q", Tier.L2_COUNTERFACTUAL, "DualReturnWrite"))

    def test_d_patch_is_refused_before_q_only_episode(self):
        state = LearnerPersistentState()
        state.apply_transaction([Edit(DECISION, DecisionAddress(K.State(*K.START, 0, 0, 0), 1, 0), K.WAIT)])
        self.reject_before_rollout(state=state)

    def test_healthy_p_and_deviant_t_are_refused(self):
        self.reject_before_rollout(state=LearnerPersistentState())
        self.reject_before_rollout(regime="T")

    def test_p_transient_fault_and_option_fault_are_composition_not_p(self):
        self.reject_before_rollout(mask=K.FaultMask(decision=K.DecisionOverride(0, K.WAIT)))
        self.reject_before_rollout(option_fault=0)

    def test_i_or_unknown_regime_cannot_borrow_p_contract(self):
        for regime in ("I", "p", True, None):
            self.reject_before_rollout(regime=regime)

    def test_parent_reference_binding_is_checked_before_rollout(self):
        bad = dict(self.reference); bad["lock_sha256"] = "0" * 64
        with patch.object(K, "rollout", side_effect=AssertionError("no rollout")), self.assertRaises(ready.ProtocolError):
            candidate.prepare_owned_l2_source(self.waiting(), scene=EvaluationScene(0, 0, 0, 0, 1), regime="P",
                solution=self.sol, q_reference=self.q, parent=self.parent, reference=bad)

    def test_duck_solution_is_refused_before_reference_adapter(self):
        with patch.object(K, "rollout", side_effect=AssertionError("no rollout")), self.assertRaises(ready.ProtocolError):
            candidate.prepare_owned_l2_source(self.waiting(), scene=EvaluationScene(0, 0, 0, 0, 1), regime="P",
                solution=SimpleNamespace(q=self.sol.q), q_reference=self.q, parent=self.parent, reference=self.reference)

    def test_reference_content_not_name_or_object_identity_binds_source(self):
        src = candidate.prepare_owned_l2_source(self.waiting(), scene=EvaluationScene(0, 0, 0, 0, 1), regime="P",
            solution=self.sol, q_reference=reference_view_from(self.sol, name="another-label"),
            parent=self.parent, reference=self.reference)
        self.assertEqual(candidate.source_audit(src)["configuration"]["q_reference_sha256"], self.q.digest())

    def test_mutable_external_solution_rows_are_sealed_at_source_creation(self):
        mutable = replace(self.sol, q={k: dict(v) for k, v in self.sol.q.items()})
        src = candidate.prepare_owned_l2_source(self.waiting(), scene=EvaluationScene(0, 0, 0, 0, 1), regime="P",
            solution=mutable, q_reference=self.q, parent=self.parent, reference=self.reference)
        first = next(iter(mutable.q)); action = next(iter(mutable.q[first])); mutable.q[first][action] += 123.
        self.assertEqual(candidate.source_audit(src)["configuration"]["q_reference_sha256"], self.q.digest())
        self.cell(src)

    def test_source_state_change_is_refused_before_targets(self):
        state = self.waiting(); src = self.source(state)
        state.apply_transaction([Edit(PROCESS, 0, 1)])
        with patch.object(candidate, "build_counterfactual_envelope", side_effect=AssertionError("no CF")):
            with self.assertRaises(ready.ProtocolError):
                self.cell(src)

    def test_hidden_suffix_mask_change_is_refused_even_if_factual_rows_unchanged(self):
        src = self.source(); d = candidate._ISSUED[src]
        old_rows = candidate._row_payload(candidate.method_evidence(src))
        # At x=3 the WAIT factual episode never visits this controller site.
        fault = K.ControllerFault(K.State(3, 1, 4, 0, 0), K.WAIT, K.UP)
        object.__setattr__(d.episode, "mask", K.FaultMask(controller=fault))
        self.assertEqual(candidate._row_payload(d.evidence), old_rows)
        with self.assertRaises(ready.ProtocolError):
            candidate.method_evidence(src)

    def test_derived_channel_callable_replacement_is_refused(self):
        src = self.source(); d = candidate._ISSUED[src]
        object.__setattr__(d.episode, "controller_mapping", lambda *args: K.WAIT)
        with self.assertRaises(ready.ProtocolError):
            candidate.source_audit(src)

    def test_source_audit_is_copy_not_truth_or_config_mutation_handle(self):
        src = self.source(); audit = candidate.source_audit(src)
        audit["configuration"]["base_option"] = 3
        audit["truth_evaluator_only"]["Gamma_P_star"] = ["Strategy"]
        self.assertEqual(candidate.source_audit(src)["configuration"]["base_option"], 1)
        self.assertNotEqual(candidate.source_audit(src)["truth_evaluator_only"]["Gamma_P_star"], ["Strategy"])

    def test_other_tiers_and_families_are_refused_without_reading_source(self):
        pairs = (bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite"),
            bridge.registered_pair("D_Q", Tier.L3_ORACLE, "LocalOracleRestore"),
            bridge.registered_pair("P", Tier.L1_CORRECTIVE, "P_id"))
        for arms in pairs:
            with patch.object(candidate, "_checked", side_effect=AssertionError("wrong authority consumed")), \
                 self.assertRaises(ready.ProtocolError):
                candidate.prepare_l2_engineering_cell(None, None, arms)

    def test_pair_role_order_is_strict(self):
        arms = bridge.registered_pair("D_Q", Tier.L2_COUNTERFACTUAL, "DualReturnWrite")
        with self.assertRaises(ready.ProtocolError):
            candidate.prepare_l2_engineering_cell(None, None, tuple(reversed(arms)))

    def test_foreign_factual_packet_is_refused_before_cf(self):
        src = self.source(); ev = candidate.method_evidence(src)
        changed = replace(ev, steps=(replace(ev.steps[0], reward=ev.steps[0].reward + .001),) + ev.steps[1:])
        prepared = credit.prepare_credit(changed, kind="causal", proposal=native.CausalProposal(frozenset({"Decision_0"})))
        with patch.object(candidate, "build_counterfactual_envelope", side_effect=AssertionError("no CF")), self.assertRaises(ready.ProtocolError):
            candidate.prepare_l2_engineering_cell(src, prepared,
                bridge.registered_pair("D_Q", Tier.L2_COUNTERFACTUAL, "DualReturnWrite"))

    def test_equal_factual_packet_does_not_claim_actual_diagnostic_origin(self):
        cell = self.cell()
        self.assertFalse(cell.audit["proposal_origin_authenticated"])
        self.assertFalse(cell.audit["diagnostic_algorithm_executed"])
        self.assertFalse(cell.audit["extra_B1_information_is_ordinary_diagnostic_authority"])

    def test_native_rho_d_and_all_chronological_addresses_are_preserved(self):
        cell = self.cell(units=("L",), kind="module")
        self.assertEqual(cell.credited_units, tuple(f"Decision_{t}" for t in range(K.HORIZON)))
        self.assertEqual(tuple(a.state.t for a in cell.addresses), tuple(range(K.HORIZON)))
        self.assertEqual(len(cell.envelope), K.HORIZON)
        self.assertTrue(cell.audit["residual_predictions_retained_not_reclassified"])

    def test_empty_prediction_has_no_cf_and_not_unknown_or_zero_sample(self):
        src = self.source()
        with patch.object(candidate, "build_counterfactual_envelope", side_effect=AssertionError("abstention CF")):
            cell = self.cell(src, units=())
        self.assertEqual(cell.addresses, ())
        self.assertEqual(cell.deliveries, (None, None))
        self.assertEqual(cell.audit["route"], "NO_DQ_CREDIT_NOT_ZERO_FILLED")
        self.assertEqual(cell.audit["all_expanded_units"], [])

    def test_nonwriteable_only_prediction_is_retained_without_dq_target(self):
        src = self.source()
        with patch.object(candidate, "build_counterfactual_envelope", side_effect=AssertionError("no DQ CF")):
            cell = self.cell(src, units=("Unknown/NoWrite", "ExternalPlant"))
        self.assertEqual(cell.audit["residual_predictions_retained_not_reclassified"], ["ExternalPlant", "Unknown/NoWrite"])
        self.assertIsNone(cell.envelope)

    def test_original_two_role_delivery_exact_fields_and_same_object(self):
        cell = self.cell()
        self.assertIs(cell.deliveries[0], cell.deliveries[1])
        self.assertIs(type(cell.deliveries[0]), MappingProxyType)
        self.assertEqual(set(cell.deliveries[0][cell.addresses[0]]), {"a_factual", "g_factual", "a_plus", "g_cf"})

    def test_factual_return_uses_original_reverse_fold_bitwise(self):
        cell = self.cell(units=("Decision_0", "Decision_4", "Decision_10"))
        for a, target in cell.envelope.items():
            self.assertEqual(target.g_factual.hex(), factual_return_to_go(cell.rows, a.state.t).hex())

    def test_cf_is_full_t0_same_config_one_replaced_decision_not_suffix(self):
        cell = self.cell(units=("Decision_4",)); data = candidate._ISSUED[cell.source]
        address = cell.addresses[0]; target = cell.envelope[address]
        self.assertIsNotNone(target.a_plus)
        cf = data.episode.replay(4, target.a_plus)
        rows = learner_rows(cf, data.scene.kappa, data.scene.phase)
        self.assertEqual(rows[:4], cell.rows[:4])
        self.assertEqual(rows[0][2], 0)
        self.assertEqual(cf.mask, data.episode.mask)
        self.assertEqual(cf.option_in_force, data.episode.factual_trace.option_in_force)
        self.assertEqual(target.g_cf.hex(), factual_return_to_go(rows, 4).hex())

    def test_native_missing_cf_error_propagates_without_fallback(self):
        src = self.source(); before = fingerprint(candidate._ISSUED[src].pre_state)
        with patch.object(candidate, "build_counterfactual_envelope", side_effect=CounterfactualUndefined("fixture later-node refusal")):
            with self.assertRaises(CounterfactualUndefined):
                self.cell(src, law="DualReturnWrite")
        self.assertEqual(fingerprint(candidate._ISSUED[src].pre_state), before)

    def test_source_unchanged_if_native_rollout_raises(self):
        state = self.waiting(); before = fingerprint(state)
        with patch.object(K, "rollout", side_effect=K.MalformedIntervention("native fixture error")):
            with self.assertRaises(K.MalformedIntervention):
                self.source(state)
        self.assertEqual(fingerprint(state), before)

    def test_counterfactual_preparation_cannot_draw_train_or_write(self):
        state = self.waiting(); before = fingerprint(state)
        with patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("environment seed")), \
             patch.object(LearnerPersistentState, "apply_transaction", side_effect=AssertionError("B1 write")):
            cell = self.cell(self.source(state))
        self.assertEqual(fingerprint(state), before)
        self.assertEqual(cell.audit["future_training_episodes"], 0)
        self.assertFalse(cell.audit["collection_authorized"])

    def test_original_b1_pair_clones_link_to_own_episode_without_future(self):
        cell = self.cell(law="DualReturnWrite"); data = candidate._ISSUED[cell.source]
        before = fingerprint(data.pre_state)
        clones = (data.pre_state.clone(), data.pre_state.clone())
        results = tuple(run_dq_law(arm.law, clone, cell.addresses, cell.rows, self.q,
            sol=data.solution, episode=data.episode) for arm, clone in zip(cell.arms, clones))
        self.assertEqual(fingerprint(data.pre_state), before)
        self.assertEqual(results[0].ledger.receipts[0].status, EVALUABLE_NOOP)
        self.assertIsNot(clones[0], clones[1])
        for result in results:
            result.ledger.check_fingerprint_invariants()
            self.assertEqual(result.ledger.fingerprint_pre, before)
        print("SEEDLESS_OWNED_L2_B1_COMPONENT_SUMMARY=" + json.dumps({
            "factual_outcome": data.audit["factual_outcome"], "n_credited": len(cell.addresses),
            "target_audit_sha256": cell.audit_sha256, "native_B1_reference_status": results[0].ledger.receipts[0].status,
            "native_B1_treatment_status": results[1].ledger.receipts[0].status,
            "actual_diagnostic_algorithm_executed": False, "future_training_episodes": 0,
            "environment_seed_draws": 0, "collection_authorized": False}, sort_keys=True))

    def test_original_b1_rejects_foreign_prestate_even_with_valid_cf_targets(self):
        cell = self.cell(); data = candidate._ISSUED[cell.source]
        with self.assertRaises(ready.ProtocolError):
            run_dq_law(cell.arms[1].law, LearnerPersistentState(), cell.addresses, cell.rows, self.q,
                sol=data.solution, episode=data.episode)

    def test_failure_with_no_valid_alternative_is_not_factual_only_fallback(self):
        # Fixed native option0 START row has only RIGHT. The trap makes an
        # actual failed task while its credited decision has no alternative.
        src = self.source(LearnerPersistentState(), regime="T", scene=EvaluationScene(0, 0, 0, 0, 0),
            mask=K.FaultMask(trap=K.Trap((1, 2), 0)))
        cell = self.cell(src, law="DualReturnWrite"); data = candidate._ISSUED[src]
        target = cell.envelope[cell.addresses[0]]
        self.assertEqual(data.audit["factual_outcome"], K.Outcome.TRAP)
        self.assertIsNone(target.a_plus); self.assertIsNone(target.g_cf)
        self.assertEqual(cell.audit["no_valid_alternative_count"], 1)
        self.assertEqual(candidate.validate_l2_engineering_cell(cell), cell.audit_sha256)
        clone = data.pre_state.clone(); before = fingerprint(clone)
        result = run_dq_law(cell.arms[1].law, clone, cell.addresses, cell.rows, self.q,
            sol=data.solution, episode=data.episode)
        self.assertEqual(result.ledger.receipts[0].status, NO_VALID_ALTERNATIVE)
        self.assertEqual(fingerprint(clone), before)
        self.assertEqual(result.ledger.n_scalar, 0)

    def test_real_cf_shadows_decision_effect_but_retains_same_fault_assignment(self):
        # WAIT at option1's actual t1 context hits a legal non-START trap.
        # This is a deterministic geometry fixture, NOT scientific fault
        # population selection; START/GOAL traps remain forbidden unchanged.
        healthy = CfEpisode(kappa=0, tape=EvaluationScene(0, 0, 0, 0, 1).tape,
            snapshot_pre=LearnerPersistentState().snapshot(), reference=self.q, base_option=1)
        cell_at_t1 = healthy.factual_trace.steps[0].state.cell
        self.assertNotIn(cell_at_t1, (K.START, K.GOAL))
        mask = K.FaultMask(decision=K.DecisionOverride(1, K.WAIT), trap=K.Trap(cell_at_t1, 1))
        src = self.source(LearnerPersistentState(), regime="T", mask=mask)
        cell = self.cell(src, units=("Decision_1",)); d = candidate._ISSUED[src]
        self.assertEqual(d.episode.factual_trace.outcome, K.Outcome.TRAP)
        target = cell.envelope[cell.addresses[0]]
        self.assertIsNotNone(target.a_plus)
        cf = d.episode.replay(1, target.a_plus)
        self.assertEqual(cf.mask, mask)
        self.assertEqual(cf.steps[1].a_cmd, target.a_plus)
        self.assertEqual(tuple(iv.kind for iv in cf.interventions.members), ("decision",))

    def test_trace_metadata_change_is_refused_even_with_same_raw_steps(self):
        src = self.source(); d = candidate._ISSUED[src]
        object.__setattr__(d.episode.factual_trace, "base_option", 0)
        with self.assertRaises(ready.ProtocolError):
            candidate.method_evidence(src)

    def test_owned_method_projection_low_level_change_is_refused(self):
        src = self.source(); d = candidate._ISSUED[src]
        object.__setattr__(d.evidence.steps[0], "reward", d.evidence.steps[0].reward + .001)
        with self.assertRaises(ready.ProtocolError):
            candidate.method_evidence(src)

    def test_fresh_native_rederivation_not_cached_audit_is_used(self):
        cell = self.cell()
        with patch.object(candidate, "build_counterfactual_envelope", wraps=candidate.build_counterfactual_envelope) as builder:
            self.assertEqual(candidate.validate_l2_engineering_cell(cell), cell.audit_sha256)
        self.assertEqual(builder.call_count, 1)

    def test_legal_but_false_counterfactual_return_is_refused_bitwise(self):
        cell = self.cell(); a = cell.addresses[0]
        altered = MappingProxyType({a: replace(cell.envelope[a], g_cf=cell.envelope[a].g_cf + .001)})
        with self.assertRaises(ready.ProtocolError):
            candidate.validate_l2_engineering_cell(replace(cell, envelope=altered))

    def test_integer_action_float_alias_and_float_return_integer_alias_are_refused(self):
        cell = self.cell(); a = cell.addresses[0]; target = cell.envelope[a]
        for altered in (replace(target, a_factual=float(target.a_factual)),
                        replace(target, g_factual=int(target.g_factual))):
            with self.subTest(target=altered), self.assertRaises(ready.ProtocolError):
                candidate.validate_l2_engineering_cell(replace(cell, envelope=MappingProxyType({a: altered})))

    def test_half_absent_counterfactual_pair_is_refused(self):
        cell = self.cell(); a = cell.addresses[0]
        with self.assertRaises(ready.ProtocolError):
            candidate.validate_l2_engineering_cell(replace(cell, envelope=MappingProxyType({a:
                replace(cell.envelope[a], g_cf=None)})))

    def test_delivery_extra_field_or_false_return_is_refused(self):
        cell = self.cell(); a = cell.addresses[0]
        for change in ({"z_proposal": 1}, {"g_cf": cell.envelope[a].g_cf + .001},
                       {"a_factual": float(cell.envelope[a].a_factual)}):
            row = MappingProxyType(dict(cell.deliveries[0][a]) | change)
            delivered = MappingProxyType({a: row})
            with self.subTest(change=change), self.assertRaises(ready.ProtocolError):
                candidate.validate_l2_engineering_cell(replace(cell, deliveries=(delivered, delivered)))

    def test_two_content_equal_but_independently_chosen_deliveries_are_refused(self):
        cell = self.cell()
        other = MappingProxyType(dict(cell.deliveries[0]))
        with self.assertRaises(ready.ProtocolError):
            candidate.validate_l2_engineering_cell(replace(cell, deliveries=(cell.deliveries[0], other)))

    def test_row_float_alias_is_refused_before_join(self):
        cell = self.cell(); row = list(cell.rows[0]); row[2] = float(row[2])
        with self.assertRaises(ready.ProtocolError):
            candidate.validate_l2_engineering_cell(replace(cell, rows=(tuple(row),) + cell.rows[1:]))

    def test_forged_collection_audit_even_with_matching_hash_is_refused(self):
        cell = self.cell(); audit = dict(cell.audit); audit["collection_authorized"] = True
        with self.assertRaises(ready.ProtocolError):
            candidate.validate_l2_engineering_cell(replace(cell, audit=audit, audit_sha256=bridge.sha(audit)))


if __name__ == "__main__":
    unittest.main()
