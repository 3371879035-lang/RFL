from dataclasses import asdict
from pathlib import Path
import hashlib,json,random,sys,time
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v221 import EvidenceMemoryNet,PracticeAgent
from feedback_program_v220.runtime import model_fingerprint
from checks import run_checks


class VectorEnvironment:
    """Observed three-step tasks; local trials execute the last decision anew."""
    def __init__(self,family,seed,record):
        self.family=family;self.rng=random.Random(seed);self.record=record;self.calls=0
    def initial(self):return tuple(self.rng.uniform(-.6,.6) for _ in range(16))
    def executor(self,observation,goal,actions,episode,step,role):
        def execute(action):
            self.calls+=1
            direction=-1 if self.family=='changed_noisy' and episode>=6 else 1
            x=observation;a=actions[action]
            following=[.75*v+.1*a[i%8]+self.rng.gauss(0,.08) for i,v in enumerate(x)]
            following[0]=.7*x[0]+direction*(.25*a[0]-.15*a[1]+.2*x[2+action])+self.rng.gauss(0,.35)
            terminal=step==2;met=terminal and following[0]>.15
            feedback=(float(met),following[0],following[0]-x[0],1.,float(action),float(terminal),following[1],following[-1])
            mask=(True,True,True,True,True,True,not(self.family=='changed_noisy' and episode>=6),True)
            feedback=tuple(v if m else 0. for v,m in zip(feedback,mask))
            result={'next_observation':tuple(following),'feedback':feedback,'feedback_mask':mask,'goal_met':met,'terminal':terminal,'cost':1.}
            self.record({'kind':'external_execution','call':self.calls,'episode_index':episode,'step':step,'role':role,
                         'observation':observation,'goal':goal,'actions':actions,'action_index':action,'result':result})
            return result
        return execute


def main():
    contract=json.loads((HERE/'contract.json').read_text());torch.set_num_threads(contract['torch_threads']);cap=HERE/'capture'
    start=time.perf_counter();runs=[]
    with (cap/'events.jsonl').open('x',encoding='utf-8',buffering=1) as stream:
        def record(row):stream.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
        checks=run_checks(record,contract['memory_profile_nodes'])
        (cap/'checks.json').write_text(json.dumps(checks,indent=2,allow_nan=False),encoding='utf-8')
        for seed in contract['model_seeds']:
            for family_index,family in enumerate(contract['families']):
                torch.manual_seed(seed);model=EvidenceMemoryNet().eval();before=model_fingerprint(model)
                if family_index==0:torch.save({'state_dict':model.state_dict(),'config':asdict(model.config),'schema':asdict(model.schema),
                                               'seed':seed,'status':'UNTRAINED_INITIALIZATION'},cap/f'untrained_seed_{seed}.pt')
                rid=f'{family}/seed{seed}'
                def run_record(row):record({'run_id':rid,**row})
                agent=PracticeAgent(model,rid,random.Random(70000+seed));environment=VectorEnvironment(family,40000+seed*13+family_index,run_record)
                run_record({'kind':'run_start','model_id':before,'seed':seed,'family':family,'config':asdict(model.config),'schema':asdict(model.schema)})
                ec=dc=0;successes=0;run_start=time.perf_counter();comparison_examples=0
                for episode in range(contract['episodes_per_run']):
                    observation=environment.initial();goal=(1.,0.,0.,0.,0.,0.,0.,0.);previous=None
                    action_count=(2,3,5)[episode%3]
                    actions=tuple(tuple(float(i==j) for j in range(8)) for i in range(action_count))
                    for step in range(contract['main_steps_per_episode']):
                        execute=environment.executor(observation,goal,actions,episode,step,'task')
                        event=agent.execute(observation,goal,actions,execute,f'{rid}/episode/{episode}',step,previous)
                        observation=event.next_observation;previous=event.id
                        if step<2:assert agent.reflect(event,execute,4) is None
                    successes+=int(event.goal_met)
                    trial_env=environment.executor(event.observation,event.goal,event.actions,episode,2,'trial')
                    session=agent.reflect(event,trial_env,contract['trials_per_terminal_failure_maximum'])
                    if session is not None:
                        run_record({'kind':'session','session':agent.session_record(session)})
                        baseline=[r for r in session.receipts if r.arm==0];candidate=[r for r in session.receipts if r.arm!=0]
                        if baseline and candidate:
                            example=agent.comparison_example(session,candidate[0].event_id,baseline[0].event_id)
                            run_record({'kind':'comparison_example','session_id':session.id,'input_history_ids':example['memory']['ids'],
                                        'input_evidence_ids':example['evidence']['ids'],'target_ids':[e.id for e in example['target_events']],
                                        'public_goal_difference':float(example['target_events'][0].goal_met)-float(example['target_events'][1].goal_met),
                                        'arm_a':example['arm_a'],'arm_b':example['arm_b']});comparison_examples+=1
                    for e in agent.bank.events[ec:]:run_record({'kind':'event','event':asdict(e)})
                    ec=len(agent.bank.events)
                    for d in agent.decisions[dc:]:run_record({'kind':'decision','decision':d})
                    dc=len(agent.decisions)
                imaginary=agent.imagine(event.observation,event.goal,event.actions,0)
                run_record({'kind':'imagined','transition':asdict(imaginary)})
                text=agent.bank.to_json();(cap/f'memory_{family}_seed{seed}.json').write_text(text,encoding='utf-8')
                after=model_fingerprint(model);assert before==after
                assert agent.counters['task_steps']==36 and agent.counters['failure_sessions']==12-successes
                assert environment.calls==len(agent.bank.events)==agent.counters['task_steps']+agent.counters['trial_steps']
                repetitions=sum(len(s.receipts)-len(set(r.arm for r in s.receipts)) for s in agent.sessions.values())
                result={'run_id':rid,'seed':seed,'family':family,'counters':agent.counters,'completed_main_episodes':12,'main_successes':successes,
                        'actual_environment_calls':environment.calls,'memory_nodes':len(agent.bank.events),'repeated_arm_trials':repetitions,
                        'comparison_examples':comparison_examples,'model_before':before,'model_after':after,'optimizer_steps':0,
                        'memory_sha256':hashlib.sha256(text.encode()).hexdigest(),'wall_seconds':time.perf_counter()-run_start}
                run_record({'kind':'run_complete',**result});runs.append(result)
        counts={k:sum(r['counters'][k] for r in runs) for k in runs[0]['counters']}
        report={'status':'COMPLETED_UNTRAINED_MEMORY_PRACTICE_PROBE','checks':len(checks),'capacity':checks['capacity_and_trainability'],
                'runs':runs,'counts':counts,'actual_probe_calls':sum(r['actual_environment_calls'] for r in runs),
                'fixture_calls':7,'completed_main_episodes':sum(r['completed_main_episodes'] for r in runs),
                'repeated_arm_trials':sum(r['repeated_arm_trials'] for r in runs),'comparison_examples':sum(r['comparison_examples'] for r in runs),
                'optimizer_steps':0,'wall_seconds':time.perf_counter()-start,'torch_version':torch.__version__}
        (cap/'probe_summary.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('capacity','runs')},indent=2))


if __name__=='__main__':main()
