"""Versioned ordinary-experience consumer; condition on the own mechanisms actually consulted."""
from dataclasses import dataclass
from mechanism_loop import ObservationTaskLoop as NativeLoop,NativeTrialObservation,ProtocolError,EpisodeAdapter
from rfl_rebuild.env import kernel as K

@dataclass(frozen=True,slots=True)
class ObservationTransferResult:
    applied:bool
    reason:str
    observation_id:str
    mechanism_changes:tuple


def mechanism_changes(origin,current,observation):
    changes=[];base=observation.trace.base_option
    before=origin.process_overrides.get(base,base);after=current.process_overrides.get(base,base)
    if before!=after:changes.append({'channel':'P','address':base,'origin':before,'current':after})
    at=K.State(K.START[0],K.START[1],0,observation.episode.kappa,observation.episode.tape.phase)
    for step in observation.trace.steps:
        site=K.ControllerSite(at,step.a_cmd)
        before=origin.controller_overrides.get(site,site.cmd);after=current.controller_overrides.get(site,site.cmd)
        if before!=after:changes.append({'channel':'X','address':site,'origin':before,'current':after})
        at=step.state
    return tuple(changes)


class ConditionedObservationLoop(NativeLoop):
    def payload(self):
        result=super().payload();result['experience_condition_revision']='v147-consulted-own-PX-only'
        return result

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
            source._check()
            changes=mechanism_changes(source._immediate,self._current,observation)
            if changes:
                before=self.payload();self._consumed_observations.add(observation)
                receipt=ObservationTransferResult(False,'learner_mechanism_changed_on_observed_path',observation.observation_id,changes)
                self._emit('OBSERVATION_MECHANISM_REJECTED',{'receipt':receipt,'observation':observation.audit(),
                           'before':before,'after':self.payload(),'consumed_once':True,'ordinary_update_executed':False})
                return receipt
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
            return ObservationTransferResult(True,'same_learner_mechanism_on_observed_path',observation.observation_id,())
