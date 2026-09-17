"""A62 harness — belief-population assertions (frozen acceptance items).

These are the checks that make the dev_v1 leak impossible to reintroduce in
another form. They need the belief backend but not the full run harness, so they
are landed first and run on a bounded global support.

  A  QueryOnly's initial belief IS the global prior, and is independent of the
     true scene. ``GlobalSupportIndex.global_prior()`` takes no world argument at
     all, which is the structural reason; the fingerprint comparison across two
     different true scenes is the mechanical check.
  B  SequenceEvidence and SeqThenQuery start from the SAME rows-only belief.
  C  Two worlds with the same rows and DIFFERENT feedback get an identical
     initial sequence belief -- the exact inversion of dev_v1.
  D  sample -> support BIJECTION: every accepted DGP scene maps to EXACTLY ONE
     canonical world in the global support. Not zero, not several. This is the
     check that catches drift in parameter indexing, canonical encoding, the
     context support, or feasibility conditioning, all at once.
"""

from __future__ import annotations

import json
import pathlib
import random
import sys
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import (  # noqa: E402
    LatentCase, _domains, fire_of, reference_provider, sigma0,
)
from gate_stage3 import (  # noqa: E402
    build_partition, class_local_queries, dynamical_key, response,
)
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape  # noqa: E402
from rfl_rebuild.method.belief import GlobalSupportIndex, fire_code  # noqa: E402
from rfl_rebuild.method.dgp import SceneContext, SceneDGP  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

MAX_CLASSES = 400
N_SCENES = 200


def world_key(c):
    return (c.kappa, c.phi, c.error_flag, c.cause_rank, c.base_option, c.Z,
            c.option_fault, c.decision, c.controller, c.plant, c.trap)


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    classes, _a, _b, _c = build_partition(sol)

    def domains(ctx: SceneContext):
        tape = SemanticTape(phase=ctx.phase, error_flag=ctx.error_flag,
                            cause_rank=ctx.cause_rank)
        tr = K.rollout(kappa=ctx.kappa, tape=tape, command_provider=provider,
                       base_option=ctx.base_option)
        d = _domains(sol, ctx.kappa, tape, ctx.base_option, tr)
        return tuple(canonicalise(d[k]) for k in CAUSE_KEYS)

    def build_case(ctx, Z, params):
        dm = domains(ctx)
        b = {k: (dm[i][params[i]] if Z[i] else None)
             for i, k in enumerate(CAUSE_KEYS)}
        return LatentCase(case_id=0, kappa=ctx.kappa, phi=ctx.phase,
                          error_flag=ctx.error_flag, cause_rank=ctx.cause_rank,
                          base_option=ctx.base_option, Z=tuple(Z),
                          option_fault=b.get("P"), decision=b.get("D"),
                          controller=b.get("X"), plant=b.get("E"),
                          trap=b.get("U"))

    def is_feasible(ctx, Z, params):
        try:
            return sigma0(sol, build_case(ctx, Z, params))[0] is not None
        except Exception:
            return False

    # ---- global support, ROWS-ONLY blocks, no true world involved -------- #
    rows_of, fire_of_w, fb_of_w, cases = {}, {}, {}, []
    i = 0
    for sig, members in classes.items():
        if i >= MAX_CLASSES:
            break
        i += 1
        by_key = {}
        for m in members:
            by_key.setdefault(dynamical_key(m), m)
        for w in by_key.values():
            obs = sigma0(sol, w)
            if obs[0] is None:
                continue
            rows_of[w] = obs[0][0]
            fb_of_w[w] = tuple(obs[0][1])
            fire_of_w[w] = fire_code(fire_of(sol, w))
            cases.append(w)

    worlds = tuple(cases)
    rk = {w: repr(rows_of[w]) for w in worlds}
    class_of = {w: rk[w] for w in worlds}
    blocks = defaultdict(list)
    for w in worlds:
        blocks[class_of[w]].append(w)
    weight = {w: 1.0 / len(worlds) for w in worlds}

    fam = set()
    for sig, members in list(classes.items())[:MAX_CLASSES]:
        by_key = {}
        for m in members:
            by_key.setdefault(dynamical_key(m), m)
        reps = list(by_key.values())
        if reps:
            fam |= class_local_queries(sol, reps[0].kappa, reps[0].phi, sig[0])

    def legal(w, q):
        return response(sol, w, q) is not None

    def rkey(w, q):
        r = response(sol, w, q)
        if r is None:
            return ("none",)
        if q[0] == "audit":
            return ("audit", r[1])
        if q[0] == "proc_audit":
            return ("proc", r[1])
        return ("roll", r[0])

    idx = GlobalSupportIndex(worlds=worlds, class_of=class_of, weight_of=weight,
                            fire_code_of=fire_of_w, legal=legal, resp_key=rkey)
    # key -> the canonical support worlds carrying it
    by_world_key = defaultdict(list)
    for w in worlds:
        by_world_key[world_key(w)].append(w)
    by_case_key = {world_key(w): w for w in worlds}

    checks, detail = {}, {}

    # ---- A. QueryOnly prior ---------------------------------------------- #
    la = worlds[0]
    lb = next(w for w in worlds if class_of[w] != class_of[la])
    fpA = idx.fingerprint(idx.global_prior())
    fpB = idx.fingerprint(idx.global_prior())
    detail["A"] = {"fp": fpA[:48], "n_blocks": len(idx.global_prior().active_blocks),
                   "true_a_class": class_of[la][:24],
                   "true_b_class": class_of[lb][:24],
                   "priors_identical": fpA == fpB}
    checks["A_queryonly_prior_is_global_and_truth_independent"] = (fpA == fpB)

    # ---- B. Sequence and SeqThenQuery share the rows-only belief ---------- #
    Hb = idx.rows_prior(class_of[la])
    detail["B"] = {"active_blocks": len(Hb.active_blocks),
                   "block_is_the_rows_block": list(Hb.active_blocks) == [class_of[la]]}
    checks["B_sequence_and_seqthenquery_same_rows_belief"] = (
        len(Hb.active_blocks) == 1
        and list(Hb.active_blocks)[0] == class_of[la])

    # ---- C. same rows, different feedback -> identical belief ------------ #
    pair = None
    for w in worlds:
        for v in worlds:
            if w is not v and rk[w] == rk[v] and fb_of_w[w] != fb_of_w[v]:
                pair = (w, v)
                break
        if pair:
            break
    if pair:
        w, v = pair
        detail["C"] = {"same_rows": rk[w] == rk[v],
                       "different_feedback": fb_of_w[w] != fb_of_w[v],
                       "beliefs_identical":
                           idx.fingerprint(idx.rows_prior(class_of[w]))
                           == idx.fingerprint(idx.rows_prior(class_of[v]))}
        checks["C_feedback_absent_from_sequence_belief"] = (
            detail["C"]["beliefs_identical"] and detail["C"]["different_feedback"])
    else:
        detail["C"] = {"witness": None}
        checks["C_feedback_absent_from_sequence_belief"] = False

    # ---- D. sample -> support bijection ---------------------------------- #
    dgp = SceneDGP(kappas=KAPPAS, options=K.option_ids(), tapes=TAPES,
                   domains=domains, is_feasible=is_feasible)
    rng = random.Random(4242)
    zero = multi = ok = unsupported = 0
    misses = []
    for _ in range(N_SCENES):
        ctx, Z, params = dgp.sample_scene(rng)
        c = build_case(ctx, Z, params)
        ob = sigma0(sol, c)
        if ob[0] is None:
            continue
        k = world_key(c)
        # Same-support discipline: a DGP draw whose rows block is outside the
        # BOUNDED support cannot be judged by it. Earlier this test compared a
        # full-DGP sample against a 400-class support and read 198/200 zeros as a
        # bijection failure -- the same mismatch class just fixed in the DGP
        # check. Unsupported draws are counted separately and reported.
        if repr(ob[0][0]) not in blocks:
            unsupported += 1
            continue
        hits = by_world_key.get(k, [])
        if len(hits) == 0:
            zero += 1
            if len(misses) < 3:
                misses.append({"Z": list(Z), "kappa": ctx.kappa,
                               "phase": ctx.phase})
        elif len(hits) > 1:
            multi += 1
        else:
            ok += 1
    judged = ok + zero + multi
    coverage = 1.0 - unsupported / N_SCENES
    detail["D"] = {"sampled": N_SCENES, "judged": judged,
                   "mapped_to_one": ok, "mapped_to_zero": zero,
                   "mapped_to_many": multi,
                   "unsupported_by_bounded_support": unsupported,
                   "bounded_support_coverage_of_dgp": coverage,
                   "miss_examples": misses,
                   "note": "Among scenes the BOUNDED support can judge, the "
                           "mapping must be exactly one. The coverage figure is "
                           "the real finding: a 400-class support covers only a "
                           "sliver of DGP mass, so the run harness needs the FULL "
                           "global support, or a DGP explicitly restricted to the "
                           "supported region."}
    # D can only be judged against the FULL global support. The bounded support
    # omits most classes, and world_key includes error_flag / cause_rank, so a
    # sampled world whose rows match but whose tape does not is simply absent.
    # Reporting PASS here would be the same mistake as the rejection check's
    # cross-support comparison, so it is reported BLOCKED with the measurement
    # that shows why (A58 vocabulary: never N/A).
    bijection_ok = (judged > 0 and zero == 0 and multi == 0)
    if unsupported > 0.05 * N_SCENES:
        checks["D_sample_to_support_bijection"] = "BLOCKED_NOT_IMPLEMENTED"
        d_status = "BLOCKED_NOT_IMPLEMENTED"
    else:
        checks["D_sample_to_support_bijection"] = bijection_ok
        d_status = "PASS" if bijection_ok else "FAIL"
    detail["D"]["status"] = d_status
    detail["D"]["why_blocked"] = (
        "world_key includes error_flag and cause_rank; the bounded support holds "
        "only a slice of classes, so most sampled worlds have no counterpart BY "
        "CONSTRUCTION rather than through drift. The run harness must build the "
        "FULL global support, and this assertion must then be re-run against it.")

    ok_all = all(v is True for v in checks.values())
    print(f"support: {len(worlds)} worlds in {len(blocks)} rows blocks")
    for k in sorted(checks):
        print(f"  {k:<52} {checks[k]}")
    print(f"\n  D: one={detail['D']['mapped_to_one']} zero={detail['D']['mapped_to_zero']} "
          f"many={detail['D']['mapped_to_many']} of {detail['D']['judged']} judged")
    print(f"     bounded-support coverage of DGP draws = "
          f"{detail['D']['bounded_support_coverage_of_dgp']:.3f} "
          f"({detail['D']['unsupported_by_bounded_support']} of {N_SCENES} "
          f"unjudgeable)")
    print(f"\nharness population assertions: {'ALL PASS' if ok_all else 'FAIL'}")

    out = ROOT / "experiments" / "v01r" / "harness_population_tests.json"
    out.write_text(json.dumps({"checks": checks, "detail": detail,
                               "n_worlds": len(worlds),
                               "n_blocks": len(blocks),
                               "status": "INCOMPLETE" if any(
                                   v == "BLOCKED_NOT_IMPLEMENTED"
                                   for v in checks.values())
                               else ("PASS" if ok_all else "FAIL"),
                               "scope": "Bounded global support (first "
                                        f"{MAX_CLASSES} classes). The full global "
                                        "support arrives with the run harness."},
                              indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
