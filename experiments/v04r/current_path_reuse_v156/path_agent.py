"""Avoid redundant current trials; do not use historical query programs."""
from bound_agent import StrictTrialDerivedAgent
from candidate_loop import Proposal
from value_policy import candidate
from prefix_probe import compile_observed_prefix,assess_actual_reach
from path_equivalence import CurrentPathProof
from dataclasses import replace
from evidence_loop import A

class PathwiseAgent(CurrentPathProof,StrictTrialDerivedAgent):
    def _diagnose_visible(self,terminal,evidence,budget):
        first=candidate(evidence)
        if first is None:
            self._emit('NO_VISIBLE_MISMATCH_KEEP',{'main_epoch':self._completed-1,'terminal':terminal,'diagnostic_account':self.diagnostic_account()});return Proposal()
        if self.trial_tasks_used+2>self.trial_budget:
            self._emit('TRIAL_BUDGET_KEEP',{'main_epoch':self._completed-1,'diagnostic_account':self.diagnostic_account()});return Proposal()
        base=self.payload();prefix=compile_observed_prefix(evidence)
        self._emit('DIAGNOSTIC_INPUT',{'evidence':evidence,'post_TD':base,'candidate':first,'prefix':prefix,'horizon':1})
        def run(name,proposal,view):
            pp=compile_observed_prefix(view)
            with self._private_context(name):
                plan=self._plan_factory(view,pp,1,False)
                source=self.issue_branch(proposal,plan=plan,label=self.source_label+':main:'+str(self._completed-1)+':'+name)
                self._emit('PRIVATE_START',{'state':source.payload(),'parent':base,'n':1,'probe_prefix':pp,'greedy':False,'plan_episodes':plan.episodes})
                self.trial_tasks_used+=1;r=self._private_executor(source);obs=source.owned_observation()
                vals=[sum(float.fromhex(s['reward']['binary64_hex']) for s in r['trace']['steps'])]
                self._emit('PRIVATE_COMPLETE',{'returns':vals,'state':source.payload(),'n':1,'first_task_target_reach':assess_actual_reach(pp,r['trace']),'observation_id':obs.observation_id})
                return vals,obs
        def choose(menu,observed):
            values={n:sum(v)/len(v) for n,v in observed.items()}
            return min(menu,key=lambda n:(-values[n],len(menu[n].edits),n)),values
        menu={'keep':Proposal(),'first':first};observed={};owned=[]
        for name,proposal in menu.items():
            vals,obs=run(name,proposal,evidence);observed[name]=vals;owned.append(obs)
        self.base_queries+=1;selected,values=choose(menu,observed)
        self._emit('BASE_MENU_VALUE',{'menu':menu,'observed':observed,'values':values,'choice':selected,'horizon':1,'diagnostic_account':self.diagnostic_account()})
        if owned[1].trace.outcome!='SUCCESS':
            derived=self.extend_from_failed_trial(owned[1])
            if derived is not None:
                joint,view=derived;desired=self._plan_factory(view,compile_observed_prefix(view),1,False)
                proofs=[self.path_equivalence(o,desired,p,base) for o,p in zip(owned,(Proposal(),first))]
                reuse=all(p.equivalent for p in proofs)
                self._emit('CURRENT_PATH_EQUIVALENCE',{'proofs':proofs,'reuse':reuse,'observation_ids':[o.observation_id for o in owned],
                    'desired_episodes':desired.episodes,'desired_protocol':{'parameters':desired.parameters,'sample':desired.evaluation_sample,'v_pre':desired.v_pre,'lock_digest':desired.lock_digest}})
                if self._completed==1:
                    # A real counterfactual-plan rejection using this genuine live source.
                    # It does not execute the bad plan or fabricate an observation.
                    ep=desired.episodes[0];chi=list(ep.rejections);chi[0]=(0,)
                    bad=replace(desired,episodes=(replace(ep,rejections=tuple(chi)),))
                    rejected=self.path_equivalence(owned[0],bad,Proposal(),base)
                    self._emit('CONSUMED_COMMAND_CHANGE_REJECTED',{'proof':rejected,'observation_id':owned[0].observation_id,'desired_episodes':bad.episodes})
                    assert not rejected.equivalent
                needed=1 if reuse else 3
                if self.trial_tasks_used+needed<=self.trial_budget:
                    initial_values,initial_owned=observed,owned
                    menu={'deep-keep':Proposal(),'deep-first':first,'joint':joint};observed={};owned=[]
                    aliases={'deep-keep':'keep','deep-first':'first'} if reuse else {}
                    if reuse:
                        observed.update({'deep-keep':initial_values['keep'],'deep-first':initial_values['first']});owned.extend(initial_owned)
                    for name,proposal in menu.items():
                        if name in aliases:continue
                        vals,obs=run(name,proposal,view);observed[name]=vals;owned.append(obs)
                    self.expanded_queries+=1;selected,values=choose(menu,observed)
                    self._emit('EXPANDED_MENU_VALUE',{'menu':menu,'observed':observed,'values':values,'choice':selected,'horizon':1,'live_aliases':aliases,'diagnostic_account':self.diagnostic_account(),
                         'interpretation':'current deterministic same-command/source-root outcome reuse only; aliases are not new observations'})
                else:self._emit('EXPANSION_BUDGET_KEEP_BASE',{'diagnostic_account':self.diagnostic_account(),'joint_proposal':joint})
        assert self.payload()==base
        chosen=menu[selected];self._pending_owned=tuple(owned)
        self._emit('SELECTED_FEEDBACK',{'proposal':chosen,'choice':selected,'target_index':prefix.target_index,'diagnostic_account':self.diagnostic_account()})
        return chosen
