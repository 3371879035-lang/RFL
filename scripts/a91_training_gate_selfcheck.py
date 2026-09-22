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
RUNNER = ROOT / "src" / "rfl_rebuild" / "b2" / "runner.py"
TESTS = "tests/rebuild/test_b2_training.py"
RUNNER_TESTS = "tests/rebuild/test_b2_runner.py"

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
    (
        "future_training_mutates_collateral_state",
        "the future trains the arm's own post-B1 state instead of a clone, so the collateral measures a "
        "trained learner while A85 73.2.2 fixes V_unaffected,post as the immediate post-update state -- "
        "and the defect is invisible in the future dimension itself",
        RUNNER,
        "            future_state = post_states[arm.name].clone()",
        "            future_state = post_states[arm.name]  # MUTATED",
        f"{RUNNER_TESTS}::test_5b_the_collateral_measures_the_immediate_post_b1_state",
        "measures $V_{unaffected,post}$ on the immediate post-B1 state",
    ),
    (
        "remeasure_v_pre_per_arm",
        "the production curve re-measures V_pre instead of using the locked shared value, so two arms "
        "consume two measurements that happen to agree -- which A85 73.1 exists to forbid",
        TRAINING,
        "                 pre_level=protocol.v_pre, t_max=protocol.t_max)",
        "                 pre_level=pre_level(protocol.evaluation_sample, q_reference=q_reference),\n"
        "                 t_max=protocol.t_max)  # MUTATED",
        f"{TESTS}::test_23_the_curve_uses_the_locked_v_pre_and_never_re_measures_it",
        "re-measured V_pre",
    ),
    (
        "second_arm_uses_different_training_seed",
        "the second arm is handed a training protocol with a different seed, so the arms no longer draw "
        "one keyed episode stream and the contrast stops being paired -- the real CRN boundary that the "
        "old single-episode exogenous setup no longer guarded",
        RUNNER,
        "            protocol = self._training\n",
        "            protocol = (self._training if arm.name == arms[0].name else\n"
        "                        FutureTrainingProtocol(seed=self._training.seed + 1,\n"
        "                                               alpha=self._training.alpha,\n"
        "                                               epsilon=self._training.epsilon,\n"
        "                                               t_max=self._training.t_max,\n"
        "                                               grid=self._training.grid,\n"
        "                                               evaluation_sample=self._training.evaluation_sample,\n"
        "                                               v_pre=self._training.v_pre))  # MUTATED\n",
        f"{RUNNER_TESTS}::test_5_the_paired_futures_share_one_training_stream",
        "did not consume one shared training protocol",
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

    results, restored = harness.run_mutations(MUTATIONS, ROOT, (TRAINING, RUNNER))
    return harness.summarise("A91 training-time instrument: pre-step context, in-force option, uniform draw, "
                             "collateral state, locked V_pre, shared stream",
                             MUTATIONS, results, restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
