"""Physical receipts and candidate ownership include measurement semantics."""
from dataclasses import asdict
import hashlib,json
import torch
from feedback_program_v220.runtime import model_fingerprint
from feedback_program_v222.runtime import PracticeAgent as PreviousAgent
from .memory import MemoryBank
from .imagination import noise_tape,thought_record


def model_identity(model):
    payload={'weights':model_fingerprint(model),'schema':asdict(model.schema),'config':asdict(model.config),'layout':model.layout.to_dict()}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


class PracticeAgent(PreviousAgent):
    def __init__(self,model,namespace,rng,bank=None,thought_depth=3):
        bank=MemoryBank(model.schema,model.layout) if bank is None else bank
        if bank.layout!=model.layout:raise ValueError('Model and factual memory measurement semantics differ')
        super().__init__(model,namespace,rng,bank,thought_depth);self.version=model_identity(model)
    def assert_snapshot(self):
        if model_identity(self.model)!=self.version:raise ValueError('Weights or measurement semantics changed without replacing model')
    def replace_model(self,model):
        if model.schema!=self.bank.schema or model.layout!=self.bank.layout:raise ValueError('An observation-format change requires explicit memory conversion')
        version=model_identity(model)
        if version!=self.version:
            self.current_code=None;self.current_candidate=None
            for session in self.sessions.values():session.active=False
        self.model=model;self.version=version
    @torch.no_grad()
    def reflect(self,event,environment,budget):
        if not event.terminal or event.goal_met:return None
        session=self.new_session(event);codes=self.tensor([[c.code for c in session.arms]])
        for index in range(budget):
            output=self.infer(event.observation,event.goal,event.actions);evidence=self.evidence(session)
            tape=noise_tape(self.rng.randrange(2**31),self.thought_depth,self.model.config.hypotheses,self.model.schema.observation,self.model.innovations)
            thought=self.model.dream(output,codes,tape);tid=f'{self.namespace}/thought/{len(self.thoughts)}'
            self.thoughts.append(dict(thought_record(thought),id=tid,session_id=session.id,model_id=self.version,history_ids=tuple(self.bank.index),evidence_ids=evidence['ids']))
            logits,_=self.model.trial_logits_with_thought(output,codes,evidence,self.tensor([[float(budget-index),float(index)]]),thought)
            choice,propensity,policy=self.choose(logits)
            self.decisions.append({'kind':'trial_choice','session_id':session.id,'history_ids':tuple(self.bank.index),'evidence_ids':evidence['ids'],
                                   'model_id':self.version,'choice':choice,'propensity':propensity,'policy':policy,'remaining_budget':budget-index,'thought_id':tid})
            if choice==0:break
            self.trial(session,choice-1,environment)
        output=self.infer(event.observation,event.goal,event.actions);evidence=self.evidence(session);logits,state=self.model.adoption_logits(output,codes,evidence)
        choice,propensity,policy=self.choose(logits)
        self.decisions.append({'kind':'adoption','session_id':session.id,'history_ids':tuple(self.bank.index),'evidence_ids':evidence['ids'],'model_id':self.version,
                               'choice':choice,'propensity':propensity,'policy':policy,'counts':state['counts'][0].tolist(),
                               'contrast_mean':state['contrast_mean'][0].tolist(),'contrast_variance':state['contrast_variance'][0].tolist()})
        self.promote(session,choice);return session
