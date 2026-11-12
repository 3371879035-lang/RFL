"""Read-only, stdlib result aggregation and complete canonical raw EOF/count audit."""
import argparse
import collections
import gzip
import json
from pathlib import Path
import statistics

def main():
    ap=argparse.ArgumentParser();ap.add_argument('capture');args=ap.parse_args();cap=Path(args.capture)
    exit_record=json.loads((cap/'exit.json').read_text())
    if exit_record['exit_code']!=0: raise RuntimeError('Incomplete experiment, no complete-run summary')
    common=exit_record['common_round'];groups=('RL-plain','RL-outer','F0','F-RP','F-R','N227')
    audit=[]; results={}; raw_steps=0
    for folder in sorted(cap.glob('*_seed*')):
        if not folder.is_dir():continue
        initial=json.loads((folder/'initial.json').read_text()); final=json.loads((folder/'final.json').read_text())
        assert final['round']==common
        domain=folder.name.split('_seed')[0];seed=int(folder.name.split('_seed')[1])
        results.setdefault(domain,[]).append(dict(seed=seed,initial=initial['results'],final=final['results']))
        for group in groups:
            seen=set();count=0; purpose=collections.Counter(); stages=collections.Counter();pairs=[];gates=[]
            for r in range(1,common+1):
                with gzip.open(folder/f'round{r:04d}_{group}.jsonl.gz','rt',encoding='utf-8') as f:
                    round_count=0
                    for line in f:
                        row=json.loads(line)
                        if row.get('kind')=='round_log':
                            for event in row['events']:
                                if event['kind']=='optimizer': stages[event['stage']]+=1
                                elif event['kind']=='actual_pair':pairs.append(event)
                                elif event['kind']=='full_task_gate':gates.append(event)
                            continue
                        assert row['id']==f'{domain}/{seed}/{group}/{count}'
                        assert row['id'] not in seen
                        assert len(set(row['memory_ids']))==len(row['memory_ids'])
                        assert all(e in seen for e in row['memory_ids'])
                        assert row['action'] in row['source']['legal']
                        seen.add(row['id']);count+=1;round_count+=1;purpose[row['purpose']]+=1
                assert round_count==4096
            assert count==4096*common
            assert sum(stages.values())==256*common
            for ep in ('0.0','0.1'):
                for phase in (initial,final):
                    ev=phase['results'][group][ep]
                    assert ev['successes']==sum(int(x['success']) for x in ev['rows'])
                    assert sum(ev['actions'])==sum(x['steps'] for x in ev['rows'])
            record=dict(domain=domain,seed=seed,group=group,raw_steps=count,purposes=dict(purpose),updates=dict(stages),
              pairs=len(pairs),nonpositive_pairs=sum(p['delta']<=0 for p in pairs),
              teacher_tests=sum(g['stage']=='teacher' for g in gates),teacher_pass=sum(g['stage']=='teacher' and g['passed'] for g in gates),
              student_tests=sum(g['stage']=='student' for g in gates),student_pass=sum(g['stage']=='student' and g['passed'] for g in gates))
            assert record['student_tests']==record['teacher_pass']
            assert record['student_pass']<=record['student_tests']
            audit.append(record);raw_steps+=count
    summary={}
    for domain,workers in results.items():
        summary[domain]={}
        for group in groups:
            summary[domain][group]={}
            for epsilon in ('0.0','0.1'):
                phases={}
                for phase in ('initial','final'):
                    evs=[w[phase][group][epsilon] for w in workers]
                    rows=[r for e in evs for r in e['rows']]
                    phases[phase]=dict(episodes=len(rows),successes=sum(int(r['success']) for r in rows),
                      mean_score=statistics.mean(r['score'] for r in rows),mean_steps=statistics.mean(r['steps'] for r in rows),
                      mean_distance=statistics.mean(r['distance'] for r in rows) if domain=='generic' else None,
                      per_seed=[dict(seed=w['seed'],mean_score=w[phase][group][epsilon]['mean_score'],successes=w[phase][group][epsilon]['successes'],
                                     mean_distance=w[phase][group][epsilon]['mean_distance']) for w in workers])
                summary[domain][group][epsilon]=phases
    output=dict(status='READ_ONLY_COMPLETE_RAW_AUDIT',common_round=common,raw_steps=raw_steps,source_exit=exit_record,
                audit=audit,summary=summary,independent_training_seeds={d:len(x) for d,x in results.items()},
                limitations=['Fixed-weight evaluation, not extra-test inference service','Same compact backbone; not literal historical agents',
                             'Three seeds in the long run; episode counts are not independent training seeds',
                             'No saturation or general superiority inference','F0 goal-related factual prediction is not absence of a goal preference'])
    (cap/'result_summary.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# V227 paired-domain result','',f'Common completed rounds: {common}. Actual charged steps: {raw_steps}.',
           f"Wall seconds: {exit_record['elapsed_seconds']:.1f} / cap {exit_record['wall_cap_seconds']}.",
           'All rows below use fixed weights; greedy and epsilon=.1 are separate. No cross-domain score comparison.','']
    for domain,rows in summary.items():
        for epsilon in ('0.0','0.1'):
            lines += [f'## {domain}, epsilon={epsilon}','|Group|Initial score|Final score|Initial success|Final success|Final distance|',
                      '|---|---:|---:|---:|---:|---:|']
            for group,data in rows.items():
                a=data[epsilon]['initial'];b=data[epsilon]['final']
                lines.append(f"|{group}|{a['mean_score']:.6f}|{b['mean_score']:.6f}|{a['successes']}/{a['episodes']}|{b['successes']}/{b['episodes']}|{b['mean_distance']}|")
            lines.append('')
    lines += ['## Limits']+['- '+x for x in output['limitations']]
    (cap/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=output['status'],rounds=common,steps=raw_steps,report=str(cap/'REPORT.md'))))

if __name__=='__main__':main()
