"""Learned candidate decisions coupled to actual, explicitly costed practice.

The environment callback is outside the neural model. It must return observed
consequences, not labels for unexecuted actions. Eligibility is a provenance
boundary; no hand-coded success/improvement threshold chooses adoption.
"""
from dataclasses import asdict,dataclass
import hashlib,json
import torch
from .memory import Event,ImaginedTransition,MemoryBank


def model_fingerprint(model):
    h=hashlib.sha256()
    for name,tensor in model.state_dict().items():
        h.update(name.encode());h.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


@dataclass(frozen=True)
class Candidate:
    id: str
    code: tuple
    model_id: str
    source_event_id: str
    history_ids: tuple

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class PracticeReceipt:
    candidate_id: str
    candidate_digest: str
    model_id: str
    event_id: str


class PracticeAgent:
    def __init__(self,model,namespace,rng,bank=None):
        self.model=model;self.namespace=namespace;self.rng=rng
        self.bank=MemoryBank(model.schema) if bank is None else bank
        self.current_code=None;self.current_candidate=None
        self.candidates={};self.receipts={};self.decisions=[]
        self.counters={'tasks':0,'trials':0,'reflections':0,'adoptions':0,'imagined':0}

    def tensor(self,value):
        p=next(self.model.parameters())
        return torch.tensor(value,dtype=p.dtype,device=p.device)

    def infer(self,observation,goal,actions,code=None):
        if code is None:code=self.current_code
        return self.model(self.tensor([observation]),self.tensor([goal]),self.tensor([actions]),self.bank.view(),
                          None if code is None else self.tensor([code]))

    def choose(self,logits):
        probabilities=torch.softmax(logits.detach(),-1).cpu()[0].tolist()
        pick=self.rng.choices(range(len(probabilities)),weights=probabilities,k=1)[0]
        return pick,probabilities[pick],probabilities

    @torch.no_grad()
    def execute(self,observation,goal,actions,environment,role='task',candidate=None,episode=None,step=0,previous_id=None):
        if role=='trial' and candidate is None:raise ValueError('A trial names its proposed candidate')
        current=model_fingerprint(self.model)
        if candidate is not None:
            if self.candidates.get(candidate.id)!=candidate or candidate.model_id!=current:
                raise ValueError('Trial candidate or model snapshot does not match its proposal')
        out=self.infer(observation,goal,actions,None if candidate is None else candidate.code)
        history_ids=tuple(self.bank.index)
        action,propensity,policy=self.choose(out['logits'])
        # Only this call interacts with the environment. No hidden kernel is passed to the network.
        result=environment(action)
        event_id=f'{self.namespace}/event/{len(self.bank.events)}'
        event=Event(id=event_id,episode=episode or event_id,step=step,observation=tuple(observation),actions=tuple(actions),
                    action_index=action,next_observation=tuple(result['next_observation']),feedback=tuple(result['feedback']),
                    feedback_mask=tuple(result['feedback_mask']),goal=tuple(goal),
                    predicted_feedback=tuple(out['feedback_prediction'][0,action].cpu().tolist()),
                    predicted_mask=(True,)*self.model.schema.feedback,propensity=propensity,
                    goal_met=bool(result['goal_met']),terminal=bool(result['terminal']),cost=float(result['cost']),
                    source='environment',role=role,previous_id=previous_id,
                    candidate_id=candidate.id if candidate else self.current_candidate,model_id=current)
        self.bank.add(event);self.counters['trials' if role=='trial' else 'tasks']+=1
        if role=='trial':
            self.receipts[candidate.id]=PracticeReceipt(candidate.id,candidate.digest,current,event_id)
        self.decisions.append({'kind':role,'event_id':event_id,'action':action,'policy':policy,'propensity':propensity,
                               'model_id':current,'history_ids':history_ids,'code':None if candidate is None and self.current_code is None else
                               list(candidate.code if candidate else self.current_code)})
        return event

    @torch.no_grad()
    def propose(self,event):
        if self.bank.events[self.bank.index[event.id]]!=event:raise ValueError('Proposal requires this agent\'s observed event')
        if event.goal_met:raise ValueError('Success uses ordinary learning, not failure reflection')
        out=self.infer(event.observation,event.goal,event.actions)
        codes=self.model.propose(out)[0].cpu().tolist();current=model_fingerprint(self.model)
        proposed=[]
        for code in codes:
            candidate=Candidate(f'{self.namespace}/candidate/{len(self.candidates)}',tuple(code),current,event.id,tuple(self.bank.index))
            self.candidates[candidate.id]=candidate;proposed.append(candidate)
        self.counters['reflections']+=1
        return out,tuple(proposed)

    def trial_summary(self,candidate):
        receipt=self.receipts[candidate.id];event=self.bank.events[self.bank.index[receipt.event_id]]
        return [*(v if m else 0. for v,m in zip(event.feedback,event.feedback_mask)),*map(float,event.feedback_mask),
                float(event.goal_met),event.cost,1.]

    def promote(self,candidate):
        receipt=self.receipts.get(candidate.id)
        if self.candidates.get(candidate.id)!=candidate or receipt is None:
            raise ValueError('Untested or changed candidate cannot be adopted')
        current=model_fingerprint(self.model)
        if receipt.candidate_digest!=candidate.digest or receipt.model_id!=current or candidate.model_id!=current:
            raise ValueError('Candidate, actual practice, and current model snapshot must match')
        event=self.bank.events[self.bank.index[receipt.event_id]]
        if event.role!='trial' or event.candidate_id!=candidate.id or event.model_id!=current:
            raise ValueError('Adoption lacks a matching factual trial')
        self.current_code=candidate.code;self.current_candidate=candidate.id;self.counters['adoptions']+=1

    @torch.no_grad()
    def reflect(self,event,environment,remaining_trials):
        if event.goal_met:return None
        out,candidates=self.propose(event)
        codes=self.tensor([[c.code for c in candidates]])
        logits=self.model.trial_logits(out,codes,self.tensor([[float(remaining_trials),event.cost]]))
        if remaining_trials<=0:logits[:,1:]=-torch.inf
        choice,propensity,policy=self.choose(logits)
        decision={'kind':'trial_choice','source_event_id':event.id,'candidate_ids':[c.id for c in candidates],
                  'history_ids':tuple(self.bank.index),'model_id':candidates[0].model_id,
                  'eligible':[remaining_trials>0]*len(candidates),'choice':choice,'policy':policy,'propensity':propensity}
        self.decisions.append(decision)
        if choice==0:return None
        candidate=candidates[choice-1]
        trial=self.execute(event.observation,event.goal,event.actions,environment,'trial',candidate)
        eligible=[c.id in self.receipts for c in candidates]
        summaries=[self.trial_summary(c) if ok else [0.]*(2*self.model.schema.feedback+3) for c,ok in zip(candidates,eligible)]
        post=self.infer(event.observation,event.goal,event.actions)
        logits=self.model.adoption_logits(post,codes,self.tensor([summaries]),torch.tensor([eligible],device=codes.device))
        adoption,propensity,policy=self.choose(logits)
        self.decisions.append({'kind':'adoption','source_event_id':event.id,'candidate_ids':[c.id for c in candidates],
                               'history_ids':tuple(self.bank.index),'model_id':candidate.model_id,
                               'eligible':eligible,'trial_summaries':summaries,'choice':adoption,'policy':policy,'propensity':propensity})
        if adoption:self.promote(candidates[adoption-1])
        return trial

    @torch.no_grad()
    def imagine(self,observation,goal,actions,action_index):
        out=self.infer(observation,goal,actions);self.counters['imagined']+=1
        def variance(prefix):
            means=out[prefix+'_mean'][0,:,action_index];var=out[prefix+'_variance'][0,:,action_index]
            weights=out['weights'][0,:,None];average=(weights*means).sum(0)
            return tuple((weights*(var+(means-average).square())).sum(0).cpu().tolist())
        return ImaginedTransition(tuple(observation),tuple(actions[action_index]),
                                 tuple(out['next_prediction'][0,action_index].cpu().tolist()),
                                 tuple(out['feedback_prediction'][0,action_index].cpu().tolist()),
                                 tuple(self.bank.index),model_fingerprint(self.model),variance('next'),variance('feedback'))
