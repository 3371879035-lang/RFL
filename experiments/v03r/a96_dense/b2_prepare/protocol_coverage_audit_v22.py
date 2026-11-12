"""Read-only coverage analysis of existing bytes, not a scientific gate.

stdlib only: no RFL import, rollout, update, RNG, test, source mutation or
automatic output write. The saved v20 fixture is NOT the scientific population.
This auditor selects no whole-set region, aggregation, threshold or family.
"""
from __future__ import annotations

import ast
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha1, sha256
import itertools
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parent
REL = FOLDER.relative_to(ROOT).as_posix()
F1 = "experiments/v03r/a96_dense"
PARENT = "e978316c70e7ba2dd93c05595b8190f895c2a8da"
SOURCE_SHA = "1dfd80ce49255231998b70fca2b7bcd72e0940822a1bf9d4a8e731603ccc4838"
LOCK_SHA = "7d43ee9ae33a218e1266ab3cd2351e07d7e30922302e4527c65facbddaa3472f"
STDOUT_SHA = "30d875614f7fd3efb2939aabd5bab62a25165f9ba008cb0e5df8f8d5a6f05760"
PAYLOAD_SHA = "aababacfc468ca2e7882ab15bf645819cd53ffd465fde5ace00e886e6b6de308"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def raw(name):
    path = (ROOT / name).resolve()
    require(path.is_relative_to(ROOT) and path.is_file(), "invalid input: " + name)
    return path.read_bytes()


def load(name):
    return json.loads(raw(name))


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def marked(text, name):
    values = [line[len(name):] for line in text.splitlines() if line.startswith(name)]
    require(len(values) == 1, "one complete stored marker required: " + name)
    return json.loads(values[0])


def function(name, qualified):
    """Parse source text; never import or execute the inspected module."""
    node = ast.parse(raw(name).decode("utf-8"))
    for part in qualified.split("."):
        nodes = [n for n in node.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))
                 and n.name == part]
        require(len(nodes) == 1, "unique source function required: " + qualified)
        node = nodes[0]
    return {"path": name, "function": qualified, "lines": [node.lineno, node.end_lineno],
            "actual_sha256": sha256(raw(name)).hexdigest()}


def main():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    require(head == PARENT, "audit requires its declared parent HEAD")
    frozen = load(F1 + "/pipeline/frozen_inputs.json")
    sources = frozen["sources"]
    require(len(sources) == 313 and all(sha256(raw(n)).hexdigest() == h for n, h in sources.items()),
            "original frozen313 byte drift")
    source_digest = sha256((json.dumps(sources, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")).hexdigest()
    require(source_digest == frozen["sources_digest"] == SOURCE_SHA, "parent source digest differs")
    native = load(F1 + "/pipeline/full_f1_complete_external_audit.json")
    native_hashes = dict(native["audit"]["fixed_native_file_hashes"])
    native_hashes.update(native["audit"]["post_controller_commit_native_tail_hashes"])
    require(len(native_hashes) == 153 and all(sha256(raw(n)).hexdigest() == h
        for n, h in native_hashes.items()), "old native153 byte drift")
    require(sha256(raw(F1 + "/dev_lock.json")).hexdigest() == LOCK_SHA,
            "atomic F1 lock drift")
    require(native["native_F1_receipt"]["native_exit_code"] ==
        native["native_controller_exit"]["native_exit_code"] == 0,
        "original closed native F1/controller evidence missing")
    git_entries = {}
    tree = subprocess.check_output(["git", "ls-tree", "-r", "--full-tree", "-z", head], cwd=ROOT)
    for entry in tree.split(b"\0"):
        if entry:
            metadata, name = entry.split(b"\t", 1)
            git_entries[name.decode("utf-8")] = metadata.split()[2].decode("ascii")
    prep = sorted(n for n in git_entries if n.startswith(REL + "/"))
    require(len(prep) == 227, "declared prior preparation universe changed")
    bound = sorted(set(sources) | set(prep) | {"experiments/rebuild_status_current.json"})
    require(len(bound) == 541, "prior source/preparation/ledger universe changed")
    for name in bound:
        data = raw(name)
        blob = sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
        require(blob == git_entries[name], "actual parent Git bytes differ: " + name)
    spec = load(REL + "/whole_cell_inputs_candidate_v20.json")
    require(len(spec["input_file_hashes"]) == 210 and all(sha256(raw(n)).hexdigest() == h
        for n, h in spec["input_file_hashes"].items()), "stored v20 execution inputs drift")
    stdout_path = REL + "/evidence_v20/whole_cell_full_preparation.stdout.log"
    stdout = raw(stdout_path)
    require(len(stdout) == 9467903 and sha256(stdout).hexdigest() == STDOUT_SHA,
            "complete original v20 stdout differs")
    text = stdout.decode("utf-8")
    stored = marked(text, "FULL_WHOLE_CELL_RAW_V20=")
    payload = stored["complete_payload"]
    require(digest(payload) == stored["complete_payload_sha256"] == PAYLOAD_SHA,
            "complete raw payload seal differs")
    rows = marked(text, "FULL_WHOLE_CELL_PRE_CENSUS_V20=")["ordered_rows"]
    require(len(rows) == 5760 and digest(rows) == payload["pre_census"]["full_census_sha256"],
            "complete stored census seal differs")
    domain = itertools.product(range(2), range(6), range(2), range(60), range(4))
    for row, key in zip(rows, domain):
        require(len(row) == 5 and tuple(row[0]) == key and type(row[1]) is bool and
            len(row[2]) == 12 and all(type(v) is bool for v in row[2]),
            "stored scene chronology or flags differ")
    suite = marked(text, "FULL_PREPARATION_SUITE_V20=")
    require(suite["input_hashes_before"] == suite["input_hashes_after"] == spec["input_file_hashes"],
            "original v20 before/after input binding differs")
    sites = payload["pre_census"]["ordered_sites"]
    require(len(sites) == len(set(sites)) == 12 and stored["environment_seed_draws"] ==
        stored["future_training_episodes"] == 0, "stored fixture role/count differs")
    require(payload["whole_native_pair"]["B1_arm_calls"] == 2 and
        all(l["n_addressed"] == len(l["ordered_receipts"]) == 12
            for l in payload["whole_native_pair"]["ordered_arm_ledgers"]),
        "same complete whole B1 pair required")
    for key in ("primary_Collateral_scalar", "multi_credit_region", "per_site_to_primary_aggregation"):
        require(payload[key] is None, "stored component cannot define an unapproved endpoint")
    descriptions = []
    key_sequences = []
    for i, site in enumerate(sites):
        eligible = [r for r in rows if r[1] and not r[2][i]]
        keys = [r[0] for r in eligible]
        key_sequences.append(keys)
        maps = [payload["all_pre_maps"][i]] + [role["maps"][i]
            for role in payload["ordered_post_maps"]]
        require(len(maps) == 3 and all(m["ordered_unit_keys"] == keys and m["site"] == site and
            m["construction"] == "E1(c=" + site + ")@eligible_all" and
            len(m["values_hex"]) == len(keys) for m in maps), "original E(c) map domain differs")
        diagnostic = payload["per_site_diagnostics_after_same_whole_update"][i]
        counts = [sum(int(r[2][j]) for r in eligible) for j in range(12)]
        require(counts == diagnostic["ordered_other_credit_consult_counts"] and counts[i] == 0,
            "stored cross-credit incidence disagrees")
        descriptions.append({"site": site, "original_E_c_size": len(keys),
            "ordered_unit_keys_sha256": digest(keys),
            "eligible_scenes_consulting_any_other_written_site": sum(any(r[2]) for r in eligible),
            "ordered_other_credit_consult_counts": counts,
            "pre_equals_reference_elementwise_hex": maps[0]["values_hex"] == maps[1]["values_hex"],
            "pre_equals_treatment_elementwise_hex": maps[0]["values_hex"] == maps[2]["values_hex"],
            "stored_native_raw_difference_hex": diagnostic["ordered_native_raw_difference_hex"]})
    histogram = Counter((r[1], sum(r[2])) for r in rows)
    report = {
        "schema": "a96-original-protocol-implementation-coverage-audit-v22",
        "role": "EXTERNAL_READ_ONLY_COVERAGE_DIAGNOSIS_NOT_PROTOCOL_EXTENSION_OR_NATIVE_SCIENTIFIC_GATE",
        "parent_commit": head,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "direct_human_request": "Continue after v21 scope correction; no new endpoint, population reduction, ordinary algorithm family or acquisition inferred.",
        "byte_verification": {"frozen313_digest": source_digest, "original_native_bindings": 153,
            "F1_lock_sha256": LOCK_SHA, "prior_preparation_files": 227,
            "prior_HEAD_source_preparation_ledger_byte_bindings": len(bound),
            "prior_v20_execution_inputs": 210, "full_v20_stdout_path": stdout_path,
            "full_v20_stdout_bytes": len(stdout), "full_v20_stdout_sha256": STDOUT_SHA,
            "full_v20_payload_sha256": PAYLOAD_SHA,
            "auditor_sha256": sha256(Path(__file__).read_bytes()).hexdigest()},
        "source_coverage": [
            {**function("src/rfl_rebuild/method/credit.py", "OracleCreditAdapter.evaluate"),
                "finding": "Evaluator-only Oracle takes Gamma_star, not ordinary method input. It is NOT a new diagnostic algorithm to select."},
            {**function(REL + "/factual_event_candidate.py", "_persistent_truth"),
                "finding": "Candidate engineering evaluator retains all actual P manifestations separately from learner evidence; it does not authenticate a science population or collector."},
            {**function("src/rfl_rebuild/b1/runner.py", "_run"),
                "finding": "Native B1 plans all supplied credited addresses against one pre-state and commits one transaction; no singleton-equivalence or B2 endpoint follows."},
            {**function("src/rfl_rebuild/b1/process.py", "resolve_process_addresses"),
                "finding": "Within one episode the Process channel has the one static ProcessCommit unit and resolves one explicitly assisted proposal. Do not conflate regime P with Process architecture P or claim every architecture requires multiple addresses."},
            {**function("src/rfl_rebuild/b2/unaffected.py", "eligibility"),
                "finding": "Original E(c) excludes reads of only the declared c and requires pre SUCCESS. No simultaneous-set endpoint or aggregation is implemented here."},
            {**function("src/rfl_rebuild/b2/runner.py", "PairedRunner._run_instrument"),
                "finding": "Every architecture's resolved credit must exactly equal one credited_site.address before E(c), B1 or future training runs. This is a safety binding, not an original all-manifestations scope reduction."},
            {**function(REL + "/native_record_candidate.py", "validate_ledger"),
                "finding": "Candidate extractor also requires one addressed receipt; a whole B1 ledger cannot be relabelled singleton even if a future curve is available."},
            {**function(REL + "/credit_delivery_candidate.py", "prepare_credit"),
                "finding": "This optional proposal-expansion adapter rejects the evaluator Oracle path by design. Reusing it as mandatory Oracle update-law routing is not justified; do not loosen its truth-blind contract."},
        ],
        "normative_quantifiers": [
            {"path": "docs/rebuild/12-AMENDMENTS.md", "lines": [3414, 3503],
                "finding": "A75 retains all genuine manifestations and requires k-by-shape defect-family reports. Installed k, manifested cardinality, predicted cardinality and independent seed are distinct."},
            {"path": "docs/rebuild/12-AMENDMENTS.md", "lines": [6854, 6972],
                "finding": "A89 quantifies nonempty/proper E(c) and refinement totality over individual production sites. That quantifier alone does not authorize a simultaneous-set domain or per-site primary aggregation."},
            {"path": "docs/rebuild/12-AMENDMENTS.md", "lines": [4858, 4881],
                "finding": "A79 compares native update laws with same-tier references, not unselected diagnostic candidates; ceilings are not algorithm rankings."},
        ],
        "new_stored_fixture_coverage_diagnosis": {
            "input_role": "OLD_V20_SEEDLESS_TRAJECTORY_CANDIDATE_FIXTURE_NOT_ORACLE_TRUTH_OR_SCIENTIFIC_POPULATION",
            "ordered_site_count": len(sites), "old_complete_pre_census_scenes": len(rows),
            "pre_outcome_by_number_of_consulted_fixture_addresses": [
                {"pre_SUCCESS": success, "number_consulted": number, "scene_count": count}
                for (success, number), count in sorted(histogram.items())],
            "all12_original_E_c_have_identical_ordered_scene_keys": all(k == key_sequences[0] for k in key_sequences),
            "per_site_descriptions": descriptions,
            "coverage_conclusion": "This retained fixture does not discriminate per-site from simultaneous-set nonconsult semantics: every original E(c) is the same list and contains no reads of any other written fixture address. Every stored pre/reference/treatment map is elementwise equal. These zeros establish neither science gain nor a calibrated whole-set primary endpoint.",
            "limitations": [
                "Not evidence that cross-credit contamination occurs in this particular fixture.",
                "Not evidence that all original scientific populations have identical eligibility sets or singleton manifestations.",
                "No E(S), union/intersection, mean/max aggregation or alternative threshold was selected or measured.",
                "Repeated per-site membership is not twelve independent samples; no scientific sample was added.",
            ],
        },
        "implementation_decision_boundary": {
            "safe_further_work": "Only necessary normative/implementation coverage clarification independent of new scientific choices; preserve original credit and byte-bound evidence.",
            "before_material_endpoint_change": "Explain precise uncovered whole-manifestation measurement and obtain direct human direction for a prospective specification draft; draft does not ratify the endpoint or authorize collection.",
            "not_an_old_candidate_binary_choice": True,
            "not_repaired_by_dropping_credits_or_loosening_singleton_guard": True,
            "coverage_not_closed": True,
        },
        "new_execution": {"new_rollouts": 0, "B1_calls": 0, "future_training_episodes": 0,
            "environment_or_analysis_RNG_draws": 0, "tests_rerun": 0,
            "scientific_keys_allocated": 0, "engineering_workload_keys_allocated": 0,
            "original_sources_or_old_evidence_edited": False,
            "new_native_scientific_validation_PASS": False, "independent_expert_review": False},
        "scientific_state": {"F1": "LOCKED_PRESERVED", "collection_authorized": False,
            "new_endpoint_or_scope_reduction_authorized": False,
            "scientific_result": "NOT_EVALUATED_F1_DESIGN_LOCKED", "research_complete": False,
            "valid_current_scientific_STOP_or_NO_ADMISSIBLE": False, "continuation_active": True},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
