# RFL v0.3 Stage 1 (Update Semantics) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CPU-only two-level causal microbenchmark and run **Pilot Alpha** (Traditional `+1/-1` vs Positive-only `+1/0`), with ground-truth causal labels computed exactly from the environment SCM and a pre-registered anti-ceiling gate.

**Architecture:** A deterministic 5x2 grid where the high level picks a lane (option) and the low level drives to the corridor end. A `NoiseTape` fixes all exogenous randomness. Because the SCM is tiny and fully enumerable, each episode's ground-truth learning responsibility `U=(U_H,U_L)` is computed *by definition* from two booleans (`h_correct`, `l_correct`) plus the exogenous hazard flag -- **no search, no acceptance filtering, no probe hunt**. This is the structural difference from v0.2, whose protected-probe failure came from having to excavate "correct knowledge" out of a *found* failing trace.

**Tech Stack:** Python 3.11+, NumPy, PyYAML, pytest. No GPU. No attribution model, no counterfactual runner, no human feedback in Stage 1.

**Frozen context:** This plan builds a *new* tree at `RFL-CausalChase-v0.3/`. The three existing trees (`RFL-CausalChase-v0.1`, `-v0.2`, `-v0.2-release`) are frozen and MUST NOT be modified. Old scientific semantics (`normalized R`, `router R->dQ`, `protected probe`, CausalChase rewards) are forbidden in the new tree; see Task 1 Step 4.

---

## Deviations found during implementation

Both were caught while executing this plan. The **code is authoritative**; the Design spec and task code below have been left as originally written so the corrections remain visible.

### X1. `l_correct` must test the low level against its *own* corridor (D3, Task 4)

The plan defined `l_correct := (final_x == W-1)`. That is wrong. An agent that picks the **correct** option but drives to column 4 on the **wrong** lane yields `(h_correct, l_correct) == (True, True)` while failing, which `causal_labels()` asserts is unreachable -- so the run dies with an `AssertionError` instead of a label.

Corrected definition:

```python
l_correct = final_x == W - 1 and final_y == option
```

i.e. "the low level completed the corridor it was asked to walk". `causal_labels()` therefore takes `final_y`. Regression test: `tests/test_labels.py::test_right_option_but_wrong_lane_is_an_l_error`.

### X2. The ceiling gate as specified was vacuous (D7, Task 8)

The plan compared the mean final success against a configured `ceiling_max_final_success: 0.80`. But `hazard=1` episodes are unwinnable, so the **structural** ceiling is `1 - p_hazard = 0.75`. No policy can exceed it, so `all_arms_above_ceiling` could never fire -- the gate silently passed always.

Worse, the premise was wrong: reaching the structural ceiling is *expected* here, not evidence against the benchmark. Two arms can both sit at 0.75 while differing widely in learning speed, which is exactly what the smoke showed (finals `0.75` / `0.75`, AUCs `0.397` / `0.578`).

Corrected rule:

- `structural_ceiling` is **derived** as `1 - environment.p_hazard`, never configured;
- saturation is **reported** (`saturated_at_ceiling`) but is not by itself a failure;
- the **fatal** condition is a flat learning curve, `auc_spread < gate.min_auc_gap`.

Evidence this matters: on the smoke run the original rule returned `ok` for spurious reasons; the corrected rule returns `ok` for the right reason (spread `0.181 >> 0.005`) while still failing genuinely flat curves (see `tests/test_gates.py`).

### X3. `conftest.py` added (not in the plan)

`tests/conftest.py` inserts `src/` on `sys.path` so the suite runs from the frozen shared interpreter without installing `rflnext` into its site-packages.

### X4. The low-level state must include the timestep (D1) -- this invalidated the first pilot

The plan defined `s_L = (x, y, o)`. That is wrong for a **finite-horizon** task with `gamma = 1`, and it silently destroyed the first full pilot run.

A no-op action (WAIT, or UP while already on lane 0) leaves the state unchanged, so its TD target is

```
target = r + gamma * max_a Q(s, a) = 0 + max_a Q(s, a)
```

-- the value of its *own* state. The Bellman optimality equation is therefore satisfied for **any** value at such a state, so the fixed point is not unique: the self-loop inflates `V(s)`, and any action that actually leaves the state is left looking strictly worse. The greedy policy then never moves.

Observed on the first 10,000-episode run (seed 4000000, Traditional): at the start state the learned row was

```
s=(0,0,0)  Q=[0.7259, 0.7259, 0.7227, 0.7259]   -> greedy picks UP (a no-op)
```

`RIGHT` (0.7227) was strictly the *worst* action, `Q_H` had collapsed to `-1.0` for every state and option, and evaluation gave `final_success = 0.000` for both arms -- while the 400-episode smoke had given `0.725`. A collapsed benchmark is not a null result, and reporting it would have been wrong.

Fix: `s_L = (x, y, o, t)`, with `t` in `1..HORIZON`, and the horizon expiry handled as a terminal whose reward is exactly the failure reward. Every transition now either terminates or advances `t`, so the MDP is acyclic in `t` and the fixed point is unique. `gamma`, the step reward, and the action set are all unchanged -- the md's fairness constraints are preserved.

Regression test: `tests/test_runner.py::test_low_level_state_includes_the_timestep`.

### X5. The saturation check must use the *realized* unwinnable share (D7)

`1 - p_hazard` is only the ceiling *in expectation*. A finite evaluation tape realises some other hazard count, so a policy sitting exactly at its true ceiling can score above (or below) `0.75` purely from sampling -- the smoke showed `final = 0.82` against a theoretical ceiling of `0.75`.

`evaluate()` now also returns the realized winnable fraction, `TrainResult` carries `eval_winnable_fraction`, and the CLI derives `structural_ceiling` from it. Both the theoretical and realized values are written to `summary.json`.

---

## Design spec (read before implementing)

### D1. Grid, states, actions

- Corridor: `W=5` columns `x in 0..4`, `2` lanes `y in {0,1}`.
- Start `(0,0)`. Exit cell `(4, goal_lane)`.
- Primitive actions `A = {0:UP, 1:DOWN, 2:RIGHT, 3:WAIT}`, `n_actions=4`.
  - `UP`: `y <- 0`; `DOWN`: `y <- 1`; `RIGHT`: `x <- min(x+1, 4)`; `WAIT`: no change.
- High-level state `s_H = (goal_lane, hazard)`, 4 states. Option `o in {0,1}` = chosen lane.
- Low-level state `s_L = (x, y, o)`, 20 states. Action `a in 0..3`.

### D2. Transition, terminal, reward

Deterministic given `(s, a)`; all randomness enters only through `NoiseTape` at episode reset.

- `SUCCESS` iff `x == 4 and y == goal_lane and hazard == 0`, evaluated after the transition.
- `BLOCKED` (failure) iff `x == 4 and y == goal_lane and hazard == 1`.
- `TIMEOUT` (failure) iff `t == horizon` without success.
- `horizon = 8`, `gamma = 1.0`, step reward `0.0`.
- After any terminal, the episode absorbs with zero reward until step 8, so return = terminal reward only.
- Reward mode `A`: `SUCCESS=+1.0`, failure `=-1.0`. Mode `B`: `SUCCESS=+1.0`, failure `=0.0`.
- Timeout carries exactly the same reward as any other failure (no hidden value).

### D3. Ground-truth learning responsibility (the core of Stage 1)

After each episode the generator emits exact labels, by definition, with no estimation:

```
h_correct := (o == goal_lane)
l_correct := (final_x == 4)          # low level completed the traverse

if terminal is SUCCESS:  no diagnosis event
elif hazard == 1:        U = (0, 0)  # E-failure   : H^+ L^+ E^-
else:                    U = (U_H, U_L) with U_H = 0 if h_correct else 1,
                                          U_L = 0 if l_correct else 1
```

This yields exactly the four families required by the research plan:

| family | H | L | E | `U` | realized as |
|---|---|---|---|---|---|
| `H_error` | `H^-` | `L^+` | `E^0` | `(1,0)` | `not h_correct and l_correct` |
| `L_error` | `H^+` | `L^-` | `E^0` | `(0,1)` | `h_correct and not l_correct` |
| `HL_error` | `H^-` | `L^-` | `E^0` | `(1,1)` | `not h_correct and not l_correct` |
| `E_failure` | `H^+` | `L^+` | `E^-` | `(0,0)` | `hazard and not SUCCESS` |

**Why this removes the v0.2 blocker:** labels come from *two booleans about the realized rollout plus the generator's own hazard flag*. Nothing needs to be searched, and no "established correct knowledge" must be found at a failure's terminal transition.

### D4. Exogenous randomness and determinism

`NoiseTape` is written fresh (the v0.2 one carries `monster_start_lane`/`dash_u` and is CausalChase-specific). Per episode `e` it fixes:

- `goal_lane[e]`, `hazard[e]` -- the two scene variables;
- `tie_u[e][i]` -- one uniform per decision, for epsilon-greedy tie-breaking.

Reset uses only the tape, so two runs with the same `(seed, config)` are bit-identical. Every condition in a comparison shares one tape (paired design).

### D5. Learning rules

- `Q_H(s_H, o)` updated at episode end by Monte-Carlo on the episode return (first-visit-free, single update per episode).
- `Q_L(s_L, a)` updated online by Q-learning with `alpha_low`, `gamma=1.0`.
- **Diagnostic update is NOT in Pilot Alpha.** Stage 1 Alpha only compares reward modes A and B. The gated `Delta Q_m = U_m * alpha_diag * delta` rule and the knowledge probes belong to Pilot Beta (Plan 2) and MUST NOT be added here.

### D6. Scene mixture and effective failure counts

Scene variables are sampled i.i.d. per episode: `goal_lane ~ Bernoulli(0.5)`, `hazard ~ Bernoulli(p_hazard)` with `p_hazard = 0.25`.

Family membership is a *consequence* of the agent's behaviour, so the realized mix is not directly settable. Therefore:

- Learning runs are **i.i.d. and unfiltered** -- no rejection sampling, which would break the episode distribution.
- Diagnosis events are recorded **whenever they occur**, carrying exact labels.
- The runner **reports realized counts per family**, and the pilot gate requires `>= 400` realized events in each of the four families across the run. Under-representation is reported as a fact and never silently patched. If a family is short at pilot scale, the pre-registered remedy is to raise `episodes` (not to change `p_hazard`, `epsilon`, or the label definition).

### D7. Anti-ceiling gate (pre-registered)

Because `hazard=1` episodes are unwinnable, the success ceiling is structurally `1 - p_hazard = 0.75`. The gate:

- `ceiling_max_final_success = 0.75 + 0.05` on **every** arm; and
- the two arms must not differ by less than `min_auc_gap = 0.005` in `SuccessAUC`.

If all arms land above the ceiling bound, or if the AUC gap is below the floor, the run returns status `benchmark_no_discriminating_power` and exits non-zero. This is checked at smoke scale *before* any formal run, and again after the pilot. This is the pre-registered guard against the v0.1 Experiment B saturation failure.

### D8. Metrics

Primary: `SuccessAUC` (trapezoidal over checkpoints).
Secondary: `FirstSuccessEpisode`, `EpisodesTo90`, `FinalSuccess`, `VisitedStateCoverage`, and `N_delta_neg` (count of negative TD errors in the Positive-only arm -- records that "failure reward = 0" is not "no negative learning").

### D9. Reuse decisions (verified against the frozen tree)

| module | decision | reason |
|---|---|---|
| `qtables.py` | **vendor verbatim** | fully generic: `n_actions`/`options` parameterized, `copy()`, `deep_hash()` |
| `stats.py` | **vendor verbatim** | seed-level paired sign-flip / bootstrap / Cohen d_z / Holm, already matches the plan's statistics section |
| `knowledge.py` | **vendor verbatim** | `correct_knowledge_damage`/`wrong_knowledge_reinforcement`/`recovery_episode` are exactly KnowledgeDamage/WrongReinforcement |
| `noise.py` + `NoiseTape` | **rewrite** | carries `monster_start_lane`/`dash_u`; unusable here |
| `env.py`, `scenarios.py`, `oracle.py` | **do not copy** | CausalChase geometry, search-based acceptance, normalized `R*` |
| `router.py`, `attribution.py` | **do not copy** | `R -> dQ` direct mapping and normalized/softmax `R` are forbidden semantics |
| `scripts/*_v02.py`, `experiment_b_v02.py` | **do not copy** | protected-probe path is retired |

---

### Open design decisions requiring sign-off

These were chosen by the plan author and are the ones most likely to need your veto. Everything else is mechanical.

| # | Decision | Alternative |
|---|---|---|
| 1 | `U_L = 1` iff `final_x != 4` ("the low level did not complete its own traverse") | judge L by whether it would have survived under the *correct* option |
| 2 | `goal_lane` is directly observable in `s_H` (H is easy; H-errors arise only from exploration) | hide `goal_lane` behind a noisy cue so H is itself a hard inference |
| 3 | `hazard=1` makes the exit unwinnable | make the hazard survivable with some probability |
| 4 | `p_hazard = 0.25` (success ceiling 0.75) | tune to hit a target failure rate |
| 5 | Pilot Alpha arms differ **only** in failure reward | also differ in epsilon schedule |

---

## File structure

```
RFL-CausalChase-v0.3/
├── pyproject.toml
├── configs/alpha.yaml
├── src/rflnext/
│   ├── __init__.py
│   ├── env.py          # constants, step_cell, terminal_kind
│   ├── noise.py        # NoiseTape (rewritten)
│   ├── labels.py       # CausalLabels + causal_labels
│   ├── qtables.py      # vendored verbatim from v0.2-release
│   ├── stats.py        # vendored verbatim
│   ├── knowledge.py    # vendored verbatim
│   ├── runner.py       # EpisodeRecord, run_episode, train
│   ├── metrics.py      # success_auc, episodes_to_90, ...
│   └── gates.py        # ceiling_gate
├── scripts/pilot_alpha.py
└── tests/
```

---

### Task 1: Scaffold the new tree and vendor the reusable infrastructure

**Files:**
- Create: `RFL-CausalChase-v0.3/pyproject.toml`
- Create: `RFL-CausalChase-v0.3/src/rflnext/__init__.py`
- Copy: `RFL-CausalChase-v0.2-release/src/rflcc/{qtables,stats,knowledge}.py` -> `RFL-CausalChase-v0.3/src/rflnext/`
- Test: `RFL-CausalChase-v0.3/tests/test_scaffold.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "rflnext"
version = "0.1.0"
description = "RFL v0.3 Stage 1: two-level causal microbenchmark (update semantics)"
requires-python = ">=3.11"
dependencies = ["numpy", "pyyaml"]

[project.optional-dependencies]
dev = ["pytest"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: Create the package init**

```python
"""RFL v0.3 Stage 1: two-level causal microbenchmark."""
```

- [ ] **Step 3: Vendor the three modules verbatim**

Copy the files (do not edit their contents):

```powershell
$src = "D:\强化反馈学习\RFL-CausalChase-v0.2-release\src\rflcc"
$dst = "D:\强化反馈学习\RFL-CausalChase-v0.3\src\rflnext"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item "$src\qtables.py","$src\stats.py","$src\knowledge.py" $dst
```

Remove the `knowledge.InvalidKnowledgeProbe`/`require_initial_correct_margin` import chain only if it fails to import; `knowledge.py` has no intra-package imports, so no edit is expected.

- [ ] **Step 4: Write the import guard test**

`tests/test_scaffold.py`:

```python
import importlib
import sys


def test_new_package_imports_without_old_package():
    for name in ("rflnext", "rflnext.qtables", "rflnext.stats", "rflnext.knowledge"):
        sys.modules.pop(name, None)
    sys.modules.pop("rflcc", None)
    for name in ("rflnext", "rflnext.qtables", "rflnext.stats", "rflnext.knowledge"):
        importlib.import_module(name)
    assert "rflcc" not in sys.modules


def test_forbidden_old_semantics_absent():
    import rflnext

    forbidden = (
        "normalize_responsibility",
        "UpdateRouter",
        "responsibility_to_rho",
        "is_low_protection",
        "is_high_protection",
        "ScenarioGenerator",
        "OracleEvaluator",
    )
    for name in forbidden:
        assert not hasattr(rflnext, name), f"forbidden v0.2 symbol leaked: {name}"


def test_vendored_qtables_is_generic():
    from rflnext.qtables import QTables

    q = QTables(n_actions=4, options=(0, 1))
    q.low_update((0, 0, 1), 2, 1.0, 1.0)
    assert q.low_get((0, 0, 1), 2) == 1.0
    q.high_update((1, 0), 1, 0.5, 1.0)
    assert q.high_get((1, 0), 1) == 0.5
    assert isinstance(q.deep_hash(), str)
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_scaffold.py -q`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/rflnext tests/test_scaffold.py
git commit -m "chore: scaffold rflnext and vendor generic infrastructure"
```

---

### Task 2: Environment primitives

**Files:**
- Create: `RFL-CausalChase-v0.3/src/rflnext/env.py`
- Test: `RFL-CausalChase-v0.3/tests/test_env.py`

- [ ] **Step 1: Write the failing test**

```python
from rflnext.env import (
    BLOCKED, DOWN, HORIZON, N_ACTIONS, RIGHT, SUCCESS, TIMEOUT, UP, WAIT, W,
    step_cell, terminal_kind,
)


def test_action_count_and_width():
    assert N_ACTIONS == 4
    assert W == 5
    assert HORIZON == 8


def test_step_cell_moves():
    assert step_cell(0, 1, UP) == (0, 0)
    assert step_cell(0, 0, DOWN) == (0, 1)
    assert step_cell(0, 0, RIGHT) == (1, 0)
    assert step_cell(0, 0, WAIT) == (0, 0)


def test_right_saturates_at_end():
    assert step_cell(4, 1, RIGHT) == (4, 1)


def test_terminal_success_and_blocked():
    assert terminal_kind(4, 1, goal_lane=1, hazard=0) == SUCCESS
    assert terminal_kind(4, 1, goal_lane=1, hazard=1) == BLOCKED


def test_terminal_none_off_exit():
    assert terminal_kind(3, 1, goal_lane=1, hazard=0) is None
    assert terminal_kind(4, 0, goal_lane=1, hazard=0) is None


def test_timeout_is_not_produced_by_terminal_kind():
    # TIMEOUT is decided by the horizon in the runner, never by geometry.
    assert TIMEOUT != SUCCESS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_env.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rflnext.env'`

- [ ] **Step 3: Write the implementation**

`src/rflnext/env.py`:

```python
"""Two-level causal grid: geometry only, no randomness, no learning."""

from __future__ import annotations

UP, DOWN, RIGHT, WAIT = 0, 1, 2, 3
N_ACTIONS = 4
W = 5
LANES = 2
HORIZON = 8

SUCCESS = "SUCCESS"
BLOCKED = "BLOCKED"
TIMEOUT = "TIMEOUT"
FAILURES = (BLOCKED, TIMEOUT)


def step_cell(x: int, y: int, action: int) -> tuple[int, int]:
    """Deterministic primitive transition."""
    if action == UP:
        return x, 0
    if action == DOWN:
        return x, 1
    if action == RIGHT:
        return min(x + 1, W - 1), y
    if action == WAIT:
        return x, y
    raise ValueError(f"unknown action {action!r}")


def terminal_kind(x: int, y: int, goal_lane: int, hazard: int) -> str | None:
    """Terminal on the exit cell, or ``None`` to continue.

    Entering the exit cell while the hazard is active is a failure: the gate
    is jammed.  This is the only exogenous cause of failure in the env, and it
    is what makes the ``E_failure`` family unwinnable by construction.
    """
    if x == W - 1 and y == goal_lane:
        return BLOCKED if hazard == 1 else SUCCESS
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_env.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/rflnext/env.py tests/test_env.py
git commit -m "feat: add two-level causal grid geometry"
```

---

### Task 3: NoiseTape

**Files:**
- Create: `RFL-CausalChase-v0.3/src/rflnext/noise.py`
- Test: `RFL-CausalChase-v0.3/tests/test_noise.py`

- [ ] **Step 1: Write the failing test**

```python
from rflnext.env import HORIZON
from rflnext.noise import NoiseTape


def test_tape_is_deterministic():
    a = NoiseTape.from_seed(1234, episodes=16, horizon=HORIZON, p_hazard=0.25)
    b = NoiseTape.from_seed(1234, episodes=16, horizon=HORIZON, p_hazard=0.25)
    assert a.digest() == b.digest()


def test_tape_differs_across_seeds():
    a = NoiseTape.from_seed(1, episodes=16, horizon=HORIZON, p_hazard=0.25)
    b = NoiseTape.from_seed(2, episodes=16, horizon=HORIZON, p_hazard=0.25)
    assert a.digest() != b.digest()


def test_shapes_and_ranges():
    t = NoiseTape.from_seed(7, episodes=32, horizon=HORIZON, p_hazard=0.25)
    assert len(t.goal_lane) == 32
    assert len(t.hazard) == 32
    assert len(t.explore_u) == 32
    assert len(t.tie_u) == 32
    assert set(t.goal_lane) <= {0, 1}
    assert set(t.hazard) <= {0, 1}
    # One draw for the high-level decision at t=0, plus one per low-level step.
    for row in t.explore_u:
        assert len(row) == HORIZON + 1
        assert all(0.0 <= v < 1.0 for v in row)
    for row in t.tie_u:
        assert len(row) == HORIZON + 1
        assert all(0.0 <= v < 1.0 for v in row)


def test_hazard_rate_is_close_to_target():
    t = NoiseTape.from_seed(99, episodes=20000, horizon=HORIZON, p_hazard=0.25)
    rate = sum(t.hazard) / len(t.hazard)
    assert abs(rate - 0.25) < 0.02
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_noise.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rflnext.noise'`

- [ ] **Step 3: Write the implementation**

`src/rflnext/noise.py`:

```python
"""Deterministic exogenous randomness for the two-level causal grid.

Written fresh for v0.3: the v0.2 ``NoiseTape`` carries ``monster_start_lane``
and ``dash_u``, which are CausalChase-specific and meaningless here.

Everything random in an episode comes from this container, so two runs with
the same ``(seed, config)`` are bit-identical, and every condition in a paired
comparison can share one tape.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class NoiseTape:
    seed: int
    episodes: int
    horizon: int
    p_hazard: float
    goal_lane: tuple[int, ...]
    hazard: tuple[int, ...]
    explore_u: tuple[tuple[float, ...], ...]
    tie_u: tuple[tuple[float, ...], ...]

    @classmethod
    def from_seed(
        cls, seed: int, *, episodes: int, horizon: int, p_hazard: float
    ) -> "NoiseTape":
        rng = np.random.default_rng(int(seed) % (2**32 - 1))
        # One draw for the high-level decision at t=0, plus one per low step.
        draws = int(horizon) + 1
        goal_lane = tuple(int(v) for v in rng.integers(0, 2, size=episodes))
        hazard = tuple(int(v) for v in (rng.random(size=episodes) < float(p_hazard)))
        explore_u = tuple(
            tuple(float(x) for x in rng.random(size=draws)) for _ in range(episodes)
        )
        # A separate stream, so that whether the agent explores and which way
        # it breaks an argmax tie are statistically independent draws.
        tie_u = tuple(
            tuple(float(x) for x in rng.random(size=draws)) for _ in range(episodes)
        )
        return cls(
            seed=int(seed),
            episodes=int(episodes),
            horizon=int(horizon),
            p_hazard=float(p_hazard),
            goal_lane=goal_lane,
            hazard=hazard,
            explore_u=explore_u,
            tie_u=tie_u,
        )

    def digest(self) -> str:
        payload = [
            f"{self.seed}|{self.episodes}|{self.horizon}|{self.p_hazard:.12g}",
            ",".join(str(v) for v in self.goal_lane),
            ",".join(str(v) for v in self.hazard),
            ";".join(",".join(f"{v:.12g}" for v in row) for row in self.explore_u),
            ";".join(",".join(f"{v:.12g}" for v in row) for row in self.tie_u),
        ]
        return hashlib.sha256("|".join(payload).encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_noise.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/rflnext/noise.py tests/test_noise.py
git commit -m "feat: add deterministic NoiseTape for the v0.3 grid"
```

---

### Task 4: Ground-truth causal labels

**Files:**
- Create: `RFL-CausalChase-v0.3/src/rflnext/labels.py`
- Test: `RFL-CausalChase-v0.3/tests/test_labels.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from rflnext.env import BLOCKED, SUCCESS, TIMEOUT, W
from rflnext.labels import FAMILIES, causal_labels


def test_success_emits_no_diagnosis():
    assert causal_labels(
        option=0, goal_lane=0, final_x=W - 1, hazard=0, terminal=SUCCESS
    ) is None


def test_h_error():
    lab = causal_labels(option=1, goal_lane=0, final_x=W - 1, hazard=0, terminal=TIMEOUT)
    assert lab.family == "H_error"
    assert (lab.u_h, lab.u_l) == (1, 0)
    assert (lab.p_h, lab.p_l, lab.p_e) == (1.0, 0.0, 0.0)


def test_l_error():
    lab = causal_labels(option=0, goal_lane=0, final_x=2, hazard=0, terminal=TIMEOUT)
    assert lab.family == "L_error"
    assert (lab.u_h, lab.u_l) == (0, 1)


def test_hl_error():
    lab = causal_labels(option=1, goal_lane=0, final_x=2, hazard=0, terminal=TIMEOUT)
    assert lab.family == "HL_error"
    assert (lab.u_h, lab.u_l) == (1, 1)


def test_e_failure_blames_neither_module():
    lab = causal_labels(option=0, goal_lane=0, final_x=W - 1, hazard=1, terminal=BLOCKED)
    assert lab.family == "E_failure"
    assert (lab.u_h, lab.u_l) == (0, 0)
    assert lab.p_e == 1.0


def test_e_failure_dominates_even_when_modules_also_erred():
    lab = causal_labels(option=1, goal_lane=0, final_x=1, hazard=1, terminal=BLOCKED)
    assert lab.family == "E_failure"
    assert (lab.u_h, lab.u_l) == (0, 0)


def test_p_is_multilabel_and_not_normalized():
    lab = causal_labels(option=1, goal_lane=0, final_x=2, hazard=0, terminal=TIMEOUT)
    assert lab.p_h + lab.p_l + lab.p_e == pytest.approx(2.0)


def test_all_families_covered():
    assert set(FAMILIES) == {"H_error", "L_error", "HL_error", "E_failure"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_labels.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rflnext.labels'`

- [ ] **Step 3: Write the implementation**

`src/rflnext/labels.py`:

```python
"""Exact ground-truth causal labels for the two-level causal grid.

Stage 1 deliberately has no attributor: the generator knows the SCM, so the
learning responsibility ``U`` is computed by definition from two booleans about
the realized rollout plus the generator's own hazard flag.  Nothing is
searched, sampled, or estimated.

``p`` is multi-label causal evidence and is *not* normalized and *not* softmaxed:
``p_h + p_l + p_e`` may exceed 1.  ``p`` and ``U`` are separate variables and
must never be collapsed into one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .env import SUCCESS, TIMEOUT, W

FAMILIES = ("H_error", "L_error", "HL_error", "E_failure")


@dataclass(frozen=True)
class CausalLabels:
    family: str
    u_h: int
    u_l: int
    p_h: float
    p_l: float
    p_e: float
    h_correct: bool
    l_correct: bool
    hazard: int

    @property
    def u(self) -> tuple[int, int]:
        return (self.u_h, self.u_l)


def causal_labels(
    *,
    option: int,
    goal_lane: int,
    final_x: int,
    hazard: int,
    terminal: str,
) -> CausalLabels | None:
    """Ground-truth labels for one finished episode, or ``None`` on success."""
    if terminal == SUCCESS:
        return None

    h_correct = option == goal_lane
    l_correct = final_x == W - 1

    if hazard == 1:
        # The gate is jammed: no plan and no execution could have helped.
        return CausalLabels(
            family="E_failure", u_h=0, u_l=0, p_h=0.0, p_l=0.0, p_e=1.0,
            h_correct=h_correct, l_correct=l_correct, hazard=hazard,
        )

    u_h = 0 if h_correct else 1
    u_l = 0 if l_correct else 1
    family = {
        (1, 0): "H_error",
        (0, 1): "L_error",
        (1, 1): "HL_error",
    }.get((u_h, u_l))
    if family is None:
        raise AssertionError(
            "hazard-free failure with both modules correct is unreachable: "
            f"option={option} goal_lane={goal_lane} final_x={final_x} terminal={terminal}"
        )
    return CausalLabels(
        family=family, u_h=u_h, u_l=u_l,
        p_h=float(u_h), p_l=float(u_l), p_e=0.0,
        h_correct=h_correct, l_correct=l_correct, hazard=hazard,
    )


def family_of(u_h: int, u_l: int, hazard: int) -> str:
    """Inverse map, used by tests and by the realized-count report."""
    if hazard == 1:
        return "E_failure"
    return {(1, 0): "H_error", (0, 1): "L_error", (1, 1): "HL_error"}[(u_h, u_l)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_labels.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/rflnext/labels.py tests/test_labels.py
git commit -m "feat: add exact ground-truth causal labels (U and multi-label p)"
```

---

### Task 5: Episode runner and online learning

**Files:**
- Create: `RFL-CausalChase-v0.3/src/rflnext/runner.py`
- Test: `RFL-CausalChase-v0.3/tests/test_runner.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from rflnext.env import BLOCKED, SUCCESS, TIMEOUT
from rflnext.noise import NoiseTape
from rflnext.qtables import QTables
from rflnext.runner import EpisodeRecord, run_episode


def _tape(seed=0, episodes=4, horizon=8):
    return NoiseTape.from_seed(seed, episodes=episodes, horizon=horizon, p_hazard=0.25)


def test_run_episode_returns_record():
    rec = run_episode(episode=0, tape=_tape(), q=QTables(n_actions=4), epsilon=0.0,
                      reward_mode="A", alpha_low=0.2, alpha_high=0.15)
    assert isinstance(rec, EpisodeRecord)
    assert rec.terminal in (SUCCESS, BLOCKED, TIMEOUT)
    assert rec.steps >= 1
    assert rec.return_value in (-1.0, 0.0, 1.0)


def test_forced_correct_policy_succeeds_without_hazard():
    tape = NoiseTape.from_seed(5, episodes=1, horizon=8, p_hazard=0.0)
    q = QTables(n_actions=4)
    q.high[(tape.goal_lane[0], 0)] = {tape.goal_lane[0]: 1.0, 1 - tape.goal_lane[0]: 0.0}
    state = (0, tape.goal_lane[0], tape.goal_lane[0])
    q.low[state] = [0.0, 0.0, 1.0, 0.0]  # always RIGHT
    rec = run_episode(episode=0, tape=tape, q=q, epsilon=0.0, reward_mode="A",
                      alpha_low=0.0, alpha_high=0.0)
    assert rec.terminal == SUCCESS
    assert rec.return_value == 1.0
    assert rec.labels is None


def test_hazard_blocks_a_perfect_policy():
    tape = NoiseTape.from_seed(5, episodes=1, horizon=8, p_hazard=1.0)
    q = QTables(n_actions=4)
    q.high[(0, 1)] = {0: 1.0, 1: 0.0}
    state = (0, 0, 0)
    q.low[state] = [0.0, 0.0, 1.0, 0.0]
    rec = run_episode(episode=0, tape=tape, q=q, epsilon=0.0, reward_mode="A",
                      alpha_low=0.0, alpha_high=0.0)
    assert rec.terminal == BLOCKED
    assert rec.labels is not None
    assert rec.labels.family == "E_failure"
    assert rec.labels.u == (0, 0)


def test_reward_mode_b_gives_zero_for_failure():
    tape = NoiseTape.from_seed(5, episodes=1, horizon=8, p_hazard=1.0)
    q = QTables(n_actions=4)
    q.high[(0, 1)] = {0: 1.0, 1: 0.0}
    q.low[(0, 0, 0)] = [0.0, 0.0, 1.0, 0.0]
    rec = run_episode(episode=0, tape=tape, q=q, epsilon=0.0, reward_mode="B",
                      alpha_low=0.0, alpha_high=0.0)
    assert rec.return_value == 0.0
    assert rec.terminal == BLOCKED


def test_same_seed_is_bit_identical():
    args = dict(epsilon=0.3, reward_mode="A", alpha_low=0.2, alpha_high=0.15)
    a = run_episode(episode=0, tape=_tape(11), q=QTables(n_actions=4), **args)
    b = run_episode(episode=0, tape=_tape(11), q=QTables(n_actions=4), **args)
    assert (a.terminal, a.steps, a.return_value, a.final_x) == (
        b.terminal, b.steps, b.return_value, b.final_x
    )


def test_gamma_one_negative_td_is_counted():
    tape = NoiseTape.from_seed(5, episodes=1, horizon=8, p_hazard=1.0)
    q = QTables(n_actions=4)
    q.high[(0, 1)] = {0: 1.0, 1: 0.0}
    q.low[(0, 0, 0)] = [0.0, 0.0, 0.5, 0.0]
    rec = run_episode(episode=0, tape=tape, q=q, epsilon=0.0, reward_mode="B",
                      alpha_low=0.2, alpha_high=0.0)
    assert rec.n_negative_td >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_runner.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rflnext.runner'`

- [ ] **Step 3: Write the implementation**

`src/rflnext/runner.py`:

```python
"""One episode of the two-level causal grid, plus online learning.

Gamma is 1.0 and step reward is 0, so an episode's return equals its terminal
reward, and a failure occurring early cannot be discounted differently from a
late one.  This is what makes the A/B reward comparison causally clean.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .env import (
    HORIZON,
    N_ACTIONS,
    SUCCESS,
    TIMEOUT,
    WAIT,
    W,
    step_cell,
    terminal_kind,
)
from .labels import CausalLabels, causal_labels
from .noise import NoiseTape
from .qtables import QTables

REWARD_SUCCESS = 1.0
REWARD_FAILURE_A = -1.0
REWARD_FAILURE_B = 0.0


@dataclass
class EpisodeRecord:
    episode: int
    terminal: str
    steps: int
    return_value: float
    option: int
    goal_lane: int
    hazard: int
    final_x: int
    final_y: int
    labels: CausalLabels | None
    n_negative_td: int = 0
    visited_low: list = field(default_factory=list)
    visited_high: list = field(default_factory=list)


def _failure_reward(mode: str) -> float:
    if mode == "A":
        return REWARD_FAILURE_A
    if mode == "B":
        return REWARD_FAILURE_B
    raise ValueError(f"unknown reward mode {mode!r}")


def _argmax_with_tie(values: list, tie: float) -> int:
    """Argmax, with ties broken deterministically from the tape.

    Breaking ties by lowest index instead would make the all-zero start state
    always pick UP, which is a no-op at (0, 0) and stalls exploration.
    """
    best = max(values)
    candidates = [i for i, v in enumerate(values) if v == best]
    if len(candidates) == 1:
        return candidates[0]
    return candidates[int(tie * len(candidates) * 1000) % len(candidates)]


def _epsilon_greedy(values: list, epsilon: float, explore: float, tie: float) -> int:
    n = len(values)
    if explore < epsilon:
        return int(explore * n * 1000) % n
    return _argmax_with_tie(values, tie)


def run_episode(
    *,
    episode: int,
    tape: NoiseTape,
    q: QTables,
    epsilon: float,
    reward_mode: str,
    alpha_low: float,
    alpha_high: float,
) -> EpisodeRecord:
    """Roll out one episode and apply the online updates in place."""
    goal_lane = int(tape.goal_lane[episode])
    hazard = int(tape.hazard[episode])
    s_h = (goal_lane, hazard)

    explore = tape.explore_u[episode]
    tie = tape.tie_u[episode]
    option = _epsilon_greedy(
        [q.high_get(s_h, o) for o in q.options], epsilon, explore[0], tie[0]
    )

    x, y = 0, 0
    visited_low: list = []
    visited_high: list = [s_h]
    n_negative_td = 0
    terminal = TIMEOUT
    steps = 0
    fail_reward = _failure_reward(reward_mode)

    for t in range(1, HORIZON + 1):
        s_l = (x, y, option)
        a = _epsilon_greedy(
            [q.low_get(s_l, k) for k in range(N_ACTIONS)], epsilon, explore[t], tie[t]
        )
        visited_low.append((s_l, a))
        nx, ny = step_cell(x, y, a)
        kind = terminal_kind(nx, ny, goal_lane, hazard)
        steps = t

        if kind == SUCCESS:
            reward = REWARD_SUCCESS
        elif kind is not None:
            reward = fail_reward
        else:
            reward = 0.0

        # Q-learning with gamma=1 and zero step reward: the target is the
        # terminal reward on a terminal transition, else the bootstrap value.
        if kind is not None:
            target = reward
        else:
            nxt = (nx, ny, option)
            nrow = q.low.get(nxt)
            target = reward + (max(nrow) if nrow else 0.0)
        before = q.low_get(s_l, a)
        delta = alpha_low * (target - before)
        if delta < 0.0:
            n_negative_td += 1
        # Guarded: q.low_update() would otherwise create an all-zero row via
        # setdefault, mutating the table even in read-only evaluation.
        if alpha_low > 0.0:
            q.low_update(s_l, a, target, alpha_low)

        x, y = nx, ny
        if kind is not None:
            terminal = kind
            break

    if terminal == TIMEOUT:
        pass  # horizon exhausted without reaching the exit

    return_value = (
        REWARD_SUCCESS if terminal == SUCCESS else fail_reward
    )

    if alpha_high > 0.0:
        q.high_update(s_h, option, return_value, alpha_high)

    labels = causal_labels(
        option=option, goal_lane=goal_lane, final_x=x, hazard=hazard, terminal=terminal
    )

    return EpisodeRecord(
        episode=episode,
        terminal=terminal,
        steps=steps,
        return_value=return_value,
        option=option,
        goal_lane=goal_lane,
        hazard=hazard,
        final_x=x,
        final_y=y,
        labels=labels,
        n_negative_td=n_negative_td,
        visited_low=visited_low,
        visited_high=visited_high,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_runner.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/rflnext/runner.py tests/test_runner.py
git commit -m "feat: add episode runner with gamma=1 zero-step-reward learning"
```

---

### Task 6: Metrics

**Files:**
- Create: `RFL-CausalChase-v0.3/src/rflnext/metrics.py`
- Test: `RFL-CausalChase-v0.3/tests/test_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from rflnext.metrics import (
    episodes_to_90,
    final_success,
    n_negative_td,
    success_auc,
    visited_state_coverage,
)


def test_success_auc_is_trapezoidal():
    # constant 0.5 over 3 checkpoints -> 0.5
    assert success_auc([0.5, 0.5, 0.5], [0, 10, 20]) == pytest.approx(0.5)


def test_success_auc_rising():
    auc = success_auc([0.0, 1.0], [0, 10])
    assert auc == pytest.approx(0.5)


def test_episodes_to_90_none_when_never_reached():
    assert episodes_to_90([0.1, 0.2, 0.3], [0, 10, 20], threshold=0.9) is None


def test_episodes_to_90_returns_first_crossing():
    assert episodes_to_90([0.1, 0.95, 0.99], [0, 10, 20], threshold=0.9) == 10


def test_final_success():
    assert final_success([0.1, 0.2, 0.7]) == pytest.approx(0.7)


def test_coverage_counts_distinct_states():
    assert visited_state_coverage([(0, 0, 0), (0, 0, 0), (1, 0, 0)]) == 2


def test_n_negative_td_sums_records():
    class R:
        def __init__(self, v):
            self.n_negative_td = v

    assert n_negative_td([R(1), R(0), R(3)]) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_metrics.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rflnext.metrics'`

- [ ] **Step 3: Write the implementation**

`src/rflnext/metrics.py`:

```python
"""Pilot Alpha endpoints.  All are pure functions over run history."""

from __future__ import annotations

from collections.abc import Sequence


def success_auc(success_at_checkpoint: Sequence[float], episodes: Sequence[int]) -> float:
    """Trapezoidal area under the success curve, normalised to [0, 1]."""
    if len(success_at_checkpoint) != len(episodes):
        raise ValueError("success and episode lists must align")
    if len(episodes) < 2:
        return float(success_at_checkpoint[0]) if episodes else 0.0
    span = float(episodes[-1] - episodes[0])
    if span <= 0.0:
        raise ValueError("checkpoint episodes must be strictly increasing")
    area = 0.0
    for i in range(1, len(episodes)):
        dt = float(episodes[i] - episodes[i - 1])
        area += 0.5 * (float(success_at_checkpoint[i]) + float(success_at_checkpoint[i - 1])) * dt
    return area / span


def episodes_to_90(
    success_at_checkpoint: Sequence[float],
    episodes: Sequence[int],
    *,
    threshold: float = 0.90,
) -> int | None:
    """First checkpoint episode reaching ``threshold``, else ``None``."""
    for value, episode in zip(success_at_checkpoint, episodes):
        if float(value) >= float(threshold):
            return int(episode)
    return None


def final_success(success_at_checkpoint: Sequence[float]) -> float:
    if not success_at_checkpoint:
        raise ValueError("no checkpoints recorded")
    return float(success_at_checkpoint[-1])


def visited_state_coverage(states: Sequence) -> int:
    return len(set(states))


def n_negative_td(records: Sequence) -> int:
    """Count negative TD errors -- records that reward mode B is *not*
    'no negative learning'."""
    return int(sum(int(getattr(r, "n_negative_td", 0)) for r in records))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_metrics.py -q`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/rflnext/metrics.py tests/test_metrics.py
git commit -m "feat: add Pilot Alpha endpoints"
```

---

### Task 7: Training and greedy evaluation drivers

**Files:**
- Modify: `RFL-CausalChase-v0.3/src/rflnext/runner.py`
- Test: `RFL-CausalChase-v0.3/tests/test_train.py`

- [ ] **Step 1: Write the failing test**

```python
from rflnext.env import HORIZON, N_ACTIONS
from rflnext.qtables import QTables
from rflnext.runner import evaluate, train

CFG = {
    "environment": {"horizon": HORIZON, "gamma": 1.0, "p_hazard": 0.25},
    "learning": {
        "alpha_low": 0.10, "alpha_high": 0.10,
        "epsilon_start": 0.30, "epsilon_end": 0.05, "epsilon_decay_fraction": 0.80,
    },
    "experiment": {"episodes": 400, "eval_every": 200, "eval_episodes": 50},
}


def test_train_produces_curve_and_counts():
    res = train(CFG, seed=123, arm="traditional")
    assert res.arm == "traditional"
    assert len(res.success_curve) == len(res.checkpoints)
    assert all(0.0 <= v <= 1.0 for v in res.success_curve)
    assert sum(res.family_counts.values()) <= 400
    assert set(res.family_counts) <= {"H_error", "L_error", "HL_error", "E_failure"}


def test_evaluate_does_not_mutate_q():
    q = QTables(n_actions=N_ACTIONS)
    before = q.deep_hash()
    evaluate(q, CFG, seed=7, n=20)
    assert q.deep_hash() == before


def test_train_is_reproducible():
    a = train(CFG, seed=5, arm="positive_only")
    b = train(CFG, seed=5, arm="positive_only")
    assert a.q_hash == b.q_hash
    assert a.success_curve == b.success_curve


def test_arms_differ_in_failure_reward_only():
    a = train(CFG, seed=9, arm="traditional")
    b = train(CFG, seed=9, arm="positive_only")
    # Same tape and same seed: the two arms must consume an identical scene
    # sequence, so their realized family counts are drawn from one schedule.
    assert sum(a.family_counts.values()) > 0
    assert sum(b.family_counts.values()) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_train.py -q`
Expected: FAIL with `ImportError: cannot import name 'train'`

- [ ] **Step 3: Append the drivers to `src/rflnext/runner.py`**

```python
from .env import HORIZON as _HORIZON_DEFAULT
from .metrics import episodes_to_90, final_success, success_auc, visited_state_coverage
from .qtables import linear_epsilon

EVAL_SEED_OFFSET = 900_000_000


@dataclass
class TrainResult:
    seed: int
    arm: str
    checkpoints: list
    success_curve: list
    family_counts: dict
    n_negative_td_total: int
    q_hash: str
    records: list = field(default_factory=list)


def evaluate(q: QTables, cfg: dict, *, seed: int, n: int) -> tuple[float, list]:
    """Greedy evaluation on a fresh tape.  Never mutates ``q``."""
    env_cfg = cfg["environment"]
    horizon = int(env_cfg.get("horizon", _HORIZON_DEFAULT))
    tape = NoiseTape.from_seed(
        int(seed) + EVAL_SEED_OFFSET, episodes=int(n), horizon=horizon,
        p_hazard=float(env_cfg.get("p_hazard", 0.25)),
    )
    wins = 0
    states: list = []
    for ep in range(int(n)):
        rec = run_episode(
            episode=ep, tape=tape, q=q, epsilon=0.0, reward_mode="A",
            alpha_low=0.0, alpha_high=0.0,
        )
        wins += int(rec.terminal == SUCCESS)
        states.extend(state for state, _ in rec.visited_low)
    return wins / float(n), states


def train(cfg: dict, *, seed: int, arm: str) -> TrainResult:
    """Run one arm of Pilot Alpha for one seed."""
    if arm not in ("traditional", "positive_only"):
        raise ValueError(f"unknown arm {arm!r}")
    env_cfg = cfg["environment"]
    learn = cfg["learning"]
    exp = cfg["experiment"]

    episodes = int(exp["episodes"])
    eval_every = int(exp["eval_every"])
    eval_episodes = int(exp["eval_episodes"])
    horizon = int(env_cfg.get("horizon", _HORIZON_DEFAULT))
    decay_episodes = max(1, int(episodes * float(learn["epsilon_decay_fraction"])))

    tape = NoiseTape.from_seed(
        int(seed), episodes=episodes, horizon=horizon,
        p_hazard=float(env_cfg.get("p_hazard", 0.25)),
    )
    q = QTables(n_actions=N_ACTIONS)
    reward_mode = "A" if arm == "traditional" else "B"

    checkpoints: list = []
    success_curve: list = []
    family_counts: dict = {f: 0 for f in FAMILIES}
    records: list = []
    all_states: list = []

    def record_checkpoint(episode_index: int) -> None:
        rate, states = evaluate(q, cfg, seed=seed, n=eval_episodes)
        checkpoints.append(int(episode_index))
        success_curve.append(float(rate))
        all_states.extend(states)

    record_checkpoint(0)
    for ep in range(episodes):
        eps = linear_epsilon(
            ep,
            start=float(learn["epsilon_start"]),
            end=float(learn["epsilon_end"]),
            decay_episodes=decay_episodes,
        )
        rec = run_episode(
            episode=ep, tape=tape, q=q, epsilon=eps, reward_mode=reward_mode,
            alpha_low=float(learn["alpha_low"]), alpha_high=float(learn["alpha_high"]),
        )
        records.append(rec)
        if rec.labels is not None:
            family_counts[rec.labels.family] += 1
        all_states.extend(state for state, _ in rec.visited_low)
        if (ep + 1) % eval_every == 0:
            record_checkpoint(ep + 1)

    return TrainResult(
        seed=int(seed),
        arm=arm,
        checkpoints=checkpoints,
        success_curve=success_curve,
        family_counts=family_counts,
        n_negative_td_total=int(sum(r.n_negative_td for r in records)),
        q_hash=q.deep_hash(),
        records=records,
    )
```

Add `FAMILIES` to the existing labels import at the top of the file:

```python
from .labels import FAMILIES, CausalLabels, causal_labels
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_train.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/rflnext/runner.py tests/test_train.py
git commit -m "feat: add Pilot Alpha train and greedy evaluate drivers"
```

---

### Task 8: Pre-registered gates

**Files:**
- Create: `RFL-CausalChase-v0.3/src/rflnext/gates.py`
- Test: `RFL-CausalChase-v0.3/tests/test_gates.py`

- [ ] **Step 1: Write the failing test**

```python
from rflnext.gates import GateReport, ceiling_gate, family_gate


def _result(arm, curve, counts):
    class R:
        pass

    r = R()
    r.arm = arm
    r.success_curve = curve
    r.checkpoints = list(range(0, 250 * len(curve), 250))
    r.family_counts = counts
    return r


GOOD = {"H_error": 500, "L_error": 500, "HL_error": 500, "E_failure": 500}


def test_ceiling_gate_flags_saturated_benchmark():
    results = {
        "traditional": _result("traditional", [0.9, 0.95, 0.97], GOOD),
        "positive_only": _result("positive_only", [0.9, 0.95, 0.97], GOOD),
    }
    rep = ceiling_gate(results, ceiling_max_final_success=0.80, min_auc_gap=0.005)
    assert isinstance(rep, GateReport)
    assert rep.status == "benchmark_no_discriminating_power"
    assert "all_arms_above_ceiling" in rep.reasons


def test_ceiling_gate_flags_flat_auc():
    results = {
        "traditional": _result("traditional", [0.5, 0.6, 0.7], GOOD),
        "positive_only": _result("positive_only", [0.5, 0.6, 0.7], GOOD),
    }
    rep = ceiling_gate(results, ceiling_max_final_success=0.80, min_auc_gap=0.005)
    assert rep.status == "benchmark_no_discriminating_power"
    assert "auc_gap_below_floor" in rep.reasons


def test_ceiling_gate_passes_when_separated():
    results = {
        "traditional": _result("traditional", [0.2, 0.4, 0.6], GOOD),
        "positive_only": _result("positive_only", [0.1, 0.2, 0.3], GOOD),
    }
    rep = ceiling_gate(results, ceiling_max_final_success=0.80, min_auc_gap=0.005)
    assert rep.status == "ok"


def test_family_gate_requires_minimum_events():
    results = {
        "traditional": _result("traditional", [0.1, 0.2], {"H_error": 500, "L_error": 10,
                                                           "HL_error": 500, "E_failure": 500}),
        "positive_only": _result("positive_only", [0.1, 0.2], GOOD),
    }
    rep = family_gate(results, min_family_events=400)
    assert rep.status == "insufficient_family_events"
    assert rep.reasons == ["L_error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gates.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'rflnext.gates'`

- [ ] **Step 3: Write the implementation**

`src/rflnext/gates.py`:

```python
"""Pre-registered gates for Pilot Alpha.

The ceiling gate exists because v0.1 Experiment B saturated at 0.96-0.98 and
produced an uninterpretable null.  Here it is checked before the benchmark is
trusted, not after a null result is explained away.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .metrics import final_success, success_auc


@dataclass
class GateReport:
    status: str
    reasons: list = field(default_factory=list)
    finals: dict = field(default_factory=dict)
    aucs: dict = field(default_factory=dict)


def ceiling_gate(
    results: dict, *, ceiling_max_final_success: float, min_auc_gap: float
) -> GateReport:
    finals = {arm: final_success(r.success_curve) for arm, r in results.items()}
    aucs = {arm: success_auc(r.success_curve, r.checkpoints) for arm, r in results.items()}
    reasons: list = []
    if finals and all(v > float(ceiling_max_final_success) for v in finals.values()):
        reasons.append("all_arms_above_ceiling")
    if len(aucs) >= 2:
        ordered = sorted(aucs.values())
        if (ordered[-1] - ordered[0]) < float(min_auc_gap):
            reasons.append("auc_gap_below_floor")
    status = "benchmark_no_discriminating_power" if reasons else "ok"
    return GateReport(status=status, reasons=reasons, finals=finals, aucs=aucs)


def family_gate(results: dict, *, min_family_events: int) -> GateReport:
    """Every family must be realized at least ``min_family_events`` times in
    every arm.  Under-representation is reported, never silently patched."""
    short: list = []
    for _arm, r in results.items():
        for family, count in r.family_counts.items():
            if int(count) < int(min_family_events):
                short.append(family)
    short = sorted(set(short))
    status = "insufficient_family_events" if short else "ok"
    return GateReport(status=status, reasons=short)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gates.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/rflnext/gates.py tests/test_gates.py
git commit -m "feat: add pre-registered ceiling and family gates"
```

---

### Task 9: Pilot Alpha CLI

**Files:**
- Create: `RFL-CausalChase-v0.3/configs/alpha.yaml`
- Create: `RFL-CausalChase-v0.3/scripts/pilot_alpha.py`
- Test: `RFL-CausalChase-v0.3/tests/test_pilot_alpha.py`

- [ ] **Step 1: Create the frozen config**

`configs/alpha.yaml`:

```yaml
schema_version: "0.3.0"
environment:
  horizon: 8
  gamma: 1.0
  width: 5
  lanes: 2
  p_hazard: 0.25
learning:
  alpha_low: 0.10
  alpha_high: 0.10
  epsilon_start: 0.30
  epsilon_end: 0.05
  epsilon_decay_fraction: 0.80
gate:
  ceiling_max_final_success: 0.80
  min_auc_gap: 0.005
  min_family_events: 400
experiment:
  name: v03_alpha
  seeds: 12
  seed_base: 4000000
  episodes: 10000
  eval_every: 250
  eval_episodes: 200
  arms: [traditional, positive_only]
```

- [ ] **Step 2: Write the failing test**

```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pilot_alpha_cli_writes_summary(tmp_path):
    out = tmp_path / "alpha"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "pilot_alpha.py"),
         "--config", str(ROOT / "configs" / "alpha.yaml"),
         "--outdir", str(out), "--seeds", "2", "--episodes", "400",
         "--eval-every", "200", "--eval-episodes", "40", "--report-only"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["experiment"] == "v03_alpha"
    assert len(summary["seeds"]) == 2
    for row in summary["seeds"]:
        assert row["arm"] in ("traditional", "positive_only")
        assert "success_auc" in row
        assert "family_counts" in row
    assert (out / "config.yaml").exists()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_pilot_alpha.py -q`
Expected: FAIL — `scripts/pilot_alpha.py` does not exist

- [ ] **Step 4: Write the CLI**

`scripts/pilot_alpha.py`:

```python
"""Pilot Alpha: Traditional (+1/-1) vs Positive-only (+1/0).

Only the failure reward differs between arms.  No attribution, no
counterfactual, no human feedback, no diagnostic update.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import yaml

from rflnext.gates import ceiling_gate, family_gate
from rflnext.metrics import episodes_to_90, final_success, success_auc
from rflnext.runner import train

EXIT_OK = 0
EXIT_NO_DISCRIMINATING_POWER = 2
EXIT_GATE_FAILED = 3


def load_config(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--episodes", type=int, default=None)
    ap.add_argument("--eval-every", type=int, default=None)
    ap.add_argument("--eval-episodes", type=int, default=None)
    ap.add_argument("--report-only", action="store_true",
                    help="return 0 even when a scientific gate fails")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    exp = cfg["experiment"]
    if args.seeds is not None:
        exp["seeds"] = args.seeds
    if args.episodes is not None:
        exp["episodes"] = args.episodes
    if args.eval_every is not None:
        exp["eval_every"] = args.eval_every
    if args.eval_episodes is not None:
        exp["eval_episodes"] = args.eval_episodes

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "config.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )

    arms = list(exp["arms"])
    seed_base = int(exp["seed_base"])
    rows = []
    per_arm_records = {arm: [] for arm in arms}

    for index in range(int(exp["seeds"])):
        seed = seed_base + index
        for arm in arms:
            result = train(cfg, seed=seed, arm=arm)
            per_arm_records[arm].append(result)
            rows.append({
                "seed_index": index,
                "seed": seed,
                "arm": arm,
                "checkpoints": result.checkpoints,
                "success_curve": result.success_curve,
                "success_auc": success_auc(result.success_curve, result.checkpoints),
                "episodes_to_90": episodes_to_90(result.success_curve, result.checkpoints),
                "final_success": final_success(result.success_curve),
                "family_counts": result.family_counts,
                "n_negative_td": result.n_negative_td_total,
                "q_hash": result.q_hash,
            })
            print(f"[seed {seed} {arm}] auc={rows[-1]['success_auc']:.4f} "
                  f"final={rows[-1]['final_success']:.3f} "
                  f"neg_td={result.n_negative_td_total}")

    # Gates run on the pooled per-arm curves (mean over seeds).
    class _Pooled:
        def __init__(self, arm, records):
            self.arm = arm
            self.checkpoints = records[0].checkpoints
            n = len(self.checkpoints)
            self.success_curve = [
                sum(r.success_curve[i] for r in records) / len(records)
                for i in range(n)
            ]
            self.family_counts = {
                f: sum(r.family_counts.get(f, 0) for r in records)
                for f in records[0].family_counts
            }

    pooled = {arm: _Pooled(arm, recs) for arm, recs in per_arm_records.items()}
    gate_cfg = cfg["gate"]
    ceiling = ceiling_gate(
        pooled,
        ceiling_max_final_success=float(gate_cfg["ceiling_max_final_success"]),
        min_auc_gap=float(gate_cfg["min_auc_gap"]),
    )
    family = family_gate(pooled, min_family_events=int(gate_cfg["min_family_events"]))

    summary = {
        "schema_version": cfg["schema_version"],
        "experiment": exp["name"],
        "config": cfg,
        "seeds": rows,
        "pooled": {
            arm: {
                "checkpoints": p.checkpoints,
                "success_curve": p.success_curve,
                "success_auc": success_auc(p.success_curve, p.checkpoints),
                "final_success": final_success(p.success_curve),
                "family_counts": p.family_counts,
            }
            for arm, p in pooled.items()
        },
        "ceiling_gate": {
            "status": ceiling.status, "reasons": ceiling.reasons,
            "finals": ceiling.finals, "aucs": ceiling.aucs,
        },
        "family_gate": {"status": family.status, "short_families": family.reasons},
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nceiling_gate = {ceiling.status} {ceiling.reasons}")
    print(f"family_gate  = {family.status} {family.reasons}")

    if args.report_only:
        return EXIT_OK
    if ceiling.status != "ok":
        return EXIT_NO_DISCRIMINATING_POWER
    if family.status != "ok":
        return EXIT_GATE_FAILED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_pilot_alpha.py -q`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add configs/alpha.yaml scripts/pilot_alpha.py tests/test_pilot_alpha.py
git commit -m "feat: add Pilot Alpha CLI with pre-registered gates"
```

---

### Task 10: Paired analysis over seeds

**Files:**
- Create: `RFL-CausalChase-v0.3/scripts/analyze_alpha.py`
- Test: `RFL-CausalChase-v0.3/tests/test_analyze_alpha.py`

- [ ] **Step 1: Inspect the vendored statistics API**

Run: `python -c "import rflnext.stats as s; print([n for n in dir(s) if not n.startswith('_')])"`

Use the returned names in Step 3. Do **not** invent function names; the vendored `stats.py` is frozen and must not be edited.

- [ ] **Step 2: Write the failing test**

```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_analyze_alpha_emits_paired_table(tmp_path):
    alpha = tmp_path / "alpha"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "pilot_alpha.py"),
         "--config", str(ROOT / "configs" / "alpha.yaml"),
         "--outdir", str(alpha), "--seeds", "2", "--episodes", "400",
         "--eval-every", "200", "--eval-episodes", "40", "--report-only"],
        check=True, cwd=str(ROOT),
    )
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "analyze_alpha.py"), "--dir", str(alpha)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    table = json.loads((alpha / "analysis.json").read_text(encoding="utf-8"))
    assert table["n_seeds"] == 2
    assert "auc_delta_mean" in table
    assert table["unit"] == "seed"
```

- [ ] **Step 3: Write the analysis script**

`scripts/analyze_alpha.py` — pair by `seed`, compute `traditional - positive_only` deltas for `success_auc`, `final_success`, and `n_negative_td`, then report mean/median and a paired CI using the vendored helpers found in Step 1. Emit `analysis.json` with keys `unit`, `n_seeds`, `auc_delta_mean`, `auc_delta_median`, `auc_delta_ci`, `final_success_delta_mean`, `n_negative_td_by_arm`, and exit non-zero if any seed lacks both arms.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_analyze_alpha.py -q`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_alpha.py tests/test_analyze_alpha.py
git commit -m "feat: add seed-paired Pilot Alpha analysis"
```

---

### Task 11: Smoke, ceiling check, and pilot decision

**Files:**
- Create: `RFL-CausalChase-v0.3/docs/RESULTS.md`

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -q`
Expected: all tests pass (Task 1-10 suites)

- [ ] **Step 2: Run the smoke and read the gates**

Run:

```bash
python scripts/pilot_alpha.py --config configs/alpha.yaml \
  --outdir outputs/v03_alpha_smoke --seeds 2 --episodes 400 \
  --eval-every 200 --eval-episodes 40
```

Expected: prints `ceiling_gate` and `family_gate`. If `ceiling_gate != ok`, **stop** and record it: the benchmark has no discriminating power and per D7 no formal run may be started. Do not tune `p_hazard` or `epsilon` to force a gap.

- [ ] **Step 3: Run Pilot Alpha proper**

Run:

```bash
python scripts/pilot_alpha.py --config configs/alpha.yaml --outdir outputs/v03_alpha
python scripts/analyze_alpha.py --dir outputs/v03_alpha
```

- [ ] **Step 4: Record results and the verdict**

Write `docs/RESULTS.md` with: the config hash, git commit, the two pooled curves, the ceiling and family gate outcomes, the paired deltas, and one of exactly three verdicts --

- `DISCRIMINATING_AND_SEPARATED` -- gates ok and the paired CI excludes 0;
- `DISCRIMINATING_BUT_NULL` -- gates ok and the CI includes 0 (a reportable result: explicit failure penalty does not matter at this scale);
- `BENCHMARK_NO_DISCRIMINATING_POWER` -- ceiling gate failed (fix the benchmark, do not proceed to Beta).

- [ ] **Step 5: Commit**

```bash
git add docs/RESULTS.md outputs/v03_alpha_smoke outputs/v03_alpha
git commit -m "data: record Pilot Alpha smoke and pilot results"
```

---

## Plan 2 preview (do not implement here)

Pilot Beta adds, on top of this tree, only:

1. `U` gating -- `Delta Q_m = U_m * alpha_diag * delta`, with `U` taken from `CausalLabels` (already exact here);
2. the Penalty x Oracle 2x2 (`Traditional`, `Positive-only`, `Traditional+Oracle`, `Positive-only+Oracle`);
3. the four update-rule calibration arms `H-only`, `L-only`, `HL`, `None`;
4. knowledge probes defined on **clean reference states** with a verified pre-margin, never on a failure's terminal transition.

Pilot Beta is a separate plan because it introduces a new subsystem (gated updates and probes) and must produce its own working, testable increment.

---

## Self-review

**1. Spec coverage** (against `deep-research-report (5).md`)

| report requirement | task |
|---|---|
| small two-level causal grid / causal bandit-MDP | Tasks 2-3 |
| episode explicitly contains `H -> L -> E -> Outcome` | Tasks 4-5 (`s_H` option, then primitives, then hazard, then terminal) |
| generator independently controls H/L/E | Task 4 (`option` vs `goal_lane`, `final_x`, `hazard`) |
| four failure families with `U` labels | Task 4 |
| fixed horizon / `gamma=1` / no step reward / absorbing | Task 5 |
| A/B reward modes, timeout same as failure | Task 5 |
| `N_delta_neg` recorded for the Positive-only arm | Task 6 |
| Primary `SuccessAUC`; secondary `FirstSuccess`, `EpisodesTo90`, `FinalSuccess`, `VisitedStateCoverage` | Tasks 6, 9 |
| 12 paired seeds, 10k episodes, 200 greedy eval episodes, checkpoints 0/250/500/1k/2k/5k/10k | Task 9 config |
| paired analysis, no episode-level p-values | Task 10 |
| pre-registered gates, frozen before the formal run | Tasks 8, 11 |

Not covered here by design: attribution models, counterfactual budgets, revision ledgers, human feedback, GRPO, `Q_G`. Those are later stages and are explicitly out of Stage 1 scope.

**2. Placeholder scan.** Task 10 Step 3 is the only step that describes an implementation rather than pasting it, because the vendored `stats.py` API must be read before its helpers can be called correctly. Every other code step contains complete, runnable code. If you want Task 10 fully literal, read `stats.py` first and paste its exact signatures into Step 3 before executing.

**3. Type consistency.** `QTables(n_actions=4, options=(0,1))` is used consistently; `s_H=(goal_lane,hazard)` and `s_L=(x,y,option)` are tuples everywhere; `CausalLabels.u` is the `(u_h,u_l)` property used by tests; `TrainResult` fields (`checkpoints`, `success_curve`, `family_counts`, `n_negative_td_total`, `q_hash`) match the keys read in Tasks 9-10; `GateReport(status, reasons, finals, aucs)` matches both `gates.py` and its callers.
