r"""A76 §63 — $\rho_D$, and the total, **verified** target envelope.

$\rho_D$ resolves a credited unit to a store address using the **factual trace's real
pre-action timeline**, reusing ``observation.walk_transition`` rather than rebuilding
a timeline locally:

$$\rho_D(\texttt{Decision}_t, \tau) = \texttt{DecisionAddress}(s_t, z_t, m_t)$$

Failure to resolve, a $t$ absent from the factual trace, a duplicated credited unit, or
two units resolving to one address is a :class:`ProtocolError`. **Duplicates are not
deduplicated**: silently collapsing them would change $N_{\text{addressed}}$ and the
budget, so the guard has to fail-stop rather than sit behind a filter that has already
removed everything it could catch.

The **target envelope is exactly the credited address set, and structurally verified**:
every credited address carries a record and no other key is present, the record's own
address matches its key, `factual_command` is a real action id, and any $a^+$ is a
genuine action inside $A_z(m,s)$ that differs from the factual command — because it is
called a *verified* envelope, and a store that accepted an inadmissible $a^+$ would
report ``APPLIED`` now and only surface the breach in a later episode.

Exactness, not containment: requiring only "every credited address has a record" left
``targets = {A, B, C, ROGUE}`` legal, so an $L_1$ law was handed corrective content for
an address that was never credited — the runner's laundering hole, one layer up.
"""

from __future__ import annotations

import re
from collections.abc import Mapping as _Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from rfl_rebuild.b1.contract import ProtocolError
from rfl_rebuild.env.kernel import ACTIONS, ControlState, State, option_actions
from rfl_rebuild.env.observation import walk_transition
from rfl_rebuild.learner.store import DecisionAddress

__all__ = [
    "TargetRecord",
    "build_target_envelope",
    "resolve_credited_units",
    "resolve_decision_address",
    "validate_envelope",
]

_DECISION_RE = re.compile(r"^Decision_(\d+)$")


def _is_action(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(ACTIONS)


def _require_unit(unit: object) -> str:
    """A credit unit is a string, checked **before** anything hashes or matches it.

    ``resolve_credited_units`` used to test ``u in seen_units`` first, so an
    unhashable unit such as ``["Decision_0"]`` raised ``TypeError: unhashable type:
    'list'`` out of the duplicate guard, and a bare non-string raised ``TypeError`` out
    of the regex — both where the contract promises a ``PROTOCOL_ERROR``. Same defect
    shape as the kernel's old ``ACTIONS[u]`` and the unvalidated store address.
    """
    if not isinstance(unit, str):
        raise ProtocolError(
            f"credit unit {unit!r} is not a string; a decision credit unit is written "
            "'Decision_<t>'")
    return unit


def _contexts(trace, kappa: int, phi: int) -> dict:
    """``t -> (State, z, m, a_cmd)`` on the factual pre-action timeline."""
    out = {}
    for (s, z, m, a_cmd, _ar, _rw) in walk_transition(
            trace, kappa, phi, trace.option_in_force):
        out.setdefault(s.t, (s, z, m, a_cmd))
    return out


def resolve_decision_address(unit: str, trace, kappa: int, phi: int) -> DecisionAddress:
    r"""$\rho_D(\texttt{Decision}_t, \tau)$."""
    unit = _require_unit(unit)
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
    return DecisionAddress(state=s, z=z, m=mm)


def resolve_credited_units(units, trace, kappa: int, phi: int) -> tuple:
    """Resolve credited units, **failing stop** on any duplicate or collision.

    An earlier version filtered repeats out while building the list and then checked
    for duplicates, so the check could never fire: the docstring promised rejection
    while the behaviour was silent de-duplication. Two ``Decision_3`` entries became
    one address, quietly changing $N_{\text{addressed}}$ and the budget.

    The type check runs **first**: a non-string unit is rejected before it reaches the
    duplicate set, so an unhashable one cannot turn the duplicate guard into a
    ``TypeError``.
    """
    seen_units: set = set()
    by_address: dict = {}
    out = []
    for u in units:
        u = _require_unit(u)
        if u in seen_units:
            raise ProtocolError(
                f"credited unit {u!r} appears more than once; de-duplicating it would "
                "silently change N_addressed and the address budget")
        seen_units.add(u)
        addr = resolve_decision_address(u, trace, kappa, phi)
        if addr in by_address:
            raise ProtocolError(
                f"credited units {by_address[addr]!r} and {u!r} both resolve to "
                f"{addr!r}; one address cannot be credited twice")
        by_address[addr] = u
        out.append(addr)
    return tuple(out)


@dataclass(frozen=True, slots=True)
class TargetRecord:
    r"""$Target_D(\text{addr})$ — either a verified $a^+$ or a verified emptiness.

    ``alternative is None`` means **verified no valid alternative exists**, which is a
    scientific fact yielding ``NO_VALID_ALTERNATIVE``. It is not the same as the record
    being absent, which is a :class:`ProtocolError`.
    """

    address: DecisionAddress
    alternative: int | None
    factual_command: int


def validate_envelope(addresses, targets) -> None:
    r"""Structural integrity of a *verified* envelope.

    $$\boxed{\operatorname{keys}(\texttt{targets})
    = \operatorname{set}(\texttt{addresses})}$$

    **Exact equality, not containment.** The earlier version only required every
    credited address to carry a record, so ``targets = {A, B, C, ROGUE}`` was accepted
    and an $L_1$ law was delivered corrective content for an address that was never
    credited. A check that only looks for missing keys is not a check on the envelope.

    Checks:

    * the envelope is a mapping, and its keys are **exactly** the credited addresses —
      a missing record is a protocol failure, not a verified absence, and an extra key
      is corrective content the law was never entitled to;
    * every value is a :class:`TargetRecord`;
    * ``record.address == key`` — otherwise ``targets[A] = TargetRecord(address=B,
      ...)`` would write B's target at A;
    * ``factual_command`` is a true action id;
    * any $a^+$ is a true action id **inside** $A_z(m,s)$;
    * $a^+ \neq a^F$, since an "alternative" equal to the factual command is not an
      alternative.

    Scope, stated precisely — what this function does **not** establish:

    * it cannot detect a *legal but false* ``factual_command``. The field is read from
      the record and there is no trace here to compare it with, so a record claiming
      the wrong (but valid) factual command would let an $a^+$ equal to the *real*
      factual action pass. Grounding that field is :func:`build_target_envelope`'s job,
      and the check below is a consistency check on a record, not a truth check;
    * it does not re-run the DP: that $a^+$ is argmax-derived remains the
      evaluator-side builder's guarantee.
    """
    if not isinstance(targets, _Mapping):
        raise ProtocolError(
            f"the target envelope is {targets!r}, not a mapping; a law that requires an "
            "alternative cannot be run without one")
    credited = set(addresses)
    keys = set(targets)
    if keys != credited:
        missing = sorted(map(repr, credited - keys))
        extra = sorted(map(repr, keys - credited))
        raise ProtocolError(
            "the target envelope is not exactly the credited address set: missing "
            f"record(s) {missing} — a missing record is a protocol failure, not a "
            f"verified absence of an alternative — and non-credited key(s) {extra}, "
            "which would deliver corrective content for an address that was never "
            "credited")
    for a in addresses:
        rec = targets[a]
        if not isinstance(rec, TargetRecord):
            raise ProtocolError(
                f"the target for {a!r} is {rec!r}, not a TargetRecord")
        if rec.address != a:
            raise ProtocolError(
                f"target record for {a!r} carries address {rec.address!r}; a record "
                "must describe the address it is keyed by")
        if not _is_action(rec.factual_command):
            raise ProtocolError(
                f"the factual command recorded for {a!r} is {rec.factual_command!r}, "
                "which is not an action id; a^+ != a^F is only meaningful against a "
                "real factual command")
        if rec.alternative is None:
            continue
        if not _is_action(rec.alternative):
            raise ProtocolError(
                f"target for {a!r} is {rec.alternative!r}, which is not an action id")
        allowed = option_actions(a.z, ControlState(z=a.z, m=a.m), a.state)
        if rec.alternative not in allowed:
            raise ProtocolError(
                f"target {rec.alternative!r} for {a!r} is outside A_z(m,s); an "
                "envelope called verified may not carry an inadmissible target")
        if rec.alternative == rec.factual_command:
            raise ProtocolError(
                f"target for {a!r} equals the factual command; that is not an "
                "alternative")


def build_target_envelope(sol, addresses, trace, kappa: int, phi: int,
                          ) -> Mapping[DecisionAddress, TargetRecord]:
    r"""The evaluator-side, architecture-blind target adapter.

    For every credited address it records

    $$a^+ = \min\left(A_D^\ast(s,z,m) \setminus \{a^F\}\right)$$

    or a verified emptiness when that set is empty — the 3,600 case A76 §63.3 measured,
    reachable only under a co-fault.

    The address is checked against the timeline rather than assumed: the context at
    ``addr.state.t`` must be **the same** $(s, z, m)$, not merely the same timestep.
    ``factual_command`` is therefore the trace's own $a^F$, not a declared field — this
    function is the only place an envelope for a real scene is produced, and it is where
    $a^+ \neq a^F$ gets grounded in truth rather than in the record.

    The adapter reads truth, which is why it lives here and not in a law. Its output is
    never handed to a law directly: the runner projects it onto the cell's declared field
    set first (A77 §65.2), so ``factual_command`` stops here. Only cells that declare a
    field are built at all (A76 §63.1).
    """
    ctx = _contexts(trace, kappa, phi)
    out: dict[DecisionAddress, TargetRecord] = {}
    for addr in addresses:
        hit = ctx.get(addr.state.t)
        if hit is None:
            raise ProtocolError(
                f"no factual context at t={addr.state.t} for address {addr!r}")
        s_t, z_t, m_t, a_f = hit
        if (s_t, z_t, m_t) != (addr.state, addr.z, addr.m):
            raise ProtocolError(
                f"address {addr!r} is not the factual context at t={addr.state.t} "
                f"({s_t!r}, z={z_t}, m={m_t}); rho_D must come from the trace")
        row = sol.q.get((addr.state, addr.z, addr.m))
        if not row:
            raise ProtocolError(
                f"no exact value row for address {addr!r}; the target envelope cannot "
                "be built")
        best = max(row.values())
        optimal = sorted(a for a, v in row.items() if v >= best - 1e-12)
        alt = [a for a in optimal if a != a_f]
        out[addr] = TargetRecord(address=addr,
                                 alternative=(min(alt) if alt else None),
                                 factual_command=a_f)
    validate_envelope(addresses, out)
    return MappingProxyType(out)
