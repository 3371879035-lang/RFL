r"""A89 §77.3--§77.6 — the $U_2$-native unaffected ontology.

$$\boxed{\text{an interpretable partition of } U_2 \;\neq\; \text{an unaffected region}}$$

An evaluation scene is a unit $u = (\kappa, \text{tape}, z_{\text{base}})$, and the unaffected region is a
set of such units. Two layers, kept apart because the first draft of A89 merged them:

* **eligibility**, one frozen construction carrying both of A79 §67.4's requirements as scene-level
  conjuncts,

  $$\boxed{E(c) = \bigl\{u \in U_2:\ \neg\textit{Consult}(u,c)\ \land\ H_{\text{pre}}(u)\bigr\}}$$

  where $\textit{Consult}(u,c)$ asks whether the **unedited** episode of $u$ consults the credited
  address $c$, and $H_{\text{pre}}(u)$ is that episode's own healthy outcome. It may read the credited
  unit in the learner's address vocabulary, the unit's own fields, the unedited trajectory and the
  frozen solve -- never evaluator truth, an arm's write target, a post-update value, or a canary
  identity as a *source* of $c$;
* **refinements**, intersections with a field-semantic slice, $C_i(c) = E(c) \cap S_i$ over the six
  frozen names.

A slice answers *which part* of an already-legitimate universe is reported. It is not asked to answer
*why* that universe is unaffected, and it cannot make the universe legitimate.

The credited domains have **executable extents** rather than a quantifier: "for all $c$" without an
enumerator is still prose, and B1's `AddressDomain` classes say which addresses are *legal*, not which
population a runner presents. $X$ needs both of its validators, because
`X_DOMAIN.require_credited` checks only the site's types while `require_admissible_sites` additionally
demands a learner-visible factual row and $a^{\text{cmd}} \in A_z(m,s)$.
"""

from __future__ import annotations

from dataclasses import dataclass

from rfl_rebuild.b1.controller import require_admissible_sites
from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b1.tier import DQ_DOMAIN, P_DOMAIN, X_DOMAIN
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.env.domain import decision_contexts, is_true_int
from rfl_rebuild.env.kernel import (
    PHASE_DOMAIN,
    START,
    ControllerSite,
    Outcome,
    SemanticTape,
    State,
    initial_control,
    option_ids,
)
from rfl_rebuild.learner.store import DecisionAddress, LearnerPersistentState

__all__ = [
    "CHANNELS",
    "REFINEMENTS",
    "CreditedSite",
    "EvaluationScene",
    "PreUpdateTraces",
    "UnaffectedSet",
    "credited_domain",
    "eligibility",
    "build_unaffected",
    "pre_update_traces",
    "refinement",
    "require_refinement_totality",
    "scene_domain",
]

CHANNELS = ("D_Q", "X", "P")

#: A87 §75.4 / A89 §77.3: the frozen tape support, as three separate supports.
TAPE_ERROR_SUPPORT = (0, 1)
TAPE_CAUSE_SUPPORT = tuple(range(60))

#: The six refinement names, frozen by A89 §77.4. `eligible_all` *is* the eligibility layer.
REFINEMENTS = (
    "eligible_all",
    "eligible_phase_even",
    "eligible_phase_odd",
    "eligible_cause_rank_lower",
    "eligible_error_absent",
    "eligible_base_option_nonzero",
)

#: `ROW_SCHEMA` order, so a factual row is built in the shape the B1 validators read.
_X, _Y, _T, _KAPPA, _PHI, _Z, _M, _A_CMD = 0, 1, 2, 3, 4, 5, 6, 7


@dataclass(frozen=True, slots=True)
class EvaluationScene:
    r"""$u = (\kappa, \text{phase}, \texttt{error\_flag}, \texttt{cause\_rank}, z_{\text{base}})$.

    Strictly typed, like every other key in this rebuild: `True` and `1.0` compare equal to `1` with
    equal hashes, so a scene that merely *looks* like a member would be one.
    """

    kappa: int
    phase: int
    error_flag: int
    cause_rank: int
    base_option: int

    def __post_init__(self) -> None:
        for name in ("kappa", "phase", "error_flag", "cause_rank", "base_option"):
            value = getattr(self, name)
            if not is_true_int(value):
                raise ProtocolError(f"{name}={value!r} is not a true integer; scenes are typed keys")
        if self.kappa not in (0, 1):
            raise ProtocolError(f"kappa={self.kappa!r} is outside the frozen context domain")
        if self.phase not in PHASE_DOMAIN:
            raise ProtocolError(f"phase={self.phase!r} is outside the frozen phase domain")
        if self.error_flag not in TAPE_ERROR_SUPPORT:
            raise ProtocolError(f"error_flag={self.error_flag!r} is outside the frozen support")
        if self.cause_rank not in TAPE_CAUSE_SUPPORT:
            raise ProtocolError(f"cause_rank={self.cause_rank!r} is outside the frozen support")
        if self.base_option not in option_ids():
            raise ProtocolError(f"base_option={self.base_option!r} is not an option id")

    @property
    def tape(self) -> SemanticTape:
        return SemanticTape(phase=self.phase, error_flag=self.error_flag,
                            cause_rank=self.cause_rank)

    @property
    def key(self) -> tuple:
        r"""A88 §76.2's lexicographic order extended to scenes: $(\kappa, \phi, e, r, z_{\text{base}})$."""
        return (self.kappa, self.phase, self.error_flag, self.cause_rank, self.base_option)


def scene_domain() -> tuple:
    r"""$U_2 = \mathcal K \times \mathcal T \times \mathcal Z$, in the frozen lexicographic order."""
    return tuple(sorted(
        (EvaluationScene(kappa=kappa, phase=phase, error_flag=e, cause_rank=r, base_option=base)
         for kappa in (0, 1) for phase in PHASE_DOMAIN
         for e in TAPE_ERROR_SUPPORT for r in TAPE_CAUSE_SUPPORT for base in option_ids()),
        key=lambda scene: scene.key))


@dataclass(frozen=True, slots=True)
class CreditedSite:
    r"""The credited unit $c$, **at credited-site granularity**.

    For $D_Q$ that is a `DecisionAddress` and not a `QAddress`: A76/A77 freeze
    `owner_Q(QAddress) = DecisionAddress`, and the scalar store sits one layer below the credited
    decision context. The distinction is load-bearing -- two address types are never equal, so a
    $Q$-granular site would satisfy "off-target" automatically even when its row belongs to the
    credited context.
    """

    channel: str
    address: object

    def __post_init__(self) -> None:
        if self.channel not in CHANNELS:
            raise ProtocolError(f"unknown channel {self.channel!r}")
        if self.channel == "D_Q" and type(self.address) is not DecisionAddress:
            raise ProtocolError("the D_Q credited site is a DecisionAddress, not a store key")
        if self.channel == "X" and type(self.address) is not ControllerSite:
            raise ProtocolError("the X credited site is a ControllerSite")
        if self.channel == "P" and not is_true_int(self.address):
            raise ProtocolError("the P credited site is a proposal key, a true integer")

    @property
    def owner(self) -> "CreditedSite":
        r"""$\text{owner}_A$: the domain's own projection, identity for $X$ and $P$."""
        if self.channel == "D_Q":
            return CreditedSite("D_Q", DQ_DOMAIN.owner(self.address))
        if self.channel == "X":
            return CreditedSite("X", X_DOMAIN.owner(self.address))
        return CreditedSite("P", P_DOMAIN.owner(self.address))

    def render(self) -> str:
        if self.channel == "D_Q":
            a = self.address
            s = a.state
            return (f"DecisionAddress(State({s.x},{s.y},{s.t},{s.kappa},{s.phi}),{a.z},{a.m})")
        if self.channel == "X":
            s = self.address.state
            return f"ControllerSite(State({s.x},{s.y},{s.t},{s.kappa},{s.phi}),{self.address.cmd})"
        return f"P({self.address})"


def _episode_walk(trace, scene: EvaluationScene):
    r"""Yield ``(pre_state, pre_control, step)`` — the context each step actually acted from.

    ``step.state`` is the *post*-action state, so a walk that used it as the context would be off by
    one and would ask about sites the episode never constructed.
    """
    state = State(x=START[0], y=START[1], t=0, kappa=scene.kappa, phi=scene.phase)
    control = initial_control(scene.base_option)
    for step in trace.steps:
        yield state, control, step
        state, control = step.state, step.control


class PreUpdateTraces:
    r"""The unedited episodes of $U_2$, computed once and shared by every eligibility query.

    One object, one rollout per scene: $E(c)$ is asked for many credited units, and recomputing the
    same unedited trajectory per query would be harmless but would also let two queries disagree if
    the learner were rebuilt between them.
    """

    __slots__ = ("_traces", "_rows", "_walks")

    def __init__(self, *, q_reference, domain=None) -> None:
        if q_reference is None:
            raise ProtocolError("eligibility needs the injected reference artifact")
        scenes = scene_domain() if domain is None else tuple(domain)
        learner = LearnerPersistentState()
        traces, rows, walks = {}, {}, {}
        for scene in scenes:
            trace = learned_rollout(learner, kappa=scene.kappa, tape=scene.tape,
                                    base_option=scene.base_option, q_reference=q_reference)
            walk = tuple(_episode_walk(trace, scene))
            traces[scene] = trace
            walks[scene] = walk
            rows[scene] = tuple(
                (state.x, state.y, state.t, state.kappa, state.phi,
                 control.z, control.m, step.a_cmd, step.a_realized, step.reward)
                for state, control, step in walk)
        self._traces, self._rows, self._walks = traces, rows, walks

    def trace(self, scene: EvaluationScene):
        return self._traces[scene]

    def rows(self, scene: EvaluationScene) -> tuple:
        return self._rows[scene]

    def walk(self, scene: EvaluationScene) -> tuple:
        return self._walks[scene]

    def successful(self, scene: EvaluationScene) -> bool:
        r"""$H_{\text{pre}}(u)$: the unedited episode's own healthy outcome."""
        return self._traces[scene].outcome == Outcome.SUCCESS

    def consulted(self, channel: str, scene: EvaluationScene) -> tuple:
        r"""The credited sites of ``channel`` this unedited episode consults.

        Returned as a tuple of `CreditedSite` so that a whole-domain totality check can invert the
        relation -- mark, per scene, which sites it excludes -- instead of asking each of the 13824
        credited units about each of the 5760 scenes. The counting form is the same predicate; it is
        the difference between seconds and hours.
        """
        if channel == "D_Q":
            out, seen = [], set()
            for state, control, _step in self._walks[scene]:
                key = (state, control.z, control.m)
                if key not in seen:
                    seen.add(key)
                    out.append(CreditedSite("D_Q", DecisionAddress(state=state, z=control.z,
                                                                   m=control.m)))
            return tuple(out)
        if channel == "X":
            out, seen = [], set()
            for state, _control, step in self._walks[scene]:
                site = ControllerSite(state=state, cmd=step.u)
                if site not in seen:
                    seen.add(site)
                    out.append(CreditedSite("X", site))
            return tuple(out)
        return (CreditedSite("P", scene.base_option),)

    def consults(self, site: CreditedSite, scene: EvaluationScene) -> bool:
        r"""$\textit{Consult}(u,c)$ — read from the **unedited** trajectory only.

        * $D_Q$: the decision read path consults the credited decision context $(s,z,m)$ at every step
          whose pre-action context is that context, entry included;
        * $X$: the controller channel is consulted at
          $\texttt{ControllerSite}(s_j, a^{\text{eff}}_j)$; with no controller override the effective
          action is the step's own $u$, so the site is recoverable from the trace;
        * $P$: the commit edge is consulted once, at the episode's proposal, so the credited proposal
          is consulted exactly when it is the scene's base option.
        """
        if site.channel == "P":
            return scene.base_option == site.address
        return any(consulted == site for consulted in self.consulted(site.channel, scene))


def pre_update_traces(*, q_reference, domain=None) -> PreUpdateTraces:
    return PreUpdateTraces(q_reference=q_reference, domain=domain)


def eligibility(site: CreditedSite, traces: PreUpdateTraces, *, domain=None) -> tuple:
    r"""$E(c)$, the one frozen eligibility construction -- both conjuncts, scene level."""
    scenes = scene_domain() if domain is None else tuple(domain)
    return tuple(u for u in scenes
                 if not traces.consults(site, u) and traces.successful(u))


def _slice(name: str, scene: EvaluationScene) -> bool:
    if name == "eligible_all":
        return True
    if name == "eligible_phase_even":
        return scene.phase % 2 == 0
    if name == "eligible_phase_odd":
        return scene.phase % 2 == 1
    if name == "eligible_cause_rank_lower":
        return scene.cause_rank < 30
    if name == "eligible_error_absent":
        return scene.error_flag == 0
    if name == "eligible_base_option_nonzero":
        return scene.base_option != 0
    raise ProtocolError(f"unknown refinement {name!r}")


def refinement(site: CreditedSite, traces: PreUpdateTraces, name: str, *, domain=None) -> tuple:
    r"""$C_i(c) = E(c) \cap S_i$ — an intersection, never a rival definition of *unaffected*."""
    if name not in REFINEMENTS:
        raise ProtocolError(f"unknown refinement {name!r}; the six names are frozen")
    return tuple(u for u in eligibility(site, traces, domain=domain) if _slice(name, u))


@dataclass(frozen=True, slots=True)
class UnaffectedSet:
    r"""`UnaffectedSet = (units, construction)` — one object is the set.

    `construction` is written `<eligibility>@<refinement>` so both layers are auditable from the object
    itself.
    """

    units: tuple
    construction: str

    def __post_init__(self) -> None:
        if type(self.units) is not tuple:
            raise ProtocolError(f"{self.construction}: units must be a tuple")
        if not self.units:
            raise ProtocolError(
                f"{self.construction}: an empty unit set has no mean, so BehavioralCollateral would be "
                "undefined rather than small")
        if len(set(self.units)) != len(self.units):
            raise ProtocolError(f"{self.construction}: duplicate units")
        domain = scene_domain()
        if len(self.units) >= len(domain):
            raise ProtocolError(
                f"{self.construction}: the region must be a proper subset of U_2; the whole domain is "
                "the treatment effect wearing a different name")
        for u in self.units:
            if type(u) is not EvaluationScene:
                raise ProtocolError(f"{self.construction}: {u!r} is not an EvaluationScene")
            if u not in domain:
                raise ProtocolError(f"{self.construction}: {u!r} is not a member of U_2")
        if tuple(sorted(self.units, key=lambda s: s.key)) != self.units:
            raise ProtocolError(f"{self.construction}: units are not in the frozen order")

    @property
    def size(self) -> int:
        return len(self.units)


def build_unaffected(site: CreditedSite, traces: PreUpdateTraces, name: str,
                     *, domain=None) -> UnaffectedSet:
    r"""The nominal set for one cell, with its two-part construction id."""
    if name not in REFINEMENTS:
        raise ProtocolError(f"unknown refinement {name!r}")
    units = refinement(site, traces, name, domain=domain)
    return UnaffectedSet(units=units, construction=f"E1(c={site.render()})@{name}")


def credited_domain(channel: str, traces: PreUpdateTraces) -> tuple:
    r"""$\mathcal D^{\text{credit}}_A$ — the executable extent, not a quantifier.

    $D_Q$: `DecisionAddress` over the frozen decision-context support, filtered by
    `DQ_DOMAIN.require_credited`. $P$: `option_ids()`, filtered by `P_DOMAIN.require_credited`. $X$: the
    `ControllerSite` instances the unedited episodes construct, filtered by
    `X_DOMAIN.require_credited` **and** `require_admissible_sites(sites, rows)`.
    """
    if channel not in CHANNELS:
        raise ProtocolError(f"unknown channel {channel!r}")
    if channel == "D_Q":
        out, seen = [], set()
        for (state, z, m) in sorted(decision_contexts(),
                                    key=lambda k: (k[0].t, k[0].x, k[0].y, k[0].kappa,
                                                   k[0].phi, k[1], k[2])):
            address = DecisionAddress(state=state, z=z, m=m)
            DQ_DOMAIN.require_credited(address)
            if address not in seen:
                seen.add(address)
                out.append(CreditedSite("D_Q", address))
        return tuple(out)
    if channel == "P":
        out = []
        for z in option_ids():
            P_DOMAIN.require_credited(z)
            out.append(CreditedSite("P", z))
        return tuple(out)
    out, seen = [], set()
    for scene in scene_domain():
        rows = traces.rows(scene)
        for row in rows:
            state = State(x=row[_X], y=row[_Y], t=row[_T], kappa=row[_KAPPA], phi=row[_PHI])
            site = ControllerSite(state=state, cmd=row[_A_CMD])
            X_DOMAIN.require_credited(site)
            require_admissible_sites([site], rows)
            if site not in seen:
                seen.add(site)
                out.append(CreditedSite("X", site))
    return tuple(out)


def require_refinement_totality(channel: str, traces: PreUpdateTraces, sites=None) -> dict:
    r"""$\forall c \in \mathcal D^{\text{credit}}_A,\ \forall i:\ C_i(c) \neq \varnothing$.

    Seedless **admissibility**: an empty refinement has no mean, so it is an inadmissible candidate
    construction rather than a coverage statistic. Whether a non-empty subset is wide enough is the
    separate development-stage question -- defined is not the same as good enough.

    Computed by inversion: each successful scene contributes to the count of every site it consults, and

    $$\lvert C_i(c)\rvert = \lvert S_i\rvert - \operatorname{count}_i(c)$$

    with $S_i$ the successful scenes inside slice $i$. That is the same predicate as asking every site
    about every scene, without the quadratic factor.
    """
    domain = credited_domain(channel, traces) if sites is None else tuple(sites)
    index = {site: i for i, site in enumerate(domain)}
    totals = {name: 0 for name in REFINEMENTS}
    counts = {name: [0] * len(domain) for name in REFINEMENTS}
    for scene in scene_domain():
        if not traces.successful(scene):
            continue
        hits = [index[c] for c in traces.consulted(channel, scene) if c in index]
        for name in REFINEMENTS:
            if _slice(name, scene):
                totals[name] += 1
                for i in hits:
                    counts[name][i] += 1
    sizes = {name: {domain[i].render(): totals[name] - counts[name][i]
                    for i in range(len(domain))} for name in REFINEMENTS}
    empty = [(domain[i].render(), name) for name in REFINEMENTS
             for i in range(len(domain)) if sizes[name][domain[i].render()] == 0]
    if empty:
        raise ProtocolError(
            "refinement totality failed: "
            + ", ".join(f"{name} is empty at {where}" for where, name in empty[:6])
            + ("" if len(empty) <= 6 else f" (+{len(empty) - 6} more)"))
    return sizes
