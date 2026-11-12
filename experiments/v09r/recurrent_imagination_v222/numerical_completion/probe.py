from pathlib import Path
import json,random,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OLD=HERE.parent/'capture'
sys.path.insert(0,str(ROOT/'src'))
import torch
from feedback_program_v222 import RecurrentFeedbackNet,NetworkConfig,Schema,MemoryBank,PracticeAgent
from feedback_program_v220.runtime import model_fingerprint
from checks import run_checks


def main():
    torch.set_num_threads(1);start=time.perf_counter();cap=HERE/'capture'
    stored=torch.load(OLD/'untrained_seed_73.pt',map_location='cpu',weights_only=True)
    model=RecurrentFeedbackNet(Schema(**stored['schema']),NetworkConfig(**stored['config'])).eval();model.load_state_dict(stored['state_dict'])
    bank=MemoryBank.from_json((OLD/'memory_masked_shift_seed73.json').read_text())
    # Replay of immutable observed facts, not reconstruction of issued live sessions/receipts.
    agent=PracticeAgent(model,'new_numerical_check_no_environment',random.Random(222),bank)
    before=model_fingerprint(model)
    with (cap/'checks.jsonl').open('x',encoding='utf-8',buffering=1) as f:
        def record(value):f.write(json.dumps(value,sort_keys=True,allow_nan=False)+'\n')
        checks=run_checks(agent,record)
    assert before==model_fingerprint(model)
    result={'status':'DIRECTED_NUMERICAL_AND_PENDING_CHECKS_COMPLETE','checks':checks,'model_before':before,'model_after':model_fingerprint(model),
            'actual_environment_calls':0,'optimizer_steps':0,'first_failed_native_not_relabelled':True,'wall_seconds':time.perf_counter()-start}
    with (cap/'summary.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))


if __name__=='__main__':main()
