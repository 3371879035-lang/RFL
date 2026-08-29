# RFL-CausalChase v0.2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the Word-specified v0.2 chain `responsibility -> actual update -> knowledge state -> recovery/learning` while preserving v0.1 outputs and interfaces.

**Architecture:** Add v0.2 primitives beside the frozen v0.1 modules. The router returns auditable `AppliedUpdate` records, pure knowledge/actual-update metrics consume those records, acceptance-filtered scenarios provide known-good knowledge labels, and separate v0.2 scripts orchestrate attribution/update microbenchmarks plus common-checkpoint transfer and online learning. All new runs use `outputs/v02_*` and remain evaluator/learner isolated.

**Tech Stack:** Python 3.11+, NumPy, pandas, SciPy, PyYAML, pytest, existing `rflcc` tabular simulator and statistics helpers.

---

### Task 1: Create the clean v0.2 branch baseline and smoke configuration

**Files:**
- Create: `configs/v02_smoke.yaml`, `configs/v02_pilot.yaml`, `configs/v02_confirmatory.yaml`
- Create: `scripts/smoke_v02.py`
- Test: `tests/test_imports.py`

- [ ] **Step 1: Record the clean starting commit and branch**

Run `git status --short` and `git rev-parse HEAD`; the worktree must contain no tracked changes before implementation files are edited.

- [ ] **Step 2: Add the three frozen YAML configurations**

Use the Word values exactly: smoke seeds=2, attribution_per_cause=5, update_scenarios_per_type=3, pretrain=200, shocks=4, recovery=50, online=300; pilot seeds=12, per-cause=30, update scenarios=10, pretrain=5000, shocks=20, recovery=500, online=5000; confirmatory seeds=50, seed_base=3000000, per-cause=30, update scenarios=20, pretrain=5000, shocks=20, recovery=500, online=5000. Include `diagnostic_update_semantics: scaled_additive`, `routing.primary: last_action`, `routing.secondary_cf_critical: true`, and the frozen v0.1 environment/sequence/feedback values.

- [ ] **Step 3: Implement `scripts/smoke_v02.py` as a real gate runner**

The CLI accepts `--config` and `--stage {all,router,metrics,scenarios,experiments}`. It runs the selected pytest files, then calls the v0.2 A/B smoke functions, exits non-zero on any failed gate, writes `outputs/v02_smoke/run_meta.json`, and never writes to a v0.1 output directory.

- [ ] **Step 4: Run the import and configuration smoke checks**

Run `python -m pytest tests/test_imports.py -q` and `python scripts/smoke_v02.py --config configs/v02_smoke.yaml --stage router`; expected result is exit 0 after Tasks 2-4 are implemented.

- [ ] **Step 5: Commit the configuration scaffold**

Run `git add configs/v02_*.yaml scripts/smoke_v02.py` and commit with `chore: scaffold v0.2 configs and smoke entrypoint`.

### Task 2: Fix scaled diagnostic updates and return actual update receipts

**Files:**
- Modify: `src/rflcc/router.py`
- Modify: `tests/test_router.py`
- Create: `tests/test_router_scaling.py`

- [ ] **Step 1: Add the failing scaling test**

```python
def test_apply_uses_scaled_additive_delta_and_returns_receipt():
    q = QTables()
    routed = UpdateRouter(alpha_diag=0.1).route(
        responsibility={"H": 1.0, "L": 0.0, "E": 0.0},
        s_h=0, option=0, last_low=None,
    )
    applied = UpdateRouter(alpha_diag=0.1).apply(q, routed)
    assert applied[0].delta_q == pytest.approx(-0.1)
    assert applied[0].q_before == pytest.approx(0.0)
    assert applied[0].q_after == pytest.approx(-0.1)
```

- [ ] **Step 2: Run the focused test and verify the current failure**

Run `python -m pytest tests/test_router_scaling.py -q`; it must fail because `apply()` currently returns `None` and writes unscaled `rho`.

- [ ] **Step 3: Implement `AppliedUpdate` and scaled `apply()`**

Add a frozen dataclass with fields `module`, `site`, `q_before`, `q_after`, and `delta_q`. In `route()`, store `rho` as `-alpha_diag * R` in the routed tuples while retaining `update_mass` as absolute scaled mass. In `apply()`, read the old Q, call the existing `high_update`/`low_update` with target `old + delta_q` and `alpha=1.0`, append one receipt per changed site, and return `list[AppliedUpdate]`. Keep E-only zero responsibility from creating internal receipts.

- [ ] **Step 4: Update the legacy router assertion to the v0.2 semantic**

Change only the assertion in `tests/test_router.py::test_router_apply_updates_q` from `-1.0` to `-0.1`; preserve all routing-site and E-only assertions.

- [ ] **Step 5: Run router regression tests**

Run `python -m pytest tests/test_router.py tests/test_router_scaling.py -q`; expected result is all router tests passing.

- [ ] **Step 6: Commit the router semantic fix**

Run `git add src/rflcc/router.py tests/test_router.py tests/test_router_scaling.py` and commit with `fix: scale v0.2 diagnostic updates and record receipts`.

### Task 3: Add pure knowledge-state metrics

**Files:**
- Create: `src/rflcc/knowledge.py`
- Create: `tests/test_knowledge_metrics.py`

- [ ] **Step 1: Write deterministic margin and damage tests**

```python
def test_margin_damage_and_reinforcement():
    before = {"safe": 0.60, "unsafe": 0.0}
    after = {"safe": 0.50, "unsafe": 0.0}
    assert correct_margin(before, "safe") == pytest.approx(0.60)
    assert correct_knowledge_damage(before, after, "safe") == pytest.approx(1/6)
    assert wrong_knowledge_reinforcement(before, {"safe": 0.60, "unsafe": 0.10}, "safe", "unsafe") > 0
```

- [ ] **Step 2: Implement pure functions**

Implement `correct_margin(values, correct_key)`, `wrong_margin(values, correct_key, wrong_key)`, `correct_knowledge_damage(before, after, correct_key, eps=1e-9)`, `wrong_knowledge_reinforcement(before, after, correct_key, wrong_key, eps=1e-9)`, and `recovery_episode(margins, initial_margin, fraction=0.95, consecutive=3, checkpoint_interval=10, horizon=500)`. Use the exact formulas from the Word plan; return `horizon + 1` for right-censored recovery.

- [ ] **Step 3: Run the pure metric tests**

Run `python -m pytest tests/test_knowledge_metrics.py -q`; expected result is PASS with no environment or Oracle imports.

- [ ] **Step 4: Commit the knowledge metric layer**

Run `git add src/rflcc/knowledge.py tests/test_knowledge_metrics.py` and commit with `feat: add pure knowledge damage and recovery metrics`.

### Task 4: Add actual-update precision/recall metrics

**Files:**
- Modify: `src/rflcc/metrics.py`
- Modify: `tests/test_metrics.py`
- Create: `tests/test_update_metrics.py`

- [ ] **Step 1: Add failing tests for actual receipts**

Test `update_precision`, `update_recall`, `update_f1`, and `actual_wrong_update_rate` using `AppliedUpdate(module="H", delta_q=-0.1)` and oracle responsibility `{H: 1, L: 0, E: 0}`. Assert precision, recall, and F1 are 1.0, and assert a low-level update against an H-only oracle receives zero precision.

- [ ] **Step 2: Implement `compute_update_metrics()`**

Aggregate `abs(delta_q)` by H/L from receipts; compare with `alpha_diag * oracle_r[H/L]`; use soft overlap `min(actual, expected)` and `eps=1e-9`. Return a dataclass or dict containing actual mass, precision, recall, F1, and WUR. Do not call or import `OracleEvaluator`; the oracle responsibility is an explicit evaluator-side argument.

- [ ] **Step 3: Preserve v0.1 API compatibility**

Keep `compute_attribution_metrics()` unchanged for old callers, and add new functions without changing its argument names or behavior. Add a regression test proving the old test vectors remain identical.

- [ ] **Step 4: Run metric tests**

Run `python -m pytest tests/test_metrics.py tests/test_update_metrics.py -q`; expected result is PASS.

- [ ] **Step 5: Commit the actual-update metrics**

Run `git add src/rflcc/metrics.py tests/test_metrics.py tests/test_update_metrics.py` and commit with `feat: measure actual diagnostic update fidelity`.

### Task 5: Build acceptance-filtered update scenarios

**Files:**
- Create: `src/rflcc/update_scenarios.py`
- Create: `tests/test_update_scenarios.py`

- [ ] **Step 1: Define `KnowledgeScenario` and acceptance predicates**

Use fields `scenario_id`, `trace`, `oracle_r`, `feedback`, `q_snapshot`, `correct_items`, and `wrong_items`. Implement predicates for high protection (`R*_L >= 0.8, R*_H <= 0.1`), low protection (`R*_H >= 0.8, R*_L <= 0.1`), environment/mixed, and H+L mixed (`R*_H >= .2, R*_L >= .2, R*_H+R*_L >= .7`).

- [ ] **Step 2: Implement the four generators**

Implement `make_high_protection`, `make_low_protection`, `make_environment_mixed`, and `make_hl_mixed` using existing `ScenarioGenerator`, `OracleEvaluator`, and `QTables`. Each generated scenario must carry the actual evaluator responsibility, false diagnostic label, and a cloned Q snapshot; reject candidates that fail the acceptance predicate instead of forcing geometry.

- [ ] **Step 3: Add scenario tests**

Assert every returned scenario meets its predicate, has non-null NoiseTape, and has a Q snapshot whose correct margin is 0.60. Assert H+L mixed preserves proportional oracle mass instead of converting to one-hot.

- [ ] **Step 4: Run scenario tests and commit**

Run `python -m pytest tests/test_update_scenarios.py -q`; then commit with `git add src/rflcc/update_scenarios.py tests/test_update_scenarios.py` and `git commit -m "feat: add acceptance-filtered update shock scenarios"`.

### Task 6: Implement v0.2 Experiment A (attribution and update microbenchmarks)

**Files:**
- Create: `scripts/experiment_a_v02.py`
- Modify: `src/rflcc/logging_io.py`
- Modify: `schemas/episode.schema.json`
- Create: `tests/test_experiment_a_v02.py`

- [ ] **Step 1: Add stage-level smoke tests**

Assert `--stage attribution` delegates to the frozen v0.1 methods without changing their outputs, and `--stage update` clones each Q snapshot, attributes without Oracle access, routes, snapshots before/after, applies once, and emits actual-update plus CKD/WKR metrics.

- [ ] **Step 2: Implement the attribution stage**

Reuse `experiment_a.py` calibration and scenario generation with the v0.2 config; write seed-level rows for AE/WUR/coverage and preserve paired clean/symmetric feedback. Do not train Q in this stage.

- [ ] **Step 3: Implement the update stage**

For each four-family shock, clone Q, call the selected learner algorithm, call `UpdateRouter.route()`, snapshot before, call `apply()`, snapshot after, compute actual update metrics and knowledge metrics, and record exactly one diagnostic update. Provide `--stage all` to run both and return a non-zero code if smoke acceptance counts are wrong.

- [ ] **Step 4: Extend the schema and logger**

Add `q_margin_before`, `q_margin_after`, `actual_update`, `update_precision`, `update_recall`, `update_f1`, `correct_knowledge_damage`, `wrong_knowledge_reinforcement`, and `recovery_episode` under learner/metrics while keeping oracle fields only in `evaluator_only`. Keep `additionalProperties: false` and update schema tests.

- [ ] **Step 5: Run A-v0.2 smoke tests**

Run `python -m pytest tests/test_experiment_a_v02.py tests/test_no_oracle_leakage.py -q` and `python scripts/experiment_a_v02.py --config configs/v02_smoke.yaml --stage all`; expected result is valid raw JSONL and non-zero actual updates in update scenarios.

- [ ] **Step 6: Commit Experiment A v0.2**

Run `git add scripts/experiment_a_v02.py src/rflcc/logging_io.py schemas/episode.schema.json tests/test_experiment_a_v02.py` and commit with `feat: add v0.2 attribution and update microbenchmarks`.

### Task 7: Implement common checkpoints and B-Transfer/B-Online

**Files:**
- Create: `src/rflcc/checkpoints.py`, `tests/test_common_checkpoint.py`, `tests/test_recovery.py`
- Create: `scripts/experiment_b_v02.py`

- [ ] **Step 1: Add checkpoint identity tests**

Train one Standard-HQ smoke checkpoint, clone it to Immediate, PE-Seq, Full-RFL, and OracleUpdate, and assert `QTables.deep_hash()` is equal before shock. Assert clones diverge only after their diagnostic update.

- [ ] **Step 2: Implement checkpoint save/load**

Use a deterministic JSON/pickle-free representation of the existing dict tables or a deep copy plus `deep_hash`; save `checkpoint_meta.json` with seed, episode count, hash, and config hash. Reject loading a checkpoint with a mismatched hash or schema version.

- [ ] **Step 3: Implement `--stage checkpoint`**

Train Standard-HQ for configured pretrain episodes, evaluate success and safe-option accuracy, enforce both >=0.90 in pilot/confirmatory, and write one common checkpoint per seed.

- [ ] **Step 4: Implement `--stage transfer`**

Apply 10 L-dominant/false-H and 10 H-dominant/false-L shocks per seed with task Q update disabled, compute CKD/WKR/update fidelity, then run 500 recovery episodes using true task reward only. Evaluate every 10 or 25 episodes and record right-censored recovery as 501.

- [ ] **Step 5: Implement `--stage online`**

Reuse the frozen B4 environment with `p_false=0.40`, train each primary algorithm from scratch for 5000 episodes, evaluate every 25 episodes, and write seed-level success AUC, EpisodesTo90, and final success/non-inferiority.

- [ ] **Step 6: Run B-v0.2 smoke and tests**

Run `python -m pytest tests/test_common_checkpoint.py tests/test_recovery.py -q` and `python scripts/experiment_b_v02.py --config configs/v02_smoke.yaml --stage transfer`; expected result is identical pre-shock hashes, finite recovery outputs, and no Oracle calls from learner code.

- [ ] **Step 7: Commit Experiment B v0.2**

Run `git add src/rflcc/checkpoints.py tests/test_common_checkpoint.py tests/test_recovery.py scripts/experiment_b_v02.py` and commit with `feat: add common-checkpoint transfer and online v0.2 experiments`.

### Task 8: Add v0.2 statistics, analysis, documentation, and gates

**Files:**
- Create: `scripts/analyze_v02.py`
- Modify: `README.md`, `CHANGELOG.md`
- Create: `tests/test_v02_outputs.py`

- [ ] **Step 1: Implement analysis outputs**

Use existing seed-level paired sign-flip, bootstrap CI, Cohen dz, and Holm helpers. Compare Full-RFL-Immediate for AE/F1U/CKD/Recovery and Full-RFL-Standard for behavioral non-inferiority. Never compute episode-level p-values.

- [ ] **Step 2: Add output integrity tests**

Validate 50-seed and pilot row counts, config hash/commit presence, JSONL schema, evaluator-only oracle fields, and separate `outputs/v02_*` directories. Assert all actual update masses equal the sum of receipt `abs(delta_q)`.

- [ ] **Step 3: Update README and changelog**

Document the exact smoke -> pilot -> confirmatory command sequence, the missing `smoke.py` replacement, the v0.2 branch, output directories, and the five valid result interpretations from the Word plan. State that v0.1 outputs are never overwritten.

- [ ] **Step 4: Run the complete test suite and smoke gate**

Run `python -m pytest -q`, then `python scripts/smoke_v02.py --config configs/v02_smoke.yaml --stage all`; expected result is exit 0 and all old/new tests passing.

- [ ] **Step 5: Commit the v0.2 gate and docs**

Run `git add scripts/analyze_v02.py tests/test_v02_outputs.py README.md CHANGELOG.md` and commit with `docs: add v0.2 analysis and reproducibility gates`.

### Task 9: Pilot, freeze, and confirmatory execution

**Files:**
- Generate only under: `outputs/v02_pilot_*`, `outputs/v02_confirmatory_*`
- Record: `outputs/v02_reproducibility/environment.txt`, `python_version.txt`, `dependency_versions.txt`, `git_commit.txt`, `config_hashes.txt`, `seed_manifest.csv`, `benchmark.json`

- [ ] **Step 1: Run pilot commands in order**

Run `python scripts/smoke_v02.py --config configs/v02_smoke.yaml --stage all`, then `python scripts/experiment_a_v02.py --config configs/v02_pilot.yaml --stage all`, `python scripts/experiment_b_v02.py --config configs/v02_pilot.yaml --stage transfer`, and `python scripts/experiment_b_v02.py --config configs/v02_pilot.yaml --stage online`.

- [ ] **Step 2: Analyze pilot and freeze parameters**

Run `python scripts/analyze_v02.py --dir outputs/v02_pilot`; verify pre-shock gates, runtime, variance, and update receipt semantics. Record the frozen config hashes and do not alter confirmatory configs based on confirmatory data.

- [ ] **Step 3: Run confirmatory only after all gates pass**

Run the same A/B commands with `configs/v02_confirmatory.yaml`, 50 fresh paired seeds, and resumable per-seed outputs. If any gate fails, stop downstream confirmatory execution and report the failure stage.

- [ ] **Step 4: Run final analysis and integrity verification**

Run `python scripts/analyze_v02.py --dir outputs/v02_confirmatory`, `python -m pytest -q`, and the output-integrity tests. Only report the chain as supported if H-A, H-U, H-K, and at least one recovery/learning endpoint meet their preregistered thresholds.

- [ ] **Step 5: Commit and push reproducibility artifacts**

Commit only v0.2 code, configs, tests, metadata, and results; never stage `.pyc`, v0.1 output directories, or failed exploratory data. Push `v0.2-responsibility-update-learning` to `origin` and record the commit in the final report.
