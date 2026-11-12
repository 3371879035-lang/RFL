"""Bind the preferred revision to stored evidence and reloadable initial tensors."""
from pathlib import Path
import hashlib,json,subprocess
import torch
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];REV=HERE/'consistency_revision/capture'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    first=json.loads((HERE/'result_summary.json').read_text());revision=json.loads((REV/'probe_summary.json').read_text())
    audit=json.loads((REV/'stored_audit.json').read_text());claim=json.loads((REV/'claim.json').read_text());native=json.loads((REV/'exit.json').read_text())
    assert not [n for n,d in claim['input_sha256'].items() if sha(ROOT/n)!=d]
    restored=[]
    for seed in (41,53):
        path=REV/f'untrained_seed_{seed}.pt';checkpoint=torch.load(path,map_location='cpu',weights_only=True);h=hashlib.sha256()
        for name,tensor in checkpoint['state_dict'].items():h.update(name.encode());h.update(tensor.cpu().contiguous().numpy().tobytes())
        assert {r['model_before'] for r in revision['runs'] if r['seed']==seed}=={h.hexdigest()}
        assert checkpoint['status']=='UNTRAINED_INITIALIZATION'
        restored.append({'seed':seed,'model_id':h.hexdigest(),'checkpoint_sha256':sha(path),'bytes':path.stat().st_size})
    worst=0.;matrices=0
    for row in map(json.loads,(HERE/'capture/events.jsonl').read_text().splitlines()):
        if row['kind']=='decision' and row['decision']['kind']=='adoption':
            m=row['decision']['contrast_mean'];matrices+=1
            worst=max(worst,max(abs(m[a][b]+m[b][c]-m[a][c]) for a in range(len(m)) for b in range(len(m)) for c in range(len(m))))
    result={'status':'COMPLETED_STRUCTURAL_ITERATION_WITH_PRESERVED_FIRST_VERSION_AND_TARGETED_CORRECTION',
            'preferred_class':'feedback_program_v221.consistent_network.ConsistentEvidenceMemoryNet',
            'preferred_trainable_parameters':revision['parameter_count'],'preferred_gradient_tensors':revision['parameter_tensors'],
            'first_version_checks':first['checks'],'targeted_revision_checks':revision['checks'],'optimizer_steps':0,
            'first_version_main_and_trial_calls':first['actual_probe_calls'],'revision_main_and_trial_calls':revision['actual_environment_calls'],
            'fixture_calls':7,'all_environment_calls_this_iteration':first['actual_probe_calls']+revision['actual_environment_calls']+7,
            'original_comparison_matrices':matrices,'original_maximum_cycle_residual':worst,
            'revised_actual_matrices':audit['actual_adoption_matrices'],'revised_maximum_cycle_residual':audit['maximum_cycle_residual'],
            'revision_first_exit':native,'checkpoint_readback':restored,'checkpoint_readback_forward_calls':0,
            'input_pin_count_verified_unchanged':len(claim['input_sha256']),
            'actual_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'artifact_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in (HERE/'RESULTS.md',HERE/'USAGE.md',REV/'probe_summary.json',REV/'stored_audit.json',ROOT/'src/feedback_program_v221/consistent_network.py')},
            'limits':'Untrained architecture. Long-memory readability is not memory skill; practice adoption is not proven improvement; no full DreamRSI/SLEEP or calibration claim.'}
    with (HERE/'delivery_summary.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k not in ('artifact_sha256','checkpoint_readback')},indent=2))


if __name__=='__main__':main()
