r"""Mutation self-check for the $P$ / `ProcessCommit` B1 path (A80 §68.5).

$$\boxed{\text{a gate that passes is not evidence; it is evidence only that the gate did not
look}}$$

Every gate added with the $P$ cell is re-run against a **deliberately reverted** source tree, one
mutation at a time, and must go **red**. A gate whose mutation leaves it green is reported as
`NOT_A_GATE`, and a mutation whose anchor does not match exactly once is `MUTATION_NOT_APPLIED`.

The mutations are the defects this cell can actually have:

| # | hole | mutation |
|---|---|---|
| 1 | $P_{id}$ moved to $L_0$ — the placement A76 §63.1 forbids | `PId.tier` -> `L0_FACTUAL` |
| 2 | the proposal is read from the **state** rather than the delivered input | the runner sources it from `snapshot().process_commit_provider()` |
| 3 | numeric aliases pass the exact-integer rule | `is_true_int` -> `isinstance(int)` |
| 4 | the option-domain check stops firing | membership test disabled |
| 5 | the assisted input is duck-typed | nominal check replaced by `is None` |
| 6 | the $L_3$ alias is re-implemented | a second `plan` on `PLocalOracleRestore` |
| 7 | the envelope may be a superset of the credited population | `!=` -> `not <=` |
| 8 | the delivery need not agree with the credited address | agreement test disabled |
| 9 | the credit unit check stops firing | family test disabled |

Mutation 2 is the laundering one A80 §68.5 names: the fact that some kernel object can *reach* a
proposal does not license the cell, and the gate that kills it is the one that runs on a store
already holding a different legal option at the same key.

Usage::

    python scripts/p_gate_selfcheck.py [--json PATH]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _mutation_harness as harness  # noqa: E402
SRC = ROOT / "src" / "rfl_rebuild"
TESTS = "tests/rebuild/test_p_process.py"

LAWS = SRC / "b1" / "laws.py"
RUNNER = SRC / "b1" / "runner.py"
TIER = SRC / "b1" / "tier.py"
PROC = SRC / "b1" / "process.py"

#: (id, hole, path, old, new, pytest node id[, expected failure text])
MUTATIONS: tuple = (
    (
        "p_id_moved_to_l0",
        "P_id is declared in the L0 cell -- the placement A76 63.1 rules out, because the factual "
        "rows carry z^in-force and never z^proposal, so the key cannot be known there. The run is "
        "still refused, so what kills this is the table assertion rather than a raise",
        LAWS,
        "    name = \"P_id\"\n    tier = Tier.L1_CORRECTIVE",
        "    name = \"P_id\"\n    tier = Tier.L0_FACTUAL        # MUTATED: moved to L0",
        f"{TESTS}::test_4_p_id_at_l0_is_a_protocol_error_even_with_a_legal_integer_in_hand",
        "PId.tier is Tier.L1_CORRECTIVE",
    ),
    (
        "proposal_from_the_state_side_channel",
        "the runner takes the proposal from the kernel's own C_P^L (snapshot()."
        "process_commit_provider()) instead of the delivered assisted input -- the laundering "
        "A80 68.5 forbids. On a store already holding a different legal option at the same key "
        "the run stops being the restore it exists for",
        RUNNER,
        "        envelope = build_process_envelope(addresses, assisted)\n"
        "        validate_process_envelope(addresses, envelope)\n",
        "        from rfl_rebuild.b1.process import AssistedInput as _AI        # MUTATED\n"
        "        _provider = pre_state.snapshot().process_commit_provider()    # MUTATED\n"
        "        envelope = build_process_envelope(addresses, _AI(\n"
        "            z_proposal=_provider(addresses[0])))                      # MUTATED\n"
        "        validate_process_envelope(addresses, envelope)\n",
        f"{TESTS}::test_8_the_proposal_comes_from_the_assisted_input_not_from_the_store",
        "disagrees with the credited process address",
    ),
    (
        "exact_int_check_relaxed",
        "the exact-integer rule becomes a subclass rule, so True/False (and any int subclass) are "
        "credited as the option they are value-equal to -- A78 66.5's folding lesson, reopened",
        PROC,
        "    if not is_true_int(value):\n",
        "    if not isinstance(value, int):        # MUTATED: subclass, not exact type\n",
        f"{TESTS}::test_3_the_option_key_is_exact_integer_first_then_domain_membership",
        "DID NOT RAISE",
    ),
    (
        "option_domain_check_removed",
        "an integer outside option_ids() becomes a legal process address -- the `P_override[99]` "
        "defect class the store already had to be closed against",
        PROC,
        "    if value not in K.option_ids():\n",
        "    if False:                            # MUTATED: domain check disabled\n",
        f"{TESTS}::test_3_the_option_key_is_exact_integer_first_then_domain_membership",
        "DID NOT RAISE",
    ),
    (
        "assisted_input_duck_typed",
        "any object carrying z_proposal is accepted as the assisted input, so the cell takes its "
        "input from whatever looks like one, including code under test",
        PROC,
        "    if type(assisted) is not AssistedInput:\n",
        "    if assisted is None:                 # MUTATED: duck-typed carrier\n",
        f"{TESTS}::test_2_the_assisted_input_is_nominal",
        "DID NOT RAISE",
    ),
    (
        "p_alias_reimplemented",
        "the L3 class defines its own plan, so the alias is two implementations that agree rather "
        "than one shared operation",
        LAWS,
        "    name = \"LocalOracleRestore\"\n    alias_of = \"P_id\"\n    tier = Tier.L3_ORACLE",
        "    name = \"LocalOracleRestore\"\n    alias_of = \"P_id\"\n    tier = Tier.L3_ORACLE\n\n"
        "    def plan(self, addresses, targets):        # MUTATED: a second implementation\n"
        "        return LawPlan(self.name, tuple(\n"
        "            AddressPlan(z, (Edit(PROCESS, z, z),)) for z in addresses))",
        f"{TESTS}::test_10_the_alias_is_one_implementation_and_the_same_transformation",
        "PLocalOracleRestore.plan is PId.plan",
    ),
    (
        "envelope_superset_accepted",
        "the L1 envelope need only contain the credited addresses, so it may carry an entry for "
        "an address that was never credited",
        PROC,
        "    if keys != expected:\n",
        "    if not expected <= keys:             # MUTATED: superset accepted\n",
        f"{TESTS}::test_6_the_envelope_must_be_exactly_the_credited_population_and_must_agree",
        "DID NOT RAISE",
    ),
    (
        "delivery_agreement_removed",
        "the delivered proposal need not equal the credited address, so the cell may write one "
        "option while being credited at another",
        PROC,
        "        if z != a:\n",
        "        if False:                        # MUTATED: agreement unchecked\n",
        f"{TESTS}::test_6_the_envelope_must_be_exactly_the_credited_population_and_must_agree",
        "DID NOT RAISE",
    ),
    (
        "credited_unit_check_removed",
        "another architecture's credit unit is accepted by rho_P, so a foreign credit reaches the "
        "process store",
        PROC,
        "    if unit != PROCESS_UNIT:\n",
        "    if False:                            # MUTATED: family check disabled\n",
        f"{TESTS}::test_1_the_credit_unit_is_the_static_process_family",
        "DID NOT RAISE",
    ),
    (
        "entry_point_trusts_a_pre_resolved_address",
        "the entry point treats an integer in the units position as an address rho_P already "
        "produced, so a caller can assert an address the resolver never yielded -- the provenance "
        "blocker, in the shape the review found it: the L3 arm then writes a key that is not "
        "rho_P(ProcessCommit, z^proposal) at all",
        RUNNER,
        "    addresses = resolve_process_addresses(credited_units, assisted)\n",
        "    addresses = tuple(u for u in credited_units if type(u) is int) or \\\n"
        "        resolve_process_addresses(credited_units, assisted)        # MUTATED\n",
        f"{TESTS}::test_17_the_credited_population_is_units_and_the_address_follows_the_input",
        "DID NOT RAISE",
    ),
    (
        "l3_skips_rho_p",
        "L3 resolves its address from the credited population directly instead of through rho_P, "
        "so it never consumes the assisted input and the same-cell guarantee goes with it -- the "
        "other half of the provenance blocker. It is killed on the BAD-INPUT loop, which is the "
        "point: an input nobody reads cannot be refused",
        RUNNER,
        "    law, tier = _law_contract(law, spec)\n"
        "    addresses = resolve_process_addresses(credited_units, assisted)\n"
        "    described = spec.fields(tier)\n",
        "    law, tier = _law_contract(law, spec)\n"
        "    described = spec.fields(tier)\n"
        "    addresses = (resolve_process_addresses(credited_units, assisted)\n"
        "                 if described else credited_units)                 # MUTATED\n",
        f"{TESTS}::test_16_both_l3_arms_consume_the_assisted_input_before_planning",
        "DID NOT RAISE",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "p_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = harness.check_nodes(MUTATIONS, ROOT)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID       ] {key:34} -> {node} ({why})")

    results, restored = harness.run_mutations(MUTATIONS, ROOT, (LAWS, TIER, RUNNER, PROC))
    return harness.summarise("P / ProcessCommit gate mutation self-check", MUTATIONS, results,
                             restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
