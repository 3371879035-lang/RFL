r"""A72 §8.1 / A73 §60 — ``CausalSetLocator``: exact SCM set inversion.

The locator carries **no world knowledge**. It does one thing:

    enumerate hypotheses -> forward simulate -> compare learner-visible rows
    and Z^fire -> union / intersect the credit units

$$\hat\Gamma_{\text{CSL}}(X) = \Gamma^+(X)$$

with $\Gamma^-(X)$ returned alongside as the *certain* responsibility diagnostic. A
mixed class therefore does not guess a site; it reports both addresses as
compatible, which is set identification rather than point identification.

Input is $X^{\text{loc}}_{0.2} = (\text{rows}, Z^{\text{fire}})$ — A73's quotient.
``rows`` carries ``z^in-force``, never the proposal, so the proposal is enumerated;
``kappa`` and ``phi`` are read off ``rows`` because they are learner-visible.

Information boundary
--------------------
This module imports ``public_scm`` and nothing else from the project. It cannot see
``DenseSupport``, the DGP, world or block ids, either repair truth, or the real
``Gamma*`` — those live in modules it must not import, and
``scripts/a73_locator_gate.py`` audits the import graph to keep it that way. The
mutual check is the point: the evaluator reference is built from the frozen support
with its own projection, while the locator re-derives everything from $X$ through
``PublicSCMView``.

An empty compatible set is a protocol failure
---------------------------------------------
$\mathcal C_{\text{SCM}}(X) = \varnothing$ raises :class:`EmptyCompatibleSet`. It is
**never** reported as ``{Unknown/NoWrite}``: that is a substantive responsibility
verdict (A67), whereas emptiness means the model and the evidence disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

from rfl_rebuild.method.public_scm import (
    EmptyCompatibleSet,
    Hypothesis,
    PublicSCMView,
)

__all__ = ["CausalSetLocator", "LocatorResult", "XLoc"]

#: Cause-key bit positions, shared with the kernel's ``fired_mechanisms`` (A54).
BIT_P = 0
BIT_D = 1
BIT_X = 2
BIT_E = 3
BIT_U = 4
EXECUTION_PLANT_MASK = (1 << BIT_X) | (1 << BIT_E)


@dataclass(frozen=True, slots=True)
class XLoc:
    r"""$X^{\text{loc}}_{0.2} = (\text{rows}, Z^{\text{fire}})$ — the whole input.

    Nothing else is permitted: no block id, no world id, no support handle, no
    weights, no repair truth.
    """

    rows: tuple
    fire_code: int

    @property
    def kappa(self) -> int:
        """Learner-visible: ``kappa`` is a field of every row."""
        return self.rows[0][3]

    @property
    def phi(self) -> int:
        """Learner-visible: ``phi`` is a field of every row."""
        return self.rows[0][4]


@dataclass(frozen=True, slots=True)
class LocatorResult:
    r"""The set-valued identification, plus the diagnostic and the audit trail."""

    gamma_plus: frozenset[str]
    r"""$\Gamma^+$: the primary prediction (A72 §8.1)."""

    gamma_minus: frozenset[str]
    r"""$\Gamma^-$: units compatible with *every* retained world."""

    units_set: frozenset[frozenset[str]]
    r"""The distinct $\Gamma^\ast$ values among the retained worlds.

    Retained explicitly so the gate can check A73's exact-set requirement --
    $\{\Gamma^\ast(\tilde\ell) : \tilde\ell \in \mathcal C_{\text{SCM}}(X)\}
    = \{\Gamma^\ast(\ell) : \ell \in H_{\text{eval}}(X)\}$ -- instead of only the
    two envelopes, which could agree while the underlying sets differ.
    """

    n_compatible: int
    r"""$|\mathcal C_{\text{SCM}}(X)|$ -- how many worlds survive the inversion."""

    fire_code: int

    @property
    def ambiguous(self) -> bool:
        """True when the evidence does not pin the responsibility set (A71)."""
        return len(self.units_set) > 1


class CausalSetLocator:
    r"""Exact SCM set inversion from $X^{\text{loc}}$ through ``PublicSCMView``."""

    def __init__(self, view: PublicSCMView) -> None:
        self._view = view

    # -- the one overridable step, so mutation controls can target it ----- #
    def _matches(self, hyp: Hypothesis, x: XLoc) -> bool:
        """Retain a hypothetical world iff it reproduces the learner's evidence.

        Two comparisons, in the order A72 §8.1 states them: the learner-visible
        factual rows first, then the fired-cause vector.
        """
        if self._view.forward(hyp) != x.rows:
            return False
        return self._view.fire_vector(hyp) == x.fire_code

    def compatible(self, x: XLoc) -> tuple[Hypothesis, ...]:
        r"""$\mathcal C_{\text{SCM}}(X)$ — factual-consistency inversion.

        Raises :class:`EmptyCompatibleSet` when nothing is compatible; an empty set
        is a protocol failure, not a verdict.
        """
        kept = tuple(h for h in self._view.hypotheses(x.kappa, x.phi)
                     if self._matches(h, x))
        if not kept:
            raise EmptyCompatibleSet(
                "no hypothetical world is compatible with the learner-visible "
                "evidence; this is a model/evidence disagreement (A73 §60), not a "
                "responsibility conclusion")
        return kept

    def locate(self, x: XLoc) -> LocatorResult:
        r"""$\hat\Gamma_{\text{CSL}}(X) = \Gamma^+(X)$, with $\Gamma^-$ alongside."""
        kept = self.compatible(x)
        units = [self._view.credit_units(h) for h in kept]
        units = [u for u in units if u is not None]
        if not units:
            raise EmptyCompatibleSet(
                "compatible worlds exist but none yields a credit projection")
        plus = frozenset().union(*units)
        if len(units) == 1:
            minus = frozenset(units[0])
        else:
            minus = frozenset(units[0]).intersection(*units[1:])
        return LocatorResult(gamma_plus=plus, gamma_minus=minus,
                             units_set=frozenset(units), n_compatible=len(kept),
                             fire_code=x.fire_code)
