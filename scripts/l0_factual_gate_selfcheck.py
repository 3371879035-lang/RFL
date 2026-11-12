r"""Mutation self-check for the $D_Q\times L_0$ gates (A77 §65.6, §65.8, §65.10).

$$\boxed{\text{a gate that passes is not evidence; it is evidence only that the gate
did not look}}$$

The L0 gates were authored alongside their implementation, so on their own they have not
been shown to fail on anything. Each is re-run against a deliberately reverted source tree
and must go **red**, with the failure reason the mutation declares where one is declared.

| # | hole | mutation | gate that must catch it |
|---|---|---|---|
| 1 | the fold is reordered | the reverse recurrence replaced by ``math.fsum`` | `test_3` |
| 2 | the validator compares with a tolerance instead of bit patterns | ``hex() != hex()`` weakened to ``abs(...) > 1e-9`` | `test_3b` |
| 3 | a created entry is measured against zero | $\\lvert q_{\\text{post}} - Q_D^\\ast\\rvert$ becomes $\\lvert q_{\\text{post}}\\rvert$ | `test_6` |
| 4 | the scalar accounting is skipped entirely | the scalar branch disabled | `test_5` |
| 5 | the healthy write stops canonicalising | Q identity canonicalisation disabled | `test_4` |
| 6 | a law/slice mismatch crashes instead of failing stop | the plan-call guard disabled | `test_2c` |
| 7 | the ledger sum depends on address order | sorted `fsum` replaced by sequential accumulation | `test_8` |
| 8 | the reference boundary differs by arm | the uniform reference check disabled | `test_9` |

Mutation 5 targets the same fix as the Q self-check's `q_identity_canonicalisation`, but
gates a different property: there it is the store's canonical form, here it is L0's
scientific claim that a healthy factual target is a genuine no-op.

Usage::

    python scripts/l0_factual_gate_selfcheck.py [--json PATH]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import _mutation_harness as harness  # noqa: E402

SRC = ROOT / "src" / "rfl_rebuild"
FACTUAL = SRC / "b1" / "factual.py"
RUNNER = SRC / "b1" / "runner.py"
STORE = SRC / "learner" / "store.py"
TESTS = "tests/rebuild/test_l0_factual_return.py"

MUTATIONS: tuple = (
    (
        "fold_reordered",
        "the reverse Bellman fold is replaced by math.fsum, which is the more accurate "
        "summation and disagrees with the DP on 92 of 278 healthy addresses",
        FACTUAL,
        "    g = 0.0\n"
        "    for j in range(len(rows) - 1, t - 1, -1):\n"
        "        g = rows[j][_REWARD] + g\n"
        "    return g",
        "    return math.fsum(row[_REWARD] for row in rows[t:])   # MUTATED",
        f"{TESTS}::test_3_the_healthy_support_is_bit_exact_278_of_278",
    ),
    (
        "validator_tolerance",
        "the construction-path comparison is weakened to a tolerance, so a target that "
        "merely rounds to the reference is accepted and the write lands next to it",
        FACTUAL,
        "        if float(rec.g_factual).hex() != float(expected.g_factual).hex():",
        "        if abs(float(rec.g_factual) - float(expected.g_factual)) > 1e-9:  # MUTATED",
        f"{TESTS}::test_3b_a_reordered_fold_is_rejected_even_though_the_numbers_are_close",
    ),
    (
        "accounting_against_zero",
        "a created entry's delta is measured against zero instead of the effective Q, so "
        "a nearly-reference-valued write reads as a huge edit",
        RUNNER,
        "                delta = abs(float(now) - float(q_reference.value(e.address)))",
        "                delta = abs(float(now))     # MUTATED: zero baseline",
        f"{TESTS}::test_6_a_created_entry_is_measured_against_the_reference_not_against_zero",
    ),
    (
        "scalar_accounting_disabled",
        "the scalar ledger is left at its defaults, so a scene that wrote an override "
        "reports no scalars at all",
        RUNNER,
        "    if spec.scalar:\n"
        "        n_scalar, total_delta, largest_delta = _scalar_accounting(\n"
        "            plan, pre_view, post_view, q_reference)",
        "    if False:                       # MUTATED: accounting skipped\n"
        "        n_scalar, total_delta, largest_delta = _scalar_accounting(\n"
        "            plan, pre_view, post_view, q_reference)",
        f"{TESTS}::test_5_a_faulted_target_produces_exactly_one_non_oracle_override",
    ),
    (
        "healthy_write_persists",
        "an override equal to the reference is stored rather than deleted, so every "
        "healthy scene carries a minimal override and stops being healthy",
        STORE,
        "                if e.value is None or float(e.value) == q_reference.value(e.address):",
        "                if e.value is None:            # MUTATED: canonicalisation off",
        f"{TESTS}::test_4_a_healthy_write_leaves_the_store_empty",
    ),
    (
        "accounting_order_dependent",
        "the changed entries are accumulated in plan order with a sequential float sum, "
        "so the ledger bytes depend on the order the addresses were credited in",
        RUNNER,
        "    changed.sort(key=lambda pair: pair[0])\n"
        "    deltas = [d for _key, d in changed]\n"
        "    return len(deltas), math.fsum(deltas), max(deltas, default=0.0)",
        "    total = 0.0\n"
        "    largest = 0.0\n"
        "    for _key, d in changed:      # MUTATED: plan order, sequential sum\n"
        "        total += d\n"
        "        largest = max(largest, d)\n"
        "    return len(changed), total, largest",
        f"{TESTS}::test_8_the_ledger_canonical_is_independent_of_address_order",
    ),
    (
        "reference_boundary_arm_specific",
        "the reference-typing check is skipped, so a mutable fake completes on the "
        "NoWrite reference arm while the treatment arm still fail-stops",
        RUNNER,
        "    if spec.scalar:\n"
        "        try:\n"
        "            require_q_reference(q_reference)\n"
        "        except ReferenceContractError as exc:",
        "    if False:                       # MUTATED: boundary unchecked\n"
        "        try:\n"
        "            require_q_reference(q_reference)\n"
        "        except ReferenceContractError as exc:",
        f"{TESTS}::test_9_the_reference_boundary_is_the_same_for_every_arm",
    ),
    (
        "plan_call_unwrapped",
        "a law run on a slice whose cell does not deliver the fields it reads crashes "
        "with a bare TypeError instead of failing stop",
        RUNNER,
        "    except (TypeError, KeyError, AttributeError, IndexError) as exc:",
        "    except () as exc:               # MUTATED: nothing is converted",
        f"{TESTS}::test_2c_a_scalar_slice_cannot_be_run_through_the_patch_entry_point",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(ROOT / "experiments" / "v03r"
                                         / "l0_factual_gate_selfcheck.json"))
    args = ap.parse_args()

    stale = harness.check_nodes(MUTATIONS, ROOT)
    for key, node, why in stale:
        print(f"[STALE_NODE_ID       ] {key:34} -> {node} ({why})")

    results, restored = harness.run_mutations(MUTATIONS, ROOT,
                                             (FACTUAL, RUNNER, STORE))
    return harness.summarise("L0 factual-return gate mutation self-check", MUTATIONS,
                             results, restored, stale, ROOT, pathlib.Path(args.json))


if __name__ == "__main__":
    raise SystemExit(main())
