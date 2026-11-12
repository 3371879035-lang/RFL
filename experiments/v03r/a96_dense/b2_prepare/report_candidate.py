"""Prospective reporting mechanics, NOT a collection gate or scientific verdict.

No environment, training, seed reservation, file publication or acquisition API.
Concrete populations/arms/families still need their separate preregistration.
Only paired, already aggregated seed rows enter these candidate functions.
"""
from __future__ import annotations

import math

from readiness import validate_design
from statistics_candidate import holm, paired_differences, summarize

STAGE_N = {"primary": 400, "secondary": 200}
ORIENTATIONS = {
    ("P", "RMST"): "reference-minus-treatment",
    ("P", "DeficitAUC"): "reference-minus-treatment",
    ("P", "BehavioralCollateral"): "reference-minus-treatment",
    ("P", "Retention"): "treatment-minus-reference",
    ("T", "RMST"): "reference-minus-treatment",
    ("T", "DeficitAUC"): "reference-minus-treatment",
}
SPEC_KEYS = {"contrast_id", "regime", "statistic", "stage", "reference_arm",
             "treatment_arm", "reference_tier", "treatment_tier", "orientation"}
TIERS = {"L0", "L1", "L2", "L3"}
SIGN_ALPHA_CANDIDATE = .05  # prospective convention, not collection authorization


def require(ok, message):
    if not ok:
        raise ValueError(message)


def number(x):
    return type(x) in (int, float) and math.isfinite(x)


def sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def validate_spec(spec):
    require(type(spec) is dict and set(spec) == SPEC_KEYS, "closed contrast declaration required")
    require(all(type(spec[k]) is str and spec[k] for k in SPEC_KEYS), "named contrast fields required")
    key = spec["regime"], spec["statistic"]
    require(key in ORIENTATIONS and spec["orientation"] == ORIENTATIONS[key],
            "unknown/pooled endpoint or incorrect declared orientation")
    require(spec["stage"] in STAGE_N, "contrast stage cannot be upgraded or inferred")
    require(spec["reference_tier"] in TIERS and
            spec["reference_tier"] == spec["treatment_tier"], "same-tier reference required")
    require(spec["reference_arm"] != spec["treatment_arm"], "two distinct named arms required")
    return key


def look_schedule(stage, expected_seeds, observed_n):
    require(stage in STAGE_N, "unknown primary/secondary stage")
    require(type(expected_seeds) in (list, tuple), "complete prospective population required")
    seeds = tuple(expected_seeds)
    require(len(seeds) == STAGE_N[stage] and all(type(x) is int and x >= 0 for x in seeds)
            and len(set(seeds)) == len(seeds), "not the complete unique seed population")
    require(type(observed_n) is int and 0 < observed_n <= len(seeds)
            and observed_n % 100 == 0, "only complete scheduled hundred-seed looks")
    return [{"look_n": n, "cumulative_seeds": seeds[:n], "fresh_block_seeds": seeds[n-100:n],
             "diagnostic_only": n != len(seeds), "final_for_declared_stage": n == len(seeds),
             "primary_final": stage == "primary" and n == 400,
             "secondary_cannot_establish_core_claim": stage == "secondary"}
            for n in range(100, observed_n + 1, 100)]


def margin_label(lower, upper, margin, statistic):
    require(statistic in {x[1] for x in ORIENTATIONS}, "unknown endpoint statistic")
    require(number(lower) and number(upper) and lower <= upper and number(margin)
            and margin > 0, "ordered finite CI and positive fixed margin required")
    rmst = statistic == "RMST"
    if lower > margin:
        return "MARGIN_A" if rmst else "SUPPORT_A"
    if upper < -margin:
        return "MARGIN_B" if rmst else "SUPPORT_B"
    if lower >= -margin and upper <= margin:
        return "WITHIN_BENCHMARK_MARGIN" if rmst else "EQUIVALENT"
    return "INCONCLUSIVE"


def quantity_bound(lower, upper, margin, *, preregistered_rule):
    """Bounds are separate from four-way labels. No unspecified rule is inferred.

    T RMST has the inherited inclusive rule. Other bound rules are deliberately
    not supplied by this module; their prospective registration remains open.
    """
    require(number(lower) and number(upper) and lower <= upper and number(margin)
            and margin > 0, "invalid bound arguments")
    if preregistered_rule is None:
        return {"met": None, "reason": "BOUND_RULE_NOT_SEPARATELY_PREREGISTERED"}
    require(preregistered_rule == "lower-ci>=-margin", "unsupported or relaxed bound rule")
    return {"met": lower >= -margin, "reason": None}


def distribution_diagnostics(summary, *, sign_holm_p):
    """Candidate distribution gate, independent of the CI/margin decision.

    Holm significance is a prospective candidate convention. It has to be
    committed with the whole family before collection; no family means no PASS.
    """
    require(type(summary) is dict, "summary required")
    for key in ("mean", "median", "trimmed_mean_5pct_each_tail"):
        require(number(summary[key]), "nonfinite location statistic")
    n, nt, poi = summary["n_seeds"], summary["non_tied_seeds"], summary["probability_of_improvement"]
    require(type(n) is int and type(nt) is int and 0 <= nt <= n and n > 0 and
            number(poi) and 0 <= poi <= 1, "invalid independent seed counts")
    positive = round(poi * n)
    require(0 <= positive <= nt and abs(poi - positive / n) <= 1e-15,
            "probability is not a per-seed proportion")
    direction = sign(summary["mean"])
    same = direction != 0 and all(sign(summary[k]) == direction
                                 for k in ("median", "trimmed_mean_5pct_each_tail"))
    majority = sign(2 * positive - nt)
    require(sign_holm_p is None or (number(sign_holm_p) and 0 <= sign_holm_p <= 1),
            "invalid corrected sign-test p")
    sign_agrees = (sign_holm_p is not None and sign_holm_p <= SIGN_ALPHA_CANDIDATE
                   and direction != 0 and majority == direction)
    share = summary["top5_share_of_net_sum"]
    require(share is None or number(share), "invalid top5 contribution share")
    tail_ok = share is not None and 0 <= share < .5
    status = ("TAIL-DRIVEN" if share is not None and share >= .5 else
              "DIRECTION UNRESOLVED" if not (same and sign_agrees and tail_ok) else
              "DISTRIBUTION_COMPANIONS_SATISFIED")
    return {"status": status, "mean_median_trimmed_sign_agree": same,
            "corrected_sign_test_agrees": sign_agrees, "top5_below_half": tail_ok,
            "mean_without_top5": summary["mean_without_top5"],
            "directional_finding_candidate_eligible": same and sign_agrees and tail_ok,
            "scientific_claim_authorized": False}


def complete_holm_family(ordered_ids, reports):
    """Refuse missing/reordered families rather than correcting a flattering subset."""
    require(type(ordered_ids) in (list, tuple) and ordered_ids and
            all(type(x) is str and x for x in ordered_ids) and
            len(set(ordered_ids)) == len(ordered_ids), "complete unique ordered family required")
    require(type(reports) is list and [r["contrast_id"] for r in reports] == list(ordered_ids),
            "missing, extra, duplicate or reordered contrast family")
    for r in reports:
        validate_spec(r["declaration"])
        n = r["n_seeds"]
        require(type(n) is int and 0 < n <= STAGE_N[r["declaration"]["stage"]]
                and n % 100 == 0 and r["statistics"]["n_seeds"] == n,
                "family member is not a complete scheduled seed look")
    require(len({(r["declaration"]["stage"], r["n_seeds"]) for r in reports}) == 1,
            "mixed stages or mixed look sizes in one family")
    output = {}
    for source in ("sign", "wilcoxon"):
        values = [r["statistics"]["p_exact_sign"] if source == "sign" else
                  r["statistics"]["wilcoxon"]["p"] for r in reports]
        require(all(p is None or (number(p) and 0 <= p <= 1) for p in values),
                "invalid test p in family")
        absent = [ordered_ids[i] for i, p in enumerate(values) if p is None]
        # Undefined is NOT p=1 or p=0, and an incomplete numeric family cannot PASS.
        output[source] = {"status": "UNRESOLVED_UNDEFINED_MEMBER" if absent else "COMPLETE",
                          "undefined_ids": absent,
                          "adjusted_p": [None] * len(values) if absent else holm(values)}
    return {"ordered_contrast_ids": list(ordered_ids), "families": output,
            "declared_stage": reports[0]["declaration"]["stage"],
            "look_n": reports[0]["n_seeds"],
            "multiplicity_family_candidate_complete": all(x["status"] == "COMPLETE"
                                                         for x in output.values()),
            "scientific_claim_authorized": False}


def contrast_reports(rows, expected_seeds, spec, lock):
    key = validate_spec(spec)
    design = validate_design(lock)
    schedule = look_schedule(spec["stage"], expected_seeds, len(rows))
    # Full prefix/order validation before the first expensive calculation.
    paired_differences(rows, tuple(expected_seeds)[:len(rows)], spec["orientation"])
    margin = next(x["value"] for x in design["thresholds"]
                  if (x["regime"], x["statistic"]) == key)
    results = []
    for look in schedule:
        n = look["look_n"]
        cumulative = summarize(rows[:n], look["cumulative_seeds"], orientation=spec["orientation"])
        fresh = summarize(rows[n-100:n], look["fresh_block_seeds"], orientation=spec["orientation"])
        lower, upper = cumulative["paired_bootstrap_95_ci"]
        inherited = "lower-ci>=-margin" if key == ("T", "RMST") else None
        results.append({"role": "CANDIDATE_SCHEDULED_REPORT_NOT_CONFIRMATORY_VERDICT",
                        "contrast_id": spec["contrast_id"], "declaration": dict(spec),
                        "n_seeds": n, "n_train": design["T"], "n_eval": design["N_eval"],
                        "checkpoint_grid": list(design["grid"]), "look": look,
                        "statistics": cumulative, "fresh_block_statistics": fresh,
                        "fixed_endpoint_margin": margin,
                        "margin_label": margin_label(lower, upper, margin, key[1]),
                        "quantity_bound": quantity_bound(lower, upper, margin,
                                                         preregistered_rule=inherited),
                        "T_positive_result_is_contract_review_signal": key[0] == "T" and lower > 0,
                        "tier_role": "learner-feasible" if spec["treatment_tier"] == "L0"
                                     else "ceiling-or-registered-noncore-tier-not-L0-algorithm-ranking",
                        "collection_authorized": False, "scientific_claim_authorized": False,
                        "research_complete": False})
    return results


def reversal(previous, current):
    require(previous["contrast_id"] == current["contrast_id"] and
            previous["declaration"] == current["declaration"] and
            current["n_seeds"] == previous["n_seeds"] + 100,
            "reversal requires the same frozen contrast and adjacent scheduled looks")
    require(previous["fixed_endpoint_margin"] == current["fixed_endpoint_margin"],
            "a changed threshold is not a reversal")
    fresh = current["fresh_block_statistics"]
    require(fresh["n_seeds"] == 100 and number(fresh["mean"]), "fresh block mean required")
    changed = previous["margin_label"] != current["margin_label"]
    inside = abs(fresh["mean"]) <= current["fixed_endpoint_margin"]
    return {"four_way_label_changed": changed, "fresh_block_mean": fresh["mean"],
            "interpretation": "NO_OP_NOT_REVERSAL" if not changed else
                              "DECISION_BOUNDARY_MOVEMENT" if inside else
                              "LABEL_CHANGE_WITH_FRESH_BLOCK_MEAN",
            "CI_excludes_zero_is_not_the_reversal_definition": True,
            "scientific_claim_authorized": False}


def joint_readiness(reports):
    """Enumerate the core conjunction without inventing unspecified bound rules.

    Concrete contrast populations, primary family and Collateral/Retention bound
    registration are still missing. Therefore this cannot emit V0.3R PASS even
    when all supplied intervals look favorable.
    """
    require(type(reports) is list, "endpoint reports required")
    for r in reports:
        validate_spec(r["declaration"])
    keys = [(r["declaration"]["regime"], r["declaration"]["statistic"]) for r in reports]
    require(len(keys) == len(set(keys)), "a core endpoint cannot be duplicated or pooled")
    expected = set(ORIENTATIONS)
    require(set(keys) <= expected, "unknown core endpoint")
    eligible = all(r["look"]["primary_final"] and r["n_seeds"] == 400 and
                   r["declaration"]["stage"] == "primary" and
                   r["declaration"]["reference_tier"] == r["declaration"]["treatment_tier"] == "L0"
                   for r in reports)
    return {"status": "JOINT_VERDICT_CLOSED_PENDING_COMPLETE_COLLECTION_AND_ANALYSIS_GATE",
            "required_endpoint_keys": [list(x) for x in ORIENTATIONS],
            "missing_endpoint_keys": [list(x) for x in ORIENTATIONS if x not in keys],
            "complete_core_endpoint_presence": set(keys) == expected,
            "all_reports_primary_final_same_L0_tier": bool(reports) and eligible,
            "joint_rule": "P RMST and DeficitAUC benefit AND Collateral bound AND Retention criterion AND separate T harm/companion constraints",
            "missing_authority": ["concrete population/arm/contrast/family preregistration",
                                  "Collateral and Retention persistence/noninferiority rule registration",
                                  "full integration/workload/collection gate and complete acquired seed provenance",
                                  "full final family correction and qualified conjunct decisions"],
            "weighted_score_used": False, "V03R_PASS": False,
            "V04R_authorized": False, "collection_authorized": False,
            "scientific_claim_authorized": False, "research_complete": False}
