r"""Mutation self-check for the $D_Q\times L_3$ gates (A78 §66).

$$\boxed{\text{a gate that passes is not evidence; it is evidence only that the gate
did not look}}$$

| # | hole | mutation | gate that must catch it |
|---|---|---|---|
| 1 | the row operation is not lowered at all | lowering disabled | `test_10` |
| 2 | only the credited address's own entry is deleted | the lowering keeps one entry | `test_13` |
| 3 | the plan-shape rule is not enforced | edits and a row op accepted together | `test_8` |
| 4 | the empty cell acquires a builder | the L3 branch builds one anyway | `test_6` |
| 5 | the substrate learns the row operation | `owner_Q` branches on `RestoreRow` | `test_3` |
| 6 | $D_Q$'s $L_3$ law reuses the patch plan | the D_Q `plan` returns the patch plan | `test_18` |
| 7 | the runner never consults the row owner | the row-op owner check deleted | `test_9c` |
| 8 | the owner resolver forgets the row operation | `dq_owner`'s row branch removed | `test_9d` |
| 9 | the row operation's type is not closed | the nominal check deleted | `test_9b` |
| 10 | a value-equal context alias is accepted | the strict-context check deleted | `test_9bx` |
| 11 | the boundary is arm-specific | the cell-level credited-address check deleted | `test_9f` |

**Two properties are deliberately NOT mutated here**, and saying so is part of the evidence:

* "the ledger reads the lowered edits" is covered by mutation 1 from the other end —
  skipping the lowering is the same defect — and a receipt-computation mutation that still
  receives the lowered plan behaves *identically*, so it would be a mutation with no
  observable difference. That is the `NOT_A_GATE` this table was corrected for.
* "the lowering is not reused across runs" is gated by `test_11b`, but has no
  single-expression mutation: making the lowering stale means giving `_lower_row_ops` state
  it does not have, which is inventing a defect rather than reverting a fix.

An earlier revision of this table also carried a "lower against the post-state" entry whose
mutation reduced to `plan = plan` — the same thing as mutation 1 — and was reported
`WRONG_FAILURE_REASON` for declaring a message that a different assertion produced.

Usage::

    python scripts/l3_row_restore_gate_selfcheck.py [--json PATH]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _mutation_harness as harness  # noqa: E402

SRC = ROOT / "src" / "rfl_rebuild"
RUNNER = SRC / "b1" / "runner.py"
LAWS = SRC / "b1" / "laws.py"
PLAN = SRC / "b1" / "plan.py"
STORE = SRC / "learner" / "store.py"
TESTS = "tests/rebuild/test_l3_row_restore.py"

MUTATIONS: tuple = (
    (
        "row_op_not_lowered",
        "the symbolic row operation is never lowered, so the law's plan reaches the "
        "transaction with no edits and the row is left as it was",
        RUNNER,
        "    plan = _lower_row_ops(plan, pre_view, spec)\n"
        "    _validate_plan(plan, addresses, spec)",
        "    pass                        # MUTATED: lowering skipped\n"
        "    _validate_plan(plan, addresses, spec)",
        f"{TESTS}::test_10_lowering_uses_the_pre_state_and_the_ledger_reads_its_output",
    ),
    (
        "only_one_entry_restored",
        "the lowering keeps the first present entry, so the row is only partly returned "
        "to Q_D*",
        RUNNER,
        "        present = sorted(\n"
        "            (e for e in pre_view\n"
        "             if (e.state, e.z, e.m) == (context.state, context.z, context.m)),\n"
        "            key=_entry_key)",
        "        present = sorted(\n"
        "            (e for e in pre_view\n"
        "             if (e.state, e.z, e.m) == (context.state, context.z, context.m)),\n"
        "            key=_entry_key)[:1]     # MUTATED: first entry only",
        f"{TESTS}::test_13_a_row_restore_does_not_reach_outside_its_credited_rows",
    ),
    (
        "plan_shape_rule_removed",
        "an address-plan may carry entry edits and a row operation together, so two "
        "descriptions of one context compose by accident",
        LAWS,
        "            if self.edits:\n"
        "                raise ProtocolError(\n"
        "                    f\"the address-plan for {self.address!r} carries both entry edits and \"\n",
        "            if False:               # MUTATED: shape rule removed\n"
        "                raise ProtocolError(\n"
        "                    f\"the address-plan for {self.address!r} carries both entry edits and \"\n",
        f"{TESTS}::test_8_an_address_plan_is_entry_edits_or_one_row_op_never_both",
        "DID NOT RAISE",
    ),
    (
        "empty_cell_acquires_a_builder",
        "the L3 branch builds an envelope anyway, so an empty cell silently gains an "
        "evaluator-side read path and the poison evidence is dereferenced",
        RUNNER,
        "        return _run(law, tier, pre_state, addresses, None, spec, q_reference)\n",
        "        return _run(law, tier, pre_state, addresses,\n"
        "                    build_factual_envelope(rows, addresses),   # MUTATED\n"
        "                    spec, q_reference)\n",
        f"{TESTS}::test_6_poison_evidence_does_not_reach_the_l3_path",
        # The poison raises on attribute access, iteration and indexing, and this mutation
        # reaches it by iterating -- so the reason is the shared phrase rather than the
        # first message. Declaring "touched evaluator evidence" made the verdict
        # WRONG_FAILURE_REASON for a gate that had failed correctly.
        "evaluator evidence",
    ),
    (
        "substrate_learns_the_row_op",
        "owner_Q branches on the B1 row operation, so the store learns an update law and "
        "the separation Step 3 established is traded away",
        STORE,
        "    return DecisionAddress(state=address.state, z=address.z, m=address.m)\n",
        "    if type(address).__name__ == \"RestoreRow\":   # MUTATED: the store learns a law\n"
        "        return address.context\n"
        "    return DecisionAddress(state=address.state, z=address.z, m=address.m)\n",
        f"{TESTS}::test_3_the_substrate_does_not_learn_the_row_operation",
    ),
    (
        "dq_l3_reuses_the_patch_plan",
        "the D_Q L3 law REUSES the patch implementation's plan, so the arm emits DECISION "
        "edits rather than a row operation. Inheriting the class was not this defect: the "
        "subclass's own `plan` still won the method resolution, so the hole never reopened "
        "and the gate went red only on `issubclass`",
        LAWS,
        "    def plan(self, addresses, targets) -> LawPlan:\n"
        "        return LawPlan(self.name, tuple(AddressPlan(a, row_op=RestoreRow(a))\n"
        "                                        for a in addresses))",
        "    def plan(self, addresses, targets) -> LawPlan:\n"
        "        # MUTATED: the patch implementation, which emits DECISION edits\n"
        "        return DeleteFactualPatch().plan(addresses, targets)",
        f"{TESTS}::test_18_the_reused_patch_plan_is_caught_by_the_operation_kind",
    ),
    (
        "row_op_owner_unchecked",
        "the runner never consults the owner resolver for a row operation, so a row "
        "operation emitted under another architecture reaches the lowering",
        RUNNER,
        "        if p.row_op is not None:\n"
        "            # §66.5 is only a contract if the runner CONSULTS the resolver. Without this,\n",
        "        if False:                   # MUTATED: row owner unchecked\n"
        "            # §66.5 is only a contract if the runner CONSULTS the resolver. Without this,\n",
        f"{TESTS}::test_9c_a_row_operation_cannot_leak_into_another_architecture",
    ),
    (
        "row_owner_resolver_row_branch_removed",
        "the D_Q owner resolver no longer knows the row operation, so a legitimate L3 run "
        "cannot establish locality",
        PLAN,
        "    if type(op) is RestoreRow:\n        return op.context\n",
        "    pass                            # MUTATED: row branch removed\n",
        f"{TESTS}::test_9d_a_real_run_depends_on_the_row_owner_resolver",
    ),
    (
        "credited_address_boundary_removed",
        "the credited-address boundary is not checked at the cell level, so it is carried "
        "by whichever arm constructs a typed object: the treatment still refuses a "
        "value-equal context alias through RestoreRow, while NoWriteRef(L3) accepts it and "
        "completes",
        RUNNER,
        "    _require_strict_decision_addresses(addresses)\n",
        "    pass                            # MUTATED: cell boundary removed\n",
        f"{TESTS}::test_9f_the_credited_address_boundary_is_arm_uniform",
        "DID NOT RAISE",
    ),
    (
        "row_context_not_strictly_typed",
        "RestoreRow accepts a value-equal but type-malformed context alias, which then "
        "satisfies the plan's context check, the owner resolver's locality check and the "
        "lowering's row match by value equality, deleting a legal credited row",
        PLAN,
        "        if not is_decision_context(self.context.state, self.context.z, self.context.m):\n",
        "        if False:               # MUTATED: alias accepted\n",
        f"{TESTS}::test_9bx_a_value_equal_context_alias_is_not_a_legal_context",
        "DID NOT RAISE",
    ),
    (
        "row_op_type_not_closed",
        "any object exposing `.context` grants row-restore capability, because the plan "
        "boundary does not close the operation's type",
        LAWS,
        "            if type(self.row_op) is not RestoreRow:\n",
        "            if False:               # MUTATED: duck-typed row op\n",
        f"{TESTS}::test_9b_a_stand_in_row_operation_cannot_grant_row_restore",
        "DID NOT RAISE",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "l3_row_restore_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = harness.check_nodes(MUTATIONS, ROOT)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID       ] {key:34} -> {node} ({why})")

    results, restored = harness.run_mutations(MUTATIONS, ROOT, (RUNNER, LAWS, PLAN, STORE))
    return harness.summarise("L3 row-restore gate mutation self-check", MUTATIONS, results,
                             restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
