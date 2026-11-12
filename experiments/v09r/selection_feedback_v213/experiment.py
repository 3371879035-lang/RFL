"""Finite actual interactions for allocator isolation, not full learner training."""
from pathlib import Path
from dataclasses import asdict
from fractions import Fraction
import gzip
import hashlib
import itertools
import json
import math
import random
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'src'))
import torch
from feedback_program_v210 import Fact
from feedback_program_v210.network import parameter_digest
from feedback_program_v213 import BehaviorBank, TrialLedger
from check_model import analytic_policies, CONTEXTS

FAMILIES = ('single', 'triple', 'small_gap', 'noise')
ARMS = ('locked_ips', 'uniform_mix', 'feedback_mix')


def tape(family, seed, phase, slot):
    number = (((FAMILIES.index(family)*100+seed)*3+phase)*1000+slot)
    rng = random.Random(213000000000+number)
    return tuple(rng.randrange(2) for _ in range(4)), rng.random(), rng.random()


def hidden_probability(family, seed, x, action):
    desired = x[seed % 4] if family == 'single' else (x[0]^x[1]^x[2])
    if family == 'noise':
        return .5
    correct = .58 if family == 'small_gap' else .9
    return correct if action == desired else 1.-correct


def neural_probs(policy, context, epsilon=.2):
    chosen = policy.act(context)
    return tuple((1.-epsilon)*int(a == chosen)+epsilon/2 for a in range(2))


def true_value(policy, family, seed):
    return math.fsum(math.fsum(neural_probs(policy, x)[a]*hidden_probability(family, seed, x, a)
                               for a in range(2)) for x in CONTEXTS)/len(CONTEXTS)


def main():
    contract = json.loads((HERE/'contract.json').read_text(encoding='utf-8'))
    before = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in contract['input_sha256']}
    assert before == contract['input_sha256']
    torch.set_num_threads(1)
    rng_state = torch.get_rng_state().clone()
    policies = analytic_policies()
    parameters = [parameter_digest(p) for p in policies]
    reference = policies[0]
    bank = BehaviorBank(reference, policies)
    rows = []
    count = 0
    with (HERE/'raw.jsonl.gz').open('xb') as binary, gzip.GzipFile(fileobj=binary, mode='wb', mtime=0) as raw:
        def emit(kind, **data):
            nonlocal count
            raw.write((json.dumps({'kind': kind, **data}, sort_keys=True, separators=(',', ':'),
                                  allow_nan=False)+'\n').encode())
            count += 1
        emit('setup', bank=bank.summary(), definitions=[[], [0], [1], [2], [3], [0,1], [0,2], [1,2], [0,1,2]],
             parameters=parameters, input_sha256=before, constructor_facts_are_synthetic=True,
             policy_ids=[p.identity for p in policies], reference=reference.identity)
        for family in FAMILIES:
            for seed in range(16):
                for arm in ARMS:
                    started, cpu = time.perf_counter(), time.process_time()
                    event_id = 64
                    totals = {0: 0, 1: 0, 2: 0}
                    def execute(phase, slot, probabilities, policy_id, **extra):
                        nonlocal event_id
                        x, au, ou = tape(family, seed, phase, slot)
                        action = int(au < probabilities[1])
                        outcome = int(ou < hidden_probability(family, seed, x, action))
                        fact = Fact(event_id, x, action, outcome, probabilities[action], policy_id)
                        emit('episode', family=family, seed=seed, arm=arm, phase=phase, slot=slot,
                             public=asdict(fact), probabilities=probabilities, action_u=au, outcome_u=ou, **extra)
                        event_id += 1
                        totals[phase] += outcome
                        return fact
                    ranking = []
                    for slot in range(32):
                        x = tape(family, seed, 0, slot)[0]
                        ranking.append(execute(0, slot, neural_probs(reference, x), reference.identity))
                    scores = []
                    for p in bank.policies:
                        terms = [Fraction(neural_probs(p, f.context)[f.action]).limit_denominator(10)
                                 *f.outcome/Fraction(f.propensity).limit_denominator(10) for f in ranking]
                        scores.append(sum(terms, Fraction())/32)
                    selected_index = max(range(len(scores)), key=lambda j: scores[j])
                    ledger = TrialLedger(51.2)
                    lease = ledger.start(bank, 128, 51.2, 95) if arm == 'feedback_mix' else None
                    emit('begin_trial', family=family, seed=seed, arm=arm, selected_index=selected_index,
                         ranking_scores=[str(s) for s in scores], lease_id=lease.identity if lease else None)
                    tv_spent = 0.
                    for slot in range(128):
                        x = tape(family, seed, 1, slot)[0]
                        base = neural_probs(reference, x)
                        if arm == 'feedback_mix':
                            receipt = lease.offer(x, event_id)
                            fact = execute(1, slot, receipt.probabilities, lease.identity,
                                           receipt=asdict(receipt), before_weights=torch.softmax(lease.log_weights, 0).tolist())
                            update = lease.observe(receipt, fact)
                            emit('update', family=family, seed=seed, arm=arm, slot=slot, **update)
                            tv_spent += receipt.total_variation
                        else:
                            if arm == 'locked_ips':
                                q = neural_probs(bank.policies[selected_index], x)
                            else:
                                vectors = [neural_probs(p, x) for p in bank.policies]
                                q = tuple(math.fsum(v[a] for v in vectors)/len(vectors) for a in range(2))
                            mu = tuple(.5*b+.5*v for b, v in zip(base, q))
                            tv_spent += math.fsum(abs(m-b) for m, b in zip(mu, base))/2
                            execute(1, slot, mu, arm+'-mixture')
                    if lease is not None:
                        nomination = lease.finish()
                        proposed = nomination.candidate
                        lease_summary = lease.summary()
                    else:
                        # Uniform control has no evidence-based favorite: predeclared first class.
                        proposed = bank.policies[selected_index if arm == 'locked_ips' else 0]
                        lease_summary = None
                    emit('nomination', family=family, seed=seed, arm=arm, proposed=proposed.identity,
                         lease=lease_summary, tv_spent=tv_spent, permanent_adoption=False)
                    for slot in range(128):
                        x = tape(family, seed, 2, slot)[0]
                        execute(2, slot, neural_probs(proposed, x), proposed.identity)
                    assert event_id == 352 and tv_spent <= 51.2+1e-10
                    row = {'family': family, 'seed': seed, 'arm': arm, 'episodes': 288, 'steps': 1152,
                           'warm_successes': totals[0], 'trial_successes': totals[1],
                           'proposal_eval_successes': totals[2], 'proposed': proposed.identity,
                           'proposal_expected_value_posthoc': true_value(proposed, family, seed),
                           'tv_spent': tv_spent, 'permanent_adoptions': 0,
                           'wall_seconds': time.perf_counter()-started, 'cpu_seconds': time.process_time()-cpu}
                    rows.append(row)
                    emit('run_end', **row)
                print(f'{family} seed {seed} complete', flush=True)
        assert parameters == [parameter_digest(p) for p in policies]
        assert torch.equal(rng_state, torch.get_rng_state())
        after = {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in before}
        assert after == before
        emit('end', runs=len(rows), episodes=sum(r['episodes'] for r in rows),
             steps=sum(r['steps'] for r in rows), parameter_unchanged=True, input_unchanged=True)
    result = {'runs': rows, 'records': count, 'episodes': sum(r['episodes'] for r in rows),
              'steps': sum(r['steps'] for r in rows), 'gradient_updates': 0,
              'raw_sha256': hashlib.sha256((HERE/'raw.jsonl.gz').read_bytes()).hexdigest(),
              'constructor_facts_are_synthetic': True, 'input_unchanged': True}
    with (HERE/'native_result.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, allow_nan=False)


if __name__ == '__main__':
    main()
