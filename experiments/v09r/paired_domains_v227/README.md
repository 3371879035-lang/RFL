# V227 — mathematical repair and concurrent pursuit / generic comparison

## Scope

The latest user explicitly requested mathematical/neural repair first, capacity fairness, then concurrent three-hour training in the pursuit map and generic tasks. This directory is a new isolated revision. The old V226 failure and every old source/result remain unchanged; no old automation was resumed.

Read [MATH.md](MATH.md) for derivations and limitations, [contract.json](contract.json) for the pre-execution budget. The architecture is a fresh compact replacement, **not the old 20-million-parameter model with a new label**. All groups are fresh. Old map scores and the old generic run are historical context, not a one-factor comparator.

## What was repaired

1. Direct, action-specific trainable control path from current observation, goal and conditional history. The only decision path no longer relies on interactions with detached world action states.
2. Generic R-only terminal objective no longer rewards approach/retreat cycles. The physical environment is unchanged; the reward protocol change is explicit.
3. Two actual paired finite-horizon trials produce conditional effect targets for a separate head. They are not substituted for full-horizon Q targets or causal probabilities.
4. Both the teacher and the SLEEP-distilled student require new actual full-task paired checks. Negative or zero trials are retained. Rejected proposals fall back to the ordinary-learning matched reference, not a frozen control.
5. Equal compact tensor architecture and per-round interaction/optimizer budgets; fixed-weight greedy AND epsilon=.1 evaluation, using the final completed common round.

## Six conditions

| Group | Control | Extra loop |
|---|---|---|
| RL-plain | Double-DQN with reward and punishment | None; budget spent on ordinary learning |
| RL-outer | Same Double-DQN | Actual trials, teacher gate, SLEEP and student gate; no factual head learning |
| F0 | Direct finite-horizon factual prediction and goal readout | Actual trials and gated consolidation; no reward packet or Q target |
| F-RP | Q control plus factual learning | Reward and punishment; ordinary failed-history proposals and gated consolidation |
| F-R | Q control plus factual learning | Reward only; ordinary failed-history proposals and gated consolidation |
| N227 | Q control plus factual learning | Reward only; learned historical disagreement/effect proposals, direct actual-pair effect learning and gated consolidation |

Every group has 213,329 tensor parameters. Active-path parameter counts are 203,025 / 203,025 / 209,201 / 211,265 / 211,265 / 213,329 respectively. The difference is only small unused output heads, not hidden capacity padding. Optimizer calls and actual steps are matched; FLOPs, completed episodes and independent information are not claimed identical.

F0's facts include a deterministic, observable distance-derived goal-quality measurement. It receives no external reward packet or Q target, but this does **not** mean it has no goal preference or that value-like computation has been philosophically eliminated. Its predictions average empirical continuation outcomes from replay; they do not identify arbitrary untried continuations. The history attention, ensemble disagreement and applicability gate are learned proposal mechanisms, not calibrated Bayesian or causal probabilities.

## Actual short validation

- `diagnostic/result.json`: 480 real generic transitions; 120 supervised optimizer steps on their observed outcomes. Direct action-contrast input gradient was nonzero. In-sample target MSE fell from 0.224255 to 0.000292. This is a learnability/data-flow check, **not held-out generalization or control superiority**.
- `smoke/exit.json`: both domains, one independent smoke seed, all six groups, 49,152 charged real steps, 3,072 optimizer calls, completed in 66.09 seconds; first execution succeeded, no retry.
- `smoke/result_summary.json`: independent stdlib read of all raw lines through EOF, chronological event IDs, memory provenance, legal actions and counts. Generic N227 performed one actual teacher pass and one actual post-SLEEP student pass; failed/zero/adverse proposals also occurred and remain stored.
- 796 declared input files were identical before/after the short checks, including the 763 prior V226 pins. This is the declared scope, not a claim to audit all tracked data.

## Three-hour run

`three_hour/claim.json` and `launch.json` record the launch around **2026-11-12 10:12:24 Asia/Shanghai**. Status at writing: **launched, not completed**. Seeds 137/149/163 independently train in both domains: six CPU worker processes, 36 models. Each model receives 4,096 charged real interactions and 256 optimizer calls per common round. New rounds stop early enough to perform final evaluation inside the shared 10,800-second cap. Initial/final evaluation uses 32 fixed scenarios per seed and policy mode.

Progress: `three_hour/progress.json`. Completion: `three_hour/exit.json` AND `guard_exit.json`. Any failure/partial is retained without retry. The bounded Windows guard owns only this process tree. Final read-only aggregation entry point:

```powershell
& 'D:/强化反馈学习/.venv-v09/Scripts/python.exe' -X utf8 -B 'experiments/v09r/paired_domains_v227/analyze.py' 'experiments/v09r/paired_domains_v227/three_hour'
```

The current model is deliberately small but has learned memory nodes and trainable goal-conditioned action outputs. It does not solve calibrated uncertainty, unlimited memory, all historical applicability or arbitrary imagination. These remaining limits must be evaluated rather than assumed fixed by having an executable network.
