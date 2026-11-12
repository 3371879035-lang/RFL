"""Seedless protected future-input construction/refusal tests, not collection."""
from dataclasses import replace
from fractions import Fraction
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import future_inputs_candidate as candidate
import test_single_map_source_candidate as fixture_module
import diagnostic_source_candidate as diagnostic
import counterfactual_source_candidate as owned
import pair_source_candidate as pair
import single_map_source_candidate as maps
import readiness as ready
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.b2.runner import PairedRunner
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.store import PROCESS, Edit, LearnerPersistentState


class FutureInputsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.SingleMapTests.setUpClass()
        cls.fixture = fixture_module.SingleMapTests.fixture
        cls.source = fixture_module.SingleMapTests.source
        cls.diagnostic_run = fixture_module.SingleMapTests.diagnostic_run
        cls.map_handle = fixture_module.SingleMapTests.handle
        cls.before_maps = maps.single_maps_audit(cls.map_handle, cls.diagnostic_run, cls.source)
        cls.calls = []
        actual_clone = pair.clone_immediate_post
        def clone(*args, **kw):
            cls.calls.append(kw["role"]); return actual_clone(*args, **kw)
        with patch.object(pair, "clone_immediate_post", side_effect=clone), \
             patch.object(candidate.training, "train_curve", side_effect=AssertionError("training")), \
             patch.object(candidate.training.ExogenousEpisode, "derive", side_effect=AssertionError("key")), \
             patch.object(candidate.training, "FutureTrainingProtocol", side_effect=AssertionError("protocol")), \
             patch.object(PairedRunner, "_apply", side_effect=AssertionError("repeat B1")), \
             patch.object(maps.maps, "measure_scene_map", side_effect=AssertionError("repeat map")), \
             patch.object(maps.native, "pre_update_traces", side_effect=AssertionError("repeat census")):
            cls.handle = candidate.prepare_owned_future_inputs(cls.map_handle, cls.diagnostic_run, cls.source)

    def audit(self): return candidate.future_inputs_audit(self.handle, self.diagnostic_run, self.source)

    def test_closed_API_no_seed_protocol_curve_state_gate_or_callback(self):
        self.assertEqual(tuple(inspect.signature(candidate.prepare_owned_future_inputs).parameters),
                         ("map_handle", "run", "source"))
        for key in ("seed", "protocol", "curves", "state", "receipt", "callback", "arms", "t_max"):
            with self.assertRaises(TypeError):
                candidate.prepare_owned_future_inputs(self.map_handle, self.diagnostic_run, self.source, **{key: None})

    def test_actual_existing_pair_consumed_once_without_any_training(self):
        self.assertEqual(self.calls, ["reference", "treatment"])
        self.assertEqual(maps.single_maps_audit(self.map_handle, self.diagnostic_run, self.source), self.before_maps)
        a = self.audit()
        self.assertIs(a["existing_unique_B1_pair_consumed_no_reexecution"], True)
        self.assertEqual(a["future_training_episodes"], 0); self.assertEqual(a["environment_seed_draws"], 0)
        print("SEEDLESS_PROTECTED_FUTURE_INPUTS_SUMMARY=" + json.dumps({
            "new_U2_rollouts": 0, "new_map_calls": 0, "new_B1_calls": 0,
            "shared_seed_free_templates": 1, "protected_role_bases": 2,
            "native_protocols_created": 0, "native_curves_created": 0,
            "environment_seed_draws": 0, "future_training_episodes": 0,
            "collection_authorized": False}, sort_keys=True))

    def test_one_shared_object_all_locked_constants_and_dense466_axis(self):
        d = candidate._ISSUED[self.handle]; t = d.template
        self.assertIs(d.role_templates[0], t); self.assertIs(d.role_templates[1], t)
        self.assertEqual(t.alpha, Fraction(1, 2)); self.assertEqual(t.epsilon, Fraction(1, 10))
        self.assertEqual(t.t_max, 465); self.assertEqual(t.grid, tuple(range(466)))
        self.assertEqual(t.evaluation_sample, candidate.prefix(100))
        self.assertEqual(t.v_pre.hex(), (.7642000000000008).hex())
        self.assertNotEqual(t.v_pre, candidate._PARENT["lock"]["v_pre"])
        self.assertFalse(hasattr(t, "seed")); self.assertEqual(self.audit()["shared_template_object_count"], 1)

    def test_all_future_bases_independent_from_source_immediate_and_raw_targets(self):
        d = candidate._ISSUED[self.handle]; md = maps._ISSUED[self.map_handle]
        pd = pair._PAIRS[md.pair]; pre = owned._ISSUED[self.source].pre_state
        states = [b.state for b in d.bases]
        self.assertIsNot(states[0], states[1])
        for i, s in enumerate(states):
            self.assertTrue(all(s is not c for c in (pre, *pd.clones, *md.post_clones)))
            self.assertEqual(fingerprint(s), fingerprint(pd.clones[i]))

    def test_requested_role_export_is_fresh_and_cannot_mutate_pinned_inputs(self):
        before = self.audit(); d = candidate._ISSUED[self.handle]
        a = candidate.clone_future_start(self.handle, self.diagnostic_run, self.source, role="treatment")
        b = candidate.clone_future_start(self.handle, self.diagnostic_run, self.source, role="treatment")
        self.assertIsNot(a, b); self.assertTrue(all(a is not x.state for x in d.bases))
        a.apply_transaction([Edit(PROCESS, 0, 1)])
        self.assertEqual(self.audit(), before)
        self.assertEqual(maps.single_maps_audit(self.map_handle, self.diagnostic_run, self.source), self.before_maps)

    def test_no_write_future_start_matches_full_original_pre_state(self):
        d = candidate._ISSUED[self.handle]
        self.assertEqual(fingerprint(d.bases[0].state), owned._ISSUED[self.source].fingerprint_pre)

    def test_closed_constructor_and_fake_audit_hash_protocol_handle_refused(self):
        with self.assertRaises(ready.ProtocolError): candidate.OwnedFutureInputs()
        for fake in (None, {}, self.audit(), self.audit()["input_sha256"], self.map_handle,
                     object.__new__(candidate.OwnedFutureInputs), candidate._ISSUED[self.handle].template):
            with self.assertRaises(ready.ProtocolError): candidate.future_inputs_audit(fake, self.diagnostic_run, self.source)

    def test_detached_map_audit_or_hash_cannot_prepare(self):
        for fake in (self.before_maps, self.before_maps["raw_input_sha256"],
                     object.__new__(maps.OwnedSingleMaps), None):
            with self.assertRaises(ready.ProtocolError): candidate.prepare_owned_future_inputs(fake, self.diagnostic_run, self.source)

    def test_equal_new_source_and_new_diagnostic_call_cannot_transfer_origin(self):
        source = self.fixture.transient()
        with self.assertRaises(ready.ProtocolError): candidate.future_inputs_audit(self.handle, self.diagnostic_run, source)
        run = diagnostic.run_owned_diagnostic(self.source, method_id="ObservedExecutionCreditCandidate")
        with self.assertRaises(ready.ProtocolError): candidate.future_inputs_audit(self.handle, run, self.source)

    def test_exported_audit_is_detached_not_mutable_internal_reference(self):
        a = self.audit(); a["complete_input_payload"]["template"]["grid"].pop()
        a["complete_input_payload"]["ordered_future_bases"].reverse()
        self.assertEqual(len(self.audit()["complete_input_payload"]["template"]["grid"]), 466)

    def test_fresh_audits_and_exports_never_repeat_key_rollout_B1_or_map(self):
        with patch.object(candidate.training, "train_curve", side_effect=AssertionError("future")), \
             patch.object(candidate.training.ExogenousEpisode, "derive", side_effect=AssertionError("key")), \
             patch.object(diagnostic, "run_owned_diagnostic", side_effect=AssertionError("diagnosis")), \
             patch.object(PairedRunner, "_apply", side_effect=AssertionError("B1")), \
             patch.object(maps.maps, "measure_scene_map", side_effect=AssertionError("map")), \
             patch.object(maps.native, "pre_update_traces", side_effect=AssertionError("U2")):
            self.audit(); candidate.clone_future_start(self.handle, self.diagnostic_run, self.source, role="reference")

    def test_swapped_role_bases_refused_even_when_healthy_fingerprints_tie(self):
        d = candidate._ISSUED[self.handle]
        self.assertEqual(fingerprint(d.bases[0].state), fingerprint(d.bases[1].state))
        with patch.dict(candidate._ISSUED, {self.handle: replace(d, bases=tuple(reversed(d.bases)))}):
            with self.assertRaisesRegex(ready.ProtocolError, "role"): self.audit()

    def test_alias_and_partial_bases_refused(self):
        d = candidate._ISSUED[self.handle]
        for bases in ((d.bases[0], d.bases[0]), d.bases[:1], (), list(d.bases)):
            with patch.dict(candidate._ISSUED, {self.handle: replace(d, bases=bases)}):
                with self.assertRaises(ready.ProtocolError): self.audit()

    def test_detached_equal_state_base_does_not_authenticate_actual_role(self):
        d = candidate._ISSUED[self.handle]; fake = object.__new__(candidate._FutureBase)
        fake.state = d.bases[0].state.clone()
        with patch.dict(candidate._ISSUED, {self.handle: replace(d, bases=(fake, d.bases[1]))}):
            with self.assertRaisesRegex(ready.ProtocolError, "owner-issued"): self.audit()

    def test_base_alias_to_immediate_or_pre_refused(self):
        d = candidate._ISSUED[self.handle]; b = d.bases[0]; old = b.state
        md = maps._ISSUED[self.map_handle]; pd = pair._PAIRS[md.pair]
        for state in (pd.clones[0], md.post_clones[0], owned._ISSUED[self.source].pre_state, d.bases[1].state):
            try:
                b.state = state
                with self.assertRaises(ready.ProtocolError): self.audit()
            finally: b.state = old

    def test_future_base_content_mutation_refused_without_corrupting_original(self):
        d = candidate._ISSUED[self.handle]; state = d.bases[1].state
        self.assertNotIn(0, state.process_overrides)
        try:
            state.apply_transaction([Edit(PROCESS, 0, 1)])
            with self.assertRaisesRegex(ready.ProtocolError, "aliased/moved"): self.audit()
        finally: state.apply_transaction([Edit(PROCESS, 0, None)])
        self.assertEqual(maps.single_maps_audit(self.map_handle, self.diagnostic_run, self.source), self.before_maps)

    def test_simultaneous_healthy_base_state_swap_refused_by_initial_role_identity(self):
        d = candidate._ISSUED[self.handle]; a, b = d.bases; old_a, old_b = a.state, b.state
        self.assertEqual(fingerprint(old_a), fingerprint(old_b))
        try:
            a.state, b.state = old_b, old_a
            with self.assertRaisesRegex(ready.ProtocolError, "initial state identity"): self.audit()
        finally: a.state, b.state = old_a, old_b

    def test_equal_detached_clone_cannot_replace_issued_wrapper_state(self):
        d = candidate._ISSUED[self.handle]; base = d.bases[0]; old = base.state
        try:
            base.state = old.clone()
            self.assertEqual(fingerprint(base.state), fingerprint(old))
            with self.assertRaisesRegex(ready.ProtocolError, "initial state identity"): self.audit()
        finally: base.state = old

    def test_fixture_does_not_shadow_TestCase_run_entry(self):
        self.assertNotIn("run", type(self).__dict__)
        self.assertTrue(callable(self.run))

    def test_one_shared_template_cannot_be_replaced_by_equal_object_per_arm(self):
        d = candidate._ISSUED[self.handle]; equal = replace(d.template)
        with patch.dict(candidate._ISSUED, {self.handle: replace(d, role_templates=(d.template, equal))}):
            with self.assertRaisesRegex(ready.ProtocolError, "ONE"): self.audit()
        with patch.dict(candidate._ISSUED, {self.handle: replace(d, template=equal, role_templates=(equal, equal))}):
            with self.assertRaisesRegex(ready.ProtocolError, "owner-issued"): self.audit()

    def test_template_constant_axis_reference_and_numeric_alias_changes_refused(self):
        t = candidate._ISSUED[self.handle].template
        cases = (("alpha", .5), ("epsilon", .1), ("t_max", 465.),
                 ("grid", tuple(range(465))), ("grid", tuple(range(0, 466, 5))),
                 ("grid", (False,) + t.grid[1:]), ("grid", list(t.grid)),
                 ("v_pre", candidate._PARENT["lock"]["v_pre"]), ("v_pre", float("nan")))
        for field, value in cases:
            old = getattr(t, field)
            try:
                object.__setattr__(t, field, value)
                with self.assertRaises(ready.ProtocolError): self.audit()
            finally: object.__setattr__(t, field, old)

    def test_wrong_bank_order_prefix_and_scene_numeric_alias_refused(self):
        t = candidate._ISSUED[self.handle].template; old = t.evaluation_sample
        alias = object.__new__(EvaluationScene)
        for field in ("kappa", "phase", "error_flag", "cause_rank", "base_option"):
            object.__setattr__(alias, field, getattr(old[0], field))
        object.__setattr__(alias, "kappa", float(old[0].kappa))
        for sample in (old[:-1], tuple(reversed(old)), (alias,) + old[1:], list(old)):
            try:
                object.__setattr__(t, "evaluation_sample", sample)
                with self.assertRaises(ready.ProtocolError): self.audit()
            finally: object.__setattr__(t, "evaluation_sample", old)

    def test_underlying_raw_map_tamper_invalidates_future_before_export(self):
        md = maps._ISSUED[self.map_handle]
        with patch.dict(maps._ISSUED, {self.map_handle: replace(md, raw_sha="0" * 64)}):
            with self.assertRaises(ready.ProtocolError): self.audit()
            with self.assertRaises(ready.ProtocolError): candidate.clone_future_start(self.handle, self.diagnostic_run, self.source, role="reference")

    def test_seals_and_reference_or_code_drift_refused(self):
        d = candidate._ISSUED[self.handle]
        for bad in (replace(d, maps_sha="0" * 64), replace(d, payload_sha="0" * 64)):
            with patch.dict(candidate._ISSUED, {self.handle: bad}):
                with self.assertRaises(ready.ProtocolError): self.audit()
        with patch.dict(candidate._REFERENCE, {"v_pre": .5}):
            with self.assertRaises(ready.ProtocolError): self.audit()
        with patch.object(candidate, "_CODE_BINDING", ()):
            with self.assertRaises(ready.ProtocolError): self.audit()

    def test_success_skip_no_arm_template_clone_seed_or_record(self):
        source = self.fixture.source(LearnerPersistentState(), regime="T", scene=EvaluationScene(0, 0, 0, 0, 0))
        run = diagnostic.run_owned_diagnostic(source, method_id="TrajectoryCredit")
        mh = maps.run_owned_single_maps(run, source, object())
        with patch.object(candidate, "prefix", side_effect=AssertionError("skip template")), \
             patch.object(pair, "clone_immediate_post", side_effect=AssertionError("skip clone")):
            h = candidate.prepare_owned_future_inputs(mh, run, source)
            a = candidate.future_inputs_audit(h, run, source)
        self.assertIsNone(a["complete_input_payload"]["template"])
        self.assertEqual(a["independent_future_start_bases"], 0)
        with self.assertRaises(ready.ProtocolError): candidate.clone_future_start(h, run, source, role="reference")

    def test_empty_credit_projection_has_no_zero_filled_future(self):
        run = diagnostic.run_owned_diagnostic(self.source, method_id="AbstainCreditCandidate")
        mh = maps.run_owned_single_maps(run, self.source, fixture_module.SingleMapTests.arms)
        h = candidate.prepare_owned_future_inputs(mh, run, self.source)
        a = candidate.future_inputs_audit(h, run, self.source)
        self.assertEqual(a["shared_template_object_count"], 0)
        self.assertEqual(a["complete_input_payload"]["ordered_future_bases"], [])
        with self.assertRaises(ready.ProtocolError): candidate.clone_future_start(h, run, self.source, role="treatment")

    def test_preparation_error_issues_no_partial_handle_or_retry(self):
        before = len(candidate._ISSUED); calls = []
        def fail(*args, **kw): calls.append(kw["role"]); raise ready.ProtocolError("clone error")
        with patch.object(pair, "clone_immediate_post", side_effect=fail):
            with self.assertRaisesRegex(ready.ProtocolError, "clone error"):
                candidate.prepare_owned_future_inputs(self.map_handle, self.diagnostic_run, self.source)
        self.assertEqual(calls, ["reference"]); self.assertEqual(len(candidate._ISSUED), before)

    def test_explicit_role_and_no_record_workload_or_collection_claims(self):
        for role in (0, None, "Reference", "unknown"):
            with self.assertRaises(ready.ProtocolError): candidate.clone_future_start(self.handle, self.diagnostic_run, self.source, role=role)
        a = self.audit()
        for key in ("native_future_protocol_or_curve_or_paired_record_created", "actual_keyed_curve_origin_authenticated",
            "full_dense_B2_workload_resources_certified", "population_seed_registry_and_collection_gate_authenticated",
            "collection_authorized", "scientific_claim_authorized", "research_complete"):
            self.assertIs(a[key], False)


if __name__ == "__main__": unittest.main()
