from dataclasses import replace
import math,random,time
import torch
from feedback_program_v221 import Event,MemoryBank,Schema,EvidenceMemoryNet,NetworkConfig,PracticeAgent
from feedback_program_v221.losses import factual_nll,off_policy_loss,replay_distillation_loss,comparison_nll
from feedback_program_v220.runtime import model_fingerprint


def fixture_event(i):
    return Event(f'fixture/{i}','fixture_episode',i,tuple((i%13+j)/23 for j in range(16)),((0.,)*8,(1.,)*8),i%2,
                 (.2,)*16,tuple((i%3+j)/13 for j in range(8)),(True,)*8,(1.,)*8,(.1,)*8,(True,)*8,.5,False,False,1.,
                 ('environment','human','tool')[i%3],previous_id=None if i==0 else f'fixture/{i-1}')


def make_bank(n):
    bank=MemoryBank()
    for i in range(n):bank.add(fixture_event(i))
    return bank


def query(model,bank,code=None,memory=None):
    return model(torch.zeros(1,16),torch.ones(1,8),torch.tensor([[[0.]*8,[1.]*8,[.3]*8]]),bank.view() if memory is None else memory,code)


def expect_error(kind,fn):
    try:fn()
    except kind:return
    raise AssertionError(f'Expected {kind.__name__}')


def run_checks(record,profile_sizes):
    torch.manual_seed(221);model=EvidenceMemoryNet().eval();original=model_fingerprint(model);bank=make_bank(8);results={}
    def check(name,fn):
        details=fn();record({'kind':'check','name':name,'passed':True,'details':details});results[name]=details

    def parameters():
        groups={}
        for name,p in model.named_parameters():groups[name.split('.')[0]]=groups.get(name.split('.')[0],0)+p.numel()
        assert sum(groups.values())>2870271 and all(p.requires_grad for p in model.parameters())
        return {'trainable_parameters':sum(groups.values()),'parameter_tensors':len(list(model.parameters())),'by_module':groups}
    check('capacity_and_trainability',parameters)

    def profiles():
        rows=[];pairs=[]
        def hook(module,args,kwargs):
            q,k=args[:2];pairs.append((q.shape[1],k.shape[1]))
        handles=[m.attention.register_forward_pre_hook(hook,with_kwargs=True) for block in model.memory_blocks for m in (block.read,block.work,block.write)]
        try:
            for n in profile_sizes:
                history=make_bank(n);pairs.clear();start=time.perf_counter()
                with torch.no_grad():out=query(model,history)
                elapsed=time.perf_counter()-start;s=model.config.memory_slots
                assert pairs==[(s,n+1),(s,s),(n+1,s)]*model.config.memory_layers
                assert out['attention'].shape[-1]==n+1 and torch.isfinite(out['policy']).all()
                assert len(history.events)==n and history.events[0].id=='fixture/0'
                rows.append({'fixture_nodes':n,'wall_seconds':elapsed,'attention_shapes':pairs.copy(),
                             'attention_pair_count_per_head':model.attention_pair_budget(n,3),'raw_fact_count_after':len(history.events)})
        finally:
            for h in handles:h.remove()
        return {'profiles':rows,'old_v220_forwards':0,'no_n_by_n_memory_attention':True,'note':'Synthetic nodes, not new environment data; no training or production scaling claim'}
    check('long_memory_actual_attention_shapes',profiles)

    def identity_prefix():
        before=bank.to_json();prefix,event=bank.training_example('fixture/3');assert prefix['ids']==tuple(f'fixture/{i}' for i in range(3))
        assert bank.add(bank.events[0]) is False;expect_error(ValueError,lambda:bank.add(replace(bank.events[0],cost=2.)))
        bank.replay(['fixture/3','fixture/5']);assert bank.to_json()==before
        restored=MemoryBank.from_json(before)
        with torch.no_grad():assert torch.equal(query(model,bank)['policy'],query(model,restored)['policy'])
        return {'reimport_and_replay_new_facts':0,'restored_prediction_exact':True,'target_excluded':event.id not in prefix['ids']}
    check('unique_facts_chronological_prefix_and_restore',identity_prefix)

    agent=PracticeAgent(model,'protocol_fixture',random.Random(21));calls=[]
    def environment(action):
        calls.append(action);success=len(calls)%2==0
        return {'next_observation':[.2]*16,'feedback':[float(success)]*8,'feedback_mask':[True]*8,'goal_met':success,'terminal':True,'cost':1.}
    source=agent.execute([0.]*16,[1.]*8,[[0.]*8,[1.]*8],environment,'source')
    session=agent.new_session(source)
    # This deliberately scheduled fixture verifies interfaces; it is not autonomous trial selection.
    for arm in (0,1,1,0):agent.trial(session,arm,environment)

    def retained():
        evidence=agent.evidence(session);counts=evidence['valid'].sum(-1).tolist()[0]
        assert counts==[2,2,0,0] and len(session.receipts)==4 and len(calls)==5
        assert all(source.id not in ids for ids in evidence['ids'])
        outcomes=[agent.bank.events[agent.bank.index[i]].goal_met for i in evidence['ids'][1]]
        assert set(outcomes)=={False,True}
        expect_error(ValueError,lambda:agent.bank.evidence([[evidence['ids'][0][0]],[evidence['ids'][0][0]]]))
        return {'per_arm_actual_trials':counts,'all_receipts':4,'trigger_failure_in_trial_set':False,'candidate_mixed_outcomes':outcomes,
                'fixture_environment_calls_so_far':5,'fixture_trials_manually_scheduled':True}
    check('repeated_trial_evidence_not_overwritten',retained)

    def evidence_sensitivity():
        out=agent.infer(source.observation,source.goal,source.actions);codes=agent.tensor([[c.code for c in session.arms]])
        evidence=agent.evidence(session)
        with torch.no_grad():full=model.practice_state(out,codes,evidence)
        groups=[list(g) for g in evidence['ids']];groups[1]=groups[1][1:]
        with torch.no_grad():trim=model.practice_state(out,codes,agent.bank.evidence(groups))
        assert full['counts'][0,1]==2 and trim['counts'][0,1]==1
        change=float((full['states'][0,1]-trim['states'][0,1]).abs().max());assert change>0
        return {'earlier_trial_affects_learned_representation':True,'state_max_difference':change,'not_a_quality_claim':True}
    check('earlier_practice_reaches_network',evidence_sensitivity)

    def symmetries():
        out=query(model,bank);codes=torch.randn(1,4,model.config.width);ev=bank.evidence([['fixture/0'],['fixture/1','fixture/2'],[],['fixture/4']])
        state=model.practice_state(out,codes,ev)
        assert torch.equal(state['contrast_mean'],-state['contrast_mean'].transpose(-1,-2))
        assert torch.equal(state['contrast_variance'],state['contrast_variance'].transpose(-1,-2))
        assert bool((state['contrast_variance']>0).all())
        perm=[0,3,2,1];ev2={k:(v[:,perm] if torch.is_tensor(v) else tuple(v[i] for i in perm)) for k,v in ev.items()}
        other=model.practice_state(out,codes[:,perm],ev2)
        error=float((other['states']-state['states'][:,perm]).abs().max());assert error<1e-6
        logits,_=model.adoption_logits(out,codes,ev);assert torch.isneginf(logits[0,2]) and torch.isfinite(logits[0,0])
        return {'mean_antisymmetric':True,'variance_symmetric':True,'arm_permutation_max_error':error,'untested_candidate_masked':True}
    check('symmetric_comparison_and_arm_treatment',symmetries)

    def target_isolation():
        a=session.receipts[0].event_id;b=session.receipts[2].event_id
        example=agent.comparison_example(session,a,b);cut=min(agent.bank.index[a],agent.bank.index[b])
        assert example['memory']['ids']==tuple(e.id for e in agent.bank.events[:cut])
        assert a not in example['memory']['ids'] and b not in example['memory']['ids']
        assert not any(a in g or b in g for g in example['evidence']['ids'])
        assert example['target_events'][0].role==example['target_events'][1].role=='trial'
        return {'support_nodes':cut,'target_events':[a,b],'targets_excluded_from_memory_and_practice_support':True}
    check('comparison_support_query_time_split',target_isolation)

    def likelihood():
        state={'contrast_mean':torch.tensor([[[0.,.2],[-.2,0.]]],dtype=torch.float64),
               'contrast_variance':torch.full((1,2,2),.5,dtype=torch.float64)}
        target=torch.tensor([1.],dtype=torch.float64);loss=comparison_nll(state,0,1,target)
        expected=.5*(math.log(2*math.pi*.5)+.8**2/.5)
        assert abs(loss.item()-expected)<1e-12
        expect_error(ValueError,lambda:comparison_nll(state,0,0,target))
        directions=[]
        for error in (0.,2.):
            s=torch.tensor(0.,requires_grad=True);l=.5*(s+error**2*torch.exp(-s));l.backward();directions.append(s.grad.item())
        assert directions==[.5,-1.5]
        return {'nll_absolute_error':abs(loss.item()-expected),'logvariance_gradient_small_and_large_error':directions,
                'variance_target':'new paired outcomes, not an effect confidence interval'}
    check('comparison_likelihood_and_uncertainty_direction',likelihood)

    def code_boundary():
        with torch.no_grad():a=query(model,bank);b=query(model,bank,torch.ones(1,model.config.width))
        for key in ('next_mean','next_variance','feedback_mean','feedback_variance','value_mean','value_variance','weights'):assert torch.equal(a[key],b[key])
        assert not torch.equal(a['policy'],b['policy'])
        return {'candidate_does_not_rewrite_fixed_action_world':True,'policy_max_difference':float((a['policy']-b['policy']).abs().max())}
    check('candidate_world_boundary_preserved',code_boundary)

    def gradients():
        model.zero_grad(set_to_none=True);out=query(model,bank)
        codes=torch.cat((model.base_code[None,None,:],model.propose(out)),1)
        evidence=bank.evidence([['fixture/0','fixture/3'],['fixture/1'],['fixture/2','fixture/5'],['fixture/4']])
        tl,state=model.trial_logits(out,codes,evidence,torch.tensor([[3.,1.]]));al,_=model.adoption_logits(out,codes,evidence)
        loss=factual_nll(out,torch.tensor([1]),torch.ones(1,16)*.2,torch.ones(1,8)*.3,torch.ones(1,8),torch.tensor([.7]))
        loss+=off_policy_loss(out['logits'],torch.tensor([2]),torch.tensor([1/3]),torch.tensor([.8]))
        coded=query(model,bank,codes[:,2]);loss+=off_policy_loss(coded['logits'],torch.tensor([0]),torch.tensor([1/3]),torch.tensor([.6]))
        loss+=off_policy_loss(tl,torch.tensor([3]),torch.tensor([.2]),torch.tensor([.5]))
        loss+=off_policy_loss(al,torch.tensor([1]),torch.tensor([.25]),torch.tensor([.9]))
        loss+=comparison_nll(state,1,0,torch.tensor([.4]))
        loss+=replay_distillation_loss(out['logits'],torch.tensor([[.1,.2,.7]]))
        loss.backward();bad=[];norms={}
        for name,p in model.named_parameters():
            if p.grad is None or not torch.isfinite(p.grad).all() or p.grad.abs().sum()==0:bad.append(name)
            if p.grad is not None:norms[name.split('.')[0]]=norms.get(name.split('.')[0],0.)+float(p.grad.square().sum())
        assert not bad,bad
        assert model_fingerprint(model)==original
        return {'all_parameter_tensors_with_finite_nonzero_gradient':len(list(model.parameters())),
                'group_l2_norms':{k:math.sqrt(v) for k,v in norms.items()},'loss':float(loss.detach()),'optimizer_steps':0}
    check('full_gradient_routes_no_parameter_update',gradients)

    def imagination():
        before=agent.bank.to_json();obj=agent.imagine(source.observation,source.goal,source.actions,0)
        expect_error(TypeError,lambda:agent.bank.add(obj));assert before==agent.bank.to_json()
        assert obj.source_ids==tuple(agent.bank.index) and all(v>0 for v in obj.feedback_variance)
        return {'imagination_factual_writes':0,'one_step_interface_preserved':True}
    check('imagination_remains_nonfactual',imagination)

    def no_reflection_paths():
        def public_env(terminal,goal):
            def call(action):
                calls.append(action);return {'next_observation':[0.]*16,'feedback':[float(goal)]*8,'feedback_mask':[True]*8,
                                            'goal_met':goal,'terminal':terminal,'cost':1.}
            return call
        for i,(terminal,goal) in enumerate(((False,False),(True,True))):
            env=public_env(terminal,goal);event=agent.execute([0.]*16,[1.]*8,[[0.]*8,[1.]*8],env,f'no_reflection_{i}')
            assert agent.reflect(event,env,4) is None
        assert len(calls)==7 and agent.counters['failure_sessions']==1
        return {'extra_fixture_environment_calls':2,'total_fixture_environment_calls':7,'nonterminal_and_success_reflections':0,
                'both_events_remain_for_ordinary_learning':True}
    check('online_observation_and_success_not_offline_failure',no_reflection_paths)

    def versions():
        expect_error(ValueError,lambda:agent.promote(session,2));agent.promote(session,1)
        before=agent.bank.to_json();count=len(agent.bank.events)
        torch.manual_seed(222);replacement=EvidenceMemoryNet(config=NetworkConfig(width=64,attention_heads=4,memory_layers=1,memory_slots=8)).eval()
        agent.replace_model(replacement);assert agent.current_code is None and agent.current_candidate is None and not session.active
        expect_error(ValueError,lambda:agent.promote(session,1))
        assert before==agent.bank.to_json() and len(agent.bank.events)==count
        renewed=agent.new_session(source);assert renewed.model_id!=session.model_id and len(renewed.arms[0].code)==64
        expect_error(ValueError,lambda:agent.promote(renewed,1))
        return {'explicit_model_replacement_fixture':1,'old_raw_facts_preserved':count,'old_receipts_preserved':len(session.receipts),
                'stale_code_cleared':True,'new_candidate_requires_new_actual_practice':True,'optimizer_steps':0}
    check('parameter_version_change_retains_facts_not_old_authority',versions)

    def configurable():
        net=EvidenceMemoryNet(Schema(5,3,2,4),NetworkConfig(width=48,attention_heads=3,memory_layers=1,memory_slots=7,candidates=2,hypotheses=4))
        for a in (1,4,7):
            out=net(torch.zeros(1,5),torch.ones(1,4),torch.zeros(1,a,3),MemoryBank(net.schema).view())
            assert out['policy'].shape==(1,a) and torch.isfinite(out['policy']).all()
        assert model_fingerprint(model)==original
        return {'alternative_schema':[5,3,2,4],'actions':[1,4,7],'slots_configurable':7,'default_model_parameters_unchanged':True}
    check('configurable_schema_empty_memory_and_actions',configurable)
    model.zero_grad(set_to_none=True)
    return results
