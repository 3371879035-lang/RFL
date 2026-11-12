"""Failure-conditioned event hypothesis -> actual experiment -> ordinary learning."""
from bound_agent import StrictTrialDerivedAgent
from candidate_loop import Proposal
from arrival_query import propose_alternate

class EventHypothesisAgent(StrictTrialDerivedAgent):
    def __init__(self,*args,query_plan_factory,public_transition_budget,**kwargs):
        self._query_plan_factory=query_plan_factory;self._public_transition_budget=public_transition_budget
        super().__init__(*args,**kwargs)
        self._write_limit=0

    def _diagnose_visible(self,terminal,evidence,budget):
        if terminal!='TRAP' or any(s.a_cmd!=s.a_realized for s in evidence.steps):
            self._emit('OUT_OF_SCOPE_FAILURE_KEEP',{'terminal':terminal,'evidence':evidence,'diagnostic_account':self.diagnostic_account()});return Proposal()
        if self.trial_tasks_used>=self.trial_budget:
            self._emit('TRIAL_BUDGET_KEEP',{'main_epoch':self._completed-1,'diagnostic_account':self.diagnostic_account()});return Proposal()
        base=self.payload();spec,search=propose_alternate(evidence,self._public_transition_budget)
        self._emit('ARRIVAL_HYPOTHESIS_PROPOSED',{'terminal':terminal,'evidence':evidence,'post_TD':base,'specification':spec,'public_search':search})
        if spec is None:return Proposal()
        with self._private_context('alternate-entry'):
            plan=self._query_plan_factory(evidence,spec)
            source=self.issue_branch(Proposal(),plan=plan,label=self.source_label+':main:'+str(self._completed-1)+':alternate-entry')
            self._emit('PRIVATE_START',{'state':source.payload(),'parent':base,'n':1,'arrival_specification':spec,'plan_episodes':plan.episodes})
            self.trial_tasks_used+=1;r=self._private_executor(source);observation=source.owned_observation()
            self._emit('PRIVATE_COMPLETE',{'state':source.payload(),'n':1,'return':sum(float.fromhex(s['reward']['binary64_hex']) for s in r['trace']['steps']),
                'hypothesis_assessment':spec.assess(r['trace']),'observation_id':observation.observation_id})
        self.base_queries+=1;self._pending_owned=(observation,)
        assert self.payload()==base
        self._emit('SELECTED_EVENT_EXPERIENCE',{'observation_id':observation.observation_id,'proposal':Proposal(),'diagnostic_account':self.diagnostic_account()})
        return Proposal()
