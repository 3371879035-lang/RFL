from dataclasses import asdict
from pathlib import Path
import hashlib,json,random,sys,time
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v222 import RecurrentFeedbackNet,PracticeAgent
from feedback_program_v220.runtime import model_fingerprint
from checks import run_checks


class VectorEnvironment:
    """Small public vector task used only to check the new data/compute loop."""
    def __init__(self,family,seed,record):
        self.family=family;self.rng=random.Random(seed);self.record=record;self.calls=0
    def initial(self):return tuple(self.rng.uniform(-.6,.6) for _ in range(16))
    def executor(self,observation,goal,actions,episode,step,role):
        def execute(action):
            self.calls+=1;shift=self.family=='masked_shift' and episode>=2
            x=observation;a=actions[action];direction=-1 if shift else 1
            following=[.75*v+.1*a[i%8]+self.rng.gauss(0,.08) for i,v in enumerate(x)]
            following[0]=.7*x[0]+direction*(.25*a[0]-.15*a[1]+.2*x[2+action])+self.rng.gauss(0,.35)
            terminal=step==2;met=terminal and following[0]>.15
            feedback=(float(met),following[0],following[0]-x[0],1.,float(action),float(terminal),following[1],following[-1])
            mask=(True,True,True,True,True,True,not shift,True);feedback=tuple(v if m else 0. for v,m in zip(feedback,mask))
            result={'next_observation':tuple(following),'feedback':feedback,'feedback_mask':mask,'goal_met':met,'terminal':terminal,'cost':1.}
            self.record({'kind':'external_execution','call':self.calls,'episode_index':episode,'step':step,'role':role,
                         'observation':observation,'goal':goal,'actions':actions,'action_index':action,'result':result})
            return result
        return execute


def save(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,allow_nan=False)


def main():
    contract=json.loads((HERE/'contract.json').read_text());torch.set_num_threads(contract['torch_threads']);cap=HERE/'capture'
    start=time.perf_counter();runs=[]
    with (cap/'events.jsonl').open('x',encoding='utf-8',buffering=1) as stream:
        def record(row):stream.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
        for seed in contract['model_seeds']:
            for fi,family in enumerate(contract['families']):
                torch.manual_seed(seed);model=RecurrentFeedbackNet().eval();before=model_fingerprint(model)
                if fi==0:torch.save({'state_dict':model.state_dict(),'config':asdict(model.config),'schema':asdict(model.schema),
                                    'seed':seed,'status':'UNTRAINED_INITIALIZATION','class':'feedback_program_v222.RecurrentFeedbackNet'},cap/f'untrained_seed_{seed}.pt')
                rid=f'{family}/seed{seed}'
                def rr(row):record({'run_id':rid,**row})
                agent=PracticeAgent(model,rid,random.Random(80000+seed),thought_depth=contract['thought_depth'])
                environment=VectorEnvironment(family,60000+seed*13+fi,rr);successes=0;ec=dc=tc=0
                rr({'kind':'run_start','model_id':before,'seed':seed,'family':family,'config':asdict(model.config),'schema':asdict(model.schema)})
                for episode in range(contract['episodes_per_run']):
                    obs=environment.initial();goal=(1.,0.,0.,0.,0.,0.,0.,0.);previous=None
                    actions=tuple(tuple(float(i==j) for j in range(8)) for i in range((2,3,5)[episode%3]))
                    for step in range(contract['main_steps_per_episode']):
                        execute=environment.executor(obs,goal,actions,episode,step,'task')
                        event=agent.execute(obs,goal,actions,execute,f'{rid}/episode/{episode}',step,previous)
                        obs=event.next_observation;previous=event.id
                        if step<2:assert agent.reflect(event,execute,2) is None
                    successes+=int(event.goal_met)
                    trial_env=environment.executor(event.observation,event.goal,event.actions,episode,2,'trial')
                    session=agent.reflect(event,trial_env,contract['trials_per_terminal_failure_maximum'])
                    if session is not None:rr({'kind':'session','session':agent.session_record(session)})
                    for e in agent.bank.events[ec:]:rr({'kind':'event','event':asdict(e)})
                    for d in agent.decisions[dc:]:rr({'kind':'decision','decision':d})
                    for t in agent.thoughts[tc:]:rr({'kind':'thought','thought':t})
                    ec=len(agent.bank.events);dc=len(agent.decisions);tc=len(agent.thoughts)
                after=model_fingerprint(model);assert before==after
                assert environment.calls==len(agent.bank.events)==agent.counters['task_steps']+agent.counters['trial_steps']
                assert agent.counters['failure_sessions']==4-successes
                text=agent.bank.to_json();(cap/f'memory_{family}_seed{seed}.json').write_text(text,encoding='utf-8')
                run={'run_id':rid,'seed':seed,'family':family,'counters':agent.counters,'main_episodes':4,'main_successes':successes,
                     'actual_environment_calls':environment.calls,'memory_nodes':len(agent.bank.events),'thought_sessions':len(agent.thoughts),
                     'imagined_nodes':sum(len(t['nodes']) for t in agent.thoughts),'internal_kernel_batches':sum(t['kernel_batches'] for t in agent.thoughts),
                     'allocated_particle_rows':sum(t['allocated_particle_rows'] for t in agent.thoughts),
                     'maximum_reached_depth':max([max(t['depths']) for t in agent.thoughts]+[0]),
                     'zero_node_thoughts':sum(not t['nodes'] for t in agent.thoughts),'model_before':before,'model_after':after,
                     'optimizer_steps':0,'memory_sha256':hashlib.sha256(text.encode()).hexdigest()}
                rr({'kind':'run_complete',**run});runs.append(run)
        checks=run_checks(agent,record);save(cap/'checks.json',checks)
        counts={name:sum(r['counters'][name] for r in runs) for name in runs[0]['counters']}
        report={'status':'COMPLETED_UNTRAINED_RECURRENT_INTERFACE_PROBE','runs':runs,'counts':counts,'checks':len(checks),
                'actual_environment_calls':sum(r['actual_environment_calls'] for r in runs),'additional_actual_fixture_calls':0,
                'imagined_nodes':sum(r['imagined_nodes'] for r in runs),'thought_sessions':sum(r['thought_sessions'] for r in runs),
                'allocated_particle_rows':sum(r['allocated_particle_rows'] for r in runs),'optimizer_steps':0,
                'torch_version':torch.__version__,'wall_seconds':time.perf_counter()-start}
        assert report['actual_environment_calls']<=contract['actual_environment_calls_maximum']
        save(cap/'probe_summary.json',report);print(json.dumps({k:v for k,v in report.items() if k!='runs'},indent=2))


if __name__=='__main__':main()
