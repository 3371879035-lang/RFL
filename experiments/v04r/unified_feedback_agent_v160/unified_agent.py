"""One full-state agent, shared private budget and registry, two evidence-driven routes."""
from path_agent import PathwiseAgent
from event_agent import EventHypothesisAgent
from candidate_loop import Proposal
from value_policy import candidate

class UnifiedFeedbackAgent(PathwiseAgent,EventHypothesisAgent):
    def __init__(self,*args,learning_values,event_enabled,**kwargs):
        self.event_enabled=event_enabled
        super().__init__(*args,**kwargs)
        # Event-only entry deliberately has no repair write permission. The
        # integrated entry explicitly restores the declared two-site grammar.
        self._write_limit=0 if self.algorithm=='TaskTD' else 2
        self._values=learning_values.clone()
        self._check()

    def configuration(self):
        return {'revision':'v160-unified-full-state','event_enabled':self.event_enabled,
            'trial_budget_shared':self.trial_budget,'feedback_address_limit':self._write_limit,
            'mro':[cls.__name__ for cls in type(self).__mro__]}

    def _diagnose_visible(self,terminal,evidence,budget):
        mismatch=candidate(evidence) is not None
        branch='execution' if mismatch else 'event' if self.event_enabled and terminal=='TRAP' else 'keep'
        self._emit('DIAGNOSTIC_DISPATCH',{'branch':branch,'terminal':terminal,'visible_mismatch':mismatch,
            'post_TD':self.payload(),'diagnostic_account':self.diagnostic_account()})
        if branch=='execution':return PathwiseAgent._diagnose_visible(self,terminal,evidence,budget)
        if branch=='event':return EventHypothesisAgent._diagnose_visible(self,terminal,evidence,budget)
        return Proposal()
