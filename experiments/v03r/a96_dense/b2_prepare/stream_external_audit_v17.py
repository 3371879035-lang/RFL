"""Primary-agent independent byte/seed aggregation check, NOT a native gate.

Does not import the stream candidate/extractor or historical programs. Fixed
readonly artifacts and inputs only; no outcome statistics or key allocation.
"""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat

ROOT = Path(__file__).resolve().parents[4]
FOLDER = Path(__file__).resolve().parent
INITIAL_SHA = "282fee1e91e2764bc1d3cd29e15e76e0915e44ac228da44aad90d6a3ee9deb9f"
CORRECTED_SHA = "e05b0d2aaf79fa4bbada1fe869888a75ca108900e2ffc4ecfd6dc46b274b3652"


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("ascii")


def duplicate_safe(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, "duplicate JSON member"
        result[key] = value
    return result


def finite_float(text):
    value = float(text)
    assert math.isfinite(value), "nonfinite/overflow JSON number"
    return value


def reject_constant(text):
    raise AssertionError("nonfinite JSON constant")


def strict(blob):
    return json.loads(blob.decode("utf-8-sig"), object_pairs_hook=duplicate_safe,
                      parse_float=finite_float, parse_constant=reject_constant)


def byte_hash(path):
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"bytes": size, "sha256": digest.hexdigest()}


def safe_path(name, relative):
    assert type(name) is str and name not in ("", ".", "..") and "/" not in name and "\\" not in name and ":" not in name
    assert type(relative) is str and relative and "\\" not in relative and ":" not in relative
    rel = PurePosixPath(relative)
    assert not rel.is_absolute() and rel.as_posix() == relative and all(p not in ("", ".", "..") for p in relative.split("/"))
    root = ROOT.parent / name
    assert root.resolve().parent == ROOT.parent.resolve()
    here = root
    for component in (None,) + rel.parts:
        if component is not None:
            here /= component
        attrs = here.lstat()
        assert not here.is_symlink() and not (getattr(attrs, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    assert here.is_file() and here.resolve().is_relative_to(root.resolve())
    return here


def singleton_union(values):
    # Independent integer set -> ordered compact union; no candidate merge helper.
    result = []
    for value in sorted(values):
        if result and value == result[-1][1] + 1:
            result[-1][1] = value
        else:
            result.append([value, value])
    return [[str(a), str(b)] for a, b in result]


def audit():
    pair = []
    for filename, expected in (("stream_snapshot.stdout.log", INITIAL_SHA),
                               ("stream_snapshot_corrected.stdout.log", CORRECTED_SHA)):
        path = FOLDER / "evidence_v17" / filename
        raw = path.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected
        value = strict(raw)
        assert hashlib.sha256(canonical(value["payload"])).hexdigest() == value["payload_sha256"]
        assert value["collection_authorized"] is False and value["research_complete"] is False
        pair.append(value)
    initial, corrected = (v["payload"]["file_evidence"] for v in pair)
    assert len(initial) == len(corrected) == 100
    assert [(r["root"], r["path"], r["bytes"], r["sha256"]) for r in initial] == [
        (r["root"], r["path"], r["bytes"], r["sha256"]) for r in corrected]
    records = claims = total_bytes = firstpass_discarded_files = 0
    aliases, rows, paths = set(), [], []
    for before, result in zip(initial, corrected):
        path = safe_path(result["root"], result["path"])
        expected_bytes = {"bytes": result["bytes"], "sha256": result["sha256"]}
        total_bytes += result["bytes"]
        if path.suffix.lower() == ".jsonl":
            assert result["parse_complete"] and not result["issues"]
            if not before["parse_complete"]:
                firstpass_discarded_files += 1
                assert before["claims"] == [] and before["conservative_exclusion_intervals_decimal_inclusive"] == []
            expected = {(r["field"], int(r["original_integer_decimal"])): r for r in result["claims"]}
            assert len(expected) == len(result["claims"]) and all(k[0] == "seed" for k in expected)
            observed = {}
            digest, size, count = hashlib.sha256(), 0, 0
            with path.open("rb") as handle:
                for raw in handle:
                    digest.update(raw)
                    size += len(raw)
                    count += 1
                    assert len(raw) <= 16 * 1024 * 1024 and raw.strip()
                    assert count == 1 or not raw.startswith(b"\xef\xbb\xbf")
                    obj = strict(raw)
                    assert type(obj) is dict
                    stack = [("", obj)]
                    while stack:
                        pointer, node = stack.pop()
                        if type(node) is dict:
                            for key, value in node.items():
                                p = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
                                if key == "seed":
                                    assert type(value) is int
                                    row = observed.setdefault(("seed", value), {"occurrences": 0,
                                        "first_record": count, "example_pointer": p})
                                    row["occurrences"] += 1
                                if type(value) in (dict, list):
                                    stack.append((p, value))
                        elif type(node) is list:
                            for i, value in enumerate(node):
                                if type(value) in (dict, list):
                                    stack.append((pointer + "/" + str(i), value))
            assert {"bytes": size, "sha256": digest.hexdigest()} == expected_bytes
            assert observed.keys() == expected.keys()
            for key, observed_row in observed.items():
                expected_row = expected[key]
                assert all(expected_row[k] == observed_row[k] for k in observed_row)
                assert expected_row["canonical_modulo64_exclusion_decimal"] == str(key[1] % (1 << 64))
                assert expected_row["original_is_canonical_uint64"] == (0 <= key[1] < (1 << 64))
            file_aliases = {k[1] % (1 << 64) for k in observed}
            assert singleton_union(file_aliases) == result["conservative_exclusion_intervals_decimal_inclusive"]
            aliases.update(file_aliases)
            assert count == result["physical_record_count"] == result["valid_object_record_count"]
            assert result["invalid_record_count"] == 0
            records += count
            claims += len(expected)
        else:
            assert path.suffix.lower() == ".json" and not result["parse_complete"]
            assert result["claims"] == [] and result["conservative_exclusion_intervals_decimal_inclusive"] == []
            assert byte_hash(path) == expected_bytes
        rows.append({"root": result["root"], "path": result["path"], **expected_bytes})
        paths.append((path, expected_bytes))
    assert total_bytes == 915316767 and records == 733754 and claims == 43849 and firstpass_discarded_files == 1
    assert singleton_union(aliases) == pair[1]["payload"]["conservative_exclusion_intervals_decimal_inclusive"]
    # Whole100-file stable boundary independently repeated from actual disk bytes.
    for path, expected in paths:
        assert byte_hash(path) == expected
    return {"schema": "a96-primary-readonly-stream-external-audit-v17",
        "role": "INDEPENDENT_IMPLEMENTATION_PRIMARY_AGENT_CHECK_NOT_NATIVE_SCIENTIFIC_PASS",
        "files_actual_SHA_before_after_checked": 100, "total_actual_bytes": total_bytes,
        "both_engineering_snapshots_identical_input_bytes": True,
        "complete_JSONL_files_checked": 98, "complete_JSONL_records_not_statistical_N": records,
        "file_grouped_declared_seed_claims_not_science_samples": claims,
        "distinct_modulo64_aliases_not_statistical_N": len(aliases),
        "compact_union_interval_count": len(singleton_union(aliases)),
        "actual_input_binding_rows_sha256": hashlib.sha256(canonical(rows)).hexdigest(),
        "initial_one_capacity_refusal_full_file_no_prefix_claims_retained": True,
        "two_ordinary_large_JSON_semantic_gaps_not_silently_passed": True,
        "no_candidate_extractor_or_union_helper_imported": True,
        "historical_programs_executed": False, "environment_key_draws": 0,
        "keys_allocated_or_reserved": False, "complete_historical_usage_freshness_audit": False,
        "collection_authorized": False, "scientific_claim_authorized": False,
        "research_complete": False}


if __name__ == "__main__":
    print(canonical(audit()).decode("ascii"))
