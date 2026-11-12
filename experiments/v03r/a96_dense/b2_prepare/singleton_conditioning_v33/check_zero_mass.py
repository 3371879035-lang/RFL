"""Full stdlib audit of authentic zero-mass failure and all new X native confirmations."""
from collections import Counter
from fractions import Fraction
from hashlib import sha1,sha256
import json,subprocess
# Only original stdlib checker helper definitions; not its main or RFL/candidate/predictor.
from check_stored import HERE,PREP,ROOT,read,require,canonical,frac,records,payload_from_basis,verify_trace


def main():
    c=read(HERE/'zero_mass_contract.json');original=read(HERE/'contract.json')
    cl,ex=read(HERE/'evidence/claim.json'),read(HERE/'evidence/exit.json')
    require(ex['native_child_exit_code']==1 and all(ex[k]==v for k,v in cl.items()),'initial native failure receipt')
    for n,v in ex['files'].items():
        b=(HERE/'evidence'/n).read_bytes();require(len(b)==v['bytes'] and sha256(b).hexdigest()==v['sha256'],'failure raw bytes')
    for n,d in cl['inputs'].items():require(sha256((HERE/n).read_bytes()).hexdigest()==d,'initial source changed')
    require(ex['files']['stdout.log']['sha256']==c['initial_attempt']['stdout_sha256'] and ex['files']['stderr.log']['sha256']==c['initial_attempt']['stderr_sha256'],'failure contract differs')
    err=(HERE/'evidence/stderr.log').read_text(encoding='utf8');require(err.rstrip().endswith('AssertionError: singleton candidate has zero triggerable mass; retain and report'),'wrong failure')
    initial=[]
    for line in (HERE/'evidence/stdout.log').read_bytes().splitlines(keepends=True):
        require(line.endswith(b'\n'),'truncated initial line');t,v=line.rstrip(b'\r\n').split(b'=',1);o=json.loads(v)
        require(canonical(o).rstrip(b'\n')==v,'initial noncanonical');initial.append((t.decode(),o))
    require(Counter(t for t,o in initial)=={'INPUT_BINDING_BEFORE':1,'NOMINAL_BASIS_BOUND':1,'CONFIGURATION_PREDICTION':19964},'initial unexpectedly executed native factual')
    rows,receipt=records(HERE/'evidence_zero_mass',strict=True)
    for n,d in receipt['inputs'].items():require(sha256((HERE/n).read_bytes()).hexdigest()==d,'confirmation inputs')
    scalar={t:o for t,o in rows if t in ('INPUT_BINDING_BEFORE','INPUT_BINDING_AFTER','COMPLETE_ZERO_MASS_AUDIT_BEFORE_NATIVE','FINAL')}
    before=scalar['INPUT_BINDING_BEFORE'];require(before==scalar['INPUT_BINDING_AFTER'],'confirmation inputs changed')
    initial_before=next(o for t,o in initial if t=='INPUT_BINDING_BEFORE')
    require(len(initial_before['input_sha256'])==837 and all(before['input_sha256'][p]==d for p,d in initial_before['input_sha256'].items()),'failure and confirmation parent/source differs')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit']==before['parent_HEAD']==initial_before['parent_HEAD'],'parent changed')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources'];audit=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=audit['fixed_native_file_hashes']|audit['post_controller_commit_native_tail_hashes'];prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')};bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound),len(before['input_sha256']))==(313,153,365,679,845),'runtime extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native|before['input_sha256']).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    cat,_=records(PREP/original['stored_catalog']['folder'],original['stored_catalog']['stdout_sha256']);D=[o for t,o in cat if t=='DECISION_CONTEXT'];X=[o for t,o in cat if t=='CONTROLLER_SITE']
    q={tuple(r['context']):{a:float.fromhex(v) for a,v in r['q_row_hex']} for r in D}
    br,_=records(PREP/original['stored_basis']['folder'],original['stored_basis']['stdout_sha256']);basis=next(o['entries'] for t,o in br if t=='NATIVE_BASIS');keys=[(b['kappa'],b['phase'],b['committed']) for b in basis]
    require(len(keys)==len(set(keys))==48,'nominal basis extent');nominal=[payload_from_basis(b['payload']) for b in basis]
    for k,p in zip(keys,nominal):verify_trace(p,k,q)
    registry=[o for t,o in initial if t=='CONFIGURATION_PREDICTION'];index={r['id']:r for r in registry};require(len(index)==19964,'duplicate initial configuration')
    summaries={};expected_ids=[];expected_X=set();consulted_X=set();prediction_rows=0
    for arch,catalog,field in (('D',D,'context'),('X',X,'site')):
        eligible=[r for r in catalog if r['alternatives']];M=len(eligible);Z=Fraction();J=Fraction();mass_sum=Fraction();worlds=0
        for pos,r in enumerate(eligible):
            address=r[field];visits=[b for b,p in enumerate(nominal) if any(t['pre_state']+([t['z'],t['m']] if arch=='D' else [t['a_cmd']])==address for t in p['trace'])]
            require(bool(visits)==r['nominal_basis_consulted'],'consultation flag')
            for target in r['alternatives']:
                wid=f'{arch}:{pos}:{target}';expected_ids.append(wid);pred=index[wid];mass=Fraction(1,M*len(r['alternatives']));worlds+=1;mass_sum+=mass
                require(pred['address']==address and pred['target']==target and pred['architecture']==arch and pred['eligible_position']==pos and pred['alternatives']==len(r['alternatives']),'initial world changed')
                require(pred['original_mass']==frac(mass) and pred['consulted_basis']==visits and [b for b,p in pred['consulted_predictions']]==visits,'initial extent/measure')
                triggers=[]
                for b,p in pred['consulted_predictions']:
                    verify_trace(p,keys[b],q,arch,address,target);prediction_rows+=len(p['trace'])
                    hit=next(i for i,t in enumerate(nominal[b]['trace']) if t['pre_state']+([t['z'],t['m']] if arch=='D' else [t['a_cmd']])==address)
                    require(p['trace'][:hit]==nominal[b]['trace'][:hit],'first-hit prefix')
                    if p['outcome']!='SUCCESS' and p['Gamma_P_star']:triggers.append(b)
                    if arch=='X':expected_X.add((wid,b));consulted_X.add(wid)
                require(pred['trigger_basis']==triggers and pred['trigger_scene_mass']==frac(Fraction(len(triggers),48)),'trigger support')
                if triggers:Z+=mass
                J+=mass*Fraction(len(triggers),48)
        require(mass_sum==1,'unconditional mass not preserved')
        summaries[arch]={'eligible_positions':M,'assigned_configurations':worlds,'original_mass_sum':frac(mass_sum),
                         'triggerable_mass':frac(Z),'nontrigger_mass':frac(1-Z),'joint_defect_scene_failure_mass_NOT_defect_normalizer':frac(J),
                         'conditional_defect_distribution_defined':Z>0}
    require([r['id'] for r in registry]==expected_ids,'not complete ordered singleton support')
    require(summaries['X']['triggerable_mass']==[0,1] and summaries['X']['nontrigger_mass']==[1,1],'zero-mass counterexample absent')
    pre_audit=scalar['COMPLETE_ZERO_MASS_AUDIT_BEFORE_NATIVE'];require(summaries==pre_audit['normalizers']==scalar['FINAL']['normalizers'],'normalizers')
    require(sha256(canonical(registry)).hexdigest()==pre_audit['prediction_registry_sha256'],'prediction digest')
    anchor=next(r for r in X if r['site']==[1,2,1,0,2,0]);require(anchor==pre_audit['old_v26_site_catalog'] and not anchor['all8_common_legal'] and not anchor['alternatives'],'valid old mechanism site not excluded')
    actual=[o for t,o in rows if t=='ACTUAL_X_SINGLETON'];raw=[o for t,o in rows if t=='RAW_NATIVE_FACTUAL_BEFORE_TRUTH'];raw_index={(r['id'],r['basis_index']):r for r in raw};seen=set();nrows=0;outcomes=Counter()
    require(len(raw)==len(raw_index)==len(actual)==len(expected_X),'native coverage extent')
    require(next(i for i,(t,o) in enumerate(rows) if t=='COMPLETE_ZERO_MASS_AUDIT_BEFORE_NATIVE')<min(i for i,(t,o) in enumerate(rows) if t=='RAW_NATIVE_FACTUAL_BEFORE_TRUTH'),'native before complete audit')
    for a in actual:
        key=(a['id'],a['basis_index']);require(key not in seen,'duplicate native');seen.add(key);r=index[key[0]];b=key[1];p=a['payload']
        require(a['address']==r['address'] and a['target']==r['target'] and a['basis']==list(keys[b]) and a['scene']==[keys[b][0],keys[b][1],0,0,keys[b][2]],'native scene/world')
        require(p==dict(r['consulted_predictions'])[b] and all(raw_index[key][n]==p[n] for n in ('trace','outcome','return_hex')),'full native/raw/prediction differs')
        verify_trace(p,keys[b],q,'X',r['address'],r['target'])
        fp=sha256(('\0\0X:'+','.join(map(str,r['address']+[r['target']]))+'\0').encode()).hexdigest()
        require(a['all_store_sizes']==[0,0,1,0] and a['fingerprint_pre']==a['fingerprint_after_read']==fp,'full pre/observation state')
        require(p['outcome']=='SUCCESS' and p['Gamma_P_star'],'all consulted sole X changes should manifest but succeed')
        outcomes[p['outcome']]+=1;nrows+=len(p['trace'])
    require(seen==expected_X and len(actual)==pre_audit['all_consulted_native_cases_to_check'],'missing/extra native')
    f=scalar['FINAL'];require(len(actual)==f['new_native_initial_X_rollouts'] and nrows==f['new_native_raw_rows'] and dict(outcomes)==f['all_observed_outcomes'],'native counts')
    require(sha256(canonical(actual)).hexdigest()==f['actual_registry_sha256'],'actual canonical hash')
    print(json.dumps({'status':'ZERO_TRIGGER_MASS_COUNTEREXAMPLE_FULLY_CHECKED_NOT_SCIENTIFIC_STOP',
          'role':'PRIMARY_INDEPENDENT_STDLIB_STORED_ORACLE_NOT_EXPERT_OR_SCIENCE',
          'initial_native_exit':1,'initial_new_native_rollouts':0,'initial_source_and_complete_failure_preserved':True,
          'configurations_checked':19964,'all_prediction_raw_rows_checked':prediction_rows,'normalizers':summaries,
          'X_consulted_configurations':len(consulted_X),'X_never_consulted_configurations':3600-len(consulted_X),
          'new_native_initial_X_rollouts':len(actual),'new_native_raw_rows':nrows,'all_actual_outcomes':dict(outcomes),
          'old_nominal_basis':48,'old_nominal_raw_rows':sum(len(p['trace']) for p in nominal),
          'runtime_inputs_checked':845,'parent_HEAD_byte_bindings':679,'source_count':313,'old_native_count':153,'prior_preparation_count':365,
          'failed_candidate_or_old_fixture_rerun':False,'predictor_candidate_RFL_solver_execution_by_checker':False,
          'scientific_rules_adopted':False,'scientific_PASS':False,'independent_expert':False,
          'mechanism_direction_falsified':False,'collection_authorized':False,'valid_current_scientific_STOP':False},sort_keys=True))


if __name__=='__main__':main()
