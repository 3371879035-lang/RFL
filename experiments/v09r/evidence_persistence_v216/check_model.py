from pathlib import Path
import itertools,json,math,sys,traceback
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v210.network import Fact,parameter_digest
from feedback_program_v214 import ApplicabilityGate,RelationPredictor,state_digest
from feedback_program_v215 import DecisionSeparatedNet
from feedback_program_v216 import PersistenceGate,PersistenceFeedbackNet
from scalar_v216 import Gate,Predictor,make_model


def main():
    torch.set_num_threads(1);rng=torch.get_rng_state().clone();results=[]
    contexts=list(itertools.product((0,1),repeat=3))
    hp=torch.tensor([[[.9,.1],[.1,.9]]],dtype=torch.float64);fp=1-hp
    def check(name,fun):
        try:results.append({'name':name,'ok':True,'details':fun()})
        except Exception:results.append({'name':name,'ok':False,'traceback':traceback.format_exc()})
    def degeneration():
        old=ApplicabilityGate((2,)*3);new=PersistenceGate((2,)*3,(.02,));err=0.
        for i in range(128):
            x=contexts[i%8];a=i%2;y=(i//3)%2
            po,lo,co=old.predict([x],hp,fp);pn,ln,cn=new.predict([x],hp,fp)
            err=max(err,float((po-pn).abs().max()),abs(float(lo-ln)))
            old.observe(co,a,y);new.observe(cn,a,y)
        assert err<1e-12 and torch.equal(old.visits,new.visits)
        return {'R1_matches_original_fixed_rate':True,'max_error':err}
    check('single_rate_reduces_to_V215_gate',degeneration)
    def independent():
        net=PersistenceGate((2,)*3);ref=Gate();err=0.
        for i in range(192):
            x=contexts[i%8];a=(i//8)%2;y=int(a==(x[0]^(i>=96)))
            p,l,c=net.predict([x],hp,fp);sp,sl,sc=ref.predict(x,hp[0].tolist(),fp[0].tolist())
            err=max(err,float((p[0]-torch.tensor(sp,dtype=torch.float64)).abs().max()),abs(float(l[0])-sl))
            assert torch.allclose(c['rate_marginal'][0],torch.tensor(sc[-1],dtype=torch.float64),atol=1e-12,rtol=0)
            net.observe(c,a,y);ref.observe(sc,a,y)
        assert err<1e-12
        return {'synthetic_observations':192,'max_scalar_error':err}
    check('all_nested_prequential_updates_match_scalar',independent)
    def normalization():
        g=PersistenceGate((2,)*3);before=state_digest(g)
        p,l,c=g.predict(contexts,hp.repeat(8,1,1),fp.repeat(8,1,1))
        assert torch.allclose(p.sum(-1),torch.ones_like(p.sum(-1)),atol=1e-14)
        assert torch.allclose(c['rate_marginal'].sum(-1),torch.ones(8,dtype=torch.float64),atol=1e-14)
        assert bool(((l>=0)&(l<=1)).all()) and before==state_digest(g)
        return {'normalized':True,'read_only':True}
    check('probabilities_and_readonly_gate',normalization)
    def bound():
        g=PersistenceGate((2,)*3,conditional=False);loss=0.;losses=[0.]*4
        for i in range(160):
            y=int(i<100 and i%10!=0)
            p,_,c=g.predict([(0,0,0)],hp,fp)
            loss-=math.log(float(p[0,0,y]))
            for r in range(4):losses[r]-=math.log(float(c['rate_predictions'][0,0,r,0,y]))
            g.observe(c,0,y)
        assert loss<=min(losses)+math.log(4)+1e-11
        return {'mixture_log_loss':loss,'individual_rate_log_losses':losses,'bound':min(losses)+math.log(4)}
    check('one_cell_logloss_mixture_bound',bound)
    def stability_and_change():
        g=PersistenceGate((2,)*3,conditional=False)
        for i in range(160):
            _,_,c=g.predict([(0,0,0)],hp,fp);g.observe(c,0,int(i%10!=0))
        _,before,c=g.predict([(0,0,0)],hp,fp);rho=c['rate_marginal'][0].tolist()
        assert rho[0]>rho[-1] and float(before)<.2
        for i in range(24):
            _,_,c=g.predict([(0,0,0)],hp,fp);g.observe(c,0,0)
        _,after,c=g.predict([(0,0,0)],hp,fp)
        assert float(after)>.8
        return {'stable_rate_weights':rho,'history_before':float(before),'history_after_24_reversal_observations':float(after),
                'artificial_sequence_not_task_evidence':True}
    check('stable_evidence_and_possible_recovery_synthetic',stability_and_change)
    def local_only():
        g=PersistenceGate((2,)*3);before=g.log_sources.clone();rb=g.log_rates.clone()
        _,_,cache=g.predict([(0,0,0)],hp,fp);visited=set(cache['indices'][0].tolist());g.observe(cache,0,1)
        remaining=[i for i in range(g.lift.cells) if i not in visited]
        assert torch.equal(before[remaining],g.log_sources[remaining]) and torch.equal(rb[remaining],g.log_rates[remaining])
        return {'unvisited_cells_unchanged':len(remaining),'visited_cells':len(visited)}
    check('do_not_rewrite_unvisited_context_cells',local_only)
    def model_flow():
        h=RelationPredictor((2,)*3,hazard=0.);t=RelationPredictor((2,)*3,hazard=.05);sh=Predictor(0.);st=Predictor(.05);archive=[]
        for i in range(96):
            x=contexts[i%8];a=(i//8)%2;y=int(a==x[0]);f=Fact(i,x,a,y,.5,'synthetic')
            h.observe(f);t.observe(f);sh.observe(x,a,y);st.observe(x,a,y);archive.append(f)
        net=PersistenceFeedbackNet(h,t,archive);ref=make_model('rate_mixture_v216',sh,st);par=parameter_digest(net);err=0.
        for i in range(48):
            x=contexts[i%8];a=i%2;y=int(a==(x[0]^x[1]));wire=net.offer(x,96+i)
            p,l,_,_,cache=ref.predict(x)
            err=max(err,max(abs(v-w) for aa,bb in zip(wire['prediction'],p) for v,w in zip(aa,bb)))
            fact=Fact(96+i,x,a,y,wire['behavior'][a],net.mode);net.observe(wire,fact);ref.observe(x,a,y,cache)
        assert err<1e-12 and net.current.n==net.gate.updates==48 and len(net.archive)==144 and par==parameter_digest(net)
        net.assert_history_unchanged();before=state_digest(net);net.predict(contexts);assert before==state_digest(net)
        try:net.observe(wire,fact)
        except ValueError:pass
        else:raise AssertionError('Duplicate fact accepted')
        return {'max_scalar_error':err,'actual_style_synthetic_facts':48,'fixed_parameters':True,'duplicate_rejected':True}
    check('whole_model_actual_fact_order_and_archive',model_flow)
    def no_gradient():
        g=PersistenceGate((2,)*3)
        assert not any(p.requires_grad for p in g.parameters()) and torch.equal(rng,torch.get_rng_state())
        return {'gradient_updates':0,'torch_rng_unchanged':True}
    check('no_gradient_or_random_initialization',no_gradient)
    out={'checks':results,'passed':sum(r['ok'] for r in results),'failed':sum(not r['ok'] for r in results),
         'synthetic_only':True,'actual_environment_interactions':0}
    with(HERE/'check_result.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    print(json.dumps({'passed':out['passed'],'failed':out['failed']}));return int(out['failed']!=0)


if __name__=='__main__':sys.exit(main())
