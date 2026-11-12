"""Ten deterministic rational-arithmetic examples for the two V1 documents.

Not a model test, training run, environment experiment, or theorem prover.
Only stdlib; no random draws, network, neural parameters, or RFL imports.
The output is created exclusively so the first result is not overwritten.
"""
import argparse
from fractions import Fraction as F
import json
from pathlib import Path


def verify():
    rows = []

    def keep(name, **values):
        rows.append(dict(name=name, values={k: str(v) for k, v in values.items()}))

    x, y = F(3, 2), F(-2, 3)
    compiled = ((x + y) ** 2 - (x - y) ** 2) / 4
    assert compiled == x * y == -1
    keep('N10_square_activation_product', output=compiled)

    gamma = F(1, 2)
    c0, c1, terminal_fact = [F(2), F(1)], [F(3), F(0)], [F(0), F(4)]
    terminal_x = [c + z for c, z in zip(c1, terminal_fact)]
    returns = [c + gamma * z for c, z in zip(c0, terminal_x)]
    assert returns == [F(7, 2), F(3)]
    keep('N3_N5_process_plus_terminal', channel0=returns[0], channel1=returns[1])

    ignored_tail = [F(999), F(-999)]
    stopped = [z + gamma * (1 - 1) * v for z, v in zip(terminal_x, ignored_tail)]
    assert stopped == terminal_x
    keep('N4_terminal_blocks_continuation', channel0=stopped[0], channel1=stopped[1])

    successors = [F(-1), F(1)]
    actual_mixture = sum(s * s / 2 for s in successors)
    imagined_mean_state = (sum(successors) / 2) ** 2
    assert actual_mixture == 1 and imagined_mean_state == 0
    keep('actual_successor_mixture_not_mean_state', mixture=actual_mixture, mean_state=imagined_mean_state)

    values, known, weights = [F(0), F(100)], [1, 0], [F(1), F(1)]
    observed = sum(v * m * w for v, m, w in zip(values, known, weights)) / sum(m * w for m, w in zip(known, weights))
    assert observed == 0 and sum(values) / 2 == 50
    assert sum(w * 0 for w in weights) == 0  # No-observation denominator, not a zero-valued estimate.
    keep('equation7_missing_is_not_observed_zero', observed=observed, invalid_unmasked_mean=sum(values) / 2)

    w = [F(1), F(2), F(1)]
    p = [v / sum(w) for v in w]
    s, t, noise = [F(0), F(1), F(2)], [F(1), F(2), F(3)], [F(1, 5), F(-1, 10), F(0)]
    delta = lambda z, age: F(1, 2) + z / 10 + age / 20
    target = delta(F(0), F(3))
    observed_d = [delta(z, age) + e for z, age, e in zip(s, t, noise)]
    alpha = sum(w) / (sum(w) + 1)
    estimate = alpha * sum(a * b for a, b in zip(p, observed_d))
    bound = alpha * (sum(a * abs(z) for a, z in zip(p, s)) / 10
                     + sum(a * abs(age - 3) for a, age in zip(p, t)) / 20
                     + abs(sum(a * e for a, e in zip(p, noise)))) + (1 - alpha) * abs(target)
    assert estimate == F(14, 25) and abs(estimate - target) == F(9, 100)
    assert bound == F(1, 4) and abs(estimate - target) <= bound
    keep('equation12_scope_drift_noise_shrinkage', estimate=estimate, target=target, absolute_error=abs(estimate - target), bound=bound)

    effective_n = sum(w) ** 2 / sum(v * v for v in w)
    assert effective_n == F(8, 3) and effective_n != sum(w)
    keep('equation13_effective_n_not_mass', effective_n=effective_n, mass=sum(w))

    # Two equally likely worlds; each action succeeds in exactly one world.
    # The signal matches the world with probability 3/4. This is a probability table, not a simulation.
    prior_value = F(1, 2)
    informed_value = F(0)
    for signal in (0, 1):
        joint = [F(1, 2) * (F(3, 4) if world == signal else F(1, 4)) for world in (0, 1)]
        signal_mass = sum(joint)
        posterior_action_values = [mass / signal_mass for mass in joint]
        informed_value += signal_mass * max(posterior_action_values)
    assert informed_value == F(3, 4) and informed_value >= prior_value
    keep('equation16_costless_information_example', before=prior_value, after=informed_value, gross_gain=informed_value - prior_value)

    p0, p1, n = F(1, 5), F(4, 5), 3
    for rho in (F(1, 2), F(1, 10)):
        mean = p0
        for _ in range(n):
            mean = (1 - rho) * mean + rho * p1
        assert mean - p1 == (1 - rho) ** n * (p0 - p1)
        variance = rho / (2 - rho) * p1 * (1 - p1)
        assert variance == (1 - rho) ** 2 * variance + rho ** 2 * p1 * (1 - p1)
    keep('equations18_19_EWMA_bias_variance', fast_bias_fraction=F(1, 2) ** 3, slow_bias_fraction=F(9, 10) ** 3)

    e0, eps = F(1, 3), [F(1, 10), F(1, 5), F(1, 20)]
    accumulated = e0
    for local in eps:
        accumulated = local + gamma * accumulated
    expanded = gamma ** len(eps) * e0 + sum(gamma ** (len(eps) - 1 - h) * local for h, local in enumerate(eps))
    assert accumulated == expanded == F(13, 60)
    keep('finite_depth_error_indexing', recursive=accumulated, expanded=expanded)

    assert len(rows) == 10
    return dict(status='TEN_EXACT_RATIONAL_EXAMPLES_MATCH', scope='algebra_examples_only',
                cases=rows, checks=len(rows), environment_steps=0, model_forward_calls=0,
                optimizer_steps=0, parameters_changed=False,
                limitations='Examples check arithmetic and indexing, not general proofs, floating-point implementation, or empirical benefits.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify()
    with args.output.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}, ensure_ascii=False))
