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
                 tapes: Sequence, domains: Callable, is_feasible: Callable):
        self.kappas = tuple(kappas)
        self.options = tuple(options)
        self.tapes = tuple(tapes)
        self._domains = domains
        self._is_feasible = is_feasible
        # A62 closure: the protocol fixes the tape's rank key at 60 values, so
        # the constructor refuses anything else rather than offering a
        # generalisation nothing uses. A configurable rank count would let
        # SceneContext.is_valid and the sampler disagree about the support.
        self.n_cause_rank = N_CAUSE_RANK
        if not (self.kappas and self.options and self.tapes):
            raise ValueError("DGP needs non-empty kappa, option and tape supports")
        # P0-1: the phase mass is built ONCE and read by BOTH the sampler and
        # log_prob. A62 rev1 sampled the phase with rng.choice but never paid
        # P(phi) in log_prob, so log_prob != log P_sampler at the context level.
        # Equal phase frequencies would have cancelled in a normalised
        # posterior, but "it cancels by coincidence" is not a single measure.
        counts: dict = {}
        for t in self.tapes:
            counts[t.phase] = counts.get(t.phase, 0) + 1
        n = len(self.tapes)
        self.phase_mass = {ph: c / n for ph, c in counts.items()}

    def phase_log_prob(self, phase: int) -> float:
        p = self.phase_mass.get(phase)
        return -math.inf if p is None else math.log(p)

    # ---- context level --------------------------------------------------- #
    def context_log_prob(self, ctx: SceneContext) -> float:
        if not ctx.is_valid:
            return -math.inf
        if ctx.kappa not in self.kappas or ctx.base_option not in self.options:
            return -math.inf
        lp = self.phase_log_prob(ctx.phase)
        if lp == -math.inf:
            return -math.inf
        lp -= math.log(len(self.kappas))
        lp -= math.log(len(self.options))
        lp += _L_P_ERR if ctx.error_flag == 1 else _L_1M_ERR
        lp -= math.log(self.n_cause_rank)
        return lp

    def context_total(self) -> float:
        """``sum over contexts of P(ctx)`` — must be exactly 1 (P0-1)."""
        tot = 0.0
        for kappa in self.kappas:
            for phase in self.phase_mass:
                for err in (0, 1):
                    for rank in range(self.n_cause_rank):
                        for z in self.options:
                            ctx = SceneContext(kappa=kappa, phase=phase,
                                               error_flag=err, cause_rank=rank,
                                               base_option=z)
                            tot += math.exp(self.context_log_prob(ctx))
        return tot

    # ---- world level ----------------------------------------------------- #
    def world_log_prob(self, ctx: SceneContext, Z: Sequence[int],
                       param_index: Sequence[int]) -> float:
        """``log P(Z, params | ctx)`` — conditional part of the measure.

        Canonical representation is ENFORCED, not assumed: ``Z_i in {0,1}``,
        ``Z_i = 0 => param_i = -1``, and ``Z_i = 1 => 0 <= param_i < |D_i|``. A62
        rev1 ignored ``param_index`` entirely when ``Z_i = 0``, so
        ``(0, -1)``, ``(0, 0)`` and ``(0, 999)`` were three encodings of one
        world each receiving the same probability.
        """
        if len(Z) != N_CAUSES or len(param_index) != N_CAUSES or not ctx.is_valid:
            # A62 closure: param_index length was unchecked, so a short tuple
            # raised IndexError and a long one had its tail silently ignored --
            # two ways for one world to stop having one encoding.
            return -math.inf
        dm = self._domains(ctx)
        lp = 0.0
        for i in range(N_CAUSES):
            zi = Z[i]
            if zi not in (0, 1):
                return -math.inf
            d = dm[i]
            if zi == 0:
                if param_index[i] != -1:
                    return -math.inf
                if not d:
                    continue
                lp += _L_1M_CAUSE
            else:
                if not d:
                    return -math.inf      # cannot be present with no domain
                if not (0 <= param_index[i] < len(d)):
                    return -math.inf
                lp += _L_P_CAUSE
                lp -= math.log(len(d))    # uniform within the canonical domain
        return lp

    def log_prob(self, ctx: SceneContext, Z: Sequence[int],
                 param_index: Sequence[int]) -> float:
        return self.context_log_prob(ctx) + self.world_log_prob(ctx, Z, param_index)

    # ---- sampling, from the same measure --------------------------------- #
    def sample_context(self, rng) -> SceneContext:
        r = rng.random()
        acc = 0.0
        phase = next(iter(self.phase_mass))
        for ph, p in self.phase_mass.items():
            acc += p
            if r <= acc:
                phase = ph
                break
        return SceneContext(kappa=rng.choice(self.kappas),
                            phase=phase,
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

    # ---- feasibility conditioning (P0-2) --------------------------------- #
    def sample_scene(self, rng, max_tries: int = 10_000):
        """Draw from ``P_raw(ell | ell in F)`` by REJECTING THE WHOLE SCENE.

        Stage2 already measured 127,440 MALFORMED factual cases out of 1,166,400
        candidates, so this is not hypothetical: raw draws land outside F often.
        The frozen definition is

            P_scene(ell) = P_raw(ell | ell in F)

        and the cleanest implementation is whole-scene rejection -- draw a new
        context too, not just new faults. Resampling faults under a FIXED context
        would give P(ctx) P(world | ctx, F), which is a different distribution.
        """
        for _ in range(max_tries):
            ctx = self.sample_context(rng)
            Z, params = self.sample_world(rng, ctx)
            if self._is_feasible(ctx, Z, params):
                return ctx, Z, params
        raise RuntimeError("feasibility rejection did not terminate")

    # ---- the enumerable slice used by the exact consistency test --------- #
    def slice_total(self, ctx: SceneContext) -> float:
        """``sum over all (Z, params) of P(Z, params | ctx)``.

        Must be 1: this is the exact check that the sampler and the prior use one
        measure. Only usable on a context small enough to enumerate. Parameter
        indices obey the canonical encoding (``-1`` iff the cause is off).
        """
        dm = self._domains(ctx)
        tot = 0.0
        for bits in range(1 << N_CAUSES):
            Z = [(bits >> i) & 1 for i in range(N_CAUSES)]
            if any(Z[i] == 1 and not dm[i] for i in range(N_CAUSES)):
                continue
            params = [0 if Z[i] == 1 else -1 for i in range(N_CAUSES)]
            combos = 1
            for i in range(N_CAUSES):
                if Z[i] == 1:
                    combos *= len(dm[i])
            tot += math.exp(self.world_log_prob(ctx, Z, params)) * combos
        return tot
