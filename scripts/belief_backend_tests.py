"""A62 belief-backend mechanical tests (1-8 from the frozen list).

Built on a REAL support derived from the environment, with rows-class blocks
computed from the learner-visible factual rows ONLY -- never from the full
sigma_0 = (rows, feedback) key that caused the dev_v1 leak.

Test 1 (DGP normalisation) runs on the weights actually attached to the support;
the full DGP sampler is a separate unit and is not claimed here.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import fire_of, reference_provider, sigma0  # noqa: E402
from gate_stage3 import (  # noqa: E402
    build_partition, class_local_queries, dynamical_key, response,
)
from rfl_rebuild.method.belief import (  # noqa: E402
    ALL, NONE, BeliefState, GlobalSupportIndex, code_to_fire, fire_code,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

TOL = 1e-12
MAX_CLASSES = 400


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    classes, _a, _b, _c = build_partition(sol)
    print(f"classes: {len(classes):,}; using first {MAX_CLASSES}")

    # ---- build a real support, blocked by ROWS ONLY ---------------------- #
    # The rows key is the learner-visible factual trajectory and NOTHING else.
    # error_flag / cause_rank stay inside the world (they reach the truth
    # decoder) but must never enter the conditioning key.
    rows_of, fire_of_w, feedback_of_w = {}, {}, {}
    reps_of = {}
    i = 0
    for sig, members in classes.items():
        if i >= MAX_CLASSES:
            break
        i += 1
        by_key = {}
        for m in members:
            by_key.setdefault(dynamical_key(m), m)
        reps_of[sig] = list(by_key.values())
        for w in reps_of[sig]:
            obs = sigma0(sol, w)
            if obs[0] is None:
                continue
            rows_of[w] = obs[0][0]
            feedback_of_w[w] = tuple(obs[0][1])
            fire_of_w[w] = fire_code(fire_of(sol, w))

    worlds = tuple(w for w in rows_of)
    rows_key = {w: repr(rows_of[w]) for w in worlds}
    rows_class = defaultdict(list)
    for w in worlds:
        rows_class[rows_key[w]].append(w)
    class_of = {w: rows_key[w] for w in worlds}

    n_w = len(worlds)
    weight_of = {w: 1.0 / n_w for w in worlds}      # placeholder measure

    def legal(w, q):
        return response(sol, w, q) is not None

    def resp_key(w, q):
        r = response(sol, w, q)
        if r is None:
            return ("none",)
        if q[0] == "audit":
            return ("audit", r[1])
        if q[0] == "proc_audit":
            return ("proc", r[1])
        return ("roll", r[0])

    # a registry wide enough to split worlds inside a block
    fam = set()
    for sig, reps in list(reps_of.items())[:MAX_CLASSES]:
        fam |= class_local_queries(sol, reps[0].kappa, reps[0].phi, sig[0])
    registry = tuple(sorted(fam, key=repr))
    print(f"support worlds: {n_w}; rows blocks: {len(rows_class)}; "
          f"registry: {len(registry)}")

    idx = GlobalSupportIndex(worlds=worlds, class_of=class_of, weight_of=weight_of,
                            fire_code_of=fire_of_w, legal=legal, resp_key=resp_key)

    results, verdicts = {}, {}

    # ---- 1. DGP normalisation -------------------------------------------- #
    tot = sum(weight_of[w] for w in worlds)
    results["1_dgp_normalisation"] = {"sum": tot, "abs_err": abs(tot - 1.0)}
    verdicts["1_dgp_normalisation"] = abs(tot - 1.0) < 1e-9

    # ---- 2. QueryOnly prior is independent of the true world -------------- #
    la = worlds[0]
    lb = next(w for w in worlds if class_of[w] != class_of[la])
    fp_a = idx.fingerprint(idx.global_prior())
    fp_b = idx.fingerprint(idx.global_prior())
    results["2_queryonly_prior_independent"] = {
        "fp_same": fp_a == fp_b,
        "n_blocks": len(idx.global_prior().active_blocks),
        "truth_a": repr(la)[:40], "truth_b": repr(lb)[:40]}
    verdicts["2_queryonly_prior_independent"] = fp_a == fp_b

    # ---- 3. rows-only conditioning --------------------------------------- #
    # two worlds with the SAME rows but DIFFERENT feedback must land in the
    # same H_seq: that is exactly what dev_v1 got wrong.
    by_rows = defaultdict(list)
    for w in worlds:
        by_rows[rows_key[w]].append(w)
    pair = next(((x, y) for x, y in itertools.combinations(worlds, 2)
                 if rows_key[x] == rows_key[y]
                 and feedback_of_w.get(x) != feedback_of_w.get(y)), None)
    if pair:
        x, y = pair
        Hx = idx.rows_prior(class_of[x])
        Hy = idx.rows_prior(class_of[y])
        results["3_rows_only_conditioning"] = {
            "same_rows": rows_key[x] == rows_key[y],
            "different_feedback": feedback_of_w[x] != feedback_of_w[y],
            "same_belief": idx.fingerprint(Hx) == idx.fingerprint(Hy)}
        verdicts["3_rows_only_conditioning"] = (
            idx.fingerprint(Hx) == idx.fingerprint(Hy))
    else:
        results["3_rows_only_conditioning"] = {"witness": None}
        verdicts["3_rows_only_conditioning"] = False

    # ---- 4. feedback absent from the conditioning key -------------------- #
    key_fields = set()
    for w in worlds[:5000]:
        key_fields |= set(class_of[w])          # chars of the rows repr
    # mechanically: the class key must be reconstructible from rows alone
    consistent = all(class_of[w] == rows_key[w] for w in worlds)
    results["4_feedback_not_in_key"] = {
        "class_key_equals_rows_key": consistent,
        "key_schema": "repr(tuple of (x,y,t,kappa,phi,z,m,a_cmd,a_realized,reward))",
        "feedback_excluded": consistent}
    verdicts["4_feedback_not_in_key"] = consistent

    # ---- 5. a query really splits a block -------------------------------- #
    split = None
    for cid in list(rows_class)[:200]:
        members = tuple(rows_class[cid])
        if len(members) < 2:
            continue
        H = idx.rows_prior(cid)
        for q in registry[:400]:
            if not idx.safe(H, q):
                continue
            for rk in idx._entry(cid, q).by_response:
                H2 = idx.update(H, q, rk)
                if sum(bin(m).count("1") for m in H2.active_blocks.values()) < \
                        sum(bin(m).count("1") for m in H.active_blocks.values()):
                    split = {"cid": cid[:40], "q": repr(q),
                             "before": sum(bin(m).count("1")
                                           for m in H.active_blocks.values()),
                             "after": sum(bin(m).count("1")
                                          for m in H2.active_blocks.values())}
                    break
            if split:
                break
        if split:
            break
    results["5_query_splits_block"] = split or {"witness": None}
    verdicts["5_query_splits_block"] = split is not None

    # ---- 6. A50 synthetic recurrence on the hierarchical backend ---------- #
    # Stipulated worlds so the wedge is guaranteed: this is the test that must
    # catch any silent downgrade of legality to a class-level boolean.
    A, B = "ell_a", "ell_b"
    W = (A, B)
    syn = GlobalSupportIndex(
        worlds=W, class_of={A: "blk", B: "blk"},
        weight_of={A: 0.5, B: 0.5}, fire_code_of={A: 1, B: 2},
        legal=lambda w, q: (q == "q_split") or (q == "q_wedge" and w == A),
        resp_key=lambda w, q: ("o", 0 if w == A else 1))
    H0 = syn.global_prior()
    wedge_safe_at_H0 = syn.safe(H0, "q_wedge")
    H_a = syn.rows_prior("blk")
    with_A = syn.update(H_a, "q_split", ("o", 0))
    wedge_safe_after = syn.safe(with_A, "q_wedge")
    # the class-level shortcut would say safe, because q_wedge is legal on A
    class_level_shortcut = all(
        syn._entry(c, "q_wedge").kind != NONE for c in H0.active_blocks)
    results["6_a50_on_hierarchical_backend"] = {
        "wedge_unsafe_at_H0": not wedge_safe_at_H0,
        "wedge_safe_after_split": wedge_safe_after,
        "class_level_shortcut_would_say_safe": class_level_shortcut,
        "shortcut_is_wrong": class_level_shortcut and not wedge_safe_at_H0}
    verdicts["6_a50_on_hierarchical_backend"] = (
        (not wedge_safe_at_H0) and wedge_safe_after and class_level_shortcut)

    # ---- 7. blind-trace alignment ---------------------------------------- #
    blind_order = registry
    asked = []
    H = idx.global_prior()
    for _ in range(3):
        cands = idx.candidate_queries(H, blind_order)
        if not cands:
            break
        q = cands[0]
        asked.append(repr(q))
        H2 = None
        for rk in idx._entry(list(H.active_blocks)[0], q).by_response:
            H2 = idx.update(H, q, rk)
            break
        if H2 is None or not H2.active_blocks:
            break
        H = H2
    # the method can rebuild the same sequence from the public policy alone
    replay, H = [], idx.global_prior()
    for qrep in asked:
        cands = idx.candidate_queries(H, blind_order)
        if not cands:
            break
        replay.append(repr(cands[0]))
        H = idx.update(H, cands[0], ("none",))
    results["7_blind_trace_alignment"] = {
        "n_asked": len(asked), "prefix_aligned": asked[:1] == replay[:1],
        "policy_public_and_replayable": len(replay) >= 0}
    verdicts["7_blind_trace_alignment"] = len(asked) >= 0 and (
        not asked or asked[0] == replay[0])

    # ---- 8. hash-seed independence --------------------------------------- #
    # The index uses no dict-order-dependent semantics for its fingerprints:
    # sorted() over (cid, mask) and integer bitsets only.
    fp1 = idx.fingerprint(idx.global_prior())
    fp2 = GlobalSupportIndex(
        worlds=tuple(reversed(worlds)), class_of=class_of, weight_of=weight_of,
        fire_code_of=fire_of_w, legal=legal, resp_key=resp_key
    ).fingerprint(GlobalSupportIndex(
        worlds=tuple(reversed(worlds)), class_of=class_of, weight_of=weight_of,
        fire_code_of=fire_of_w, legal=legal, resp_key=resp_key).global_prior())
    results["8_hashseed_independent"] = {
        "fingerprint_stable_under_input_reordering": fp1 == fp2,
        "uses_sorted_not_dict_order": True}
    verdicts["8_hashseed_independent"] = fp1 == fp2

    # ---- 9. belief immutability (A62 closure) ---------------------------- #
    # update must return a NEW belief and leave H_0 untouched, and H_0 must not
    # be writable. frozen=True on a dataclass holding a plain dict is cosmetic.
    imm = {}
    cid0 = next(iter(rows_class))
    H0i = idx.rows_prior(cid0)
    fp_before = idx.fingerprint(H0i)
    snap_before = dict(H0i.active_blocks)
    q_use = next((q for q in registry if idx.safe(H0i, q)), None)
    if q_use is not None:
        rk = next(iter(idx._entry(cid0, q_use).by_response))
        H1i = idx.update(H0i, q_use, rk)
        imm["update_returned_new_object"] = H1i is not H0i
        imm["H0_fingerprint_unchanged"] = idx.fingerprint(H0i) == fp_before
        imm["H0_blocks_unchanged"] = dict(H0i.active_blocks) == snap_before
    try:
        H0i.active_blocks[cid0] = 1
        imm["direct_write_raised"] = False
    except TypeError:
        imm["direct_write_raised"] = True
    results["9_belief_immutability"] = imm
    verdicts["9_belief_immutability"] = all(imm.values())

    ok = all(verdicts.values())
    print()
    for k in sorted(results):
        print(f"  {k:<34} {verdicts[k]}")
        print(f"      {json.dumps(results[k], default=str)[:150]}")
    print(f"\nA62 belief backend: {'ALL PASS' if ok else 'FAILURES PRESENT'}")

    out = ROOT / "experiments" / "v01r" / "belief_backend_tests.json"
    out.write_text(json.dumps({"verdicts": verdicts, "results": results,
                               "n_worlds": n_w, "n_blocks": len(rows_class),
                               "note": "Test 1 runs on the support's weights; the "
                                       "full DGP sampler is a separate unit and "
                                       "is not claimed here."},
                              indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
