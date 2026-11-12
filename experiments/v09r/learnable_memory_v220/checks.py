"""Structural probes, not learned-skill or scientific performance evidence."""
from dataclasses import replace
import math,random
import torch
from feedback_program_v220.memory import Event,MemoryBank,Schema
from feedback_program_v220.network import LearnableFeedbackNet,NetworkConfig,joint_moments
from feedback_program_v220.runtime import PracticeAgent,model_fingerprint
from feedback_program_v220.losses import factual_nll,off_policy_loss,replay_distillation_loss


def sample_event(i=0,previous=None,source='environment'):
    return Event(f'e{i}','episode',i,(.1*i,)*16,((0.,)*8,(1.,)*8),i%2,(.2,)*16,
                 (.3,)*8,(True,)*8,(.5,)*8,(.1,)*8,(True,)*8,.5,False,True,1.,source,previous_id=previous)


def query(model,bank,code=None):
    return model(torch.zeros(1,16),torch.ones(1,8),torch.tensor([[[0.]*8,[1.]*8]]),bank.view(),code)


def expect_error(kind,fn):
    try:fn()
    except kind:return
    raise AssertionError(f'Expected {kind.__name__}')


def run_checks(record):
    torch.manual_seed(220)
    model=LearnableFeedbackNet();model.eval();bank=MemoryBank()
    for i,source in enumerate(('environment','human','tool')):bank.add(sample_event(i,None if i==0 else f'e{i-1}',source))
    original=model_fingerprint(model);report={}

    def check(name,fn):
        result=fn();record({'kind':'check','name':name,'passed':True,'details':result});report[name]=result

    def parameters():
        counts={}
        for n,p in model.named_parameters():counts[n.split('.')[0]]=counts.get(n.split('.')[0],0)+p.numel()
        total=sum(counts.values());assert total>1_000_000 and all(p.requires_grad for p in model.parameters())
        return {'total':total,'trainable':total,'by_module':counts}
    check('parameterized_capacity',parameters)

    def covariance():
        w=torch.tensor([[.5,.5]],dtype=torch.float64);v=torch.full((1,2,2),.1,dtype=torch.float64)
        pos=joint_moments(w,torch.tensor([[[1.,1.],[-1.,-1.]]],dtype=torch.float64),v)
        neg=joint_moments(w,torch.tensor([[[1.,-1.],[-1.,1.]]],dtype=torch.float64),v)
        assert torch.allclose(pos['difference_variance'][0,0,1],torch.tensor(.2,dtype=torch.float64))
        assert torch.allclose(neg['difference_variance'][0,0,1],torch.tensor(4.2,dtype=torch.float64))
        assert torch.allclose(pos['total_covariance'].diagonal(dim1=-2,dim2=-1),neg['total_covariance'].diagonal(dim1=-2,dim2=-1))
        for x in (pos,neg):assert torch.linalg.eigvalsh(x['total_covariance']).min()>0 and x['difference_variance'].diagonal(dim1=-2,dim2=-1).abs().max()==0
        single=joint_moments(torch.ones(1,1),torch.tensor([[[1.,0.]]]),torch.tensor([[[.25,.25]]]))
        expected=.5*(1+math.erf(1.));assert abs(single['comparison_probability'][0,0,1].item()-expected)<1e-6
        return {'same_marginal_variances':[1.1,1.1],'positive_correlation_gap_variance':.2,'negative_correlation_gap_variance':4.2,
                'naive_marginal_sum':2.2,'comparison_diagonal':'0.5 tie convention, not strict self-comparison probability'}
    check('joint_action_uncertainty',covariance)

    def dimensions():
        small=LearnableFeedbackNet(Schema(5,3,2,4),NetworkConfig(48,3,1,4,2))
        for count in (1,3,7):
            out=small(torch.zeros(1,5),torch.zeros(1,4),torch.randn(1,count,3),MemoryBank(small.schema).view())
            assert out['policy'].shape==(1,count) and torch.isfinite(out['policy']).all()
        assert query(model,MemoryBank())['attention'].shape==(1,2,1)
        return {'alternative_schema':[5,3,2,4],'legal_action_counts':[1,3,7],'empty_memory_supported':True}
    check('variable_schema_actions_empty_memory',dimensions)

    def duplicate():
        count=len(bank.events)
        with torch.no_grad():before=query(model,bank)['policy'].clone()
        assert bank.add(bank.events[0]) is False and len(bank.events)==count
        with torch.no_grad():after=query(model,bank)['policy']
        assert torch.equal(before,after)
        expect_error(ValueError,lambda:bank.add(replace(bank.events[0],cost=2.)))
        separate=MemoryBank();separate.add(sample_event());separate.add(replace(sample_event(),id='independent',episode='independent'))
        assert len(separate.events)==2
        return {'identical_reimport_output_bitwise_equal':True,'different_real_ids_preserved':2}
    check('identity_not_replay_count',duplicate)

    def prefix():
        prefix,event=bank.training_example('e1');assert prefix['ids']==('e0',) and event.id=='e1'
        old=prefix['features'].clone();bank.add(sample_event(3,'e2'))
        assert torch.equal(old,bank.training_example('e1')[0]['features'])
        count=len(bank.events);bank.replay(['e1','e2']);bank.replay(['e1','e2']);assert len(bank.events)==count
        expect_error(ValueError,lambda:bank.replay(['e1','e1']))
        return {'target_excluded':True,'future_append_does_not_change_training_prefix':True,'repeated_epochs_new_facts':0}
    check('chronological_replay_without_future',prefix)

    def persistence():
        serialized=bank.to_json();restored=MemoryBank.from_json(serialized);assert serialized==restored.to_json()
        with torch.no_grad():assert torch.equal(query(model,bank)['logits'],query(model,restored)['logits'])
        supplied=[0.]*16;e=replace(sample_event(),observation=supplied);supplied[0]=99.;assert e.observation[0]==0.
        return {'raw_roundtrip_exact':True,'prediction_roundtrip_exact':True,'external_list_alias_not_retained':True}
    check('raw_memory_restoration_and_immutability',persistence)

    def missing():
        a=MemoryBank();b=MemoryBank();a.add(replace(sample_event(),feedback=(0.,)*8));b.add(replace(sample_event(),feedback=(0.,)*8,feedback_mask=(False,)*8))
        assert not torch.equal(a.view()['features'],b.view()['features'])
        out=query(model,bank);out['feedback_mean'].retain_grad();mask=torch.tensor([[1.,0.,1.,0.,1.,0.,1.,0.]])
        loss=factual_nll(out,torch.tensor([0]),torch.ones(1,16),torch.ones(1,8),mask)
        model.zero_grad(set_to_none=True);loss.backward()
        grad=out['feedback_mean'].grad
        assert grad[:,:,:,1::2].abs().max()==0 and grad[:,:,:,::2].abs().sum()>0
        return {'zero_and_missing_inputs_distinct':True,'masked_feedback_target_gradient':0.}
    check('missing_is_not_zero_or_training_label',missing)

    def joint_likelihood():
        # Batch indexing and a single shared mixture sum across observed dimensions.
        b=2;k=2;a=3;o=1;f=2
        out={'weights':torch.tensor([[.3,.7],[.6,.4]],dtype=torch.float64),
             'next_mean':torch.arange(b*k*a*o,dtype=torch.float64).reshape(b,k,a,o)/5,
             'next_variance':torch.ones(b,k,a,o,dtype=torch.float64),
             'feedback_mean':torch.arange(b*k*a*f,dtype=torch.float64).reshape(b,k,a,f)/9,
             'feedback_variance':torch.ones(b,k,a,f,dtype=torch.float64)}
        chosen=torch.tensor([0,2]);nx=torch.tensor([[.2],[.8]],dtype=torch.float64);fb=torch.tensor([[.5,1.],[.3,.7]],dtype=torch.float64);mask=torch.tensor([[1.,0.],[1.,1.]],dtype=torch.float64)
        got=factual_nll(out,chosen,nx,fb,mask);expected=[]
        for row in range(b):
            terms=[]
            for component in range(k):
                j=int(chosen[row]);logp=-.5*(math.log(2*math.pi)+(nx[row]-out['next_mean'][row,component,j]).square()).sum()
                logp+=(-.5*(math.log(2*math.pi)+(fb[row]-out['feedback_mean'][row,component,j]).square())*mask[row]).sum()
                terms.append(out['weights'][row,component].log()+logp)
            expected.append(-torch.logsumexp(torch.stack(terms),0))
        assert torch.allclose(got,torch.stack(expected).mean(),rtol=0,atol=1e-12)
        return {'batch':2,'component_sum_after_joint_dimensions':True,'absolute_error':float(abs(got-torch.stack(expected).mean()))}
    check('proper_joint_mixture_nll',joint_likelihood)

    def conditional_confidence():
        # d L / d log(v) = (1 - error^2/v)/2 in the Gaussian one-component case.
        values=[]
        for error in (0.,2.):
            logvar=torch.tensor(0.,requires_grad=True);loss=.5*(logvar+error**2*torch.exp(-logvar));loss.backward();values.append(logvar.grad.item())
        assert values==[.5,-1.5]
        return {'small_error_logvariance_gradient':values[0],'large_error_logvariance_gradient':values[1],
                'gradient_descent_can_lower_or_raise_uncertainty':True,'empirical_calibration_established':False}
    check('bidirectional_variance_learning_direction',conditional_confidence)

    def code_boundary():
        with torch.no_grad():
            base=query(model,bank);changed=query(model,bank,torch.ones(1,model.config.width)*2)
        for key in ('weights','next_mean','next_variance','feedback_mean','feedback_variance','value_mean','value_variance'):
            assert torch.equal(base[key],changed[key])
        delta=float((base['policy']-changed['policy']).abs().max());assert delta>0
        return {'world_prediction_bitwise_unchanged':True,'actor_probability_max_change':delta}
    check('candidate_changes_actor_not_world',code_boundary)

    def gradients():
        model.zero_grad(set_to_none=True);out=query(model,bank);codes=model.propose(out)
        factual=factual_nll(out,torch.tensor([1]),torch.ones(1,16)*.2,torch.ones(1,8)*.3,torch.ones(1,8),torch.tensor([.4]))
        actor=off_policy_loss(out['logits'],torch.tensor([1]),torch.tensor([.5]),torch.tensor([1.]))
        policy_after=query(model,bank,codes[:,0])
        proposal=off_policy_loss(policy_after['logits'],torch.tensor([0]),torch.tensor([.5]),torch.tensor([.8]))
        trial_logits=model.trial_logits(out,codes,torch.tensor([[2.,1.]]))
        trial=off_policy_loss(trial_logits,torch.tensor([2]),torch.tensor([.25]),torch.tensor([.4]))
        summaries=torch.linspace(-.3,.7,model.config.candidates*(2*model.schema.feedback+3)).reshape(1,model.config.candidates,-1)
        adopt_logits=model.adoption_logits(out,codes,summaries,torch.ones(1,model.config.candidates,dtype=torch.bool))
        adopt=off_policy_loss(adopt_logits,torch.tensor([1]),torch.tensor([.25]),torch.tensor([.7]))
        replay=replay_distillation_loss(out['logits'],torch.tensor([[.2,.8]]))
        loss=factual+actor+proposal+trial+adopt+replay;loss.backward();norms={};bad=[]
        for name,p in model.named_parameters():
            if p.grad is None or not torch.isfinite(p.grad).all() or p.grad.abs().sum()==0:bad.append(name)
            if p.grad is not None:norms[name.split('.')[0]]=norms.get(name.split('.')[0],0.)+float(p.grad.square().sum())
        assert not bad,bad
        assert model_fingerprint(model)==original
        return {'loss':float(loss.detach()),'parameters_with_finite_nonzero_gradient':len(list(model.parameters())),
                'group_l2_norm':{k:math.sqrt(v) for k,v in norms.items()},'optimizer_steps':0,
                'synthetic_gradient_targets_not_learning_outcomes':True}
    check('all_named_parameter_tensors_receive_gradients',gradients)

    def practice_protocol():
        agent=PracticeAgent(model,'protocol_fixture',random.Random(37));calls=[]
        def env(action):
            calls.append(action)
            return {'next_observation':[.2]*16,'feedback':[0.]*8,'feedback_mask':[True]*8,'goal_met':False,'terminal':True,'cost':1.}
        event=agent.execute([0.]*16,[1.]*8,[[0.]*8,[1.]*8],env)
        _,proposed=agent.propose(event);c=proposed[0]
        expect_error(ValueError,lambda:agent.promote(c));assert len(calls)==1
        trial=agent.execute(event.observation,event.goal,event.actions,env,'trial',c)
        expect_error(ValueError,lambda:agent.promote(replace(c,code=tuple(x+.1 for x in c.code))))
        agent.promote(c);assert agent.current_candidate==c.id and len(calls)==2 and trial.role=='trial'
        assert not trial.goal_met  # Protocol does not hard-code "success means adopt".
        count=len(agent.bank.events);imagined=agent.imagine(event.observation,event.goal,event.actions,0)
        expect_error(TypeError,lambda:agent.bank.add(imagined));assert len(agent.bank.events)==count
        return {'fixture_external_calls':2,'fixture_forced_promotion_not_autonomous_selection':True,
                'untested_and_changed_candidates_rejected':True,'imagined_nodes_added':0}
    check('practice_required_and_imagination_separate',practice_protocol)

    def success_path():
        agent=PracticeAgent(model,'success_fixture',random.Random(1))
        def env(action):return {'next_observation':[0.]*16,'feedback':[1.]*8,'feedback_mask':[True]*8,'goal_met':True,'terminal':True,'cost':1.}
        event=agent.execute([0.]*16,[1.]*8,[[0.]*8,[1.]*8],env)
        result=agent.reflect(event,env,1);assert result is None and agent.counters['reflections']==0 and len(agent.bank.events)==1
        prefix,target=agent.bank.training_example(event.id);assert len(prefix['ids'])==0 and target.goal_met
        return {'fixture_external_calls':1,'reflections':0,'ordinary_replay_event_available':True}
    check('success_no_reflection_but_ordinary_learning_available',success_path)

    def evaluation():
        before=bank.to_json();state=model_fingerprint(model)
        with torch.no_grad():query(model,bank);query(model,bank)
        assert bank.to_json()==before and model_fingerprint(model)==state==original
        return {'evaluation_fact_writes':0,'parameter_updates':0}
    check('readonly_evaluation_and_frozen_parameters',evaluation)
    model.zero_grad(set_to_none=True)
    return report
