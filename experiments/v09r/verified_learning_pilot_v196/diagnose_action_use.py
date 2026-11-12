"""Post-hoc forward-only diagnosis on saved real roots, not new trial outcomes."""
import copy
import datetime
import gzip
import hashlib
import json
import traceback
from pathlib import Path

import numpy as np
import torch
from future_facts import goal_scores

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
torch.set_num_threads(1)


def load(p):
    with gzip.open(p, 'rb') as f:
        return torch.load(f, map_location='cpu', weights_only=False)


@torch.no_grad()
def values(net, rs, index, q_enabled):
    im = torch.from_numpy(np.stack([r['image'] for r in rs[:index+1]])[None].astype(np.float32))
    sc = torch.from_numpy(np.stack([r['scalar'] for r in rs[:index+1]])[None].astype(np.float32))
    resets = torch.zeros(1, index+1)
    resets[:, 0] = 1
    h = net.unroll(im, sc, resets)[:, -1]
    score = net.q(h) if q_enabled else torch.stack([goal_scores(m(h)) for m in net.measurements]).mean(0)
    return score[0].numpy()


def main():
    with (HERE/'analysis/action_diagnosis_claim.json').open('x', encoding='utf-8') as f:
        json.dump(dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       scope='Forward saved networks on saved factual histories; zero new world/optimizer calls'), f)
    try:
        summary = json.loads((HERE/'evidence/summary.json').read_text())
        rows = []
        for job in sorted(summary['results'], key=lambda j: (j['seed'], j['arm'])):
            d = HERE/'evidence'/f"seed{job['seed']}"/job['arm']
            old = load(ROOT/job['source']['path'])
            parent = old['agent'].net
            del old
            data = load(d/'data.pt.gz')
            sources = {t['episode']: t for t in data if t['kind'] == 'source'}
            with gzip.open(d/'events.jsonl.gz', 'rt', encoding='utf-8') as f:
                events = [r for r in map(json.loads, f) if r['kind'] == 'intervention']
            for cycle, result in enumerate(job['cycles']):
                saved = load(d/f'checkpoint_cycle{cycle}.pt.gz')
                for name, t in result['teachers'].items():
                    child = copy.deepcopy(parent)
                    child.load_state_dict(saved['networks'][f'cycle{cycle}_{name}'])
                    prefs_before, prefs_after = [], []
                    for e in [e for e in events if e['cycle'] == cycle]:
                        rs, index = sources[e['source_episode']]['records'], e['root_t']
                        before = values(parent, rs, index, job['arm'] != 'F0')
                        after = values(child, rs, index, job['arm'] != 'F0')
                        legal = rs[index]['legal']
                        ba = int(np.where(legal, before, -1e9).argmax())
                        aa = int(np.where(legal, after, -1e9).argmax())
                        comparisons = []
                        trials = [x for x in data if x['kind'] == 'trial' and x['episode'] == e['source_episode']]
                        next64 = [.015*min(64, len(x['records'])-index)+sum(r['pickup'] for r in x['records'][index:index+64]) for x in trials]
                        for j in range(1, len(e['actions'])):
                            delta = e['actual_scores'][j]-e['actual_scores'][0]
                            if delta != 0 and job['arm'] != 'RL-RP':
                                p, n = (e['actions'][j], e['actions'][0]) if delta > 0 else (e['actions'][0], e['actions'][j])
                                b, a = float(before[p]-before[n]), float(after[p]-after[n])
                                prefs_before.append(b)
                                prefs_after.append(a)
                                comparisons.append(dict(before_margin=b, after_margin=a,
                                                        full_episode_effect=delta,
                                                        observed_next64_goal_effect=next64[j]-next64[0]))
                        rows.append(dict(seed=job['seed'], arm=job['arm'], cycle=cycle, teacher=name,
                                         case=e['case'], before_greedy=ba, after_greedy=aa,
                                         changed=ba != aa, comparisons=comparisons))
                    assert np.allclose(prefs_before, t['fit']['margins_before'], rtol=0, atol=1e-6)
                    assert np.allclose(prefs_after, t['fit']['margins_after'], rtol=0, atol=1e-6)
                    del child
                parent = saved['agent'].net
                del saved
            del parent, data, sources
        groups = []
        for arm in ('RL-RP', 'F0', 'F-RP', 'F-R'):
            rs = [r for r in rows if r['arm'] == arm]
            ps = [p for r in rs for p in r['comparisons']]
            groups.append(dict(arm=arm, root_candidate_pairs=len(rs), greedy_changed=sum(r['changed'] for r in rs),
                               trained_comparisons=len(ps), margin_improved=sum(p['after_margin'] > p['before_margin'] for p in ps),
                               correct_pair_order_before=sum(p['before_margin'] > 0 for p in ps),
                               correct_pair_order_after=sum(p['after_margin'] > 0 for p in ps),
                               full_vs_next64_direction_conflicts=sum(p['full_episode_effect']*p['observed_next64_goal_effect'] < 0 for p in ps)))
        out = dict(status='PASS_FORWARD_DIAGNOSIS', groups=groups, rows=rows,
                   interpretation='A changed greedy root or improved training margin is NOT an independently measured teacher rollout gain.',
                   environment_calls=0, optimizer_calls=0)
    except BaseException:
        out = dict(status='ERROR_FORWARD_DIAGNOSIS', error=traceback.format_exc())
    with (HERE/'analysis/action_diagnosis.json').open('x', encoding='utf-8') as f:
        json.dump(out, f, indent=2)
        f.write('\n')
    print(json.dumps({k: v for k, v in out.items() if k != 'rows'}))
    return 0 if out['status'] == 'PASS_FORWARD_DIAGNOSIS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
