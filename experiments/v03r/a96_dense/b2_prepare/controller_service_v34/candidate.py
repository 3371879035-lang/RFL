"""Native finite legal-history graph; not keyed training or a fault sampler."""
from collections import Counter,deque
from hashlib import sha1,sha256
from pathlib import Path
import json,subprocess,sys
from unittest.mock import patch
HERE=Path(__file__).resolve().parent;PREP=HERE.parent;ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/'src'))
from rfl_rebuild.env import kernel as K


def canonical(o):return (json.dumps(o,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)+'\n').encode()
def emit(t,o):print(t+'='+canonical(o).decode().rstrip('\n'),flush=True)
def read(p):return json.loads(p.read_bytes())
def require(ok,why):
    if not ok:raise AssertionError(why)


def binding(c):
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip();require(head==c['parent_commit'],'parent')
    tree={r.split(b'\t')[1].decode():r.split()[2].decode() for r in subprocess.check_output(['git','ls-tree','-r','-z',head],cwd=ROOT).split(b'\0') if r}
    sources=read(ROOT/'experiments/v03r/a96_dense/pipeline/frozen_inputs.json')['sources']
    a=read(ROOT/'experiments/v03r/a96_dense/pipeline/full_f1_complete_external_audit.json')['audit'];native=a['fixed_native_file_hashes']|a['post_controller_commit_native_tail_hashes']
    prior={p for p in tree if p.startswith(PREP.relative_to(ROOT).as_posix()+'/')};bound=set(sources)|prior|{'experiments/rebuild_status_current.json'}
    require((len(sources),len(native),len(prior),len(bound))==(313,153,389,703),'parent extent')
    for p in bound:
        b=(ROOT/p).read_bytes();require(sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==tree[p],p)
    for p,d in (sources|native).items():require(sha256((ROOT/p).read_bytes()).hexdigest()==d,p)
    names=bound|set(native)|{(HERE/n).relative_to(ROOT).as_posix() for n in ('contract.json','candidate.py','execute.py','check_stored.py')}
    require(len(names)==860,'runtime extent')
    return {'parent_HEAD':head,'HEAD_byte_bindings':703,'input_sha256':{p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(names)}}


def catalog(c):
    folder=PREP/c['stored_catalog']['folder'];cl,ex=read(folder/'claim.json'),read(folder/'exit.json')
    require(ex['native_child_exit_code']==0 and all(ex[k]==v for k,v in cl.items()),'old native receipt')
    for n,v in ex['files'].items():
        b=(folder/n).read_bytes();require(len(b)==v['bytes'] and sha256(b).hexdigest()==v['sha256'],'old native raw')
    require(ex['files']['stdout.log']['sha256']==c['stored_catalog']['stdout_sha256'] and not (folder/'stderr.log').read_bytes(),'old catalog')
    rows=[]
    for line in (folder/'stdout.log').read_bytes().splitlines():
        t,v=line.split(b'=',1);rows.append((t.decode(),json.loads(v)))
    return [o for t,o in rows if t=='DECISION_CONTEXT'],[o for t,o in rows if t=='CONTROLLER_SITE']


def result_payload(r):
    return {'post':[r.state.x,r.state.y,r.state.t,r.state.kappa,r.state.phi,r.control.z,r.control.m],
            'a_cmd':r.a_cmd,'u':r.u,'a_realized':r.a_realized,'reward_hex':r.reward.hex(),
            'terminal':r.terminal,'outcome':r.outcome,'illegal':r.illegal}


def main():
    c=read(HERE/'contract.json');before=binding(c);emit('INPUT_BINDING_BEFORE',before);D,X=catalog(c)
    require(len(D)==13824 and len(X)==5904,'full original domain')
    legal={}
    for r in D:
        key=tuple(r['context']);s=K.State(*key[:5]);ctrl=K.ControlState(*key[5:]);acts=K.option_actions(ctrl.z,ctrl,s)
        require(list(acts)==[a for a,h in r['q_row_hex']],'stored full Q legal row differs')
        legal[key]=set(acts)
    roots=[(0,2,0,k,phi,z,0) for k in range(2) for phi in range(6) for z in range(4)]
    queue=deque(roots);seen=set(roots);edges=[];path={r:[] for r in roots}
    emit('ROOTS',{'roots':[list(r) for r in roots],'scope':'ALL_LEGAL_HISTORY_LANGUAGE_NOT_KEYED_PROBABILITY'})
    while queue:
        node=queue.popleft();s=K.State(*node[:5]);ctrl=K.ControlState(*node[5:]);require(node in legal,'graph outside full decision domain')
        for cmd in sorted(legal[node]):
            r=K.step(s,ctrl,cmd,tape=K.SemanticTape(node[4],0,0));p=result_payload(r)
            edge={'pre':list(node),'command':cmd,'result':p};edges.append(edge);emit('NATIVE_LEGAL_EDGE',edge)
            nxt=tuple(p['post'])
            require(r.u==r.a_realized==cmd and not r.illegal,'not identity legal transition')
            if not r.terminal and nxt not in seen:
                seen.add(nxt);path[nxt]=path[node]+[cmd];queue.append(nxt)
    nodes=sorted(seen);emit('ALL_REACHABLE_NODES',{'nodes':[list(n) for n in nodes]})
    domain={};reachable={}
    for key,acts in legal.items():
        for cmd in sorted(acts):
            site=key[:5]+(cmd,);domain.setdefault(site,[]).append(key[5:])
            if key in seen:reachable.setdefault(site,[]).append(key[5:])
    require(set(domain)=={tuple(r['site']) for r in X},'service must preserve every union site')
    rows=[];stats=Counter()
    for old in X:
        site=tuple(old['site']);ds=sorted(domain[site]);rs=sorted(reachable.get(site,[]))
        dc=sorted(set.intersection(*(legal[site[:5]+zm] for zm in ds)))
        rc=sorted(set.intersection(*(legal[site[:5]+zm] for zm in rs))) if rs else None
        require(set(old['all8_common_legal'])<=set(dc),'old intersection not subset of domain command-conditioned')
        if rs:require(set(dc)<=set(rc),'domain intersection not subset of reachable')
        da=[a for a in dc if a!=site[5]];ra=None if rc is None else [a for a in rc if a!=site[5]]
        row={'site':list(site),'old_all8_common':old['all8_common_legal'],'old_alternatives':old['alternatives'],
             'domain_service':[list(zm) for zm in ds],'reachable_service':[list(zm) for zm in rs],
             'domain_command_common':dc,'reachable_command_common':rc,'domain_alternatives':da,
             'reachable_alternatives':ra,'status':'REACHABLE_SERVICE' if rs else 'NO_REACHABLE_SERVICE_NOT_DELETED',
             'old_nominal_consulted':old['nominal_basis_consulted']}
        rows.append(row);emit('COMPLETE_SITE_SERVICE',row)
        stats['sites']+=1;stats['old_eligible_sites']+=bool(old['alternatives']);stats['domain_alternative_sites']+=bool(da)
        stats['reachable_sites']+=bool(rs);stats['unreachable_sites_retained']+=not rs
        stats['reachable_alternative_sites']+=bool(ra);stats['old_assigned_targets']+=len(old['alternatives'])
        stats['domain_assigned_targets']+=len(da);stats['reachable_assigned_targets']+=len(ra or [])
        stats['old_eligible_but_unreachable']+=bool(old['alternatives']) and not rs
        stats['reachable_new_alternatives_vs_all8']+=len(set(ra or [])-set(old['alternatives']))
    witness=c['fixed_counterexample'];site=tuple(witness['site']);node=site[:5]+(witness['serving_option'],witness['serving_m'])
    require(node in seen and path[node]==witness['prefix_commands'] and site[5] in legal[node] and witness['target'] not in legal[node],'fixed serving witness changed')
    predicted={'site':list(site),'target':witness['target'],'serving_context':list(node),'root':witness['root'],
               'prefix_commands':path[node],'serving_legal_actions':sorted(legal[node]),'expected_exception':'LearnerContractViolation'}
    emit('FIXED_ADMISSIBILITY_COUNTEREXAMPLE_BEFORE_NATIVE',predicted)
    try:
        K.step(K.State(*node[:5]),K.ControlState(*node[5:]),site[5],tape=K.SemanticTape(node[4],0,0),
               controller={K.ControllerSite(K.State(*node[:5]),site[5]):witness['target']})
    except K.LearnerContractViolation as err:
        emit('NATIVE_ADMISSIBILITY_REJECTION',{'exception':type(err).__name__,'message':str(err),'witness':predicted})
    else:raise AssertionError('fixed inadmissibility counterexample refuted; retain all evidence')
    after=binding(c);emit('INPUT_BINDING_AFTER',after);require(before==after,'inputs changed')
    emit('FINAL',{'status':'FULL_ORIGINAL_CONTROLLER_SERVICE_ENVELOPE_AUDITED_NOT_SCIENCE',
          'roots':len(roots),'reachable_decision_contexts':len(nodes),'unreachable_decision_contexts_retained':len(D)-len(nodes),
          'new_native_identity_kernel_steps':len(edges),'new_native_rejected_controller_steps':1,
          'terminal_edges':dict(Counter(e['result']['outcome'] for e in edges if e['result']['terminal'])),
          'node_registry_sha256':sha256(canonical([list(n) for n in nodes])).hexdigest(),
          'edge_registry_sha256':sha256(canonical(edges)).hexdigest(),'site_registry_sha256':sha256(canonical(rows)).hexdigest(),
          'site_comparison_counts_NOT_adopted_grammar':dict(stats),'full_inputs_equal':True,
          'future_keyed_history_probability_proved':False,'new_fault_installer_or_sampler':False,
          'learner_rollouts':0,'B1_arms':0,'new_DP_execution':False,'future_training':0,'keys_allocated':0,
          'collector_executed':False,'scientific_rules_adopted':False,'population_reduced':False,
          'scientific_PASS':False,'mechanism_direction_falsified':False,'joint_calibration_totality':False,
          'delta_joint':None,'collection_authorized':False,'valid_current_scientific_STOP':False,'research_complete':False})


if __name__=='__main__':
    with patch.object(K,'rollout',side_effect=AssertionError('no learner episodes')), \
         patch.object(K.SemanticTape,'sample',side_effect=AssertionError('no sampling')):
        main()
