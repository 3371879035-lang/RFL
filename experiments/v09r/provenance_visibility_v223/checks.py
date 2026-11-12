from dataclasses import replace
import math,traceback
import torch
from feedback_program_v223 import ObservableFeedbackNet,MemoryBank,FeedbackLayout
from feedback_program_v223.runtime import model_identity
from feedback_program_v223.losses import sequence_nll,observed_gaussian_log_prob,decision_path_loss,comparison_nll
from feedback_program_v223.imagination import noise_tape


def rejected(kind,fn):
    try:fn()
    except kind:return
    raise AssertionError('Expected '+kind.__name__)


def run_checks(agent,record):
    model=agent.model;bank=agent.bank;before=model_identity(model);saved=bank.to_json();results={}
    event=bank.events[-1];p=next(model.parameters());k=model.config.hypotheses;o=model.schema.observation
    tensor=lambda x:torch.as_tensor(x,device=p.device,dtype=p.dtype)
    def query(m=model,b=bank):return m(tensor([event.observation]),tensor([event.goal]),tensor([event.actions]),b.view())
    def codes(out):return torch.cat((model.base_code[None,None,:],model.propose(out)),1)
    tasks=[e for e in bank.events if e.role=='task'];targets=tuple(e.id for e in tasks[3:6])
    def check(name,fn):
        try:results[name]={'passed':True,'details':fn()}
        except Exception:results[name]={'passed':False,'traceback':traceback.format_exc()}
        record({'kind':'check','name':name,**results[name]})

    alias_layout=FeedbackLayout(model.layout.primitive_ids,model.layout.views+(model.layout.views[0],model.layout.views[6],model.layout.views[6]))
    alias_schema=replace(model.schema,feedback=11);alias_bank=MemoryBank(alias_schema,alias_layout)
    for e in bank.events:
        extras=(0,6,6)
        alias_bank.add(replace(e,feedback=e.feedback+tuple(e.feedback[i] for i in extras),feedback_mask=e.feedback_mask+tuple(e.feedback_mask[i] for i in extras),
                              predicted_feedback=e.predicted_feedback+tuple(e.predicted_feedback[i] for i in extras),predicted_mask=e.predicted_mask+tuple(e.predicted_mask[i] for i in extras)))
    alias_model=ObservableFeedbackNet(alias_layout,alias_schema,model.config).eval();alias_model.load_state_dict(model.state_dict())

    def aliases():
        assert torch.equal(bank.view()['features'],alias_bank.view()['features'])
        with torch.no_grad():
            a=query();b=query(alias_model,alias_bank);la,_=sequence_nll(model,bank,targets);lb,_=sequence_nll(alias_model,alias_bank,targets)
            pa=model.propose(a);pb=alias_model.propose(b)
        assert torch.equal(la,lb) and torch.equal(a['policy'],b['policy']) and torch.equal(pa,pb)
        assert torch.equal(a['root_mean'],b['root_mean']) and len(bank.events)==len(alias_bank.events)
        assert model_identity(model)!=model_identity(alias_model)  # Same predictions, distinct explicit wire contract.
        return {'public_fields_before':8,'public_fields_after':11,'primitive_fields_both':2,'canonical_memory_exact':True,
                'sequence_loss_difference':float(la-lb),'policy_and_candidates_exact':True,'new_actual_events':0,
                'layout_bound_model_identity':True}
    check('duplicate_views_do_not_add_evidence_or_change_behavior',aliases)

    def provenance():
        first=bank.events[0];bad=replace(first,feedback=(first.feedback[0]+1,)+first.feedback[1:])
        rejected(ValueError,lambda:MemoryBank(model.schema,model.layout).add(bad))
        e=alias_bank.events[0];values=list(e.feedback);mask=list(e.feedback_mask)
        values[9]=1.;values[10]=2.;mask[9]=mask[10]=True
        rejected(ValueError,lambda:MemoryBank(alias_schema,alias_layout).add(replace(e,feedback=tuple(values),feedback_mask=tuple(mask))))
        independent=list(first.feedback);independent[6]=independent[7]=.25;m=list(first.feedback_mask);m[6]=m[7]=True
        distinct=MemoryBank(model.schema,model.layout);distinct.add(replace(first,feedback=tuple(independent),feedback_mask=tuple(m)))
        u,observed=model.layout.innovations(distinct.events[0]);assert u==(.25,.25) and observed==(True,True)
        assert bank.add(first) is False and bank.to_json()==saved
        return {'false_relation_rejected':True,'conflicting_copy_rejected':True,'same_value_different_primitive_ids_retained':2,'repeated_event_count_increase':0}
    check('provenance_not_numerical_similarity',provenance)

    def covariance():
        mean=torch.zeros(2,dtype=torch.float64);lower=torch.tensor([[1.,0.],[.8,.6]],dtype=torch.float64)
        value=torch.tensor([.3,500.],dtype=torch.float64);observed=torch.tensor([True,False])
        score=observed_gaussian_log_prob(mean,lower,value,observed)
        expected=-.5*(math.log(2*math.pi)+.3**2);assert abs(float(score)-expected)<1e-12
        other=observed_gaussian_log_prob(mean,lower,torch.tensor([.3,-500.],dtype=torch.float64),observed)
        assert torch.equal(score,other)
        with torch.no_grad():out=query();eig=torch.linalg.eigvalsh(out['root_covariance']).min()
        assert eig>=-1e-5 and torch.isfinite(out['root_covariance']).all()
        return {'one_coordinate_marginal_log_probability':float(score),'analytic_difference':float(score)-expected,
                'hidden_value_effect':float(score-other),'forecast_covariance_min_eigenvalue':float(eig),'off_diagonal_covariance_supported':True}
    check('correlated_observed_gaussian_marginal',covariance)

    def masked_actual():
        a=MemoryBank(model.schema,model.layout);b=MemoryBank(model.schema,model.layout);changed=targets[0]
        for e in bank.events:
            if e.id==changed:
                mask=e.feedback_mask[:6]+(False,False);ea=replace(e,feedback_mask=mask)
                eb=replace(ea,feedback=ea.feedback[:6]+(1e6,-1e6))
            else:ea=eb=e
            a.add(ea);b.add(eb)
        assert torch.equal(a.view()['features'],b.view()['features'])
        with torch.no_grad():la,info=sequence_nll(model,a,targets);lb,_=sequence_nll(model,b,targets)
        assert torch.equal(la,lb) and not set(targets)&set(info['history_ids'])
        assert info['terms'][0]['observed_continuous_coordinates']==o
        exact=-torch.logsumexp(info['log_prior']+sum(t['step'] for t in info['terms']),0);assert torch.equal(la,exact)
        return {'masked_actual_value_change_loss_difference':float(la-lb),'masked_target_continuous_dimensions':o,
                'target_ids':targets,'history_prefix_size':len(info['history_ids']),'shared_hypothesis_sequence_mix_once':True}
    check('missing_actual_values_are_not_targets_or_memory',masked_actual)

    tape=noise_tape(2233,3,k,o,model.innovations);tape['mask']=torch.ones_like(tape['mask']);tape['terminal']=torch.ones_like(tape['terminal'])
    with torch.no_grad():out=query();candidate_codes=codes(out);hidden=model.dream(out,candidate_codes,tape,force_continue=True,fixed_action=0)
    def hidden_imagination():
        changed={key:value.clone() if isinstance(value,torch.Tensor) else value for key,value in tape.items()}
        changed['normal'][...,o:]+=13.
        with torch.no_grad():again=model.dream(out,candidate_codes,changed,force_continue=True,fixed_action=0)
        assert hidden['nodes']==again['nodes'] and torch.equal(hidden['summary'],again['summary'])
        assert len(hidden['nodes'])==96 and all(not any(n.innovation_mask) and n.innovation==(0.,0.) for n in hidden['nodes'])
        visible=dict(tape,mask=torch.zeros_like(tape['mask']))
        with torch.no_grad():shown=model.dream(out,candidate_codes,visible,force_continue=True,fixed_action=0)
        assert len(shown['nodes'])==96 and all(all(n.innovation_mask) for n in shown['nodes'])
        assert not torch.equal(hidden['summary'],shown['summary'])
        rejected(TypeError,lambda:bank.add(hidden['nodes'][0]));assert bank.to_json()==saved
        return {'hidden_fixture_nodes':96,'visible_fixture_nodes':96,'hidden_draw_changes_node_or_work_state':False,
                'mask_changes_work_state':True,'new_factual_nodes':0,'forced_boundary_fixture_not_autonomous_performance':True}
    check('unseen_imagined_measurements_cannot_enter_work_state',hidden_imagination)

    def nodes():
        for index,node in enumerate(hidden['nodes']):
            assert node.original_weight==float(hidden['root_weights'][node.hypothesis])
            if node.parent is None:assert node.depth==0
            else:
                parent=hidden['nodes'][node.parent];assert node.parent<index
                assert (parent.arm,parent.hypothesis,parent.depth+1)==(node.arm,node.hypothesis,node.depth)
                assert parent.next_observation==node.observation and not parent.terminal
        for arm in range(4):
            for depth in range(3):assert len({n.action_index for n in hidden['nodes'] if n.arm==arm and n.depth==depth})==1
        restored=MemoryBank.from_json(saved);assert torch.equal(restored.view()['features'],bank.view()['features'])
        return {'canonical_memory_roundtrip_exact':True,'parent_links':64,'shared_action_across_latent_hypotheses':True,'unchanged_prior_weights':True}
    check('canonical_memory_and_masked_thought_chronology',nodes)

    def gradients():
        world,policy=model.parameter_groups();model.zero_grad(set_to_none=True)
        loss,_=sequence_nll(model,bank,targets);loss.backward()
        world_live={n for n,q in world.items() if q.grad is not None and torch.isfinite(q.grad).all() and q.grad.abs().sum()>0}
        assert not set(world)-world_live,sorted(set(world)-world_live)
        assert all(q.grad is None for q in policy.values());visibility_gradient=float(model.visibility_head[-1].weight.grad.abs().sum())
        model.zero_grad(set_to_none=True);output=query();cc=codes(output)
        thought=model.dream(output,cc,tape,force_continue=True,fixed_action=0)
        evidence=bank.evidence([[bank.events[-4+i].id] for i in range(4)]);budget=tensor([[2.,0.]])
        trial,state=model.trial_logits_with_thought(output,cc,evidence,budget,thought);adoption,_=model.adoption_logits(output,cc,evidence)
        path=output['logits'].log_softmax(-1)[0,event.action_index]+trial.log_softmax(-1)[0,2]+adoption.log_softmax(-1)[0,1]
        cont=model.thought_continue(torch.cat((output['context'].expand(4,-1),thought['summary'][0],tensor([[1.]]).expand(4,-1)),-1))
        objective=decision_path_loss(thought['internal_log_probability'],path,1.)+comparison_nll(state,1,0,tensor(.4))
        objective=objective+torch.nn.functional.binary_cross_entropy_with_logits(cont,torch.ones_like(cont))
        objective.backward();assert all(q.grad is None for q in world.values())
        policy_live={n for n,q in policy.items() if q.grad is not None and torch.isfinite(q.grad).all() and q.grad.abs().sum()>0}
        assert not set(policy)-policy_live,sorted(set(policy)-policy_live)
        detail={'trainable_parameters':sum(q.numel() for q in model.parameters()),'parameter_tensors':len(list(model.parameters())),
                'world_parameters':sum(q.numel() for q in world.values()),'policy_parameters':sum(q.numel() for q in policy.values()),
                'world_gradient_tensors':len(world_live),'policy_gradient_tensors':len(policy_live),'visibility_head_gradient_l1':visibility_gradient,
                'cross_route_gradient_leak_tensors':0,'optimizer_steps':0,'policy_objective_is_synthetic_reachability_check':True}
        model.zero_grad(set_to_none=True);assert model_identity(model)==before
        return detail
    check('learned_visibility_joint_outcome_and_policy_gradient_routes',gradients)

    def eligibility():
        empty=bank.evidence([[] for _ in range(4)])
        with torch.no_grad():
            scores,_=model.adoption_logits(out,candidate_codes,empty)
            original,_=model.trial_logits_with_thought(out,candidate_codes,empty,tensor([[2.,0.]]),hidden)
            changed,_=model.trial_logits_with_thought(out,candidate_codes,empty,tensor([[2.,0.]]),dict(hidden,summary=hidden['summary']+1.))
        assert torch.isneginf(scores[0,1:]).all() and torch.isfinite(scores[0,0])
        delta=float((original-changed).abs().max());assert delta>0
        return {'untested_candidates_ineligible':True,'thought_summary_trial_logit_difference':delta,'imagined_evidence_receipts':0}
    check('observed_only_imagination_still_requires_real_practice',eligibility)
    assert bank.to_json()==saved and model_identity(model)==before
    return results
