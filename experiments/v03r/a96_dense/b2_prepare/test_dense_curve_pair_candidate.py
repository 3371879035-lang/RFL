"""Nominal complete-curve/formula tests. No keyed trainer or collection runs."""
from dataclasses import replace
from fractions import Fraction
import inspect
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dense_curve_pair_candidate as candidate
import readiness as ready
from rfl_rebuild.b2 import training, utility, retention
from rfl_rebuild.b2.runner import PairedRunner

T = 465
GRID = tuple(range(T + 1))
PRE = .7642000000000008


def curve(levels=None):
    return training.Curve(tuple([PRE] * 466 if levels is None else levels), GRID, PRE, T)


def altered(c, **changes):
    # Malformed nominal objects are explicitly engineering refusal fixtures;
    # they are not actual trainer output or evidence of acquisition.
    bad = object.__new__(training.Curve)
    for field in ("values", "episodes", "pre_level", "t_max"):
        object.__setattr__(bad, field, changes.get(field, getattr(c, field)))
    return bad


class DenseCurvePairTests(unittest.TestCase):
    def setUp(self):
        self.reference_curve = curve()
        self.treatment_curve = curve([PRE - .2] * 466)

    def inspect(self, reference=None, treatment=None):
        return candidate.inspect_dense_pair(self.reference_curve if reference is None else reference,
                                            self.treatment_curve if treatment is None else treatment)

    def metrics(self, result=None):
        return (self.inspect() if result is None else result)["input_payload"]["ordered_metrics"]

    def refused(self, **changes):
        with self.assertRaises(ready.ProtocolError):
            self.inspect(treatment=altered(self.treatment_curve, **changes))

    def test_closed_two_curve_API_no_seed_protocol_scalar_receipt_or_callbacks(self):
        self.assertEqual(tuple(inspect.signature(candidate.inspect_dense_pair).parameters),
                         ("reference_curve", "treatment_curve"))
        for key in ("seed", "protocol", "gate", "receipt", "metrics", "callback",
                    "t_max", "reference", "regime", "cell_id"):
            with self.assertRaises(TypeError):
                candidate.inspect_dense_pair(self.reference_curve, self.treatment_curve, **{key: None})

    def test_no_train_rollout_protocol_diagnosis_or_B1_execution(self):
        with patch.object(training, "train_curve", side_effect=AssertionError("train")), \
             patch.object(training.ExogenousEpisode, "derive", side_effect=AssertionError("key")), \
             patch.object(training, "FutureTrainingProtocol", side_effect=AssertionError("protocol")), \
             patch.object(training, "learned_rollout", side_effect=AssertionError("rollout")), \
             patch.object(PairedRunner, "_apply", side_effect=AssertionError("B1")), \
             patch.object(ready, "build_reference", side_effect=AssertionError("new reference")):
            a = self.inspect()
            shape = candidate.dense_pair_workload_shape()
        self.assertFalse(a["new_training_or_rollout_executed"])
        print("NOMINAL_COMPLETE_DENSE_CURVE_SUMMARY=" + json.dumps({
            "nominal_supplied_roles": 2, "complete_levels": a["complete_raw_level_count"],
            "native_training_called": False, "native_protocol_created": False,
            "environment_key_draws": 0, "actual_keyed_origin_authenticated": False,
            "prospective_pair_eval_rollouts_not_measured": shape["evaluation_scene_rollouts_per_pair"],
            "collection_authorized": False}, sort_keys=True))

    def test_complete466_per_arm_fixed_order_hex_and_exact_reference(self):
        a = self.inspect(); raw = a["input_payload"]["complete_raw_pair"]
        self.assertEqual(raw["ordered_roles"], ["reference", "treatment"])
        self.assertEqual(a["complete_raw_level_count"], 932)
        for c, expected in zip(raw["ordered_curves"], (self.reference_curve, self.treatment_curve)):
            self.assertEqual(c["episodes"], list(GRID)); self.assertEqual(len(c["levels_hex"]), 466)
            self.assertEqual(c["levels_hex"], [v.hex() for v in expected.values])
            self.assertEqual(c["pre_level_hex"], PRE.hex())
        self.assertEqual(raw["N_eval"], 100)

    def test_original_future_utility_and_retention_exact_float_hex(self):
        a = self.inspect()
        for got, c in zip(self.metrics(a), (self.reference_curve, self.treatment_curve)):
            u = utility.FutureUtility.from_curve(c.values, c.episodes, pre_level=PRE, t_max=T)
            r = retention.select_form("LateWindowRetention")(c.values, c.episodes, H1=387, H2=465)
            self.assertEqual(got["tau"], u.tau); self.assertEqual(got["recovered"], u.recovered)
            self.assertEqual(got["restricted_time"], u.restricted_time)
            self.assertEqual(got["DeficitAUC_hex"], u.deficit_auc.hex())
            self.assertEqual(got["Retention_hex"], r.hex())

    def test_no_scalar_metric_input_or_nominal_record_substitution(self):
        for fake in (None, {}, 0, [], (self.reference_curve.values, GRID),
                     self.inspect(), self.reference_curve.__class__):
            with self.assertRaises(ready.ProtocolError):
                candidate.inspect_dense_pair(fake, self.treatment_curve)

    def test_curve_subclass_refused(self):
        class Subclass(training.Curve): pass
        with self.assertRaises(ready.ProtocolError):
            self.inspect(treatment=Subclass(self.treatment_curve.values, GRID, PRE, T))

    def test_same_curve_object_refused_but_distinct_equal_contents_allowed(self):
        with self.assertRaises(ready.ProtocolError):
            candidate.inspect_dense_pair(self.reference_curve, self.reference_curve)
        got = candidate.inspect_dense_pair(self.reference_curve, curve())
        self.assertEqual(got["input_payload"]["ordered_metrics"][0]["restricted_time"],
                         got["input_payload"]["ordered_metrics"][1]["restricted_time"])

    def test_prefix_no_padding_or_extrapolation(self):
        self.refused(values=self.treatment_curve.values[:-1], episodes=GRID[:-1])

    def test_sparse_axis_no_dense_zero_error_pass(self):
        self.refused(values=(PRE, PRE, PRE), episodes=(0, 100, 465))

    def test_cap576_curve_cannot_replace_current_own_F1_horizon(self):
        self.refused(values=(PRE,) * 577, episodes=tuple(range(577)), t_max=576)

    def test_extra_level_partial_level_and_empty_axis_refused(self):
        for changes in ({"values": (PRE,) * 467}, {"values": ()}, {"episodes": ()},
                        {"values": (PRE,) * 465}):
            self.refused(**changes)

    def test_list_or_generator_instead_of_complete_tuple_refused(self):
        for values in (list(self.treatment_curve.values), iter(self.treatment_curve.values)):
            self.refused(values=values)
        self.refused(episodes=list(GRID))

    def test_episode_bool_float_and_fraction_aliases_refused(self):
        for alias in (False, 0., Fraction(0)):
            self.refused(episodes=(alias,) + GRID[1:])

    def test_horizon_bool_float_and_fraction_aliases_refused(self):
        for alias in (True, 465., Fraction(465)):
            self.refused(t_max=alias)

    def test_duplicate_reordered_or_shifted_episode_axis_refused(self):
        for episodes in ((0, 0) + GRID[2:], tuple(reversed(GRID)), tuple(range(1, 467))):
            self.refused(episodes=episodes)

    def test_every_level_must_be_native_float_not_bool_integer_fraction_or_string(self):
        for value in (True, 0, Fraction(1, 2), ".5", complex(.5)):
            self.refused(values=(value,) + self.treatment_curve.values[1:])

    def test_nonfinite_values_anywhere_including_last_and_late_window_refused(self):
        for position in (0, 387, 465):
            for value in (float("nan"), float("inf"), -float("inf")):
                values = list(self.treatment_curve.values); values[position] = value
                self.refused(values=tuple(values))

    def test_finite_inputs_with_overflowing_auc_refused_without_zero_imputation(self):
        self.refused(values=(-1e308,) * 466)

    def test_finite_inputs_with_overflowing_retention_refused(self):
        self.refused(values=(1e308,) * 466)

    def test_old1024_master_or_own_episode0_reference_refused(self):
        for pre in (candidate._PARENT["lock"]["v_pre"], self.treatment_curve.values[0], 0.):
            self.refused(pre_level=pre)

    def test_shared_reference_numeric_alias_nan_and_one_ulp_change_refused(self):
        for value in (1, True, Fraction(1), float("nan"), float("inf"),
                      math.nextafter(PRE, math.inf)):
            self.refused(pre_level=value)

    def test_right_censoring_explicit_none_T_and_all_seed_retention_not_tau_conditioned(self):
        m = self.metrics()[1]
        self.assertIsNone(m["tau"]); self.assertIs(m["recovered"], False)
        self.assertEqual(m["restricted_time"], 465)
        self.assertIsInstance(m["Retention"], float)
        self.assertEqual(m["restricted_time_role"], "PER_CURVE_NOT_CROSS_SEED_RMST")

    def test_K3_threshold_equality_first_window_start_not_end(self):
        threshold = .95 * PRE
        c = curve([0.] * 20 + [threshold] * 3 + [0.] * 443)
        m = self.metrics(self.inspect(treatment=c))[1]
        self.assertEqual(m["tau"], 20); self.assertEqual(m["restricted_time"], 20)

    def test_one_or_two_late_crossings_do_not_recover(self):
        for n in (1, 2):
            c = curve([0.] * (466 - n) + [PRE] * n)
            self.assertIsNone(self.metrics(self.inspect(treatment=c))[1]["tau"])

    def test_last_complete_K3_window_463_recovers(self):
        m = self.metrics(self.inspect(treatment=curve([0.] * 463 + [PRE] * 3)))[1]
        self.assertEqual(m["tau"], 463); self.assertIs(m["recovered"], True)

    def test_one_below_threshold_breaks_window_without_smoothing(self):
        threshold = .95 * PRE
        c = curve([threshold] * 2 + [math.nextafter(threshold, -math.inf)] +
                  [threshold] * 3 + [0.] * 460)
        self.assertEqual(self.metrics(self.inspect(treatment=c))[1]["tau"], 3)

    def test_healthy_constant_recovery0_zero_deficit_and_original_sum_retention(self):
        m = self.metrics()[0]
        self.assertEqual(m["tau"], 0); self.assertEqual(m["DeficitAUC_hex"], (0.).hex())
        expected = retention.LateWindowRetention.value(self.reference_curve.values, GRID, H1=387, H2=465)
        self.assertEqual(m["Retention_hex"], expected.hex())

    def test_real_axis_trapezoid_analytic_linear_deficit(self):
        levels = [PRE - .25 * e / T for e in GRID]
        m = self.metrics(self.inspect(treatment=curve(levels)))[1]
        self.assertAlmostEqual(m["DeficitAUC"], .125, places=13)
        self.assertEqual(m["DeficitAUC_hex"],
                         utility.deficit_auc(levels, GRID, pre_level=PRE, t_max=T).hex())

    def test_retention_reads79_integer_levels387_through465_inclusive(self):
        levels = [0.] * 387 + [float(i) / 100 for i in range(79)]
        m = self.metrics(self.inspect(treatment=curve(levels)))[1]
        self.assertEqual(m["Retention_hex"], (sum(float(v) for v in levels[387:466]) / 79).hex())
        self.assertEqual(self.inspect()["input_payload"]["retention_design"],
                         {"form": "LateWindowRetention", "parameters": {"H1": 387, "H2": 465}})

    def test_metric_call_keeps_original_full_ordered_arguments(self):
        real_u = utility.FutureUtility.from_curve; real_r = retention.select_form
        observed = []
        def util(values, episodes, **kw):
            observed.append(("utility", values, episodes, kw)); return real_u(values, episodes, **kw)
        def select(name):
            f = real_r(name)
            def call(values, episodes, **kw):
                observed.append(("retention", values, episodes, kw)); return f(values, episodes, **kw)
            return call
        with patch.object(utility.FutureUtility, "from_curve", side_effect=util), \
             patch.object(retention, "select_form", side_effect=select):
            self.inspect()
        self.assertEqual([r[0] for r in observed], ["utility", "retention", "utility", "retention"])
        for i, c in enumerate((self.reference_curve, self.treatment_curve)):
            self.assertIs(observed[2*i][1], c.values); self.assertIs(observed[2*i][2], c.episodes)
            self.assertIs(observed[2*i+1][1], c.values); self.assertEqual(observed[2*i+1][3], {"H1": 387, "H2": 465})

    def test_raw_signed_zero_is_preserved_not_silently_normalized(self):
        plus, minus = curve([0.] * 466), curve([-0.] * 466)
        a = self.inspect(reference=plus, treatment=minus)["input_payload"]["complete_raw_pair"]["ordered_curves"]
        self.assertEqual(a[0]["levels_hex"][0], (0.).hex())
        self.assertEqual(a[1]["levels_hex"][0], (-0.).hex())

    def test_all_raw_levels_bind_hash_not_only_summary_or_tail(self):
        a = self.inspect()["input_payload"]
        changed = list(self.treatment_curve.values); changed[10] = math.nextafter(changed[10], math.inf)
        b = self.inspect(treatment=curve(changed))["input_payload"]
        self.assertNotEqual(a["raw_pair_payload_sha256"], b["raw_pair_payload_sha256"])
        self.assertEqual(a["ordered_metrics"][1]["Retention_hex"], b["ordered_metrics"][1]["Retention_hex"])

    def test_curve_role_order_is_explicit_not_sorted_by_benefit(self):
        a = self.inspect()["input_payload"]["ordered_metrics"]
        b = candidate.inspect_dense_pair(self.treatment_curve, self.reference_curve)["input_payload"]["ordered_metrics"]
        self.assertEqual(a[0]["role"], b[0]["role"])
        self.assertEqual(a[0]["restricted_time"], b[1]["restricted_time"])
        self.assertNotEqual(a[0]["restricted_time"], b[0]["restricted_time"])
        # Neither nominal assignment claims the real arm's source identity.
        self.assertFalse(self.inspect()["actual_keyed_curve_origin_authenticated"])

    def test_output_hashes_match_complete_export_and_detached_mutation_cannot_poison(self):
        a = self.inspect()
        self.assertEqual(a["input_payload_sha256"], candidate.bridge.sha(a["input_payload"]))
        self.assertEqual(a["input_payload"]["raw_pair_payload_sha256"],
                         candidate.bridge.sha(a["input_payload"]["complete_raw_pair"]))
        a["input_payload"]["complete_raw_pair"]["ordered_curves"][0]["levels_hex"].pop()
        a["input_payload"]["ordered_metrics"].reverse()
        self.assertEqual(self.inspect()["complete_raw_level_count"], 932)

    def test_input_mutation_during_recalculation_refused(self):
        c = self.treatment_curve; old = c.values; real = candidate._metrics; calls = []
        def moving(*args):
            out = real(*args); calls.append(1)
            if len(calls) == 2: object.__setattr__(c, "values", (PRE,) + old[1:])
            return out
        try:
            with patch.object(candidate, "_metrics", side_effect=moving):
                with self.assertRaisesRegex(ready.ProtocolError, "changed during"):
                    self.inspect()
        finally: object.__setattr__(c, "values", old)

    def test_code_reference_parent_and_lock_payload_drift_refused(self):
        with patch.object(candidate, "_CODE_BINDING", ()):
            with self.assertRaisesRegex(ready.ProtocolError, "bytes changed"): self.inspect()
        with patch.dict(candidate._REFERENCE, {"v_pre": .5}):
            with self.assertRaises(ready.ProtocolError): self.inspect()
        with patch.dict(candidate._PARENT, {"sources_digest": "0" * 64}):
            with self.assertRaises(ready.ProtocolError): self.inspect()
        d = candidate._PARENT["lock"]["design"]
        with patch.dict(d, {"T": 576}):
            with self.assertRaises(ready.ProtocolError): self.inspect()

    def test_invalid_native_metric_output_refused_no_partial_authorized_payload(self):
        u = utility.FutureUtility.from_curve(self.reference_curve.values, GRID, pre_level=PRE, t_max=T)
        for bad in (replace(u, tau=True), replace(u, restricted_time=1),
                    replace(u, deficit_auc=float("nan")), replace(u, recovered=False)):
            with patch.object(utility.FutureUtility, "from_curve", return_value=bad):
                with self.assertRaises(ready.ProtocolError): self.inspect()

    def test_workload_counts_match_original_loop_not465_checkpoints_or466_training(self):
        a = candidate.dense_pair_workload_shape()
        self.assertEqual(a["training_episode_indices"], list(range(465)))
        self.assertEqual(a["evaluation_episode_indices"], list(range(466)))
        self.assertEqual(a["ordinary_training_episodes_per_pair"], 930)
        self.assertEqual(a["evaluation_scene_rollouts_per_pair"], 93200)
        self.assertEqual(a["evaluation_scene_rollouts_per_arm"], 46600)
        self.assertIn("U2_incidence", a["excluded_overhead"])
        self.assertFalse(a["wall_time_or_memory_measured"]); self.assertFalse(a["workload_resources_certified"])

    def test_no_acquisition_collateral_record_population_or_effect_claim(self):
        a = self.inspect()
        for name in ("actual_keyed_curve_origin_authenticated", "collateral_or_native_record_authenticated",
                     "new_training_or_rollout_executed", "population_seed_registry_and_collection_gate_authenticated",
                     "full_dense_B2_workload_resources_certified", "collection_authorized",
                     "scientific_claim_authorized", "research_complete"):
            self.assertIs(a[name], False)
        for key in ("seed", "p_value", "benefit_PASS", "scientific_result", "statistical_sample_size",
                    "collateral", "PairedSceneRecord"):
            self.assertNotIn(key, a)

    def test_fixture_keeps_TestCase_run_entry_callable(self):
        self.assertNotIn("run", type(self).__dict__); self.assertTrue(callable(self.run))


if __name__ == "__main__": unittest.main()

