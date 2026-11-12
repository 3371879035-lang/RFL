"""Constructed maps plus ONE seedless full-U2 B1/collateral engineering cell.

No scientific/engineering RNG key is allocated, no future training runs, and
there is no factual-trigger origin or collection gate. Fixture protocol 41 is
only the earlier nominal array identifier, never an environment key.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collateral_evidence_candidate as maps
import native_record_candidate as bridge
import readiness as ready
import test_native_record_candidate as constructed_fixtures
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b1.process import AssistedInput
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.training import ExogenousEpisode
from rfl_rebuild.b2.unaffected import EvaluationScene, UnaffectedSet, scene_domain
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import Edit, LearnerPersistentState, PROCESS
from rfl_rebuild.solve.dp import solve_reference


class CollateralEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = ready.load_parent()
        cls.reference = ready.read_json(Path(__file__).with_name("healthy_reference_candidate.json"))
        cls.domain = scene_domain()

    def fixture(self):
        x = constructed_fixtures.NativeRecordTests.fixture(
            SimpleNamespace(parent=self.parent, reference=self.reference))
        record, u = x["record"], x["capture"].events[0][1]
        names = record.arm_names
        # Synthetic all-U2 boolean census, not observed trajectories/eligibility.
        census = tuple((s, s in u.units, False) for s in self.domain)
        pre_values = (.75, .65)
        post_values = ((names[0], pre_values), (names[1], (.72, .62)))
        scalar = maps.behavioral_collateral_scenes(u, values_pre=dict(zip(u.units, pre_values)),
                                                  values_post=dict(zip(u.units, post_values[1][1])))
        x["record"] = replace(record, collateral={names[0]: 0., names[1]: scalar})
        raw = maps.RawCollateralEvidence(maps.ROLE, names, x["credited_site"], census, u,
            pre_values, post_values, record.fingerprints_pre[names[0]],
            tuple(record.fingerprints_post.items()), tuple(record.ledgers.items()),
            self.reference["q_reference_sha256"], self.parent["lock_sha256"],
            self.parent["sources_digest"], bridge.sha(self.reference), maps.ORDER)
        return raw, x

    def call(self, raw=None, x=None):
        if raw is None:
            raw, x = self.fixture()
        return maps.validate_collateral_evidence(raw, **{k: x[k] for k in
            ("arms", "credited_site", "parent", "reference")})

    def reject(self, raw, x):
        with self.assertRaises(ready.ProtocolError):
            self.call(raw, x)

    def test_full_supplied_census_and_original_maps_recomputed(self):
        raw, x = self.fixture()
        got = self.call(raw, x)
        self.assertEqual(len(got["input_payload"]["pre_census"]), len(self.domain))
        self.assertEqual(got["collateral"], x["record"].collateral)
        self.assertTrue(got["raw_collateral_maps_recomputed"])
        self.assertTrue(got["eligibility_recomputed_from_full_supplied_pre_census"])

    def test_recomputed_inputs_do_not_authenticate_prestate_failure_population(self):
        got = self.call()
        for field in ("supplied_census_prestate_origin_authenticated",
            "actual_factual_failure_origin_authenticated", "population_seed_registry_and_collection_gate_authenticated",
            "collection_authorized", "scientific_claim_authorized", "research_complete"):
            self.assertIs(got[field], False)

    def test_nominal_role_is_not_a_collection_role(self):
        raw, x = self.fixture()
        self.reject(replace(raw, role="NATIVE_PASS"), x)
        self.reject(SimpleNamespace(**{f: getattr(raw, f) for f in raw.__slots__}), x)

    def test_frozen_capture_is_not_mutable(self):
        raw, _ = self.fixture()
        with self.assertRaises(FrozenInstanceError):
            raw.values_pre = (1.,)

    def test_complete_portable_digest_is_reproducible(self):
        raw, x = self.fixture()
        a = self.call(raw, x); b = self.call(raw, x)
        self.assertEqual(a["input_sha256"], b["input_sha256"])
        self.assertEqual(a["input_sha256"], bridge.sha(a["input_payload"]))
        self.assertNotIn("process_id", a["input_payload"])

    def test_changed_raw_value_changes_digest_without_new_authority(self):
        raw, x = self.fixture()
        posts = (raw.values_post[0], (raw.arm_names[1], (.71, .62)))
        got = self.call(replace(raw, values_post=posts), x)
        self.assertNotEqual(got["input_sha256"], self.call(raw, x)["input_sha256"])
        self.assertFalse(got["collection_authorized"])

    def test_census_prefix_empty_and_list_refused(self):
        raw, x = self.fixture()
        for census in (raw.pre_census[:-1], (), list(raw.pre_census)):
            self.reject(replace(raw, pre_census=census), x)

    def test_census_duplicate_reordered_and_missing_replacement_refused(self):
        raw, x = self.fixture()
        for census in ((raw.pre_census[0],) + raw.pre_census[:-1],
                        tuple(reversed(raw.pre_census)), raw.pre_census[1:] + (raw.pre_census[0],)):
            self.reject(replace(raw, pre_census=census), x)

    def test_census_boolean_columns_not_integer_aliases(self):
        raw, x = self.fixture()
        for row in ((raw.pre_census[0][0], 1, False), (raw.pre_census[0][0], True, 0)):
            self.reject(replace(raw, pre_census=(row,) + raw.pre_census[1:]), x)

    def test_census_typed_scene_alias_refused(self):
        raw, x = self.fixture()
        forged = object.__new__(EvaluationScene)
        for field in EvaluationScene.__slots__:
            object.__setattr__(forged, field, getattr(raw.pre_census[0][0], field))
        object.__setattr__(forged, "kappa", False)
        self.reject(replace(raw, pre_census=((forged, True, False),) + raw.pre_census[1:]), x)

    def test_unaffected_value_equal_typed_scene_alias_refused(self):
        raw, x = self.fixture()
        forged = object.__new__(EvaluationScene)
        for field in EvaluationScene.__slots__:
            object.__setattr__(forged, field, getattr(raw.unaffected.units[0], field))
        object.__setattr__(forged, "kappa", False)
        u = UnaffectedSet((forged,) + raw.unaffected.units[1:], raw.unaffected.construction)
        self.reject(replace(raw, unaffected=u), x)

    def test_eligibility_requires_healthy_AND_not_consulted(self):
        raw, x = self.fixture()
        for row in ((raw.pre_census[0][0], False, False), (raw.pre_census[0][0], True, True)):
            self.reject(replace(raw, pre_census=(row,) + raw.pre_census[1:]), x)

    def test_extra_eligible_unit_not_silently_dropped(self):
        raw, x = self.fixture()
        rows = list(raw.pre_census); rows[2] = (rows[2][0], True, False)
        self.reject(replace(raw, pre_census=tuple(rows)), x)

    def test_empty_eligible_region_not_zero_filled(self):
        raw, x = self.fixture()
        self.reject(replace(raw, pre_census=tuple((s, False, False) for s in self.domain)), x)

    def test_credited_site_channel_and_address_match(self):
        raw, x = self.fixture()
        self.reject(replace(raw, site=bridge.CreditedSite("P", 0)), x)
        site = raw.site
        wrong = bridge.CreditedSite("D_Q", replace(site.address, z=1))
        self.reject(replace(raw, site=wrong), x)

    def test_refinement_and_set_construction_cannot_change(self):
        raw, x = self.fixture()
        self.reject(replace(raw, unaffected=UnaffectedSet(raw.unaffected.units, "wrong")), x)

    def test_parent_lock_source_Q_and_healthy_reference_hash_mismatch_refused(self):
        raw, x = self.fixture()
        for field in ("lock_sha256", "parent_sources_digest", "q_reference_sha256",
                      "healthy_reference_canonical_payload_sha256"):
            self.reject(replace(raw, **{field: "a" * 64}), x)

    def test_state_hash_syntax_checked(self):
        raw, x = self.fixture()
        self.reject(replace(raw, fingerprint_pre="historical-PID-is-not-a-state-hash"), x)
        self.reject(replace(raw, fingerprints_post=((raw.arm_names[0], "bad"), raw.fingerprints_post[1])), x)

    def test_declared_order_is_not_arbitrary_or_post_update_selection(self):
        raw, x = self.fixture()
        for order in (tuple(reversed(raw.order)), raw.order[:-1], list(raw.order)):
            self.reject(replace(raw, order=order), x)

    def test_two_arm_roles_cannot_reverse_duplicate_or_rename(self):
        raw, x = self.fixture()
        self.reject(replace(raw, arm_names=tuple(reversed(raw.arm_names))), x)
        for field in ("values_post", "fingerprints_post", "ledgers"):
            rows = getattr(raw, field)
            for changed in (tuple(reversed(rows)), (rows[0], rows[0]), rows[:1], list(rows)):
                self.reject(replace(raw, **{field: changed}), x)

    def test_maps_must_cover_exact_full_unaffected_set(self):
        raw, x = self.fixture()
        for values in ((), raw.values_pre[:1], raw.values_pre + (.8,), list(raw.values_pre)):
            self.reject(replace(raw, values_pre=values), x)
        self.reject(replace(raw, values_post=(raw.values_post[0], (raw.arm_names[1], (.72,)))), x)

    def test_bool_int_nan_inf_and_overflowing_real_refused(self):
        raw, x = self.fixture()
        for v in (True, 1, float("nan"), float("inf"), -float("inf"), 10**400):
            self.reject(replace(raw, values_post=(raw.values_post[0], (raw.arm_names[1], (v, .62)))), x)

    def test_overflowing_original_mean_not_reported_finite(self):
        raw, x = self.fixture()
        pre = (1e308, 1e308)
        self.reject(replace(raw, values_pre=pre,
            values_post=((raw.arm_names[0], pre), (raw.arm_names[1], pre))), x)

    def test_NoWrite_elementwise_equality_not_only_zero_net_mean(self):
        raw, x = self.fixture()
        # Both raw means equal .7, but individual scene values moved.
        self.reject(replace(raw, values_post=((raw.arm_names[0], (.65, .75)), raw.values_post[1])), x)

    def test_NoWrite_signed_zero_substitution_refused(self):
        raw, x = self.fixture()
        self.reject(replace(raw, values_pre=(0., .65),
            values_post=((raw.arm_names[0], (-0., .65)), raw.values_post[1])), x)

    def test_original_builtin_sum_on_ordered_values_not_manual_add_rewrite(self):
        raw, x = self.fixture()
        units = self.domain[:3]
        u = UnaffectedSet(units, raw.unaffected.construction)
        pre = (1e16, 1., -1e16)
        census = tuple((s, s in units, False) for s in self.domain)
        changed = replace(raw, unaffected=u, pre_census=census, values_pre=pre,
            values_post=((raw.arm_names[0], pre), (raw.arm_names[1], (0., 0., 0.))))
        expected = sum(float(v) for v in pre) / len(pre)
        self.assertEqual(self.call(changed, x)["collateral"][raw.arm_names[1]], expected)
        # Current native Python sum compensates this cancellation. The frozen
        # formula calls sum; replacing it by repeated += would change its bytes.
        self.assertNotEqual(((pre[0] + pre[1]) + pre[2]) / 3, expected)

    def test_bad_ledger_or_pre_post_fingerprint_bindings_refused(self):
        raw, x = self.fixture()
        name, ledger = raw.ledgers[1]
        self.reject(replace(raw, ledgers=(raw.ledgers[0], (name, replace(ledger, fingerprint_pre="b"*64)))), x)
        self.reject(replace(raw, fingerprints_post=(raw.fingerprints_post[0], (name, "b"*64))), x)

    def test_join_recomputes_original_collateral_and_keeps_seed_level_rows(self):
        raw, x = self.fixture()
        got = maps.extract_with_collateral(raw, **x)
        self.assertEqual(got["scalar_rows"], bridge.extract_paired_record(**x)["scalar_rows"])
        self.assertTrue(got["raw_collateral_maps_recomputed"])
        self.assertFalse(got["unaffected_eligibility_from_prestate_recomputed"])
        self.assertFalse(got["actual_factual_failure_origin_authenticated"])
        self.assertFalse(got["collection_authorized"])

    def test_join_rejects_scalar_summary_drift(self):
        raw, x = self.fixture()
        x["record"] = replace(x["record"], collateral={raw.arm_names[0]: 0., raw.arm_names[1]: .03})
        with self.assertRaises(ready.ProtocolError):
            maps.extract_with_collateral(raw, **x)

    def test_join_rejects_changed_maps_even_if_curve_and_ledger_unchanged(self):
        raw, x = self.fixture()
        raw = replace(raw, values_post=(raw.values_post[0], (raw.arm_names[1], (.71, .62))))
        with self.assertRaises(ready.ProtocolError):
            maps.extract_with_collateral(raw, **x)

    def test_pure_map_join_never_runs_kernel_or_training(self):
        raw, x = self.fixture()
        with patch.object(maps, "pre_update_traces", side_effect=AssertionError("pure input")), \
             patch.object(maps, "measure_scene_map", side_effect=AssertionError("pure input")), \
             patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("no environment keys")):
            maps.extract_with_collateral(raw, **x)

    def test_supplied_inputs_unchanged_after_pure_validation(self):
        raw, x = self.fixture(); before = repr((raw, x["record"], x["capture"].events))
        self.call(raw, x); maps.extract_with_collateral(raw, **x)
        self.assertEqual(before, repr((raw, x["record"], x["capture"].events)))

    def test_seedless_builder_rejects_fake_learner_reference_and_credit_before_rollout(self):
        raw, x = self.fixture()
        with patch.object(maps, "pre_update_traces", side_effect=AssertionError("must reject")):
            for state, q in ((object(), object()), (LearnerPersistentState(), object())):
                with self.assertRaises(ready.ProtocolError):
                    maps.measure_seedless_pair(state, arms=x["arms"], evidence={},
                        credited_site=x["credited_site"], q_reference=q,
                        parent=self.parent, reference=self.reference)

    def test_seedless_builder_rejects_other_Q_reference_before_rollout(self):
        raw, x = self.fixture()
        q_reference = reference_view_from(solve_reference())
        reference = dict(self.reference); reference["q_reference_sha256"] = "b" * 64
        with patch.object(maps, "pre_update_traces", side_effect=AssertionError("must reject")):
            with self.assertRaises(ready.ProtocolError):
                maps.measure_seedless_pair(LearnerPersistentState(), arms=x["arms"], evidence={},
                    credited_site=x["credited_site"], q_reference=q_reference,
                    parent=self.parent, reference=reference)

    def test_seedless_builder_rejects_unrelated_B1_credit_before_rollout(self):
        q_reference = reference_view_from(solve_reference())
        arms = bridge.registered_pair("P", Tier.L1_CORRECTIVE, "P_id")
        with patch.object(maps, "pre_update_traces", side_effect=AssertionError("must reject")):
            with self.assertRaises(ready.ProtocolError):
                maps.measure_seedless_pair(LearnerPersistentState(), arms=arms,
                    evidence={"units": ("ProcessCommit",), "assisted": AssistedInput(1)},
                    credited_site=bridge.CreditedSite("P", 0), q_reference=q_reference,
                    parent=self.parent, reference=self.reference)

    def test_seedless_builder_has_no_seed_domain_or_environment_factory_parameter(self):
        # Argument rejection itself cannot draw, run or silently use a subset.
        for keyword in ("seed", "domain", "environment_factory", "train_curve"):
            with self.assertRaises(TypeError):
                maps.measure_seedless_pair(None, **{keyword: 41})

    def test_seedless_full_U2_B1_three_measurements_no_future_no_source_mutation(self):
        # ONE actual deterministic engineering cell, not a P-trigger sample.
        q_reference = reference_view_from(solve_reference())
        pre = LearnerPersistentState()
        pre.apply_transaction([Edit(PROCESS, 0, 1)], q_reference=q_reference)
        before = fingerprint(pre)
        arms = bridge.registered_pair("P", Tier.L1_CORRECTIVE, "P_id")
        site = bridge.CreditedSite("P", 0)
        evidence = {"units": ("ProcessCommit",), "assisted": AssistedInput(0)}
        with patch.object(maps, "measure_scene_map", wraps=maps.measure_scene_map) as spy, \
             patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("no environment keys")), \
             patch("rfl_rebuild.b2.runner.train_curve", side_effect=AssertionError("no future training")):
            got = maps.measure_seedless_pair(pre, arms=arms, evidence=evidence, credited_site=site,
                q_reference=q_reference, parent=self.parent, reference=self.reference)
        self.assertEqual(spy.call_count, 3)
        self.assertIs(spy.call_args_list[0].args[0], pre)
        self.assertEqual(len({id(call.args[0]) for call in spy.call_args_list}), 3)
        self.assertTrue(all(call.kwargs["q_reference"] is q_reference for call in spy.call_args_list))
        self.assertEqual(fingerprint(pre), before)
        self.assertEqual(got["full_U2_pretrace_count"], len(self.domain))
        self.assertEqual(got["environment_seed_draws"], got["future_training_episodes"])
        self.assertEqual(got["environment_seed_draws"], 0)
        self.assertEqual(dict(got["raw"].fingerprints_post)[arms[0].name], before)
        self.assertNotEqual(dict(got["raw"].fingerprints_post)[arms[1].name], before)
        self.assertTrue(got["native_B1_dispatch_executed"])
        self.assertFalse(got["collection_authorized"])
        print("SEEDLESS_ENGINEERING_SUMMARY " + json.dumps({
            "role": got["role"], "full_U2_pretrace_count": got["full_U2_pretrace_count"],
            "unaffected_count": got["unaffected_count"], "scene_map_measurements": spy.call_count,
            "source_fingerprint_unchanged": fingerprint(pre) == before,
            "environment_seed_draws": 0, "future_training_episodes": 0,
            "raw_input_sha256": got["checked"]["input_sha256"],
            "native_receipt_statuses": [ledger.receipts[0].status for _, ledger in got["raw"].ledgers],
            "collection_authorized": False, "scientific_claim_authorized": False}, sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
