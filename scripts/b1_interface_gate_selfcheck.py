r"""Mutation self-check for the four B1 interface hardenings.

$$\boxed{\text{a gate that passes is not evidence; it is evidence only that the gate
did not look}}$$

The four interface holes closed before the $D_Q$ draft each have a gate. A gate that
was written *after* the fix and passes on the fixed code proves nothing on its own: it
would pass identically if the fix were cosmetic and the hole still open. So each gate is
re-run against a **deliberately reverted** source tree, one mutation at a time, and must
go **red**. A gate whose mutation leaves it green is reported as `NOT_A_GATE`.

The mutations are textual, must match exactly once, and are always reverted in a
``finally`` block; the script re-hashes every touched file at the end and reports
whether the tree is byte-identical to how it started.

| # | hole | mutation | gate that must catch it |
|---|---|---|---|
| 1 | undeclared tier inherited `False` | base sentinel `None` -> `False` | `test_8h` |
| 2 | tier coerced instead of typed | `type(tier) is not bool` -> `tier is None` | `test_8i` |
| 3 | law could re-acquire a store handle | signature check disabled | `test_8j` |
| 4 | envelope was a superset, not exact | `keys != credited` -> `credited - keys` | `test_17e` |
| 5 | `targets=None` crashed as `TypeError` | mapping guard disabled | `test_17f` |
| 6 | `factual_command` unchecked | action-id guard disabled | `test_17g` |
| 7 | unhashable credit unit crashed | type check moved after the duplicate guard | `test_16c` |
| 8 | the snapshot was still constructed | snapshot call restored in the runner | `test_8l` |

Usage::

    python scripts/b1_interface_gate_selfcheck.py [--json PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "rfl_rebuild"
TESTS = "tests/rebuild/test_b1_patch_slice.py"

LAWS = SRC / "b1" / "laws.py"
RUNNER = SRC / "b1" / "runner.py"
TARGETS = SRC / "b1" / "targets.py"
TIER = SRC / "b1" / "tier.py"

#: (id, hole, path, old, new, pytest node id)
MUTATIONS: tuple[tuple[str, str, pathlib.Path, str, str, str], ...] = (
    (
        "undeclared_tier",
        "the base tier sentinel falls back to False, so a subclass that forgets its "
        "tier silently becomes L0",
        LAWS,
        "    tier: Tier | None = None                      # None == NOT DECLARED",
        "    tier: Tier | None = Tier.L0_FACTUAL         # MUTATED to a default",
        f"{TESTS}::test_8h_a_real_subclass_that_forgets_its_tier_fails_stop",
    ),
    (
        "tier_coerced",
        "the tier is coerced with truthiness instead of being required to be a bool",
        RUNNER,
        "    if type(tier) is not Tier:",
        "    if tier is None:            # MUTATED: coercion, not typing",
        f"{TESTS}::test_8i_a_tier_that_is_not_a_real_bool_fails_stop",
    ),
    (
        "ill_typed_cell",
        "an ill-typed cell is declared as an empty field set, so a law in it is "
        "accepted as though the cell had a treatment",
        TIER,
        "        Tier.L2_COUNTERFACTUAL: ILL_TYPED,",
        "        Tier.L2_COUNTERFACTUAL: frozenset(),        # MUTATED to a legal cell",
        f"{TESTS}::test_8m_a_law_declared_in_an_ill_typed_cell_is_rejected",
    ),
    (
        "law_signature",
        "a law may declare plan(self, addresses, targets, snapshot) again",
        RUNNER,
        "    if params != _LAW_PLAN_PARAMS:",
        "    if False:                   # MUTATED: signature check disabled",
        f"{TESTS}::test_8j_a_law_cannot_re_acquire_a_store_handle",
    ),
    (
        "receipt_first_entry_only",
        "the receipt tests only the first entry of an address-plan, so a k>1 plan that "
        "changed the store reports EVALUABLE_NOOP and the ledger invariant kills the run",
        RUNNER,
        "        changed = any(\n"
        "            pre_view.get(e.address, _MISSING) != post_view.get(e.address, _MISSING)\n"
        "            for e in p.edits)",
        "        changed = (pre_view.get(p.edits[0].address) !=\n"
        "                   post_view.get(p.edits[0].address)) if p.edits else False",
        f"{TESTS}::test_8s_a_multi_entry_address_plan_reports_applied_from_any_entry",
    ),
    (
        "descriptor_extractor_unchecked",
        "a cell field with no extractor is accepted at construction and blows up as a "
        "KeyError inside delivery",
        TIER,
        "        if missing_extractors:",
        "        if False:                   # MUTATED: extractor check disabled",
        f"{TESTS}::test_8t_a_descriptor_missing_an_extractor_fails_at_construction",
    ),
    (
        "cells_left_mutable",
        "the cell table is left as a plain dict, so the frozen information contract can "
        "be edited in place at runtime",
        TIER,
        '        object.__setattr__(self, "cells", MappingProxyType(dict(self.cells)))',
        "        pass  # MUTATED: cells left mutable",
        f"{TESTS}::test_8u_the_cell_table_and_extractors_are_read_only",
    ),
    (
        "tier_truthiness",
        "Tier keeps a truth value, so `if tier:` silently collapses all four members "
        "into one branch",
        TIER,
        "    def __bool__(self) -> bool:                      # pragma: no cover - always raises\n"
        "        raise ProtocolError(",
        "    def __bool__(self) -> bool:                      # MUTATED\n"
        "        return True\n"
        "        raise ProtocolError(",
        f"{TESTS}::test_8v_tier_has_no_truth_value",
    ),
    (
        "envelope_superset",
        "the envelope is accepted as a superset of the credited set",
        TARGETS,
        "    if keys != credited:",
        "    if credited - keys:         # MUTATED: containment, not exactness",
        f"{TESTS}::test_17e_an_extra_non_credited_key_fails_stop",
    ),
    (
        "envelope_none",
        "a None / non-mapping envelope raises TypeError instead of PROTOCOL_ERROR",
        TARGETS,
        "    if not isinstance(targets, _Mapping):",
        "    if False:                   # MUTATED: mapping guard disabled",
        f"{TESTS}::test_17f_a_none_envelope_is_a_protocol_error_not_a_typeerror",
    ),
    (
        "factual_command",
        "a record may carry a factual command that is not an action id",
        TARGETS,
        "        if not _is_action(rec.factual_command):",
        "        if False:               # MUTATED: factual command unchecked",
        f"{TESTS}::test_17g_a_bogus_factual_command_fails_stop",
    ),
    (
        "credit_unit_order",
        "the duplicate guard hashes an untyped credit unit, so an unhashable one "
        "crashes with TypeError",
        TARGETS,
        "        u = _require_unit(u)\n        if u in seen_units:",
        "        if u in seen_units:     # MUTATED: type check moved after the guard",
        f"{TESTS}::test_16c_a_non_string_credit_unit_is_a_protocol_error_not_a_crash",
    ),
    (
        "snapshot_constructed",
        "the runner still builds the full learner snapshot during a law run",
        RUNNER,
        "    pre_view = spec.view(pre_state)\n    fp_pre = fingerprint(pre_state)",
        "    snapshot = pre_state.snapshot()     # MUTATED\n"
        "    pre_view = spec.view(pre_state)\n    fp_pre = fingerprint(pre_state)",
        f"{TESTS}::test_8l_the_snapshot_is_not_even_constructed_for_a_law_run",
    ),
)


def _digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_node(node: str) -> tuple[int, str]:
    """Run one gate with **bytecode writing disabled**.

    Not a style choice. The mutated and the original file can land in the same mtime
    second, and CPython validates a cached ``.pyc`` on ``(mtime, size)``; a stale cache
    then runs the *previous* mutation's code. That is exactly what happened: on 4 of 5
    runs `law_signature` came back ``NOT_A_GATE``, because the run replayed mutation 2 —
    which disables the tier check but leaves the signature check in place, so the gate
    correctly passed for code that was never written in that iteration. Six isolated
    repetitions of the same mutation were red 6/6, which is what located the harness
    rather than the gate.
    """
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", node, "-q", "-p", "no:cacheprovider",
         "--no-header", "-x"],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    lines = [ln for ln in (proc.stdout + proc.stderr).strip().splitlines() if ln.strip()]
    return proc.returncode, (lines[-1] if lines else "")


#: pytest exits these when it never collected the requested node (4 = usage error,
#: 5 = no tests collected). Counting them as "the gate went red" is how a typo earns a
#: pass, so they get their own verdict AND a pre-flight check.
_NODE_NOT_FOUND_CODES = (4, 5)


def check_nodes(mutations) -> list:
    """Every mutation's gate must name a test that still exists in its file.

    Found the hard way: renaming a gate left this table pointing at the old name, and
    because pytest exits non-zero for "not found" the stale entry was reported
    ``GATE_IS_REAL`` -- a dead gate wearing a pass. The exit-code table catches it at
    runtime; this catches it before anything runs.
    """
    stale = []
    for key, _hole, _path, _old, _new, node in mutations:
        path, _, test = node.partition("::")
        try:
            src = (ROOT / path).read_text(encoding="utf-8")
        except OSError:
            stale.append((key, node, "test file missing"))
            continue
        if f"def {test}(" not in src:
            stale.append((key, node, "no such test function"))
    return stale


def _read(path: pathlib.Path) -> str:
    """Read with **no newline translation**, so a round trip is byte-faithful.

    ``Path.read_text`` uses universal newlines and ``Path.write_text`` translates
    ``\\n`` back to ``os.linesep``. On Windows that quietly converted the three sources
    from LF to CRLF during the first run of this script — and the digest guard below
    is what caught it, which is the only reason it is not in the commit.
    """
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _write(path: pathlib.Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "b1_interface_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = check_nodes(MUTATIONS)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID     ] {key:22} -> {node} ({why})")

    before = {p: _digest(p) for p in (LAWS, RUNNER, TARGETS, TIER)}
    results = []
    for key, hole, path, old, new, node in MUTATIONS:
        original = _read(path)
        count = original.count(old)
        entry = {"mutation": key, "hole": hole, "gate": node.split("::")[-1],
                 "site": f"{path.relative_to(ROOT)}", "matched": count}
        if count != 1:
            entry.update(verdict="MUTATION_NOT_APPLIED",
                         detail=f"the anchor matched {count} times, expected exactly 1")
            results.append(entry)
            continue
        try:
            _write(path, original.replace(old, new))
            code, tail = _run_node(node)
        finally:
            _write(path, original)
        if code in _NODE_NOT_FOUND_CODES:
            verdict = "NODE_NOT_FOUND"
        elif code != 0:
            verdict = "GATE_IS_REAL"
        else:
            verdict = "NOT_A_GATE"
        entry.update(exit_code=code, tail=tail, verdict=verdict)
        results.append(entry)
        print(f"[{entry['verdict']:18}] {key:22} -> {entry['gate']}")

    after = {p: _digest(p) for p in (LAWS, RUNNER, TARGETS, TIER)}
    restored = before == after
    real = sum(1 for r in results if r["verdict"] == "GATE_IS_REAL")
    payload = {
        "check": "b1 interface gate mutation self-check",
        "n_mutations": len(MUTATIONS),
        "n_gate_is_real": real,
        "n_not_a_gate": sum(1 for r in results if r["verdict"] == "NOT_A_GATE"),
        "n_node_not_found": sum(1 for r in results if r["verdict"] == "NODE_NOT_FOUND"),
        "stale_node_ids": [list(s) for s in stale],
        "tree_restored_byte_identical": restored,
        "file_digests": {str(p.relative_to(ROOT)): d for p, d in after.items()},
        "results": results,
    }
    out = pathlib.Path(args.json)
    if not out.is_absolute():
        # A relative --json used to crash at the final print instead of writing.
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\n  mutations            : {len(MUTATIONS)}")
    print(f"  gates that went red  : {real}/{len(MUTATIONS)}")
    print(f"  tree restored        : {restored}")
    print(f"  written              : {out.relative_to(ROOT)}")
    ok = restored and real == len(MUTATIONS) and not stale
    print("  SELF-CHECK " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
