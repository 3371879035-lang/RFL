r"""Pre-refactor byte baseline for every $D_{patch}$ ledger.

A77 §65.12 makes the first implementation step a **pure** generic slice refactor, and
its first acceptance condition is that the $D_{patch}$ ledger's ``canonical()`` bytes
are unchanged for every arm. That condition can only be checked against a baseline
captured **before** the refactor exists -- so this script captures it, and afterwards
re-derives and compares it.

$$\boxed{\text{a regression guard generated after the change is not a regression guard}}$$

Two scene families, so the baseline covers more than one shape of outcome:

* **real scenes** — every $(\kappa, \varphi, z_0)$ healthy trace, every credited
  decision context, each arm, healthy and pre-patched states. **Every** $\varphi$ in
  ``K.PHASE_DOMAIN``, not a sample: $\varphi$ is part of the frozen ``State`` and of the
  canonical receipt address, and no frozen quotient folds it away, so a sampled $\varphi$
  would leave part of the address space unguarded;
* **synthetic envelope family** — a three-address envelope with
  `alternative = {UP, None, DOWN}`, which is what exercises
  ``NO_VALID_ALTERNATIVE`` and the "already holds the target" no-op without needing
  the co-fault worlds that produce an empty alternative set on a real trace.

Also recorded, because A77 §65.12's fourth condition is about them: ``law_metadata()``,
``independent_treatment_count()``, the alias plan identity, and the four arm names.

$$\boxed{2 \times 6 \times 4 \times 4\ \text{arms} \times 2\ \text{pre-states}
+ 12\ \text{synthetic} = 396}$$

Usage::

    # BEFORE the refactor, in a worktree of the pre-refactor revision:
    python scripts/dpatch_ledger_baseline.py --capture
    # after it, at HEAD:
    python scripts/dpatch_ledger_baseline.py --verify

``--verify`` writes ``experiments/v03r/dpatch_ledger_verification.json``, so the
comparison is a committed artifact rather than a line in a commit message.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1 import (                                    # noqa: E402
    LAWS, DeleteFactualPatch, LocalOracleRestore, SetAlternative, TargetRecord,
    independent_treatment_count, law_metadata, resolve_credited_units,
    run_patch_law, run_patch_law_with_envelope,
)
from rfl_rebuild.b1.laws import _Law                              # noqa: E402
from rfl_rebuild.env import kernel as K                           # noqa: E402
from rfl_rebuild.env.kernel import ControlState, State, option_actions  # noqa: E402
from rfl_rebuild.env.observation import walk_transition           # noqa: E402
from rfl_rebuild.learner.store import (                           # noqa: E402
    DECISION, DecisionAddress, Edit, LearnerPersistentState,
)
from rfl_rebuild.solve.dp import solve_reference                  # noqa: E402

UP, DOWN, LEFT, RIGHT = K.UP, K.DOWN, K.LEFT, K.RIGHT
DEFAULT_JSON = ROOT / "experiments" / "v03r" / "dpatch_ledger_baseline.json"

#: The canonical payload's digest-of-learner-state fields. A later step may legitimately
#: change these — A77 §65.12 makes the Q fingerprint component step 3's business — so a
#: difference confined to them is an encoding change, while a difference anywhere else is
#: a moved number wearing an encoding change's clothes.
_FINGERPRINT_FIELDS = ("fingerprint_pre", "fingerprint_post")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rel(path: pathlib.Path) -> str:
    """Display a path relative to ROOT when it is inside it.

    The baseline is captured in a **worktree** of the pre-refactor revision while the
    artifact is written into the main checkout, so an unconditional ``relative_to(ROOT)``
    crashed *after* writing the file. A print at the end of a run must not be able to
    turn a successful capture into a non-zero exit.
    """
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _legal_alt(addr: DecisionAddress) -> int:
    allowed = option_actions(addr.z, ControlState(z=addr.z, m=addr.m), addr.state)
    return allowed[-1]


def _patched(state: LearnerPersistentState, addr: DecisionAddress) -> None:
    state.apply_transaction([Edit(DECISION, addr, _legal_alt(addr))])


def real_scene_entries(sol) -> list[dict]:
    entries: list[dict] = []
    for kappa in (0, 1):
        for phi in K.PHASE_DOMAIN:
            for z0 in K.option_ids():
                provider = lambda s, c: sol.best_action(s, c.z, c.m)   # noqa: E731
                tr = K.rollout(
                    kappa=kappa,
                    tape=K.SemanticTape(phase=phi, error_flag=0, cause_rank=0),
                    command_provider=provider,
                    base_option=z0,
                )
                ts = sorted({s.t for (s, *_r)
                             in walk_transition(tr, kappa, phi, tr.option_in_force)})
                units = tuple(f"Decision_{t}" for t in ts)
                if not units:
                    continue
                addrs = resolve_credited_units(units, tr, kappa, phi)
                for law in LAWS:
                    for pre in ("healthy", "patched"):
                        st = LearnerPersistentState()
                        if pre == "patched":
                            _patched(st, addrs[0])
                        key = f"real|k{kappa}|p{phi}|z{z0}|{law.name}|{pre}"
                        res = run_patch_law(law, st, units, tr, kappa, phi, sol)
                        entries.append({"key": key,
                                        "canonical": res.ledger.canonical(),
                                        "sha256": _sha(res.ledger.canonical())})
    return entries


A = DecisionAddress(state=State(x=1, y=2, t=1, kappa=0, phi=0), z=1, m=0)
B = DecisionAddress(state=State(x=2, y=2, t=2, kappa=0, phi=0), z=1, m=0)
C = DecisionAddress(state=State(x=3, y=2, t=3, kappa=0, phi=0), z=1, m=0)
SYNTH = (A, B, C)


def synthetic_entries() -> list[dict]:
    env = {A: TargetRecord(A, UP, RIGHT),
           B: TargetRecord(B, None, RIGHT),
           C: TargetRecord(C, DOWN, RIGHT)}
    entries: list[dict] = []
    for law in LAWS:
        for pre in ("healthy", "patched_A", "patched_A_up"):
            st = LearnerPersistentState()
            if pre == "patched_A":
                st.apply_transaction([Edit(DECISION, A, LEFT)])
            elif pre == "patched_A_up":
                st.apply_transaction([Edit(DECISION, A, UP)])
            key = f"synthetic|{law.name}|{pre}"
            res = run_patch_law_with_envelope(law, st, SYNTH, env)
            entries.append({"key": key,
                            "canonical": res.ledger.canonical(),
                            "sha256": _sha(res.ledger.canonical())})
    return entries


def structural_record() -> dict:
    return {
        "law_metadata": [list(row) for row in law_metadata()],
        "arm_names": [law.name for law in LAWS],
        "independent_treatment_count": independent_treatment_count(),
        "alias_plan_is_same_function_object":
            LocalOracleRestore.plan is DeleteFactualPatch.plan,
        "alias_target_name": DeleteFactualPatch.name,
        "set_alternative_name": SetAlternative.name,
        "law_base_is_dunder_law": all(issubclass(law, _Law) for law in LAWS),
    }


def probe() -> dict:
    sol = solve_reference()
    entries = real_scene_entries(sol) + synthetic_entries()
    import rfl_rebuild.b1 as _b1
    return {
        "check": "D_patch ledger canonical bytes, pre-refactor baseline",
        "git_rev_at_capture": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True).stdout.strip(),
        # Evidence that the capture really ran against the intended source tree: when
        # the baseline is taken in a worktree of the pre-refactor revision, this points
        # into that worktree, not into the main checkout.
        "b1_source": str(_b1.__file__),
        "kappa_domain": [0, 1],
        "phi_domain": list(K.PHASE_DOMAIN),
        "option_ids": list(K.option_ids()),
        "n_entries": len(entries),
        "structural": structural_record(),
        "entries": entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--json", default=str(DEFAULT_JSON))
    ap.add_argument("--verification-json",
                    default=str(ROOT / "experiments" / "v03r"
                                / "dpatch_ledger_verification.json"))
    ap.add_argument(
        "--allow-fingerprint-encoding-change", action="store_true",
        help="A77 §65.12: the byte lock governs step 2 alone. A later step may add the Q "
             "fingerprint component, which changes every canonical string. With this "
             "flag a difference confined to the fingerprint fields is reported as "
             "ENCODING_ONLY instead of DRIFTED, and a difference outside them is still "
             "a failure.")
    args = ap.parse_args()
    if not (args.capture or args.verify):
        ap.error("choose --capture or --verify")
    path = pathlib.Path(args.json)
    if not path.is_absolute():
        path = ROOT / path

    now = probe()

    if args.capture:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(now, indent=2) + "\n", encoding="utf-8")
        print(f"captured {now['n_entries']} ledger canonicals")
        print(f"  git rev : {now['git_rev_at_capture']}")
        print(f"  b1 from : {now['b1_source']}")
        print(f"  written : {_rel(path)}")
        return 0

    if not path.exists():
        print(f"no baseline at {path}; run --capture before the refactor")
        return 1
    base = json.loads(path.read_text(encoding="utf-8"))
    old = {e["key"]: e for e in base["entries"]}
    new = {e["key"]: e for e in now["entries"]}

    bad = 0
    missing = sorted(set(old) - set(new))
    added = sorted(set(new) - set(old))
    field_diffs: Counter = Counter()
    outside_fingerprint = 0
    for key in sorted(set(old) & set(new)):
        if old[key]["sha256"] == new[key]["sha256"]:
            continue
        bad += 1
        was = json.loads(old[key]["canonical"])
        is_ = json.loads(new[key]["canonical"])
        fields = sorted(set(was) | set(is_))
        differing = [f for f in fields if was.get(f) != is_.get(f)]
        for f in differing:
            field_diffs[f] += 1
        beyond = [f for f in differing if f not in _FINGERPRINT_FIELDS]
        if beyond:
            outside_fingerprint += 1
            if outside_fingerprint <= 5:
                print(f"  CHANGED OUTSIDE THE FINGERPRINT {key}: {beyond}")
                for f in beyond:
                    print(f"    {f}: {was.get(f)!r} -> {is_.get(f)!r}")
    for key in missing:
        bad += 1
        print(f"  MISSING {key}")
    for key in added:
        bad += 1
        print(f"  ADDED   {key}")

    sbad = []
    for k, v in base["structural"].items():
        if now["structural"].get(k) != v:
            sbad.append(k)
            print(f"  STRUCTURAL CHANGED {k}: {v!r} -> {now['structural'].get(k)!r}")

    shapes_ok = not sbad and not missing and not added and len(old) == len(new)
    if bad == 0:
        status = "EXACT"
    elif args.allow_fingerprint_encoding_change and outside_fingerprint == 0 \
            and shapes_ok:
        status = "ENCODING_ONLY"
    else:
        status = "DRIFTED"
    ok = status != "DRIFTED"
    payload = {
        "check": "D_patch ledger canonical bytes, refactor verification",
        "baseline_rev": base["git_rev_at_capture"],
        "verification_rev": now["git_rev_at_capture"],
        "baseline_b1_source": base.get("b1_source"),
        "verification_b1_source": now["b1_source"],
        "n_baseline": len(old),
        "n_recomputed": len(new),
        "canonical_mismatches": bad,
        "differing_fields": dict(sorted(field_diffs.items())),
        "mismatches_outside_fingerprint_fields": outside_fingerprint,
        "structural_mismatches": len(sbad),
        "structural_mismatch_keys": sbad,
        "missing_keys": missing,
        "added_keys": added,
        "status": status,
        "obligation": (
            "A77 §65.12: the byte lock governs step 2, where status must be EXACT. A "
            "later step that adds the Q fingerprint component must show ENCODING_ONLY "
            "-- every difference confined to the fingerprint fields -- because a change "
            "outside them is a moved number wearing an encoding change's clothes"
        ),
    }
    vpath = pathlib.Path(args.verification_json)
    if not vpath.is_absolute():
        vpath = ROOT / vpath
    vpath.parent.mkdir(parents=True, exist_ok=True)
    vpath.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"\n  baseline entries          : {len(old)} (from {base['git_rev_at_capture']})")
    print(f"  recomputed entries        : {len(new)}")
    print(f"  canonical byte mismatches : {bad}")
    print(f"  structural mismatches     : {len(sbad)}")
    print(f"  written                   : {_rel(vpath)}")
    print(f"  differing fields          : {dict(sorted(field_diffs.items()))}")
    print(f"  outside fingerprint fields: {outside_fingerprint}")
    print("  LEDGER BASELINE " + status)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
