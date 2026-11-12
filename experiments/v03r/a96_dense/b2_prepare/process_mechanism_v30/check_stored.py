"""Primary stdlib-only full raw/receipt reconstruction, not another experiment."""
import ast
from collections import Counter
from hashlib import sha1, sha256
import importlib.util
from itertools import product
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PREP = HERE.parent
ROOT = HERE.parents[4]
# Generic byte/chronology helpers only; never invoke the prior checker main.
spec = importlib.util.spec_from_file_location('v29_stdlib_helpers',PREP/'calibration_revision_v29/check_stored.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)
canonical, require, process_fp, verify_trace = (helpers.canonical, helpers.require,
                                               helpers.process_fp, helpers.verify_trace)


def read(p):
    return json.loads(p.read_text(encoding='utf8'))


def capture(folder, code, compact=True):
    claim,receipt = read(folder/'claim.json'),read(folder/'exit.json')
    require(receipt['native_child_exit_code']==code,'actual native exit differs')
    require(all(receipt[k]==v for k,v in claim.items()),'claim not carried into receipt')
    for name,digest in claim['inputs'].items():
        require(sha256((folder.parent/name).read_bytes()).hexdigest()==digest,'capture source differs '+name)
    for name,item in receipt['files'].items():
        raw = (folder/name).read_bytes()
        require(len(raw)==item['bytes'] and sha256(raw).hexdigest()==item['sha256'],'complete raw differs '+name)
    raw = (folder/'stdout.log').read_bytes()
    records = []
    for line in raw.splitlines(keepends=True):
        require(line.endswith(b'\n'),'incomplete raw output')
        tag,payload = line.rstrip(b'\r\n').split(b'=',1)
        obj = json.loads(payload)
        encoded = canonical(obj).rstrip(b'\n') if compact else json.dumps(
                  obj,ensure_ascii=True,sort_keys=True,allow_nan=False).encode('utf8')
        require(encoded==payload,'unexpected log encoding')
        records.append((tag.decode(),obj))
    return records,receipt


def derived(w, owner, basis, domain):
    post = list(w); post[owner]=owner
    a = [basis[s[0],s[1],w[s[4]]] for s in domain]
    b = [basis[s[0],s[1],post[s[4]]] for s in domain]
    indices = [i for i,s in enumerate(domain) if s[4]==owner and w[owner]!=owner and a[i]['outcome']!='SUCCESS']
    off = [i for i,s in enumerate(domain) if s[4]!=owner]
    region = [i for i in off if a[i]['outcome']=='SUCCESS']
    require(indices and region,'unexpected missing domain, never remove it')
    oldmean = helpers.ordered_mean([float.fromhex(a[i]['return_hex']) for i in region])
    newmean = helpers.ordered_mean([float.fromhex(b[i]['return_hex']) for i in region])
    digest = {id(v):sha256(canonical(v)).hexdigest() for v in basis.values()}
    ha,hb = sha256(),sha256();signs=Counter();cost=0
    for s,v,u in zip(domain,a,b):
        d = float.fromhex(u['return_hex'])-float.fromhex(v['return_hex'])
        signs['positive' if d>0 else 'negative' if d<0 else 'zero']+=1
        cost += v['outcome']=='SUCCESS' and d<0
        ha.update(canonical({'scene':list(s),'basis_payload_sha256':digest[id(v)]}))
        hb.update(canonical({'scene':list(s),'basis_payload_sha256':digest[id(u)]}))
    return {'world':list(w),'owner':owner,'post_world':post,'first_trigger_scene':list(domain[indices[0]]),
         'complete_credit':['ProcessCommit'],'trigger_scene_count':len(indices),
         'all_trigger_post_outcomes':dict(Counter(b[i]['outcome'] for i in indices)),
         'outside_owner_scene_count':len(off),'outside_owner_full_behavior_equal':all(a[i]==b[i] for i in off),
         'original_E_owner_size':len(region),'E_owner_pre_mean_hex':oldmean.hex(),
         'E_owner_post_mean_hex':newmean.hex(),'E_owner_signed_difference_hex':(oldmean-newmean).hex(),
         'all_scene_return_change_signs':dict(signs),'previously_successful_scene_return_decreases':cost,
         'canonical_full5760_pre_map_reference_sha256':ha.hexdigest(),
         'canonical_full5760_post_map_reference_sha256':hb.hexdigest(),
         'post_healthy':post==list(range(4)),'native_full5760_post_census':False,'statistical_N':None}


def raw_audit(a):
    fields=['pre_state','z','m','a_cmd','u','a_realized','reward_hex','post_state','post_control',
            'terminal','outcome','illegal']
    rows=[[r[f] for f in fields] for r in a['raw_trace']]
    return {'scene':a['scene'],'outcome':a['factual_outcome'],'z_in_force':a['z_in_force'],
            'return_hex':float(sum(float.fromhex(r[6]) for r in rows)).hex(),'trace':rows}


def main():
    c=read(HERE/'contract.json')
    original,r0=capture(HERE/'evidence',1)
    format_only,r1=capture(HERE/'evidence_corrected',1)
    records,r2=capture(HERE/'evidence_api_corrected',0)
    require([t for t,o in original]==['INPUT_BINDING_BEFORE','SOURCE_REDUCTION'],'initial failure stage differs')
    require('noncanonical historical content' in (HERE/'evidence/stderr.log').read_text(encoding='utf8'),
            'initial failure cause differs')
    require('unexpected keyword argument' in (HERE/'evidence_corrected/stderr.log').read_text(encoding='utf8'),
            'Oracle API failure cause differs')
    require(not any(t=='ACTUAL_PAIR' for t,o in format_only),'partial native pair executed before API failure')
    require((HERE/'evidence_api_corrected/stderr.log').read_bytes()==b'','completed component stderr nonempty')
    for contract in ('repair_contract.json','api_repair_contract.json'):
        repair=read(HERE/contract)
        names=repair.get('both_failure_files_sha256',repair.get('initial_failure_files_sha256'))
        for p,d in names.items():require(sha256((HERE/p).read_bytes()).hexdigest()==d,'prior failure overwritten')
    # Stored native evidence is read in full, not rerun or promoted to a new PASS.
    old,oldreceipt=capture(PREP/'calibration_revision_v29/evidence',0)
    old26,receipt26=capture(PREP/'mechanism_v26/evidence',0,compact=False)
    require(oldreceipt['files']['stdout.log']['sha256']==c['stored_basis']['stdout_sha256'] and
            receipt26['files']['stdout.log']['sha256']==c['stored_exact_pair']['stdout_sha256'],'historical origin differs')
    basis_record=[o for t,o in old if t=='NATIVE_BASIS'][0]
    basis={(e['kappa'],e['phase'],e['committed']):e['payload'] for e in basis_record['entries']}
    require(set(basis)==set(product(range(2),range(6),range(4))),'basis incomplete')
    domain=list(product(range(2),range(6),range(2),range(60),range(4)))
    old28,receipt28=capture(PREP/'feasibility_v28/evidence',0)
    pre=[o for t,o in old28 if t=='PRE_SCENE']
    maps={x:[] for x in (0,2,3)}
    for t,o in old:
        if t=='POST_SCENE':maps[o['target']].append(o['payload'])
    stored_rows=0
    for z,rows in [(1,pre)]+list(maps.items()):
        require([tuple(r['scene']) for r in rows]==domain,'old full native U2 map incomplete')
        for s,r in zip(domain,rows):
            effective=z if s[4]==0 else [1,0,0,0][s[4]]
            stored_rows+=verify_trace(r,s,effective)
            require({n:r[n] for n in ('outcome','return_hex','z_in_force','trace')}==basis[s[0],s[1],effective],
                    'old native basis factorization differs')
    for t,o in records:
        if t=='SOURCE_REDUCTION':
            for p,d in o['source_sha256'].items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    kernel=ast.parse((ROOT/'src/rfl_rebuild/env/kernel.py').read_text(encoding='utf8'))
    fs={n.name:n for n in kernel.body if isinstance(n,ast.FunctionDef)}
    require(not any(isinstance(n,ast.Name) and n.id=='tape' for n in ast.walk(fs['step'])),'tape affects basis')
    parents={ch:n for n in ast.walk(fs['continue_rollout']) for ch in ast.iter_child_nodes(n)}
    for n in ast.walk(fs['continue_rollout']):
        if isinstance(n,ast.Name) and n.id in ('base_option','option_in_force'):
            p=parents[n]
            require(isinstance(p,ast.keyword) and p.arg==n.id and isinstance(parents[p],ast.Call) and
                    isinstance(parents[p].func,ast.Name) and parents[p].func.id=='RolloutTrace','proposal affects continuation')
    worlds=[w for w in product(range(4),repeat=4) if w!=tuple(range(4))]
    memberships=[o for t,o in records if t=='WORLD_MEMBERSHIP']
    predictions=[o for t,o in records if t=='PAIR_PREDICTION_BEFORE_EXECUTION']
    actual=[o for t,o in records if t=='ACTUAL_PAIR']
    audits=[o for t,o in records if t=='OWNED_FACTUAL_BEFORE_ORACLE']
    require([tuple(o['world']) for o in memberships]==worlds,'world dropped or reordered')
    closed_index=next(i for i,(t,o) in enumerate(records) if t=='ALL_PREDICTIONS_CLOSED')
    require(all(i>closed_index for i,(t,o) in enumerate(records) if t in
                ('OWNED_FACTUAL_BEFORE_ORACLE','ACTUAL_PAIR')),'post affected prospective predictions')
    closed=records[closed_index][1]
    require(closed['canonical_predictions_sha256']==sha256(b''.join(canonical(o) for o in predictions)).hexdigest(),
            'prediction complete registry hash differs')
    expected_pairs=[];counts=Counter();costs=Counter();signs=Counter()
    for w,rec in zip(worlds,memberships):
        owners=sorted({s[4] for s in domain if w[s[4]]!=s[4] and basis[s[0],s[1],w[s[4]]]['outcome']!='SUCCESS'})
        outcomes=Counter(basis[s[0],s[1],w[s[4]]]['outcome'] for s in domain)
        require(rec=={'world':list(w),'k':sum(v!=z for z,v in enumerate(w)),
                     'actual_manifesting_failure_owners':owners,'derived_outcomes':dict(outcomes),
                     'native_world_census':False,'statistical_N':None},'world membership differs')
        counts['trigger_worlds' if owners else 'nontrigger_worlds']+=1
        for owner in owners:
            o=derived(w,owner,basis,domain)
            o['execution_origin']='STORED_V26_EXACT_PAIR_NOT_RERUN' if (list(w)==c['stored_exact_pair']['world']
                                     and owner==c['stored_exact_pair']['owner']) else 'NEW_NATIVE_B1_PAIR'
            expected_pairs.append(o)
            signs.update(o['all_scene_return_change_signs'])
            costs[owner]+=o['previously_successful_scene_return_decreases']
    require(predictions==expected_pairs and len(actual)==len(predictions)==192,'pair domain/complete predictions differ')
    require([t for t,o in format_only]==[t for t,o in records[:closed_index+1]],'API failure stage differs')
    require([o for t,o in format_only if t in ('WORLD_MEMBERSHIP','PAIR_PREDICTION_BEFORE_EXECUTION')]==
            [o for t,o in records if t in ('WORLD_MEMBERSHIP','PAIR_PREDICTION_BEFORE_EXECUTION')],
            'API correction changed world or prediction results')
    prior=[o for t,o in old26 if t=='COMPLETE_CHANNELS'][0][0]
    new_rows=0;new_pairs=0;healthy_after=0
    for p,a in zip(predictions,actual):
        w,owner=p['world'],p['owner'];post=p['post_world'];scene=p['first_trigger_scene']
        require(a['world']==w and a['owner']==owner and a['origin']==p['execution_origin'],'pair execution origin differs')
        require(a['pre']['process']==[[z,v] for z,v in enumerate(w) if z!=v] and
                a['pre']['fingerprint']==process_fp(dict(enumerate(w))) and
                a['pre']['q']==a['pre']['decision']==a['pre']['controller']==[],'full pre differs')
        audit=a['audit'];truth=audit['truth']
        require(truth['Gamma_P_star']==['ProcessCommit'] and truth['J_L']==[True,False,False] and
                truth['manifested_process_proposals']==[owner] and
                truth['manifested_decision_timesteps']==truth['manifested_controller_sites']==[],
                'whole Oracle truth lost')
        require(audit['scene']==scene and audit['fingerprint_pre']==audit['fingerprint_post']==a['pre']['fingerprint'] and
                audit['environment_seed_draws']==audit['future_training_episodes']==0,'factual binding differs')
        for row in truth['source_separated_baseline_rows']:
            require(row['a_learner'] in row['optimal_actions'] and row['u_learner']==row['a_learner'],
                    'non-Process manifestation trimmed')
        r=raw_audit(audit);verify_trace(r,tuple(scene),w[owner])
        require({n:r[n] for n in ('outcome','return_hex','z_in_force','trace')}==basis[scene[0],scene[1],w[owner]],'factual raw differs')
        require([arm['role'] for arm in a['arms']]==['reference','treatment'],'same-tier arms missing/reordered')
        for arm in a['arms']:
            treatment=arm['role']=='treatment';state=arm['all_store_post'];mapping=post if treatment else w
            require(arm['tier']=='L1_CORRECTIVE' and arm['law']==('P_id' if treatment else 'NoWrite'),'tier or law differs')
            require(state['process']==[[z,v] for z,v in enumerate(mapping) if z!=v] and
                    state['fingerprint']==process_fp(dict(enumerate(mapping))) and
                    state['q']==state['controller']==state['decision']==[] and
                    state['healthy']==(mapping==list(range(4))),'post/locality fingerprint differs')
            expected_ledger={'fingerprint_pre':a['pre']['fingerprint'],'fingerprint_post':state['fingerprint'],
                  'receipts':[f'z={owner}|'+('APPLIED|1' if treatment else 'EVALUABLE_NOOP|0')],
                  'scalar_metrics_applicable':False,'n_scalar':0,'sum_abs_delta':0.0,'max_abs_delta':0.0}
            require(arm['ledger']==expected_ledger,'complete native ledger differs')
            expected_transaction=[{'on_this_clone':True,'fingerprint_pre':a['pre']['fingerprint'],
                    'entry_edits':1,'stores':['process'],'addresses':[str(owner)]}] if treatment else []
            require(arm['transactions']==expected_transaction,'not one same-pre owner-local transaction')
            r=arm['raw'];rows=verify_trace(r,tuple(scene),mapping[owner])
            require({n:r[n] for n in ('outcome','return_hex','z_in_force','trace')}==
                    basis[scene[0],scene[1],mapping[owner]],'immediate complete raw differs')
            if a['origin']=='NEW_NATIVE_B1_PAIR':new_rows+=rows
        if a['origin']=='NEW_NATIVE_B1_PAIR':
            require(a['new_rollouts']==3 and a['new_B1_arms']==2,'new execution counts differ')
            require(audits[new_pairs]=={'world':w,'owner':owner,'audit':audit},'audit not emitted before Oracle')
            new_rows+=len(audit['raw_trace']);new_pairs+=1
        else:
            require(a['new_rollouts']==a['new_B1_arms']==0 and a['pre']==prior['all_store_pre'] and
                    a['audit']==prior['original_owned_audit'],'stored exact pair misattributed')
            for oldarm,newarm in zip(prior['same_tier_pair'],a['arms']):
                require({k:newarm[k] for k in oldarm}==oldarm,'historical native pair modified')
        healthy_after+=p['post_healthy']
        require(p['all_trigger_post_outcomes']=={'SUCCESS':p['trigger_scene_count']} and
                p['outside_owner_full_behavior_equal'] and float.fromhex(p['E_owner_signed_difference_hex'])==0,
                'reported mechanism/locality result differs')
    require(new_pairs==len(audits)==191,'new native scope differs')
    single={t:o for t,o in records if t in ('INPUT_BINDING_BEFORE','INPUT_BINDING_AFTER','FINAL')}
    before,after=single['INPUT_BINDING_BEFORE'],single['INPUT_BINDING_AFTER']
    require(before==after and len(before['input_sha256'])==787,'full runtime binding differs')
    for p,d in before['input_sha256'].items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(head==c['parent_commit']==before['parent_HEAD'],'parent changed')
    tree={}
    for row in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0'):
        if row:
            meta,p=row.split(b'\t',1);tree[p.decode('utf8')]=meta.split()[2].decode()
    pipeline=ROOT/'experiments/v03r/a96_dense/pipeline'
    sources=read(pipeline/'frozen_inputs.json')['sources']
    na=read(pipeline/'full_f1_complete_external_audit.json')['audit']
    native=na['fixed_native_file_hashes']|na['post_controller_commit_native_tail_hashes']
    priorpaths={p for p in tree if p.startswith('experiments/v03r/a96_dense/b2_prepare/')}
    bound=set(sources)|priorpaths|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(priorpaths),len(bound))==(313,153,303,617),'parent extent differs')
    for p in bound:
        raw=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==tree[p],p)
    for p,d in (sources|native).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    final=single['FINAL']
    require(final['canonical_actual_pairs_sha256']==sha256(b''.join(canonical(o) for o in actual)).hexdigest(),
            'full actual registry hash differs')
    require(final['new_native_pairs']==191 and final['new_native_B1_arms']==382 and
            final['new_native_repair_transactions']==191 and final['new_native_factual_rollouts']==191 and
            final['new_native_immediate_rollouts']==382 and final['historical_native_pairs_read_not_reexecuted']==1,
            'final component counts differ')
    for k in ('full_B2_totality_certified','scientific_PASS','new_scientific_rule_adopted','collector_executed',
              'collection_authorized','research_complete','valid_current_scientific_STOP'):
        require(final[k] is False,'unauthorized scientific conclusion')
    report={'role':'PRIMARY_STDLIB_RAW_CHECK_NOT_EXPERT_OR_SCIENTIFIC_PASS','status':'COMPLETE_FINITE_PROCESS_COMPONENT_CHECK',
      'parent_HEAD':head,'runtime_input_count':787,'parent_HEAD_byte_bindings':617,'source_count':313,
      'native_count':153,'prior_preparation_count':303,'worlds':255,**dict(counts),'owner_pairs':192,
      'new_native_pairs':191,'new_B1_arms':382,'new_repair_transactions':191,
      'completed_capture_new_factual_rollouts':191,'completed_capture_new_immediate_rollouts':382,
      'preceding_API_failure_extra_factual_rollout':1,'all_attempts_actual_new_rollouts':574,
      'new_complete_capture_raw_trace_rows':new_rows,'stored_basis_scenes_read':23040,'stored_basis_raw_rows_read':stored_rows,
      'all_scene_derived_return_change_signs':dict(signs),'owner_success_return_costs':dict(costs),
      'post_healthy_pair_count':healthy_after,'post_still_defective_pair_count':192-healthy_after,
      'all_owner_trigger_scenes_recovered_by_source_reduction':True,'outside_owner_exact_behavior_unchanged':True,
      'canonical_prediction_registry_sha256':closed['canonical_predictions_sha256'],
      'canonical_actual_registry_sha256':final['canonical_actual_pairs_sha256'],
      'native_stdout_bytes':r2['files']['stdout.log']['bytes'],'native_stdout_sha256':r2['files']['stdout.log']['sha256'],
      'initial_and_format_corrected_failures_preserved':True,'candidate_or_RFL_reexecution':False,
      'independent_expert_review':False,'statistical_N':None,'scientific_PASS':False,'collection_authorized':False}
    print(json.dumps(report,ensure_ascii=True,sort_keys=True))


if __name__=='__main__':main()
