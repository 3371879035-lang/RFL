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
PRODUCER = SRC / "b2" / "producer.py"

#: (id, hole, path, old, new, pytest node id[, expected failure text])
MUTATIONS: tuple = (
    (
        "origin_check_removed",
        "evidence tagged as evaluator truth is admitted, so the view can be built from forbidden "
        "truth one step upstream of the metric",
        VIEW,
        "    if rollout.origin is not EvidenceOrigin.LEARNER_FUTURE_ROLLOUT:\n",
        "    if False:                            # MUTATED: origin check disabled\n",
        f"{TESTS}::test_5_only_the_learners_own_future_rollout_may_feed_the_view",
        "DID NOT RAISE",
    ),
    (
        "origin_type_check_removed",
        "a string that spells the right origin is accepted for the member itself -- and the guard "
        "then crashes formatting `origin.value`, so the promised PROTOCOL_ERROR is an "
        "AttributeError: the error path failing first",
        VIEW,
        "    if type(rollout.origin) is not EvidenceOrigin:\n",
        "    if False:                            # MUTATED: nominal origin type unchecked\n",
        f"{TESTS}::test_5_only_the_learners_own_future_rollout_may_feed_the_view",
        "has no attribute 'value'",
    ),
    (
        "rollout_seal_check_removed",
        "any object can be presented as a rollout that reports its own provenance -- the hole "
        "B2-2a closes by minting rather than by labelling",
        VIEW,
        "        if not is_sealed(self._seal):\n",
        "        if False:                        # MUTATED: self-reported provenance accepted\n",
        f"{TESTS}::test_3_the_rollout_is_sealed_and_the_view_is_one_future",
        "DID NOT RAISE",
    ),
    (
        "raw_value_accepted",
        "a bare value is admitted as a view field, which is how an already-computed truth-derived "
        "scalar enters while the metric imports nothing forbidden",
        VIEW,
        "            if type(field) is not FutureField:\n",
        "            if False:                    # MUTATED: bare values admitted\n",
        f"{TESTS}::test_6_the_fabricated_truth_feature_is_killed",
        "has no attribute 'name'",
    ),
    (
        "payload_not_rederived",
        "the payload is trusted instead of re-derived from its own rollout, so a clean shell can "
        "carry a forged, truth-derived value -- B2-1's most dangerous remaining route",
        VIEW,
        "            if tuple(field.value) != tuple(getattr(rollout, name)):\n",
        "            if False:                    # MUTATED: payload trusted\n",
        f"{TESTS}::test_6_the_fabricated_truth_feature_is_killed",
        "DID NOT RAISE",
    ),
    (
        "t_index_not_bound",
        "the ordinary time indices are supplied separately from the rollout, so they can be "
        "truth-derived while every field is clean",
        VIEW,
        "        if tuple(self.t_index) != tuple(rollout.t_index):\n",
        "        if False:                        # MUTATED: t_index unbound\n",
        f"{TESTS}::test_6_the_fabricated_truth_feature_is_killed",
        "DID NOT RAISE",
    ),
    (
        "mixed_rollouts_accepted",
        "fields from several different futures are assembled into one view, so 'what happened "
        "next' is no longer one horizon",
        VIEW,
        "        if len(rollouts) != 1:\n",
        "        if False:                        # MUTATED: several futures accepted\n",
        f"{TESTS}::test_3_the_rollout_is_sealed_and_the_view_is_one_future",
        "DID NOT RAISE",
    ),
    (
        "closed_fields_widened",
        "the field surface becomes a superset, so a fabricated feature rides along in the "
        "envelope the metric receives",
        VIEW,
        "        if keys != expected:\n",
        "        if not expected <= keys:             # MUTATED: superset accepted\n",
        f"{TESTS}::test_6_the_fabricated_truth_feature_is_killed",
        "DID NOT RAISE",
    ),
    (
        "builder_takes_any_callable",
        "the builder goes back to accepting an arbitrary callable, which can close over forbidden "
        "truth while the audited module's AST scan sees nothing -- the B2-1 hole itself",
        VIEW,
        "        if type(producer) is not FutureRolloutProducer:\n",
        "        if not callable(producer):       # MUTATED: an injected callable\n",
        f"{TESTS}::test_4_the_builder_consumes_the_audited_producer_not_a_callable",
        "DID NOT RAISE",
    ),
    (
        "environment_duck_typed",
        "any object with `future_records` is accepted as the environment, which is how an "
        "evaluator-supplied truth table arrives wearing the interface's method name",
        PRODUCER,
        "        if not isinstance(environment, LearnerEnvironment):\n",
        "        if False:                        # MUTATED: duck-typed environment\n",
        f"{TESTS}::test_4_the_builder_consumes_the_audited_producer_not_a_callable",
        "DID NOT RAISE",
    ),
    (
        "arm_parameter_added",
        "the builder can be told which arm it is in. A builder that CAN be told is one that may "
        "one day branch on it, which is why the gate reads the signature rather than the intent",
        VIEW,
        "    def build(self, state) -> FutureConsequenceView:\n",
        "    def build(self, state, arm=None) -> FutureConsequenceView:   # MUTATED\n",
        f"{TESTS}::test_8_arm_blind_by_interface_and_pre_update_by_absence",
        'assert params == ("state",)',
    ),
    (
        "update_metadata_added",
        "the view gains a ledger member, merging 'what was written' into 'what happened next'",
        VIEW,
        "    fields: Mapping\n    t_index: tuple\n",
        "    fields: Mapping\n    t_index: tuple\n    ledger: object = None       # MUTATED\n",
        f"{TESTS}::test_8_arm_blind_by_interface_and_pre_update_by_absence",
        "Extra items in the left set",
    ),
    (
        "import_allowlist_widened",
        "the module reaches a non-allowlisted (truth-bearing) import, which is the AST layer's "
        "job to refuse",
        VIEW,
        "from rfl_rebuild.learner.store import LearnerPersistentState\n",
        "from rfl_rebuild.learner.store import LearnerPersistentState\n"
        "from rfl_rebuild.method import credit                      # MUTATED\n",
        f"{TESTS}::test_7_the_ast_allowlist_layer_covers_the_chain_and_is_not_vacuous",
        "not on the allowlist",
    ),
    (
        "producer_reads_forbidden_truth",
        "the producer itself derives its records from forbidden truth and labels them as the "
        "learner's -- the mislabelled rollout, which no type can catch and which the audit of the "
        "PRODUCER module is therefore for",
        PRODUCER,
        "        records = self._environment.future_records(state)\n",
        "        records = self._environment.future_records(state)\n"
        "        _leak = Gamma_P_star                                   # MUTATED\n",
        f"{TESTS}::test_7_the_ast_allowlist_layer_covers_the_chain_and_is_not_vacuous",
        "forbidden dependency set",
    ),
    (
        "fixture_module_reachable",
        "a production module may import the test-only fixture mint, so production code can be "
        "built from the fixtures rather than the other way round",
        VIEW,
        "                if name.startswith(\"rfl_rebuild.b2.testing\"):\n",
        "                if False:                # MUTATED: fixture mint reachable\n",
        f"{TESTS}::test_7_the_ast_allowlist_layer_covers_the_chain_and_is_not_vacuous",
        "test-only fixture module",
    ),
    (
        "capability_imported_outside_owner",
        "another production module reaches for the mint itself. An allowlisted import is still an "
        "escalation when the name it brings is the ability to mint evidence: with the capability in "
        "hand, a truth-derived payload can be minted with a VALID seal, and no downstream layer can "
        "tell -- which is why the holder is one module and the audit enforces it",
        VIEW,
        "from rfl_rebuild.learner.store import LearnerPersistentState\n",
        "from rfl_rebuild.learner.store import LearnerPersistentState\n"
        "from rfl_rebuild.b2.producer import _mint_rollout          # MUTATED\n",
        f"{TESTS}::test_10_the_mint_capability_has_exactly_one_holder_in_the_production_graph",
        "mint capability",
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

    results, restored = harness.run_mutations(MUTATIONS, ROOT, (VIEW, PRODUCER))
    return harness.summarise("B2-1 view/builder gate mutation self-check", MUTATIONS, results,
                             restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
