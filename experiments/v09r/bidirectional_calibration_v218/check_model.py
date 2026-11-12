from pathlib import Path
import itertools,json,math,sys,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v210.network import Fact,parameter_digest
from feedback_program_v214 import RelationPredictor,state_digest
from feedback_program_v218 import IdentityCalibrationHead,BidirectionalFeedbackNet
from scalar_v218 import Calibrator


def main():
    torch.set_num_threads(1);rng=torch.get_rng_state().clone();results=[];xs=list(itertools.product((0,1),repeat=3))
    base=torch.tensor([[[.2,.8],[.7,.3]]],dtype=torch.float64)
    def check(name,fn):
        try:results.append({'name':name,'ok':True,'details':fn()})
        except Exception:results.append({'name':name,'ok':False,'traceback':traceback.format_exc()})
    def fill(head,n=80):
        for i in range(n):
            _,c=head.predict([xs[i%8]],base);head.observe(c,i%2,int(i%5!=0))
    def identity():
        values=torch.linspace(.001,.999,100,dtype=torch.float64).reshape(50,2)
        p=torch.stack((1-values,values),-1)
        for cond,full in [(True,True),(True,False),(False,True)]:
            h=IdentityCalibrationHead((2,)*3,conditional=cond,full=full);q,c=h.predict([xs[i%8] for i in range(50)],p)
            assert torch.equal(p,q) and torch.equal(c['coefficients'],torch.zeros_like(c['coefficients']))
        return {'bitwise_identity':True,'conditions':3}
    check('identity_before_any_feedback',identity)
    def legal():
        h=IdentityCalibrationHead((2,)*3);p=torch.linspace(0,1,1001,dtype=torch.float64)[:,None].repeat(1,2)
        mm,_,_=h.maps(torch.stack((1-p,p),-1));assert float(mm.min())>=0 and float(mm.max())<=1
        assert bool((mm[1:,:,:,1]>=mm[:-1,:,:,1]).all())
        assert torch.allclose(mm.sum(-1),torch.ones_like(mm[...,0]),atol=1e-14)
        return {'grid_points':1001,'valid_and_monotone':True}
    check('bounded_bidirectional_map_family',legal)
    def directions():
        h=IdentityCalibrationHead((2,)*3,conditional=False);mm,u,v=h.maps(base)
        assert mm[0,0,1,1]>.8 and mm[0,0,2,1]<.8
        assert mm[0,1,1,1]<.3 and mm[0,1,2,1]>.3
        assert mm[0,1,3,1]>.3 and mm[0,0,4,1]<.8
        return {'maps_at_p08':mm[0,0,:,1].tolist(),'maps_at_p03':mm[0,1,:,1].tolist()}
    check('confidence_and_bias_are_distinct_directions',directions)
    def conditional():
        h=IdentityCalibrationHead((2,)*3);bp=torch.tensor([[[.2,.8],[.2,.8]]],dtype=torch.float64)
        for i in range(800):
            condition=i%2;x=(condition,0,0);j=i//2;y=int(j%10<(9 if condition==0 else 5))
            _,c=h.predict([x],bp);h.observe(c,0,y)
        p,c=h.predict([(0,0,0),(1,0,0)],bp.repeat(2,1,1))
        assert p[0,0,1]>.8 and p[1,0,1]<.8
        return {'condition0':float(p[0,0,1].detach()),'condition1':float(p[1,0,1].detach()),'synthetic_not_task_result':True}
    check('different_conditions_can_raise_and_lower',conditional)
    def independent():
        error=0.
        for cond,full in [(True,True),(True,False),(False,True)]:
            h=IdentityCalibrationHead((2,)*3,conditional=cond,full=full);s=Calibrator(cond,full)
            for i in range(96):
                x=xs[i%8];p,c=h.predict([x],base);sp,sc=s.predict(x,base[0].tolist())
                error=max(error,float((p[0]-torch.tensor(sp,dtype=torch.float64)).abs().max().detach()))
                assert error<1e-12
                assert torch.allclose(c['mass'][0].detach(),torch.tensor(sc['weights'],dtype=torch.float64),atol=2e-12,rtol=0)
                assert torch.allclose(c['within']+c['between'],p[:,:,1]*(1-p[:,:,1]),atol=1e-12,rtol=0)
                h.observe(c,i%2,int(i%5!=0));s.observe(sc,i%2,int(i%5!=0))
        return {'max_scalar_error':error}
    check('independent_scalar_and_variance',independent)
    def likelihood():
        h=IdentityCalibrationHead((2,)*3,conditional=False);loss=raw=0.
        for i in range(128):
            p,c=h.predict([xs[i%8]],base);a=i%2;y=int(i%5!=0)
            loss-=math.log(float(p[0,a,y].detach()));raw-=math.log(float(base[0,a,y]));h.observe(c,a,y)
        z=float(h.posterior()[2].detach());assert abs(loss-(raw-z))<1e-10 and loss<=raw+math.log(2)+1e-10
        assert torch.equal(h.log_ratio[:,0],torch.zeros_like(h.log_ratio[:,0]))
        return {'calibrated_log_loss':loss,'base_log_loss':raw,'log_ratio_marginal':z,'identity_expert_log_ratio':0}
    check('single_factor_ratio_and_identity_reference_bound',likelihood)
    def ranking():
        h=IdentityCalibrationHead((2,)*3,conditional=False);fill(h)
        p=torch.tensor([[[.01,.99],[.1,.9]],[[.6,.4],[.8,.2]],[[.2,.8],[.7,.3]],[[.5,.5],[.5,.5]]],dtype=torch.float64)
        q,_=h.predict(xs[:4],p);assert torch.equal(p[:,:,1].argmax(-1),q[:,:,1].argmax(-1))
        return {'global_monotone_argmax_unchanged':True}
    check('global_calibration_cannot_create_action_gain',ranking)
    def make_net():
        h=RelationPredictor((2,)*3,hazard=0.);t=RelationPredictor((2,)*3);history=[]
        for i in range(32):
            x=xs[i%8];f=Fact(i,x,i%2,int(i%2==x[0]),.5,'synthetic');h.observe(f);t.observe(f);history.append(f)
        return BidirectionalFeedbackNet(h,t,history+history),history
    def replay():
        net,h=make_net();w=net.offer((0,0,0),32);f=Fact(32,(0,0,0),0,1,w['behavior'][0],net.mode);net.observe(w,f)
        before=state_digest(net)
        for _ in range(4):net.replay_fact(f);net.replay_fact(h[0])
        assert before==state_digest(net) and net.current.n==net.gate.updates==net.calibrator.updates==1 and len(net.archive)==33
        try:net.observe(w,f)
        except ValueError:pass
        else:raise AssertionError('Repeated observation counted again')
        assert before==state_digest(net)
        return {'unique_current_events':1,'replay_updates':0,'original_history_unique':32}
    check('duplicate_identity_and_replay',replay)
    def gradient():
        h=IdentityCalibrationHead((2,)*3);fill(h);par=h.prior_logits
        p,c=h.predict([xs[0]],base);loss=-p[0,0,1].log();gr=torch.autograd.grad(loss,par)[0]
        idx=tuple(int(v) for v in torch.nonzero(gr.abs()==gr.abs().max())[0]);value=float(gr[idx]);old=float(par[idx].detach());eps=1e-5
        assert torch.isfinite(gr).all() and abs(value)>1e-9
        with torch.no_grad():
            par[idx]=old+eps;plus=float(-h.predict([xs[0]],base)[0][0,0,1].log())
            par[idx]=old-eps;minus=float(-h.predict([xs[0]],base)[0][0,0,1].log())
            par[idx]=old
        fd=(plus-minus)/(2*eps);assert abs(fd-value)<1e-7
        return {'analytic':value,'finite_difference':fd,'optimizer_steps':0}
    check('trainable_prior_gradient_finite_difference',gradient)
    def whole_loss():
        n,_=make_net();before=state_digest(n);par=parameter_digest(n)
        loss=n.predictive_loss([(0,0,0),(1,1,1)],torch.tensor([0,1]),torch.tensor([1,0]));loss.backward()
        gr=n.calibrator.prior_logits.grad;assert torch.isfinite(gr).all() and float(gr.abs().sum())>0
        assert before==state_digest(n) and par==parameter_digest(n)
        return {'trainable_scalars':gr.numel(),'loss':float(loss.detach()),'gradient_l1':float(gr.abs().sum())}
    check('whole_network_training_loss_connected',whole_loss)
    def readonly():
        h=IdentityCalibrationHead((2,)*3);fill(h);before=state_digest(h)
        for _ in range(3):h.predict(xs,base.repeat(8,1,1))
        assert before==state_digest(h)
        return {'read_only':True}
    check('evaluation_does_not_train',readonly)
    def fixed():
        h=IdentityCalibrationHead((2,)*3);par=parameter_digest(h);fill(h)
        assert par==parameter_digest(h) and torch.equal(rng,torch.get_rng_state())
        assert [n for n,p in h.named_parameters() if p.requires_grad]==['prior_logits']
        return {'trainable_but_unoptimized':True,'random_initialization':False}
    check('fixed_parameters_and_rng',fixed)
    out={'checks':results,'passed':sum(r['ok'] for r in results),'failed':sum(not r['ok'] for r in results),
         'synthetic_only':True,'actual_environment_interactions':0,'optimizer_steps':0}
    with(HERE/'check_result.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    print(json.dumps({'passed':out['passed'],'failed':out['failed']}));return int(out['failed']!=0)

if __name__=='__main__':sys.exit(main())
