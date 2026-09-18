"""A73 §60 / A72 §8.2 — the ``PublicSCMView`` information-boundary gate.

A59's lesson is that a documented promise is weaker than a type, so the view's
boundary is checked as a fact about the object and its import graph, not trusted:

1. **Import allowlist.** An AST scan of ``public_scm.py`` (and ``causal_locator.py``
   once it exists) must find only allowed modules. ``support``, ``dgp``, ``belief``,
   ``gate_stage2``, ``a71_indexed_truth`` and ``identifiability_gate`` are
   forbidden -- importing any of them would hand the locator the DenseSupport
   identity, the DGP weights or the evaluator's precomputed truth.
2. **Public surface.** The non-underscore attribute set of a live view must be
   exactly the four capabilities plus the two canonical-nuisance constants. A
   future attribute named ``block_id`` or ``weights`` fails here.
3. **Licence tie.** The canonical nuisance representative is only permitted if
   A73's quotient gate passed. The gate artifact is read and required to say PASS,
   so the licence cannot outlive its evidence.
4. **The candidate space contains the truth.** For every one of the 893 locator
   classes, the true world's hypothesis must be in ``hypotheses(kappa, phi)``, and
   ``forward`` / ``fire_vector`` must reproduce the evaluator's own ``X`` exactly.
   This is what makes ``C_SCM(X) != {}`` for real evidence, and it confirms A73's
   I1 (rows independent of the nuisance pair) through a completely separate path:
   the view fixes ``(error_flag, cause_rank) = (0, 0)`` while the evaluator uses the
   world's own values.
5. **No silent collapse.** ``credit_units`` must never return the empty set:
   abstention is not a verdict (A73 §60). ``EmptyCompatibleSet`` must exist and be a
   ``ProtocolError``.

Read-only with respect to the frozen artifacts.
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from gate_stage2 import LatentCase, fire_of, reference_provider, sigma0  # noqa: E402
from identifiability_gate import CAUSE_KEYS, KAPPAS  # noqa: E402
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.method.belief import fire_code  # noqa: E402
from rfl_rebuild.method.credit import ProtocolError  # noqa: E402
from rfl_rebuild.method.public_scm import (  # noqa: E402
    EmptyCompatibleSet, Hypothesis, PublicSCMView,
)
from rfl_rebuild.method.support import DenseSupport  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

CACHE = ROOT / "experiments" / "v01r" / "support_cache"
QUOTIENT_GATE = ROOT / "experiments" / "v02r" / "a73_quotient_gate.json"

STDLIB_ALLOWED = {"__future__", "dataclasses", "typing", "itertools",
                  "collections", "math", "functools", "enum"}
PKG_ALLOWED = {"env.kernel", "env.fault_grammar", "env.observation",
               "method.credit"}
# A `from X import Y` node contributes both the module and the name, and the name
# may itself be a submodule (`from rfl_rebuild.env import fault_grammar`) or a
# symbol (`from rfl_rebuild.env.kernel import Trap`). They are distinguished by
# prefix rather than by guessing: an import path is allowed when it equals an
# allowed prefix or extends one. `rfl_rebuild.env.kernel.Trap` extends
# `rfl_rebuild.env.kernel`; `rfl_rebuild.method.support` extends none of them.
ALLOWED_PREFIXES = ({"rfl_rebuild", "rfl_rebuild.env", "rfl_rebuild.method"}
                    | {f"rfl_rebuild.{s}" for s in PKG_ALLOWED})
FORBIDDEN_SUBSTRINGS = ("support", "dgp", "belief", "gate_stage2",
                        "a71_indexed_truth", "identifiability_gate", "weights",
                        "block_id", "world_id")
ALLOWED_PUBLIC = {
    "CANONICAL_CAUSE_RANK", "CANONICAL_ERROR_FLAG",
    "credit_unit", "credit_units", "fire_vector", "forward", "hypotheses",
    "proposals",
}


def imported_modules(path: pathlib.Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                found.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
                for a in node.names:
                    found.add(f"{node.module}.{a.name}")
    return found


def audit_imports(path: pathlib.Path) -> tuple[list[str], list[str]]:
    mods = imported_modules(path)
    bad = []
    for m in sorted(mods):
        top = m.split(".")[0]
        if top == "rfl_rebuild":
            if not any(m == p or m.startswith(p + ".") for p in ALLOWED_PREFIXES):
                bad.append(m)
        elif top not in STDLIB_ALLOWED:
            bad.append(m)
        if any(s in m for s in FORBIDDEN_SUBSTRINGS):
            bad.append(f"FORBIDDEN {m}")
    return sorted(set(bad)), sorted(mods)


def main() -> int:
    checks: dict[str, bool] = {}
    details: dict = {}

    # ---- 1. import allowlist ------------------------------------------- #
    for name in ("public_scm.py", "causal_locator.py"):
        p = ROOT / "src" / "rfl_rebuild" / "method" / name
        if not p.exists():
            details[f"imports_{name}"] = "not present (locator not implemented yet)"
            continue
        bad, mods = audit_imports(p)
        details[f"imports_{name}"] = {"imports": mods, "disallowed": bad}
        checks[f"import_allowlist_{name}"] = not bad

    # ---- 2. public surface --------------------------------------------- #
    sol = solve_reference()
    provider = reference_provider(sol)
    sup = DenseSupport.load(CACHE, expected_kernel_fingerprint="full",
                            expected_dgp_fingerprint="full")
    view = PublicSCMView(sol)
    surface = {a for a in dir(view) if not a.startswith("_")}
    details["public_surface"] = sorted(surface)
    checks["public_surface_is_exactly_the_four_capabilities"] = \
        surface == ALLOWED_PUBLIC
    checks["no_forbidden_name_on_the_surface"] = not any(
        any(s in a.lower() for s in FORBIDDEN_SUBSTRINGS) for a in surface)

    # ---- 3. the nuisance representative's licence ------------------------ #
    if QUOTIENT_GATE.exists():
        q = json.loads(QUOTIENT_GATE.read_text(encoding="utf-8"))
        details["quotient_gate_status"] = q.get("status")
        checks["canonical_nuisance_representative_is_licensed"] = \
            q.get("status") == "PASS"
    else:
        checks["canonical_nuisance_representative_is_licensed"] = False
        details["quotient_gate_status"] = "artifact missing"
    checks["representative_is_zero_zero"] = (
        PublicSCMView.CANONICAL_ERROR_FLAG == 0
        and PublicSCMView.CANONICAL_CAUSE_RANK == 0)

    # ---- 4. the candidate space contains the truth, one per class -------- #
    def rebuild(wid):
        kappa, phi = sup.field(wid, "kappa"), sup.field(wid, "phase")
        prop = sup.field(wid, "proposal")
        tape = PublicSCMView._tape(phi)
        healthy = K.rollout(kappa=kappa, tape=tape, command_provider=provider,
                            base_option=prop)
        import rfl_rebuild.env.fault_grammar as FG
        doms = FG.canonical_domains(sol, kappa, tape, prop, healthy)
        idx = [sup.field(wid, f"p{i}") for i in range(5)]
        b = FG.assign(doms, [(sup.field(wid, "Z_code") >> i) & 1 for i in range(5)],
                      idx)
        return LatentCase(
            case_id=0, kappa=kappa, phi=phi,
            error_flag=sup.field(wid, "error_flag"),
            cause_rank=sup.field(wid, "cause_rank"), base_option=prop,
            Z=tuple((sup.field(wid, "Z_code") >> i) & 1 for i in range(5)),
            option_fault=b.get("P"), decision=b.get("D"), controller=b.get("X"),
            plant=b.get("E"), trap=b.get("U")), idx

    hyp_cache: dict = {}
    seen_classes: set = set()
    n_checked = n_in_space = n_rows_ok = n_fire_ok = 0
    empty_units = 0
    u_only_mismatch = 0
    first_failures: list = []

    for wid in range(len(sup)):
        key = (sup.field(wid, "block_id"), sup.field(wid, "fire_code"))
        if key in seen_classes:
            continue
        seen_classes.add(key)
        n_checked += 1

        case, idx = rebuild(wid)
        sig, _err = sigma0(sol, case)
        if sig is None:
            continue
        rows, _feedback = sig
        truth_fire = fire_code(fire_of(sol, case))

        hyp = Hypothesis(kappa=case.kappa, phi=case.phi,
                         proposal=case.base_option,
                         presence=case.Z, params=tuple(idx))

        kp = (case.kappa, case.phi)
        space = hyp_cache.get(kp)
        if space is None:
            space = set(view.hypotheses(case.kappa, case.phi))
            hyp_cache[kp] = space
        if hyp in space:
            n_in_space += 1
        elif len(first_failures) < 3:
            first_failures.append(("not in candidate space", key))

        got_rows = view.forward(hyp)
        if got_rows == rows:
            n_rows_ok += 1
        elif len(first_failures) < 3:
            first_failures.append(("rows differ", key))

        got_fire = view.fire_vector(hyp)
        if got_fire == truth_fire:
            n_fire_ok += 1
        elif len(first_failures) < 3:
            first_failures.append(("fire differs", key, got_fire, truth_fire))

        units = view.credit_units(hyp)
        if units == frozenset():
            empty_units += 1
        if got_fire == 0 and units != frozenset({"Unknown/NoWrite"}):
            u_only_mismatch += 1

    details["classes_checked"] = n_checked
    details["truth_in_candidate_space"] = n_in_space
    details["rows_reproduced"] = n_rows_ok
    details["fire_reproduced"] = n_fire_ok
    details["first_failures"] = first_failures

    checks["truth_in_candidate_space_for_every_class"] = n_in_space == n_checked
    checks["forward_reproduces_evaluator_rows_for_every_class"] = \
        n_rows_ok == n_checked
    checks["fire_vector_reproduces_evaluator_fire_for_every_class"] = \
        n_fire_ok == n_checked
    checks["classes_checked_is_893"] = n_checked == 893

    # ---- 5. no silent collapse ------------------------------------------ #
    checks["credit_units_never_returns_the_empty_set"] = empty_units == 0
    checks["clean_worlds_give_Unknown_NoWrite"] = u_only_mismatch == 0
    checks["EmptyCompatibleSet_is_a_ProtocolError"] = issubclass(
        EmptyCompatibleSet, ProtocolError)

    ok = all(checks.values())

    print(f"PublicSCMView information-boundary gate\n")
    print(f"  public surface      : {sorted(surface)}")
    for k in ("imports_public_scm.py", "imports_causal_locator.py"):
        if k in details:
            print(f"  {k:<20}: {details[k]}")
    print(f"  quotient gate status: {details['quotient_gate_status']}")
    print(f"\n  locator classes checked                    : {n_checked}")
    print(f"  truth inside hypotheses(kappa, phi)        : {n_in_space}")
    print(f"  forward() reproduces evaluator rows        : {n_rows_ok}")
    print(f"  fire_vector() reproduces evaluator fire    : {n_fire_ok}")
    print(f"  credit_units() empty-set collapses         : {empty_units}")
    for name, cond in checks.items():
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if first_failures:
        print("\n  first failures:")
        for f in first_failures:
            print(f"    {f}")
    ok_txt = ("boundary holds and the candidate space contains the truth"
              if ok else "boundary or candidate-space failure")
    print(f"\nA73 PublicSCMView gate: {ok_txt}")

    out = ROOT / "experiments" / "v02r" / "a73_public_scm_gate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "checks": checks, "details": details,
        "status": "PASS" if ok else "FAIL",
        "allowed_public_surface": sorted(ALLOWED_PUBLIC),
        "package_import_allowlist": sorted(PKG_ALLOWED),
        "verdict": ok_txt,
    }, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
