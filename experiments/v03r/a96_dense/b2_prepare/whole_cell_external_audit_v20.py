"""Separate stdlib raw-output audit, not a new native science validation PASS."""
from hashlib import sha256
import itertools
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parent
EVIDENCE = FOLDER / "evidence_v20"


def require(condition, message):
    if not condition: raise RuntimeError(message)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def marked(text, name):
    rows = [line[len(name):] for line in text.splitlines() if line.startswith(name)]
    require(len(rows) == 1, "exact single complete raw marker required: " + name)
    return json.loads(rows[0])  # complete JSON only, no prefix salvage


def passed_cases(path, n):
    text = path.read_text(encoding="utf-8")
    cases = re.findall(r"^test_[^\r\n]+ \(([^\r\n]+)\) \.\.\. ok$", text, re.M)
    require(len(cases) == n and len(set(cases)) == n, "complete distinct successful case IDs required")
    require(re.search(r"^Ran " + str(n) + r" tests in [0-9.]+s$", text, re.M), "complete suite footer missing")
    require(text.rstrip().endswith("OK") and not re.search(r"\.\.\. (?:FAIL|ERROR|skipped)", text),
            "no failure/error/skip permitted")
    return tuple(cases)


def main():
    full_path = EVIDENCE / "whole_cell_full_preparation.stdout.log"
    text = full_path.read_text(encoding="utf-8")
    audit = marked(text, "FULL_WHOLE_CELL_RAW_V20=")
    raw_census = marked(text, "FULL_WHOLE_CELL_PRE_CENSUS_V20=")
    suite = marked(text, "FULL_PREPARATION_SUITE_V20=")
    spec = json.loads((FOLDER / "whole_cell_inputs_candidate_v20.json").read_text(encoding="utf-8"))
    pipeline = FOLDER.parent / "pipeline"
    frozen = json.loads((pipeline / "frozen_inputs.json").read_text(encoding="utf-8"))
    parent_audit = json.loads((pipeline / "full_f1_complete_external_audit.json").read_text(encoding="utf-8"))
    sources = frozen["sources"]
    require(len(sources) == 313 and all(sha256((ROOT / name).read_bytes()).hexdigest() == expected
        for name, expected in sources.items()), "all original313 actual source bytes required")
    source_digest = sha256((json.dumps(sources, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")).hexdigest()
    require(source_digest == frozen["sources_digest"] == spec["parent_sources_digest"],
            "complete original313 canonical source digest differs")
    native_hashes = dict(parent_audit["audit"]["fixed_native_file_hashes"])
    native_hashes.update(parent_audit["audit"]["post_controller_commit_native_tail_hashes"])
    require(len(native_hashes) == 153 and all(sha256((ROOT / name).read_bytes()).hexdigest() == expected
        for name, expected in native_hashes.items()), "all original native153 byte bindings required")
    require(sha256((FOLDER.parent / "dev_lock.json").read_bytes()).hexdigest() == spec["lock_sha256"] and
        parent_audit["native_F1_receipt"]["native_exit_code"] ==
        parent_audit["native_controller_exit"]["native_exit_code"] == 0,
        "normal closed original F1/controller native0 required")
    current = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in spec["input_file_hashes"]}
    require(current == spec["input_file_hashes"] == suite["input_hashes_before"] == suite["input_hashes_after"],
            "all 210 parent/addon/test/harness input bytes must match before/after/current")
    require(suite["ordered_test_modules"] == spec["complete_preparation_test_modules"] and
            len(suite["ordered_test_modules"]) == 21 and suite["tests_run"] == spec["expected_case_count"] == 806,
            "complete fixed preparation module/case universe required")
    require(suite["failures"] == suite["errors"] == suite["skipped"] == 0, "whole suite must pass without skips")
    small_cases = passed_cases(EVIDENCE / "whole_cell_targeted_corrected.stderr.log", 26)
    all_cases = passed_cases(EVIDENCE / "whole_cell_full_preparation.stderr.log", 806)
    require(set(small_cases).issubset(all_cases), "26 new cases included in 806, not additive")
    initial = (EVIDENCE / "whole_cell_targeted.stderr.log").read_text(encoding="utf-8")
    require("TypeError: 'OwnedDiagnosticRun' object is not callable" in initial and
            not re.search(r"^Ran [0-9]+ tests", initial, re.M),
            "preserve initial harness exit before test execution, not 26 failed science cases")
    require(audit["complete_DQ_credited_site_count"] == 12 and audit["native_U2_pre_rollouts"] == 5760 and
            audit["native_scene_map_calls"] == 36 and audit["native_B1_arm_calls"] == 2 and
            audit["environment_seed_draws"] == audit["future_training_episodes"] == 0,
            "complete whole-cell actual engineering counts differ")
    p = audit["complete_payload"]
    require(digest(p) == audit["complete_payload_sha256"], "full raw payload hash differs")
    targeted = marked((EVIDENCE / "whole_cell_targeted_corrected.stdout.log").read_text(encoding="utf-8"),
                      "SEEDLESS_WHOLE_CELL_V20_SUMMARY=")
    require(targeted["complete_payload_sha256"] == audit["complete_payload_sha256"],
            "separate controlled seedless constructions must retain identical full raw bits")
    require(p["lock_sha256"] == spec["lock_sha256"] == suite["lock_sha256"] and
            p["parent_sources_digest"] == spec["parent_sources_digest"] == suite["parent_sources_digest"],
            "F1/original313 binding differs")
    sites = p["pre_census"]["ordered_sites"]
    membership = p["pre_census"]["production_payload"][2]
    require(len(membership) == 12 and all(type(v) is bool and v is True for v in membership),
            "all full-cell original production memberships required, no partial pass")
    require(len(sites) == len(set(sites)) == 12 and len(p["whole_cell_with_all_residuals"]["residual_predictions"]) == 16,
            "complete D_Q projection and all cross-architecture residuals required")
    rows = raw_census["ordered_rows"]
    require(len(rows) == 5760 and digest(rows) == p["pre_census"]["full_census_sha256"],
            "full actual stored census, not descriptor or prefix required")
    domain = list(itertools.product(range(2), range(6), range(2), range(60), range(4)))
    for row, expected in zip(rows, domain):
        require(type(row) is list and len(row) == 5 and
            type(row[0]) is list and len(row[0]) == 5 and all(type(k) is int for k in row[0]) and
            tuple(row[0]) == expected and type(row[1]) is bool and type(row[2]) is list and
            len(row[2]) == 12 and all(type(k) is bool for k in row[2]),
            "strict complete ordered U2 native census")
        require(all(type(h) is str and re.fullmatch("[0-9a-f]{64}", h) for h in row[3:]),
                "full native trace/row SHA bindings required")
    pre = p["all_pre_maps"]; post = p["ordered_post_maps"]; diagnostics = p["per_site_diagnostics_after_same_whole_update"]
    require(len(pre) == len(diagnostics) == 12 and len(post) == 2 and
            [r["role"] for r in post] == ["reference", "treatment"],
            "all ordered site/role maps required")
    require(all(len(r["maps"]) == 12 for r in post), "post prefix rejected")
    expected_rollouts = 0
    for i, site in enumerate(sites):
        units = [r[0] for r in rows if r[1] and not r[2][i]]
        require(len(units) > 0 and pre[i]["ordered_unit_keys"] == units and
                pre[i]["construction"] == "E1(c=" + site + ")@eligible_all" and pre[i]["site"] == site,
                "complete original E1(c), not E(S)/subset/truth/post selection")
        expected_rollouts += 3 * len(units)
        values = []
        for m in (pre[i], post[0]["maps"][i], post[1]["maps"][i]):
            require(m["site"] == site and m["ordered_unit_keys"] == units and
                    m["construction"] == pre[i]["construction"] and len(m["values_hex"]) == len(units),
                    "same complete ordered original region in every arm")
            vs = [float.fromhex(v) for v in m["values_hex"]]
            require(all(math.isfinite(v) and v.hex() == s for v, s in zip(vs, m["values_hex"])),
                    "exact finite native float hex")
            values.append(vs)
        require(pre[i]["values_hex"] == post[0]["maps"][i]["values_hex"], "NoWrite must be elementwise exact")
        expected = [(sum(values[0]) / len(units) - sum(vs) / len(units)).hex() for vs in values[1:]]
        row = diagnostics[i]
        require(row["site"] == site and row["E1_size"] == len(units) and
                row["ordered_native_raw_difference_hex"] == expected, "original sum arithmetic differs")
        eligible = set(tuple(u) for u in units)
        counts = [sum(int(r[2][j]) for r in rows if tuple(r[0]) in eligible) for j in range(12)]
        require(row["ordered_other_credit_consult_counts"] == counts and counts[i] == 0 and
            row["single_credit_counterfactual_effect"] is False and row["unaffected_by_whole_set_claimed"] is False,
            "cross-credit reads/limitations must remain explicit")
    require(expected_rollouts == audit["map_scene_rollouts"] == 190080, "all actual per-site map rolls required")
    pair = p["whole_native_pair"]
    require(pair["cell"] == p["whole_cell_with_all_residuals"] and pair["B1_arm_calls"] == 2 and
            len(pair["ordered_arm_ledgers"]) == 2, "same whole B1 pair, not 12 isolated edits")
    for ledger in pair["ordered_arm_ledgers"]:
        require(ledger["n_addressed"] == 12 and len(ledger["ordered_receipts"]) == 12,
                "complete native whole ledgers, never fabricated singleton ledger")
    require(pair["ordered_arm_ledgers"][1]["n_scalar"] == 12 and
            float.fromhex(pair["ordered_arm_ledgers"][1]["sum_abs_delta_hex"]) > 0., "native scalar accounting missing")
    for name in ("primary_Collateral_scalar", "multi_credit_region", "per_site_to_primary_aggregation"):
        require(p[name] is None, "unfrozen multi-credit scalar may not be invented")
    for name in ("multi_credit_E_S_defined", "singleton_update_attribution_claimed",
        "native_raw_collateral_record_or_future_protocol_fabricated",
        "portable_security_or_scientific_acquisition_origin_authenticated",
        "full_dense_B2_workload_resources_certified", "collection_authorized", "scientific_claim_authorized", "research_complete"):
        require(audit[name] is False, "engineering material cannot authorize science: " + name)
    chain = audit["runtime_content_chain"]
    prior = "0" * 64
    require(len(chain) == 7, "complete owner execution checkpoint chain")
    for stage, content, current_hash in chain:
        require(digest([prior, stage, content]) == current_hash, "whole-map content chain differs")
        prior = current_hash
    print(json.dumps({"schema": "a96-v20-separate-stdlib-raw-output-audit",
        "auditor": "PRIMARY_AGENT_SEPARATE_CODE_PATH_NOT_INDEPENDENT_AGENT_OR_EXPERT",
        "input_bytes_checked": len(current), "original313_bytes_checked": 313,
        "original_native_receipt_bindings_checked": 153, "full_preparation_tests": 806,
        "new_cases_included": 26, "native_U2_pre_rollouts": 5760,
        "whole_DQ_sites": 12, "residual_predictions": 16, "native_map_calls": 36,
        "native_map_scene_rollouts": 190080, "same_whole_B1_arm_calls": 2,
        "full_raw_payload_sha256": audit["complete_payload_sha256"],
        "full_stdout_bytes": full_path.stat().st_size, "full_stdout_sha256": sha256(full_path.read_bytes()).hexdigest(),
        "case_ids_sha256": digest(all_cases),
        "multi_credit_primary_endpoint_defined": False,
        "external_audit_is_new_native_scientific_validation_PASS": False,
        "collection_authorized": False, "scientific_claim_authorized": False, "research_complete": False},
        sort_keys=True, allow_nan=False))


if __name__ == "__main__": main()
