"""Stored-only review. Python stdlib; imports no learner, torch or environment.

Reconstructs every actual episode, every expert update and every captured policy
action, and verifies the full recorded Bellman table. No environment execution.
"""
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics as st
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
E = HERE / 'evidence'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def rows(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as f:
        for line in f:
            yield json.loads(line)


def near(a, b, tol=2e-9):
    assert math.isfinite(a) and math.isfinite(b) and abs(a-b) <= tol, (a, b)


def feature(obs, definition):
    kind, pos, field = definition
    if kind == 'constant':
        return 0
    if kind == 'current':
        return obs[-1][field+1]
    previous = obs[:-1]
    if pos >= len(previous):
        return 2
    return previous[pos if kind == 'past' else -1-pos][field+1]


def seed_for(*values):
    return int.from_bytes(hashlib.sha256('|'.join(map(str, values)).encode()).digest()[:8], 'big')


class ExpertReview:
    """Lazy decay is algebraically independent from the native dense tensor update."""
    def __init__(self, definitions, halves, uniform):
        self.defs, self.halves, self.uniform = definitions, halves, uniform
        self.r, self.k, self.seen = len(definitions), len(halves), 0
        self.w = [1/(self.r*self.k)] * (self.r*self.k)
        self.cells = [{} for _ in self.w]
        self.decays = [1. if h is None else 2**(-1/h) for h in halves]

    def cell(self, i, a, f, n):
        v0, v1, last = self.cells[i].get((a, f), (0., 0., 0))
        d = self.decays[i//self.r] ** (n-last)
        return v0*d, v1*d

    def observe(self, ep, receipt):
        assert receipt['before'] == self.seen
        n, a, y = self.seen+1, ep['actions'][-1], ep['outcome']
        fs = [feature(ep['observations'], d) for d in self.defs]
        predictions, selected = [], []
        for i in range(len(self.w)):
            f = fs[i % self.r]
            v0, v1 = self.cell(i, a, f, n)
            predictions.append((v1+1)/(v0+v1+2))
            selected.append((f, v0, v1))
        p = sum(w*q for w, q in zip(self.w, predictions))
        near(p, receipt['prediction'])
        near((p-y)**2, receipt['loss'])
        assert receipt['outcome'] == y
        if not self.uniform:
            w = [w*math.exp(-4*(q-y)**2) for w, q in zip(self.w, predictions)]
            s = sum(w)
            self.w = [.98*x/s + .02/len(w) for x in w]
        for i, (f, v0, v1) in enumerate(selected):
            self.cells[i][a, f] = (v0+(y == 0), v1+(y == 1), n)
        near(max(self.w), receipt['top_weight'])
        near(self.w[receipt['top_scale']*self.r+receipt['top_selector']], max(self.w))
        self.seen = n

    def snapshot(self, snap):
        assert snap['seen'] == self.seen
        for k in range(self.k):
            for r in range(self.r):
                i = k*self.r+r
                near(self.w[i], snap['weights'][k][r])
                for a in range(2):
                    for f in range(3):
                        expected = self.cell(i, a, f, self.seen)
                        for y in range(2):
                            near(expected[y], snap['counts'][k][r][a][f][y])


class PolicyReview:
    def __init__(self, snap):
        self.defs = snap['definitions']
        self.w = [v for row in snap['weights'] for v in row]
        self.rates = []
        for k in snap['counts']:
            for selector in k:
                self.rates.append([[(cell[1]+1)/(sum(cell)+2) for cell in action] for action in selector])

    def check(self, ep):
        fs = [feature(ep['observations'], d) for d in self.defs]
        p = [sum(w*rate[a][fs[i % len(fs)]] for i, (w, rate) in enumerate(zip(self.w, self.rates))) for a in range(2)]
        chosen = ep['actions'][-1]
        # A roundoff tie may select either action; never bless a meaningful reversal.
        assert p[chosen] >= max(p)-2e-12, (ep['id'], chosen, p)


def stat(values):
    return dict(n=len(values), mean=st.mean(values), se=st.stdev(values)/math.sqrt(len(values)) if len(values)>1 else None)


def main():
    started = time.perf_counter()
    cfg, end, native = read(HERE/'contract.json'), read(HERE/'native_exit.json'), read(HERE/'native_result.json')
    assert end['exit_code'] == 0 and not end['timeout']
    assert end['inputs_before'] == end['inputs_after']
    for name, digest in end['inputs_before'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    assert native['controller_parameter_before'] == native['controller_parameter_after']
    assert native['optimizer_steps'] == 0 and not native['parameters_changed']
    episodes, role_counts, steps = [], Counter(), 0
    learning = defaultdict(list)
    for ep in rows(E/'episodes.jsonl.gz'):
        assert ep['id'] == len(episodes)
        assert ep['actions'][-1] in (0, 1)
        u = random.Random(ep['outcome_seed']).random()
        if ep['section'] == 'memory':
            rng = random.Random(ep['context_seed'])
            length = rng.choice((8, 10, 12))
            obs = [[t, rng.randrange(2), rng.randrange(2)] for t in range(length+1)]
            slot, field = ep['instance']%5, (ep['instance']//5)%2
            target = obs[slot][field+1]
            if ep['family'] == 'two_cue_xor':
                target ^= obs[(slot+2)%5][2-field]
            if ep['family'] == 'rule_reversal' and ep['cycle'] >= 2:
                target = 1-target
            p = .9 if ep['actions'][-1] == target else .1
            assert ep['observations'] == obs and ep['actions'][:-1] == [0]*length
            if ep['role'] in ('warm', 'discovery'):
                for v in cfg['variants']:
                    learning[f"{ep['family']}:{ep['instance']}:{v}"].append(ep['id'])
            elif not ep['role'].startswith('eval_'):
                learning[ep['run']].append(ep['id'])
        else:
            assert ep['section'] == 'gate' and ep['observations'] == [[0, 0, 0]]
            p = cfg['gate_cases'][ep['case']][ep['actions'][0]]
        near(ep['draw'], u, 0.)
        near(ep['analyst_probability'], p, 0.)
        assert ep['outcome'] == int(u < p) and ep['steps'] == len(ep['actions'])
        steps += ep['steps']
        role_counts[ep['section']+':'+ep['role']] += 1
        episodes.append(ep)
    assert len(episodes) == native['actual_episodes'] == cfg['maximum_actual_episodes']
    assert steps == native['actual_steps'] <= cfg['maximum_actual_steps']
    print('All raw observations, actions, outcomes and episode counts reconstructed', flush=True)

    table = {(r['budget'], r['cap'], tuple(r['counts'])): (r['value'], r['decision']) for r in rows(E/'dp_table.jsonl.gz')}
    assert len(table) == native['dp_states']
    for (b, cap, counts), (value, decision) in table.items():
        alpha = [c+1 for c in counts]
        total = sum(alpha)
        old, new = (alpha[2]+alpha[3])/total, (alpha[1]+alpha[3])/total
        if b == 0:
            assert value == 0. and decision == 'keep'
            continue
        options = {'keep': b*old}
        if sum(counts):
            options['adopt'] = b*new
        if b >= 2 and cap > 0:
            terms = []
            for i in range(4):
                nxt = list(counts)
                nxt[i] += 1
                terms.append(alpha[i]/total * table[b-2, cap-1, tuple(nxt)][0])
            options['trial'] = old+new-cfg['pair_cost_utility_proxy']+sum(terms)
        near(value, max(options.values()), 1e-10)
        near(value, options[decision], 1e-10)
    print('Full stored Bellman table verified', flush=True)

    snapshots = {(s['run'], s['cycle']): s for s in rows(E/'snapshots.jsonl.gz')}
    assert len(snapshots) == 3*24*5*4
    experts, checked_snapshots, update_count = {}, set(), 0
    for rec in rows(E/'updates.jsonl.gz'):
        rid = rec['run']
        if rid not in experts:
            s = snapshots[rid, 0]
            experts[rid] = ExpertReview(s['definitions'], s['half_lives'], cfg['variants'][rid.split(':')[-1]]['uniform'])
        state = experts[rid]
        if state.seen >= 56 and (state.seen-56)%64 == 0:
            c = (state.seen-56)//64
            if c < 4:
                state.snapshot(snapshots[rid, c])
                checked_snapshots.add((rid, c))
        assert learning[rid][state.seen] == rec['id']
        state.observe(episodes[rec['id']], rec)
        update_count += 1
    assert len(checked_snapshots) == len(snapshots)
    assert update_count == native['learning_update_events'] == 109440
    assert all(x.seen == 304 for x in experts.values())
    print('Every expert update and candidate snapshot reconstructed independently', flush=True)

    results = list(rows(E/'results.jsonl'))
    assert len(results) == native['result_rows'] == 2720
    incumbents, policies = {}, {key: PolicyReview(s) for key, s in snapshots.items()}
    used_active, used_eval = set(), set()
    for r in results:
        memory = r['section'] == 'memory'
        b = cfg['active_budget_per_variant_cycle'] if memory else r['budget']
        method = cfg['variants'][r['variant']]['controller'] if memory else r['method']
        active = [episodes[i] for i in r['active_ids']]
        assert len(active) == b and not (used_active & set(r['active_ids']))
        used_active.update(r['active_ids'])
        assert all(e['run'] == r['run'] and e['section'] == r['section'] for e in active)
        counts = [0, 0, 0, 0]
        for j, d in enumerate(r['decisions']):
            assert counts == d['counts'] and j == sum(counts)
            expected = ('trial' if j < 8 else 'adopt' if counts[1]>counts[2] else 'keep') if method == 'fixed8' else table[b-2*j, min(cfg['maximum_trial_pairs'], b//2)-j, tuple(counts)][1]
            assert expected == d['decision']
            if d['decision'] == 'trial':
                old, new = active[2*j:2*j+2]
                assert old['role'] == 'trial_old' and new['role'] == 'trial_new'
                if memory:
                    assert old['observations'] == new['observations']
                counts[2*old['outcome']+new['outcome']] += 1
            else:
                assert j == len(r['decisions'])-1
        n = sum(counts)
        assert n == r['trial_pairs'] and r['adopted'] == (r['decisions'][-1]['decision'] == 'adopt')
        assert not r['adopted'] or n > 0
        assert all(e['role'] == 'deployment' for e in active[2*n:])
        gross = sum(e['outcome'] for e in active)
        near(r['active_gross' if memory else 'gross'], gross, 0.)
        near(r['active_net' if memory else 'net'], gross-.02*n)
        if memory:
            rid, c = r['run'], r['cycle']
            candidate, incumbent = policies[rid, c], incumbents.get(rid)
            chosen = candidate if r['adopted'] else incumbent
            assert r['parameter_before'] == r['parameter_after']
            assert r['snapshot_before'] == r['snapshot_after']
            for e in active:
                actor = candidate if e['role'] == 'trial_new' else incumbent if e['role'] == 'trial_old' else chosen
                if actor is None:
                    assert e['actions'][-1] == 0
                else:
                    actor.check(e)
            for key, actor in [('eval_old', incumbent), ('eval_candidate', candidate)]:
                assert len(r[key]) == 32 and not used_eval.intersection(r[key])
                used_eval.update(r[key])
                for j, i in enumerate(r[key]):
                    e = episodes[i]
                    assert e['run'] == rid and e['cycle'] == c and e['role'] == key
                    assert e['context_seed'] == seed_for('context', r['family'], r['instance'], c, 'evaluation', j)
                    if actor is None:
                        assert e['actions'][-1] == 0
                    else:
                        actor.check(e)
            assert r['eval_selected'] == r['eval_candidate' if r['adopted'] else 'eval_old']
            for field, ids in [('deployed_mean', r['eval_selected']), ('candidate_mean', r['eval_candidate']), ('incumbent_mean', r['eval_old'])]:
                near(r[field], st.mean(episodes[i]['outcome'] for i in ids), 0.)
            near(r['selected_law_mean'], st.mean(episodes[i]['analyst_probability'] for i in r['eval_selected']))
            incumbents[rid] = chosen
        else:
            assert all(e['actions'] == [int(r['adopted'])] for e in active[2*n:])
            p0, p1 = cfg['gate_cases'][r['case']]
            near(r['law_expected_total'], sum(e['analyst_probability'] for e in active))
            assert r['harmful_adoption'] == bool(r['adopted'] and p1<p0)
            assert r['missed_gain'] == bool(not r['adopted'] and p1>p0)
    assert not used_active.intersection(used_eval)
    assert len(used_active) == 136960 and len(used_eval) == 92160
    print('All real trial decisions, captured-policy actions and reported outcomes verified', flush=True)

    groups = defaultdict(list)
    for r in results:
        key = (r['family'], r['variant'], r['cycle']) if r['section'] == 'memory' else (r['case'], r['method'], r['budget'])
        groups[(r['section'],)+key].append(r)
    aggregates = []
    for key, group in groups.items():
        memory = key[0] == 'memory'
        fields = ['deployed_mean', 'candidate_mean', 'incumbent_mean', 'selected_law_mean', 'active_gross', 'active_net', 'trial_pairs'] if memory else ['gross', 'net', 'law_expected_total', 'trial_pairs']
        row = dict(key=list(key), adopted=sum(r['adopted'] for r in group), metrics={f: stat([r[f] for r in group]) for f in fields})
        if not memory:
            row.update(harmful_adoptions=sum(r['harmful_adoption'] for r in group), missed_gains=sum(r['missed_gain'] for r in group))
        aggregates.append(row)
    comparisons = []
    memory_index = {(r['family'], r['variant'], r['instance'], r['cycle']): r for r in results if r['section']=='memory'}
    for family in cfg['memory_families']:
        for other in cfg['variants']:
            if other == 'full_v2':
                continue
            for field in ('deployed_mean', 'candidate_mean', 'active_gross', 'trial_pairs'):
                delta = [st.mean(memory_index[family, 'full_v2', i, c][field]-memory_index[family, other, i, c][field] for c in range(4)) for i in range(24)]
                comparisons.append(dict(family=family, comparison='full_v2 - '+other, field=field, **stat(delta)))
    summary = dict(status='STORED_REVIEW_MATCH', episodes=len(episodes), steps=steps, role_counts=dict(role_counts),
                   expert_updates=update_count, snapshots=len(snapshots), bellman_states=len(table), result_rows=len(results),
                   neural_parameter_hash_unchanged_native=True, independent_parameter_tensor_reload=False,
                   no_environment_or_torch_imports=True, wall_seconds=time.perf_counter()-started,
                   aggregates=aggregates, seed_paired_allcycle_comparisons=comparisons)
    with (HERE/'reviewed_summary.json').open('x', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, allow_nan=False)
    flat = [{k:v for k,v in r.items() if not isinstance(v, (list, dict))} for r in results]
    keys = list(dict.fromkeys(k for r in flat for k in r))
    with (HERE/'per_seed_results.csv').open('x', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(flat)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('aggregates','seed_paired_allcycle_comparisons')}), flush=True)


if __name__ == '__main__':
    main()
