"""Nominal dataclasses with CONSTRUCTED arrays/events, NOT acquisition records.

41 is an array/protocol fixture identifier. ExogenousEpisode.derive, rollout and
train_curve are never called. Tests do not allocate any scientific/engineering
environment keys or execute a B2 workload, and cannot establish collection PASS.
"""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
import hashlib
from pathlib import Path
import sys
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_record_candidate as bridge
import readiness as ready
from aggregate_cells_candidate import aggregate_paired_cells
from rfl_rebuild.b1.contract import APPLIED, EVALUABLE_NOOP, DecisionWriteReceipt, UpdateLedger
from rfl_rebuild.b1.laws import NoWriteRef
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.retention import select_form
from rfl_rebuild.b2.runner import ArmSpec, NoReflectionResult, PairedSceneRecord
from rfl_rebuild.b2.training import ExogenousEpisode, FutureTrainingProtocol
from rfl_rebuild.b2.unaffected import CreditedSite, EvaluationScene, UnaffectedSet
from rfl_rebuild.b2.utility import FutureUtility
from rfl_rebuild.env.kernel import ControllerSite, Outcome, State
from rfl_rebuild.learner.store import DecisionAddress


class NativeRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = ready.load_parent()
        cls.reference = ready.read_json(Path(__file__).with_name("healthy_reference_candidate.json"))
        cls.contract = ready.read_json(Path(__file__).with_name("record_contract_candidate_v3.json"))

    def fixture(self, architecture="D_Q", tier=Tier.L0_FACTUAL, law="FactualReturnWrite"):
        arms = bridge.registered_pair(architecture, tier, law)
        d = self.parent["design"]
        protocol = FutureTrainingProtocol(41, Fraction(1, 2), Fraction(1, 10), d["T"],
                   tuple(d["grid"]), bridge.prefix(d["N_eval"]), self.reference["v_pre"])
        state = State(0, 2, 0, 0, 0)
        address = (DecisionAddress(state, 0, 0) if architecture == "D_Q" else
                   ControllerSite(state, 3) if architecture == "X" else 0)
        site = CreditedSite(architecture, address)
        construction = f"E1(c={site.render()})@{d['refinement']}"
        units = (EvaluationScene(0, 0, 0, 0, 0), EvaluationScene(0, 0, 0, 0, 1))
        unaffected = UnaffectedSet(units, construction)
        names = tuple(a.name for a in arms)
        pre = hashlib.sha256(b"synthetic-pre-NOT-a-collected-learner-state").hexdigest()
        post = hashlib.sha256(b"synthetic-post-NOT-a-collected-learner-state").hexdigest()
        curves = {names[0]: tuple(.2 if e < 4 else .8 for e in protocol.grid),
                  names[1]: tuple(.4 if e < 2 else .8 for e in protocol.grid)}
        utility = {n: FutureUtility.from_curve(v, protocol.grid, pre_level=protocol.v_pre,
                   t_max=protocol.t_max) for n, v in curves.items()}
        retain = {n: select_form(d["retention"]["form"])(v, protocol.grid,
                   **d["retention"]["parameters"]) for n, v in curves.items()}
        canon = bridge.SLICES[architecture].domain.canonical(address)
        receipts = (DecisionWriteReceipt(address, EVALUABLE_NOOP, False, canon),
                    DecisionWriteReceipt(address, APPLIED, True, canon))
        scalar = architecture == "D_Q"
        ledgers = {names[0]: UpdateLedger((receipts[0],), pre, pre, scalar),
                   names[1]: UpdateLedger((receipts[1],), pre, post, scalar,
                                1 if scalar else 0, .3 if scalar else 0., .3 if scalar else 0.)}
        record = PairedSceneRecord(names, architecture, construction, len(units), d["retention"]["form"],
                   MappingProxyType(utility), MappingProxyType({names[0]: 0., names[1]: .03}),
                   MappingProxyType(retain), MappingProxyType(ledgers),
                   MappingProxyType({n: pre for n in names}),
                   MappingProxyType({names[0]: pre, names[1]: post}),
                   tuple((n, 41, protocol.t_max, protocol.grid, d["N_eval"], protocol.v_pre) for n in names))
        capture = bridge.TraceCapture()
        for event in (("unaffected", unaffected, id(unaffected)), ("pre_map", 111, unaffected.size),
                      ("update_applied", names[0], 222), ("update_applied", names[1], 333),
                      ("training_protocol", names[0], id(protocol)),
                      ("future", names[0], (curves[names[0]], protocol.grid)),
                      ("training_protocol", names[1], id(protocol)),
                      ("future", names[1], (curves[names[1]], protocol.grid)),
                      ("collateral_state", names[0], pre), ("collateral_state", names[1], post)):
            capture(*event)
        return {"record": record, "capture": capture, "arms": arms, "protocol": protocol,
                "parent": self.parent, "reference": self.reference, "seed": 41,
                "cell_id": "CONSTRUCTED-array-cell-NOT-population", "regime": "P",
                "credited_site": site, "factual_outcome": Outcome.COLLISION}

    def call(self, **changes):
        x = self.fixture(); x.update(changes)
        return bridge.extract_paired_record(**x)

    def reject(self, x):
        with self.assertRaises(ready.ProtocolError):
            bridge.extract_paired_record(**x)

    def replace_map(self, x, field, key, value):
        m = dict(getattr(x["record"], field)); m[key] = value
        x["record"] = replace(x["record"], **{field: MappingProxyType(m)})

    def change_event(self, x, index, event):
        events = list(x["capture"].events); events[index] = event
        capture = bridge.TraceCapture()
        for item in events:
            capture(*item)
        x["capture"] = capture

    def test_complete_matrix_is_inherited_eight_pairs_in_fixed_order(self):
        m = bridge.frozen_matrix()
        self.assertEqual([(r["architecture"], r["tier"], r["treatment_law"]) for r in m],
            [("D_Q", "L0", "FactualReturnWrite"), ("D_Q", "L2", "CounterfactualReturnWrite"),
             ("D_Q", "L2", "DualReturnWrite"), ("D_Q", "L3", "LocalOracleRestore"),
             ("X", "L0", "X_id"), ("X", "L3", "LocalOracleRestore"),
             ("P", "L1", "P_id"), ("P", "L3", "LocalOracleRestore")])

    def test_aliases_not_additional_independent_treatments(self):
        aliases = [(r["architecture"], r["alias_of"]) for r in bridge.frozen_matrix()
                   if r["treatment_kind"] == "alias"]
        self.assertEqual(aliases, [("X", "X_id"), ("P", "P_id")])
        self.assertTrue(all(r["ceiling_not_algorithm_ranking"] for r in bridge.frozen_matrix()
                           if r["tier"] in ("L2", "L3")))

    def test_delivery_fields_are_original_cell_fields(self):
        self.assertEqual(bridge.frozen_matrix()[0]["delivery_fields"], ["a_factual", "g_factual"])
        self.assertEqual(bridge.frozen_matrix()[2]["delivery_fields"], ["a_factual", "a_plus", "g_cf", "g_factual"])
        self.assertEqual(bridge.frozen_matrix()[-1]["delivery_fields"], [])

    def test_ill_typed_cells_and_numeric_tier_aliases_refused(self):
        for a, t, law in (("P", Tier.L0_FACTUAL, "P_id"), ("X", Tier.L2_COUNTERFACTUAL, "X_id"),
                          ("D_Q", Tier.L1_CORRECTIVE, "FactualReturnWrite"), ("D_Q", 0, "FactualReturnWrite"),
                          ("D_Q", False, "FactualReturnWrite"), ("D_Q", "L0", "FactualReturnWrite")):
            with self.subTest(a=a, t=repr(t)), self.assertRaises(ready.ProtocolError):
                bridge.registered_pair(a, t, law)

    def test_no_arbitrary_law_or_reference_reference_contrast(self):
        for a, t, law in (("D_patch", Tier.L0_FACTUAL, "DeleteFactualPatch"),
                          ("D_Q", Tier.L0_FACTUAL, "NoWrite"), ("X", Tier.L0_FACTUAL, "positive-fit")):
            with self.assertRaises(ready.ProtocolError):
                bridge.registered_pair(a, t, law)

    def test_cross_tier_or_architecture_pair_refused(self):
        x = self.fixture()
        for foreign in (bridge.registered_pair("D_Q", Tier.L3_ORACLE, "LocalOracleRestore")[0],
                        bridge.registered_pair("X", Tier.L0_FACTUAL, "X_id")[0]):
            x["arms"] = (foreign, self.fixture()["arms"][1]); self.reject(x)

    def test_arm_role_reverse_or_renaming_refused(self):
        x = self.fixture(); x["arms"] = tuple(reversed(x["arms"])); self.reject(x)
        x = self.fixture(); x["arms"] = (replace(x["arms"][0], name="fake-reference"), x["arms"][1]); self.reject(x)

    def test_registry_binding_not_mutable_equal_type_standin(self):
        x = self.fixture(); a = x["arms"][0]
        x["arms"] = (ArmSpec(a.name, a.architecture, a.tier, NoWriteRef(a.tier)), x["arms"][1])
        self.reject(x)

    def test_all_eight_nominal_pairs_extract_constructed_arrays(self):
        for m in bridge.frozen_matrix():
            tier = next(t for t in Tier if t.value == m["tier_value"])
            x = self.fixture(m["architecture"], tier, m["treatment_law"])
            result = bridge.extract_paired_record(**x)
            self.assertEqual(len(result["scalar_rows"]), 4)
            self.assertEqual(result["input_payload"]["law_binding"], m)
            self.assertFalse(result["collection_authorized"])

    def test_P_outputs_four_distinct_dimensions_not_weighted_score(self):
        result = self.call()
        self.assertEqual([r["statistic"] for r in result["scalar_rows"]], list(bridge.STATISTICS))
        self.assertEqual(result["scalar_rows"][0]["reference"], 4)
        self.assertEqual(result["scalar_rows"][0]["treatment"], 2)
        self.assertNotIn("weighted_score", result)

    def test_T_statistical_rows_are_only_registered_endpoints(self):
        result = self.call(regime="T")
        self.assertEqual([r["statistic"] for r in result["scalar_rows"]], ["RMST", "DeficitAUC"])
        self.assertIn("Retention", next(iter(result["input_payload"]["values"].values())))

    def test_output_bridges_to_one_seed_aggregation_not_cell_pseudoreplication(self):
        rows = self.call()["scalar_rows"][:1]
        out = aggregate_paired_cells(rows, [41], [{"cell_id": rows[0]["cell_id"],
                    "weight_numerator": 1, "weight_denominator": 1}], regime="P", statistic="RMST")
        self.assertEqual(out, [{"seed": 41, "reference": 4., "treatment": 2.}])

    def test_exact_full_curve_original_formula_recalculation(self):
        x = self.fixture(); result = bridge.extract_paired_record(**x)
        for n in x["record"].arm_names:
            encoded = result["input_payload"]["curves"][n]
            self.assertEqual(len(encoded["episodes"]), 466)
            values = tuple(float.fromhex(h) for h in encoded["levels_hex"])
            expected = FutureUtility.from_curve(values, tuple(encoded["episodes"]),
                       pre_level=x["protocol"].v_pre, t_max=465)
            self.assertEqual(result["input_payload"]["values"][n]["DeficitAUC"], expected.deficit_auc)

    def test_right_censor_atT_and_no_recovery_remain_defined(self):
        x = self.fixture(); n = x["record"].arm_names[1]; v = (.01,)*466
        utility = FutureUtility.from_curve(v, x["protocol"].grid, pre_level=x["protocol"].v_pre, t_max=465)
        self.replace_map(x, "future_utility", n, utility)
        retention = select_form(x["record"].retention_form)(v, x["protocol"].grid,
                    **self.parent["design"]["retention"]["parameters"])
        self.replace_map(x, "retention", n, retention)
        self.change_event(x, 7, ("future", n, (v, x["protocol"].grid)))
        out = bridge.extract_paired_record(**x)["input_payload"]["values"][n]
        self.assertEqual(out["RMST"], 465); self.assertIsNone(out["tau"]); self.assertFalse(out["recovered"])

    def test_SUCCESS_NO_REFLECTION_and_unknown_terminal_not_zero_filled(self):
        for outcome in (Outcome.SUCCESS, "NOT_TERMINAL", None, False):
            x = self.fixture(); x["factual_outcome"] = outcome; self.reject(x)
        x = self.fixture(); x["record"] = NoReflectionResult(); self.reject(x)

    def test_each_native_failure_name_admitted_without_outcome_relabeling(self):
        for outcome in (Outcome.COLLISION, Outcome.TRAP, Outcome.TIMEOUT):
            self.assertEqual(self.call(factual_outcome=outcome)["input_payload"]["factual_outcome"], outcome)

    def test_no_bool_seed_or_pooled_regime_or_unnamed_cell(self):
        for changes in ({"seed": True}, {"seed": -1}, {"seed": 41.}, {"cell_id": ""},
                        {"regime": "T+P"}, {"regime": True}):
            x = self.fixture(); x.update(changes); self.reject(x)

    def test_duck_record_and_capture_refused(self):
        x = self.fixture(); x["record"] = SimpleNamespace(**{f: getattr(x["record"], f)
                    for f in x["record"].__dataclass_fields__}); self.reject(x)
        x = self.fixture(); x["capture"] = SimpleNamespace(events=x["capture"].events); self.reject(x)

    def test_source_reference_master_bank_cannot_be_substituted(self):
        x = self.fixture(); object.__setattr__(x["protocol"], "v_pre", self.parent["lock"]["v_pre"]); self.reject(x)
        x = self.fixture(); object.__setattr__(x["protocol"], "evaluation_sample", bridge.prefix(1024)); self.reject(x)

    def test_wrong_seed_alpha_epsilon_or_profile_grid_refused(self):
        for field, value in (("seed", 42), ("seed", True), ("alpha", Fraction(1, 3)),
                            ("epsilon", Fraction(1, 5)), ("t_max", 465.), ("grid", tuple(range(0, 466, 5)))):
            x = self.fixture(); object.__setattr__(x["protocol"], field, value); self.reject(x)

    def test_value_equal_boolean_grid_and_scene_aliases_refused(self):
        x = self.fixture(); grid = (False,)+x["protocol"].grid[1:]
        object.__setattr__(x["protocol"], "grid", grid); self.reject(x)
        x = self.fixture(); scene = replace(x["protocol"].evaluation_sample[0])
        object.__setattr__(scene, "kappa", False)
        object.__setattr__(x["protocol"], "evaluation_sample", (scene,)+x["protocol"].evaluation_sample[1:]); self.reject(x)

    def test_shuffled_bank_or_duplicate_unit_refused(self):
        x = self.fixture(); object.__setattr__(x["protocol"], "evaluation_sample", tuple(reversed(x["protocol"].evaluation_sample))); self.reject(x)
        x = self.fixture(); sample = x["protocol"].evaluation_sample
        object.__setattr__(x["protocol"], "evaluation_sample", (sample[1],)+sample[1:]); self.reject(x)

    def test_record_role_order_architecture_and_retention_must_match(self):
        for changes in ({"arm_names": tuple(reversed(self.fixture()["record"].arm_names))},
                        {"architecture": "X"}, {"retention_form": "RetentionFraction"}, {"unaffected_size": True}):
            x = self.fixture(); x["record"] = replace(x["record"], **changes); self.reject(x)

    def test_incomplete_extra_or_reordered_arm_mapping_refused(self):
        for field in ("future_utility", "collateral", "retention", "ledgers", "fingerprints_pre", "fingerprints_post"):
            for how in ("missing", "extra", "reverse"):
                x = self.fixture(); m = dict(getattr(x["record"], field))
                if how == "missing": m.pop(next(iter(m)))
                elif how == "extra": m["unregistered"] = next(iter(m.values()))
                else: m = dict(reversed(list(m.items())))
                x["record"] = replace(x["record"], **{field: m}); self.reject(x)

    def test_different_prestate_or_noncanonical_hash_refused(self):
        for field, value in (("fingerprints_pre", "1"*64), ("fingerprints_post", "F"*64),
                             ("fingerprints_post", "0"*63)):
            x = self.fixture(); self.replace_map(x, field, x["record"].arm_names[1], value); self.reject(x)

    def test_partial_reordered_or_false_typed_observations_refused(self):
        x = self.fixture(); x["record"] = replace(x["record"], observations=x["record"].observations[:1]); self.reject(x)
        x = self.fixture(); x["record"] = replace(x["record"], observations=tuple(reversed(x["record"].observations))); self.reject(x)
        x = self.fixture(); obs = list(x["record"].observations); r = list(obs[0]); r[1] = 41.; obs[0] = tuple(r)
        x["record"] = replace(x["record"], observations=tuple(obs)); self.reject(x)

    def test_missing_duplicate_or_reordered_recorder_sequence_refused(self):
        for mutate in (lambda e: e[:7], lambda e: e+e[-1:],
                       lambda e: e[:2]+tuple(reversed(e[2:4]))+e[4:],
                       lambda e: e[:4]+e[6:8]+e[4:6]+e[8:]):
            x = self.fixture(); capture = bridge.TraceCapture()
            for event in mutate(x["capture"].events): capture(*event)
            x["capture"] = capture; self.reject(x)

    def test_same_clone_or_distinct_protocol_objects_refused(self):
        x = self.fixture(); self.change_event(x, 3, ("update_applied", x["record"].arm_names[1], x["capture"].events[2][2])); self.reject(x)
        x = self.fixture(); self.change_event(x, 6, ("training_protocol", x["record"].arm_names[1], id(x["protocol"])+1)); self.reject(x)

    def test_unaffected_credited_site_refinement_and_shared_premap_must_bind(self):
        x = self.fixture(); x["record"] = replace(x["record"], unaffected_construction="E1(wrong)@eligible_all"); self.reject(x)
        x = self.fixture(); self.change_event(x, 1, ("pre_map", 111, 1)); self.reject(x)
        x = self.fixture(); u = x["capture"].events[0][1]
        self.change_event(x, 0, ("unaffected", u, id(u)+1)); self.reject(x)

    def test_raw_future_prefix_or_wrong_axis_no_fallback(self):
        for kind in ("prefix", "reverse", "shift", "bool"):
            x = self.fixture(); e = x["capture"].events[7]; values, axis = e[2]
            if kind == "prefix": values, axis = values[:-1], axis[:-1]
            if kind == "reverse": axis = tuple(reversed(axis))
            if kind == "shift": axis = tuple(i+1 for i in axis)
            if kind == "bool": axis = (False,)+axis[1:]
            self.change_event(x, 7, ("future", e[1], (values, axis))); self.reject(x)

    def test_curve_nonfinite_and_boolean_levels_refused(self):
        for value in (float("nan"), float("inf"), -float("inf"), False):
            x = self.fixture(); e = x["capture"].events[7]; v = list(e[2][0]); v[9] = value
            self.change_event(x, 7, ("future", e[1], (tuple(v), e[2][1]))); self.reject(x)

    def test_forged_tau_recovered_horizon_restricted_time_and_auc_refused(self):
        for fields in ({"tau": 3}, {"recovered": 1}, {"restricted_time": True}, {"t_max": 464},
                       {"deficit_auc": .001}, {"deficit_auc": float("nan")}, {"tau": None}):
            x = self.fixture(); n = x["record"].arm_names[1]
            self.replace_map(x, "future_utility", n, replace(x["record"].future_utility[n], **fields)); self.reject(x)

    def test_original_retention_sum_not_toleranced_or_tau_conditioned(self):
        x = self.fixture(); n = x["record"].arm_names[1]
        self.replace_map(x, "retention", n, x["record"].retention[n]+1e-14); self.reject(x)

    def test_endpoint_scalars_nonfinite_nested_boolean_refused(self):
        for field in ("collateral", "retention"):
            for value in (float("nan"), float("inf"), True, [0.]):
                x = self.fixture(); self.replace_map(x, field, x["record"].arm_names[1], value); self.reject(x)

    def test_no_write_reference_state_receipt_and_collateral_canaries(self):
        x = self.fixture(); self.replace_map(x, "collateral", x["record"].arm_names[0], .01); self.reject(x)
        x = self.fixture(); n = x["record"].arm_names[0]; wrong = x["record"].ledgers[x["record"].arm_names[1]]
        self.replace_map(x, "ledgers", n, wrong); self.reject(x)

    def test_ledger_fingerprints_receipt_address_or_canonical_identity_must_bind(self):
        x = self.fixture(); n = x["record"].arm_names[1]; ledger = x["record"].ledgers[n]
        self.replace_map(x, "ledgers", n, replace(ledger, fingerprint_post="2"*64)); self.reject(x)
        for changes in ({"canonical_form": "not-canonical"}, {"address": 0},
                        {"store_changed": 1}, {"status": "PROTOCOL_ERROR"}, {"status": EVALUABLE_NOOP}):
            x = self.fixture(); n = x["record"].arm_names[1]; ledger = x["record"].ledgers[n]
            r = replace(ledger.receipts[0], **changes)
            self.replace_map(x, "ledgers", n, replace(ledger, receipts=(r,))); self.reject(x)

    def test_scalar_cost_and_accounting_invariants_and_single_receipt(self):
        for changes in ({"n_scalar": True}, {"n_scalar": 0}, {"sum_abs_delta": -1},
                        {"sum_abs_delta": float("nan")}, {"max_abs_delta": .4},
                        {"scalar_metrics_applicable": False}, {"receipts": ()}):
            x = self.fixture(); n = x["record"].arm_names[1]; ledger = x["record"].ledgers[n]
            self.replace_map(x, "ledgers", n, replace(ledger, **changes)); self.reject(x)
        x = self.fixture("X", Tier.L0_FACTUAL, "X_id"); n = x["record"].arm_names[1]
        self.replace_map(x, "ledgers", n, replace(x["record"].ledgers[n], n_scalar=1)); self.reject(x)

    def test_collateral_immediate_post_state_not_future_state(self):
        x = self.fixture(); self.change_event(x, 9, ("collateral_state", x["record"].arm_names[1], "3"*64)); self.reject(x)

    def test_trace_digest_reproducible_not_process_identity(self):
        a = self.call(); b = self.call()
        self.assertEqual(a["input_sha256"], b["input_sha256"])
        self.assertEqual(bridge.sha(a["input_payload"]), a["input_sha256"])
        self.assertNotIn("object_id", repr(a["input_payload"]))
        self.assertNotEqual(a["input_sha256"], self.call(cell_id="another-fixture-cell")["input_sha256"])

    def test_no_mutation_of_input_record_protocol_capture_or_design(self):
        x = self.fixture(); p, r, c = x["protocol"], x["record"], x["capture"]
        before = (repr(p), repr(r), c.events, bridge.sha(self.parent["lock"]), bridge.sha(self.reference))
        bridge.extract_paired_record(**x)
        self.assertEqual(before, (repr(p), repr(r), c.events, bridge.sha(self.parent["lock"]), bridge.sha(self.reference)))

    def test_no_rollout_training_or_environment_draw_called(self):
        with patch.object(ExogenousEpisode, "derive", side_effect=AssertionError("NO environment draw")), \
             patch("rfl_rebuild.b2.runner.train_curve", side_effect=AssertionError("NO training")), \
             patch("rfl_rebuild.b2.environment.learned_rollout", side_effect=AssertionError("NO rollout")):
            self.assertTrue(self.call()["utility_retention_recomputed"])

    def test_nominal_constructed_input_cannot_authenticate_origin_or_authorize_collection(self):
        result = self.call()
        self.assertEqual(result["role"], "VALIDATED_IN_MEMORY_INPUT_NOT_AUTHENTICATED_ACQUISITION")
        for field in ("raw_collateral_maps_recomputed", "actual_factual_failure_origin_authenticated",
                      "unaffected_eligibility_from_prestate_recomputed", "population_seed_registry_and_collection_gate_authenticated",
                      "collection_authorized", "scientific_claim_authorized", "research_complete"):
            self.assertIs(result[field], False)

    def test_unrepresentable_integer_magnitude_fails_protocol_not_overflow(self):
        x = self.fixture(); e = x["capture"].events[7]; v = list(e[2][0]); v[9] = 10**1000
        self.change_event(x, 7, ("future", e[1], (tuple(v), e[2][1]))); self.reject(x)

    def test_signed_zero_cannot_substitute_native_formula_bytes(self):
        x = self.fixture(); n = x["record"].arm_names[0]
        self.replace_map(x, "collateral", n, -0.); self.reject(x)
        for field in ("deficit_auc", "retention"):
            x = self.fixture(); n = x["record"].arm_names[1]
            v = (.8,)*466 if field == "deficit_auc" else (0.,)*466
            utility = FutureUtility.from_curve(v, x["protocol"].grid,
                       pre_level=x["protocol"].v_pre, t_max=465)
            retained = select_form(x["record"].retention_form)(v, x["protocol"].grid,
                       **self.parent["design"]["retention"]["parameters"])
            self.replace_map(x, "future_utility", n, replace(utility, deficit_auc=-0.) if field == "deficit_auc" else utility)
            self.replace_map(x, "retention", n, -0. if field == "retention" else retained)
            self.change_event(x, 7, ("future", n, (v, x["protocol"].grid))); self.reject(x)

    def test_candidate_contract_matrix_parent_and_no_collection_authority(self):
        self.assertEqual(self.contract["inherited_available_pair_matrix"], bridge.frozen_matrix())
        self.assertEqual(self.contract["parent"]["sources_digest"], self.parent["sources_digest"])
        self.assertEqual(self.contract["parent"]["lock_sha256"], self.parent["lock_sha256"])
        for field in ("science_and_engineering_seed_registry", "scientific_failure_population",
                      "prospective_cell_order_and_weights", "prospective_primary_secondary_contrast_family"):
            self.assertIsNone(self.contract[field])
        for field in ("collection_authorized", "scientific_claim_authorized", "research_complete"):
            self.assertIs(self.contract[field], False)

    def test_reference_canonical_payload_digest_is_not_reference_file_sha(self):
        p = self.call()["input_payload"]
        self.assertEqual(p["healthy_reference_canonical_payload_sha256"], bridge.sha(self.reference))
        self.assertNotEqual(p["healthy_reference_canonical_payload_sha256"],
            ready.file_hash(Path(__file__).with_name("healthy_reference_candidate.json")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
