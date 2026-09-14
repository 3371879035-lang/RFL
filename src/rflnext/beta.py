"""Pilot Beta: penalty x Oracle selective correction, with U-gated updates.

Stage 1 has no attributor, so ``U`` comes from the generator's SCM (see
``labels.py``).  This module adds the one thing Beta needs beyond Alpha: a
**selective diagnostic correction** applied only to the modules that are
responsible, plus knowledge probes that measure whether that correction damaged
knowledge it had no business touching.

Why the probes are where they are
---------------------------------
``KnowledgeDamage`` is "harm to the correct-but-not-responsible module".  For
that number to mean anything, the probe has to sit at a site the correction
actually writes to -- otherwise every arm scores zero and the metric is vacuous.
That was precisely how the v0.2 protected probe died: it looked for established
correct knowledge at a failing trace's terminal transition, which is the one
place the collision had just taught Q to dislike.

Here both probe sites are on the **clean reference path**, which every episode
visits regardless of how it ends:

* ``s_H = (goal_lane, hazard)``; the correct option is ``goal_lane``.
* ``s_L0 = (0, 0, option, 1)``, the first low-level decision; the correct action
  is RIGHT for option 0 and DOWN for option 1.

Damage is reported as an **absolute** margin loss rather than the vendored
relative ``ckd``.  The relative form divides by the initial margin, which is
~0 for the first episodes of a from-scratch run; the absolute form is defined
throughout, and the mean pre-margin is reported alongside so a reader can see
whether there was any established knowledge to damage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .env import DOWN, HORIZON, N_ACTIONS, RIGHT, SUCCESS, TIMEOUT, WAIT
from .knowledge import correct_margin, wrong_margin
from .noise import NoiseTape
from .qtables import QTables, linear_epsilon
from .runner import EpisodeRecord, evaluate, run_episode

# name -> (reward mode, correction rule)
#   rule "none"   : no diagnostic update at all
#   rule "oracle" : update exactly the modules the SCM marks responsible
#   rule "h"/"l"  : always update that module, whatever the truth
#   rule "hl"     : always update both
CONDITIONS: dict[str, tuple[str, str]] = {
    "traditional": ("A", "none"),
    "positive_only": ("B", "none"),
    "traditional_oracle": ("A", "oracle"),
    "positive_only_oracle": ("B", "oracle"),
    "h_only": ("A", "h"),
    "l_only": ("A", "l"),
    "hl": ("A", "hl"),
}

# Which module is "correct but not responsible" in each realized family.
INNOCENT: dict[str, str | None] = {
    "H_error": "L",
    "L_error": "H",
    "HL_error": None,
    "E_failure": "both",
}


@dataclass(frozen=True)
class ProbeSites:
    s_h: tuple
    h_correct: int
    h_wrong: int
    s_l0: tuple
    l_correct: int
    l_wrong: int


def probe_sites(rec: EpisodeRecord) -> ProbeSites:
    """The two clean-reference probe sites for one episode."""
    return ProbeSites(
        s_h=(rec.goal_lane, rec.hazard),
        h_correct=rec.goal_lane,
        h_wrong=1 - rec.goal_lane,
        s_l0=(0, 0, rec.option, 1),
        l_correct=RIGHT if rec.option == 0 else DOWN,
        l_wrong=WAIT,
    )


def _h_values(q: QTables, p: ProbeSites) -> dict:
    return {p.h_correct: q.high_get(p.s_h, p.h_correct),
            p.h_wrong: q.high_get(p.s_h, p.h_wrong)}


def _l_values(q: QTables, p: ProbeSites) -> dict:
    return {p.l_correct: q.low_get(p.s_l0, p.l_correct),
            p.l_wrong: q.low_get(p.s_l0, p.l_wrong)}


@dataclass
class DiagnosticRecord:
    seed: int
    condition: str
    family: str
    terminal: str
    option: int
    goal_lane: int
    corrected_h: bool
    corrected_l: bool
    margin_h_before: float
    margin_l_before: float
    kd_h: float
    kd_l: float
    wr_h: float
    wr_l: float

    @property
    def innocent(self) -> str | None:
        return INNOCENT[self.family]

    @property
    def kd_innocent(self) -> float | None:
        """Damage to the correct-but-not-responsible module, or ``None`` when
        every module was responsible (HL_error)."""
        if self.innocent is None:
            return None
        if self.innocent == "both":
            return 0.5 * (self.kd_h + self.kd_l)
        return self.kd_h if self.innocent == "H" else self.kd_l


def _should_correct(rule: str, u_h: int, u_l: int) -> tuple[bool, bool]:
    if rule == "none":
        return False, False
    if rule == "oracle":
        return bool(u_h), bool(u_l)
    if rule == "h":
        return True, False
    if rule == "l":
        return False, True
    if rule == "hl":
        return True, True
    raise ValueError(f"unknown correction rule {rule!r}")


def apply_diagnostic(
    q: QTables,
    rec: EpisodeRecord,
    *,
    condition: str,
    alpha_diag: float,
) -> DiagnosticRecord | None:
    """Apply one selective diagnostic correction and record what it damaged.

    Returns ``None`` on a successful episode: there is nothing to diagnose.
    """
    if rec.labels is None or rec.terminal == SUCCESS:
        return None
    rule = CONDITIONS[condition][1]
    p = probe_sites(rec)

    h_before, l_before = _h_values(q, p), _l_values(q, p)
    mh_before = correct_margin(h_before, p.h_correct)
    ml_before = correct_margin(l_before, p.l_correct)

    do_h, do_l = _should_correct(rule, rec.labels.u_h, rec.labels.u_l)

    if do_h and alpha_diag > 0.0:
        cur = q.high_get(p.s_h, rec.option)
        q.high_update(p.s_h, rec.option, cur - alpha_diag, 1.0)
    if do_l and alpha_diag > 0.0:
        for site, action in rec.visited_low:
            cur = q.low_get(site, action)
            q.low_update(site, action, cur - alpha_diag, 1.0)

    h_after, l_after = _h_values(q, p), _l_values(q, p)
    mh_after = correct_margin(h_after, p.h_correct)
    ml_after = correct_margin(l_after, p.l_correct)

    return DiagnosticRecord(
        seed=-1,
        condition=condition,
        family=rec.labels.family,
        terminal=rec.terminal,
        option=rec.option,
        goal_lane=rec.goal_lane,
        corrected_h=do_h,
        corrected_l=do_l,
        margin_h_before=mh_before,
        margin_l_before=ml_before,
        # Absolute margin loss: how much correct-vs-wrong separation this one
        # diagnostic update destroyed.
        kd_h=max(0.0, mh_before - mh_after),
        kd_l=max(0.0, ml_before - ml_after),
        # Wrong-choice reinforcement: growth of the wrong item's advantage.
        wr_h=max(0.0, wrong_margin(h_after, p.h_correct, p.h_wrong)
                 - wrong_margin(h_before, p.h_correct, p.h_wrong)),
        wr_l=max(0.0, wrong_margin(l_after, p.l_correct, p.l_wrong)
                 - wrong_margin(l_before, p.l_correct, p.l_wrong)),
    )


@dataclass
class BetaTrainResult:
    seed: int
    condition: str
    reward_mode: str
    rule: str
    checkpoints: list
    success_curve: list
    family_counts: dict
    diagnostics: list = field(default_factory=list)
    q_hash: str = ""
    eval_winnable_fraction: float = 1.0


def train_beta(cfg: dict, *, seed: int, condition: str) -> BetaTrainResult:
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    reward_mode, rule = CONDITIONS[condition]
    env_cfg = cfg["environment"]
    learn = cfg["learning"]
    exp = cfg["experiment"]

    episodes = int(exp["episodes"])
    eval_every = int(exp["eval_every"])
    eval_episodes = int(exp["eval_episodes"])
    horizon = int(env_cfg.get("horizon", HORIZON))
    alpha_diag = float(learn.get("alpha_diag", 0.0))
    decay_episodes = max(1, int(episodes * float(learn["epsilon_decay_fraction"])))

    tape = NoiseTape.from_seed(
        int(seed), episodes=episodes, horizon=horizon,
        p_hazard=float(env_cfg.get("p_hazard", 0.25)),
    )
    q = QTables(n_actions=N_ACTIONS)

    checkpoints: list = []
    success_curve: list = []
    winnable: list = []
    family_counts: dict = {f: 0 for f in INNOCENT}
    diagnostics: list = []

    def record_checkpoint(index: int) -> None:
        rate, _states, win = evaluate(q, cfg, seed=seed, n=eval_episodes)
        checkpoints.append(int(index))
        success_curve.append(float(rate))
        winnable.append(float(win))

    record_checkpoint(0)
    for ep in range(episodes):
        eps = linear_epsilon(
            ep, start=float(learn["epsilon_start"]), end=float(learn["epsilon_end"]),
            decay_episodes=decay_episodes,
        )
        rec = run_episode(
            episode=ep, tape=tape, q=q, epsilon=eps, reward_mode=reward_mode,
            alpha_low=float(learn["alpha_low"]), alpha_high=float(learn["alpha_high"]),
        )
        if rec.labels is not None:
            family_counts[rec.labels.family] += 1
        diag = apply_diagnostic(q, rec, condition=condition, alpha_diag=alpha_diag)
        if diag is not None:
            diag.seed = int(seed)
            diagnostics.append(diag)
        if (ep + 1) % eval_every == 0:
            record_checkpoint(ep + 1)

    return BetaTrainResult(
        seed=int(seed),
        condition=condition,
        reward_mode=reward_mode,
        rule=rule,
        checkpoints=checkpoints,
        success_curve=success_curve,
        family_counts=family_counts,
        diagnostics=diagnostics,
        q_hash=q.deep_hash(),
        eval_winnable_fraction=(
            sum(winnable) / len(winnable) if winnable else 1.0
        ),
    )
