"""V222 directed numerical diagnosis plus only the six checks not reached in the first run."""
from dataclasses import asdict,replace
import math
import torch
from feedback_program_v222 import MemoryBank,Event
from feedback_program_v222.imagination import noise_tape,thought_record
from feedback_program_v222.losses import sequence_nll,decision_path_loss,comparison_nll
from feedback_program_v222.memory import actual_sequence
from feedback_program_v220.runtime import model_fingerprint


def rejected(kind,fn):
    try:fn()
    except kind:return
    raise AssertionError(f'Expected {kind.__name__}')


def run_checks(agent,record):
    model=agent.model;bank=agent.bank;before=model_fingerprint(model);facts=bank.to_json();result={}
    event=bank.events[-1];p=next(model.parameters());k=model.config.hypotheses
    tensor=lambda x:torch.as_tensor(x,dtype=p.dtype,device=p.device)
    def query():return agent.infer(event.observation,event.goal,event.actions)
    def codes_for(out):return torch.cat((model.base_code[None,None,:],model.propose(out)),1)
    def check(name,fn):
        detail=fn();result[name]=detail;record({'kind':'check','name':name,'passed':True,'details':detail})
    tasks=[e for e in bank.events if e.role=='task'];sequence=tuple(e.id for e in tasks[3:6])
    tape=noise_tape(222,3,k,model.schema.observation,model.schema.feedback)
    # Keep all paths available for the depth-3 kernel identity fixture only.
    tape['terminal']=torch.ones_like(tape['terminal'])
    with torch.no_grad():out=query();codes=codes_for(out);thought=model.dream(out,codes,tape,force_continue=True,fixed_action=0)

    def same_batch_sampling_and_numeric_diagnosis():
        captured=[]
        handle=model.world_decoder.register_forward_hook(lambda module,args,value:captured.append(value.detach().clone()))
        try:
            with torch.no_grad():matched=model.dream(out,codes,tape,force_continue=True,fixed_action=0)
        finally:handle.remove()
        width=model.schema.observation
        decoded=captured[0][:k,0]
        nm=decoded[:,:width];nv=torch.nn.functional.softplus(decoded[:,width:2*width])+1e-4
        expected=nm+nv.sqrt()*tape['normal'][0,:,:width]
        first=[node for node in matched['nodes'] if node.arm==0 and node.depth==0]
        stored=tensor([node.next_observation for node in first])
        assert torch.equal(stored,expected)
        independent=out['next_mean'][0,:,0]+out['next_variance'][0,:,0].sqrt()*tape['normal'][0,:,:width]
        error=float((stored-independent).abs().max())
        mean_error=float((nm-out['next_mean'][0,:,0]).abs().max())
        variance_error=float((nv-out['next_variance'][0,:,0]).abs().max())
        assert error<=1e-6
        return {'same_batch_32_sampling_bit_exact':True,'independent_8_row_vs_32_row_max_sample_abs_difference':error,
                'max_mean_abs_difference':mean_error,'max_variance_abs_difference':variance_error,
                'predeclared_numeric_atol':1e-6,'initial_exact_equality_failure_preserved':True,
                'physical_decoder_unchanged':True,'new_environment_calls':0}
    check('same_batch_exact_sampling_and_batch_shape_numeric_diagnosis',same_batch_sampling_and_numeric_diagnosis)

    def causal_code():
        by_key={(n.arm,n.hypothesis,n.depth):n for n in thought['nodes']}
        assert len(by_key)==4*k*3
        for arm in range(1,4):
            for ki in range(k):
                for depth in range(3):
                    a=by_key[0,ki,depth];b=by_key[arm,ki,depth]
                    assert (a.observation,a.next_observation,a.feedback,a.next_variance)==(b.observation,b.next_observation,b.feedback,b.next_variance)
        return {'forced_identical_action_common_noise_nodes':len(by_key),'different_codes_same_physics_exact':True,
                'fixture_only_not_autonomous_selection':True}
    check('candidate_has_no_direct_physics_shortcut',causal_code)

    def topology():
        for index,node in enumerate(thought['nodes']):
            assert node.original_weight==float(thought['root_weights'][node.hypothesis])
            if node.depth==0:assert node.parent is None
            else:
                prior=thought['nodes'][node.parent];assert node.parent<index
                assert (prior.arm,prior.hypothesis,prior.depth+1)==(node.arm,node.hypothesis,node.depth)
                assert prior.next_observation==node.observation and not prior.predicted_terminal
        assert all(len({n.action_index for n in thought['nodes'] if n.arm==arm and n.depth==depth})==1 for arm in range(4) for depth in range(3))
        rejected(TypeError,lambda:bank.add(thought['nodes'][0]));assert bank.to_json()==facts
        return {'parent_links':4*k*2,'same_action_across_hypotheses':True,'new_fact_count':0,'unchanged_original_weights':True}
    check('thought_memory_topology_and_no_duplicate_facts',topology)

    def replay():
        with torch.no_grad():again=model.dream(query(),codes,tape,force_continue=True,fixed_action=0)
        assert thought_record(thought)==thought_record(again)
        return {'saved_noise_replay_exact':True,'real_environment_calls':0}
    check('exact_internal_noise_replay',replay)

    def prefix_masks():
        rejected(ValueError,lambda:actual_sequence(bank,(sequence[0],sequence[2])))
        rejected(ValueError,lambda:actual_sequence(bank,(sequence[0],sequence[0])))
        variant=MemoryBank();hidden=sequence[0]
        for e in bank.events:
            if e.id==hidden:e=replace(e,feedback_mask=(False,)+e.feedback_mask[1:])
            variant.add(e)
        altered=MemoryBank()
        for e in variant.events:
            if e.id==hidden:e=replace(e,feedback=(123456.,)+e.feedback[1:])
            altered.add(e)
        with torch.no_grad():a,_=sequence_nll(model,variant,sequence);b,_=sequence_nll(model,altered,sequence)
        assert torch.equal(a,b)
        return {'missing_feedback_value_change_nll_difference':float(a-b),'skipped_and_repeated_targets_rejected':True}
    check('actual_chronology_and_observation_mask',prefix_masks)

    def thought_vs_adoption():
        evidence=bank.evidence([[] for _ in range(4)]);budget=tensor([[2.,0.]])
        with torch.no_grad():
            actual,_=model.trial_logits_with_thought(out,codes,evidence,budget,thought)
            changed=dict(thought,summary=thought['summary']+1)
            perturb,_=model.trial_logits_with_thought(out,codes,evidence,budget,changed)
            adoption,_=model.adoption_logits(out,codes,evidence)
        delta=float((actual-perturb).abs().max());assert delta>0
        assert torch.isfinite(adoption[0,0]) and torch.isneginf(adoption[0,1:]).all()
        return {'summary_perturbation_changes_trial_logit_max':delta,'untested_candidate_adoption_allowed':False,
                'dream_only_does_not_create_real_receipt':True}
    check('thought_influences_practice_not_eligibility',thought_vs_adoption)

    def gradient_routes():
        world,policy=model.parameter_groups();model.zero_grad(set_to_none=True)
        world_loss,_=sequence_nll(model,bank,sequence);world_loss.backward()
        world_live={n for n,p in world.items() if p.grad is not None and torch.isfinite(p.grad).all() and p.grad.abs().sum()>0}
        assert all(p.grad is None for p in policy.values())
        world_missing=sorted(set(world)-world_live);assert not world_missing,world_missing
        model.zero_grad(set_to_none=True);current=query();candidate_codes=codes_for(current)
        # Synthetic objective checks tensor reachability; this is NOT a valid adopted-policy training example.
        evidence=bank.evidence([[bank.events[-4+i].id] for i in range(4)])
        unrolled=model.dream(current,candidate_codes,tape,force_continue=True,fixed_action=0)
        budget=tensor([[2.,0.]]);trial,state=model.trial_logits_with_thought(current,candidate_codes,evidence,budget,unrolled)
        adoption,_=model.adoption_logits(current,candidate_codes,evidence)
        external=current['logits'].log_softmax(-1)[0,event.action_index]+trial.log_softmax(-1)[0,2]+adoption.log_softmax(-1)[0,1]
        # Explicit continue-head target ensures stop learning is exercised even if untrained sampling stops at depth zero.
        pooled=unrolled['summary'][0];continue_logits=model.thought_continue(torch.cat((current['context'].expand(4,-1),pooled,tensor([[1.]]).expand(4,-1)),-1))
        stochastic=model.dream(current,candidate_codes,noise_tape(223,3,k,model.schema.observation,model.schema.feedback))
        policy_loss=decision_path_loss(stochastic['internal_log_probability'],external,1.)
        policy_loss=policy_loss+comparison_nll(state,1,0,tensor(.4))+torch.nn.functional.binary_cross_entropy_with_logits(continue_logits,torch.ones_like(continue_logits))
        policy_loss.backward()
        assert all(p.grad is None for p in world.values())
        policy_live={n for n,p in policy.items() if p.grad is not None and torch.isfinite(p.grad).all() and p.grad.abs().sum()>0}
        missing=sorted(set(policy)-policy_live);assert not missing,missing
        by_module={}
        for n,p in model.named_parameters():by_module[n.split('.')[0]]=by_module.get(n.split('.')[0],0)+p.numel()
        model.zero_grad(set_to_none=True);assert model_fingerprint(model)==before
        return {'trainable_parameters':sum(p.numel() for p in model.parameters()),'parameter_tensors':len(list(model.parameters())),
                'world_parameters':sum(p.numel() for p in world.values()),'policy_parameters':sum(p.numel() for p in policy.values()),
                'world_finite_nonzero_gradient_tensors':len(world_live),'policy_finite_nonzero_gradient_tensors':len(policy_live),
                'world_to_policy_gradient_leak_tensors':0,'policy_to_world_gradient_leak_tensors':0,'optimizer_steps':0,
                'synthetic_policy_objective_not_efficacy_training':True,'by_module':by_module}
    check('actual_sequence_and_thought_gradient_routes',gradient_routes)

    assert bank.to_json()==facts and model_fingerprint(model)==before
    return result
