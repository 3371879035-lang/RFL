"""Post-outcome algebraic diagnosis of stored V218 forecasts; no model execution.

This was written AFTER seeing the main results. Decompositions are descriptive,
not new policy ablations, and do not create additional environment observations.
"""
import gzip
import hashlib
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def kernel(family, spec, checkpoint, x):
    desired = x[spec['payload']]
    if family == 'changed_novel':
        desired ^= 1
    elif family == 'selective_change' or (family == 'selective_return' and checkpoint < 128):
        desired ^= x[spec['condition']]
    if family == 'mixed_reliability':
        rate = .98 if x[spec['condition']] == 0 else .6
        return [rate if a == desired else 1-rate for a in range(2)]
    return [.5 if family == 'noise' else .9 if a == desired else .1 for a in range(2)]


def main():
    review_path = HERE/'stored_review.json'
    review = json.loads(review_path.read_text(encoding='utf-8'))
    sources = {'stored_review.json': hashlib.sha256(review_path.read_bytes()).hexdigest()}
    rows = []
    max_error = 0.
    record_count = 0
    for folder in sorted((HERE/'shards').iterdir()):
        source = folder/'raw.jsonl.gz'
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        native = json.loads((folder/'native_result.json').read_text(encoding='utf-8'))
        assert digest == native['raw_sha256']
        sources[source.relative_to(HERE).as_posix()] = digest
        accum = {}
        with gzip.open(source, 'rt', encoding='utf-8') as stream:
            for line in stream:
                r = json.loads(line)
                record_count += 1
                if r['kind'] == 'start':
                    family, seed, spec = r['family'], r['seed'], r['source_spec']
                    points = [144,160,192,256] if family == 'selective_return' else [16,64,128,256]
                if r['kind'] != 'eval_episode' or r['checkpoint'] not in points:
                    continue
                w = r['offer']
                base, pred = w['base_prediction'], w['prediction']
                coefficients = w.get('calibration_coefficients', [[0.,0.],[0.,0.]])
                target = kernel(family, spec, r['checkpoint'], r['public']['context'])
                parts = []
                for a in range(2):
                    p, q, t = base[a][1], pred[a][1], target[a]
                    alpha, beta = coefficients[a]
                    u = p*(1-p)
                    v = u*(2*p-1)
                    sharp, bias = alpha*v, beta*u
                    e = p-t
                    values = {
                        'base_same_state_mse': e*e,
                        'confidence_cross': 2*e*sharp,
                        'confidence_square': sharp*sharp,
                        'bias_cross': 2*e*bias,
                        'bias_square': bias*bias,
                        'confidence_bias_interaction': 2*sharp*bias,
                        'calibrated_mse': (q-t)**2,
                        'absolute_confidence_shift': abs(sharp),
                        'absolute_bias_shift': abs(bias),
                    }
                    reconstructed = sum(values[k] for k in (
                        'base_same_state_mse','confidence_cross','confidence_square',
                        'bias_cross','bias_square','confidence_bias_interaction'))
                    error = max(abs(q-p-sharp-bias), abs(reconstructed-values['calibrated_mse']))
                    max_error = max(max_error, error)
                    assert error < 2e-12
                    parts.append(values)
                m = {k: statistics.mean(v[k] for v in parts) for k in parts[0]}
                m['greedy_changed'] = int(max(range(2), key=lambda a: base[a][1]) != max(range(2), key=lambda a: pred[a][1]))
                accum.setdefault(r['arm'], []).append(m)
        for arm, values in accum.items():
            means = {k: statistics.mean(v[k] for v in values) for k in values[0]}
            ref = next(x for x in review['rows'] if x['family']==family and x['arm']==arm and x['seed']==seed)
            assert len(values) == 512
            assert abs(means['calibrated_mse']-statistics.mean(ref['eval_metrics'][str(k)]['kernel_mse'] for k in points)) < 2e-12
            rows.append({'family':family,'arm':arm,'seed':seed,'forecast_records':len(values),**means})
    assert record_count == review['canonical_native_records']
    table = []
    for family, arm in sorted({(r['family'],r['arm']) for r in rows}):
        sub = [r for r in rows if r['family']==family and r['arm']==arm]
        assert len(sub)==16
        means = {k:statistics.mean(r[k] for r in sub) for k in sub[0] if k not in ('family','arm','seed','forecast_records')}
        table.append({'family':family,'arm':arm,'seeds':16,'forecast_records':sum(r['forecast_records'] for r in sub),**means})
    directions = []
    for arm in ['conditional_temperature_v218','conditional_full_v218']:
        sub = [r for r in review['rows'] if r['family']=='mixed_reliability' and r['arm']==arm]
        for condition in ['0','1']:
            delta = [statistics.mean(r['condition_metrics'][str(k)][condition]['delta_best_probability'] for k in [16,64,128,256]) for r in sub]
            directions.append({'arm':arm,'condition':condition,'seed_mean_deltas':delta,
                               'positive_seeds':sum(d>0 for d in delta),'negative_seeds':sum(d<0 for d in delta)})
    out = {'schema':'v218-posthoc-algebraic-diagnosis','written_after_main_results':True,
           'new_environment_interactions':0,'model_executions':0,'parameter_updates':0,
           'source_sha256':sources,'canonical_native_records_read':record_count,
           'primary_forecasts_analyzed':sum(r['forecast_records'] for r in rows),
           'max_reconstruction_error':max_error,'table':table,'mixed_direction_by_seed':directions,
           'interpretation':'Same-record algebraic terms, not counterfactual runs with a branch removed.'}
    with (HERE/'posthoc_diagnostics.json').open('x',encoding='utf-8') as stream:
        json.dump(out,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:out[k] for k in ['new_environment_interactions','canonical_native_records_read','primary_forecasts_analyzed','max_reconstruction_error']}))


if __name__ == '__main__':
    main()
