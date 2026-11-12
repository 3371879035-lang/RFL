"""A72 §8.2 / A73 §60 — ``PublicSCMView``: the only object the locator may touch.

``CausalSetLocator`` does not import the full kernel API. It receives this object,
which exposes exactly four capabilities and nothing else:

1. **canonical public fault hypotheses** — the grammar's candidate worlds, for a
   learner-visible ``(kappa, phi)``;
2. **forward factual rollout** — what a learner would have seen in a hypothetical
   world, in the frozen row schema;
3. **fired-mechanism vector** — that world's own ``Z^fire``;
4. **hypothetical descriptor -> Gamma unit** — the public credit ontology.

NOT exposed: ``Intervention`` / repair / rescue, ``DenseSupport``, DGP probability
or weight, world id, block id, class frequencies, any precomputed
``(block, fire) -> Gamma+`` table, either repair truth, the real ``Gamma*``, or any
``do(...)``. A59's lesson is that a documented promise is weaker than a type, so
the boundary is a *fact about the object*: see
``scripts/a73_public_scm_gate.py``, which audits the import graph and asserts the
public attribute surface is exactly the allowed set.

``kappa`` and ``phi`` are inputs, not secrets: they appear verbatim in the
learner-visible rows (``observation.ROW_SCHEMA``). ``proposal`` is **not** — the
evidence carries ``z^in-force`` only, so the proposal is enumerated (A55).

The canonical nuisance representative
-------------------------------------
``error_flag = cause_rank = 0`` is fixed here. That is **licensed, not hoped for**:
A73's quotient gate proved ``(error_flag, cause_rank)`` is target-preserving for
rows, fire vector, ``Gamma_desc`` and feasibility across all 4,513 observational
classes (9/9 PASS, 0 violations). Fixing the representative is what collapses the
120-fold nuisance duplication.

An empty compatible set is a protocol failure
---------------------------------------------
``{Unknown/NoWrite}`` is a *substantive* responsibility verdict (A67: the ontology
contains no writable mechanism to blame). A model that finds no compatible world
has not concluded that; it has contradicted its own evidence. A73 therefore forbids
the collapse, and :class:`EmptyCompatibleSet` exists so the mistake cannot be made
silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rfl_rebuild.env import fault_grammar as FG
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.kernel import (
    ControllerFault,
    DecisionOverride,
    FaultMask,
    MalformedIntervention,
    OptionViolation,
    PlantFault,
    SemanticTape,
    Trap,
)
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.method.credit import ProtocolError

__all__ = ["EmptyCompatibleSet", "Hypothesis", "PublicSCMView"]

#: Cause key order shared with the kernel's ``fired_mechanisms`` (A54).
FIRE_KEYS: tuple[str, ...] = ("Z_P", "Z_D", "Z_X", "Z_E", "Z_U")


class EmptyCompatibleSet(ProtocolError):
    """``C_SCM(X) = {}``.

    Deliberately a ``ProtocolError`` (A73 §60). It must never be reported as
    ``{Unknown/NoWrite}``: that is a real responsibility verdict, whereas this
    means the model and the evidence disagree.
    """


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """A hypothetical latent world, as the public grammar can name it.

    Carries no support identity: no world id, no block id. Two hypotheses that the
    grammar cannot distinguish are the same hypothesis.
    """

    kappa: int
    phi: int
    proposal: int
    presence: tuple[int, ...]
    params: tuple[int, ...]

    @property
    def z_code(self) -> int:
        return sum((1 << i) for i, b in enumerate(self.presence) if b)


class PublicSCMView:
    """The restricted public SCM. Capability object, not a data accessor."""

    #: A73: fixed only because the quotient gate proved it target-preserving.
    CANONICAL_ERROR_FLAG: int = 0
    CANONICAL_CAUSE_RANK: int = 0

    def __init__(self, reference: Any, *, provider: Any | None = None) -> None:
        self._reference = reference
        self._provider = provider if provider is not None else _default_provider(reference)
        self._dom_cache: dict = {}
        self._roll_cache: dict = {}
        self._fire_cache: dict = {}

    # -- internals -------------------------------------------------------- #
    @staticmethod
    def _tape(phi: int) -> SemanticTape:
        return SemanticTape(phase=phi,
                            error_flag=PublicSCMView.CANONICAL_ERROR_FLAG,
                            cause_rank=PublicSCMView.CANONICAL_CAUSE_RANK)

    def _domains(self, kappa: int, phi: int, proposal: int) -> dict:
        key = (kappa, phi, proposal)
        hit = self._dom_cache.get(key)
        if hit is None:
            tape = self._tape(phi)
            healthy = K.rollout(kappa=kappa, tape=tape,
                                command_provider=self._provider,
                                base_option=proposal)
            hit = FG.canonical_domains(self._reference, kappa, tape, proposal,
                                       healthy)
            self._dom_cache[key] = hit
        return hit

    def _descriptors(self, hyp: Hypothesis) -> dict:
        return FG.assign(self._domains(hyp.kappa, hyp.phi, hyp.proposal),
                         hyp.presence, hyp.params)

    def _roll(self, hyp: Hypothesis):
        """``(trace, descriptors)`` or ``None`` if the world is not feasible."""
        key = hyp
        if key in self._roll_cache:
            return self._roll_cache[key]
        b = self._descriptors(hyp)
        mask = FaultMask(decision=b["D"], controller=b["X"], plant=b["E"],
                         trap=b["U"])
        tape = self._tape(hyp.phi)
        try:
            trace = K.rollout(kappa=hyp.kappa, tape=tape,
                              command_provider=self._provider,
                              base_option=hyp.proposal, mask=mask,
                              option_fault=b["P"])
            self._roll_cache[key] = (trace, b)
        except (MalformedIntervention, OptionViolation):
            # A73: feasibility is exactly this -- reject MALFORMED / OptionViolation.
            self._roll_cache[key] = None
        return self._roll_cache[key]

    # -- capability 1: canonical public fault hypotheses ------------------ #
    def proposals(self) -> tuple[int, ...]:
        """The options the controller could have been asked to commit."""
        return K.option_ids()

    def hypotheses(self, kappa: int, phi: int) -> tuple[Hypothesis, ...]:
        """Every canonical public fault hypothesis for a learner-visible context."""
        out: list[Hypothesis] = []
        for proposal in K.option_ids():
            doms = self._domains(kappa, phi, proposal)
            for presence, params in FG.iter_assignments(doms):
                out.append(Hypothesis(kappa, phi, proposal, tuple(presence),
                                      tuple(params)))
        return tuple(out)

    # -- capability 2: forward factual rollout ---------------------------- #
    def forward(self, hyp: Hypothesis) -> tuple | None:
        """The learner-visible rows of a hypothetical world, or ``None`` if infeasible."""
        hit = self._roll(hyp)
        if hit is None:
            return None
        trace, _b = hit
        return learner_rows(trace, hyp.kappa, hyp.phi)

    # -- capability 3: fired-mechanism vector ----------------------------- #
    def fire_vector(self, hyp: Hypothesis) -> int | None:
        """That world's own ``Z^fire`` as a 5-bit mask, or ``None`` if infeasible.

        Memoised: ``fired_mechanisms`` costs its own rollout, and the locator asks
        for the fire vector of every hypothesis it enumerates. Without the cache a
        single 893-class sweep would repeat it once per (class, hypothesis) pair.
        """
        key = hyp
        if key in self._fire_cache:
            return self._fire_cache[key]
        hit = self._roll(hyp)
        if hit is None:
            self._fire_cache[key] = None
            return None
        _trace, b = hit
        d = K.fired_mechanisms(kappa=hyp.kappa, tape=self._tape(hyp.phi),
                              command_provider=self._provider,
                              base_option=hyp.proposal,
                              mask=FaultMask(decision=b["D"], controller=b["X"],
                                             plant=b["E"], trap=b["U"]),
                              option_fault=b["P"])
        out = sum((int(d[k]) & 1) << i for i, k in enumerate(FIRE_KEYS))
        self._fire_cache[key] = out
        return out

    # -- capability 4: hypothetical descriptor -> Gamma unit ------------- #
    @staticmethod
    def credit_unit(descriptor: Any) -> str:
        """The public descriptor -> credit-unit mapping (A67, A72 §8.0).

        A *descriptor*, not a type name: ``D`` and ``X`` carry episode-local
        addresses, which is the whole point of A71. Feeding a generic
        ``"Decision_t"`` here is impossible -- only real descriptors are accepted --
        so the empty-intersection bug A71 found cannot recur through this door.
        """
        if isinstance(descriptor, DecisionOverride):
            return f"Decision_{descriptor.t}"
        if isinstance(descriptor, ControllerFault):
            f = descriptor
            return f"ControllerSite_{f.state.x}_{f.state.y}_{f.state.t}_{f.cmd}"
        if isinstance(descriptor, PlantFault):
            return "ExternalPlant"
        if isinstance(descriptor, Trap):
            return "Unknown/NoWrite"
        if descriptor is None:
            raise ValueError("no descriptor: an absent cause is not a credit unit")
        if descriptor == "ProcessCommit":
            return "ProcessCommit"
        raise ValueError(f"unknown descriptor {descriptor!r}")

    def credit_units(self, hyp: Hypothesis) -> frozenset[str] | None:
        """``pi_credit`` applied to this hypothetical world's own fired causes."""
        fc = self.fire_vector(hyp)
        if fc is None:
            return None
        b = self._descriptors(hyp)
        out = set()
        for i, key in enumerate(FG.CAUSE_KEYS):
            if not ((fc >> i) & 1):
                continue
            if key == "P":
                out.add("ProcessCommit")
            else:
                # Dispatch through the INSTANCE, not the class. Calling
                # `PublicSCMView.credit_unit` here made the method unoverridable,
                # so A72 8.3's mutation control silently did nothing and the
                # locator gate's kill set came back empty -- a no-op mutation that
                # would have read as "the gate is robust".
                out.add(self.credit_unit(b[key]))
        # A67: an empty mechanism repair is a substantive verdict, not abstention.
        return frozenset(out) if out else frozenset({"Unknown/NoWrite"})


def _default_provider(reference: Any):
    def provider(state, ctrl):
        return reference.best_action(state, ctrl.z, ctrl.m)
    return provider
