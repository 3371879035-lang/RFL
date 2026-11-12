"""Exact proposed-syntax catalog; not a stochastic generator or collector."""
from collections import Counter, defaultdict
from fractions import Fraction
from hashlib import sha1, sha256
from math import comb
import ast
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PREP = HERE.parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(PREP))
import readiness as ready
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.domain import decision_contexts, decision_states
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.solve.dp import solve_reference


def canonical(o):
    return (json.dumps(o, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def emit(tag, o):
    print(tag+'='+canonical(o).decode().rstrip('\n'), flush=True)


def require(ok, why):
    if not ok:
        raise AssertionError(why)


def bind():
    contract = ready.read_json(HERE/'contract.json')
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(head==contract['parent_commit'], 'parent changed')
    tree = {}
    for row in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0'):
        if row:
            meta,p = row.split(b'\t',1);tree[p.decode()]=meta.split()[2].decode()
    sources = ready.read_json(ROOT/ready.FOLDER/'pipeline/frozen_inputs.json')['sources']
    audit = ready.read_json(ROOT/ready.FOLDER/'pipeline/full_f1_complete_external_audit.json')['audit']
    native = audit['fixed_native_file_hashes']|audit['post_controller_commit_native_tail_hashes']
    prior = {p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound = set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound))==(313,153,333,647),'parent extent differs')
    for p in bound:
        b=(ROOT/p).read_bytes()
        require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native).items():
        require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('candidate.py','contract.json','execute.py')}
    require(len(names)==contract['expected_parent']['runtime_inputs'],'runtime extent differs')
    return {'parent_HEAD':head,'HEAD_byte_bindings':len(bound),
            'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}


def stored(info):
    folder=PREP/info['folder'];claim=ready.read_json(folder/'claim.json');receipt=ready.read_json(folder/'exit.json')
    require(receipt['native_child_exit_code']==0 and all(receipt[k]==v for k,v in claim.items()),'old native receipt differs')
    for name,item in receipt['files'].items():
        b=(folder/name).read_bytes()
        require(len(b)==item['bytes'] and sha256(b).hexdigest()==item['sha256'],'stored raw differs')
    require(receipt['files']['stdout.log']['sha256']==info['stdout_sha256'],'stored stdout differs')
    require((folder/'stderr.log').read_bytes()==b'','stored stderr differs')
    # Historical output formats differ; non-JSON scalar lines are retained in the bytes binding.
    rows=[]
    for line in (folder/'stdout.log').read_bytes().splitlines():
        if not line or b'=' not in line:continue
        tag,value=line.split(b'=',1)
        if value[:1] in (b'{',b'['):rows.append((tag.decode(),json.loads(value)))
    return rows


def symmetric(weights, limit=8):
    out=[1]+[0]*limit
    for n,w in enumerate(weights):
        for k in range(min(limit,n+1),0,-1):out[k]+=w*out[k-1]
    return out


def fraction(a,b):
    f=Fraction(a,b);return [f.numerator,f.denominator]


def counts(rows, ks, shapes=True):
    groups=defaultdict(list);unseen=defaultdict(list)
    for r in rows:
        groups[tuple(r['group'])].append(len(r['alternatives']))
        if not r['nominal_basis_consulted']:unseen[tuple(r['group'])].append(len(r['alternatives']))
    allweights=[len(r['alternatives']) for r in rows];miss=[len(r['alternatives']) for r in rows if not r['nominal_basis_consulted']]
    ap,mp=symmetric(allweights),symmetric(miss)
    gp={g:symmetric(w) for g,w in groups.items()};up={g:symmetric(w) for g,w in unseen.items()}
    out=[]
    for k in ks:
        total=comb(len(rows),k);unread=comb(len(miss),k)
        cluster=sum(comb(len(w),k) for w in groups.values())
        uncluster=sum(comb(len(w),k) for w in unseen.values())
        targetcluster=sum(p[k] for p in gp.values());targetuncluster=sum(p[k] for p in up.values())
        for shape in (['singleton'] if k==1 else ['clustered','distributed']) if shapes else ['no-shape']:
            if shape=='clustered':subset,world,non,nonworld=cluster,targetcluster,uncluster,targetuncluster
            elif shape=='distributed':subset,world,non,nonworld=total-cluster,ap[k]-targetcluster,unread-uncluster,mp[k]-targetuncluster
            else:subset,world,non,nonworld=total,ap[k],unread,mp[k]
            require(subset>0 and world>0,'empty structural cell, never replace it')
            out.append({'k':k,'shape':shape,'context_subsets':subset,'target_assigned_syntax_worlds':world,
                'nominal_unconsulted_context_subsets':non,'nominal_unconsulted_target_worlds':nonworld,
                'nontrigger_mass_lower_bound_under_proposed_context_sampling':fraction(non,subset),
                'not_exact_trigger_conditioning_mass':True,'uniform_context_subset_M_fits256bit':subset<=2**256,
                'uniform_target_world_rank_is_not_proposed_sampling':True,'statistical_N':None})
    return out


def main():
    before=bind();emit('INPUT_BINDING_BEFORE',before)
    c=ready.read_json(HERE/'contract.json')
    sources=['env/kernel.py','env/domain.py','solve/dp.py','learner/reference.py','learner/store.py',
             'b2/environment.py','b2/calibration.py']
    sourcehash={f'src/rfl_rebuild/{p}':sha256((ROOT/'src/rfl_rebuild'/p).read_bytes()).hexdigest() for p in sources}
    kernel=ast.parse((ROOT/'src/rfl_rebuild/env/kernel.py').read_text(encoding='utf8'))
    funcs={n.name:n for n in kernel.body if isinstance(n,ast.FunctionDef)}
    require(not any(isinstance(n,ast.Name) and n.id=='tape' for n in ast.walk(funcs['step'])),'tape affects nominal reduction')
    basis_records=stored(c['stored_basis']);anchor_records=stored(c['stored_anchor'])
    basis=[o for t,o in basis_records if t=='NATIVE_BASIS'][0]['entries']
    require(len(basis)==48,'basis extent differs')
    decision_seen=set();controller_seen=set()
    for entry in basis:
        for row in entry['payload']['trace']:
            s=row[0];decision_seen.add(tuple(s+[row[1],row[2]]));controller_seen.add(tuple(s+[row[3]]))
    solution=solve_reference();reference=reference_view_from(solution)
    nominal=ready.read_json(PREP/'healthy_reference_candidate.json')
    require(reference.digest()==nominal['q_reference_sha256'],'nominal ruler differs')
    legal=reference.domains
    require(set(legal)==decision_contexts(),'reference context extent differs')
    allrows=[];eligible=[]
    for s,z,m in legal:
        key=[s.x,s.y,s.t,s.kappa,s.phi,z,m]
        values=solution.action_values(s,z,m)
        allowed=tuple(sorted(K.option_actions(z,K.ControlState(z=z,m=m),s)))
        require(tuple(sorted(values))==allowed,'reference action support differs')
        optimal=solution.optimal_actions(s,z,m);bad=[a for a in allowed if a not in optimal]
        row={'context':key,'group':[s.kappa,s.phi,z,m],
             'q_row_hex':[[a,float(values[a]).hex()] for a in allowed],
             'optimal_actions':list(optimal),'alternatives':bad,'nominal_basis_consulted':tuple(key) in decision_seen}
        emit('DECISION_CONTEXT',row);allrows.append(row)
        if bad:eligible.append(row)
    xall=[];xeligible=[]
    for s in sorted(decision_states(),key=lambda s:(s.t,s.x,s.y,s.kappa,s.phi)):
        sets=[set(K.option_actions(z,K.ControlState(z=z,m=m),s)) for z in K.option_ids() for m in (0,1)]
        common=set.intersection(*sets);union=set.union(*sets)
        for cmd in sorted(union):
            key=[s.x,s.y,s.t,s.kappa,s.phi,cmd]
            row={'site':key,'group':[s.kappa,s.phi],'all8_common_legal':sorted(common),
                 'alternatives':sorted(common-{cmd}),'nominal_basis_consulted':tuple(key) in controller_seen}
            emit('CONTROLLER_SITE',row);xall.append(row)
            if row['alternatives']:xeligible.append(row)
    dcounts=counts(eligible,(1,2,4,8));xcounts=counts(xeligible,(1,2,4,8),False)
    anchor=next(r for r in eligible if r['context']==c['stored_anchor']['owner'])
    require(c['stored_anchor']['action'] in anchor['alternatives'] and anchor['nominal_basis_consulted'],'anchor outside syntax')
    fixture=[o for t,o in anchor_records if t=='FIXTURE'][0]
    require(fixture['scene']==c['stored_anchor']['scene'],'anchor scene differs')
    oldarms=[o for t,o in anchor_records if t=='COMPLETE_ARCHITECTURES'][0]
    require([o['architecture'] for o in oldarms]==['D_Q','D_patch'],'historical architectures differ')
    oldaudit=oldarms[0]['original_owned_audit']
    require(oldaudit==oldarms[1]['original_owned_audit'] or
            oldaudit['raw_trace']==oldarms[1]['original_owned_audit']['raw_trace'],'historical raw mismatch')
    require(oldaudit['factual_outcome']=='COLLISION' and oldaudit['truth']['Gamma_P_star']==['Decision_1'] and
            len(oldaudit['raw_trace'])==2 and oldaudit['raw_trace'][-1]['a_cmd']==c['stored_anchor']['action'] and
            oldaudit['raw_trace'][-1]['pre_state']+[oldaudit['raw_trace'][-1]['z'],oldaudit['raw_trace'][-1]['m']]==anchor['context'],
            'old anchor does not prove the stated extensional collision')
    # No reexecution of v25. Compare the declared action's prospective Q promotion at this one row.
    vals={a:float.fromhex(v) for a,v in anchor['q_row_hex']};b=max(vals.values());q=vals[c['stored_anchor']['action']]
    promoted=b+(b-q)
    require(promoted>b,'v27 installation does not force bad action')
    sentinels=[r for r in eligible if not r['nominal_basis_consulted'] and r['group']!=anchor['group']]
    positive=symmetric([len(r['alternatives']) for r in sentinels])
    lower=[{'k':k,'shape':'distributed','fixed_anchor_action':c['stored_anchor']['action'],
            'distinct_pre_states_with_source_proved_positive_trigger_lower_bound':positive[k-1],
            'literal_full_U2_census_scene_evaluations_lower_bound':positive[k-1]*5760,
            'source_derived_not_new_native_worlds':True} for k in (2,4,8)]
    # Exhibit both distributions on two real eligible contexts with different action multiplicity.
    pair=next((a,b) for a in eligible for b in eligible if len(a['alternatives'])!=len(b['alternatives']))
    naive=sum(len(r['alternatives']) for r in pair)
    sampling={'contexts':[r['context'] for r in pair],'target_counts':[len(r['alternatives']) for r in pair],
        'proposed_uniform_context_probabilities':[[1,2],[1,2]],
        'uniform_complete_world_context_probabilities':[fraction(len(r['alternatives']),naive) for r in pair],
        'proposed_per_assigned_target_probability':[fraction(1,2*len(r['alternatives'])) for r in pair],
        'uniform_complete_world_per_target_probability':fraction(1,naive),
        'scope':'Exact two-member mathematical illustration using actual legal contexts, no random draw, no scientific population replacement.'}
    emit('SAMPLING_MEASURE_DISTINCTION',sampling)
    emit('ANCHOR_STRUCTURAL_BOUND',{'anchor':anchor,'v27_promoted_value_hex':promoted.hex(),
         'v25_nominal_fixture':fixture,'v25_full_native_factual_audits':[o['original_owned_audit'] for o in oldarms],
         'unconsulted_outside_group_sentinels':len(sentinels),'bounds':lower,
         'argument':'No nominal path can read an unconsulted sentinel before its first change; the anchor first changes the fixed two-step healthy prefix to immediate collision. All sentinels are outside its group, all their choices legal, and none are on that prefix. Different sentinel configs yield distinct full pre states with the same complete Decision_1 manifestation for this scene. Not a new native census or mechanism efficacy test.'})
    grouping=Counter(tuple(r['group']) for r in eligible)
    summary={'status':'EXACT_PROPOSED_BASE_GRAMMAR_CATALOG_NOT_SCIENCE',
      'nominal_Q_reference_sha256':reference.digest(),'source_sha256':sourcehash,
      'decision_legal_contexts':len(allrows),'decision_eligible_contexts':len(eligible),
      'decision_noneligible_contexts_retained':len(allrows)-len(eligible),
      'decision_bad_action_count_histogram':dict(Counter(len(r['alternatives']) for r in eligible)),
      'decision_nominal_unconsulted_eligible_contexts':sum(not r['nominal_basis_consulted'] for r in eligible),
      'decision_groups':[[list(g),n] for g,n in sorted(grouping.items())],
      'controller_union_legal_sites':len(xall),'controller_candidate_sites':len(xeligible),
      'controller_no_common_alternative_sites_retained':len(xall)-len(xeligible),
      'controller_target_count_histogram':dict(Counter(len(r['alternatives']) for r in xeligible)),
      'decision_cells':dcounts,'controller_cells':xcounts,'positive_trigger_instance_bounds':lower,
      'complete_decision_catalog_canonical_sha256':sha256(b''.join(canonical(o) for o in allrows)).hexdigest(),
      'complete_controller_catalog_canonical_sha256':sha256(b''.join(canonical(o) for o in xall)).hexdigest(),
      'stored_native_basis_entries_read':48,'stored_native_anchor_read_not_rerun':True,
      'native_new_rollouts':0,'native_new_B1_arms':0,'full_world_enumeration':False,
      'exact_trigger_mass_computed':False,'full_joint_totality_certified':False,'delta_joint':None,
      'sampling_ambiguity_resolved_as_unadopted_technical_candidate':True,
      'statistical_N':None,'scientific_PASS':False,'scientific_rules_adopted':False,
      'keys_allocated':0,'future_training':0,'collector_executed':False,'collection_authorized':False,
      'research_complete':False,'valid_current_scientific_STOP':False}
    emit('CATALOG_SUMMARY',summary)
    after=bind();require(before==after,'runtime inputs drifted');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':summary['status'],'all_inputs_equal':True,'summary_sha256':sha256(canonical(summary)).hexdigest(),
         'collection_authorized':False,'research_complete':False})


if __name__=='__main__':
    from rfl_rebuild.b2 import training
    with patch.object(K,'rollout',side_effect=AssertionError('no new rollout')), \
         patch.object(K,'continue_rollout',side_effect=AssertionError('no new continuation')), \
         patch.object(training.ExogenousEpisode,'derive',side_effect=AssertionError('no keys')), \
         patch.object(training,'train_curve',side_effect=AssertionError('no future training')):
        main()
