"""Identifiability gate — Gate E / Gate L.

``docs/rebuild/00-INDEX.md`` §7 step 4, and `03-IDENTIFIABILITY.md`.

Stages, in the frozen order:

1. **count-only.** Enumerate the feasible latent space and count. If it is
   infeasible, **STOP** — `03` §1.1 forbids sampling and then calling it
   exhaustive.
2. factual partition: ``ell -> sigma_0(ell)``.
3. per-class legal queries ``Q(C)`` (`03` §1.6).
4. Gate L: non-adaptive search for a separating subset of size <= B_CF.
   Finding one is a **sound PASS**; failing to find one is
   ``INCONCLUSIVE_NEEDS_ADAPTIVE``, **not** FAIL (`03` §1.4).

The signature is ``I_t = (obs_t, z_t, m_t)``, never ``obs_t`` alone (`03` §9 of
`11-ENVIRONMENT.md`, A27): withholding the control state would manufacture an
identifiability failure.

Counterfactual rollouts use the exact reference policy ``pi_D*(s,z,m)`` (`03` §1.7).
This module defines no world semantics of its own.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import sys
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerFault, ControllerSite, DecisionOverride, FaultMask, Intervention,
    InterventionSet, MalformedIntervention, OptionViolation, PlantFault,
    SemanticTape, State, Trap,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

B_CF = 4  # frozen default, 11-ENVIRONMENT.md s10
CONTEXTS = [(k, p) for k in (0, 1) for p in K.PHASE_DOMAIN]

# The tape support: 6 x 2 x 60 = 720 (11 s8.1.1)
TAPES = tuple(
    SemanticTape(phase=p, error_flag=e, cause_rank=r)
    for p, e, r in itertools.product(K.PHASE_DOMAIN, (0, 1), range(60))
)


# --------------------------------------------------------------------------- #
# Stage 1 — count the feasible latent space. No sampling.
# --------------------------------------------------------------------------- #

def healthy_rollout(sol, kappa: int, phi: int, z: int):
    def provider(s, c):
        return sol.best_action(s, c.z, c.m)

    return K.rollout(kappa=kappa, tape=SemanticTape(phase=phi, error_flag=0,
                                                    cause_rank=0),
                     command_provider=provider, base_option=z)


def fault_parameter_domains(sol, kappa: int, phi: int, z: int) -> dict:
    """The feasible parameter domain of each fault block, on the healthy trace.

    Each block's domain is *trajectory-dependent*: a decision fault can only
    substitute into the admissible set of a state the episode actually visits.
    That is exactly why ``M`` is not a free Cartesian product (`03` §1).
    """
    tr = healthy_rollout(sol, kappa, phi, z)
    state = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=phi)
    ctrl = K.initial_control(z)
    dp, dd, dx, de, du = [], [], [], [], []
    for res in tr.steps:
        allowed = K.option_actions(ctrl.z, ctrl, state)
        for a in allowed:
            if a != res.a_cmd:
                dd.append((state.t, a))
        for r in K.legal_actions(state):
            if r != res.a_cmd:
                dx.append((ControllerSite(state=state, cmd=res.a_cmd), r))
                de.append((state.t, r))
        for cell in sorted(K.OPEN_CELLS - {K.START, K.GOAL}):
            du.append((cell, state.t))
        state, ctrl = res.state, res.control
    dp = [zp for zp in K.option_ids() if zp != z]
    return {"P": dp, "D": dd, "X": dx, "E": de, "U": du}


def stage1_count(sol) -> dict:
    per_block: dict[str, Counter] = {k: Counter() for k in "PDXEU"}
    z_counts = Counter()
    total = 0
    by_Z: dict[str, int] = {}
    for kappa, phi in CONTEXTS[:1]:          # domains do not depend on phi's value
        for z in K.option_ids():
            dom = fault_parameter_domains(sol, kappa, phi, z)
            for k in "PDXEU":
                per_block[k][len(dom[k])] = per_block[k].get(len(dom[k]), 0) + 1
            for Zi in itertools.product((0, 1), repeat=5):
                m = 1
                for bit, key in zip(Zi, "PDXEU"):
                    if bit:
                        m *= max(1, len(dom[key]))
                by_Z["".join(map(str, Zi))] = m
                z_counts[sum(Zi)] += 1
                total += m
    return {
        "per_block_domain_sizes": {k: dict(sorted(v.items())) for k, v in per_block.items()},
        "by_fault_count": dict(sorted(z_counts.items())),
        "by_Z": by_Z,
        "M_assignments_per_option_context": total,
    }


# --------------------------------------------------------------------------- #
# Stages 2-4 — factual classes, class-local queries, non-adaptive Gate L
# --------------------------------------------------------------------------- #

def sigma0(trace) -> tuple:
    """``sigma_0(ell) = I_t`` for the factal episode — the FREE observation."""
    return tuple(
        (res.state.cell, res.state.t, res.a_cmd, res.a_realized, round(res.reward, 6),
         ctrl_before.z, ctrl_before.m)
        for (state, ctrl_before, res) in _walk(trace)
    )


def _walk(trace):
    for i, res in enumerate(trace.steps):
        if i == 0:
            state = None  # filled by caller's closure below
    # simple reconstruction: the first pre-state is START with initial control
    raise NotImplementedError


def build_episode(sol, kappa: int, phi: int, z: int, mask: FaultMask,
                  tape: SemanticTape | None = None):
    """Roll out the healthy policy under ``mask``; returns the trace."""
    def provider(s, c):
        return sol.best_action(s, c.z, c.m)

    return K.rollout(
        kappa=kappa,
        tape=tape if tape is not None else SemanticTape(phase=phi, error_flag=0,
                                                        cause_rank=0),
        command_provider=provider, base_option=z, mask=mask,
    )


def class_local_queries(sol, kappa: int, phi: int, z: int, trace) -> list[Intervention]:
    """``Q(C) = Q_P u Q_D u Q_X``, legal **on this factual trace**.

    A query outside ``A_z(m,s)`` is not a rejected observation — it never enters
    the family at all (`03` §1.6).
    """
    out: list[Intervention] = []
    for zp in K.option_ids():
        if zp != z:
            out.append(Intervention.process(zp))
    state = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=phi)
    ctrl = K.initial_control(z)
    for res in trace.steps:
        for a in K.option_actions(ctrl.z, ctrl, state):
            if a != res.a_cmd:
                out.append(Intervention.decision(state.t, a))
        for a in K.legal_actions(state):
            if a != res.a_cmd:
                out.append(Intervention.execution(
                    ControllerSite(state=state, cmd=res.a_cmd)))
        state, ctrl = res.state, res.control
    return out


def signature_of(sol, kappa, phi, z, mask, query=None):
    """``sigma(ell, q) = (I_t)`` — with and without an intervention."""
    ivs = InterventionSet((query,)) if query is not None else InterventionSet()
    try:
        tr = build_episode(sol, kappa, phi, z, mask)
        if query is not None:
            tr = K.rollout(
                kappa=kappa,
                tape=SemanticTape(phase=phi, error_flag=0, cause_rank=0),
                command_provider=lambda s, c: sol.best_action(s, c.z, c.m),
                base_option=z, mask=mask, interventions=ivs,
            )
    except (MalformedIntervention, OptionViolation):
        return None
    state = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=phi)
    ctrl = K.initial_control(z)
    sig = []
    for res in tr.steps:
        sig.append((res.state.cell, res.state.t, res.a_cmd, res.a_realized,
                    round(res.reward, 6), ctrl.z, ctrl.m))
        state, ctrl = res.state, res.control
    return tuple(sig)


def main() -> int:
    sol = solve_reference()
    print("=" * 78)
    print("Identifiability gate — stage 1 (count-only)")
    print("=" * 78)
    c = stage1_count(sol)
    print("\nfault-parameter domain sizes per (option, context):")
    for k, v in c["per_block_domain_sizes"].items():
        print(f"  {k}: {v}")
    print("\nnumber of Z assignments by fault count:")
    for k, v in c["by_fault_count"].items():
        print(f"  {k} active: {v}")
    print(f"\nM assignments per (option, context): {c['M_assignments_per_option_context']}")

    per_ell = (len(K.option_ids()) * len(CONTEXTS) * len(TAPES)
               * sum(c["by_Z"].values()) / 1)
    print(f"x options x contexts x tapes x Z = {per_ell:.3e}")
    est = c["M_assignments_per_option_context"] * len(K.option_ids()) \
        * len(CONTEXTS) * len(TAPES)
    print(f"\n|L| upper bound ~= {est:.3e}")

    outdir = ROOT / "outputs" / "rebuild"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "gate_count.json").write_text(json.dumps(c, indent=1), encoding="utf-8")
    print(f"\nwrote {outdir / 'gate_count.json'}")

    if est > 1e7:
        print("\nSTOP — the latent space is too large for exhaustive enumeration.")
        print("03 s1.1 forbids sampling and calling it exhaustive.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
