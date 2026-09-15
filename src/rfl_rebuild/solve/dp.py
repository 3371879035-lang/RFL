"""Exact reference solution — finite-horizon backward induction over the kernel.

``docs/rebuild/00-INDEX.md`` §7 step 2. This module **reads** the kernel and
**solves** it. It defines nothing about the world: every transition it uses comes
from :func:`rfl_rebuild.env.kernel.step`. That is what keeps it from being a
second simulator (A16, A19).

Two reasons this is exact rather than learned (A16):

1. ``Q*`` is the ruler every arm is scored against. Deriving it from a stochastic
   training run would make the measuring instrument depend on a seed, an
   epsilon schedule and a stopping rule.
2. It answers "what were ``z_2`` and ``z_4`` trained on?" by construction: each
   option is solved inside its own admissible set.

**There is no expectation here.** In the healthy environment the transition is
deterministic given ``(s, a)``: the hazard is a function of ``(t, kappa, phi)`` —
all of which live in ``s`` (A23) — the controller is the identity and the plant is
the identity. So the backup is a plain maximum over a DAG that is stratified by
``t``, which strictly increases.
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass
from typing import Iterator, Mapping

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    Action, ControlState, FaultMask, SemanticTape, State,
)

__all__ = ["ReferenceSolution", "solve_reference", "iter_states"]

_HEALTHY = FaultMask()
_DUMMY_TAPE = SemanticTape(phase=0, error_flag=0, cause_rank=0)


def iter_states() -> Iterator[State]:
    """Every reachable decision state: open cell, ``t in [0, H)``, both lanes, every phase."""
    for x in range(K.N_COLS):
        for y in range(K.N_ROWS):
            if (x, y) not in K.OPEN_CELLS:
                continue
            for t in range(K.HORIZON):
                for kappa in (0, 1):
                    for phi in K.PHASE_DOMAIN:
                        yield State(x=x, y=y, t=t, kappa=kappa, phi=phi)


@dataclass(frozen=True)
class ReferenceSolution:
    """``Q_D*(s, z, m, a)``, ``V*(s, z, m)`` and ``pi_D*(s, z, m)``.

    Option-conditioned and automaton-conditioned: ``(s, z)`` is not a sufficient
    statistic (A22), because ``A_z`` depends on ``m``.
    """

    q: Mapping[tuple[State, int, int], Mapping[Action, float]]
    v: Mapping[tuple[State, int, int], float]
    policy: Mapping[tuple[State, int, int], Action]
    horizon: int = K.HORIZON

    # -- lookups -------------------------------------------------------------

    def q_value(self, s: State, z: int, m: int, a: Action) -> float:
        return self.q[(s, z, m)][a]

    def value(self, s: State, z: int, m: int) -> float:
        return self.v[(s, z, m)]

    def best_action(self, s: State, z: int, m: int) -> Action:
        """``pi_D*(s, z, m)``. Ties broken by the lowest action index, frozen."""
        return self.policy[(s, z, m)]

    def action_values(self, s: State, z: int, m: int) -> Mapping[Action, float]:
        return self.q[(s, z, m)]

    def admissible(self, s: State, z: int, m: int) -> tuple[Action, ...]:
        return K.option_actions(z, ControlState(z=z, m=m), s)

    # -- derived reporting quantities ---------------------------------------

    def option_value(self, s: State, z: int) -> float:
        """``V_z*(s)``: the value of option ``z`` from its initial automaton state."""
        return self.value(s, z, 0)

    def best_option(self, s: State) -> int:
        """``z*(s)`` — **derived, never a generation input** (A28).

        The fault generator draws ``z'`` uniformly instead of consulting this;
        the generator runs before the DP, so consulting it would be circular.
        """
        return max(K.option_ids(), key=lambda z: (self.option_value(s, z), -z))

    def context_option(self, kappa: int, phi: int) -> int:
        """``z*(s)`` at the start state, for reporting a per-context best option."""
        start = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=phi)
        return self.best_option(start)

    def policy_success(self, *, kappa: int, phi: int, z: int) -> bool:
        """Run ``pi_D*(., z, .)`` from the start and report success."""
        def provider(s: State, c: ControlState) -> int:
            return self.best_action(s, c.z, c.m)

        tape = SemanticTape(phase=phi, error_flag=0, cause_rank=0)
        return K.rollout(
            kappa=kappa, tape=tape, command_provider=provider, base_option=z
        ).success

    def optimal_actions(self, s: State, z: int, m: int, tol: float = 1e-12) -> tuple[Action, ...]:
        """``A*(s)`` for this ``(z, m)``: every admissible maximiser, ties included."""
        vals = self.q[(s, z, m)]
        best = max(vals.values())
        return tuple(a for a in sorted(vals) if vals[a] >= best - tol)


def solve_reference(horizon: int = K.HORIZON) -> ReferenceSolution:
    """Backward induction over ``t``, for every option and automaton state.

    Complexity: ``|states| x |Z| x |M| x |A|`` ~ 3900 x 4 x 2 x 5, evaluated
    through the kernel. Runs in seconds and is deterministic.
    """
    if horizon != K.HORIZON:
        raise ValueError(
            "the kernel freezes HORIZON = 12; a different horizon needs an "
            "amendment, not a keyword argument"
        )

    q: dict[tuple[State, int, int], dict[Action, float]] = {}
    v: dict[tuple[State, int, int], float] = {}
    policy: dict[tuple[State, int, int], Action] = {}

    states_by_t: dict[int, list[State]] = {t: [] for t in range(horizon)}
    for s in iter_states():
        states_by_t[s.t].append(s)

    # t = horizon is terminal and is never a decision point, so it needs no
    # entry: every step from t = horizon - 1 ends the episode.

    for t in range(horizon - 1, -1, -1):
        for s in states_by_t[t]:
            for z in K.option_ids():
                for m in (0, 1):
                    ctrl = ControlState(z=z, m=m)
                    admissible = K.option_actions(z, ctrl, s)
                    if not admissible:
                        raise AssertionError(
                            f"empty admissible set at {s} for option {z}, m={m}"
                        )
                    row: dict[Action, float] = {}
                    for a in admissible:
                        res = K.step(
                            s, ctrl, a, tape=_DUMMY_TAPE, mask=_HEALTHY,
                            controller=None,
                        )
                        if res.terminal:
                            row[a] = res.reward
                        else:
                            row[a] = res.reward + v[(res.state, z, res.control.m)]
                    q[(s, z, m)] = row
                    best = max(row, key=lambda a: (row[a], -a))
                    v[(s, z, m)] = row[best]
                    policy[(s, z, m)] = best

    return ReferenceSolution(q=q, v=v, policy=policy, horizon=horizon)


def main() -> int:
    sol = solve_reference()
    print(f"states x options x automaton states: {len(sol.v)}")
    print()
    print("  kappa phi  z*  V*(start)  succeeds")
    for kappa in (0, 1):
        for phi in K.PHASE_DOMAIN:
            z = sol.context_option(kappa, phi)
            start = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=phi)
            print(
                f"  {kappa:^5} {phi:^3} {K.option_name(z):>16} "
                f"{sol.option_value(start, z):+.4f}  "
                f"{sol.policy_success(kappa=kappa, phi=phi, z=z)}"
            )
    print()
    print("  every option, kappa=0, phi=0:")
    start = State(x=0, y=2, t=0, kappa=0, phi=0)
    for z in K.option_ids():
        print(
            f"    {K.option_name(z):>16}  V={sol.option_value(start, z):+.4f}  "
            f"reachable={sol.policy_success(kappa=0, phi=0, z=z)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
