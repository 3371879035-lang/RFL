r"""$F_0$ §3's baseline-initializer construction gate --- the pre-specified, fail-closed check.

$$\boxed{I_{\text{baseline}} = I_{D_Q} = W^{\varnothing} + \Delta W^{\text{cal}}_{D_Q} \text{ is admitted
only if (a), (a$'$), (b1), (b2) and (c) all hold on } \mathcal B^{\text{op}}_{\text{dev}}$$

**This is operational evidence, not development data.** Its keys are $\mathcal B_{\text{bench}}$'s, it draws
no scientific seed, it reads no $f_T, f_N, f_G, f_C, f_R$, no threshold and no ranking, and it writes only
its own artifact. §1 permits the keys to drive pre-specified binary construction-validity gates; a failing
gate is a **verdict about the amendment**, never a signal to enlarge the cap or to substitute a different
corruption after the fact.

The workload is the frozen one and is not chosen here: all $32$ operational keys, the envelope's
`ACQUISITION_CAP = 40`, and the balanced master bank $\mathcal S^{\text{master}}_{\text{eval}}$ of §3.

    python scripts/f0_initializer_gate.py            # the gate; exit 0 iff admissible
    python scripts/f0_initializer_gate.py --plan     # validate the inputs, run no episode, write nothing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fractions import Fraction  # noqa: E402

from rfl_rebuild.b2.evalorder import prefix, prefix_digest  # noqa: E402
from rfl_rebuild.b2.initializer import (  # noqa: E402
    INITIALIZER_ARCH,
    baseline_gate,
    canary_address,
)
from rfl_rebuild.b2.training import BaselineAcquisitionPlan  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

BENCH_KEYS = tuple(range(900001, 900033))       # B^op_dev: all thirty-two operational keys
N_MAX = 1024                                    # S^master_eval's length, frozen by §3
ACQUISITION_CAP = 40                            # §1's pre-data cap
ALPHA = Fraction(1, 2)                          # §1's pre-data constants
EPSILON = Fraction(1, 10)
ARTIFACT = ROOT / "experiments" / "v03r" / "f0_initializer_gate.json"


def _plan() -> BaselineAcquisitionPlan:
    return BaselineAcquisitionPlan(seed=BENCH_KEYS[0], alpha=ALPHA, epsilon=EPSILON,
                                   acquisition_cap=ACQUISITION_CAP,
                                   evaluation_bank=prefix(N_MAX))


def _report(evidence, *, runtime_s: float) -> dict:
    failures = evidence.failures()
    return {
        "gate": "f0_initializer_construction_gate",
        "initializer": f"W_empty + delta_W_cal_{INITIALIZER_ARCH}",
        "canary_address": repr(canary_address()),
        "keys": list(evidence.keys),
        "cap": evidence.cap,
        "bank_size": evidence.bank_size,
        "bank_digest": prefix_digest(N_MAX),
        "propositions": {
            "a_canary_at_entry": evidence.canary_at_entry(),
            "a_prime_left_the_fixed_point": evidence.left_the_fixed_point(),
            "b1_curve_moves": evidence.curve_moves(),
            "b2_curves_separate": evidence.curves_separate(),
            "c_repaired_within_cap": evidence.repaired_within_cap(),
        },
        "witnesses": evidence.witnesses(),
        "diagnostic": {
            "note": "reported, never a criterion: how many training episodes would write the canary address",
            "canary_ever_visited": evidence.canary_ever_visited(),
            "episodes": len(evidence.keys) * evidence.cap,
        },
        "failures": list(failures),
        "verdict": "ADMISSIBLE" if not failures else "INADMISSIBLE",
        "runtime_s": round(runtime_s, 3),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="the F0 baseline-initializer construction gate")
    parser.add_argument("--plan", action="store_true",
                        help="validate the inputs, print the plan, run no episode and write no artifact")
    parser.add_argument("--out", default=str(ARTIFACT))
    args = parser.parse_args(argv)

    plan = _plan()
    reference = reference_view_from(solve_reference())
    if args.plan:
        print(json.dumps({
            "initializer": f"W_empty + delta_W_cal_{INITIALIZER_ARCH}",
            "canary": repr(canary_address()),
            "keys": list(BENCH_KEYS),
            "cap": ACQUISITION_CAP,
            "bank_size": len(plan.evaluation_bank),
            "bank_digest": prefix_digest(N_MAX),
            "artifact": args.out,
            "writes": False,
        }, indent=2, sort_keys=True))
        return 0

    start = time.perf_counter()
    evidence = baseline_gate(plan, keys=BENCH_KEYS, q_reference=reference)
    report = _report(evidence, runtime_s=time.perf_counter() - start)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    out.write_bytes(payload.encode("utf-8"))
    print(json.dumps(report["propositions"], indent=2, sort_keys=True))
    print(f"diagnostic: canary visited by {report['diagnostic']['canary_ever_visited']} of "
          f"{report['diagnostic']['episodes']} training episodes")
    print(f"verdict: {report['verdict']}   failures: {report['failures'] or 'none'}")
    print(f"artifact: {out}  ({len(payload)} bytes, sha256 "
          f"{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]})")
    if report["verdict"] != "ADMISSIBLE":
        print("The amendment's response to a failed gate is to return to the reviewer: the cap is not "
              "enlarged and no other corruption is substituted after seeing this result.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
