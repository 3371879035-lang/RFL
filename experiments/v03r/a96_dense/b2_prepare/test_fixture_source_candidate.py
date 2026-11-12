"""Source-parser construction tests; no environment keys, runs or allocations."""
import ast
import hashlib
import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_source_candidate as c


class FixtureSourceTests(unittest.TestCase):
    def parse(self, text):
        return c.inspect_fixture_python_bytes(text.encode("utf-8"))
    def aliases(self, result):
        rows = result["fixture_alias_intervals"]
        return {x for a, b in rows for x in range(int(a), int(b) + 1)}
    def test_native_bytes_only_no_duck_input(self):
        for value in ("seed=1", bytearray(b"seed=1"), None, 1):
            with self.assertRaises(TypeError): c.inspect_fixture_python_bytes(value)
    def test_whole_invalid_syntax_discards_prefix(self):
        a = self.parse("seed=42\nthis (is broken")
        self.assertIs(a["parse_complete"], False); self.assertEqual(a["claims"], [])
    def test_whole_invalid_utf8_discards_prefix(self):
        a = c.inspect_fixture_python_bytes(b"seed=42\n\xff")
        self.assertFalse(a["parse_complete"]); self.assertEqual(a["fixture_alias_intervals"], [])
    def test_byte_budget_discards_all(self):
        with patch.object(c, "MAX_BYTES", 5):
            self.assertFalse(self.parse("seed=12")["parse_complete"])
    def test_node_budget_discards_all(self):
        with patch.object(c, "MAX_NODES", 1):
            self.assertFalse(self.parse("seed=12")["parse_complete"])
    def test_utf8_BOM_accepted_whole(self):
        a = c.inspect_fixture_python_bytes(b"\xef\xbb\xbfseed=42")
        self.assertEqual(self.aliases(a), {42})
    def test_arbitrary_numbers_outcomes_counts_not_harvested(self):
        a = self.parse("world=77\nT=465\nRMST=1.5\nn_seeds=400\nseed_count=200\nCPU=1024\n")
        self.assertEqual(a["claims"], [])
    def test_scalar_and_declared_dict_and_keyword_fields(self):
        a = self.parse('seed=41\nrow={"scenario_seed":42}\nf(algorithm_seed=43)')
        self.assertEqual(self.aliases(a), {41, 42, 43})
    def test_bool_float_fraction_string_not_native_seed(self):
        for value in ("True", "False", "1.0", "'2'", "Fraction(2)", "None"):
            a = self.parse("seed=" + value)
            self.assertEqual(a["claims"], []); self.assertTrue(a["gaps"])
    def test_exact_negative_overwide_originals_and_modulo_alias(self):
        a = self.parse("seeds=[-1, (1<<64)+7]")
        self.assertEqual(self.aliases(a), {(1 << 64) - 1, 7})
        self.assertEqual(a["claims"][0]["original_integers_decimal"], ["-1", str((1<<64)+7)])
    def test_decimal_strings_do_not_round_64bit_endpoints(self):
        a = self.parse("seed=(1<<64)-1")
        self.assertEqual(a["fixture_alias_intervals"], [[str((1<<64)-1)] * 2])
    def test_native_shift_and_add_subtract_mult(self):
        a = self.parse("seed=(1<<6)+3*7-1")
        self.assertEqual(self.aliases(a), {84})
    def test_excess_shift_int_bits_and_unsupported_ops_refused(self):
        for expr in ("1<<256", "1<<-1", "1/2", "1**100", "1%2", "1>>2"):
            a = self.parse("seed=" + expr); self.assertEqual(a["claims"], [])
    def test_flat_and_nested_lists_are_ordered_literal_occurrences(self):
        a = self.parse("primary_blocks=[[1,2],[2,3]]")
        self.assertEqual(a["claims"][0]["literal_occurrences"], 4)
        self.assertEqual(self.aliases(a), {1,2,3})
    def test_scalar_plural_may_be_count_not_identity(self):
        a = self.parse("seeds=400")
        self.assertEqual(a["claims"], []); self.assertTrue(a["gaps"])
    def test_range_list_and_tuple_constructor_bounded(self):
        a = self.parse("seeds=list(range(7,12,2))\nKEYS=tuple(range(2))")
        self.assertEqual(self.aliases(a), {0,1,7,9,11})
    def test_item_budget_no_prefix_keys_retained(self):
        with patch.object(c, "MAX_ITEMS", 2):
            a = self.parse("seeds=list(range(4))")
            self.assertEqual(a["claims"], []); self.assertEqual(a["fixture_alias_intervals"], [])
    def test_two_nested_comprehensions_original600_nominal_labels(self):
        a = self.parse('def proposal():\n base=1<<63\n return {"primary_blocks": [[base+b*100+i for i in range(100)] for b in range(4)], "secondary_blocks": [[base+400+b*100+i for i in range(100)] for b in range(2)]}')
        self.assertEqual(a["fixture_alias_intervals"], [[str(1<<63), str((1<<63)+599)]])
        self.assertEqual(sum(x["literal_occurrences"] for x in a["claims"]), 600)
    def test_multiple_generator_comprehension_bounded(self):
        a = self.parse("seeds=[i*10+j for i in range(2) for j in range(2)]")
        self.assertEqual(self.aliases(a), {0,1,10,11})
    def test_filtered_async_complex_target_comp_refused(self):
        for expr in ("[i for i in range(3) if i]", "[a for a,b in [(1,2)]]"):
            self.assertEqual(self.parse("seeds="+expr)["claims"], [])
    def test_module_preceding_unique_arithmetic_aliases(self):
        a = self.parse("BASE=10\nOFFSET=BASE+2\nseeds=[OFFSET,BASE]")
        self.assertEqual(self.aliases(a), {10,12})
    def test_module_changed_constant_not_trusted(self):
        a = self.parse("BASE=10\nBASE=20\nseed=BASE")
        self.assertEqual(a["claims"], [])
    def test_function_local_unique_preceding_constant(self):
        a = self.parse('def f():\n base=12\n return {"seeds":[base,base+1]}')
        self.assertEqual(self.aliases(a), {12,13})
    def test_local_shadow_of_module_unknown_not_leak(self):
        a = self.parse('BASE=12\ndef f(BASE):\n return {"seed":BASE}')
        self.assertEqual(a["claims"], [])
    def test_later_local_definition_not_dominating(self):
        a = self.parse('BASE=12\ndef f():\n x={"seed":BASE}\n BASE=13\n return x')
        self.assertEqual(a["claims"], [])
    def test_local_mutated_or_deleted_variable_not_trusted(self):
        for op in ("base=13", "base+=1", "del base"):
            a = self.parse('def f():\n base=12\n '+op+'\n return {"seed":base}')
            self.assertEqual(a["claims"], [])
    def test_control_flow_before_local_constant_not_certified(self):
        a = self.parse('def f(x):\n if x: return None\n base=12\n return {"seed":base}')
        self.assertEqual(a["claims"], [])
    def test_function_local_builtin_shadow_not_called_or_leaked(self):
        for text in ('def f(range):\n return {"seeds":list(range(3))}',
                     'range=custom\nseeds=list(range(3))'):
            self.assertEqual(self.parse(text)["claims"], [])
    def test_unknown_global_attribute_callback_import_not_executed(self):
        a = self.parse('import malicious\nseed=malicious.steal()\nseeds=factory()')
        self.assertEqual(a["claims"], []); self.assertTrue(a["gaps"])
    def test_nested_closure_kept_unresolved(self):
        a = self.parse('def f():\n base=12\n def g():\n  return {"seed":base}\n return g')
        self.assertEqual(a["claims"], [])
    def test_literal_for_body_binding_conservative_fixture(self):
        a = self.parse('for x in (12,13):\n row={"seed":x}')
        self.assertEqual(self.aliases(a), {12,13})
    def test_nested_for_literal_body_bindings(self):
        a = self.parse('for x in range(2):\n for y in range(2):\n  row={"seed":x*10+y}')
        self.assertEqual(self.aliases(a), {0,1,10,11})
    def test_mutated_for_variable_kept_unresolved(self):
        a = self.parse('for x in (12,13):\n x+=1\n row={"seed":x}')
        self.assertEqual(a["claims"], [])
    def test_for_else_and_unknown_iterator_kept_unresolved(self):
        for text in ('for x in (12,13):\n pass\nelse:\n row={"seed":x}',
                     'for x in args.seeds:\n row={"seed":x}'):
            self.assertEqual(self.parse(text)["claims"], [])
    def test_refuse_key_literal_or_bound_loop_is_rejection_fixture(self):
        a = self.parse('for x in (-1, (1<<64)+7):\n self.refuse_key(x)')
        self.assertEqual(self.aliases(a), {(1<<64)-1,7})
        self.assertEqual(a["claims"][0]["role"], "REJECTED_INPUT_FIXTURE_LABEL_NOT_ENVIRONMENT_USE")
    def test_direct_subscript_mutation_rhs_captured_not_target_indices(self):
        a = self.parse('p["engineering_keys"]=[77]\np["primary_blocks"]=[list(range(80,82))]')
        self.assertEqual(self.aliases(a), {77,80,81})
    def test_synthetic_huge_range_envelope_never_fixture_key_union(self):
        a = self.parse('r["old_engineering_ranges"]=[[1<<63,(1<<64)-1]]')
        self.assertEqual(a["fixture_alias_intervals"], [])
        self.assertEqual(a["synthetic_range_envelopes"][0]["intervals_inclusive_decimal"], [[str(1<<63),str((1<<64)-1)]])
    def test_augmented_synthetic_envelope_rhs_separate_not_full_value(self):
        a = self.parse('r["old_engineering_ranges"] += [[1<<63,(1<<64)-1]]')
        self.assertEqual(a["claims"], []); self.assertEqual(len(a["synthetic_range_envelopes"]), 1)
        self.assertTrue(a["gaps"])
    def test_bad_range_shape_and_bounds_not_salvaged(self):
        for value in ("[[1,2,3]]", "[[2,1]]", "[[0,1<<64]]", "[[True,2]]"):
            a = self.parse('r["old_engineering_ranges"]='+value)
            self.assertEqual(a["fixture_alias_intervals"], [])
            self.assertEqual(a["synthetic_range_envelopes"], [])
    def test_augmented_seed_mutation_not_complete_declaration(self):
        a = self.parse("seeds += [77]")
        self.assertEqual(a["claims"], []); self.assertTrue(a["gaps"])
    def test_malformed_embedded_JSON_prefix_not_harvested(self):
        a = self.parse("raw=b'{\"seed\":42} broken'")
        self.assertEqual(a["claims"], []); self.assertTrue(a["gaps"])
    def test_embedded_python_payload_not_imported_or_reinterpreted(self):
        a = self.parse("raw='seed=42'")
        self.assertEqual(a["claims"], []); self.assertTrue(a["gaps"])
    def test_union_sorted_exact_with_adjacent_and_disjoint_aliases(self):
        a = self.parse("seeds=[5,2,3,2,6,9]")
        self.assertEqual(a["fixture_alias_intervals"], [["2","3"],["5","6"],["9","9"]])
    def test_no_runtime_coverage_or_allocation_flags_promoted(self):
        a = self.parse("seeds=[2,3]")
        self.assertIs(a["runtime_flows_complete"], False)
        self.assertIs(a["runtime_key_use_proved"], False)
        self.assertTrue(all(x["environment_key_use_proved"] is False for x in a["claims"]))
    def test_parse_result_is_detached_and_deterministic(self):
        a = self.parse("seeds=[2,3]"); a["claims"][0]["field"]="tampered"
        self.assertEqual(self.parse("seeds=[2,3]")["claims"][0]["field"], "seeds")
    def test_API_closed_no_scope_output_seed_or_callback_override(self):
        self.assertEqual(tuple(inspect.signature(c.snapshot_preparation_fixtures).parameters), ())
        self.assertEqual(tuple(inspect.signature(c.inspect_fixture_python_bytes).parameters), ("blob",))
        with self.assertRaises(TypeError): c.snapshot_preparation_fixtures(seed=1)
    def test_no_collection_allocator_trainer_sampler_entry_points(self):
        for name in ("collect","allocate","reserve","sample","retry","train","freeze","write"):
            self.assertFalse(hasattr(c,name))
    def test_original_v14_bound_proposal603_and_separate_interval_challenge(self):
        path = Path(__file__).parent / "test_seed_plan_candidate.py"
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "a922c4a2ac2e7ac1269479ba7b87f587b2795081c137ddbc30b02a8e677f82e5")
        a = c.inspect_fixture_python_bytes(raw)
        claims = [r for r in a["claims"] if r["line"] < 30]
        self.assertEqual(sum(r["literal_occurrences"] for r in claims), 603)
        self.assertTrue(any(r["field"]=="primary_blocks" and len(r["original_integers_decimal"])==400 for r in claims))
        self.assertTrue(any(r["field"]=="secondary_blocks" and len(r["original_integers_decimal"])==200 for r in claims))
        self.assertTrue(a["synthetic_range_envelopes"])
        # This source never supports an environmental-used-key interval
        # base..UINT64_MAX; envelope and bounded label union stay different.
        self.assertNotIn([str(1<<63),str((1<<64)-1)], a["fixture_alias_intervals"])
    def test_contract_binds_exact_parent19_files_and_sha(self):
        data = json.loads(c.CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(len(data["bound_parent_test_sources"]),19)
        for name,wanted in data["bound_parent_test_sources"].items():
            self.assertEqual(hashlib.sha256((c.ROOT/name).read_bytes()).hexdigest(),wanted)
        self.assertFalse("test_fixture_source_candidate.py" in "\n".join(data["bound_parent_test_sources"]))
    def test_current_v19_parser_test_literals_are_not_covered_by_parent19(self):
        data = json.loads(c.CONTRACT.read_text(encoding="utf-8"))
        self.assertIn("including later source additions", data["consumer_boundary"])
        self.assertFalse(data.get("collection_authorized",False))

    def test_nested_declared_field_subscript_rhs_no_indices_as_keys(self):
        a = self.parse('p["primary_blocks"][999][998]=77')
        self.assertEqual(self.aliases(a), {77})

    def test_separate_literal_sibling_loops_may_rebind_same_name(self):
        a = self.parse('def f():\n for n in (0,1):\n  pass\n for n in (99,101):\n  p["primary_blocks"][0]=list(range(80,80+n))')
        self.assertEqual(a["fixture_alias_intervals"], [["80","180"]])


if __name__ == "__main__":
    unittest.main()

