r"""Mutation self-check for the $F_0$ §7 harness: the authorisation gate, the seed sets, and the surface.

$$\boxed{\text{a refusal gate is evidence only if the thing it refuses would otherwise run}}$$

`tests/rebuild/test_b2_devstage.py` asserts that an empty `currently_authorises` refuses every stage and
that a manifest naming the stage lets it through. Both halves matter, and both are reverted here one at a
time: a guard whose removal changes nothing was never a guard, and a "refusal" that survives the removal
of the token comparison is a script that always says no.

Each mutation is applied to the working tree, its own pytest node must go **red with the expected
message**, and the tree must come back byte-identical.

Usage::

    python scripts/b2_run_gate_selfcheck.py [--json PATH]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _mutation_harness as harness  # noqa: E402

DEVSTAGE = ROOT / "src" / "rfl_rebuild" / "b2" / "devstage.py"
RUN_SMOKE = ROOT / "scripts" / "run_smoke.py"
TESTS = "tests/rebuild/test_b2_devstage.py"

#: (key, hole, file, old, new, pytest node, expected failure text)
MUTATIONS = (
    (
        "authorisation_token_ignored",
        "the token comparison is disabled, so every stage runs whatever the manifest says -- the boundary "
        "becomes a comment",
        DEVSTAGE,
        '    if token not in state["currently_authorises"]:',
        "    if False:  # MUTATED",
        f"{TESTS}::test_8_a_manifest_naming_the_stage_lets_it_through",
        "DID NOT RAISE",
    ),
    (
        "probe_manifest_accepted_as_evidence",
        "a manifest stamped MUTATION-PROBE is read as evidence, so a self-check's throwaway output could "
        "authorise a stage",
        DEVSTAGE,
        '    if status.startswith("MUTATION-PROBE"):',
        "    if False:  # MUTATED",
        f"{TESTS}::test_9_a_mutation_probe_manifest_authorises_nothing",
        "DID NOT RAISE",
    ),
    (
        "authorises_more_than_validity_grants",
        "the subset check is dropped, so a manifest may authorise a stage its own validity grant never "
        "covered",
        DEVSTAGE,
        "    if stray:",
        "    if False:  # MUTATED",
        f"{TESTS}::test_10_a_manifest_may_not_authorise_beyond_its_validity_grant",
        "DID NOT RAISE",
    ),
    (
        "seed_set_size_unchecked",
        "a seed set of the wrong size is accepted, so a truncated file would silently run a different "
        "stage while every other check still passed",
        DEVSTAGE,
        "        if len(seeds) != expected:",
        "        if False:  # MUTATED",
        f"{TESTS}::test_5_a_set_of_the_wrong_size_is_refused_rather_than_truncated",
        "DID NOT RAISE",
    ),
    (
        "seed_sets_may_overlap",
        "the disjointness check is dropped, so smoke could burn development streams",
        DEVSTAGE,
        "    if overlap:",
        "    if False:  # MUTATED",
        f"{TESTS}::test_6_overlapping_sets_are_refused",
        "DID NOT RAISE",
    ),
    (
        "duplicate_seed_accepted",
        "a duplicated seed is accepted, so one stream would be counted twice as two statistical units",
        DEVSTAGE,
        "    if len(set(seeds)) != len(seeds):",
        "    if False:  # MUTATED",
        f"{TESTS}::test_2_a_duplicate_seed_is_refused",
        "DID NOT RAISE",
    ),
    (
        "smoke_surface_guard_dropped",
        "the smoke surface assertion is removed, so an efficacy field could be added to the artifact "
        "without any gate noticing",
        DEVSTAGE,
        "    if set(report) != SMOKE_REPORT_FIELDS:",
        "    if False:  # MUTATED",
        f"{TESTS}::test_16_the_surface_guard_goes_red_when_the_field_set_drifts",
        "DID NOT RAISE",
    ),
    (
        "benchmark_reads_a_seed_set",
        "the benchmark claims to be seedless while reading a seed set, which would make 'the bound was "
        "measured without drawing a seed' false",
        DEVSTAGE,
        "    scenes = scene_domain()\n    if not 0 < n <= len(scenes):",
        "    scenes = scene_domain()\n    load_seed_set(smoke_seeds_file())  # MUTATED\n"
        "    if not 0 < n <= len(scenes):",
        f"{TESTS}::test_17_the_benchmark_draws_no_seed",
        "the benchmark read a seed set",
    ),
    (
        "plan_claims_to_have_run",
        "the plan reports that it ran episodes, which is the report a reviewer reads when deciding "
        "whether a stage touched a seed",
        DEVSTAGE,
        '        "runs_episodes": False,',
        '        "runs_episodes": True,  # MUTATED',
        f"{TESTS}::test_20_the_plan_never_claims_to_have_run_anything",
        "assert (True is False)",
    ),
    (
        "cli_swallows_its_refusal",
        "the smoke CLI exits 0 after refusing, so a refused run would look like a successful one to any "
        "caller that only checks the exit code",
        RUN_SMOKE,
        "        print(f\"REFUSED: {exc}\", file=sys.stderr)\n        return 2",
        "        print(f\"REFUSED: {exc}\", file=sys.stderr)\n        return 0  # MUTATED",
        f"{TESTS}::test_14_every_cli_refuses_to_run_but_exits_zero_for_plan",
        "run_smoke.py",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "b2_run_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = harness.check_nodes(MUTATIONS, ROOT)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID       ] {key:34} -> {node} ({why})")

    results, restored = harness.run_mutations(MUTATIONS, ROOT, (DEVSTAGE, RUN_SMOKE))
    return harness.summarise("F0 section 7 harness: authorisation, seed sets, smoke surface",
                             MUTATIONS, results, restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
