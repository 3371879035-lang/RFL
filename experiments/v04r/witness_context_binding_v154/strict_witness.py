"""Narrow v153 trial-evidence admission to its actual current task context.
No change to candidate language, ordinary TD, source execution or atomic writes.
"""
from evidence_loop import EvidenceExperienceLoop,ProtocolError,EpisodeAdapter,K,A

class StrictWitnessLoop(EvidenceExperienceLoop):
    def _check_trial_plan_context(self,plan):
        if self._last_evidence is None or self._completed<1:
            raise ProtocolError('actual failedmain context required')
        source0=plan.episode(0);main=self.plan.episode(self._completed-1)
        if (type(source0) is not EpisodeAdapter or source0.plan is not plan or source0.epoch!=0
            or source0.kappa!=self._last_evidence.kappa or source0.tape.phase!=self._last_evidence.phi
            or (source0.kappa,source0.tape,source0.proposal)!=(main.kappa,main.tape,main.proposal)
            or plan.parameters!=self.plan.parameters):
            raise ProtocolError('trialcontext differsfromactualmainkappa/tape/proposal')
        return source0

    def issue_branch(self,proposal,*,plan,label):
        self._check_trial_plan_context(plan)
        return super().issue_branch(proposal,plan=plan,label=label)

    def _check_witness(self,observation):
        reg=super()._check_witness(observation);source=observation.issuer
        expected=self._check_trial_plan_context(source.plan);episode=observation.episode;trace=observation.trace
        if (type(episode) is not EpisodeAdapter or episode.plan is not source.plan or episode.epoch!=0
            or episode._input is not expected._input or episode.kappa!=reg['kappa'] or episode.tape.phase!=reg['phi']
            or (episode.kappa,episode.tape,episode.proposal)!=(expected.kappa,expected.tape,expected.proposal)
            or observation.observation_id!=reg['id'] or A.stores(source._immediate)!=reg['source_I']
            or type(trace) is not K.RolloutTrace or not trace.steps or source._completed<1
            or not trace.steps[-1].terminal or trace.outcome!=trace.steps[-1].outcome
            or trace.base_option!=episode.proposal
            or any((s.state.kappa,s.state.phi)!=(episode.kappa,episode.tape.phase) for s in trace.steps)):
            raise ProtocolError('ownedwitness episode/trace/registration context mismatch')
        return reg
