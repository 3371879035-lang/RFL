"""First finite V210 mathematical/operator check. No environment or training run."""
from pathlib import Path
from fractions import Fraction
from itertools import combinations, product
import hashlib
import json
import math
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))
import torch
from feedback_program_v210 import AdaptiveFeedbackNet, Fact, RelationLift, TemporalRelation
from feedback_program_v210 import EvidenceBook, PairObservation, rank_candidates
from feedback_program_v210.network import parameter_digest


def rejected(call):
    try:
        call()
    except (ValueError, TypeError):
        return
    raise AssertionError('Expected this invalid external-boundary input to be rejected')


def two_policies():
    net = AdaptiveFeedbackNet((1,), block_size=8, hazard=0.)
    net.grow(1)
    reference = net.snapshot((0., 1.))[0]
    net.set_initial_policy(reference)
    net.observe(Fact(0, (0,), 1, 1, .5, 'observed-behavior'))
    candidate = net.snapshot((0., 1.))[0]
    assert reference.act((0,)) == 0 and candidate.act((0,)) == 1
    return net, reference, candidate


def packet(trial, index, difference, base=1000):
    old, new = (0, 1) if difference == 1 else (1, 0) if difference == -1 else (0, 0)
    return PairObservation(f't{trial.index}-p{index}', base+2*index, base+2*index+1,
                           trial.reference.identity, trial.candidate.identity, old, new)


def conjunctions():
    cards = (2, 3, 2)
    rows = list(product(*(range(c) for c in cards)))
    count = 0
    for order in range(1, 4):
        for structure in combinations(range(3), order):
            lift = RelationLift(cards, structure)
            actual = lift(lift.encode(rows)).tolist()
            expected = [[float(tuple(row[j] for j in structure) == values)
                         for values in lift.values] for row in rows]
            assert actual == expected
            count += len(rows)*len(lift.values)
    return {'exact_activation_entries': count, 'cardinalities': cards}


def frontier():
    net = AdaptiveFeedbackNet((2, 2, 2))
    assert net.grow(2)['added'] == [(0,)]
    first = parameter_digest(net.heads[0])
    assert net.grow(1)['added'] == []
    assert net.grow(4)['added'] == [(1,), (2,)]
    assert net.grow(12)['added'] == [(0, 1), (0, 2), (1, 2)]
    assert net.grow(7)['added'] == []
    result = net.grow(8)
    assert result['added'] == [(0, 1, 2)] and result['next_structure'] is None
    assert parameter_digest(net.heads[0]) == first
    return {'structures': [h.lift.structure for h in net.heads], 'total_cells': 26}


def parity_representation():
    # Artificial exhaustive operator input, NOT a sampled task experiment.
    net = AdaptiveFeedbackNet((2,)*4, hazard=0.)
    net.grow(32)  # All unary and pair relations; no access to the rule below.
    rows = list(product((0, 1), repeat=4))
    for repeat in range(4):
        for row in rows:
            label = row[0] ^ row[2] ^ row[3]
            for action in (0, 1):
                net.observe(Fact(len(net.history), row, action, int(action == label), .5, 'balanced'))
    def accuracies():
        return [sum(p.act(row) == (row[0] ^ row[2] ^ row[3]) for row in rows)/len(rows)
                for p in net.snapshot((0., 1.))]
    before = accuracies()
    assert before == [.5]*10
    old_parameters = [parameter_digest(h) for h in net.heads]
    growth = net.grow(32)  # All four triples, not a supplied correct triple.
    after = accuracies()
    assert len(growth['added']) == 4 and max(after) == 1.
    assert sum(a == 1. for a in after) == 1
    assert [parameter_digest(h) for h in net.heads[:10]] == old_parameters
    assert net.replay_reads == 4*128
    return {'artificial_records': 128, 'before': before, 'after': after,
            'new_structures': growth['added'], 'replay_reads_not_new_samples': net.replay_reads}


def propensity_not_sample_count():
    outputs = []
    for propensity in (.1, 1.):
        net = AdaptiveFeedbackNet((1,), hazard=0.)
        net.grow(1)
        net.observe(Fact(0, (0,), 0, 1, propensity, 'known-behavior'))
        probabilities, support = net.heads[0]([(0,)])
        assert net.heads[0].counts.sum() == 1 and support[0, 0] == 1
        outputs.append(float(probabilities[0, 0, 1]))
    assert outputs == [2/3, 2/3]
    return {'one_observation_predictions_mu_01_mu_1': outputs, 'not_beta_11_1': True}


def scalar_filter():
    head = TemporalRelation((2,), (0,), 2, 2, 7, .13)
    # Independent scalar dictionary recursion; no network readout in expected path.
    branches = [{'start': 0, 'weight': 1., 'counts': {}}]
    max_error = 0.
    for i in range(63):
        if i and i % 7 == 0:
            for b in branches:
                b['weight'] *= .87
            branches.append({'start': i, 'weight': .13, 'counts': {}})
        x, a, y = i % 2, (i//2) % 2, ((i//13)+(i//3)+(i % 2)) % 2
        expected = []
        for action in (0, 1):
            expected.append(sum(b['weight']*(b['counts'].get((x, action, 1), 0)+1)
                                /(sum(b['counts'].get((x, action, z), 0) for z in (0, 1))+2)
                                for b in branches))
        before = head([(x,)])[0][0, :, 1].tolist()
        max_error = max(max_error, *(abs(a-b) for a, b in zip(before, expected)))
        likelihoods = [(b['counts'].get((x, a, y), 0)+1)
                       /(sum(b['counts'].get((x, a, z), 0) for z in (0, 1))+2)
                       for b in branches]
        predictive = sum(b['weight']*p for b, p in zip(branches, likelihoods))
        log_prediction = head.observe(Fact(i, (x,), a, y, .5, 'scalar-fixture'))
        max_error = max(max_error, abs(math.exp(log_prediction)-predictive))
        for b, likelihood in zip(branches, likelihoods):
            b['weight'] = b['weight']*likelihood/predictive
            b['counts'][x, a, y] = b['counts'].get((x, a, y), 0)+1
        max_error = max(max_error, *(abs(a-b['weight'])
                                    for a, b in zip(head.log_weights.exp().tolist(), branches)))
    assert max_error < 5e-14
    assert head.starts == tuple(b['start'] for b in branches)
    assert head.counts[0].sum() == 63
    return {'observations': 63, 'maximum_abs_difference': max_error, 'starts': head.starts}


def temporal_change():
    adaptive = AdaptiveFeedbackNet((1,), actions=1, block_size=8, hazard=.1)
    stationary = AdaptiveFeedbackNet((1,), actions=1, block_size=8, hazard=0.)
    for model in (adaptive, stationary):
        model.grow(1)
    outcomes = [0]*91+[1]*25  # Deliberately NOT aligned with the block boundary.
    for i, y in enumerate(outcomes):
        fact = Fact(i, (0,), 0, y, 1., 'fixed-action')
        adaptive.observe(fact)
        stationary.observe(fact)
    recent_p = float(adaptive.heads[0]([(0,)])[0][0, 0, 1])
    pooled_p = float(stationary.heads[0]([(0,)])[0][0, 0, 1])
    assert recent_p > pooled_p
    assert len(adaptive.history) == 116 and adaptive.heads[0].counts[0].sum() == 116
    assert tuple(f.outcome for f in adaptive.history) == tuple(outcomes)
    return {'artificial_sequence_only': True, 'old_observations': 91, 'new_observations': 25,
            'new_outcome_probability_adaptive': recent_p, 'all_history_pool': pooled_p,
            'archived_facts': len(adaptive.history)}


def predict_before_update():
    head = TemporalRelation((1,), (0,), 1, 2, 2, .2)
    for i in range(2):
        expected = float(head([(0,)])[0][0, 0, 1])
        actual = math.exp(head.observe(Fact(i, (0,), 0, 1, 1., 'fixed')))
        assert abs(actual-expected) < 1e-14
    counts = head.counts.clone()
    before = float(head([(0,)])[0][0, 0, 1])
    assert abs(before-.7) < 1e-14
    assert head.n == 2 and torch.equal(counts, head.counts) and len(head.starts) == 1
    log_p = head.observe(Fact(2, (0,), 0, 0, 1., 'fixed'))
    assert abs(math.exp(log_p)-.3) < 1e-14
    assert abs(float(head.log_weights.exp()[1])-1/3) < 1e-14
    return {'pre_outcome_p_success': before, 'failure_prediction': math.exp(log_p),
            'new_segment_weight_after_failure': float(head.log_weights.exp()[1])}


def common_action_mixture():
    head = TemporalRelation((1,), (0,), 2, 2, 8, 0.)
    head.counts = torch.tensor([[[[20., 0.], [0., 20.]]],
                                [[[0., 20.], [20., 0.]]]], dtype=torch.float64)
    head.log_weights = torch.tensor([math.log(.5)]*2, dtype=torch.float64)
    head.n, head.starts = 1, (0, 1)
    values = head([(0,)])[0][0, :, 1].tolist()
    assert values == [.5, .5]
    assert max(values) < 21/22
    return {'same_action_values': values, 'invalid_average_of_worldwise_maxima': 21/22}


def frozen_snapshot():
    net, reference, candidate = two_policies()
    digest = candidate.identity
    before = candidate([(0,)]).clone()
    parameters = parameter_digest(net.heads[0])
    for i in range(1, 12):
        net.observe(Fact(i, (0,), 0, 1, .5, 'new-behavior'))
    candidate.assert_frozen()
    assert candidate.identity == digest and torch.equal(before, candidate([(0,)]))
    assert parameter_digest(net.heads[0]) == parameters
    assert all(not p.requires_grad for p in net.parameters())
    assert candidate._head.counts.data_ptr() != net.heads[0].counts.data_ptr()
    return {'live_facts': len(net.history), 'snapshot_facts': candidate._head.n,
            'same_parameters': True, 'snapshot_nonalias': True}


def ranking_and_fresh_cutoff():
    net = AdaptiveFeedbackNet((2,), hazard=0.)
    net.grow(2)
    ref = net.snapshot((0., 1.))[0]
    net.set_initial_policy(ref)
    for x in (0, 1):
        for a in (0, 1):
            net.observe(Fact(len(net.history), (x,), a, int(x == a), .5, 'training'))
    candidate = net.snapshot((0., 1.))[0]
    rows = []
    for x in (0, 1):
        actions = [x]*9+[1-x]
        for a in actions:
            rows.append(Fact(100+len(rows), (x,), a, int(a == x), .9 if a == x else .1, 'rank'))
    nomination, detail = rank_candidates([candidate], ref, rows, epsilon=.2)
    assert abs(detail['reference_score']-.5) < 1e-14
    assert abs(detail['candidate_scores'][0]-.9) < 1e-14
    assert nomination.known_through_id == 119
    trial = net.start_trial(nomination, EvidenceBook(.05), horizon=100, switch_cost=0., max_pairs=8)
    rejected(lambda: trial.add_pair(packet(trial, 0, 1, base=118)))
    assert trial.n == 0
    rejected(lambda: rank_candidates([candidate], ref, [net.history[-1]]))
    return {'reference': detail['reference_score'], 'candidate': detail['candidate_scores'][0],
            'selection_cutoff_propagated_even_without_observe': trial.cutoff}


def evidence_algebra():
    _, ref, cand = two_policies()
    trial = EvidenceBook(.01).start(ref, cand, 0, horizon=100, switch_cost=10., max_pairs=8)
    plus, minus = [Fraction(1)]*4, [Fraction(1)]*4
    delta = Fraction(1, 10)
    for i, d in enumerate((1, 0, -1, 1, 1, 0, -1, 0)):
        trial.add_pair(packet(trial, i, d))
        for j, q in enumerate((Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1))):
            plus[j] *= 1+q*(d-delta)/(1+delta)
            minus[j] *= 1+q*(delta-d)/(1-delta)
    assert abs(math.exp(trial.log_e_plus)-float(sum(plus)/4)) < 1e-14
    assert abs(math.exp(trial.log_e_minus)-float(sum(minus)/4)) < 1e-14
    # For a boundary-null +/-1 variable, each one-step expectation is exactly one.
    for q in (Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1)):
        p = (1+delta)/2
        expectation = p*(1+q*(1-delta)/(1+delta))+(1-p)*(1+q*(-1-delta)/(1+delta))
        assert expectation == 1
    return {'e_plus': float(sum(plus)/4), 'e_minus': float(sum(minus)/4),
            'status': trial.status, 'boundary_null_factor_expectation': 1}


def exact_null_enumeration():
    # Pair outcomes independent fair coins: D probabilities 1/4,1/2,1/4.
    # Exact arithmetic, all possible paths, no random/environment sampling.
    qs = (Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1))
    threshold = Fraction(40)  # alpha=.05; first candidate spends .025.
    def walk(depth, positive, negative):
        if sum(positive)/4 >= threshold:
            return Fraction(1)
        if sum(negative)/4 >= threshold or depth == 8:
            return Fraction(0)
        return sum(probability*walk(depth+1,
                   tuple(w*(1+q*d) for w, q in zip(positive, qs)),
                   tuple(w*(1-q*d) for w, q in zip(negative, qs)))
                   for d, probability in ((-1, Fraction(1, 4)), (0, Fraction(1, 2)), (1, Fraction(1, 4))))
    new = walk(0, (Fraction(1),)*4, (Fraction(1),)*4)
    tie = Fraction(math.comb(16, 8), 4**8)
    old = (1-tie)/2
    assert new <= Fraction(1, 40) and new < old
    return {'distribution': 'two independent fair binary outcomes per pair', 'pairs_max': 8,
            'old_positive_mean_accept_probability': float(old),
            'new_anytime_accept_probability': float(new), 'new_exact_fraction': str(new),
            'single_trial_alpha': .025, 'not_empirical_task_evidence': True}


def early_stop_and_unresolved():
    _, ref, cand = two_policies()
    detail = {}
    for name, d in (('strong_positive', 1), ('all_equal', 0), ('strong_negative', -1)):
        trial = EvidenceBook(.05).start(ref, cand, 0, 100, 0., 16)
        for i in range(16):
            trial.add_pair(packet(trial, i, d))
            if trial.status != 'continue':
                break
        detail[name] = {'pairs': trial.n, 'status': trial.status}
        rejected(lambda: trial.add_pair(packet(trial, 99, d)))
    assert detail['strong_positive']['status'] == 'adopt' and detail['strong_positive']['pairs'] < 16
    assert detail['strong_negative']['status'] == 'not_worth_cost'
    assert detail['all_equal'] == {'pairs': 16, 'status': 'unresolved_keep'}
    return detail


def costs_and_error_budget():
    _, ref, cand = two_policies()
    book = EvidenceBook(.05)
    t1 = book.start(ref, cand, 0, 10, 10., 8)
    assert t1.status == 'cost_dominates' and t1.n == 0
    t2 = book.start(ref, ref, 0, 100, 0., 8)
    assert t2.status == 'same_snapshot'
    t3 = book.start(ref, cand, 0, 100, 10., 2, pair_cost=.3)
    t3.add_pair(packet(t3, 0, 0))
    t3.add_pair(packet(t3, 1, 0))
    assert t3.summary()['pair_cost_spent'] == .6
    assert abs(sum(t.alpha for t in book.trials)-.05*3/4) < 1e-15
    return {'trial_alphas': [t.alpha for t in book.trials], 'threshold': t3.delta,
            'pair_cost_spent': t3.summary()['pair_cost_spent']}


def no_evidence_reuse():
    _, ref, cand = two_policies()
    book = EvidenceBook(.05)
    t1 = book.start(ref, cand, 0, 100, 0., 1)
    t1.add_pair(packet(t1, 0, 0))
    t2 = book.start(ref, cand, 0, 100, 0., 1)
    rejected(lambda: t2.add_pair(packet(t2, 0, 1)))
    assert t2.n == 0 and book.last_observation_id == 1001
    t2.add_pair(packet(t2, 1, 0))
    assert len(book.used_observations) == 4 and len(book.used_pairs) == 2
    return {'distinct_observation_ids': sorted(book.used_observations), 'second_cutoff': t2.cutoff}


def feedback_closed_loop():
    net = AdaptiveFeedbackNet((2, 2), block_size=8, hazard=.1)
    net.grow(2)
    net.set_initial_policy(net.snapshot((0., 1.))[0])
    net.observe(Fact(0, (0, 0), 1, 1, .5, 'initial-observation'))
    reference_id = net.active.identity
    parameters = parameter_digest(net.heads[0])
    book = EvidenceBook(.05)
    candidate = net.snapshot((0., 1.))[0]
    trial = net.start_trial(net.nominate(candidate), book, horizon=100, switch_cost=0., max_pairs=2, epsilon=0.)
    for i in range(2):
        facts = [Fact(10+2*i+j, (0, 0), p.act((0, 0)), 0, 1., p.identity)
                 for j, p in enumerate((trial.reference, trial.candidate))]
        net.record_trial_pair(trial, *facts, f'first-{i}')
    first = net.respond_to_trial(trial, expansion_cell_budget=2)
    assert first['status'] == 'unresolved_keep' and net.active.identity == reference_id
    assert first['growth']['added'] == [(1,)] and len(net.history) == 5
    rejected(lambda: net.respond_to_trial(trial, expansion_cell_budget=2))
    candidate2 = net.snapshot((0., 1.))[0]
    trial2 = net.start_trial(net.nominate(candidate2), book, horizon=100, switch_cost=0., max_pairs=16, epsilon=0.)
    for i in range(16):
        facts = [Fact(100+2*i+j, (0, 0), p.act((0, 0)), j, 1., p.identity)
                 for j, p in enumerate((trial2.reference, trial2.candidate))]
        net.record_trial_pair(trial2, *facts, f'second-{i}')
        if trial2.status != 'continue':
            break
    second = net.respond_to_trial(trial2)
    assert second['status'] == 'adopt' and net.active.identity == candidate2.identity
    assert parameter_digest(net.heads[0]) == parameters
    assert len(net.history) == 5+2*trial2.n
    return {'artificial_input_only': True, 'first_status': first['status'],
            'growth_after_unresolved': first['growth']['added'], 'second_status': second['status'],
            'second_pairs': trial2.n, 'all_trial_facts_preserved': len(net.history)}


def schema_and_frozen_boundaries():
    net, ref, cand = two_policies()
    rejected(lambda: net.observe(Fact(0, (0,), 1, 1, .5, 'duplicate')))
    rejected(lambda: net.observe(Fact(1, (2,), 1, 1, .5, 'bad-context')))
    rejected(lambda: Fact(1, (0,), 1, 1, .5, 'bad', hidden_cause=1))
    assert len(net.history) == 1
    book = EvidenceBook(.05)
    trial = net.start_trial(net.nominate(cand), book, horizon=100, switch_cost=0., max_pairs=8)
    bad = PairObservation('bad-id', 50, 51, 'foreign', cand.identity, 0, 1)
    rejected(lambda: trial.add_pair(bad))
    assert trial.n == 0
    with torch.no_grad():
        cand._head.counts[0, 0, 0, 0] += 1
    rejected(lambda: trial.add_pair(packet(trial, 0, 1)))
    return {'duplicate_and_hidden_schema_rejected': True, 'modified_frozen_snapshot_rejected': True}


CHECKS = [conjunctions, frontier, parity_representation, propensity_not_sample_count,
          scalar_filter, temporal_change, predict_before_update, common_action_mixture,
          frozen_snapshot, ranking_and_fresh_cutoff, evidence_algebra, exact_null_enumeration,
          early_stop_and_unresolved, costs_and_error_budget, no_evidence_reuse,
          feedback_closed_loop, schema_and_frozen_boundaries]


def main():
    started = time.perf_counter()
    contract = json.loads((OUT/'contract.json').read_text(encoding='utf-8'))
    before = {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
              for path in contract['input_sha256']}
    assert before == contract['input_sha256']
    torch.set_num_threads(2)
    rng = torch.get_rng_state().clone()
    results = []
    for check in CHECKS:
        t = time.perf_counter()
        try:
            detail = check()
            result = {'name': check.__name__, 'status': 'PASS', 'detail': detail}
        except Exception:
            result = {'name': check.__name__, 'status': 'FAIL', 'traceback': traceback.format_exc()}
        result['seconds'] = time.perf_counter()-t
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    after = {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in before}
    unchanged = before == after
    rng_unchanged = torch.equal(rng, torch.get_rng_state())
    results.append({'name': 'frozen_inputs_and_torch_rng',
                    'status': 'PASS' if unchanged and rng_unchanged else 'FAIL',
                    'detail': {'input_files': len(before), 'input_bytes_unchanged': unchanged,
                               'torch_rng_unchanged': rng_unchanged}})
    result = {'schema': 'v210-finite-mathematical-operator-check-v1',
              'checks': results, 'passed': sum(x['status'] == 'PASS' for x in results),
              'failed': sum(x['status'] != 'PASS' for x in results),
              'environment_episodes': 0, 'gradient_or_optimizer_updates': 0,
              'v209_reruns': 0, 'artificial_input_not_performance_evidence': True,
              'wall_seconds': time.perf_counter()-started}
    with (OUT/'checks_result.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return int(result['failed'] > 0)


if __name__ == '__main__':
    raise SystemExit(main())
