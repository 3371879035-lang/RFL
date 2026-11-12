"""One actual lazy-coordinate exact-rejection request; no rollout or RFL trial."""
from fractions import Fraction
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
V95 = ROOT / "experiments/v03r/a96_dense/b2_prepare/owned_curve_connector_v95"
sys.path[:0] = [str(V95), str(V95.parent / "owned_adaptive_handoff_v92"),
                str(V95.parent / "adaptive_training_v90"), str(ROOT / "src")]

import adaptive_training as A
import learning as L
from rfl_rebuild.b2 import training as T
from rfl_rebuild.b2.unaffected import EvaluationScene
from rfl_rebuild.env import kernel as K


def main():
    maximum = T.M64
    rejections = ((maximum, 4),) + ((0,),) * (K.HORIZON - 1)
    episode = L.EngineeringEpisode(0, 0, 0, K.SemanticTape(2, 0, 57),
                                   (0,) + (maximum,) * (K.HORIZON - 1), rejections)
    params = A.LearningParameters(Fraction(1, 2), Fraction(1, 10))
    plan = L.EngineeringPlan((episode,), (EvaluationScene(0, 2, 0, 57, 0),),
                             0.7642000000000008, params, "V103-LOCKED-INPUT-PROBE")
    adapter = plan.episode(0)
    admissible = (0, 1, 2, 3, 4)
    exact_action = T.uniform_action(adapter, 0, admissible)
    exact_calls = tuple(adapter.calls)
    assert exact_action == 4
    assert exact_calls == ((0, 1, 0, maximum), (0, 1, 1, 4)), exact_calls

    # The source-level mutation's behavior, applied to a fresh adapter. The
    # same action is returned, but it fails the lazy-coordinate trace contract.
    mutant_adapter = plan.episode(0)
    first = mutant_adapter.chi(0, 1, 0)
    floor_action = admissible[(first * len(admissible)) >> 64]
    floor_calls = tuple(mutant_adapter.calls)
    assert floor_action == exact_action == 4
    assert floor_calls == ((0, 1, 0, maximum),)
    assert floor_calls != exact_calls
    result = {"schema": "V103_ACTUAL_ADAPTER_COMPONENT_RESULT_NOT_SCIENCE",
              "admissible_n": len(admissible), "uint64_max_rejected": True,
              "accepted_coordinate_c": 1, "accepted_value": 4,
              "exact_action": exact_action, "floor_mutant_action": floor_action,
              "exact_lazy_calls": [list(x) for x in exact_calls],
              "floor_mutant_lazy_calls": [list(x) for x in floor_calls],
              "mutant_rejected_by_coordinate_transcript": True,
              "adapter_instances": 2, "native_rollout_step_B1_transaction": 0,
              "rng_keyderive_DP_calibration_formal_curve_collection": 0,
              "scientific_qualification": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
