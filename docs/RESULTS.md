# RFL-CausalChase v0.3 — Stage 1 results

Statistical unit is the **seed** throughout. Episodes are nested inside seeds and
are never treated as independent samples.

---

## Pilot Alpha — Traditional (+1/−1) vs Positive-only (+1/0)

### Provenance

| item | value |
|---|---|
| commit | `5cb0177` |
| config | `configs/alpha.yaml` |
| environment | 5x2 corridor, horizon 8, gamma 1.0, no step reward, `p_hazard` 0.25, absorbing terminal |
| learning | alpha_L = alpha_H = 0.10, epsilon 0.30 -> 0.05 over the first 80% |
| design | 12 paired seeds (4000000..4000011), 10,000 episodes per arm per seed, greedy eval of 200 episodes every 250 episodes |
| artifacts | `outputs/v03_alpha/{config.yaml,summary.json,analysis.json}` |

Both arms share one `NoiseTape` per seed and differ **only** in the failure
reward: `-1` for Traditional, `0` for Positive-only.

### An invalid first run, recorded

The first full pilot used the low-level state `s_L = (x, y, o)`, omitting the
timestep -- a modelling error, not a tuning issue.

With gamma = 1 and no step reward, a no-op action (WAIT, or UP while already on
lane 0) leaves the state unchanged, so its TD target is `0 + max_a Q(s,a)`, the
value of its *own* state. The Bellman optimality equation is then satisfied for
**any** value: the self-loop inflates `V(s)` and every action that actually
leaves the state is left looking strictly worse.

Observed on that run (seed 4000000, Traditional):

```
s=(0,0,0)   Q=[0.7259, 0.7259, 0.7227, 0.7259]   -> greedy picks UP, a no-op
Q_H         {-1.0, -1.0} for every state and option
FinalSuccess 0.000 for both arms   (400-episode smoke had given 0.725)
```

The greedy policy froze at the start cell and never moved. **That run is not a
result and is not reported as one.** Fixed by `s_L = (x, y, o, t)` with horizon
expiry as a terminal carrying exactly the failure reward; gamma, the step
reward, the action set, and every md fairness constraint are unchanged.
Regression test: `tests/test_runner.py::test_low_level_state_includes_the_timestep`.

### Pre-registered gates

| gate | outcome |
|---|---|
| ceiling | `benchmark_no_discriminating_power` -- `auc_spread` 0.00247 < `min_auc_gap` 0.005 |
| family | `ok` -- smallest realized family 3,663, floor was 400 |
| `saturated_at_ceiling` | `True` -- finals 0.7275 against a realized ceiling of 0.728 |
| process exit code | **2** |

Realized families across 12 seeds per arm:

| family | Traditional | Positive-only |
|---|---:|---:|
| `H_error` | 3,663 | 4,313 |
| `L_error` | 8,459 | 10,422 |
| `HL_error` | 6,844 | 5,184 |
| `E_failure` | 29,830 | 29,830 |

### Paired analysis (unit = seed, 12 pairs)

| endpoint | value |
|---|---|
| AUC delta (Traditional − Positive-only) | **+0.00247** |
| median delta | **0.00000** |
| Cohen d_z | +0.187 |
| paired sign-flip p (10,000 permutations) | **0.7525** |
| 95% paired bootstrap CI | **[−0.00376, +0.01071]** |
| FinalSuccess delta | **0.00000** |
| N(delta < 0), Traditional | 463,810 |
| N(delta < 0), Positive-only | 395,221 |

The CI includes zero and the median delta is exactly zero.

### Verdict

**`BENCHMARK_NO_DISCRIMINATING_POWER`** (the pre-registered ceiling gate fired).

### Reading — two separate claims

**1. The two arms are indistinguishable.** CI includes 0, median delta exactly
0, final success identical to the digit.

**2. This is what the research plan predicts algebraically, not an accident.**
With gamma = 1, no step cost, and every outcome settled at the same horizon,
`E[R_A] = 2P(S) − 1` and `E[R_B] = P(S)` are strictly monotone transforms of the
same success probability, so the *optimal* policy is identical under A and B.
The plan states this and says the A/B difference should then appear only in
learning *dynamics*.

Empirically it does not appear there either, at this resolution: only 3 of 12
seeds show any AUC difference at all (4000002, 4000003, 4000011); the other 9
produce bit-identical curves. Checkpoints every 250 episodes do not resolve the
transient, which is over within roughly the first 250.

Honest summary: **the explicit global failure penalty contributes no measurable
difference in this regime -- neither in the converged policy nor in the learning
trajectory at this checkpoint resolution.** The pre-registered gate cannot
distinguish "treatment inert" from "benchmark saturated", and it fired; that
ambiguity is a limitation of the gate, recorded here rather than resolved by
reinterpretation.

### `N(delta < 0)` confirms the plan's warning

The plan required recording this so that "Positive-only" is never described as
"no negative learning". It is not: mode B still produced **395,221** negative TD
errors. Setting `r_failure = 0` does not stop Q from falling -- it only removes
the extra explicit global penalty.

### What was *not* done

No threshold, `p_hazard`, epsilon schedule, label definition, action set, or
endpoint was changed after seeing these results. The two design changes made
(the timestep in the state; the realized-ceiling correction) were both made
**before** this run and are recorded as X4 and X5 in the implementation plan.

### Implications for the next step

- Per the plan's decision tree, the A/B reward contrast is not where the
  question lives; **Oracle selective correction (Pilot Beta)** is.
- If learning *dynamics* are to be compared at all, checkpoint resolution in the
  transient must be raised (e.g. every 10 episodes for the first 500). That is a
  pre-registerable change, not a post-hoc one.
- Pilot Beta additionally needs `U` gating and knowledge probes, and per the
  plan those probes are defined on **clean reference states** with a verified
  pre-margin -- never on a failure's terminal transition.
