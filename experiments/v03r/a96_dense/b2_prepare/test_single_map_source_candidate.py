"""Complete-singleton actual raw-map lineage, seedless engineering only."""
from dataclasses import replace
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import single_map_source_candidate as candidate
import test_diagnostic_source_candidate as fixture_module
import diagnostic_source_candidate as diagnostic
import counterfactual_source_candidate as owned
import native_record_candidate as bridge
import pair_source_candidate as pair
import pre_census_source_candidate as census
import readiness as ready
from rfl_rebuild.b1.contract import EVALUABLE_NOOP, fingerprint
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.runner import PairedRunner
from rfl_rebuild.b2.training import ExogenousEpisode
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.store import CONTROLLER, PROCESS, Q, QAddress, Edit, LearnerPersistentState


class SingleMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.DiagnosticSourceTests.setUpClass(); cls.fixture = fixture_module.DiagnosticSourceTests()
        cls.source = cls.fixture.transient()
        cls.diagnostic_run = diagnostic.run_owned_diagnostic(cls.source,
            method_id="ObservedExecutionCreditCandidate")
        cls.arms = bridge.registered_pair("X", Tier.L0_FACTUAL, "X_id")
        cls.before = fingerprint(owned._ISSUED[cls.source].pre_state)
        cls.events = []; cls.map_states = []; cls.regions = []
        actual_apply = PairedRunner._apply
        actual_map = candidate.maps.measure_scene_map
        actual_census = candidate.native.pre_update_traces
        def pretraces(**kw):
            cls.events.append("census"); return actual_census(**kw)
        def measure(state, units, **kw):
            cls.events.append("map"); cls.map_states.append(state); cls.regions.append(units)
            return actual_map(state, units, **kw)
        def apply(*args, **kw):
            cls.events.append("B1"); return actual_apply(*args, **kw)
        with patch.object(candidate.native, "pre_update_traces", side_effect=pretraces), \
             patch.object(candidate.maps, "measure_scene_map", side_effect=measure), \
             patch.object(PairedRunner, "_apply", side_effect=apply), \
             patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("science key")):
            cls.handle = candidate.run_owned_single_maps(cls.diagnostic_run, cls.source, cls.arms)

    def audit(self): return candidate.single_maps_audit(self.handle, self.diagnostic_run, self.source)

    def test_closed_API_no_old_pair_census_map_state_seed_or_callback(self):
        self.assertEqual(tuple(inspect.signature(candidate.run_owned_single_maps).parameters), ("run", "source", "arms"))
        with self.assertRaises(TypeError): candidate.run_owned_single_maps(self.diagnostic_run, self.source, self.arms, pair=self.handle)

    def test_real_runtime_order_one_full_census_then_pre_then_two_B1_then_post(self):
        self.assertEqual(self.events, ["census", "map", "B1", "B1", "map", "map"])
        audit = self.audit()
        self.assertEqual(audit["native_U2_pre_rollouts"], 5760)
        self.assertEqual(audit["native_map_calls"], 3); self.assertEqual(audit["B1_arm_calls"], 2)
        self.assertIs(self.map_states[0], owned._ISSUED[self.source].pre_state)
        self.assertIsNot(self.map_states[1], self.map_states[2])
        self.assertTrue(all(r is self.regions[0] for r in self.regions))
        self.assertIs(audit["actual_owned_pre_before_unique_B1_order_in_process"], True)
        self.assertEqual(tuple(row[0] for row in audit["runtime_content_chain"]), candidate._STAGES)
        print("SEEDLESS_SINGLETON_RAW_MAP_SUMMARY=" + json.dumps({
            "native_U2_pre_rollouts": 5760, "map_calls": 3, "B1_arm_calls": 2,
            "unaffected_size": audit["unaffected_size"], "full_credit_singleton_no_residual": True,
            "actual_component_pre_before_B1": True, "environment_seed_draws": 0,
            "future_training_episodes": 0, "collection_authorized": False}, sort_keys=True))

    def test_original_eligible_all_full_H_pre_Consult_shared_region(self):
        d = candidate._ISSUED[self.handle]; cd = census._ISSUED[d.census]
        self.assertEqual(d.unaffected.units, tuple(s for s, h, f, ts, rs in cd.census if h and not f[0]))
        self.assertEqual(d.unaffected.construction, f"E1(c={d.site.render()})@eligible_all")
        self.assertEqual(cd.production_payload[2], (True,))
        self.assertEqual(cd.cell_payload["residual_predictions"], [])
        self.assertEqual(len(cd.census), 5760)

    def test_actual_NoWrite_elementwise_not_mean_only_and_exact_native_formula(self):
        d = candidate._ISSUED[self.handle]
        self.assertEqual(tuple(v.hex() for v in d.raw.values_pre), tuple(v.hex() for v in d.raw.values_post[0][1]))
        self.assertTrue(all(r.status == EVALUABLE_NOOP for r in d.raw.ledgers[0][1].receipts))
        a = self.audit()
        for i, arm in enumerate(self.arms):
            expected = sum(d.raw.values_pre) / d.unaffected.size - sum(d.raw.values_post[i][1]) / d.unaffected.size
            self.assertEqual(a["collateral_hex"][arm.name], expected.hex())
        self.assertEqual(fingerprint(owned._ISSUED[self.source].pre_state), self.before)

    def test_persistent_single_X_state_edits_keep_original_production_semantics(self):
        # Non-science multi-defect engineering fixture, not population selection.
        # PROCESS0->1 keeps rush0 U2 legality; later START Q-WAIT values make
        # actual TIMEOUT after the sole t0 X deviation instead of assuming that
        # one delay implies failure under an otherwise optimal healthy Q*.
        state = LearnerPersistentState(); start = K.State(*K.START, 0, 0, 0)
        edits = [Edit(PROCESS, 0, 1), Edit(CONTROLLER, K.ControllerSite(start, K.RIGHT), K.WAIT)]
        for t in range(1, K.HORIZON):
            s = K.State(*K.START, t, 0, 0)
            edits.append(Edit(Q, QAddress(s, 1, 0, K.WAIT), max(self.fixture.q.row(s, 1, 0).values()) + 1.))
        state.apply_transaction(edits, q_reference=self.fixture.q)
        source = self.fixture.source(state)
        self.assertEqual(owned._ISSUED[source].episode.factual_trace.outcome, K.Outcome.TIMEOUT)
        run = diagnostic.run_owned_diagnostic(source, method_id="ObservedExecutionCreditCandidate")
        self.assertEqual(len(diagnostic.diagnostic_credit(run, source).expanded_units), 1)
        before = fingerprint(state)
        handle = candidate.run_owned_single_maps(run, source, self.arms)
        d = candidate._ISSUED[handle]; pd = pair._PAIRS[d.pair]
        self.assertEqual(len(pd.cell.addresses), 1); self.assertEqual(pd.cell_payload["residual_predictions"], [])
        self.assertNotEqual(fingerprint(pd.clones[1]), before)
        self.assertEqual(dict(pd.clones[1].process_overrides), {0: 1})
        self.assertEqual(dict(pd.clones[1].controller_overrides), {})
        self.assertEqual(dict(pd.clones[1].q_overrides), dict(state.q_overrides))
        self.assertEqual(fingerprint(state), before)
        self.assertIs(candidate.single_maps_audit(handle, run, source)["collection_authorized"], False)
        with patch.dict(candidate._ISSUED, {handle: replace(d, post_clones=tuple(reversed(d.post_clones)))}):
            with self.assertRaises(ready.ProtocolError): candidate.single_maps_audit(handle, run, source)

    def test_plant_same_visible_rows_not_truth_best_selection_or_accuracy_claim(self):
        source = self.fixture.transient(plant=True)
        run = diagnostic.run_owned_diagnostic(source, method_id="ObservedExecutionCreditCandidate")
        self.assertEqual(diagnostic.diagnostic_credit(run, source).expanded_units,
            diagnostic.diagnostic_credit(self.diagnostic_run, self.source).expanded_units)
        # Full execution on original healthy W still yields an evaluable X noop;
        # factual plant truth cannot replace ordinary X diagnosis or pick a c.
        handle = candidate.run_owned_single_maps(run, source, self.arms)
        pd = pair._PAIRS[candidate._ISSUED[handle].pair]
        self.assertEqual(pd.results[1].ledger.receipts[0].status, EVALUABLE_NOOP)
        self.assertEqual(candidate.single_maps_audit(handle, run, source)["credited_site"], self.audit()["credited_site"])

    def test_later_audit_never_repeats_rollout_diagnosis_B1_or_map(self):
        with patch.object(candidate.native, "pre_update_traces", side_effect=AssertionError("repeat census")), \
             patch.object(candidate.maps, "measure_scene_map", side_effect=AssertionError("repeat map")), \
             patch.object(diagnostic, "run_owned_diagnostic", side_effect=AssertionError("repeat diagnosis")), \
             patch.object(PairedRunner, "_apply", side_effect=AssertionError("repeat B1")):
            self.audit()

    def test_constructor_forged_audit_hash_pair_census_cannot_transfer_origin(self):
        with self.assertRaises(ready.ProtocolError): candidate.OwnedSingleMaps()
        d = candidate._ISSUED[self.handle]
        for fake in (None, {}, object.__new__(candidate.OwnedSingleMaps), self.audit(), d.raw_sha, d.pair, d.census):
            with self.assertRaises(ready.ProtocolError): candidate.single_maps_audit(fake, self.diagnostic_run, self.source)

    def test_equal_source_or_new_actual_diagnostic_call_refused(self):
        source = self.fixture.transient()
        with self.assertRaises(ready.ProtocolError): candidate.single_maps_audit(self.handle, self.diagnostic_run, source)
        run = diagnostic.run_owned_diagnostic(self.source, method_id="ObservedExecutionCreditCandidate")
        with self.assertRaises(ready.ProtocolError): candidate.single_maps_audit(self.handle, run, self.source)

    def test_multi_credit_or_cross_architecture_residual_refused_before_census_maps_B1(self):
        source = self.fixture.source()
        run = diagnostic.run_owned_diagnostic(source, method_id="TrajectoryCredit")
        with patch.object(candidate.native, "pre_update_traces", side_effect=AssertionError("truncated U2")), \
             patch.object(PairedRunner, "_apply", side_effect=AssertionError("truncated B1")):
            with self.assertRaisesRegex(ready.ProtocolError, "complete singleton"):
                candidate.run_owned_single_maps(run, source, bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite"))

    def test_nonempty_P_original_assistance_refusal_before_U2_or_B1(self):
        source = self.fixture.source(); run = diagnostic.run_owned_diagnostic(source, method_id="TrajectoryCredit")
        for tier, law in ((Tier.L1_CORRECTIVE, "P_id"), (Tier.L3_ORACLE, "LocalOracleRestore")):
            with patch.object(candidate.native, "pre_update_traces", side_effect=AssertionError("P hidden help")), \
                 patch.object(PairedRunner, "_apply", side_effect=AssertionError("P hidden help")):
                with self.assertRaisesRegex(ready.ProtocolError, "P requires explicit nominal assisted input"):
                    candidate.run_owned_single_maps(run, source, bridge.registered_pair("P", tier, law))

    def test_success_skips_before_arm_census_or_pair_read_no_scientific_zero(self):
        source = self.fixture.source(LearnerPersistentState(), regime="T", scene=EvaluationScene(0, 0, 0, 0, 0))
        run = diagnostic.run_owned_diagnostic(source, method_id="TrajectoryCredit")
        with patch.object(bridge, "validate_pair", side_effect=AssertionError("success arm")), \
             patch.object(candidate.native, "pre_update_traces", side_effect=AssertionError("success U2")), \
             patch.object(pair, "run_owned_b1_pair", side_effect=AssertionError("success pair")):
            handle = candidate.run_owned_single_maps(run, source, object())
            audit = candidate.single_maps_audit(handle, run, source)
        self.assertEqual(audit["B1_arm_calls"], 0); self.assertIsNone(audit["collateral_hex"])
        self.assertIsNone(audit["raw_input_sha256"]); self.assertEqual(audit["runtime_content_chain"], [])

    def test_empty_projection_no_fake_zero_pair_census_or_maps(self):
        run = diagnostic.run_owned_diagnostic(self.source, method_id="AbstainCreditCandidate")
        with patch.object(candidate.native, "pre_update_traces", side_effect=AssertionError("empty U2")), \
             patch.object(pair, "run_owned_b1_pair", side_effect=AssertionError("empty B1")):
            handle = candidate.run_owned_single_maps(run, self.source, self.arms)
            audit = candidate.single_maps_audit(handle, run, self.source)
        self.assertIsNone(audit["collateral_hex"]); self.assertEqual(audit["native_map_calls"], 0)

    def test_invalid_or_reversed_pair_refused_before_U2(self):
        with patch.object(candidate.native, "pre_update_traces", side_effect=AssertionError("bad pair U2")):
            with self.assertRaises(ready.ProtocolError): candidate.run_owned_single_maps(self.diagnostic_run, self.source, tuple(reversed(self.arms)))

    def test_audit_detached_copy_cannot_change_pinned_raw_content(self):
        audit = self.audit(); before = audit["raw_input_sha256"]
        audit["complete_raw_input"]["pre_values_hex"].clear(); audit["runtime_content_chain"].clear()
        self.assertEqual(self.audit()["raw_input_sha256"], before)

    def test_map_prefix_order_int_bool_nan_and_scene_alias_refused(self):
        d = candidate._ISSUED[self.handle]; original = d.pre_map; first = next(iter(original))
        bad = dict(original); bad.pop(first)
        cases = [bad, dict(reversed(tuple(original.items())))]
        for value in (1, True, float("nan")):
            changed = dict(original); changed[first] = value; cases.append(changed)
        alias = object.__new__(EvaluationScene)
        for field in EvaluationScene.__slots__:
            object.__setattr__(alias, field, float(first.kappa) if field == "kappa" else getattr(first, field))
        cases.append({alias if s == first else s: v for s, v in original.items()})
        for mapping in cases:
            with patch.dict(candidate._ISSUED, {self.handle: replace(d, pre_map=mapping)}):
                with self.assertRaises(ready.ProtocolError): self.audit()

    def test_NoWrite_mean_preserving_map_change_refused_elementwise(self):
        d = candidate._ISSUED[self.handle]; changed = dict(d.post_maps[0]); units = d.unaffected.units
        changed[units[0]] += .25; changed[units[1]] -= .25
        raw_values = tuple(changed[s] for s in units)
        raw = replace(d.raw, values_post=((self.arms[0].name, raw_values), d.raw.values_post[1]))
        with patch.dict(candidate._ISSUED, {self.handle: replace(d, raw=raw, post_maps=(changed, d.post_maps[1]))}):
            with self.assertRaisesRegex(ready.ProtocolError, "elementwise"): self.audit()

    def test_float_bits_and_signed_zero_payload_seals_not_numeric_equality(self):
        d = candidate._ISSUED[self.handle]; original = d.pre_map
        data = owned._ISSUED[self.source]
        positive = candidate._pre_payload(d.site, d.unaffected, (0.,), data)
        negative = candidate._pre_payload(d.site, d.unaffected, (-0.,), data)
        self.assertNotEqual(bridge.sha(positive), bridge.sha(negative))
        scene = next((s for s, v in original.items() if v == 0.), None)
        if scene is None:
            # Controlled stored map fixture: set a finite nonzero bit instead;
            # no science material, no skipped test or map remeasurement.
            scene = next(iter(original)); value = original[scene] + .00001
        else: value = -original[scene]
        mapping = dict(original); mapping[scene] = value
        with patch.dict(candidate._ISSUED, {self.handle: replace(d, pre_map=mapping)}):
            with self.assertRaises(ready.ProtocolError): self.audit()

    def test_maps_or_post_clones_cannot_alias(self):
        d = candidate._ISSUED[self.handle]
        for changed in (replace(d, post_maps=(d.pre_map, d.post_maps[1])),
            replace(d, post_clones=(d.post_clones[0], d.post_clones[0])),
            replace(d, post_clones=(owned._ISSUED[self.source].pre_state, d.post_clones[1]))):
            with patch.dict(candidate._ISSUED, {self.handle: changed}):
                with self.assertRaises(ready.ProtocolError): self.audit()

    def test_post_export_state_mutation_refused(self):
        d = candidate._ISSUED[self.handle]; clone = d.post_clones[1].clone()
        clone.apply_transaction([Edit(PROCESS, 0, 1)])
        with patch.dict(candidate._ISSUED, {self.handle: replace(d, post_clones=(d.post_clones[0], clone))}):
            with self.assertRaises(ready.ProtocolError): self.audit()

    def test_full_native_ledger_identity_cannot_be_detached_or_replaced(self):
        d = candidate._ISSUED[self.handle]
        raw = replace(d.raw, ledgers=((self.arms[0].name, replace(d.raw.ledgers[0][1])), d.raw.ledgers[1]))
        with patch.dict(candidate._ISSUED, {self.handle: replace(d, raw=raw)}):
            with self.assertRaisesRegex(ready.ProtocolError, "identity"): self.audit()

    def test_raw_prefix_and_content_chain_reordering_refused(self):
        d = candidate._ISSUED[self.handle]
        for bad in (replace(d, raw=replace(d.raw, pre_census=d.raw.pre_census[:-1])),
                    replace(d, sequence=d.sequence[:-1]), replace(d, sequence=tuple(reversed(d.sequence))),
                    replace(d, raw_sha="0" * 64)):
            with patch.dict(candidate._ISSUED, {self.handle: bad}):
                with self.assertRaises(ready.ProtocolError): self.audit()

    def test_native_pre_map_failure_issues_no_handle_and_never_calls_B1(self):
        before = len(candidate._ISSUED)
        with patch.object(candidate.maps, "measure_scene_map", side_effect=ready.ProtocolError("pre map error")), \
             patch.object(pair, "run_owned_b1_pair", side_effect=AssertionError("after failed pre map")):
            with self.assertRaisesRegex(ready.ProtocolError, "pre map error"):
                candidate.run_owned_single_maps(self.diagnostic_run, self.source, self.arms)
        self.assertEqual(len(candidate._ISSUED), before)

    def test_production_exclusion_is_not_filtered_to_partial_pass(self):
        before = len(candidate._ISSUED); actual = candidate.native.credited_domain
        site = candidate._ISSUED[self.handle].site
        def reduced(channel, traces):
            return tuple(c for c in actual(channel, traces) if c != site)
        with patch.object(candidate.native, "credited_domain", side_effect=reduced), \
             patch.object(pair, "run_owned_b1_pair", side_effect=AssertionError("production exclusion B1")):
            with self.assertRaisesRegex(ready.ProtocolError, "production singleton"):
                candidate.run_owned_single_maps(self.diagnostic_run, self.source, self.arms)
        self.assertEqual(len(candidate._ISSUED), before)

    def test_empty_region_refusal_no_zero_collateral_and_no_B1(self):
        before = len(candidate._ISSUED)
        with patch.object(candidate.native, "build_unaffected", side_effect=ready.ProtocolError("empty native region")), \
             patch.object(pair, "run_owned_b1_pair", side_effect=AssertionError("empty region B1")):
            with self.assertRaisesRegex(ready.ProtocolError, "empty native region"):
                candidate.run_owned_single_maps(self.diagnostic_run, self.source, self.arms)
        self.assertEqual(len(candidate._ISSUED), before)

    def test_post_map_failure_issues_no_partial_maps_or_auto_retry(self):
        before = len(candidate._ISSUED); actual = candidate.maps.measure_scene_map; calls = []
        def measure(*args, **kw):
            calls.append(1)
            if len(calls) == 2: raise ready.ProtocolError("post map error")
            return actual(*args, **kw)
        with patch.object(candidate.maps, "measure_scene_map", side_effect=measure):
            with self.assertRaisesRegex(ready.ProtocolError, "post map error"):
                candidate.run_owned_single_maps(self.diagnostic_run, self.source, self.arms)
        self.assertEqual(len(calls), 2); self.assertEqual(len(candidate._ISSUED), before)
        self.assertEqual(fingerprint(owned._ISSUED[self.source].pre_state), self.before)

    def test_native_map_mutation_of_owned_learner_is_refused(self):
        # Local exported clone only; no mutation to an issued source fixture.
        d = candidate._ISSUED[self.handle]; state = d.post_clones[0].clone()
        def malicious(*args, **kw):
            state.apply_transaction([Edit(PROCESS, 0, 1)]); return dict(d.pre_map)
        with patch.object(candidate.maps, "measure_scene_map", side_effect=malicious):
            with self.assertRaisesRegex(ready.ProtocolError, "mutated"):
                candidate._measure(state, d.unaffected, owned._ISSUED[self.source].reference)

    def test_stored_native_census_change_invalidates_maps_without_new_rollouts(self):
        d = candidate._ISSUED[self.handle]; cd = census._ISSUED[d.census]
        changed = dict(cd.traces._rows); changed.pop(next(iter(changed)))
        with patch.object(cd.traces, "_rows", changed):
            with self.assertRaises(ready.ProtocolError): self.audit()

    def test_dependency_guard_and_no_science_portable_or_multi_credit_authority(self):
        with patch.object(candidate, "_CODE_BINDING", tuple("0" * 64 for _ in candidate._CODE_BINDING)):
            with self.assertRaises(ready.ProtocolError): self.audit()
        audit = self.audit()
        for key in ("supplied_pair_retroactive_order_authenticated", "multi_credit_region_or_residual_selection_defined",
            "portable_security_or_science_acquisition_origin_authenticated", "collection_authorized",
            "scientific_claim_authorized", "research_complete"):
            self.assertIs(audit[key], False)
        self.assertEqual(audit["future_training_episodes"], 0); self.assertEqual(audit["environment_seed_draws"], 0)


if __name__ == "__main__": unittest.main()
