# RFL-CausalChase v0.2 Responsibility-to-Learning Design

**Status:** Approved by the user for implementation on 2026-08-30.

**Source of truth:** `RFL-CausalChase v0.2：验证“Responsibility → Update → Learning”的可执行研究计划.docx`.

## Goal

Extend the frozen v0.1 tabular benchmark into an auditable v0.2 experiment that measures the complete chain

`R* -> R -> actual diagnostic ΔQ -> knowledge margin -> recovery -> learning`.

The v0.2 work must preserve v0.1 and must not claim a behavioral benefit unless the intermediate update and knowledge-protection evidence is present.

## Boundaries and invariants

- Keep the 9x7 CausalChase environment, NoiseTape, causal events, counterfactual runner, and no-oracle learner boundary unchanged unless a test demonstrates a v0.2 semantic defect.
- Keep tabular Q-learning; do not add DQN, sequence attention, Shapley, SSP-BO, or fast/slow control.
- Create a clean `v0.2-responsibility-update-learning` branch from the v0.1 result commit. Do not overwrite `outputs/confirmatory_a` or `outputs/pilot_b`.
- Write every new run under `outputs/v02_*` with config hash, git commit, seed manifest, raw JSONL, seed-level CSV, and analysis outputs.
- No pilot parameter may be copied into confirmatory data. Confirmatory settings are frozen before any confirmatory run.
- `OracleEvaluator` and oracle labels are evaluator-only. Learner-facing attribution and routing interfaces must not receive `oracle_R`, `oracle_delta`, or an evaluator instance.

## Core semantic correction

`UpdateRouter.route()` must produce a routed update whose actual Q change is scaled additive diagnostic learning:

```text
ΔQ_H = -alpha_diag * R_H
ΔQ_L = -alpha_diag * R_L
```

`UpdateRouter.apply()` must return an `AppliedUpdate` record for each changed slot, containing module, site, `q_before`, `q_after`, and `delta_q`. Metrics must read `delta_q` from these records rather than infer actual updates from proposed responsibility.

## Metrics and scenarios

Keep AE and legacy WUR for continuity, and add actual-update metrics:

- update precision, recall, and F1 against `alpha_diag * R*`;
- actual wrong-update rate from applied `delta_q`;
- correct-knowledge damage (CKD), wrong-knowledge reinforcement (WKR);
- recovery episodes with the three-checkpoint 0.95-margin rule;
- real, counterfactual, replay, and wall-clock cost fields.

The update microbenchmark has four acceptance-filtered scenario families: high-protection (L-dominant failure with false H), low-protection (H-dominant failure with false L), environment/mixed responsibility using the actual mixed oracle, and H+L mixed responsibility. Every algorithm receives a cloned Q snapshot and exactly one diagnostic update; ordinary task Q-learning is disabled during the shock.

## Experiment stages

### Experiment A v0.2

- `attribution`: frozen v0.1 replication (AR), 30 H/L/E traces per seed in pilot/confirmatory.
- `update`: responsibility-to-update microbenchmark (AU), 10 scenarios per type in pilot and 20 per type in confirmatory.
- `all`: runs both stages and writes paired seed-level metrics.

### Experiment B v0.2

- `checkpoint`: train Standard-HQ once for 5,000 episodes, clone a bitwise-identical checkpoint to every algorithm, and enforce pre-shock success and safe-option gates.
- `transfer`: apply 20 controlled misleading-feedback shocks (10 L-dominant/false-H and 10 H-dominant/false-L), then run 500 recovery episodes with true task reward only.
- `online`: train from scratch in the original B4 environment with `p_false=0.40`, recording success AUC, EpisodesTo90, and final-success non-inferiority.

## Verification gates

1. Full existing pytest suite passes.
2. New router scaling, knowledge, update-metric, scenario, checkpoint, and recovery tests pass.
3. v0.2 smoke passes with small deterministic settings and validates output schema and oracle isolation.
4. Pilot uses 12 seeds to lock runtime, variance, and the 5,000-episode pretrain setting.
5. Confirmatory uses 50 fresh paired seeds only after the preceding gates pass.

The following outcomes are valid and must be reported without post-hoc tuning: AE improves but F1U does not; F1U improves but CKD does not; CKD and recovery improve without policy utility; or the complete chain improves. If a gate fails, stop that downstream stage and retain the failure artifacts for audit.

## Error handling and reproducibility

Smoke and pilot failures stop the command with a non-zero exit code and a clear gate message. Every record keeps learner and evaluator namespaces separate. The common-checkpoint stage asserts identical `QTables.deep_hash()` values before shock. Any incomplete confirmatory run is resumable by seed and never overwrites completed seed files.
