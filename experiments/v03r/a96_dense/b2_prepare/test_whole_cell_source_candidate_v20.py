"""Seedless whole D_Q raw diagnostics, not scientist samples or efficacy tests."""
from dataclasses import replace
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import whole_cell_source_candidate_v20 as candidate
import test_diagnostic_source_candidate as fixtures
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
from rfl_rebuild.learner.store import LearnerPersistentState


class WholeCellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.DiagnosticSourceTests.setUpClass()
        cls.fixture = fixtures.DiagnosticSourceTests()
        cls.source = cls.fixture.source()
        cls.diagnostic_run = diagnostic.run_owned_diagnostic(cls.source, method_id="TrajectoryCredit")
        cls.arms = bridge.registered_pair("D_Q", Tier.L0_FACTUAL, "FactualReturnWrite")
        cls.before = fingerprint(owned._ISSUED[cls.source].pre_state)
        cls.events = []; cls.measure_inputs = []; cls.apply_inputs = []
        original_map = candidate.native_maps.measure_scene_map
        original_census = census.native.pre_update_traces
        original_apply = PairedRunner._apply
        def trace(**kw):
            cls.events.append("census"); return original_census(**kw)
        def measure(state, units, **kw):
            cls.events.append("map"); cls.measure_inputs.append((state, units))
            return original_map(state, units, **kw)
        def apply(*args, **kw):
            cls.events.append("B1"); cls.apply_inputs.append(args)
            return original_apply(*args, **kw)
        with patch.object(census.native, "pre_update_traces", side_effect=trace), \
             patch.object(candidate.native_maps, "measure_scene_map", side_effect=measure), \
             patch.object(PairedRunner, "_apply", side_effect=apply), \
             patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("science key")), \
             patch("rfl_rebuild.b2.runner.train_curve", side_effect=AssertionError("future training")):
            cls.handle = candidate.run_owned_whole_cell_maps(cls.diagnostic_run, cls.source, cls.arms)

    def audit(self): return candidate.whole_cell_maps_audit(self.handle, self.diagnostic_run, self.source)

    def data(self): return candidate._ISSUED[self.handle]

    def reject(self, changed, message=None):
        with patch.dict(candidate._ISSUED, {self.handle: changed}):
            if message:
                with self.assertRaisesRegex(ready.ProtocolError, message): self.audit()
            else:
                with self.assertRaises(ready.ProtocolError): self.audit()

    def test_closed_API_no_key_callback_preexisting_pair_map_or_selection(self):
        self.assertEqual(tuple(inspect.signature(candidate.run_owned_whole_cell_maps).parameters),
                         ("run", "source", "arms"))
        with self.assertRaises(TypeError):
            candidate.run_owned_whole_cell_maps(self.diagnostic_run, self.source, self.arms, selection=(0,))

    def test_whole_actual_trajectory_credit_12_DQ_and_16_residuals_retained(self):
        d = self.data(); p = self.audit()["complete_payload"]
        self.assertEqual(len(d.sites), 12)
        self.assertEqual(len(d.cell_payload["residual_predictions"]), 16)
        self.assertEqual(p["whole_cell_with_all_residuals"], d.cell_payload)
        self.assertEqual(tuple(site.address for site in d.sites), pair._PAIRS[d.pair].cell.addresses)
        self.assertEqual(d.cell_payload, pair._PAIRS[d.pair].cell_payload)

    def test_real_runtime_all_pre_maps_before_unique_whole_pair_then_all_post(self):
        self.assertEqual(self.events, ["census"] + ["map"] * 12 + ["B1"] * 2 + ["map"] * 24)
        a = self.audit()
        self.assertEqual(a["native_U2_pre_rollouts"], 5760)
        self.assertEqual(a["native_scene_map_calls"], 36)
        self.assertEqual(a["native_B1_arm_calls"], 2)
        self.assertEqual(tuple(row[0] for row in a["runtime_content_chain"]), candidate._STAGES)
        self.assertTrue(a["owner_pre_before_one_whole_B1_order_in_process"])

    def test_one_original_region_object_per_site_shared_by_all_three_actual_measurements(self):
        d = self.data()
        for i in range(12):
            self.assertIs(self.measure_inputs[i][0], owned._ISSUED[self.source].pre_state)
            for offset in (0, 12, 24):
                self.assertIs(self.measure_inputs[offset + i][1], d.regions[i].units)
        self.assertIsNot(self.measure_inputs[12][0], self.measure_inputs[24][0])
        self.assertEqual(len({id(m) for m in d.pre_maps + d.post_maps[0] + d.post_maps[1]}), 36)

    def test_full_native_5760_census_and_every_E1_original_H_pre_not_Consult(self):
        d = self.data(); cd = census._ISSUED[d.census]
        self.assertEqual(len(cd.census), 5760)
        self.assertEqual(cd.production_payload[2], (True,) * 12)
        for i, region in enumerate(d.regions):
            self.assertEqual(region.units, tuple(s for s, h, f, ts, rs in cd.census if h and not f[i]))
            self.assertEqual(region.construction, f"E1(c={d.sites[i].render()})@eligible_all")

    def test_ledger_whole_not_fake_singleton_native_scalar_accounting_preserved(self):
        d = self.data(); pd = pair._PAIRS[d.pair]
        self.assertEqual(len(self.apply_inputs), 2)
        self.assertIs(self.apply_inputs[0][2], self.apply_inputs[1][2])
        self.assertIsNot(self.apply_inputs[0][1], self.apply_inputs[1][1])
        for result in pd.results:
            self.assertEqual(len(result.ledger.receipts), 12)
            self.assertEqual(result.ledger.n_addressed, 12)
        self.assertEqual(pd.results[1].ledger.n_scalar, 12)
        self.assertGreater(pd.results[1].ledger.sum_abs_delta, 0.)
        self.assertEqual(self.audit()["complete_payload"]["whole_native_pair"], pair.pair_audit(d.pair, self.diagnostic_run, self.source))

    def test_no_write_elementwise_float_bits_and_original_ordered_sum_formula(self):
        d = self.data(); p = self.audit()["complete_payload"]; pd = pair._PAIRS[d.pair]
        self.assertTrue(all(r.status == EVALUABLE_NOOP for r in pd.results[0].ledger.receipts))
        for i, region in enumerate(d.regions):
            pre = tuple(d.pre_maps[i][s] for s in region.units)
            ref = tuple(d.post_maps[0][i][s] for s in region.units)
            self.assertEqual(tuple(v.hex() for v in pre), tuple(v.hex() for v in ref))
            for role in range(2):
                expected = sum(pre) / region.size - sum(d.post_maps[role][i][s] for s in region.units) / region.size
                self.assertEqual(p["per_site_diagnostics_after_same_whole_update"][i]["ordered_native_raw_difference_hex"][role],
                                 expected.hex())
        self.assertEqual(fingerprint(owned._ISSUED[self.source].pre_state), self.before)

    def test_cross_credit_consult_counts_are_full_pre_material_not_new_unaffected_union(self):
        d = self.data(); cd = census._ISSUED[d.census]; p = self.audit()["complete_payload"]
        for i, region in enumerate(d.regions):
            eligible = set(region.units)
            expected = [sum(int(f[j]) for s, h, f, ts, rs in cd.census if s in eligible) for j in range(12)]
            row = p["per_site_diagnostics_after_same_whole_update"][i]
            self.assertEqual(row["ordered_other_credit_consult_counts"], expected)
            self.assertEqual(expected[i], 0)
            self.assertIs(row["unaffected_by_whole_set_claimed"], False)
            self.assertIs(row["single_credit_counterfactual_effect"], False)
        self.assertIsNone(p["multi_credit_region"]); self.assertIsNone(p["primary_Collateral_scalar"])
        self.assertIsNone(p["per_site_to_primary_aggregation"])

    def test_audit_repeats_no_rollout_map_B1_diagnosis_or_key_draw(self):
        with patch.object(census.native, "pre_update_traces", side_effect=AssertionError("repeated U2")), \
             patch.object(candidate.native_maps, "measure_scene_map", side_effect=AssertionError("repeated map")), \
             patch.object(PairedRunner, "_apply", side_effect=AssertionError("repeated B1")), \
             patch.object(diagnostic, "run_owned_diagnostic", side_effect=AssertionError("repeated diagnosis")), \
             patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("key")):
            self.audit()

    def test_detached_copy_not_capability_or_pinned_payload_mutation(self):
        a = self.audit(); before = a["complete_payload_sha256"]
        a["complete_payload"]["all_pre_maps"].clear()
        self.assertEqual(self.audit()["complete_payload_sha256"], before)
        d = self.data()
        for fake in (a, before, d.pair, d.census, object.__new__(candidate.OwnedWholeCellMaps), None):
            with self.assertRaises(ready.ProtocolError):
                candidate.whole_cell_maps_audit(fake, self.diagnostic_run, self.source)
        with self.assertRaises(ready.ProtocolError): candidate.OwnedWholeCellMaps()

    def test_equal_source_or_other_actual_run_cannot_transfer_origin(self):
        other = self.fixture.source()
        with self.assertRaises(ready.ProtocolError):
            candidate.whole_cell_maps_audit(self.handle, self.diagnostic_run, other)
        other_run = diagnostic.run_owned_diagnostic(self.source, method_id="TrajectoryCredit")
        with self.assertRaises(ready.ProtocolError):
            candidate.whole_cell_maps_audit(self.handle, other_run, self.source)

    def test_all_site_prefix_reorder_duplicate_refused(self):
        d = self.data()
        for sites in (d.sites[:-1], tuple(reversed(d.sites)), d.sites[:-1] + d.sites[:1]):
            self.reject(replace(d, sites=sites))
        self.reject(replace(d, regions=d.regions[:-1]))
        self.reject(replace(d, pre_maps=d.pre_maps[:-1]))
        self.reject(replace(d, post_maps=(d.post_maps[0], d.post_maps[1][:-1])))

    def test_dropped_residual_predictions_refused_not_partial_scientific_pass(self):
        d = self.data(); whole = dict(d.cell_payload); whole["residual_predictions"] = []
        self.reject(replace(d, cell_payload=whole))

    def test_map_scene_prefix_order_bool_int_nan_refused(self):
        d = self.data(); original = d.pre_maps[0]; first = next(iter(original))
        missing = dict(original); missing.pop(first)
        cases = [missing, dict(reversed(tuple(original.items())))]
        for value in (1, True, float("nan")):
            changed = dict(original); changed[first] = value; cases.append(changed)
        for bad in cases:
            self.reject(replace(d, pre_maps=(bad,) + d.pre_maps[1:]))

    def test_reference_mean_preserving_map_change_refused_elementwise(self):
        d = self.data(); units = d.regions[0].units; bad = dict(d.post_maps[0][0])
        bad[units[0]] += .25; bad[units[1]] -= .25
        self.reject(replace(d, post_maps=((bad,) + d.post_maps[0][1:], d.post_maps[1])), "elementwise")

    def test_map_alias_refused_even_when_regions_and_values_equal(self):
        d = self.data()
        self.reject(replace(d, post_maps=(d.pre_maps, d.post_maps[1])), "independently measured")

    def test_clone_alias_role_swap_or_equal_detached_replacement_refused(self):
        d = self.data(); pd = pair._PAIRS[d.pair]
        self.reject(replace(d, clones=tuple(reversed(d.clones))))
        self.reject(replace(d, clones=(d.clones[0], d.clones[0])))
        self.reject(replace(d, clones=pd.clones))
        # A clone with equal bytes IS allowed only as a component-owned export:
        # replacing with equal external clone preserves fp but the seal must not
        # assert object ownership that this v20 record does not itself pin.
        # This limitation is reported rather than advertised as hostile security.
        self.assertFalse(self.audit()["portable_security_or_scientific_acquisition_origin_authenticated"])

    def test_native_whole_ledger_prefix_refused_without_rerunning_B1(self):
        d = self.data(); pd = pair._PAIRS[d.pair]; result = pd.results[1]
        ledger = replace(result.ledger, receipts=result.ledger.receipts[:-1])
        with patch.dict(pair._PAIRS, {d.pair: replace(pd, results=(pd.results[0], replace(result, ledger=ledger)))}):
            with self.assertRaises(ready.ProtocolError): self.audit()

    def test_census_prefix_consult_bit_drift_invalidates_all_maps(self):
        d = self.data(); cd = census._ISSUED[d.census]
        bad = dict(cd.traces._rows); bad.pop(next(iter(bad)))
        with patch.object(cd.traces, "_rows", bad):
            with self.assertRaises(ready.ProtocolError): self.audit()
        row = cd.census[0]; flags = (not row[2][0],) + row[2][1:]
        changed = replace(cd, census=((row[0], row[1], flags, row[3], row[4]),) + cd.census[1:])
        with patch.dict(census._ISSUED, {d.census: changed}):
            with self.assertRaises(ready.ProtocolError): self.audit()

    def test_sequence_hash_or_stage_prefix_reorder_refused(self):
        d = self.data()
        for changed in (replace(d, sequence=d.sequence[:-1]),
            replace(d, sequence=tuple(reversed(d.sequence))), replace(d, payload_sha="0" * 64)):
            self.reject(changed)

    def test_wrong_cell_or_tier_or_reversed_role_refused_before_U2(self):
        wrong = (bridge.registered_pair("X", Tier.L0_FACTUAL, "X_id"),
                 bridge.registered_pair("D_Q", Tier.L2_COUNTERFACTUAL, "DualReturnWrite"),
                 tuple(reversed(self.arms)))
        with patch.object(census.native, "pre_update_traces", side_effect=AssertionError("bad U2")):
            for arms in wrong:
                with self.assertRaises(ready.ProtocolError):
                    candidate.run_owned_whole_cell_maps(self.diagnostic_run, self.source, arms)

    def test_success_skip_precedes_arm_read_no_zero_pair_or_maps(self):
        source = self.fixture.source(LearnerPersistentState(), regime="T", scene=EvaluationScene(0, 0, 0, 0, 0))
        run = diagnostic.run_owned_diagnostic(source, method_id="TrajectoryCredit")
        with patch.object(bridge, "validate_pair", side_effect=AssertionError("success arms")), \
             patch.object(census.native, "pre_update_traces", side_effect=AssertionError("success U2")):
            a = candidate.whole_cell_maps_audit(candidate.run_owned_whole_cell_maps(run, source, object()), run, source)
        self.assertIsNone(a["complete_payload"]); self.assertIsNone(a["primary_Collateral_scalar"])
        self.assertEqual(a["native_B1_arm_calls"], 0); self.assertEqual(a["native_scene_map_calls"], 0)

    def test_abstention_or_X_only_projection_empty_no_scientific_zero(self):
        for method in ("AbstainCreditCandidate", "ObservedExecutionCreditCandidate"):
            run = diagnostic.run_owned_diagnostic(self.source, method_id=method)
            with patch.object(census.native, "pre_update_traces", side_effect=AssertionError("empty U2")):
                a = candidate.whole_cell_maps_audit(candidate.run_owned_whole_cell_maps(run, self.source, self.arms), run, self.source)
            self.assertIsNone(a["complete_payload"]); self.assertEqual(a["native_B1_arm_calls"], 0)

    def test_production_exclusion_is_all_cell_failure_before_any_map_or_B1(self):
        before = len(candidate._ISSUED); original = census.native.credited_domain
        site = self.data().sites[-1]
        def reduced(channel, traces): return tuple(s for s in original(channel, traces) if s != site)
        with patch.object(census.native, "credited_domain", side_effect=reduced), \
             patch.object(candidate.native_maps, "measure_scene_map", side_effect=AssertionError("partial maps")), \
             patch.object(pair, "run_owned_b1_pair", side_effect=AssertionError("partial B1")):
            with self.assertRaisesRegex(ready.ProtocolError, "all production sites"):
                candidate.run_owned_whole_cell_maps(self.diagnostic_run, self.source, self.arms)
        self.assertEqual(len(candidate._ISSUED), before)

    def test_pre_map_failure_issues_no_handle_and_calls_no_B1(self):
        before = len(candidate._ISSUED); original = candidate.native_maps.measure_scene_map; calls = []
        def failed(*a, **kw):
            calls.append(1)
            if len(calls) == 2: raise ready.ProtocolError("second pre map error")
            return original(*a, **kw)
        with patch.object(candidate.native_maps, "measure_scene_map", side_effect=failed), \
             patch.object(pair, "run_owned_b1_pair", side_effect=AssertionError("B1 after incomplete pre")):
            with self.assertRaisesRegex(ready.ProtocolError, "second pre map error"):
                candidate.run_owned_whole_cell_maps(self.diagnostic_run, self.source, self.arms)
        self.assertEqual(len(calls), 2); self.assertEqual(len(candidate._ISSUED), before)
        self.assertEqual(fingerprint(owned._ISSUED[self.source].pre_state), self.before)

    def test_code_or_contract_guard_refuses_no_science_authority_and_machine_summary(self):
        with patch.object(candidate, "_CODE_BINDING", tuple("0" * 64 for p in candidate._CODE_BINDING)):
            with self.assertRaises(ready.ProtocolError): self.audit()
        a = self.audit(); p = a["complete_payload"]
        for key in ("multi_credit_E_S_defined", "singleton_update_attribution_claimed",
            "native_raw_collateral_record_or_future_protocol_fabricated",
            "portable_security_or_scientific_acquisition_origin_authenticated",
            "full_dense_B2_workload_resources_certified", "collection_authorized",
            "scientific_claim_authorized", "research_complete"):
            self.assertIs(a[key], False)
        self.assertEqual(a["environment_seed_draws"], 0); self.assertEqual(a["future_training_episodes"], 0)
        print("SEEDLESS_WHOLE_CELL_V20_SUMMARY=" + json.dumps({
            "parent_sources_digest": p["parent_sources_digest"], "lock_sha256": p["lock_sha256"],
            "native_U2_pre_rollouts": a["native_U2_pre_rollouts"],
            "complete_DQ_credited_site_count": len(self.data().sites), "residual_prediction_count": 16,
            "native_scene_map_calls": a["native_scene_map_calls"], "native_B1_arm_calls": a["native_B1_arm_calls"],
            "map_scene_rollouts": a["map_scene_rollouts"], "complete_payload_sha256": a["complete_payload_sha256"],
            "ordered_E1_sizes": [r.size for r in self.data().regions],
            "primary_Collateral_scalar": None, "multi_credit_E_S_defined": False,
            "environment_seed_draws": 0, "future_training_episodes": 0,
            "collection_authorized": False, "scientific_claim_authorized": False}, sort_keys=True))


if __name__ == "__main__": unittest.main()
