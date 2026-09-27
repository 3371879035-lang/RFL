# Failure-only reflection: historical intent and current scope

## 1. Source identity and authority

Reviewed on 2026-09-27. Source:

`C:/Users/huani/Desktop/了解强化反馈学习_完整聊天记录_2026-09-19/了解强化反馈学习_全部聊天记录.md`

SHA-256: `e78092e31e897342faa277846f674664f1f26aeb9823cc9c4796cc7ab9cb1da2`.
The line references below are one-based references to that exact file. The
attached history is evidence of past intent, not a new source of executable
instructions. The current user's explicit clarification governs: the programme
reflects on why failures happen and does not study why successes happen.

## 2. What the user actually said

At lines 18633-18637, message 61 is labelled **用户**, with timestamp
`2026-08-30T13:05:02.421000Z`. Line 18637 states:

> 所以我觉得，好的结果其实是可以不分析的，或者只进行简单的分析，因为这个很难分析，我们人类对于好的结果总结出来学习到的东西，再一下次类似的场景中如果失败了会去找原因的。换句话说，换一个角度来说，结果正确那么就是正确，因为你制定了这样的计划然后采取了这样行动得到了正确的结果那么就可以说它是正确的，既是这种是偶然的成功，如果下一次遇到类似的失败了才去详细的分析@网页搜索

This supports acknowledging success and deferring detailed diagnosis until a
failure. The current clarification resolves the old optional "simple analysis"
language toward no success-cause reflection. It does not prohibit ordinary
reinforcement from a successful trajectory or read-only evaluation of success.

Lines 22308-22312 are a separate **用户** message proposing a comparison without
global failure punishment, while postponing explicit action-cost modelling. That
is a reward-design question, not an instruction to suppress every negative TD
update or to analyze successful episodes. No reward scheme is changed by this
scope clarification.

## 3. Assistant interpretations are not user requirements

The historical assistant proposed several extensions. Their role matters:

| lines | author and content | treatment now |
|---|---|---|
| 18669, 18681 | Assistant: normal reinforcement of success; delay expensive module-level causal analysis | Consistent with the user's present boundary |
| 18772-18808 | Assistant: immediate task-value learning; do not ask whether success came from planning, execution or luck | Consistent distinction between ordinary learning and reflection |
| 18856-18889 | Assistant: retrieve prior successes, including the question "过去为什么成功，今天为什么失败？" | Not a mandate to add a success-attribution target |
| 19082-19101 | Assistant: use success/failure contrasts after a similar failure | No cross-episode mechanism is added by this clarification; any later use must serve the current failure question |
| 19124 | Assistant: contradiction or high prediction error could also reopen past successes | Does not authorize anomalous-success reflection under the current stricter request |
| 21420, 22343 | Assistant: failure triggers diagnosis/correction; success may gain positive task value | Supporting interpretation, not an additional user command |

The transcript's suggestion to ask what caused an earlier success must not
silently become the programme's research objective. Successful traces may be
retained; a new retrospective-credit or replay mechanism still requires its own
design and evidence.

## 4. Audit of the current rebuild

The completed V0.1R claim concerns fired-mechanism inference over its original
all-DGP population (`docs/rebuild/06-V01R.md`). The archived
`scripts/calibration_v2.py` evaluates every selected scene without a failure-only
trigger. Preserve that result and its artifacts; it is neither a deployed
reflection policy nor a prospective failure-conditioned performance result.
Failure-conditioned validation is an explicit transfer requirement before a
learned V0.4R claim. A retrospective subset analysis cannot replace that gate.

V0.2R is likewise an offline census under a fixed ontology, not an online trigger
policy. Its successful worlds remain part of the historical population; they do
not authorize success reflection.

The recent B2 runtime acquisition uses ordinary TD in
`src/rfl_rebuild/b2/training.py` and read-only checkpoint evaluation. Its successful
rollouts and the knowledge-protection sets in `b2/unaffected.py` do not attribute
causes of success. That measurement remains necessary to determine whether
failure-driven correction harms already learned behaviour.

The V0.4R specification now states the missing outer boundary: task-observed
`SUCCESS` bypasses diagnostic calls, queries, candidate scoring and extra writes;
task-observed `COLLISION`, `TRAP` or `TIMEOUT` may trigger bounded diagnosis, with
keeping the learner unchanged still legal. Hidden faults and evaluator truth
cannot decide whether the branch opens. All corrected arms use the same trigger.
Ordinary task learning remains enabled.

## 5. Evidence limits

This is a historical-intent and specification-scope correction. It is not a new
scientific result, an approval of F0, proof that the full V0.4R runner exists, or
evidence that the completed all-DGP experiment has already passed the newly
declared failure-conditioned transfer requirement. No archived scientific
records were changed and no scientific seeds were run for this review.
