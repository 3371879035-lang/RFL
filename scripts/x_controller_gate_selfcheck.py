r"""Mutation self-check for the $D_X$ gates (A80 §68.3–§68.4).

$$\boxed{\text{a gate that passes is not evidence; it is evidence only that the gate did
not look}}$$

| # | hole | mutation | gate that must catch it |
|---|---|---|---|
| 1 | the shared operation secretly depends on the $L_0$-only envelope | `site.cmd` replaced by `targets[site]["a_cmd"]` | `test_10` (a **real** $L_3$ run) |
| 2 | the contract check stops running | `require_admissible_sites` disabled | `test_1` |
| 3 | the canonical receipt drops the command | `_site_canonical` omits `cmd` | `test_12` |
| 4 | the alias is reimplemented instead of shared | a second `plan` on the $L_3$ class | `test_9` |
| 5 | the credited population stops being typed | `require_credited` disabled | `test_4` |
| 6 | locality stops being the runner's rule | the owner consult disabled | `test_6` |

Mutation 1 is the one this step produced and had to undo: `XId.plan` first read
`targets[site]["a_cmd"]`, which is correct at $L_0$ and impossible at $L_3$, where the cell
delivers $\varnothing$. It is killed by a **real $L_3$ execution**, not by comparing plan objects —
`XLocalOracleRestore.plan is XId.plan` proves identity, and this proves the shared plan *runs* in
both cells, which is the pair that makes the alias non-nominal.

Usage::

    python scripts/x_controller_gate_selfcheck.py [--json PATH]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _mutation_harness as harness  # noqa: E402

SRC = ROOT / "src" / "rfl_rebuild"
LAWS = SRC / "b1" / "laws.py"
TIER = SRC / "b1" / "tier.py"
RUNNER = SRC / "b1" / "runner.py"
CTRL = SRC / "b1" / "controller.py"
TESTS = "tests/rebuild/test_x_controller.py"

MUTATIONS: tuple = (
    (
        "cmd_from_the_l0_envelope",
        "the shared operation reads a^{cmd} from the L0-only envelope, so it cannot run in the "
        "L3 cell where the delivery is empty -- the very defect this step produced",
        LAWS,
        "        return LawPlan(self.name, tuple(\n"
        "            AddressPlan(site, (Edit(CONTROLLER, site, site.cmd),))\n"
        "            for site in addresses))",
        "        return LawPlan(self.name, tuple(\n"
        "            AddressPlan(site, (Edit(CONTROLLER, site,\n"
        "                                    targets[site][\"a_cmd\"]),))   # MUTATED\n"
        "            for site in addresses))",
        f"{TESTS}::test_10_the_same_plan_runs_at_l3_with_no_envelope",
    ),
    (
        "contract_check_disabled",
        "the pre-plan contract check stops running, so an inadmissible command reaches planning",
        CTRL,
        "    index = _row_index(rows)\n    for site in sites:\n"
        "        if type(site) is not K.ControllerSite:\n",
        "    index = _row_index(rows)\n    for site in ():                # MUTATED: check disabled\n"
        "        if type(site) is not K.ControllerSite:\n",
        f"{TESTS}::test_1_an_inadmissible_command_is_refused_at_the_pre_plan_boundary",
    ),
    (
        "canonical_drops_the_command",
        "the canonical receipt omits cmd, so two distinct credited sites share one receipt "
        "identity -- the defect the legacy controller key actually had",
        TIER,
        '    return f"{s.x},{s.y},{s.t},{s.kappa},{s.phi}|{value.cmd}"',
        '    return f"{s.x},{s.y},{s.t},{s.kappa},{s.phi}"      # MUTATED: cmd dropped',
        f"{TESTS}::test_12_the_canonical_receipt_changes_with_the_command",
    ),
    (
        "alias_reimplemented",
        "the L3 class defines its own plan, so the alias is two implementations that agree "
        "rather than one shared operation",
        LAWS,
        "    name = \"LocalOracleRestore\"\n    alias_of = \"X_id\"\n    tier = Tier.L3_ORACLE",
        "    name = \"LocalOracleRestore\"\n    alias_of = \"X_id\"\n    tier = Tier.L3_ORACLE\n\n"
        "    def plan(self, addresses, targets):        # MUTATED: a second implementation\n"
        "        return LawPlan(self.name, tuple(\n"
        "            AddressPlan(s, (Edit(CONTROLLER, s, s.cmd),)) for s in addresses))",
        f"{TESTS}::test_9_the_alias_is_a_real_implementation_alias",
    ),
    (
        "credited_site_untyped",
        "the credited site stops being strictly typed, so a floated state or a bool command is "
        "credited as the legal site",
        TIER,
        "    bad = non_integer_state_fields(value.state)\n",
        "    bad = None                      # MUTATED: state fields untyped\n",
        f"{TESTS}::test_4_the_credited_site_is_strictly_typed",
        "DID NOT RAISE",
    ),
    (
        "owner_consult_removed",
        "the runner stops consulting owner_X for entry edits, so a mis-owned write passes",
        RUNNER,
        "            if spec.domain.owner(e.address) != p.address:\n",
        "            if False:                   # MUTATED: locality unchecked\n",
        f"{TESTS}::test_6_owner_x_is_load_bearing_on_the_real_path",
        "DID NOT RAISE",
    ),
    (
        "rho_x_accepts_the_decision_family",
        "the controller parser is widened back to the decision family, so rho_X consumes "
        "Decision_t again -- the merge of A69's two families that A76 63.10 keeps apart. This is "
        "the Step 2 blocker: every store-side gate stays green while the arrow's input is wrong",
        CTRL,
        '_CONTROLLER_RE = re.compile(r"^ControllerSite_(\\d+)$")',
        '_CONTROLLER_RE = re.compile(r"^(?:ControllerSite|Decision)_(\\d+)$")   # MUTATED',
        f"{TESTS}::test_18_rho_x_consumes_the_controller_family_and_refuses_the_"
        "decision_family",
        "DID NOT RAISE",
    ),
    (
        "rho_x_duplicate_guard_dead",
        "the duplicate check can never fire, so two copies of one controller unit are silently "
        "de-duplicated -- the historical shape of this defect in targets.py, and the reason the "
        "gate asserts the rule's own message rather than that something was refused",
        CTRL,
        "        if u in seen:\n",
        "        if False:                   # MUTATED: the check can never fire\n",
        f"{TESTS}::test_19_rho_x_fails_stop_on_bad_units",
        "both resolve to",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "x_controller_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = harness.check_nodes(MUTATIONS, ROOT)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID       ] {key:34} -> {node} ({why})")

    results, restored = harness.run_mutations(MUTATIONS, ROOT, (LAWS, TIER, RUNNER, CTRL))
    return harness.summarise("X controller gate mutation self-check", MUTATIONS, results,
                             restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
