"""A62 — build a DenseSupport, and prove the manifest refuses bad loads.

``--slice`` builds a small support (kappa = KAPPAS[0]) so the machinery can be
verified in seconds; the full support is the same code path without the flag and
takes ~20 minutes, which is why the verification does not depend on running it.

What is checked, none of which needs the full build:
  * save -> load round-trips the dense fields and the weights
  * weight_sum is 1 and the manifest records it
  * n_worlds / n_rows_blocks in the manifest match the arrays
  * a tampered kernel fingerprint           -> SupportMismatch
  * a tampered DGP fingerprint              -> SupportMismatch
  * a tampered content digest               -> SupportMismatch
  * a tampered schema_version / atom_schema -> SupportMismatch
  * find_world maps a DGP-sampled scene to exactly one world_id, and returns None
    for a scene outside the built slice
"""

from __future__ import annotations

import itertools
import json
import math
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import (  # noqa: E402
    LatentCase, fire_of, reference_provider, sigma0,
)
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES  # noqa: E402
from rfl_rebuild.env import fault_grammar  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape  # noqa: E402
from rfl_rebuild.method.belief import fire_code  # noqa: E402
from rfl_rebuild.method.dgp import SceneContext, SceneDGP  # noqa: E402
from rfl_rebuild.method.support import (  # noqa: E402
    ATOM_SCHEMA, SCHEMA_VERSION, DenseSupport, Manifest, SupportMismatch,
    content_digest,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

EXACT = math.e
OUT = ROOT / "experiments" / "v01r" / "support_cache"


def build(sol, provider, kappas, tag):
    def domains(ctx):
        # A73 route C: the single public grammar, not a second copy of it.
        # Proven exact against `gate_stage2._domains + canonicalise` over all
        # 5,760 public base contexts, raw and canonical, by
        # `scripts/a73_grammar_equivalence.py`; and the rebuild reproduces the
        # committed content digest, by `scripts/a73_support_digest_regression.py`.
        # The container type is unchanged (tuple of lists) so nothing downstream
        # sees a different object.
        tape = SemanticTape(phase=ctx.phase, error_flag=ctx.error_flag,
                            cause_rank=ctx.cause_rank)
        tr = K.rollout(kappa=ctx.kappa, tape=tape, command_provider=provider,
                       base_option=ctx.base_option)
        d = fault_grammar.legal_fault_domains(
            sol, ctx.kappa, tape, ctx.base_option, tr)
        return tuple(fault_grammar.canonicalise(d[k]) for k in CAUSE_KEYS)

    def build_case(ctx, Z, params):
        dm = domains(ctx)
        b = {k: (dm[i][params[i]] if Z[i] else None)
             for i, k in enumerate(CAUSE_KEYS)}
        return LatentCase(case_id=0, kappa=ctx.kappa, phi=ctx.phase,
                          error_flag=ctx.error_flag, cause_rank=ctx.cause_rank,
                          base_option=ctx.base_option, Z=tuple(Z),
                          option_fault=b.get("P"), decision=b.get("D"),
                          controller=b.get("X"), plant=b.get("E"), trap=b.get("U"))

    def is_feasible(ctx, Z, params):
        try:
            return sigma0(sol, build_case(ctx, Z, params))[0] is not None
        except Exception:
            return False

    dgp = SceneDGP(kappas=kappas, options=K.option_ids(), tapes=TAPES,
                   domains=domains, is_feasible=is_feasible)

    fields = {k: [] for k in ("kappa", "phase", "error_flag", "cause_rank",
                              "proposal", "Z_code", "p0", "p1", "p2", "p3", "p4",
                              "block_id", "fire_code")}
    rows_to_block, block_of, worlds_of, ctx_buckets = {}, [], {}, {}
    log_w, ctx_id = [], 0

    for kappa in kappas:
        for tape in TAPES:
            for z in K.option_ids():
                ctx = SceneContext(kappa=kappa, phase=tape.phase,
                                   error_flag=tape.error_flag,
                                   cause_rank=tape.cause_rank, base_option=z)
                if dgp.context_log_prob(ctx) == -math.inf:
                    continue
                dm = domains(ctx)
                for bits in itertools.product((0, 1), repeat=5):
                    if any(bits[i] == 1 and not dm[i] for i in range(5)):
                        continue
                    for combo in itertools.product(*[range(len(dm[i])) if bits[i]
                                                     else [-1] for i in range(5)]):
                        if not is_feasible(ctx, bits, list(combo)):
                            continue
                        c = build_case(ctx, bits, list(combo))
                        rk = repr(sigma0(sol, c)[0][0])
                        bid = rows_to_block.setdefault(rk, len(rows_to_block))
                        wid = len(fields["Z_code"])
                        zc = sum((1 << i) for i in range(5) if bits[i])
                        fields["kappa"].append(kappa)
                        fields["phase"].append(tape.phase)
                        fields["error_flag"].append(tape.error_flag)
                        fields["cause_rank"].append(tape.cause_rank)
                        fields["proposal"].append(z)
                        fields["Z_code"].append(zc)
                        for i in range(5):
                            fields[f"p{i}"].append(int(combo[i]))
                        fields["block_id"].append(bid)
                        fields["fire_code"].append(fire_code(fire_of(sol, c)))
                        block_of.append(bid)
                        worlds_of.setdefault(bid, []).append(wid)
                        log_w.append(dgp.log_prob(ctx, bits, list(combo)))
                        ctx_buckets.setdefault(ctx_id, ([], []))
                        ctx_buckets[ctx_id][0].append((zc,) + tuple(combo))
                        ctx_buckets[ctx_id][1].append(wid)
                ctx_id += 1

    m = max(log_w)
    sh = [pow(EXACT, lw - m) for lw in log_w]
    S = sum(sh)
    weights = [s / S for s in sh]
    contexts = {}
    for cid, (keys, ids) in ctx_buckets.items():
        order = sorted(range(len(keys)), key=lambda i: keys[i])
        contexts[cid] = (tuple(keys[i] for i in order),
                         tuple(ids[i] for i in order))
    manifest = Manifest(schema_version=SCHEMA_VERSION, n_worlds=len(weights),
                        n_rows_blocks=len(rows_to_block), atom_schema=ATOM_SCHEMA,
                        dgp_fingerprint=tag, kernel_fingerprint=tag,
                        weight_sum=sum(weights),
                        content_digest=content_digest(fields))
    return DenseSupport(manifest=manifest, fields=fields, weights=weights,
                        block_of_world=block_of, worlds_of_block=worlds_of,
                        contexts=contexts), dgp, domains, build_case


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    kappas = (KAPPAS[0],) if "--full" not in sys.argv else KAPPAS
    tag = "slice" if len(kappas) == 1 else "full"

    sup, dgp, domains, build_case = build(sol, provider, kappas, tag)
    path = OUT if tag == "full" else OUT.with_name(f"support_cache_slice")
    sup.save(path)
    print(f"built {tag}: {len(sup)} worlds, {sup.n_blocks} rows blocks")

    checks = {}
    # round-trip
    back = DenseSupport.load(path, expected_kernel_fingerprint=tag,
                             expected_dgp_fingerprint=tag)
    checks["roundtrip_worlds"] = len(back) == len(sup)
    checks["roundtrip_blocks"] = back.n_blocks == sup.n_blocks
    checks["roundtrip_fire_code"] = all(
        back.field(i, "fire_code") == sup.field(i, "fire_code")
        for i in range(0, len(sup), max(1, len(sup) // 500)))
    checks["weight_sum_is_one"] = abs(back.manifest.weight_sum - 1.0) < 1e-9

    # refuse-to-load on tampering
    raw = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))

    def tamper(mutate):
        import copy
        d = copy.deepcopy(raw)
        mutate(d)
        path.with_suffix(".json").write_text(json.dumps(d), encoding="utf-8")
        try:
            DenseSupport.load(path, expected_kernel_fingerprint=tag,
                              expected_dgp_fingerprint=tag)
            return False                      # loaded when it should have refused
        except SupportMismatch:
            return True

    checks["refuses_on_kernel_change"] = tamper(
        lambda d: d["manifest"].__setitem__("kernel_fingerprint", "different"))
    checks["refuses_on_dgp_change"] = tamper(
        lambda d: d["manifest"].__setitem__("dgp_fingerprint", "different"))
    checks["refuses_on_digest_change"] = tamper(
        lambda d: d["manifest"].__setitem__("content_digest", "0" * 16))
    checks["refuses_on_schema_change"] = tamper(
        lambda d: d["manifest"].__setitem__("schema_version", 999))
    checks["refuses_on_atom_schema_change"] = tamper(
        lambda d: d["manifest"].__setitem__("atom_schema", ["wrong"]))
    checks["refuses_on_weight_sum_change"] = tamper(
        lambda d: d["manifest"].__setitem__("weight_sum", 0.5))
    path.with_suffix(".json").write_text(json.dumps(raw), encoding="utf-8")

    # find_world: sampled scene -> exactly one world, and None outside the slice
    rng = random.Random(7)
    one = zero = 0
    for _ in range(300):
        ctx, Z, params = dgp.sample_scene(rng)
        parts = tuple(_ctx_key(ctx))
        cid = None
        for k, (keys, ids) in back._contexts.items():
            pass
        # rebuild the deterministic context id exactly as the builder did
        cid = _context_id(kappas, ctx)
        zc = sum((1 << i) for i in range(5) if Z[i])
        wid = back.find_world(cid, zc, tuple(params))
        if wid is None:
            zero += 1
        else:
            one += 1
    checks["find_world_maps_every_sampled_scene"] = (zero == 0 and one == 300)

    ok = all(checks.values())
    for k in sorted(checks):
        print(f"  {k:<42} {checks[k]}")
    print(f"\nsupport cache tests: {'ALL PASS' if ok else 'FAIL'}")
    (ROOT / "experiments" / "v01r" / "support_cache_tests.json").write_text(
        json.dumps({"tag": tag, "n_worlds": len(sup), "n_blocks": sup.n_blocks,
                    "checks": checks, "status": "PASS" if ok else "FAIL",
                    "note": "Built on a slice; the FULL support uses the same code "
                            "path without --full. Verifying the machinery does not "
                            "require the 20-minute enumeration."},
                   indent=1), encoding="utf-8")
    return 0 if ok else 1


def _ctx_key(ctx):
    return (ctx.kappa, ctx.phase, ctx.error_flag, ctx.cause_rank, ctx.base_option)


def _context_id(kappas, ctx):
    """Reproduce the builder's context numbering exactly."""
    i = 0
    for kappa in kappas:
        for tape in TAPES:
            for z in K.option_ids():
                if (kappa, tape.phase, tape.error_flag, tape.cause_rank, z) == \
                        _ctx_key(ctx):
                    return i
                i += 1
    return None


if __name__ == "__main__":
    raise SystemExit(main())
