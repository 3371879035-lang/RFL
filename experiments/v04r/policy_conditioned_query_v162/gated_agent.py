"""Supported empirical zero -> skip; unknown evidence -> actual budgeted test."""
from unified_agent import UnifiedFeedbackAgent
from candidate_loop import Proposal
from value_policy import candidate
from arrival_query import propose_alternate
from query_value import QueryFeatureData,query_features

class PolicyQueryAgent(UnifiedFeedbackAgent):
    def __init__(self,*args,query_value_model,value_gate_enabled,**kwargs):
        self.query_value_model=query_value_model;self.value_gate_enabled=value_gate_enabled
        super().__init__(*args,**kwargs)

    def configuration(self):
        cfg=super().configuration();cfg.update(revision='v162-same-data-policy-conditioning',value_gate_enabled=self.value_gate_enabled,query_value_model=self.query_value_model)
        return cfg

    def _diagnose_visible(self,terminal,evidence,budget):
        if not self.value_gate_enabled or candidate(evidence) is not None or not self.event_enabled or terminal!='TRAP':
            return UnifiedFeedbackAgent._diagnose_visible(self,terminal,evidence,budget)
        self._emit('DIAGNOSTIC_DISPATCH',{'branch':'event','terminal':terminal,'visible_mismatch':False,'post_TD':self.payload(),'diagnostic_account':self.diagnostic_account()})
        if self.trial_tasks_used>=self.trial_budget:
            self._emit('TRIAL_BUDGET_KEEP',{'main_epoch':self._completed-1,'diagnostic_account':self.diagnostic_account()});return Proposal()
        base=self.payload();spec,search=propose_alternate(evidence,self._public_transition_budget)
        self._emit('ARRIVAL_HYPOTHESIS_PROPOSED',{'terminal':terminal,'evidence':evidence,'post_TD':base,'specification':spec,'public_search':search})
        if spec is None:return Proposal()
        projected=QueryFeatureData.from_live(evidence,spec,self._values,self._current);all_features=query_features(projected,self.reference);x=all_features[:len(self.query_value_model.support)];value=self.query_value_model.predict(x)
        decision='unknown_probe' if value is None else 'supported_probe' if value>0 else 'supported_skip'
        self._emit('QUERY_VALUE_DECISION',{'feature_data':projected,'x':x,'predicted_gain_per_paid_probe':value,'decision':decision,'model':self.query_value_model,'post_TD':base,'diagnostic_account':self.diagnostic_account()})
        if decision=='supported_skip':return Proposal()
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
