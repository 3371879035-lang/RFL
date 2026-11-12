"""Seedless actual diagnostic/native whole B1 lineage, NOT B2 collection."""
from dataclasses import replace
import inspect
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pair_source_candidate as candidate
import diagnostic_source_candidate as diagnostic
import counterfactual_source_candidate as owned
import native_record_candidate as bridge
import readiness as ready
import test_diagnostic_source_candidate as fixture_module
from rfl_rebuild.b1.contract import APPLIED, EVALUABLE_NOOP, NO_VALID_ALTERNATIVE, fingerprint
from rfl_rebuild.b1.runner import B1Result
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.runner import PairedRunner
from rfl_rebuild.b2.training import ExogenousEpisode
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.store import CONTROLLER, Q, Edit, LearnerPersistentState, QAddress


class PairSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.DiagnosticSourceTests.setUpClass()
        cls.fixture = fixture_module.DiagnosticSourceTests()

    def setup_call(self, *, method="TrajectoryCredit", controller=False, source=None):
        if source is None and controller:
            state = LearnerPersistentState(); edits = []
            for t in range(K.HORIZON):
                s = K.State(*K.START, t, 0, 0)
                edits += [Edit(CONTROLLER, K.ControllerSite(s, a), K.WAIT)
                    for a in K.option_actions(1, K.ControlState(1, 0), s) if a != K.WAIT]
            state.apply_transaction(edits); source = self.fixture.source(state)
        source = self.fixture.source() if source is None else source
        return diagnostic.run_owned_diagnostic(source, method_id=method), source

    def pair(self, *, architecture="D_Q", tier=Tier.L0_FACTUAL, law="FactualReturnWrite", **kw):
        run, source = self.setup_call(**kw)
        handle = candidate.run_owned_b1_pair(run, source, bridge.registered_pair(architecture, tier, law))
        return handle, run, source

    def audit(self, pair):
        return candidate.pair_audit(*pair)

    def test_closed_api_accepts_no_cell_state_ledger_reference_callback_seed(self):
        self.assertEqual(tuple(inspect.signature(candidate.run_owned_b1_pair).parameters), ("run", "source", "arms"))

    def test_nominal_handle_and_detached_records_are_not_origin(self):
        run, source = self.setup_call()
        with self.assertRaises(ready.ProtocolError): candidate.OwnedB1Pair()
        for fake in ({}, None, SimpleNamespace(route="native0"), object.__new__(candidate.OwnedB1Pair)):
            with self.subTest(type=type(fake).__name__), self.assertRaises(ready.ProtocolError):
                candidate.pair_audit(fake, run, source)

    def test_success_skips_before_invalid_arm_or_B1_reads(self):
        source = self.fixture.source(LearnerPersistentState(), regime="T", scene=EvaluationScene(0, 0, 0, 0, 0))
        run, source = self.setup_call(source=source)
        with patch.object(PairedRunner, "_apply", side_effect=AssertionError("success B1")), \
             patch.object(bridge, "validate_pair", side_effect=AssertionError("success arm")):
            handle = candidate.run_owned_b1_pair(run, source, object())
            audit = self.audit((handle, run, source))
        self.assertEqual(audit["B1_arm_calls"], 0); self.assertIsNone(audit["cell"])
        self.assertEqual(audit["ordered_arm_ledgers"], [])

    def test_actual_abstention_has_no_clones_ledgers_or_zero_future(self):
        with patch.object(PairedRunner, "_apply", side_effect=AssertionError("empty B1")):
            pair = self.pair(method="AbstainCreditCandidate")
        audit = self.audit(pair)
        self.assertEqual(audit["route"], "NO_CREDIT_IN_CELL_NO_B1_NOT_SCIENTIFIC_ZERO")
        self.assertEqual(audit["immediate_post_clones"], 0)
        self.assertEqual(audit["ordered_arm_ledgers"], [])
        with self.assertRaises(ready.ProtocolError): candidate.clone_immediate_post(*pair, role="reference")

    def test_zero_projection_keeps_all_other_architecture_predictions(self):
        pair = self.pair(method="ObservedExecutionCreditCandidate", controller=True)
        audit = self.audit(pair)
        self.assertEqual(audit["cell"]["cell_credited_units"], [])
        self.assertEqual(len(audit["cell"]["residual_predictions"]), K.HORIZON)
        self.assertEqual(audit["B1_arm_calls"], 0)

    def test_P_requires_separate_assisted_source_not_current_option(self):
        run, source = self.setup_call()
        with patch.object(PairedRunner, "_apply", side_effect=AssertionError("unlicensed P")):
            with self.assertRaises(ready.ProtocolError): candidate.run_owned_b1_pair(run, source,
                bridge.registered_pair("P", Tier.L1_CORRECTIVE, "P_id"))

    def test_pair_roles_order_and_tier_are_validated_before_B1(self):
        run, source = self.setup_call(); arms = bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite")
        with patch.object(PairedRunner, "_apply", side_effect=AssertionError("bad pair B1")):
            for bad in (list(arms), tuple(reversed(arms)), (arms[0], arms[0]), None):
                with self.subTest(type=type(bad).__name__), self.assertRaises(ready.ProtocolError):
                    candidate.run_owned_b1_pair(run, source, bad)

    def test_whole_X12_value_free_APPLIED_not_scalar_NOOP(self):
        pair = self.pair(architecture="X", law="X_id", controller=True, method="ObservedExecutionCreditCandidate")
        audit = self.audit(pair); ref, treatment = audit["ordered_arm_ledgers"]
        self.assertEqual(ref["n_addressed"], K.HORIZON); self.assertEqual(treatment["n_changed_addresses"], K.HORIZON)
        self.assertTrue(all(r[1] == EVALUABLE_NOOP for r in ref["ordered_receipts"]))
        self.assertTrue(all(r[1] == APPLIED for r in treatment["ordered_receipts"]))
        self.assertFalse(treatment["scalar_metrics_applicable"]); self.assertEqual(treatment["n_scalar"], 0)
        self.assertNotEqual(treatment["fingerprint_pre"], treatment["fingerprint_post"])
        print("SEEDLESS_OWNED_WHOLE_B1_PAIR_SUMMARY=" + json.dumps({
            "n_addressed_each_arm": K.HORIZON, "treatment_changed": K.HORIZON,
            "native_X_scalar_applicable": False, "native_X_n_scalar": 0,
            "actual_diagnostic_call_bound": True, "B1_arm_calls": 2,
            "environment_seed_draws": 0, "future_training_episodes": 0,
            "collection_authorized": False}, sort_keys=True))

    def test_whole_DQ12_native_scalar_accounting_and_residuals(self):
        pair = self.pair(); audit = self.audit(pair)
        ref, treatment = audit["ordered_arm_ledgers"]
        self.assertEqual(ref["n_addressed"], K.HORIZON)
        self.assertEqual(treatment["n_scalar"], K.HORIZON)
        self.assertTrue(treatment["scalar_metrics_applicable"])
        self.assertGreater(float.fromhex(treatment["sum_abs_delta_hex"]), 0.)
        self.assertEqual(len(audit["cell"]["residual_predictions"]), 4 + K.HORIZON)

    def test_L2_whole_native_targets_remain_after_diagnostic(self):
        pair = self.pair(tier=Tier.L2_COUNTERFACTUAL, law="DualReturnWrite")
        audit = self.audit(pair)
        self.assertEqual(audit["ordered_arm_ledgers"][1]["n_addressed"], K.HORIZON)
        self.assertEqual(len(candidate._PAIRS[pair[0]].cell.envelope), K.HORIZON)
        self.assertEqual(diagnostic.diagnostic_audit(pair[1], pair[2])["diagnostic_method_calls"], 1)

    def test_native_no_valid_alternative_is_not_skipped_or_no_credit(self):
        source = self.fixture.source(LearnerPersistentState(), regime="T", scene=EvaluationScene(0, 0, 0, 0, 0),
            mask=K.FaultMask(trap=K.Trap((1, 2), 0)))
        pair = self.pair(source=source, tier=Tier.L2_COUNTERFACTUAL, law="DualReturnWrite")
        audit = self.audit(pair); treatment = audit["ordered_arm_ledgers"][1]
        self.assertEqual(audit["B1_arm_calls"], 2)
        self.assertEqual(treatment["ordered_receipts"][0][1], NO_VALID_ALTERNATIVE)
        self.assertEqual(treatment["fingerprint_pre"], treatment["fingerprint_post"])

    def test_native_calls_are_once_per_arm_shared_evidence_reference_distinct_clones(self):
        run, source = self.setup_call(); before = fingerprint(owned._ISSUED[source].pre_state)
        with patch.object(PairedRunner, "_apply", wraps=PairedRunner._apply) as spy:
            handle = candidate.run_owned_b1_pair(run, source, bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite"))
            candidate.pair_audit(handle, run, source)
        self.assertEqual(spy.call_count, 2)
        first, second = (c.args for c in spy.call_args_list)
        self.assertIsNot(first[1], second[1]); self.assertIsNot(first[1], owned._ISSUED[source].pre_state)
        self.assertIs(first[2], second[2]); self.assertIs(first[3], second[3])
        self.assertEqual(fingerprint(owned._ISSUED[source].pre_state), before)

    def test_validation_does_not_repeat_diagnostic_or_B1(self):
        pair = self.pair()
        with patch.object(diagnostic, "run_owned_diagnostic", side_effect=AssertionError("repeat diagnosis")), \
             patch.object(PairedRunner, "_apply", side_effect=AssertionError("repeat B1")):
            self.audit(pair); candidate.clone_immediate_post(*pair, role="treatment")

    def test_no_environment_keys_or_future_training(self):
        run, source = self.setup_call()
        with patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("environment key")), \
             patch("rfl_rebuild.b2.runner.train_curve", side_effect=AssertionError("future training")):
            handle = candidate.run_owned_b1_pair(run, source, bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite"))
            audit = self.audit((handle, run, source))
        self.assertEqual(audit["future_training_episodes"], 0)

    def test_native_first_error_propagates_no_pair_or_source_write(self):
        run, source = self.setup_call(); before = fingerprint(owned._ISSUED[source].pre_state); n = len(candidate._PAIRS)
        with patch.object(PairedRunner, "_apply", side_effect=ready.ProtocolError("native failure")):
            with self.assertRaises(ready.ProtocolError): candidate.run_owned_b1_pair(run, source,
                bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite"))
        self.assertEqual(len(candidate._PAIRS), n); self.assertEqual(fingerprint(owned._ISSUED[source].pre_state), before)

    def test_second_error_does_not_issue_partial_reference_pair(self):
        run, source = self.setup_call(); original = PairedRunner._apply; calls = []
        before = fingerprint(owned._ISSUED[source].pre_state); n = len(candidate._PAIRS)
        def fail_second(*args):
            calls.append(args)
            if len(calls) == 2: raise ready.ProtocolError("native second failure")
            return original(*args)
        with patch.object(PairedRunner, "_apply", side_effect=fail_second):
            with self.assertRaises(ready.ProtocolError): candidate.run_owned_b1_pair(run, source,
                bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite"))
        self.assertEqual(len(calls), 2); self.assertEqual(len(candidate._PAIRS), n)
        self.assertEqual(fingerprint(owned._ISSUED[source].pre_state), before)

    def test_native_result_cannot_swap_its_post_state_for_equal_clone(self):
        run, source = self.setup_call(); original = PairedRunner._apply
        def swapped(*args):
            r = original(*args); return B1Result(r.ledger, r.post_state.clone())
        with patch.object(PairedRunner, "_apply", side_effect=swapped):
            with self.assertRaises(ready.ProtocolError): candidate.run_owned_b1_pair(run, source,
                bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite"))

    def test_shared_clone_refused_before_native_apply(self):
        run, source = self.setup_call(); clone = owned._ISSUED[source].pre_state.clone()
        with patch.object(LearnerPersistentState, "clone", return_value=clone), \
             patch.object(PairedRunner, "_apply", side_effect=AssertionError("aliased clone B1")):
            with self.assertRaises(ready.ProtocolError): candidate.run_owned_b1_pair(run, source,
                bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite"))

    def test_equal_source_or_other_actual_call_cannot_transfer_pair(self):
        pair = self.pair(); other = self.fixture.source()
        with self.assertRaises(ready.ProtocolError): candidate.pair_audit(pair[0], pair[1], other)
        other_run = diagnostic.run_owned_diagnostic(pair[2], method_id="TrajectoryCredit")
        with self.assertRaises(ready.ProtocolError): candidate.pair_audit(pair[0], other_run, pair[2])

    def test_audit_is_copy_not_capability_or_mutable_result(self):
        pair = self.pair(); audit = self.audit(pair); original = self.audit(pair)
        audit["ordered_arm_ledgers"][1]["ordered_receipts"].clear(); audit["cell"]["cell_credited_units"].clear()
        self.assertEqual(self.audit(pair), original)
        with self.assertRaises(ready.ProtocolError): candidate.pair_audit(original, pair[1], pair[2])

    def test_export_fresh_clones_cannot_mutate_pinned_post_or_other_arm(self):
        pair = self.pair(); audit = self.audit(pair)
        first = candidate.clone_immediate_post(*pair, role="treatment")
        second = candidate.clone_immediate_post(*pair, role="treatment")
        self.assertIsNot(first, second)
        s = K.State(*K.START, 0, 0, 0)
        first.apply_transaction([Edit(CONTROLLER, K.ControllerSite(s, K.WAIT), K.RIGHT)])
        self.assertEqual(self.audit(pair), audit); self.assertNotEqual(fingerprint(first), fingerprint(second))

    def test_role_is_explicit_no_bool_or_integer_alias(self):
        pair = self.pair()
        for role in (True, 0, 1, "future", None):
            with self.subTest(role=role), self.assertRaises(ready.ProtocolError): candidate.clone_immediate_post(*pair, role=role)

    def test_export_refuses_pinned_source_other_arm_wrong_state_and_type(self):
        pair = self.pair(); data = candidate._PAIRS[pair[0]]
        source_pre = owned._ISSUED[pair[2]].pre_state
        wrong_state = data.clones[1].clone(); s = K.State(*K.START, 0, 0, 0)
        wrong_state.apply_transaction([Edit(CONTROLLER, K.ControllerSite(s, K.WAIT), K.RIGHT)])
        for bad in (data.clones[1], data.clones[0], source_pre, wrong_state, object()):
            with self.subTest(type=type(bad).__name__), \
                 patch.object(LearnerPersistentState, "clone", return_value=bad):
                with self.assertRaises(ready.ProtocolError): candidate.clone_immediate_post(*pair, role="treatment")

    def test_pinned_post_state_change_refused(self):
        pair = self.pair(); state = candidate._PAIRS[pair[0]].clones[1]; s = K.State(*K.START, 0, 0, 0)
        state.apply_transaction([Edit(CONTROLLER, K.ControllerSite(s, K.WAIT), K.RIGHT)])
        with self.assertRaises(ready.ProtocolError): self.audit(pair)

    def test_source_change_after_native_pair_refused(self):
        pair = self.pair(); state = owned._ISSUED[pair[2]].pre_state; s = K.State(*K.START, 0, 0, 0)
        state.apply_transaction([Edit(CONTROLLER, K.ControllerSite(s, K.WAIT), K.RIGHT)])
        with self.assertRaises(ready.ProtocolError): self.audit(pair)

    def test_missing_reordered_receipts_cannot_keep_whole_ledger_authority(self):
        for change in (lambda rs: rs[:-1], lambda rs: tuple(reversed(rs))):
            pair = self.pair(); ledger = candidate._PAIRS[pair[0]].results[1].ledger
            object.__setattr__(ledger, "receipts", change(ledger.receipts))
            with self.assertRaises(ready.ProtocolError): self.audit(pair)

    def test_receipt_canonical_identity_and_status_are_not_free_labels(self):
        for field, value in (("canonical_form", "WRONG"), ("status", "PROTOCOL_ERROR"), ("store_changed", 1)):
            pair = self.pair(); receipt = candidate._PAIRS[pair[0]].results[1].ledger.receipts[0]
            object.__setattr__(receipt, field, value)
            with self.assertRaises(ready.ProtocolError): self.audit(pair)

    def test_native_scalar_count_and_exact_original_sum_recomputed(self):
        for field, value in (("n_scalar", K.HORIZON + 1), ("sum_abs_delta", 1.), ("max_abs_delta", float("nan"))):
            pair = self.pair(); ledger = candidate._PAIRS[pair[0]].results[1].ledger
            object.__setattr__(ledger, field, value)
            with self.assertRaises(ready.ProtocolError): self.audit(pair)

    def test_scalar_type_alias_or_signed_zero_is_not_accepted(self):
        for field, value in (("n_scalar", True), ("scalar_metrics_applicable", 1), ("sum_abs_delta", -0.)):
            pair = self.pair(architecture="X", law="X_id", controller=True, method="ObservedExecutionCreditCandidate")
            object.__setattr__(candidate._PAIRS[pair[0]].results[1].ledger, field, value)
            with self.assertRaises(ready.ProtocolError): self.audit(pair)

    def test_whole_cell_cannot_be_truncated_after_execution(self):
        pair = self.pair(); cell = candidate._PAIRS[pair[0]].cell
        object.__setattr__(cell, "addresses", cell.addresses[:1])
        with self.assertRaises(ready.ProtocolError): self.audit(pair)

    def test_dependency_byte_guard_not_nominal_code_name(self):
        with patch.object(candidate, "_CODE_BINDING", tuple("0" * 64 for _ in candidate._CODE_BINDING)):
            with self.assertRaises(ready.ProtocolError): self.pair()

    def test_no_science_U2_future_or_old_cell_relabelling_authority(self):
        pair = self.pair(); audit = self.audit(pair)
        for key in ("collection_authorized", "scientific_claim_authorized", "research_complete",
            "science_acquisition_origin_authenticated", "whole_set_U2_or_NoWrite_science_policy_selected",
            "old_cell_audit_relabelled_as_scientific_execution"):
            self.assertIs(audit[key], False)
        self.assertFalse(candidate._PAIRS[pair[0]].cell.audit["B1_executed"])


if __name__ == "__main__": unittest.main()
