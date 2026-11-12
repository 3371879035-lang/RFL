"""Read saved models and observations; no training or new environment interaction."""
import ast
import concurrent.futures
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
import traceback

os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / 'spatial_feedback_v179'
ROOT = HERE.parents[2]
sys.path.insert(0, str(ORIGINAL))
import numpy as np
import psutil
import torch
from torch.nn import functional as F

torch.set_num_threads(1)
torch.set_num_interop_threads(1)


def write(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def paused_states():
    receipt = json.loads((HERE / 'pause_receipt.json').read_text(encoding='utf-8'))
    result = []
    for row in receipt['identity']:
        p = psutil.Process(row['pid'])
        assert p.create_time() == row['create_time'] and p.status() == 'stopped'
        cpu = p.cpu_times()
        result.append(dict(pid=p.pid, status=p.status(), user=cpu.user, system=cpu.system))
    return result


def review_existing_intervention():
    tree = ast.parse((ORIGINAL / 'experiment.py').read_text(encoding='utf-8'))
    definition = next(n.value.args[0] for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'DTYPE' for t in n.targets))
    dtype = np.dtype(ast.literal_eval(definition))
    reviews = []
    for seed in range(9001, 9013):
        for arm in ('F-RP', 'F-R'):
            d = HERE.parent / 'frozen_q_readout_diagnostic_v180/evidence' / f'seed{seed}' / arm
            result = json.loads((d / 'result.json').read_text())
            episodes = json.loads((d / 'episodes.json').read_text())
            with gzip.open(d / 'steps.bin.gz', 'rb') as f:
                size, = struct.unpack('<I', f.read(4))
                header = json.loads(f.read(size))
                payload = f.read()  # Full EOF and gzip CRC, not a prefix.
            assert len(payload) % dtype.itemsize == 0
            raw = np.frombuffer(payload, dtype)
            assert header['seed'] == seed and header['source_arm'] == arm
            assert len(raw) == result['steps']
            assert hashlib.sha256(payload).hexdigest() == result['raw_payload_sha256']
            assert result['parameter_hash_before'] == result['parameter_hash_after'] == header['parameter_hash']
            assert result['training_steps_added'] == 0 and result['persistent_history_unchanged']
            assert np.all(raw['kind'] == 4) and np.all(raw['checkpoint'] == 262144)
            assert np.all(raw['depth'] == 0) and np.all(raw['explore'] == 0)
            assert np.all(raw['action'] < 16) and np.isnan(raw['reward']).all()
            assert np.all((raw['action'] < 8) | (raw['cooldown_before'] == 0))
            offset = 0
            for j, episode in enumerate(episodes):
                count = episode['steps']
                rows = raw[offset:offset + count]
                assert episode['episode'] == j and len(rows) == count
                assert np.all(rows['episode'] == j) and np.array_equal(rows['step'], np.arange(1, count + 1))
                assert np.all(rows['map'] == episode['map']) and np.all(rows['mode'] == episode['mode'])
                assert np.array_equal(rows['score'], 1.5 * rows['step'] + 100 * rows['pickup'].cumsum())
                terminal = (rows['captured'] != 0) | (rows['completed'] != 0)
                assert terminal[-1] and not terminal[:-1].any()
                assert bool(rows[-1]['captured']) == episode['captured']
                assert bool(rows[-1]['completed']) == episode['completed']
                assert float(rows[-1]['score']) == episode['score']
                assert np.array_equal(rows['hero'][:-1], rows['before_hero'][1:])
                assert np.array_equal(rows['monsters'][:-1], rows['before_monsters'][1:])
                after_cd = np.maximum(0, np.where(rows['action'] >= 8, 32, rows['cooldown_before']).astype(int) - 1)
                assert np.array_equal(after_cd[:-1], rows['cooldown_before'][1:])
                offset += count
            assert offset == len(raw) and len(episodes) == 128
            assert float(np.mean([e['score'] for e in episodes])) == result['mean_score']
            reviews.append(dict(seed=seed, arm=arm, records=len(raw), status='STORED_INVARIANTS_MATCH'))
    return dict(cases=reviews, records=sum(r['records'] for r in reviews),
                scope='EOF/CRC/payload hash/frozen hash/count/legal action/cooldown/continuity/score; not full physics or neural replay')


def matched_scores():
    means = []
    for seed in range(9001, 9013):
        for arm in ('RL-RP', 'F0', 'F-RP', 'F-R'):
            path = ORIGINAL / 'evidence_matrix' / f'seed{seed}' / arm / 'episodes.jsonl.gz'
            rows = []
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                for line in f:
                    e = json.loads(line)
                    if e['kind'] == 'evaluation' and e['checkpoint'] == 262144 and e['episode'] < 128:
                        rows.append(e)
            assert len(rows) == 128 and [e['episode'] for e in rows] == list(range(128))
            means.append(dict(seed=seed, arm=arm, mean_score=float(np.mean([e['score'] for e in rows])),
                              mean_survival=float(np.mean([e['steps'] for e in rows]))))
    return means


def auc(scores, labels):
    positives, negatives = int(labels.sum()), int((1 - labels).sum())
    if not positives or not negatives:
        return None
    unique, index = np.unique(scores, return_inverse=True)
    pos = np.bincount(index, weights=labels, minlength=len(unique))
    neg = np.bincount(index, weights=1-labels, minlength=len(unique))
    return float((pos * (np.cumsum(neg)-.5*neg)).sum() / (positives * negatives))


def gradient_probe(agent, starts):
    r, net = agent.replay, agent.net
    indices = (starts[:16, None] + np.arange(25)) % len(r.action)
    images = torch.from_numpy(r.image[indices].astype(np.float32))
    scalars = torch.from_numpy(r.scalar[indices].astype(np.float32))
    resets = torch.from_numpy(r.reset[indices].astype(np.float32))
    hidden = net.unroll(images, scalars, resets)
    cur, nxt, ii = hidden[:, 8:24], hidden[:, 9:25], indices[:, 8:24]
    actions = torch.from_numpy(r.action[ii].astype(np.int64))
    done = torch.from_numpy(r.done[ii].astype(np.float32))
    shared = [p for name, p in net.named_parameters() if name.startswith(('conv.', 'projection.', 'gru.'))]
    q_loss = None
    if agent.q_enabled:
        current = net.q(cur).gather(-1, actions[..., None]).squeeze(-1)
        with torch.no_grad():
            target_h = agent.target_net.unroll(images, scalars, resets)[:, 9:25]
            online_next = net.q(nxt.detach())
            online_next[~torch.from_numpy(r.legal[indices[:, 9:25]])] = -1e9
            best = online_next.argmax(-1)
            y = torch.from_numpy(r.reward[ii]) + .99*(1-done)*agent.target_net.q(target_h).gather(-1, best[..., None]).squeeze(-1)
        q_loss = F.smooth_l1_loss(current, y)
    inputs = torch.cat((cur, F.one_hot(actions, 16).float()), -1)
    targets, masks = torch.from_numpy(r.target[ii]), torch.from_numpy(r.target_mask[ii])
    fact_loss = cur.sum()*0
    for j, head in enumerate(net.heads):
        raw = head(inputs)
        prediction = torch.cat((torch.tanh(raw[..., :6]), F.softplus(raw[..., 6:7]), torch.sigmoid(raw[..., 7:10])), -1)
        boot = torch.from_numpy((((starts[:16, None] + np.arange(8, 24)+j*17)*1103515245+12345) % 7 < 5).astype(np.float32))
        weights = masks * boot[..., None]
        loss = ((prediction-targets)**2*weights).sum()/weights.sum().clamp_min(1)
        loss = loss+(F.binary_cross_entropy_with_logits(raw[..., 7], targets[..., 7], reduction='none')*boot).mean()
        latent = torch.tanh(cur + raw[..., 10:]*.1)
        loss = loss+.1*(((latent-nxt.detach())**2).mean(-1)*(1-done)*boot).mean()
        fact_loss = fact_loss+loss/3
    q_grad = None
    if q_loss is not None:
        q_grad = torch.cat([g.flatten() for g in torch.autograd.grad(q_loss, shared, retain_graph=True)])
    fact_grad = torch.cat([g.flatten() for g in torch.autograd.grad(fact_loss, shared)])
    fn = float(fact_grad.norm())
    result = dict(fact_loss=float(fact_loss.detach()), factual_shared_gradient_norm=fn,
                  Q_loss=None, Q_shared_gradient_norm=None, factual_to_Q_gradient_norm_ratio=None, gradient_cosine=None)
    if q_grad is not None:
        qn = float(q_grad.norm())
        result.update(Q_loss=float(q_loss.detach()), Q_shared_gradient_norm=qn,
                      factual_to_Q_gradient_norm_ratio=fn/qn if qn else None,
                      gradient_cosine=float(F.cosine_similarity(q_grad, fact_grad, dim=0)))
    return result


def run_case(spec):
    seed, arm = spec
    path = ORIGINAL / 'evidence_matrix' / f'seed{seed}' / arm / 'checkpoint_262144.pt.gz'
    with gzip.open(path, 'rb') as f:
        donor = torch.load(f, map_location='cpu', weights_only=False)
    agent = donor['agent']
    del donor
    net, r = agent.net, agent.replay
    net.eval()
    before, counters = agent.parameter_hash(), agent.counters.copy()
    assert agent.training_steps == 262144 and r.n == 262144
    starts = np.linspace(max(0, r.n-len(r.action)), r.n-25, 64, dtype=np.int64)
    observed, root = [], []
    with torch.no_grad():
        for start_batch in starts.reshape(4, 16):
            indices = (start_batch[:, None] + np.arange(25)) % len(r.action)
            images = torch.from_numpy(r.image[indices].astype(np.float32))
            scalars = torch.from_numpy(r.scalar[indices].astype(np.float32))
            resets = torch.from_numpy(r.reset[indices].astype(np.float32))
            h = net.unroll(images, scalars, resets)
            cur, nxt = h[:, 8:24].reshape(-1, 64), h[:, 9:25].reshape(-1, 64)
            ii, jj = indices[:, 8:24].ravel(), indices[:, 9:25].ravel()
            acts = torch.from_numpy(r.action[ii].astype(np.int64))
            count = len(acts)
            raw = torch.stack([head(torch.cat((cur, F.one_hot(acts, 16).float()), -1)) for head in net.heads])
            cap = raw[..., 7].sigmoid().mean(0).numpy()
            pickup = F.softplus(raw[..., 6]).mean(0).numpy()
            move = raw[..., :2].tanh().mean(0).numpy()
            predlatent = torch.tanh(cur[None]+raw[..., 10:]*.1).mean(0)
            done = r.done[ii]
            observed.append(dict(capture_probability=cap, capture=r.target[ii, 7],
                pickup_error=pickup-r.target[ii, 6], movement_error_cells=10*(move-r.target[ii, :2]),
                latent_mse=((predlatent-nxt)**2).mean(-1).numpy()[~done],
                persistence_mse=((cur-nxt)**2).mean(-1).numpy()[~done],
                capture_head_std=raw[..., 7].sigmoid().std(0, unbiased=False).numpy(),
                future_steps_error=raw[..., 8].sigmoid().mean(0).numpy()-r.target[ii, 8],
                future_pickups_error=raw[..., 9].sigmoid().mean(0).numpy()-r.target[ii, 9],
                future_mask=r.target_mask[ii, 8] != 0))
            if agent.q_enabled:
                current_q = net.q(cur)
                legal = torch.from_numpy(r.legal[ii])
                masked_q = current_q.masked_fill(~legal, -1e9)
                direct = masked_q.argmax(-1)
                all_cur = cur[:, None, :].expand(-1, 16, -1)
                all_acts = torch.eye(16)[None].expand(count, -1, -1)
                all_raw = torch.stack([head(torch.cat((all_cur, all_acts), -1)) for head in net.heads])
                next_h = torch.tanh(cur[None, :, None, :]+all_raw[..., 10:]*.1)
                next_q = net.q(next_h)
                cooldown = torch.from_numpy(np.rint(r.scalar[ii, 3].astype(np.float32)*32).astype(np.int64))
                next_cd = (torch.where(torch.arange(16)[None] >= 8, 32, cooldown[:, None])-1).clamp_min(0)
                next_q[..., 8:] = next_q[..., 8:].masked_fill((next_cd != 0)[None, :, :, None], -1e9)
                tail = next_q.max(-1).values
                pc = all_raw[..., 7].sigmoid()
                score = (.015+F.softplus(all_raw[..., 6])-agent.penalty*pc+.99*(1-pc)*tail).mean(0)
                model_best = score.masked_fill(~legal, -1e9).argmax(-1)
                actual_next = net.q(nxt).masked_fill(~torch.from_numpy(r.legal[jj]), -1e9).max(-1).values
                actual_target = torch.from_numpy(r.reward[ii])+.99*(1-torch.from_numpy(done.astype(np.float32)))*actual_next
                row_index = torch.arange(count)
                predicted_target = score[row_index, acts]
                root.append(dict(disagree=(direct != model_best).numpy(),
                    q_action_gap=(masked_q[row_index, direct]-masked_q[row_index, model_best]).numpy(),
                    prediction_target_error=(predicted_target-actual_target).numpy(),
                    current_Q_target_error=(current_q[row_index, acts]-actual_target).numpy(),
                    predicted_tail_error=(tail.mean(0)[row_index, acts]-actual_next).numpy()[~done],
                    model_flash=(model_best >= 8).numpy(), Q_flash=(direct >= 8).numpy(),
                    Q_action=direct.numpy(), model_action=model_best.numpy()))
    def concat(key):
        return np.concatenate([x[key] for x in observed])
    p, y = concat('capture_probability'), concat('capture')
    prevalence = float(y.mean())
    cp = np.clip(p.astype(np.float64), 1e-8, 1-1e-8)
    measurements = dict(positions=len(p), captured_positions=int(y.sum()), capture_prevalence=prevalence,
        predicted_capture_mean=float(p.mean()), capture_Brier=float(np.mean((p-y)**2)),
        constant_prevalence_Brier=prevalence*(1-prevalence), capture_AUROC=auc(p, y),
        capture_log_loss=float(np.mean(-y*np.log(cp)-(1-y)*np.log(1-cp))),
        capture_head_std_mean=float(concat('capture_head_std').mean()),
        pickup_MAE=float(np.abs(concat('pickup_error')).mean()),
        movement_cells_RMSE=float(np.sqrt((concat('movement_error_cells')**2).mean())),
        successor_latent_MSE=float(concat('latent_mse').mean()),
        persistence_latent_MSE=float(concat('persistence_mse').mean()))
    mask = concat('future_mask')
    measurements['future_remaining_steps_MAE'] = float(np.abs(concat('future_steps_error')[mask]).mean()*256)
    measurements['future_remaining_pickups_MAE'] = float(np.abs(concat('future_pickups_error')[mask]).mean()*10)
    if root:
        def rc(key):
            return np.concatenate([x[key] for x in root])
        measurements['H1_no_retrieval_probe'] = dict(Q_model_action_disagreement=float(rc('disagree').mean()),
            Q_implied_action_gap_mean=float(rc('q_action_gap').mean()),
            model_one_step_vs_real_successor_target_MAE=float(np.abs(rc('prediction_target_error')).mean()),
            current_Q_vs_real_successor_target_MAE=float(np.abs(rc('current_Q_target_error')).mean()),
            predicted_vs_observed_successor_Q_tail_MAE=float(np.abs(rc('predicted_tail_error')).mean()),
            model_flash_fraction=float(rc('model_flash').mean()), Q_flash_fraction=float(rc('Q_flash').mean()),
            model_action_counts=np.bincount(rc('model_action'), minlength=16).tolist(),
            Q_action_counts=np.bincount(rc('Q_action'), minlength=16).tolist())
    gradients = gradient_probe(agent, starts)
    assert agent.parameter_hash() == before and agent.counters == counters and r.n == 262144
    return dict(seed=seed, arm=arm, parameter_hash=before, parameters_counters_history_unchanged=True,
                measurements=measurements, fixed_batch_gradients=gradients)


def main():
    output = HERE / 'evidence'
    output.mkdir(exist_ok=False)
    started = time.perf_counter()
    initial_pause = paused_states()
    write(output / 'claim.json', dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        contract_sha256=hashlib.sha256((HERE/'contract.json').read_bytes()).hexdigest(),
        main_states=initial_pause))
    cases, error, review, scores = [], None, None, None
    try:
        review = review_existing_intervention()
        scores = matched_scores()
        specs = [(s, a) for s in range(9001, 9013) for a in ('F0', 'F-RP', 'F-R')]
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            for result in pool.map(run_case, specs):
                cases.append(result)
                write(output / f"seed{result['seed']}_{result['arm']}.json", result)
        binding = json.loads((HERE / 'source_binding.json').read_text(encoding='utf-8'))
        for row in binding['pins']:
            p = ROOT / row['path']
            assert p.stat().st_size == row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest() == row['sha256']
        assert len(cases) == 36
        assert paused_states() == initial_pause, 'Main must remain suspended with CPU times unchanged'
        assert time.perf_counter()-started <= 600
    except BaseException:
        error = traceback.format_exc()
    result = dict(status='COMPLETE_OFFLINE_DIAGNOSTIC' if error is None else 'ERROR_PARTIAL_RETAINED',
        exit_code=int(error is not None), error=error, cases=cases, matched_original_scores=scores,
        existing_v180_stored_review=review, new_training_steps=0, optimizer_steps=0,
        new_environment_steps=0, wall_seconds=time.perf_counter()-started, main_automatically_resumed=False)
    write(output / 'result.json', result)
    print(json.dumps({k:result[k] for k in ('status', 'exit_code', 'error', 'wall_seconds', 'new_training_steps', 'new_environment_steps')}), flush=True)
    return result['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
