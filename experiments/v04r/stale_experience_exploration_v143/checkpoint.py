"""Recorded ordinary model state, not a restored issued runtime handle."""
from dataclasses import dataclass
from copy import deepcopy
import hashlib,json
import adaptive_training as A
from rfl_rebuild.env import kernel as K
from rfl_rebuild.learner.store import (LearnerPersistentState,DecisionAddress,QAddress,Edit,DECISION,PROCESS,Q)

@dataclass(frozen=True,slots=True)
class RecordedOrdinaryCheckpoint:
    raw_sha256:str
    completed_main_tasks:int
    external_updates:int
    full_payload:dict

    @classmethod
    def read(cls,root,spec):
        p=root/spec['raw']['path'];data=p.read_bytes()
        assert len(data)==spec['raw']['bytes'] and hashlib.sha256(data).hexdigest()==spec['raw']['sha256']
        records=[json.loads(s) for s in data.decode('ascii').splitlines()]
        assert [x['seq'] for x in records]==list(range(len(records)))
        matches=[r['payload']['final_state'] for r in records if r['tag']==spec['selector']['tag'] and r['context'].get('arm')==spec['selector']['arm']]
        assert len(matches)==1
        p=matches[0];assert p['mode']=='patch-adaptive' and p['completed_episodes']==spec['recorded_completed_main_tasks'] and p['external_updates']==spec['recorded_external_updates']
        return cls(spec['raw']['sha256'],p['completed_episodes'],p['external_updates'],deepcopy(p))

    def materialize(self,reference):
        assert reference.digest()==self.full_payload['reference_digest']
        def store(wire):
            assert set(wire)=={'D','P','X','Q'} and wire['X']==[], 'checkpoint extent explicitly has no X overrides'
            def at(d):return K.State(**d)
            edits=[]
            for x in wire['D']:
                d=x['address'];edits.append(Edit(DECISION,DecisionAddress(at(d['state']),d['z'],d['m']),x['value']))
            for x in wire['P']:edits.append(Edit(PROCESS,x['address'],x['value']))
            for x in wire['Q']:
                d=x['address'];edits.append(Edit(Q,QAddress(at(d['state']),d['z'],d['m'],d['a']),float.fromhex(x['value']['binary64_hex'])))
            s=LearnerPersistentState();s.apply_transaction(tuple(edits),q_reference=reference)
            assert A.wire(A.stores(s))==wire
            return s
        return tuple(store(self.full_payload[k]) for k in ('immediate','current','learning_values'))


def initialize(loop_type,checkpoint,states,*,reference,plan,label,emit,diagnose):
    immediate,current,values=states
    loop=loop_type(immediate,mode='patch-adaptive',role='treatment',source_label=label,reference=reference,plan=plan,
                   diagnose=diagnose,max_writes=0,emit=emit,diagnostic_enabled=False)
    loop._current=current.clone();loop._values=values.clone();loop._check()
    p=loop.payload();old=checkpoint.full_payload
    assert all(A.wire(p[k])==old[k] for k in ('immediate','current','learning_values'))
    assert p['completed_episodes']==p['external_updates']==0 and p['attempted_epochs']==[]
    emit('CHECKPOINT_INITIALIZED',{'checkpoint_raw_sha256':checkpoint.raw_sha256,'recorded_main_tasks':checkpoint.completed_main_tasks,
         'recorded_external_updates':checkpoint.external_updates,'fresh_clock':True,'state':p})
    return loop
