r"""A77 §65.6 — $F_t = (a_t^F,\ G_t^F)$, built from the learner-visible rows.

$$\boxed{F_t = f\bigl(I^{\text{factual}}_{0:T}\bigr)} \quad\text{— not}\quad
f(\text{the evaluator's latent trace})$$

The builder's input type **is** the contract. It takes the row tuple from
:mod:`rfl_rebuild.env.observation` and nothing else: no trace, no fault mask, no
reference, no world identity. The numbers would be identical if it read the trace
directly; the same value reached by a different construction path is a different
information contract, and "it happens to compute the same number" is not the claim —
"it computes it from learner-visible evidence" is. A signature that cannot accept the
trace is worth more than a docstring promising not to use it.

$G_t^F$ is the **factual suffix return** and uses the **frozen reverse Bellman fold**:

$$\boxed{G_T = 0, \qquad G_j = r_j + G_{j+1} \quad (j = T-1, \ldots, t)}$$

Left-to-right ``sum``, ``math.fsum`` and any reordering are prohibited, and no epsilon
canonicalisation may stand in for exactness. The reason is not numerical taste: on a
healthy trajectory $G_t^F$ must be **bit-identical** to $Q_D^\ast(x_t,a_t^F)$, or the
write lands *next to* the reference instead of on it, the canonicalisation to deletion
never fires, and a minimal override appears — clearing ``healthy`` and corrupting
$N_{\text{scalar}}$, $\Sigma$ and the fingerprint.

Measured on the healthy support (48 trajectories $= \kappa \times \varphi \times z_0$,
278 decision addresses): the frozen fold is bit-identical to the DP at **278/278**, while
left-to-right ``sum`` and ``math.fsum`` each mismatch **92/278**. ``fsum`` is the more
accurate summation and still fails.

$G_t^F$ is **never** replaced by $Q_D^\ast$: on a faulted trajectory the observed suffix
return is the target, and substituting the reference would make the $L_0$ law an oracle
in disguise — the defect class of the retired ``+1``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from rfl_rebuild.b1.contract import ProtocolError
from rfl_rebuild.env.kernel import ACTIONS, ControlState, option_actions
from rfl_rebuild.env.observation import ROW_SCHEMA
from rfl_rebuild.learner.store import DecisionAddress

__all__ = [
    "FactualTarget",
    "context_index",
    "facts_for",
    "is_finite_real",
    "build_factual_envelope",
    "factual_return_to_go",
    "validate_factual_envelope",
]

_X = ROW_SCHEMA.index("x")
_Y = ROW_SCHEMA.index("y")
_T = ROW_SCHEMA.index("t")
_KAPPA = ROW_SCHEMA.index("kappa")
_PHI = ROW_SCHEMA.index("phi")
_Z = ROW_SCHEMA.index("z")
_M = ROW_SCHEMA.index("m")
_A_CMD = ROW_SCHEMA.index("a_cmd")
_REWARD = ROW_SCHEMA.index("reward")

#: The row fields that identify a decision context, in the address's own order.
_CONTEXT = (_X, _Y, _T, _KAPPA, _PHI, _Z, _M)


def is_true_int(v: object) -> bool:
    return type(v) is int


def is_action(v: object) -> bool:
    return is_true_int(v) and 0 <= v < len(ACTIONS)


def is_finite_real(v: object) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v))


def context_index(rows: Sequence) -> dict:
    """``(x, y, t, kappa, phi, z, m) -> row index``, failing on a duplicate."""
    index: dict = {}
    for i, row in enumerate(rows):
        key = tuple(row[k] for k in _CONTEXT)
        if key in index:
            raise ProtocolError(
                f"the rows carry the context {key!r} twice, at steps {index[key]} and "
                f"{i}; a decision context must be identifiable from the factual rows")
        index[key] = i
    return index


def factual_return_to_go(rows: Sequence, t: int) -> float:
    r"""$G_t^F$ by the frozen reverse fold, over the rows only.

    The recurrence is written out rather than delegated to ``sum`` because the
    *construction path* is part of the frozen semantics: ``sum`` and ``fsum`` both
    disagree with the DP on 92 of 278 healthy addresses.
    """
    if not (0 <= t < len(rows)):
        raise ProtocolError(f"t={t} is not a step of the factual rows (T={len(rows)})")
    g = 0.0
    for j in range(len(rows) - 1, t - 1, -1):
        g = rows[j][_REWARD] + g
    return g


@dataclass(frozen=True, slots=True)
class FactualTarget:
    r"""$F_t$ for one credited context: the factual action and its suffix return."""

    address: DecisionAddress
    a_factual: int
    g_factual: float


def facts_for(rows: Sequence, index: Mapping, address: DecisionAddress) -> FactualTarget:
    """$F_t$ for one address, from the rows. Shared by builder and validator."""
    key = (address.state.x, address.state.y, address.state.t, address.state.kappa,
           address.state.phi, address.z, address.m)
    i = index.get(key)
    if i is None:
        raise ProtocolError(
            f"credited address {address!r} is not a context of the factual rows; rho_D "
            "must come from the trace that produced these rows")
    row = rows[i]
    a_f = row[_A_CMD]
    if not is_action(a_f):
        raise ProtocolError(
            f"the factual command at {address!r} is {a_f!r}, which is not an action id")
    allowed = option_actions(address.z, ControlState(z=address.z, m=address.m),
                             address.state)
    if a_f not in allowed:
        raise ProtocolError(
            f"the factual command {a_f!r} at {address!r} is outside A_z(m,s); the rows "
            "and the address disagree about the context")
    return FactualTarget(address=address, a_factual=a_f,
                         g_factual=factual_return_to_go(rows, i))


def build_factual_envelope(rows: Sequence,
                           addresses: Sequence[DecisionAddress],
                           ) -> Mapping[DecisionAddress, FactualTarget]:
    r"""The evaluator-side $L_0$ adapter: $F_t$ for every credited context.

    Takes **rows**, not a trace. That is the whole point of the signature.
    """
    index = context_index(rows)
    out = {a: facts_for(rows, index, a) for a in addresses}
    validate_factual_envelope(addresses, out, rows)
    return MappingProxyType(out)


def validate_factual_envelope(addresses: Sequence[DecisionAddress],
                              envelope, rows: Sequence) -> None:
    r"""Structural integrity **and** construction-path identity.

    The outer rule is A76's: the envelope's keys are the credited addresses **exactly** —
    a missing record is a protocol failure, not a verified absence, and an extra key is
    content the law was never entitled to.

    The inner rule is A77 §65.6's, and it is stronger than a schema check: every field is
    **recomputed from the rows and required to be bit-identical**. So a builder that used
    ``sum``, or ``math.fsum``, or substituted $Q_D^\ast$, is caught here even though its
    numbers are "nearly right" — which is exactly the failure the fold clause exists to
    prevent, and exactly the failure a tolerance-based check would wave through.

    What this cannot show: that the builder *only* read the rows. That is enforced by its
    signature instead, and the two together are the contract.
    """
    if not isinstance(envelope, Mapping):
        raise ProtocolError(
            f"the factual envelope is {envelope!r}, not a mapping; a law that requires "
            "the factual fields cannot be run without one")
    credited = set(addresses)
    keys = set(envelope)
    if keys != credited:
        missing = sorted(map(repr, credited - keys))
        raise ProtocolError(
            "the factual envelope is not exactly the credited address set: missing "
            f"record(s) {missing} — a missing record is a protocol failure, not a "
            "verified absence — and non-credited key(s) "
            f"{sorted(map(repr, keys - credited))}")
    index = context_index(rows)
    for a in addresses:
        rec = envelope[a]
        if not isinstance(rec, FactualTarget):
            raise ProtocolError(f"the factual target for {a!r} is {rec!r}, not a "
                                "FactualTarget")
        if rec.address != a:
            raise ProtocolError(
                f"the factual record for {a!r} carries address {rec.address!r}; a record "
                "must describe the address it is keyed by")
        if not is_finite_real(rec.g_factual):
            raise ProtocolError(
                f"the factual return for {a!r} is {rec.g_factual!r}; the value domain is "
                "the finite reals and bool is not a real")
        expected = facts_for(rows, index, a)
        if rec.a_factual != expected.a_factual:
            raise ProtocolError(
                f"the factual action for {a!r} is {rec.a_factual!r} but the rows say "
                f"{expected.a_factual!r}; a_t^F is rows[t].a_cmd, not a declared field")
        if float(rec.g_factual).hex() != float(expected.g_factual).hex():
            raise ProtocolError(
                f"the factual return for {a!r} is {float(rec.g_factual).hex()} but the "
                f"frozen reverse fold gives {float(expected.g_factual).hex()}. The fold "
                "is part of the target's semantics: sum, fsum and any reordering "
                "disagree with the DP (92 of 278 healthy addresses), and a target that "
                "merely rounds to the reference is a target the canonicalisation to "
                "deletion will not recognise (A77 §65.6)")
