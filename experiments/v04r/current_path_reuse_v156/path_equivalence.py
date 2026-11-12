"""Current deterministic outcome equivalence; no desired-native trace is minted."""
from dataclasses import dataclass
from evidence_loop import A,K,T,ProtocolError
from v105_normal_learning import EngineeringPlan,EngineeringEpisode

@dataclass(frozen=True,slots=True)
class PathOutcomeEquivalence:
    equivalent:bool
    reason:str
    bindings:dict
    steps:tuple
    native_episode_input_equal:bool
    original_coordinate_calls:tuple

class CurrentPathProof:
    def path_equivalence(self,observation,desired,proposal,base):
        if not self._active or self._failed or type(desired) is not EngineeringPlan or len(desired.episodes)!=1:
            raise ProtocolError('current active deterministic engineering-plan proof only')
        reg=self._check_witness(observation);self._check_trial_plan_context(desired)
        source=observation.issuer;ep=desired.episodes[0]
        if type(ep) is not EngineeringEpisode:raise ProtocolError('literal episode DATA required')
        expected={k:list(v) for k,v in base['current'].items()};removed=[A.wire(e.address) for e in proposal.edits]
        expected['X']=[x for x in expected['X'] if x['address'] not in removed]
        bindings={'origin_R_equal':reg['source_I']==expected==A.stores(source._immediate),
            'origin_L_equal':reg['origin_L']==base['learning_values']==self.payload()['learning_values'],
            'proposal_equal':reg['proposal']==proposal,
            'same_current_complete_observation':source._owned_observation is observation and source._completed==1 and len(source.task_receipts)==1,
            'reference_identity_equal':source.reference is self.reference,'mode_role_equal':(source.mode,source.role)==(self.mode,self.role),
            'plan_protocol_equal':(source.plan.parameters,source.plan.evaluation_sample,source.plan.v_pre.hex(),source.plan.lock_digest,source.plan.grid)==(desired.parameters,desired.evaluation_sample,desired.v_pre.hex(),desired.lock_digest,desired.grid)}
        calls=tuple(observation.episode.calls);equal=observation.episode._input==ep;rows=[]
        def result(ok,reason):
            assert tuple(observation.episode.calls)==calls
            return PathOutcomeEquivalence(ok,reason,bindings,tuple(rows),equal,calls)
        if not all(bindings.values()):return result(False,'different_current_source_root_or_protocol')
        # Source and desired use the same fixed pre-rollout D/L selector.
        # Proposals only delete X; root check above proves D and numeric L identical.
        greedy=self._greedy();at=K.State(0,2,0,ep.kappa,ep.tape.phase);ctrl=K.initial_control(observation.trace.option_in_force)
        for i,actual in enumerate(observation.trace.steps):
            admissible=tuple(K.option_actions(ctrl.z,ctrl,at));coin=ep.coins[i];explore=T.is_explore(coin,desired.parameters.epsilon)
            coordinates=[(i,0,0,coin)]
            if explore:
                limit=(1<<64)-((1<<64)%len(admissible));cmd=None
                for j,value in enumerate(ep.rejections[i]):
                    coordinates.append((i,1,j,value))
                    if value<limit:cmd=admissible[value%len(admissible)];break
                if cmd is None:return result(False,'desired_literal_rejection_exhausted')
            else:cmd=greedy(at,ctrl)
            rows.append({'pre_state':at,'pre_control':ctrl,'actual_command':actual.a_cmd,'desired_command':cmd,
                'desired_explore':explore,'desired_coordinate_DATA':tuple(coordinates),'command_equal':cmd==actual.a_cmd})
            if cmd!=actual.a_cmd:return result(False,'desired_command_differs_on_actual_consumed_path')
            at,ctrl=actual.state,actual.control
        return result(True,'same_commands_inductively_same_deterministic_terminal_outcome')
