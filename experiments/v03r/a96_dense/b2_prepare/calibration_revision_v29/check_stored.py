"""Independent primary-agent stdlib reconstruction; no RFL import or experiment rerun."""
import ast
from collections import Counter
from hashlib import sha1, sha256
from itertools import product
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def read(p):
    return json.loads(p.read_text(encoding='utf8'))


def canonical(obj):
    return (json.dumps(obj, ensure_ascii=True, sort_keys=True,
                       separators=(',', ':'), allow_nan=False) + '\n').encode('utf8')


def ordered_mean(values):
    require(values, 'empty region is undefined')
    result = 0.0
    for v in values:
        result += v
    return result / len(values)


def process_fp(mapping):
    return sha256(b'\0' + '\n'.join(f'P:{z},{v}' for z, v in sorted(mapping.items())
                                  if z != v).encode() + b'\0\0').hexdigest()


def verify_trace(r, scene, effective):
    rows = r['trace']
    k, p, e, c, z = scene
    require(r['scene'] == list(scene) and r['z_in_force'] == effective, 'scene/commit differs')
    require(rows and len(rows) <= 12 and rows[0][0] == [0, 2, 0, k, p], 'start/extent differs')
    require(float(sum(float.fromhex(x[6]) for x in rows)).hex() == r['return_hex'],
            'native full reward sum differs')
    for i, row in enumerate(rows):
        require(len(row) == 12 and row[0][2] == i and row[7][2] == i + 1, 'native chronology differs')
        require(row[0][3:] == row[7][3:] == [k, p], 'context differs')
        require(row[1] == effective and row[3] == row[4] == row[5] and row[11] is False,
                'another channel or illegal action present')
        require(row[9] is (i == len(rows) - 1) and
                row[10] == (r['outcome'] if row[9] else None), 'terminal/outcome differs')
        if i + 1 < len(rows):
            require(row[7] == rows[i+1][0] and row[8] == rows[i+1][1:3], 'state discontinuity')
    return len(rows)


def main():
    contract = read(HERE / 'contract.json')
    receipt = read(HERE / 'evidence/exit.json')
    claim = read(HERE / 'evidence/claim.json')
    require(receipt['native_child_exit_code'] == 0 and all(receipt[k] == v for k, v in claim.items()),
            'native receipt or claim differs')
    for n, digest in claim['inputs'].items():
        require(sha256((HERE / n).read_bytes()).hexdigest() == digest, n)
    for n, record in receipt['files'].items():
        raw = (HERE / 'evidence' / n).read_bytes()
        require(len(raw) == record['bytes'] and sha256(raw).hexdigest() == record['sha256'], n)
    require((HERE / 'evidence/stderr.log').read_bytes() == b'', 'stderr not empty')
    native_raw = (HERE / 'evidence/stdout.log').read_bytes()
    parsed = []
    for line in native_raw.splitlines(keepends=True):
        require(line.endswith(b'\n'), 'incomplete raw stdout')
        tag, payload = line.rstrip(b'\r\n').split(b'=', 1)
        obj = json.loads(payload)
        require(canonical(obj).rstrip(b'\n') == payload, 'noncanonical/incomplete payload')
        parsed.append((tag.decode(), obj))
    expected = ['INPUT_BINDING_BEFORE', 'SOURCE_REDUCTION', 'STORED_PRE_ORIGIN', 'BATTERY_SELECTED',
                'STORED_PRE_PREDICTION_CHECK'] + ['PREDICTION_BEFORE_ANY_POST'] * 3
    for target in (0, 2, 3):
        expected += ['POST_STATE'] + ['POST_SCENE'] * 5760 + ['BATTERY_RESULT']
    expected += ['NATIVE_BASIS'] + ['DERIVED_WORLD'] * 255 + ['FINITE_PROCESS_CENSUS',
                 'INPUT_BINDING_AFTER', 'FINAL']
    require([t for t, o in parsed] == expected, 'missing/duplicate/reordered native stages')
    single = {t: o for t, o in parsed if t not in
              ('PREDICTION_BEFORE_ANY_POST', 'POST_STATE', 'POST_SCENE', 'BATTERY_RESULT', 'DERIVED_WORLD')}
    predictions = {o['target']: o for t, o in parsed if t == 'PREDICTION_BEFORE_ANY_POST'}
    poststates = {o['target']: o for t, o in parsed if t == 'POST_STATE'}
    results = {o['target']: o for t, o in parsed if t == 'BATTERY_RESULT'}
    maps = {target: [] for target in (0, 2, 3)}
    map_hashes = {target: sha256() for target in maps}
    for t, o in parsed:
        if t == 'POST_SCENE':
            maps[o['target']].append(o['payload'])
            map_hashes[o['target']].update(canonical(o))
    oldfolder = ROOT / contract['preserved_counterexample']['folder']
    oldraw = (oldfolder / 'evidence/stdout.log').read_bytes()
    require(sha256(oldraw).hexdigest() == contract['preserved_counterexample']['stdout_sha256'],
            'stored old native bytes differ')
    pre, pre_hash, oldscalar = [], sha256(), {}
    for line in oldraw.splitlines():
        t, payload = line.split(b'=', 1)
        o = json.loads(payload)
        if t == b'PRE_SCENE':
            pre.append(o)
            pre_hash.update(canonical(o))
        elif t != b'POST_SCENE':
            oldscalar[t.decode()] = o
    domain = list(product(range(2), range(6), range(2), range(60), range(4)))
    require([tuple(r['scene']) for r in pre] == domain and pre_hash.hexdigest() ==
            contract['preserved_counterexample']['canonical_pre_map_sha256'], 'old pre incomplete')
    world = dict(contract['fixed_world']['proposal_mapping'])
    require(world == {0:1, 1:0, 2:0, 3:0}, 'fixed world changed')
    factual = oldscalar['FIXED_FACTUAL_EVENT']
    truth = factual['truth']
    require(truth['Gamma_P_star'] == ['ProcessCommit'] and truth['J_L'] == [True, False, False]
            and truth['manifested_process_proposals'] == [1] and
            truth['manifested_decision_timesteps'] == truth['manifested_controller_sites'] == [],
            'whole original truth not retained')
    origin = single['STORED_PRE_ORIGIN']
    require(origin['stored_native_event'] == factual and origin['whole_truth'] == truth and
            origin['complete_original_owners'] == [1] and not origin['old_noop_repeated'] and
            origin['new_pre_rollouts'] == 0, 'old evidence misattributed as new execution')
    selected = single['BATTERY_SELECTED']
    indices = [i for i, r in enumerate(pre) if r['outcome'] == 'SUCCESS' and domain[i][4] != 1]
    require([pre[i]['scene'] for i in indices] == oldscalar['REGION']['region_units'] and
            len(indices) == selected['region_size'] == 3600, 'original full E(P1) changed')
    require(selected['site'] == 0 and selected['actual_pre_value'] == 1 and selected['targets'] == [0,2,3]
            and selected['first_region_scene'] == pre[indices[0]]['scene'] == [0,0,0,0,0],
            'not the prospective fixed actual-state battery')
    require(selected['pre']['fingerprint'] == process_fp(world) and
            selected['pre'] == read(oldfolder / 'result_summary.json')['fixed_world']['pre'],
            'pre-state not all-store identical')
    basis = {}
    pre_rows = sum(verify_trace(r, s, world[s[4]]) for r, s in zip(pre, domain))
    new_rows, zero_count = 0, 0
    values_pre = [float.fromhex(r['return_hex']) for r in pre]
    mean_pre = ordered_mean([values_pre[i] for i in indices])
    for target in (0,2,3):
        state = poststates[target]['state']
        changed = dict(world)
        changed[0] = target
        require(state['process'] == [[z,v] for z,v in sorted(changed.items()) if z!=v]
                and state['fingerprint'] == process_fp(changed) != process_fp(world),
                'not canonical single-owner actual change')
        require(not state['q'] and not state['decision'] and not state['controller'],
                'another store changed')
        rows = maps[target]
        require([tuple(r['scene']) for r in rows] == domain, 'new post U2 incomplete')
        new_rows += sum(verify_trace(r, s, changed[s[4]]) for r, s in zip(rows, domain))
        pv = [float.fromhex(v) for v in predictions[target]['all_scene_return_hex']]
        require(len(pv) == 5760 and not predictions[target]['uses_measured_post'], 'prediction incomplete')
        measured_values = [float.fromhex(r['return_hex']) for r in rows]
        maximum_error = max(abs(a-b) for a,b in zip(pv, measured_values))
        require(maximum_error <= 1e-12 and maximum_error == results[target]['maximum_scene_prediction_error'],
                'scene prediction mismatch')
        postmean = ordered_mean([measured_values[i] for i in indices])
        predictionmean = ordered_mean([pv[i] for i in indices])
        pdiff, mdiff = mean_pre-predictionmean, mean_pre-postmean
        require(predictions[target]['pre_ordered_mean_hex'] == results[target]['pre_ordered_mean_hex'] ==
                mean_pre.hex() and predictions[target]['signed_difference_hex'] ==
                results[target]['predicted_difference_hex'] == pdiff.hex() and
                results[target]['post_ordered_mean_hex'] == postmean.hex() and
                results[target]['measured_difference_hex'] == mdiff.hex(), 'ordered scalar differs')
        require(abs(pdiff-mdiff) <= max(1e-12,1e-6*abs(pdiff)), 'aggregate mismatch')
        require(map_hashes[target].hexdigest() == results[target]['canonical_post_map_sha256'],
                'complete map hash differs')
        zero_count += mdiff == 0.0
        for s, r, old in zip(domain, rows, pre):
            if s[4] != 0:
                require(r == old, 'untouched proposal changed')
    for z, rows in [(1,pre)] + list(maps.items()):
        for r in rows:
            if r['scene'][4] == 0:
                key = (r['scene'][0], r['scene'][1], z)
                value = {n:r[n] for n in ('outcome','return_hex','z_in_force','trace')}
                if key in basis:
                    require(basis[key] == value, 'error/cause changes behavior')
                basis[key] = value
    require(len(basis) == 48 and single['NATIVE_BASIS']['entries'] ==
            [{'kappa':k, 'phase':p, 'committed':z, 'payload':v} for (k,p,z),v in sorted(basis.items())],
            'native full committed-option basis incomplete')
    for z, rows in [(1,pre)] + list(maps.items()):
        for r in rows:
            proposal = r['scene'][4]
            effective = z if proposal==0 else world[proposal]
            require({n:r[n] for n in ('outcome','return_hex','z_in_force','trace')} ==
                    basis[r['scene'][0],r['scene'][1],effective], 'factorization not full-map consistent')
    source = single['SOURCE_REDUCTION']
    for p,d in source['source_sha256'].items():
        require(sha256((ROOT/p).read_bytes()).hexdigest()==d, p)
    treeast = ast.parse((ROOT/'src/rfl_rebuild/env/kernel.py').read_text(encoding='utf8'))
    fs = {n.name:n for n in treeast.body if isinstance(n,ast.FunctionDef)}
    require(not any(isinstance(n,ast.Name) and n.id=='tape' for n in ast.walk(fs['step'])),
            'step reads tape, reduction invalid')
    cont = fs['continue_rollout']
    parents = {c:n for n in ast.walk(cont) for c in ast.iter_child_nodes(n)}
    for n in ast.walk(cont):
        if isinstance(n,ast.Name) and n.id in ('base_option','option_in_force'):
            par = parents[n]
            require(isinstance(par,ast.keyword) and par.arg==n.id and
                    isinstance(parents[par],ast.Call) and isinstance(parents[par].func,ast.Name) and
                    parents[par].func.id=='RolloutTrace','proposal affects continuation')
    counters, signs, registry_hash = Counter(), Counter(), sha256()
    records = [o for t,o in parsed if t=='DERIVED_WORLD']
    worlds = [w for w in product(range(4),repeat=4) if w!=tuple(range(4))]
    require([tuple(r['world']) for r in records]==worlds, 'a difficult world was lost/reordered')
    for w,record in zip(worlds,records):
        outcomes = Counter(basis[s[0],s[1],w[s[4]]]['outcome'] for s in domain)
        owners = sorted({s[4] for s in domain if w[s[4]]!=s[4] and
                         basis[s[0],s[1],w[s[4]]]['outcome']!='SUCCESS'})
        require(record['derived_outcomes']==dict(outcomes) and record['actual_manifesting_failure_owners']==owners
                and record['k']==sum(z!=v for z,v in enumerate(w)) and record['native_world_rollouts']==0
                and record['statistical_N'] is None and not record['scientific_population_adopted'],
                'derived world membership/claim differs')
        expected_regions = []
        for owner in owners:
            selected_indices = [i for i,s in enumerate(domain) if s[4]!=owner and
                                basis[s[0],s[1],w[s[4]]]['outcome']=='SUCCESS']
            require(selected_indices, 'unexpected empty Process-only production region')
            first = domain[selected_indices[0]]
            site = first[4]
            before_mean = ordered_mean([float.fromhex(basis[domain[i][0],domain[i][1],w[domain[i][4]]]
                                                      ['return_hex']) for i in selected_indices])
            battery = []
            for target in range(4):
                if target==w[site]:
                    continue
                post_mean = ordered_mean([float.fromhex(basis[domain[i][0],domain[i][1],
                          target if domain[i][4]==site else w[domain[i][4]]]['return_hex'])
                          for i in selected_indices])
                effect = before_mean-post_mean
                signs['positive' if effect>0 else 'negative' if effect<0 else 'zero'] += 1
                battery.append({'target':target,'post_mean_hex':post_mean.hex(),
                                'signed_difference_hex':effect.hex()})
            sensitive = any(float.fromhex(b['signed_difference_hex'])!=0 for b in battery)
            expected_regions.append({'owner':owner,'region_size':len(selected_indices),
                 'complete_truth':['ProcessCommit'],'first_region_scene':list(first),'site':site,
                 'actual_pre_value':w[site],'pre_mean_hex':before_mean.hex(),
                 'status':'NONZERO_BATTERY_EXISTS' if sensitive else 'ALL_ZERO_UNCERTIFIED',
                 'battery':battery,'address_replacement':False})
            counters['owner_regions'] += 1
            counters['sensitive_owner_regions' if sensitive else 'all_zero_owner_regions'] += 1
        require(record['owner_regions']==expected_regions,'full derived owner battery differs')
        counters['worlds'] += 1
        counters['trigger_worlds' if owners else 'nontrigger_worlds_retained'] += 1
        registry_hash.update(canonical(record))
    census = single['FINITE_PROCESS_CENSUS']
    require(census['counts']==dict(counters) and census['canonical_registry_sha256']==registry_hash.hexdigest()
            and census['all255_including_nontriggers_retained'] and not census['native_world_census_executed']
            and not census['full_B2_totality_certified'],'census extent/hash/claims differ')
    before,after = single['INPUT_BINDING_BEFORE'],single['INPUT_BINDING_AFTER']
    require(before==after and len(before['input_sha256'])==757,'run bindings differ')
    for p,d in before['input_sha256'].items():
        require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(head==contract['parent_commit']==before['parent_HEAD'],'parent changed')
    git_tree = {}
    for row in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0'):
        if row:
            meta,n = row.split(b'\t',1)
            git_tree[n.decode('utf8')]=meta.split()[2].decode()
    pipeline = ROOT/'experiments/v03r/a96_dense/pipeline'
    sources = read(pipeline/'frozen_inputs.json')['sources']
    audit = read(pipeline/'full_f1_complete_external_audit.json')['audit']
    native = audit['fixed_native_file_hashes']|audit['post_controller_commit_native_tail_hashes']
    prior = {p for p in git_tree if p.startswith('experiments/v03r/a96_dense/b2_prepare/')}
    parent_bound = set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(parent_bound))==(313,153,287,601),'parent extent differs')
    require(set(before['input_sha256'])==parent_bound|set(native)|
            {f'experiments/v03r/a96_dense/b2_prepare/calibration_revision_v29/{n}' for n in claim['inputs']},
            'runtime membership differs')
    for p in parent_bound:
        raw = (ROOT/p).read_bytes()
        require(sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==git_tree[p],p)
    for p,d in (sources|native).items():
        require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    final = single['FINAL']
    require(final['battery_results']==list(results.values()) and final['finite_process_census']==census
            and final['new_native_post_rollouts']==17280 and final['new_native_post_trace_rows']==new_rows
            and final['new_native_pre_or_factual_rollouts']==0 and final['native_update_law_treatment_calls']==0,
            'execution counts differ')
    for key in ('scientific_PASS','new_scientific_rule_adopted','delta_joint_computed_or_adopted',
                'population_reduced','collection_authorized','valid_current_scientific_STOP',
                'whole_scientific_domain_totality','research_complete'):
        require(final[key] is False,'scientific authority or completion inferred')
    report = {'role':'PRIMARY_AGENT_STDLIB_STORED_CONTENT_CHECK_NOT_EXPERT_OR_SCIENTIFIC_PASS',
        'status':'COMPLETE_ALL_NATIVE_MAPS_AND_FINITE_PROCESS_REGISTRY_CHECK',
        'parent_HEAD':head,'runtime_input_bindings_checked':757,'parent_HEAD_byte_bindings':601,
        'source_count':313,'native_count':153,'prior_preparation_count':287,
        'native_stdout_bytes':len(native_raw),'native_stdout_sha256':sha256(native_raw).hexdigest(),
        'old5760_pre_scenes_read_not_reexecuted':len(pre),'old_pre_trace_rows_read':pre_rows,
        'new_post_scenes_checked':17280,'new_post_trace_rows_checked':new_rows,
        'basis_entries':48,'complete_finite_Process_counts':dict(counters),
        'derived_battery_effect_signs_all_retained':dict(signs),
        'canonical_registry_sha256':registry_hash.hexdigest(),
        'actual_fixed_battery_results':list(results.values()),
        'RFL_imports_or_experiment_reexecution':False,'independent_expert_review':False,
        'full_B2_totality_certified':False,'scientific_PASS':False,'collection_authorized':False}
    print(json.dumps(report,ensure_ascii=True,sort_keys=True,allow_nan=False))


if __name__=='__main__':
    main()
