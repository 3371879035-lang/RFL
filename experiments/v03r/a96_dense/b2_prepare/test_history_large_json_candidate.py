"""Seed-free whole-JSON tests; fixtures are literals, not draws or allocation."""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import history_large_json_candidate as large
import history_seed_audit_candidate as history
import readiness as ready


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf8")


class LargeJSONTests(unittest.TestCase):
    def parse(self, blob):
        return large.inspect_large_json_bytes(blob)

    def keys(self, result):
        return [r["original_integer_decimal"] for r in result["claims"]]

    def refused(self, blob):
        result = self.parse(blob)
        self.assertFalse(result["parse_complete"])
        self.assertEqual(result["claims"], [])
        self.assertEqual(result["conservative_exclusion_intervals_decimal_inclusive"], [])
        self.assertEqual(result["bytes"], len(blob))
        self.assertEqual(result["sha256"], hashlib.sha256(blob).hexdigest())
        self.assertTrue(result["issues"])
        return result

    def test_single_whole_object(self):
        self.assertEqual(self.keys(self.parse(b'{"seed":7}')), ["7"])

    def test_whitespace_and_CRLF_not_JSONL_split(self):
        self.assertEqual(self.keys(self.parse(b' \r\n{"seed":7}\r\n ')), ["7"])

    def test_optional_initial_UTF8_BOM(self):
        self.assertEqual(self.keys(self.parse(b'\xef\xbb\xbf{"seed":7}')), ["7"])

    def test_second_UTF8_BOM_refuses_complete_file(self):
        self.refused(b'\xef\xbb\xbf\xef\xbb\xbf{"seed":7}')

    def test_BOM_after_whitespace_not_guessed(self):
        self.refused(b' \xef\xbb\xbf{"seed":7}')

    def test_empty_file(self):
        self.refused(b'')

    def test_blank_file(self):
        self.refused(b' \r\n\t')

    def test_JSONL_two_objects_are_not_whole_JSON(self):
        self.refused(b'{"seed":7}\n{"seed":8}\n')

    def test_complete_array_of_objects(self):
        self.assertEqual(self.keys(self.parse(b'[{"seed":7},{"seed":8}]')), ["7", "8"])

    def test_complete_scalar_no_identity(self):
        for raw in (b'7', b'null', b'true', b'"seed"'):
            result = self.parse(raw)
            self.assertTrue(result["parse_complete"])
            self.assertEqual(result["claims"], [])

    def test_duplicate_seed_discards_valid_prefix(self):
        self.refused(b'{"seed":7,"seed":8}')

    def test_duplicate_non_seed_member_discards_all_claims(self):
        self.refused(b'{"seed":7,"x":1,"x":2}')

    def test_nested_duplicate_non_seed_member(self):
        self.refused(b'{"seed":7,"fields":{"x":1,"x":2}}')

    def test_duplicate_key_with_escaped_spelling(self):
        self.refused(b'{"seed":7,"se\\u0065d":8}')

    def test_malformed_final_byte_discards_valid_prefix(self):
        self.refused(b'{"seed":7,"fields":[0,1,2,]}')

    def test_missing_final_brace_discards_prefix(self):
        self.refused(b'{"seed":7,"fields":[0,1,2]')

    def test_trailing_second_document(self):
        self.refused(b'{"seed":7}{}')

    def test_nonfinite_constants_and_overflow(self):
        for raw in (b'NaN', b'Infinity', b'-Infinity', b'1e999'):
            self.refused(b'{"seed":7,"fields":' + raw + b'}')

    def test_invalid_UTF8(self):
        self.refused(b'{"seed":7,"text":"\xff"}')

    def test_UTF16_not_inferred(self):
        self.refused('{"seed":7}'.encode("utf16"))

    def test_unescaped_control_character(self):
        self.refused(b'{"seed":7,"text":"\x00"}')

    def test_unknown_seed_member_remains_semantic_issue(self):
        result = self.parse(b'{"mystery_seed":77}')
        self.assertTrue(result["parse_complete"])
        self.assertFalse(result["claims"])
        self.assertIn("unknown-seed-related-field-not-resolved", [r["reason"] for r in result["issues"]])

    def test_null_declared_container_unassigned(self):
        result = self.parse(b'{"treatment":{"seeds":null}}')
        self.assertFalse(result["claims"])
        self.assertIn("unassigned-null-seed-declaration", [r["reason"] for r in result["issues"]])

    def test_container_scalar_is_count_not_identity(self):
        result = self.parse(b'{"seeds":400}')
        self.assertFalse(result["claims"])
        self.assertIn("scalar-seed-container-may-be-count-not-identity", [r["reason"] for r in result["issues"]])

    def test_bool_float_string_not_normalized_seed(self):
        for value in (True, False, 7.0, "7", None):
            result = self.parse(encoded({"seed": value}))
            self.assertFalse(result["claims"])
            self.assertTrue(result["issues"])

    def test_world_indices_outcomes_PIDs_ticks_and_counts_not_seeds(self):
        result = self.parse(encoded({"manifest": {"n_worlds": 1038960}, "fields": {
            "world_index": [0, 1, 1038959], "RMST": [465]}, "pid": 9924,
            "ticks": 639271289393389540, "n_seeds": 400, "seed_index": 1, "seed_draws": 0}))
        self.assertTrue(result["parse_complete"])
        self.assertFalse(result["claims"])
        self.assertFalse(result["issues"])

    def test_support_cache_style_large_scalar_arrays_no_identity(self):
        result = self.parse(encoded({"manifest": {"n_worlds": 100000},
            "fields": {"kappa": [0] * 100000, "world_index": list(range(100000))}}))
        self.assertTrue(result["parse_complete"])
        self.assertFalse(result["claims"])

    def test_escaped_unicode_JSON_pointer(self):
        result = self.parse(encoded({"中文/~": {"seed": 8}}))
        self.assertEqual(result["claims"][0]["example_pointer"], "/中文~1~0/seed")

    def test_uint64_max_decimal_lossless(self):
        result = self.parse(encoded({"seed": (1 << 64) - 1}))
        self.assertEqual(self.keys(result), ["18446744073709551615"])
        self.assertEqual(result["claims"][0]["canonical_modulo64_exclusion_decimal"], "18446744073709551615")
        self.assertTrue(result["claims"][0]["original_is_canonical_uint64"])

    def test_negative_and_overwide_historical_exclusions_not_new_plan(self):
        result = self.parse(encoded({"seeds": [-1, (1 << 64) + 7]}))
        self.assertEqual(self.keys(result), ["-1", "18446744073709551623"])
        self.assertEqual([r["canonical_modulo64_exclusion_decimal"] for r in result["claims"]],
                         ["18446744073709551615", "7"])
        self.assertTrue(all(not r["original_is_canonical_uint64"] for r in result["claims"]))

    def test_repetitions_not_independent_N(self):
        result = self.parse(b'{"seed":7,"nested":{"seed":7},"seeds":[7,7]}')
        self.assertEqual([r["occurrences"] for r in result["claims"]], [2, 2])
        self.assertEqual(result["conservative_exclusion_intervals_decimal_inclusive"], [["7", "7"]])
        self.assertIn("NOT_VALID_RUN_OR_STATISTICAL_N", result["identity_role"])

    def test_fields_sorted_by_native_integer_not_decimal_lexical_order(self):
        self.assertEqual(self.keys(self.parse(b'{"seeds":[10,2,1]}')), ["1", "2", "10"])

    def test_same_integer_in_different_fields_not_collapsed(self):
        result = self.parse(b'{"seed":7,"algorithm_seed":7}')
        self.assertEqual([r["field"] for r in result["claims"]], ["algorithm_seed", "seed"])

    def test_full_uint64_interval_stays_compact(self):
        result = self.parse(encoded({"permanent_exclusions": {"old_engineering_ranges":
                                                             [[0, (1 << 64) - 1]]}}))
        self.assertEqual(result["conservative_exclusion_intervals_decimal_inclusive"],
                         [["0", "18446744073709551615"]])

    def test_interval_and_identity_union_native_math(self):
        result = self.parse(b'{"seed":10,"permanent_exclusions":{"old_engineering_ranges":[[7,9]]}}')
        self.assertEqual(result["conservative_exclusion_intervals_decimal_inclusive"], [["7", "10"]])

    def test_malformed_suffix_also_discards_intervals(self):
        self.refused(b'{"seed":7,"permanent_exclusions":{"old_engineering_ranges":[[7,9]]},"x":}')

    def test_declared_stage_containers(self):
        result = self.parse(b'{"scientific_seeds":{"primary":[7,8],"secondary":[9]}}')
        self.assertEqual(self.keys(result), ["7", "8", "9"])

    def test_unrecognized_stage_members_not_guessed(self):
        result = self.parse(b'{"seeds":{"unknown":[7]}}')
        self.assertFalse(result["claims"])
        self.assertTrue(result["issues"])

    def test_schedule_and_external_references_not_executed(self):
        result = self.parse(b'{"seed_file":"run.py","seed_base":77,"program":"danger()"}')
        self.assertFalse(result["claims"])
        self.assertTrue(result["issues"])

    def test_exact_size_boundary_accepted(self):
        blob = b'{"seed":7}'
        with patch.object(large, "_JSON_LIMIT", len(blob)):
            self.assertTrue(self.parse(blob)["parse_complete"])

    def test_over_limit_whole_bytes_hashed_no_parser_or_prefix(self):
        blob = b'{"seed":7}'
        with patch.object(large, "_JSON_LIMIT", len(blob) - 1), \
                patch.object(history, "inspect_json_bytes", side_effect=AssertionError("no decode")):
            self.refused(blob)

    def test_unique_claim_limit_no_prefix(self):
        with patch.object(large, "_CLAIM_LIMIT", 1):
            self.refused(b'{"seeds":[7,9]}')

    def test_exact_claim_limit_and_repeat_does_not_overflow(self):
        with patch.object(large, "_CLAIM_LIMIT", 1):
            result = self.parse(b'{"seeds":[7,7,7]}')
        self.assertTrue(result["parse_complete"])
        self.assertEqual(result["claims"][0]["occurrences"], 3)

    def test_disjoint_interval_limit_no_prefix(self):
        with patch.object(large, "_CLAIM_LIMIT", 1):
            self.refused(b'{"permanent_exclusions":{"old_engineering_ranges":[[7,7],[9,9]]}}')

    def test_decoder_MemoryError_no_prefix(self):
        with patch.object(history, "inspect_json_bytes", side_effect=MemoryError):
            result = self.refused(b'{"seed":7}')
        self.assertIn("MemoryError", result["issues"][0]["reason"])

    def test_union_MemoryError_after_extraction_no_prefix(self):
        with patch.object(history, "merge_intervals", side_effect=MemoryError):
            self.refused(b'{"seed":7}')

    def test_nonbytes_rejected_without_coercion(self):
        for value in (None, "{}", bytearray(b"{}"), {}, 1):
            with self.assertRaises(ready.ProtocolError):
                self.parse(value)

    def test_default_static_caps_not_scientific_parameters(self):
        self.assertEqual(large._JSON_LIMIT, 128 * 1024 * 1024)
        self.assertEqual(large._SCOPE_LIMIT, 192 * 1024 * 1024)
        self.assertEqual(large._CLAIM_LIMIT, 262144)
        self.assertEqual(sum(t[2] for t in large._TARGETS), 172926983)

    def test_closed_API_no_scope_key_output_override(self):
        self.assertEqual(str(inspect.signature(large.snapshot_large_json_history)), "()")
        for kwargs in ({"root": "."}, {"seed": 7}, {"output": "x"}, {"limit": 1}):
            with self.assertRaises(TypeError):
                large.snapshot_large_json_history(**kwargs)

    def test_exact_inputs_both_fixed_prior_actual_SHA(self):
        snapshot = history._strict_json(large._SNAPSHOT.read_bytes())
        self.assertEqual(large._bound_targets(snapshot, ["RFL-CausalChase-v0.3"]), large._TARGETS)
        self.assertEqual(ready.file_hash(large._SNAPSHOT), large._SNAPSHOT_SHA)

    def test_prior_snapshot_wrong_payload_digest_refused(self):
        with self.assertRaises(ready.ProtocolError):
            large._bound_targets({"payload": {}, "payload_sha256": "0"*64}, ["RFL-CausalChase-v0.3"])

    def test_missing_duplicate_wrong_hash_target_fail_closed(self):
        def fake(rows):
            payload = {"file_evidence": rows}
            digest = large._sha(large.stream._canonical(payload))
            return {"payload": payload, "payload_sha256": digest}, digest
        good = [dict(zip(("root","path","bytes","sha256"), t)) for t in large._TARGETS]
        for rows in (good[:1], good + good[:1], [dict(good[0], sha256="0"*64), good[1]],
                     [dict(good[0], bytes=1), good[1]]):
            snapshot, digest = fake(rows)
            with patch.object(large, "_PAYLOAD_SHA", digest):
                with self.assertRaises(ready.ProtocolError):
                    large._bound_targets(snapshot, ["RFL-CausalChase-v0.3"])

    def test_outside_fixed_roots_refused(self):
        snapshot = history._strict_json(large._SNAPSHOT.read_bytes())
        with self.assertRaises(ready.ProtocolError):
            large._bound_targets(snapshot, ["other"])

    def test_closed_scope_size_cap_refused(self):
        snapshot = history._strict_json(large._SNAPSHOT.read_bytes())
        with patch.object(large, "_SCOPE_LIMIT", 1):
            with self.assertRaises(ready.ProtocolError):
                large._bound_targets(snapshot, ["RFL-CausalChase-v0.3"])

    def test_contract_parent_role_no_collection_authority(self):
        contract = history._strict_json(large._CONTRACT.read_bytes())
        self.assertEqual(contract["parent_preparation_commit"], "ef064c442cd1f9feea3f077331cb6c96a2589e34")
        for flag in ("collection_authorized", "keys_allocated_or_reserved",
                     "research_complete", "scientific_claim_authorized",
                     "complete_historical_usage_freshness_audit"):
            self.assertFalse(contract[flag])

    def test_code_dependency_snapshot_drift_guard(self):
        with patch.object(large.ready, "file_hash", return_value="0"*64):
            with self.assertRaises(ready.ProtocolError):
                large._guard()

    def test_no_eval_or_historical_system_execution(self):
        with patch("builtins.eval", side_effect=AssertionError("no eval")), \
                patch("os.system", side_effect=AssertionError("no historical system")):
            self.assertEqual(self.keys(self.parse(b'{"seed":7,"program":"danger()"}')), ["7"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

