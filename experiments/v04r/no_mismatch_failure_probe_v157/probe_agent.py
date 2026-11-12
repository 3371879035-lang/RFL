"""Failure-only practice without inventing controller faults or feedback writes."""
from bound_agent import StrictTrialDerivedAgent
from candidate_loop import Proposal
from action_query import ActionTrialSpecification
from evidence_loop import K,A
from rfl_rebuild.learner.store import QAddress

class NoMismatchProbeAgent(StrictTrialDerivedAgent):
    def __init__(self,*args,query_plan_factory,**kwargs):
        self._query_plan_factory=query_plan_factory
        super().__init__(*args,**kwargs)
        self._write_limit=0

    def _diagnose_visible(self,terminal,evidence,budget):
        if any(s.a_cmd!=s.a_realized for s in evidence.steps):
            self._emit('OUT_OF_SCOPE_MISMATCH_KEEP',{'evidence':evidence,'diagnostic_account':self.diagnostic_account()});return Proposal()
        if self.trial_tasks_used>=self.trial_budget:
            self._emit('TRIAL_BUDGET_KEEP',{'main_epoch':self._completed-1,'diagnostic_account':self.diagnostic_account()});return Proposal()
        target=evidence.steps[-1];at=K.State(target.x,target.y,target.t,target.kappa,target.phi);ctrl=K.ControlState(target.z,target.m)
        actions=tuple(K.option_actions(ctrl.z,ctrl,at));alternatives=[a for a in actions if a!=target.a_cmd]
        if not alternatives:
            self._emit('NO_ADMISSIBLE_ALTERNATIVE_KEEP',{'evidence':evidence,'diagnostic_account':self.diagnostic_account()});return Proposal()
        numeric=self._values if self.mode=='patch-adaptive' else self._current
        def value(action):
            q=QAddress(at,ctrl.z,ctrl.m,action)
            return numeric.q_overrides.get(q,self.reference.value(q))
        alternative=min(alternatives,key=lambda a:(-value(a),a));spec=ActionTrialSpecification.from_visible_failure(evidence,alternative)
        base=self.payload();greedy=self.algorithm=='GreedyPractice'
        self._emit('FAILURE_QUERY_PLANNED',{'terminal':terminal,'evidence':evidence,'post_TD':base,'specification':spec,'greedy':greedy,
            'row_after_main_TD':[(a,value(a)) for a in actions],'ordinary_selector_at_target':self._greedy()(at,ctrl)})
        with self._private_context('practice'):
            plan=self._query_plan_factory(evidence,spec,greedy)
            source=self.issue_branch(Proposal(),plan=plan,label=self.source_label+':main:'+str(self._completed-1)+':practice')
            self._emit('PRIVATE_START',{'state':source.payload(),'parent':base,'n':1,'action_trial_specification':spec,'greedy':greedy,'plan_episodes':plan.episodes})
            self.trial_tasks_used+=1;r=self._private_executor(source);observation=source.owned_observation()
            self._emit('PRIVATE_COMPLETE',{'state':source.payload(),'n':1,'return':sum(float.fromhex(s['reward']['binary64_hex']) for s in r['trace']['steps']),
                'actual_target_reach':spec.actual_reach(r['trace']),'observation_id':observation.observation_id})
        self.base_queries+=1;self._pending_owned=(observation,)
        assert self.payload()==base
        self._emit('SELECTED_FAILURE_EXPERIENCE',{'observation_id':observation.observation_id,'proposal':Proposal(),'diagnostic_account':self.diagnostic_account()})
        return Proposal()
