"""Stored-record sensitivity probes for six A91 error modes; no RFL imports."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CONTRACT = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
V95 = ROOT / CONTRACT["reference"]["namespace"]


def require(condition, why):
    if not condition:
        raise AssertionError(why)


def records():
    # Check the exact executed inputs and receipt before using the immutable log.
    import hashlib
    contract_raw = (V95 / "contract.json").read_bytes()
    exit_raw = (V95 / "evidence/exit.json").read_bytes()
    require(hashlib.sha256(contract_raw).hexdigest() == CONTRACT["reference"]["contract_sha256"],
            "V95 contract pin changed")
    require(hashlib.sha256(exit_raw).hexdigest() == CONTRACT["reference"]["exit_sha256"],
            "V95 exit receipt pin changed")
    receipt = json.loads(exit_raw)
    require(receipt["child_exit_code"] == 0 and receipt["automatic_retry"] is False,
            "bound V95 native receipt is not the recorded first exit")
    raw = (V95 / "evidence/stdout.log").read_bytes()
    import hashlib
    require(hashlib.sha256(raw).hexdigest() == CONTRACT["reference"]["stdout_sha256"], "V95 stdout pin changed")
    lines = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    return lines


def expect_mutant_rejected(name, mutated, predicate):
    try:
        predicate(mutated)
    except AssertionError as exc:
        return {"mutation": name, "rejected": True, "reason": str(exc)}
    raise AssertionError(f"mutant escaped: {name}")


def qaddr(s, z, m, a):
    return {"state": s, "z": z, "m": m, "a": a}


def td_address_check(record, td):
    trace = record["trace"]
    details = td["details"]
    require(len(details) == len(trace["steps"]), "TD/trace extent mismatch")
    state = {"x": 0, "y": 2, "t": 0, "kappa": record["episode"]["kappa"],
             "phi": record["episode"]["tape"]["phase"]}
    z, m = trace["option_in_force"], 0
    for i, (step, detail) in enumerate(zip(trace["steps"], details)):
        expected = qaddr(state, z, m, step["a_cmd"])
        require(detail["address"] == expected, f"TD address is not pre-step context at i={i}")
        state = step["state"]
        z, m = step["control"]["z"], step["control"]["m"]


def run():
    lines = records()
    tagged = {}
    for item in lines:
        tagged.setdefault(item["tag"], []).append(item["payload"])
    core = tagged["CORE_EPISODE"]
    td = tagged["INDEPENDENT_TD"]
    require(len(core) == 12 and len(td) == 12, "V95 completed raw/TD record counts changed")
    by_key = {(r["before"]["mode"], r["before"]["role"], r["epoch"]): r for r in core}
    td_by_key = {(r["mode"], r["role"], r["epoch"]): r for r in td}
    results = []

    # 1. The post-state-address mutation is rejected against the independently
    # captured chronological TD address sequence.
    sample = next((r for r in core if r["trace"]["steps"] and
                   r["trace"]["steps"][0]["state"] != {"x": 0, "y": 2, "t": 0,
                       "kappa": r["episode"]["kappa"], "phi": r["episode"]["tape"]["phase"]}), None)
    require(sample is not None, "no nonidentity first transition in V95 trace")
    sample_td = td_by_key[(sample["before"]["mode"], sample["before"]["role"], sample["epoch"])]
    mutant = deepcopy(sample_td)
    mutant["details"][0]["address"]["state"] = sample["trace"]["steps"][0]["state"]
    results.append(expect_mutant_rejected("use_post_state_as_current_q_address", mutant,
                                          lambda x: td_address_check(sample, x)))

    # 2. P manifests a real proposal/in-force distinction, so the mutant is not
    # vacuous; the first TD address must use the actual in-force option.
    p_record = next(r for r in core if r["before"]["mode"] == "dq" and r["before"]["role"] == "reference" and r["epoch"] == 0)
    p_td = td_by_key[(p_record["before"]["mode"], p_record["before"]["role"], p_record["epoch"])]
    require(p_record["trace"]["base_option"] != p_record["trace"]["option_in_force"],
            "chosen actual record does not manifest proposal/in-force difference")
    mutant = deepcopy(p_td)
    mutant["details"][0]["address"]["z"] = p_record["trace"]["base_option"]
    results.append(expect_mutant_rejected("use_proposal_as_initial_in_force", mutant,
                                          lambda x: td_address_check(p_record, x)))

    # 3. Exercise the exact integer rule on a true rejection boundary n=5. The
    # V95 runtime record itself used n=2 at its explored step; detect that gap.
    explored = [d for r in core for d in r["draws"] if d["explore"]]
    sizes = [len(d["admissible"]) for r in core for d in r["draws"] if d["explore"]]
    require(explored and set(sizes) == {2}, "V95 explored-set audit no longer matches bound evidence")
    values, n = ((1 << 64) - 1, 4), 5
    limit = (1 << 64) - ((1 << 64) % n)
    consumed = 0
    for value in values:
        consumed += 1
        if value < limit:
            exact = value % n
            break
    floor = (values[0] * n) >> 64
    require(exact == floor == 4 and consumed == 2,
            "boundary example no longer isolates coordinate-consumption mutant")
    results.append({"mutation": "uniform_action_by_flooring_a_real", "rejected": True,
                    "reason": "V95 claim/runtime mismatch detected: actual explored n=2; separate n=5 probe consumes c=0,1 while flooring consumes c=0 only",
                    "v95_actual_explored_sizes": sizes, "probe_n": n,
                    "exact_action_index": exact, "floor_action_index": floor,
                    "exact_coordinates_consumed": consumed, "floor_coordinates_consumed": 1})

    # 4. An alias-to-immediate mutant would make immediate equal the changed
    # current state. Actual episode receipts supply a changed current state and
    # unchanged immediate fingerprint.
    changed = next((r for r in core if r["before"]["current"] != r["after"]["current"]), None)
    require(changed is not None, "V95 has no state-changing episode for alias sensitivity")
    require(changed["before"]["immediate"] == changed["after"]["immediate"], "actual protected immediate drift")
    mutant = deepcopy(changed["after"])
    mutant["immediate"] = deepcopy(mutant["current"])
    results.append(expect_mutant_rejected("future_training_mutates_collateral_state", mutant,
        lambda x: require(x["immediate"] == changed["before"]["immediate"], "immediate I_a changed under alias mutant")))

    # 5. A per-arm V_pre mutant is one ULP away and rejected by the locked
    # shared-plan value encoded in every raw-derived projection.
    shared = json.loads((V95 / "contract.json").read_text(encoding="utf-8"))["shared_v_pre"]
    views = tagged["EXTERNAL_CURVE_VIEW"]
    value_from_wire = lambda w: float.fromhex(w["binary64_hex"])
    require(len(views) == 4 and all(value_from_wire(v["projection"]["pre_level"]) == shared for v in views),
            "V95 external curves do not share locked pre-level")
    mutant = deepcopy(views[0]["projection"])
    import math
    mutant["pre_level"] = math.nextafter(value_from_wire(mutant["pre_level"]), math.inf)
    results.append(expect_mutant_rejected("remeasure_v_pre_per_arm", mutant,
        lambda x: require(x["pre_level"] == shared, "arm-specific pre-level differs from locked V_pre")))

    # 6. Actual paired roles share epoch inputs and common lazy coordinates. A
    # one-word coordinate perturbation in the second arm is rejected.
    first = by_key[("dq", "reference", 1)]
    second = by_key[("dq", "treatment", 1)]
    require(first["episode"] == second["episode"], "actual role episodes are not shared")
    first_coords = {tuple(c[:3]): c[3] for c in first["coordinates"]}
    second_coords = {tuple(c[:3]): c[3] for c in second["coordinates"]}
    common = sorted(first_coords.keys() & second_coords.keys())
    require(common and all(first_coords[k] == second_coords[k] for k in common), "actual common coordinates differ")
    mutant = deepcopy(second_coords)
    k = common[0]
    mutant[k] ^= 1
    results.append(expect_mutant_rejected("second_arm_uses_different_training_seed", mutant,
        lambda x: require(all(first_coords[j] == x[j] for j in common), "paired coordinate stream changed")))

    require([x["mutation"] for x in results] == [
        "use_post_state_as_current_q_address", "use_proposal_as_initial_in_force",
        "uniform_action_by_flooring_a_real", "future_training_mutates_collateral_state",
        "remeasure_v_pre_per_arm", "second_arm_uses_different_training_seed"], "mutation order changed")
    return {"schema": "V102_STORED_OBSERVATION_MUTATION_SENSITIVITY_NOT_SOURCE_MUTATION_GATE",
            "input_records": {"CORE_EPISODE": len(core), "INDEPENDENT_TD": len(td),
                              "EXTERNAL_CURVE_VIEW": len(views)},
            "mutations_rejected": len(results), "results": results,
            "source_level_mutants_executed": 0, "RFL_imports_or_calls": 0,
            "native_rollout_step_B1_transaction": 0, "formal_keyed_stream": False,
            "scientific_qualification": False}


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, separators=(",", ":"), ensure_ascii=True))
