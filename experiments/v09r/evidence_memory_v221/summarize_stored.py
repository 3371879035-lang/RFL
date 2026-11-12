"""Post-run, read-only delivery analysis; no model forward or environment execution."""
from collections import defaultdict
from pathlib import Path
import hashlib,json,math,subprocess
import torch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];CAP=HERE/'capture'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    probe=json.loads((CAP/'probe_summary.json').read_text());audit=json.loads((CAP/'stored_audit.json').read_text())
    claim=json.loads((CAP/'claim.json').read_text());native=json.loads((CAP/'exit.json').read_text())
    events={};sessions={};adoptions=[];policies=[]
    with (CAP/'events.jsonl').open(encoding='utf-8') as f:
        for row in map(json.loads,f):
            if row['kind']=='event':events[row['event']['id']]=row['event']
            elif row['kind']=='session':sessions[row['session']['id']]=row['session']
            elif row['kind']=='decision':
                decision=row['decision']
                if decision['kind']=='task':policies.append(decision['policy'])
                if decision['kind']=='adoption' and decision['choice']:adoptions.append(decision)
    mixed=0;repeated=0
    for session in sessions.values():
        groups=defaultdict(list)
        for receipt in session['receipts']:groups[receipt['arm']].append(events[receipt['event_id']]['goal_met'])
        repeated+=sum(len(v)>1 for v in groups.values());mixed+=sum(len(set(v))>1 for v in groups.values())
    families={}
    for family in ('stable_noisy','changed_noisy'):
        runs=[r for r in probe['runs'] if r['family']==family]
        families[family]={'main_episodes':sum(r['completed_main_episodes'] for r in runs),'main_successes':sum(r['main_successes'] for r in runs),
                          'counts':{k:sum(r['counters'][k] for r in runs) for k in probe['counts']},
                          'comparison_examples':sum(r['comparison_examples'] for r in runs)}
    restored=[]
    for seed in (11,23,37):
        path=CAP/f'untrained_seed_{seed}.pt';c=torch.load(path,map_location='cpu',weights_only=True);h=hashlib.sha256()
        for name,t in c['state_dict'].items():h.update(name.encode());h.update(t.cpu().contiguous().numpy().tobytes())
        expected={r['model_before'] for r in probe['runs'] if r['seed']==seed}
        assert expected=={h.hexdigest()} and c['status']=='UNTRAINED_INITIALIZATION'
        restored.append({'seed':seed,'model_id':h.hexdigest(),'sha256':sha(path),'bytes':path.stat().st_size})
    changed=[n for n,d in claim['input_sha256'].items() if sha(ROOT/n)!=d];assert not changed
    result={'status':probe['status'],'trainable_parameters':probe['capacity']['trainable_parameters'],
            'parameter_tensors_with_finite_nonzero_gradient':probe['capacity']['parameter_tensors'],'checks':probe['checks'],
            'native_first':native,'counts':probe['counts'],'completed_main_episodes':probe['completed_main_episodes'],
            'actual_probe_calls':probe['actual_probe_calls'],'fixture_calls_separately_counted':7,'total_environment_calls':probe['actual_probe_calls']+7,
            'unique_actual_probe_facts':len(events),'repeated_arm_trials':probe['repeated_arm_trials'],'arms_with_repeated_trials':repeated,
            'arms_with_both_success_and_failure':mixed,'paired_baseline_candidate_sessions':probe['comparison_examples'],
            'adoptions_with_no_fresh_baseline_trial':sum(not d['counts'][0] for d in adoptions),
            'adoptions_with_fresh_baseline_trial':sum(bool(d['counts'][0]) for d in adoptions),
            'main_policy_max_deviation_uniform':max(abs(v-1/len(p)) for p in policies for v in p),
            'main_policy_mean_normalized_entropy':sum(-sum(v*math.log(v) for v in p)/math.log(len(p)) for p in policies)/len(policies),
            'families':families,'optimizer_steps':0,'checkpoint_readback':restored,'checkpoint_readback_model_forwards':0,
            'post_summary_environment_calls':0,'input_pins_unchanged':len(claim['input_sha256']),
            'stored_audit_status':audit['status'],'jsonl_records':audit['jsonl_records'],
            'actual_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'warning':'One scalar-report conversion of requires_grad tensor in symmetry check; no optimizer or modified evidence; original stderr retained.',
            'source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src/feedback_program_v221').glob('*.py')},
            'evidence_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in (CAP/'probe_summary.json',CAP/'stored_audit.json',CAP/'exit.json',CAP/'events.jsonl',HERE/'contract.json')},
            'interpretation':'Untrained structure and complete practice evidence. Adopting, repeating and comparing are not themselves learning improvements.'}
    with (HERE/'result_summary.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,ensure_ascii=False,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','evidence_sha256','checkpoint_readback','families')},indent=2))


if __name__=='__main__':main()
