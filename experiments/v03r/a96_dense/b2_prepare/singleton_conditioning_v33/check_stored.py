"""Independent stdlib full stored-data checker; no predictor/candidate/RFL/solver imports."""
from collections import Counter,defaultdict
from fractions import Fraction
from hashlib import sha1,sha256
from pathlib import Path
import json,subprocess
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]


def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def read(p):return json.loads(p.read_bytes())
def require(ok,why):
    if not ok:raise AssertionError(why)
def frac(f):return [f.numerator,f.denominator]


def records(folder,expected=None,strict=False):
    claim,ex=read(folder/'claim.json'),read(folder/'exit.json')
    require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in claim.items()),'receipt differs')
    for n,v in ex['files'].items():
        b=(folder/n).read_bytes();require(len(b)==v['bytes'] and sha256(b).hexdigest()==v['sha256'],'raw bytes differ')
    require(not (folder/'stderr.log').read_bytes(),'nonempty stderr')
    if expected:require(ex['files']['stdout.log']['sha256']==expected,'bound evidence differs')
    result=[]
    for line in (folder/'stdout.log').read_bytes().splitlines(keepends=True):
        require(line.endswith(b'\n'),'incomplete raw line')
        if b'=' not in line:
            require(not strict,'untagged current line');continue
        t,v=line.rstrip(b'\r\n').split(b'=',1)
        if v[:1] not in (b'{',b'['):
            require(not strict,'invalid current payload');continue
        o=json.loads(v)
        if strict:require(canonical(o).rstrip(b'\n')==v,'noncanonical current JSON')
        result.append((t.decode(),o))
    return result,ex


def payload_from_basis(p):
    return {'trace':[dict(zip(('pre_state','z','m','a_cmd','u','a_realized','reward_hex','post_state','post_control','terminal','outcome','illegal'),r)) for r in p['trace']],
            'outcome':p['outcome'],'return_hex':p['return_hex'],'Gamma_P_star':[]}


def verify_trace(p,key,q,arch=None,address=None,target=None):
    # Independent equations check each observed transition, not a second forecast run.
    k,phi,z=key;s=[0,2,0,k,phi];m=0;gamma=[];rewards=[]
    open_cells={(x,y) for x in range(5) for y in range(1,5) if x in (1,2,3)}-{(2,3)}|{(0,2),(4,2)}
    delta={0:(0,-1),1:(0,1),2:(-1,0),3:(1,0),4:(0,0)}
    for n,r in enumerate(p['trace']):
        require(r['pre_state']==s and r['z']==z and r['m']==m,'trajectory continuity')
        row=q[tuple(s+[z,m])];best=max(row.values());a=min(a for a,v in row.items() if v==best)
        if arch=='D' and s+[z,m]==address:a=target
        require(r['a_cmd']==a and a in row,'native command not sole edit or nominal action')
        u=target if arch=='X' and s+[a]==address else a
        require(r['u']==r['a_realized']==u,'native execution not sole controller edit')
        if a not in [x for x,v in row.items() if v>=best-1e-12]:gamma.append('Decision_'+str(s[2]))
        if u!=a:gamma.append('ControllerSite_'+'_'.join(map(str,s[:3]+[a])))
        dx,dy=delta[u];cell=(s[0]+dx,s[1]+dy)
        require(cell in open_cells,'illegal persistent action')
        t=s[2]+1;period=(6,3)[k]
        outcome='COLLISION' if cell==(2,2) and t%period==phi%period else 'SUCCESS' if cell==(4,2) else 'TIMEOUT' if t==12 else None
        nm=1 if m or (z==1 and cell==(2,1)) or (z==3 and cell==(2,4)) or (z==2 and s[:2]==[1,2] and s[2]%period!=phi%period) else 0
        reward=-.02
        if outcome:reward+=1. if outcome=='SUCCESS' else -1.
        nxt=[cell[0],cell[1],t,k,phi]
        require(r['post_state']==nxt and r['post_control']==[z,nm],'native state/automaton equation')
        require(r['reward_hex']==reward.hex() and r['terminal']==(outcome is not None) and r['outcome']==outcome and r['illegal'] is False,'native reward/terminal equation')
        require(not outcome or n==len(p['trace'])-1,'continued after terminal')
        s=nxt;m=nm;rewards.append(reward)
    require(p['trace'] and p['trace'][-1]['terminal'],'incomplete trajectory')
    require(p['outcome']==p['trace'][-1]['outcome'] and p['return_hex']==float(sum(rewards)).hex() and p['Gamma_P_star']==gamma,'return/truth differs')


def main():
    c=read(HERE/'contract.json');rows,ex=records(HERE/'evidence',strict=True)
    for n,d in ex['inputs'].items():require(sha256((HERE/n).read_bytes()).hexdigest()==d,n)
    scalar={t:o for t,o in rows if t in ('INPUT_BINDING_BEFORE','INPUT_BINDING_AFTER','ALL_PREDICTIONS_COMPLETE_BEFORE_NATIVE','FINAL','NOMINAL_BASIS_BOUND')}
    before=scalar['INPUT_BINDING_BEFORE'];require(before==scalar['INPUT_BINDING_AFTER'],'input drift')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit']==before['parent_HEAD'],'parent drift')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    audit=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=audit['fixed_native_file_hashes']|audit['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound),len(before['input_sha256']))==(313,153,365,679,837),'binding extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native|before['input_sha256']).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    cat,_=records(PREP/c['stored_catalog']['folder'],c['stored_catalog']['stdout_sha256'])
    D=[o for t,o in cat if t=='DECISION_CONTEXT'];X=[o for t,o in cat if t=='CONTROLLER_SITE']
    q={tuple(r['context']):{a:float.fromhex(v) for a,v in r['q_row_hex']} for r in D}
    br,_=records(PREP/c['stored_basis']['folder'],c['stored_basis']['stdout_sha256']);basis=next(o['entries'] for t,o in br if t=='NATIVE_BASIS')
    keys=[(b['kappa'],b['phase'],b['committed']) for b in basis];require(len(keys)==len(set(keys))==48,'basis')
    nominal=[payload_from_basis(b['payload']) for b in basis]
    for k,p in zip(keys,nominal):verify_trace(p,k,q)
    require(scalar['NOMINAL_BASIS_BOUND']['canonical_sha256']==sha256(canonical(nominal)).hexdigest(),'nominal digest')
    registry=[o for t,o in rows if t=='CONFIGURATION_PREDICTION'];actual=[o for t,o in rows if t=='ACTUAL_FACTUAL']
    require(max(i for i,(t,o) in enumerate(rows) if t=='CONFIGURATION_PREDICTION')<next(i for i,(t,o) in enumerate(rows) if t=='ALL_PREDICTIONS_COMPLETE_BEFORE_NATIVE')<min(i for i,(t,o) in enumerate(rows) if t=='ACTUAL_FACTUAL'),'prediction not before native')
    index={r['id']:r for r in registry};require(len(index)==len(registry),'duplicate configuration')
    summaries={};expected_ids=[];expected_actual=set()
    for arch,catalog,field in (('D',D,'context'),('X',X,'site')):
        eligible=[r for r in catalog if r['alternatives']];M=len(eligible);Z=Fraction();J=Fraction();hist=defaultdict(Fraction);worlds=0
        for pos,r in enumerate(eligible):
            address=r[field];visits=[b for b,p in enumerate(nominal) if any(t['pre_state']+([t['z'],t['m']] if arch=='D' else [t['a_cmd']])==address for t in p['trace'])]
            require(bool(visits)==r['nominal_basis_consulted'],'catalog consultation')
            for target in r['alternatives']:
                wid=f'{arch}:{pos}:{target}';expected_ids.append(wid);pred=index[wid];mass=Fraction(1,M*len(r['alternatives']));worlds+=1
                require(pred['address']==address and pred['target']==target and pred['architecture']==arch and pred['eligible_position']==pos and pred['alternatives']==len(r['alternatives']),'configuration changed')
                require(pred['original_mass']==frac(mass) and pred['consulted_basis']==visits,'configuration weight/extent')
                require([b for b,p in pred['consulted_predictions']]==visits,'prediction completeness')
                triggers=[]
                for b,p in pred['consulted_predictions']:
                    verify_trace(p,keys[b],q,arch,address,target)
                    hit=next(i for i,t in enumerate(nominal[b]['trace']) if t['pre_state']+([t['z'],t['m']] if arch=='D' else [t['a_cmd']])==address)
                    require(p['trace'][:hit]==nominal[b]['trace'][:hit],'first-hit prefix altered')
                    if p['outcome']!='SUCCESS' and p['Gamma_P_star']:triggers.append(b)
                    for installed in (('D_Q','D_patch') if arch=='D' else ('X',)):expected_actual.add((wid,installed,b))
                require(pred['trigger_basis']==triggers and pred['trigger_scene_mass']==frac(Fraction(len(triggers),48)),'trigger extent')
                if triggers:Z+=mass
                J+=mass*Fraction(len(triggers),48);hist[len(triggers)]+=mass
        require(sum(hist.values(),Fraction())==1 and Z>0,'measure normalization')
        summaries[arch]={'eligible_positions':M,'assigned_configurations':worlds,'triggerable_mass':frac(Z),'nontrigger_mass':frac(1-Z),
          'joint_defect_scene_failure_mass_NOT_defect_normalizer':frac(J),'trigger_count_original_mass_histogram':[[n,frac(v)] for n,v in sorted(hist.items())],
          'conditional_configuration_mass_sum':frac(sum((Fraction(*r['original_mass'])/Z for r in registry if r['architecture']==arch and r['trigger_basis']),Fraction()))}
        require(summaries[arch]['conditional_configuration_mass_sum']==[1,1],'conditional mass not one')
    require([r['id'] for r in registry]==expected_ids and len(registry)==16364+3600,'whole finite singleton support')
    require(summaries==scalar['ALL_PREDICTIONS_COMPLETE_BEFORE_NATIVE']['normalizers']==scalar['FINAL']['normalizers'],'normalizer summary')
    require(sha256(canonical(registry)).hexdigest()==scalar['FINAL']['configuration_prediction_registry_sha256']==scalar['ALL_PREDICTIONS_COMPLETE_BEFORE_NATIVE']['registry_sha256'],'prediction registry digest')
    unfiltered=[o for t,o in rows if t=='RAW_NATIVE_FACTUAL_BEFORE_TRUTH']
    unfiltered_index={(o['id'],o['architecture'],o['basis_index']):o for o in unfiltered}
    require(len(unfiltered_index)==len(unfiltered),'duplicate raw before truth')
    seen=set();new=raw=reuse=0;outcomes=Counter()
    old,_=records(PREP/c['stored_patch_anchor']['folder'],c['stored_patch_anchor']['stdout_sha256']);old_patch=next(o for t,os in old if t=='COMPLETE_ARCHITECTURES' for o in os if o['architecture']=='D_patch')
    for a in actual:
        wid,arch,b=a['id'],a['architecture'],a['basis_index'];key=(wid,arch,b);require(key not in seen,'duplicate actual');seen.add(key)
        r=index[wid];p=a['payload'];require(p==dict(r['consulted_predictions'])[b],'predicted and observed differ')
        verify_trace(p,keys[b],q,r['architecture'],r['address'],r['target'])
        address=r['address'];target=r['target'];parts=['','','',''];amplitude=None
        if arch=='D_Q':
            row=q[tuple(address)];best=max(row.values());amplitude=best+(best-row[target]);require(amplitude>best,'DQ promotion')
            parts[3]='Q:'+','.join(map(str,address+[target]))+'|'+amplitude.hex()
        elif arch=='D_patch':parts[0]='D:'+','.join(map(str,address+[target]))
        else:parts[2]='X:'+','.join(map(str,address+[target]))
        fp=sha256('\0'.join(parts).encode()).hexdigest()
        require(a['fingerprint_pre']==a['fingerprint_after_read']==fp and a['DQ_promoted_value_hex']==(None if amplitude is None else amplitude.hex()),'all-store fingerprint/installer')
        require(a['all_store_sizes']=={'D_Q':[0,0,0,1],'D_patch':[1,0,0,0],'X':[0,0,1,0]}[arch],'extra store defect')
        require(a['basis']==list(keys[b]) and a['scene']==[keys[b][0],keys[b][1],0,0,keys[b][2]],'basis scene order')
        anchor=c['stored_patch_anchor'];is_old=arch=='D_patch' and address==anchor['context'] and target==anchor['target'] and list(keys[b])==anchor['basis']
        require(a['source']==('READ_ONLY_EXACT_v25_FACTUAL' if is_old else 'NEW_NATIVE_SINGLETON_FACTUAL'),'old/new origin')
        if is_old:
            audit=old_patch['original_owned_audit'];require(p['trace']==audit['raw_trace'] and p['Gamma_P_star']==audit['truth']['Gamma_P_star'] and fp==old_patch['source_fingerprint'],'old factual mismatch');reuse+=1
        else:
            raw_before=unfiltered_index[key]
            require(all(raw_before[n]==p[n] for n in ('trace','outcome','return_hex')),'raw factual was not retained before truth')
            new+=1;raw+=len(p['trace'])
        outcomes[arch+':'+p['outcome']]+=1
    require(seen==expected_actual and len(unfiltered)==new,'native consultation cases missing/extra')
    f=scalar['FINAL'];require(new==f['new_native_initial_defect_rollouts'] and raw==f['new_native_raw_rows'] and reuse==f['old_exact_patch_factual_reused']==1 and len(actual)==f['actual_records'],'actual counts')
    require(sha256(canonical(actual)).hexdigest()==f['actual_registry_sha256'],'actual registry hash')
    print(json.dumps({'status':'FULL_STORED_SINGLETON_CONTENT_CHECKED','role':'PRIMARY_INDEPENDENT_STDLIB_ORACLE_NOT_EXPERT_OR_SCIENCE',
          'parent_HEAD_byte_bindings':679,'runtime_inputs_checked':837,'source_count':313,'old_native_count':153,'prior_preparation_count':365,
          'configurations':len(registry),'normalizers':summaries,'all_consulted_actual_records':len(actual),
          'new_native_initial_defect_rollouts':new,'new_native_raw_rows':raw,'old_exact_patch_factual_reused':reuse,
          'all_observed_outcomes':dict(sorted(outcomes.items())),'all_original_basis_raw_rows':sum(len(p['trace']) for p in nominal),
          'no_RFL_predictor_candidate_or_solver_import':True,'scientific_PASS':False,'independent_expert':False,
          'multi_address_or_mixed_totality':False,'collection_authorized':False},sort_keys=True))


if __name__=='__main__':main()
