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
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _mutation_harness as harness  # noqa: E402
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r" / "q_substrate_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = harness.check_nodes(MUTATIONS, ROOT)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID       ] {key:34} -> {node} ({why})")

    results, restored = harness.run_mutations(MUTATIONS, ROOT, (STORE, REFERENCE))
    return harness.summarise('Q substrate gate mutation self-check', MUTATIONS, results, restored, stale, ROOT,
                             pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
