"""Paused-run diagnosis: exact mask arithmetic and frozen successor error decomposition."""
import ast
import concurrent.futures
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORIGINAL = HERE.parent/'spatial_feedback_v179'
sys.path.insert(0, str(ORIGINAL))
import numpy as np
import psutil
import torch
from torch.nn import functional as F

torch.set_num_threads(1)
torch.set_num_interop_threads(1)


def save(path, data):
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)


def paused():
    prior = HERE.parent/'training_pause_investigation_v181/pause_receipt.json'
    rows = []
    for identity in json.loads(prior.read_text(encoding='utf-8'))['identity']:
        p = psutil.Process(identity['pid'])
        assert p.create_time() == identity['create_time'] and p.status() == 'stopped'
        c = p.cpu_times()
        rows.append(dict(pid=p.pid, user=c.user, system=c.system, status=p.status()))
    return rows


def formula_checks():
    tree = ast.parse((ORIGINAL/'learning.py').read_text(encoding='utf-8'))
    agent = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Agent')
    learn = next(n for n in agent.body if isinstance(n, ast.FunctionDef) and n.name == 'learn')
    boot = next(n for n in ast.walk(learn) if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'boot' for t in n.targets))
    # Evaluate only the pure NumPy inner expression, not Agent.learn or any optimizer.
    inner = boot.value.args[0]
    expression = compile(ast.Expression(inner), str(ORIGINAL/'learning.py')+':mask-only', 'eval')
    # offsets create every uid0..262143 exactly once; negative test-start is only arithmetic.
    starts = np.arange(-8, 262144-8, 16, dtype=np.int64)
    masks = [eval(expression, {'__builtins__': {}, 'np': np}, {'starts': starts, 'j': j}).ravel() for j in range(3)]
    assert all(len(m) == 262144 and np.all(m == 1) for m in masks)
    maximum_intermediate = (262143+2*17)*1103515245+12345
    assert maximum_intermediate < np.iinfo(np.int64).max
    mask_result = dict(status='CONFIRMED_DECLARED_BOOTSTRAP_MASK_DEFECT', original_line=boot.lineno,
        original_expression=ast.unparse(boot.value), multiplier_mod7=1103515245 % 7,
        intercept_mod7=12345 % 7, threshold=5, all_uid_count_each=262144,
        selected_fraction_each=[float(m.mean()) for m in masks],
        pairwise_mask_differences=[int(np.count_nonzero(masks[i] != masks[j])) for i, j in [(0,1),(0,2),(1,2)]],
        maximum_int64_intermediate=maximum_intermediate, overflow=False,
        consequence='Declared five-of-seven per-head sample masking is absent. Initial parameters still differ; this does not prove identical heads or quantify performance loss.')
    prior_rows = []
    for n in range(1, 9):
        empirical = 1/(n+2)
        prior_rows.append(dict(safe_record_count=n, observed_capture_count=0,
            assumed_model_capture=.03, empirical_with_prior=empirical,
            RP_capture_correction=n/(n+8)*(.03-empirical), R_capture_correction=0.))
    return dict(bootstrap=mask_result, retrieval_prior_example=dict(rows=prior_rows,
        unsupported_action_correction=0., interpretation='Algebraic example only: all-safe support can lower RP action score because of pseudocount prior. Not a measured counterfactual policy effect.'))


def case(spec):
    seed, arm = spec
    path = ORIGINAL/'evidence_matrix'/f'seed{seed}'/arm/'checkpoint_262144.pt.gz'
    with gzip.open(path, 'rb') as f:
        stored = torch.load(f, map_location='cpu', weights_only=False)
    agent = stored['agent']
    del stored
    net, r = agent.net, agent.replay
    net.eval()
    initial_hash, counters = agent.parameter_hash(), agent.counters.copy()
    assert r.n == agent.training_steps == 262144
    starts = np.linspace(r.n-len(r.action), r.n-25, 64, dtype=np.int64)
    collected, excluded = [], 0
    with torch.no_grad():
        for starts16 in starts.reshape(4, 16):
            ix = (starts16[:, None]+np.arange(25)) % len(r.action)
            hidden = net.unroll(torch.from_numpy(r.image[ix].astype(np.float32)),
                torch.from_numpy(r.scalar[ix].astype(np.float32)),
                torch.from_numpy(r.reset[ix].astype(np.float32)))
            ii, jj = ix[:, 8:24].ravel(), ix[:, 9:25].ravel()
            keep = ~r.done[ii]
            excluded += int((~keep).sum())
            cur = hidden[:, 8:24].reshape(-1, 64)[keep]
            nxt = hidden[:, 9:25].reshape(-1, 64)[keep]
            ii, jj = ii[keep], jj[keep]
            actions = torch.from_numpy(r.action[ii].astype(np.int64))
            assert np.all(r.target[ii, 7] == 0)
            legal_next = torch.from_numpy(r.legal[jj])
            raw = torch.stack([head(torch.cat((cur, F.one_hot(actions, 16).float()), -1)) for head in net.heads])
            cap, pickup = raw[..., 7].sigmoid(), F.softplus(raw[..., 6])
            pred_h = torch.tanh(cur[None]+.1*raw[..., 10:])
            pred_tail = net.q(pred_h).masked_fill(~legal_next[None], -1e9).max(-1).values
            observed_tail = net.q(nxt).masked_fill(~legal_next, -1e9).max(-1).values
            actual_pickup = torch.from_numpy(r.target[ii, 6])
            target = .015+actual_pickup+.99*observed_tail
            original = (.015+pickup-agent.penalty*cap+.99*(1-cap)*pred_tail).mean(0)
            fix_successor = (.015+pickup-agent.penalty*cap+.99*(1-cap)*observed_tail).mean(0)
            fix_outcomes = .015+actual_pickup+.99*pred_tail.mean(0)
            factual_error = pickup.mean(0)-actual_pickup-agent.penalty*cap.mean(0)
            gating_error = -.99*cap.mean(0)*observed_tail
            successor_error = .99*((1-cap)*(pred_tail-observed_tail)).mean(0)
            identity_error = original-target-factual_error-gating_error-successor_error
            assert float(identity_error.abs().max()) < 1e-5
            zero_h = torch.tanh(cur)
            collected.append(dict(original_error=(original-target).numpy(),
                successor_replaced_error=(fix_successor-target).numpy(),
                outcome_replaced_error=(fix_outcomes-target).numpy(),
                immediate_component=factual_error.numpy(), gating_component=gating_error.numpy(),
                successor_component=successor_error.numpy(), identity_error=identity_error.numpy(),
                model_hidden_MSE=((pred_h.mean(0)-nxt)**2).mean(-1).numpy(),
                identity_hidden_MSE=((cur-nxt)**2).mean(-1).numpy(),
                zero_delta_hidden_MSE=((zero_h-nxt)**2).mean(-1).numpy(),
                zero_delta_shrink_MSE=((zero_h-cur)**2).mean(-1).numpy(),
                learned_delta_change_MSE=((pred_h.mean(0)-zero_h)**2).mean(-1).numpy(),
                current_abs_gt09=(cur.abs()>.9).float().mean(-1).numpy(),
                current_abs=cur.abs().mean(-1).numpy(), actual_next_abs=nxt.abs().mean(-1).numpy(),
                zero_delta_abs=zero_h.abs().mean(-1).numpy(), predicted_next_abs=pred_h.mean(0).abs().mean(-1).numpy()))
    arrays = {k:np.concatenate([r[k] for r in collected]) for k in collected[0]}
    metrics = {}
    for k, v in arrays.items():
        if k.endswith('_error') or k.endswith('_component'):
            metrics[k] = dict(mean=float(v.mean()), MAE=float(np.abs(v).mean()), max_abs=float(np.abs(v).max()))
        else:
            metrics[k] = float(v.mean())
    assert agent.parameter_hash() == initial_hash and agent.counters == counters and r.n == 262144
    return dict(seed=seed, arm=arm, sample_positions=1024, nonterminal_positions=len(arrays['original_error']),
                terminal_positions_excluded=excluded, metrics=metrics,
                parameter_hash=initial_hash, parameters_history_counters_unchanged=True)


def main():
    out = HERE/'evidence'
    out.mkdir(exist_ok=False)
    start, initial_pause = time.perf_counter(), paused()
    save(out/'claim.json', dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        contract_sha256=hashlib.sha256((HERE/'contract.json').read_bytes()).hexdigest(), main=initial_pause))
    cases, formulas, error = [], None, None
    try:
        formulas = formula_checks()
        save(out/'formula_result.json', formulas)
        specs = [(seed, arm) for seed in range(9001, 9013) for arm in ('F-RP', 'F-R')]
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            for row in pool.map(case, specs):
                cases.append(row)
                save(out/f"seed{row['seed']}_{row['arm']}.json", row)
        assert len(cases) == 24 and paused() == initial_pause
        pins = json.loads((HERE/'source_binding.json').read_text(encoding='utf-8'))['pins']
        for pin in pins:
            p = ROOT/pin['path']
            assert p.stat().st_size == pin['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest() == pin['sha256']
        assert time.perf_counter()-start <= 300
    except BaseException:
        error = traceback.format_exc()
    result = dict(status='COMPLETE_PAUSED_OFFLINE_DECOMPOSITION' if error is None else 'ERROR_PARTIAL_RETAINED',
        exit_code=int(error is not None), error=error, formulas=formulas, cases=cases,
        wall_seconds=time.perf_counter()-start, new_training_steps=0, new_environment_steps=0,
        optimizer_updates=0, main_resumed=False)
    save(out/'result.json', result)
    print(json.dumps({k:result[k] for k in ('status','exit_code','error','wall_seconds','new_training_steps','new_environment_steps')}), flush=True)
    return result['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
