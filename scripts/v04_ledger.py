"""v0.4 candidate ledger and step traces.

The two artifacts ``docs/V0_4_RESULTS.md`` lists as **not done**:

    outputs/v04_ledger/candidate_ledger.jsonl    per failed episode: the
                                                 admissible candidate repairs,
                                                 their ``V_true``, the selection
                                                 outcome and its regret
    outputs/v04_ledger/step_traces.jsonl         per sampled failed episode: the
                                                 full per-timestep trace

Usage
-----
    python scripts/v04_ledger.py --config configs/v04_beta.yaml \
        --outdir outputs/v04_ledger --seeds 8 --episodes 2000
    python scripts/v04_ledger.py --config configs/v04_beta.yaml \
        --outdir outputs/v04_ledger --report-only

``--report-only`` recomputes the report from the ``*.jsonl`` already on disk and
does **not** re-run training.

Why this script re-implements the training loop
-----------------------------------------------
``rflv04.train.train`` keeps no per-episode record -- the oracle result is used
and discarded and the failed trace never leaves the function -- so a ledger
needs the same loop with a capture hook.  ``src/rflv04/`` is frozen, so the
loop is replicated here and then **verified against ``train()`` for every seed**
(``--verify-train``, on by default): Q-table hash, family counts, correction
count, sites touched, clippings, negative-TD count, checkpoints and the whole
success curve must match exactly.  That can only happen if the RNG consumption
and the arm-specific update path are identical, which is the property the ledger
depends on.

Two capture points, both matching the semantics of the run being described:

* the Q view used by ``step_traces.jsonl`` is snapshotted **after the agent's
  rollout and before ``_task_update``** -- i.e. the values the agent actually
  acted on;
* the ledger row is built **after** the oracle call and **before** the arm's
  corrective write -- i.e. the candidates that were on the table for that
  failure.

Fidelity: the oracle is called with ``n_samples=8``, exactly as ``train.py``
does, so the ledger describes the candidate ranking the mechanism really used.
``--v-samples`` can change it, but any value other than 8 breaks exact
``train()`` equivalence in the (rare) multi-candidate episodes and is reported
as such instead of being hidden.

Determinism: no wall-clock, no ids, no set iteration order reaches the jsonl;
seeds are ``cfg.experiment.seed_base + i`` exactly as in the other v0.4 pilots.
**The run also pins PYTHONHASHSEED=0 by re-executing itself**, because
``rflv04.train.train`` is *not* reproducible across processes as it stands:

    credit_units.decision_oracle iterates ``best.primitives`` -- a frozenset of
    (str, int) tuples -- so the site list order varies with the process hash
    seed.  A WholeProcess repair {unstick:t, exec:t} then emits
    ('DECISION', q_key, a) and ('EXECUTION', q_key, a): two "different" sites
    that updates.py routes to the *same* Q_L entry (every non-PLAN unit reads
    and writes ``q.low``).  alternative_sites() returns a site with the same
    (unit, state, action) key as the DECISION one, so ``merged`` overwrites its
    target 1.0, while the EXECUTION twin keeps -1.0.  Two relative writes on one
    entry in varying order => the written value flips sign.

Measured: the same seed/arm in three processes gave three different q_hashes
(310c8d4e..., d579c62f..., 1ed7b88a...) and 881/881/886 corrections, while
three processes with PYTHONHASHSEED=0 were byte-identical.  ``--no-pin-hash-seed``
keeps the upstream behaviour and accepts that the jsonl is then not
byte-reproducible.  ``src/`` is deliberately left untouched; this is reported,
not silently patched.

Beyond the required fields the summary carries four measured diagnostics that
decide how the ledger should be read at all: the candidate-set size histogram,
the V_true landscape, the family structure of the *reconstructed* scene, and
the execution-fault collision (``decision_fault_at == execution_fault_at``)
that makes a size-1 ``exec`` repair insufficient.  Nothing there is asserted
without a number next to it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import yaml

from rflnext.qtables import QTables, linear_epsilon

from rflv04.credit_units import (
    REPRESENTATIONS,
    alternative_sites,
    decision_oracle,
    responsible_units,
    selected_repair,
)
from rflv04.env import (
    ACT,
    ACT_ACTIONS,
    ACTION_NAMES,
    HORIZON,
    PHASE_NAMES,
    PLAN,
    PLAN_ACTIONS,
    WAIT,
    X_MAX,
    Scene,
    reference_action,
)
from rflv04.knowledge import build_knowledge_set, kd_innocent, wmd
from rflv04.oracle import (
    oracle_repair_set,
    repair_regret,
    repair_value,
    scene_from_trace,
)
from rflv04.train import (
    ARMS,
    BETA_TARGET_MODE,
    TARGET_ARMS,
    _task_update,
    agent_rollout,
    evaluate,
    train,
)
from rflv04.updates import MODES

EXIT_OK = 0
EXIT_GATE_FAILED = 2          # the pre-registered equivalence claim was refuted
EXIT_REPLICA_MISMATCH = 3     # the loop replica does not match train()
EXIT_BAD_OUTDIR = 4           # refusing to write into a foreign outputs dir

RUN_ORACLE_SAMPLES = 8   # train.py's own fidelity; do not change silently
HASH_SEED_PIN = "0"
_PIN_MARKER = "V04_LEDGER_HASHSEED_PINNED"


def reexec_with_pinned_hash_seed(argv):
    """Re-run this script with PYTHONHASHSEED fixed, returning the exit code.

    train() is not cross-process reproducible without this (see the module
    docstring).  ``None`` means "already pinned, carry on in this process".
    """
    if os.environ.get(_PIN_MARKER) == "1" or os.environ.get("PYTHONHASHSEED") == HASH_SEED_PIN:
        return None
    env = dict(os.environ, PYTHONHASHSEED=HASH_SEED_PIN, **{_PIN_MARKER: "1"})
    print(f"[ledger] PYTHONHASHSEED={HASH_SEED_PIN} pinned by re-exec: "
          f"rflv04.train is hash-seed dependent (see module docstring)", flush=True)
    return subprocess.run([sys.executable, os.path.abspath(__file__), *argv],
                          env=env).returncode

FIELD_NOTES = {
    "candidates[].repair": "sorted primitive strings, e.g. 'unstick:2', 'plan:1', "
                           "'exec:2'; 'step:t:a' if a forced-step primitive ever appears",
    "candidates[].V_true": "oracle.repair_value(scene, repair, n_samples=v_samples), "
                           "evaluator-only",
    "candidates[].selected": "was this the candidate selected_repair() picked "
                             "(pick='best', train.py's rule)",
    "candidates[].regret_vs_best": "V_true - max(V_true over this episode's candidates)",
    "candidates[].minimal": "repair.size == oracle minimal_size. NOTE: "
                            "enumerate_sufficient() stops at the first size that "
                            "yields any sufficient intervention, so every returned "
                            "candidate has that size and 'minimal' is True for all "
                            "of them by construction -- the run reports the count "
                            "of False values so this is measured, not assumed.",
    "regret_of_selected": "oracle.repair_regret(scene, selected, n_samples=v_samples); "
                          "null when the candidate set is empty",
    "scene": "the reconstructed scene scene_from_trace(trace) that the oracle "
             "classified: what the agent actually chose (g = context lane, plan, "
             "plan_matches_context) plus the faults the reconstruction carries",
    "steps[].action": "realized action index (what the environment executed)",
    "steps[].agent_action": "intent -- the action the agent itself chose",
    "steps[].is_deviation": "agent_action != reference_action (ACT steps only; false "
                            "on the PLAN step, null where no action exists)",
    "steps[].q_values_selected_unit": "the Q row read at that timestep, i.e. the row "
                                      "the credit unit's site indexes: {action_name: "
                                      "value}; the HIGH row at (g,0,0) on the PLAN "
                                      "step, the LOW row at (x,y,o,t) on ACT steps, "
                                      "null on ABSORB.  q_unit/q_key identify it.",
    "steps[].chosen_value": "the value of agent_action inside that row (the value "
                            "epsilon-greedy compared against)",
    "steps[].plan_chosen": "t=0 only: the plan the agent emitted (step 'o' is -1 in "
                           "PLAN phase, so this is the readable form)",
    "first_deviation_t": "first ACT step where agent_action != reference_action",
    "first_realized_deviation_t": "first ACT step where the *realized* action != "
                                  "reference_action -- the oracle's own critical_t, "
                                  "which differs from first_deviation_t under an "
                                  "execution fault",
    "terminal_step": "t at which the outcome was decided (goal reached, or horizon)",
    "absorbing": "the trace entered the ABSORB phase before the horizon, i.e. the "
                 "outcome was decided early; always false for horizon-timeouts",
}


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _prim_str(prim) -> str:
    if len(prim) == 3 and prim[0] == "step":
        return f"step:{prim[1]}:{prim[2]}"
    return f"{prim[0]}:{prim[1]}"


def _repair_strs(repair) -> list:
    return sorted(_prim_str(p) for p in repair.primitives)


def _repair_key(repair) -> frozenset:
    return frozenset(repair.primitives)


def _histogram(values: Counter) -> dict:
    return {str(k): int(v) for k, v in sorted(values.items())}


def _mean(xs) -> float | None:
    return float(np.mean(xs)) if xs else None


def _median(xs) -> float | None:
    return float(np.median(xs)) if xs else None


# --------------------------------------------------------------------------
# step traces
# --------------------------------------------------------------------------


def snapshot_q(q, trace) -> dict:
    """The Q rows the agent read during this rollout.

    Taken *before* the task update, so it is what the policy acted on.
    """
    high = {}
    low = {}
    for step in trace.steps:
        if step.state[4] == PLAN:
            key = (step.state[0], step.state[1], step.state[2])
            high[key] = [float(q.high_get(key, o)) for o in q.options]
        elif step.state[4] == ACT:
            key = (step.state[1], step.state[2], step.state[3], step.t)
            low[key] = [float(q.low_get(key, a)) for a in ACT_ACTIONS]
    return {"high": high, "low": low}


def _terminal_step(trace) -> int:
    g = trace.scene.g
    for step in trace.steps:
        if step.state[4] == ACT and step.next_state[1] == X_MAX \
                and step.next_state[2] == g:
            return int(step.t)
    return int(trace.scene.horizon)


def build_steps(trace, qview) -> list:
    out = []
    for step in trace.steps:
        phase = int(step.state[4])
        row = {
            "t": int(step.t),
            "x": int(step.state[1]),
            "y": int(step.state[2]),
            "o": int(step.state[3]),
            "phase": PHASE_NAMES[phase],
            "action": None,
            "agent_action": None,
            "reference_action": None,
            "q_values_selected_unit": None,
            "chosen_value": None,
            "is_deviation": None,
            "q_unit": None,
            "q_key": None,
            "plan_chosen": None,
        }
        if phase == PLAN:
            chosen = int(step.next_state[3])
            key = (step.state[0], step.state[1], step.state[2])
            vals = qview["high"].get(key, [])
            vmap = {o: vals[i] for i, o in enumerate(PLAN_ACTIONS) if i < len(vals)}
            row["action"] = int(step.realized)
            row["agent_action"] = int(step.intent)
            row["plan_chosen"] = chosen
            row["q_unit"] = "HIGH"
            row["q_key"] = list(key)
            row["q_values_selected_unit"] = {ACTION_NAMES[o]: v for o, v in vmap.items()}
            row["chosen_value"] = vmap.get(chosen)
            row["is_deviation"] = False
        elif phase == ACT:
            key = (step.state[1], step.state[2], step.state[3], step.t)
            ref = int(reference_action(*key[:3]))
            vals = qview["low"].get(key, [])
            vmap = {a: vals[i] for i, a in enumerate(ACT_ACTIONS) if i < len(vals)}
            row["action"] = int(step.realized)
            row["agent_action"] = int(step.intent)
            row["reference_action"] = ref
            row["q_unit"] = "LOW"
            row["q_key"] = list(key)
            row["q_values_selected_unit"] = {ACTION_NAMES[a]: v for a, v in vmap.items()}
            row["chosen_value"] = vmap.get(int(step.intent))
            row["is_deviation"] = bool(step.intent != ref)
        out.append(row)
    return out


def build_step_trace(seed, episode, trace, qview, res, selected) -> dict:
    steps = build_steps(trace, qview)
    dev = [s["t"] for s in steps if s["is_deviation"]]
    real_dev = [s["t"] for s in steps
                if s["phase"] == "ACT" and s["reference_action"] is not None
                and s["action"] != s["reference_action"]]
    return {
        "seed": int(seed),
        "episode": int(episode),
        "family": res.family,
        "outcome": trace.terminal,
        "g": int(trace.scene.g),
        "plan_chosen": int(trace.steps[0].next_state[3]),
        "selected_repair": _repair_strs(selected) if selected is not None else None,
        "n_candidates": len(res.sufficient),
        "minimal_size": res.minimal_size,
        "steps": steps,
        "first_deviation_t": int(dev[0]) if dev else None,
        "first_realized_deviation_t": int(real_dev[0]) if real_dev else None,
        "terminal_step": _terminal_step(trace),
        "absorbing": any(s["phase"] == "ABSORB" for s in steps),
    }


# --------------------------------------------------------------------------
# candidate ledger row
# --------------------------------------------------------------------------


def build_ledger_row(seed, episode, arm, episodes, trace, scene, res, *,
                     v_samples) -> dict:
    """One failed episode's candidate set, its V_true ranking and selection."""
    selected = selected_repair(trace, res)                       # train.py's rule
    selected_first = selected_repair(trace, res, pick="first")   # secondary rule
    sel_key = _repair_key(selected) if selected is not None else None
    first_key = _repair_key(selected_first) if selected_first is not None else None

    values: dict = {}
    minimal_flags: dict = {}
    for rep in res.sufficient:
        key = _repair_key(rep)
        values[key] = float(repair_value(scene, rep, n_samples=v_samples))
        minimal_flags[key] = bool(res.minimal_size is not None
                                  and rep.size == res.minimal_size)
    best_value = max(values.values()) if values else None

    candidates = []
    for rep in res.sufficient:
        key = _repair_key(rep)
        candidates.append({
            "repair": _repair_strs(rep),
            "V_true": values[key],
            "selected": bool(sel_key is not None and key == sel_key),
            "regret_vs_best": float(values[key] - best_value) if best_value is not None else None,
            "minimal": minimal_flags[key],
        })
    candidates.sort(key=lambda c: (c["repair"],))

    regret = repair_regret(scene, selected, n_samples=v_samples)
    # independent cross-check of the API path against the local candidate table
    local = None
    if best_value is not None and sel_key is not None:
        local = float(best_value - values[sel_key])
    regret_agrees = bool(
        (regret is None and local is None)
        or (regret is not None and local is not None and abs(regret - local) < 1e-12))
    first_regret = None
    if best_value is not None and first_key is not None:
        first_regret = float(best_value - values[first_key])

    return {
        "seed": int(seed),
        "episode": int(episode),
        "arm": arm,
        "episodes": int(episodes),
        "v_samples": int(v_samples),
        "family": res.family,
        "scene": {
            "g": int(scene.g),
            "plan": int(scene.plan),
            "plan_matches_context": bool(scene.plan == scene.g),
            "decision_fault_at": scene.decision_fault_at,
            "decision_fault_action": int(scene.decision_fault_action),
            "execution_fault_at": scene.execution_fault_at,
            "execution_fault_action": int(scene.execution_fault_action),
            "horizon": int(scene.horizon),
        },
        "candidates": candidates,
        "n_candidates": len(candidates),
        "minimal_size": res.minimal_size,
        "n_enumerated": int(res.n_enumerated),
        "selected_repair": _repair_strs(selected) if selected is not None else None,
        "selected_rule": "selected_repair(pick='best')",
        "regret_of_selected": regret,
        "selected_repair_first": (_repair_strs(selected_first)
                                  if selected_first is not None else None),
        "regret_of_selected_first": first_regret,
        "selection_rules_disagree": bool(sel_key != first_key),
        "regret_api_agrees": regret_agrees,
    }


# --------------------------------------------------------------------------
# the training replica
# --------------------------------------------------------------------------


def run_seed(cfg, *, seed, arm, v_samples, on_row, on_trace) -> dict:
    """``train()``'s loop, with the ledger capture hooks.

    Faithful to ``rflv04.train.train``; ``--verify-train`` checks that.
    """
    env_cfg = cfg.get("environment", {})
    learn = cfg.get("learning", {})
    exp = cfg.get("experiment", {})
    horizon = int(env_cfg.get("horizon", HORIZON))
    alpha_low = float(learn.get("alpha_low", 0.10))
    alpha_high = float(learn.get("alpha_high", 0.10))
    alpha_diag = float(learn.get("alpha_diag", 0.10))
    reward_mode = str(exp.get("reward_mode", "A"))
    warmup = int(exp.get("warmup_episodes", 300))
    episodes = int(exp.get("episodes", 2000))
    eval_every = int(exp.get("eval_every", 250))
    eval_episodes = int(exp.get("eval_episodes", 100))
    decay = max(1, int((warmup + episodes) * float(learn.get("epsilon_decay_fraction", 0.8))))

    rng = np.random.default_rng((int(seed) + 4_100_000) % (2**32 - 1))
    q = QTables(n_actions=6, options=(0, 1))
    counts: dict = {}
    neg_td = 0

    for ep in range(warmup):
        g = ep % 2
        scene = Scene(f"W{ep}", g, g, horizon=horizon)
        trace = agent_rollout(q, scene, epsilon=linear_epsilon(
            ep, start=0.30, end=0.05, decay_episodes=decay), rng=rng)
        neg_td += _task_update(q, trace, alpha_low=alpha_low,
                               alpha_high=alpha_high, reward_mode=reward_mode)

    checkpoint = q.copy()
    ks = build_knowledge_set(q, theta=float(exp.get("knowledge_theta", 0.60)),
                             horizon=horizon)

    corrupt_delta = float(exp.get("corrupt_delta", 1.0))
    n_corrupt = int(exp.get("corrupt_states", 0))
    if arm != "NoCorruption" and n_corrupt > 0:
        pool = [k for k in ks.items if k.unit == "DECISION"]
        for item in pool[:n_corrupt]:
            row = q.low.get(item.state)
            if row is None:
                continue
            row[WAIT] = row[item.correct] + corrupt_delta

    checkpoints, curve = [], []
    wmd_sum = kd_sum = 0.0
    corrections = sites_touched = clippings = collateral = 0
    n_fail = 0

    def record(ep: int) -> None:
        checkpoints.append(int(ep))
        curve.append(float(evaluate(q, cfg, seed=seed, n=eval_episodes)))

    record(0)
    for ep in range(episodes):
        exec_fault = (ep % 4 == 3)
        g = int(rng.integers(0, 2)) if exec_fault else (ep % 2)
        if exec_fault:
            ft = int(rng.integers(1, horizon))
            scene = Scene(f"S{ep}", g, g, execution_fault_at=ft, horizon=horizon)
        else:
            scene = Scene(f"S{ep}", g, g, horizon=horizon)

        eps = linear_epsilon(warmup + ep, start=0.30, end=0.05, decay_episodes=decay)
        trace = agent_rollout(q, scene, epsilon=eps, rng=rng)
        # --- capture: the Q rows the agent acted on (pre task-update) --------
        qview = None if trace.success else snapshot_q(q, trace)

        neg_td += _task_update(q, trace, alpha_low=alpha_low,
                               alpha_high=alpha_high, reward_mode=reward_mode)

        if trace.success:
            counts["clean"] = counts.get("clean", 0) + 1
            if (ep + 1) % eval_every == 0:
                record(ep + 1)
            continue

        n_fail += 1
        oracle_scene = scene_from_trace(trace)
        res = oracle_repair_set(oracle_scene, n_samples=v_samples)

        # --- capture: the candidates on the table for this failure ----------
        row = build_ledger_row(seed, ep, arm, episodes, trace, oracle_scene, res,
                               v_samples=v_samples)
        on_row(row)
        if qview is not None:
            on_trace(build_step_trace(seed, ep, trace, qview, res,
                                      selected_repair(trace, res)))

        counts[res.family] = counts.get(res.family, 0) + 1
        if arm in ("NoCorrection", "NoCorruption") or not res.sufficient:
            if (ep + 1) % eval_every == 0:
                record(ep + 1)
            continue

        sel = selected_repair(trace, res)
        if arm in TARGET_ARMS:
            credit = decision_oracle(trace, res)
            alts = alternative_sites(trace, res)
        elif arm == "RepairOracle":
            credit = REPRESENTATIONS[arm](trace, res, sel)
            alts = []
        else:
            credit = REPRESENTATIONS[arm](trace, res)
            alts = []

        before = q.copy()
        fail_v = -1.0 if reward_mode == "A" else 0.0
        targets = {site.key: fail_v for site in credit.sites}
        alt_targets = {site.key: 1.0 for site in alts}
        if arm == "CFRevalue":
            from rflv04.env import rollout_intervened
            cf_return = rollout_intervened(
                trace.scene, sel.primitives if sel is not None else frozenset(),
            ).return_value
            targets = {site.key: cf_return for site in credit.sites}
            alt_targets = {site.key: cf_return for site in alts}

        if arm == "CFRevalue":
            rec = MODES["negative_only"](q, credit.sites, targets, alpha=alpha_diag)
        elif arm in TARGET_ARMS:
            mode = BETA_TARGET_MODE[arm]
            merged = {**targets, **alt_targets}
            if mode == "contrastive":
                rec = MODES["contrastive"](q, credit.sites, alts, merged,
                                           alpha=alpha_diag)
            elif mode == "positive_alternative_only":
                rec = MODES["positive_alternative_only"](q, alts, merged,
                                                         alpha=alpha_diag)
            else:
                rec = MODES["negative_only"](q, credit.sites, merged,
                                             alpha=alpha_diag)
        else:
            rec = MODES["negative_only"](q, credit.sites, targets, alpha=alpha_diag)
        corrections += 1
        sites_touched += len(rec.applied)
        clippings += sum(1 for u in rec.applied if u.clipped)
        responsible = responsible_units(res)
        collateral += sum(1 for u in rec.applied if u.unit not in responsible)
        wmd_sum += wmd(before, q, ks, credit.blamed_units)
        kd_sum += kd_innocent(before, q, ks, credit.blamed_units)

        if (ep + 1) % eval_every == 0:
            record(ep + 1)

    n_corr = max(1, corrections)
    return {
        "seed": int(seed),
        "arm": arm,
        "n_failed": n_fail,
        "family_counts": counts,
        "corrections": corrections,
        "sites_touched": sites_touched,
        "clippings": clippings,
        "collateral": collateral / max(1, sites_touched),
        "wmd": wmd_sum / n_corr,
        "kd_innocent": kd_sum / n_corr,
        "n_negative_td": int(neg_td),
        "checkpoints": checkpoints,
        "success_curve": curve,
        "q_hash": q.deep_hash(),
        "ks_size": len(ks.items),
    }


def verify_seed(cfg, *, seed, arm, replica) -> dict:
    """Run the repository's own ``train()`` and compare fingerprints."""
    ref = train(cfg, seed=seed, arm=arm)
    checks = {
        "q_hash": ref.q_hash == replica["q_hash"],
        "family_counts": ref.family_counts == replica["family_counts"],
        "corrections": ref.corrections == replica["corrections"],
        "sites_touched": ref.sites_touched == replica["sites_touched"],
        "clippings": ref.clippings == replica["clippings"],
        "n_negative_td": ref.n_negative_td == replica["n_negative_td"],
        "checkpoints": ref.checkpoints == replica["checkpoints"],
        "success_curve": ref.success_curve == replica["success_curve"],
        "wmd": abs(ref.wmd - replica["wmd"]) < 1e-12,
        "kd_innocent": abs(ref.kd_innocent - replica["kd_innocent"]) < 1e-12,
        "collateral": abs(ref.collateral - replica["collateral"]) < 1e-12,
    }
    return {"seed": int(seed), "arm": arm, "identical": all(checks.values()),
            "checks": checks,
            "mismatched": sorted(k for k, v in checks.items() if not v)}


# --------------------------------------------------------------------------
# summary + report (works from disk, so --report-only is a real re-analysis)
# --------------------------------------------------------------------------


def summarise(rows: list, *, meta: dict) -> dict:
    n = len(rows)
    sizes = Counter(r["n_candidates"] for r in rows)
    fam_counts = Counter(r["family"] for r in rows)
    regrets = [r["regret_of_selected"] for r in rows if r["regret_of_selected"] is not None]
    regrets_first = [r["regret_of_selected_first"] for r in rows
                     if r["regret_of_selected_first"] is not None]
    zero = [r for r in rows if r["regret_of_selected"] == 0.0]
    zero_first = [r for r in rows if r["regret_of_selected_first"] == 0.0]
    nonvacuous = [r for r in rows if r["n_candidates"] >= 2]
    min_gt1 = [r for r in rows if (r["minimal_size"] or 0) > 1]
    empty = [r for r in rows if r["n_candidates"] == 0]

    agree = [r for r in rows
             if (r["family"] == "WholeProcess") == bool((r["minimal_size"] or 0) > 1)]
    disagree = [r for r in rows
                if (r["family"] == "WholeProcess") != bool((r["minimal_size"] or 0) > 1)]

    all_candidates = [c for r in rows for c in r["candidates"]]
    n_minimal_false = sum(1 for c in all_candidates if not c["minimal"])
    spread = Counter(len({c["V_true"] for c in r["candidates"]})
                     for r in rows if r["candidates"])
    v_hist = Counter(round(c["V_true"], 12) for c in all_candidates)

    def struct_key(r):
        s = r["scene"]
        plan_ok = s.get("plan_matches_context")
        if plan_ok is None:
            plan_ok = s.get("g") is not None and s["plan"] == s["g"]
        return ("plan_ok=%s|dec=%s|exec=%s|same_step=%s" % (
            "Y" if plan_ok else "N",
            "Y" if s["decision_fault_at"] is not None else "N",
            "Y" if s["execution_fault_at"] is not None else "N",
            "Y" if (s["execution_fault_at"] is not None
                     and s["decision_fault_at"] == s["execution_fault_at"]) else "N"))

    by_structure = {}
    for key in sorted({struct_key(r) for r in rows}):
        sub = [r for r in rows if struct_key(r) == key]
        by_structure[key] = {
            "n": len(sub),
            "families": {k: int(v) for k, v in sorted(Counter(r["family"] for r in sub).items())},
            "n_minimal_size_gt1": sum(1 for r in sub if (r["minimal_size"] or 0) > 1),
            "n_empty_candidates": sum(1 for r in sub if r["n_candidates"] == 0),
        }
    exec_rows = [r for r in rows if r["scene"]["execution_fault_at"] is not None]
    plan_rows = [r for r in rows if r["family"] == "Plan"]
    v_by_plan_prim = {"candidates_touching_plan": {}, "candidates_not_touching_plan": {}}
    for c in all_candidates:
        bucket = ("candidates_touching_plan"
                  if any(p.startswith("plan:") for p in c["repair"])
                  else "candidates_not_touching_plan")
        k = f"{c['V_true']:.6g}"
        v_by_plan_prim[bucket][k] = v_by_plan_prim[bucket].get(k, 0) + 1

    by_family = {}
    for fam, cnt in sorted(fam_counts.items()):
        sub = [r for r in rows if r["family"] == fam]
        sreg = [r["regret_of_selected"] for r in sub
                if r["regret_of_selected"] is not None]
        sfirst = [r["regret_of_selected_first"] for r in sub
                  if r["regret_of_selected_first"] is not None]
        by_family[fam] = {
            "n": cnt,
            "share": cnt / n if n else None,
            "mean_n_candidates": _mean([r["n_candidates"] for r in sub]),
            "n_empty": sum(1 for r in sub if r["n_candidates"] == 0),
            "fraction_empty": (sum(1 for r in sub if r["n_candidates"] == 0) / cnt),
            "n_minimal_size_gt1": sum(1 for r in sub if (r["minimal_size"] or 0) > 1),
            "fraction_minimal_size_gt1": (sum(1 for r in sub
                                              if (r["minimal_size"] or 0) > 1) / cnt),
            "n_selected_regret_zero": sum(1 for r in sub
                                          if r["regret_of_selected"] == 0.0),
            "fraction_selected_regret_zero": (
                sum(1 for r in sub if r["regret_of_selected"] == 0.0) / len(sreg)
                if sreg else None),
            "mean_regret_of_selected": _mean(sreg),
            "median_regret_of_selected": _median(sreg),
            "max_regret_of_selected": (max(sreg) if sreg else None),
            "mean_regret_of_selected_first": _mean(sfirst),
            "median_regret_of_selected_first": _median(sfirst),
            "n_candidates_gt1": sum(1 for r in sub if r["n_candidates"] >= 2),
            "n_rule_disagreements": sum(1 for r in sub if r["selection_rules_disagree"]),
            "mean_V_true": _mean([c["V_true"] for r in sub for c in r["candidates"]]),
        }

    return {
        "schema_version": meta.get("schema_version"),
        "experiment": "v04_ledger",
        "arm": meta.get("arm"),
        "seeds": meta.get("seeds"),
        "seed_base": meta.get("seed_base"),
        "episodes": meta.get("episodes"),
        "v_samples": meta.get("v_samples"),
        "run_oracle_samples": RUN_ORACLE_SAMPLES,
        "n_failed_episodes": n,
        "n_training_episodes": meta.get("n_training_episodes"),
        "fraction_failed": (n / meta["n_training_episodes"]
                            if meta.get("n_training_episodes") else None),
        "candidate_set_size_histogram": _histogram(sizes),
        "candidate_set_size_fractions": (
            {str(k): v / n for k, v in sorted(sizes.items())} if n else {}),
        "n_candidates_total": len(all_candidates),
        "candidate_set_singleton_fraction": (sizes.get(1, 0) / n if n else None),
        "fraction_empty_candidate_set": len(empty) / n if n else None,
        "n_empty_candidate_set": len(empty),
        "fraction_minimal_size_gt1": len(min_gt1) / n if n else None,
        "n_minimal_size_gt1": len(min_gt1),
        "fraction_minimal_size_gt1_of_nonempty": (
            len(min_gt1) / (n - len(empty)) if n - len(empty) else None),
        "minimal_size_histogram": _histogram(
            Counter(r["minimal_size"] for r in rows if r["minimal_size"] is not None)),
        "wholeprocess_equals_minimal_size_gt1": {
            "confirmed": len(disagree) == 0,
            "n_rows": n,
            "n_agree": len(agree),
            "n_disagree": len(disagree),
            "disagreements": [
                {"seed": r["seed"], "episode": r["episode"], "family": r["family"],
                 "minimal_size": r["minimal_size"], "n_candidates": r["n_candidates"]}
                for r in disagree[:5]],
        },
        "selection_primary_rule": {
            "rule": "selected_repair(trace, res, pick='best')  [train.py's rule]",
            "n_episodes_with_candidates": len(regrets),
            "n_selected_regret_zero": len(zero),
            "fraction_selected_regret_zero": len(zero) / len(regrets) if regrets else None,
            "fraction_selected_regret_zero_over_all_failed": (len(zero) / n if n else None),
            "mean_regret_of_selected": _mean(regrets),
            "median_regret_of_selected": _median(regrets),
            "max_regret_of_selected": (max(regrets) if regrets else None),
            "n_episodes_with_2plus_candidates": len(nonvacuous),
            "fraction_selected_regret_zero_given_2plus": (
                sum(1 for r in nonvacuous if r["regret_of_selected"] == 0.0)
                / len(nonvacuous) if nonvacuous else None),
        },
        "selection_secondary_rule": {
            "rule": "selected_repair(trace, res, pick='first')  "
                    "[smallest, then lexicographic; non-oracle]",
            "n_selected_regret_zero": len(zero_first),
            "fraction_selected_regret_zero": (len(zero_first) / len(regrets_first)
                                              if regrets_first else None),
            "mean_regret_of_selected": _mean(regrets_first),
            "median_regret_of_selected": _median(regrets_first),
            "max_regret_of_selected": (max(regrets_first) if regrets_first else None),
            "n_rule_disagreements": sum(1 for r in rows if r["selection_rules_disagree"]),
        },
        "v_true": {
            "histogram": {repr(k): int(v) for k, v in sorted(v_hist.items())},
            "mean": _mean([c["V_true"] for c in all_candidates]),
            "n_distinct_candidate_values_per_episode": _histogram(spread),
            "n_candidates_not_minimal": n_minimal_false,
            "by_plan_primitive": v_by_plan_prim,
        },
        "by_scene_structure": by_structure,
        "execution_fault_rows": {
            "n": len(exec_rows),
            "share_of_failures": len(exec_rows) / n if n else None,
            "families": {k: int(v) for k, v in sorted(Counter(
                r["family"] for r in exec_rows).items())},
            "minimal_size_histogram": _histogram(Counter(
                r["minimal_size"] for r in exec_rows if r["minimal_size"] is not None)),
            "n_decision_fault_equals_execution_fault": sum(
                1 for r in exec_rows
                if r["scene"]["decision_fault_at"] == r["scene"]["execution_fault_at"]),
        },
        "n_family_plan_but_plan_matches_context": sum(
            1 for r in plan_rows if r["scene"].get("plan_matches_context")),
        "regret_api_check": {
            "n_rows_checked": sum(1 for r in rows if "regret_api_agrees" in r),
            "n_mismatch_with_local_candidate_table": sum(
                1 for r in rows if r.get("regret_api_agrees") is False),
        },
        "family_counts": {k: int(v) for k, v in sorted(fam_counts.items())},
        "by_family": by_family,
        "field_notes": FIELD_NOTES,
        "meta": {k: v for k, v in meta.items() if k != "config"},
    }


def _bar(frac: float, width: int = 36) -> str:
    return "#" * int(round(max(0.0, min(1.0, frac)) * width))


def format_report(s: dict) -> str:
    n = s["n_failed_episodes"]
    seeds = s["seeds"] or []
    out = []
    out.append("=== v0.4 candidate ledger ===")
    if seeds:
        out.append(f"arm={s['arm']}  seeds={len(seeds)} "
                   f"({seeds[0]}..{seeds[-1]})")
    else:
        out.append(f"arm={s['arm']}  seeds=none")
    out.append(f"episodes/seed={s['episodes']}  v_samples={s['v_samples']} "
               f"(train.py's runtime oracle uses {s['run_oracle_samples']})")
    if s.get("n_training_episodes"):
        out.append(f"failed episodes: {n} / {s['n_training_episodes']} "
                   f"({(s['fraction_failed'] or 0):.4f})")
    if s.get("wall_s") is not None:
        out.append(f"wall: {s['wall_s']:.1f}s")
    if s.get("pythonhashseed") is not None:
        out.append(f"PYTHONHASHSEED={s['pythonhashseed']}"
                   f"{'' if s.get('hash_seed_pinned') else '  (NOT pinned: jsonl not '
                      'guaranteed byte-reproducible across processes)'}")

    veq = s.get("train_equivalence")
    if veq is not None:
        nok = sum(1 for v in veq if v["identical"])
        out.append(f"train() equivalence: {nok}/{len(veq)} seeds identical "
                   f"(q_hash, family_counts, corrections, sites, clippings, "
                   f"neg-TD, checkpoints, curve, wmd, kd, collateral)")

    out.append("")
    out.append("candidate-set size   (n_candidates -> episodes)")
    hist = s["candidate_set_size_histogram"]
    fr = s.get("candidate_set_size_fractions", {})
    for k in sorted(hist, key=int):
        c = hist[k]
        out.append(f"  {k:>3}: {c:>7}  {fr.get(k, 0.0):>7.4f}  {_bar(fr.get(k, 0.0))}")
    out.append(f"empty candidate set:      {s['fraction_empty_candidate_set']:.4f} "
               f"({s['n_empty_candidate_set']} episodes)")
    out.append(f"minimal_size > 1:         {s['fraction_minimal_size_gt1']:.4f} "
               f"(of non-empty: {s['fraction_minimal_size_gt1_of_nonempty']:.4f})")
    out.append(f"minimal_size histogram:   {s['minimal_size_histogram']}")
    w = s["wholeprocess_equals_minimal_size_gt1"]
    out.append(f"WholeProcess == (minimal_size>1): "
               f"{'CONFIRMED' if w['confirmed'] else 'REFUTED'} "
               f"({w['n_agree']}/{w['n_rows']} rows agree, {w['n_disagree']} disagree)")
    for d in w["disagreements"]:
        out.append(f"    counterexample: seed={d['seed']} ep={d['episode']} "
                   f"family={d['family']} minimal_size={d['minimal_size']} "
                   f"n_candidates={d['n_candidates']}")

    out.append("")
    p = s["selection_primary_rule"]
    out.append(f"selection rule: {p['rule']}")
    out.append(f"  picked a regret-0 candidate: {_fmt(p['fraction_selected_regret_zero'], 4)} "
               f"({p['n_selected_regret_zero']}/{p['n_episodes_with_candidates']} episodes "
               f"with candidates; {_fmt(p['fraction_selected_regret_zero_over_all_failed'], 4)}"
               f" over all {n} failures)")
    out.append(f"  mean/median/max regret_of_selected: "
               f"{_fmt(p['mean_regret_of_selected'])} / "
               f"{_fmt(p['median_regret_of_selected'])} / "
               f"{_fmt(p['max_regret_of_selected'])}")
    out.append(f"  episodes with >=2 candidates: {p['n_episodes_with_2plus_candidates']}"
               + (f"  (regret-0 share there: "
                  f"{_fmt(p['fraction_selected_regret_zero_given_2plus'])})"
                  if p["n_episodes_with_2plus_candidates"] else "  (no choice ever arose)"))
    q = s["selection_secondary_rule"]
    out.append(f"secondary rule: {q['rule']}")
    out.append(f"  picked a regret-0 candidate: {_fmt(q['fraction_selected_regret_zero'])}"
               f"  mean regret {_fmt(q['mean_regret_of_selected'])}"
               f"  max {_fmt(q['max_regret_of_selected'])}"
               f"  disagreements with 'best': {q['n_rule_disagreements']}")

    out.append("")
    out.append("by family")
    head = (f"  {'family':<13}{'n':>7}{'share':>8}{'cand/row':>10}{'empty':>8}"
            f"{'min>1':>8}{'regret0':>9}{'meanReg':>10}{'medReg':>9}{'>1cand':>8}")
    out.append(head)
    for fam, v in s["by_family"].items():
        out.append(
            f"  {fam:<13}{v['n']:>7}{v['share']:>8.4f}"
            f"{_fmt(v['mean_n_candidates'], 3):>10}{v['fraction_empty']:>8.3f}"
            f"{v['fraction_minimal_size_gt1']:>8.3f}"
            f"{_fmt(v['fraction_selected_regret_zero'], 3):>9}"
            f"{_fmt(v['mean_regret_of_selected'], 5):>10}"
            f"{_fmt(v['median_regret_of_selected'], 5):>9}"
            f"{v['n_candidates_gt1']:>8}")
    out.append("  (regret0 = share of that family's episodes with a candidate set where "
               "the rule picked a regret-0 candidate; n/a where no episode had one)")

    v = s["v_true"]
    out.append("")
    out.append(f"V_true over {s['n_candidates_total']} candidates: mean="
               f"{_fmt(v['mean'], 5)}  histogram={v['histogram']}")
    out.append(f"  distinct V_true values per episode: "
               f"{v['n_distinct_candidate_values_per_episode']}")
    out.append(f"  by plan primitive: {v['by_plan_primitive']}")
    out.append(f"  candidates with minimal=False: {v['n_candidates_not_minimal']} "
               f"(enumerate_sufficient returns one size only)")

    out.append("")
    out.append("scene structure of the reconstructed scene -> family "
               "(plan_ok = chosen plan == context lane)")
    for key, v2 in s["by_scene_structure"].items():
        out.append(f"  {key:<38}{v2['n']:>7}  min>1={v2['n_minimal_size_gt1']:>6}  "
                   f"empty={v2['n_empty_candidates']:>5}  {v2['families']}")
    ex = s["execution_fault_rows"]
    out.append(f"  execution-fault failures: {ex['n']} "
               f"({_fmt(ex['share_of_failures'], 4)} of failures); "
               f"decision_fault_at == execution_fault_at in "
               f"{ex['n_decision_fault_equals_execution_fault']} of them; "
               f"families={ex['families']}")
    out.append(f"  failures labelled Plan although the chosen plan already "
               f"matched the context: {s['n_family_plan_but_plan_matches_context']}")

    st = s.get("step_traces")
    if st:
        out.append("")
        out.append(f"step traces: {st['n']} episodes "
                   f"(first-failure sample {st['first_n']} + every "
                   f"'{st['smallest_family']}' episode, {st['n_smallest_family']} "
                   f"of {st['smallest_family_count_in_run']}"
                   + (", CAPPED" if st["capped"] else "") + ")")
        out.append(f"  families in the trace sample: {st['families']}")

    api = s["regret_api_check"]
    out.append("")
    out.append("structural notes (all measured above, not assumed)")
    out.append(f"  candidate set is a singleton in "
               f"{_fmt(s['candidate_set_singleton_fraction'], 4)} of failures and "
               f"empty in {_fmt(s['fraction_empty_candidate_set'], 4)}")
    multi = s["selection_primary_rule"]["n_episodes_with_2plus_candidates"]
    out.append(f"  episodes where the selection rule had a choice "
               f"(>=2 candidates): {multi}")
    same_v = sum(cnt for k, cnt in
                 v["n_distinct_candidate_values_per_episode"].items() if k == "1")
    out.append(f"  episodes whose candidates all share one V_true value: {same_v}"
               f"  -> regret_vs_best is 0 for every candidate")
    out.append(f"  pick='best' vs pick='first': "
               f"{s['selection_secondary_rule']['n_rule_disagreements']} disagreements")
    out.append(f"  candidates with minimal=False: {v['n_candidates_not_minimal']} "
               f"-- enumerate_sufficient() stops at the first sufficient size, so "
               f"every returned candidate is minimal by construction")
    out.append(f"  repair_regret vs the local candidate table: "
               f"{api['n_rows_checked']} rows checked, "
               f"{api['n_mismatch_with_local_candidate_table']} mismatches")
    return "\n".join(out)


def _fmt(x, nd: int = 5) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


# --------------------------------------------------------------------------
# io
# --------------------------------------------------------------------------


def read_jsonl(path: Path) -> list:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--episodes", type=int, default=2000)
    ap.add_argument("--arm", default="NegativeOnly",
                    help="which arm's training stream to record (default: the "
                         "Pilot Beta winner, the arm whose applied correction is "
                         "exactly selected_repair(pick='best'))")
    ap.add_argument("--v-samples", type=int, default=RUN_ORACLE_SAMPLES,
                    help="n_samples for repair_value / oracle_repair_set "
                         f"(default {RUN_ORACLE_SAMPLES}, train.py's own fidelity)")
    ap.add_argument("--trace-first", type=int, default=40,
                    help="emit step traces for the first N failures")
    ap.add_argument("--trace-family-max", type=int, default=200,
                    help="cap on how many episodes the smallest family contributes")
    ap.add_argument("--no-verify-train", action="store_true",
                    help="skip the per-seed equivalence check against train()")
    ap.add_argument("--no-pin-hash-seed", action="store_true",
                    help="do not pin PYTHONHASHSEED=0; train() is then not "
                         "cross-process reproducible and neither is the jsonl")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args(argv)

    if not args.report_only and not args.no_pin_hash_seed:
        code = reexec_with_pinned_hash_seed(sys.argv[1:])
        if code is not None:
            return code

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    exp = cfg["experiment"]
    exp["seeds"] = args.seeds
    exp["episodes"] = args.episodes
    if args.arm not in ARMS:
        raise SystemExit(f"unknown arm {args.arm!r}; choose from {ARMS}")

    outdir = Path(args.outdir)
    ledger_path = outdir / "candidate_ledger.jsonl"
    traces_path = outdir / "step_traces.jsonl"
    summary_path = outdir / "candidate_ledger_summary.json"

    if args.report_only:
        if not ledger_path.exists():
            raise SystemExit(f"--report-only: {ledger_path} does not exist")
        rows = read_jsonl(ledger_path)
        traces = read_jsonl(traces_path) if traces_path.exists() else []
        arms = sorted({r["arm"] for r in rows})
        seeds = sorted({r["seed"] for r in rows})
        episodes = sorted({r["episodes"] for r in rows}) if rows and "episodes" in rows[0] \
            else [exp["episodes"]]
        meta = {"schema_version": cfg["schema_version"], "arm": arms[0] if len(arms) == 1
                else arms, "seeds": seeds, "episodes": episodes[0],
                "seed_base": exp["seed_base"], "v_samples":
                (rows[0]["v_samples"] if rows else None),
                "n_training_episodes": len(seeds) * episodes[0]}
        summary = summarise(rows, meta=meta)
        if traces:
            summary["step_traces"] = _trace_meta(traces)
        # carry over the run-only evidence the jsonl cannot reproduce
        if summary_path.exists():
            try:
                old = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                old = {}
            for key in ("wall_s", "pythonhashseed", "hash_seed_pinned",
                        "determinism_note", "train_equivalence",
                        "replica_fingerprints"):
                if key in old:
                    summary[key] = old[key]
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(format_report(summary))
        print(f"\n[report-only] recomputed from {ledger_path} "
              f"({len(rows)} ledger rows, {len(traces)} step traces); "
              f"training NOT re-run.")
        print(f"[report-only] run-only evidence carried over from the previous "
              f"summary: "
              f"{[k for k in ('wall_s', 'train_equivalence', 'replica_fingerprints') if k in summary]}")
        return EXIT_OK

    if outdir.exists() and any(outdir.iterdir()) and not ledger_path.exists():
        raise SystemExit(
            f"refusing to write into non-empty {outdir} which holds no "
            f"candidate_ledger.jsonl -- pick the new outputs/v04_ledger directory "
            f"(existing outputs/* runs must not be touched)")

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "config.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=True), encoding="utf-8")

    t0 = time.perf_counter()
    seeds = [int(exp["seed_base"]) + i for i in range(int(exp["seeds"]))]
    trace_buf: list = []
    seed_stats, verification = [], []

    with ledger_path.open("w", encoding="utf-8", newline="\n") as fh:
        for seed in seeds:
            stats = run_seed(cfg, seed=seed, arm=args.arm, v_samples=args.v_samples,
                             on_row=lambda row: fh.write(
                                 json.dumps(_strip_private(row), ensure_ascii=False) + "\n"),
                             on_trace=lambda tr: trace_buf.append(tr))
            seed_stats.append(stats)
            line = (f"[seed {seed}] failed={stats['n_failed']} "
                    f"corrections={stats['corrections']} "
                    f"families={stats['family_counts']}")
            if not args.no_verify_train:
                v = verify_seed(cfg, seed=seed, arm=args.arm, replica=stats)
                verification.append(v)
                line += f"  train()_identical={v['identical']}"
                if not v["identical"]:
                    line += f" MISMATCH={v['mismatched']}"
            print(line, flush=True)
    wall = time.perf_counter() - t0

    # ---- step-trace sample: first N failures + every smallest-family episode
    traces = _select_traces(trace_buf, first_n=args.trace_first,
                            family_max=args.trace_family_max)
    with traces_path.open("w", encoding="utf-8", newline="\n") as fh:
        for tr in traces:
            fh.write(json.dumps(tr, ensure_ascii=False) + "\n")

    rows = read_jsonl(ledger_path)
    n_episodes = len(seeds) * int(exp["episodes"])
    meta = {"schema_version": cfg["schema_version"], "arm": args.arm,
            "seeds": seeds, "seed_base": int(exp["seed_base"]),
            "episodes": int(exp["episodes"]), "v_samples": args.v_samples,
            "n_training_episodes": n_episodes, "config": cfg}
    summary = summarise(rows, meta=meta)
    summary["wall_s"] = wall
    summary["pythonhashseed"] = os.environ.get("PYTHONHASHSEED")
    summary["hash_seed_pinned"] = (
        os.environ.get("PYTHONHASHSEED") == HASH_SEED_PIN or args.no_pin_hash_seed)
    summary["determinism_note"] = (
        "PYTHONHASHSEED is pinned to 0 by re-exec so the jsonl is byte-identical "
        "for a given --seeds/--episodes/--arm/--v-samples. Without the pin, "
        "rflv04.credit_units.decision_oracle's frozenset iteration order changes "
        "the Q writes and train() is not cross-process reproducible "
        "(measured: 3 processes x same seed -> 3 different q_hashes).")
    summary["train_equivalence"] = verification or None
    summary["replica_fingerprints"] = [
        {k: s[k] for k in ("seed", "arm", "n_failed", "corrections", "sites_touched",
                           "clippings", "n_negative_td", "q_hash", "family_counts")}
        for s in seed_stats]
    summary["step_traces"] = _trace_meta(traces)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    print()
    print(format_report(summary))
    print(f"\nwrote {ledger_path} ({len(rows)} rows), {traces_path} "
          f"({len(traces)} rows), {summary_path}")

    if verification and not all(v["identical"] for v in verification):
        return EXIT_REPLICA_MISMATCH
    if not summary["wholeprocess_equals_minimal_size_gt1"]["confirmed"]:
        return EXIT_GATE_FAILED
    return EXIT_OK


def _strip_private(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _trace_meta(traces: list) -> dict:
    fams = Counter(t["family"] for t in traces)
    sample = traces[0].get("sample", {}) if traces else {}
    return {
        "n": len(traces),
        "first_n": sum(1 for t in traces if t.get("sample", {}).get("first_failures")),
        "families": {k: int(v) for k, v in sorted(fams.items())},
        "smallest_family": sample.get("smallest_family_name"),
        "n_smallest_family": sum(1 for t in traces
                                 if t.get("sample", {}).get("smallest_family")),
        "smallest_family_count_in_run": sample.get("smallest_family_count_in_run"),
        "capped": bool(sample.get("capped")),
    }


def _select_traces(buffered: list, *, first_n: int, family_max: int) -> list:
    """First ``first_n`` failures plus every episode of the smallest family."""
    if not buffered:
        return []
    buffered = sorted(buffered, key=lambda t: (t["seed"], t["episode"]))
    fam_counts = Counter(t["family"] for t in buffered)
    smallest = min(sorted(fam_counts), key=lambda f: (fam_counts[f], f))
    chosen: dict = {}
    reasons: dict = {}

    def add(trace, reason):
        key = (trace["seed"], trace["episode"])
        chosen[key] = trace
        reasons.setdefault(key, set()).add(reason)

    for t in buffered[:first_n]:
        add(t, "first_failures")
    for t in [x for x in buffered if x["family"] == smallest][:family_max]:
        add(t, "smallest_family")

    out = []
    for key in sorted(chosen):
        trace = dict(chosen[key])
        reasons_here = reasons[key]
        trace["sample"] = {
            "first_failures": "first_failures" in reasons_here,
            "smallest_family": "smallest_family" in reasons_here,
            "smallest_family_name": smallest,
            "smallest_family_count_in_run": fam_counts[smallest],
            "capped": fam_counts[smallest] > family_max,
        }
        out.append(trace)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
