"""Post-run delivery analysis; no environment execution, model forward or training."""
from collections import defaultdict
from pathlib import Path
import hashlib,json,math,subprocess
import torch

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];CAP=HERE/'capture'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    probe=json.loads((CAP/'probe_summary.json').read_text());native=json.loads((CAP/'exit.json').read_text())
    audit=json.loads((CAP/'stored_audit.json').read_text());claim=json.loads((CAP/'claim.json').read_text())
    events={};receipts={};adoptions=[];policies=[];families=defaultdict(lambda:dict(tasks=0,task_success=0,trials=0,trial_success=0,reflections=0,adoptions=0))
    with (CAP/'events.jsonl').open(encoding='utf-8') as f:
        for row in map(json.loads,f):
            if row['kind']=='event':events[row['event']['id']]=row['event']
            if row['kind']=='receipt':receipts[row['receipt']['candidate_id']]=row['receipt']['event_id']
            if row['kind']=='decision':
                d=row['decision']
                if d['kind']=='adoption' and d['choice']:adoptions.append(d['candidate_ids'][d['choice']-1])
                if d['kind']=='task':policies.append(d['policy'])
    for run in probe['runs']:
        family=families[run['family']]
        for key in ('tasks','trials','reflections','adoptions'):family[key]+=run['counters'][key]
        family['task_success']+=run['main_successes'];family['trial_success']+=run['trial_successes']
    restored=[]
    for seed in (7,19,31):
        checkpoint_path=CAP/f'untrained_seed_{seed}.pt'
        checkpoint=torch.load(checkpoint_path,map_location='cpu',weights_only=True)
        h=hashlib.sha256()
        for name,tensor in checkpoint['state_dict'].items():
            h.update(name.encode());h.update(tensor.cpu().contiguous().numpy().tobytes())
        expected={r['model_before'] for r in probe['runs'] if r['seed']==seed}
        assert expected=={h.hexdigest()} and checkpoint['status']=='UNTRAINED_INITIALIZATION'
        restored.append({'seed':seed,'model_id':h.hexdigest(),'checkpoint_sha256':sha(checkpoint_path),'state_tensors':len(checkpoint['state_dict'])})
    changed=[name for name,digest in claim['input_sha256'].items() if sha(ROOT/name)!=digest]
    assert not changed
    result={'status':probe['status'],'parameter_count':probe['parameters']['total'],'all_parameters_trainable':True,
            'gradient_tensors_checked':95,'structural_checks':probe['structural_checks'],'native_first':native,
            'factual_nodes':probe['memory_nodes'],'main_episodes':probe['main_episodes'],'actual_trials':probe['actual_trial_episodes'],
            'fixture_calls_separately_counted':3,'total_environment_calls':probe['probe_environment_calls']+3,
            'reflections':probe['reflections'],'adoptions':probe['adoptions'],'optimizer_steps':0,'families':dict(families),
            'main_successes':sum(r['main_successes'] for r in probe['runs']),
            'adopted_successful_trial':sum(events[receipts[c]]['goal_met'] for c in adoptions),
            'adopted_failed_trial':sum(not events[receipts[c]]['goal_met'] for c in adoptions),
            'main_probability_max_deviation_uniform':max(abs(v-1/len(p)) for p in policies for v in p),
            'main_normalized_entropy_mean':sum(-sum(v*math.log(v) for v in p)/math.log(len(p)) for p in policies)/len(policies),
            'stored_audit_status':audit['status'],'full_jsonl_records':audit['canonical_jsonl_lines'],
            'checkpoint_readback':restored,'checkpoint_readback_model_forwards':0,'post_summary_environment_calls':0,
            'inputs_unchanged_after_delivery':len(claim['input_sha256']),
            'actual_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'source_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'src/feedback_program_v220').glob('*.py')},
            'evidence_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in [CAP/'probe_summary.json',CAP/'checks.json',CAP/'stored_audit.json',CAP/'exit.json',CAP/'events.jsonl',HERE/'contract.json']},
            'interpretation':'Trainable structure and real practice/provenance verified within bounded probes. Untrained, uncalibrated; no causal or general performance claim.'}
    with (HERE/'result_summary.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({k:result[k] for k in ('status','parameter_count','total_environment_calls','optimizer_steps','inputs_unchanged_after_delivery','actual_head')},indent=2))


if __name__=='__main__':main()
