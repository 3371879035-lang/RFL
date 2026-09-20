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
| 4 | the domains stop being distinct | every tag forced to one value | `test_address_domain::test_2` |

Mutations 1 and 2 target the **generic** rule in `runner.py`, so they are the ones that show the
boundary is load-bearing for every architecture rather than for the real ones only. Mutation 3 is
the failure this project already paid for once: a canonical form that omits a component gives two
distinct addresses one receipt identity. Mutation 4 shows the tag is what keeps two architectures'
domains apart.

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
        "domains_not_distinct",
        "every address domain reports the same tag, so one architecture's plan can be read as "
        "another's",
        ADDR_PATH,
        "    return AddressDomain(tag=tag, require_credited=require_credited,",
        '    return AddressDomain(tag="same", require_credited=require_credited,   # MUTATED',
        f"{ADDR}::test_4_the_canonical_form_is_injective_on_the_legal_domain",
        "share a receipt identity",
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
