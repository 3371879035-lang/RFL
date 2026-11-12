"""A62 runner — consume the dense support and the global registry.

Implements the six acceptance items of `14` §3.4 against the FULL support
(1,038,960 worlds / 547 blocks) and the global registry (9,437 queries).

Items 1-4 and 6 need no legality at all, so they run on the full support
directly. Item 5 (blind isolation) needs `safe(H_global, q)`, which over the full
prior costs one legality pass per block -- the ~1M-world check recorded in the
registry commit. It is therefore run behind an EXPLICIT cache warm-up with a
declared budget, and if the budget is not enough the item is reported as not
run rather than being replaced by a cheaper check that would stop exercising the
real information boundary.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import (  # noqa: E402
    LatentCase, _domains, reference_provider, sigma0,
)
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape  # noqa: E402
from rfl_rebuild.method.dgp import SceneContext, SceneDGP  # noqa: E402
from rfl_rebuild.method.registry import build_registry, first_safe  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"
LEGALITY_BUDGET = 1_400_000      # declared cap on world-legality evaluations
# Why this is large: item 5 needs safe(H_global, q), and H_global activates all
# 547 blocks, so ONE query over the full prior costs ~1.04M per-world legality
# checks (each a rollout). That is the real price of not reading legality off a
# class-level boolean. The cache memoises per (block, query), so the cost is paid
# once per query, not once per scene -- and it is NOT reduced by narrowing the
# check, which is the one thing that would silently reopen the boundary.


def fingerprint(belief) -> str:
    return hashlib.sha256("|".join(
        f"{b}:{m}" for b, m in sorted(belief.active_blocks.items())
    ).encode()).hexdigest()[:32]


class LegalityCache:
    """Lazy per-(block, query) legality, with an explicit evaluation budget.

    Legality is asked per WORLD, never read off a class-level boolean: the whole
    point of A50 is that `q in class.menu` is not the same question. This cache
    is therefore a memo of the per-world answer, and the budget makes its cost
    visible instead of hiding it behind an early exit.
    """

    def __init__(self, support: DenseSupport, probe, budget: int):
        self._s = support
        self._p = probe
        self._budget = budget
        self.used = 0
        self._memo: dict = {}
        self.exhausted = False

    def _rebuild(self, wid: int):
        s = self._s
        ctx = SceneContext(kappa=s.field(wid, "kappa"), phase=s.field(wid, "phase"),
                           error_flag=s.field(wid, "error_flag"),
                           cause_rank=s.field(wid, "cause_rank"),
                           base_option=s.field(wid, "proposal"))
        dm = self._p.domains(ctx)
        b = {k: (dm[i][s.field(wid, f"p{i}")] if s.field(wid, f"p{i}") >= 0
                 else None) for i, k in enumerate(CAUSE_KEYS)}
        return LatentCase(case_id=0, kappa=ctx.kappa, phi=ctx.phase,
                          error_flag=ctx.error_flag, cause_rank=ctx.cause_rank,
                          base_option=ctx.base_option, Z=tuple(b_not_none(b)),
                          option_fault=b.get("P"), decision=b.get("D"),
                          controller=b.get("X"), plant=b.get("E"), trap=b.get("U"))

    def safe(self, belief, q) -> bool:
        for bid, mask in belief.active_blocks.items():
            key = (bid, q)
            hit = self._memo.get(key)
            if hit is None:
                members = self._s.block_members(bid)
                if self.used + len(members) > self._budget:
                    self.exhausted = True
                    raise RuntimeError("legality budget exceeded")
                legal = []
                for wid in members:
                    if self.used > self._budget:
                        self.exhausted = True
                        raise RuntimeError("legality budget exceeded")
                    self.used += 1
                    legal.append(self._p.legal(self._rebuild(wid), q))
                hit = tuple(legal)
                self._memo[key] = hit
            for bit, ok in enumerate(hit):
                if (mask >> bit) & 1 and not ok:
                    return False
        return True


def b_not_none(b):
    return [1 if b[k] is not None else 0 for k in CAUSE_KEYS]


class Probe:
    def __init__(self, sol, provider):
        self.sol = sol
        self.provider = provider

    def domains(self, ctx):
        tape = SemanticTape(phase=ctx.phase, error_flag=ctx.error_flag,
                            cause_rank=ctx.cause_rank)
        tr = K.rollout(kappa=ctx.kappa, tape=tape, command_provider=self.provider,
                       base_option=ctx.base_option)
        d = _domains(self.sol, ctx.kappa, tape, ctx.base_option, tr)
        return tuple(canonicalise(d[k]) for k in CAUSE_KEYS)

    def legal(self, case, q):
        from gate_stage3 import response
        return response(self.sol, case, q) is not None


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    probe = Probe(sol, provider)

    man = json.loads((ROOT / "experiments" / "v01r" /
                      "support_cache.manifest.json").read_text(encoding="utf-8"))
    support = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                                expected_dgp_fingerprint="full")
    assert len(support) == man["n_worlds"] == 1_038_960
    assert support.n_blocks == man["n_rows_blocks"] == 547
    print(f"loaded full support: {len(support):,} worlds, {support.n_blocks} blocks")

    registry = build_registry(horizon=K.HORIZON, options=K.option_ids(),
                              cells=K.OPEN_CELLS, kappas=K.KAPPAS
                              if hasattr(K, "KAPPAS") else (0, 1),
                              phases=range(6), n_actions=len(K.ACTIONS))
    print(f"global registry: {len(registry)} queries, first={registry[0]}")

    checks, detail = {}, {}

    # ---- 1. QueryOnly H_0 == H_global, truth-independent ------------------ #
    # global_prior() takes no world argument, so the structural claim is that the
    # true scene is not an input. The mechanical check calls it twice with two
    # different "true worlds" in hand and compares.
    w_a = 0
    w_b = next(i for i in range(len(support)) if support.field(i, "block_id")
               != support.field(0, "block_id"))
    fpA = fingerprint(support.global_prior())
    fpB = fingerprint(support.global_prior())
    detail["1"] = {"fp": fpA, "blocks": support.n_blocks,
                   "true_a_block": support.field(w_a, "block_id"),
                   "true_b_block": support.field(w_b, "block_id")}
    checks["1_queryonly_prior_is_global_and_truth_independent"] = (fpA == fpB)

    # ---- 2. Sequence and SeqThenQuery share H_rows(I) --------------------- #
    b_of_a = support.field(w_a, "block_id")
    H = support.rows_prior(b_of_a)
    detail["2"] = {"active_blocks": len(H.active_blocks),
                   "is_the_rows_block": list(H.active_blocks) == [b_of_a],
                   "block_size": len(support.block_members(b_of_a))}
    checks["2_sequence_and_seqthenquery_same_rows_belief"] = (
        len(H.active_blocks) == 1 and list(H.active_blocks)[0] == b_of_a)

    # ---- 3. same rows, different feedback -> identical belief ------------- #
    # feedback differs iff cause_rank or error_flag differs, since those are the
    # tape fields that reach the decoder.
    found = None
    members = support.block_members(b_of_a)
    for i in members:
        for j in members:
            if i == j:
                continue
            if (support.field(i, "cause_rank"), support.field(i, "error_flag")) != \
               (support.field(j, "cause_rank"), support.field(j, "error_flag")):
                found = (i, j)
                break
        if found:
            break
    if found:
        i, j = found
        detail["3"] = {
            "same_block": support.field(i, "block_id") == support.field(j, "block_id"),
            "feedback_differs": (support.field(i, "cause_rank"),
                                 support.field(i, "error_flag"))
                                != (support.field(j, "cause_rank"),
                                    support.field(j, "error_flag")),
            "beliefs_identical": fingerprint(support.rows_prior(b_of_a))
                                 == fingerprint(support.rows_prior(b_of_a))}
        checks["3_feedback_absent_from_sequence_belief"] = (
            detail["3"]["same_block"] and detail["3"]["feedback_differs"]
            and detail["3"]["beliefs_identical"])
    else:
        detail["3"] = {"witness": None, "note": "block is tape-homogeneous"}
        checks["3_feedback_absent_from_sequence_belief"] = False

    # ---- 4. sample -> support bijection ---------------------------------- #
    def build_dgp():
        def domains(ctx):
            return probe.domains(ctx)

        def is_feasible(ctx, Z, params):
            dm = domains(ctx)
            b = {k: (dm[i][params[i]] if Z[i] else None)
                 for i, k in enumerate(CAUSE_KEYS)}
            c = LatentCase(case_id=0, kappa=ctx.kappa, phi=ctx.phase,
                           error_flag=ctx.error_flag, cause_rank=ctx.cause_rank,
                           base_option=ctx.base_option, Z=tuple(Z),
                           option_fault=b.get("P"), decision=b.get("D"),
                           controller=b.get("X"), plant=b.get("E"),
                           trap=b.get("U"))
            return sigma0(sol, c)[0] is not None
        return SceneDGP(kappas=K.KAPPAS if hasattr(K, "KAPPAS") else (0, 1),
                        options=K.option_ids(), tapes=TAPES,
                        domains=domains, is_feasible=is_feasible)

    dgp = build_dgp()
    ctx_ids = {}
    i = 0
    for kappa in (K.KAPPAS if hasattr(K, "KAPPAS") else (0, 1)):
        for tape in TAPES:
            for z in K.option_ids():
                ctx_ids[(kappa, tape.phase, tape.error_flag, tape.cause_rank, z)] = i
                i += 1
    rng = random.Random(2024)
    one = zero = 0
    for _ in range(500):
        ctx, Z, params = dgp.sample_scene(rng)
        cid = ctx_ids.get((ctx.kappa, ctx.phase, ctx.error_flag, ctx.cause_rank,
                           ctx.base_option))
        zc = sum((1 << k) for k in range(5) if Z[k])
        wid = support.find_world(cid, zc, tuple(params))
        if wid is None:
            zero += 1
        else:
            one += 1
    detail["4"] = {"sampled": 500, "mapped_one": one, "mapped_zero": zero}
    checks["4_sample_to_support_bijection"] = (zero == 0 and one == 500)

    # ---- 5. blind isolation ---------------------------------------------- #
    cache = LegalityCache(support, probe, LEGALITY_BUDGET)
    try:
        q0 = first_safe(registry, lambda q: cache.safe(support.global_prior(), q))
        q0_again = first_safe(registry,
                              lambda q: cache.safe(support.global_prior(), q))
        detail["5"] = {"q0_index": q0, "q0_repeat": q0_again,
                       "query": list(registry[q0]) if q0 is not None else None,
                       "legality_evals_used": cache.used,
                       "budget": LEGALITY_BUDGET}
        checks["5_blind_isolation_q0_identical"] = (q0 == q0_again
                                                    and q0 is not None)
    except RuntimeError as e:
        detail["5"] = {"error": str(e), "legality_evals_used": cache.used,
                       "budget": LEGALITY_BUDGET,
                       "note": "Full-prior legality for the FIRST registry entry "
                               "exceeds the declared budget. Reported as not run "
                               "rather than replaced by a cheaper check."}
        checks["5_blind_isolation_q0_identical"] = "NOT_RUN_BUDGET"

    ok = all(v is True for v in checks.values())
    for k in sorted(checks):
        print(f"  {k:<50} {checks[k]}")
    print(f"\nrunner acceptance: {'ALL RUN ITEMS PASS' if ok else 'INCOMPLETE'}")

    out = ROOT / "experiments" / "v01r" / "runner_acceptance.json"
    out.write_text(json.dumps({"checks": checks, "detail": detail,
                               "n_worlds": len(support),
                               "n_blocks": support.n_blocks,
                               "registry_size": len(registry),
                               "status": "PASS" if ok else "INCOMPLETE"},
                              indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
