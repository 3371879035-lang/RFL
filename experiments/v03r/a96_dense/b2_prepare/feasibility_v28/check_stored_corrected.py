"""Read every stored byte/trace with stdlib only; never import or rerun RFL."""
from collections import Counter
from fractions import Fraction
from hashlib import sha1, sha256
from itertools import product
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PREP = HERE.parent


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def ordered_mean(values):
    require(values, 'empty region has no mean')
    total = 0.0
    for x in values:
        total += x
    return total / len(values)


def main():
    claim = read(HERE / 'evidence/claim.json')
    exit_record = read(HERE / 'evidence/exit.json')
    require(exit_record['native_child_exit_code'] == 0, 'native child did not complete')
    require(all(exit_record[k] == v for k, v in claim.items()), 'claim changed')
    for name, digest in claim['inputs'].items():
        require(sha256((HERE / name).read_bytes()).hexdigest() == digest, name)
    for name, record in exit_record['files'].items():
        raw = (HERE / 'evidence' / name).read_bytes()
        require(len(raw) == record['bytes'] and sha256(raw).hexdigest() == record['sha256'], name)
    require((HERE / 'evidence/stderr.log').read_bytes() == b'', 'stderr is not empty')
    raw = (HERE / 'evidence/stdout.log').read_bytes()
    stages = []
    pre, post = [], []
    pre_hash, post_hash = sha256(), sha256()
    singleton = {}
    for line in raw.splitlines(keepends=True):
        require(line.endswith(b'\n'), 'unterminated stdout line')
        tag, payload = line.rstrip(b'\r\n').split(b'=', 1)
        tag = tag.decode('ascii')
        obj = json.loads(payload)
        canonical = (json.dumps(obj, ensure_ascii=True, sort_keys=True,
                     separators=(',', ':'), allow_nan=False) + '\n').encode('utf8')
        require(payload + b'\n' == canonical, 'noncanonical or incomplete stdout line')
        stages.append(tag)
        if tag in ('PRE_SCENE', 'POST_SCENE'):
            (pre if tag == 'PRE_SCENE' else post).append(obj)
            (pre_hash if tag == 'PRE_SCENE' else post_hash).update(canonical)
        else:
            require(tag not in singleton, 'duplicate scalar stage')
            singleton[tag] = obj
    require(stages == ['INPUT_BINDING', 'FIXED_WORLD'] + ['PRE_SCENE'] * 5760 +
            ['FIXED_FACTUAL_EVENT', 'REGION', 'CALIBRATION_PREDICTION_BEFORE_POST'] +
            ['POST_SCENE'] * 5760 + ['FINAL'], 'full stdout stage extent/order differs')
    domain = list(product(range(2), range(6), range(2), range(60), range(4)))
    require([tuple(x['scene']) for x in pre] == domain == [tuple(x['scene']) for x in post],
            'not two complete ordered native U2 maps')
    require(pre == post and pre_hash.digest() == post_hash.digest(), 'pre/post traces differ')
    mapping = [[0, 1], [1, 0], [2, 0], [3, 0]]
    world = singleton['FIXED_WORLD']
    require(mapping == read(HERE / 'contract.json')['fixed_world']['proposal_mapping'] == world['declared'],
            'fixed map differs')
    require(mapping == [[z, min(set(range(4)) - {z})] for z in range(4)], 'not lex-first legal map')
    fp = sha256(b'\0' + '\n'.join(f'P:{z},{v}' for z, v in mapping).encode() + b'\0\0').hexdigest()
    require(world['pre']['fingerprint'] == fp and world['pre']['process'] == mapping,
            'canonical all-store fingerprint differs')
    for key in ('q', 'decision', 'controller'):
        require(world['pre'][key] == [], 'another persistent store acquired a deviation')
    require(world['pre']['healthy'] is False, 'pre-state is not defective')
    outcomes = Counter()
    failure_mass = Fraction(0)
    region = []
    trace_rows = 0
    for entry in pre:
        kappa, phase, error, cause, proposal = entry['scene']
        rows = entry['trace']
        require(rows and len(rows) <= 12 and entry['z_in_force'] == dict(mapping)[proposal],
                'committed process value differs')
        require(rows[0][0] == [0, 2, 0, kappa, phase], 'entry state differs')
        require(float(sum(float.fromhex(row[6]) for row in rows)).hex() == entry['return_hex'],
                'native reward sum differs')
        for i, row in enumerate(rows):
            require(len(row) == 12 and row[0][2] == i and row[7][2] == i + 1, 'trace time differs')
            require(row[0][3:] == [kappa, phase] == row[7][3:], 'trace context differs')
            require(row[3] == row[4] == row[5] and row[11] is False, 'non-Process firing/illegal')
            require(row[9] is (i == len(rows) - 1), 'terminal chronology differs')
            require(row[10] == (entry['outcome'] if row[9] else None), 'outcome differs')
            if i + 1 < len(rows):
                require(row[7] == rows[i+1][0] and row[8] == rows[i+1][1:3], 'trace discontinuity')
        trace_rows += len(rows)
        outcomes[entry['outcome']] += 1
        if entry['outcome'] != 'SUCCESS':
            failure_mass += Fraction(1, 2) * Fraction(1, 6) * Fraction(1, 4) * Fraction(1, 60) * (
                Fraction(3, 5) if error == 0 else Fraction(2, 5))
        if entry['outcome'] == 'SUCCESS' and proposal != 1:
            region.append(entry['scene'])
    factual = singleton['FIXED_FACTUAL_EVENT']
    require(factual['scene'] == [0, 2, 0, 0, 1] and factual['factual_outcome'] == 'COLLISION',
            'fixed actual failure differs')
    require(factual['fingerprint_pre'] == fp == factual['fingerprint_post'], 'factual mutation')
    require(all(v is None for v in factual['transient_fault_setup_evaluator_only'].values()),
            'transient intervention present')
    actual = next(e for e in pre if e['scene'] == factual['scene'])
    names = read(HERE / 'contract.json')['execution']['raw_scene_schema']
    require([[r[n] for n in names] for r in factual['raw_trace']] == actual['trace'],
            'factual native trace differs from census')
    truth = factual['truth']
    baseline = truth['source_separated_baseline_rows']
    require(len(baseline) == len(actual['trace']), 'manifestation rows incomplete')
    for b, row in zip(baseline, actual['trace']):
        require([b['pre_state'], b['z'], b['m'], b['a_learner'], b['u_learner']] == row[:5],
                'baseline row differs')
        require(b['a_learner'] in b['optimal_actions'], 'unretained decision manifestation')
    require(truth['Gamma_P_star'] == ['ProcessCommit'] and truth['J_L'] == [True, False, False]
            and truth['manifested_process_proposals'] == [1]
            and truth['manifested_decision_timesteps'] == truth['manifested_controller_sites'] == [],
            'complete truth differs')
    rg = singleton['REGION']
    require(rg['region_units'] == region and rg['region_size'] == len(region) == 3600,
            'region does not equal all pre-success scenes outside full owner1')
    require(rg['complete_owners'] == [1] and rg['complete_truth'] == truth['Gamma_P_star'], 'owner drift')
    require(dict(outcomes) == {k:v for k,v in rg['pre_outcomes'].items() if v}, 'outcomes differ')
    require([failure_mass.numerator, failure_mass.denominator] == rg['full_failure_mass'] == [3, 16],
            'full failure mass differs')
    conditional_mass = Fraction(1, 4800) / failure_mass
    require([conditional_mass.numerator, conditional_mass.denominator] ==
            rg['trigger_failure_conditional_mass'] == [1, 900], 'conditional mass differs')
    calibration = singleton['CALIBRATION_PREDICTION_BEFORE_POST']
    require(calibration['first_region_scene'] == region[0] == [0, 0, 0, 0, 0], 'not lex first')
    require(calibration['site'] == 'P(0)' and calibration['target'] ==
            calibration['prior_effective_value'] == dict(mapping)[0] == 1, 'not actual-state no-op')
    require(calibration['pre'] == calibration['post'] == world['pre'], 'any persistent store changed')
    require(calibration['prediction']['aggregate_difference'] == 0.0, 'predeclared state proof differs')
    mean_value = ordered_mean([float.fromhex(e['return_hex']) for e in pre
                              if e['scene'] in region])
    final = singleton['FINAL']
    require(final['pre_ordered_mean_hex'] == final['post_ordered_mean_hex'] == mean_value.hex(),
            'ordered region means differ')
    require(final['canonical_pre_scenes_sha256'] == final['canonical_post_scenes_sha256'] ==
            pre_hash.hexdigest() == rg['canonical_pre_scenes_sha256'], 'canonical trace hashes differ')
    require(final['counterexample_confirmed'] and final['same_all_stores'] and
            final['measured_difference'] == final['independent_predicted_difference'] ==
            final['maximum_scene_difference'] == 0.0, 'counterexample inference differs')
    require(not final['scientific_PASS'] and not final['collection_authorized'] and
            not final['new_scientific_rule_adopted'] and not final['valid_current_scientific_STOP'],
            'scientific authority inferred')
    binding = singleton['INPUT_BINDING']
    require(len(binding['input_sha256']) == 745, 'runtime input extent differs')
    for name, digest in binding['input_sha256'].items():
        require(sha256((ROOT / name).read_bytes()).hexdigest() == digest, name)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    require(head == binding['parent_HEAD'] == read(HERE / 'contract.json')['parent_commit'], 'HEAD drift')
    tree = {}
    for row in subprocess.check_output(['git', 'ls-tree', '-r', '-z', head], cwd=ROOT).split(b'\0'):
        if row:
            meta, name = row.split(b'\t', 1)
            tree[name.decode('utf8')] = meta.split()[2].decode('ascii')
    folder = ROOT / 'experiments/v03r/a96_dense/pipeline'
    sources = read(folder / 'frozen_inputs.json')['sources']
    audit = read(folder / 'full_f1_complete_external_audit.json')['audit']
    native = audit['fixed_native_file_hashes'] | audit['post_controller_commit_native_tail_hashes']
    prior = {p for p in tree if p.startswith('experiments/v03r/a96_dense/b2_prepare/')}
    parent_bound = set(sources) | prior | {'experiments/rebuild_status_current.json'}
    require((len(sources), len(native), len(prior), len(parent_bound)) == (313, 153, 275, 589),
            'parent byte inventory differs')
    require(set(binding['input_sha256']) == parent_bound | set(native) |
            {f'experiments/v03r/a96_dense/b2_prepare/feasibility_v28/{n}' for n in claim['inputs']},
            'runtime input membership differs')
    for p in parent_bound:
        b = (ROOT / p).read_bytes()
        require(sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest() == tree[p], p)
    for p, digest in (sources | native).items():
        require(sha256((ROOT / p).read_bytes()).hexdigest() == digest, p)
    report = {'role': 'PRIMARY_AGENT_STDLIB_STORED_CONTENT_CHECK_NOT_NATIVE_SCIENCE_OR_EXPERT_REVIEW',
              'status': 'STORED_BYTES_AND_COUNTEREXAMPLE_CHECK_COMPLETE', 'parent_HEAD': head,
              'full_stdout_bytes': len(raw), 'full_stdout_sha256': sha256(raw).hexdigest(),
              'full_pre_scene_count': len(pre), 'full_post_scene_count': len(post),
              'pre_native_trace_rows': trace_rows, 'post_native_trace_rows': trace_rows,
              'canonical_scene_sha256': pre_hash.hexdigest(), 'all_maps_and_rewards_equal': True,
              'pre_outcomes': dict(outcomes), 'proper_nonempty_region_count': len(region),
              'fixed_factual_return_hex': actual['return_hex'], 'full_credit': truth['Gamma_P_star'],
              'resolved_owner': rg['complete_owners'], 'no_op_calibration_owner': 0,
              'current_value_and_fixed_target': 1, 'independent_all_store_fingerprint': fp,
              'raw_ordered_region_mean_hex': mean_value.hex(), 'full_failure_mass': [3, 16],
              'original_trigger_mass': [1, 4800], 'conditional_trigger_mass': [1, 900],
              'proposed_k4_conditional_map_mass': [1, 81], 'proposed_family_map_mass': [1, 324],
              'parent_HEAD_byte_bindings': len(parent_bound), 'source_count': len(sources),
              'native_count': len(native), 'prior_preparation_count': len(prior),
              'runtime_input_bindings_checked': len(binding['input_sha256']),
              'counterexample_to_draft_calibration_confirmed': True,
              'RFL_imports_or_experiment_reexecution': False, 'scientific_PASS': False,
              'independent_expert_review': False, 'collection_authorized': False}
    print(json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
