r"""A86 §74.3 — the seedless structural screening, over the six cells of A87 §75.

$$\boxed{\text{coverage} \to \text{detection} \to \text{direction at the witness} \to
\text{one status per cell} \to \text{one verdict}}$$

This module is the screening **harness**, not the screening result: it enumerates the frozen domains,
forms the closed nominal maps $V_W^{meas} : U \to \mathbb{R}$, evaluates the six cells and computes the
aggregate verdict by A86's own three rules. It draws no seed, selects no development-stage quantity and
touches no arm outside the three preregistered architectures.

Three things are structural here, because each one is a way a screening can be wrong while looking
finished:

* **one shared reference artifact.** `run_screening` takes exactly one `q_reference` and hands the same
  object to every measurement of every cell. A86 §74.1 makes `QReferenceView` a fixed
  measurement-instrument dependency, so a per-arm or per-cell reference would be a different
  instrument per cell -- and the difference would look like a candidate effect;
* **a closed map.** Every measurement is completed over the whole domain before any cell is judged:
  missing units and extra units both raise. A86's detection is $\exists u \in U$, so a map whose extent
  depended on what it happened to find would make the domain depend on the outcome;
* **the frozen status function.** `cell_status` implements A86 §74.3's ordered cases verbatim,
  including `BLIND`'s precedence, rather than a convenient re-derivation. The directions
  $d_{D_Q} = d_X = d_P = +1$ are A87 §75.7's declared values, and the measured sign uses the same loss
  convention: $\operatorname{sign}[V_W(u^*) - V_{W+\Delta W}(u^*)]$.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.continuation import continuation, exogenous_lift
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.env.domain import KAPPA_DOMAIN, decision_contexts
from rfl_rebuild.env.kernel import (
    PHASE_DOMAIN,
    START,
    ControllerSite,
    SemanticTape,
    State,
    option_ids,
)
from rfl_rebuild.learner.store import (
    CONTROLLER,
    PROCESS,
    Q,
    Edit,
    LearnerPersistentState,
    QAddress,
)

__all__ = [
    "ARCHITECTURES",
    "DECLARED_DIRECTION",
    "STATUSES",
    "STATUS_BLIND",
    "STATUS_DIRECTION_FAIL",
    "STATUS_DIRECTION_UNRESOLVED",
    "STATUS_STRUCTURAL_PASS",
    "STRUCTURAL_REJECT",
    "UNIT_1",
    "UNIT_2",
    "WITNESS_SUFFIX_STEP",
    "X_SITE",
    "CellResult",
    "ScreeningReport",
    "VERDICT_ALL_REJECTED",
    "VERDICT_INCONCLUSIVE",
    "VERDICT_SURVIVES",
    "aggregate_verdict",
    "canary_edit",
    "cell_status",
    "learner_prestate",
    "measure_map",
    "run_screening",
    "u1_domain",
    "u2_domain",
    "witness",
]

UNIT_1 = "U1"
UNIT_2 = "U2"
ARCHITECTURES = ("D_Q", "X", "P")

STATUS_STRUCTURAL_PASS = "STRUCTURAL_PASS"
STATUS_BLIND = "BLIND"
STATUS_DIRECTION_FAIL = "DIRECTION_FAIL"
STATUS_DIRECTION_UNRESOLVED = "DIRECTION_UNRESOLVED"
STATUSES = (STATUS_STRUCTURAL_PASS, STATUS_BLIND, STATUS_DIRECTION_FAIL,
            STATUS_DIRECTION_UNRESOLVED)
STRUCTURAL_REJECT = frozenset({STATUS_BLIND, STATUS_DIRECTION_FAIL})

VERDICT_SURVIVES = "UNIFIED_SURVIVES"
VERDICT_ALL_REJECTED = "ALL_PREREG_UNIFIED_REJECTED"
VERDICT_INCONCLUSIVE = "SCREENING_INCONCLUSIVE"

#: A87 §75.7: the declared directions, discharged against the frozen solver. Not measured here.
DECLARED_DIRECTION = {"D_Q": +1, "X": +1, "P": +1}

#: A87 §75.4: the frozen tape support, $\mathcal T = \text{PHASE\_DOMAIN} \times \{0,1\} \times [0,60)$.
TAPE_ERROR_SUPPORT = (0, 1)
TAPE_CAUSE_SUPPORT = tuple(range(60))

WITNESS_STATE = State(x=START[0], y=START[1], t=0, kappa=0, phi=0)
#: A88 §76.3: the X witness moved to the healthy path's first site at which the rewrite is legal
#: for **every** $(z, m)$ -- the constraint A87 §75.1 was missing.
X_SITE = State(x=1, y=1, t=2, kappa=0, phi=0)
CANARY_TAPE = SemanticTape(phase=0, error_flag=0, cause_rank=0)

#: A88 §76.4: where G1's suffix comparison starts on each architecture's frozen $U_2$ image.
WITNESS_SUFFIX_STEP = {"D_Q": 0, "X": 2, "P": 0}


def u1_domain() -> tuple:
    r"""$U_1 = \mathcal X_D$, in the frozen enumerator's own keys: $(\texttt{State}, z, m)$."""
    return tuple(sorted(decision_contexts(),
                        key=lambda k: (k[0].t, k[0].x, k[0].y, k[0].kappa, k[0].phi, k[1], k[2])))


def u2_domain() -> tuple:
    r"""$U_2 = \mathcal K \times \mathcal T \times \mathcal Z$ — the full tape support, not a subset."""
    tapes = tuple(SemanticTape(phase=p, error_flag=e, cause_rank=r)
                  for p in PHASE_DOMAIN for e in TAPE_ERROR_SUPPORT for r in TAPE_CAUSE_SUPPORT)
    return tuple((kappa, tape, base) for kappa in sorted(KAPPA_DOMAIN)
                 for tape in tapes for base in option_ids())


def canary_edit(arch: str) -> Edit:
    r"""$\Delta W_A^{cal}$ of A87 §75.2, in the substrate's edit vocabulary."""
    if arch == "D_Q":
        return Edit(Q, QAddress(state=WITNESS_STATE, z=1, m=0, a=3), -0.14)
    if arch == "X":
        return Edit(CONTROLLER, ControllerSite(state=X_SITE, cmd=3), 1)
    if arch == "P":
        return Edit(PROCESS, 0, 1)
    raise ProtocolError(f"unknown architecture {arch!r}")


def learner_prestate(arch: str | None = None, *, q_reference) -> LearnerPersistentState:
    r"""$W_{\text{pre}}$, or $W_{\text{pre}} + \Delta W_A^{cal}$.

    The reference view is passed because a $Q$ edit must be handed one (A77 §65.4); it is the same
    object every cell measures with, which is the point of taking it as an argument.
    """
    state = LearnerPersistentState()
    if arch is not None:
        state.apply_transaction([canary_edit(arch)], q_reference=q_reference)
    return state


def witness(unit: str, arch: str) -> object:
    r"""$u^*_{A,U} = g_U(\xi_A^*)$: the frozen projection images of A87 §75.2."""
    if unit == UNIT_1:
        if arch == "D_Q":
            return (WITNESS_STATE, 1, 0)
        if arch == "X":
            return (X_SITE, 1, 0)
        return (WITNESS_STATE, 0, 0)
    if unit == UNIT_2:
        return (0, CANARY_TAPE, 1) if arch in ("D_Q", "X") else (0, CANARY_TAPE, 0)
    raise ProtocolError(f"unknown unit {unit!r}")


def _require_closed(measured: dict, domain: tuple, unit: str) -> None:
    missing = set(domain) - set(measured)
    extra = set(measured) - set(domain)
    nonfinite = [u for u, v in measured.items() if not math.isfinite(v)]
    if nonfinite:
        raise ProtocolError(
            f"the {unit} map has {len(nonfinite)} non-finite values; the frozen contract is "
            "V_W^{meas} : U -> R_finite, so NaN and the infinities are refused as well as missing "
            "and extra units")
    if missing or extra:
        raise ProtocolError(
            f"the {unit} map is not closed: {len(missing)} missing and {len(extra)} extra units; "
            "A86's detection is exists-u-in-U, so the extent of the map may not depend on the "
            "outcome (missing and extra units are both refused)")


def measure_map(learner: LearnerPersistentState, unit: str, *, q_reference) -> dict:
    r"""$V_W^{meas} : U \to \mathbb{R}$, completed over the whole domain before any judgement.

    No short-circuit: a positive found at the first unit does not stop the map, because `BLIND`
    requires $\forall u: \Delta V(u) = 0$ and a data-dependent stopping rule would make the recorded
    domain a function of the answer.
    """
    if unit == UNIT_1:
        out = {}
        for (state, z, m) in u1_domain():
            trace = continuation(learner=learner, state=state, z=z, m=m, kappa=state.kappa,
                                 tape=exogenous_lift(state, z, m), q_reference=q_reference)
            out[(state, z, m)] = float(trace.return_value)
        _require_closed(out, u1_domain(), unit)
        return out
    if unit == UNIT_2:
        out = {}
        for (kappa, tape, base) in u2_domain():
            trace = learned_rollout(learner, kappa=kappa, tape=tape, base_option=base,
                                    q_reference=q_reference)
            out[(kappa, tape, base)] = float(trace.return_value)
        _require_closed(out, u2_domain(), unit)
        return out
    raise ProtocolError(f"unknown unit {unit!r}")


def cell_status(*, coverage: bool, detection: bool, d_A: object, measured: object) -> str:
    r"""A86 §74.3's status function, clause for clause and in its own order.

    $$\boxed{\operatorname{status} =
    \begin{cases}
    \texttt{BLIND}, & \neg\text{coverage} \lor \neg\text{detection}\\
    \texttt{DIRECTION\_UNRESOLVED}, & \text{coverage} \land \text{detection} \land
        d_A = \texttt{DIRECTION\_UNRESOLVED}\\
    \texttt{STRUCTURAL\_PASS}, & \dots \land d_A \in \{-1,+1\} \land \text{measured} = d_A\\
    \texttt{DIRECTION\_FAIL}, & \dots \land d_A \in \{-1,+1\} \land \text{measured} \neq d_A
    \end{cases}}$$

    `BLIND` takes precedence: if the measurement cannot see an effect there is nothing left for a
    direction to be right or wrong about.
    """
    if not coverage or not detection:
        return STATUS_BLIND
    if d_A == STATUS_DIRECTION_UNRESOLVED:
        return STATUS_DIRECTION_UNRESOLVED
    if d_A not in (-1, +1):
        raise ProtocolError(f"the direction field is status-typed, got {d_A!r}")
    if measured not in (-1, 0, +1):
        # A86 §74.3: the measured quantity can be zero. Delta V(u*) = 0 with some other u moving
        # is detection with a failed direction test -- DIRECTION_FAIL -- not a crash, and
        # collapsing it here would re-open the BLIND-versus-DIRECTION_FAIL distinction.
        raise ProtocolError(f"a measured sign must be -1, 0 or +1, got {measured!r}")
    return STATUS_STRUCTURAL_PASS if measured == d_A else STATUS_DIRECTION_FAIL


@dataclass(frozen=True)
class CellResult:
    unit: str
    arch: str
    coverage: bool
    detection: bool
    d_A: object
    measured_sign: object
    status: str
    n_units: int
    n_moved: int
    witness_pre: float
    witness_post: float

    @property
    def witness_delta(self) -> float:
        r"""$V_W(u^*) - V_{W+\Delta W}(u^*)$: the loss, in A86 §74.3's own order."""
        return self.witness_pre - self.witness_post

    @property
    def rejected(self) -> bool:
        return self.status in STRUCTURAL_REJECT


@dataclass(frozen=True)
class ScreeningReport:
    cells: tuple
    verdict: str
    #: The closed nominal maps, keyed ``("pre", unit)`` and ``(unit, arch)``. Carried so the evidence
    #: artifact can digest the *measurements* rather than only their summary, and so a re-run can be
    #: compared unit by unit. Digests are computed by the caller: `hashlib` is not on the production
    #: allowlist, and the harness is a production module.
    maps: dict | None = None

    def cell(self, unit: str, arch: str) -> CellResult:
        for cell in self.cells:
            if (cell.unit, cell.arch) == (unit, arch):
                return cell
        raise KeyError((unit, arch))

    def status_matrix(self) -> dict:
        return {(c.unit, c.arch): c.status for c in self.cells}


def aggregate_verdict(cells) -> str:
    r"""A86 §74.4's three rules, applied to the status matrix, in their own order.

    $$\boxed{\exists U\ \forall A: \texttt{STRUCTURAL\_PASS} \Rightarrow \texttt{UNIFIED\_SURVIVES}}$$
    $$\boxed{\forall U\ \exists A: \texttt{STRUCTURAL\_REJECT} \Rightarrow
    \texttt{ALL\_PREREG\_UNIFIED\_REJECTED}}$$
    $$\boxed{\text{otherwise} \Rightarrow \texttt{SCREENING\_INCONCLUSIVE}}$$

    The third rule stays in the harness even though A87 §75.7 shows the present instance cannot reach
    it: the harness implements the frozen rule, not this instance's narrowing, so a future instance
    cannot inherit a verdict it did not earn.
    """
    cells = tuple(cells)
    units = {c.unit for c in cells}
    arches = {c.arch for c in cells}
    pairs = {(c.unit, c.arch) for c in cells}
    # Fail closed on anything but the complete matrix. A86's conclusions are defined on the 2 x 3
    # status matrix, so a subset that happens to look evaluable must not produce a verdict: the same
    # discipline as the closed nominal map, applied to the cells rather than to the units.
    if (len(cells) != 6 or len(pairs) != 6
            or units != {UNIT_1, UNIT_2} or arches != set(ARCHITECTURES)):
        raise ProtocolError(
            f"the status matrix must be exactly {sorted((UNIT_1, UNIT_2))} x "
            f"{sorted(ARCHITECTURES)}; got {len(cells)} cells, {len(pairs)} distinct pairs, "
            f"units {sorted(units)} and architectures {sorted(arches)}")
    for unit in sorted(units):
        rows = [c for c in cells if c.unit == unit]
        if all(c.status == STATUS_STRUCTURAL_PASS for c in rows):
            return VERDICT_SURVIVES
    if all(any(c.rejected for c in cells if c.unit == unit) for unit in sorted(units)):
        return VERDICT_ALL_REJECTED
    return VERDICT_INCONCLUSIVE


def run_screening(*, q_reference) -> ScreeningReport:
    r"""Measure the six cells and return the report. One reference, one pass per (unit, learner).

    The pre-state map of a unit is measured once and reused by all three architectures: "shared"
    means the *same measurement*, so recomputing it per cell would be harmless but implying that three
    separate maps were taken. The post-state maps differ per architecture because $\Delta W$ does.
    """
    if q_reference is None:
        raise ProtocolError("the screening needs the injected nominal reference artifact")
    pre = {unit: measure_map(learner_prestate(None, q_reference=q_reference), unit,
                             q_reference=q_reference)
           for unit in (UNIT_1, UNIT_2)}
    post = {(unit, arch): measure_map(learner_prestate(arch, q_reference=q_reference), unit,
                                      q_reference=q_reference)
            for unit in (UNIT_1, UNIT_2) for arch in ARCHITECTURES}

    cells = []
    for unit in (UNIT_1, UNIT_2):
        base_map = pre[unit]
        for arch in ARCHITECTURES:
            edited = post[(unit, arch)]
            n_units = len(base_map)
            n_moved = sum(1 for u in base_map if base_map[u] != edited[u])
            u_star = witness(unit, arch)
            coverage = u_star in base_map and u_star in edited
            detection = n_moved > 0
            delta = (base_map[u_star] - edited[u_star]) if coverage else None
            measured = None if not coverage else (0 if delta == 0 else (1 if delta > 0 else -1))
            status = cell_status(coverage=coverage, detection=detection,
                                 d_A=DECLARED_DIRECTION[arch], measured=measured)
            cells.append(CellResult(
                unit=unit, arch=arch, coverage=coverage, detection=detection,
                d_A=DECLARED_DIRECTION[arch], measured_sign=measured, status=status,
                n_units=n_units, n_moved=n_moved,
                witness_pre=base_map.get(u_star, float("nan")),
                witness_post=edited.get(u_star, float("nan"))))
    maps = {("pre", unit): pre[unit] for unit in (UNIT_1, UNIT_2)}
    maps.update({(unit, arch): post[(unit, arch)] for unit in (UNIT_1, UNIT_2)
                 for arch in ARCHITECTURES})
    return ScreeningReport(cells=tuple(cells), verdict=aggregate_verdict(cells), maps=maps)
