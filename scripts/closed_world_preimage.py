r"""Closed-world observation PREIMAGE, taken before the kernel is touched.

Why this exists, and why `content_digest` is not enough. `support.content_digest`
hashes only `_DENSE_FIELDS` -- kappa, phase, error_flag, cause_rank, proposal,
Z_code, p0..p4, block_id, fire_code. Those are all integer *partition* fields. The
**observable payload** that the learner actually sees -- the rows (positions,
commands, realized actions, rewards) and the terminal feedback vector -- is not
hashed at all. So an edit that changed a reward or a realized action while leaving the
partition intact could pass the support digest unchanged.

Backward compatibility is supposed to mean

    new learner state absent  =>  V0.1R/V0.2R observable semantics identical

and "identical" has to include the payload, not just the topology. This script writes
that preimage down FIRST, on the unmodified kernel. After the kernel patch the same
script must reproduce the same digest exactly; a mismatch means the patch changed a
closed version's world, whatever the support digest says.

Serialization is explicit and order-fixed: worlds are visited in ascending world-id
order and each contributes its own line, so order is part of the digest. Python's
`hash()` is never used (it is salted per process).

Read-only with respect to the frozen artifacts; it writes only its own report.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from a73_locator_gate import rebuild_case  # noqa: E402
from gate_stage2 import reference_provider, sigma0  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"
OUT = ROOT / "experiments" / "v02r" / "closed_world_observable_preimage.json"


def canon_rows(rows) -> str:
    """Explicit, locale-free, repr-free encoding of the learner-visible rows."""
    out = []
    for (x, y, t, kp, ph, z, m, ac, ar, r) in rows:
        out.append(f"{int(x)},{int(y)},{int(t)},{int(kp)},{int(ph)},"
                   f"{int(z)},{int(m)},{int(ac)},{int(ar)},{float(r):.6f}")
    return "|".join(out)


def canon_feedback(fb) -> str:
    return "".join(str(int(b)) for b in fb)


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    n = len(sup)

    h_all = hashlib.sha256()
    h_rows = hashlib.sha256()
    h_reward = hashlib.sha256()
    h_action = hashlib.sha256()
    h_fb = hashlib.sha256()
    n_malformed = 0
    t0 = time.time()

    for wid in range(n):
        case, _idx = rebuild_case(sol, provider, sup, wid)
        sig, err = sigma0(sol, case)
        if sig is None:
            n_malformed += 1
            line = f"{wid}:MALFORMED:{err}"
            h_all.update(line.encode("utf-8"))
            continue
        rows, fb = sig
        rs, fs = canon_rows(rows), canon_feedback(fb)
        h_all.update(f"{wid}:{rs}:{fs}\n".encode("utf-8"))
        h_rows.update(f"{wid}:{rs}\n".encode("utf-8"))
        h_fb.update(f"{wid}:{fs}\n".encode("utf-8"))
        h_reward.update(
            f"{wid}:{'|'.join(f'{float(r[9]):.6f}' for r in rows)}\n".encode("utf-8"))
        h_action.update(
            f"{wid}:{'|'.join(f'{int(r[7])},{int(r[8])}' for r in rows)}\n"
            .encode("utf-8"))

    digest = h_all.hexdigest()
    payload = {
        "n_worlds": n,
        "n_malformed": n_malformed,
        "world_order": "ascending world id, one line per world",
        "serialization": ("explicit f-string rows (x,y,t,kappa,phi,z,m,a_cmd,"
                          "a_realized,reward:.6f) joined by '|', then ':' then the "
                          "feedback bits; Python hash() is never used"),
        "observable_digest": digest,
        "observable_digest16": digest[:16],
        "component_digests": {
            "rows_only": h_rows.hexdigest(),
            "terminal_feedback_only": h_fb.hexdigest(),
            "reward_column_only": h_reward.hexdigest(),
            "action_columns_only": h_action.hexdigest(),
        },
        "why_not_content_digest": ("support.content_digest hashes only _DENSE_FIELDS "
                                   "(kappa, phase, error_flag, cause_rank, proposal, "
                                   "Z_code, p0..p4, block_id, fire_code) -- integer "
                                   "partition fields. The observable payload is not "
                                   "hashed, so a payload change that leaves the "
                                   "partition intact could pass it unchanged"),
        "obligation": ("after the kernel patch this script must reproduce "
                       "observable_digest EXACTLY; a mismatch means the patch changed "
                       "a closed version's world regardless of the support digest"),
        "elapsed_seconds": None,
    }
    payload["elapsed_seconds"] = round(time.time() - t0, 1)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print("closed-world observation preimage")
    print(f"  worlds                       : {n:,}")
    print(f"  malformed                    : {n_malformed}")
    print(f"  observable_digest            : {digest}")
    print(f"  observable_digest16          : {digest[:16]}")
    for k, v in payload["component_digests"].items():
        print(f"  {k:<28} : {v[:16]}")
    print(f"  elapsed                      : {payload['elapsed_seconds']}s")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
