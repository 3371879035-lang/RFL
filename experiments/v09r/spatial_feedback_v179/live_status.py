"""Read volatile progress only; never starts or changes experiments."""
import datetime
import json
from pathlib import Path

base=Path(__file__).parent
source=base/'evidence_matrix'
counts=dict(completed_models=0,active_models=0,training_steps_lower_bound=0,
            transient_progress_writes_skipped=0)
for path in source.glob('seed*/*/progress.json'):
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        counts['transient_progress_writes_skipped']+=1
        continue
    if data['status']=='COMPLETE':
        counts['completed_models']+=1
        counts['training_steps_lower_bound']+=data['training_steps']
    else:
        counts['active_models']+=1
        counts['training_steps_lower_bound']+=data.get('steps',data.get('training_steps',0))
counts.update(time=datetime.datetime.now().astimezone().isoformat(),
              stop=(source/'STOP.json').exists(),final_exit=(source/'exit.json').exists(),
              reviewed_cases=len(list((base/'review_shards').glob('seed*__*.json'))))
print(json.dumps(counts),flush=True)
