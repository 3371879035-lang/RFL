from dataclasses import asdict
from pathlib import Path
import json,random,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(HERE.parent))
import torch
from feedback_program_v221.consistent_network import ConsistentEvidenceMemoryNet,consistent_comparison
from feedback_program_v221 import PracticeAgent
from feedback_program_v221.losses import factual_nll,off_policy_loss,replay_distillation_loss,comparison_nll
from feedback_program_v220.runtime import model_fingerprint
from run import VectorEnvironment
from checks import make_bank,query


def cycle_error(means):
    return (means[:,:,:,None]+means[:,None,:,:]-means[:,:,None,:]).abs().max()


def main():
    cap=HERE/'capture';contract=json.loads((HERE/'contract.json').read_text());torch.set_num_threads(1);start=time.perf_counter();runs=[]
    with (cap/'events.jsonl').open('x',encoding='utf-8',buffering=1) as stream:
        def record(row):stream.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
        p=torch.tensor([[1.,2.,3.]],dtype=torch.float64);l=torch.tensor([[[1.,0.],[0.,1.],[-1.,1.]]],dtype=torch.float64)
        residual=torch.tensor([[.1,.2,.3]],dtype=torch.float64);m,v,c=consistent_comparison(p,l,residual)
        assert cycle_error(m)==0 and torch.equal(m,-m.transpose(-1,-2)) and torch.linalg.eigvalsh(c).min()>0
        diagonal=c.diagonal(dim1=-2,dim2=-1);direct=diagonal[:,:,None]+diagonal[:,None,:]-2*c
        assert torch.allclose(v,direct,atol=1e-12,rtol=0) and torch.equal(v.diagonal(dim1=-2,dim2=-1),torch.zeros(1,3,dtype=torch.float64))
        record({'kind':'check','name':'additive_mean_psd_covariance_and_difference_identity','passed':True,
                'cycle_error':0.,'covariance_min_eigenvalue':float(torch.linalg.eigvalsh(c).min()),'difference_formula_error':float((v-direct).abs().max())})

        torch.manual_seed(2211);model=ConsistentEvidenceMemoryNet().eval();original=model_fingerprint(model);bank=make_bank(6)
        output=query(model,bank);codes=torch.cat((model.base_code[None,None,:],model.propose(output)),1)
        evidence=bank.evidence([['fixture/0'],['fixture/1','fixture/4'],['fixture/2'],['fixture/3','fixture/5']])
        trial,state=model.trial_logits(output,codes,evidence,torch.tensor([[3.,1.]]));adopt,_=model.adoption_logits(output,codes,evidence)
        loss=factual_nll(output,torch.tensor([1]),torch.ones(1,16)*.2,torch.ones(1,8)*.3,torch.ones(1,8),torch.tensor([.4]))
        loss+=off_policy_loss(output['logits'],torch.tensor([1]),torch.tensor([1/3]),torch.tensor([.8]))
        other=query(model,bank,codes[:,2]);loss+=off_policy_loss(other['logits'],torch.tensor([0]),torch.tensor([1/3]),torch.tensor([.5]))
        loss+=off_policy_loss(trial,torch.tensor([2]),torch.tensor([.2]),torch.tensor([.6]))
        loss+=off_policy_loss(adopt,torch.tensor([1]),torch.tensor([.25]),torch.tensor([.9]))
        loss+=comparison_nll(state,1,0,torch.tensor([.7]))+replay_distillation_loss(output['logits'],torch.tensor([[.1,.3,.6]]))
        loss.backward();bad=[n for n,p in model.named_parameters() if p.grad is None or not torch.isfinite(p.grad).all() or p.grad.abs().sum()==0]
        assert not bad,bad
        assert float(cycle_error(state['contrast_mean']).detach())<1e-7 and torch.linalg.eigvalsh(state['comparison_covariance']).min()>0
        capacity=sum(p.numel() for p in model.parameters());tensors=len(list(model.parameters()))
        record({'kind':'check','name':'revised_head_full_gradient_paths','passed':True,'parameter_count':capacity,
                'finite_nonzero_gradient_tensors':tensors,'neural_cycle_error':float(cycle_error(state['contrast_mean']).detach()),'optimizer_steps':0})
        with torch.no_grad():normal=query(model,bank);coded=query(model,bank,torch.ones(1,model.config.width))
        for key in ('weights','feedback_mean','feedback_variance','next_mean','next_variance'):assert torch.equal(normal[key],coded[key])
        assert model_fingerprint(model)==original
        record({'kind':'check','name':'fixed_world_prediction_and_unmodified_weights','passed':True,'optimizer_steps':0})
        model.zero_grad(set_to_none=True)

        for seed in contract['model_seeds']:
            torch.manual_seed(seed);model=ConsistentEvidenceMemoryNet().eval();before=model_fingerprint(model)
            torch.save({'state_dict':model.state_dict(),'config':asdict(model.config),'schema':asdict(model.schema),'comparison_rank':model.comparison_rank,
                        'seed':seed,'status':'UNTRAINED_INITIALIZATION'},cap/f'untrained_seed_{seed}.pt')
            rid=f'consistent/seed{seed}'
            def run_record(row):record({'run_id':rid,**row})
            env=VectorEnvironment('stable_noisy',80000+seed,run_record);agent=PracticeAgent(model,rid,random.Random(90000+seed));ec=dc=0
            run_record({'kind':'run_start','model_id':before,'seed':seed});successes=0
            for episode in range(contract['episodes_per_seed']):
                observation=env.initial();goal=(1.,0.,0.,0.,0.,0.,0.,0.);previous=None
                action_count=(2,3,5)[episode%3];actions=tuple(tuple(float(i==j) for j in range(8)) for i in range(action_count))
                for step in range(3):
                    event=agent.execute(observation,goal,actions,env.executor(observation,goal,actions,episode,step,'task'),f'{rid}/episode{episode}',step,previous)
                    observation=event.next_observation;previous=event.id
                successes+=int(event.goal_met)
                session=agent.reflect(event,env.executor(event.observation,goal,actions,episode,2,'trial'),4)
                if session is not None:run_record({'kind':'session','session':agent.session_record(session)})
                for event in agent.bank.events[ec:]:run_record({'kind':'event','event':asdict(event)})
                ec=len(agent.bank.events)
                for decision in agent.decisions[dc:]:run_record({'kind':'decision','decision':decision})
                dc=len(agent.decisions)
            after=model_fingerprint(model);assert after==before and env.calls==len(agent.bank.events)
            text=agent.bank.to_json();(cap/f'memory_seed{seed}.json').write_text(text,encoding='utf-8')
            result={'run_id':rid,'seed':seed,'model_before':before,'model_after':after,'counts':agent.counters,'actual_calls':env.calls,
                    'main_episodes':4,'main_successes':successes,'optimizer_steps':0}
            run_record({'kind':'run_complete',**result});runs.append(result)
        result={'status':'COMPLETED_CONSISTENT_HEAD_LIMITED_PROBE','parameter_count':capacity,'parameter_tensors':tensors,'checks':3,
                'runs':runs,'counts':{k:sum(r['counts'][k] for r in runs) for k in runs[0]['counts']},
                'actual_environment_calls':sum(r['actual_calls'] for r in runs),'optimizer_steps':0,'wall_seconds':time.perf_counter()-start}
        (cap/'probe_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
