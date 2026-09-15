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
    expected = len(K.OPEN_CELLS) * K.HORIZON * 2 * len(K.PHASE_DOMAIN) \
        * len(K.option_ids()) * 2
    assert len(sol.v) == expected


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
    assert checked > 40_000


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


def test_greedy_following_the_dp_succeeds(sol):
    for z in K.option_ids():
        for kappa in (0, 1):
            for phi in K.PHASE_DOMAIN:
                assert sol.policy_success(kappa=kappa, phi=phi, z=z)


def test_terminal_states_are_not_decision_points(sol):
    assert all(s.t < K.HORIZON for (s, _, _) in sol.v)


# --------------------------------------------------------------------------- #
# The design degeneracy the DP exposed
# --------------------------------------------------------------------------- #

def test_z1_is_unconstrained_and_therefore_dominates(sol):
    """**A recorded design defect, not a desirable property.**

    ``A_{z_1} = A_legal`` (02 §2.4.2) means ``z_1`` carries no obligation at all,
    so the DP's optimal policy *inside* ``z_1`` is simply the unconstrained
    optimum. Consequences, all verified here:

    * ``z*(s)`` is ``z_1`` for **every** ``(kappa, phi)`` — "context-appropriate
      option" is vacuous;
    * ``z_1``'s optimal trajectory under ``kappa=1, phi=2`` is
      ``RIGHT, WAIT, RIGHT, RIGHT, RIGHT`` — it waits out the hazard and
      succeeds, so "rush" is not a rush;
    * property **P1** ("``rush`` succeeds under ``kappa=0`` and *fails* under
      ``kappa=1``") is therefore **false** for the DP-optimal policy.

    This test asserts the *current* behaviour so the defect is visible and
    tracked. It must be replaced — not deleted — when ``z_1`` is given an
    obligation (amendment A39), at which point ``z*`` should become
    context-dependent and P1 should hold.
    """
    assert K.option_actions(0, ControlState(0, 0), State(1, 2, 1, 1, 2)) == \
        K.legal_actions(State(1, 2, 1, 1, 2))

    assert {sol.context_option(k, p) for k in (0, 1) for p in K.PHASE_DOMAIN} == {0}

    def provider(s: State, c: ControlState) -> int:
        return sol.best_action(s, c.z, c.m)

    tr = K.rollout(kappa=1, tape=SemanticTape(phase=2, error_flag=0, cause_rank=0),
                   command_provider=provider, base_option=0)
    assert tr.success
    assert [K.ACTIONS[a] for a in tr.commands()] == \
        ["RIGHT", "WAIT", "RIGHT", "RIGHT", "RIGHT"]


def test_the_context_appropriate_option_is_meant_to_depend_on_context(sol):
    """The design *intent*, asserted so the gap to reality is measurable.

    Under ``kappa=1`` the hazard is fast and the short corridor is unsafe, so
    ``wait_then_cross`` ought to be at least as good as ``rush``. Today it ties
    (both 0.90) precisely because ``rush`` is unconstrained and can imitate it.
    """
    s = State(x=0, y=2, t=0, kappa=1, phi=2)
    assert sol.option_value(s, 0) == pytest.approx(sol.option_value(s, 2))
