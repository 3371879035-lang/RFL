from pathlib import Path
from fractions import Fraction
import copy,itertools,json,math,sys,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v210.network import Fact,parameter_digest
from feedback_program_v214 import RelationPredictor,state_digest
from feedback_program_v219 import ContinuousBiasHead,ContinuousPriorNet
from scalar_v219 import Calibrator


def main():
    torch.set_num_threads(1);rng=torch.get_rng_state().clone();results=[];xs=list(itertools.product((0,1),repeat=3))
    base=torch.tensor([[[.2,.8],[.7,.3]]],dtype=torch.float64)
    neutral=torch.full((1,2,2),.5,dtype=torch.float64)
    def check(name,fn):
        try:results.append({'name':name,'ok':True,'details':fn()})
        except Exception:results.append({'name':name,'ok':False,'traceback':traceback.format_exc()})
    def fill(h,n=64):
        for i in range(n):
            _,c=h.predict([xs[i%8]],base);h.observe(c,i%2,int(i%5!=0))
    def identity():
        h=ContinuousBiasHead((2,)*3);p,c=h.predict(xs,base.repeat(8,1,1))
        assert torch.equal(p,base.repeat(8,1,1)) and bool((c['coefficients']==0).all())
        assert torch.allclose(c['bias_variance'],torch.full_like(c['bias_variance'],1/3),atol=1e-14,rtol=0)
        return {'bitwise_identity':True,'bias_prior_mean':0.,'bias_prior_variance':float(c['bias_variance'][0,0].detach()),'aggregate_bias_mass':float(c['mass'][0,0,3].detach())}
    check('identity_does_not_mean_zero_uncertainty',identity)
    def exact_integral():
        h=ContinuousBiasHead((2,)*3,conditional=False);coeff=[Fraction(1)];events=[1,1,0,1,0,0,1,1]
        for y in events:
            _,c=h.predict([xs[0]],neutral);h.observe(c,0,y)
            lm,lp=(Fraction(1,2),Fraction(3,2)) if y else (Fraction(3,2),Fraction(1,2))
            nxt=[Fraction(0)]*(len(coeff)+1)
            for j,v in enumerate(coeff):nxt[j]+=v*lm;nxt[j+1]+=v*lp
            coeff=nxt
        n=len(events)
        def moment(power):
            return sum(v*Fraction(math.factorial(j+power)*math.factorial(n-j),math.factorial(n+power+1)) for j,v in enumerate(coeff))
        z=moment(0);m=2*moment(1)/z-1;s=4*moment(2)/z-4*moment(1)/z+1
        hz,hm,hs=h.bias_posterior();error=max(abs(math.exp(float(hz[0].detach()))-float(z)),abs(float(hm[0].detach())-float(m)),abs(float(hs[0].detach())-float(s)))
        assert error<1e-12
        return {'rational_integral_max_error':error,'observed_events':n,'extra_binomial_factor':False}
    check('exact_beta_integral_against_rational_expansion',exact_integral)
    def one_event():
        h=ContinuousBiasHead((2,)*3,conditional=False);_,c=h.predict([xs[0]],neutral);h.observe(c,0,1)
        p,c=h.predict([xs[0]],neutral)
        assert abs(float(c['bias_mean'][0,0].detach())-1/6)<1e-13 and abs(float(c['bias_variance'][0,0].detach())-11/36)<1e-13
        assert abs(float(p[0,0,1].detach())-(.5+1/96))<1e-13
        return {'bias_mean':1/6,'bias_variance':11/36,'mixture_prediction':float(p[0,0,1].detach())}
    check('outcome_not_mislabeled_as_latent_expert',one_event)
    def balanced():
        h=ContinuousBiasHead((2,)*3,conditional=False)
        for i in range(256):
            _,c=h.predict([xs[0]],neutral);h.observe(c,0,i%2)
        p,c=h.predict([xs[0]],neutral);var=float(c['bias_variance'][0,0].detach())
        assert abs(float(p[0,0,1].detach())-.5)<1e-12 and var<1/3
        return {'mean_prediction':float(p[0,0,1].detach()),'bias_variance_after_256':var,'synthetic_not_task_result':True}
    check('evidence_can_reduce_uncertainty_without_moving_mean',balanced)
    def signed():
        answers=[]
        for success_count in [3,5]:
            h=ContinuousBiasHead((2,)*3,conditional=False)
            for i in range(256):
                _,c=h.predict([xs[0]],neutral);h.observe(c,0,int(i%8<success_count))
            p,c=h.predict([xs[0]],neutral);answers.append(float(p[0,0,1].detach()))
        assert answers[0]<.43 and answers[1]>.57
        return {'predictions':answers,'bias_capability_retained':True,'synthetic_not_task_result':True}
    check('systematic_positive_and_negative_bias_remain_learnable',signed)
    def independent():
        h=ContinuousBiasHead((2,)*3);s=Calibrator();error=0.
        for i in range(80):
            x=xs[i%8];p,c=h.predict([x],base);sp,sc=s.predict(x,base[0].tolist())
            for actual,expected in [(p[0],sp),(c['mass'][0],sc['weights']),(c['bias_mean'][0],sc['bias_mean']),(c['bias_variance'][0],sc['bias_variance'])]:
                error=max(error,float((actual.detach()-torch.tensor(expected,dtype=torch.float64)).abs().max()))
            assert error<2e-11
            assert torch.allclose(c['within']+c['between'],p[:,:,1]*(1-p[:,:,1]),atol=2e-12,rtol=0)
            assert bool((c['within']>=-1e-13).all()) and bool((c['between']>=0).all())
            h.observe(c,i%2,int(i%5!=0));s.observe(sc,i%2,int(i%5!=0))
        return {'max_scalar_error':error,'total_variance_identity':True}
    check('independent_scalar_and_full_uncertainty',independent)
    def likelihood():
        h=ContinuousBiasHead((2,)*3,conditional=False);loss=raw=0.
        for i in range(128):
            p,c=h.predict([xs[i%8]],base);a=i%2;y=int(i%5!=0)
            loss-=math.log(float(p[0,a,y].detach()));raw-=math.log(float(base[0,a,y]));h.observe(c,a,y)
        z=float(h.posterior()[-1].detach());assert abs(loss-(raw-z))<1e-10 and loss<=raw+math.log(2)+1e-10
        assert bool((h.log_discrete[:,0]==0).all())
        return {'loss':loss,'base_loss':raw,'log_marginal_ratio':z,'identity_bound':math.log(2)}
    check('single_likelihood_factor_and_identity_reference',likelihood)
    def reprior():
        h=ContinuousBiasHead((2,)*3,conditional=False);fill(h);before=h.log_coefficients.clone();count=h.visits.clone()
        changed=copy.deepcopy(h)
        with torch.no_grad():changed.log_concentration.fill_(math.log(2.))
        s=Calibrator(False,2.)
        for i in range(64):
            _,c=s.predict(xs[i%8],base[0].tolist());s.observe(c,i%2,int(i%5!=0))
        p,_=changed.predict([xs[0]],base);sp,_=s.predict(xs[0],base[0].tolist())
        error=float((p[0].detach()-torch.tensor(sp,dtype=torch.float64)).abs().max());assert error<1e-11
        assert torch.equal(before,changed.log_coefficients) and torch.equal(count,changed.visits)
        return {'recomputed_from_likelihood_not_old_posterior':True,'max_error':error,'new_events':0}
    check('prior_change_does_not_recount_history',reprior)
    def gradient():
        h=ContinuousBiasHead((2,)*3);fill(h);p,_=h.predict([xs[0]],base);loss=-p[0,0,1].log();pars=[h.prior_logits,h.log_concentration]
        grads=torch.autograd.grad(loss,pars);details=[]
        for name,par,grad in zip(['branch_prior','bias_concentration'],pars,grads):
            idx=tuple(int(i) for i in torch.nonzero(grad.abs()==grad.abs().max())[0]);g=float(grad[idx]);old=float(par[idx].detach());eps=1e-5
            assert torch.isfinite(grad).all() and abs(g)>1e-9
            with torch.no_grad():
                par[idx]=old+eps;plus=float(-h.predict([xs[0]],base)[0][0,0,1].log())
                par[idx]=old-eps;minus=float(-h.predict([xs[0]],base)[0][0,0,1].log());par[idx]=old
            fd=(plus-minus)/(2*eps);assert abs(fd-g)<2e-7
            details.append({'parameter':name,'analytic':g,'finite_difference':fd})
        return {'gradients':details,'optimizer_steps':0}
    check('trainable_branch_and_concentration_gradients',gradient)
    def make_net():
        h=RelationPredictor((2,)*3,hazard=0.);t=RelationPredictor((2,)*3);history=[]
        for i in range(32):
            x=xs[i%8];f=Fact(i,x,i%2,int(i%2==x[0]),.5,'synthetic');h.observe(f);t.observe(f);history.append(f)
        return ContinuousPriorNet(h,t,history+history),history
    def replay():
        net,old=make_net();w=net.offer((0,0,0),32);f=Fact(32,(0,0,0),0,1,w['behavior'][0],net.mode);net.observe(w,f);before=state_digest(net)
        for _ in range(5):net.replay_fact(f);net.replay_fact(old[0])
        try:net.observe(w,f)
        except ValueError:pass
        else:raise AssertionError('duplicate event accepted')
        assert before==state_digest(net) and len(net.archive)==33 and net.current.n==net.gate.updates==net.calibrator.updates==1
        try:net.replay_fact(Fact(f.id,f.context,f.action,0,f.propensity,f.policy_id))
        except ValueError:pass
        else:raise AssertionError('conflicting identity accepted')
        return {'unique_history':32,'unique_current':1,'repeat_updates':0,'conflict_rejected':True}
    check('history_and_current_identity_replay_do_not_update',replay)
    def training_query():
        net,_=make_net()
        for i in range(8):
            x=xs[i];w=net.offer(x,32+i);net.observe(w,Fact(32+i,x,i%2,int(i%3==0),w['behavior'][i%2],net.mode))
        par=parameter_digest(net);state=state_digest(net);loss=net.predictive_loss(xs,torch.arange(8)%2,torch.arange(8)%2)
        grads=torch.autograd.grad(loss,[p for p in net.parameters() if p.requires_grad]);total=sum(float(g.abs().sum()) for g in grads)
        for _ in range(3):net.predictive_loss(xs,torch.arange(8)%2,torch.arange(8)%2)
        assert state==state_digest(net) and par==parameter_digest(net) and total>0
        assert sum(p.numel() for p in net.parameters() if p.requires_grad)==80
        return {'trainable_scalars':80,'gradient_l1':total,'repeated_query_new_evidence':0,'optimizer_steps':0}
    check('full_network_query_training_ready_and_readonly',training_query)
    def rng_check():
        assert torch.equal(rng,torch.get_rng_state())
        return {'random_initialization':False,'optimizer_steps':0}
    check('fixed_initialization_no_optimizer',rng_check)
    out={'checks':results,'passed':sum(r['ok'] for r in results),'failed':sum(not r['ok'] for r in results),
         'synthetic_only':True,'actual_environment_interactions':0,'optimizer_steps':0}
    with(HERE/'check_result.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    print(json.dumps(out));return int(out['failed']>0)


if __name__=='__main__':sys.exit(main())
