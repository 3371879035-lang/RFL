"""Pilot Gamma: Sequence evidence x counterfactual verification.

The question is not "can counterfactuals find the faulty step" -- that is the
part other 2026 work already covers.  It is whether a *cheap observational*
signal can pick which counterfactual to spend budget on, so that a fixed
verification budget buys more attribution quality.

Structural setup that makes the comparison honest
------------------------------------------------
The diagnoser sees only what a learner could see: the sequence of low-level
``(state, action)`` pairs, the ``option`` that was chosen, and the terminal
kind.  It does **not** see ``goal_lane`` or ``hazard`` -- both are latent, and
both are recorded evaluator-side only.

That leaves a real, irreducible ambiguity:

* ``terminal == BLOCKED``  -> the agent entered the exit cell and the gate was
  jammed -> the environment is responsible.  Observable.
* ``reached the end of its own corridor, then TIMEOUT`` -> the corridor it
  walked was not the one holding the exit -> the high level is responsible.
  Observable.
* ``TIMEOUT without reaching the end`` -> **ambiguous**.  Either the low level
  failed to execute, or the environment was jammed and the agent never got
  there.  Both look identical in the action sequence.

Counterfactual verification resolves exactly that ambiguity: re-running the
reference execution under the *same* tape tells the diagnoser whether perfect
execution would have won, which separates "execution failed" from "the world
was against it" without ever revealing ``hazard``.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from .env import (
    DOWN,
    HORIZON,
    RIGHT,
    SUCCESS,
    TIMEOUT,
    UP,
    W,
    WAIT,
    step_cell,
    terminal_kind,
)
from .labels import causal_labels

CAUSES = ("H", "L", "E")
FAILURE_FAMILIES = ("H_error", "L_error", "HL_error", "E_failure")


# --------------------------------------------------------------------------
# Traces
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Trace:
    trace_id: str
    option: int
    actions: tuple[int, ...]
    states: tuple[tuple, ...]
    terminal: str
    steps: int
    final_x: int
    final_y: int
    # evaluator-side only; never handed to an attributor
    goal_lane: int
    hazard: int
    family: str
    u_h: int
    u_l: int


def _corridor_action(x: int, y: int, option: int) -> int:
    """The reference (correct) action for walking corridor ``option``."""
    if y != option:
        return DOWN if option == 1 else UP
    if x < W - 1:
        return RIGHT
    return WAIT


def make_trace(
    trace_id: str,
    *,
    goal_lane: int,
    hazard: int,
    option: int,
    fault: bool,
    fault_start: int = 1,
    horizon: int = HORIZON,
) -> Trace | None:
    """Generate one episode with an independently controlled causal structure.

    ``fault`` makes the low level stall from ``fault_start`` (a WAIT loop), so
    it cannot complete its corridor.  ``option`` may be set against
    ``goal_lane`` to make the high level wrong.  ``hazard`` jams the exit.
    Returns ``None`` on success: a successful episode has nothing to diagnose.
    """
    x, y = 0, 0
    actions: list = []
    states: list = []
    terminal = TIMEOUT
    for t in range(1, horizon + 1):
        stalled = fault and t >= fault_start
        a = WAIT if stalled else _corridor_action(x, y, option)
        states.append((x, y, option, t))
        nx, ny = step_cell(x, y, a)
        kind = terminal_kind(nx, ny, goal_lane, hazard)
        actions.append(a)
        x, y = nx, ny
        if kind is not None:
            terminal = kind
            break

    lab = causal_labels(
        option=option, goal_lane=goal_lane, final_x=x, final_y=y,
        hazard=hazard, terminal=terminal,
    )
    if lab is None:
        return None
    return Trace(
        trace_id=trace_id, option=option, actions=tuple(actions), states=tuple(states),
        terminal=terminal, steps=len(actions), final_x=x, final_y=y,
        goal_lane=goal_lane, hazard=hazard, family=lab.family,
        u_h=lab.u_h, u_l=lab.u_l,
    )


def generate_balanced(
    n_total: int,
    *,
    seed: int,
    horizon: int = HORIZON,
    p_hazard: float = 0.25,
    max_draws: int | None = None,
) -> list[Trace]:
    """Draw traces until each failure family has its quota, so the four
    families are balanced by construction rather than by luck."""
    import numpy as np

    quota = n_total // len(FAILURE_FAMILIES)
    rng = np.random.default_rng(int(seed) % (2**32 - 1))
    counts = {f: 0 for f in FAILURE_FAMILIES}
    out: list[Trace] = []
    draws = 0
    limit = max_draws if max_draws is not None else n_total * 200
    while any(counts[f] < quota for f in FAILURE_FAMILIES) and draws < limit:
        draws += 1
        goal_lane = int(rng.integers(0, 2))
        hazard = int(rng.random() < p_hazard)
        wrong = bool(rng.random() < 0.5)
        option = goal_lane if not wrong else 1 - goal_lane
        fault = bool(rng.random() < 0.5)
        fault_start = int(rng.integers(1, 4))
        tr = make_trace(
            f"T{draws:07d}", goal_lane=goal_lane, hazard=hazard, option=option,
            fault=fault, fault_start=fault_start, horizon=horizon,
        )
        if tr is None:
            continue
        if counts[tr.family] >= quota:
            continue
        counts[tr.family] += 1
        out.append(tr)
    if any(counts[f] < quota for f in FAILURE_FAMILIES):
        raise RuntimeError(f"could not balance families within {limit} draws: {counts}")
    # Families fill at different rates, so generation order is not balanced.
    # Shuffle deterministically before returning, otherwise a naive head/tail
    # train-test split is badly imbalanced (e.g. E_failure 192 vs H_error 132).
    order = rng.permutation(len(out))
    return [out[i] for i in order]


# --------------------------------------------------------------------------
# Sequence-only observational model
# --------------------------------------------------------------------------


def observable_features(tr: Trace) -> dict:
    """Everything a diagnoser could read off the action sequence alone.

    Deliberately excluded: ``goal_lane`` and ``hazard``.  The features are
    chosen to be close to independent, because the model is naive Bayes and
    correlated features make its posterior wildly overconfident.
    """
    return {
        # completed the corridor it was asked to walk
        "reached_end": int(tr.final_x == W - 1 and tr.final_y == tr.option),
        # entered the exit cell and found the gate jammed
        "blocked": int(tr.terminal == "BLOCKED"),
        # never even reached the last column
        "incomplete": int(tr.final_x < W - 1),
    }


FEATURE_NAMES = ("reached_end", "blocked", "incomplete")


def cause_responsible(tr: Trace, cause: str) -> int:
    """Multi-label truth for one cause.  ``H`` and ``L`` can both hold; ``E``
    holds only when neither module was at fault."""
    if cause == "H":
        return int(tr.u_h)
    if cause == "L":
        return int(tr.u_l)
    if cause == "E":
        return int(not tr.u_h and not tr.u_l)
    raise ValueError(cause)


@dataclass
class SequenceModel:
    """Naive Bayes over the observable features.  Cheap, and deliberately not
    allowed to see the latent scene variables.

    Fitted **multi-label**: the likelihood for cause ``c`` is estimated from
    every trace in which ``c`` is responsible, so an ``HL_error`` trace
    contributes to both the H and the L class instead of being collapsed into
    one of them.
    """

    log_prior: dict = field(default_factory=dict)
    log_likelihood: dict = field(default_factory=dict)

    def fit(self, traces: list[Trace]) -> "SequenceModel":
        import math

        n = len(traces)
        self.log_prior = {}
        self.log_likelihood = {}
        for c in CAUSES:
            subset = [t for t in traces if cause_responsible(t, c)]
            nc = len(subset)
            self.log_prior[c] = math.log((nc + 1) / (n + len(CAUSES)))
            self.log_likelihood[c] = {}
            for f in FEATURE_NAMES:
                ones = sum(observable_features(t)[f] for t in subset)
                p1 = (ones + 1) / (nc + 2)
                # Stored as (log P(f=0), log P(f=1)) so that ``score`` can
                # index straight with the binary feature value.  Storing
                # (log p1, log(1-p1)) reads every feature inverted.
                self.log_likelihood[c][f] = (math.log(1.0 - p1), math.log(p1))
        return self

    def score(self, tr: Trace) -> dict:
        """Normalised posterior.  Gamma needs a categorical score for
        AUPRC/Brier; the multi-label ``p`` vs gated ``U`` separation is
        enforced in the update path, not here."""
        import math

        feats = observable_features(tr)
        logits = {}
        for c in CAUSES:
            s = self.log_prior[c]
            for f in FEATURE_NAMES:
                s += self.log_likelihood[c][f][feats[f]]
            logits[c] = s
        m = max(logits.values())
        exps = {c: math.exp(v - m) for c, v in logits.items()}
        z = sum(exps.values())
        return {c: exps[c] / z for c in CAUSES}  # type: ignore[operator]


# --------------------------------------------------------------------------
# Counterfactual verification
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CFResult:
    hypothesis: str  # "H" or "L"
    outcome: str
    queries: int


def cf_query(tr: Trace, hypothesis: str, *, horizon: int = HORIZON) -> CFResult:
    """Re-run the *reference* execution under the same latent scene.

    ``hypothesis="L"``: perfect low-level execution with the factual option.
    ``hypothesis="H"``: perfect execution with the option flipped.

    The latent ``hazard`` and ``goal_lane`` are held fixed -- this is the
    common-random-numbers discipline that makes the comparison causal.
    """
    if hypothesis == "L":
        option = tr.option
    elif hypothesis == "H":
        option = 1 - tr.option
    else:
        raise ValueError(hypothesis)
    x, y = 0, 0
    terminal = TIMEOUT
    for _t in range(1, horizon + 1):
        a = _corridor_action(x, y, option)
        nx, ny = step_cell(x, y, a)
        kind = terminal_kind(nx, ny, tr.goal_lane, tr.hazard)
        x, y = nx, ny
        if kind is not None:
            terminal = kind
            break
    return CFResult(hypothesis=hypothesis, outcome=terminal, queries=1)


def responsibility_from_cf(results: dict) -> dict:
    """Map a (possibly partial) set of counterfactual outcomes to a score."""
    l_res = results.get("L")
    h_res = results.get("H")
    if l_res is not None and l_res.outcome == SUCCESS:
        return {"H": 0.0, "L": 1.0, "E": 0.0}
    if h_res is not None and h_res.outcome == SUCCESS:
        return {"H": 1.0, "L": 0.0, "E": 0.0}
    if l_res is not None and h_res is not None:
        # Perfect execution under either option still loses: exogenous.
        return {"H": 0.0, "L": 0.0, "E": 1.0}
    return {}


# --------------------------------------------------------------------------
# Attributors
# --------------------------------------------------------------------------

CANONICAL_ORDER = ("L", "H")


@dataclass
class Attribution:
    method: str
    score: dict
    cf_queries: int
    order: tuple = ()


def attribute_oracle(tr: Trace) -> Attribution:
    return Attribution("oracle", {"H": float(tr.u_h), "L": float(tr.u_l),
                                  "E": 1.0 if (not tr.u_h and not tr.u_l) else 0.0}, 0)


def attribute_sequence(tr: Trace, model: SequenceModel) -> Attribution:
    return Attribution("sequence_only", model.score(tr), 0)


def attribute_cf_only(tr: Trace, model: SequenceModel, k: int) -> Attribution:
    """Run the first ``k`` hypotheses in a fixed canonical order."""
    results = {}
    queries = 0
    for hyp in CANONICAL_ORDER[:k]:
        results[hyp] = cf_query(tr, hyp)
        queries += 1
        score = responsibility_from_cf(results)
        if score:
            return Attribution("cf_only", score, queries, CANONICAL_ORDER[:queries])
    score = responsibility_from_cf(results)
    return Attribution("cf_only", score or model.score(tr), queries, CANONICAL_ORDER[:queries])


def attribute_seq_then_cf(tr: Trace, model: SequenceModel, k: int) -> Attribution:
    """Spend the same budget, but choose which hypotheses to test by the
    sequence model's ranking."""
    prior = model.score(tr)
    ranked = tuple(sorted(CANONICAL_ORDER, key=lambda h: -prior.get(h, 0.0)))
    results = {}
    queries = 0
    for hyp in ranked[:k]:
        results[hyp] = cf_query(tr, hyp)
        queries += 1
        score = responsibility_from_cf(results)
        if score:
            return Attribution("seq_then_cf", score, queries, ranked[:queries])
    score = responsibility_from_cf(results)
    return Attribution("seq_then_cf", score or prior, queries, ranked[:queries])


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------


def average_precision(scores: list[float], labels: list[int]) -> float | None:
    """AUPRC via the standard step-wise average precision."""
    pairs = sorted(zip(scores, labels), key=lambda p: -p[0])
    positives = sum(labels)
    if positives == 0:
        return None
    tp = 0
    precisions = []
    for rank, (_s, y) in enumerate(pairs, start=1):
        if y:
            tp += 1
            precisions.append(tp / rank)
    return float(sum(precisions) / positives)


def brier_multilabel(scores: list[dict], truths: list[dict]) -> float:
    total = 0.0
    n = 0
    for sc, tr in zip(scores, truths):
        for c in CAUSES:
            total += (float(sc.get(c, 0.0)) - float(tr.get(c, 0.0))) ** 2
            n += 1
    return total / n if n else 0.0


def update_quality(attributions: list[Attribution], traces: list[Trace]) -> dict:
    """Translate attribution into the diagnostic update it would cause.

    The correction goes to the top-scoring non-environment module.  If that
    module was innocent, the update damages correct knowledge -- which is the
    downstream quantity the whole chain cares about.
    """
    corrected = 0
    correct_hits = 0
    collateral = 0
    no_op = 0
    for att, tr in zip(attributions, traces):
        best = max(CAUSES, key=lambda c: att.score.get(c, 0.0))
        if best == "E":
            no_op += 1
            continue
        corrected += 1
        truth = tr.u_h if best == "H" else tr.u_l
        if truth:
            correct_hits += 1
        else:
            collateral += 1
    precision = (correct_hits / corrected) if corrected else None
    return {
        "n": len(traces),
        "corrected": corrected,
        "no_op": no_op,
        "no_op_rate": no_op / len(traces) if traces else 0.0,
        "update_precision": precision,
        "collateral_rate": (collateral / corrected) if corrected else None,
    }


def score_method(name: str, attributions: list[Attribution], traces: list[Trace],
                 *, alpha_diag: float = 0.10) -> dict:
    scores = [a.score for a in attributions]
    truths = [{"H": float(t.u_h), "L": float(t.u_l),
               "E": 1.0 if (not t.u_h and not t.u_l) else 0.0} for t in traces]
    out = {"method": name, "n": len(traces)}
    for c in CAUSES:
        out[f"auprc_{c}"] = average_precision(
            [float(s.get(c, 0.0)) for s in scores], [int(t[c]) for t in truths]
        )
    out["brier"] = brier_multilabel(scores, truths)
    out["mean_cf_queries"] = (
        sum(a.cf_queries for a in attributions) / len(attributions) if attributions else 0.0
    )
    out.update(update_quality(attributions, traces))
    out["expected_knowledge_damage"] = alpha_diag * (out["collateral_rate"] or 0.0)
    return out


def run_method(
    name: str, traces: list[Trace], model: SequenceModel, *, k: int = 0
) -> list[Attribution]:
    if name == "oracle":
        return [attribute_oracle(t) for t in traces]
    if name == "sequence_only":
        return [attribute_sequence(t, model) for t in traces]
    if name == "cf_only":
        return [attribute_cf_only(t, model, k) for t in traces]
    if name == "seq_then_cf":
        return [attribute_seq_then_cf(t, model, k) for t in traces]
    raise ValueError(name)
