"""Strict, size-bounded whole-JSON history declarations; never a collection gate.

Only two immutable old support-cache inputs from the already bound v17 snapshot.
Whole-file decoding is serial, not constant-memory; file caps do not bound decoder
object overhead. No historical program, generator, allocator or trainer is run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import history_seed_audit_candidate as history
import history_stream_candidate as stream
import readiness as ready

_FOLDER = Path(__file__).resolve().parent
_CONTRACT = _FOLDER / "large_json_contract_candidate_v18.json"
_SNAPSHOT = _FOLDER / "evidence_v17/stream_snapshot_corrected.stdout.log"
_SNAPSHOT_SHA = "e05b0d2aaf79fa4bbada1fe869888a75ca108900e2ffc4ecfd6dc46b274b3652"
_PAYLOAD_SHA = "45c2d27c0697ea2e1c19461ba748a4f7458263ecff90ca1746eca3c74de83ee3"
_JSON_LIMIT = 128 * 1024 * 1024
_SCOPE_LIMIT = 192 * 1024 * 1024
_CLAIM_LIMIT = 262144
_TARGETS = (
    ("RFL-CausalChase-v0.3", "experiments/v01r/support_cache.json", 115542484,
     "4f429347a7c0a039013ef1a401e2a6d2bf29e947cf8e191c7655296a2418a4b1"),
    ("RFL-CausalChase-v0.3", "experiments/v01r/support_cache_slice.json", 57384499,
     "e535f31614112eed9161b4598468d629758c267593a0dba4933456091c2ca872"),
)
_BINDINGS = (Path(__file__), _CONTRACT, _FOLDER / "test_history_large_json_candidate.py",
             Path(history.__file__), Path(stream.__file__), Path(ready.__file__), _SNAPSHOT)
_BOUND = tuple(ready.file_hash(p) for p in _BINDINGS)


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("ascii")


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _guard():
    base, roots = stream._guard()
    ready.require(tuple(ready.file_hash(p) for p in _BINDINGS) == _BOUND and
                  ready.file_hash(_SNAPSHOT) == _SNAPSHOT_SHA,
                  "large-JSON code/test/contract/dependency/parent evidence drift")
    contract = history._strict_json(_CONTRACT.read_bytes())
    ready.require(contract["schema"] == "a96-large-json-history-contract-candidate-v18" and
                  contract["parent_preparation_commit"] == "ef064c442cd1f9feea3f077331cb6c96a2589e34" and
                  tuple((r["root"], r["path"], r["bytes"], r["sha256"])
                        for r in contract["inputs"]) == _TARGETS and
                  contract["parent_sources_digest"] == "1dfd80ce49255231998b70fca2b7bcd72e0940822a1bf9d4a8e731603ccc4838" and
                  contract["lock_sha256"] == "7d43ee9ae33a218e1266ab3cd2351e07d7e30922302e4527c65facbddaa3472f" and
                  contract["collection_authorized"] is False and
                  contract["keys_allocated_or_reserved"] is False and
                  contract["complete_historical_usage_freshness_audit"] is False,
                  "large-JSON closed role differs")
    return base, roots


def inspect_large_json_bytes(blob):
    """Strict complete JSON using immutable v15 semantics; no prefix extraction.

    Declarations/counts/issues retain v15 meanings. No outcome or world-number
    interpretation. Whole-file UTF8/BOM, duplicate-member and finite-number checks
    precede any retained claim. Resource refusal never retains partial identities.
    Exact historical integers and modulo64 exclusions leave as decimal strings.
    """
    ready.require(type(blob) is bytes, "native byte input required")
    result = {"bytes": len(blob), "sha256": _sha(blob), "parse_complete": False,
              "claims": [], "conservative_exclusion_intervals_decimal_inclusive": [],
              "issues": [], "identity_role":
              "CONSERVATIVE_HISTORICAL_DECLARATIONS_NOT_VALID_RUN_OR_STATISTICAL_N"}
    def refused(reason):
        result["parse_complete"] = False
        result["claims"] = []
        result["conservative_exclusion_intervals_decimal_inclusive"] = []
        result["issues"] = [{"reason": reason, "occurrences": 1, "example_pointer": ""}]
        return result
    if len(blob) > _JSON_LIMIT:
        return refused("whole-JSON-file-size-resource-refusal-no-prefix-identities")
    try:
        parsed = history.inspect_json_bytes(blob)
        if not parsed["parse_complete"]:
            result["issues"] = parsed["issues"]
            return result
        if len(parsed["claims"]) > _CLAIM_LIMIT or len(parsed["intervals_inclusive"]) > _CLAIM_LIMIT:
            return refused("whole-JSON-claim-or-interval-resource-refusal-no-prefix-identities")
        union = history.merge_intervals(parsed["intervals_inclusive"] + [
            [r["canonical_modulo64_exclusion"]] * 2 for r in parsed["claims"]])
        # Build candidate exports locally before assigning: MemoryError must not
        # leave any prefix of identities in the returned result.
        claims = [{"field": r["field"], "original_integer_decimal": str(r["original_integer"]),
            "canonical_modulo64_exclusion_decimal": str(r["canonical_modulo64_exclusion"]),
            "original_is_canonical_uint64": r["original_is_canonical_uint64"],
            "occurrences": r["occurrences"], "example_pointer": r["example_pointer"]}
            for r in parsed["claims"]]
        intervals = [[str(a), str(b)] for a, b in union]
        result.update(parse_complete=True, claims=claims,
            conservative_exclusion_intervals_decimal_inclusive=intervals, issues=parsed["issues"])
        return result
    except MemoryError:
        # Best-effort fail closed. Hard process/system OOM is operationally
        # incomplete, not a negative scientific result or automatic retry.
        return refused("whole-JSON-decoder-MemoryError-no-prefix-identities")


def _bound_targets(snapshot, roots):
    ready.require(snapshot["payload_sha256"] == _PAYLOAD_SHA and
                  _sha(stream._canonical(snapshot["payload"])) == _PAYLOAD_SHA,
                  "v17 full snapshot payload differs")
    found = [(r["root"], r["path"], r["bytes"], r["sha256"])
             for r in snapshot["payload"]["file_evidence"] if r["path"] in {
                 t[1] for t in _TARGETS} and r["root"] == "RFL-CausalChase-v0.3"]
    ready.require(tuple(sorted(found)) == _TARGETS and len(found) == len(set(found)) and
                  all(n in roots for n, _, _, _ in _TARGETS),
                  "exactly two v17-bound ordinary JSON targets required")
    ready.require(sum(t[2] for t in _TARGETS) <= _SCOPE_LIMIT and
                  all(t[2] <= _JSON_LIMIT for t in _TARGETS), "closed JSON input size bound exceeded")
    return _TARGETS


def snapshot_large_json_history():
    """Closed read-only scope; no root, key, output or resource overrides."""
    base, roots = _guard()
    snapshot = history._strict_json(_SNAPSHOT.read_bytes())
    targets = _bound_targets(snapshot, roots)
    results = []
    # One complete file at a time. Explicitly delete raw input before the next
    # file; this is NOT a streaming parser nor a hard RSS/decoder-memory bound.
    for name, relative, expected_bytes, expected_sha in targets:
        path = stream._safe_path(base, name, relative)
        ready.require(path.stat().st_size == expected_bytes, "large JSON size drift")
        with path.open("rb") as handle:
            before = stream.hash_chunks(stream._chunks(handle))
        ready.require(before == {"bytes": expected_bytes, "sha256": expected_sha},
                      "large JSON actual bytes differ from v17")
        with path.open("rb") as handle:
            blob = handle.read(_JSON_LIMIT + 1)
            ready.require(not handle.read(1), "bounded JSON read must include complete file")
        result = inspect_large_json_bytes(blob)
        del blob
        ready.require(result["bytes"] == expected_bytes and result["sha256"] == expected_sha,
                      "large JSON parse input differs from prior complete hash")
        results.append({"root": name, "path": relative, "v17_actual_sha256": expected_sha, **result})
    # Rehash BOTH complete inputs after the entire semantic pass, not existence
    # or size only. A drift prevents emitting the snapshot, not a partial PASS.
    for name, relative, expected_bytes, expected_sha in targets:
        path = stream._safe_path(base, name, relative)
        with path.open("rb") as handle:
            after = stream.hash_chunks(stream._chunks(handle))
        ready.require(after == {"bytes": expected_bytes, "sha256": expected_sha},
                      "large JSON changed at full scope boundary")
    _guard()
    union = history.merge_intervals([[int(a), int(b)] for r in results
        for a, b in r["conservative_exclusion_intervals_decimal_inclusive"]])
    payload = {"fixed_v17_input_snapshot_sha256": _SNAPSHOT_SHA,
        "fixed_target_count": len(results), "total_actual_bytes": sum(r["bytes"] for r in results),
        "full_scope_before_after_actual_SHA_match": True, "file_evidence": results,
        "conservative_exclusion_intervals_decimal_inclusive": [[str(a), str(b)] for a, b in union],
        "all_two_complete_JSON_syntax_and_declared_fields_parsed": all(r["parse_complete"] for r in results),
        "remaining_gaps": ["no authenticated execution/role association inferred from declarations",
            "unknown/dynamic seed fields, external schedules and wider retained scopes",
            "archive/opaque/Git history and unresolved PS/log/MD/TOML/unreferenced TXT",
            "v16/v17/v18 and future fixture-role exclusions require separate complete inventory",
            "B2 real fault population/integrated gates/workload/resources/frozen collection preregistration"]}
    return {"schema": "a96-large-json-history-snapshot-candidate-v18",
        "role": "TWO_FULL_BOUND_JSON_DECLARATIONS_NOT_UNUSED_KEY_CERTIFICATE",
        "payload": payload, "payload_sha256": _sha(_canonical(payload)),
        "parent_sources_digest": "1dfd80ce49255231998b70fca2b7bcd72e0940822a1bf9d4a8e731603ccc4838",
        "lock_sha256": "7d43ee9ae33a218e1266ab3cd2351e07d7e30922302e4527c65facbddaa3472f",
        "complete_historical_usage_freshness_audit": False, "seed_plan_v14_exclusions_automatically_extended": False,
        "keys_allocated_or_reserved": False, "environment_key_draws": 0,
        "native_protocol_or_training_started": False, "collection_authorized": False,
        "scientific_claim_authorized": False, "research_complete": False}


if __name__ == "__main__":
    ready.require(len(sys.argv) == 1, "no history-scope, key, output or collection CLI override")
    print(_canonical(snapshot_large_json_history()).decode("ascii"))

