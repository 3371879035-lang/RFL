"""Failure-session practice with retained, arm-specific actual trials.

Task facts, practice facts, work nodes, and proposed controls remain distinct.
The learned policy can stop, repeat an arm, or test the current behavior.
"""
from dataclasses import asdict,dataclass,field
import torch
from feedback_program_v220.runtime import Candidate,model_fingerprint
from feedback_program_v220.memory import ImaginedTransition
from .memory import Event,MemoryBank


@dataclass(frozen=True)
class TrialReceipt:
    event_id: str
    session_id: str
    arm: int
    candidate_id: str
    candidate_digest: str
    model_id: str


@dataclass
class PracticeSession:
    id: str
    source_event_id: str
    arms: tuple
    model_id: str
    receipts: list = field(default_factory=list)
    active: bool = True


class PracticeAgent:
    def __init__(self,model,namespace,rng,bank=None):
        self.model=model;self.namespace=namespace;self.rng=rng
        self.bank=MemoryBank(model.schema) if bank is None else bank
        self.version=model_fingerprint(model);self.current_code=None;self.current_candidate=None
        self.sessions={};self.decisions=[]
        self.counters={'task_steps':0,'trial_steps':0,'baseline_trials':0,'candidate_trials':0,'failure_sessions':0,'adoptions':0}

    def tensor(self,value):return torch.tensor(value,dtype=next(self.model.parameters()).dtype,device=next(self.model.parameters()).device)

    def assert_snapshot(self):
        if model_fingerprint(self.model)!=self.version:
            raise ValueError('Parameter version changed: acknowledge via replace_model before using old control codes')

    def replace_model(self,model):
        if model.schema!=self.bank.schema:raise ValueError('Changing the observation schema requires an explicit data conversion')
        new_version=model_fingerprint(model)
        if new_version!=self.version:
            self.current_code=None;self.current_candidate=None
            for session in self.sessions.values():session.active=False
        self.model=model;self.version=new_version

    def infer(self,observation,goal,actions,code=None,memory=None):
        if code is None:code=self.current_code
        return self.model(self.tensor([observation]),self.tensor([goal]),self.tensor([actions]),
                          self.bank.view() if memory is None else memory,None if code is None else self.tensor([code]))

    def choose(self,logits):
        probabilities=torch.softmax(logits.detach(),-1).cpu()[0].tolist()
        choice=self.rng.choices(range(len(probabilities)),weights=probabilities,k=1)[0]
        return choice,probabilities[choice],probabilities

    def require_session(self,session):
        self.assert_snapshot()
        if self.sessions.get(session.id) is not session or not session.active or session.model_id!=self.version:
            raise ValueError('Practice session belongs to an inactive model version')

    @torch.no_grad()
    def execute(self,observation,goal,actions,environment,episode,step=0,previous_id=None,session=None,arm=None):
        role='task';candidate=None
        if session is not None:
            self.require_session(session);candidate=session.arms[arm];role='trial'
        else:self.assert_snapshot()
        code=self.current_code if candidate is None else candidate.code
        output=self.infer(observation,goal,actions,code);history_ids=tuple(self.bank.index)
        action,propensity,policy=self.choose(output['logits'])
        result=environment(action)
        eid=f'{self.namespace}/event/{len(self.bank.events)}'
        event=Event(eid,episode,step,tuple(observation),tuple(actions),action,tuple(result['next_observation']),tuple(result['feedback']),
                    tuple(result['feedback_mask']),tuple(goal),tuple(output['feedback_prediction'][0,action].cpu().tolist()),
                    (True,)*self.model.schema.feedback,propensity,bool(result['goal_met']),bool(result['terminal']),float(result['cost']),
                    'environment',role,previous_id,candidate.id if candidate else self.current_candidate,self.version)
        self.bank.add(event);self.counters['task_steps' if role=='task' else 'trial_steps']+=1
        if role=='trial':
            session.receipts.append(TrialReceipt(eid,session.id,arm,candidate.id,candidate.digest,self.version))
            self.counters['baseline_trials' if arm==0 else 'candidate_trials']+=1
        self.decisions.append({'kind':role,'event_id':eid,'action':action,'propensity':propensity,'policy':policy,
                               'history_ids':history_ids,'model_id':self.version,'code':code,
                               'session_id':None if session is None else session.id,'arm':arm})
        return event

    @torch.no_grad()
    def new_session(self,event):
        self.assert_snapshot()
        if self.bank.events[self.bank.index[event.id]]!=event:raise ValueError('Reflection requires an observed local event')
        if event.goal_met or not event.terminal:raise ValueError('Only a terminal failure starts this offline practice session')
        if any(s.active and s.model_id==self.version and s.source_event_id==event.id for s in self.sessions.values()):
            raise ValueError('This failure already owns a practice session in the current model version')
        output=self.infer(event.observation,event.goal,event.actions)
        proposed=self.model.propose(output)[0].cpu().tolist()
        base=self.current_code if self.current_code is not None else tuple(self.model.base_code.detach().cpu().tolist())
        sid=f'{self.namespace}/session/{len(self.sessions)}';history=tuple(self.bank.index)
        arms=tuple(Candidate(f'{sid}/arm/{j}',tuple(code),self.version,event.id,history) for j,code in enumerate((base,*proposed)))
        session=PracticeSession(sid,event.id,arms,self.version);self.sessions[sid]=session;self.counters['failure_sessions']+=1
        return session

    def evidence(self,session,stop=None):
        if stop is None:stop=len(self.bank.events)
        groups=[[] for _ in session.arms]
        for receipt in session.receipts:
            candidate=session.arms[receipt.arm]
            event=self.bank.events[self.bank.index[receipt.event_id]]
            if receipt.model_id!=session.model_id or receipt.candidate_digest!=candidate.digest or event.candidate_id!=candidate.id or event.role!='trial':
                raise ValueError('Mismatched actual practice evidence')
            if self.bank.index[receipt.event_id]<stop:groups[receipt.arm].append(receipt.event_id)
        return self.bank.evidence(groups,stop)

    @torch.no_grad()
    def trial(self,session,arm,environment):
        source=self.bank.events[self.bank.index[session.source_event_id]]
        return self.execute(source.observation,source.goal,source.actions,environment,
                            f'{session.id}/trial/{len(session.receipts)}',session=session,arm=arm)

    def promote(self,session,arm):
        self.require_session(session)
        if arm==0:return  # Keep current behavior, even when no new baseline trial was taken.
        ids=self.evidence(session)['ids'][arm]
        if not ids:raise ValueError('Untested candidate cannot become current behavior')
        self.current_code=session.arms[arm].code;self.current_candidate=session.arms[arm].id;self.counters['adoptions']+=1

    @torch.no_grad()
    def reflect(self,event,environment,budget):
        if not event.terminal or event.goal_met:return None
        session=self.new_session(event);codes=self.tensor([[c.code for c in session.arms]])
        for index in range(budget):
            output=self.infer(event.observation,event.goal,event.actions);evidence=self.evidence(session)
            logits,_=self.model.trial_logits(output,codes,evidence,self.tensor([[float(budget-index),float(index)]]))
            choice,propensity,policy=self.choose(logits)
            self.decisions.append({'kind':'trial_choice','session_id':session.id,'history_ids':tuple(self.bank.index),
                                   'evidence_ids':evidence['ids'],'model_id':self.version,'choice':choice,'policy':policy,'propensity':propensity,
                                   'remaining_budget':budget-index})
            if choice==0:break
            self.trial(session,choice-1,environment)
        output=self.infer(event.observation,event.goal,event.actions);evidence=self.evidence(session)
        logits,state=self.model.adoption_logits(output,codes,evidence)
        choice,propensity,policy=self.choose(logits)
        self.decisions.append({'kind':'adoption','session_id':session.id,'history_ids':tuple(self.bank.index),'evidence_ids':evidence['ids'],
                               'model_id':self.version,'choice':choice,'policy':policy,'propensity':propensity,
                               'counts':state['counts'][0].cpu().tolist(),'contrast_mean':state['contrast_mean'][0].cpu().tolist(),
                               'contrast_variance':state['contrast_variance'][0].cpu().tolist()})
        self.promote(session,choice)
        return session

    def comparison_example(self,session,event_a,event_b):
        by_id={r.event_id:r for r in session.receipts}
        a,b=by_id[event_a],by_id[event_b]
        if a.arm==b.arm:raise ValueError('Use different actual behavior arms for this comparison')
        stop=min(self.bank.index[event_a],self.bank.index[event_b])
        ea=self.bank.events[self.bank.index[event_a]];eb=self.bank.events[self.bank.index[event_b]]
        if (ea.observation,ea.goal,ea.actions)!=(eb.observation,eb.goal,eb.actions):raise ValueError('Unmatched public practice conditions')
        return {'memory':self.bank.view(stop),'evidence':self.evidence(session,stop),
                'codes':self.tensor([[c.code for c in session.arms]]),'arm_a':a.arm,'arm_b':b.arm,
                'target_events':(ea,eb),'observation':ea.observation,'goal':ea.goal,'actions':ea.actions,
                'model_id':session.model_id}

    def session_record(self,session):
        return {'id':session.id,'source_event_id':session.source_event_id,'model_id':session.model_id,'active':session.active,
                'arms':[dict(asdict(c),digest=c.digest) for c in session.arms],'receipts':[asdict(r) for r in session.receipts]}

    @torch.no_grad()
    def imagine(self,observation,goal,actions,action_index):
        self.assert_snapshot();output=self.infer(observation,goal,actions)
        def variance(prefix):
            means=output[prefix+'_mean'][0,:,action_index];var=output[prefix+'_variance'][0,:,action_index]
            weights=output['weights'][0,:,None];mean=(weights*means).sum(0)
            return tuple((weights*(var+(means-mean).square())).sum(0).cpu().tolist())
        return ImaginedTransition(tuple(observation),tuple(actions[action_index]),
                                 tuple(output['next_prediction'][0,action_index].cpu().tolist()),
                                 tuple(output['feedback_prediction'][0,action_index].cpu().tolist()),
                                 tuple(self.bank.index),self.version,variance('next'),variance('feedback'))
