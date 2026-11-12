from dataclasses import asdict
from pathlib import Path
import hashlib,json,random,sys,time
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v223 import ObservableFeedbackNet,PracticeAgent,FeedbackLayout,View
from feedback_program_v223.runtime import model_identity
from checks import run_checks


def layout():
    return FeedbackLayout(('novel_measurement_0','novel_measurement_1'),(
        View((('goal_met',0,1.),)),View((('next',0,1.),)),View((('next',0,1.),('observation',0,-1.))),
        View((),1.),View((('action_index',0,1.),)),View((('terminal',0,1.),)),
        View((('innovation',0,1.),)),View((('innovation',1,1.),))))


class Environment:
    def __init__(self,condition,seed,spec,record):
        self.condition=condition;self.rng=random.Random(seed);self.layout=spec;self.record=record;self.calls=0
    def initial(self):return tuple(self.rng.uniform(-.6,.6) for _ in range(16))
    def executor(self,observation,goal,actions,episode,step,role):
        def execute(action):
            self.calls+=1;x=observation;a=actions[action]
            nxt=[.75*v+.1*a[i%8]+self.rng.gauss(0,.1) for i,v in enumerate(x)]
            nxt[0]=.7*x[0]+.25*a[0]-.15*a[1]+.2*x[2+action]+self.rng.gauss(0,.35)
            u=(nxt[0]+self.rng.gauss(0,.25),.5*nxt[0]+nxt[1]+self.rng.gauss(0,.25))
            if self.condition=='external_missing':mask=tuple(self.rng.random()<.6 for _ in range(2))
            else:mask=(self.rng.random()<(.8 if u[0]>.0 else .2),self.rng.random()<(.8 if u[1]<.1 else .2))
            terminal=step==2;met=terminal and nxt[0]>.15
            raw=self.layout.render(nxt,u,float(met),float(terminal),x,a,action);visible=self.layout.visible_views(mask)
            feedback=tuple(v if m else 0. for v,m in zip(raw,visible))
            result={'next_observation':tuple(nxt),'feedback':feedback,'feedback_mask':visible,'goal_met':met,'terminal':terminal,'cost':1.}
            self.record({'kind':'external_execution','call':self.calls,'episode_index':episode,'step':step,'role':role,'observation':observation,
                         'goal':goal,'actions':actions,'action_index':action,'result':result})
            return result
        return execute


def save(p,value):
    with p.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,allow_nan=False)
def main():
    contract=json.loads((HERE/'contract.json').read_text());torch.set_num_threads(1);cap=HERE/'capture';start=time.perf_counter();runs=[]
    with (cap/'events.jsonl').open('x',encoding='utf-8',buffering=1) as f:
        def record(row):f.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
        for seed in contract['model_seeds']:
            for ci,condition in enumerate(contract['conditions']):
                torch.manual_seed(seed);model=ObservableFeedbackNet(layout()).eval();before=model_identity(model);rid=f'{condition}/seed{seed}'
                if ci==0:torch.save({'state_dict':model.state_dict(),'schema':asdict(model.schema),'config':asdict(model.config),'layout':model.layout.to_dict(),
                                    'seed':seed,'model_id':before,'class':'feedback_program_v223.ObservableFeedbackNet','status':'UNTRAINED_INITIALIZATION'},cap/f'untrained_seed_{seed}.pt')
                def rr(row):record({'run_id':rid,**row})
                agent=PracticeAgent(model,rid,random.Random(91000+seed),thought_depth=3)
                env=Environment(condition,80000+seed*13+ci,model.layout,rr);ec=dc=tc=0;successes=0
                rr({'kind':'run_start','model_id':before,'seed':seed,'condition':condition,'schema':asdict(model.schema),'config':asdict(model.config),'layout':model.layout.to_dict()})
                for episode in range(3):
                    observation=env.initial();goal=(1.,0.,0.,0.,0.,0.,0.,0.);previous=None
                    actions=tuple(tuple(float(i==j) for j in range(8)) for i in range((2,3,5)[episode]))
                    for step in range(3):
                        execute=env.executor(observation,goal,actions,episode,step,'task')
                        event=agent.execute(observation,goal,actions,execute,f'{rid}/episode/{episode}',step,previous)
                        observation=event.next_observation;previous=event.id
                        if step<2:assert agent.reflect(event,execute,2) is None
                    successes+=int(event.goal_met)
                    session=agent.reflect(event,env.executor(event.observation,event.goal,event.actions,episode,2,'trial'),2)
                    if session is not None:rr({'kind':'session','session':agent.session_record(session)})
                    for e in agent.bank.events[ec:]:rr({'kind':'event','event':asdict(e)})
                    for dec in agent.decisions[dc:]:rr({'kind':'decision','decision':dec})
                    for t in agent.thoughts[tc:]:rr({'kind':'thought','thought':t})
                    ec=len(agent.bank.events);dc=len(agent.decisions);tc=len(agent.thoughts)
                assert before==model_identity(model) and env.calls==len(agent.bank.events)
                text=agent.bank.to_json();(cap/f'memory_{condition}_seed{seed}.json').write_text(text,encoding='utf-8')
                nodes=[n for t in agent.thoughts for n in t['nodes']]
                run={'run_id':rid,'condition':condition,'seed':seed,'counters':agent.counters,'main_episodes':3,'main_successes':successes,
                     'actual_environment_calls':env.calls,'memory_nodes':len(agent.bank.events),'thought_sessions':len(agent.thoughts),'imagined_nodes':len(nodes),
                     'imagined_hidden_innovation_slots':sum(not v for n in nodes for v in n['innovation_mask']),
                     'real_hidden_innovation_slots':sum(not v for e in agent.bank.events for v in model.layout.innovations(e)[1]),
                     'allocated_particle_rows':sum(t['allocated_particle_rows'] for t in agent.thoughts),
                     'model_before':before,'model_after':model_identity(model),'optimizer_steps':0,'memory_sha256':hashlib.sha256(text.encode()).hexdigest()}
                rr({'kind':'run_complete',**run});runs.append(run)
        checks=run_checks(agent,record);save(cap/'checks.json',checks);passed=all(v['passed'] for v in checks.values())
        counts={k:sum(r['counters'][k] for r in runs) for k in runs[0]['counters']}
        summary={'status':'UNTRAINED_PROVENANCE_VISIBILITY_CHECKED' if passed else 'DIRECTED_FAILURES_RETAINED','checks':len(checks),'checks_all_passed':passed,
                 'runs':runs,'counts':counts,'actual_environment_calls':sum(r['actual_environment_calls'] for r in runs),
                 'imagined_nodes':sum(r['imagined_nodes'] for r in runs),'imagined_hidden_innovation_slots':sum(r['imagined_hidden_innovation_slots'] for r in runs),
                 'real_hidden_innovation_slots':sum(r['real_hidden_innovation_slots'] for r in runs),'optimizer_steps':0,'actual_fixture_calls':0,
                 'wall_seconds':time.perf_counter()-start,'torch_version':torch.__version__}
        assert summary['actual_environment_calls']<=60
        save(cap/'summary.json',summary);print(json.dumps({k:v for k,v in summary.items() if k!='runs'},indent=2))
    return 0 if passed else 1
if __name__=='__main__':sys.exit(main())
