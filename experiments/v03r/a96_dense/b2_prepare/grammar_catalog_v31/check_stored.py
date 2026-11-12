"""Stdlib-only reconstruction of full stored catalogs; no RFL/solver execution."""
from collections import Counter, defaultdict
from fractions import Fraction
from hashlib import sha1, sha256
from itertools import product
from math import comb, isfinite
from pathlib import Path
import ast
import json
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
PREP=HERE.parent


def canonical(o):
    return (json.dumps(o,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def require(ok,why):
    if not ok:raise AssertionError(why)


def read(p):return json.loads(p.read_bytes())


def records(folder,expected):
    claim,receipt=read(folder/'claim.json'),read(folder/'exit.json')
    require(receipt['native_child_exit_code']==0 and all(receipt[k]==v for k,v in claim.items()),'receipt differs')
    for n,item in receipt['files'].items():
        b=(folder/n).read_bytes();require(len(b)==item['bytes'] and sha256(b).hexdigest()==item['sha256'],n)
    require(receipt['files']['stdout.log']['sha256']==expected and (folder/'stderr.log').read_bytes()==b'','raw binding differs')
    out=[]
    for line in (folder/'stdout.log').read_bytes().splitlines(keepends=True):
        require(line.endswith(b'\n'),'truncated stdout')
        line=line.rstrip(b'\r\n')
        if b'=' not in line:continue
        t,v=line.split(b'=',1)
        if v[:1] in (b'{',b'['):out.append((t.decode(),json.loads(v)))
    return out,receipt


def polynomial(weights,degree=8):
    """Independent grouped-binomial expansion, not candidate's per-row recurrence."""
    result=[1]+[0]*degree
    for w,n in sorted(Counter(weights).items()):
        block=[comb(n,j)*w**j for j in range(min(degree,n)+1)]
        result=[sum(result[k-j]*block[j] for j in range(min(k,len(block)-1)+1)) for k in range(degree+1)]
    return result


def frac(n,d):
    f=Fraction(n,d);return [f.numerator,f.denominator]


def cell_check(rows,actual,shapes):
    groups=defaultdict(list)
    for r in rows:groups[tuple(r['group'])].append(r)
    weights=[len(r['alternatives']) for r in rows]
    missed=[r for r in rows if not r['nominal_basis_consulted']]
    allpoly=polynomial(weights);misspoly=polynomial([len(r['alternatives']) for r in missed])
    for item in actual:
        k=item['k'];shape=item['shape']
        cluster=sum(comb(len(v),k) for v in groups.values())
        clusterworld=sum(polynomial([len(r['alternatives']) for r in v])[k] for v in groups.values())
        mc=sum(comb(sum(not r['nominal_basis_consulted'] for r in v),k) for v in groups.values())
        mw=sum(polynomial([len(r['alternatives']) for r in v if not r['nominal_basis_consulted']])[k] for v in groups.values())
        subset,world,non,nonworld=comb(len(rows),k),allpoly[k],comb(len(missed),k),misspoly[k]
        if shape=='clustered':subset,world,non,nonworld=cluster,clusterworld,mc,mw
        if shape=='distributed':subset,world,non,nonworld=subset-cluster,world-clusterworld,non-mc,nonworld-mw
        require(item=={'k':k,'shape':shape,'context_subsets':subset,'target_assigned_syntax_worlds':world,
                'nominal_unconsulted_context_subsets':non,'nominal_unconsulted_target_worlds':nonworld,
                'nontrigger_mass_lower_bound_under_proposed_context_sampling':frac(non,subset),
                'not_exact_trigger_conditioning_mass':True,'uniform_context_subset_M_fits256bit':subset<=2**256,
                'uniform_target_world_rank_is_not_proposed_sampling':True,'statistical_N':None},'cell count/measure differs')
    expected=[(1,'singleton')]+[(k,s) for k in (2,4,8) for s in ('clustered','distributed')] if shapes else [(k,'no-shape') for k in (1,2,4,8)]
    require([(r['k'],r['shape']) for r in actual]==expected,'cell deleted/reordered')


def main():
    c=read(HERE/'contract.json');native=read(HERE/'evidence/exit.json')
    rows,receipt=records(HERE/'evidence',native['files']['stdout.log']['sha256'])
    for n,d in receipt['inputs'].items():require(sha256((HERE/n).read_bytes()).hexdigest()==d,n)
    require(all(canonical(o).rstrip(b'\n')==v for t,o,v in
                ((line.split(b'=',1)[0],json.loads(line.split(b'=',1)[1]),line.split(b'=',1)[1])
                 for line in (HERE/'evidence/stdout.log').read_bytes().splitlines())),'noncanonical new output')
    scalar={t:o for t,o in rows if t not in ('DECISION_CONTEXT','CONTROLLER_SITE')}
    before,after=scalar['INPUT_BINDING_BEFORE'],scalar['INPUT_BINDING_AFTER']
    require(before==after and len(before['input_sha256'])==803,'runtime binding differs')
    for p,d in before['input_sha256'].items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    require(head==before['parent_HEAD']==c['parent_commit'],'parent changed')
    tree={}
    for b in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0'):
        if b:
            m,p=b.split(b'\t',1);tree[p.decode()]=m.split()[2].decode()
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    oldnative=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith('experiments/v03r/a96_dense/b2_prepare/')}
    bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(oldnative),len(prior),len(bound))==(313,153,333,647),'parent extent differs')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|oldnative).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    dc=[o for t,o in rows if t=='DECISION_CONTEXT'];xc=[o for t,o in rows if t=='CONTROLLER_SITE'];s=scalar['CATALOG_SUMMARY']
    # Independent whole state/context product from the frozen map constants, not the candidate enumerator.
    open_cells={(x,y) for x in range(1,4) for y in range(1,5)}-{(2,3)}|{(0,2),(4,2)}
    states=[(x,y,t,k,phi) for x,y in sorted(open_cells-{(4,2)}) for t,k,phi in product(range(12),range(2),range(6))]
    expected=sorted((state+(z,m) for state in states for z,m in product(range(4),range(2))),key=lambda q:(q[2],q[3],q[4],q[0],q[1],q[5],q[6]))
    require([tuple(r['context']) for r in dc]==expected,'whole context support differs')
    basisrows,_=records(PREP/c['stored_basis']['folder'],c['stored_basis']['stdout_sha256'])
    basis=[o for t,o in basisrows if t=='NATIVE_BASIS'][0]['entries']
    require({(e['kappa'],e['phase'],e['committed']) for e in basis}==set(product(range(2),range(6),range(4))),'basis incomplete')
    seen=set();xseen=set();raw_basis_rows=0
    qtable={tuple(r['context']):r for r in dc}
    for e in basis:
        for row in e['payload']['trace']:
            key=tuple(row[0]+[row[1],row[2]]);seen.add(key);xseen.add(tuple(row[0]+[row[3]]));raw_basis_rows+=1
            vals={a:float.fromhex(v) for a,v in qtable[key]['q_row_hex']}
            require(row[3]==max(vals,key=lambda a:(vals[a],-a)) and row[4]==row[3],'basis not nominal command/identity')
    parts=[];eligible=[]
    for r in dc:
        key=r['context'];vals={a:float.fromhex(v) for a,v in r['q_row_hex']};best=max(vals.values())
        require(all(isfinite(v) for v in vals.values()) and sorted(vals)==[a for a,v in r['q_row_hex']],'malformed reference row')
        optimal=[a for a in sorted(vals) if vals[a]>=best-1e-12];bad=[a for a in sorted(vals) if a not in optimal]
        require(r['optimal_actions']==optimal and r['alternatives']==bad and r['group']==key[3:5]+key[5:7] and
                r['nominal_basis_consulted']==(tuple(key) in seen),'decision catalog semantics differ')
        parts.append(','.join(map(str,key))+'|'+','.join(f'{a}={float(v).hex()}' for a,v in sorted(vals.items())))
        if bad:eligible.append(r)
    ref=sha256('\n'.join(parts).encode()).hexdigest()
    require(ref==s['nominal_Q_reference_sha256']==read(PREP/'healthy_reference_candidate.json')['q_reference_sha256'],'full reference bytes differ')
    expected_x=[]
    for state in sorted(states,key=lambda q:(q[2],q[0],q[1],q[3],q[4])):
        allowed=[{a for a,v in qtable[state+(z,m)]['q_row_hex']} for z,m in product(range(4),range(2))]
        common=set.intersection(*allowed)
        for cmd in sorted(set.union(*allowed)):
            site=list(state)+[cmd]
            expected_x.append({'site':site,'group':list(state[3:5]),'all8_common_legal':sorted(common),
                     'alternatives':sorted(common-{cmd}),'nominal_basis_consulted':tuple(site) in xseen})
    require(xc==expected_x,'whole controller support differs')
    xeligible=[r for r in xc if r['alternatives']]
    cell_check(eligible,s['decision_cells'],True);cell_check(xeligible,s['controller_cells'],False)
    require(s['complete_decision_catalog_canonical_sha256']==sha256(b''.join(canonical(o) for o in dc)).hexdigest() and
            s['complete_controller_catalog_canonical_sha256']==sha256(b''.join(canonical(o) for o in xc)).hexdigest(),'catalog hash differs')
    require(s['decision_legal_contexts']==len(dc) and s['decision_eligible_contexts']==len(eligible) and
            s['decision_noneligible_contexts_retained']==len(dc)-len(eligible) and
            s['controller_union_legal_sites']==len(xc) and s['controller_candidate_sites']==len(xeligible) and
            s['controller_no_common_alternative_sites_retained']==len(xc)-len(xeligible),'retained extent differs')
    for label,data in [('decision_bad_action_count_histogram',eligible),('controller_target_count_histogram',xeligible)]:
        require(s[label]=={str(k):v for k,v in Counter(len(r['alternatives']) for r in data).items()},'histogram differs')
    groupcount=Counter(tuple(r['group']) for r in eligible)
    require(s['decision_groups']==[[list(g),n] for g,n in sorted(groupcount.items())],'group extent differs')
    require(s['decision_nominal_unconsulted_eligible_contexts']==sum(not r['nominal_basis_consulted'] for r in eligible),'unconsulted extent differs')
    anchor=scalar['ANCHOR_STRUCTURAL_BOUND'];ar=qtable[tuple(c['stored_anchor']['owner'])]
    require(anchor['anchor']==ar and c['stored_anchor']['action'] in ar['alternatives'],'anchor outside grammar')
    old,_=records(PREP/c['stored_anchor']['folder'],c['stored_anchor']['stdout_sha256'])
    old_arch=[o for t,o in old if t=='COMPLETE_ARCHITECTURES'][0]
    require(anchor['v25_full_native_factual_audits']==[o['original_owned_audit'] for o in old_arch] and
            anchor['v25_nominal_fixture']==[o for t,o in old if t=='FIXTURE'][0],'anchor evidence changed')
    vals={a:float.fromhex(v) for a,v in ar['q_row_hex']};b=max(vals.values());promoted=b+(b-vals[3])
    require(promoted>b and promoted.hex()==anchor['v27_promoted_value_hex'],'new amplitude policy not proved')
    sentinels=[r for r in eligible if not r['nominal_basis_consulted'] and r['group']!=ar['group']]
    prefixes=[]
    for oldarm in old_arch:
        audit=oldarm['original_owned_audit'];raw=audit['raw_trace']
        require(audit['scene']==c['stored_anchor']['scene'] and audit['factual_outcome']=='COLLISION' and
                audit['truth']['Gamma_P_star']==['Decision_1'] and audit['truth']['J_L']==[False,True,False] and
                len(raw)==2 and raw[-1]['a_cmd']==3 and raw[-1]['terminal'],'not complete anchor collision truth')
        require(raw[-1]['pre_state']+[raw[-1]['z'],raw[-1]['m']]==ar['context'],'anchor owner differs')
        prefixes.append({tuple(r['pre_state']+[r['z'],r['m']]) for r in raw})
    require(all(tuple(r['context']) not in prefixes[0]|prefixes[1] for r in sentinels),'sentinel hits fixed prefix')
    positive=polynomial([len(r['alternatives']) for r in sentinels])
    expected_bound=[{'k':k,'shape':'distributed','fixed_anchor_action':3,
        'distinct_pre_states_with_source_proved_positive_trigger_lower_bound':positive[k-1],
        'literal_full_U2_census_scene_evaluations_lower_bound':5760*positive[k-1],
        'source_derived_not_new_native_worlds':True} for k in (2,4,8)]
    require(s['positive_trigger_instance_bounds']==anchor['bounds']==expected_bound and
            anchor['unconsulted_outside_group_sentinels']==len(sentinels),'positive bound differs')
    illustration=scalar['SAMPLING_MEASURE_DISTINCTION'];selected=[qtable[tuple(q)] for q in illustration['contexts']]
    ns=[len(r['alternatives']) for r in selected];n=sum(ns)
    require(ns[0]!=ns[1] and illustration['target_counts']==ns and
            illustration['proposed_uniform_context_probabilities']==[[1,2],[1,2]] and
            illustration['uniform_complete_world_context_probabilities']==[frac(v,n) for v in ns] and
            illustration['proposed_per_assigned_target_probability']==[frac(1,2*v) for v in ns] and
            illustration['uniform_complete_world_per_target_probability']==frac(1,n),'sampling distinction differs')
    for p,d in s['source_sha256'].items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    source=ast.parse((ROOT/'src/rfl_rebuild/env/kernel.py').read_text(encoding='utf8'))
    step=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='step')
    require(not any(isinstance(n,ast.Name) and n.id=='tape' for n in ast.walk(step)),'nominal tape factorization invalid')
    # Hash-bound original learner providers ensure one-context Q/patch reads. This checker does not simulate them.
    require('overrides.get(QAddress' in (ROOT/'src/rfl_rebuild/learner/store.py').read_text(encoding='utf8'),'Q lookup source boundary changed')
    for k in ('scientific_PASS','scientific_rules_adopted','collector_executed','collection_authorized','research_complete',
              'valid_current_scientific_STOP','exact_trigger_mass_computed','full_joint_totality_certified','full_world_enumeration'):
        require(s[k] is False,'unsupported scientific conclusion')
    require(s['native_new_rollouts']==s['native_new_B1_arms']==s['keys_allocated']==s['future_training']==0 and s['delta_joint'] is None,'unexpected acquisition')
    require(scalar['FINAL']['summary_sha256']==sha256(canonical(s)).hexdigest(),'final summary binding differs')
    report={'role':'PRIMARY_STDLIB_STORED_CATALOG_CHECK_NOT_EXPERT_OR_SCIENTIFIC_PASS','status':'FULL_BASE_CATALOG_AND_COUNTS_CHECKED',
       'parent_HEAD':head,'runtime_inputs_checked':803,'parent_HEAD_byte_bindings_checked':647,'original_sources':313,
       'old_native':153,'prior_preparation':333,'full_stored_decision_rows':len(dc),'full_stored_controller_rows':len(xc),
       'stored_nominal_native_basis_rows_read':raw_basis_rows,'eligible_decision':len(eligible),'candidate_controller':len(xeligible),
       'full_nominal_reference_sha256':ref,'all11_structural_cells_checked':True,'all_counts_exact_integer':True,
       'positive_trigger_bounds':expected_bound,'sampling_measure_distinction_checked':True,
       'new_RFL_or_solver_execution':False,'independent_expert_review':False,'scientific_PASS':False,'collection_authorized':False}
    print(json.dumps(report,ensure_ascii=True,sort_keys=True))


if __name__=='__main__':main()
