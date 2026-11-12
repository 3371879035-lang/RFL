"""History learns how to query; only current actual trials authorize repair."""
from bound_agent import StrictTrialDerivedAgent
from candidate_loop import Proposal
from value_policy import candidate
from prefix_probe import compile_observed_prefix,assess_actual_reach
from program import PlannedProbeProgram
from evidence_loop import A

class ProgramMemoryAgent(StrictTrialDerivedAgent):
    def __init__(self,*args,initial_program,program_plan_factory,**kwargs):
        self.programs=[initial_program];self._program_plan_factory=program_plan_factory
        super().__init__(*args,**kwargs)

    def _reuse_check(self,observation,desired,proposal,base):
        # Validate the existing LIVE object, not a serialized restoration.
        reg=self._check_witness(observation);source=observation.issuer
        expected={k:list(v) for k,v in base['current'].items()}
        removed=[A.wire(e.address) for e in proposal.edits]
        expected['X']=[x for x in expected['X'] if x['address'] not in removed]
        return {'plan_type_equal':type(source.plan) is type(desired),
                'episodes_equal':source.plan.episodes==desired.episodes,
                'plan_protocol_equal':(source.plan.parameters,source.plan.evaluation_sample,source.plan.v_pre.hex(),source.plan.lock_digest,source.plan.grid)==(desired.parameters,desired.evaluation_sample,desired.v_pre.hex(),desired.lock_digest,desired.grid),
                'reference_identity_equal':source.reference is self.reference,
                'mode_role_equal':(source.mode,source.role)==(self.mode,self.role),
                'origin_R_equal':reg['source_I']==expected==A.stores(source._immediate),
                'origin_L_equal':reg['origin_L']==base['learning_values'],
                'same_current_observation':source._owned_observation is observation and source._completed==1 and len(source.task_receipts)==1,
                'proposal_equal':reg['proposal']==proposal}

    def _diagnose_visible(self,terminal,evidence,budget):
        first=candidate(evidence)
        if first is None:
            self._emit('NO_VISIBLE_MISMATCH_KEEP',{'main_epoch':self._completed-1,'terminal':terminal,'diagnostic_account':self.diagnostic_account()});return Proposal()
        if self.trial_tasks_used+2>self.trial_budget:
            self._emit('TRIAL_BUDGET_KEEP',{'main_epoch':self._completed-1,'diagnostic_account':self.diagnostic_account()});return Proposal()
        base=self.payload();prefix=compile_observed_prefix(evidence)
        self._emit('DIAGNOSTIC_INPUT',{'evidence':evidence,'post_TD':base,'candidate':first,'prefix':prefix,'horizon':1})
        selected_index=next((i for i in reversed(range(len(self.programs))) if self.programs[i].matches_first(evidence)),None)
        selected_program=self.programs[selected_index] if selected_index is not None else None
        self._emit('PROGRAM_SELECTED',{'program':selected_program,'program_version':selected_index,'matches_visible_first':selected_program is not None})
        def run(name,proposal,view,program=None):
            pp=None if program else compile_observed_prefix(view)
            with self._private_context(name):
                plan=self._program_plan_factory(view,program) if program else self._plan_factory(view,pp,1,False)
                source=self.issue_branch(proposal,plan=plan,label=self.source_label+':main:'+str(self._completed-1)+':'+name)
                self._emit('PRIVATE_START',{'state':source.payload(),'parent':base,'n':1,'probe_prefix':pp,'planned_program':program,'greedy':False,'plan_episodes':plan.episodes})
                self.trial_tasks_used+=1;r=self._private_executor(source);obs=source.owned_observation()
                vals=[sum(float.fromhex(s['reward']['binary64_hex']) for s in r['trace']['steps'])]
                self._emit('PRIVATE_COMPLETE',{'returns':vals,'state':source.payload(),'n':1,'first_task_target_reach':assess_actual_reach(pp,r['trace']) if pp else None,'observation_id':obs.observation_id})
                return vals,obs
        def choose(menu,observed):
            values={n:sum(v)/len(v) for n,v in observed.items()}
            return min(menu,key=lambda n:(-values[n],len(menu[n].edits),n)),values
        menu={'keep':Proposal(),'first':first};observed={};owned=[]
        for name,proposal in menu.items():
            vals,obs=run(name,proposal,evidence,selected_program);observed[name]=vals;owned.append(obs)
        self.base_queries+=1;selected,values=choose(menu,observed)
        self._emit('BASE_MENU_VALUE',{'menu':menu,'observed':observed,'values':values,'choice':selected,'horizon':1,'diagnostic_account':self.diagnostic_account()})
        if owned[1].trace.outcome!='SUCCESS':
            derived=self.extend_from_failed_trial(owned[1])
            if derived is not None:
                joint,view=derived;desired=self._plan_factory(view,compile_observed_prefix(view),1,False)
                checks=[self._reuse_check(o,desired,p,base) for o,p in zip(owned,(Proposal(),first))]
                reuse=all(all(v.values()) for v in checks)
                self._emit('CURRENT_PLAN_REUSE_CHECK',{'checks':checks,'reuse':reuse,'observation_ids':[o.observation_id for o in owned],'desired_episodes':desired.episodes,
                    'desired_protocol':{'parameters':desired.parameters,'sample':desired.evaluation_sample,'v_pre':desired.v_pre,'lock_digest':desired.lock_digest}})
                learned=PlannedProbeProgram.from_evidence(view);self.programs.append(learned)
                self._emit('PROGRAM_UPDATED',{'program':learned,'program_version':len(self.programs)-1,'witness_id':owned[1].observation_id,'independent_of_joint_reward':True})
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
                         'interpretation':'current exact-plan/source-root reuse only; aliases are not new observations'})
                else:self._emit('EXPANSION_BUDGET_KEEP_BASE',{'diagnostic_account':self.diagnostic_account(),'joint_proposal':joint})
        assert self.payload()==base
        chosen=menu[selected];self._pending_owned=tuple(owned)
        self._emit('SELECTED_FEEDBACK',{'proposal':chosen,'choice':selected,'target_index':prefix.target_index,'diagnostic_account':self.diagnostic_account()})
        return chosen
