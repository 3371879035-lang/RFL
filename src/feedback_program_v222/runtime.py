"""Failure-only offline thoughts inform real practice, never replace its receipts."""
import torch
from feedback_program_v221.runtime import PracticeAgent as PreviousPracticeAgent
from .imagination import noise_tape,thought_record


class PracticeAgent(PreviousPracticeAgent):
    def __init__(self,model,namespace,rng,bank=None,thought_depth=3):
        super().__init__(model,namespace,rng,bank);self.thought_depth=thought_depth;self.thoughts=[]

    @torch.no_grad()
    def reflect(self,event,environment,budget):
        if not event.terminal or event.goal_met:return None
        session=self.new_session(event);codes=self.tensor([[c.code for c in session.arms]])
        for index in range(budget):
            output=self.infer(event.observation,event.goal,event.actions);evidence=self.evidence(session)
            tape=noise_tape(self.rng.randrange(2**31),self.thought_depth,self.model.config.hypotheses,
                            self.model.schema.observation,self.model.schema.feedback)
            thought=self.model.dream(output,codes,tape);tid=f'{self.namespace}/thought/{len(self.thoughts)}'
            self.thoughts.append(dict(thought_record(thought),id=tid,session_id=session.id,model_id=self.version,
                                      history_ids=tuple(self.bank.index),evidence_ids=evidence['ids']))
            logits,_=self.model.trial_logits_with_thought(output,codes,evidence,self.tensor([[float(budget-index),float(index)]]),thought)
            choice,propensity,policy=self.choose(logits)
            self.decisions.append({'kind':'trial_choice','session_id':session.id,'history_ids':tuple(self.bank.index),
                                   'evidence_ids':evidence['ids'],'model_id':self.version,'choice':choice,'policy':policy,
                                   'propensity':propensity,'remaining_budget':budget-index,'thought_id':tid})
            if choice==0:break
            self.trial(session,choice-1,environment)
        output=self.infer(event.observation,event.goal,event.actions);evidence=self.evidence(session)
        logits,state=self.model.adoption_logits(output,codes,evidence)
        choice,propensity,policy=self.choose(logits)
        self.decisions.append({'kind':'adoption','session_id':session.id,'history_ids':tuple(self.bank.index),
                               'evidence_ids':evidence['ids'],'model_id':self.version,'choice':choice,'policy':policy,'propensity':propensity,
                               'counts':state['counts'][0].cpu().tolist(),'contrast_mean':state['contrast_mean'][0].cpu().tolist(),
                               'contrast_variance':state['contrast_variance'][0].cpu().tolist()})
        self.promote(session,choice)
        return session
