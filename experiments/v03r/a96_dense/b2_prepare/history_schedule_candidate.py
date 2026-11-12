"""Bounded static declarations/references, not execution or freshness evidence.

Historical Python is parsed, never imported/evaluated/executed. A declared
range, config envelope or CLI-default possibility is conservatively excluded,
but is NOT an observed run. Unknown overrides/flows/archives remain gaps.
"""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

import history_seed_audit_candidate as history
import readiness as ready

_FOLDER = Path(__file__).resolve().parent
_SNAPSHOT = _FOLDER / "evidence_v15/retained_snapshot_final.stdout.log"
_SNAPSHOT_SHA = "0d396ef4dd175a22e2084ac483a9a1f0c8241eb1d4d521e43d928e327bfc364c"
_PAYLOAD_SHA = "a1c355d63abd10f2ec397f6010b9e509fd17e6790eec43faac6024b1a2b57306"
_MAX_ITEMS = 8192
_M = 1 << 64
_BINDINGS = (Path(__file__), Path(history.__file__), Path(ready.__file__), _SNAPSHOT)
_BOUND = tuple(ready.file_hash(p) for p in _BINDINGS)
_SINGLES = history._SINGLE | {"base_seed", "seed_base", "seed_offset",
    "pilot_seed_base", "confirmatory_seed_base", "calibration_seed_offset"}
_LISTS = history._LISTS | {"KEYS", "STAGE_SEEDS", "SEEDS"}
_REFS = {"seed_file", "seeds_file", "seed_files"}


class Unresolved(ValueError):
    pass


def _int(value):
    if type(value) is not int or value.bit_length() > 256:
        raise Unresolved("bounded-native-integer-required")
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _expr(node, names=None, depth=0):
    """Closed AST arithmetic only; no eval/compile/import or user call dispatch."""
    if depth > 32:
        raise Unresolved("expression-depth-limit")
    names = {} if names is None else names
    sub = lambda n, ns=names: _expr(n, ns, depth + 1)
    if isinstance(node, ast.Constant):
        return _int(node.value)
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _int(sub(node.operand))
        return _int(v if isinstance(node.op, ast.UAdd) else -v)
    if isinstance(node, ast.BinOp):
        a, b = _int(sub(node.left)), _int(sub(node.right))
        if isinstance(node.op, ast.Add):
            return _int(a + b)
        if isinstance(node.op, ast.Sub):
            return _int(a - b)
        if isinstance(node.op, ast.Mult):
            return _int(a * b)
        if isinstance(node.op, ast.LShift) and 0 <= b <= 256:
            return _int(a << b)
        if isinstance(node.op, ast.Pow) and 0 <= b <= 256 and a.bit_length() * b <= 256:
            return _int(a ** b)
        raise Unresolved("unsupported-arithmetic")
    if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) <= _MAX_ITEMS:
        return [sub(n) for n in node.elts]
    if isinstance(node, ast.Dict) and len(node.keys) <= _MAX_ITEMS:
        result = {}
        for k, v in zip(node.keys, node.values):
            if not isinstance(k, ast.Constant) or type(k.value) is not str or k.value in result:
                raise Unresolved("literal-unique-dict-key-required")
            result[k.value] = sub(v)
        return result
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        name = node.func.id
        args = [sub(n) for n in node.args]
        if name == "range" and 1 <= len(args) <= 3 and all(type(v) is int for v in args):
            try:
                vals = range(*args)
                if len(vals) > _MAX_ITEMS:
                    raise Unresolved("sequence-size-limit")
                return list(vals)
            except (ValueError, OverflowError) as exc:
                raise Unresolved("invalid-or-overwide-range") from exc
        if name in ("list", "tuple") and len(args) == 1 and type(args[0]) is list:
            return args[0]
        if name == "int" and len(args) == 1 and type(args[0]) is int:
            return args[0]
    if isinstance(node, (ast.ListComp, ast.GeneratorExp)) and len(node.generators) == 1:
        gen = node.generators[0]
        if isinstance(gen.target, ast.Name) and not gen.ifs and not gen.is_async:
            vals = sub(gen.iter)
            if type(vals) is list and len(vals) <= _MAX_ITEMS:
                return [sub(node.elt, dict(names, **{gen.target.id: v})) for v in vals]
    raise Unresolved("dynamic-or-unsupported-expression")


def _alias_intervals(start, count):
    _int(start)
    _int(count)
    if count < 0:
        raise Unresolved("negative-count")
    if count == 0:
        return []
    if count >= _M:
        return [[0, _M - 1]]
    first = start % _M
    last = first + count - 1
    return [[first, last]] if last < _M else [[0, last % _M], [first, _M - 1]]


def _flatten(value):
    if type(value) is int:
        return [value]
    if type(value) is list:
        result = []
        for v in value:
            result.extend(_flatten(v))
        if len(result) > _MAX_ITEMS:
            raise Unresolved("sequence-size-limit")
        return result
    if type(value) is dict and set(value) <= history._STAGES:
        return _flatten(list(value.values()))
    raise Unresolved("unsupported-seed-container")


def inspect_python_bytes(blob):
    """Static possibilities only, including explicitly conditional CLI defaults.

Name substitution is restricted to unique literal module constants. Function
arguments/local bindings mask them. Loop context is lexical; defaults never
become runtime observations and every default substitution retains an override
gap. Complete syntax errors discard the entire file's claims.
"""
    ready.require(type(blob) is bytes, "native bytes required")
    try:
        tree = ast.parse(blob)
    except (SyntaxError, ValueError, UnicodeError, RecursionError) as exc:
        return {"syntax_complete": False, "claims": [], "intervals_inclusive": [],
                "issues": [{"line": 0, "reason": "whole-python-refused:" + type(exc).__name__}]}
    claims, issues, intervals = [], [], []
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    def ancestors(node):
        while node in parents:
            node = parents[node]
            yield node
    counts, constants = Counter(), {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    counts[target.id] += 1
                    try:
                        constants[target.id] = _expr(node.value)
                    except Unresolved:
                        pass
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
            counts[node.target.id] += 1
    constants = {k: v for k, v in constants.items() if counts[k] == 1}
    def context(node):
        names = dict(constants)
        enclosing = list(ancestors(node))
        func = next((p for p in enclosing if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
        defaults = {}
        if func:
            for n in ast.walk(func):
                if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                    names.pop(n.id, None)
                if isinstance(n, ast.arg):
                    names.pop(n.arg, None)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument":
                    if any(isinstance(a, ast.Constant) and a.value == "--seeds" for a in n.args):
                        v = next((k.value for k in n.keywords if k.arg == "default"), None)
                        try:
                            val = _expr(v)
                            defaults.setdefault("seeds", []).append(val)
                        except Unresolved:
                            pass
        conditional = []
        for p in reversed(enclosing):
            if not isinstance(p, ast.For) or not isinstance(p.target, ast.Name):
                continue
            # Only the loop body, not its iterator or else block, binds a value.
            if not any(node is b or b in enclosing for b in p.body):
                continue
            iterator = p.iter
            try:
                vals = _expr(iterator, names)
            except Unresolved:
                vals = None
                if isinstance(iterator, ast.Call) and isinstance(iterator.func, ast.Name) and iterator.func.id == "range" and len(iterator.args) == 1 and not iterator.keywords:
                    arg = iterator.args[0]
                    if isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == "args" and arg.attr == "seeds" and len(defaults.get("seeds", [])) == 1:
                        count = defaults["seeds"][0]
                        if type(count) is int and 0 <= count <= _MAX_ITEMS:
                            vals = list(range(count))
                            conditional.append({"line": p.lineno, "count": count,
                                "reason": "CLI-default-possibility-only-overrides-unresolved"})
            if type(vals) is list and len(vals) <= _MAX_ITEMS:
                names[p.target.id] = vals
        return names, conditional
    def record(node, field, value_node, plural):
        names, conditional = context(node)
        vector_names = {k: v for k, v in names.items() if type(v) is list}
        scalar_names = {k: v for k, v in names.items() if type(v) is not list}
        try:
            used = {n.id for n in ast.walk(value_node) if isinstance(n, ast.Name)} & set(vector_names)
            if len(used) > 1:
                raise Unresolved("multiple-loop-binders-unresolved")
            if used:
                key = next(iter(used))
                vals = [_expr(value_node, dict(scalar_names, **{key: v})) for v in vector_names[key]]
            else:
                vals = _expr(value_node, scalar_names)
            if plural and type(vals) is int:
                raise Unresolved("plural-scalar-may-be-count-not-identity")
            vals = _flatten(vals)
            aliases = history.merge_intervals([[v % _M, v % _M] for v in vals])
            intervals.extend(aliases)
            claims.append({"line": node.lineno, "field": field,
                "role": "STATIC_DECLARATION_NOT_OBSERVED_EXECUTION",
                "expression": ast.get_source_segment(blob.decode("utf-8-sig"), value_node),
                "original_integers": vals, "canonical_modulo64_intervals": aliases,
                "CLI_default_conditions": conditional})
            issues.extend(conditional)
        except (Unresolved, UnicodeError) as exc:
            issues.append({"line": node.lineno, "field": field, "reason": str(exc)})
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in _SINGLES | _LISTS:
                    record(node, target.id, node.value, target.id in _LISTS)
        if isinstance(node, ast.keyword) and node.arg in _SINGLES | _LISTS:
            record(node, node.arg, node.value, node.arg in _LISTS)
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and type(k.value) is str and k.value in _SINGLES | _LISTS:
                    record(k, k.value, v, k.value in _LISTS)
    return {"syntax_complete": True, "claims": claims,
            "intervals_inclusive": history.merge_intervals(intervals), "issues": issues,
            "all_runtime_flows_resolved": False}


def inspect_json_schedules(blob):
    """Declared adjacent base/count envelopes only, not verified generator laws."""
    ready.require(type(blob) is bytes, "native bytes required")
    try:
        obj = history._strict_json(blob)
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        return {"parse_complete": False, "claims": [], "references": [],
                "intervals_inclusive": [], "issues": [{"reason": "whole-json-refused:" + type(exc).__name__}]}
    claims, refs, issues, intervals = [], [], [], []
    def walk(value, pointer):
        if type(value) is list:
            for i, v in enumerate(value):
                if type(v) in (dict, list):
                    walk(v, pointer + "/" + str(i))
        elif type(value) is dict:
            for key, val in value.items():
                p = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
                if key in {"seed_base", "pilot_seed_base", "confirmatory_seed_base"}:
                    try:
                        base, count = _int(val), _int(value.get("seeds"))
                        aliases = _alias_intervals(base, count)
                        intervals.extend(aliases)
                        claims.append({"pointer": p, "base_original": base, "count": count,
                            "canonical_modulo64_intervals": aliases,
                            "role": "DECLARED_BASE_COUNT_CONSERVATIVE_ENVELOPE_NOT_VERIFIED_GENERATOR_LAW"})
                    except Unresolved as exc:
                        issues.append({"pointer": p, "reason": str(exc)})
                if key in _REFS:
                    refs.append({"pointer": p, "field": key, "declaration": val})
                if type(val) in (dict, list):
                    walk(val, p)
    walk(obj, "")
    return {"parse_complete": True, "claims": claims, "references": refs,
            "intervals_inclusive": history.merge_intervals(intervals), "issues": issues}


def inspect_yaml_experiment(blob):
    """Narrow flat experiment block; no YAML constructors, anchors or includes.

Reject unsupported syntax in that block, duplicate experiment/field, aliases,
tags and tabs. Other sections remain unparsed; no whole-YAML validity claim.
"""
    ready.require(type(blob) is bytes, "native bytes required")
    try:
        text = blob.decode("utf-8-sig")
        lines = text.splitlines()
        starts = [i for i, l in enumerate(lines) if re.fullmatch(r"experiment:\s*(?:#.*)?", l)]
        if len(starts) != 1:
            raise Unresolved("unique-flat-experiment-block-required")
        values, pointers = {}, {}
        for i in range(starts[0] + 1, len(lines)):
            line = lines[i]
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if not line.startswith(" "):
                break
            if "\t" in line or re.search(r"[&*!]|<<:", line):
                raise Unresolved("YAML-alias-tag-tab-merge-unresolved")
            m = re.fullmatch(r"  ([A-Za-z_][A-Za-z_0-9]*):\s*(.*?)\s*(?:#.*)?", line)
            if not m or m[1] in values:
                raise Unresolved("nested-or-duplicate-experiment-field")
            values[m[1]] = m[2].split(" #", 1)[0].strip()
            pointers[m[1]] = i + 1
        key = next((k for k in ("seed_base", "pilot_seed_base", "confirmatory_seed_base") if k in values), None)
        if key is None or "seeds" not in values:
            raise Unresolved("declared-base-count-pair-missing")
        if not re.fullmatch(r"-?[0-9]+", values[key]) or not re.fullmatch(r"[0-9]+", values["seeds"]):
            raise Unresolved("literal-decimal-base-count-required")
        base, count = _int(int(values[key])), _int(int(values["seeds"]))
        aliases = _alias_intervals(base, count)
        return {"experiment_block_parsed": True, "claims": [{"base_line": pointers[key],
            "count_line": pointers["seeds"], "base_original": base, "count": count,
            "name_literal": values.get("name"), "canonical_modulo64_intervals": aliases,
            "role": "DECLARED_BASE_COUNT_CONSERVATIVE_ENVELOPE_NOT_VERIFIED_GENERATOR_LAW"}],
            "intervals_inclusive": aliases, "issues": [], "whole_yaml_validated": False}
    except (UnicodeError, Unresolved, ValueError) as exc:
        return {"experiment_block_parsed": False, "claims": [], "intervals_inclusive": [],
                "issues": [{"reason": str(exc)}], "whole_yaml_validated": False}


def inspect_seed_text(blob):
    ready.require(type(blob) is bytes, "native bytes required")
    try:
        lines = [l.split("#", 1)[0].strip() for l in blob.decode("utf-8-sig").splitlines()]
        vals = [int(l) for l in lines if l]
        if not vals or any(not re.fullmatch(r"-?[0-9]+", l) for l in lines if l):
            raise Unresolved("complete-literal-seed-text-required")
        for v in vals:
            _int(v)
        return {"parse_complete": True, "original_integers": vals,
            "intervals_inclusive": history.merge_intervals([[v % _M, v % _M] for v in vals])}
    except (UnicodeError, ValueError, Unresolved) as exc:
        return {"parse_complete": False, "original_integers": [], "intervals_inclusive": [], "reason": str(exc)}


def _reference_leaves(value, pointer):
    if type(value) is str:
        return [(pointer, value, None)]
    if type(value) is dict:
        if type(value.get("path")) is str:
            return [(pointer, value["path"], value.get("sha256"))]
        if set(value) <= history._STAGES:
            return [r for k, v in value.items() for r in _reference_leaves(v, pointer + "/" + k)]
    return [(pointer, None, None)]


def reference_path(value):
    """Only a POSIX relative root-local TXT path present in the old byte index."""
    if type(value) is not str or "\\" in value or ":" in value:
        raise Unresolved("external-or-noncanonical-reference")
    p = PurePosixPath(value)
    if p.is_absolute() or p.as_posix() != value or any(v in (".", "..", "") for v in value.split("/")) or p.suffix != ".txt":
        raise Unresolved("outside-closed-reference-path-law")
    return value


def snapshot_static_schedules():
    """Re-read only v15-indexed inputs. No new root/config/seed/output arguments."""
    history._scope_guard()
    ready.require(tuple(ready.file_hash(p) for p in _BINDINGS) == _BOUND and
        ready.file_hash(_SNAPSHOT) == _SNAPSHOT_SHA, "v16 component or v15 input bytes drifted")
    snap = history._strict_json(_SNAPSHOT.read_bytes())
    ready.require(snap["payload_sha256"] == _PAYLOAD_SHA and
        _sha(history._canonical(snap["payload"])) == _PAYLOAD_SHA and
        snap["all_available_roots_stable"] is True, "bound prior snapshot differs")
    base, names = history._scope_guard()
    evidence, intervals, gaps = [], [], Counter()
    selected = []
    for block in snap["payload"]["file_evidence"]:
        ready.require(block["root"] in names, "unknown retained root")
        root = base / block["root"]
        ready.require(root.is_dir() and not history._reparse(root) and root.resolve().parent == base.resolve(), "root missing/reparse")
        indexed = {r["path"]: r for r in block["records"]}
        for row in block["records"]:
            rel = PurePosixPath(row["path"])
            ready.require(not rel.is_absolute() and ".." not in rel.parts, "unsafe historical index path")
            if row.get("sha256") is None:
                gaps["prior-unhashed-overlimit"] += 1
                continue
            suffix = rel.suffix.lower()
            if suffix not in (".py", ".json", ".yaml", ".yml"):
                gaps["not-semantic-v16:" + suffix] += 1
                continue
            path = root / rel
            ready.require(not any(history._reparse(p) for p in (path, *path.parents) if p != base.parent) and
                path.resolve().is_relative_to(root.resolve()), "indexed file path reparse/outside root")
            blob = path.read_bytes()
            ready.require(_sha(blob) == row["sha256"], "v15-indexed source bytes drifted")
            selected.append((path, row["sha256"]))
            if suffix == ".py":
                result = inspect_python_bytes(blob)
            elif suffix == ".json":
                result = inspect_json_schedules(blob)
            else:
                result = inspect_yaml_experiment(blob)
            intervals.extend(result["intervals_inclusive"])
            if result["claims"] or result.get("references") or result["issues"]:
                record = {"root": block["root"], "path": row["path"], "bytes": len(blob),
                          "sha256": row["sha256"], "inspection": result}
                links = []
                for ref in result.get("references", []):
                    for pointer, declared, expected in _reference_leaves(ref["declaration"], ref["pointer"]):
                        link = {"pointer": pointer, "declared_path": declared, "declared_sha256": expected}
                        try:
                            target = reference_path(declared)
                            bound = indexed.get(target)
                            if bound is None or bound.get("sha256") is None:
                                raise Unresolved("reference-not-byte-bound-in-prior-index")
                            if expected is not None and expected != bound["sha256"]:
                                raise Unresolved("declared-reference-byteSHA-mismatch")
                            p = root / target
                            if any(history._reparse(q) for q in (p, *p.parents) if q != base.parent) or not p.resolve().is_relative_to(root.resolve()):
                                raise Unresolved("reference-reparse-or-outside-root")
                            data = p.read_bytes()
                            ready.require(_sha(data) == bound["sha256"], "reference bytes drifted")
                            parsed = inspect_seed_text(data)
                            link.update(actual_byte_sha256=bound["sha256"], bytes=len(data), inspection=parsed)
                            intervals.extend(parsed["intervals_inclusive"])
                            selected.append((p, bound["sha256"]))
                        except Unresolved as exc:
                            link["gap"] = str(exc)
                        links.append(link)
                if links:
                    record["reference_resolution"] = links
                evidence.append(record)
    for path, expected in selected:
        ready.require(ready.file_hash(path) == expected, "selected historical bytes moved at final boundary")
    history._scope_guard()
    ready.require(tuple(ready.file_hash(p) for p in _BINDINGS) == _BOUND, "v16 bound component moved")
    merged = history.merge_intervals(intervals)
    prior = snap["payload"]["conservative_literal_exclusion_intervals_inclusive"]
    payload = {"v15_snapshot_file_sha256": _SNAPSHOT_SHA, "v15_payload_sha256": _PAYLOAD_SHA,
        "selected_byte_bound_files": len({str(p) for p, _ in selected}), "evidence": evidence,
        "static_possibility_exclusion_intervals": merged,
        "static_possibilities_not_in_v15_literal_union": history.subtract_intervals(merged, prior),
        "gaps_by_unparsed_format": dict(sorted(gaps.items())),
        "scope_limitations": ["v15 selection only; no new files/root inventory coverage", "Python dynamic calls, overrides, imports, side effects and nonconstant flows unresolved", "config envelopes are conservative possibilities, not source/run association or generator-law verification", "YAML only flat experiment block; other fields/offset descendants unresolved", "PowerShell/log/JSONL/large/archive/Git/wider histories still unresolved", "prior nominal fixture labels remain not allocated; no implicit promotion"]}
    return {"schema": "a96-static-history-schedules-candidate-v16", "payload": payload,
        "payload_sha256": _sha(_canonical(payload)), "selected_input_bytes_stable": True,
        "complete_historical_usage_freshness_audit": False,
        "registry_or_seed_plan_exclusions_automatically_extended": False,
        "keys_allocated_or_reserved": False, "environment_key_draws": 0,
        "historical_programs_executed": False, "native_protocol_or_training_started": False,
        "collection_authorized": False, "scientific_claim_authorized": False, "research_complete": False}


if __name__ == "__main__":
    print(_canonical(snapshot_static_schedules()).decode("ascii"))
