"""Finite trial-derived joint repair: failed practice proposes a new experiment.
One additional hypothesis here is a declared experimental budget, not a general search limit.
"""
from evidence_loop import EvidenceExperienceLoop
from candidate_loop import Proposal
from prefix_probe import compile_observed_prefix,assess_actual_reach
from value_policy import candidate

class TrialDerivedAgent(EvidenceExperienceLoop):
    def __init__(self,*args,algorithm,trial_budget,private_plan_factory,private_context,**kwargs):
        self.algorithm=algorithm;self.trial_budget=trial_budget;self.trial_tasks_used=0;self.base_queries=0;self.expanded_queries=0
        self._plan_factory=private_plan_factory;self._private_context=private_context;self._private_executor=None;self._pending_owned=()
        super().__init__(*args,diagnose=self._diagnose_visible,max_writes=0 if algorithm=='TaskTD' else 2,
                         diagnostic_enabled=algorithm!='TaskTD',**kwargs)

    def diagnostic_account(self):
        return {'algorithm':self.algorithm,'trial_tasks_used':self.trial_tasks_used,'trial_task_budget':self.trial_budget,
                'base_queries':self.base_queries,'expanded_queries':self.expanded_queries}

    def _diagnose_visible(self,terminal,evidence,budget):
        first=candidate(evidence)
        if first is None:
            self._emit('NO_VISIBLE_MISMATCH_KEEP',{'main_epoch':self._completed-1,'terminal':terminal,'diagnostic_account':self.diagnostic_account()});return Proposal()
        n=3 if self.algorithm=='HorizonSingle' else 1
        if self.trial_tasks_used+2*n>self.trial_budget:
            self._emit('TRIAL_BUDGET_KEEP',{'main_epoch':self._completed-1,'diagnostic_account':self.diagnostic_account()});return Proposal()
        base=self.payload();prefix=compile_observed_prefix(evidence)
        self._emit('DIAGNOSTIC_INPUT',{'evidence':evidence,'post_TD':base,'candidate':first,'prefix':prefix,'horizon':n})
        def run(name,proposal,view,count,greedy):
            pp=compile_observed_prefix(view)
            with self._private_context(name):
                plan=self._plan_factory(view,pp,count,greedy)
                source=self.issue_branch(proposal,plan=plan,label=self.source_label+':main:'+str(self._completed-1)+':'+name)
                self._emit('PRIVATE_START',{'state':source.payload(),'parent':base,'n':count,'probe_prefix':pp,'greedy':greedy});vals=[];obs=None
                for j in range(count):
                    self.trial_tasks_used+=1;r=self._private_executor(source);vals.append(sum(float.fromhex(s['reward']['binary64_hex']) for s in r['trace']['steps']))
                    if j==0:obs=source.owned_observation()
                assert source.owned_observation() is obs
                self._emit('PRIVATE_COMPLETE',{'returns':vals,'state':source.payload(),'n':count,'first_task_target_reach':assess_actual_reach(pp,source.task_receipts[0]['trace']),'observation_id':obs.observation_id})
                return vals,obs
        def choose(menu,observed):
            values={name:sum(v)/len(v) for name,v in observed.items()}
            chosen=min(menu,key=lambda name:(-values[name],len(menu[name].edits),name));return chosen,values
        menu={'keep':Proposal(),'first':first};observed={};owned=[]
        for name,proposal in menu.items():
            vals,obs=run(name,proposal,evidence,n,self.algorithm=='HorizonSingle');observed[name]=vals;owned.append(obs)
        self.base_queries+=1;selected,values=choose(menu,observed)
        self._emit('BASE_MENU_VALUE',{'menu':menu,'observed':observed,'values':values,'choice':selected,'horizon':n,'diagnostic_account':self.diagnostic_account()})
        if self.algorithm=='TrialExpanded' and owned[1].trace.outcome!='SUCCESS':
            derived=self.extend_from_failed_trial(owned[1])
            if derived is not None:
                joint,view=derived
                if self.trial_tasks_used+3<=self.trial_budget:
                    menu={'deep-keep':Proposal(),'deep-first':first,'joint':joint};observed={};owned=[]
                    for name,proposal in menu.items():
                        vals,obs=run(name,proposal,view,1,False);observed[name]=vals;owned.append(obs)
                    self.expanded_queries+=1;selected,values=choose(menu,observed)
                    self._emit('EXPANDED_MENU_VALUE',{'menu':menu,'observed':observed,'values':values,'choice':selected,'horizon':1,
                         'diagnostic_account':self.diagnostic_account(),'interpretation':'whole scripted task comparison; conditionalsecondsitecontrastdeep-first-vs-joint'})
                else:self._emit('EXPANSION_BUDGET_KEEP_BASE',{'diagnostic_account':self.diagnostic_account(),'joint_proposal':joint})
        assert self.payload()==base
        chosen=menu[selected];self._pending_owned=tuple(owned)
        self._emit('SELECTED_FEEDBACK',{'proposal':chosen,'choice':selected,'target_index':prefix.target_index,'diagnostic_account':self.diagnostic_account()})
        return chosen

    def run_observed_task(self,*,mask):
        self._pending_owned=();self._private_executor=lambda source:source.run_task(mask=mask)
        receipt=super().run_task(mask=mask)
        if self._pending_owned:
            obs=self._pending_owned;self._pending_owned=();self.consume_owned_batch(obs)
        self._private_executor=None
        self._emit('POST_OBSERVED_TASK',{'epoch':receipt['epoch'],'state':self.payload(),'diagnostic_account':self.diagnostic_account()})
        return receipt
