# F0 initializer candidate C1: ordinary learning of an overestimated action

Status: **PROPOSED, isolated construction experiment** (2026-09-26). This does not
supersede rev 4, ratify F0, change A87's canary, or open scientific collection.
The current user request authorises continuing the investigation. Historical
review messages are evidence, not fresh instructions. The experiment below makes
the proposed change concrete and testable before integration.

## 1. Why a new instance and a different construction predicate are needed

The corrected original gate remains INADMISSIBLE. Its t=0 canary depresses the
optimal action at one of 48 initial (kappa, phase, option) cells. In that cell the
row has two admissible actions, so the affected action is sampled only through
epsilon exploration. Under independent uniform draws the nominal hit probability
is (1/48)*(1/10)*(1/2)=1/960 per episode. This is an explanatory approximation,
not an independence theorem about the deterministic keyed generator. Zero hits
in the 1280 operational episodes does not establish unreachable support.

There is a separate deterministic obstruction: alpha=1/2 needs 54 hits to return
the original value to the exact binary64 reference, while t increases strictly
and permits at most one hit per episode. Cap=40 cannot satisfy that exact-return
predicate even with a hit every episode, under the verified fixed-target recurrence.

Binary64 equality and behavioural recovery answer different questions. A learner
can choose the correct action with residual Q error. The proposed construction
criterion explicitly changes from exact override deletion to restored behaviour;
the old gate is preserved, not reinterpreted as having passed. B2's scientific
recovery endpoints, thresholds, alpha, epsilon and cap are NOT changed here.

## 2. Candidate fixed before new keyed runs

Use the same decision context as A87's D_Q witness, but a separate stage initializer:

1. Read the frozen reference row. Let b=max Q*(a).
2. Choose the smallest action ID among strict suboptimal actions; call its value q.
3. Write only that action's Q entry to b+(b-q). All other stores remain healthy.
4. Require a positive gap and a representable value strictly above b; fail if absent.

This rule uses no run outcomes, candidate ranking, calibrated metric or new free
magnitude. On the current row a=4, q=0.8599999999999999, b=0.8799999999999999,
and the initial value is 0.8999999999999999. Action 3 remains the healthy choice.
It is an oracle-constructed fixture for stage development, NOT a learner-feasible
way to infer defects and NOT a distribution of naturally occurring defects.

Only a t=0 address changes. There is no earlier state whose bootstrap can read
that change. On a greedy visit the next state is healthy, so the target is q.
For alpha=1/2 the first ideal update reaches b; a second reaches b-(b-q)/2 < b.
Thus at most two matching greedy visits suffice to restore the healthy decision
(possibly one by the actual tie rule). Actual kernel/rounding behaviour must be
verified, not inferred solely from that real-arithmetic argument. The episode
stream itself, including exploration, remains A91's unchanged stream.

## 3. Predeclared operational check

- New keys: 910001 through 910032 inclusive. Never reuse these as scientific seeds.
- One candidate, one run; no sweep, adaptive cap, seed replacement or retries to pass.
- Alpha=1/2, epsilon=1/10, cap=40, balanced bank prefix=1024 remain unchanged.
- Preserve healthy and no-learning negative controls; tests exercise actual rollouts.
- Freeze a manifest with protocol and relevant source hashes before acquiring runs.
- Write independent output artifacts; do not overwrite rev-4 artifacts.

Candidate passes only if all five propositions hold:

(a) every run enters with the sole prescribed Q override, wrong local greedy action,
and at least one degraded bank scene relative to the healthy reference;
(a') some chronological episode changes the complete Q store;
(b1) at least one bank-mean curve changes over episodes;
(b2) at least two whole curves differ;
(c-behaviour) at least one run restores both the healthy local greedy action and the
complete healthy bank return vector at an episode 1..40.

Condition (c-behaviour) is narrower than proving recovery on every possible future
scene. A separate seedless full U2-support comparison at a constructed repaired
state will check that example more broadly. Neither check replaces B2 confirmatory
testing. Exact override deletion, visits and recovery persistence are diagnostics,
not acceptance conditions. The five predicates remain independent; a partial pass
does not admit this candidate. A pass means only CANDIDATE_CONSTRUCTION_PASS.

## 4. Remaining boundaries

No f_T/f_N/f_G/f_C/f_R selector consumes these runs. No retention form or training
horizon is selected. F0 still needs explicit integration of any accepted amendment,
complete acquisition/serialization/manifest work and resolution of the independent
persistent-regime (P) RMST practical-effect rationale. A passing construction does not resolve
those matters or show RFL treatment benefit.
