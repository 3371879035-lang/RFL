"""Full native pre-census component tests; no science keys/future/B1."""
from dataclasses import replace
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pre_census_source_candidate as candidate
import test_diagnostic_source_candidate as fixture_module
import diagnostic_source_candidate as diagnostic
import counterfactual_source_candidate as owned
import native_record_candidate as bridge
import pair_source_candidate as pair
import readiness as ready
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.runner import PairedRunner
from rfl_rebuild.b2.training import ExogenousEpisode
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.store import CONTROLLER, PROCESS, Q, Edit, LearnerPersistentState, QAddress


class PreCensusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.DiagnosticSourceTests.setUpClass(); cls.fixture = fixture_module.DiagnosticSourceTests()
        cls.source = cls.fixture.source()
        cls.diagnostic_run = diagnostic.run_owned_diagnostic(cls.source, method_id="TrajectoryCredit")
        cls.arms = bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite")
        cls.before = fingerprint(owned._ISSUED[cls.source].pre_state)
        with patch.object(candidate.native, "learned_rollout", wraps=candidate.native.learned_rollout) as spy, \
             patch.object(PairedRunner, "_apply", side_effect=AssertionError("pre-census B1")), \
             patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("pre-census key")):
            cls.handle = candidate.prepare_owned_pre_census(cls.diagnostic_run, cls.source, cls.arms)
            cls.rollout_count = spy.call_count
            cls.rollout_state_identity = all(c.args[0] is owned._ISSUED[cls.source].pre_state for c in spy.call_args_list)

    def audit(self): return candidate.pre_census_audit(self.handle, self.diagnostic_run, self.source)

    def test_closed_api_no_supplied_traces_census_truth_state_domain_seed(self):
        self.assertEqual(tuple(inspect.signature(candidate.prepare_owned_pre_census).parameters), ("run", "source", "arms"))

    def test_full5760_native_rollouts_once_on_actual_source_no_B1(self):
        audit = self.audit()
        self.assertEqual(self.rollout_count, 5760); self.assertTrue(self.rollout_state_identity)
        self.assertEqual(audit["native_U2_pre_rollouts"], 5760)
        self.assertEqual(len(audit["full_ordered_census"]), 5760)
        self.assertEqual(audit["B1_arm_calls"], 0)
        self.assertEqual(fingerprint(owned._ISSUED[self.source].pre_state), self.before)
        print("SEEDLESS_OWNED_U2_PRE_CENSUS_SUMMARY=" + json.dumps({
            "native_U2_pre_rollouts": 5760, "credited_sites": len(audit["ordered_credited_sites"]),
            "all_projection_residuals_retained": True, "B1_arm_calls": 0,
            "environment_seed_draws": 0, "future_training_episodes": 0,
            "pre_before_B1_order_authenticated": False, "multi_credit_region_defined": False,
            "collection_authorized": False}, sort_keys=True))

    def test_complete_native_Consult_and_H_pre_not_post_or_truth(self):
        d = candidate._ISSUED[self.handle]
        for scene, healthy, flags, ts, rs in d.census:
            self.assertEqual(healthy, d.traces.trace(scene).outcome == K.Outcome.SUCCESS)
            self.assertEqual(flags, tuple(d.traces.consults(c, scene) for c in d.sites))
        self.assertEqual(tuple(s for s, *_ in d.census), candidate.native.scene_domain())
        self.assertEqual(len(d.sites), K.HORIZON)

    def test_whole_projection_and_nonwriteable_residuals_retained(self):
        audit = self.audit(); cell = audit["cell"]
        self.assertEqual(len(cell["cell_credited_units"]), K.HORIZON)
        self.assertEqual(len(cell["residual_predictions"]), K.HORIZON + 4)
        self.assertEqual(len(audit["production_membership"]), K.HORIZON)
        self.assertTrue(all(type(v) is bool for v in audit["production_membership"]))

    def test_actual_X_Consult_uses_command_not_controller_output(self):
        # Test-only process commitment prevents rush0 from reading a WAIT
        # controller baseline outside rush0's legal action set in full U2.
        state = LearnerPersistentState(); edits = [Edit(PROCESS, 0, 1)]
        for t in range(K.HORIZON):
            s = K.State(*K.START, t, 0, 0)
            edits += [Edit(CONTROLLER, K.ControllerSite(s, a), K.WAIT)
                for a in K.option_actions(1, K.ControlState(1, 0), s) if a != K.WAIT]
        state.apply_transaction(edits)
        source = self.fixture.source(state)
        run = diagnostic.run_owned_diagnostic(source, method_id="ObservedExecutionCreditCandidate")
        with patch.object(PairedRunner, "_apply", side_effect=AssertionError("X census B1")), \
             patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("X census key")):
            handle = candidate.prepare_owned_pre_census(run, source,
                bridge.registered_pair("X", Tier.L0_FACTUAL, "X_id"))
        d = candidate._ISSUED[handle]; deviations = 0
        for scene, healthy, flags, ts, rs in d.census:
            self.assertEqual(flags, tuple(d.traces.consults(c, scene) for c in d.sites))
            for pre, control, step in d.traces.walk(scene):
                if step.a_cmd != step.u:
                    deviations += 1
                    self.assertIn(candidate.native.CreditedSite("X", K.ControllerSite(pre, step.a_cmd)),
                        d.traces.consulted("X", scene))
        self.assertGreater(deviations, 0); self.assertEqual(len(d.census), 5760)

    def test_actual_P_Consult_uses_proposal_not_option_in_force(self):
        state = LearnerPersistentState(); edits = [Edit(PROCESS, 1, 2)]
        for t in range(K.HORIZON):
            s = K.State(*K.START, t, 0, 0)
            edits.append(Edit(Q, QAddress(s, 2, 0, K.WAIT),
                max(self.fixture.q.row(s, 2, 0).values()) + 1.))
        state.apply_transaction(edits, q_reference=self.fixture.q)
        source = self.fixture.source(state)
        run = diagnostic.run_owned_diagnostic(source, method_id="TrajectoryCredit")
        with patch.object(PairedRunner, "_apply", side_effect=AssertionError("P census B1")), \
             patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("P census key")):
            # Original native P semantics only; NOT an issued v10 P handle.
            # Owned diagnostic->P cell still refuses absent assisted input.
            data = owned._checked(source)
            traces = candidate.native.pre_update_traces(learner=data.pre_state, q_reference=data.reference)
            sites = candidate.native.credited_domain("P", traces)
            census, production = candidate._seal(traces, data, sites)
        for scene, healthy, flags, ts, rs in census:
            self.assertEqual(flags, tuple(scene.base_option == c.address for c in sites))
            if scene.base_option == 1:
                self.assertEqual(traces.trace(scene).option_in_force, 2)
                self.assertEqual(traces.walk(scene)[0][1], K.initial_control(2))
        self.assertEqual(len(census), 5760)
        self.assertEqual(production[2], (True,) * len(sites))

    def test_P_unassisted_owned_pipeline_refuses_before_U2_not_hidden_assistance(self):
        for tier, law in ((Tier.L1_CORRECTIVE, "P_id"), (Tier.L3_ORACLE, "LocalOracleRestore")):
            with patch.object(candidate.native, "pre_update_traces", side_effect=AssertionError("P hidden help")):
                with self.assertRaisesRegex(ready.ProtocolError, "P requires explicit nominal assisted input"):
                    candidate.prepare_owned_pre_census(self.diagnostic_run, self.source,
                        bridge.registered_pair("P", tier, law))

    def test_later_audit_never_repeats_rollout_diagnosis_or_B1(self):
        with patch.object(candidate.native, "learned_rollout", side_effect=AssertionError("repeat U2")), \
             patch.object(diagnostic, "run_owned_diagnostic", side_effect=AssertionError("repeat diagnosis")), \
             patch.object(PairedRunner, "_apply", side_effect=AssertionError("repeat B1")):
            self.audit()

    def test_nominal_or_detached_handles_cannot_transfer_origin(self):
        with self.assertRaises(ready.ProtocolError): candidate.OwnedPreCensus()
        for fake in (None, {}, object.__new__(candidate.OwnedPreCensus)):
            with self.assertRaises(ready.ProtocolError): candidate.pre_census_audit(fake, self.diagnostic_run, self.source)
        with self.assertRaises(ready.ProtocolError): candidate.pre_census_audit(self.audit(), self.diagnostic_run, self.source)

    def test_equal_source_or_new_actual_call_cannot_transfer_material(self):
        other = self.fixture.source()
        with self.assertRaises(ready.ProtocolError): candidate.pre_census_audit(self.handle, self.diagnostic_run, other)
        run = diagnostic.run_owned_diagnostic(self.source, method_id="TrajectoryCredit")
        with self.assertRaises(ready.ProtocolError): candidate.pre_census_audit(self.handle, run, self.source)

    def test_success_skips_before_arm_or_native_U2_reads(self):
        source = self.fixture.source(LearnerPersistentState(), regime="T", scene=EvaluationScene(0, 0, 0, 0, 0))
        run = diagnostic.run_owned_diagnostic(source, method_id="TrajectoryCredit")
        with patch.object(candidate.native, "pre_update_traces", side_effect=AssertionError("success U2")), \
             patch.object(bridge, "validate_pair", side_effect=AssertionError("success arm")):
            handle = candidate.prepare_owned_pre_census(run, source, object())
            audit = candidate.pre_census_audit(handle, run, source)
        self.assertEqual(audit["native_U2_pre_rollouts"], 0); self.assertIsNone(audit["census_sha256"])

    def test_empty_credit_has_no_zero_filled_census(self):
        run = diagnostic.run_owned_diagnostic(self.source, method_id="AbstainCreditCandidate")
        with patch.object(candidate.native, "pre_update_traces", side_effect=AssertionError("empty U2")):
            handle = candidate.prepare_owned_pre_census(run, self.source, self.arms)
            audit = candidate.pre_census_audit(handle, run, self.source)
        self.assertEqual(audit["full_ordered_census"], []); self.assertIsNone(audit["production_domain_size"])

    def test_native_failure_propagates_no_partial_material_or_source_edit(self):
        count = len(candidate._ISSUED)
        with patch.object(candidate.native, "pre_update_traces", side_effect=ready.ProtocolError("native U2 error")):
            with self.assertRaises(ready.ProtocolError): candidate.prepare_owned_pre_census(self.diagnostic_run, self.source, self.arms)
        self.assertEqual(len(candidate._ISSUED), count)
        self.assertEqual(fingerprint(owned._ISSUED[self.source].pre_state), self.before)

    def test_audit_copy_does_not_mutate_private_census(self):
        audit = self.audit(); digest = audit["census_sha256"]
        audit["full_ordered_census"].clear(); audit["ordered_credited_sites"].clear()
        self.assertEqual(self.audit()["census_sha256"], digest)

    def test_prefix_reorder_boolean_alias_and_missing_incidence_refused(self):
        original = candidate._ISSUED[self.handle]; rows = original.census; first = rows[0]
        badrows = (rows[:-1], tuple(reversed(rows)),
            ((first[0], 1, *first[2:]),) + rows[1:],
            ((first[0], first[1], (1,) + first[2][1:], *first[3:]),) + rows[1:],
            ((first[0], first[1], first[2][:-1], *first[3:]),) + rows[1:])
        for bad in badrows:
            with patch.dict(candidate._ISSUED, {self.handle: replace(original, census=bad)}):
                with self.assertRaises(ready.ProtocolError): self.audit()

    def test_native_trace_row_walk_or_domain_change_refused(self):
        d = candidate._ISSUED[self.handle]; first = candidate._DOMAIN[0]
        for attr in ("_traces", "_rows", "_walks"):
            changed = dict(getattr(d.traces, attr)); changed.pop(first)
            with patch.object(d.traces, attr, changed):
                with self.assertRaises(ready.ProtocolError): self.audit()
        changed = dict(d.traces._rows); row = changed[first][0]
        changed[first] = ((True,) + row[1:],) + changed[first][1:]
        with patch.object(d.traces, "_rows", changed):
            with self.assertRaises(ready.ProtocolError): self.audit()

    def test_walk_numeric_alias_or_cloned_step_identity_refused(self):
        d = candidate._ISSUED[self.handle]; first = candidate._DOMAIN[0]
        row = d.traces.walk(first)[0]; state = row[0]
        for bad in ((K.State(state.x, state.y, False, state.kappa, state.phi), row[1], row[2]),
                    (row[0], row[1], replace(row[2]))):
            changed = dict(d.traces._walks); changed[first] = (bad,) + changed[first][1:]
            with patch.object(d.traces, "_walks", changed):
                with self.assertRaises(ready.ProtocolError): self.audit()

    def test_scene_key_or_captured_scene_numeric_alias_refused(self):
        d = candidate._ISSUED[self.handle]; first = candidate._DOMAIN[0]
        for alias in (False, 0.0):
            bad = object.__new__(EvaluationScene)
            for field in EvaluationScene.__slots__:
                object.__setattr__(bad, field, alias if field == "kappa" else getattr(first, field))
            for attr in ("_traces", "_rows", "_walks"):
                original = getattr(d.traces, attr)
                changed = {bad if scene == first else scene: value for scene, value in original.items()}
                with patch.object(d.traces, attr, changed):
                    with self.assertRaises(ready.ProtocolError): self.audit()
            rows = ((bad,) + d.census[0][1:],) + d.census[1:]
            with patch.dict(candidate._ISSUED, {self.handle: replace(d, census=rows)}):
                with self.assertRaises(ready.ProtocolError): self.audit()

    def test_changed_native_trace_metadata_and_u_refused(self):
        d = candidate._ISSUED[self.handle]; first = candidate._DOMAIN[0]; trace = d.traces.trace(first)
        for bad in (replace(trace, control=K.ControlState(trace.control.z, 1)),
                    replace(trace, mask=K.FaultMask(plant=K.PlantFault(0, K.WAIT))),
                    replace(trace, steps=(replace(trace.steps[0], u=(trace.steps[0].u + 1) % len(K.ACTIONS)),)
                        + trace.steps[1:])):
            changed = dict(d.traces._traces); changed[first] = bad
            with patch.object(d.traces, "_traces", changed):
                with self.assertRaises(ready.ProtocolError): self.audit()

    def test_absent_production_membership_is_retained_not_filtered(self):
        # A controlled production-extent fixture only, NOT a new native PASS.
        d = candidate._ISSUED[self.handle]
        original = candidate.native.credited_domain("D_Q", d.traces)
        reduced = tuple(c for c in original if c != d.sites[0])
        with patch.object(candidate.native, "credited_domain", return_value=reduced):
            census, production = candidate._seal(d.traces, owned._ISSUED[self.source], d.sites)
        self.assertIs(production[2][0], False)
        self.assertEqual(len(production[2]), len(d.sites))
        self.assertEqual(census, d.census)

    def test_unknown_channel_cannot_enter_native_P_fallback(self):
        d = candidate._ISSUED[self.handle]
        bad = object.__new__(candidate.native.CreditedSite)
        object.__setattr__(bad, "channel", "UNKNOWN")
        object.__setattr__(bad, "address", 0)
        with patch.object(candidate.native, "credited_domain", side_effect=AssertionError("unknown entered native")):
            with self.assertRaises(ready.ProtocolError):
                candidate._seal(d.traces, owned._ISSUED[self.source], (bad,))

    def test_production_boolean_alias_or_changed_digest_refused(self):
        original = candidate._ISSUED[self.handle]; n, sha, flags = original.production_payload
        for bad in ((True, sha, flags), (n, "0" * 64, flags), (n, sha, (1,) + flags[1:])):
            with patch.dict(candidate._ISSUED, {self.handle: replace(original, production_payload=bad)}):
                with self.assertRaises(ready.ProtocolError): self.audit()

    def test_no_science_multi_region_or_actual_B1_order_authority(self):
        audit = self.audit()
        for key in ("pre_before_B1_execution_order_authenticated", "multi_credit_unaffected_region_defined",
            "primary_Collateral_scalar_defined", "scientific_admissibility_or_F1_threshold_claimed",
            "collection_authorized", "scientific_claim_authorized", "research_complete"):
            self.assertIs(audit[key], False)

    def test_dependency_byte_guard_and_unregistered_arm_refused(self):
        with patch.object(candidate, "_CODE_BINDING", tuple("0" * 64 for _ in candidate._CODE_BINDING)):
            with self.assertRaises(ready.ProtocolError): self.audit()
        with patch.object(candidate.native, "pre_update_traces", side_effect=AssertionError("bad arm U2")):
            with self.assertRaises(ready.ProtocolError): candidate.prepare_owned_pre_census(self.diagnostic_run, self.source, tuple(reversed(self.arms)))


if __name__ == "__main__": unittest.main()
