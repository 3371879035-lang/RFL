r"""Mutation self-check for the A91 §79 training-time instrument.

$$\boxed{\text{a gate that cannot go red is not evidence that the rule it guards is implemented}}$$

A91 froze three implementation-determining rules that a working implementation can get wrong while every
other test stays green, so each is reverted here one at a time and its own test must go red:

1. `use_post_state_as_current_q_address` --- a `StepResult` carries the *post*-step state and control, so a
   walk that reads them as the current context shifts every update one step right;
2. `use_proposal_as_initial_in_force` --- the episode starts in the option the learner's process commit put
   in force, not in the proposal; the test that kills this runs against a real $Z_P^{\text{fire}} = 1$
   fixture (`trace.option_in_force != trace.base_option`), because on a healthy learner the two coincide
   and the assertion would be vacuous;
3. `uniform_action_by_flooring_a_real` --- the exploration index is an exactly uniform draw by keyed
   rejection, not the floor of a scaled 64-bit integer, which is biased whenever $n \nmid 2^{64}$.

Usage::

    python scripts/a91_training_gate_selfcheck.py [--json PATH]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _mutation_harness as harness  # noqa: E402

TRAINING = ROOT / "src" / "rfl_rebuild" / "b2" / "training.py"
TESTS = "tests/rebuild/test_b2_training.py"

MUTATIONS = (
    (
        "use_post_state_as_current_q_address",
        "the walk yields the step's own post-step state and control as the context it acted from, so the "
        "Q update is computed at s_{j+1} and every update moves one step to the right -- legal code, wrong "
        "scientific object",
        TRAINING,
        "        out.append((state, control, result))",
        "        out.append((result.state, result.control, result))  # MUTATED",
        f"{TESTS}::test_11_the_walk_reconstructs_the_pre_step_context",
        "the walk must start at the episode's initial context",
    ),
    (
        "use_proposal_as_initial_in_force",
        "the episode's initial control is built from the proposal option instead of the one in force, so "
        "under a P-architecture write every step-0 Q update is written against an option the learner never "
        "had -- invisible on healthy learners, which is why the fixture must fire Z_P",
        TRAINING,
        "    control = initial_control(trace.option_in_force)",
        "    control = initial_control(trace.base_option)  # MUTATED",
        f"{TESTS}::test_12_the_fixture_really_fires_z_p_and_the_walk_follows_the_in_force_option",
        "the walk must start in the option in force",
    ),
    (
        "uniform_action_by_flooring_a_real",
        "the exploration index is the floor of a scaled 64-bit draw instead of a rejection draw, which is "
        "biased whenever n does not divide 2**64 -- the bias the frozen rule exists to remove",
        TRAINING,
        "        if r < limit:\n            return ordered[r % n]",
        "        return ordered[(r * n) >> 64]  # MUTATED",
        f"{TESTS}::test_10_uniform_action_has_exact_pre_images_and_uses_rejection",
        "the index draw is not balanced",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "a91_training_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = harness.check_nodes(MUTATIONS, ROOT)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID       ] {key:34} -> {node} ({why})")

    results, restored = harness.run_mutations(MUTATIONS, ROOT, (TRAINING,))
    return harness.summarise("A91 training-time instrument: pre-step context, in-force option, uniform draw",
                             MUTATIONS, results, restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
