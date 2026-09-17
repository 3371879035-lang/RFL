"""A62 — the frozen scene DGP, as a SINGLE probability definition.

The point of this module is that there is exactly one place where the measure over
worlds is written down. If scenes are sampled by one piece of code and the
inference prior ``w_l`` is built by another, the two can drift apart silently, and
nothing downstream would notice until the metrics stopped making sense. So:

    SceneDGP.log_prob(world)   -> log P_DGP(world)
    SceneDGP.sample(rng)       -> a world drawn from that same measure
    support weights            w_l  proportional to  exp(log_prob(l))

Frozen constants (see `15-SCENE-DGP.md`):

    kappa           ~ Uniform(K)
    tape            already-frozen real measure, P(error_flag = 1) = 0.4
    cause_rank      ~ Uniform(60), which is the tape's uniform-draw key (A25)
    z^proposal      ~ Uniform(Z)
    Z_i^pres        ~ Bernoulli(0.2) on causes whose canonical domain is
                      non-empty in this context, and 0 otherwise
    fault parameter ~ Uniform over that cause's canonical domain, once active

0.2 is not a tuning knob. It is what the existing "causes are sparse"
specification implies: E[|Z|] = 1 and P(|Z| <= 1) ~ 0.737 when all five causes
are available.

The domain oracle is injected, so this module depends on no environment script
while still being the only writer of the measure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

N_CAUSES = 5
P_ERROR_FLAG = 0.4
P_CAUSE = 0.2
N_CAUSE_RANK = 60

# log values, computed once so the sampler and log_prob cannot disagree
_L_P_ERR = math.log(P_ERROR_FLAG)
_L_1M_ERR = math.log(1.0 - P_ERROR_FLAG)
_L_P_CAUSE = math.log(P_CAUSE)
_L_1M_CAUSE = math.log(1.0 - P_CAUSE)


@dataclass(frozen=True)
class SceneContext:
    """What is drawn before the fault pattern: kappa, tape, z^proposal."""

    kappa: int
    phase: int
    error_flag: int
    cause_rank: int
    base_option: int

    @property
    def is_valid(self) -> bool:
        return 0 <= self.error_flag <= 1 and 0 <= self.cause_rank < N_CAUSE_RANK


class SceneDGP:
    """``log_prob`` and ``sample`` from one measure.

    ``domains(ctx) -> tuple of canonical domains per cause`` is injected; entry
    ``i`` is empty exactly when cause ``i`` has no admissible parameter in this
    context, which forces ``Z_i = 0``.
    """

    p_error_flag = P_ERROR_FLAG
    p_cause = P_CAUSE

    def __init__(self, *, kappas: Sequence[int], options: Sequence[int],
                 tapes: Sequence, domains: Callable, n_cause_rank: int = N_CAUSE_RANK):
        self.kappas = tuple(kappas)
        self.options = tuple(options)
        self.tapes = tuple(tapes)
        self._domains = domains
        self.n_cause_rank = n_cause_rank
        if not (self.kappas and self.options and self.tapes):
            raise ValueError("DGP needs non-empty kappa, option and tape supports")

    # ---- context level --------------------------------------------------- #
    def context_log_prob(self, ctx: SceneContext) -> float:
        if not ctx.is_valid:
            return -math.inf
        if ctx.kappa not in self.kappas or ctx.base_option not in self.options:
            return -math.inf
        if not any(t.phase == ctx.phase for t in self.tapes):
            return -math.inf
        lp = 0.0
        lp -= math.log(len(self.kappas))
        lp -= math.log(len(self.options))
        lp += _L_P_ERR if ctx.error_flag == 1 else _L_1M_ERR
        lp -= math.log(self.n_cause_rank)
        return lp

    # ---- world level ----------------------------------------------------- #
    def world_log_prob(self, ctx: SceneContext, Z: Sequence[int],
                       param_index: Sequence[int]) -> float:
        """``log P(Z, params | ctx)`` — conditional part of the measure."""
        if len(Z) != N_CAUSES or ctx.is_valid is False:
            return -math.inf
        dm = self._domains(ctx)
        lp = 0.0
        for i in range(N_CAUSES):
            d = dm[i]
            if not d:
                if Z[i] != 0:
                    return -math.inf          # cannot be present with no domain
                continue
            if Z[i] == 0:
                lp += _L_1M_CAUSE
            else:
                lp += _L_P_CAUSE
                if not (0 <= param_index[i] < len(d)):
                    return -math.inf
                lp -= math.log(len(d))        # uniform within the canonical domain
        return lp

    def log_prob(self, ctx: SceneContext, Z: Sequence[int],
                 param_index: Sequence[int]) -> float:
        return self.context_log_prob(ctx) + self.world_log_prob(ctx, Z, param_index)

    # ---- sampling, from the same measure --------------------------------- #
    def sample_context(self, rng) -> SceneContext:
        return SceneContext(kappa=rng.choice(self.kappas),
                            phase=rng.choice(self.tapes).phase,
                            error_flag=1 if rng.random() < self.p_error_flag else 0,
                            cause_rank=rng.randrange(self.n_cause_rank),
                            base_option=rng.choice(self.options))

    def sample_world(self, rng, ctx: SceneContext):
        dm = self._domains(ctx)
        Z, params = [], []
        for i in range(N_CAUSES):
            d = dm[i]
            if not d:
                Z.append(0)
                params.append(-1)
            elif rng.random() < self.p_cause:
                Z.append(1)
                params.append(rng.randrange(len(d)))
            else:
                Z.append(0)
                params.append(-1)
        return tuple(Z), tuple(params)

    # ---- the enumerable slice used by the exact consistency test --------- #
    def slice_total(self, ctx: SceneContext) -> float:
        """``sum over all (Z, params) of P(Z, params | ctx)``.

        Must be 1: this is the exact check that the sampler and the prior use one
        measure. Only usable on a context small enough to enumerate.
        """
        dm = self._domains(ctx)
        tot = 0.0
        for bits in range(1 << N_CAUSES):
            Z = [(bits >> i) & 1 for i in range(N_CAUSES)]
            if any(Z[i] == 1 and not dm[i] for i in range(N_CAUSES)):
                continue
            # sum over parameter assignments
            combos = 1
            for i in range(N_CAUSES):
                if Z[i] == 1:
                    combos *= len(dm[i])
            tot += math.exp(self.world_log_prob(ctx, Z, [0] * N_CAUSES)) * combos
        return tot
