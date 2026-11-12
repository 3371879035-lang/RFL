"""Finite original Process PId component; stored basis is explicit, not new science."""
from collections import Counter
from hashlib import sha1, sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PREP = HERE.parent
ROOT = PREP.parents[3]
sys.path.insert(0, str(PREP))
import readiness as ready
import factual_event_candidate as factual
from calibration_revision_v29.candidate import canonical, emit, require, state_payload, raw_scene, source_proof
from rfl_rebuild.b1.contract import fingerprint
from rfl_rebuild.b1.laws import NoWriteRef, PId
from rfl_rebuild.b1.process import AssistedInput, resolve_process_addresses
from rfl_rebuild.b1.runner import run_process_law
from rfl_rebuild.b1.tier import Tier
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.unaffected import scene_domain
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.learner.store import PROCESS, Edit, LearnerPersistentState
from rfl_rebuild.method.credit import OracleCreditAdapter
from rfl_rebuild.solve.dp import solve_reference


def bindings():
    c = ready.read_json(HERE / 'contract.json')
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(head == c['parent_commit'], 'parent changed')
    sources = ready.read_json(ROOT / ready.FOLDER / 'pipeline/frozen_inputs.json')['sources']
    audit = ready.read_json(ROOT / ready.FOLDER / 'pipeline/full_f1_complete_external_audit.json')['audit']
    native = audit['fixed_native_file_hashes'] | audit['post_controller_commit_native_tail_hashes']
    tree = {}
    for row in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0'):
        if row:
            meta,name = row.split(b'\t',1)
            tree[name.decode('utf8')] = meta.split()[2].decode()
    prior = {p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound = set(sources) | prior | {'experiments/rebuild_status_current.json'}
    want = c['expected_parent']
    require((len(sources),len(native),len(prior),len(bound)) ==
            (want['sources'],want['native'],want['prior_preparation'],want['HEAD_byte_bindings']), 'extent changed')
    for p in bound:
        raw = (ROOT/p).read_bytes()
        require(sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==tree[p],p)
    for p,d in (sources|native).items():
        require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names = bound | set(native) | {p.relative_to(ROOT).as_posix() for p in
                                (HERE/'candidate.py',HERE/'contract.json',HERE/'execute.py')}
    require(len(names)==want['runtime_inputs'],'runtime extent changed')
    return {'parent_HEAD':head,'parent_HEAD_bindings':len(bound),
            'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}


def stored(folder, expected):
    f = PREP/folder/'evidence'
    receipt = ready.read_json(f/'exit.json')
    raw = (f/'stdout.log').read_bytes()
    require(receipt['native_child_exit_code']==0 and sha256(raw).hexdigest()==expected==
            receipt['files']['stdout.log']['sha256'],'historical native bytes changed')
    require((f/'stderr.log').read_bytes()==b'','historical stderr changed')
    rows = []
    for line in raw.splitlines():
        tag,value = line.split(b'=',1)
        o = json.loads(value)
        require(canonical(o).rstrip(b'\n')==value,'noncanonical historical content')
        rows.append((tag.decode(),o))
    return rows


def derive_pair(w, owner, basis, domain):
    post = list(w)
    post[owner] = owner
    bpre = [basis[s.kappa,s.phase,w[s.base_option]] for s in domain]
    bpost = [basis[s.kappa,s.phase,post[s.base_option]] for s in domain]
    trigger = [i for i,s in enumerate(domain) if s.base_option==owner and w[owner]!=owner
               and bpre[i]['outcome']!='SUCCESS']
    require(trigger,'pair without manifestation')
    outside = [i for i,s in enumerate(domain) if s.base_option!=owner]
    region = [i for i in outside if bpre[i]['outcome']=='SUCCESS']
    signs = Counter()
    old_success_cost = 0
    hpre,hpost = sha256(),sha256()
    for s,a,b in zip(domain,bpre,bpost):
        difference = float.fromhex(b['return_hex'])-float.fromhex(a['return_hex'])
        signs['positive' if difference>0 else 'negative' if difference<0 else 'zero'] += 1
        old_success_cost += a['outcome']=='SUCCESS' and difference<0
        for h,payload in ((hpre,a),(hpost,b)):
            h.update(canonical({'scene':list(s.key),'basis_payload_sha256':sha256(canonical(payload)).hexdigest()}))
    outside_equal = all(bpre[i]==bpost[i] for i in outside)
    require(outside_equal,'Process read-once locality contradicted')
    premean = mean([float.fromhex(bpre[i]['return_hex']) for i in region])
    postmean = mean([float.fromhex(bpost[i]['return_hex']) for i in region])
    return {'world':list(w),'owner':owner,'post_world':post,'first_trigger_scene':list(domain[trigger[0]].key),
            'complete_credit':['ProcessCommit'],'trigger_scene_count':len(trigger),
            'all_trigger_post_outcomes':dict(Counter(bpost[i]['outcome'] for i in trigger)),
            'outside_owner_scene_count':len(outside),'outside_owner_full_behavior_equal':outside_equal,
            'original_E_owner_size':len(region),'E_owner_pre_mean_hex':premean.hex(),
            'E_owner_post_mean_hex':postmean.hex(),'E_owner_signed_difference_hex':(premean-postmean).hex(),
            'all_scene_return_change_signs':dict(signs),'previously_successful_scene_return_decreases':old_success_cost,
            'canonical_full5760_pre_map_reference_sha256':hpre.hexdigest(),
            'canonical_full5760_post_map_reference_sha256':hpost.hexdigest(),
            'post_healthy':post==list(range(4)),'native_full5760_post_census':False,'statistical_N':None}


def audit_as_raw(audit):
    names = ['pre_state','z','m','a_cmd','u','a_realized','reward_hex','post_state',
             'post_control','terminal','outcome','illegal']
    rows = [[r[n] for n in names] for r in audit['raw_trace']]
    return {'scene':audit['scene'],'outcome':audit['factual_outcome'],
            'return_hex':float(sum(float.fromhex(r[6]) for r in rows)).hex(),
            'z_in_force':audit['z_in_force'],'trace':rows}


def require_basis(r, basis):
    require({n:r[n] for n in ('outcome','return_hex','z_in_force','trace')}==
            basis[r['scene'][0],r['scene'][1],r['z_in_force']], 'native trace differs from stored basis')


def main():
    before = bindings()
    emit('INPUT_BINDING_BEFORE',before)
    c = ready.read_json(HERE/'contract.json')
    emit('SOURCE_REDUCTION',source_proof())
    old = stored(c['stored_basis']['folder'],c['stored_basis']['stdout_sha256'])
    worlds = [o for t,o in old if t=='DERIVED_WORLD']
    require(sha256(b''.join(canonical(o) for o in worlds)).hexdigest()==c['stored_basis']['registry_sha256'],
            'whole finite registry changed')
    entries = [o for t,o in old if t=='NATIVE_BASIS']
    require(len(entries)==1 and len(entries[0]['entries'])==48,'incomplete historical basis')
    basis = {(e['kappa'],e['phase'],e['committed']):e['payload'] for e in entries[0]['entries']}
    old26 = stored(c['stored_exact_pair']['folder'],c['stored_exact_pair']['stdout_sha256'])
    prior_pair = [o for t,o in old26 if t=='COMPLETE_CHANNELS'][0][0]
    require(prior_pair['architecture']=='P','historical pair architecture differs')
    emit('STORED_DEPENDENCIES',{'basis_entries':entries[0]['entries'],
         'basis_stdout_sha256':c['stored_basis']['stdout_sha256'],
         'registry_sha256':c['stored_basis']['registry_sha256'],
         'exact_prior_pair_stdout_sha256':c['stored_exact_pair']['stdout_sha256'],
         'exact_prior_pair_not_reexecuted':True})
    domain = scene_domain()
    pairs = []
    for world in worlds:
        emit('WORLD_MEMBERSHIP',{'world':world['world'],'k':world['k'],
             'actual_manifesting_failure_owners':world['actual_manifesting_failure_owners'],
             'derived_outcomes':world['derived_outcomes'],'native_world_census':False,'statistical_N':None})
        for owner in world['actual_manifesting_failure_owners']:
            row = derive_pair(world['world'],owner,basis,domain)
            row['execution_origin'] = ('STORED_V26_EXACT_PAIR_NOT_RERUN' if
                row['world']==c['stored_exact_pair']['world'] and owner==c['stored_exact_pair']['owner']
                else 'NEW_NATIVE_B1_PAIR')
            emit('PAIR_PREDICTION_BEFORE_EXECUTION',row)
            pairs.append(row)
    require(len(worlds)==255 and len(pairs)==192,'finite extent changed')
    emit('ALL_PREDICTIONS_CLOSED',{'worlds':len(worlds),'pairs':len(pairs),
         'canonical_predictions_sha256':sha256(b''.join(canonical(o) for o in pairs)).hexdigest(),
         'no_new_native_pair_executed_yet':True})
    parent = ready.load_parent()
    healthy = ready.read_json(PREP/'healthy_reference_candidate.json')
    ready.validate_reference(healthy,parent)
    q_reference = reference_view_from(solve_reference())
    require(q_reference.digest()==healthy['q_reference_sha256'],'Q reference changed')
    actual_results = []
    for item in pairs:
        w,owner = item['world'],item['owner']
        scene = next(s for s in domain if list(s.key)==item['first_trigger_scene'])
        if item['execution_origin']=='STORED_V26_EXACT_PAIR_NOT_RERUN':
            require(item['first_trigger_scene']==c['stored_exact_pair']['scene'],'historical trigger differs')
            record = {'world':w,'owner':owner,'origin':item['execution_origin'],
                      'pre':prior_pair['all_store_pre'],'audit':prior_pair['original_owned_audit'],
                      'arms':prior_pair['same_tier_pair'],'new_rollouts':0,'new_B1_arms':0}
            for arm in record['arms']:
                names = ['pre_state','z','m','a_cmd','u','a_realized','reward_hex','post_state',
                         'post_control','terminal','outcome','illegal']
                arm['raw'] = {'scene':list(scene.key),'outcome':arm['immediate_outcome'],
                    'return_hex':float(arm['immediate_return']).hex(),'z_in_force':arm['z_in_force'],
                    'trace':[[r[n] for n in names] for r in arm['full_immediate_trace']]}
            require(record['pre']['process']==[[z,v] for z,v in enumerate(w) if z!=v],'stored pre differs')
        else:
            pre = LearnerPersistentState()
            pre.apply_transaction([Edit(PROCESS,z,v) for z,v in enumerate(w) if z!=v])
            pre_payload = state_payload(pre)
            audit = factual.prepare_factual_event(pre,scene=scene,regime='P',q_reference=q_reference,
                      parent=parent,reference=healthy)['evaluator_audit']
            oracle = OracleCreditAdapter().evaluate({}, {}, oracle_credit=audit['truth']['Gamma_P_star'])
            units = tuple(sorted(oracle.credited_units))
            require(list(units)==item['complete_credit'] and audit['truth']['J_L']==[True,False,False],
                    'whole actual manifestation differs; never trim')
            assisted = AssistedInput(owner)
            require(resolve_process_addresses(units,assisted)==(owner,),'rho_P differs')
            record = {'world':w,'owner':owner,'origin':item['execution_origin'],'pre':pre_payload,
                      'audit':audit,'arms':[],'new_rollouts':3,'new_B1_arms':2}
            for role,law in [('reference',NoWriteRef(Tier.L1_CORRECTIVE)),('treatment',PId)]:
                clone = pre.clone()
                transactions = []
                original = LearnerPersistentState.apply_transaction
                def watched(self, edits, **kwargs):
                    transactions.append({'on_this_clone':self is clone,'fingerprint_pre':fingerprint(self),
                         'entry_edits':len(edits),'stores':[e.store for e in edits],
                         'addresses':[str(e.address) for e in edits]})
                    return original(self,edits,**kwargs)
                with patch.object(LearnerPersistentState,'apply_transaction',watched):
                    result = run_process_law(law,clone,units,assisted)
                post = state_payload(clone)
                expected = w if role=='reference' else item['post_world']
                require(post['process']==[[z,v] for z,v in enumerate(expected) if z!=v],
                        'write outside owner or incorrect identity')
                require(len(transactions)==(role=='treatment') and all(t['on_this_clone'] and
                        t['fingerprint_pre']==pre_payload['fingerprint'] and t['stores']==[PROCESS] and
                        t['addresses']==[str(owner)] and t['entry_edits']==1 for t in transactions),
                        'not one same-pre owner-local transaction')
                trace = learned_rollout(clone,kappa=scene.kappa,tape=scene.tape,
                        base_option=scene.base_option,q_reference=q_reference)
                require(state_payload(clone)==post and state_payload(pre)==pre_payload,'evaluation mutation')
                arm = {'role':role,'law':result.ledger.receipts and ('NoWrite' if role=='reference' else 'P_id'),
                       'tier':'L1_CORRECTIVE','all_store_post':post,'transactions':transactions,
                       'ledger':json.loads(result.ledger.canonical()),'raw':raw_scene(trace,scene)}
                record['arms'].append(arm)
        require_basis(audit_as_raw(record['audit']),basis)
        require(record['audit']['truth']['Gamma_P_star']==['ProcessCommit'] and
                record['audit']['truth']['J_L']==[True,False,False],'historical whole truth differs')
        for arm in record['arms']:
            require_basis(arm['raw'],basis)
            require(arm['ledger']['fingerprint_pre']==record['pre']['fingerprint'] and
                    arm['ledger']['fingerprint_post']==arm['all_store_post']['fingerprint'] and
                    arm['ledger']['receipts']==[f'z={owner}|'+
                      ('EVALUABLE_NOOP|0' if arm['role']=='reference' else 'APPLIED|1')], 'receipt differs')
            require(not arm['ledger']['scalar_metrics_applicable'] and arm['ledger']['n_scalar']==0,
                    'categorical scalar accounting is inapplicable')
        emit('ACTUAL_PAIR',record)
        actual_results.append(record)
    after = bindings()
    require(before==after,'execution inputs changed')
    emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'FINITE_PROCESS_ORIGINAL_L1_COMPONENT_COMPLETE_NOT_SCIENCE',
         'worlds_retained':255,'trigger_worlds':148,'nontrigger_worlds_retained':107,'complete_owner_pairs':192,
         'new_native_pairs':191,'historical_native_pairs_read_not_reexecuted':1,
         'new_native_B1_arms':382,'new_native_repair_transactions':191,'new_native_factual_rollouts':191,
         'new_native_immediate_rollouts':382,'new_native_full5760_censuses':0,
         'canonical_actual_pairs_sha256':sha256(b''.join(canonical(o) for o in actual_results)).hexdigest(),
         'all_original_manifestations_retained':True,'before_after_inputs_equal':True,
         'full_B2_totality_certified':False,'scientific_PASS':False,'new_scientific_rule_adopted':False,
         'keys_allocated':0,'future_training':0,'collector_executed':False,'collection_authorized':False,
         'research_complete':False,'valid_current_scientific_STOP':False})


if __name__=='__main__':
    from rfl_rebuild.b2 import training
    with patch.object(training.ExogenousEpisode,'derive',side_effect=AssertionError('no keys')), \
         patch.object(training,'train_curve',side_effect=AssertionError('no training')):
        main()
