"""Seedless/constructed engineering tests; no B2 acquisition or treatment data."""
from copy import deepcopy
import itertools
from pathlib import Path
import unittest

import readiness as ready
import statistics_candidate as stats


class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent = ready.load_parent()
        cls.reference = ready.read_json(Path(__file__).with_name("healthy_reference_candidate.json"))

    def bad_design(self, mutate):
        value = deepcopy(self.parent["lock"])
        mutate(value["design"])
        with self.assertRaises(ready.ProtocolError):
            ready.validate_design(value)

    def bad_reference(self, key, value):
        candidate = deepcopy(self.reference)
        candidate[key] = value
        with self.assertRaises(ready.ProtocolError):
            ready.validate_reference(candidate, self.parent)

    def test_parent_full_atomic_lock_remains_bound(self):
        d = ready.validate_design(self.parent["lock"])
        self.assertEqual((d["T"], d["N_eval"]), (465, 100))
        self.assertEqual(len(self.parent["sources"]), 313)

    def test_preparation_is_not_collection_gate(self):
        result = ready.readiness(self.parent)
        self.assertFalse(result["collection_authorized"])
        self.assertFalse(result["research_complete"])
        self.assertEqual(len(result["required_before_collection"]), 6)

    def test_locked_reference_uses100_not_master1024(self):
        value = ready.validate_reference(self.reference, self.parent)
        self.assertEqual(self.reference["N_eval"], 100)
        self.assertEqual(len(self.reference["ordered_healthy_scene_levels"]), 100)
        self.assertNotEqual(value, self.parent["lock"]["v_pre"])

    def test_master_bank_identity_cannot_substitute(self):
        self.bad_reference("N_eval", 1024)
        self.bad_reference("evaluation_sample_sha256", ready.prefix_digest(1024))
        self.bad_reference("v_pre", self.parent["lock"]["v_pre"])

    def test_missing_reference_fields_refused(self):
        candidate = deepcopy(self.reference)
        del candidate["q_reference_sha256"]
        with self.assertRaises(ready.ProtocolError):
            ready.validate_reference(candidate, self.parent)

    def test_reference_extra_field_refused(self):
        self.bad_reference("effect_size", .8)

    def test_no_false_reference_authorization(self):
        for key in ("collection_authorized", "treatment_collected", "confirmatory_collected"):
            with self.subTest(key=key):
                self.bad_reference(key, True)

    def test_reference_types_and_nonfinite_refused(self):
        for key, value in (("seed_draws", False), ("N_eval", 100.0),
                           ("q_reference_sha256", "z" * 64), ("v_pre", float("nan"))):
            with self.subTest(key=key):
                self.bad_reference(key, value)

    def test_sparse_or_boolean_grid_refused(self):
        self.bad_design(lambda d: d.update(grid=[0, 1, 2, 465]))
        self.bad_design(lambda d: d["grid"].__setitem__(0, False))

    def test_posthoc_horizon_or_retention_change_refused(self):
        self.bad_design(lambda d: d.update(T=466))
        self.bad_design(lambda d: d["retention"]["parameters"].update(H1=388))

    def test_pooled_or_duplicate_endpoint_identity_refused(self):
        self.bad_design(lambda d: d["thresholds"][-1].update(regime="P"))

    def test_relaxed_rmst_or_harm_bound_refused(self):
        self.bad_design(lambda d: d["thresholds"][0].update(value=1.0))
        self.bad_design(lambda d: d["thresholds"][4].update(bound_inclusive=False))

    def test_practical_or_zero_harm_claim_refused(self):
        self.bad_design(lambda d: d["thresholds"][0].update(practical_meaning_claimed=True))
        self.bad_design(lambda d: d["thresholds"][4].update(zero_harm_claimed=True))


def pairs(differences):
    # Constructed deterministic numbers, NOT simulated seeds/environment observations.
    return [{"seed": i, "reference": float(value), "treatment": 0.0}
            for i, value in enumerate(differences)]


class StatisticsTests(unittest.TestCase):
    def test_sign_test_two_tails_not_legacy_half_probability(self):
        self.assertEqual(stats.exact_sign_p([1., 2., 3., 4.]), .125)
        self.assertIsNone(stats.exact_sign_p([0., 0.]))
        self.assertEqual(stats.exact_sign_p([1., -1.]), 1.)

    def test_wilcoxon_all_positive_includes_both_tails(self):
        result = stats.exact_wilcoxon([1., 2., 3., 4.])
        self.assertEqual(result["p"], .125)
        self.assertEqual(result["statistic"], 0.)

    def test_exact_rank_distribution_matches_enumeration(self):
        d = [1., -1., 2., -3.]
        ranks = [3, 3, 6, 8]  # doubled average ranks
        total, observed = sum(ranks), 3 + 6
        low = min(observed, total - observed)
        count = 0
        for signs in itertools.product((0, 1), repeat=4):
            rank = sum(s * w for s, w in zip(signs, ranks))
            count += rank <= low or rank >= total - low
        self.assertEqual(stats.exact_wilcoxon(d)["p"], count / 16)

    def test_all_zero_wilcoxon_remains_undefined(self):
        result = stats.exact_wilcoxon([0., 0.])
        self.assertIsNone(result["p"])
        self.assertEqual(result["reason"], "ALL_EXACT_TIES")

    def test_holm_preserves_family_order_and_monotonicity(self):
        self.assertEqual(stats.holm([.04, .01, .03]), [.06, .03, .06])
        with self.assertRaises(ValueError):
            stats.holm([.1, None])

    def test_orientation_is_explicit_not_lexical(self):
        rows = pairs([2., -1.])
        self.assertEqual(stats.paired_differences(rows, [0, 1], "reference-minus-treatment"), [2., -1.])
        self.assertEqual(stats.paired_differences(rows, [0, 1], "treatment-minus-reference"), [-2., 1.])
        with self.assertRaises(ValueError):
            stats.paired_differences(rows, [0, 1], "auto")

    def test_partial_pseudoreplicated_reordered_seeds_refused(self):
        for rows, seeds in ((pairs([1.]), [0, 1]), (pairs([1., 2.]), [0, 0]),
                            (list(reversed(pairs([1., 2.]))), [0, 1])):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    stats.paired_differences(rows, seeds, "reference-minus-treatment")

    def test_missing_nonfinite_bool_nested_values_refused(self):
        for value in (float("nan"), float("inf"), True, [1.]):
            rows = pairs([1.])
            rows[0]["reference"] = value
            with self.assertRaises(ValueError):
                stats.paired_differences(rows, [0], "reference-minus-treatment")

    def test_boolean_seed_is_not_integer_seed(self):
        rows = pairs([1.])
        rows[0]["seed"] = False
        with self.assertRaises(ValueError):
            stats.paired_differences(rows, [0], "reference-minus-treatment")

    def test_probability_is_per_seed_not_bootstrap_mean(self):
        rows = pairs([0., 0., 1., 1., -1., 3.])
        result = stats.summarize(rows, range(6), orientation="reference-minus-treatment")
        self.assertEqual(result["probability_of_improvement"], .5)
        self.assertEqual(result["tie_fraction"], 2 / 6)
        self.assertFalse(result["confirmatory_claim_authorized"])
        self.assertFalse(result["holm_applied"])

    def test_constant_spread_reports_null_dz_not_zero_effect(self):
        result = stats.summarize(pairs([2.] * 6), range(6), orientation="reference-minus-treatment")
        self.assertEqual(result["paired_bootstrap_95_ci"], [2., 2.])
        self.assertIsNone(result["cohens_dz"])
        self.assertEqual(result["cohens_dz_undefined_reason"], "ZERO_SAMPLE_SPREAD")

    def test_tail_and_zero_net_are_not_imputed(self):
        result = stats.summarize(pairs([0.] * 6), range(6), orientation="reference-minus-treatment")
        self.assertIsNone(result["top5_share_of_net_sum"])
        self.assertIsNone(result["p_exact_sign"])
        self.assertEqual(result["probability_of_improvement"], 0.)

    def test_percentile_linear_convention_is_declared(self):
        self.assertEqual(stats.percentile_linear([0., 10.], .25), 2.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
