"""New intervention-origin observations and once-only ordinary TD batches.
Native source task body is v144 literally except the explicit new nominal issue block.
"""
from dataclasses import dataclass
from copy import deepcopy
from mechanism_loop import (ObservationTaskLoop as NativeLoop,EpisodeAdapter,ProtocolError,observed_terminal,
    TD,T,A,K,make_evidence,learner_rows,DecisionAddress,Edit,CONTROLLER,LearnerPersistentState,
    FailureOnlyOrchestrator,TaskObservation,BudgetView,DiagnosticResult,LearnerObservation,RouteRecord,SUCCESS)
from candidate_loop import Proposal
from conditioned_experience import mechanism_changes

@dataclass(frozen=True,eq=False,slots=True)
class OwnedTrialObservation:
    issuer: object
    trace: K.RolloutTrace
    episode: EpisodeAdapter
    observation_id: str
    main_epoch: int
    def audit(self):
        return {'observation_id':self.observation_id,'issuer_label':self.issuer.source_label,
                'consumer_label':self.issuer._owned_receiver.source_label,'mode':self.issuer.mode,
                'main_epoch':self.main_epoch,'source_epoch':self.episode.epoch,
                'episode':A.wire(self.episode._input),'trace':A.wire(self.trace),
                'reference_digest':self.issuer.reference.digest(),'observation_revision':'v151-native-intervention-origin'}

@dataclass(frozen=True,slots=True)
class BatchTransferReceipt:
    applied: bool
    reason: str
    observation_id: str
    mechanism_changes: tuple

class OwnedInterventionSource(NativeLoop):
    def owned_observation(self):
        if self._failed or self._active or self._owned_observation is None:
            raise ProtocolError('partial or unissued new trial observation')
        return self._owned_observation

    def run_task(self, *, mask=K.FaultMask()):
        """No supplied terminal/trace; one consumed chronological task, no retry."""
        if self._failed:
            raise ProtocolError('partial task loop is closed; no retry')
        episode = self.plan.episode(self._completed)
        if type(episode) is not EpisodeAdapter or episode.epoch in self._attempted:
            raise ProtocolError('task epoch already consumed; no retry')
        if type(mask) is not K.FaultMask:
            raise ProtocolError('nominal environment mask required')
        self._attempted.add(episode.epoch)
        before = self.payload()
        counters = {'ordinary_updates': 0, 'diagnostic_calls': 0, 'query_calls': 0,
                    'diagnostic_transactions': 0, 'diagnostic_edit_addresses': 0}
        pending = {'ordinary': None, 'proposal': None, 'trace': None}
        snap, greedy, draws = self._current.snapshot(), self._greedy(), []

        def provider(state, control):
            i = len(draws)
            admissible = tuple(K.option_actions(control.z, control, state))
            explore = T.is_explore(episode.coin(i), self.plan.parameters.epsilon)
            action = TD.uniform_action(episode, i, admissible) if explore else greedy(state, control)
            draws.append({'i': i, 'explore': explore, 'admissible': list(admissible), 'a_cmd': action})
            return action

        self._active=True
        try:
            self._emit('TASK_BEGIN', {'epoch': episode.epoch, 'before': before,
                       'episode': A.wire(episode._input), 'environment_mask_audit_only': A.wire(mask)})
            trace = K.rollout(kappa=episode.kappa, tape=episode.tape, base_option=episode.proposal,
                              command_provider=provider, controller=snap.controller_mapping(),
                              learner_process_commit=snap.process_commit_provider(), mask=mask,
                              reward_mode='A')
            pending['trace'] = trace
            self._emit('TASK_RAW', {'epoch': episode.epoch, 'trace': A.wire(trace),
                       'return_hex': trace.return_value.hex(), 'draws': draws,
                       'coordinates': A.wire(episode.calls)})
            terminal = observed_terminal(trace)
            evidence = None if terminal == SUCCESS else make_evidence(
                learner_rows(trace, episode.kappa, episode.tape.phase), trace.option_in_force,
                episode.kappa, episode.tape.phase)
            self._last_evidence = evidence
            visited = {DecisionAddress(s, ctrl.z, ctrl.m) for s, ctrl, _ in
                       TD.visited_order(trace, kappa=episode.kappa, phi=episode.tape.phase)}

            def ordinary(obs):
                if obs.terminal != terminal or hasattr(obs, 'evaluator_metadata'):
                    raise ProtocolError('ordinary input differs from actual task view')
                counters['ordinary_updates'] += 1
                pending['ordinary'] = self._ordinary_update_from_trace(trace, episode)
                self._emit('ORDINARY_UPDATE', pending['ordinary'])

            def diagnose(term, visible, budget):
                if term != terminal or terminal == SUCCESS or type(budget) is not BudgetView:
                    raise ProtocolError('invalid diagnostic route')
                state_before = self.payload()
                counters['diagnostic_calls'] += 1
                self._emit('DIAGNOSE_BEGIN', {'terminal': term, 'evidence': A.wire(visible),
                           'budget': A.wire(budget), 'state_before': state_before})
                proposal = self._diagnose(term, visible, budget)
                self._emit('DIAGNOSE_RETURN', {'proposal': A.wire(proposal)})
                if self.payload() != state_before:
                    raise ProtocolError('diagnostician changed learner outside executor')
                if type(proposal) is not Proposal or type(proposal.edits) is not tuple:
                    raise ProtocolError('typed structured diagnostic proposal required')
                if proposal.action not in ('keep', 'apply'):
                    raise ProtocolError('unknown diagnostic action')
                if proposal.action == 'keep' and proposal.edits:
                    raise ProtocolError('keep cannot contain edits')
                if proposal.action == 'apply' and not proposal.edits:
                    raise ProtocolError('apply must name at least one local edit')
                sites={K.ControllerSite(state,step.a_cmd) for state,control,step in TD.visited_order(trace,kappa=episode.kappa,phi=episode.tape.phase)}
                for edit in proposal.edits:
                    if type(edit) is not Edit or edit.store!=CONTROLLER or type(edit.address) is not K.ControllerSite or edit.value is not None:
                        raise ProtocolError('new executor only permits typed observed-site controller deletion')
                    if edit.address not in sites:
                        raise ProtocolError('controller site was not consulted in actual main factual')
                pending['proposal'] = proposal
                return DiagnosticResult(proposal.action, query_cost=0, write_cost=len(proposal.edits),
                                        payload=proposal)

            def apply(result):
                proposal = result.payload
                candidate = self._current.clone()
                self._emit('DIAGNOSTIC_TX_BEGIN', {'before': self.payload(),
                           'edits': A.wire(proposal.edits)})
                # One actual transaction. The original store validates domains,
                # duplicate addresses, legal D actions and exact Q canonicalization.
                candidate.apply_transaction(proposal.edits, q_reference=self.reference)
                self._current = candidate
                self._ordinary_channels={k:deepcopy(A.stores(candidate)[k]) for k in ('P','X')}
                counters['diagnostic_transactions'] += 1
                counters['diagnostic_edit_addresses'] += len(proposal.edits)
                self._check()
                self._emit('DIAGNOSTIC_TX_END', {'after': self.payload()})

            router = FailureOnlyOrchestrator(ordinary, diagnose, apply,
                                             max_queries=0, max_writes=self._write_limit)
            if self._diagnostic_enabled:
                route = router.run(TaskObservation(terminal, evidence))
            else:
                ordinary(LearnerObservation(terminal, evidence))
                route = RouteRecord(terminal, "TASK_ONLY", True, 0, 0, 0, "none")
            if route.write_spend != counters['diagnostic_edit_addresses']:
                raise ProtocolError('declared and executed diagnostic writes differ')
            receipt = {'epoch': episode.epoch, 'terminal': terminal, 'route': A.wire(route),
                       'counters': dict(counters), 'before': before, 'after': self.payload(),
                       'ordinary_after': pending['ordinary']['after'],
                       'trace': A.wire(trace), 'coordinates': A.wire(episode.calls)}
            self.task_receipts.append(deepcopy(receipt))
            self._emit('TASK_COMPLETE', receipt)
            if episode.epoch==0:
                observation=OwnedTrialObservation(self,trace,episode,self._owned_id,self._owned_main_epoch)
                self._owned_observation=observation
                self._emit('OWNED_OBSERVATION_ISSUED',observation.audit())
            return receipt
        except BaseException as error:
            self._failed = True
            self._emit('TASK_PARTIAL', {'epoch': episode.epoch, 'error_type': type(error).__name__,
                       'error': str(error), 'ordinary_committed': pending['ordinary'] is not None,
                       'counters': dict(counters), 'after': self.payload(),
                       'complete_task_receipt': False})
            raise

        finally:
            self._active=False

class InterventionExperienceLoop(NativeLoop):
    def __init__(self,*args,**kwargs):
        self._owned_registry={};self._owned_consumed=set();self._owned_counter=0
        super().__init__(*args,**kwargs)
    def payload(self):
        p=super().payload();p['experience_revision']='v151-intervention-origin-batch';return p

    def issue_branch(self,proposal,*,plan,label):
        if not self._active or self._failed or self._last_evidence is None or type(proposal) is not Proposal:
            raise ProtocolError('new branch requires active genuine failed main diagnosis')
        if plan.parameters!=self.plan.parameters:raise ProtocolError('ordinary parameters changed')
        sites={K.ControllerSite(K.State(s.x,s.y,s.t,s.kappa,s.phi),s.a_cmd) for s in self._last_evidence.steps}
        if proposal.action not in ('keep','apply') or (proposal.action=='keep')!=(not bool(proposal.edits)):
            raise ProtocolError('new source proposal is not keep or one actual local delete')
        for e in proposal.edits:
            if type(e) is not Edit or e.store!=CONTROLLER or e.value is not None or e.address not in sites:
                raise ProtocolError('new source edit must delete an actually consulted own controller site')
        if len(proposal.edits)>1:raise ProtocolError('finite local source edit extent exceeded')
        before=self.payload();initial=self._current.clone()
        if proposal.edits:
            old=A.stores(initial);initial.apply_transaction(proposal.edits,q_reference=self.reference)
            self._emit('OWNED_BRANCH_EDIT',{'before':old,'edits':proposal.edits,'after':A.stores(initial)})
        def no_diagnosis(*args):raise AssertionError('private source diagnosis forbidden')
        branch=OwnedInterventionSource(initial,mode=self.mode,role=self.role,source_label=label,reference=self.reference,
            plan=plan,diagnose=no_diagnosis,max_writes=0,emit=self._emit,diagnostic_enabled=False)
        branch._values=self._values.clone();branch._check();self._owned_counter+=1
        oid=self.source_label+':owned:'+str(self._owned_counter)
        branch._owned_receiver=self;branch._owned_id=oid;branch._owned_main_epoch=self._completed-1;branch._owned_observation=None
        registration={'ordinal':self._owned_counter,'id':oid,'main_epoch':self._completed-1,'origin_L':before['learning_values'],
            'kappa':self._last_evidence.kappa,'phi':self._last_evidence.phi,'source_I':A.stores(initial)}
        self._owned_registry[branch]=registration
        self._emit('OWNED_BRANCH_REGISTERED',{'registration':registration,'consumer':before,'source_before':branch.payload(),'proposal':proposal})
        return branch

    def consume_owned_batch(self,observations):
        if type(observations) is not tuple or not observations or len(set(observations))!=len(observations):
            raise ProtocolError('nonempty unique ordered owned observation batch required')
        if self._active or self._failed:raise ProtocolError('main must be complete and open')
        before=self.payload();ordinals=[]
        for obs in observations:
            if type(obs) is not OwnedTrialObservation or obs in self._owned_consumed:
                raise ProtocolError('new owned type required and already consumed batch cannot retry')
            source=obs.issuer;reg=self._owned_registry.get(source)
            if (reg is None or type(source) is not OwnedInterventionSource or source._owned_receiver is not self
                or source._owned_observation is not obs or source._failed or source._active
                or obs.observation_id!=reg['id'] or obs.main_epoch!=reg['main_epoch'] or self._completed!=obs.main_epoch+1
                or type(obs.trace) is not K.RolloutTrace or type(obs.episode) is not EpisodeAdapter
                or obs.episode.plan is not source.plan or obs.episode.epoch!=0
                or obs.episode.kappa!=reg['kappa'] or obs.episode.tape.phase!=reg['phi']
                or source.reference is not self.reference or source.mode!=self.mode or source.role!=self.role
                or source.plan.parameters!=self.plan.parameters or before['learning_values']!=reg['origin_L']):
                raise ProtocolError('actual intervention source, chronology, plan or common numeric root differs')
            source._check()
            if A.stores(source._immediate)!=reg['source_I']:raise ProtocolError('source immediate origin changed')
            ordinals.append(reg['ordinal'])
        if ordinals!=sorted(ordinals):raise ProtocolError('batch must use declared source registration order')
        self._owned_consumed.update(observations)
        self._emit('OWNED_BATCH_BEGIN',{'before':before,'observations':[o.audit() for o in observations],'ordinals':ordinals,'all_consumed_before_TD':True})
        receipts=[]
        try:
            for obs in observations:
                diff=mechanism_changes(obs.issuer._immediate,self._current,obs);pre=self.payload()
                if diff:
                    receipt=BatchTransferReceipt(False,'current_mechanism_differs_on_observed_path',obs.observation_id,diff)
                    self._emit('OWNED_OBSERVATION_REJECTED',{'observation':obs.audit(),'receipt':receipt,'before':pre,'after':self.payload()})
                else:
                    self._emit('OWNED_EXTERNAL_BEGIN',{'observation':obs.audit(),'before':pre,'external_update_index':self._external_updates,'main_clock_advanced':False})
                    result=self._update_from_observed_trace(obs.trace,obs.episode,advance_main=False)
                    self._external_updates+=1;result['after']=self.payload()
                    assert result['after']['immediate']==pre['immediate'] and result['after']['completed_episodes']==pre['completed_episodes'] and result['after']['attempted_epochs']==pre['attempted_epochs']
                    receipt=BatchTransferReceipt(True,'same_mechanism_on_observed_path',obs.observation_id,())
                    self._emit('OWNED_EXTERNAL_END',{'observation_id':obs.observation_id,'receipt':receipt,**result})
                receipts.append(receipt)
            self._emit('OWNED_BATCH_END',{'receipts':receipts,'before':before,'after':self.payload()})
        except BaseException:
            self._failed=True;raise
        return tuple(receipts)
