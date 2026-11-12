"""C3 seedless structural selection. Never reads any C1/C2 run or statistical key."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.temporal_initializer import layer_edits
from rfl_rebuild.env.kernel import HORIZON
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import LearnerPersistentState
from rfl_rebuild.solve.dp import solve_reference


def bank_values(learner, reference, bank):
    cache = {}
    for u in bank:
        cell = (u.kappa, u.phase, u.base_option)
        if cell not in cache:
            cache[cell] = learned_rollout(learner, kappa=u.kappa, tape=u.tape,
                                          base_option=u.base_option, q_reference=reference).return_value
    return tuple(cache[(u.kappa, u.phase, u.base_option)] for u in bank)


def selection(reference):
    bank = prefix(5760)
    sizes = (100, 256, 512, 1024, 5760)
    healthy = bank_values(LearnerPersistentState(), reference, bank)
    healthy_means = {n: mean(healthy[:n]) for n in sizes}
    rows = []
    selected = None
    for layer in range(HORIZON):
        learner = LearnerPersistentState()
        edits = layer_edits(reference, layer)
        learner.apply_transaction(edits, q_reference=reference)
        levels = bank_values(learner, reference, bank)
        means = {n: mean(levels[:n]) for n in sizes}
        observable = all(means[n] < .95 * healthy_means[n] for n in sizes)
        rows.append({"layer": layer, "n_edits": len(edits), "means": means, "observable": observable})
        if observable:
            selected = layer
            break  # earliest qualifying layer, no search for a better result
    return {"role": "SEEDLESS_STRUCTURAL_SELECTION", "scientific_seeds": [],
            "training_data_read": False, "healthy": healthy_means,
            "layers_inspected": rows, "selected_layer": selected}


if __name__ == "__main__":
    result = selection(reference_view_from(solve_reference()))
    out = ROOT / "experiments/v03r/c3_static.json"
    with out.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["selected_layer"] is not None else 1)
