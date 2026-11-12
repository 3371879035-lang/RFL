r"""A89 §77.7 — the synthetic calibration chain, frozen arrow by arrow.

$$\boxed{c^{\text{cal}}_A \to C(c^{\text{cal}}_A) \to u^{\text{spill}}_{C,A} \to
\text{owner}_A(q^{\text{spill}}) = s^{\text{spill}}_{C,A} \to \Delta W^{\text{spill}}_A \to
B^{ref}_{C,A}}$$

Three things are structural here rather than documented:

* **the credited sites are frozen**, at credited-site granularity: for $D_Q$ a `DecisionAddress` and not
  a `QAddress`, because `owner_Q(QAddress) = DecisionAddress` (A76/A77) and the scalar store sits a
  layer below the credited decision context. Two address types are never equal, so a $Q$-granular site
  would satisfy "off-target" automatically even when its row belongs to the credited context, and the
  intended site's own scalar would be reported as collateral;
* **the edit is a function**, $\mathcal I_A$, returning a unique legal edit or `None`. Nothing about the
  target is left to implementation time: the $D_Q$ clause lowers the taken action's own row where an
  alternative exists, the $X$ clause takes the least common admissible alternative over **all**
  $(z,m)$ -- A88 §76.2's contract-preservation rule, since a target legal at one witness is not
  automatically legal wherever the site fires -- and the $P$ clause maps the proposal to the least other
  option;
* **the reference is a prediction**, formed from the frozen solver's rows and the unedited trajectory.
  It may read the frozen reference, $C$ and $\Delta W^{\text{spill}}_A$ and nothing else: never a measured
  map, never the measured collateral, never an arm's output. Otherwise the calibration equation would
  certify itself.

The *measured* side of Gate A -- `BehavioralCollateral` over the same functional -- needs the scene-level
collateral instrument and is the remaining piece; this module supplies the predicted side, the chain and
the edit, which Gate B and Gate E exercise on their own.
"""

from __future__ import annotations

from dataclasses import dataclass

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.unaffected import (
    REFINEMENTS,
    CreditedSite,
    EvaluationScene,
    PreUpdateTraces,
    refinement,
)
from rfl_rebuild.env.kernel import (
    START,
    ControlState,
    ControllerSite,
    SemanticTape,
    State,
    initial_control,
    option_actions,
    option_ids,
    step,
)
from rfl_rebuild.learner.store import CONTROLLER, PROCESS, Q, DecisionAddress, Edit, QAddress

__all__ = [
    "CALIBRATION_FAIL",
    "CAL_SITES",
    "SpilloverEdit",
    "aggregate_reference",
    "calibration_cells",
    "cal_site",
    "predicted_pre_value",
    "predicted_spill_value",
    "spillover_edit",
]

#: §77.7's frozen credited sites, at credited-site granularity.
_DQ_CAL_STATE = State(x=START[0], y=START[1], t=0, kappa=0, phi=0)
_X_CAL_STATE = State(x=1, y=1, t=2, kappa=0, phi=0)

CAL_SITES = {
    "D_Q": CreditedSite("D_Q", DecisionAddress(state=_DQ_CAL_STATE, z=1, m=0)),
    "X": CreditedSite("X", ControllerSite(state=_X_CAL_STATE, cmd=3)),
    "P": CreditedSite("P", 0),
}

CALIBRATION_FAIL = "CALIBRATION_FAIL"


def cal_site(channel: str) -> CreditedSite:
    if channel not in CAL_SITES:
        raise ProtocolError(f"unknown channel {channel!r}")
    return CAL_SITES[channel]


@dataclass(frozen=True, slots=True)
class SpilloverEdit:
    r"""One cell's synthetic spillover: the unit, the two sites, the target and the substrate edit."""

    channel: str
    refinement: str
    unit: EvaluationScene
    channel_address: object          # $q^{\text{spill}}$, at channel granularity
    site: CreditedSite               # $\text{owner}_A(q^{\text{spill}})$, must differ from $c^{\text{cal}}$
    substrate_edit: Edit
    target: object                   # what the substrate stores: a scalar for Q, an action for X, an option for P
    applied_action: object           # the action the kernel executes at the edited context (D_Q, X)
    applied_option: object           # the option in force at the entry (P); None where not applicable
    edited_context: object           # the decision context the edit acts at (for the prediction)

    def render(self) -> str:
        return f"{self.channel}/{self.refinement}: {self.site.render()} <- {self.target!r}"


def _successor(state: State, control: ControlState, action: int, scene: EvaluationScene):
    r"""One application of the **frozen transition**, to place the prediction after the edit.

    This is not a measurement: it is the kernel's deterministic step applied to the reference policy's
    own path, exactly as §75.7 forms $\Delta V^{ref}$ from the solver's rows.
    """
    result = step(state, control, action, tape=scene.tape)
    return result.state, result.control, result.reward, result.terminal


def _walk(traces: PreUpdateTraces, scene: EvaluationScene):
    r"""The same pre-action walk eligibility uses -- one walk, not two that could disagree."""
    return traces.walk(scene)


def _dq_edit(solution, traces: PreUpdateTraces, scene: EvaluationScene, q: QAddress):
    r"""$\mathcal I_{D_Q}(q)$: the taken action's row, lowered where an alternative exists.

    Returns the substrate edit **and** the action the kernel will then execute: lowering the taken
    action's row to $\min_a Q^{*} - 1$ makes it the least valued row, so the read path's argmax becomes
    the best of the remaining actions. Carrying the value alone and re-deriving the action later is how
    a prediction silently steps with the wrong action.
    """
    state, control = q.state, ControlState(z=q.z, m=q.m)
    allowed = sorted(option_actions(q.z, control, state))
    if q.a not in allowed or len(allowed) < 2:
        return None
    values = {a: solution.q_value(state, q.z, q.m, a) for a in allowed}
    others = {a: v for a, v in values.items() if a != q.a}
    applied = max(sorted(others), key=lambda a: others[a])
    return Edit(Q, q, min(values.values()) - 1.0), applied


def _x_edit(solution, traces: PreUpdateTraces, scene: EvaluationScene, site: ControllerSite):
    r"""$\mathcal I_X(q)$: the least common admissible alternative, A88 §76.2's rule."""
    common = None
    for z in option_ids():
        for m in (0, 1):
            allowed = set(option_actions(z, ControlState(z=z, m=m), site.state))
            common = allowed if common is None else (common & allowed)
    alternatives = sorted((common or set()) - {site.cmd})
    if not alternatives:
        return None
    return Edit(CONTROLLER, site, alternatives[0]), alternatives[0]


def _p_edit(solution, traces: PreUpdateTraces, scene: EvaluationScene, proposal: int):
    r"""$\mathcal I_P(q)$: the proposal remapped to the least other option."""
    targets = sorted(set(option_ids()) - {proposal})
    if not targets:
        return None
    return Edit(PROCESS, proposal, targets[0]), targets[0]


def _consulted_channel_sites(channel: str, traces: PreUpdateTraces, scene: EvaluationScene):
    r"""$q$ at **channel** granularity, in lexicographic order.

    For $D_Q$ the channel address is a `QAddress` -- the store key -- whose owner is the credited
    `DecisionAddress`; for $X$ the site is its own owner; for $P$ the proposal is.
    """
    if channel == "D_Q":
        out, seen = [], set()
        for state, control, step_result in _walk(traces, scene):
            address = QAddress(state=state, z=control.z, m=control.m, a=step_result.u)
            if address not in seen:
                seen.add(address)
                out.append(address)
        return sorted(out, key=lambda a: (a.state.t, a.state.x, a.state.y, a.state.kappa,
                                          a.state.phi, a.z, a.m, a.a))
    if channel == "X":
        out, seen = [], set()
        for state, _control, step_result in _walk(traces, scene):
            site = ControllerSite(state=state, cmd=step_result.a_cmd)
            if site not in seen:
                seen.add(site)
                out.append(site)
        return sorted(out, key=lambda s: (s.state.t, s.state.x, s.state.y, s.state.kappa,
                                          s.state.phi, s.cmd))
    return [scene.base_option]


def _owner_of(channel: str, address, solution) -> CreditedSite:
    if channel == "D_Q":
        return CreditedSite("D_Q", DecisionAddress(state=address.state, z=address.z, m=address.m))
    if channel == "X":
        return CreditedSite("X", address)
    return CreditedSite("P", address)


def _make_edit(channel: str, solution, traces, scene, address):
    r"""``(edit, applied_action, applied_option)`` or `None` — never a bare value."""
    if channel == "D_Q":
        made = _dq_edit(solution, traces, scene, address)
        return None if made is None else (made[0], made[1], None)
    if channel == "X":
        made = _x_edit(solution, traces, scene, address)
        return None if made is None else (made[0], made[1], None)
    made = _p_edit(solution, traces, scene, address)
    return None if made is None else (made[0], None, made[1])


def spillover_edit(channel: str, traces: PreUpdateTraces, refinement_name: str, *,
                   solution, c_cal: CreditedSite | None = None) -> SpilloverEdit:
    r"""The fixture of one calibration cell, or `CALIBRATION_FAIL`.

    $$u^{\text{spill}}_{C,A} = \min_{\text{lex}} \bigl\{u \in C:\ \text{the } W_{\text{pre}}
    \text{ trajectory of } u \text{ consults an address } q \text{ with }
    \text{owner}_A(q) \neq c^{\text{cal}}_A \text{ and } \mathcal I_A(q) \neq \texttt{None}\bigr\}}$$

    and $q^{\text{spill}}$ is the lexicographically least such address. Fail closed: nothing is
    relocated, no target is substituted, and the candidate is not narrowed.
    """
    if refinement_name not in REFINEMENTS:
        raise ProtocolError(f"unknown refinement {refinement_name!r}")
    c_cal = cal_site(channel) if c_cal is None else c_cal
    units = refinement(c_cal, traces, refinement_name)
    for scene in units:
        for address in _consulted_channel_sites(channel, traces, scene):
            owner = _owner_of(channel, address, solution)
            if owner.render() == c_cal.render():
                continue
            made = _make_edit(channel, solution, traces, scene, address)
            if made is None:
                continue
            substrate_edit, applied_action, applied_option = made
            return SpilloverEdit(channel=channel, refinement=refinement_name, unit=scene,
                                 channel_address=address, site=owner,
                                 substrate_edit=substrate_edit, target=substrate_edit.value,
                                 applied_action=applied_action, applied_option=applied_option,
                                 edited_context=owner.address)
    raise ProtocolError(
        f"{CALIBRATION_FAIL}: {channel}/{refinement_name} has no eligible unit that consults a "
        "channel address with a different owner and a defined edit; the fixture is not relocated and "
        "the candidate is not narrowed")


def predicted_pre_value(channel: str, scene: EvaluationScene, *, solution) -> float:
    r"""$V^{ref}_{\text{pre}}(u)$ — the frozen solver's own value for the scene's entry."""
    entry = State(x=START[0], y=START[1], t=0, kappa=scene.kappa, phi=scene.phase)
    return float(solution.value(entry, scene.base_option, 0))


def predicted_spill_value(channel: str, scene: EvaluationScene, edit: SpilloverEdit, *,
                          traces: PreUpdateTraces, solution) -> float:
    r"""$V^{ref}_{\text{spill}}(u)$ — the same quantity under the synthetic edit.

    Formed the way §75.7 forms $\Delta V^{ref}$: the frozen solver's rows, with the edited address
    applied where the unit's trajectory consults it, and the unedited value where it does not. The
    continuation after the edited step is the reference policy again, because $t$ strictly increases and
    the edited context cannot recur.
    """
    pre = predicted_pre_value(channel, scene, solution=solution)
    if channel == "P":
        if scene.base_option != edit.channel_address:
            return pre
        entry = State(x=START[0], y=START[1], t=0, kappa=scene.kappa, phi=scene.phase)
        return float(solution.value(entry, edit.applied_option, 0))

    walk = _walk(traces, scene)
    for index, (state, control, step_result) in enumerate(walk):
        if channel == "D_Q":
            if (state, control.z, control.m, step_result.u) != (
                    edit.channel_address.state, edit.channel_address.z, edit.channel_address.m,
                    edit.channel_address.a):
                continue
        else:
            if ControllerSite(state=state, cmd=step_result.a_cmd) != edit.channel_address:
                continue
        prefix = sum(s.reward for s in traces.trace(scene).steps[:index])
        successor_state, successor_control, reward, terminal = _successor(
            state, control, edit.applied_action, scene)
        # The edited step's **own** reward is part of the value and it changes with the action: a
        # prediction that adds only the successor's value is short by exactly that reward, which is
        # how this module first reported a value-neutral $D_Q$ site that the measurement disagreed
        # with. Gate A's equality requirement is what caught it.
        if terminal:
            return float(prefix) + float(reward)
        return float(prefix) + float(reward) + float(solution.value(successor_state,
                                                                    successor_control.z,
                                                                    successor_control.m))
    return pre


def aggregate_reference(channel: str, traces: PreUpdateTraces, refinement_name: str, *,
                        solution, c_cal: CreditedSite | None = None) -> dict:
    r"""$B^{ref}_{C,A}$: the **aggregate functional**, on frozen predictions.

    $$\boxed{B^{ref}_{C,A} := \frac{1}{\lvert C\rvert}\sum_{u \in C}
    \bigl[V^{ref}_{\text{pre}}(u) - V^{ref}_{\text{spill}}(u)\bigr]}$$

    A unit-level sign cannot certify a set-level ruler: one persistent edit moves more than one unit, so
    $\operatorname{sign}\Delta V(u^{\text{spill}}) \not\Rightarrow
    \operatorname{sign}\texttt{BehavioralCollateral}(C)$. A zero prediction is `CALIBRATION_FAIL`,
    because an injection the aggregate ruler predicts as invisible is not a calibratable spillover.
    """
    c_cal = cal_site(channel) if c_cal is None else c_cal
    units = refinement(c_cal, traces, refinement_name)
    edit = spillover_edit(channel, traces, refinement_name, solution=solution, c_cal=c_cal)
    total = 0.0
    contributions = {}
    for scene in units:
        pre = predicted_pre_value(channel, scene, solution=solution)
        spill = predicted_spill_value(channel, scene, edit, traces=traces, solution=solution)
        contributions[scene] = pre - spill
        total += pre - spill
    value = total / len(units)
    if value == 0.0:
        raise ProtocolError(
            f"{CALIBRATION_FAIL}: {channel}/{refinement_name} has B^ref = 0, so the injection is not a "
            "calibratable spillover for this aggregate ruler")
    return {"channel": channel, "refinement": refinement_name, "size": len(units),
            "edit": edit, "B_ref": value, "d_ref": 1 if value > 0 else -1,
            "contributions": contributions}


def calibration_cells(*, traces: PreUpdateTraces, solution) -> dict:
    r"""The eighteen obligations of §77.7: six refinements by three architectures."""
    out = {}
    for channel in ("D_Q", "X", "P"):
        for name in REFINEMENTS:
            out[(channel, name)] = aggregate_reference(channel, traces, name, solution=solution)
    return out
