"""Package only stored evidence; imports no model, learner, or environment."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,data):
    with p.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False,allow_nan=False)
def main():
    original=HERE/'capture';directed=HERE/'numerical_completion/capture';completed=HERE/'remaining_checks/capture'
    audit=json.loads((completed/'stored_audit.json').read_text());remaining=json.loads((completed/'summary.json').read_text())
    rows=[json.loads(line) for line in (original/'events.jsonl').read_text().splitlines()]
    runs=[row for row in rows if row['kind']=='run_complete'];events=[row['event'] for row in rows if row['kind']=='event']
    early=[json.loads(line) for line in (directed/'checks.jsonl').read_text().splitlines()]
    redundancies={'feedback0_equals_goal_met':sum(e['feedback_mask'][0] and e['feedback'][0]==float(e['goal_met']) for e in events),
                  'feedback5_equals_terminal':sum(e['feedback_mask'][5] and e['feedback'][5]==float(e['terminal']) for e in events),
                  'feedback1_equals_next_observation0':sum(e['feedback_mask'][1] and e['feedback'][1]==e['next_observation'][0] for e in events),
                  'total_actual_events':len(events),'interpretation':'Repeated semantic views are not additional independent evidence; auxiliary losses require an explicit likelihood interpretation.'}
    summary={'version':'V222','status':'UNTRAINED_RECURRENT_ARCHITECTURE_IMPLEMENTED_AND_DIRECTED_CHECKED_WITH_FIRST_FAILURES_RETAINED',
             'utc':datetime.now(timezone.utc).isoformat(),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
             'preferred_class':'feedback_program_v222.RecurrentFeedbackNet','actual_counts':audit['counts'],
             'actual_environment_calls':audit['actual_environment_calls'],'additional_actual_fixture_calls':0,'main_episodes':16,
             'main_successes_untrained_not_comparative':sum(r['main_successes'] for r in runs),
             'thought_sessions':sum(r['thought_sessions'] for r in runs),'imagined_nodes':audit['imagined_nodes'],
             'allocated_particle_rows':sum(r['allocated_particle_rows'] for r in runs),'zero_node_thoughts':sum(r['zero_node_thoughts'] for r in runs),
             'updated_actual_prefixes':audit['updated_actual_prefixes'],'gradient_check':remaining['checks']['actual_sequence_and_thought_gradient_routes']['details'],
             'first_run_exit':json.loads((original/'exit.json').read_text()),'first_directed_exit':json.loads((directed/'exit.json').read_text()),
             'remaining_checks_exit':json.loads((completed/'exit.json').read_text()),'numerical_diagnosis':early[0]['details'],
             'same_row_code_intervention':remaining['checks']['candidate_code_causal_isolation_same_rows']['details'],
             'distinct_completed_math_network_checks':8,'stored_review_jsonl_records':audit['jsonl_records'],
             'semantic_redundancy_in_current_probe':redundancies,'optimizer_steps':0,'performance_or_calibration_claim':False,
             'old_experiments_rerun':False,'network_source_changed_after_first_native':False,
             'files':{'report':str(HERE/'RESULTS.md'),'usage':str(HERE/'USAGE.md'),
                      'mathematics':str(ROOT/'docs/feedback_math/recurrent_imagination_v222/MATHEMATICAL_MODEL_V14.md'),
                      'post_check_assumptions':str(ROOT/'docs/feedback_math/recurrent_imagination_v222/POST_CHECK_ASSUMPTIONS.md')},
             'untrained_checkpoints':[{ 'path':str(original/f'untrained_seed_{seed}.pt'),'sha256':sha(original/f'untrained_seed_{seed}.pt'),'status':'UNTRAINED_INITIALIZATION'} for seed in (61,73)]}
    save(HERE/'result_summary.json',summary)
    prior=json.loads((completed/'claim.json').read_text())['input_sha256']
    mismatches=[name for name,digest in prior.items() if sha(ROOT/name)!=digest];assert not mismatches,mismatches
    allpins=dict(prior)
    for directory in (HERE,ROOT/'src/feedback_program_v222',ROOT/'docs/feedback_math/recurrent_imagination_v222'):
        for p in directory.rglob('*'):
            if p.is_file():allpins[p.relative_to(ROOT).as_posix()]=sha(p)
    binding={'utc':datetime.now(timezone.utc).isoformat(),'head':summary['head'],'preserved_claim_inputs':len(prior),
             'preserved_declared_bytes':sum((ROOT/name).stat().st_size for name in prior),'changed_previous_inputs':mismatches,
             'input_and_delivery_sha256':allpins,'limits':'Declared inputs and this delivery only, not a full repository audit; no commit/staging or training.'}
    save(HERE/'source_binding.json',binding)
    print(json.dumps({'actual_calls':len(events),'imagined_nodes':summary['imagined_nodes'],'trainable_parameters':summary['gradient_check']['trainable_parameters'],
                      'completed_checks':8,'preserved_inputs':len(prior),'changed_inputs':mismatches,'semantic_redundancy':redundancies},indent=2))
if __name__=='__main__':main()
