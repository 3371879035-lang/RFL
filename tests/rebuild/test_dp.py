"""Exact reference solution tests.

Two jobs:

1. lock the DP's *correctness* — that it agrees with the kernel it reads, is
   deterministic, and handles ties and terminal states as specified;
2. record the *design degeneracy* the DP immediately exposed, so it cannot be
   forgotten. See :func:`test_z1_is_unconstrained_and_therefore_dominates`.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import ControlState, SemanticTape, State  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402


@pytest.fixture(scope="module")
def sol():
    return solve_reference()


# --------------------------------------------------------------------------- #
# Correctness
# --------------------------------------------------------------------------- #

def test_solution_covers_every_state_option_and_automaton_state(sol):
    # GOAL is excluded: arriving there is terminal, never a decision point (A39).
    decision_cells = len(K.OPEN_CELLS) - 1
    expected = decision_cells * K.HORIZON * 2 * len(K.PHASE_DOMAIN) \
        * len(K.option_ids()) * 2
    assert len(sol.v) == expected == 13_824


def test_dp_agrees_with_the_kernel_it_reads(sol):
    """The Bellman identity, checked directly against ``kernel.step``.

    This is the test that would catch the DP reimplementing the world instead of
    reading it: if the DP's own transition differed from the kernel's, the
    identity would fail.
    """
    from rfl_rebuild.solve.dp import _DUMMY_TAPE, _HEALTHY

    checked = 0
    for (s, z, m), row in sol.q.items():
        for a, value in row.items():
            res = K.step(s, ControlState(z=z, m=m), a,
                         tape=_DUMMY_TAPE, mask=_HEALTHY)
            expected = res.reward if res.terminal else (
                res.reward + sol.value(res.state, z, res.control.m)
            )
            assert value == pytest.approx(expected)
            checked += 1
    assert checked > 35_000


def test_policy_is_admissible_everywhere(sol):
    for (s, z, m), a in sol.policy.items():
        assert a in K.option_actions(z, ControlState(z=z, m=m), s)


def test_value_is_the_max_of_q(sol):
    for key, row in sol.q.items():
        assert sol.v[key] == pytest.approx(max(row.values()))


def test_solution_is_deterministic():
    a = solve_reference()
    b = solve_reference()
    assert a.policy == b.policy
    assert a.v == b.v


def test_the_best_option_always_succeeds_and_rush_does_not(sol):
    """A39 changed this test's premise, deliberately.

    Before A39 every option succeeded everywhere, because ``rush`` was the
    unconstrained optimum wearing a name. A rush that always succeeds is not a
    rush. What holds now:

    * the **best** option in each context always reaches the goal;
    * ``rush`` reaches it **iff** the short corridor is clear at ``t=2``.
    """
    for kappa in (0, 1):
        for phi in K.PHASE_DOMAIN:
            z = sol.context_option(kappa, phi)
            assert sol.policy_success(kappa=kappa, phi=phi, z=z)
            assert sol.policy_success(kappa=kappa, phi=phi, z=0) == (
                not K.hazard_at(2, kappa, phi)
            )


def test_terminal_states_are_not_decision_points(sol):
    assert all(s.t < K.HORIZON for (s, _, _) in sol.v)


# --------------------------------------------------------------------------- #
# The design degeneracy the DP exposed
# --------------------------------------------------------------------------- #

def test_z1_is_static_shortest_path_descent(sol):
    """A39: ``rush`` must strictly decrease the static distance to the goal.

    Replaces ``test_z1_is_unconstrained_and_therefore_dominates``. That test
    recorded a defect; this one asserts the correction. ``d_G`` is static — it
    ignores the hazard, ``kappa``, ``phi`` and ``t`` and never consults the DP —
    so the constraint defines a *behaviour style* rather than encoding the
    answer. If it read the current situation it would be writing the correct
    action into the option.
    """
    d = K.STATIC_DISTANCE_TO_GOAL

    # d_G is the static open-cell distance, hazard-blind.
    assert d[K.START] == 4 and d[K.GOAL] == 0
    assert d[(1, 2)] == 3 and d[(2, 1)] == 3 and d[(2, 4)] == 4

    # At the start, the only admissible action is the one that descends.
    s = K.State(0, 2, 0, 0, 0)
    assert [K.ACTIONS[a] for a in K.option_actions(0, K.ControlState(0, 0), s)] \
        == ["RIGHT"]

    # At (1,2) neither WAIT nor a detour is available.
    s = K.State(1, 2, 1, 1, 2)
    acts = [K.ACTIONS[a] for a in K.option_actions(0, K.ControlState(0, 0), s)]
    assert "WAIT" not in acts
    assert acts == ["RIGHT"]

    # Everywhere, every admissible action strictly decreases d_G.
    for cell in K.OPEN_CELLS - {K.GOAL}:
        for kappa in (0, 1):
            for phi in K.PHASE_DOMAIN:
                for t in range(K.HORIZON):
                    st = K.State(cell[0], cell[1], t, kappa, phi)
                    acts = K.option_actions(0, K.ControlState(0, 0), st)
                    assert acts, f"empty A_z1 at {cell}"
                    for a in acts:
                        nxt = K._enter(a, st)
                        assert d[nxt] == d[cell] - 1


def test_rush_is_actually_a_rush_P1a_P1b(sol):
    """P1a/P1b: the outcome of ``rush`` is decided by ``hazard_at(2, kappa, phi)``.

    The old P1 keyed on ``kappa`` alone. Once ``phi`` became part of the state
    (A23) that was no longer the right predicate: what decides whether the short
    corridor is safe at ``t=2`` is the full context.
    """
    from rfl_rebuild.env.kernel import SemanticTape

    for kappa in (0, 1):
        for phi in K.PHASE_DOMAIN:
            s0 = K.State(0, 2, 0, kappa, phi)
            safe = not K.hazard_at(2, kappa, phi)

            def provider(s, c, _sol=sol):
                return _sol.best_action(s, c.z, c.m)

            tr = K.rollout(
                kappa=kappa,
                tape=SemanticTape(phase=phi, error_flag=0, cause_rank=0),
                command_provider=provider, base_option=0,
            )
            if safe:
                # P1a: four steps, no collision.
                assert tr.success, f"kappa={kappa} phi={phi} should succeed"
                assert len(tr.steps) == 4
            else:
                # P1b: collides at the contested cell on step 2.
                assert tr.outcome == K.Outcome.COLLISION
                assert len(tr.steps) == 2
                assert tr.visited()[-1] == K.CONTESTED


def test_best_option_depends_on_full_context(sol):
    """P1c: the context-appropriate option is not a constant.

    This is the assertion that closes the A39 degeneracy. It deliberately does
    **not** require a particular winner in the hazardous contexts — whether
    ``wait_then_cross``, ``detour_upper`` or a tie wins is for the DP to say, not
    for the environment to arrange.
    """
    zs = {
        sol.context_option(kappa, phi)
        for kappa in (0, 1)
        for phi in K.PHASE_DOMAIN
    }
    assert len(zs) >= 2, f"z* is constant at {zs} — the degeneracy is back"

    # And specifically: where the short corridor is unsafe, rushing must lose.
    for kappa in (0, 1):
        for phi in K.PHASE_DOMAIN:
            if not K.hazard_at(2, kappa, phi):
                continue
            s0 = K.State(0, 2, 0, kappa, phi)
            best = max(sol.option_value(s0, z) for z in K.option_ids())
            assert sol.option_value(s0, 0) < best, (
                f"rush still optimal at kappa={kappa} phi={phi}"
            )
