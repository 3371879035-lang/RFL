"""Pure nonallocated key proposals only; never generate a training stream."""
from copy import deepcopy
from fractions import Fraction
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seed_plan_candidate as candidate
import readiness as ready


def proposal():
    # Input-construction integers ONLY. Not allocated/reserved/acquired keys;
    # these visible fixture labels must not later be mistaken for science.
    base = 1 << 63
    return {"schema": candidate._PLAN_SCHEMA, "role": candidate._PLAN_ROLE,
        "primary_blocks": [[base + b * 100 + i for i in range(100)] for b in range(4)],
        "secondary_blocks": [[base + 400 + b * 100 + i for i in range(100)] for b in range(2)],
        "engineering_keys": [base + 1000, base + 1001, base + 1002]}


class SeedPlanTests(unittest.TestCase):
    def check(self, value=None):
        return candidate.inspect_seed_plan(proposal() if value is None else value)

    def refuse_key(self, key, category="primary_blocks"):
        p = proposal()
        if category == "engineering_keys":
            p[category][0] = key
        else:
            p[category][0][0] = key
        with self.assertRaises(ready.ProtocolError):
            self.check(p)

    def test_complete400_and200_preserve_caller_block_order_no_sort(self):
        p = proposal()
        p["primary_blocks"][0].reverse()
        a = self.check(p); raw = a["input_payload"]
        self.assertEqual(raw["proposal"], p)
        self.assertEqual(raw["ordered_primary_keys"], [x for b in p["primary_blocks"] for x in b])
        self.assertEqual(raw["ordered_secondary_keys"], [x for b in p["secondary_blocks"] for x in b])
        self.assertEqual(a["primary_proposed_keys"], 400)
        self.assertEqual(a["secondary_proposed_keys"], 200)
        self.assertEqual(a["engineering_proposed_keys"], 3)

    def test_closed_one_proposal_API_no_gate_seed_override_callback(self):
        self.assertEqual(tuple(inspect.signature(candidate.inspect_seed_plan).parameters), ("proposal",))
        for kw in ("seed", "permit", "registry", "exclusions", "callback", "allocate",
                   "treatment_keys", "N", "runtime", "output"):
            with self.assertRaises(TypeError):
                candidate.inspect_seed_plan(proposal(), **{kw: None})

    def test_unknown_missing_authorization_or_receipt_fields_refused(self):
        for key in ("schema", "role", "primary_blocks", "secondary_blocks", "engineering_keys"):
            p = proposal(); del p[key]
            with self.assertRaises(ready.ProtocolError): self.check(p)
        for key, value in (("collection_authorized", True), ("native_exit_code", 0),
                           ("reserved", True), ("known_exclusions", [])):
            p = proposal(); p[key] = value
            with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_nominal_dict_not_subclass_duck_tuple_or_receipt(self):
        class Alias(dict): pass
        for p in (Alias(proposal()), None, [], (), "receipt", object()):
            with self.assertRaises(ready.ProtocolError): candidate.inspect_seed_plan(p)

    def test_role_and_schema_are_closed_native_strings(self):
        class Text(str): pass
        for field in ("schema", "role"):
            for x in (Text(proposal()[field]), False, None, "RESERVED_OR_AUTHORIZED"):
                p = proposal(); p[field] = x
                with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_primary_has_exact_four_complete100_blocks(self):
        for n in (0, 1, 2, 3, 5):
            p = proposal(); p["primary_blocks"] = [list(p["primary_blocks"][0]) for _ in range(n)]
            with self.assertRaises(ready.ProtocolError): self.check(p)
        for n in (0, 1, 99, 101):
            p = proposal(); p["primary_blocks"][0] = list(range((1 << 62), (1 << 62) + n))
            with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_secondary_has_exact_two_complete100_blocks(self):
        for n in (0, 1, 3, 4):
            p = proposal(); p["secondary_blocks"] = [list(p["secondary_blocks"][0]) for _ in range(n)]
            with self.assertRaises(ready.ProtocolError): self.check(p)
        for n in (0, 1, 99, 101):
            p = proposal(); p["secondary_blocks"][0] = list(range((1 << 62), (1 << 62) + n))
            with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_secondary_not_silently_upgraded_to400_or_primary_reduced(self):
        p = proposal(); p["secondary_blocks"] += deepcopy(p["secondary_blocks"])
        with self.assertRaises(ready.ProtocolError): self.check(p)
        p = proposal(); p["primary_blocks"] = p["primary_blocks"][:2]
        with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_stage_block_and_engineering_container_types_are_closed(self):
        for category in ("primary_blocks", "secondary_blocks"):
            p = proposal(); p[category] = tuple(p[category])
            with self.assertRaises(ready.ProtocolError): self.check(p)
            p = proposal(); p[category][0] = tuple(p[category][0])
            with self.assertRaises(ready.ProtocolError): self.check(p)
        for x in (None, (), [], set(), "some-key"):
            p = proposal(); p["engineering_keys"] = x
            with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_bool_float_fraction_and_int_subclass_not_seed_ids(self):
        class Number(int): pass
        for x in (False, True, 1.0, float(1 << 63), Fraction(1 << 63), Number(1 << 63)):
            self.refuse_key(x)

    def test_negative_over64bit_and_wrap_alias_not_normalized(self):
        for x in (-1, -(1 << 64), 1 << 64, (1 << 64) + (1 << 63), (1 << 128) - 1):
            self.refuse_key(x)
        p = proposal(); p["primary_blocks"][1][0] = p["primary_blocks"][0][0] + (1 << 64)
        with self.assertRaisesRegex(ready.ProtocolError, "64-bit"): self.check(p)

    def test_nonfinite_and_non_json_key_values_fail_with_protocol_error(self):
        for x in (float("nan"), float("inf"), float("-inf"), "1", None, {}, [], object()):
            self.refuse_key(x)

    def test_canonical_unsigned_upper_endpoint_is_only_nominal_validity(self):
        p = proposal(); p["primary_blocks"][0][0] = (1 << 64) - 1
        a = self.check(p)
        self.assertEqual(a["input_payload"]["ordered_primary_keys"][0], (1 << 64) - 1)
        self.assertIs(a["complete_historical_usage_freshness_audit"], False)
        self.assertIs(a["keys_allocated_or_reserved"], False)

    def test_duplicate_within_a_block_refused(self):
        p = proposal(); p["primary_blocks"][0][1] = p["primary_blocks"][0][0]
        with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_duplicate_across_blocks_refused(self):
        p = proposal(); p["primary_blocks"][1][0] = p["primary_blocks"][0][0]
        with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_duplicate_between_primary_and_secondary_refused(self):
        p = proposal(); p["secondary_blocks"][0][0] = p["primary_blocks"][3][99]
        with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_engineering_cannot_alias_either_science_stage(self):
        for category in ("primary_blocks", "secondary_blocks"):
            p = proposal(); p["engineering_keys"][0] = p[category][0][0]
            with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_engineering_duplicate_refused(self):
        p = proposal(); p["engineering_keys"][1] = p["engineering_keys"][0]
        with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_all_parent_current_science_keys_stay_excluded_in_any_stage(self):
        for category in ("smoke", "dev_baseline"):
            for x in candidate._REGISTRY["scientific"][category]:
                for target in ("primary_blocks", "secondary_blocks", "engineering_keys"):
                    self.refuse_key(x, target)

    def test_all_parent_current_engineering_keys_stay_non_scientific(self):
        for category in ("smoke", "dev_baseline"):
            for x in candidate._REGISTRY["engineering"][category]:
                self.refuse_key(x)
                self.refuse_key(x, "engineering_keys")

    def test_all_historical_science_exclusions_including_interrupted_refused(self):
        for x in candidate._REGISTRY["permanent_exclusions"]["old_scientific"]:
            self.refuse_key(x)
            self.refuse_key(x, "engineering_keys")

    def test_old_engineering_ranges_closed_both_endpoints_and_interior(self):
        for lo, hi in candidate._REGISTRY["permanent_exclusions"]["old_engineering_ranges"]:
            for x in (lo, (lo + hi) // 2, hi):
                self.refuse_key(x)

    def test_fixture_ranges_closed_both_endpoints_and_interior(self):
        for lo, hi in candidate._REGISTRY["permanent_exclusions"]["operational_fixture_ranges"]:
            for x in (lo, (lo + hi) // 2, hi):
                self.refuse_key(x)
                self.refuse_key(x, "engineering_keys")

    def test_analysis_RNG_not_environment_or_science_key(self):
        x = candidate._DRAFT["analysis_procedure_candidate"]["bootstrap"]["algorithm_seed"]
        for category in ("primary_blocks", "secondary_blocks", "engineering_keys"):
            self.refuse_key(x, category)

    def test_intervals_union_is_exact_sorted_and_never_expands_huge_range(self):
        registry = deepcopy(candidate._REGISTRY)
        registry["permanent_exclusions"]["old_engineering_ranges"] += [
            [1 << 62, (1 << 62) + 5], [(1 << 62) + 3, (1 << 62) + 20],
            [(1 << 62) + 21, (1 << 62) + 30], [1 << 63, (1 << 64) - 1]]
        ranges = candidate._registry_intervals(registry)
        self.assertIn((1 << 62, (1 << 62) + 30), ranges)
        self.assertIn((1 << 63, (1 << 64) - 1), ranges)
        self.assertTrue(all(a[1] + 1 < b[0] for a, b in zip(ranges, ranges[1:])))

    def test_bad_registry_schema_stage_counts_or_pending_key_fields_refused(self):
        cases = []
        for field, x in (("schema", "old"), ("profile", "sparse"),
                         ("automatic_retry", True), ("role", "COMPLETE")):
            r = deepcopy(candidate._REGISTRY); r[field] = x; cases.append(r)
        r = deepcopy(candidate._REGISTRY); r["scientific"]["smoke"].pop(); cases.append(r)
        r = deepcopy(candidate._REGISTRY); r["scientific"]["confirmatory"] = [10]; cases.append(r)
        r = deepcopy(candidate._REGISTRY); r["engineering"]["other"] = []; cases.append(r)
        r = deepcopy(candidate._REGISTRY); del r["permanent_exclusions"]["old_scientific"]; cases.append(r)
        for r in cases:
            with self.assertRaises(ready.ProtocolError): candidate._registry_intervals(r)

    def test_bad_registry_range_shape_types_and_reversal_refused(self):
        for row in (None, [], [0], [0, 1, 2], [1, 0], [False, 2],
                    [1, 2.0], [0, 1 << 64], (0, 1)):
            r = deepcopy(candidate._REGISTRY)
            r["permanent_exclusions"]["old_engineering_ranges"].append(row)
            with self.assertRaises(ready.ProtocolError): candidate._registry_intervals(r)

    def test_current_registry_payload_mutation_refused_not_caller_exclusion_override(self):
        with patch.dict(candidate._REGISTRY, {"automatic_retry": True}):
            with self.assertRaises(ready.ProtocolError): self.check()
        p = proposal(); p["exclusions"] = []
        with self.assertRaises(ready.ProtocolError): self.check(p)

    def test_loaded_parent_identity_lock_and_draft_drift_refused(self):
        with patch.dict(candidate._PARENT, {"sources_digest": "0" * 64}):
            with self.assertRaises(ready.ProtocolError): self.check()
        with patch.dict(candidate._PARENT["lock"], {"status": "UNLOCKED"}):
            with self.assertRaises(ready.ProtocolError): self.check()
        with patch.dict(candidate._DRAFT, {"role": "COLLECTION_GATE"}):
            with self.assertRaises(ready.ProtocolError): self.check()
        with patch.object(candidate, "_CODE_BINDING", ()):
            with self.assertRaises(ready.ProtocolError): self.check()
        with patch.object(candidate.training, "M64", (1 << 32) - 1):
            with self.assertRaises(ready.ProtocolError): self.check()

    def test_source_or_registry_file_hash_drift_refused_without_editing_files(self):
        actual = candidate.ready.file_hash
        def changed(path):
            return "0" * 64 if Path(path) == candidate._REGISTRY_PATH else actual(path)
        with patch.object(candidate.ready, "file_hash", side_effect=changed):
            with self.assertRaises(ready.ProtocolError): self.check()

    def test_proposal_moved_during_validation_refused(self):
        p = proposal(); actual = candidate._guard; calls = []
        def guard():
            calls.append(1)
            if len(calls) == 2: p["primary_blocks"][0].reverse()
            return actual()
        with patch.object(candidate, "_guard", side_effect=guard):
            with self.assertRaisesRegex(ready.ProtocolError, "moved"): self.check(p)
        self.assertEqual(len(calls), 2)

    def test_input_not_modified_and_output_deepcopy_hash_covers_full600_order(self):
        p = proposal(); before = deepcopy(p); a = self.check(p); b = self.check(p)
        self.assertEqual(p, before); self.assertEqual(a, b)
        p["primary_blocks"][0].reverse(); c = self.check(p)
        self.assertNotEqual(a["input_payload_sha256"], c["input_payload_sha256"])
        a["input_payload"]["proposal"]["primary_blocks"][0][0] = 0
        self.assertEqual(self.check(before), b)

    def test_no_training_protocol_draw_reservation_or_worker_is_called(self):
        with patch.object(candidate.training, "FutureTrainingProtocol", side_effect=AssertionError("protocol")), \
             patch.object(candidate.training.ExogenousEpisode, "derive", side_effect=AssertionError("episode")), \
             patch.object(candidate.training, "key", side_effect=AssertionError("key")), \
             patch.object(candidate.training, "train_curve", side_effect=AssertionError("train")):
            a = self.check()
        self.assertEqual(a["environment_key_draws"], 0)
        self.assertIs(a["native_protocol_or_training_started"], False)
        print("UNALLOCATED_SEED_PLAN_SUMMARY=" + json.dumps({
            "primary_nominal_keys": 400, "secondary_nominal_keys": 200,
            "environment_key_draws": 0, "keys_allocated_or_reserved": False,
            "complete_historical_freshness_audit": False,
            "collection_authorized": False}, sort_keys=True))

    def test_engineering_key_count_is_not_full_B2_workload_approval(self):
        for n in (1, 3, 37, 100):
            p = proposal(); p["engineering_keys"] = list(range((1 << 62), (1 << 62) + n))
            a = self.check(p)
            self.assertEqual(a["engineering_proposed_keys"], n)
            self.assertIs(a["engineering_workload_shape_or_count_authorized"], False)

    def test_all_claim_and_collection_flags_remain_false(self):
        a = self.check()
        for key in ("complete_historical_usage_freshness_audit",
                    "population_T_P_and_same_tier_family_registered",
                    "engineering_workload_shape_or_count_authorized",
                    "keys_allocated_or_reserved", "native_protocol_or_training_started",
                    "collection_authorized", "scientific_claim_authorized", "research_complete"):
            self.assertIs(a[key], False)

    def test_no_key_sampler_allocator_gate_or_retry_entry_point_exposed(self):
        for name in ("collect", "allocate", "reserve", "sample", "retry", "issue_permit",
                     "train", "launch", "freeze", "write", "activate_collection_gate"):
            self.assertFalse(hasattr(candidate, name), name)


if __name__ == "__main__":
    unittest.main()
