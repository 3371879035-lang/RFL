"""Versioned v118 task loop: v117 semantics plus an explicit task-TD-only arm.

The previous executed module remains byte-unchanged. All ordinary update and
transaction semantics are transported literally; the added switch bypasses
failure diagnosis for the no-diagnostic baseline and developmental probes.
"""
from dataclasses import dataclass
from copy import deepcopy

import adaptive_training as A
import v105_normal_td as TD
from v105_normal_learning import CoordinateLearner, EpisodeAdapter
from orchestration import (BudgetView, DiagnosticResult, FailureOnlyOrchestrator,
                           ProtocolError, TaskObservation, TERMINALS, SUCCESS,
                           LearnerObservation, RouteRecord)
from rfl_rebuild.env import kernel as K
from rfl_rebuild.b2 import training as T
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.method.runner import make_evidence
from rfl_rebuild.learner.store import DECISION, Q, DecisionAddress, Edit


from candidate_loop import Proposal


@dataclass(frozen=True, eq=False, slots=True)
class NativeTrialObservation:
    issuer: object
    trace: K.RolloutTrace
    episode: EpisodeAdapter
    observation_id: str
    main_epoch: int

    def audit(self):
        return {'observation_id':self.observation_id,'issuer_label':self.issuer.source_label,
                'consumer_label':self.issuer._trial_receiver.source_label,'mode':self.issuer.mode,
                'main_epoch':self.main_epoch,'source_epoch':self.episode.epoch,
                'episode':A.wire(self.episode._input),'trace':A.wire(self.trace),
                'reference_digest':self.issuer.reference.digest()}


def observed_terminal(trace):
    if (type(trace) is not K.RolloutTrace or not trace.steps or
            trace.steps[-1].terminal is not True or
            type(trace.outcome) is not str or trace.outcome not in TERMINALS or
            trace.steps[-1].outcome != trace.outcome):
        raise ProtocolError('actual kernel trace lacks a consistent known terminal')
    return trace.outcome


class ObservationTaskLoop(CoordinateLearner):
    """Reuse the declared V0.3 ordinary learner, not serialized issued handles."""

    def __init__(self, *args, diagnose, max_writes, emit, diagnostic_enabled=True, **kwargs):
        self._external_updates=0
        super().__init__(*args, **kwargs)
        if not callable(diagnose) or not callable(emit):
            raise ProtocolError('diagnose and audit sink must be callable')
        if type(max_writes) is not int or max_writes < 0:
            raise ProtocolError('nonnegative diagnostic address budget required')
        self._diagnose, self._write_limit, self._emit = diagnose, max_writes, emit
        if type(diagnostic_enabled) is not bool:
            raise ProtocolError("diagnostic_enabled must be a bool")
        self._diagnostic_enabled = diagnostic_enabled
        self._last_evidence = None
        self.task_receipts = []
        self._failed = False
        self._active=False;self._trial_receiver=None;self._trial_registration=None
        self._issued_observation=None;self._registered_sources={};self._consumed_observations=set()
        self._registration_counter=0

    def payload(self):
        result=super().payload()
        result['external_updates']=self._external_updates
        result['observation_revision']='v142-complete-main-supplemental-observation'
        return result

    def _ordinary_update_from_trace(self,trace,episode):
        return self._update_from_observed_trace(trace,episode,advance_main=True)

    def register_trial_source(self,source):
        if (self._active or self._failed or not self.task_receipts or self._last_evidence is None
                or self.task_receipts[-1]['epoch']!=self._completed-1
                or self.task_receipts[-1]['terminal']==SUCCESS
                or type(source) is not ObservationTaskLoop or source._diagnostic_enabled
                or source._completed!=0 or source._attempted or source._failed
                or source._trial_receiver is not None):
            raise ProtocolError('supplemental source requires an actual completed main failure and fresh native branch')
        if source.mode!=self.mode or source.reference is not self.reference or source.plan.parameters!=self.plan.parameters:
            raise ProtocolError('trial mode/reference/parameters differ from consumer')
        own,branch=self.payload(),source.payload()
        if any(own[k]!=branch[k] for k in ('current','learning_values')):
            raise ProtocolError('trial source is not the actual post-TD R+L clone')
        self._registration_counter+=1
        registration={'id':self.source_label+':observation:'+str(self._registration_counter),
                      'main_epoch':self._completed-1,'kappa':self._last_evidence.kappa,
                      'phi':self._last_evidence.phi,'origin_L':own['learning_values']}
        source._trial_receiver=self;source._trial_registration=registration
        self._registered_sources[source]=registration
        self._emit('NATIVE_OBSERVATION_REGISTERED',{'observation_id':registration['id'],
                   'main_epoch':registration['main_epoch'],'consumer':own,'source_before':branch,
                   'source_label':source.source_label,'kappa':registration['kappa'],'phi':registration['phi'],
                   'registration_phase':'after-complete-main-failure'})

    def issued_observation(self):
        if self._failed or self._active or self._issued_observation is None:
            raise ProtocolError('partial/unissued trial has no consumable observation')
        return self._issued_observation

    def consume_trial_observation(self,observation):
        if type(observation) is not NativeTrialObservation:
            raise ProtocolError('native observation type required, not serialized trace data')
        if observation in self._consumed_observations:
            raise ProtocolError('native observation already consumed; no retry')
        source=observation.issuer;registration=self._registered_sources.get(source)
        if (registration is None or source._trial_receiver is not self or source._issued_observation is not observation
                or source._failed or source._active or self._active or self._failed):
            raise ProtocolError('observation issuer/consumer or completion binding invalid')
        if (observation.main_epoch!=registration['main_epoch'] or self._completed!=observation.main_epoch+1
                or not self.task_receipts or self.task_receipts[-1]['epoch']!=observation.main_epoch
                or type(observation.trace) is not K.RolloutTrace or type(observation.episode) is not EpisodeAdapter
                or observation.episode.plan is not source.plan or observation.episode.epoch!=0
                or observation.episode.kappa!=registration['kappa'] or observation.episode.tape.phase!=registration['phi']
                or source.mode!=self.mode or source.reference is not self.reference
                or source.plan.parameters!=self.plan.parameters or self.payload()['learning_values']!=registration['origin_L']):
            raise ProtocolError('observation chronology/protocol/current numeric root invalid')
        before=self.payload();self._consumed_observations.add(observation)
        self._emit('EXTERNAL_OBSERVATION_BEGIN',{'observation':observation.audit(),'before':before,
                   'external_update_index':self._external_updates,'main_clock_advanced':False})
        try:
            result=self._update_from_observed_trace(observation.trace,observation.episode,advance_main=False)
            self._external_updates+=1;result['after']=self.payload()
            assert result['after']['immediate']==before['immediate']
            assert result['after']['completed_episodes']==before['completed_episodes']
            assert result['after']['attempted_epochs']==before['attempted_epochs']
            self._emit('EXTERNAL_OBSERVATION_END',{'observation_id':observation.observation_id,
                       'external_update_index':self._external_updates-1,**result})
        except BaseException:
            self._failed=True
            raise

    def _update_from_observed_trace(self, trace, episode, *, advance_main):
        # Exact TD, effective/canonical Q and visited-existing-D semantics of
        # v105; only the rollout and update are split at an owned trace boundary.
        numeric = self._current if self.mode == 'dq' else self._values
        edits = TD.sweep_edits(numeric, trace, episode, protocol=self.plan.parameters,
                               q_reference=self.reference)
        candidate_numeric = numeric.clone()
        candidate_numeric.apply_transaction(edits, q_reference=self.reference)
        candidate_actor = self._current.clone() if self.mode == 'patch-adaptive' else candidate_numeric
        actor_edits = []
        if self.mode == 'patch-adaptive':
            improved, seen = candidate_numeric.snapshot().q_decision_provider(self.reference), set()
            for state, control, _result in TD.visited_order(
                    trace, kappa=episode.kappa, phi=episode.tape.phase):
                address = DecisionAddress(state, control.z, control.m)
                if address in self._current.decision_overrides and address not in seen:
                    actor_edits.append(Edit(DECISION, address, improved(state, control)))
                    seen.add(address)
            if actor_edits:
                candidate_actor.apply_transaction(tuple(actor_edits))
        self._current = candidate_actor
        self._values = candidate_numeric if self.mode == 'patch-adaptive' else None
        if advance_main:self._completed += 1
        return {'numeric_edits': A.wire(edits), 'policy_edits': A.wire(actor_edits),
                'after': self.payload()}

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
                for edit in proposal.edits:
                    if type(edit) is not Edit or edit.store != (Q if self.mode == 'dq' else DECISION):
                        raise ProtocolError('diagnostic writes outside selected decision channel')
                    owner = (DecisionAddress(edit.address.state, edit.address.z, edit.address.m)
                             if edit.store == Q else edit.address)
                    if owner not in visited:
                        raise ProtocolError('diagnostic address was not visited in actual evidence')
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
            if self._trial_receiver is not None:
                registration=self._trial_registration
                observation=NativeTrialObservation(self,trace,episode,registration['id'],registration['main_epoch'])
                self._issued_observation=observation
                self._emit('NATIVE_OBSERVATION_ISSUED',observation.audit())
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
