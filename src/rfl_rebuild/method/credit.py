"""V0.2R typed contract — native alphabets, the frozen semantic expansion, and the
credit metrics. No algorithms live here (A69, `17-V02R-METHOD-CONTRACT.md`).

The type problem this module exists to solve: the three real representations do
not live in one space --

    ModuleProposal     subset of {H, L}
    TrajectoryProposal subset of {Episode}
    CausalProposal     subset of Gamma(I)

-- while the primary endpoints are set operations ON Gamma. So the pipeline is

    native proposal --eta_R (evaluator-side, frozen)--> Gamma-hat --> Coverage/FCR

Two properties are load-bearing and are enforced structurally rather than promised:

* ``eta_*`` read the native proposal and ``I^factual`` ONLY. They never see the
  truth, because a coarse representation's expander could otherwise use cause
  truth to pick out exactly the right fine-grained units, upgrading a coarse
  schema into a causal one for free.
* ``OracleCreditAdapter`` takes truth directly and shares no path with a method,
  so a truth-capable object cannot be routed through the ordinary entry point.

``eta_R`` is a SEMANTIC EXPANSION and executes no repair. The
``credit unit -> canonical intervention`` conversion is a V0.3R operational
primitive and deliberately does not appear here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

N_CAUSES = 5

# --------------------------------------------------------------------------- #
# the credit ontology, re-frozen by A65/A67
# --------------------------------------------------------------------------- #

GAMMA_STATIC = ("Strategy", "ProcessCommit", "ExternalPlant", "Unknown/NoWrite")
INDEXED_PREFIXES = ("Decision", "ControllerSite")

# A69 section 6: agent_writeable(u) = true iff V0.3R's frozen update primitive may
# write persistently to u. Strategy is ASSIGNED false here because A67 left it
# unassigned; deriving true from the existence of do(z=z') would confuse "can run
# a runtime intervention" with "may write persistently".
AGENT_WRITEABLE = {
    "Strategy": False,
    "ProcessCommit": True,
    "Decision_t": True,
    "ControllerSite": True,
    "ExternalPlant": False,
    "Unknown/NoWrite": False,
}


def is_indexed(u: str) -> bool:
    return u.startswith("Decision_") or u.startswith("ControllerSite_")


def agent_writeable(u: str) -> bool:
    if is_indexed(u):
        return True
    if u not in AGENT_WRITEABLE:
        raise ValueError(f"unknown credit unit {u!r}")
    return AGENT_WRITEABLE[u]


# --------------------------------------------------------------------------- #
# episode-local credit domain
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class FactualShape:
    """The only thing the expansion is allowed to know about the episode."""

    timesteps: tuple
    sites: tuple          # opaque site handles, one per visited ControllerSite

    def gamma(self) -> tuple:
        return tuple(sorted(
            set(GAMMA_STATIC)
            | {f"Decision_{t}" for t in self.timesteps}
            | {f"ControllerSite_{s}" for s in self.sites}))


class ProtocolError(Exception):
    """A typing violation. Never a learner-facing observation."""


# --------------------------------------------------------------------------- #
# the typed input, and the method inputs
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class V02Input:
    """``X_0.2 = (I^factual_{0:T}, Z^fire_truth)``, identical for all three methods.

    Also public: the Gamma ontology with its writability flags, the environment
    grammar, and a read-only reference-policy view. FORBIDDEN and absent by
    construction here: latent M, Z^pres, either repair truth, Gamma*, world id,
    rows-block id, the hypothesis set, DGP weights, any outcome oracle, any write
    target. ``B_Q = 0``: there is no query session.
    """

    evidence: object                     # FactualEvidence
    fire_truth: tuple
    shape: FactualShape

    def __post_init__(self) -> None:
        if len(self.fire_truth) != N_CAUSES:
            raise ProtocolError("Z^fire truth must have 5 entries")

    @property
    def B_Q(self) -> int:
        return 0


# --------------------------------------------------------------------------- #
# native proposals, each confined to its own alphabet
# --------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class ModuleProposal:
    units: frozenset

    def __post_init__(self) -> None:
        if not self.units <= {"H", "L"}:
            raise ProtocolError(f"ModuleProposal alphabet is {{H,L}}; got {self.units}")


@dataclass(frozen=True, slots=True)
class TrajectoryProposal:
    units: frozenset

    def __post_init__(self) -> None:
        if not self.units <= {"Episode"}:
            raise ProtocolError(
                f"TrajectoryProposal alphabet is {{Episode}}; got {self.units}")


@dataclass(frozen=True, slots=True)
class CausalProposal:
    units: frozenset

    def __post_init__(self) -> None:
        for u in self.units:
            if not is_indexed(u) and u not in GAMMA_STATIC:
                raise ProtocolError(f"CausalProposal got a non-Gamma unit {u!r}")


# --------------------------------------------------------------------------- #
# the frozen expansions. Each takes (proposal, shape) and NOT the truth.
# --------------------------------------------------------------------------- #

def eta_module(p: ModuleProposal, shape: FactualShape) -> frozenset:
    """H/L is a granularity partition of the SAME unit space, not a second one."""
    out = set()
    if "H" in p.units:
        out |= set(GAMMA_STATIC)
    if "L" in p.units:
        out |= {f"Decision_{t}" for t in shape.timesteps}
        out |= {f"ControllerSite_{s}" for s in shape.sites}
    return frozenset(out)


def eta_trajectory(p: TrajectoryProposal, shape: FactualShape) -> frozenset:
    """'Something in this run' means EVERY unit of this episode, and nothing less."""
    return frozenset(shape.gamma()) if p.units else frozenset()


def eta_causal(p: CausalProposal, shape: FactualShape) -> frozenset:
    """Identity — but still checked against the episode-local domain."""
    dom = set(shape.gamma())
    stray = p.units - dom
    if stray:
        raise ProtocolError(f"CausalProposal named units outside Gamma(I): {stray}")
    return frozenset(p.units)


ETA = {"module": eta_module, "trajectory": eta_trajectory, "causal": eta_causal}


# --------------------------------------------------------------------------- #
# metrics, on the shared Gamma space
# --------------------------------------------------------------------------- #

def coverage(pred: Iterable[str], truth: Iterable[str]) -> float:
    t = set(truth)
    if not t:
        raise ProtocolError("truth must be non-empty; A67 maps an empty mechanism "
                            "repair to Unknown/NoWrite")
    return len(set(pred) & t) / len(t)


def false_credit_rate(pred: Iterable[str], truth: Iterable[str]) -> float:
    """Empty prediction scores 0, and is punished by coverage instead.

    Abstention (empty set) is NOT relabelled into Unknown/NoWrite: with truth
    {Unknown/NoWrite} the two must score differently, or "say nothing" would be
    rewarded as a correct verdict.
    """
    p = set(pred)
    if not p:
        return 0.0
    return len(p - set(truth)) / len(p)


# --------------------------------------------------------------------------- #
# oracle: separated by type, not by convention
# --------------------------------------------------------------------------- #

class OracleCreditAdapter:
    """``OracleCreditAdapter.evaluate(Gamma*) -> Gamma*`` — evaluator only.

    It does not accept ``V02Input`` and does not implement ``__call__``, so no code
    path routes a truth-capable object through the ordinary method entry.
    """

    name = "OracleCredit"

    @staticmethod
    def evaluate(gamma_star: Iterable[str]) -> frozenset:
        g = frozenset(gamma_star)
        if not g:
            raise ProtocolError("Gamma* is never empty (A67)")
        return g

    def __call__(self, x: "V02Input"):
        raise ProtocolError(
            "OracleCreditAdapter is not a method: use evaluate(Gamma*). It must "
            "never be routed through the ordinary method path (A69).")


def expand(kind: str, proposal, shape: FactualShape) -> frozenset:
    """The only sanctioned route from a native proposal to Gamma."""
    return ETA[kind](proposal, shape)


def writability_of(gamma: Iterable[str]) -> Mapping[str, bool]:
    return {u: agent_writeable(u) for u in gamma}
