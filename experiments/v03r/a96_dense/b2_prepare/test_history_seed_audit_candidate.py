"""Seed-free parser/snapshot construction tests, not scientific re-acquisition."""
from copy import deepcopy
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import history_seed_audit_candidate as audit
import readiness as ready


def blob(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class HistoryAuditTests(unittest.TestCase):
    def parse(self, obj):
        return audit.inspect_json_bytes(blob(obj))

    def values(self, obj):
        return [r["canonical_modulo64_exclusion"] for r in self.parse(obj)["claims"]]

    def test_nested_declared_literals_not_outcomes_or_counts(self):
        self.assertEqual(self.values({"result": {"seed": 11, "RMST": 465,
            "n_seeds": 400, "seed_count": 200, "seed_index": 333}}), [11])

    def test_literal_order_repetition_count_and_distinct_identity(self):
        rows = self.parse({"seeds": [11, 5, 11]})["claims"]
        self.assertEqual([r["original_integer"] for r in rows], [5, 11])
        self.assertEqual(rows[1]["occurrences"], 2)

    def test_true_integer_not_bool_float_string_or_null_seed(self):
        for v in (False, True, 1.0, "1", None, [], {}):
            result = self.parse({"seed": v})
            self.assertFalse(result["claims"])
            self.assertTrue(result["issues"])

    def test_historical_alias_retains_original_not_new_plan_normalization(self):
        r = self.parse({"seeds": [-1, (1 << 64) + 5]})["claims"]
        self.assertEqual(r[0]["original_integer"], -1)
        self.assertEqual(r[0]["canonical_modulo64_exclusion"], (1 << 64) - 1)
        self.assertFalse(r[0]["original_is_canonical_uint64"])
        self.assertEqual(r[1]["original_integer"], (1 << 64) + 5)
        self.assertEqual(r[1]["canonical_modulo64_exclusion"], 5)

    def test_uint64_endpoints_not_lossy_float(self):
        self.assertEqual(self.values({"seeds": [0, (1 << 64) - 1]}), [0, (1 << 64) - 1])

    def test_duplicate_json_member_refuses_entire_prefix(self):
        r = audit.inspect_json_bytes(b'{"seed":5,"seed":6}')
        self.assertFalse(r["parse_complete"])
        self.assertFalse(r["claims"])

    def test_duplicate_in_nested_data_also_refuses_whole_document(self):
        r = audit.inspect_json_bytes(b'{"seed":5,"data":{"x":1,"x":2}}')
        self.assertFalse(r["parse_complete"])
        self.assertFalse(r["claims"])

    def test_invalid_json_or_trailing_data_has_no_partial_prefix_claim(self):
        for text in (b'{"seed":5', b'{"seed":5}{}', b'prefix {"seed":5}',
                     b'{"seed":5,"later":}'):
            r = audit.inspect_json_bytes(text)
            self.assertFalse(r["parse_complete"])
            self.assertFalse(r["claims"])

    def test_nonfinite_constants_or_numeric_overflow_refuse_whole_json(self):
        for x in (b'NaN', b'Infinity', b'-Infinity', b'1e999'):
            r = audit.inspect_json_bytes(b'{"seed":5,"outcome":' + x + b'}')
            self.assertFalse(r["parse_complete"])
            self.assertFalse(r["claims"])

    def test_bom_and_chinese_paths_pointer_are_supported(self):
        r = audit.inspect_json_bytes(b"\xef\xbb\xbf" + blob({"中文/a~b": {"seed": 7}}))
        self.assertEqual(r["claims"][0]["example_pointer"], "/中文~1a~0b/seed")

    def test_malformed_utf8_never_guessed_encoding(self):
        r = audit.inspect_json_bytes(b'{"seed":5,"x":"\xff"}')
        self.assertFalse(r["parse_complete"])

    def test_blob_must_be_native_bytes(self):
        for x in ('{"seed":5}', bytearray(b"{}"), None, {}, b"".__class__):
            with self.assertRaises(ready.ProtocolError):
                audit.inspect_json_bytes(x)

    def test_registry_stage_lists_are_declared_not_science_completion(self):
        obj = {"schema": "rfl-a96-seed-registry-v1",
            "scientific": {"smoke": [5, 6], "confirmatory": None},
            "engineering": {"dev_baseline": [20]}}
        self.assertEqual(sorted(self.values(obj)), [5, 6, 20])
        self.assertTrue(self.parse(obj)["issues"])

    def test_generic_scientific_engineering_results_are_not_integer_harvest(self):
        obj = {"scientific": {"sample_count": 400}, "engineering": {"elapsed": 20}}
        self.assertFalse(self.values(obj))

    def test_seed_container_metadata_not_blindly_harvested(self):
        r = self.parse({"seeds": {"count": 400, "offset": 123}})
        self.assertFalse(r["claims"])
        self.assertEqual(r["issues"][0]["reason"],
                         "declared-seed-container-has-unrecognized-members")

    def test_scalar_seeds12_or_stage400_can_be_count_not_identity(self):
        for obj in ({"seeds": 12}, {"scientific_seeds": 400},
                    {"scientific_seed_sets": {"primary": 400, "secondary": 200}}):
            r = self.parse(obj)
            self.assertFalse(r["claims"])
            self.assertEqual(r["issues"][0]["reason"],
                             "scalar-seed-container-may-be-count-not-identity")

    def test_recognized_stage_container_only_uses_declared_keys(self):
        self.assertEqual(self.values({"scientific_seed_sets_reserved":
            {"smoke": [5], "development": [6], "treatment": None}}), [5, 6])

    def test_unknown_schedule_and_external_reference_remain_gaps(self):
        obj = {"seed_base": 800, "seed_offset": 20, "seed_files": "dev.txt",
               "seed_registry": "other.json"}
        r = self.parse(obj)
        self.assertFalse(r["claims"])
        self.assertEqual(r["issues"][0]["occurrences"], 4)

    def test_filename_or_seed_count_alone_proves_no_literal_key(self):
        r = self.parse({"filename": "B4_standard_seed11.json", "seed_count": 400})
        self.assertFalse(r["claims"])

    def test_generic_key_and_epoch_or_pid_not_environment_seed(self):
        self.assertFalse(self.values({"key": 800, "keys": [5], "epoch": 465,
                                      "pid": 26592, "ticks": 639271289413910189}))

    def test_old_science_and_inclusive_registry_ranges_exact(self):
        r = self.parse({"permanent_exclusions": {"old_scientific": [5, 6],
            "old_engineering_ranges": [[10, 12]], "operational_fixture_ranges": [[13, 20]]}})
        self.assertEqual([r["original_integer"] for r in r["claims"]], [5, 6])
        self.assertEqual(r["intervals_inclusive"], [[10, 20]])

    def test_range_like_outcome_field_not_registry_range(self):
        self.assertEqual(self.parse({"old_engineering_ranges": [[10, 12]]})
                         ["intervals_inclusive"], [])

    def test_invalid_ranges_leave_explicit_gap_not_prefix(self):
        for x in ([[11, 10]], [[0, 1 << 64]], [[False, 2]], [10, 20],
                  [[10, 20], [5, 4]]):
            r = self.parse({"permanent_exclusions": {"old_engineering_ranges": x}})
            self.assertFalse(r["intervals_inclusive"])
            self.assertTrue(r["issues"])

    def test_interval_union_never_expands_uint64_domain(self):
        self.assertEqual(audit.merge_intervals([[0, (1 << 64) - 1], [5, 10]]),
                         [[0, (1 << 64) - 1]])

    def test_interval_union_unsorted_overlap_adjacent_closed_endpoints(self):
        self.assertEqual(audit.merge_intervals([[12, 15], [5, 10], [8, 12], [18, 18]]),
                         [[5, 15], [18, 18]])

    def test_mixed_tuple_list_interval_sort_has_one_exact_representation(self):
        self.assertEqual(audit.merge_intervals([(10, 12), [0, 4], [5, 9]]), [[0, 12]])
        self.assertEqual(audit.subtract_intervals([[0, 12]], [(0, 4), [10, 12]]), [[5, 9]])

    def test_bad_interval_types_refused(self):
        for x in (None, (), [[-1, 5]], [[5, 4]], [[0, 1.0]], [[0]], [[0, True]]):
            with self.assertRaises(ready.ProtocolError): audit.merge_intervals(x)

    def test_set_difference_exact_closed_endpoints_and_huge_ranges(self):
        self.assertEqual(audit.subtract_intervals([[0, 20]], [[0, 4], [10, 15], [20, 20]]),
                         [[5, 9], [16, 19]])
        self.assertEqual(audit.subtract_intervals([[0, (1 << 64) - 1]],
            [[0, (1 << 64) - 2]]), [[(1 << 64) - 1, (1 << 64) - 1]])

    def test_missing_registry5_to11_gap_is_not_unused_key_list(self):
        self.assertEqual(audit.subtract_intervals([[0, 11]], [[0, 4]]), [[5, 11]])

    def test_no_match_returns_parsed_but_never_complete_history(self):
        r = self.parse({"metric": [465, 400, 1.5]})
        self.assertTrue(r["parse_complete"])
        self.assertEqual(r["claims"], [])

    def test_parser_is_deterministic_with_input_untouched(self):
        x = {"seeds": [7, 5, 7]}
        old = deepcopy(x)
        self.assertEqual(self.parse(x), self.parse(x))
        self.assertEqual(x, old)

    def test_parser_case_sensitive_unknown_seed_name_not_assumed(self):
        self.assertFalse(self.values({"SEED": 7, "seed_unused": 8}))

    def test_scope_cannot_be_caller_overridden(self):
        self.assertEqual(tuple(inspect.signature(audit.snapshot_retained_history).parameters), ())
        for k in ("roots", "output", "seed", "callback", "allocate", "collection_authorized"):
            with self.assertRaises(TypeError):
                audit.snapshot_retained_history(**{k: None})

    def test_scope_guard_binds_original_parent_and_source_bytes(self):
        base, names = audit._scope_guard()
        self.assertEqual(base.resolve(), ready.ROOT.parent)
        self.assertEqual(len(names), 10)
        with patch.object(audit, "_BINDING", ()):
            with self.assertRaises(ready.ProtocolError): audit._scope_guard()
        with patch.dict(audit._SCOPE, {"collection_authorized": True}):
            with self.assertRaises(ready.ProtocolError): audit._scope_guard()

    def mock_snapshot(self, *, mutate=False, missing=False):
        base = ready.ROOT.parent
        root = base / "RFL-handoff-20260926"
        path = root / "imaginary-seed-evidence.json"
        data = b'{"seed":11,"n_seeds":400}'
        real_read = Path.read_bytes
        def read(p):
            return data if p == path else real_read(p)
        real_hash = ready.file_hash
        def file_hash(p):
            if Path(p) == path:
                return "0" * 64 if mutate else audit._digest(data)
            return real_hash(p)
        with patch.object(audit, "_scope_guard", return_value=(base, (root.name,))), \
             patch.object(audit, "_walk", return_value=([path], [], [])), \
             patch.object(audit, "_reparse", return_value=missing), \
             patch.object(Path, "read_bytes", read), \
             patch.object(Path, "stat") as mocked_stat, \
             patch.object(ready, "file_hash", side_effect=file_hash):
            # is_dir uses stat; supply an actual directory mode for the root.
            from types import SimpleNamespace
            mocked_stat.return_value = SimpleNamespace(st_size=len(data), st_mode=0o040755)
            return audit.snapshot_retained_history()

    def test_mock_root_snapshot_binds_actual_bytes_not_descriptor_sha(self):
        r = self.mock_snapshot()
        row = r["payload"]["file_evidence"][0]["records"][0]
        self.assertEqual(row["sha256"], audit._digest(b'{"seed":11,"n_seeds":400}'))
        self.assertEqual(row["claims"][0]["original_integer"], 11)
        self.assertTrue(r["all_available_roots_stable"])

    def test_boundary_source_drift_is_visible_never_freshness_pass(self):
        r = self.mock_snapshot(mutate=True)
        self.assertFalse(r["all_available_roots_stable"])
        self.assertEqual(r["payload"]["file_evidence"][0]["records"][0]["gap"],
                         "bytes-moved-at-root-boundary")

    def test_missing_or_reparse_root_kept_as_gap_not_empty_pass(self):
        r = self.mock_snapshot(missing=True)
        self.assertFalse(r["all_available_roots_stable"])
        self.assertFalse(r["payload"]["roots"][0]["available"])
        self.assertEqual(r["payload"]["file_evidence"], [])

    def test_all_authority_flags_remain_closed_even_stable_mock_evidence(self):
        r = self.mock_snapshot()
        for k in ("complete_historical_usage_freshness_audit",
                  "seed_plan_v14_exclusions_automatically_extended",
                  "keys_allocated_or_reserved", "native_protocol_or_training_started",
                  "collection_authorized", "scientific_claim_authorized", "research_complete"):
            self.assertIs(r[k], False)
        self.assertEqual(r["environment_key_draws"], 0)

    def test_no_sampler_trainer_reservation_or_collection_entry(self):
        for name in ("collect", "allocate", "reserve", "sample", "retry", "issue_permit",
                     "train", "launch", "freeze", "write", "activate_collection_gate"):
            self.assertFalse(hasattr(audit, name), name)


if __name__ == "__main__":
    unittest.main()

