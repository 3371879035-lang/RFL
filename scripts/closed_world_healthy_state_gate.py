r"""The stronger compatibility gate: an EXPLICIT healthy persistent learner state.

The previous gate proved the weaker statement

    learner state absent  =>  the old world.

This one proves the stronger statement A75 §62.11 actually needs:

$$\boxed{\text{explicit healthy persistent learner state} \Rightarrow
\text{the old world}}$$

Every world is rolled out through the **new store read path** — an empty decision
patch wrapper, an explicit identity $C_P^L$ provider, and an empty $C_X^L$ mapping —
rather than through the kernel's default absence. If the digest still matches the
preimage, the substrate is behaviourally transparent when healthy.

`fire_of` is used unchanged: A75 §62.11 deliberately does NOT wire the new provider
into ``fired_mechanisms`` / ``but_for_relevance``, and a healthy $C_P^L$ is the
identity, so the fire vector is unaffected either way.

Read-only; writes only its own report.
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
from closed_world_preimage import (  # noqa: E402
    OUT as PREIMAGE, canon_feedback, canon_rows,
)
from gate_stage2 import fire_of, reference_provider  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import MalformedIntervention, OptionViolation  # noqa: E402
from rfl_rebuild.env.observation import learner_rows  # noqa: E402
from rfl_rebuild.learner.store import LearnerPersistentState  # noqa: E402
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"
OUT = ROOT / "experiments" / "v02r" / "closed_world_healthy_state_gate.json"


def main() -> int:
    sol = solve_reference()
    provider = reference_provider(sol)
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    n = len(sup)

    prior = json.loads(PREIMAGE.read_text(encoding="utf-8"))
    state = LearnerPersistentState()
    t0 = time.time()
    h_all = hashlib.sha256()
    n_malformed = 0
    n_snapshot_calls = 0

    for wid in range(n):
        case, _idx = rebuild_case(sol, provider, sup, wid)
        # A FRESH snapshot per episode, taken through the new read path.
        snap = state.snapshot()
        n_snapshot_calls += 1
        args = dict(kappa=case.kappa, tape=case.tape(),
                    command_provider=snap.decision_provider(provider),
                    base_option=case.base_option, mask=case.mask(),
                    option_fault=case.option_fault,
                    controller=snap.controller_mapping(),
                    learner_process_commit=snap.process_commit_provider())
        try:
            trace = K.rollout(**args)
        except (MalformedIntervention, OptionViolation) as exc:
            n_malformed += 1
            h_all.update(f"{wid}:MALFORMED:{exc}\n".encode("utf-8"))
            continue
        rows = learner_rows(trace, case.kappa, case.phi)
        fb = tuple(case.tape().decode_feedback(list(fire_of(sol, case))))
        h_all.update(f"{wid}:{canon_rows(rows)}:{canon_feedback(fb)}\n"
                     .encode("utf-8"))

    digest = h_all.hexdigest()
    same = digest == prior["observable_digest"]
    payload = {
        "n_worlds": n,
        "n_malformed": n_malformed,
        "n_snapshots_taken": n_snapshot_calls,
        "healthy_state_was_empty": state.healthy,
        "read_path": ("an explicit healthy LearnerPersistentState: empty decision "
                      "patch wrapper, explicit identity C_P^L provider, empty C_X^L "
                      "mapping, and a fresh snapshot per episode"),
        "observable_digest": digest,
        "preimage_digest": prior["observable_digest"],
        "observable_digest_matches": same,
        "elapsed_seconds": round(time.time() - t0, 1),
        "statement": ("explicit healthy persistent learner state => the old world; "
                      "the stronger form of the backward-compatibility obligation, "
                      "since it exercises the new store read path rather than the "
                      "kernel's default absence"),
        "status": "PASS" if same else "FAIL",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print("closed-world gate: EXPLICIT healthy persistent learner state\n")
    print(f"  worlds                      : {n:,}")
    print(f"  malformed                   : {n_malformed}")
    print(f"  snapshots taken             : {n_snapshot_calls:,}")
    print(f"  final state healthy         : {state.healthy}")
    print(f"  preimage digest             : {prior['observable_digest']}")
    print(f"  through the store read path : {digest}")
    print(f"  [{'PASS' if same else 'FAIL'}] observable_digest matches")
    print(f"  elapsed                     : {payload['elapsed_seconds']}s")
    print(f"wrote {OUT}")
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
