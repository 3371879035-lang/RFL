"""Read-only, bounded historical-key evidence snapshot; never a freshness gate.

All literal identities found in declared seed fields are conservative exclusions,
not proof of a valid scientific run. Dynamic schedules, archives, Git history,
unparsed formats and the wider workspace remain explicit coverage gaps.
No outcome, environment generator, trainer, allocator or collection entry is used.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

import seed_plan_candidate as plans
import readiness as ready

_FOLDER = Path(__file__).resolve().parent
_SCOPE_PATH = _FOLDER / "history_scope_candidate_v15.json"
_LIMIT = 16 * 1024 * 1024
_PRUNE = frozenset({".git", ".venv", "venv", "__pycache__", ".pytest_cache",
                    "site-packages"})
_TEXT = frozenset({".json", ".jsonl", ".txt", ".py", ".ps1", ".md", ".log",
                   ".yaml", ".yml", ".toml"})
_SINGLE = frozenset({"seed", "experiment_seed", "scenario_seed", "algorithm_seed",
                     "last_visible_seed", "partial_seed", "seed_first", "seed_last"})
_LISTS = frozenset({"seeds", "scientific_seeds", "spent_smoke_seeds",
    "fresh_smoke_seeds", "development_seeds", "stage_seeds", "smoke_seeds",
    "development_fresh_seeds", "scientific_seed_sets", "scientific_seed_sets_reserved",
    "new_scientific_seed_sets", "seed_sets_assigned", "seed_reservation",
    "future_scientific_seed_sets", "scientific_seeds_used", "ordered_seeds",
    "primary_seeds", "secondary_seeds", "engineering_keys", "seed_ids"})
_SCHEDULE = frozenset({"seed_base", "seed_offset", "seed_selection_rule", "seed_files",
                       "seed_file", "seed_registry", "scientific_seed_registry"})
_RANGE = frozenset({"old_engineering_ranges", "operational_fixture_ranges"})
_NONIDENTITY = frozenset({"n_seeds", "seed_count", "seed_index", "seed_draws",
    "scientific_seed_draws", "formal_seed_draws", "environment_seed_draws",
    "environment_key_draws", "episodes_per_seed", "episodes_read_per_seed"})
_STAGES = frozenset({"smoke", "dev", "dev_baseline", "development", "treatment",
    "confirmatory", "primary", "secondary", "engineering", "scientific"})
_SCOPE = ready.read_json(_SCOPE_PATH)
_BINDING_PATHS = (Path(__file__), _SCOPE_PATH, Path(plans.__file__), Path(ready.__file__))
_BINDING = tuple(ready.file_hash(p) for p in _BINDING_PATHS)


def _digest(blob):
    return hashlib.sha256(blob).hexdigest()


def _canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON constant")


def _finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("overflow/nonfinite JSON number")
    return value


def _strict_json(blob):
    return json.loads(blob.decode("utf-8-sig"), object_pairs_hook=_pairs,
                      parse_constant=_reject_constant, parse_float=_finite_float)


def merge_intervals(rows):
    """Compact canonical exclusion union only, never expand a huge interval."""
    ready.require(type(rows) is list, "interval list required")
    result = []
    for pair in rows:
        ready.require(type(pair) in (list, tuple) and len(pair) == 2 and
            all(type(x) is int and 0 <= x < (1 << 64) for x in pair) and
            pair[0] <= pair[1], "canonical inclusive interval required")
    for lo, hi in sorted(tuple(pair) for pair in rows):
        if result and lo <= result[-1][1] + 1:
            result[-1][1] = max(result[-1][1], hi)
        else:
            result.append([lo, hi])
    return result


def subtract_intervals(rows, known):
    """Exact compact set difference; report missing known coverage, not fresh keys."""
    result = []
    cuts = merge_intervals(known)
    for lo, hi in merge_intervals(rows):
        cursor = lo
        for a, b in cuts:
            if b < cursor:
                continue
            if a > hi:
                break
            if a > cursor:
                result.append([cursor, a - 1])
            cursor = max(cursor, b + 1)
            if cursor > hi:
                break
        if cursor <= hi:
            result.append([cursor, hi])
    return result


def inspect_json_bytes(blob):
    """Only declared seed fields, never arbitrary ints, counts or result outcomes.

    Historical negative/overwide literal integers retain their exact originals
    and their modulo64 alias as a conservative exclusion. This is NOT input
    normalization for a new plan: v14 still rejects noncanonical proposed keys.
    Pointers use escaped JSON Pointer components. Repeated occurrences are
    counted with one example pointer, not treated as independent seeds.
    """
    ready.require(type(blob) is bytes, "native byte input required")
    claims, issues, intervals = {}, {}, []
    def issue(pointer, reason):
        row = issues.setdefault(reason, {"reason": reason, "occurrences": 0,
                                        "example_pointer": pointer})
        row["occurrences"] += 1
    def record(pointer, value, field):
        if type(value) is not int:
            issue(pointer, "declared-seed-value-not-literal-native-int")
            return
        alias = value % (1 << 64)
        key = (field, value)
        row = claims.setdefault(key, {"field": field, "original_integer": value,
            "canonical_modulo64_exclusion": alias,
            "original_is_canonical_uint64": value == alias,
            "occurrences": 0, "example_pointer": pointer})
        row["occurrences"] += 1
    def collect(pointer, value, field, *, in_sequence=False):
        if value is None:
            issue(pointer, "unassigned-null-seed-declaration")
        elif type(value) is int:
            if in_sequence:
                record(pointer, value, field)
            else:
                issue(pointer, "scalar-seed-container-may-be-count-not-identity")
        elif type(value) is list:
            for i, v in enumerate(value):
                collect(pointer + "/" + str(i), v, field, in_sequence=True)
        elif type(value) is dict:
            if set(value) <= _STAGES:
                for k, v in value.items():
                    collect(pointer + "/" + escape(k), v, field)
            else:
                issue(pointer, "declared-seed-container-has-unrecognized-members")
        else:
            issue(pointer, "declared-seed-list-has-unsupported-value")
    def escape(key):
        return key.replace("~", "~0").replace("/", "~1")
    try:
        obj = _strict_json(blob)
        stack = [("", obj)]
        while stack:
            pointer, value = stack.pop()
            if type(value) is dict:
                for k, v in value.items():
                    p = pointer + "/" + escape(k)
                    if k in _SINGLE:
                        record(p, v, k)
                    elif k in _LISTS or k == "old_scientific":
                        collect(p, v, k)
                    elif k in _RANGE and pointer.endswith("/permanent_exclusions"):
                        try:
                            intervals.extend(merge_intervals(v))
                        except ready.ProtocolError:
                            issue(p, "unsupported-historical-range")
                    elif k in ("scientific", "engineering") and type(obj) is dict and \
                            str(obj.get("schema", "")).startswith(("rfl-a95-seed-registry",
                                                                 "rfl-a96-seed-registry")):
                        collect(p, v, k)
                    elif k in _SCHEDULE:
                        issue(p, "schedule-or-external-reference-not-resolved")
                    elif "seed" in k.casefold() and k not in _NONIDENTITY:
                        issue(p, "unknown-seed-related-field-not-resolved")
                    if type(v) in (dict, list):
                        stack.append((p, v))
            elif type(value) is list:
                stack.extend((pointer + "/" + str(i), v) for i, v in enumerate(value)
                             if type(v) in (dict, list))
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        # Never retain a valid-looking prefix from a malformed complete file.
        return {"parse_complete": False, "claims": [], "intervals_inclusive": [],
            "issues": [{"reason": "whole-json-refused:" + type(exc).__name__,
                        "occurrences": 1, "example_pointer": ""}]}
    return {"parse_complete": True,
        "claims": sorted(claims.values(), key=lambda r: (r["field"], r["original_integer"])),
        "intervals_inclusive": merge_intervals(intervals),
        "issues": sorted(issues.values(), key=lambda r: r["reason"])}


def _walk(root):
    paths, omitted, errors = [], [], []
    def error(exc):
        errors.append({"path": str(exc.filename), "reason": "walk-error:" + type(exc).__name__})
    for here, directories, files in os.walk(root, followlinks=False, onerror=error):
        keep = []
        for name in sorted(directories):
            p = Path(here) / name
            if name in _PRUNE or _reparse(p):
                omitted.append(p.relative_to(root).as_posix())
            else:
                keep.append(name)
        directories[:] = keep
        for name in sorted(files):
            p = Path(here) / name
            if _reparse(p):
                omitted.append(p.relative_to(root).as_posix())
            else:
                paths.append(p)
    return sorted(paths), sorted(omitted), errors


def _reparse(path):
    attrs = path.lstat()
    return path.is_symlink() or bool(getattr(attrs, "st_file_attributes", 0) &
                                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _scope_guard():
    plans._guard()
    ready.require(tuple(ready.file_hash(p) for p in _BINDING_PATHS) == _BINDING and
        _SCOPE == ready.read_json(_SCOPE_PATH), "history scanner/scope/dependency bytes drifted")
    ready.require(type(_SCOPE) is dict and set(_SCOPE) == {
        "schema", "role", "workspace", "root_names", "explicit_unscanned_scopes",
        "parent_sources_digest", "lock_sha256", "collection_authorized"} and
        _SCOPE["schema"] == "a96-bounded-history-scope-candidate-v15" and
        _SCOPE["role"] == "READ_ONLY_PARTIAL_EVIDENCE_NOT_COMPLETE_HISTORY_GATE" and
        _SCOPE["collection_authorized"] is False and
        _SCOPE["parent_sources_digest"] == plans._PARENT_IDENTITY[0] and
        _SCOPE["lock_sha256"] == plans._PARENT_IDENTITY[1],
        "closed history scope differs")
    base = Path(_SCOPE["workspace"])
    names = _SCOPE["root_names"]
    ready.require(base.is_absolute() and base.resolve() == ready.ROOT.parent and
        type(names) is list and len(names) == len(set(names)) and bool(names) and
        all(type(n) is str and n not in ("", ".", "..") and "/" not in n and
            "\\" not in n and ":" not in n for n in names),
        "scope requires unique direct retained roots only")
    return base, tuple(names)


def snapshot_retained_history():
    """Fixed-scope read-only snapshot. No arbitrary root/seed/output callbacks."""
    base, names = _scope_guard()
    roots, rows, union = [], [], []
    for name in names:
        root = base / name
        if not root.is_dir() or _reparse(root) or root.resolve().parent != base.resolve():
            roots.append({"root": name, "available": False, "stable": False,
                          "gap": "root-missing-or-reparse"})
            continue
        paths, omitted, errors = _walk(root)
        records, categories = [], Counter()
        stable = True
        for path in paths:
            rel = path.relative_to(root).as_posix()
            # Audit outputs are immutable after creation, but are not historical
            # input. Exclude current version's own files to avoid circular hashes.
            if root == ready.ROOT and (rel == "experiments/rebuild_status_current.json" or
                    rel.startswith(ready.FOLDER.as_posix() + "/b2_prepare/evidence_v15/") or
                    "history_" in path.name and path.parent == _FOLDER or
                    path.name == "internal_review_history_v15.json"):
                categories["current-v15-and-ledger-self-excluded"] += 1
                continue
            suffix = path.suffix.lower()
            if suffix not in _TEXT:
                categories["opaque-or-archive-unparsed:" + suffix] += 1
                continue
            if path.stat().st_size > _LIMIT:
                categories["over16MiB-unparsed:" + suffix] += 1
                records.append({"path": rel, "bytes": path.stat().st_size,
                    "sha256": None, "parse_complete": False, "gap": "over16MiB"})
                continue
            try:
                before = path.read_bytes()
                h = _digest(before)
                record = {"path": rel, "bytes": len(before), "sha256": h}
                if suffix == ".json":
                    record.update(inspect_json_bytes(before))
                    union.extend(record["intervals_inclusive"])
                    union.extend([c["canonical_modulo64_exclusion"]]*2 for c in record["claims"])
                    categories["json-parsed" if record["parse_complete"] else "json-refused"] += 1
                elif suffix == ".txt" and path.name in ("smoke_seeds.txt", "dev_seeds.txt"):
                    try:
                        txt = before.decode("utf-8-sig")
                        parts = txt.split()
                        ready.require(bool(parts) and all(re.fullmatch(r"[0-9]+", p) for p in parts),
                                      "literal complete decimal seed file required")
                        vals = [int(p) for p in parts]
                        record["literal_originals"] = vals
                        union.extend([v % (1 << 64)]*2 for v in vals)
                        record["parse_complete"] = True
                        categories["literal-seed-text-parsed"] += 1
                    except (ValueError, UnicodeError, ready.ProtocolError):
                        record.update(parse_complete=False, gap="seed-text-refused")
                        categories["seed-text-refused"] += 1
                else:
                    # Bind all source/text bytes, but do not execute code, eval
                    # schedules, parse outcome numbers or guess environment seeds.
                    record.update(parse_complete=False, gap="format-or-dynamic-schedule-not-resolved")
                    categories["other-text-bound-not-parsed:" + suffix] += 1
                if _digest(path.read_bytes()) != h:
                    stable = False
                    record["gap"] = "bytes-moved-during-read"
                records.append(record)
            except OSError as exc:
                stable = False
                records.append({"path": rel, "sha256": None, "parse_complete": False,
                                "gap": "read-error:" + type(exc).__name__})
        after_paths, after_omitted, after_errors = _walk(root)
        stable = stable and paths == after_paths and omitted == after_omitted and not errors and not after_errors
        # Recheck every bound file after the whole root pass, not just adjacent reads.
        for record in records:
            if record["sha256"] is not None:
                try:
                    if ready.file_hash(root / record["path"]) != record["sha256"]:
                        stable = False
                        record["gap"] = "bytes-moved-at-root-boundary"
                except OSError:
                    stable = False
                    record["gap"] = "bound-file-disappeared"
        roots.append({"root": name, "available": True, "stable": stable,
            "enumerated_file_count": len(paths), "bound_record_count": len(records),
            "categories": dict(sorted(categories.items())), "omitted_directories_or_reparse": omitted,
            "walk_errors": errors + after_errors})
        rows.append({"root": name, "records": records})
    _scope_guard()
    intervals = merge_intervals(union)
    known, analysis = plans._guard()
    payload = {"scope": deepcopy(_SCOPE), "roots": roots, "file_evidence": rows,
        "conservative_literal_exclusion_intervals_inclusive": intervals,
        "literal_exclusions_not_covered_by_original_registry_and_analysis_rng":
            subtract_intervals(intervals, list(known) + [[analysis, analysis]])}
    return {"schema": "a96-bounded-history-snapshot-candidate-v15",
        "role": "PARTIAL_BOUND_HISTORICAL_LITERALS_NOT_UNUSED_KEY_CERTIFICATE",
        "payload": payload, "payload_sha256": _digest(_canonical(payload)),
        "scope_file_sha256": ready.file_hash(_SCOPE_PATH),
        "all_available_roots_stable": all(r["available"] and r["stable"] for r in roots),
        "complete_historical_usage_freshness_audit": False,
        "seed_plan_v14_exclusions_automatically_extended": False,
        "keys_allocated_or_reserved": False, "environment_key_draws": 0,
        "native_protocol_or_training_started": False, "collection_authorized": False,
        "scientific_claim_authorized": False, "research_complete": False}


if __name__ == "__main__":
    print(_canonical(snapshot_retained_history()).decode("utf-8"))

