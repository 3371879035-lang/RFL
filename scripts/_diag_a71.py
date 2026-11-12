"""Diagnostic for the A71 mixed class: is it a real finding or a bug of mine?

The mixed class had block=38, fire=01101 and two distinct Gamma*, differing only in
the ControllerSite address (3_2_4_3 vs 0_2_0_3). But two worlds in the SAME
rows-only block share the factual trajectory, so they share every pre-action state
and every ControllerSite the reference visited. If X fired in both, the fault must
have acted at a site on that shared trajectory, so the addresses should agree.
The contradiction has to be resolved before this can be reported as a finding.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase, _domains, reference_provider  # noqa: E402
from identifiability_gate import CAUSE_KEYS, canonicalise  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape, State  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    dom_cache = {}

    def domains(wid):
        key = (sup.field(wid, "kappa"), sup.field(wid, "phase"),
               sup.field(wid, "error_flag"), sup.field(wid, "cause_rank"),
               sup.field(wid, "proposal"))
        if key not in dom_cache:
            tp = SemanticTape(phase=key[1], error_flag=key[2], cause_rank=key[3])
            tr = K.rollout(kappa=key[0], tape=tp, command_provider=provider,
                           base_option=key[4])
            d = _domains(sol, key[0], tp, key[4], tr)
            dom_cache[key] = tuple(canonicalise(d[k]) for k in CAUSE_KEYS)
        return dom_cache[key]

    def rebuild(wid):
        dm = domains(wid)
        p = [sup.field(wid, f"p{i}") for i in range(5)]
        b = {k: (dm[i][p[i]] if p[i] >= 0 else None)
             for i, k in enumerate(CAUSE_KEYS)}
        return LatentCase(case_id=0, kappa=sup.field(wid, "kappa"),
                          phi=sup.field(wid, "phase"),
                          error_flag=sup.field(wid, "error_flag"),
                          cause_rank=sup.field(wid, "cause_rank"),
                          base_option=sup.field(wid, "proposal"),
                          Z=tuple((sup.field(wid, "Z_code") >> i) & 1
                                  for i in range(5)),
                          option_fault=b.get("P"), decision=b.get("D"),
                          controller=b.get("X"), plant=b.get("E"), trap=b.get("U"))

    hits = []
    for wid in range(5000):
        if sup.field(wid, "block_id") == 38 and sup.field(wid, "fire_code") == 0b01101:
            hits.append(wid)
    print(f"worlds in block 38 with fire 01101: {len(hits)}")
    for wid in hits:
        c = rebuild(wid)
        p = [sup.field(wid, f"p{i}") for i in range(5)]
        print(f"\n world {wid}: param_idx={p} Z={c.Z} option_fault={c.option_fault}")
        print(f"   decision   = {c.decision!r}")
        print(f"   controller = {c.controller!r}")
        print(f"   plant      = {c.plant!r}")
        dm = domains(wid)
        print(f"   |X domain| = {len(dm[2])}")
        tr = K.rollout(kappa=c.kappa, tape=c.tape(), command_provider=provider,
                       base_option=c.base_option, mask=c.mask(),
                       option_fault=c.option_fault)
        st = State(x=K.START[0], y=K.START[1], t=0, kappa=c.kappa, phi=c.phi)
        onpath = []
        for s in tr.steps:
            if s.u != s.a_cmd:
                onpath.append((st.x, st.y, st.t, s.a_cmd, s.u, s.a_realized))
            st = s.state
        print(f"   (x,y,t,a_cmd,u,a_realized) where u != a_cmd: {onpath}")
        print(f"   outcome={tr.outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
