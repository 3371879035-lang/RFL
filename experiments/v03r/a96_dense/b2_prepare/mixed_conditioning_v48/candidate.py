"""Complete mixed initial grammar mass by full unread cylinders, not science."""
from collections import Counter
from fractions import Fraction
from hashlib import sha1, sha256
from pathlib import Path
import json, subprocess
HERE=Path(__file__).resolve().parent; PREP=HERE.parent; ROOT=HERE.parents[4]
def read(p):return json.loads(p.read_bytes())
def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def emit(t,o):print(t+'='+canonical(o).decode().rstrip('\n'),flush=True)
def require(ok,why):
    if not ok:raise AssertionError(why)
def digest(p,blob=False):
    h=sha1(b'blob '+str(p.stat().st_size).encode()+b'\0') if blob else sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def bind(c):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'parentHEAD')
    tree={v.split(b'\t')[1].decode():v.split()[2].decode() for v in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if v}
    source=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources'];a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit']
    native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes'];prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')}
    bound=set(source)|prior|{'experiments/rebuild_status_current.json'}
    require((len(source),len(native),len(prior),len(bound))==(313,153,622,936),'parent extent')
    for p in bound:require(digest(ROOT/p,True)==tree[p],'HEAD byte '+p)
    for p,h in (source|native).items():require(digest(ROOT/p)==h,'frozen/native '+p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==1093,'runtime extent')
    return {'HEAD':head,'HEAD_bindings':936,'runtime_inputs':1093,'input_sha256':{p:digest(ROOT/p) for p in sorted(names)}}
def capture(info):
    folder=PREP/info[0];cl=read(folder/'claim.json');ex=read(folder/'exit.json')
    require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items()),'stored claim/exit')
    require(ex['files']['stdout.log']['sha256']==info[1] and (folder/'stderr.log').stat().st_size==0,'stored identity')
    for n,v in ex['files'].items():require({'bytes':(folder/n).stat().st_size,'sha256':digest(folder/n)}==v,'full stored bytes')
    for n,h in ex['inputs'].items():require(digest(folder.parent/n)==h,'executed source immutable')
    with (folder/'stdout.log').open('rb') as f:
        for l in f:
            require(l.endswith(b'\n'),'completeEOF line')
            if b'=' not in l:continue
            t,v=l.rstrip(b'\r\n').split(b'=',1)
            if v[:1] not in (b'{',b'['):continue
            o=json.loads(v)
            if info[0].startswith('mixed_projection'):require(canonical(o).rstrip(b'\n')==v,'full mixed canonical')
            yield t.decode(),o
def rat(v):return [v.numerator,v.denominator]
def toy(case):
    dr=[1+(i+case)%3 for i in range(3+case%3)];xr=[1+(2*i+case)%3 for i in range(5+case%2)]
    cylinders=[] if case==0 else [[0,0,list(range(1+case%3))],[1,0,list(range(2+case%2))]]
    single=[] if case==0 else [[0,0,0,0],[1,0,1,0],[2,0,len(xr)-1,0]]
    z=sum((Fraction(len(xr)-len(v),len(dr)*len(xr)*dr[d]) for d,t,v in cylinders),Fraction())
    z+=sum((Fraction(1,len(dr)*len(xr)*dr[d]*xr[x]) for d,t,x,u in single),Fraction())
    count=sum(dr[d]*0+sum(xr[x] for x in range(len(xr)) if x not in v) for d,t,v in cylinders)+len(single)
    return {'case':case,'D_target_counts':dr,'X_target_counts':xr,'cylinders':cylinders,'singletons':single,'Z':rat(z),'trigger_full_target_worlds':count,'reader_duplicate_mass_not_added':True}
def main():
    c=read(HERE/'contract.json');before=bind(c);emit('INPUT_BINDING_BEFORE',before)
    D=[];X=[];R=[];panel=[];barrier=None
    for t,o in capture(c['stored']['catalog']):
        if t=='DECISION_CONTEXT':D.append(o)
        if t=='CONTROLLER_SITE':X.append(o)
    for t,o in capture(c['stored']['revision']):
        if t=='REVISED_SITE_NOT_ADOPTED':R.append(o)
    for t,o in capture(c['stored']['mixed']):
        if t=='PREDICTION_BEFORE_ANY_NATIVE':panel.append(o)
        if t=='COMPLETE_PANEL_BEFORE_NATIVE':barrier=o
    ck=list(capture(c['stored']['mixed_check']));require(len(ck)==1,'stored checker extent')
    require(len(D)==13824 and len(X)==len(R)==5904 and len(panel)==5791,'complete stored support')
    require(barrier['prediction_sha256']==sha256(canonical(panel)).hexdigest() and ck[0][1]['prediction_sha256']==barrier['prediction_sha256'],'complete stored predictions')
    da={tuple(o['context']):o['alternatives'] for o in D};grammars={'old_all8':{tuple(o['site']):o['alternatives'] for o in X},'domain_command_not_adopted':{tuple(o['site']):o['targets'] for o in R}}
    require((sum(bool(v) for v in da.values()),sum(map(len,da.values())))==(7551,16364),'complete D')
    degrees=Counter(o['actual_degree'] for o in panel);require(degrees==Counter({'0,0':48,'0,1':179,'1,0':586,'1,1':4978}),'all degrees')
    require(all(o['pre']['outcome']=='SUCCESS' for o in panel if o['actual_degree']=='0,1'),'singletonX no failure')
    only=[o for o in panel if o['actual_degree']=='1,0' and o['pre']['outcome']!='SUCCESS'];both=[o for o in panel if o['actual_degree']=='1,1' and o['pre']['outcome']!='SUCCESS']
    require((len(only),len(both))==(26,143),'complete event classification')
    require(len({canonical(o['D_declaration']) for o in only})==26 and len({canonical([o['D_declaration'],o['X_declaration']]) for o in both})==143,'one actualroot full literal uniqueness')
    summaries=[];allcuts=[]
    for name,xa in grammars.items():
        eligible=[s for s,v in xa.items() if v];M=len(eligible);targettotal=sum(map(len,xa.values()));cuts=[];single=[]
        for s in eligible:emit('COMPLETE_ELIGIBLE_X_SITE',{'grammar':name,'site':list(s),'targets':xa[s]})
        for o in only:
            d,t=o['D_declaration'];queried={tuple(r['pre_state']+[r['a_cmd']]) for r in o['pre']['trace']};unread=[s for s in eligible if s not in queried]
            visited=[s for s in eligible if s in queried];weight=Fraction(len(unread),7551*M*len(da[tuple(d)]))
            cut={'grammar':name,'stored_id':o['id'],'basis':o['basis'],'D_declaration':[d,t],
                 'excluded_consulted_eligible_X_sites':[list(s) for s in visited],'unread_X_sites':len(unread),
                 'complete_unread_target_assigned_worlds':sum(len(xa[s]) for s in unread),'unconditioned_product_mass':rat(weight)}
            require(d[3:6]==o['basis'] and t in da[tuple(d)],'unique D basis address')
            cuts.append(cut);emit('COMPLETE_UNREAD_X_FAILURE_CYLINDER',cut)
        for o in both:
            d,t=o['D_declaration'];s,u=o['X_declaration'];s=tuple(s)
            if u not in xa[s]:continue
            for prev in cuts:
                if prev['D_declaration']==[d,t]:require(list(s) in prev['excluded_consulted_eligible_X_sites'],'firsthit cylinder disjoint')
            row={'grammar':name,'stored_id':o['id'],'basis':o['basis'],'D_declaration':[d,t],'X_declaration':[list(s),u],
                 'unconditioned_product_mass':rat(Fraction(1,7551*M*len(da[tuple(d)])*len(xa[s])))}
            require(d[3:6]==o['basis'],'one root trigger');single.append(row);emit('BOTH_ACTUAL_FAILURE_FULL_WORLD',row)
        Z=sum((Fraction(*o['unconditioned_product_mass']) for o in cuts+single),Fraction())
        count=sum(o['complete_unread_target_assigned_worlds'] for o in cuts)+len(single)
        summary={'grammar':name,'eligible_D_contexts':7551,'D_targets':16364,'eligible_X_sites':M,'X_targets':targettotal,
                 'full_site_pair_support':7551*M,'full_target_assigned_world_support':16364*targettotal,'unread_failure_cylinders':len(cuts),
                 'both_actual_failure_worlds':len(single),'trigger_full_target_assigned_worlds':count,'nontrigger_full_target_assigned_worlds':16364*targettotal-count,
                 'Z':rat(Z),'nontrigger_mass':rat(1-Z),'cut_sha256':sha256(canonical(cuts+single)).hexdigest(),
                 'scientific_grammar_adopted':False,'not_uniform_target_world_measure':True}
        require(0<Z<1,'candidate defined mixed conditional mass');summaries.append(summary);allcuts.extend(cuts+single);emit('COMPLETE_MIXED_CELL',summary)
    toys=[toy(i) for i in range(8)]
    for o in toys:emit('WEIGHTED_CUT_TOY',o)
    after=bind(c);require(after==before,'all inputs stable');emit('INPUT_BINDING_AFTER',after)
    emit('FINAL',{'status':'COMPLETE_MIXED_D1_X1_INITIAL_GRAMMAR_CONDITION_MASS_NOT_SCIENCE','cells':summaries,
         'cut_sha256':sha256(canonical(allcuts)).hexdigest(),'toy_sha256':sha256(canonical(toys)).hexdigest(),
         'stored_prediction_sha256':barrier['prediction_sha256'],'full48_basis_root_union_not_independent_product':True,
         'full_unread_literal_support_preserved':True,'runtime_inputs':1093,'parent_HEAD_bindings':936,'all_inputs_equal':True,
         'new_native_kernel_steps':0,'new_learner_rollouts':0,'B1_arms':0,'reference_DP':0,'learner_DP':0,'keys_allocated':0,'random_draws':0,'future_training':0,
         'sampler_or_collector_executed':False,'scientific_grammar_or_rules_adopted':False,'scientific_PASS':False,'collection_authorized':False,'research_complete':False,'mechanism_direction_falsified':False})
if __name__=='__main__':main()
