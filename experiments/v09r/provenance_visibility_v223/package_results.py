"""Package actual stored results without importing a learner or running an environment."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];CAP=HERE/'capture'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)
def main():
    summary=json.loads((CAP/'summary.json').read_text());checks=json.loads((CAP/'checks.json').read_text())
    audit=json.loads((CAP/'stored_audit.json').read_text());exit_record=json.loads((CAP/'exit.json').read_text())
    assert summary['checks_all_passed'] and exit_record['first_run_exit']==exit_record['audit_exit']==0
    result={'version':'V223','status':'CANONICAL_FACT_AND_VISIBILITY_ARCHITECTURE_CHECKED_UNTRAINED',
            'utc':datetime.now(timezone.utc).isoformat(),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'preferred_class':'feedback_program_v223.ObservableFeedbackNet','counts':summary['counts'],
            'actual_environment_calls':summary['actual_environment_calls'],'actual_fixture_calls':0,
            'main_episodes':sum(r['main_episodes'] for r in summary['runs']),'main_successes_untrained_not_comparative':sum(r['main_successes'] for r in summary['runs']),
            'thought_sessions':sum(r['thought_sessions'] for r in summary['runs']),'imagined_nodes':summary['imagined_nodes'],
            'imagined_hidden_innovation_slots':summary['imagined_hidden_innovation_slots'],'real_hidden_innovation_slots':summary['real_hidden_innovation_slots'],
            'allocated_particle_rows':sum(r['allocated_particle_rows'] for r in summary['runs']),'actual_prefix_refreshes':audit['actual_prefix_refreshes'],
            'checks':checks,'exit':exit_record,'stored_jsonl_records':audit['jsonl_records'],'optimizer_steps':0,
            'no_training_or_calibration_or_performance_claim':True,'old_experiments_rerun':False,
            'untrained_checkpoints':[{'path':str(CAP/f'untrained_seed_{seed}.pt'),'sha256':sha(CAP/f'untrained_seed_{seed}.pt'),'status':'UNTRAINED_INITIALIZATION'} for seed in (83,97)],
            'report':str(HERE/'RESULTS.md'),'usage':str(HERE/'USAGE.md'),'math':str(ROOT/'docs/feedback_math/provenance_visibility_v223/MATHEMATICAL_MODEL_V15.md')}
    save(HERE/'result_summary.json',result)
    old=json.loads((CAP/'claim.json').read_text())['input_sha256'];changed=[name for name,digest in old.items() if sha(ROOT/name)!=digest]
    assert not changed,changed;pins=dict(old)
    for folder in (HERE,ROOT/'src/feedback_program_v223',ROOT/'docs/feedback_math/provenance_visibility_v223'):
        for p in folder.rglob('*'):
            if p.is_file():pins[p.relative_to(ROOT).as_posix()]=sha(p)
    save(HERE/'source_binding.json',{'head':result['head'],'preserved_declared_inputs':len(old),'changed_previous_inputs':changed,
                                   'input_and_delivery_sha256':pins,'scope':'Declared old inputs and new delivery, not a full repository audit or science gate.'})
    print(json.dumps({'parameters':checks['learned_visibility_joint_outcome_and_policy_gradient_routes']['details']['trainable_parameters'],
                      'actual_calls':result['actual_environment_calls'],'imagined_nodes':result['imagined_nodes'],'checks':len(checks),
                      'optimizer_steps':0,'preserved_inputs':len(old),'changed_previous_inputs':changed},indent=2))
if __name__=='__main__':main()
