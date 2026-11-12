"""New finite synthetic checks, with no environment or neural training."""
import json
from pathlib import Path
from reaction import ReactionMemory


def main():
    legal = [True] * 16
    scores = list(range(16, 0, -1))
    m = ReactionMemory('wake')
    assert m.choose(17, (3, 4), legal, scores, 0, False)[0] == 0
    m.observe(17, (3, 4), 0, False)
    assert m.choose(17, (3, 4), legal, scores, 0, False)[0] == 0
    m.observe(17, (3, 4), 0, False)
    chosen, r = m.choose(17, (3, 4), legal, scores, 0, False)
    assert chosen == 1 and r['reason'] == 1
    assert m.choose(17, (3, 4), legal, scores, 0, True)[0] == 0
    assert m.choose(17, (5, 4), legal, scores, 0, False)[0] == 0
    m.reset()
    assert m.choose(17, (3, 4), legal, scores, 0, False)[0] == 0
    m = ReactionMemory('wake_sleep')
    for _ in range(2):
        m.reset()
        for _ in range(20):
            m.observe(17, (3, 4), 0, False)
        m.observe(17, (3, 4), 1, True)
        m.finish(True, True)
    assert m.counts[17][0] == [0, 2] and m.counts[17][1] == [2, 0]
    m.reset()
    assert m.choose(17, (8, 8), legal, scores, 0, False)[0] == 1
    assert m.choose(18, (8, 8), legal, scores, 0, False)[0] == 0
    h = m.digest()
    m.observe(17, (8, 8), 0, True)
    assert m.choose(17, (8, 8), legal, scores, 0, False)[0] == 0
    assert m.finish(False, False) is None and m.digest() == h
    m.finish(False, True)
    m.reset()
    assert m.rules[17] == 0 and m.failures == 2
    m = ReactionMemory('base')
    for _ in range(2): m.observe(17, (3, 4), 0, False)
    assert m.choose(17, (3, 4), legal, scores, 0, False)[0] == 0
    # A long unfinished experience never becomes a completed-episode rule.
    assert m.completed == 0 and not m.counts and not m.rules
    result = dict(exit_code=0, environment_steps=0, neural_instances=0, optimizer_updates=0,
        checks=['wake two-step response','unchanged epsilon and legal set','local context and episode reset',
                'distinct-episode support not repeated rows','cross-episode use','context mismatch',
                'counterexample revocation','frozen persistent memory','success no diagnostic',
                'ordinary base unchanged','unfinished tail not consolidated'])
    with (Path(__file__).parent/'pure_check_result.json').open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2); f.write('\n')
    print(json.dumps(result))


if __name__ == '__main__': main()
