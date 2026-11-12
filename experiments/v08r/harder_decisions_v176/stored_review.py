"""Independent stdlib reconstruction of V176 records; imports no native module.

Every real transition, model estimate, backup, chosen action and frozen bank is
checked. Stored bytes establish arithmetic consistency, not runtime identity.
"""
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import random
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def wire(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'))


def same(a, b):
    assert wire(a) == wire(b), 'Stored arithmetic/flow mismatch'


def digest(x):
    return hashlib.sha256(wire(x).encode()).hexdigest()


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def world(plan, condition, mirror):
    n = condition['states']
    nxt, probs, layers = [], [], []
    if condition['kind'] == 'layered_chain':
        for s, pair in enumerate(condition['canonical_forward_probabilities']):
            nxt.append([s+1, s+1]); probs.append([pair[mirror], pair[1 ^ mirror]]); layers.append(s)
    else:
        u = plan['branch_unit']
        for j in range(condition['units']):
            targets = [3*j+1, 3*j+2]
            nxt.extend([[targets[mirror], targets[1 ^ mirror]], [3*j+3]*2, [3*j+3]*2])
            probs.extend([[u[field][mirror], u[field][1 ^ mirror]] for field in
                          ('canonical_fork_probabilities', 'canonical_A_probabilities', 'canonical_B_probabilities')])
            layers.extend([2*j, 2*j+1, 2*j+1])
    return {'public': {'successors': nxt, 'layers': layers, 'goal': n, 'horizon': 12}, 'probabilities': probs}


def initial(arm, n):
    if arm == 'F0':
        return {'family': 'F0', 'counts': [[0, 0] for _ in range(2*n)], 'history': []}
    state = {'family': 'Q', 'failure_reward': -1.0 if 'RP' in arm else 0.0,
             'q': [0.0]*(2*n), 'buffer': [], 'history': []}
    if not arm.startswith('RL-'):
        state.update(family='hybrid', mode=arm.rsplit('-', 1)[1], counts=[[0, 0] for _ in range(2*n)])
    return state


def prob(state, s, a):
    yes, no = state['counts'][2*s+a]
    return (yes+1)/(yes+no+2)


def m1(state, task, s):
    terms = []
    for a in (0, 1):
        yes, no = state['counts'][2*s+a]
        p = (yes+1)/(yes+no+2)
        nxt = task['successors'][s][a]
        forward = 1.0 if nxt == task['goal'] else max(state['q'][2*nxt:2*nxt+2])
        score = p*forward+(1.0-p)*state['failure_reward']
        terms.append({'action': a, 'counts': [yes, no], 'probability': p,
                      'successor': nxt, 'continuation': forward, 'score': score})
    a = min((0, 1), key=lambda a: (-terms[a]['score'], -terms[a]['probability'], a))
    return a, terms


def policy(state, task):
    n = task['goal']
    if state['family'] == 'F0':
        reach, program, details = {n: 1.0}, [None]*n, []
        for s in range(n-1, -1, -1):
            scores = [prob(state, s, a)*reach[task['successors'][s][a]] for a in (0, 1)]
            a = 0 if scores[0] >= scores[1] else 1
            program[s], reach[s] = a, scores[a]
            details.append([s, scores])
        return program, details
    program, details = [], []
    for s in range(n):
        q = state['q'][2*s:2*s+2]
        candidates = [a for a in (0, 1) if q[a] == max(q)]
        if state['family'] == 'Q':
            a = min(candidates)
        elif state['mode'] == 'M1':
            a, terms = m1(state, task, s)
            details.append(terms)
        else:
            a = min(candidates, key=(lambda a: (-prob(state, s, a), a)) if state['mode'] == 'FT'
                    else (lambda a: (sum(state['counts'][2*s+a]), a)))
            details.append([q, candidates])
        program.append(a)
    return program, None if state['family'] == 'Q' else details


def shadow(state, task):
    rows = []
    for s in range(task['goal']):
        q, counts = state['q'][2*s:2*s+2], state['counts'][2*s:2*s+2]
        p = [prob(state, s, a) for a in (0, 1)]
        candidates = [a for a in (0, 1) if q[a] == max(q)]
        a, terms = m1(state, task, s)
        rows.append({'state': s, 'q': q, 'counts': counts, 'p': p, 'argmax': candidates,
                     'FT': min(candidates, key=lambda a: (-p[a], a)),
                     'CT': min(candidates, key=lambda a: (sum(counts[a]), a)), 'M1': a, 'M1_terms': terms})
    return rows


def learn(state, task, obs):
    uid, steps = obs['uid'], obs['steps']
    assert uid not in state['history']
    updates, facts, rewards = [], [], None
    def backup(s, a, target, kind, origin):
        i = 2*s+a
        before = state['q'][i]
        after = before+0.5*(target-before)
        state['q'][i] = after
        updates.append([kind, s, a, before, target, after, origin])
    def real(item, kind):
        old_uid, index, s, a, reward, nxt, terminal = item
        target = reward if terminal else reward+max(state['q'][2*nxt:2*nxt+2])
        backup(s, a, target, kind, [old_uid, index])
    if state['family'] != 'F0':
        rewards = [1.0 if row[3] == 'SUCCESS' else state['failure_reward'] if row[3] == 'COLLISION' else 0.0 for row in steps]
        for i, ((s, a, nxt, outcome), reward) in enumerate(zip(steps, rewards)):
            item = [uid, i, s, a, reward, nxt, outcome in ('SUCCESS', 'COLLISION')]
            state['buffer'].append(item)
            state['buffer'] = state['buffer'][-64:]
            real(item, 'ordinary')
    state['history'].append(uid)
    if state['family'] != 'Q':
        for s, a, nxt, outcome in steps:
            address = 2*s+a
            before = state['counts'][address][:]
            after = before[:]
            after[1 if outcome == 'COLLISION' else 0] += 1
            state['counts'][address] = after
            facts.append([s, a, before, after])
    if state['family'] == 'Q':
        for item in state['buffer'][::-1][:12]:
            real(item, 'replay')
    elif state['family'] == 'hybrid':
        contexts = sorted([(s, a) for s in range(task['goal']) for a in (0, 1) if sum(state['counts'][2*s+a])],
                          key=lambda x: (-task['layers'][x[0]], x[0], x[1]))
        for i in range(min(12, len(state['buffer']))):
            s, a = contexts[i % len(contexts)]
            p, nxt = prob(state, s, a), task['successors'][s][a]
            forward = 1.0 if nxt == task['goal'] else max(state['q'][2*nxt:2*nxt+2])
            backup(s, a, p*forward+(1.0-p)*state['failure_reward'], 'model', [p, forward])
    return rewards, updates, facts


def native(program, vector, source, uid, mode):
    s, steps, audit = 0, [], []
    while True:
        a, p, u = program[s], source['probabilities'][s][program[s]], vector[s]
        if u < p:
            nxt = source['public']['successors'][s][a]
            outcome = 'SUCCESS' if nxt == source['public']['goal'] else 'NEXT'
        else:
            nxt, outcome = s, 'COLLISION'
        steps.append([s, a, nxt, outcome]); audit.append([u, p])
        if outcome != 'NEXT':
            break
        s = nxt
    return {'uid': uid, 'mode': mode, 'steps': steps, 'terminal': outcome, 'audit': audit}


def policy_counts(state, task, counts):
    counts['policy_calls'] += 1
    if state['family'] == 'F0':
        counts['goal_planning_edges'] += 2*task['goal']
    elif state['family'] == 'hybrid':
        counts['actual_M1_edges' if state['mode'] == 'M1' else 'actual_tie_candidate_scores'] += 2*task['goal']


def review(directory):
    receipt = json.loads((directory/'exit.json').read_text(encoding='utf-8'))
    assert receipt['complete'] and receipt['child_exit_code'] == 0
    results, tapes, counts = [], {}, Counter()
    stream_i = uid = raw_bytes = tape_i = 0
    bank = pending = obs = None
    with gzip.open(directory/'raw.jsonl.gz', 'rt', encoding='utf-8', newline='') as f:
        for seq, line in enumerate(f):
            raw_bytes += len(line.encode())
            rec = json.loads(line)
            assert rec['seq'] == seq and wire(rec)+'\n' == line
            tag, x = rec['tag'], rec['payload']
            if tag == 'RUN_START':
                assert seq == 0
                plan, contract, phase = x['plan'], x['contract'], x['phase']
                same(plan, json.loads((ROOT/contract['plan']).read_text(encoding='utf-8')))
                same(contract, json.loads((HERE/'contract.json').read_text(encoding='utf-8')))
                for p, h in x['inputs'].items():
                    assert sha(ROOT/p) == h
                arms = [a['id'] for a in plan['arms']]
                order = [{'phase': 'wiring', 'arm': a} for a in arms] if phase == 'wiring' else [
                    {'phase': 'matrix', 'seed': s, 'mirror': m, 'condition': c['id'], 'arm': a}
                    for s in range(8001, 8033) for m in (0, 1) for c in plan['environments'] for a in arms]
            elif tag == 'TAPE':
                assert phase == 'matrix' and uid == 0
                b = x['block']; s, m, c = b['seed'], b['mirror'], b['condition']
                tokens = [(s, m, c['id']) for s in range(8001, 8033) for m in (0, 1) for c in plan['environments']]
                assert (s, m, c) == tokens[tape_i]; tape_i += 1
                n = next(c0['states'] for c0 in plan['environments'] if c0['id'] == c)
                rs = {p: random.Random(f'V08|{s}|{m}|{c}|{p}') for p in ('train_env', 'train_action', 'eval_env')}
                rebuilt = {'seed': s, 'mirror': m, 'condition': c,
                           'train_env': [[rs['train_env'].random() for _ in range(n)] for _ in range(256)],
                           'train_action': [[[rs['train_action'].random(), rs['train_action'].random()] for _ in range(n)] for _ in range(256)],
                           'eval_env': [[rs['eval_env'].random() for _ in range(n)] for _ in range(512)]}
                same(b, rebuilt); assert x['sha256'] == digest(b)
                tapes[s, m, c] = b
                counts['train_env_PRNG'] += 256*n; counts['train_action_PRNG'] += 512*n; counts['eval_env_PRNG'] += 512*n
            elif tag == 'STREAM_INITIAL':
                assert bank is None and pending is None
                context = x['context']; same(context, order[stream_i]); stream_i += 1
                baseline = Counter(counts)
                condition = {'id': 'wiring_unit', 'kind': 'serial_fork_rejoin', 'units': 1, 'states': 3, 'maximum_decisions': 2} if phase == 'wiring' else next(c for c in plan['environments'] if c['id'] == context['condition'])
                source = world(plan, condition, 0 if phase == 'wiring' else context['mirror'])
                same(source, x['source']); task = source['public']
                state = initial(context['arm'], task['goal']); same(state, x['learner'])
                counts['source_instances'] += 1
                tape = None if phase == 'wiring' else tapes[context['seed'], context['mirror'], context['condition']]
                rows, banks = [], []
                successes = steps = policy_ns = update_ns = shadow_ns = 0
                behavior = hashlib.sha256()
            elif tag == 'TRAIN_POLICY':
                assert pending is None and bank is None and x['epoch'] == len(rows)+1
                greedy, detail = policy(state, task)
                coins = [[False, 0]]*task['goal'] if phase == 'wiring' else [[u < .1, int(v*2)] for u, v in tape['train_action'][len(rows)]]
                scripted = phase == 'wiring' and len(rows) == 0
                program = [0]*task['goal'] if scripted else [a if explore else greedy[s] for s, (explore, a) in enumerate(coins)]
                covered = state['family'] == 'hybrid'
                expected_shadow = shadow(state, task) if covered else None
                for key, value in {'greedy': greedy, 'program': program, 'readout': detail, 'coins': coins,
                                   'scripted': scripted, 'shadow': expected_shadow, 'shadow_covered': covered}.items():
                    same(x[key], value)
                assert x['policy_ns'] >= 0 and x['shadow_ns'] >= 0
                policy_counts(state, task, counts)
                if covered:
                    counts['shadow_calls'] += 1; counts['shadow_M1_edges'] += 2*task['goal']; counts['shadow_tie_scores'] += 2*task['goal']
                pending = x
            elif tag == 'RAW':
                uid += 1
                if bank is not None:
                    vector = ([.1]*task['goal'] if bank['episodes'] == 0 else [.99]*task['goal']) if phase == 'wiring' else tape['eval_env'][bank['episodes']]
                    program, mode = bank['program'], 'eval'
                else:
                    assert pending is not None and obs is None
                    vector = ([.1, .99, .1] if not rows else [.1]*task['goal']) if phase == 'wiring' else tape['train_env'][len(rows)]
                    program, mode = pending['program'], 'train'
                expected = native(program, vector, source, uid, mode)
                same(x, expected)
                counts['rollouts'] += 1; counts[mode+'_rollouts'] += 1
                counts['steps'] += len(x['steps']); counts[mode+'_steps'] += len(x['steps'])
                if bank is not None:
                    bank['episodes'] += 1; bank['successes'] += x['terminal'] == 'SUCCESS'; bank['steps'] += len(x['steps'])
                else:
                    obs = x
            elif tag == 'LEARN':
                assert bank is None and pending is not None and obs is not None and x['uid'] == obs['uid']
                rewards, updates, facts = learn(state, task, obs)
                same(x['rewards'], rewards); same(x['updates'], updates); same(x['facts'], facts); same(x['after'], state)
                assert x['update_ns'] >= 0
                for u in updates:
                    counts[u[0]+'_backups'] += 1; counts['numeric_changes'] += u[3] != u[5]
                counts['fact_updates'] += len(facts)
                successes += obs['terminal'] == 'SUCCESS'; steps += len(obs['steps'])
                policy_ns += pending['policy_ns']; shadow_ns += pending['shadow_ns']; update_ns += x['update_ns']
                behavior.update((wire(obs['steps'])+'\n').encode())
            elif tag == 'TRAIN_CHECKPOINT':
                row = {'epoch': len(rows)+1, 'uid': obs['uid'], 'successes': successes, 'train_steps': steps,
                       'policy_ns': policy_ns, 'update_ns': update_ns, 'shadow_ns': shadow_ns}
                same(x, row); rows.append(row); pending = obs = None
            elif tag == 'FREEZE_BEGIN':
                assert pending is None and bank is None and x['checkpoint'] == len(rows)
                greedy, detail = policy(state, task)
                same(x['state'], state); same(x['program'], greedy); same(x['readout'], detail)
                assert x['nonalias_asserted'] and x['live_state_sha256'] == digest(state)
                assert x['policy_ns'] >= 0
                policy_counts(state, task, counts)
                bank = {'checkpoint': len(rows), 'first_uid': uid+1, 'episodes': 0, 'successes': 0, 'steps': 0,
                        'program': greedy, 'frozen_before': digest(state), 'policy_ns': x['policy_ns']}
            elif tag == 'FREEZE_END':
                assert bank is not None and bank['episodes'] == (2 if phase == 'wiring' else 512)
                expected = {**bank, 'last_uid': uid, 'mean_success': bank['successes']/bank['episodes'],
                            'frozen_after': digest(state), 'live_after': digest(state), 'learning_writes': 0}
                same(x, expected); banks.append(x); bank = None
            elif tag == 'STREAM_FINAL':
                assert pending is None and bank is None
                train_n = 2 if phase == 'wiring' else 256
                assert len(rows) == train_n
                same([b['checkpoint'] for b in banks], [2] if phase == 'wiring' else plan['matrix']['checkpoints'])
                expected = {**context, 'train_tasks': train_n, 'train_successes': successes, 'train_steps': steps,
                            'train_curve': rows, 'eval_banks': banks, 'counts': dict(counts-baseline),
                            'final_state': state, 'behavior_sha256': behavior.hexdigest(), 'source_unchanged': True}
                same(x, expected); results.append(x)
            elif tag == 'FINAL':
                assert x['complete'] and x['child_exit_code'] == 0 and x['inputs_unchanged'] and x['error'] is None
                same(x['counts'], dict(counts))
                for k, v in x.items():
                    same(receipt[k], v)
            else:
                raise AssertionError('Unexpected record '+tag)
    assert tag == 'FINAL' and len(results) == len(order) and receipt['canonical_records'] == seq+1
    assert receipt['uncompressed_bytes'] == raw_bytes and receipt['raw_sha256'] == sha(directory/'raw.jsonl.gz')
    assert receipt['compressed_bytes'] == (directory/'raw.jsonl.gz').stat().st_size
    same(json.loads((directory/'result.json').read_text(encoding='utf-8')), {'streams': results, 'counts': dict(counts)})
    limit = contract['phase_limits'][phase]
    assert counts['rollouts'] == limit['rollouts'] and counts['steps'] <= limit['steps']
    assert receipt['wall_seconds'] <= limit['wall_seconds'] and receipt['compressed_bytes'] <= limit['compressed_bytes']
    return {'status': 'STORED_ARITHMETIC_AND_FLOW_CHECK_COMPLETE', 'streams': len(results),
            'canonical_records': seq+1, 'uncompressed_bytes': raw_bytes, 'counts': dict(counts),
            'native_exit_preserved': receipt['child_exit_code'], 'declared_inputs': len(contract['inputs']),
            'reconstructed_PRNG_calls_not_new_population': 0 if phase == 'wiring' else 2211840,
            'old_RFL_or_checker_execution': 0, 'runtime_identity_reconstructed': False, 'independent_expert_qualification': False}


if __name__ == '__main__':
    start = time.perf_counter()
    directory = Path(sys.argv[1])
    try:
        report = review(directory); code = 0
    except BaseException as exc:
        report = {'status': 'STORED_REVIEW_FAILURE_PRESERVED', 'error': str(exc), 'traceback': traceback.format_exc()}; code = 1
    report.update(exit_code=code, wall_seconds=time.perf_counter()-start)
    with (directory/'audit_result.json').open('x', encoding='utf-8', newline='\n') as f:
        json.dump(report, f, ensure_ascii=False, indent=2); f.write('\n')
    print(json.dumps(report))
    raise SystemExit(code)
