from dataclasses import asdict
from pathlib import Path
import hashlib,json,math,random,sys,time

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v220 import LearnableFeedbackNet,PracticeAgent
from feedback_program_v220.runtime import model_fingerprint
from checks import run_checks


class ProbeEnvironment:
    """A new actual vector transition per call; stochastic outcomes are not cached."""
    def __init__(self,family,seed,record):
        self.family=family;self.rng=random.Random(seed);self.calls=0;self.record=record

    def task(self,index):
        observation=tuple(self.rng.uniform(-1,1) for _ in range(16));goal=(1.,0.,0.,0.,0.,0.,0.,0.)
        count=(2,3,5)[index%3]
        actions=tuple(tuple(float(i==j) for j in range(8)) for i in range(count))
        def execute(action):
            self.calls+=1
            direction=-1 if self.family=='changed' and index>=8 else 1
            logit=direction*(1.3*observation[action]+.5*observation[(action+5)%16])-.25*action
            probability=1/(1+math.exp(-logit))
            if self.family=='noisy':probability=.5+.25*(probability-.5)
            success=self.rng.random()<probability
            next_observation=tuple(.7*x+.2*actions[action][i%8]+self.rng.gauss(0,.05) for i,x in enumerate(observation))
            feedback=[float(success),float(not success),next_observation[0],next_observation[1],1.,observation[0],float(action),next_observation[-1]]
            mask=tuple(not(self.family=='missing' and i in (2,3,5,7)) for i in range(8))
            feedback=tuple(x if observed else 0. for x,observed in zip(feedback,mask))
            result={'next_observation':next_observation,'feedback':feedback,'feedback_mask':mask,'goal_met':success,'terminal':True,'cost':1.}
            self.record({'kind':'external_execution','call':self.calls,'task_index':index,'observation':observation,'goal':goal,
                         'actions':actions,'action_index':action,'result':result})
            return result
        return observation,goal,actions,execute


def main():
    contract=json.loads((HERE/'contract.json').read_text());torch.set_num_threads(contract['torch_threads'])
    capture=HERE/'capture';started=time.perf_counter();summaries=[]
    with (capture/'events.jsonl').open('x',encoding='utf-8',buffering=1) as stream:
        def record(data):stream.write(json.dumps(data,sort_keys=True,allow_nan=False)+'\n')
        checks=run_checks(record)
        (capture/'checks.json').write_text(json.dumps(checks,indent=2,allow_nan=False),encoding='utf-8')
        for seed in contract['model_seeds']:
            for family_index,family in enumerate(contract['families']):
                torch.manual_seed(seed);model=LearnableFeedbackNet().eval();before=model_fingerprint(model)
                if family_index==0:
                    torch.save({'state_dict':model.state_dict(),'config':asdict(model.config),'schema':asdict(model.schema),
                                'status':'UNTRAINED_INITIALIZATION','seed':seed},capture/f'untrained_seed_{seed}.pt')
                run_id=f'{family}/seed{seed}';agent=PracticeAgent(model,run_id,random.Random(100000+seed))
                def run_record(d):record({'run_id':run_id,**d})
                env=ProbeEnvironment(family,50000+seed*17+family_index,run_record)
                run_record({'kind':'run_start','model_id':before,'seed':seed,'family':family,'config':asdict(model.config),'schema':asdict(model.schema)})
                event_cursor=0;decision_cursor=0;successes=0;trials_success=0;run_time=time.perf_counter()
                for index in range(contract['main_episodes_per_run']):
                    observation,goal,actions,execute=env.task(index)
                    event=agent.execute(observation,goal,actions,execute)
                    successes+=int(event.goal_met)
                    trial=agent.reflect(event,execute,contract['trial_budget_per_run']-agent.counters['trials'])
                    if trial is not None:trials_success+=int(trial.goal_met)
                    for e in agent.bank.events[event_cursor:]:run_record({'kind':'event','event':asdict(e)})
                    event_cursor=len(agent.bank.events)
                    for d in agent.decisions[decision_cursor:]:run_record({'kind':'decision','decision':d})
                    decision_cursor=len(agent.decisions)
                imagined=agent.imagine(observation,goal,actions,0)
                run_record({'kind':'imagined','transition':asdict(imagined)})
                for candidate in agent.candidates.values():run_record({'kind':'candidate','candidate':asdict(candidate),'digest':candidate.digest})
                for receipt in agent.receipts.values():run_record({'kind':'receipt','receipt':asdict(receipt)})
                replay_count=len(agent.bank.replay(list(agent.bank.index)))
                after=model_fingerprint(model);assert before==after
                assert len(agent.bank.events)==env.calls==agent.counters['tasks']+agent.counters['trials']
                assert agent.counters['reflections']==contract['main_episodes_per_run']-successes
                bank_text=agent.bank.to_json()
                bank_path=capture/f'memory_{family}_seed{seed}.json';bank_path.write_text(bank_text,encoding='utf-8')
                result={'run_id':run_id,'seed':seed,'family':family,'counters':agent.counters,'main_successes':successes,
                        'trial_successes':trials_success,'actual_external_calls':env.calls,'memory_nodes':len(agent.bank.events),
                        'replay_examples':replay_count,'model_before':before,'model_after':after,'optimizer_steps':0,
                        'memory_sha256':hashlib.sha256(bank_text.encode()).hexdigest(),'wall_seconds':time.perf_counter()-run_time}
                run_record({'kind':'run_complete',**result});summaries.append(result)
        report={'status':'COMPLETED_UNTRAINED_ARCHITECTURE_PROBE','structural_checks':len(checks),
                'parameters':checks['parameterized_capacity'],'runs':summaries,'main_episodes':sum(s['counters']['tasks'] for s in summaries),
                'actual_trial_episodes':sum(s['counters']['trials'] for s in summaries),'reflections':sum(s['counters']['reflections'] for s in summaries),
                'adoptions':sum(s['counters']['adoptions'] for s in summaries),'memory_nodes':sum(s['memory_nodes'] for s in summaries),
                'probe_environment_calls':sum(s['actual_external_calls'] for s in summaries),'fixture_environment_calls':3,
                'optimizer_steps':0,'wall_seconds':time.perf_counter()-started,'torch_version':torch.__version__}
        (capture/'probe_summary.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('parameters','runs')},indent=2))


if __name__=='__main__':main()
