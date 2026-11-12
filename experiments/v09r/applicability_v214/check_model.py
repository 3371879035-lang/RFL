"""New artificial formula checks; not old checker reruns or environment episodes."""
from pathlib import Path
import copy
import itertools
import json
import math
import sys
import traceback

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v210.network import Fact,parameter_digest
from feedback_program_v214 import RelationPredictor,ContextLift,ApplicabilityGate,HistoricalFeedbackNet,state_digest
from scalar import Model as ScalarModel, Predictor as ScalarPredictor

CONTEXTS=list(itertools.product((0,1),repeat=3))


def main():
    torch.set_num_threads(1); rng=torch.get_rng_state().clone(); results=[]
    h=RelationPredictor((2,)*3,hazard=0.); t=RelationPredictor((2,)*3,hazard=.05); archive=[]
    for i in range(96):
        x=CONTEXTS[i%8]; a=(i//8)%2; f=Fact(i,x,a,int(a==x[0]),.5,'artificial-history')
        h.observe(f); t.observe(f); archive.append(f)
    original=[parameter_digest(h),parameter_digest(t)]
    def check(name,fun):
        try:results.append({'name':name,'ok':True,'details':fun()})
        except Exception:results.append({'name':name,'ok':False,'traceback':traceback.format_exc()})
    def reject(fun):
        try:fun()
        except ValueError:return
        raise AssertionError('Expected rejection')
    def cells():
        lift=ContextLift((2,)*3)
        actual=lift(CONTEXTS).tolist()
        for x,row in zip(CONTEXTS,actual):
            expected=[]
            for group,start in zip(lift.partitions,lift.offsets):
                k=0
                for j in group:k=k*2+x[j]
                expected.append(start+k)
            assert row==expected
        return {'partitions':len(lift.partitions),'cells':lift.cells,'contexts':len(CONTEXTS)}
    check('all_public_context_partitions_match_scalar_indices',cells)
    def local_gate():
        c=ApplicabilityGate((2,)*3,True); g=ApplicabilityGate((2,)*3,False)
        hp=torch.tensor([[[.9,.1],[.1,.9]]],dtype=torch.float64)
        fp=1-hp
        for i in range(128):
            x=CONTEXTS[i%8]; a=0; y=x[1]
            for gate in [c,g]:
                _,_,cache=gate.predict([x],hp,fp);gate.observe(cache,a,y)
        ch=[float(c.predict([x],hp,fp)[1][0]) for x in [(0,0,0),(0,1,0)]]
        gh=[float(g.predict([x],hp,fp)[1][0]) for x in [(0,0,0),(0,1,0)]]
        assert ch[0]>.8 and ch[1]<.2 and gh[0]==gh[1]
        return {'conditional_history_share':ch,'global_history_share':gh,'synthetic_observations':128}
    check('learn_conditional_applicability_not_global_truth',local_gate)
    def scalar_check():
        sh=ScalarPredictor(0.);st=ScalarPredictor(.05)
        for f in archive:
            sh.observe(f.context,f.action,f.outcome);st.observe(f.context,f.action,f.outcome)
        maximum=0.
        for mode in HistoricalFeedbackNet.MODES:
            net=HistoricalFeedbackNet(mode,h,t,archive); ref=ScalarModel(mode,sh,st)
            for k in range(48):
                i=96+k;x=CONTEXTS[k%8];a=k%2;y=int(a==(x[0]^x[1]))
                wire=net.offer(x,i);p,lam,_,_,cache=ref.predict(x)
                maximum=max(maximum,max(abs(v-w) for ar,br in zip(wire['prediction'],p) for v,w in zip(ar,br)))
                if lam is not None:maximum=max(maximum,abs(wire['history_share']-lam))
                fact=Fact(i,x,a,y,wire['behavior'][a],mode)
                net.observe(wire,fact);ref.observe(x,a,y,cache)
            net.assert_history_unchanged()
            assert len(net.archive)==144
        assert maximum<1e-12
        return {'max_scalar_prediction_error':maximum,'synthetic_facts_per_mode':48}
    check('all_five_modes_prequential_scalar_equations',scalar_check)
    def correct_order():
        net=HistoricalFeedbackNet('global_gate',h,t,archive); offer=net.offer((1,0,0),96)
        a=0;y=1;hp=offer['history_prediction'][a][y];fp=offer['fresh_prediction'][a][y]
        fact=Fact(96,(1,0,0),a,y,offer['behavior'][a],'global_gate')
        net.observe(offer,fact)
        expected=hp/(hp+fp);actual=float(torch.softmax(net.gate.log_sources[0],0)[0])
        assert abs(actual-expected)<1e-14
        reject(lambda:net.observe(offer,fact))
        assert net.current.n==1 and net.historical.n==96
        return {'history_weight_from_pre_update_predictions':actual,'expected':expected}
    check('gate_before_current_fit_and_no_duplicate_fact',correct_order)
    def action_share():
        net=HistoricalFeedbackNet('global_gate',h,t,archive)
        net.gate.log_sources[0]=torch.tensor([math.log(.001),math.log(.999)],dtype=torch.float64)
        p,mu,share,_=net.predict([(1,0,0)])
        assert int((p@net.utility).argmax(-1)[0])==1
        assert float(mu[0,1])<.12
        assert abs(float(mu[0,1])-(.1+.8*float(share[0])))<1e-14
        return {'greedy_of_prediction_would_choose':1,'actual_action_one_probability':float(mu[0,1]),
                'history_share':float(share[0])}
    check('small_prediction_weight_does_not_force_old_action',action_share)
    def indistinguishable():
        left=HistoricalFeedbackNet('conditional_gate',h,t,archive)
        right=HistoricalFeedbackNet('conditional_gate',h,t,archive)
        p0,m0,_,_=left.predict([(1,1,0)]);p1,m1,_,_=right.predict([(1,1,0)])
        assert torch.equal(p0,p1) and torch.equal(m0,m1)
        q=float(m0[0,1]);v_same=.1+.8*q;v_changed=.9-.8*q
        assert abs(v_same+v_changed-1)<1e-15
        return {'same_visible_information_same_prediction':True,'mean_two_world_success':(v_same+v_changed)/2}
    check('no_knowledge_of_unobserved_new_world_rule',indistinguishable)
    def read_only():
        net=HistoricalFeedbackNet('conditional_gate',h,t,archive); before=state_digest(net)
        p,mu,share,_=net.predict(CONTEXTS)
        assert torch.allclose(p.sum(-1),torch.ones_like(p.sum(-1)),atol=1e-14)
        assert torch.allclose(mu.sum(-1),torch.ones_like(mu.sum(-1)),atol=1e-14)
        assert before==state_digest(net) and len(net.archive)==96
        offer=net.offer((0,0,0),96)
        reject(lambda:net.observe(offer,Fact(96,(0,0,0),0,1,0.,'conditional_gate')))
        assert net.current.n==0 and net.gate.updates==0
        return {'read_only_state_unchanged':True,'bad_propensity_rejected_before_update':True}
    check('normalized_predictions_readonly_eval_and_actual_behavior',read_only)
    def unchanged():
        assert original==[parameter_digest(h),parameter_digest(t)]
        assert all(not p.requires_grad for model in [h,t] for p in model.parameters())
        assert torch.equal(rng,torch.get_rng_state())
        return {'gradient_updates':0,'torch_rng_unchanged':True}
    check('analytic_parameters_and_rng_unchanged',unchanged)
    out={'checks':results,'passed':sum(r['ok'] for r in results),'failed':sum(not r['ok'] for r in results),
         'facts_are_synthetic':True,'actual_environment_interactions':0}
    with(Path(__file__).resolve().parent/'check_result.json').open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
    print(json.dumps({'passed':out['passed'],'failed':out['failed']}));return int(out['failed']!=0)


if __name__=='__main__':sys.exit(main())
