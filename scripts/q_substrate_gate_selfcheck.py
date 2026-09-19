r"""Mutation self-check for the $Q$ substrate gates (A77 §65.4/§65.5).

$$\boxed{\text{a gate that passes is not evidence; it is evidence only that the gate
did not look}}$$

Step 3's gates were written *with* the implementation, which means they have not yet
been shown to fail on anything. Each one is therefore re-run against a deliberately
reverted source tree, one textual mutation at a time, and must go **red**; a gate whose
mutation leaves it green is reported as `NOT_A_GATE`.

The mutations are textual, must match exactly once, and are always reverted in a
``finally`` block; the script re-hashes every touched file at the end and reports whether
the tree is byte-identical to how it started.

| # | hole | mutation | gate that must catch it |
|---|---|---|---|
| 1 | a reference-valued write persists | canonicalisation disabled | `test_3` |
| 2 | an entry outside the reference domain persists | domain check disabled | `test_11` |
| 3 | a bool / NaN / infinity is storable | value-domain check disabled | `test_2` |
| 4 | $P_D^L$ and $Q_D^L$ serve one read path | co-residence check disabled | `test_13` |
| 5 | an incomplete reference is accepted | row-totality check disabled | `test_12` |
| 6 | the reference can be edited at runtime | rows left as a plain dict | `test_12d` |
| 7 | ties break to the highest action id | strict `>` weakened to `>=` | `test_6` |
| 8 | an absent entry reads as the value zero | reference fallback replaced by `0.0` | `test_4` |
| 9 | a Q edit needs no reference at all | missing-reference check disabled | `test_11b` |

Usage::

    python scripts/q_substrate_gate_selfcheck.py [--json PATH]
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
SRC = ROOT / "src" / "rfl_rebuild" / "learner"
TESTS = "tests/rebuild/test_q_substrate.py"

STORE = SRC / "store.py"
REFERENCE = SRC / "reference.py"

MUTATIONS: tuple[tuple[str, str, pathlib.Path, str, str, str], ...] = (
    (
        "q_identity_canonicalisation",
        "writing the reference value stores an entry instead of deleting it, so the "
        "store stops being canonical and a zero-delta changed entry becomes possible",
        STORE,
        "                if e.value is None or float(e.value) == q_reference.value(e.address):",
        "                if e.value is None:            # MUTATED: canonicalisation off",
        f"{TESTS}::test_3_writing_the_reference_value_canonicalises_to_deletion",
    ),
    (
        "q_domain_closure",
        "an entry outside the reference domain is stored: the fingerprint changes, "
        "healthy goes False, and the read path never consults it",
        STORE,
        "        if e.address not in q_reference:",
        "        if False:                   # MUTATED: domain closure off",
        f"{TESTS}::test_11_an_entry_outside_the_reference_domain_is_rejected_at_the_boundary",
    ),
    (
        "q_value_domain",
        "bool, NaN and infinities are storable, so the fingerprint carries a type the "
        "value domain does not have and comparison semantics decide the canary",
        STORE,
        "        if e.value is not None and not _is_finite_real(e.value):",
        "        if False:                   # MUTATED: value domain unchecked",
        f"{TESTS}::test_2_a_q_value_must_be_a_finite_real",
    ),
    (
        "q_coresidence",
        "a state holding both decision stores is served anyway, silently, through a "
        "read path A77 defines no priority for",
        STORE,
        "        if self._decision and self._q:",
        "        if False:                   # MUTATED: co-residence accepted",
        f"{TESTS}::test_13_p_patch_and_q_coresidence_fails_before_adapter_creation",
    ),
    (
        "reference_row_totality",
        "a partial reference row is accepted, so a legal entry has no reference value "
        "and the read path meets a KeyError instead of a contract error",
        REFERENCE,
        "            if keys != allowed:",
        "            if False:               # MUTATED: totality unchecked",
        f"{TESTS}::test_12_a_row_that_is_not_total_on_a_z_is_rejected",
    ),
    (
        "reference_read_only",
        "the reference rows stay plain dicts, so the frozen reference can be edited "
        "after it has been handed to a store",
        REFERENCE,
        '        object.__setattr__(self, "rows", MappingProxyType(frozen))',
        '        object.__setattr__(self, "rows", frozen)   # MUTATED: left writable',
        f"{TESTS}::test_12d_the_reference_views_are_read_only",
    ),
    (
        "q_tie_break",
        "ties resolve to the highest action id, which silently disagrees with dp.py's "
        "frozen tie-break",
        STORE,
        "                if best_v is None or v > best_v:",
        "                if best_v is None or v >= best_v:   # MUTATED: last wins",
        f"{TESTS}::test_6_ties_still_break_to_the_lowest_action_id",
    ),
    (
        "q_absent_is_zero",
        "an absent entry reads as 0.0 instead of the reference value, so a sparse store "
        "is treated as a table of zeros",
        STORE,
        "                v = overrides.get(QAddress(state=state, z=control.z, m=control.m, a=a),\n"
        "                                  row[a])",
        "                v = overrides.get(QAddress(state=state, z=control.z, m=control.m, a=a),\n"
        "                                  0.0)      # MUTATED: absent treated as zero",
        f"{TESTS}::test_4_the_empty_store_reproduces_the_reference_policy_on_every_context",
    ),
    (
        "reference_domain_totality",
        "a reference is accepted when it covers only the contexts the caller happened to "
        "supply, so a view missing 13,823 of them -- or carrying an invented one -- is "
        "legal as long as each row it does carry is internally total",
        REFERENCE,
        "        if set(rows) != expected:",
        "        if False:               # MUTATED: domain totality off",
        f"{TESTS}::test_12e_a_reference_missing_a_whole_legal_context_is_rejected",
    ),
    (
        "reference_type_boundary",
        "a duck-typed mutable stand-in is accepted wherever a QReferenceView is required, "
        "so the totality/finiteness/read-only guarantees become properties of a helper "
        "class rather than of the substrate",
        STORE,
        "    if type(reference) is not QReferenceView:",
        "    if False:                       # MUTATED: duck typing accepted",
        f"{TESTS}::test_18_a_duck_typed_fake_reference_is_refused_at_both_boundaries",
    ),
    (
        "reference_strict_key_typing",
        "the reference accepts a context key whose type only resembles a legal one, so a "
        "value-preserving substitution (z -> True, z -> 1.0, x -> float(x)) passes the "
        "domain equality because Python folds those types",
        REFERENCE,
        "            if not is_decision_context(state, z, m):",
        "            if False:               # MUTATED: strict context typing off",
        f"{TESTS}::test_12i_value_preserving_type_substitutions_are_rejected",
    ),
    (
        "reference_strict_action_typing",
        "a reference row keyed by a float action id is accepted, and the read path then "
        "hands the kernel an action id that is not an int",
        REFERENCE,
        "                if not is_true_int(a):",
        "                if False:           # MUTATED: action-key typing off",
        f"{TESTS}::test_12j_a_float_action_key_is_rejected",
    ),
    (
        "qaddress_state_field_typing",
        "a QAddress whose State carries a float or bool field is accepted, folds onto a "
        "legal reference row through dict equality, and PERSISTS",
        STORE,
        # The whole strict block goes back to the old shape. Mutating only the
        # `non_integer_state_fields` line was NOT semantic: `is_decision_context` is
        # itself type-strict now, so it kept refusing the malformed State and the gate
        # could only fail on a changed error message -- evidence that the error path
        # moved, not that the hole reopened. A mutation has to restore the vulnerability
        # it names.
        "    bad = non_integer_state_fields(addr.state)\n"
        "    if bad:\n"
        "        raise StoreTransactionError(\n"
        "            f\"QAddress.state has non-integer field(s) {bad}: {addr.state!r}. Python \"\n"
        "            \"folds 1.0, True and 1 into one dict key, so this address would match a \"\n"
        "            \"legal reference row while not being one\")\n"
        "    if not is_decision_context(addr.state, addr.z, addr.m):\n"
        "        raise StoreTransactionError(\n"
        "            f\"QAddress {addr!r} is not a legal decision context: z and m must be true \"\n"
        "            \"integers inside their domains and (x, y, t, kappa, phi) a legal state\")",
        "    if not isinstance(addr.state, State):   # MUTATED: the old lax check\n"
        "        raise StoreTransactionError(\n"
        "            f\"QAddress.state must be a State, got {addr.state!r}\")",
        f"{TESTS}::test_1b_a_state_with_non_integer_fields_cannot_key_the_q_store",
        "DID NOT RAISE",
    ),
    (
        "q_requires_reference",
        "a Q edit is accepted with no injected reference, so the substrate would have "
        "to reach for one itself",
        STORE,
        "    if q_reference is None:",
        "    if False:                       # MUTATED: reference not required",
        f"{TESTS}::test_11b_a_q_edit_requires_the_injected_reference",
    ),
)


def _digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: pathlib.Path) -> str:
    """Read with no newline translation, so a round trip is byte-faithful."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _write(path: pathlib.Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _run_node(node: str) -> tuple[int, str]:
    """Run one gate with bytecode writing disabled.

    Two harness defects are guarded here, both found by *running* this script rather
    than by reading it:

    * **bytecode writing** is disabled (``-B`` + ``PYTHONDONTWRITEBYTECODE``) because the
      mutated and the original file can land in the same mtime second, and CPython
      validates a cached ``.pyc`` on ``(mtime, size)`` -- which once replayed the previous
      mutation and produced a false ``NOT_A_GATE``;
    * **pytest exits 4 and 5 when the node did not run at all**, which is not the same
      thing as failing. A stale node id was therefore indistinguishable from a dead gate,
      and an earlier revision of this script reported ``GATE_IS_REAL`` for a test that had
      been renamed away. Same disease as a check that cannot look, so it gets its own
      verdict.
    """
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", node, "-q", "-p", "no:cacheprovider",
         "--no-header", "-x"],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    lines = [ln for ln in (proc.stdout + proc.stderr).strip().splitlines() if ln.strip()]
    # A *tail*, not the last line: with -x the final line is the "stopping after 1
    # failures" banner, so a last-line-only excerpt can never contain the failure reason
    # a mutation may declare. That made the reason check unmatchable rather than wrong.
    return proc.returncode, "\n".join(lines[-12:])


#: pytest exits these when it never collected the requested node (4 = usage error,
#: 5 = no tests collected). Treating them as "the gate went red" is how a typo earns a
#: pass.
_NODE_NOT_FOUND_CODES = (4, 5)


def check_nodes(mutations) -> list:
    """Every mutation's gate must name a test that still exists in its file.

    Found the hard way: renaming a gate left this table pointing at the old name, and
    because pytest exits non-zero for "not found" the stale entry was reported
    ``GATE_IS_REAL`` -- a dead gate wearing a pass. The exit-code table catches it at
    runtime; this catches it before anything runs.
    """
    stale = []
    for entry_spec in mutations:
        key, node = entry_spec[0], entry_spec[5]
        path, _, test = node.partition("::")
        try:
            src = (ROOT / path).read_text(encoding="utf-8")
        except OSError:
            stale.append((key, node, "test file missing"))
            continue
        if f"def {test}(" not in src:
            stale.append((key, node, "no such test function"))
    return stale


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "q_substrate_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = check_nodes(MUTATIONS)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID     ] {key:32} -> {node} ({why})")

    before = {p: _digest(p) for p in (STORE, REFERENCE)}
    results = []
    for entry_spec in MUTATIONS:
        key, hole, path, old, new, node = entry_spec[:6]
        expect_tail = entry_spec[6] if len(entry_spec) > 6 else None
        original = _read(path)
        count = original.count(old)
        entry = {"mutation": key, "hole": hole, "gate": node.split("::")[-1],
                 "site": str(path.relative_to(ROOT)), "matched": count,
                 "expected_failure_text": expect_tail}
        if count != 1:
            entry.update(verdict="MUTATION_NOT_APPLIED",
                         detail=f"the anchor matched {count} times, expected exactly 1")
            results.append(entry)
            print(f"[{entry['verdict']:18}] {key}")
            continue
        try:
            _write(path, original.replace(old, new))
            code, tail = _run_node(node)
        finally:
            _write(path, original)
        # GATE_IS_REAL iff pytest exited 1 **for the stated reason**.
        #
        # `code != 0` was too generous: pytest also exits 2 (interrupted / collection
        # error) and 3 (internal error), and these mutations edit SOURCE FILES, so a
        # mutation that accidentally introduces a syntax or import error would be
        # reported as a dead gate. That is the same mistake as counting "node not found"
        # as a pass, one failure mode further out.
        #
        # And a non-zero exit is still not enough on its own when the mutation claims to
        # reopen a hole: a gate that fails because a message changed has not shown the
        # hole was reachable, so such a mutation may declare the text its failure must
        # contain.
        if code == 1 and expect_tail and expect_tail not in tail:
            verdict = "WRONG_FAILURE_REASON"
        elif code == 1:
            verdict = "GATE_IS_REAL"
        elif code == 0:
            verdict = "NOT_A_GATE"
        elif code in _NODE_NOT_FOUND_CODES:
            verdict = "NODE_NOT_FOUND"
        else:
            verdict = "HARNESS_ERROR"
        entry.update(exit_code=code, tail=tail, verdict=verdict)
        results.append(entry)
        print(f"[{entry['verdict']:18}] {key:32} -> {entry['gate']}")

    after = {p: _digest(p) for p in (STORE, REFERENCE)}
    restored = before == after
    real = sum(1 for r in results if r["verdict"] == "GATE_IS_REAL")
    payload = {
        "check": "Q substrate gate mutation self-check",
        "n_mutations": len(MUTATIONS),
        "n_gate_is_real": real,
        "n_not_a_gate": sum(1 for r in results if r["verdict"] == "NOT_A_GATE"),
        "n_mutation_not_applied": sum(1 for r in results
                                      if r["verdict"] == "MUTATION_NOT_APPLIED"),
        "n_node_not_found": sum(1 for r in results if r["verdict"] == "NODE_NOT_FOUND"),
        "n_harness_error": sum(1 for r in results if r["verdict"] == "HARNESS_ERROR"),
        "stale_node_ids": [list(s) for s in stale],
        "tree_restored_byte_identical": restored,
        "file_digests": {str(p.relative_to(ROOT)): d for p, d in after.items()},
        "results": results,
    }
    out = pathlib.Path(args.json)
    if not out.is_absolute():
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
