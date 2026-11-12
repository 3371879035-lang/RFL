"""Pure design arithmetic only: no RFL import, rollout, training or RNG.

The historical example is read as data, never reconstructed as a runtime handle.
This checks the proposed rule and finite counts, not its learning effectiveness.
"""
import copy
import hashlib
import json
from fractions import Fraction
from pathlib import Path

from readout import factual_one_step_readout


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PLAN = HERE.parent / "plan_v175.json"
EXAMPLE = REPO / "experiments/v07r/fact_action_matrix_v174/mechanism_examples.json"


def graph(condition, mirror):
    successors, probabilities = {}, {}
    if condition["kind"] == "layered_chain":
        goal = condition["states"]
        for state, values in enumerate(condition["canonical_forward_probabilities"]):
            for command in (0, 1):
                successors[state, command] = state + 1
                probabilities[state, command] = Fraction(str(values[command ^ mirror]))
    else:
        goal = condition["states"]
        unit = json.loads(PLAN.read_text(encoding="utf-8"))["branch_unit"]
        for j in range(condition["units"]):
            fork, a, b, nxt = 3*j, 3*j+1, 3*j+2, 3*j+3
            for command in (0, 1):
                canonical = command ^ mirror
                successors[fork, command] = (a, b)[canonical]
                probabilities[fork, command] = Fraction(str(unit["canonical_fork_probabilities"][canonical]))
                for state, field in ((a, "canonical_A_probabilities"), (b, "canonical_B_probabilities")):
                    successors[state, command] = nxt
                    probabilities[state, command] = Fraction(str(unit[field][canonical]))
    return successors, probabilities, goal


def optimum(successors, probabilities, goal):
    values = {goal: Fraction(1)}
    for state in range(goal - 1, -1, -1):
        values[state] = max(probabilities[state, a]*values[successors[state, a]] for a in (0, 1))
    return values[0]


def run():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    prior = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    case = prior["first_noisy_FT_strict_Q_overrides_better_factual_probability"]
    state = case["pre_readout"]["room"]
    q = {(state, a): value for a, value in enumerate(case["pre_readout"]["q"])}
    counts = {(state, a): tuple(value) for a, value in enumerate(case["pre_readout"]["counts"])}
    successor = {(state, a): state+1 for a in (0, 1)}
    before = copy.deepcopy((successor, counts, q))
    action, rows = factual_one_step_readout(state, successor, state+1, counts, q, 0)
    assert case["actual_greedy"] == 0 and q[state, 0] > q[state, 1]
    assert action == 1 and [row["score"] for row in rows] == [1/3, 1/2]
    assert (successor, counts, q) == before
    historical_candidate_action = action

    # Synthetic zero-target case: factual exact-tie fallback still operates.
    nxt = {(0, a): 1 for a in (0, 1)}
    action, _ = factual_one_step_readout(0, nxt, 2, {(0, 0): (0, 8), (0, 1): (1, 0)}, {}, 0)
    assert action == 1

    # Synthetic downstream-value case: choose lower immediate probability
    # because it leads to the better continuation. No hidden p enters readout.
    fork = {(0, 0): 1, (0, 1): 2}
    facts = {(0, 0): (18, 0), (0, 1): (7, 1)}  # beta means .95 and .8
    downstream_cases = []
    for failure, qa, qb in ((0, .6, .95), (-1, .2, .9)):
        values = {(0, 0): .9, (0, 1): .2, (1, 0): qa, (1, 1): qa, (2, 0): qb, (2, 1): qb}
        picked, terms = factual_one_step_readout(0, fork, 3, facts, values, failure)
        assert picked == 1 and terms[0]["probability"] > terms[1]["probability"]
        downstream_cases.append({"failure_reward": failure, "action": picked, "terms": terms})

    # A disclosed limit, not a failed experiment: bad downstream Q can still
    # make the new readout choose the locally easy but globally poorer route.
    picked, _ = factual_one_step_readout(0, fork, 3, facts, {(1, 0): 1.0, (2, 0): 0.0}, 0)
    assert picked == 0

    settings = []
    expected = {"chain3": Fraction(9, 10)**3, "branch3": Fraction(76, 100)**3, "branch5": Fraction(76, 100)**5}
    for condition in plan["environments"]:
        for mirror in (0, 1):
            successors, probabilities, goal = graph(condition, mirror)
            assert len(successors) == 2*condition["states"]
            assert all(nxt > state for (state, _), nxt in successors.items())
            value = optimum(successors, probabilities, goal)
            assert value == expected[condition["id"]]
            settings.append({"condition": condition["id"], "mirror": mirror, "optimal_success_fraction": str(value), "optimal_success_decimal": float(value)})
    assert Fraction(95, 100)*Fraction(60, 100) < Fraction(80, 100)*Fraction(95, 100)

    arms, seeds, mirrors, conditions = len(plan["arms"]), plan["matrix"]["independent_seed_blocks"], len(plan["matrix"]["mirrors"]), len(plan["environments"])
    train, banks, eval_n = plan["matrix"]["train_episodes"], len(plan["matrix"]["checkpoints"]), plan["matrix"]["frozen_evaluation_episodes"]
    streams = arms*seeds*mirrors*conditions
    totals = {
        "matrix_streams": streams,
        "matrix_train_rollouts": streams*train,
        "matrix_eval_rollouts": streams*banks*eval_n,
        "matrix_total_rollouts": streams*(train+banks*eval_n),
        "combined_rollouts": streams*(train+banks*eval_n)+plan["wiring"]["native_rollouts"],
        "matrix_maximum_steps": arms*seeds*mirrors*(train+banks*eval_n)*sum(c["maximum_decisions"] for c in plan["environments"]),
        "matrix_extra_Q_backups_cap": (arms-1)*seeds*mirrors*conditions*train*12,
    }
    totals["combined_maximum_steps"] = totals["matrix_maximum_steps"]+plan["wiring"]["maximum_steps"]
    totals["combined_extra_Q_backups_cap"] = totals["matrix_extra_Q_backups_cap"]+(arms-1)*2*12
    for field, value in totals.items():
        assert value == plan["budgets"][field], (field, value, plan["budgets"][field])
    state_blocks = seeds*mirrors*sum(c["states"] for c in plan["environments"])
    rng = {"train_env": state_blocks*train, "train_action": state_blocks*train*2, "eval_env": state_blocks*eval_n}
    rng["total"] = sum(rng.values())
    assert rng == plan["randomness"]["planned_matrix_random_calls"]

    files = [PLAN, EXAMPLE, HERE/"readout.py", Path(__file__)]
    return {
        "status": "PURE_DESIGN_CHECK_COMPLETE_NOT_NATIVE_LEARNING_EVIDENCE",
        "historical_example": {"source": str(EXAMPLE.relative_to(REPO)), "source_uid": case["uid"], "actual_old_action": case["actual_greedy"], "candidate_same_snapshot_action": historical_candidate_action, "candidate_scores": [row["score"] for row in rows], "runtime_identity_reconstructed": False},
        "synthetic_downstream_examples": downstream_cases,
        "remaining_wrong_downstream_Q_limit_preserved": True,
        "world_arithmetic": settings,
        "planned_totals": totals,
        "planned_random_calls_not_executed": rng,
        "actual_new_rollouts": 0,
        "actual_training": 0,
        "actual_RNG_draws": 0,
        "old_runner_or_checker_execution": 0,
        "inputs": [{"path": str(p.relative_to(REPO)), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
    }


if __name__ == "__main__":
    result = run()
    output = HERE / "design_check_result.json"
    with output.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"status": result["status"], "actual_rollouts": 0, "planned_rollouts": result["planned_totals"]["combined_rollouts"]}))
