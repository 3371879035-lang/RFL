r"""B2-2 — the real environment's endogeneity, and FutureUtility's estimators.

$$\boxed{Y^{\text{future}} = Y^{\text{future}}(W + \Delta W)}$$

Two families of gate, both synthetic and both seedless:

* **endogeneity** — the production environment must read the state it is handed, through every
  persistent channel the rollout consults ($Q_D^L$, $P_D^L$, $C_X^L$, $C_P^L$), and must move the
  future when one of them is written. A version that used the reference policy, a default provider
  or a fresh state would produce a plausible future and be wrong in the only way that matters;
* **FutureUtility** — the maintained-recovery definition with $K=3$, right-censoring at $T_{\max}$,
  and both estimators integrated over the **real episode indices** rather than array positions.

No design number is chosen here: $T_{\max}$, the grid, $V_{\text{pre}}$ and $N_{\text{eval}}$ are
arguments, and $N_{\text{train}}$ does not exist yet.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2 import assert_modules_are_closed  # noqa: E402
from rfl_rebuild.b2.environment import (  # noqa: E402
    KernelLearnerEnvironment, audited_modules,
)
from rfl_rebuild.b2.utility import (  # noqa: E402
    K_RECOVERY, FutureUtility, deficit_auc, recovery_time,
)
from rfl_rebuild.env.kernel import SemanticTape  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    CONTROLLER, PROCESS, Q, QAddress, Edit, LearnerPersistentState,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

SOL = solve_reference()
REFERENCE = reference_view_from(SOL)


def environment(kappa: int = 0, base_option: int = 1) -> KernelLearnerEnvironment:
    return KernelLearnerEnvironment(kappa=kappa, phi=0,
                                    tape=SemanticTape(phase=0, error_flag=0, cause_rank=0),
                                    base_option=base_option, q_reference=REFERENCE)


def baseline() -> tuple:
    return environment().future_records(LearnerPersistentState())


# --------------------------------------------------------------------------- #
# 1. endogeneity: the future is a function of the passed state
# --------------------------------------------------------------------------- #

def test_1_the_rollout_reads_the_state_it_is_handed():
    r"""An identical copy of the same state gives an identical future, and a state that differs
    gives a different one — so the environment is neither random nor state-blind."""
    env = environment()
    base = env.future_records(LearnerPersistentState())
    assert env.future_records(LearnerPersistentState()) == base
    assert len(base[0]) > 0


def test_2_each_persistent_channel_moves_the_future():
    r"""$$\boxed{\text{no channel may be bypassed by a reference shortcut}}$$

    One channel at a time: write it, and the future must move. Each is the channel the kernel
    actually consults, wired from the snapshot of the state that was passed in.
    """
    env = environment()
    base = env.future_records(LearnerPersistentState())

    # C_P^L: a process commit that is no longer the identity
    process_state = LearnerPersistentState()
    process_state.apply_transaction([Edit(PROCESS, 1, 2)])
    assert env.future_records(process_state) != base, "the C_P^L channel is not read"

    # C_X^L: a controller override at the site the episode actually visits, with an action the
    # option in force admits -- the kernel's own A_z contract check would otherwise refuse it
    # (A75 62.3), which is a different (and correct) refusal than the one this gate is about.
    from rfl_rebuild.env.kernel import START, ControllerSite, State, option_actions

    trace = _trace()
    first = trace.steps[0]
    pre = State(x=START[0], y=START[1], t=0, kappa=0, phi=0)
    allowed = [a for a in option_actions(trace.option_in_force, trace.control, pre)
               if a != first.a_cmd]
    assert allowed, "the scene exposes no admissible alternative command"
    controller_state = LearnerPersistentState()
    controller_state.apply_transaction(
        [Edit(CONTROLLER, ControllerSite(state=pre, cmd=first.a_cmd), allowed[-1])])
    assert env.future_records(controller_state) != base, "the C_X^L channel is not read"

    # Q_D^L: an override of a decision context the episode reaches. The claim is existential on
    # purpose: overriding the choice at *some* contexts leaves the trajectory unchanged (the
    # alternative is equivalent for the remainder), so "the channel is read" means there is at
    # least one visited context whose choice the future depends on -- which is what endogeneity
    # requires, and all it requires.
    from rfl_rebuild.env.kernel import START, State

    previous = State(x=START[0], y=START[1], t=0, kappa=0, phi=0)
    moved = []
    for step in trace.steps:
        context = (previous, trace.option_in_force, trace.control.m)
        if context in REFERENCE.rows:
            q_state = LearnerPersistentState()
            q_state.apply_transaction(
                [Edit(Q, QAddress(state=previous, z=trace.option_in_force,
                                  m=trace.control.m, a=step.a_cmd), -1e6)],
                q_reference=REFERENCE)
            moved.append(env.future_records(q_state) != base)
        previous = step.state
    assert any(moved), f"no visited decision context controls the future from C_Q: {moved}"
    assert not all(moved), (
        "every context moved the future, which would suggest the fixture is measuring noise "
        "rather than a channel: at some contexts the alternative is equivalent")


def _trace():
    from rfl_rebuild.env.kernel import rollout
    from rfl_rebuild.learner.store import LearnerPersistentState as S

    snap = S().snapshot()
    return rollout(kappa=0, tape=SemanticTape(phase=0, error_flag=0, cause_rank=0),
                   command_provider=snap.decision_provider(snap.q_decision_provider(REFERENCE)),
                   base_option=1, controller=snap.controller_mapping(),
                   learner_process_commit=snap.process_commit_provider())


def test_3_the_environment_refuses_what_it_cannot_answer():
    r"""No reference view, no Q read path: the healthy referent *is* that view, so guessing one
    would answer a different question. A non-state is refused for the same reason."""
    for bad in (None,):
        with pytest.raises(ProtocolError) as ei:
            KernelLearnerEnvironment(kappa=0, phi=0,
                                     tape=SemanticTape(phase=0, error_flag=0, cause_rank=0),
                                     base_option=1, q_reference=bad)
        assert "reference view" in str(ei.value)
    for bad in (None, {}, 1, "state"):
        with pytest.raises(ProtocolError) as ei:
            environment().future_records(bad)
        assert "learner state" in str(ei.value)


def test_4_the_environment_is_in_the_audited_production_chain():
    r"""The provenance gap B2-2a left open closes here: the production environment is not merely a
    nominal `LearnerEnvironment`, it is a module the same AST/import/dependency audit covers."""
    modules = audited_modules(ROOT / "src")
    assert all(p.exists() for p in modules), modules
    assert any(p.name == "environment.py" for p in modules)
    assert_modules_are_closed(modules)


# --------------------------------------------------------------------------- #
# 2. FutureUtility: maintained recovery, and integration over real indices
# --------------------------------------------------------------------------- #

def test_5_recovery_needs_k_consecutive_checkpoints():
    r"""The frozen rule is a **window**: $\tau$ is the first $t$ whose next $K$ checkpoints are all
    at or above the threshold. One or two crossings are not a recovery, and the very first window
    that qualifies is the answer."""
    episodes = (0, 5, 10, 15, 20, 25)
    assert K_RECOVERY == 3
    # only isolated crossings: no window of three qualifies
    isolated = [0.96, 0.90, 0.99, 0.90, 0.99, 0.90]
    assert recovery_time(isolated, episodes, pre_level=1.0, t_max=25) is None
    # the first qualifying window starts at index 1 (0.96, 0.99, 0.99), so tau is episode 5
    assert recovery_time([0.90, 0.96, 0.99, 0.99, 0.90, 0.90], episodes, pre_level=1.0,
                         t_max=25) == 5
    # a full window from the very first checkpoint
    assert recovery_time([0.96, 0.99, 0.99, 0.99, 0.99, 0.99], episodes, pre_level=1.0,
                         t_max=25) == 0


def test_6_a_dip_inside_a_window_voids_that_window():
    r"""$$\tau = \inf\{t : V_{t'} \ge 0.95 V_{\text{pre}}\ \forall t' \in [t, t+K-1]\}$$

    A dip **inside** a candidate window voids that window, so the recovery is the later qualifying
    run. A dip *after* a complete window does not retroactively void it — the rule is a $K$-window,
    not "maintained forever after", and this gate pins both halves rather than the stronger
    reading I first wrote into it.
    """
    episodes = (0, 5, 10, 15, 20, 25, 30)
    dipped_inside = [0.96, 0.90, 0.99, 0.99, 0.99, 0.99, 0.99]
    assert recovery_time(dipped_inside, episodes, pre_level=1.0, t_max=30) == 10
    dipped_inside[0:2] = [0.90, 0.90]
    assert recovery_time(dipped_inside, episodes, pre_level=1.0, t_max=30) == 10
    # a complete window is a recovery even if the curve later falls back
    later_dip = [0.96, 0.99, 0.99, 0.90, 0.97, 0.98, 0.99]
    assert recovery_time(later_dip, episodes, pre_level=1.0, t_max=30) == 0


def test_7_never_recovered_is_right_censored_at_t_max():
    episodes = (0, 7, 14)
    values = [0.5, 0.6, 0.94]
    utility = FutureUtility.from_curve(values, episodes, pre_level=1.0, t_max=40)
    assert utility.tau is None and utility.recovered is False
    assert utility.rmst == 40 == utility.t_max


def test_8_both_estimators_integrate_over_real_episode_indices():
    r"""$$\mathrm{DeficitAUC} = \sum_i (V_{\text{pre}} - V_{t_i})^{+}\,\Delta t_i$$

    A non-uniform grid is the point: the same values on a unit grid must give a different answer,
    and RMST must be an episode index rather than an array position.
    """
    episodes = (0, 5, 15, 16)                     # deliberately non-uniform
    values = [0.90, 0.90, 0.99, 0.99]
    # deficits 0.10 at t=0 (spans 5) and 0.10 at t=5 (spans 10), then nothing
    # deficits: 0.10 over [0,5], 0.10 over [5,15], and 0.01 over [15,16] because 0.99 < V_pre
    assert deficit_auc(values, episodes, pre_level=1.0) == pytest.approx(0.10 * 5 + 0.10 * 10 + 0.01)
    # the same values on a unit grid: 0.10 + 0.10 + 0.01 (the 0.99 point is below V_pre too)
    assert deficit_auc(values, (0, 1, 2, 3), pre_level=1.0) == pytest.approx(0.21)
    assert recovery_time(values, episodes, pre_level=1.0, t_max=16) is None   # only two at 0.99
    # tau must be the EPISODE index of the window's start, not its array position: the window here
    # begins at position 1, which is episode 5
    values_recovered = [0.90, 0.99, 0.99, 0.99]
    assert recovery_time(values_recovered, episodes, pre_level=1.0, t_max=16) == 5
    # an observation at episode 15 is not one unit after episode 5
    utility = FutureUtility.from_curve([0.5, 0.5], (0, 20), pre_level=1.0, t_max=20)
    assert utility.deficit_auc == pytest.approx(0.5 * 20)


def test_9_the_grid_contract_is_enforced():
    r"""A curve without real, strictly increasing episode indices is refused rather than assumed to
    be uniformly spaced — the assumption that would rescale every deficit unnoticed."""
    with pytest.raises(ProtocolError) as ei:
        deficit_auc((0.9, 0.9), (0, 0), pre_level=1.0)
    assert "strictly increasing" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        deficit_auc((0.9,), (0, 1), pre_level=1.0)
    assert "episode indices" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        deficit_auc((0.9, 0.9), (0, 1.5), pre_level=1.0)
    assert "not an integer" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        recovery_time((0.9, 0.9), (0, 1), pre_level=1.0, t_max=True)
    assert "not an integer" in str(ei.value)
    with pytest.raises(ProtocolError):
        deficit_auc((), (), pre_level=1.0)
