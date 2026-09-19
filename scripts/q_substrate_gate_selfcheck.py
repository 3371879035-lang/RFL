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
        f"{TESTS}::test_12_an_incomplete_reference_fails_at_construction_not_at_lookup",
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

    Not style: the mutated and the original file can land in the same mtime second, and
    CPython validates a cached ``.pyc`` on ``(mtime, size)``, which once replayed the
    previous mutation and produced a false ``NOT_A_GATE``.
    """
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", node, "-q", "-p", "no:cacheprovider",
         "--no-header", "-x"],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    lines = [ln for ln in (proc.stdout + proc.stderr).strip().splitlines() if ln.strip()]
    return proc.returncode, (lines[-1] if lines else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "q_substrate_gate_selfcheck.json"))
    args = ap.parse_args()

    before = {p: _digest(p) for p in (STORE, REFERENCE)}
    results = []
    for key, hole, path, old, new, node in MUTATIONS:
        original = _read(path)
        count = original.count(old)
        entry = {"mutation": key, "hole": hole, "gate": node.split("::")[-1],
                 "site": str(path.relative_to(ROOT)), "matched": count}
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
        entry.update(exit_code=code, tail=tail,
                     verdict="GATE_IS_REAL" if code != 0 else "NOT_A_GATE")
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
    ok = restored and real == len(MUTATIONS)
    print("  SELF-CHECK " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
