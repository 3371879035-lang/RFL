"""Pure static parser fixtures. No environment draw or historical execution."""
import ast
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import history_schedule_candidate as schedules
import readiness as ready


class StaticPythonTests(unittest.TestCase):
    def parse(self, source):
        return schedules.inspect_python_bytes(source.encode("utf-8"))

    def intervals(self, source):
        return self.parse(source)["intervals_inclusive"]

    def test_literal_single(self):
        self.assertEqual(self.intervals("seed = 11"), [[11, 11]])

    def test_decimal_underscore(self):
        self.assertEqual(self.intervals("train(seed=4_700_000)"), [[4700000, 4700000]])

    def test_seed_count_not_identity(self):
        r = self.parse("seeds = 400")
        self.assertEqual(r["claims"], [])
        self.assertIn("plural-scalar", r["issues"][0]["reason"])

    def test_nonseed_numbers_not_harvested(self):
        self.assertEqual(self.intervals("PID=26592\nticks=639271289413910189\nmetric=465"), [])

    def test_list_range_closed(self):
        self.assertEqual(self.intervals("SEEDS=tuple(range(10,13))"), [[10, 12]])

    def test_negative_step_range(self):
        self.assertEqual(self.intervals("SEEDS=list(range(13,10,-1))"), [[11, 13]])

    def test_literal_comprehension(self):
        self.assertEqual(self.intervals("seeds=[10+i for i in range(3)]"), [[10, 12]])

    def test_generator_tuple(self):
        self.assertEqual(self.intervals("KEYS=tuple(10+i for i in range(3))"), [[10, 12]])

    def test_comprehension_filter_unresolved(self):
        self.assertEqual(self.intervals("seeds=[i for i in range(3) if i]"), [])

    def test_module_integer_constant(self):
        self.assertEqual(self.intervals("BASE=1<<63\nseeds=[BASE+i for i in range(3)]"), [[1<<63, (1<<63)+2]])

    def test_reassigned_constant_not_resolved(self):
        self.assertEqual(self.intervals("BASE=10\nBASE=20\nseed=BASE"), [])

    def test_function_arg_masks_module_constant(self):
        self.assertEqual(self.intervals("BASE=10\ndef f(BASE):\n    seed=BASE"), [])

    def test_local_assignment_masks_module_constant(self):
        self.assertEqual(self.intervals("BASE=10\ndef f():\n    BASE=20\n    seed=BASE"), [])

    def test_constant_lexical_for(self):
        self.assertEqual(self.intervals("for i in range(3):\n    train(seed=10+i)"), [[10, 12]])

    def test_loop_else_not_bound(self):
        self.assertEqual(self.intervals("for i in range(3):\n    pass\nelse:\n    seed=10+i"), [])

    def test_default_is_conditional_not_observed(self):
        r = self.parse('def f():\n    ap.add_argument("--seeds",type=int,default=2)\n    for s in range(args.seeds):\n        train(seed=4700000+s)')
        self.assertEqual(r["intervals_inclusive"], [[4700000, 4700001]])
        self.assertEqual(r["claims"][0]["CLI_default_conditions"][0]["count"], 2)
        self.assertTrue(r["issues"])
        self.assertFalse(r["all_runtime_flows_resolved"])

    def test_default_none_unresolved(self):
        self.assertEqual(self.intervals('def f():\n    ap.add_argument("--seeds",default=None)\n    for s in range(args.seeds):\n        seed=4700000+s'), [])

    def test_duplicate_cli_defaults_unresolved(self):
        self.assertEqual(self.intervals('def f():\n    ap.add_argument("--seeds",default=2)\n    ap.add_argument("--seeds",default=4)\n    for s in range(args.seeds):\n        seed=4700000+s'), [])

    def test_two_loop_binders_unresolved(self):
        self.assertEqual(self.intervals("for i in range(2):\n    for j in range(3):\n        seed=i+j"), [])

    def test_dict_seed_fields(self):
        self.assertEqual(self.intervals('x={"seed":11,"seeds":[12,13],"episodes":465}'), [[11, 13]])

    def test_bool_float_not_identity(self):
        self.assertEqual(self.intervals("seed=True\ntrain(seed=11.0)"), [])

    def test_negative_original_alias(self):
        r = self.parse("seed=-1")
        self.assertEqual(r["claims"][0]["original_integers"], [-1])
        self.assertEqual(r["intervals_inclusive"], [[(1<<64)-1, (1<<64)-1]])

    def test_overwide_original_alias(self):
        self.assertEqual(self.intervals("seed=(1<<64)+11"), [[11, 11]])

    def test_sequence_and_power_resource_limits(self):
        self.assertEqual(self.intervals("seeds=list(range(100000000000))\nseed=2**100000000"), [])

    def test_zero_range_step_unresolved(self):
        self.assertEqual(self.intervals("seeds=list(range(1,2,0))"), [])

    def test_malformed_whole_source_no_prefix(self):
        r = self.parse("seed=11\nif (")
        self.assertFalse(r["syntax_complete"])
        self.assertEqual(r["claims"], [])

    def test_malicious_call_never_invoked(self):
        # ast.walk legitimately imports stdlib collections.deque. The boundary
        # is no historical expression evaluation/call, not no stdlib import.
        with patch("builtins.eval", side_effect=AssertionError("must not eval")), patch("os.system", side_effect=AssertionError("must not dispatch historical call")) as command:
            self.assertEqual(self.intervals('seed=__import__("os").system("echo bad")'), [])
            command.assert_not_called()

    def test_expression_depth_limit(self):
        node = ast.Constant(value=1)
        for _ in range(40):
            node = ast.UnaryOp(op=ast.UAdd(), operand=node)
        with self.assertRaises(schedules.Unresolved):
            schedules._expr(node)

    def test_duplicate_dict_seed_list_refused(self):
        r = self.parse('STAGE_SEEDS={"smoke":[11],"smoke":[12]}')
        self.assertEqual(r["claims"], [])

    def test_nested_stage_lists(self):
        self.assertEqual(self.intervals('STAGE_SEEDS={"smoke":tuple(range(11,13)),"dev":[14]}'), [[11, 12], [14, 14]])


class StaticConfigTests(unittest.TestCase):
    def parse(self, obj):
        return schedules.inspect_json_schedules(json.dumps(obj).encode())

    def test_json_base_count_envelope_not_runtime_law(self):
        r = self.parse({"experiment": {"seed_base": 11, "seeds": 3}})
        self.assertEqual(r["intervals_inclusive"], [[11, 13]])
        self.assertIn("NOT_VERIFIED_GENERATOR_LAW", r["claims"][0]["role"])

    def test_count_alone_not_identity(self):
        self.assertEqual(self.parse({"seeds": 400})["intervals_inclusive"], [])

    def test_missing_count_keeps_gap(self):
        self.assertEqual(self.parse({"seed_base": 11})["claims"], [])

    def test_noninteger_count_keeps_gap(self):
        self.assertEqual(self.parse({"seed_base": 11, "seeds": True})["claims"], [])

    def test_negative_count_refused(self):
        self.assertEqual(self.parse({"seed_base": 11, "seeds": -1})["claims"], [])

    def test_empty_envelope(self):
        self.assertEqual(self.parse({"seed_base": 11, "seeds": 0})["intervals_inclusive"], [])

    def test_wrap_interval_split(self):
        self.assertEqual(schedules._alias_intervals((1<<64)-1, 3), [[0, 1], [(1<<64)-1, (1<<64)-1]])

    def test_full_alias_cycle_compact(self):
        self.assertEqual(schedules._alias_intervals(11, 1<<64), [[0, (1<<64)-1]])

    def test_negative_base_preserved(self):
        r = self.parse({"seed_base": -1, "seeds": 2})
        self.assertEqual(r["claims"][0]["base_original"], -1)

    def test_malformed_json_no_prefix(self):
        r = schedules.inspect_json_schedules(b'{"seed_base":11,"seeds":2}xxx')
        self.assertFalse(r["parse_complete"])
        self.assertEqual(r["claims"], [])

    def test_duplicate_json_no_prefix(self):
        r = schedules.inspect_json_schedules(b'{"seed_base":11,"seeds":2,"seeds":3}')
        self.assertFalse(r["parse_complete"])

    def test_nonfinite_json_refused(self):
        self.assertFalse(schedules.inspect_json_schedules(b'{"seed_base":11,"seeds":2,"metric":1e999}')["parse_complete"])

    def test_reference_not_read_by_parser(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("no parser file reads")):
            r = self.parse({"seed_file": "docs/rebuild/smoke_seeds.txt"})
        self.assertEqual(r["references"][0]["declaration"], "docs/rebuild/smoke_seeds.txt")

    def test_yaml_flat_experiment(self):
        r = schedules.inspect_yaml_experiment(b"experiment:\n  name: old\n  seeds: 3\n  seed_base: 11\nnext:\n  seed: 999\n")
        self.assertEqual(r["intervals_inclusive"], [[11, 13]])
        self.assertFalse(r["whole_yaml_validated"])

    def test_yaml_count_not_key(self):
        r = schedules.inspect_yaml_experiment(b"experiment:\n  seeds: 400\n")
        self.assertFalse(r["experiment_block_parsed"])
        self.assertEqual(r["intervals_inclusive"], [])

    def test_yaml_duplicate_field_refused(self):
        r = schedules.inspect_yaml_experiment(b"experiment:\n  seeds: 2\n  seeds: 3\n  seed_base: 11\n")
        self.assertEqual(r["claims"], [])

    def test_yaml_multiple_experiment_refused(self):
        r = schedules.inspect_yaml_experiment(b"experiment:\n  seeds: 2\n  seed_base: 11\nexperiment:\n  seeds: 3\n")
        self.assertEqual(r["claims"], [])

    def test_yaml_alias_tag_merge_tab_nested_refused(self):
        for line in ("  seed_base: &base 11", "  seed_base: *base", "  seed_base: !!int 11", "  <<: *base", "\tseed_base: 11", "    seed_base: 11"):
            with self.subTest(line=line):
                self.assertEqual(schedules.inspect_yaml_experiment(("experiment:\n  seeds: 2\n"+line+"\n").encode())["claims"], [])

    def test_yaml_comment_does_not_change_count(self):
        r = schedules.inspect_yaml_experiment(b"experiment: # old\n  seeds: 2 # count\n  seed_base: 11 # key\n")
        self.assertEqual(r["intervals_inclusive"], [[11, 12]])


class StaticReferenceTests(unittest.TestCase):
    def test_root_relative_txt_only(self):
        self.assertEqual(schedules.reference_path("docs/rebuild/smoke_seeds.txt"), "docs/rebuild/smoke_seeds.txt")

    def test_escape_absolute_other_extension_noncanonical_refused(self):
        for value in ("../seeds.txt", "/seeds.txt", "D:/seeds.txt", "docs\\seeds.txt", "docs//seeds.txt", "./seeds.txt", "seeds.json", None):
            with self.subTest(value=value), self.assertRaises(schedules.Unresolved):
                schedules.reference_path(value)

    def test_seed_file_comments_and_originals(self):
        r = schedules.inspect_seed_text(b"# declared list\n11\n-1 # original\n")
        self.assertEqual(r["original_integers"], [11, -1])

    def test_bad_seed_file_discards_whole_prefix(self):
        r = schedules.inspect_seed_text(b"11\n12.0\n")
        self.assertFalse(r["parse_complete"])
        self.assertEqual(r["original_integers"], [])

    def test_empty_seed_file_not_pass(self):
        self.assertFalse(schedules.inspect_seed_text(b"# empty\n")["parse_complete"])

    def test_reference_descriptor_actual_hash_not_payload(self):
        self.assertEqual(schedules._reference_leaves({"smoke": {"path": "seeds.txt", "sha256": "declared"}}, "/seed_files"), [("/seed_files/smoke", "seeds.txt", "declared")])

    def test_unknown_reference_container_gap(self):
        self.assertEqual(schedules._reference_leaves({"unknown": "seeds.txt"}, "/seed_files"), [("/seed_files", None, None)])

    def test_closed_snapshot_signature(self):
        self.assertEqual(list(inspect.signature(schedules.snapshot_static_schedules).parameters), [])

    def test_native_bytes_required(self):
        for parser in (schedules.inspect_python_bytes, schedules.inspect_json_schedules, schedules.inspect_yaml_experiment, schedules.inspect_seed_text):
            with self.subTest(parser=parser.__name__), self.assertRaises(ready.ProtocolError):
                parser("seed=11")

    def test_source_has_no_historical_import_or_training_entry(self):
        source = Path(schedules.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertFalse(set(names) & {"eval", "exec", "compile", "__import__", "train", "main"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
