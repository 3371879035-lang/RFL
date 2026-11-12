"""Constructed record IDs/vectors only: no environment/training science seeds."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_candidate as report
from readiness import ROOT, load_parent


def spec(regime="P", statistic="RMST", stage="primary", tier="L0", name="synthetic-core"):
    return {"contrast_id": name, "regime": regime, "statistic": statistic,
            "stage": stage, "reference_arm": "constructed-reference",
            "treatment_arm": "constructed-treatment", "reference_tier": tier,
            "treatment_tier": tier, "orientation": report.ORIENTATIONS[regime, statistic]}


def summary(*, center=1., median=1., trim=1., poi=1., nt=400, share=.0125,
            psign=.001, pwilcoxon=.001):
    # These are helper-test dictionaries, never called native acquisition records.
    return {"n_seeds": 400, "non_tied_seeds": nt, "probability_of_improvement": poi,
            "mean": center, "median": median, "trimmed_mean_5pct_each_tail": trim,
            "top5_share_of_net_sum": share, "mean_without_top5": center,
            "p_exact_sign": psign, "wilcoxon": {"p": pwilcoxon}}


def family_record(name, p=.01, *, stage="primary", n=400):
    s = summary(psign=p, pwilcoxon=p)
    s["n_seeds"] = n
    return {"contrast_id": name, "declaration": spec(stage=stage, name=name),
            "n_seeds": n, "statistics": s}


class DeclarationAndScheduleTests(unittest.TestCase):
    def test_only_complete_hundred_seed_schedule(self):
        x = report.look_schedule("primary", list(range(400)), 400)
        self.assertEqual([r["look_n"] for r in x], [100, 200, 300, 400])
        self.assertEqual(x[2]["fresh_block_seeds"], tuple(range(200, 300)))
        self.assertEqual(x[2]["cumulative_seeds"], tuple(range(300)))
        self.assertEqual([r["primary_final"] for r in x], [False, False, False, True])

    def test_secondary_never_becomes_core_primary(self):
        x = report.look_schedule("secondary", list(range(200)), 200)
        self.assertEqual([r["look_n"] for r in x], [100, 200])
        self.assertTrue(x[-1]["final_for_declared_stage"])
        self.assertFalse(x[-1]["primary_final"])
        with self.assertRaises(ValueError):
            report.look_schedule("primary", list(range(200)), 200)

    def test_incomplete_or_overshot_look_refused(self):
        for n in (0, 99, 199, 399, 401, 500, True, 100.0):
            with self.subTest(n=n), self.assertRaises(ValueError):
                report.look_schedule("primary", list(range(400)), n)

    def test_missing_duplicate_or_boolean_population_refused(self):
        populations = [list(range(399)), list(range(399)) + [0], [False]+list(range(1,400))]
        for p in populations:
            with self.assertRaises(ValueError):
                report.look_schedule("primary", p, 100)

    def test_same_tier_required_no_headroom_ranking(self):
        s = spec(); s["reference_tier"] = "L3"
        with self.assertRaises(ValueError):
            report.validate_spec(s)

    def test_orientation_and_endpoint_identity_explicit(self):
        s = spec("P", "Retention")
        self.assertEqual(s["orientation"], "treatment-minus-reference")
        s["orientation"] = "reference-minus-treatment"
        with self.assertRaises(ValueError):
            report.validate_spec(s)
        s = spec(); s["regime"] = "T+P"
        with self.assertRaises(ValueError):
            report.validate_spec(s)

    def test_closed_declaration_and_distinct_arms(self):
        s = spec(); s["extra"] = True
        with self.assertRaises(ValueError): report.validate_spec(s)
        s = spec(); s["treatment_arm"] = s["reference_arm"]
        with self.assertRaises(ValueError): report.validate_spec(s)


class DecisionAndDistributionTests(unittest.TestCase):
    def test_rmst_strict_exceedance_and_inclusive_containment(self):
        self.assertEqual(report.margin_label(1.5, 2, 1.5, "RMST"), "INCONCLUSIVE")
        self.assertEqual(report.margin_label(1.5001, 2, 1.5, "RMST"), "MARGIN_A")
        self.assertEqual(report.margin_label(-2, -1.5001, 1.5, "RMST"), "MARGIN_B")
        self.assertEqual(report.margin_label(-1.5, 1.5, 1.5, "RMST"), "WITHIN_BENCHMARK_MARGIN")

    def test_other_margin_semantics_not_silently_changed(self):
        self.assertEqual(report.margin_label(.02, .03, .01, "DeficitAUC"), "SUPPORT_A")
        self.assertEqual(report.margin_label(-.01, .01, .01, "DeficitAUC"), "EQUIVALENT")

    def test_T_bound_is_not_inferred_from_label(self):
        self.assertEqual(report.margin_label(-1, 3, 1.5, "RMST"), "INCONCLUSIVE")
        self.assertTrue(report.quantity_bound(-1, 3, 1.5, preregistered_rule="lower-ci>=-margin")["met"])
        self.assertTrue(report.quantity_bound(-1.5, 3, 1.5, preregistered_rule="lower-ci>=-margin")["met"])
        self.assertFalse(report.quantity_bound(-1.50001, 3, 1.5, preregistered_rule="lower-ci>=-margin")["met"])

    def test_unspecified_retention_collateral_bound_stays_open(self):
        self.assertIsNone(report.quantity_bound(1, 2, .01, preregistered_rule=None)["met"])
        with self.assertRaises(ValueError):
            report.quantity_bound(1, 2, .01, preregistered_rule="lower-ci>=-2margin")

    def test_invalid_interval_or_margin_cannot_pass(self):
        for lo, hi, m in [(2, 1, 1.5), (float("nan"), 2, 1.5), (1, float("inf"), 1.5),
                          (0, 1, True), (0, 1, 0)]:
            with self.assertRaises(ValueError): report.margin_label(lo, hi, m, "RMST")

    def test_all_distribution_companions_required(self):
        r = report.distribution_diagnostics(summary(), sign_holm_p=.01)
        self.assertTrue(r["directional_finding_candidate_eligible"])
        self.assertFalse(r["scientific_claim_authorized"])

    def test_inconsistent_median_or_trim_blocks_finding(self):
        for x in (summary(median=0), summary(trim=-1)):
            r = report.distribution_diagnostics(x, sign_holm_p=.001)
            self.assertEqual(r["status"], "DIRECTION UNRESOLVED")

    def test_sign_test_must_agree_after_holm(self):
        for p in (None, .051):
            self.assertFalse(report.distribution_diagnostics(summary(), sign_holm_p=p)
                             ["directional_finding_candidate_eligible"])
        r = report.distribution_diagnostics(summary(poi=.25), sign_holm_p=.001)
        self.assertFalse(r["corrected_sign_test_agrees"])

    def test_half_top5_is_tail_driven_not_boundary_pass(self):
        r = report.distribution_diagnostics(summary(share=.5), sign_holm_p=.001)
        self.assertEqual(r["status"], "TAIL-DRIVEN")
        self.assertFalse(r["directional_finding_candidate_eligible"])

    def test_zero_net_or_all_ties_not_imputed(self):
        r = report.distribution_diagnostics(summary(center=0, median=0, trim=0, poi=0, nt=0, share=None),
                                            sign_holm_p=None)
        self.assertEqual(r["status"], "DIRECTION UNRESOLVED")

    def test_nonfinite_and_non_seed_probability_refused(self):
        for s in (summary(center=float("nan")), summary(poi=.333333), summary(share=float("inf"))):
            with self.assertRaises(ValueError): report.distribution_diagnostics(s, sign_holm_p=.001)


class MultiplicityAndReversalTests(unittest.TestCase):
    def test_complete_ordered_family_corrects_all_members(self):
        r = report.complete_holm_family(["a", "b"], [family_record("a", .03), family_record("b", .01)])
        self.assertEqual(r["families"]["sign"]["adjusted_p"], [.03, .02])
        self.assertTrue(r["multiplicity_family_candidate_complete"])
        self.assertFalse(r["scientific_claim_authorized"])

    def test_family_subset_extra_reorder_duplicate_refused(self):
        for records in ([family_record("a")], [family_record("b"), family_record("a")],
                        [family_record("a"), family_record("a")],
                        [family_record("a"), family_record("b"), family_record("c")]):
            with self.assertRaises(ValueError): report.complete_holm_family(["a", "b"], records)

    def test_undefined_family_member_is_not_dropped_or_p_one(self):
        r = report.complete_holm_family(["a", "b"], [family_record("a", .01), family_record("b", None)])
        self.assertFalse(r["multiplicity_family_candidate_complete"])
        self.assertEqual(r["families"]["sign"]["adjusted_p"], [None, None])
        self.assertEqual(r["families"]["sign"]["undefined_ids"], ["b"])

    def test_mixed_look_sizes_or_tiers_of_confirmatory_stage_refused(self):
        for other in (family_record("b", n=100), family_record("b", stage="secondary", n=200)):
            with self.assertRaises(ValueError):
                report.complete_holm_family(["a", "b"], [family_record("a"), other])

    def test_nonfinite_p_refused(self):
        with self.assertRaises(ValueError):
            report.complete_holm_family(["a"], [family_record("a", float("nan"))])

    def test_ci_zero_flip_without_label_change_is_not_reversal(self):
        a = {"contrast_id":"a", "declaration":spec(name="a"), "n_seeds":100,
             "fixed_endpoint_margin":1.5, "margin_label":"INCONCLUSIVE"}
        b = dict(a, n_seeds=200, fresh_block_statistics={"n_seeds":100, "mean":.1})
        self.assertEqual(report.reversal(a,b)["interpretation"], "NO_OP_NOT_REVERSAL")
        b["margin_label"] = "WITHIN_BENCHMARK_MARGIN"
        self.assertEqual(report.reversal(a,b)["interpretation"], "DECISION_BOUNDARY_MOVEMENT")
        b["fresh_block_statistics"]["mean"] = 2
        self.assertEqual(report.reversal(a,b)["interpretation"], "LABEL_CHANGE_WITH_FRESH_BLOCK_MEAN")

    def test_reversal_requires_same_declaration_margin_and_adjacent_block(self):
        a = {"contrast_id":"a", "declaration":spec(name="a"), "n_seeds":100,
             "fixed_endpoint_margin":1.5, "margin_label":"INCONCLUSIVE"}
        b = dict(a, n_seeds=200, fresh_block_statistics={"n_seeds":100, "mean":.1})
        for bad in (dict(b, n_seeds=300), dict(b, fixed_endpoint_margin=1),
                    dict(b, fresh_block_statistics={"n_seeds":99, "mean":.1})):
            with self.assertRaises(ValueError): report.reversal(a,bad)


class FullConstructedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent=load_parent(ROOT)
        # Integer labels below identify constructed array rows, NOT train/env RNG keys.
        cls.ids=list(range(400))
        cls.rows=[{"seed":i,"reference":10.,"treatment":5.} for i in cls.ids]
        cls.reports=report.contrast_reports(cls.rows,cls.ids,spec(),cls.parent["lock"])

    def test_actual_10000_bootstrap_and_complete_scheduled_blocks(self):
        self.assertEqual([r["n_seeds"] for r in self.reports], [100,200,300,400])
        for r in self.reports:
            self.assertEqual(r["statistics"]["bootstrap_resamples"],10000)
            self.assertEqual(r["statistics"]["paired_bootstrap_95_ci"],[5.,5.])
            self.assertEqual(r["fresh_block_statistics"]["n_seeds"],100)
            self.assertEqual(r["margin_label"],"MARGIN_A")
            self.assertFalse(r["scientific_claim_authorized"])

    def test_four_quantities_and_null_zero_spread_preserved(self):
        r=self.reports[-1]
        self.assertEqual((r["n_seeds"],r["n_train"],r["n_eval"]),(400,465,100))
        self.assertEqual(r["checkpoint_grid"],list(range(466)))
        self.assertIsNone(r["statistics"]["cohens_dz"])

    def test_only_full400_is_primary_final_but_still_not_authorized(self):
        self.assertFalse(self.reports[-2]["look"]["primary_final"])
        self.assertTrue(self.reports[-1]["look"]["primary_final"])
        self.assertFalse(self.reports[-1]["collection_authorized"])
        self.assertFalse(self.reports[-1]["research_complete"])

    def test_partial_reordered_or_duplicate_rows_refused_before_statistics(self):
        for rows in (self.rows[:-1], self.rows[1:]+self.rows[:1], self.rows[:-1]+[self.rows[0]]):
            with self.assertRaises(ValueError):
                report.contrast_reports(rows,self.ids,spec(),self.parent["lock"])

    def test_partial_conjunction_never_becomes_version_pass(self):
        x=report.joint_readiness([self.reports[-1]])
        self.assertEqual(len(x["missing_endpoint_keys"]),5)
        self.assertFalse(x["V03R_PASS"])
        self.assertFalse(x["V04R_authorized"])

    def test_all_favorable_complete_endpoint_presence_still_no_gate_authority(self):
        records=[]
        for regime,stat in report.ORIENTATIONS:
            r=copy.deepcopy(self.reports[-1])
            r["declaration"]=spec(regime,stat,name=f"constructed-{regime}-{stat}")
            records.append(r)
        x=report.joint_readiness(records)
        self.assertTrue(x["complete_core_endpoint_presence"])
        self.assertTrue(x["all_reports_primary_final_same_L0_tier"])
        self.assertFalse(x["V03R_PASS"])
        self.assertFalse(x["weighted_score_used"])

    def test_ceiling_tier_cannot_establish_L0_core_claim(self):
        r=copy.deepcopy(self.reports[-1]);r["declaration"]=spec(tier="L3")
        x=report.joint_readiness([r])
        self.assertFalse(x["all_reports_primary_final_same_L0_tier"])

    def test_duplicated_regime_endpoint_in_conjunction_refused(self):
        with self.assertRaises(ValueError):
            report.joint_readiness([self.reports[-1],self.reports[-1]])


if __name__=="__main__":
    unittest.main(verbosity=2)
