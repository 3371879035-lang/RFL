"""Learned marginal value gates execution queries after actual ordinaryTD."""
from gated_agent import PolicyQueryAgent
from value_policy import candidate
from candidate_loop import Proposal
from execution_value import numeric_data,ExecutionFeatureData,execution_features

class ExecutionQueryAgent(PolicyQueryAgent):
    def __init__(self,*args,execution_value_model,execution_gate_enabled,**kwargs):
        self.execution_value_model=execution_value_model;self.execution_gate_enabled=execution_gate_enabled
        super().__init__(*args,**kwargs)

    def configuration(self):
        cfg=super().configuration();cfg.update(revision='v165-learned-execution-query',execution_value_model=self.execution_value_model,execution_gate_enabled=self.execution_gate_enabled)
        return cfg

    def run_observed_task(self,*,mask):
        self._execution_before_numeric=numeric_data(self._values)
        return super().run_observed_task(mask=mask)

    def _diagnose_visible(self,terminal,evidence,budget):
        if self.execution_gate_enabled and candidate(evidence) is not None:
            data=ExecutionFeatureData.from_live(evidence,self._execution_before_numeric,self._values);x=execution_features(data,self.reference);value=self.execution_value_model.predict(x)
            decision='unknown_probe' if value is None else 'supported_probe' if value>0 else 'supported_skip'
            self._emit('EXECUTION_VALUE_DECISION',{'feature_data':data,'x':x,'predicted_gain_per_paid_probe':value,'decision':decision,'model':self.execution_value_model,'post_TD':self.payload(),'diagnostic_account':self.diagnostic_account()})
            if decision=='supported_skip':
                self._emit('DIAGNOSTIC_DISPATCH',{'branch':'execution','terminal':terminal,'visible_mismatch':True,'post_TD':self.payload(),'diagnostic_account':self.diagnostic_account()})
                return Proposal()
        return super()._diagnose_visible(terminal,evidence,budget)
