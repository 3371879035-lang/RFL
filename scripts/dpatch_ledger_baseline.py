r"""Pre-refactor byte baseline for every $D_{patch}$ ledger.

A77 §65.12 makes the first implementation step a **pure** generic slice refactor, and
its first acceptance condition is that the $D_{patch}$ ledger's ``canonical()`` bytes
are unchanged for every arm. That condition can only be checked against a baseline
captured **before** the refactor exists -- so this script captures it, and afterwards
re-derives and compares it.

$$\boxed{\text{a regression guard generated after the change is not a regression guard}}$$

Two scene families, so the baseline covers more than one shape of outcome:

* **real scenes** — every $(\kappa, \varphi, z_0)$ healthy trace, every credited
  decision context, each arm, healthy and pre-patched states;
* **synthetic envelope family** — a three-address envelope with
  `alternative = {UP, None, DOWN}`, which is what exercises
  ``NO_VALID_ALTERNATIVE`` and the "already holds the target" no-op without needing
  the co-fault worlds that produce an empty alternative set on a real trace.

Also recorded, because A77 §65.12's fourth condition is about them: ``law_metadata()``,
``independent_treatment_count()``, the alias plan identity, and the four arm names.

Usage::

    python scripts/dpatch_ledger_baseline.py --capture   # before the refactor
    python scripts/dpatch_ledger_baseline.py --verify    # after it, must be identical
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

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


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _legal_alt(addr: DecisionAddress) -> int:
    allowed = option_actions(addr.z, ControlState(z=addr.z, m=addr.m), addr.state)
    return allowed[-1]


def _patched(state: LearnerPersistentState, addr: DecisionAddress) -> None:
    state.apply_transaction([Edit(DECISION, addr, _legal_alt(addr))])


def real_scene_entries(sol) -> list[dict]:
    entries: list[dict] = []
    for kappa in (0, 1):
        for phi in (0, 2):
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
    return {
        "check": "D_patch ledger canonical bytes, pre-refactor baseline",
        "git_rev_at_capture": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True).stdout.strip(),
        "n_entries": len(entries),
        "structural": structural_record(),
        "entries": entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--json", default=str(DEFAULT_JSON))
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
        print(f"  written : {path.relative_to(ROOT)}")
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
    for key in sorted(set(old) & set(new)):
        if old[key]["sha256"] != new[key]["sha256"]:
            bad += 1
            print(f"  CHANGED {key}")
            print(f"    was {old[key]['canonical'][:160]}")
            print(f"    now {new[key]['canonical'][:160]}")
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

    print(f"\n  baseline entries          : {len(old)} (from {base['git_rev_at_capture']})")
    print(f"  recomputed entries        : {len(new)}")
    print(f"  canonical byte mismatches : {bad}")
    print(f"  structural mismatches     : {len(sbad)}")
    ok = bad == 0 and not sbad and len(old) == len(new)
    print("  LEDGER BASELINE " + ("REPRODUCED EXACTLY" if ok else "DRIFTED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
