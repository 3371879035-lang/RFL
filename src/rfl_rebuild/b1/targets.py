r"""A76 §63 — $\rho_D$, and the total target envelope.

$\rho_D$ resolves a credited unit to a store address using the **factual trace's real
pre-action timeline**, reusing ``observation.walk_transition`` rather than rebuilding
a timeline locally:

$$\rho_D(\texttt{Decision}_t, \tau) = \texttt{DecisionAddress}(s_t, z_t, m_t)$$

Failure to resolve, a $t$ absent from the factual trace, or one unit resolving to
inconsistent addresses is a :class:`ProtocolError`, never a silent skip.

The **target envelope is total**: the evaluator-side adapter must produce a record for
*every* credited address, and

$$\boxed{\text{a missing record} \neq \text{a verified ``no valid alternative''}}$$

If a missing record could masquerade as the verified-empty case, a target generator
that simply dropped a row would be indistinguishable from the 3,600 genuine
empty-alternative addresses A76 §63.3 measured.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from rfl_rebuild.b1.contract import ProtocolError
from rfl_rebuild.env.kernel import State, option_actions
from rfl_rebuild.env.observation import walk_transition
from rfl_rebuild.learner.store import DecisionAddress
from rfl_rebuild.solve.dp import solve_reference

__all__ = [
    "TargetRecord",
    "build_target_envelope",
    "resolve_decision_address",
    "resolve_credited_units",
]

_DECISION_RE = re.compile(r"^Decision_(\d+)$")


def _contexts(trace, kappa: int, phi: int) -> dict:
    """``t -> (State, z, m, a_cmd)`` on the factual pre-action timeline."""
    out = {}
    for (s, z, m, a_cmd, _ar, _rw) in walk_transition(
            trace, kappa, phi, trace.option_in_force):
        out.setdefault(s.t, (s, z, m, a_cmd))
    return out


def resolve_decision_address(unit: str, trace, kappa: int, phi: int,
                             _cache: dict | None = None) -> DecisionAddress:
    r"""$\rho_D(\texttt{Decision}_t, \tau)$."""
    m = _DECISION_RE.match(unit)
    if m is None:
        raise ProtocolError(
            f"{unit!r} is not a decision credit unit; expected 'Decision_<t>'")
    t = int(m.group(1))
    ctx = _contexts(trace, kappa, phi).get(t)
    if ctx is None:
        raise ProtocolError(
            f"credited unit {unit!r} names t={t}, which is not on the factual trace's "
            "pre-action timeline")
    s, z, mm, _a = ctx
    addr = DecisionAddress(state=s, z=z, m=mm)
    if _cache is not None:
        prior = _cache.get(unit)
        if prior is not None and prior != addr:
            raise ProtocolError(
                f"credit unit {unit!r} resolved inconsistently: {prior!r} then "
                f"{addr!r}")
        _cache[unit] = addr
    return addr


def resolve_credited_units(units, trace, kappa: int, phi: int) -> tuple:
    """Resolve a credited-unit collection, rejecting duplicates and inconsistency."""
    cache: dict = {}
    out = []
    for u in units:
        addr = resolve_decision_address(u, trace, kappa, phi, _cache=cache)
        if addr not in out:
            out.append(addr)
    if len(out) != len(set(out)):
        raise ProtocolError("credited units resolved to a duplicated address")
    return tuple(out)


@dataclass(frozen=True, slots=True)
class TargetRecord:
    r"""$Target_D(\text{addr})$ — either a verified $a^+$ or a verified emptiness.

    ``alternative is None`` means **verified no valid alternative exists**, which is a
    scientific fact and yields ``NO_VALID_ALTERNATIVE``. It is not the same as the
    record being absent, which is a :class:`ProtocolError`.
    """

    address: DecisionAddress
    alternative: int | None
    factual_command: int


def build_target_envelope(sol, addresses, trace, kappa: int, phi: int,
                          ) -> Mapping[DecisionAddress, TargetRecord]:
    r"""The evaluator-side, architecture-blind target adapter.

    For every credited address it records

    $$a^+ = \min\left(A_D^\ast(s,z,m) \setminus \{a^F\}\right)$$

    or a verified emptiness when that set is empty — the 3,600 case A76 §63.3
    measured, reachable only under a co-fault.

    The adapter reads truth, which is why it lives here and not in a law: the law
    receives already-resolved addresses and already-resolved targets and never sees
    $Q_D^\ast$, the trace, or $\Gamma^\ast$.
    """
    ctx = _contexts(trace, kappa, phi)
    out: dict[DecisionAddress, TargetRecord] = {}
    for addr in addresses:
        row = sol.q.get((addr.state, addr.z, addr.m))
        if not row:
            raise ProtocolError(
                f"no exact value row for address {addr!r}; the target envelope "
                "cannot be built")
        best = max(row.values())
        optimal = sorted(a for a, v in row.items() if v >= best - 1e-12)
        hit = ctx.get(addr.state.t)
        a_f = hit[3] if hit is not None else None
        if a_f is None:
            raise ProtocolError(
                f"no factual command at t={addr.state.t} for address {addr!r}")
        alt = [a for a in optimal if a != a_f]
        out[addr] = TargetRecord(address=addr,
                                 alternative=(min(alt) if alt else None),
                                 factual_command=a_f)
    return MappingProxyType(out)
