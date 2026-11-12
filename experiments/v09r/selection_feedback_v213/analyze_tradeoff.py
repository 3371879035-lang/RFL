"""Post-hoc arithmetic only; no environment or learner execution."""
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import statistics

HERE = Path(__file__).resolve().parent
inputs = ['raw.jsonl.gz', 'native_result.json', 'stored_review.json', 'experiment.py', 'review.py', 'contract.json']
pins = {name: hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in inputs}
with (HERE/'analysis_claim.json').open('x', encoding='utf-8') as f:
    json.dump({'utc': datetime.now(timezone.utc).isoformat(), 'input_sha256': pins,
               'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, f, indent=2)

expectations = {}
actions = 0
feature_observations = 0
with gzip.open(HERE/'raw.jsonl.gz', 'rt', encoding='utf-8') as stream:
    for line in stream:
        r = json.loads(line)
        if r['kind'] != 'episode': continue
        actions += 1
        feature_observations += len(r['public']['context'])
        if r['phase'] != 1: continue
        family, seed, arm = r['family'], r['seed'], r['arm']
        x = r['public']['context']
        desired = x[seed % 4] if family == 'single' else x[0]^x[1]^x[2]
        correct = .58 if family == 'small_gap' else .9
        value = sum(p*(.5 if family == 'noise' else correct if a == desired else 1-correct)
                    for a, p in enumerate(r['probabilities']))
        key = (family,seed,arm)
        expectations[key] = expectations.get(key, 0.)+value

native = json.loads((HERE/'native_result.json').read_text())
lookup = {(r['family'],r['seed'],r['arm']):r for r in native['runs']}
table = []
for family in ['single','triple','small_gap','noise']:
    actual_trial, predictable_trial, selected, actual_whole = [], [], [], []
    good_counts = {a:0 for a in ['locked_ips','feedback_mix']}
    for seed in range(16):
        a = lookup[(family,seed,'feedback_mix')]; b = lookup[(family,seed,'locked_ips')]
        actual_trial.append(a['trial_successes']-b['trial_successes'])
        predictable_trial.append(expectations[(family,seed,'feedback_mix')]-expectations[(family,seed,'locked_ips')])
        selected.append(a['proposal_expected_value_posthoc']-b['proposal_expected_value_posthoc'])
        actual_whole.append(a['trial_successes']+a['proposal_eval_successes']-b['trial_successes']-b['proposal_eval_successes'])
        best = .5 if family=='noise' else .564 if family=='small_gap' else .82
        for arm,row in [('locked_ips',b),('feedback_mix',a)]:
            good_counts[arm] += abs(row['proposal_expected_value_posthoc']-best) < 1e-12
    trial_gap = statistics.mean(predictable_trial)
    candidate_gap = statistics.mean(selected)
    table.append({'family':family, 'new_minus_lock_actual_trial_successes_per_run':statistics.mean(actual_trial),
                  'new_minus_lock_predictable_trial_utility_per_run':trial_gap,
                  'new_minus_lock_selected_policy_expected_value':candidate_gap,
                  'new_minus_lock_actual_total_288_successes_per_run':statistics.mean(actual_whole),
                  'posthoc_payback_future_episodes':max(0.,-trial_gap)/candidate_gap if candidate_gap>1e-12 else None,
                  'selected_best_count_out_of_16':good_counts})

correction = {
    'schema':'v213-execution-semantics-clarification',
    'original_declared_and_reported_steps':native['steps'],
    'actual_action_outcome_interactions':actions,
    'context_field_observations':feature_observations,
    'reason':'experiment.execute samples one action and one outcome per episode. Four categorical input fields are not four sequential environment transitions.',
    'correct_interpretation':'55296 one-step contextual decisions, each observing four fields. Not 221184 environment transitions.',
    'original_sources_and_results_preserved':True,
    'effect_on_success_rates_and_paired_results':'none; only the step/feature cost label was wrong',
    'review_limitation':'initial stored review verified hardcoded 4x counters, not the sequential-step semantics',
    'new_environment_runs':0,
}
assert actions==55296 and feature_observations==221184
with (HERE/'execution_semantics_correction.json').open('x', encoding='utf-8') as f:
    json.dump(correction, f, indent=2)
with (HERE/'tradeoff_analysis.json').open('x', encoding='utf-8') as f:
    json.dump({'table':table, 'assumptions':'Post-hoc known environment law, unchanged final policy and future rule, no CPU utility conversion. Descriptive only, not guaranteed payback.',
               'new_environment_runs':0, 'input_sha256':pins}, f, indent=2)
print(json.dumps({'corrected_action_outcome_interactions':actions,'table':table}))
