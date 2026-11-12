"""Read-only mechanism diagnosis; no model, task import, or environment execution.

Recent-only means are a post-result counterfactual calculation, not a new trial.
"""
from collections import defaultdict, Counter
import gzip
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent


def context(ep, window):
    now = ep['steps'][-1]['observation']
    previous = [s['observation'] for s in ep['steps'][:-1]]
    z = list(now)
    for j in range(window):
        z += previous[-1-j] + [1.] if j < len(previous) else [0., 0., 0.]
    return tuple(z)


def main():
    discovered, trials, candidate_actions, prior_actions = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    aliased = {2: defaultdict(set), 6: defaultdict(set)}
    with gzip.open(HERE / 'evidence' / 'episodes.jsonl.gz', 'rt', encoding='utf-8') as f:
        for line in f:
            ep = json.loads(line)
            seed = int(ep['run'].split(':')[1])
            if ep['family'] == 'long_history' and ep['role'] == 'discovery':
                for window in aliased:
                    aliased[window][ep['cue']].add(context(ep, window))
            if ep['family'] != 'stochastic_reversal':
                continue
            key = (seed, ep['cycle'])
            if ep['role'] == 'discovery':
                discovered[key].append(ep)
            elif ep['run'].endswith(':full') and ep['role'].startswith('trial_'):
                trials[key].append(ep)
                (candidate_actions if ep['role'] == 'trial_candidate' else prior_actions)[key].append(ep['steps'][0]['action'])
    rows = [json.loads(line) for line in (HERE / 'evidence' / 'progress.jsonl').read_text(encoding='utf-8').splitlines()]
    full = {(r['seed'], r['cycle']): r for r in rows if r['family'] == 'stochastic_reversal' and r['variant'] == 'full'}
    diagnostics = []
    for seed in range(24):
        old = discovered[seed, 0] + trials[seed, 0]
        recent = discovered[seed, 1]
        def means(episodes):
            buckets = defaultdict(list)
            for ep in episodes:
                root = ep['steps'][0]
                buckets[root['action']].append(root['contribution'][0])
            return [statistics.mean(buckets[a]) for a in range(3)], [len(buckets[a]) for a in range(3)]
        all_means, counts = means(old + recent)
        recent_means, recent_counts = means(recent)
        pooled_choice = max(range(3), key=lambda a: (all_means[a], -a))
        recent_choice = max(range(3), key=lambda a: (recent_means[a], -a))
        observed = candidate_actions[seed, 1]
        assert len(set(observed)) == 1
        # Exact equality of action choices is checked separately: floating near-ties can differ.
        diagnostics.append(dict(seed=seed, old_root_records=len(old), recent_root_records=len(recent),
                                pooled_means=all_means, pooled_counts=counts, recent_means=recent_means,
                                recent_counts=recent_counts, pooled_argmax=pooled_choice,
                                observed_candidate_action=observed[0], recent_only_counterfactual_action=recent_choice,
                                adopted=full[seed, 1]['adopted'], true_delta=full[seed, 1]['analyst_expected_trial_delta']))
    aliases = {}
    for window, groups in aliased.items():
        aliases[str(window)] = dict(cue0_contexts=len(groups[0]), cue1_contexts=len(groups[1]),
                                   shared_contexts=len(groups[0] & groups[1]))
    branch = [r for r in rows if r['family'] == 'branching' and r['variant'] == 'mean_successor']
    stochastic_full = list(full.values())
    output = dict(status='STORED_DIAGNOSIS_COMPLETE', environment_calls=0, model_forward_calls=0,
                  history_aliasing=aliases,
                  branching_degraded_candidates=sum(r['analyst_expected_trial_delta'] < -1e-12 for r in branch),
                  branching_degraded_candidates_adopted=sum(r['adopted'] and r['analyst_expected_trial_delta'] < -1e-12 for r in branch),
                  stochastic_full_harmful_adoptions=sum(r['adopted'] and r['analyst_expected_trial_delta'] < -1e-12 for r in stochastic_full),
                  stochastic_full_behaviorally_neutral_adoptions=sum(r['adopted'] and abs(r['analyst_expected_trial_delta']) < 1e-12 for r in stochastic_full),
                  stochastic_full_beneficial_candidates_rejected=sum(not r['adopted'] and r['analyst_expected_trial_delta'] > 1e-12 for r in stochastic_full),
                  reversal_observed_action_counts=dict(Counter(r['observed_candidate_action'] for r in diagnostics)),
                  reversal_recent_only_counterfactual_counts=dict(Counter(r['recent_only_counterfactual_action'] for r in diagnostics)),
                  pooled_argmax_agrees_with_native=sum(r['pooled_argmax'] == r['observed_candidate_action'] for r in diagnostics),
                  records=diagnostics,
                  limitation='Recent-only calculation is exploratory, uses the known cycle boundary, and is not a tested adaptive forgetting mechanism or measured deployment gain.')
    with (HERE / 'diagnostics.json').open('x', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    print(json.dumps({k: v for k, v in output.items() if k != 'records'}))


if __name__ == '__main__':
    main()
