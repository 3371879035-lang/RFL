r"""Mutation self-check for B2-1: the view, its builder, and their four gate layers.

$$\boxed{\text{a gate that passes is not evidence; it is evidence only that the gate did not
look}}$$

A75 §62.10 lists four layers — type boundary, AST/import allowlist, constructor-flow, mutation
power — and the fourth exists because the first three can all be present and **inert**. So each
layer is re-run against a deliberately reverted source tree, one mutation at a time, and the gate
that guards it must go **red**.

| # | hole | mutation |
|---|---|---|
| 1 | evidence from evaluator truth feeds the view | the origin comparison disabled |
| 2 | a value-equal *string* origin passes for the member | the nominal origin type check disabled |
| 3 | a bare value (a prefabricated scalar) is admitted as a field | the `FutureField` type check disabled |
| 4 | the field surface is a superset, so an extra feature rides along | `!=` -> `not <=` |
| 5 | the builder can be told which arm it is in | `build` gains a parameter |
| 6 | update metadata enters "what happened next" | the view gains a ledger member |
| 7 | the module reaches a non-allowlisted (truth-bearing) import | an import is added |

Mutation 3 is the fabricated-feature route and mutation 2 is the one the gates found while this
arrow was being written: formatting `origin.value` on a string raised `AttributeError` out of the
guard, where the contract promises a `PROTOCOL_ERROR`.

Usage::

    python scripts/b2_view_gate_selfcheck.py [--json PATH]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _mutation_harness as harness  # noqa: E402
SRC = ROOT / "src" / "rfl_rebuild"
TESTS = "tests/rebuild/test_b2_view.py"
VIEW = SRC / "b2" / "view.py"

#: (id, hole, path, old, new, pytest node id[, expected failure text])
MUTATIONS: tuple = (
    (
        "origin_check_removed",
        "evidence tagged as evaluator truth is admitted, so the view can be built from forbidden "
        "truth one step upstream of the metric",
        VIEW,
        "    if rollout.origin is not EvidenceOrigin.LEARNER_FUTURE_ROLLOUT:\n",
        "    if False:                            # MUTATED: origin check disabled\n",
        f"{TESTS}::test_3_only_the_learners_own_future_rollout_may_feed_the_view",
        "DID NOT RAISE",
    ),
    (
        "origin_type_check_removed",
        "a string that spells the right origin is accepted for the member itself -- and the guard "
        "then crashes formatting `origin.value`, so the promised PROTOCOL_ERROR is an "
        "AttributeError: the error path failing first, which the gates caught while this arrow "
        "was written",
        VIEW,
        "    if type(rollout.origin) is not EvidenceOrigin:\n",
        "    if False:                            # MUTATED: nominal origin type unchecked\n",
        f"{TESTS}::test_3_only_the_learners_own_future_rollout_may_feed_the_view",
        "has no attribute 'value'",
    ),
    (
        "raw_value_accepted",
        "a bare value is admitted as a view field, which is exactly how an already-computed "
        "truth-derived scalar enters while the metric imports nothing forbidden",
        VIEW,
        "            if type(field) is not FutureField:\n",
        "            if False:                    # MUTATED: bare values admitted\n",
        f"{TESTS}::test_5_the_fabricated_truth_feature_is_killed",
        # Measured, not guessed: with the nominal check gone, the NEXT guard dereferences the
        # bare value, so the run dies with `AttributeError: 'int' object has no attribute 'name'`
        # rather than the `DID NOT RAISE` I first declared. Same family as mutation 2 -- a guard
        # removed lets the following line crash where the contract promises a PROTOCOL_ERROR.
        "has no attribute 'name'",
    ),
    (
        "closed_fields_widened",
        "the field surface becomes a superset, so a fabricated feature rides along in the "
        "envelope the metric receives",
        VIEW,
        "        if keys != expected:\n",
        "        if not expected <= keys:             # MUTATED: superset accepted\n",
        f"{TESTS}::test_5_the_fabricated_truth_feature_is_killed",
        "DID NOT RAISE",
    ),
    (
        "arm_parameter_added",
        "the builder can be told which arm it is in. A builder that CAN be told is one that may "
        "one day branch on it, which is why the gate reads the signature rather than the intent",
        VIEW,
        "    def build(self, state) -> FutureConsequenceView:\n",
        "    def build(self, state, arm=None) -> FutureConsequenceView:   # MUTATED\n",
        f"{TESTS}::test_4_arm_blind_by_signature_and_pre_update_by_absence",
        'assert params == ("state",)',
    ),
    (
        "update_metadata_added",
        "the view gains a ledger member, merging 'what was written' into 'what happened next' -- "
        "the merge A75 62.10 forbids, because the first can then not be checked against the second",
        VIEW,
        "    fields: Mapping\n    t_index: tuple\n",
        "    fields: Mapping\n    t_index: tuple\n    ledger: object = None       # MUTATED\n",
        f"{TESTS}::test_4_arm_blind_by_signature_and_pre_update_by_absence",
        'assert members == {"fields", "t_index"}',
    ),
    (
        "import_allowlist_widened",
        "the module reaches a non-allowlisted import, which is the AST layer's job to refuse: the "
        "type boundary alone would not notice the dependency",
        VIEW,
        "from rfl_rebuild.learner.store import LearnerPersistentState\n",
        "from rfl_rebuild.learner.store import LearnerPersistentState\n"
        "from rfl_rebuild.method import credit                      # MUTATED\n",
        f"{TESTS}::test_6_the_ast_allowlist_layer_is_not_vacuous",
        "not on the allowlist",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "b2_view_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = harness.check_nodes(MUTATIONS, ROOT)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID       ] {key:34} -> {node} ({why})")

    results, restored = harness.run_mutations(MUTATIONS, ROOT, (VIEW,))
    return harness.summarise("B2-1 view/builder gate mutation self-check", MUTATIONS, results,
                             restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
