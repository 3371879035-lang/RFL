"""Actual invocation/source-continuity engineering checks, no science keys."""
import ast
import inspect
import json
from pathlib import Path
import sys
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagnostic_source_candidate as candidate
import ordinary_methods_candidate as methods
import counterfactual_source_candidate as owned
import credit_delivery_candidate as credit
import native_record_candidate as bridge
import readiness as ready
from rfl_rebuild.b1.contract import EVALUABLE_NOOP, fingerprint
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.runner import PairedRunner
from rfl_rebuild.b2.training import ExogenousEpisode
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import CONTROLLER, PROCESS, Q, Edit, LearnerPersistentState, QAddress
from rfl_rebuild.method.contract import FactualEvidence, FactualStep, ProtocolError
from rfl_rebuild.method.credit import CausalProposal
from rfl_rebuild.solve.dp import solve_reference


class DiagnosticSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = ready.load_parent()
        cls.reference = ready.read_json(ready.ROOT / ready.FOLDER / "b2_prepare/healthy_reference_candidate.json")
        cls.sol = solve_reference(); cls.q = reference_view_from(cls.sol)

    def waiting(self):
        state = LearnerPersistentState()
        edits = [Edit(Q, QAddress(K.State(*K.START, t, 0, 0), 1, 0, K.WAIT),
            max(self.q.row(K.State(*K.START, t, 0, 0), 1, 0).values()) + 1.) for t in range(K.HORIZON)]
        state.apply_transaction(edits, q_reference=self.q)
        return state

    def source(self, state=None, *, regime="P", scene=None, **kw):
        return owned.prepare_owned_l2_source(self.waiting() if state is None else state,
            scene=scene or EvaluationScene(0, 0, 0, 0, 1), regime=regime,
            solution=self.sol, q_reference=self.q, parent=self.parent, reference=self.reference, **kw)

    def diagnose(self, source=None, method="TrajectoryCredit"):
        source = self.source() if source is None else source
        return candidate.run_owned_diagnostic(source, method_id=method), source

    def transient(self, *, plant=False):
        start = K.State(*K.START, 0, 0, 0)
        mask = K.FaultMask(plant=K.PlantFault(0, K.WAIT) if plant else None,
            controller=None if plant else K.ControllerFault(start, K.RIGHT, K.WAIT),
            trap=K.Trap((1, 2), 1))
        return self.source(LearnerPersistentState(), regime="T",
            scene=EvaluationScene(0, 0, 0, 0, 0), mask=mask)

    def test_api_has_no_callback_packet_prediction_truth_or_query_input(self):
        self.assertEqual(tuple(inspect.signature(candidate.run_owned_diagnostic).parameters),
                         ("source", "method_id"))

    def test_registry_is_explicit_closed_readonly_and_not_CSL(self):
        self.assertIs(type(candidate.METHODS), MappingProxyType)
        self.assertEqual(set(candidate.METHODS), {"TrajectoryCredit", "ObservedExecutionCreditCandidate", "AbstainCreditCandidate"})
        with self.assertRaises(TypeError): candidate.METHODS["fake"] = lambda x: x

    def test_unknown_method_refused_before_reading_source(self):
        with patch.object(owned, "_checked", side_effect=AssertionError("unknown method touched source")):
            for name in ("CausalSetLocator", "P_CSL", "OracleCredit", "", None, lambda x: x):
                with self.subTest(name=type(name).__name__), self.assertRaises(ready.ProtocolError):
                    candidate.run_owned_diagnostic(None, method_id=name)

    def test_registry_replacement_cannot_install_arbitrary_callback(self):
        with patch.object(candidate, "METHODS", {"TrajectoryCredit": (lambda x: x, "trajectory", "fake")}):
            with self.assertRaises(ready.ProtocolError): self.diagnose()

    def test_nominal_and_unissued_diagnostic_handles_are_refused(self):
        with self.assertRaises(ready.ProtocolError): candidate.OwnedDiagnosticRun()
        src = self.source()
        for fake in (object.__new__(candidate.OwnedDiagnosticRun), {}, None, SimpleNamespace(prepared=None)):
            with self.subTest(fake=type(fake).__name__), self.assertRaises(ready.ProtocolError):
                candidate.diagnostic_credit(fake, src)

    def test_supplied_proposal_and_matching_audit_hash_are_not_invocation_origin(self):
        run, src = self.diagnose()
        for fake in (candidate.diagnostic_audit(run, src), bridge.sha(candidate.diagnostic_audit(run, src)),
                     credit.prepare_credit(owned.method_evidence(src), kind="causal", proposal=CausalProposal(frozenset()))):
            with self.subTest(fake=type(fake).__name__), self.assertRaises(ready.ProtocolError):
                candidate.diagnostic_credit(fake, src)

    def test_actual_call_receives_only_same_owned_closed_evidence(self):
        src = self.source(); expected = owned.method_evidence(src)
        original = methods._input
        with patch.object(methods, "_input", wraps=original) as guard:
            run = candidate.run_owned_diagnostic(src, method_id="TrajectoryCredit")
        self.assertEqual(guard.call_count, 1)
        self.assertIs(guard.call_args.args[0], expected)
        self.assertEqual(set(expected.__slots__), {"steps", "z_in_force", "kappa", "phi"})
        self.assertEqual(candidate.diagnostic_audit(run, src)["diagnostic_method_calls"], 1)

    def test_success_is_skipped_without_input_call_prediction_or_query(self):
        src = self.source(LearnerPersistentState(), regime="T")
        with patch.object(methods, "_input", side_effect=AssertionError("SUCCESS reflected")):
            run = candidate.run_owned_diagnostic(src, method_id="TrajectoryCredit")
        audit = candidate.diagnostic_audit(run, src)
        self.assertEqual(audit["route"], "SUCCESS_NO_REFLECTION")
        self.assertEqual(audit["diagnostic_method_calls"], 0)
        self.assertIsNone(audit["native_proposal_units"])
        self.assertIsNone(audit["method_input_sha256"])
        with self.assertRaises(ready.ProtocolError): candidate.diagnostic_credit(run, src)

    def test_dormant_fault_success_does_not_override_trigger(self):
        src = self.source(LearnerPersistentState(), regime="T", mask=K.FaultMask(decision=K.DecisionOverride(11, K.WAIT)))
        run = candidate.run_owned_diagnostic(src, method_id="ObservedExecutionCreditCandidate")
        self.assertEqual(candidate.diagnostic_audit(run, src)["diagnostic_method_calls"], 0)

    def test_P_failure_without_manifestation_is_not_diagnostic_abstention(self):
        pre = LearnerPersistentState(); pre.apply_transaction([Edit(PROCESS, 1, 2)])
        src = self.source(pre, scene=EvaluationScene(0, 2, 0, 0, 0))
        with patch.object(methods, "_input", side_effect=AssertionError("no manifestation input")):
            run = candidate.run_owned_diagnostic(src, method_id="AbstainCreditCandidate")
        self.assertEqual(candidate.diagnostic_audit(run, src)["route"], "P_FAILURE_WITHOUT_MANIFESTATION_NO_REFLECTION")
        self.assertIsNone(candidate.diagnostic_audit(run, src)["native_proposal_units"])

    def test_actual_trajectory_rule_keeps_complete_original_eta_domain(self):
        run, src = self.diagnose(); prepared = candidate.diagnostic_credit(run, src)
        shape = credit.factual_projection(prepared.evidence)[1]
        self.assertEqual(set(prepared.expanded_units), set(shape.gamma()))
        self.assertEqual(prepared.proposal.units, frozenset({"Episode"}))
        self.assertEqual(len(prepared.expanded_units), 4 + 2 * K.HORIZON)

    def test_abstention_is_actual_call_empty_not_UnknownNoWrite(self):
        run, src = self.diagnose(method="AbstainCreditCandidate")
        audit = candidate.diagnostic_audit(run, src)
        self.assertEqual(audit["diagnostic_method_calls"], 1)
        self.assertEqual(audit["native_proposal_units"], [])
        self.assertEqual(audit["whole_original_eta_expansion"], [])

    def test_execution_heuristic_does_not_invent_Q_or_process_diagnosis(self):
        run, src = self.diagnose(method="ObservedExecutionCreditCandidate")
        # Genuine persistent Q WAIT failure; command==realization at every step.
        self.assertEqual(candidate.diagnostic_credit(run, src).expanded_units, ())
        self.assertEqual(candidate.diagnostic_audit(run, src)["diagnostic_method_calls"], 1)

    def test_execution_heuristic_keeps_all_twelve_full_wire_sites(self):
        pre = LearnerPersistentState(); edits = []
        for t in range(K.HORIZON):
            s = K.State(*K.START, t, 0, 0)
            for cmd in K.option_actions(1, K.ControlState(1, 0), s):
                if cmd != K.WAIT: edits.append(Edit(CONTROLLER, K.ControllerSite(s, cmd), K.WAIT))
        pre.apply_transaction(edits)
        run, src = self.diagnose(self.source(pre), "ObservedExecutionCreditCandidate")
        prepared = candidate.diagnostic_credit(run, src)
        self.assertEqual(len(prepared.expanded_units), K.HORIZON)
        expected = tuple(f"ControllerSite_{s.x}_{s.y}_{s.t}_{s.a_cmd}" for s in prepared.evidence.steps)
        self.assertEqual(prepared.expanded_units, expected)

    def test_same_visible_rows_controller_vs_plant_get_same_prediction_not_truth(self):
        x, e = self.transient(), self.transient(plant=True)
        self.assertEqual(owned._row_payload(owned.method_evidence(x)), owned._row_payload(owned.method_evidence(e)))
        xr, _ = self.diagnose(x, "ObservedExecutionCreditCandidate")
        er, _ = self.diagnose(e, "ObservedExecutionCreditCandidate")
        self.assertEqual(candidate.diagnostic_credit(xr, x).proposal, candidate.diagnostic_credit(er, e).proposal)
        self.assertNotEqual(owned.source_audit(x)["truth_evaluator_only"], owned.source_audit(e)["truth_evaluator_only"])
        self.assertIn("ControllerSite_0_2_0_3", candidate.diagnostic_credit(er, e).expanded_units)

    def test_identical_rows_from_different_sources_cannot_transfer_origin(self):
        x, e = self.transient(), self.transient(plant=True)
        run, _ = self.diagnose(x)
        with self.assertRaises(ready.ProtocolError): candidate.diagnostic_credit(run, e)

    def test_same_bytes_fresh_source_also_cannot_transfer_origin(self):
        run, src = self.diagnose()
        other = self.source()
        self.assertEqual(owned._row_payload(owned.method_evidence(src)), owned._row_payload(owned.method_evidence(other)))
        with self.assertRaises(ready.ProtocolError): candidate.diagnostic_credit(run, other)

    def test_learner_changed_after_call_invalidates_consumer(self):
        pre = self.waiting(); run, src = self.diagnose(self.source(pre))
        pre.apply_transaction([Edit(PROCESS, 0, 1)])
        with self.assertRaises(ready.ProtocolError): candidate.diagnostic_credit(run, src)

    def test_proposal_tampering_after_call_cannot_be_promoted(self):
        run, src = self.diagnose()
        object.__setattr__(candidate._RUNS[run].prepared.proposal, "units", frozenset())
        with self.assertRaises(ready.ProtocolError): candidate.diagnostic_credit(run, src)

    def test_expansion_tampering_after_call_is_refused(self):
        run, src = self.diagnose()
        object.__setattr__(candidate._RUNS[run].prepared, "expanded_units", ("Decision_0",))
        with self.assertRaises(ready.ProtocolError): candidate.diagnostic_credit(run, src)

    def test_audit_is_copy_and_not_a_source_capability(self):
        run, src = self.diagnose(); first = candidate.diagnostic_audit(run, src)
        first["collection_authorized"] = True; first["native_proposal_units"].clear()
        fresh = candidate.diagnostic_audit(run, src)
        self.assertFalse(fresh["collection_authorized"])
        self.assertEqual(fresh["native_proposal_units"], ["Episode"])

    def test_source_code_binding_change_refuses_before_call(self):
        with patch.object(candidate, "_CODE_BINDING", ("0" * 64, "0" * 64)):
            with self.assertRaises(ready.ProtocolError): self.diagnose()

    def test_algorithm_exception_propagates_without_record_or_fallback(self):
        src = self.source(); count = len(candidate._RUNS)
        with patch.object(methods, "_input", side_effect=RuntimeError("native candidate failure")):
            with self.assertRaisesRegex(RuntimeError, "native candidate failure"):
                candidate.run_owned_diagnostic(src, method_id="TrajectoryCredit")
        self.assertEqual(len(candidate._RUNS), count)
        self.assertEqual(owned.source_audit(src)["source_fingerprint_pre"], owned.source_audit(src)["source_fingerprint_post"])

    def test_no_environment_key_draw_training_CF_or_B1_write_in_diagnosis(self):
        src = self.source()
        with patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("env draw")), \
             patch.object(LearnerPersistentState, "apply_transaction", side_effect=AssertionError("write")), \
             patch.object(owned, "build_counterfactual_envelope", side_effect=AssertionError("method CF")):
            run = candidate.run_owned_diagnostic(src, method_id="TrajectoryCredit")
        audit = candidate.diagnostic_audit(run, src)
        self.assertEqual((audit["query_calls"], audit["environment_seed_draws"], audit["future_training_episodes"]), (0, 0, 0))

    def test_ordinary_module_import_graph_has_no_source_reference_kernel_or_B1(self):
        tree = ast.parse(Path(methods.__file__).read_text(encoding="utf-8"))
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertEqual(set(imports), {"__future__", "rfl_rebuild.method.contract", "rfl_rebuild.method.credit"})
        imported = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        self.assertEqual(imported, ["math"])

    def test_ordinary_algorithm_functions_have_only_evidence_argument(self):
        for name, (fn, _, _) in candidate.METHODS.items():
            self.assertEqual(tuple(inspect.signature(fn).parameters), ("evidence",), name)

    def test_ordinary_methods_refuse_duck_or_truth_capable_packet(self):
        for obj in (SimpleNamespace(steps=()), {"truth": [1]}, None):
            for fn, _, _ in candidate.METHODS.values():
                with self.assertRaises(ProtocolError): fn(obj)

    def test_ordinary_methods_refuse_float_alias_fields(self):
        src = self.source(); original = owned.method_evidence(src)
        fields = {name: getattr(original.steps[0], name) for name in FactualStep.__slots__}
        fields["t"] = 0.0
        forged = FactualEvidence((FactualStep(**fields),), original.z_in_force, original.kappa, original.phi)
        with self.assertRaises(ProtocolError): methods.observed_execution_credit(forged)

    def test_L2_targets_are_after_diagnosis_and_no_prediction_is_dropped(self):
        run, src = self.diagnose()
        arms = bridge.registered_pair("D_Q", Tier.L2_COUNTERFACTUAL, "DualReturnWrite")
        cell = candidate.prepare_diagnosed_l2_cell(run, src, arms)
        owned.validate_l2_engineering_cell(cell)
        self.assertEqual(len(cell.credited_units), K.HORIZON)
        self.assertEqual(set(cell.audit["all_expanded_units"]), set(candidate.diagnostic_credit(run, src).expanded_units))
        self.assertIs(cell.deliveries[0], cell.deliveries[1])
        self.assertGreater(len(cell.prepared.expanded_units), len(cell.credited_units))

    def test_single_site_instrument_still_refuses_whole_episode_truncation(self):
        run, src = self.diagnose()
        cell = candidate.prepare_diagnosed_cell(run, src,
            bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite"))
        with self.assertRaises(ready.ProtocolError): credit.single_credited_site(cell)

    def test_P_L1_diagnostic_source_does_not_grant_hidden_proposal_assistance(self):
        run, src = self.diagnose()
        with self.assertRaises(ready.ProtocolError): candidate.prepare_diagnosed_cell(run, src,
            bridge.registered_pair("P", Tier.L1_CORRECTIVE, "P_id"))

    def test_old_v7_source_audit_not_relabelled_as_actual_diagnosis(self):
        run, src = self.diagnose()
        self.assertFalse(owned.source_audit(src)["diagnostic_algorithm_executed"])
        self.assertTrue(candidate.diagnostic_audit(run, src)["actual_diagnostic_algorithm_executed"])

    def test_every_audit_has_false_collection_model_and_science_authority(self):
        for method in candidate.METHODS:
            run, src = self.diagnose(method=method); audit = candidate.diagnostic_audit(run, src)
            for key in ("complete_T_or_P_hypothesis_model_claimed", "scientific_algorithm_family_selected_or_frozen",
                "collection_authorized", "scientific_claim_authorized", "research_complete",
                "fire_truth_Q_policy_or_tier_assistance_delivered_to_method", "science_acquisition_origin_authenticated"):
                self.assertIs(audit[key], False)

    def test_actual_P_call_full_X_credit_into_native_B1_paired_clones(self):
        pre = LearnerPersistentState(); edits = []
        for t in range(K.HORIZON):
            s = K.State(*K.START, t, 0, 0)
            for cmd in K.option_actions(1, K.ControlState(1, 0), s):
                if cmd != K.WAIT: edits.append(Edit(CONTROLLER, K.ControllerSite(s, cmd), K.WAIT))
        pre.apply_transaction(edits); before = fingerprint(pre)
        run, src = self.diagnose(self.source(pre), "ObservedExecutionCreditCandidate")
        cell = candidate.prepare_diagnosed_cell(run, src, bridge.registered_pair("X", Tier.L0_FACTUAL, "X_id"))
        clones = (pre.clone(), pre.clone())
        results = tuple(PairedRunner._apply(a, clone, cell.b1_evidence, self.q)
            for a, clone in zip(cell.arms, clones))
        self.assertEqual(len(results[0].ledger.receipts), K.HORIZON)
        self.assertTrue(all(r.status == EVALUABLE_NOOP for r in results[0].ledger.receipts))
        self.assertTrue(all(r.status == "APPLIED" for r in results[1].ledger.receipts))
        self.assertEqual(len(results[1].ledger.receipts), K.HORIZON)
        self.assertEqual(fingerprint(pre), before)
        self.assertIs(cell.deliveries[0], cell.deliveries[1])
        print("SEEDLESS_ACTUAL_DIAGNOSTIC_B1_SUMMARY=" + json.dumps({
            "actual_candidate_method_calls": 1, "n_credited_controller_sites": K.HORIZON,
            "reference_receipt_statuses": [r.status for r in results[0].ledger.receipts],
            "treatment_receipt_statuses": [r.status for r in results[1].ledger.receipts],
            "environment_seed_draws": 0, "future_training_episodes": 0,
            "collection_authorized": False}, sort_keys=True))

    def test_T_plant_misattribution_kept_but_native_X_identity_is_noop(self):
        src = self.transient(plant=True)
        run, _ = self.diagnose(src, "ObservedExecutionCreditCandidate")
        cell = candidate.prepare_diagnosed_cell(run, src, bridge.registered_pair("X", Tier.L0_FACTUAL, "X_id"))
        # An observable heuristic can be wrong about blame; it is not truth.
        truth = owned.source_audit(src)["truth_evaluator_only"]["Gamma_T_star"]
        self.assertNotIn(cell.credited_units[0], truth)
        data = owned._ISSUED[src]; pre = data.pre_state; before = fingerprint(pre)
        clone = pre.clone()
        result = PairedRunner._apply(cell.arms[1], clone, cell.b1_evidence, self.q)
        self.assertEqual(len(result.ledger.receipts), 1)
        self.assertEqual(result.ledger.receipts[0].status, EVALUABLE_NOOP)
        self.assertEqual(fingerprint(clone), before)
        self.assertEqual(fingerprint(pre), before)


if __name__ == "__main__":
    unittest.main()
