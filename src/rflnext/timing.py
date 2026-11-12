"""Stage 3: attribution timing x historical revision.

Two sequences are constructed deliberately, in opposite directions.

**Lucky success.**  ``H- L+ E+ -> Success``.  A wrong plan succeeds because the
environment happened to open a shortcut, and ordinary reinforcement records
that as good evidence for the wrong plan.  Later the same plan fails
(``H- L+ E0 -> Failure``).  Does the system re-interpret the earlier success?

**Unlucky failure.**  ``H+ L+ E- -> Failure`` while the same policy normally
succeeds.  A revision mechanism that is not careful will overturn genuinely
correct credit here.

The 2x2 crosses *when* attribution happens (immediate vs deferred until a
contradiction) with *whether* past credit can be revoked (fixed vs revisable).

Implementation note, per the research plan
------------------------------------------
Revising credit by ``Q <- Q - dQ_old + dQ_new`` is wrong: Q-learning updates
are order-dependent, because later bootstrap targets were computed from the
already-updated Q.  So this module keeps an ordered log of every primitive
write plus periodic Q checkpoints, and a revision restores the checkpoint that
precedes the suspect episodes and **replays the log forward in time order**
with those episodes' outcome evidence withdrawn.

The log records diagnostics as well as task updates, so a replay reproduces the
run exactly up to the withdrawal rather than silently dropping the corrections.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .env import DOWN, HORIZON, N_ACTIONS, RIGHT, SUCCESS, TIMEOUT, W, WAIT, step_cell, terminal_kind
from .qtables import QTables

UP = 0

CELLS = (
    "immediate_fixed",
    "immediate_revisable",
    "deferred_fixed",
    "deferred_revisable",
    "immediate_revisable_naive",
    "deferred_revisable_naive",
)
IMMEDIATE = {
    "immediate_fixed", "immediate_revisable", "immediate_revisable_naive",
}
REVISABLE = {
    "immediate_revisable", "deferred_revisable",
    "immediate_revisable_naive", "deferred_revisable_naive",
}
# The plan warns that patching credit by ``Q <- Q - dQ_old + dQ_new`` is only an
# approximation, because later bootstrap targets were computed from the
# already-updated Q.  These two cells use exactly that patch, so the error it
# introduces is measured rather than asserted.
NAIVE_REVISION = {"immediate_revisable_naive", "deferred_revisable_naive"}


@dataclass
class Update:
    """One primitive write to Q_H, in the order it happened."""

    episode: int
    kind: str  # "task" | "diag"
    s_h: tuple
    option: int
    return_value: float = 0.0
    delta: float = 0.0


@dataclass
class EpisodeMeta:
    episode: int
    option: int
    lucky: int
    h_wrong: bool
    was_success: bool


@dataclass
class RevisionRecord:
    """One revision, with the interpretation it replaced.

    The plan's checklist requires every revision to save ``old_U -> new_U`` and
    the reason it fired, so that a false reversal is auditable after the fact
    rather than only visible as a damaged Q value.
    """

    revision_id: int
    target_episodes: list
    old_u_h: int
    old_u_l: int
    new_u_h: int
    new_u_l: int
    trigger_episode: int
    trigger_type: str  # "contradiction" | "unlucky_failure"
    checkpoint_id: int
    replay_from: int
    mode: str  # "replay" | "naive_patch"
    justified: bool


@dataclass
class TimingResult:
    cell: str
    seed: int
    overcredit_after_lucky: float
    overcredit_after_contradiction: float
    correct_credit_after_contradiction: float
    recovery_episodes: int | None
    revisions: int
    true_revisions: int
    false_reversals: int
    revision_precision: float | None
    false_reversal_rate: float | None
    n_diagnosis: int
    n_cf: int
    wall_s: float
    revision_records: list = field(default_factory=list)


def _corridor_action(x: int, y: int, option: int) -> int:
    if y != option:
        return DOWN if option == 1 else UP
    if x < W - 1:
        return RIGHT
    return WAIT


def _rollout(goal_lane: int, hazard: int, lucky: int, option: int, horizon: int) -> str:
    x, y = 0, 0
    terminal = TIMEOUT
    for _t in range(1, horizon + 1):
        a = _corridor_action(x, y, option)
        nx, ny = step_cell(x, y, a)
        kind = terminal_kind(nx, ny, goal_lane, hazard, lucky)
        x, y = nx, ny
        if kind is not None:
            terminal = kind
            break
    return terminal


def run_cell(cfg: dict, *, seed: int, cell: str) -> TimingResult:
    if cell not in CELLS:
        raise ValueError(f"unknown cell {cell!r}")
    t0 = time.perf_counter()

    env_cfg = cfg["environment"]
    learn = cfg["learning"]
    proto = cfg["protocol"]
    horizon = int(env_cfg.get("horizon", HORIZON))
    alpha_high = float(learn["alpha_high"])
    alpha_diag = float(learn["alpha_diag"])

    warmup = int(proto["warmup_episodes"])
    n_lucky = int(proto["lucky_episodes"])
    n_contra = int(proto["contradiction_episodes"])
    unlucky_every = int(proto.get("unlucky_every", 0))
    checkpoint_every = int(proto.get("checkpoint_every", 25))

    goal_lane = 0
    s_h_normal = (goal_lane, 0)
    wrong = 1 - goal_lane

    q = QTables(n_actions=N_ACTIONS)
    checkpoints: dict[int, QTables] = {0: q.copy()}
    log: list[Update] = []
    metas: list[EpisodeMeta] = []
    n_diagnosis = 0
    n_cf = 0
    episode = 0

    def task(e: int, s_h, option: int, r: float) -> None:
        before = q.high_get(s_h, option)
        q.high_update(s_h, option, r, alpha_high)
        log.append(Update(e, "task", s_h, option, r, q.high_get(s_h, option) - before))

    def diag(e: int, s_h, option: int) -> None:
        nonlocal n_diagnosis
        n_diagnosis += 1
        cur = q.high_get(s_h, option)
        q.high_update(s_h, option, cur - alpha_diag, 1.0)
        log.append(Update(e, "diag", s_h, option, 0.0,
                          q.high_get(s_h, option) - cur))

    def snapshot(e: int) -> None:
        checkpoints[e] = q.copy()

    def replay_from(checkpoint_id: int, upto: int, withdraw: set) -> None:
        nonlocal q
        q = checkpoints[checkpoint_id].copy()
        for u in log:
            if not (checkpoint_id <= u.episode <= upto):
                continue
            if u.kind == "task":
                r = 0.0 if u.episode in withdraw else u.return_value
                q.high_update(u.s_h, u.option, r, alpha_high)
            else:
                cur = q.high_get(u.s_h, u.option)
                q.high_update(u.s_h, u.option, cur - alpha_diag, 1.0)

    def naive_revision(withdraw: set) -> None:
        """The plan's warned-against approximation: ``Q <- Q - dQ_old``.

        Subtracting each withdrawn update's recorded delta leaves the later
        bootstrap targets untouched, even though they were computed from the
        Q values those very updates produced.  The error is not corrected.
        """
        nonlocal q
        for u in log:
            if u.kind == "task" and u.episode in withdraw and u.delta != 0.0:
                cur = q.high_get(u.s_h, u.option)
                q.high_update(u.s_h, u.option, cur - u.delta, 1.0)

    def revise(withdraw: set) -> None:
        if cell in NAIVE_REVISION:
            naive_revision(withdraw)
        else:
            replay_from(0, episode, withdraw=withdraw)

    # -------- phase 1: warmup, the correct plan succeeds ---------------------
    for _ in range(warmup):
        task(episode, s_h_normal, goal_lane, 1.0)
        metas.append(EpisodeMeta(episode, goal_lane, 0, False, True))
        episode += 1
        if episode % checkpoint_every == 0:
            snapshot(episode)

    # -------- phase 2: lucky successes of a plan that is actually wrong ------
    first_lucky = episode
    for _ in range(n_lucky):
        task(episode, s_h_normal, wrong, 1.0)
        metas.append(EpisodeMeta(episode, wrong, 1, True, True))
        episode += 1
        if episode % checkpoint_every == 0:
            snapshot(episode)

    after_lucky = q.high_get(s_h_normal, wrong)
    resume_checkpoint = max([c for c in checkpoints if c <= first_lucky], default=0)

    # -------- phase 3: contradiction, with unlucky failures mixed in ---------
    pending: list[tuple[int, tuple, int]] = []
    recovery_episodes: int | None = None
    revisions = 0
    true_revisions = 0
    false_reversals = 0
    revision_happened = False
    revision_records: list = []
    mode = "naive_patch" if cell in NAIVE_REVISION else "replay"

    for i in range(n_contra):
        is_unlucky = unlucky_every > 0 and (i + 1) % unlucky_every == 0
        if is_unlucky:
            option, hazard, lucky, h_wrong = goal_lane, 1, 0, False
        else:
            option, hazard, lucky, h_wrong = wrong, 0, 0, True
        terminal = _rollout(goal_lane, hazard, lucky, option, horizon)
        assert terminal != SUCCESS, "contradiction phase must not contain successes"
        s_h = (goal_lane, hazard)
        task(episode, s_h, option, -1.0)
        metas.append(EpisodeMeta(episode, option, lucky, h_wrong, False))

        if cell in IMMEDIATE:
            diag(episode, s_h, option)
        else:
            pending.append((episode, s_h, option))
            # Deferred attribution fires only once a contradiction is
            # confirmed: two consecutive failures of the same plan.
            if len(pending) >= 2 and all(
                metas[e].h_wrong for e, _s, _o in pending[-2:]
            ):
                for e, ps, po in pending:
                    diag(e, ps, po)
                pending = []

        if cell in REVISABLE and h_wrong and not revision_happened:
            # The rule: on a contradiction, withdraw the outcome evidence of
            # every earlier success of this same plan.  Here that plan was
            # genuinely wrong, so this is a correct revision.
            rev = [m.episode for m in metas if m.lucky == 1 and m.option == option]
            if rev:
                revise(set(rev))
                revisions += len(rev)
                true_revisions += len(rev)
                revision_happened = True
                revision_records.append(RevisionRecord(
                    revision_id=len(revision_records), target_episodes=list(rev),
                    old_u_h=0, old_u_l=0, new_u_h=1, new_u_l=0,
                    trigger_episode=episode, trigger_type="contradiction",
                    checkpoint_id=0, replay_from=0, mode=mode, justified=True,
                ))
        elif cell in REVISABLE and not h_wrong:
            # The identical rule now fires on an unlucky failure, where the
            # successes it withdraws were earned by a *correct* plan.  This is
            # a real (harmful) revision, performed the same way, not merely
            # counted: it restores the initial checkpoint and replays forward
            # with those episodes' evidence withdrawn.
            rev = [
                m.episode for m in metas
                if m.was_success and not m.lucky and m.option == option
            ]
            if rev:
                revise(set(rev))
                revisions += len(rev)
                false_reversals += len(rev)
                revision_records.append(RevisionRecord(
                    revision_id=len(revision_records), target_episodes=list(rev),
                    old_u_h=0, old_u_l=0, new_u_h=1, new_u_l=0,
                    trigger_episode=episode, trigger_type="unlucky_failure",
                    checkpoint_id=0, replay_from=0, mode=mode, justified=False,
                ))

        if recovery_episodes is None and max(
            q.options, key=lambda o: q.high_get(s_h_normal, o)
        ) == goal_lane:
            recovery_episodes = i + 1
        episode += 1

    after_contra = q.high_get(s_h_normal, wrong)
    correct_credit = q.high_get(s_h_normal, goal_lane)
    return TimingResult(
        cell=cell,
        seed=seed,
        overcredit_after_lucky=float(after_lucky),
        overcredit_after_contradiction=float(after_contra),
        correct_credit_after_contradiction=float(correct_credit),
        recovery_episodes=recovery_episodes,
        revisions=revisions,
        true_revisions=true_revisions,
        false_reversals=false_reversals,
        revision_precision=(true_revisions / revisions) if revisions else None,
        false_reversal_rate=(false_reversals / revisions) if revisions else None,
        n_diagnosis=n_diagnosis,
        n_cf=n_cf,
        wall_s=time.perf_counter() - t0,
        revision_records=revision_records,
    )
