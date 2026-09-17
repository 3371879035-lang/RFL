"""A73 §60 route C — the single public fault grammar.

This module is the one public implementation of the canonical *structural* fault
support. It is the semantic source for both the evaluator's `DenseSupport` and the
method-side `PublicSCMView`, so that the two sides cannot drift.

Why it exists
-------------
Two independent enumerations of the same object had accumulated:

* ``gate_stage2._domains`` — returns concrete fault objects and wraps the ``Trap``
  construction in ``try/except ValueError``;
* ``identifiability_gate.legal_fault_domains`` — returns plain tuples and **lacks
  that guard**, so on a context where the guard fires it raises instead of
  skipping. Measured by ``scripts/a73_grammar_equivalence.py``: the guard fires on
  **0** of the 5,760 public base contexts, so on the current SCM the two
  enumerations are behaviourally identical. The divergence is latent, not observed.

``support_build.py`` builds the frozen ``DenseSupport`` through
``gate_stage2._domains`` + ``identifiability_gate.canonicalise``, so **that** pair
is the truth source. This module reproduces it, and
``scripts/a73_grammar_equivalence.py`` proves the reproduction is exact over every
public base context before any old caller is re-pointed here.

What it exposes, and what it must never expose
----------------------------------------------
Public structure only: the healthy-trace legal parameter domains for P/D/X/E/U,
A43 canonicalisation, presence/parameter assignment, and the candidate
enumeration built from them. It carries **no** DGP probability, **no** DGP weight,
**no** world id, block id or support handle, and **no** repair.

The one non-public thing it is given is a read-only reference policy
``pi_D^*`` — permitted by A69 because the environment/action grammar and a
read-only ``pi_D^*`` view are public mechanism knowledge. It is *injected*, not
imported, so this module never depends on the solver.
"""

from __future__ import annotations

import itertools
from typing import Any, Iterator, Mapping, Protocol, Sequence

from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.kernel import (
    ControllerFault,
    DecisionOverride,
    PlantFault,
    SemanticTape,
    State,
    Trap,
)

__all__ = [
    "CAUSE_KEYS",
    "STRUCTURAL_SCHEMA",
    "ReferencePolicy",
    "assign",
    "canonical_domains",
    "canonical_structural",
    "canonicalise",
    "iter_assignments",
    "legal_fault_domains",
    "structural",
]

CAUSE_KEYS: tuple[str, ...] = ("P", "D", "X", "E", "U")

#: A73's frozen normalisation schema for the extraction regression. The order
#: inside each tuple is part of the contract, not an implementation detail.
STRUCTURAL_SCHEMA: Mapping[str, str] = {
    "P": "option_id",
    "D": "(t, action)",
    "X": "(x, y, t, kappa, phi, cmd, realized)",
    "E": "(t, realized)",
    "U": "(t, x, y)",
}


class ReferencePolicy(Protocol):
    """Read-only ``pi_D^*(s, z, m)``. Public knowledge per A69; never scored."""

    def best_action(self, state: State, z: int, m: int) -> int: ...


def legal_fault_domains(
    reference: ReferencePolicy,
    kappa: int,
    tape: SemanticTape,
    base_option: int,
    trace: Any,
    stats: dict | None = None,
) -> dict[str, list]:
    """Each fault block's full legal parameter domain on the **healthy** trace.

    Trajectory-dependent by construction: a decision fault can only substitute an
    action admissible at a state the episode actually visits, which is why ``M``
    was never a free Cartesian product.

    ``trace`` is the *healthy* rollout (no fault mask, no option fault), i.e. the
    reference trajectory the domains are defined over.

    Reproduces ``gate_stage2._domains`` exactly, **including** the ``ValueError``
    guard: ``Trap`` rejects ``t >= HORIZON``, and such a parameter must be skipped
    rather than abort the enumeration. ``stats``, if given, accumulates
    ``trap_rejected`` so the guard's work is observable instead of silent.
    """
    state = State(x=K.START[0], y=K.START[1], t=0, kappa=kappa, phi=tape.phase)
    ctrl = K.initial_control(base_option)
    dp = sorted(zp for zp in K.option_ids() if zp != base_option)
    dd, dx, de, du = set(), set(), set(), set()
    for res in trace.steps:
        want = reference.best_action(state, ctrl.z, ctrl.m)
        for a in K.option_actions(ctrl.z, ctrl, state):
            if a != want:
                dd.add(DecisionOverride(t=state.t, action=a))
        for realized in K.legal_actions(state):
            if realized != res.a_cmd:
                dx.add(ControllerFault(state=state, cmd=res.a_cmd, realized=realized))
                de.add(PlantFault(t=state.t, realized=realized))
        for cell in (K.OPEN_CELLS - {K.START, K.GOAL}):
            try:
                du.add(Trap(cell=cell, t=state.t))
            except ValueError:
                if stats is not None:
                    stats["trap_rejected"] = stats.get("trap_rejected", 0) + 1
        state, ctrl = res.state, res.control
    return {
        "P": dp,
        "D": sorted(dd, key=lambda d: (d.t, d.action)),
        "X": sorted(dx, key=lambda f: (f.state.t, f.cmd, f.realized)),
        "E": sorted(de, key=lambda f: (f.t, f.realized)),
        "U": sorted(du, key=lambda t: (t.t, t.cell)),
    }


def canonicalise(domain: Sequence) -> list:
    """``first`` and ``last`` under the frozen order, deduplicated (A43).

    Deliberately blind to outcome, ``B``, ``z*`` and any Gate result: the choice
    reads only the healthy trace and the frozen ordering. That is what makes this
    a **pre-declared finite domain** rather than outcome-conditioned sampling.
    """
    if not domain:
        return []
    if len(domain) == 1:
        return [domain[0]]
    return [domain[0], domain[-1]]


def canonical_domains(
    reference: ReferencePolicy,
    kappa: int,
    tape: SemanticTape,
    base_option: int,
    trace: Any,
    stats: dict | None = None,
) -> dict[str, list]:
    """The A43 canonical support: at most two parameters per fault block."""
    full = legal_fault_domains(reference, kappa, tape, base_option, trace, stats)
    return {k: canonicalise(v) for k, v in full.items()}


def structural(domains: Mapping[str, Sequence]) -> dict[str, tuple]:
    """A73's frozen normalised form, for the extraction regression.

    Bytes are not comparable across the two historical implementations because one
    returns objects and the other tuples; this is the common normal form.
    """
    return {
        "P": tuple(domains["P"]),
        "D": tuple((d.t, d.action) for d in domains["D"]),
        "X": tuple(
            (f.state.x, f.state.y, f.state.t, f.state.kappa, f.state.phi,
             f.cmd, f.realized)
            for f in domains["X"]
        ),
        "E": tuple((f.t, f.realized) for f in domains["E"]),
        "U": tuple((t.t, t.cell[0], t.cell[1]) for t in domains["U"]),
    }


def canonical_structural(
    reference: ReferencePolicy,
    kappa: int,
    tape: SemanticTape,
    base_option: int,
    trace: Any,
    stats: dict | None = None,
) -> dict[str, tuple]:
    """``structural(canonical_domains(...))`` — the object the regression compares."""
    return structural(canonical_domains(reference, kappa, tape, base_option,
                                        trace, stats))


def assign(
    domains: Mapping[str, Sequence],
    presence: Sequence[int],
    params: Sequence[int],
) -> dict[str, Any]:
    """Presence/parameter assignment: ``presence[i]`` picks ``params[i]`` of block i.

    ``None`` means the block is absent. Mirrors ``support_build.build_case`` so the
    method side and the evaluator side name the same world.
    """
    return {
        k: (domains[k][params[i]] if presence[i] else None)
        for i, k in enumerate(CAUSE_KEYS)
    }


def iter_assignments(
    domains: Mapping[str, Sequence],
) -> Iterator[tuple[tuple[int, ...], list[int]]]:
    """Every presence pattern and canonical parameter choice the grammar admits.

    Skips a presence pattern that asks for a block whose domain is empty, exactly
    as the support constructor does. This is the candidate space
    ``PublicSCMView`` is allowed to generate -- it is **not** ``DenseSupport``:
    feasibility (a successful public factual rollout) is applied afterwards.
    """
    sizes = [len(domains[k]) for k in CAUSE_KEYS]
    for bits in itertools.product((0, 1), repeat=5):
        if any(bits[i] == 1 and sizes[i] == 0 for i in range(5)):
            continue
        for combo in itertools.product(
            *[range(sizes[i]) if bits[i] else [-1] for i in range(5)]
        ):
            yield tuple(bits), list(combo)
