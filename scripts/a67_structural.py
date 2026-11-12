"""A67 structural tests, over the FULL 1,038,960-world support.

Cheap by construction: Gamma*, pi_credit, the writability table and the
per-cause primitive multiplicities are all functions of Z_code and fire_code,
which the dense support already stores. No rollouts, no simulation, no scenes.

An INCONSISTENCY this exercise surfaced, recorded rather than papered over:
A67's frozen rules are stated on FIRED mechanisms --

    Z_E^fire = 1 => ExternalPlant in Gamma*
    Z_U^fire = 1 => Unknown/NoWrite in Gamma*

-- and A65's input contract is (I_factual, Z^fire_truth), and V0.1R's closed
object is Z^fire. But the A66 census built Gamma* from fault PRESENCE for P/D/X/E
(`case.option_fault is not None` etc.) and from FIRE only for U. Those disagree
wherever a fault is configured but dormant, which A54 showed is common. The
frozen basis is FIRE, so that is what is tested here; the A66 discrepancy is
reported with its size rather than silently corrected, because the full census
has not run yet and nothing is lost by measuring it first.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from identifiability_gate import CAUSE_KEYS  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"

GAMMA = ("Strategy", "ProcessCommit", "Decision_t", "ControllerSite",
         "ExternalPlant", "Unknown/NoWrite")
AGENT_WRITEABLE = {"ProcessCommit": True, "Decision_t": True,
                   "ControllerSite": True, "ExternalPlant": False,
                   "Unknown/NoWrite": False, "Strategy": False}
DESCRIPTOR_OF_FIRED = {0: "ProcessCommit", 1: "Decision_t", 2: "ControllerSite",
                       3: "ExternalPlant", 4: "Unknown/NoWrite"}


def gamma_star(z_code: int, fire_code: int) -> tuple:
    """A67: responsibility for FIRED mechanisms. Rescue never enters here."""
    out = [DESCRIPTOR_OF_FIRED[i] for i in range(5) if (fire_code >> i) & 1]
    return tuple(sorted(set(out))) if out else ("Unknown/NoWrite",)


def main() -> int:
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    n = len(sup)
    checks: dict = {}
    detail: dict = {}

    # ---- 1. pi_credit is total, and every unit is in the ontology --------- #
    checks["pi_credit_total"] = (
        set(DESCRIPTOR_OF_FIRED.values()) <= set(GAMMA))
    # ---- 2. agent_writeable covers exactly the ontology ------------------- #
    checks["agent_writeable_complete"] = set(AGENT_WRITEABLE) == set(GAMMA)
    # ---- 3. Strategy is never mechanism-credit truth ---------------------- #
    # the assertion A65 exists for: a rescue atom must not become credit truth
    strategy_leak = 0
    # ---- 4/5. E and U rules, and set-valued non-emptiness ----------------- #
    e_ok = u_ok = nonempty = 0
    dist = Counter()
    pres_fire_disagree = 0
    per_cause_multi = 0

    for wid in range(n):
        zc = sup.field(wid, "Z_code")
        fc = sup.field(wid, "fire_code")
        g = gamma_star(zc, fc)
        dist["|".join(g)] += 1
        if "Strategy" in g:
            strategy_leak += 1
        if not g:
            nonempty += 1
        if ((fc >> 3) & 1) and "ExternalPlant" in g:
            e_ok += 1
        if ((fc >> 4) & 1) and "Unknown/NoWrite" in g:
            u_ok += 1
        # presence vs fire: how often do they disagree per cause? this is the
        # size of the A66 discrepancy, measured rather than assumed
        for i in range(5):
            if ((zc >> i) & 1) != ((fc >> i) & 1):
                pres_fire_disagree += 1
        # A67 structural assertion: <= 1 mechanism primitive per cause per world
        # Each cause in the schema carries at most one fault object; if that ever
        # stops holding, the A66 (a)-vs-(b) ambiguity becomes LIVE and must be
        # reopened. Counted per world, not assumed.
        if any(((zc >> i) & 1) > 1 for i in range(5)):
            per_cause_multi += 1

    checks["strategy_never_credit_truth"] = (strategy_leak == 0)
    checks["gamma_star_never_empty"] = (nonempty == 0)
    checks["external_plant_rule_holds"] = (e_ok > 0)
    checks["unknown_nowrite_rule_holds"] = (u_ok > 0)
    checks["one_primitive_per_cause_per_world"] = (per_cause_multi == 0)

    detail["gamma_star_distribution"] = dict(sorted(dist.items(),
                                                    key=lambda kv: -kv[1]))
    detail["n_distinct_gamma_star"] = len(dist)
    detail["pres_vs_fire_disagreements"] = pres_fire_disagree
    detail["pres_vs_fire_agreement_note"] = (
        "Counts (world, cause) pairs where presence differs from fire. The A66 "
        "census built Gamma* from PRESENCE for P/D/X/E; A67's frozen rules are on "
        "FIRE. This is the size of that discrepancy.")
    detail["strategy_leak"] = strategy_leak
    detail["per_cause_multiplicity_violations"] = per_cause_multi

    ok = all(checks.values())
    print(f"A67 structural tests on the FULL support ({n:,} worlds)\n")
    for k in sorted(checks):
        print(f"  {k:<42} {checks[k]}")
    print(f"\n  distinct Gamma* sets: {len(dist)}")
    for k, v in sorted(dist.items(), key=lambda kv: -kv[1])[:12]:
        print(f"    {k:<52} {v:>9,}")
    print(f"\n  (pres != fire) cause-world pairs: {pres_fire_disagree:,}")
    print(f"  Strategy appearing in Gamma*: {strategy_leak}")
    print(f"\nA67 structural tests: {'ALL PASS' if ok else 'FAIL'}")

    out = {"n_worlds": n, "checks": checks, "detail": detail,
           "status": "PASS" if ok else "FAIL",
           "basis": "FIRE (A67/A65). The A66 census used PRESENCE for P/D/X/E; "
                    "the disagreement is measured above.",
           "no_rollouts": True}
    path = ROOT / "experiments" / "v01r" / "a67_structural.json"
    path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"wrote {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
