"""New V7 operator checks. All fixtures are synthetic, zero environment interactions."""
from pathlib import Path
import itertools
import json
import math
import sys
import traceback

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'experiments/v09r/applicability_v214'))
import torch
from feedback_program_v210.network import Fact,parameter_digest
from feedback_program_v214 import RelationPredictor,HistoricalFeedbackNet,state_digest
from feedback_program_v215 import ExpectedUtilityReadout,DecisionSeparatedNet
from scalar import Model,Predictor


def main():
    torch.set_num_threads(1);rng=torch.get_rng_state().clone();results=[]
    def check(name,fun):
        try:results.append({'name':name,'ok':True,'details':fun()})
        except Exception:results.append({'name':name,'ok':False,'traceback':traceback.format_exc()})
    readout=ExpectedUtilityReadout()
    def exact_readout():
        rows=[[[1-p,p],[1-q,q]] for p,q in itertools.product([.1,.5,.9],repeat=2)]
        tensor=torch.tensor(rows,dtype=torch.float64);mu,s,m=readout(tensor)
        for i,(p,q) in enumerate(itertools.product([.1,.5,.9],repeat=2)):
            best=0 if p>=q else 1
            assert mu[i].tolist()==[.9 if a==best else .1 for a in range(2)]
            assert s[i].tolist()==[p,q] and abs(float(m[i])-abs(p-q))<1e-14
        return {'grids':9,'tie_break':'first_action','epsilon':.2}
    check('linear_goal_readout_and_common_exploration',exact_readout)
    def residual_loss():
        h=torch.tensor([[[.1,.9],[.9,.1]]],dtype=torch.float64);f=1-h
        lam=.06051753774948417;p=lam*h+(1-lam)*f
        mu,_,_=readout(p);j=sum(mu[0,a].item()*[.1,.9][a] for a in range(2))
        old=lam*.18+(1-lam)*.82
        assert abs(j-.82)<1e-14 and j>old
        return {'old_policy_mixture_value':old,'new_decision_value':j,'lambda_unchanged':lam}
    check('remove_predictive_weight_mandatory_action_quota',residual_loss)
    def predictive_optimality():
        low=-1.
        for hp0,hp1,fp0,fp1,lam in itertools.product([.1,.5,.9],repeat=5):
            h=torch.tensor([[[1-hp0,hp0],[1-hp1,hp1]]],dtype=torch.float64)
            f=torch.tensor([[[1-fp0,fp0],[1-fp1,fp1]]],dtype=torch.float64)
            p=lam*h+(1-lam)*f;mu,s,_=readout(p)
            mh=readout(h)[0];mf=readout(f)[0];old=lam*mh+(1-lam)*mf
            diff=float(((mu-old)*s).sum())
            assert diff>=-1e-14
            low=diff if low==-1 else min(low,diff)
        return {'finite_cases':243,'minimum_predicted_value_difference':low,'true_return_dominance_claimed':False}
    check('same_prediction_decision_inequality',predictive_optimality)
    def error_bound():
        cases=0
        for q0,q1,p0,p1 in itertools.product([.1,.5,.9],repeat=4):
            pred=torch.tensor([[[1-p0,p0],[1-p1,p1]]],dtype=torch.float64)
            mu,_,_=readout(pred);delta=max(abs(q0-p0),abs(q1-p1))
            regret=max(q0,q1)-sum(mu[0,a].item()*[q0,q1][a] for a in range(2))
            assert regret<=2*delta+.2+1e-14;cases+=1
        return {'finite_cases':cases,'unknown_prediction_error_is_not_estimated_confidence':True}
    check('conditional_regret_bound_not_truth_guarantee',error_bound)
    def weak_reference():
        h=torch.tensor([[[.9,.1],[.1,.9]]],dtype=torch.float64);f=torch.full_like(h,.5)
        mu,_,margin=readout(.01*h+.99*f)
        assert float(mu[0,1])==.9 and abs(float(margin[0])-.008)<1e-14
        return {'weak_reference_can_select_a_provisional_action':True,'estimated_margin':float(margin[0]),
                'verified_causal_answer':False}
    check('weak_reference_not_mislabeled_as_high_confidence',weak_reference)

    contexts=list(itertools.product((0,1),repeat=3));archive=[]
    h=RelationPredictor((2,)*3,hazard=0.);t=RelationPredictor((2,)*3,hazard=.05)
    sh=Predictor(0.);st=Predictor(.05)
    for i in range(96):
        x=contexts[i%8];a=(i//8)%2;y=int(a==x[0]);f=Fact(i,x,a,y,.5,'synthetic-prefix')
        h.observe(f);t.observe(f);sh.observe(x,a,y);st.observe(x,a,y);archive.append(f)
    originals=[parameter_digest(h),parameter_digest(t)]
    def unchanged_learning():
        old=HistoricalFeedbackNet('conditional_gate',h,t,archive);new=DecisionSeparatedNet(h,t,archive)
        ref=Model('conditional_gate',sh,st);maxerr=0.;changed_actions=0
        for k in range(48):
            x=contexts[k%8];a=k%2;y=int(a==(x[0]^x[1]));i=96+k
            ow=old.offer(x,i);nw=new.offer(x,i);sp,sl,_,_,sc=ref.predict(x)
            assert ow['prediction']==nw['prediction'] and ow['history_share']==nw['history_share']
            changed_actions+=int(ow['behavior']!=nw['behavior'])
            for aa,bb in zip(nw['prediction'],sp):
                for v,w in zip(aa,bb):maxerr=max(maxerr,abs(v-w))
            assert abs(nw['history_share']-sl)<1e-12
            best=max(range(2),key=lambda j:nw['prediction'][j][1])
            assert nw['behavior']==[.9 if j==best else .1 for j in range(2)]
            old.observe(ow,Fact(i,x,a,y,ow['behavior'][a],old.mode))
            new.observe(nw,Fact(i,x,a,y,nw['behavior'][a],new.mode));ref.observe(x,a,y,sc)
        assert maxerr<1e-12 and changed_actions>0
        assert state_digest(old.current)==state_digest(new.current) and state_digest(old.gate)==state_digest(new.gate)
        new.assert_history_unchanged();old.assert_history_unchanged()
        return {'same_supplied_facts_same_predictive_learning':True,'behavior_changes':changed_actions,
                'max_independent_scalar_error':maxerr}
    check('only_readout_changes_under_identical_facts',unchanged_learning)
    def readonly_and_once():
        net=DecisionSeparatedNet(h,t,archive);before=state_digest(net);n=net.current.n
        net.predict(contexts)
        assert before==state_digest(net) and n==net.current.n
        w=net.offer((0,0,0),96);f=Fact(96,(0,0,0),0,1,w['behavior'][0],net.mode);net.observe(w,f)
        try:net.observe(w,f)
        except ValueError:pass
        else:raise AssertionError('Duplicate observation accepted')
        assert len(net.archive)==97 and net.current.n==1 and net.gate.updates==1
        return {'read_only_evaluation':True,'one_fact_one_learning_update':True}
    check('prequential_readonly_and_once_preserved',readonly_and_once)
    def fixed():
        net=DecisionSeparatedNet(h,t,archive)
        assert originals==[parameter_digest(h),parameter_digest(t)]
        assert not any(p.requires_grad for p in net.parameters()) and torch.equal(rng,torch.get_rng_state())
        return {'gradient_updates':0,'torch_rng_unchanged':True}
    check('analytic_network_parameters_and_rng_unchanged',fixed)
    result={'checks':results,'passed':sum(r['ok'] for r in results),'failed':sum(not r['ok'] for r in results),
            'synthetic_only':True,'new_environment_interactions':0}
    with(HERE/'check_result.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({'passed':result['passed'],'failed':result['failed']}));return int(result['failed']!=0)


if __name__=='__main__':sys.exit(main())
