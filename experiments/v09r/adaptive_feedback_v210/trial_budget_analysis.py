"""Deterministic finite probability calculation, not another task run."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LIMITS = (8, 32, 64, 128)
THRESHOLD = math.log(40.)


def log_e(positive, negative):
    values = []
    for q in (.25, .5, .75, 1.):
        if q == 1. and negative:
            values.append(-math.inf)
        else:
            values.append(positive*math.log1p(q)+(negative*math.log1p(-q) if negative else 0.))
    maximum = max(values)
    return maximum+math.log(sum(math.exp(x-maximum) for x in values)/4.)


def distribution(new_success):
    old_success = .5
    return (old_success*(1-new_success),
            old_success*new_success+(1-old_success)*(1-new_success),
            (1-old_success)*new_success)


def solve(probabilities):
    minus, zero, plus = probabilities
    maximum = max(LIMITS)
    verdict = {(i, j): (1 if log_e(i, j) >= THRESHOLD else
                        -1 if log_e(j, i) >= THRESHOLD else 0)
               for i in range(maximum+1) for j in range(maximum+1-i)}
    live = {(0, 0): 1.}
    adopted = rejected = expected_pairs = 0.
    snapshots = []
    for t in range(1, maximum+1):
        expected_pairs += sum(live.values())
        next_live = {}
        for (i, j), mass in live.items():
            for key, probability in (((i, j+1), minus), ((i, j), zero), ((i+1, j), plus)):
                moved = mass*probability
                if verdict[key] == 1:
                    adopted += moved
                elif verdict[key] == -1:
                    rejected += moved
                else:
                    next_live[key] = next_live.get(key, 0.)+moved
        live = next_live
        if t in LIMITS:
            unresolved = sum(live.values())
            assert abs(adopted+rejected+unresolved-1.) < 1e-12
            snapshots.append({'max_pairs': t, 'adopt_probability': adopted,
                              'not_worth_cost_probability': rejected,
                              'unresolved_probability': unresolved,
                              'expected_pairs': expected_pairs})
    return snapshots


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    start = time.perf_counter()
    pins = [Path(__file__), ROOT/'src/feedback_program_v210/evidence.py',
            ROOT/'docs/feedback_math/adaptive_feedback_v210/TRIAL_BUDGET_ADDENDUM.md',
            HERE/'checks_result.json', HERE/'checks_exit.json']
    before = {p.relative_to(ROOT).as_posix(): sha(p) for p in pins}
    with (HERE/'trial_budget_claim.json').open('x', encoding='utf-8') as stream:
        json.dump({'created_utc': datetime.now(timezone.utc).isoformat(),
                   'fixed_max_pairs': LIMITS, 'new_success_rates': [.5, .7, .9],
                   'old_success_rate': .5, 'independent_pair_outcomes': True,
                   'environment_episodes': 0, 'rng_calls': 0, 'input_sha256': before}, stream, indent=2)
    p, q = distribution(.5), distribution(.7)
    kl = sum(a*math.log(a/b) for a, b in zip(q, p))
    binary_kl = .8*math.log(.8/.025)+.2*math.log(.2/.975)
    rows = []
    for success in (.5, .7, .9):
        for row in solve(distribution(success)):
            rows.append({'old_success': .5, 'new_success': success,
                         'mean_effect': success-.5, **row})
    first = rows[0]
    assert abs(first['adopt_probability']-9/32768) < 1e-15
    after = {p.relative_to(ROOT).as_posix(): sha(p) for p in pins}
    assert before == after
    result = {'schema': 'v210-independent-finite-trial-probability-analysis',
              'first_candidate_alpha': .025, 'cost_threshold': 0.,
              'difference_only_kl_per_pair': kl,
              'necessary_binary_kl_for_power_08': binary_kl,
              'necessary_max_pairs_for_power_08_in_this_example': math.ceil(binary_kl/kl),
              'rows': rows, 'probability_mass_conserved': True, 'input_pins_unchanged': True,
              'environment_episodes': 0, 'rng_calls': 0, 'gradient_updates': 0,
              'wall_seconds': time.perf_counter()-start}
    with (HERE/'trial_budget_result.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
