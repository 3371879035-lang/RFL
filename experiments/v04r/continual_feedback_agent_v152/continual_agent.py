"""Continual failure-only feedback agent. The runner supplies actual task execution,
not a terminal/cause label. Ordinary R+L persists and private outcomes are real.
"""
from intervention_experience import InterventionExperienceLoop
from candidate_loop import Proposal
from prefix_probe import compile_observed_prefix,assess_actual_reach
from value_policy import candidate,EmpiricalHorizonValue

class ContinualFeedbackAgent(InterventionExperienceLoop):
    def __init__(self,*args,feedback_enabled,learn_from_trials,trial_budget,private_plan_factory,private_context,**kwargs):
        self.feedback_enabled=feedback_enabled;self.learn_from_trials=learn_from_trials
        self.trial_budget=trial_budget;self.trial_tasks_used=0;self.feedback_queries=0
        self._private_plan_factory=private_plan_factory;self._private_context=private_context
        self._private_executor=None;self._pending_owned=()
        super().__init__(*args,diagnose=self._diagnose_visible,max_writes=1 if feedback_enabled else 0,
                         diagnostic_enabled=feedback_enabled,**kwargs)

    def diagnostic_account(self):
        return {'feedback_queries':self.feedback_queries,'trial_tasks_used':self.trial_tasks_used,
                'trial_task_budget':self.trial_budget,'feedback_enabled':self.feedback_enabled,
                'learn_from_trials':self.learn_from_trials}

    def _diagnose_visible(self,terminal,evidence,budget):
        proposal=candidate(evidence)
        if proposal is None:
            self._emit('NO_VISIBLE_MISMATCH_KEEP',{'terminal':terminal,'main_epoch':self._completed-1,'diagnostic_account':self.diagnostic_account()})
            return Proposal()
        if self.trial_tasks_used+2>self.trial_budget:
            self._emit('TRIAL_BUDGET_KEEP',{'main_epoch':self._completed-1,'diagnostic_account':self.diagnostic_account()})
            return Proposal()
        base=self.payload();prefix=compile_observed_prefix(evidence)
        self._emit('DIAGNOSTIC_INPUT',{'evidence':evidence,'post_TD':base,'candidate':proposal,'prefix':prefix})
        observed={};reaches={};owned=[]
        for name,prop in (('keep',Proposal()),('controller-delete',proposal)):
            with self._private_context(name):
                plan=self._private_plan_factory(evidence,prefix)
                source=self.issue_branch(prop,plan=plan,label=self.source_label+':main:'+str(self._completed-1)+':'+name)
                self._emit('PRIVATE_START',{'state':source.payload(),'parent':base,'n':1})
                self.trial_tasks_used+=1
                receipt=self._private_executor(source)
                observed[name]=(sum(float.fromhex(s['reward']['binary64_hex']) for s in receipt['trace']['steps']),)
                reaches[name]=assess_actual_reach(prefix,receipt['trace']);owned.append(source.owned_observation())
                self._emit('PRIVATE_COMPLETE',{'returns':observed[name],'state':source.payload(),'n':1,'first_task_target_reach':reaches[name]})
        self.feedback_queries+=1;value=EmpiricalHorizonValue(1);value.fit(observed)
        proper=all(v.reached for v in reaches.values());decision=value.choose() if proper else 'keep'
        self._pending_owned=tuple(owned)
        self._emit('PREFIX_DECISION',{'model':value,'observed':observed,'proper_target_comparison':proper,'target_reach':reaches,
             'choice':decision,'target_delta':value.values['controller-delete']-value.values['keep'] if proper else None,
             'diagnostic_account':self.diagnostic_account()})
        chosen=proposal if decision=='controller-delete' else Proposal()
        self._emit('SELECTED_FEEDBACK',{'proposal':chosen,'target_index':prefix.target_index})
        return chosen

    def run_observed_task(self,*,mask):
        # Environmental conditions are used only by the actual execution
        # transport. The diagnostic policy above has no mask/case input.
        self._pending_owned=()
        self._private_executor=lambda source:source.run_task(mask=mask)
        receipt=super().run_task(mask=mask)
        if self._pending_owned:
            observations=self._pending_owned;self._pending_owned=()
            if self.learn_from_trials:self.consume_owned_batch(observations)
            else:self._emit('TRIAL_OBSERVATIONS_NOT_LEARNED',{'observation_ids':[o.observation_id for o in observations],'state':self.payload()})
        self._private_executor=None
        self._emit('POST_OBSERVED_TASK',{'epoch':receipt['epoch'],'state':self.payload(),'diagnostic_account':self.diagnostic_account()})
        return receipt
