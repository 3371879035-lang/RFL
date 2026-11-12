from pathlib import Path
from dataclasses import replace
import itertools,json,math,sys,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v210.network import Fact,parameter_digest
from feedback_program_v214 import RelationPredictor,state_digest
from feedback_program_v216 import PersistenceGate
from feedback_program_v217 import SharedEvidenceGate,PriorUncertaintyNet,unique_facts
from scalar_v217 import Gate


def main():
    torch.set_num_threads(1);rng=torch.get_rng_state().clone();results=[]
    contexts=list(itertools.product((0,1),repeat=3))
    hp=torch.tensor([[[.9,.1],[.1,.9]]],dtype=torch.float64);fp=1-hp
    def check(name,fun):
        try:results.append({'name':name,'ok':True,'details':fun()})
        except Exception:results.append({'name':name,'ok':False,'traceback':traceback.format_exc()})
    def fill(g,n=64):
        for i in range(n):
            _,_,c=g.predict([contexts[i%8]],hp,fp);g.observe(c,i%2,int(i%7==0))
    def degeneration():
        a=PersistenceGate((2,)*3);b=SharedEvidenceGate((2,)*3,False,(0.,));err=0.
        for i in range(128):
            x=contexts[i%8];pa,sa,ca=a.predict([x],hp,fp);pb,sb,cb=b.predict([x],hp,fp)
            err=max(err,float((pa-pb).abs().max().detach()),float((sa-sb).abs().max().detach()))
            a.observe(ca,i%2,int(i%5==0));b.observe(cb,i%2,int(i%5==0))
        assert err<2e-12
        return {'max_error':err,'local_raw_matches_V216':True}
    check('local_raw_degenerates_to_V216',degeneration)
    def independent():
        maximum=0.
        for shared,etas in [(True,(0.,)),(False,(0.,.25,.5)),(True,(0.,.25,.5))]:
            g=SharedEvidenceGate((2,)*3,shared,etas);s=Gate(shared,etas)
            for i in range(96):
                x=contexts[i%8];p,l,c=g.predict([x],hp,fp);sp,sl,sc=s.predict(x,hp[0].tolist(),fp[0].tolist())
                err=float((p[0]-torch.tensor(sp,dtype=torch.float64)).abs().max().detach());maximum=max(maximum,err,abs(float(l.detach())-sl))
                assert err<3e-12
                for field,key in [('within','within'),('between','between'),('rate_marginal','rates'),('eta_marginal','etas')]:
                    assert torch.allclose(c[field][0].detach(),torch.tensor(sc[key],dtype=torch.float64),atol=3e-12,rtol=0)
                a=i%2;y=int(i%7==0 or i>60);g.observe(c,a,y);s.observe(sc,a,y)
        return {'max_scalar_error':maximum,'hypothesis_sequences':3}
    check('independent_scalar_equations',independent)
    def telescope(shared):
        g=SharedEvidenceGate((2,)*3,shared);loss=0.
        for i in range(96):
            p,_,c=g.predict([contexts[i%8]],hp,fp);a=i%2;y=int(i%7==0)
            loss-=math.log(float(p[0,a,y].detach()));g.observe(c,a,y)
        _,logz=g.hyper_posterior();error=abs(loss+float(logz.detach()))
        assert error<1e-10 and g.updates==96
        if shared:
            pi=g.partition_prior;lp=g.prior().detach()
            bounds=[-float(g.log_likelihood[s:s+n,r,b].sum())-float(pi[j])-float(lp[j,r,b])
                    for j,(s,n) in enumerate(zip(g.lift.offsets,g.lift.sizes)) for r in range(4) for b in range(3)]
            assert loss<=min(bounds)+1e-10
        return {'observed_log_loss':loss,'negative_log_evidence':-float(logz.detach()),'difference':error}
    check('shared_likelihood_counts_once',lambda:telescope(True))
    check('local_likelihood_counts_once',lambda:telescope(False))
    def variance():
        g=SharedEvidenceGate((2,)*3);fill(g)
        p,_,c=g.predict(contexts,hp.repeat(8,1,1),fp.repeat(8,1,1))
        err=float((c['within']+c['between']-p*(1-p)).abs().max().detach())
        assert err<1e-12 and float(c['between'].min().detach())>-1e-12
        return {'law_of_total_variance_error':err,'physical_uncertainty_identification':False}
    check('uncertainty_variance_decomposition',variance)
    def sharing():
        g=SharedEvidenceGate((2,)*3);before=g.log_sources.clone();ll=g.log_likelihood.clone()
        _,_,c=g.predict([(0,0,0)],hp,fp);visited=set(c['indices'][0].tolist());g.observe(c,0,1)
        unvisited=[i for i in range(g.lift.cells) if i not in visited]
        assert torch.equal(before[unvisited],g.log_sources[unvisited]) and torch.equal(ll[unvisited],g.log_likelihood[unvisited])
        return {'unvisited_cell_counts_unchanged':len(unvisited),'hyperparameter_sharing_not_local_fact_fabrication':True}
    check('shared_prior_not_shared_local_answers',sharing)
    def identity():
        a=Fact(0,(0,0,0),0,1,.5,'fixture');b=replace(a,id=1)
        assert unique_facts([a,a,b])==[a,b]
        try:unique_facts([a,replace(a,outcome=0)])
        except ValueError:pass
        else:raise AssertionError('conflicting identity accepted')
        return {'duplicate_removed':True,'new_identical_outcome_preserved':True,'conflict_rejected':True}
    check('history_identity_not_content_dedup',identity)
    def make_net():
        h=RelationPredictor((2,)*3,hazard=0.);t=RelationPredictor((2,)*3);history=[]
        for i in range(32):
            f=Fact(i,contexts[i%8],i%2,int((i%2)==contexts[i%8][0]),.5,'synthetic')
            h.observe(f);t.observe(f);history.append(f)
        return PriorUncertaintyNet(h,t,history+history),history
    def replay():
        n,h=make_net();par=parameter_digest(n);wire=n.offer((0,0,0),32)
        f=Fact(32,(0,0,0),0,0,wire['behavior'][0],n.mode);n.observe(wire,f)
        before=state_digest(n);count=(n.gate.updates,n.current.n,len(n.archive))
        for _ in range(5):n.replay_fact(f);n.replay_fact(h[0])
        assert before==state_digest(n) and count==(1,1,33) and par==parameter_digest(n)
        try:n.observe(wire,f)
        except ValueError:pass
        else:raise AssertionError('observed twice')
        assert before==state_digest(n)
        return {'current_updates':1,'unique_archive':33,'replay_updates':0}
    check('fact_replay_idempotent_online_duplicate_rejected',replay)
    def gradients():
        g=SharedEvidenceGate((2,)*3);fill(g)
        logits=g.prior.logits
        p,_,_=g.predict([(0,0,0)],hp,fp);loss=-p[0,0,1].log();grad=torch.autograd.grad(loss,logits)[0]
        idx=tuple(int(v) for v in torch.nonzero(grad.abs()==grad.abs().max())[0]);analytic=float(grad[idx]);old=float(logits[idx].detach());eps=1e-5
        assert abs(analytic)>1e-8 and torch.isfinite(grad).all()
        with torch.no_grad():
            logits[idx]=old+eps;pa=g.predict([(0,0,0)],hp,fp)[0];plus=float(-pa[0,0,1].log())
            logits[idx]=old-eps;pb=g.predict([(0,0,0)],hp,fp)[0];minus=float(-pb[0,0,1].log())
            logits[idx]=old
        fd=(plus-minus)/(2*eps);assert abs(analytic-fd)<1e-7
        return {'analytic_gradient':analytic,'finite_difference':fd,'optimizer_steps':0}
    check('trainable_prior_finite_difference',gradients)
    def loss_path():
        n,_=make_net();before=state_digest(n);params=parameter_digest(n)
        loss=n.predictive_loss([(0,0,0),(1,1,1)],torch.tensor([0,1]),torch.tensor([1,0]))
        loss.backward();grad=n.gate.prior.logits.grad
        assert torch.isfinite(grad).all() and float(grad.abs().sum())>0
        assert before==state_digest(n) and params==parameter_digest(n)
        return {'loss':float(loss.detach()),'trainable_parameter_scalars':grad.numel(),'gradient_l1':float(grad.abs().sum()),'parameter_updates':0}
    check('whole_network_predictive_training_path',loss_path)
    def readonly():
        g=SharedEvidenceGate((2,)*3);fill(g);before=state_digest(g)
        for _ in range(4):g.predict(contexts,hp.repeat(8,1,1),fp.repeat(8,1,1))
        assert before==state_digest(g)
        return {'repeated_prediction_does_not_increase_evidence':True}
    check('prediction_is_readonly',readonly)
    def fixed():
        assert torch.equal(rng,torch.get_rng_state())
        g=SharedEvidenceGate((2,)*3);par=parameter_digest(g);fill(g);assert par==parameter_digest(g)
        assert all(n=='prior.logits' for n,p in g.named_parameters() if p.requires_grad)
        return {'trainable_prior_not_yet_trained':True,'rng_unchanged':True,'optimizer_steps':0}
    check('analytic_initialization_no_parameter_training',fixed)
    out={'checks':results,'passed':sum(r['ok'] for r in results),'failed':sum(not r['ok'] for r in results),
         'synthetic_only':True,'actual_environment_interactions':0,'optimizer_steps':0}
    with(HERE/'check_result.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    print(json.dumps({'passed':out['passed'],'failed':out['failed']}));return int(out['failed']!=0)

if __name__=='__main__':sys.exit(main())
