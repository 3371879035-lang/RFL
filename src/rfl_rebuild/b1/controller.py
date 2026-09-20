r"""A80 §68.3–§68.4 — the $X$ cell's evidence: $\rho_X$, the envelope, and the contract check.

$$\rho_X(\texttt{ControllerSite}) = \text{the site handle } (s_t, a^{cmd}_t), \qquad
X_{id}:\ C_X^L(\rho_X(\texttt{ControllerSite})) \leftarrow a^{cmd}$$

Three things live here, and the separation between them is the point of A80 §68.4:

1. **resolution** — a credited unit becomes a `ControllerSite`. This is A76 §63.10's $\rho_X$, a
   B1-layer fact about how a credit unit meets a store key, not a law's business;
2. **the contract check** — `a_cmd ∈ A_z(m, s)`, which needs $z$ and $m$, and a `ControllerSite`
   carries only $(s, a^{cmd})$:

$$\boxed{\text{the site's } z, m \text{ come from the unique learner-visible factual row for that site}}$$

3. **the envelope** — $\{a^{cmd}\}$, and nothing else, delivered identically to the treatment and
   its same-tier reference.

$$\boxed{\text{resolve factual row} \rightarrow \text{strict } \texttt{ControllerSite}
\rightarrow a^{cmd} \in A_z(m,s) \rightarrow \text{arm planning}}$$

$z$ and $m$ are **cell-construction inputs**: they never enter the law's delivery, which stays
exactly $\{a^{cmd}\}$. A law that could read them would be reading option geometry it was not
granted, which is the widening A77 §65.2's exact field set exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.domain import is_true_int, non_integer_state_fields
from rfl_rebuild.env.observation import ROW_SCHEMA

__all__ = [
    "ControllerTarget",
    "build_controller_envelope",
    "resolve_controller_sites",
    "require_admissible_sites",
    "validate_controller_envelope",
]

_X = ROW_SCHEMA.index("x")
_Y = ROW_SCHEMA.index("y")
_T = ROW_SCHEMA.index("t")
_KAPPA = ROW_SCHEMA.index("kappa")
_PHI = ROW_SCHEMA.index("phi")
_Z = ROW_SCHEMA.index("z")
_M = ROW_SCHEMA.index("m")
_A_CMD = ROW_SCHEMA.index("a_cmd")


def _site_of(row) -> object:
    return K.ControllerSite(state=K.State(x=row[_X], y=row[_Y], t=row[_T],
                                          kappa=row[_KAPPA], phi=row[_PHI]),
                            cmd=row[_A_CMD])


def _site_key(site) -> tuple:
    s = site.state
    return (s.x, s.y, s.t, s.kappa, s.phi, site.cmd)


def _row_index(rows: Sequence) -> dict:
    """``(x, y, t, kappa, phi, a_cmd) -> row``, failing on a duplicate."""
    index: dict = {}
    for i, row in enumerate(rows):
        key = _site_key(_site_of(row))
        if key in index:
            raise ProtocolError(
                f"the factual rows carry the site {key!r} twice (steps "
                f"{index[key][_T]} and {row[_T]}); A80 §68.4 requires the row for a site to be "
                "unique, because the contract check reads the option in force from it")
        index[key] = row
    return index


@dataclass(frozen=True, slots=True)
class ControllerTarget:
    r"""$X$'s $L_0$ record: the site and the factual command at it.

    Only $a^{cmd}$ is delivered (A77 §65.2, A80 §68.3); the site is carried so the runner can
    check the record against the address it is keyed by, exactly as every other cell's records do.
    """

    site: object
    a_cmd: int


def require_admissible_sites(sites: Sequence, rows: Sequence) -> None:
    r"""The shared pre-plan validator: strict site, known row, and $a^{cmd} \in A_z(m,s)$.

    Run **before any arm plans**, and run for the reference and the treatment alike, so the two
    cannot differ in admissibility (A80 §68.3). It is the contract A75 §62.3 keeps on the learner's
    side of the fault-privilege line:

    $$\boxed{\text{fault privilege is fault semantics, not a learner privilege}}$$

    $Z_X$/$Z_E$ exist precisely because a *fault* may violate $A_z$; a persistent write is not a
    fault, so a learner-owned controller write must satisfy the option in force. The row supplies
    that option — not the kernel's live control state, which the law layer has no business reading.
    """
    index = _row_index(rows)
    for site in sites:
        if type(site) is not K.ControllerSite:
            raise ProtocolError(
                f"credited controller site {site!r} has type {type(site).__name__}, not "
                "ControllerSite; the credited population is typed before any arm plans")
        bad = non_integer_state_fields(site.state)
        if bad:
            raise ProtocolError(
                f"credited site {site!r} has non-integer State field(s) {bad}; Python folds 1.0, "
                "True and 1 into one key, so a value-equal alias would otherwise be credited as "
                "this site (A78 §66.5's lesson, at the controller key)")
        if not is_true_int(site.cmd):
            raise ProtocolError(
                f"credited site {site!r} carries cmd={site.cmd!r}, which is not a true integer")
        row = index.get(_site_key(site))
        if row is None:
            raise ProtocolError(
                f"credited site {site!r} is not a site of the learner-visible factual rows; the "
                "option in force at a site must come from the evidence, not from the caller")
        allowed = K.option_actions(row[_Z], K.ControlState(z=row[_Z], m=row[_M]),
                                   K.State(x=row[_X], y=row[_Y], t=row[_T],
                                           kappa=row[_KAPPA], phi=row[_PHI]))
        if site.cmd not in allowed:
            raise ProtocolError(
                f"the factual command {site.cmd!r} at site {site!r} is outside "
                f"A_z(m={row[_M]},s) in the option in force (z={row[_Z]}); a learner write does "
                "not inherit fault privilege (A75 §62.3)")


def build_controller_envelope(rows: Sequence, sites: Sequence) -> Mapping:
    r"""The $X$ cell's evaluator-side adapter: $\{a^{cmd}\}$ per credited site."""
    index = _row_index(rows)
    out = {}
    for site in sites:
        row = index.get(_site_key(site))
        if row is None:                                    # pragma: no cover - validator first
            raise ProtocolError(f"credited site {site!r} is not a site of the factual rows")
        out[site] = ControllerTarget(site=site, a_cmd=row[_A_CMD])
    validate_controller_envelope(sites, out, rows)
    return MappingProxyType(out)


def validate_controller_envelope(sites: Sequence, envelope, rows: Sequence) -> None:
    r"""Structure **and** re-derivation: the delivered command is the row's, bit for bit.

    A hand-made envelope cannot be distinguished from a built one by its shape, so the check is
    the same one $L_0$ and $L_2$ use — re-derive from the evidence and compare.
    """
    if not isinstance(envelope, Mapping):
        raise ProtocolError(
            f"the controller envelope is {envelope!r}, not a mapping; a law that requires the "
            "factual command cannot be run without one")
    credited = set(sites)
    if set(envelope) != credited:
        raise ProtocolError(
            "the controller envelope is not exactly the credited site set: missing "
            f"{sorted(map(repr, credited - set(envelope)))} — a missing record is a protocol "
            f"failure, not a verified absence — and non-credited key(s) "
            f"{sorted(map(repr, set(envelope) - credited))}")
    index = _row_index(rows)
    for site in sites:
        rec = envelope[site]
        if not isinstance(rec, ControllerTarget):
            raise ProtocolError(
                f"the controller target for {site!r} is {rec!r}, not a ControllerTarget")
        if rec.site != site:
            raise ProtocolError(
                f"the controller record for {site!r} carries site {rec.site!r}")
        row = index.get(_site_key(site))
        if row is None:                                    # pragma: no cover
            raise ProtocolError(f"credited site {site!r} is not a site of the factual rows")
        if rec.a_cmd != row[_A_CMD]:
            raise ProtocolError(
                f"the delivered command for {site!r} is {rec.a_cmd!r} but the factual row says "
                f"{row[_A_CMD]!r}; a_t^cmd is rows[t].a_cmd, not a declared field")
        if rec.a_cmd != site.cmd:
            # The delivery and the credited address are separate objects, and this is where they
            # are required to agree: the law reads site.cmd, so a delivery that disagreed with it
            # would be a field nobody consumes while the operation used something else.
            raise ProtocolError(
                f"the delivered command for {site!r} is {rec.a_cmd!r} but the credited address "
                f"carries cmd={site.cmd!r}; the L0 delivery and the address identity must agree "
                "(A80 §68.3)")


def resolve_controller_sites(credited_units, trace, kappa: int, phi: int) -> tuple:
    r"""$\rho_X$ at the credit-unit level: each credited step's site handle.

    A76 §63.10 puts this beside the store keys rather than in a law, so that "how a credit unit
    becomes a store key" is answered once per architecture instead of once per implementer.
    """
    from rfl_rebuild.b1.targets import resolve_credited_units

    decision_addresses = resolve_credited_units(credited_units, trace, kappa, phi)
    index = _row_index((row for row in _rows_of(trace, kappa, phi)))
    out = []
    for address in decision_addresses:
        state = address.state
        candidates = [row for row in index.values()
                      if (row[_X], row[_Y], row[_T], row[_KAPPA], row[_PHI])
                      == (state.x, state.y, state.t, state.kappa, state.phi)]
        if len(candidates) != 1:
            raise ProtocolError(
                f"the credited step t={state.t} has {len(candidates)} factual rows, so its "
                "controller site is not determined by the evidence (A80 §68.4)")
        out.append(_site_of(candidates[0]))
    return tuple(out)


def _rows_of(trace, kappa: int, phi: int):
    from rfl_rebuild.env.observation import learner_rows
    return learner_rows(trace, kappa, phi)
