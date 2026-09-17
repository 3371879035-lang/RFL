"""A62 — two-layer Test 8: PYTHONHASHSEED independence.

Layer A, BUILDER DETERMINISM: build a small slice cache in two subprocesses under
``PYTHONHASHSEED=1`` and ``999`` and require the cache file to be byte-identical.

Layer B, RUNTIME DETERMINISM: under the same two hash seeds, emit a canonical
payload -- support manifest digest, global-prior fingerprint, every rows-prior
fingerprint, the sample->world mappings for a fixed set of scenes, and the
registry order -- and require the payloads to be byte-identical.

Both run as SUBPROCESSES rather than two in-process runs, because an in-process
comparison cannot catch hash-seed dependence: the seed is fixed for the life of
the interpreter.

KNOWN GAP, recorded rather than hidden: the payload does NOT include item 5's
``q_0``, because that needs one legality pass over the 547-block global prior
(~1.04M rollouts, ~20 min per side). So this does not yet prove that the query
trace is seed-independent end to end. It proves the support, the beliefs, the
sample->world mapping and the registry order are.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import random
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "v01r"
SEEDS = ("1", "999")

PAYLOAD = r'''
import hashlib, json, pathlib, random, sys
sys.path[:0] = ["src", "scripts"]
from gate_stage2 import LatentCase, _domains, reference_provider, sigma0
from identifiability_gate import CAUSE_KEYS, KAPPAS, TAPES, canonicalise
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.kernel import SemanticTape
from rfl_rebuild.method.registry import build_registry, sort_key
from rfl_rebuild.method.support import DenseSupport
from rfl_rebuild.method.dgp import SceneDGP, SceneContext
from rfl_rebuild.solve.dp import solve_reference

sol = solve_reference(); provider = reference_provider(sol)
sup = DenseSupport.load(pathlib.Path("experiments/v01r/support_cache"),
                        expected_kernel_fingerprint="full",
                        expected_dgp_fingerprint="full")

def fp(belief):
    return hashlib.sha256("|".join(f"{b}:{m}" for b, m in
        sorted(belief.active_blocks.items())).encode()).hexdigest()[:24]

rows_fp = {str(b): fp(sup.rows_prior(b)) for b in sorted(sup._worlds_of)}
gi = fp(sup.global_prior())

def domains(ctx):
    tape = SemanticTape(phase=ctx.phase, error_flag=ctx.error_flag,
                        cause_rank=ctx.cause_rank)
    tr = K.rollout(kappa=ctx.kappa, tape=tape, command_provider=provider,
                   base_option=ctx.base_option)
    d = _domains(sol, ctx.kappa, tape, ctx.base_option, tr)
    return tuple(canonicalise(d[k]) for k in CAUSE_KEYS)

def is_feasible(ctx, Z, params):
    dm = domains(ctx)
    b = {k: (dm[i][params[i]] if Z[i] else None) for i, k in enumerate(CAUSE_KEYS)}
    c = LatentCase(case_id=0, kappa=ctx.kappa, phi=ctx.phase,
                   error_flag=ctx.error_flag, cause_rank=ctx.cause_rank,
                   base_option=ctx.base_option, Z=tuple(Z),
                   option_fault=b.get("P"), decision=b.get("D"),
                   controller=b.get("X"), plant=b.get("E"), trap=b.get("U"))
    return sigma0(sol, c)[0] is not None

dgp = SceneDGP(kappas=KAPPAS, options=K.option_ids(), tapes=TAPES,
               domains=domains, is_feasible=is_feasible)
ctx_ids = {}
i = 0
for kappa in KAPPAS:
    for tape in TAPES:
        for z in K.option_ids():
            ctx_ids[(kappa, tape.phase, tape.error_flag, tape.cause_rank, z)] = i
            i += 1
rng = random.Random(31337)
mapping = []
for _ in range(200):
    ctx, Z, params = dgp.sample_scene(rng)
    cid = ctx_ids[(ctx.kappa, ctx.phase, ctx.error_flag, ctx.cause_rank,
                   ctx.base_option)]
    zc = sum((1 << k) for k in range(5) if Z[k])
    mapping.append([cid, zc, list(params), sup.find_world(cid, zc, tuple(params))])

reg = build_registry(horizon=K.HORIZON, options=K.option_ids(), cells=K.OPEN_CELLS,
                     kappas=KAPPAS, phases=range(6), n_actions=len(K.ACTIONS))
payload = {
    "n_worlds": len(sup), "n_blocks": sup.n_blocks,
    "content_digest": sup.manifest.content_digest,
    "global_prior_fp": gi,
    "rows_fps": rows_fp,
    "mapping": mapping,
    "registry_size": len(reg),
    "registry_order_hash": hashlib.sha256(
        json.dumps([list(q) for q in reg]).encode()).hexdigest()[:24],
}
print(json.dumps(payload, sort_keys=True))
'''


def run_payload(seed: str):
    env = dict(os.environ, PYTHONHASHSEED=seed)
    p = subprocess.run([sys.executable, "-c", PAYLOAD], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"seed {seed} failed:\n{p.stderr[-2000:]}")
    return p.stdout.strip().splitlines()[-1]


def build_slice(seed: str, out_name: str):
    env = dict(os.environ, PYTHONHASHSEED=seed)
    # reuse the real builder via its module, with the output path redirected
    p = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path[:0]=['src','scripts']\n"
         "import pathlib\n"
         "import support_build as sb\n"
         "from rfl_rebuild.solve.dp import solve_reference\n"
         "from gate_stage2 import reference_provider\n"
         "sol=solve_reference(); prov=reference_provider(sol)\n"
         "sup,_,_,_=sb.build(sol, prov, (0,), 'slice')\n"
         "sup.save(pathlib.Path('experiments/v01r/" + out_name + "'))\n"],
        cwd=ROOT, env=env, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"slice build seed {seed} failed:\n{p.stderr[-2000:]}")
    return pathlib.Path(ROOT / "experiments" / "v01r" / (out_name + ".json")).read_bytes()


def main() -> int:
    checks, detail = {}, {}
    print("layer A: builder determinism (slice cache, two seeds)")
    a = {s: build_slice(s, f"_t8_slice_{s}") for s in SEEDS}
    checks["A_builder_cache_byte_identical"] = (a[SEEDS[0]] == a[SEEDS[1]])
    detail["A"] = {s: hashlib.sha256(a[s]).hexdigest()[:24] for s in SEEDS}
    for s in SEEDS:
        (ROOT / "experiments" / "v01r" / f"_t8_slice_{s}.json").unlink(missing_ok=True)

    print("layer B: runtime determinism (full support + registry, two seeds)")
    b = {s: run_payload(s) for s in SEEDS}
    checks["B_runtime_payload_byte_identical"] = (b[SEEDS[0]] == b[SEEDS[1]])
    pb = json.loads(b[SEEDS[0]])
    detail["B"] = {"payload_hash": hashlib.sha256(b[SEEDS[0]].encode()).hexdigest()[:24],
                   "n_worlds": pb["n_worlds"], "n_blocks": pb["n_blocks"],
                   "global_prior_fp": pb["global_prior_fp"],
                   "registry_order_hash": pb["registry_order_hash"],
                   "mapping_len": len(pb["mapping"]),
                   "mapped_zero": sum(1 for m in pb["mapping"] if m[3] is None)}

    ok = all(checks.values())
    for k in sorted(checks):
        print(f"  {k:<44} {checks[k]}")
    print(f"\nTest 8: {'PASS' if ok else 'FAIL'}")
    (OUT / "test8_hashseed.json").write_text(json.dumps({
        "checks": checks, "detail": detail,
        "seeds": list(SEEDS), "status": "PASS" if ok else "FAIL",
        "known_gap": "The runtime payload omits item 5's q_0, whose one legality "
                     "pass over the 547-block global prior costs ~1.04M rollouts "
                     "(~20 min per side). Support, beliefs, sample->world mapping "
                     "and registry order ARE covered; the end-to-end query trace "
                     "is not yet.",
    }, indent=1), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
