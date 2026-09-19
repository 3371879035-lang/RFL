r"""Mutation self-check for the $D_Q\times L_2$ gates (A77 §65.7, §65.8, §65.10).

$$\boxed{\text{a gate that passes is not evidence; it is evidence only that the gate
did not look}}$$

| # | hole | mutation | gate that must catch it |
|---|---|---|---|
| 1 | the prefix invariant stops being enforced | the `rows(CF)[0:t] == rows(F)[0:t]` check deleted | `test_3` |
| 2 | the counterfactual target is the *factual* suffix return | the fold run over the factual rows | `test_4` |
| 3 | Dual degenerates into its factual half | an absent $a^+$ writes the factual entry | `test_8b` |
| 4 | the alternative need not be the shared one | the $a^+$ comparison deleted | `test_5b` |
| 5 | a half counterfactual record is accepted | the paired-presence check deleted | `test_14` |
| 6 | the build set is not typed | the `type(t) is Tier` check deleted | `test_16` |
| 7 | the intervention is added rather than replaced | the removal of the factual $do(d_t)$ dropped | `test_2` |

Mutation 7 is the one that makes "replace, not add" an executable statement: without the
removal, `InterventionSet` refuses two members on one structural node and the replay
raises `MalformedIntervention` — which is the *designed* failure, not an accident.

Usage::

    python scripts/l2_counterfactual_gate_selfcheck.py [--json PATH]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _mutation_harness as harness  # noqa: E402

SRC = ROOT / "src" / "rfl_rebuild"
CF = SRC / "b1" / "counterfactual.py"
LAWS = SRC / "b1" / "laws.py"
TIER = SRC / "b1" / "tier.py"
TESTS = "tests/rebuild/test_l2_counterfactual.py"

MUTATIONS: tuple = (
    (
        "prefix_invariant_removed",
        "the counterfactual replay is no longer required to share the factual prefix, so "
        "a replay that dropped DecisionReadView_pre produces a target silently",
        CF,
        "    prefix_f = rows[:t]\n"
        "    prefix_cf = cf_rows[:t]\n"
        "    if prefix_cf != prefix_f:\n",
        "    prefix_f = rows[:t]\n"
        "    prefix_cf = cf_rows[:t]\n"
        "    if False:                   # MUTATED: prefix unchecked\n",
        f"{TESTS}::test_3_a_replay_that_drops_the_pre_update_view_is_caught_by_the_prefix",
    ),
    (
        "cf_target_is_the_factual_suffix",
        "G_t^CF is computed from the factual rows, so the counterfactual becomes a copy "
        "of the factual target and the arm measures nothing",
        CF,
        "    return factual_return_to_go(cf_rows, t)",
        "    return factual_return_to_go(rows, t)      # MUTATED: factual rows",
        f"{TESTS}::test_4_the_cf_target_is_the_frozen_fold_over_the_counterfactual_rows",
    ),
    (
        "dual_degrades_to_its_factual_half",
        "an absent a^+ writes the factual entry anyway, so Dual commits half of itself "
        "at that address (A76 §63.3)",
        LAWS,
        "            if rec[\"a_plus\"] is None:\n"
        "                plans.append(AddressPlan(a, (), NO_VALID_ALTERNATIVE))\n"
        "                continue\n"
        "            factual = QAddress(state=a.state, z=a.z, m=a.m, a=rec[\"a_factual\"])",
        "            if rec[\"a_plus\"] is None:      # MUTATED: factual half only\n"
        "                entry = QAddress(state=a.state, z=a.z, m=a.m, a=rec[\"a_factual\"])\n"
        "                plans.append(AddressPlan(a, (Edit(Q, entry, rec[\"g_factual\"]),)))\n"
        "                continue\n"
        "            factual = QAddress(state=a.state, z=a.z, m=a.m, a=rec[\"a_factual\"])",
        f"{TESTS}::test_8b_dual_does_not_degenerate_into_its_factual_half",
    ),
    (
        "alternative_not_shared",
        "the envelope may carry any admissible action as a^+, so the patch arm and the Q "
        "arm can be measuring different alternatives (A76 §63.3)",
        CF,
        "        if rec.a_plus != alt:\n",
        "        if False:                   # MUTATED: a^+ unchecked\n",
        f"{TESTS}::test_5b_a_substituted_alternative_is_rejected",
        # The gate fails here by NOT RAISING, and that is the right shape: without the
        # comparison the record is accepted, and the law would write
        # Q(x_t, rec.a_plus) <- rec.g_cf -- a value belonging to one action stored at
        # another. The g_cf recomputation does not double as this check, because it
        # replays the SHARED adapter's a^+ and so agrees with the perturbed record's own
        # g_cf. An earlier version declared the a^+ message and was therefore a
        # WRONG_FAILURE_REASON: it asserted a rejection path the mutation had removed.
        "DID NOT RAISE",
    ),
    (
        "half_record_accepted",
        "a_plus and g_cf may be present separately, so 'the alternative is unknown' and "
        "'its return is unknown' become different envelope states",
        CF,
        "        if (rec.a_plus is None) != (rec.g_cf is None):\n",
        "        if False:                   # MUTATED: pair unchecked\n",
        f"{TESTS}::test_14_a_half_counterfactual_record_is_refused",
    ),
    (
        "implemented_tiers_untyped",
        "the build set is read with .name before it is typed, so a malformed descriptor "
        "crashes with an AttributeError instead of failing stop",
        TIER,
        "        unknown = sorted(repr(t) for t in self.implemented_tiers\n"
        "                         if type(t) is not Tier)\n",
        "        unknown = []                # MUTATED: type check removed\n",
        f"{TESTS}::test_16_an_implemented_tier_must_be_a_tier",
    ),
    (
        "intervention_added_not_replaced",
        "the factual episode's own do(d_t) is left in place next to the new one, so the "
        "replay's intervention set is malformed rather than a replacement",
        CF,
        "    members = tuple(iv for iv in episode.interventions.members\n"
        "                    if not (iv.kind == \"decision\" and iv.t == t))\n",
        "    members = tuple(episode.interventions.members)   # MUTATED: not replaced\n",
        f"{TESTS}::test_2_the_decision_intervention_is_replaced_not_added",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "l2_counterfactual_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = harness.check_nodes(MUTATIONS, ROOT)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID       ] {key:34} -> {node} ({why})")

    results, restored = harness.run_mutations(MUTATIONS, ROOT, (CF, LAWS, TIER))
    return harness.summarise("L2 counterfactual gate mutation self-check", MUTATIONS,
                             results, restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
