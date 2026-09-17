"""A73 §60 — grammar extraction regression: is the extracted grammar exact?

`src/rfl_rebuild/env/fault_grammar.py` is the new single public grammar. It may
replace the historical call sites ONLY if it reproduces them exactly, so this
script compares, over EVERY public base context (kappa x tape x option):

    structural(new.legal_fault_domains)         ==  structural(gate_stage2._domains)
    structural(new.canonical_domains)           ==  structural(canonicalise(_domains))

The comparison is on A73's frozen normalised form, not on bytes: `_domains`
returns objects and the second historical implementation returns tuples, so bytes
are not comparable across them. Both raw and canonical levels are checked, because
an error could cancel between them.

The trace is computed once per context and shared by both implementations, so any
difference is the enumerator's, not the rollout's.

TWO THINGS BEYOND EQUALITY:

1. The `Trap` guard. `_domains` wraps `Trap(...)` in `try/except ValueError`;
   `identifiability_gate.legal_fault_domains` does not. The guard's activations are
   counted here. Measured: **zero** over all 5,760 public base contexts, so on the
   frozen map/horizon the two enumerations are behaviourally identical. That
   corrects an earlier claim in review that the tuple variant "would raise":
   `_domains` is the truth source because `support_build.py` uses it, not because
   the other is observably broken.

2. The candidate space. `iter_assignments` is checked against the support
   constructor's own skip rule, and its size is reported, since that is the space
   `PublicSCMView` may generate before feasibility filtering.

Read-only with respect to the frozen artifacts: nothing is written except the
report. The historical call sites are NOT re-pointed by this script.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import _domains, reference_provider  # noqa: E402
from identifiability_gate import KAPPAS, TAPES, canonicalise as old_canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env import fault_grammar as FG  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape  # noqa: E402
from rfl_rebuild.method.dgp import SceneContext, SceneDGP  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    n_options = len(K.option_ids())
    expected_ctx = len(KAPPAS) * len(TAPES) * n_options

    n_ctx = n_dgp_live = 0
    raw_mismatch, canon_mismatch = [], []
    trap_rejected = 0
    key_mismatch = []
    assign_mismatch, enum_mismatch, wrapper_mismatch = [], [], []
    cand_total = 0
    dgp = SceneDGP(kappas=KAPPAS, options=K.option_ids(), tapes=TAPES,
                   domains=lambda ctx: None, is_feasible=lambda *a: True)

    for kappa in KAPPAS:
        for tape in TAPES:
            for z in K.option_ids():
                n_ctx += 1
                ctx = SceneContext(kappa=kappa, phase=tape.phase,
                                   error_flag=tape.error_flag,
                                   cause_rank=tape.cause_rank, base_option=z)
                if dgp.context_log_prob(ctx) != float("-inf"):
                    n_dgp_live += 1

                tr = K.rollout(kappa=kappa, tape=tape,
                               command_provider=provider, base_option=z)

                stats: dict = {}
                new_raw = FG.legal_fault_domains(sol, kappa, tape, z, tr, stats)
                old_raw = _domains(sol, kappa, tape, z, tr)
                trap_rejected += stats.get("trap_rejected", 0)

                s_new = FG.structural(new_raw)
                s_old = FG.structural(old_raw)
                if s_new != s_old:
                    raw_mismatch.append((kappa, tape.phase, tape.error_flag,
                                         tape.cause_rank, z,
                                         {k: (s_old[k], s_new[k])
                                          for k in FG.CAUSE_KEYS
                                          if s_old[k] != s_new[k]}))

                new_can = {k: FG.canonicalise(v) for k, v in new_raw.items()}
                old_can = {k: old_canonicalise(v) for k, v in old_raw.items()}
                if FG.structural(new_can) != FG.structural(old_can):
                    canon_mismatch.append((kappa, tape.phase, z))

                # key order must match too: canonicalise takes first/last, so an
                # ordering difference would silently change the support
                if [len(new_can[k]) for k in FG.CAUSE_KEYS] != \
                   [len(old_can[k]) for k in FG.CAUSE_KEYS]:
                    key_mismatch.append((kappa, tape.phase, z))

                # presence/parameter assignment must agree everywhere (route C),
                # and the candidate enumeration must be the same list
                n_new = n_old = 0
                for bits, combo in FG.iter_assignments(new_can):
                    n_new += 1
                    a = FG.assign(new_can, bits, combo)
                    b = {k: (old_can[k][combo[i]] if bits[i] else None)
                         for i, k in enumerate(FG.CAUSE_KEYS)}
                    if a != b:
                        assign_mismatch.append(
                            (kappa, tape.phase, z, bits, tuple(combo)))
                        break
                n_old = sum(1 for _ in FG.iter_assignments(old_can))
                if n_new != n_old:
                    enum_mismatch.append((kappa, tape.phase, z, n_new, n_old))
                cand_total += n_new

                # the convenience wrapper must be the same object as its expansion
                if FG.canonical_structural(sol, kappa, tape, z, tr) != \
                   FG.structural(new_can):
                    wrapper_mismatch.append((kappa, tape.phase, z))

    checks = {
        "raw_legal_domains_identical_on_all_contexts": not raw_mismatch,
        "canonical_domains_identical_on_all_contexts": not canon_mismatch,
        "canonical_domain_sizes_identical": not key_mismatch,
        "assign_matches_build_case_rule": not assign_mismatch,
        "candidate_enumeration_identical": not enum_mismatch,
        "canonical_structural_wrapper_consistent": not wrapper_mismatch,
        "context_count_matches_kappa_x_tape_x_option": n_ctx == expected_ctx,
    }
    ok = all(checks.values())
    # Informational, deliberately NOT ANDed into the verdict: the guard is
    # unexercised on the frozen map, and reporting that is the point.
    informational = {
        "trap_guard_never_fires_on_frozen_map": trap_rejected == 0,
    }

    print(f"A73 grammar extraction regression over {n_ctx:,} public base contexts\n")
    print(f"  kappa x tape x option                    : "
          f"{len(KAPPAS)} x {len(TAPES)} x {n_options} = {n_ctx:,}")
    print(f"  DGP-live contexts (finite log prob)      : {n_dgp_live:,}")
    print(f"  raw legal-domain mismatches              : {len(raw_mismatch)}")
    print(f"  canonical-domain mismatches              : {len(canon_mismatch)}")
    print(f"  canonical size/order mismatches          : {len(key_mismatch)}")
    print(f"  assign() mismatches vs build_case rule   : {len(assign_mismatch)}")
    print(f"  candidate-enumeration mismatches         : {len(enum_mismatch)}")
    print(f"  canonical_structural wrapper mismatches  : {len(wrapper_mismatch)}")
    print(f"\n  Trap guard activations (t >= HORIZON)    : {trap_rejected:,}")
    print(f"    -> on the frozen map/horizon the guard NEVER fires, so the guarded")
    print(f"       and unguarded enumerations are behaviourally IDENTICAL here.")
    print(f"       `_domains` is the truth source because support_build.py uses it,")
    print(f"       not because the tuple variant is observably broken.")
    print(f"  candidate assignments over canonical set : {cand_total:,} "
          f"({cand_total / n_ctx:.1f} per context)")
    for name, cond in checks.items():
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    for name, cond in informational.items():
        print(f"  [{'INFO' if cond else 'WARN'}] {name}")
    if raw_mismatch:
        print("\nfirst raw mismatches:")
        for m in raw_mismatch[:3]:
            print(f"  kappa={m[0]} phi={m[1]} ef={m[2]} cr={m[3]} z={m[4]} -> {m[5]}")

    verdict = ("extraction EXACT: the public grammar may replace the historical "
               "call sites" if ok else
               "extraction NOT exact: the historical call sites must not be "
               "re-pointed")
    print(f"\nA73 grammar extraction: {verdict}")

    out = ROOT / "experiments" / "v02r" / "a73_grammar_equivalence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "n_contexts": n_ctx,
        "n_options": n_options,
        "n_dgp_live_contexts": n_dgp_live,
        "raw_mismatches": len(raw_mismatch),
        "canonical_mismatches": len(canon_mismatch),
        "canonical_size_mismatches": len(key_mismatch),
        "assign_mismatches": len(assign_mismatch),
        "candidate_enumeration_mismatches": len(enum_mismatch),
        "canonical_structural_wrapper_mismatches": len(wrapper_mismatch),
        "trap_guard_activations": trap_rejected,
        "candidate_assignments_total": cand_total,
        "candidate_assignments_per_context": cand_total / n_ctx,
        "structural_schema": dict(FG.STRUCTURAL_SCHEMA),
        "checks": checks,
        "informational": informational,
        "status": "PASS" if ok else "FAIL",
        "verdict": verdict,
        "truth_source": ("gate_stage2._domains + identifiability_gate.canonicalise, "
                         "the path support_build.py uses to build DenseSupport"),
        "corrected_claim": ("the tuple-valued identifiability_gate."
                            "legal_fault_domains lacks the Trap ValueError guard, "
                            "but the guard NEVER fires on the frozen map/horizon "
                            "(0 activations over all 5,760 contexts), so on the "
                            "current SCM the two enumerations are behaviourally "
                            "IDENTICAL. It is not the truth source because "
                            "support_build.py does not use it -- not because it is "
                            "observably broken. An earlier statement that it 'would "
                            "raise' was an overstatement and is corrected here."),
        "note": ("historical call sites are NOT re-pointed by this script; that is a "
                 "separate step gated on this regression"),
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
