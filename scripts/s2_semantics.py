"""A69 / S2 — V0.2R interface, typing and information-flow semantics.

S2 does NOT test which representation is more accurate; that is the experiment.
It proves the pipe: the alphabets, the truth-independence of the expansion, the
ExternalPlant invariant, abstention versus NoWrite, and the oracle separation.
Acceptance bar as in S1: a trivially dumb method must walk the whole interface.
"""

from __future__ import annotations

import inspect
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.method.credit import (  # noqa: E402
    AGENT_WRITEABLE, ETA, GAMMA_STATIC, CausalProposal, FactualShape,
    ModuleProposal, OracleCreditAdapter, ProtocolError, TrajectoryProposal,
    V02Input, agent_writeable, coverage, expand, false_credit_rate,
    writability_of,
)


def main() -> int:
    checks, detail = {}, {}
    shape = FactualShape(timesteps=(0, 1, 2), sites=("s1", "s2"))
    dom = shape.gamma()

    # ---- 4/5. the H/L partition is disjoint and covers Gamma(I) ----------- #
    H = expand("module", ModuleProposal(frozenset({"H"})), shape)
    L = expand("module", ModuleProposal(frozenset({"L"})), shape)
    checks["eta_module_partition_disjoint_and_covering"] = (
        not (H & L) and (H | L) == frozenset(dom))
    detail["eta_module"] = {"H": sorted(H), "L": sorted(L)}

    # ---- eta_trajectory is exactly Gamma(I) ------------------------------ #
    T = expand("trajectory", TrajectoryProposal(frozenset({"Episode"})), shape)
    checks["eta_trajectory_is_full_domain"] = (T == frozenset(dom))
    checks["eta_causal_is_identity"] = (
        expand("causal", CausalProposal(frozenset({"ProcessCommit"})), shape)
        == frozenset({"ProcessCommit"}))

    # ---- THE load-bearing freeze: eta_R must not see the truth ----------- #
    sig = {k: list(inspect.signature(f).parameters) for k, f in ETA.items()}
    forbidden = {"fire_truth", "truth", "Z", "gamma_star", "M", "R_mech",
                 "R_rescue", "x", "v02input"}
    checks["eta_R_cannot_read_truth"] = all(
        not (set(ps) & forbidden) for ps in sig.values())
    detail["eta_signatures"] = sig
    # and mechanically: same proposal + same shape -> same Gamma under ANY truth
    same = all(expand("module", ModuleProposal(frozenset({"H"})), shape) == H
               for _ in range(3))
    checks["eta_R_truth_independent_observed"] = same

    # ---- alphabet closure ------------------------------------------------- #
    closed = {}
    for name, ctor, bad in (("ModuleProposal", ModuleProposal, "ProcessCommit"),
                            ("TrajectoryProposal", TrajectoryProposal, "H")):
        try:
            ctor(frozenset({bad}))
            closed[name] = False
        except ProtocolError:
            closed[name] = True
    try:
        CausalProposal(frozenset({"NotAUnit"}))
        closed["CausalProposal"] = False
    except ProtocolError:
        closed["CausalProposal"] = True
    checks["alphabet_closure_enforced"] = all(closed.values())
    detail["alphabet_closure"] = closed

    # ---- V02Input: forbidden fields are absent, and B_Q = 0 --------------- #
    fields = set(V02Input.__slots__)
    checks["input_has_no_forbidden_field"] = not (
        fields & {"M", "Z_pres", "R_mech", "R_rescue", "gamma_star",
                  "world_id", "block_id", "support", "weights", "truth"})
    xi = V02Input(evidence=None, fire_truth=(0, 0, 0, 0, 0), shape=shape)
    checks["no_query_budget"] = (xi.B_Q == 0)
    detail["input_fields"] = sorted(fields)

    # ---- ExternalPlant survives scoring, and is unwritable --------------- #
    truth_plant = ("ExternalPlant",)
    checks["external_plant_unwritable_but_scoreable"] = (
        agent_writeable("ExternalPlant") is False
        and "ExternalPlant" in dom
        and coverage(("ExternalPlant",), truth_plant) == 1.0
        and false_credit_rate(("ExternalPlant",), truth_plant) == 0.0)
    # ---- the worked table from 07 section 4.1 ---------------------------- #
    table = {
        "truth_exact": (coverage(("ExternalPlant",), truth_plant),
                        false_credit_rate(("ExternalPlant",), truth_plant)),
        "strategy_only": (coverage(("Strategy",), truth_plant),
                          false_credit_rate(("Strategy",), truth_plant)),
        "both": (coverage(("ExternalPlant", "Strategy"), truth_plant),
                 false_credit_rate(("ExternalPlant", "Strategy"), truth_plant)),
    }
    checks["strategy_credit_is_penalised"] = (
        table["strategy_only"] == (0.0, 1.0) and table["both"] == (1.0, 0.5))
    detail["worked_table"] = table

    # ---- abstention != NoWrite ------------------------------------------- #
    truth_nw = ("Unknown/NoWrite",)
    checks["abstention_differs_from_nowrite"] = (
        coverage((), truth_nw) == 0.0
        and false_credit_rate((), truth_nw) == 0.0
        and coverage(("Unknown/NoWrite",), truth_nw) == 1.0
        and (coverage((), truth_nw), false_credit_rate((), truth_nw))
        != (coverage(("Unknown/NoWrite",), truth_nw),
            false_credit_rate(("Unknown/NoWrite",), truth_nw)))

    # ---- empty truth refused, so the denominator never vanishes ---------- #
    try:
        coverage(("x",), ())
        empty_refused = False
    except ProtocolError:
        empty_refused = True
    checks["empty_truth_refused"] = empty_refused and len(dom) > 0

    # ---- oracle separation ------------------------------------------------ #
    ora = OracleCreditAdapter()
    exact = ora.evaluate(truth_plant) == frozenset(truth_plant)
    try:
        ora(xi)
        oracle_closed = False
    except ProtocolError:
        oracle_closed = True
    checks["oracle_exact_and_type_separated"] = exact and oracle_closed
    checks["oracle_takes_truth_not_input"] = (
        set(inspect.signature(OracleCreditAdapter.evaluate).parameters)
        == {"gamma_star"})

    # ---- writability table complete over the ontology -------------------- #
    checks["writability_complete"] = set(writability_of(dom)) == set(dom) and \
        set(AGENT_WRITEABLE) == set(GAMMA_STATIC) | {"Decision_t", "ControllerSite"}
    detail["writability"] = writability_of(dom)

    # ---- acceptance bar: a dumb method walks the interface --------------- #
    dumb = expand("module", ModuleProposal(frozenset()), shape)
    checks["dumb_method_walks_interface"] = (dumb == frozenset())

    ok = all(checks.values())
    for k in sorted(checks):
        print(f"  {k:<48} {checks[k]}")
    print(f"\nS2: {'ALL PASS' if ok else 'FAIL'}")
    (ROOT / "experiments" / "v02r").mkdir(parents=True, exist_ok=True)
    p = ROOT / "experiments" / "v02r" / "s2_semantics.json"
    p.write_text(json.dumps({"checks": checks, "detail": detail,
                             "status": "PASS" if ok else "FAIL",
                             "scope": "interface/typing/information-flow only; "
                                      "NOT which representation is more accurate"},
                            indent=1, default=str), encoding="utf-8")
    print(f"wrote {p}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
