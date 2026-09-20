r"""Mutation self-check for A80 §68.1–§68.2, Step 1: the address/receipt substrate.

$$\boxed{\text{a gate that passes is not evidence; it is evidence only that the gate did
not look}}$$

Step 1 claims to generalise the plan/receipt/locality contract **by type**, and its acceptance
condition is that no number moves. Both halves are checked here:

| # | hole | mutation | gate that must catch it |
|---|---|---|---|
| 1 | the credited boundary stops asking the domain | `require_credited` disabled | `test_address_domain::test_2` / the L3 gates |
| 2 | the store address is not typed | `require_store` disabled | `test_address_domain::test_1` |
| 3 | the canonical form is deterministic but not injective | a component dropped from `_decision_canonical` | `test_address_domain::test_4` |
| 4 | D_Q's strict policy is imposed on the frozen $D_{patch}$ | the slice's admission policy is replaced | `test_b1_patch_slice::test_19` |

Mutations 1 and 2 target the **generic** rule in `runner.py`, so they show the boundary is
load-bearing for every architecture rather than for the real ones only. Mutation 3 is the failure
this project already paid for once: a canonical form that omits a component gives two distinct
addresses one receipt identity. Mutation 4 is the drift this step actually produced and then had
to undo: making the credited boundary universal removed the **frozen** $D_{patch}$ asymmetry.

**One earlier entry was removed rather than reworded.** `domains_not_distinct` forced the two
*dummy* domains in the test file to share a tag and was killed by the assertion
`A_DOMAIN != B_DOMAIN` -- it reopened no production hole, since what stops an $A$-slice accepting
a $B$-address is `require_credited`, not tag equality. A mutation that only rearranges test
constants is not gate evidence, so it was replaced by mutation 4 -- a real production drift -- rather
than kept to make a number.

Usage::

    python scripts/address_domain_gate_selfcheck.py [--json PATH]
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
TIER = SRC / "b1" / "tier.py"
ADDR_PATH = ROOT / "tests" / "rebuild" / "test_address_domain.py"
ADDR = "tests/rebuild/test_address_domain.py"

MUTATIONS: tuple = (
    (
        "credited_boundary_disabled",
        "the cell-level credited-address boundary stops asking the architecture's domain, so "
        "a value no domain admitted reaches a plan",
        RUNNER,
        "        spec.domain.require_credited(a)\n",
        "        pass                            # MUTATED: boundary disabled\n",
        f"{ADDR}::test_2_a_slice_rejects_the_other_domains_address",
        # the boundary no longer refuses, so the run completes and the gate fails by NOT RAISING
        "DID NOT RAISE",
    ),
    (
        "store_address_untyped",
        "the plan boundary stops typing the store address, so an edit may name a key the "
        "slice's store cannot hold",
        RUNNER,
        "            spec.domain.require_store(e.address)\n",
        "            pass                        # MUTATED: store untyped\n",
        f"{ADDR}::test_3b_an_edit_with_an_untyped_store_address_is_refused",
        "keyed by int",
    ),
    (
        "canonical_form_not_injective",
        "the canonical receipt drops the opt index, so two distinct credited contexts with "
        "different `z` share one receipt identity",
        TIER,
        '    return f"{s.x},{s.y},{s.t},{s.kappa},{s.phi},{value.z},{value.m}"',
        '    return f"{s.x},{s.y},{s.t},{s.kappa},{s.phi},{value.m}"   # MUTATED: z dropped',
        f"{ADDR}::test_4_the_canonical_form_is_injective_on_the_legal_domain",
    ),
    (
        "d_patch_policy_made_strict",
        "the generic boundary applies D_Q's strict admission to EVERY architecture, which "
        "silently repairs the frozen D_patch asymmetry: NoWrite stops accepting the alias it "
        "is recorded as accepting",
        SRC / "b1" / "tier.py",
        '    require_credited=_legacy_accept,\n'
        '    require_store=_legacy_accept,',
        '    require_credited=_decision_credited,   # MUTATED: D_Q policy imposed\n'
        '    require_store=_decision_store,',
        "tests/rebuild/test_b1_patch_slice.py"
        "::test_19_the_frozen_d_patch_alias_asymmetry_is_preserved",
    ),
    (
        "domain_rules_unchecked",
        "an address domain may be built from non-callables, so the architecture's rules become "
        "a name the shared layer cannot ask",
        SRC / "b1" / "addressing.py",
        '            if not callable(getattr(self, name)):\n',
        '            if False:                   # MUTATED: rules unchecked\n',
        f"{ADDR}::test_3c_a_domain_is_rules_not_a_name",
        # the construction succeeds, so the gate fails by NOT RAISING rather than on a message
        "DID NOT RAISE",
    ),
    (
        "slice_domain_untyped",
        "a slice may carry something that is not an AddressDomain, so the credited boundary "
        "would call a method on whatever it was handed",
        SRC / "b1" / "tier.py",
        "        if not isinstance(self.domain, AddressDomain):\n",
        "        if False:                   # MUTATED: domain untyped\n",
        f"{ADDR}::test_3c_a_domain_is_rules_not_a_name",
        "DID NOT RAISE",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "address_domain_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = harness.check_nodes(MUTATIONS, ROOT)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID       ] {key:34} -> {node} ({why})")

    results, restored = harness.run_mutations(
        MUTATIONS, ROOT, (RUNNER, TIER, ADDR_PATH, SRC / "b1" / "addressing.py"))
    return harness.summarise("Step 1 address-domain gate mutation self-check", MUTATIONS,
                             results, restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
