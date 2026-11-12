"""One-shot mathematical checks for V3, not a learning/environment experiment."""
from fractions import Fraction as Q
from functools import lru_cache
from itertools import combinations, product
from pathlib import Path
import hashlib
import json
import math
import sys
import time
import unittest

import torch
from network_operator import RelationalFacts

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCOPE = json.loads((HERE / 'scope.json').read_text(encoding='utf-8'))
RESULT = HERE / 'checks_result.json'
if RESULT.exists():
    raise SystemExit('Existing result retained; this entry is not an automatic rerun')
DETAILS = {}
MODELS = []
RNG_BEFORE = torch.get_rng_state().clone()
T0 = time.perf_counter()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


BEFORE = {p: sha(ROOT / p) for p in SCOPE['read_only_inputs']}
if BEFORE != SCOPE['input_sha256']:
    raise SystemExit('Declared input changed before algebra checks')


def model(cards, structures):
    net = RelationalFacts(cards, structures)
    MODELS.append((net, net.parameter_digest()))
    return net


def fact_table(net, target):
    """Construct a finite truth table as algebra input; do NOT sample a world."""
    rows = list(product(*(range(c) for c in net.cardinalities)))
    counts = torch.zeros((len(net.cells), 2, 2), dtype=torch.float64)
    phi = net(net.encode(rows))
    for b, row in enumerate(rows):
        for action in (0, 1):
            outcome = int(action == target(row))
            counts[:, action, outcome] += phi[b]
    return rows, counts


@lru_cache(maxsize=None)
def fixed_value(P, r, policy, horizon):
    if horizon == 0:
        return tuple(Q(0) for _ in r)
    previous = fixed_value(P, r, policy, horizon - 1)
    return tuple(r[s][policy[s]] + sum(P[s][policy[s]][j] * previous[j]
                                      for j in range(len(r))) for s in range(len(r)))


@lru_cache(maxsize=None)
def optimal_value(P, r, horizon):
    if horizon == 0:
        return tuple(Q(0) for _ in r)
    previous = optimal_value(P, r, horizon - 1)
    return tuple(max(r[s][a] + sum(P[s][a][j] * previous[j] for j in range(len(r)))
                     for a in range(len(r[s]))) for s in range(len(r)))


def small_kernels():
    reward_families = (
        ((Q(0), Q(1)), (Q(1), Q(0))),
        ((Q(1, 4), Q(3, 4)), (Q(3, 4), Q(1, 4))),
    )
    result = []
    for p, q in product((Q(0), Q(1, 2), Q(1)), repeat=2):
        P = (((p, 1-p), (q, 1-q)), ((1-q, q), (1-p, p)))
        for r in reward_families:
            result.append((P, r))
    return result


def error_constants(P, r, P2, r2):
    er = max(abs(r[s][a] - r2[s][a]) for s in range(2) for a in range(2))
    ep = max(sum(abs(P[s][a][j] - P2[s][a][j]) for j in range(2))/2
             for s in range(2) for a in range(2))
    return er, ep


class V3Checks(unittest.TestCase):
    def test_01_conjunction_exact(self):
        cells_checked = 0
        for n in range(1, 6):
            net = model((2,) * n, (tuple(range(n)),))
            rows = list(product((0, 1), repeat=n))
            phi = net(net.encode(rows))
            self.assertTrue(torch.equal(phi, torch.eye(len(rows), dtype=torch.float64)))
            cells_checked += phi.numel()
        DETAILS['conjunction'] = {'arities': [1, 2, 3, 4, 5], 'entries_checked': cells_checked}

    def test_02_missing_and_category_permutation(self):
        # Category 2 is an explicit missing value, not confused with category 0.
        net = model((3, 2), ((0, 1),))
        rows = list(product(range(3), range(2)))
        phi = net(net.encode(rows))
        self.assertTrue(torch.equal(phi, torch.eye(6, dtype=torch.float64)))
        swapped = model((2, 3), ((1, 0),))
        self.assertTrue(torch.equal(phi, swapped(swapped.encode([(b, a) for a, b in rows]))))
        DETAILS['missing_category'] = 'Explicit third category distinct; field permutation preserved'

    def test_03_same_network_multiple_relations(self):
        net = model((2, 2), ((0, 1),))
        digest = net.parameter_digest()
        record = {}
        targets = {'AND': lambda x: x[0] & x[1],
                   'OR': lambda x: x[0] | x[1],
                   'XOR': lambda x: x[0] ^ x[1]}
        for name, target in targets.items():
            rows, counts = fact_table(net, target)
            dist, support, mass = net.factual_distribution(net.encode(rows), counts)
            actions = dist[:, 0, :, 1].argmax(-1).tolist()
            self.assertEqual(actions, [target(x) for x in rows])
            self.assertTrue(bool(support.all()))
            self.assertTrue(torch.equal(mass, torch.ones_like(mass)))
            self.assertEqual(digest, net.parameter_digest())
            record[name] = {'actions': actions, 'correct_truth_table_rows': len(rows)}
        DETAILS['same_weights_fact_tables'] = record

    def test_04_unary_xor_and_joint_xor(self):
        net = model((2, 2), ((0,), (1,), (0, 1)))
        rows, counts = fact_table(net, lambda x: x[0] ^ x[1])
        dist, support, mass = net.factual_distribution(net.encode(rows), counts)
        self.assertTrue(torch.equal(dist[:, :2], torch.full_like(dist[:, :2], .5)))
        self.assertEqual(dist[:, 2, :, 1].argmax(-1).tolist(), [0, 1, 1, 0])
        self.assertEqual(mass[0, :, 0].tolist(), [2., 2., 1.])
        self.assertTrue(bool(support.all()))
        DETAILS['xor_unary_vs_joint'] = {'unary_probabilities': [.5, .5],
            'joint_actions': [0, 1, 1, 0], 'per_structure_support_not_pooled': [2, 2, 1]}

    def test_05_pair_relations_do_not_solve_all_orders(self):
        structures = tuple(combinations(range(3), 1)) + tuple(combinations(range(3), 2)) + ((0, 1, 2),)
        net = model((2, 2, 2), structures)
        rows, counts = fact_table(net, lambda x: x[0] ^ x[1] ^ x[2])
        dist, _, _ = net.factual_distribution(net.encode(rows), counts)
        self.assertTrue(torch.equal(dist[:, :-1], torch.full_like(dist[:, :-1], .5)))
        self.assertEqual(dist[:, -1, :, 1].argmax(-1).tolist(), [sum(x) % 2 for x in rows])
        DETAILS['retained_counterexample'] = 'Uniform 3-bit parity: every unary/pair fact head is 0.5; full triple resolves table'

    def test_06_unsupported_and_read_only(self):
        net = model((2, 2), ((0, 1),))
        rows, counts = fact_table(net, lambda x: x[0] ^ x[1])
        counts[:, 1, :] = 0  # Unknown action in the declared input, not a failed action.
        before = counts.clone()
        for _ in range(20):
            dist, support, mass = net.factual_distribution(net.encode(rows), counts)
        self.assertTrue(bool(support[:, :, 0].all()))
        self.assertFalse(bool(support[:, :, 1].any()))
        self.assertTrue(torch.equal(mass[:, :, 1], torch.zeros_like(mass[:, :, 1])))
        self.assertTrue(torch.equal(dist[:, :, 1], torch.zeros_like(dist[:, :, 1])))
        self.assertTrue(torch.equal(counts, before))
        DETAILS['read_only_rehearsal'] = {'repeated_reads': 20, 'evidence_count_increment': 0,
                                        'unknown_action_marked': True}

    def test_07_proper_propensity_reweighting(self):
        # Four probability atoms; the reward is X, independent of action.
        atoms = [(x, a, Q(1, 2) * (Q(9, 10) if a == x else Q(1, 10)))
                 for x, a in product((0, 1), repeat=2)]
        naive, corrected = [], []
        for target_action in (0, 1):
            mass = sum(p for x, a, p in atoms if a == target_action)
            naive.append(sum(p*x for x, a, p in atoms if a == target_action) / mass)
            corrected.append(sum(p*x / (Q(9, 10) if a == x else Q(1, 10))
                                 for x, a, p in atoms if a == target_action))
        self.assertEqual(naive, [Q(1, 10), Q(9, 10)])
        self.assertEqual(corrected, [Q(1, 2), Q(1, 2)])
        DETAILS['propensity_correction'] = {'raw': list(map(str, naive)), 'corrected': list(map(str, corrected)),
                                          'scope': 'Known full-context propensities; one-step common distribution'}

    def test_08_intervention_interactions(self):
        old, one, two, both = Q(1, 5), Q(1, 5), Q(1, 5), Q(4, 5)
        interaction = both - one - two + old
        self.assertEqual(interaction, Q(3, 5))
        self.assertEqual(one-old, 0)
        self.assertEqual(two-old, 0)
        DETAILS['joint_intervention'] = {'single_changes': ['0', '0'], 'joint_change': str(interaction)}

    def test_09_common_policy_not_average_oracles(self):
        values = ((Q(1), Q(0)), (Q(0), Q(1)))
        realizable = max(sum(v[a] for v in values)/2 for a in (0, 1))
        impossible = sum(max(v) for v in values)/2
        self.assertEqual(realizable, Q(1, 2))
        self.assertEqual(impossible, Q(1))
        DETAILS['common_policy'] = {'best_shared': str(realizable), 'average_world_oracle': str(impossible)}

    def test_10_persistent_world_joint_law(self):
        coherent = {(0, 0): Q(1, 2), (0, 1): Q(0), (1, 0): Q(0), (1, 1): Q(1, 2)}
        resampled = {key: Q(1, 4) for key in coherent}
        tv = sum(abs(coherent[key]-resampled[key]) for key in coherent)/2
        self.assertEqual(tv, Q(1, 2))
        self.assertEqual(coherent[(0, 1)] + coherent[(1, 0)], 0)
        self.assertEqual(resampled[(0, 1)] + resampled[(1, 0)], Q(1, 2))
        DETAILS['persistent_model'] = {'joint_law_tv_if_resampled_each_step': str(tv)}

    def test_11_finite_model_error_bound(self):
        total = 0
        kernels = small_kernels()
        for (P, r), (Ph, rh) in product(kernels, repeat=2):
            er, ep = error_constants(P, r, Ph, rh)
            for horizon in range(1, 5):
                bound = horizon*er + Q(horizon*(horizon-1), 2)*ep
                for policy in product((0, 1), repeat=2):
                    v, vh = fixed_value(P, r, policy, horizon), fixed_value(Ph, rh, policy, horizon)
                    self.assertLessEqual(max(abs(a-b) for a, b in zip(v, vh)), bound)
                    total += 1
        DETAILS['model_error_bound'] = {'exact_rational_comparisons': total, 'finite_horizons': [1, 2, 3, 4]}

    def test_12_model_plus_search_error_bound(self):
        total = 0
        kernels = small_kernels()
        for (P, r), (Ph, rh) in product(kernels, repeat=2):
            er, ep = error_constants(P, r, Ph, rh)
            for horizon in range(1, 5):
                # A computationally restricted solver selects the best stationary policy.
                # The comparator is the full finite-horizon (possibly nonstationary) optimum.
                policy = max(product((0, 1), repeat=2), key=lambda p: fixed_value(Ph, rh, p, horizon)[0])
                search_error = optimal_value(Ph, rh, horizon)[0] - fixed_value(Ph, rh, policy, horizon)[0]
                regret = optimal_value(P, r, horizon)[0] - fixed_value(P, r, policy, horizon)[0]
                bound = 2*(horizon*er + Q(horizon*(horizon-1), 2)*ep) + search_error
                self.assertGreaterEqual(search_error, 0)
                self.assertLessEqual(regret, bound)
                total += 1
        DETAILS['planning_bound'] = {'exact_rational_comparisons': total, 'includes_explicit_search_gap': True}

    def test_13_computation_can_improve_without_new_facts(self):
        # An explicit analytic three-state table, not a sampled environment.
        P = (((Q(0), Q(0), Q(1)), (Q(0), Q(1), Q(0))),
             ((Q(0), Q(0), Q(1)), (Q(0), Q(0), Q(1))),
             ((Q(0), Q(0), Q(1)), (Q(0), Q(0), Q(1))))
        r = ((Q(3, 5), Q(0)), (Q(1), Q(1)), (Q(0), Q(0)))
        myopic = (0, 0, 0)
        two_step = (1, 0, 0)
        self.assertEqual(fixed_value(P, r, myopic, 2)[0], Q(3, 5))
        self.assertEqual(fixed_value(P, r, two_step, 2)[0], Q(1))
        DETAILS['computation_without_observation'] = {'same_table_myopic': '3/5', 'same_table_two_step': '1',
                                                     'new_external_observations': 0}

    def test_14_fixed_n_interval_algebra(self):
        n, delta = 64, .05
        radius = math.sqrt(2*math.log(2/delta)/n)
        self.assertAlmostEqual(2*math.exp(-n*radius*radius/2), delta, places=14)
        DETAILS['fixed_n_bound'] = {'n': n, 'delta': delta, 'radius': radius,
                                   'not_an_optional_stopping_or_adoption_rule': True}

    def test_15_sleep_policy_error_bound(self):
        total = 0
        for horizon in range(1, 9):
            for epsilon in (Q(0), Q(1, 100), Q(1, 10), Q(1, 2)):
                # Teacher stays successful; one wrong student action causes absorption.
                teacher = Q(horizon)
                student = sum((1-epsilon)**step for step in range(1, horizon+1))
                loss = teacher-student
                bound = Q(horizon*(horizon+1), 2)*epsilon
                self.assertLessEqual(loss, bound)
                total += 1
        DETAILS['sleep_bound'] = {'exact_rational_comparisons': total, 'uniform_policy_tv_assumed': True}

    def test_16_zero_replay_loss_does_not_cover_omitted_context(self):
        # Training context A: both choose 0, KL=0. Missing context B: teacher 1, student 0.
        context_probability = (Q(1, 2), Q(1, 2))
        teacher = (0, 1)
        student = (0, 0)
        train_kl = 0.
        value_teacher = sum(context_probability[i]*int(teacher[i] == i) for i in (0, 1))
        value_student = sum(context_probability[i]*int(student[i] == i) for i in (0, 1))
        self.assertEqual(value_teacher-value_student, Q(1, 2))
        DETAILS['sleep_coverage_counterexample'] = {'training_kl_on_A': train_kl,
                                                  'whole_distribution_performance_loss': '1/2'}

    def test_17_sleep_amortization(self):
        training_cost, slow, fast = 100, 10, 1
        self.assertLess(11*(slow-fast), training_cost)
        self.assertGreater(12*(slow-fast), training_cost)
        DETAILS['sleep_compute_break_even'] = {'first_profitable_calls': 12, 'quality_equivalence_is_separate': True}


suite = unittest.defaultTestLoader.loadTestsFromTestCase(V3Checks)
run = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
after = {p: sha(ROOT / p) for p in SCOPE['read_only_inputs']}
parameter_unchanged = all(before_hash == net.parameter_digest() for net, before_hash in MODELS)
all_frozen = all(not p.requires_grad for net, _ in MODELS for p in net.parameters())
rng_unchanged = torch.equal(RNG_BEFORE, torch.get_rng_state())
ok = run.wasSuccessful() and BEFORE == after and parameter_unchanged and all_frozen and rng_unchanged
result = {
    'status': 'ALGEBRA_AND_OPERATOR_CHECKS_PASS' if ok else 'CHECK_FAILURE',
    'tests_run': run.testsRun, 'failures': len(run.failures), 'errors': len(run.errors),
    'skipped': len(run.skipped), 'wall_seconds': time.perf_counter()-T0,
    'scope': 'finite algebra, analytic tables, and frozen neural operators; not environment performance',
    'details': DETAILS, 'declared_inputs_unchanged': BEFORE == after,
    'network_instances': len(MODELS), 'parameter_scalars_across_instances': sum(p.numel() for net, _ in MODELS for p in net.parameters()),
    'parameters_unchanged': parameter_unchanged, 'all_parameters_frozen': all_frozen,
    'torch_rng_unchanged': rng_unchanged, 'environment_episodes': 0, 'gradient_steps': 0,
    'optimizer_steps': 0, 'old_test_or_checker_runs': 0, 'game_adaptations': 0,
    'input_sha256_before': BEFORE, 'input_sha256_after': after,
    'failure_traces': [{'test': str(t), 'trace': trace} for t, trace in run.failures + run.errors],
}
with RESULT.open('x', encoding='utf-8', newline='\n') as out:
    json.dump(result, out, ensure_ascii=False, indent=2)
    out.write('\n')
print(json.dumps({key: result[key] for key in ('status', 'tests_run', 'failures', 'errors', 'wall_seconds',
                                             'parameters_unchanged', 'torch_rng_unchanged')}, ensure_ascii=False))
sys.exit(0 if ok else 1)
