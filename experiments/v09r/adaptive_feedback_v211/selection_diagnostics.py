"""Post-run opportunity diagnosis from stored policies; never a learner selector."""
from pathlib import Path
from itertools import product
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import time

HERE = Path(__file__).resolve().parent
ROWS = list(product((0, 1), repeat=4))


def value(policy, spec, cycle):
    if spec['family'] == 'noise':
        return 25
    matches = 0
    for row, action in zip(ROWS, policy['actions']):
        target = spec['flip']
        for j in spec['relevant']:
            target ^= row[j]
        if spec['switch_cycle'] is not None and cycle >= spec['switch_cycle']:
            target ^= 1
        matches += int(action == target)
    return 9+2*matches  # /50, exact.


def main():
    started = time.perf_counter()
    raw_paths = sorted((HERE/'shards').glob('*/raw.jsonl.gz'))
    bindings = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in raw_paths}
    with (HERE/'selection_diagnostic_claim.json').open('x', encoding='utf-8') as stream:
        json.dump({'utc': datetime.now(timezone.utc).isoformat(), 'scope': 'stored bank nomination opportunities only',
                   'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   'raw_sha256': bindings, 'new_environment_runs': 0}, stream, indent=2)
    rows, exact_tie_count = [], 0
    for path in raw_paths:
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for line in stream:
                record = json.loads(line)
                kind = record['kind']
                if kind == 'shard_start':
                    family, seed = record['family'], record['seed']
                elif kind == 'run_begin':
                    spec, arm = record['spec'], record['arm']
                elif kind == 'bank':
                    bank, incumbent, cycle = record['candidates'], record['incumbent'], record['cycle']
                    ranking = []
                elif kind == 'episode' and record['phase'] == 'train' and 32 <= record['slot'] < 64:
                    ranking.append(record['public'])
                elif kind == 'nomination':
                    values = [value(p, spec, cycle) for p in bank]
                    exact_scores = []
                    for policy in bank:
                        numerator = 0
                        for f in ranking:
                            index = sum(v*2**(3-j) for j, v in enumerate(f['context']))
                            target_tenths = 9 if policy['actions'][index] == f['action'] else 1
                            behavior_tenths = round(10*f['propensity'])
                            assert behavior_tenths in (1, 9)
                            numerator += (9*target_tenths//behavior_tenths)*f['outcome']
                        exact_scores.append(numerator)
                    chosen = record['chosen']
                    assert chosen is not None and exact_scores[chosen] == max(exact_scores)
                    tie = [i for i, score in enumerate(exact_scores) if score == max(exact_scores)]
                    float_sensitive = chosen != tie[0]
                    exact_tie_count += int(float_sensitive)
                    rows.append({'family': family, 'seed': seed, 'arm': arm, 'cycle': cycle,
                                 'bank_size': len(bank), 'distinct_behaviors': len({tuple(p['actions']) for p in bank}),
                                 'reference_expected': value(incumbent, spec, cycle)/50,
                                 'best_bank_expected': max(values)/50,
                                 'nominated_expected': values[chosen]/50,
                                 'missed_better_bank_candidate': values[chosen] < max(values),
                                 'nomination_regret': (max(values)-values[chosen])/50,
                                 'best_structures': [p['meta'][1] for p, v in zip(bank, values) if v == max(values)],
                                 'nominated_structure': bank[chosen]['meta'][1],
                                 'nominated_equals_incumbent_behavior': bank[chosen]['actions'] == incumbent['actions'],
                                 'exact_rank_maximizers': tie, 'native_float_chose_nonfirst_exact_tie': float_sensitive,
                                 'exact_rank_criterion_maximum_preserved': True})
    aggregate = []
    for family in ('single', 'triple', 'switch_pair', 'noise'):
        for arm in ('full', 'fixed_order', 'pooled_history', 'mean_eight'):
            group = [r for r in rows if r['family'] == family and r['arm'] == arm]
            aggregate.append({'family': family, 'arm': arm, 'nominations': len(group),
                              'missed_better_bank': sum(r['missed_better_bank_candidate'] for r in group),
                              'regret_sum': sum(r['nomination_regret'] for r in group),
                              'identical_behavior_nominations': sum(r['nominated_equals_incumbent_behavior'] for r in group)})
    result = {'rows': rows, 'aggregate': aggregate, 'nominations': len(rows),
              'exact_rank_maximum_checks': len(rows), 'float_tie_nonfirst_choices': exact_tie_count,
              'environment_runs': 0, 'no_model_imports': True, 'wall_seconds': time.perf_counter()-started}
    with (HERE/'selection_diagnostics.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'aggregate')}))


if __name__ == '__main__':
    main()
