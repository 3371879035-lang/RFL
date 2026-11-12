"""First-run mathematical/nn checks. All supplied facts are labelled synthetic."""
from pathlib import Path
import hashlib
import itertools
import json
import math
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
import torch
from feedback_program_v210 import AdaptiveFeedbackNet, EvidenceBook
from feedback_program_v210.network import Fact, FrozenCandidate, TemporalRelation, parameter_digest
from feedback_program_v210.evidence import PairObservation
from feedback_program_v213 import BehaviorBank, TrialLedger, ShadowRelationProbe, certified_trial

CONTEXTS = tuple(itertools.product((0, 1), repeat=4))


def analytic_policies():
    """Nine precompiled hypotheses, not experience collected from the test world."""
    owner = object()
    definitions = [(), (0,), (1,), (2,), (3,), (0, 1), (0, 2), (1, 2), (0, 1, 2)]
    policies = []
    for structure in definitions:
        h = TemporalRelation((2,)*4, (0, 1, 2, 3), 2, 2, 32, 0.)
        i = 0
        for _ in range(2):
            for row in CONTEXTS:
                desired = sum(row[j] for j in structure) % 2
                for action in range(2):
                    h.observe(Fact(i, row, action, int(action == desired), .5, 'synthetic-hypothesis'))
                    i += 1
        policies.append(FrozenCandidate(h, (0., 1.), i-1, owner))
    return policies


def raises(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError('Expected protocol rejection')


def run():
    torch.set_num_threads(1)
    rng = torch.get_rng_state().clone()
    policies = analytic_policies()
    ref = policies[0]
    parameter_hashes = [parameter_digest(p) for p in policies]
    rows = []

    def check(name, function):
        start = time.perf_counter()
        try:
            detail = function()
            rows.append({'name': name, 'ok': True, 'detail': detail, 'seconds': time.perf_counter()-start})
        except Exception:
            rows.append({'name': name, 'ok': False, 'traceback': traceback.format_exc(),
                         'seconds': time.perf_counter()-start})

    def exact_equivalence():
        altered = TemporalRelation((2,)*4, (0, 1, 2, 3), 2, 2, 32, 0.)
        for i in range(256):
            x = CONTEXTS[i % 16]
            a = (i//16) % 2
            altered.observe(Fact(i, x, a, int(a == 0), .5, 'synthetic'))
        same = FrozenCandidate(altered, ref.goal, 255, ref._owner)
        assert same.identity != ref.identity
        bank = BehaviorBank(ref, [same, ref])
        assert len(bank.policies) == 1
        ledger = TrialLedger(8.)
        assert ledger.start(bank, 10, 8., 255) is None and ledger.reserved_risk == 0
        book = EvidenceBook(.05)
        from feedback_program_v210.network import Nomination
        assert certified_trial(Nomination(same, ref.identity, 255), ref, book,
                               horizon=100, switch_cost=0, max_pairs=8) is None
        assert book.issued == 0
        raises(lambda: BehaviorBank(ref, policies, context_budget=15))
        assert len(BehaviorBank(ref, policies, epsilon=1).policies) == 1
        return {'different_snapshot_same_behavior': True, 'alpha_issued': book.issued}
    check('complete_equivalence_not_snapshot_hash', exact_equivalence)

    bank = BehaviorBank(ref, policies)
    def duplicate_invariance():
        duplicate = BehaviorBank(ref, list(reversed(policies))+[policies[2]]*7)
        assert bank.signatures == duplicate.signatures
        a = TrialLedger(16.).start(bank, 20, 16., 63)
        b = TrialLedger(16.).start(duplicate, 20, 16., 63)
        assert torch.equal(a(list(CONTEXTS)), b(list(CONTEXTS)))
        return {'classes': len(bank.policies), 'complete_contexts': len(bank.contexts)}
    check('duplicate_and_input_order_invariance', duplicate_invariance)

    def propensity_identity_and_scalar_update():
        lease = TrialLedger(4.).start(bank, 10, 4., 63)
        receipt = lease.offer(CONTEXTS[7], 64)
        before = [1/len(bank.policies)]*len(bank.policies)
        fact = Fact(64, receipt.context, 1, 0, receipt.probabilities[1], lease.identity)
        raises(lambda: lease.observe(receipt, Fact(64, fact.context, 1, 0, .5, lease.identity)))
        result = lease.observe(receipt, fact)
        losses = [p[1]/fact.propensity for p in receipt.expert_probabilities]
        weights = [w*math.exp(-lease.eta*l) for w, l in zip(before, losses)]
        total = math.fsum(weights)
        assert max(abs(w/total-v) for w, v in zip(weights, result['after_weights'])) < 1e-14
        raises(lambda: lease.observe(receipt, fact))
        raises(lambda: lease.offer(fact.context, 64))
        raises(lambda: lease.finish())
        return {'max_scalar_weight_error': max(abs(w/total-v) for w, v in zip(weights, result['after_weights']))}
    check('actual_propensity_one_use_and_scalar_neural_update', propensity_identity_and_scalar_update)

    def exact_ips_and_variance():
        lease = TrialLedger(8.).start(bank, 20, 8., 63)
        receipt = lease.offer(CONTEXTS[5], 64)
        mu, experts = receipt.probabilities, receipt.expert_probabilities
        true_losses = (.8, .2)
        max_error = 0.
        for p in experts:
            estimate = math.fsum(mu[a]*p[a]*true_losses[a]/mu[a] for a in range(2))
            truth = math.fsum(p[a]*true_losses[a] for a in range(2))
            max_error = max(max_error, abs(estimate-truth))
        assert max_error < 1e-14
        second = math.fsum(math.fsum(p[a]**2 for p in experts)/len(experts)/mu[a] for a in range(2))
        assert second <= 2/lease.rho+1e-14
        return {'expectation_error': max_error, 'second_moment_upper': second, 'proved_bound': 2/lease.rho}
    check('ips_expectation_and_second_moment_exact_enumeration', exact_ips_and_variance)

    def tv_and_lifetime():
        ledger = TrialLedger(8.)
        lease = ledger.start(bank, 20, 8., 63)
        maximum_excess = 0.
        for i in range(20):
            receipt = lease.offer(CONTEXTS[i % 16], 64+i)
            for utility in itertools.product((0., 1.), repeat=2):
                regret = math.fsum((r-p)*u for r, p, u in zip(receipt.reference_probabilities,
                                                           receipt.probabilities, utility))
                maximum_excess = max(maximum_excess, regret-receipt.total_variation)
            lease.observe(receipt, Fact(64+i, receipt.context, i % 2, (i//2) % 2,
                                        receipt.probabilities[i % 2], lease.identity))
        nomination = lease.finish()
        assert maximum_excess < 1e-14 and lease.total_variation_spent <= 8.+1e-12
        assert nomination.known_through_id == 83 and lease.closed
        raises(lambda: lease.offer(CONTEXTS[0], 84))
        raises(lambda: ledger.start(bank, 20, 1., 83))
        assert ref.identity == bank.reference.identity
        return {'tv_spent': lease.total_variation_spent, 'reserved_risk': ledger.reserved_risk,
                'incumbent_unchanged': True, 'synthetic_observations': 20}
    check('tv_bound_all_extreme_utilities_and_no_budget_reset', tv_and_lifetime)

    def new_certification_cutoff():
        from feedback_program_v210.network import Nomination
        book = EvidenceBook(.05)
        candidate = policies[-1]
        trial = certified_trial(Nomination(candidate, ref.identity, 999), ref, book,
                                horizon=100, switch_cost=0., max_pairs=12)
        assert trial.cutoff == 999 and book.issued == 1
        raises(lambda: trial.add_pair(PairObservation('old', 998, 999, ref.identity, candidate.identity, 0, 1)))
        for i in range(12):
            if trial.status != 'continue':
                break
            trial.add_pair(PairObservation(f'new{i}', 1000+2*i, 1001+2*i,
                                           ref.identity, candidate.identity, 0, 1))
        assert trial.status == 'adopt'
        return {'synthetic_new_pairs': trial.n, 'status': trial.status, 'old_data_rejected': True}
    check('temporary_trial_is_not_permanent_adoption', new_certification_cutoff)

    def structure_probe(correct_order):
        net = AdaptiveFeedbackNet((2,)*4, hazard=0.)
        net.grow(32)
        rule = (0, 1, 2) if correct_order else (0,)
        history = []
        def fact(i):
            x = CONTEXTS[i % 16]
            a = (i//16) % 2
            return Fact(i, x, a, int(a == sum(x[j] for j in rule) % 2), .5, 'synthetic-probe')
        for i in range(128):
            f = fact(i); history.append(f); net.observe(f)
        structure = (0, 1) if correct_order else (0,)
        baseline = next(p for p in net.snapshot((0., 1.)) if p._head.lift.structure == structure)
        probe = ShadowRelationProbe(baseline, (0, 1, 2), history, 256)
        hashes = (parameter_digest(probe.baseline), parameter_digest(probe.shadow))
        scalar = 0.
        for i in range(128, 384):
            f = fact(i)
            output = probe.observe(f)
            scalar += math.log(output['shadow_prediction'][f.outcome])-math.log(output['baseline_prediction'][f.outcome])
        candidate, result = probe.finish()
        assert result['candidate_eligible'] == correct_order
        assert abs(scalar-result['log_gain']) < 1e-12
        assert hashes == (parameter_digest(probe.baseline), parameter_digest(probe.shadow))
        assert len(net.heads) == 10  # eligibility never silently writes into active net
        assert probe.baseline.n == probe.shadow.n == 384
        assert len(net.history) == 128
        return result
    check('three_way_relation_probe_can_become_candidate', lambda: structure_probe(True))
    check('simple_rule_does_not_force_structure_growth', lambda: structure_probe(False))

    def analytic_parameters_stay_fixed():
        assert parameter_hashes == [parameter_digest(p) for p in policies]
        assert all(not p.requires_grad for model in policies for p in model.parameters())
        assert torch.equal(rng, torch.get_rng_state())
        return {'gradient_updates': 0, 'torch_rng_unchanged': True}
    check('parameters_and_rng_unchanged', analytic_parameters_stay_fixed)
    return {'schema': 'v213-mathematical-checks', 'checks': rows,
            'passed': sum(r['ok'] for r in rows), 'failed': sum(not r['ok'] for r in rows),
            'actual_environment_episodes': 0, 'facts_are_synthetic': True}


if __name__ == '__main__':
    result = run()
    with (Path(__file__).resolve().parent/'check_result.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'passed': result['passed'], 'failed': result['failed']}))
    sys.exit(int(result['failed'] != 0))
