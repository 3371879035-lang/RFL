"""Exact original TD/draw function transport; physical mutation test seam."""
from rfl_rebuild.b2.training import (ExogenousEpisode, FutureTrainingProtocol, ProtocolError, MAX_REJECTION, effective_value)
from rfl_rebuild.env.kernel import (Action, START, State, initial_control, option_actions)
from rfl_rebuild.learner.store import Q, QAddress, Edit

def uniform_action(episode, i, admissible):
    ordered = tuple(sorted(admissible))
    return ordered[(episode.chi(i, 1, 0) * len(ordered)) >> 64]


def visited_order(trace, *, kappa: int, phi: int) -> tuple:
    r"""The pre-step contexts of a trace, in chronological order.

    `StepResult` carries **post**-step state and control (`kernel.py`: `state=nxt_state,
    control=nxt_control` with `nxt_t = state.t + 1`), so the pre-step context is the episode's initial
    context followed by the previous step's result:

    $$s_0 = \texttt{State}(\texttt{START}, t{=}0, \kappa, \phi), \qquad
    c_0 = \texttt{initial\_control}(\texttt{trace.option\_in\_force})$$

    The episode's $\kappa$ and $\phi$ are arguments because `RolloutTrace` does not carry them: it carries
    the steps, the outcome and the option in force. They are the episode tuple's own values, so passing
    anything else would be a different episode.
    """
    if not trace.steps:
        return ()
    state = State(x=START[0], y=START[1], t=0, kappa=kappa, phi=phi)
    control = initial_control(trace.option_in_force)
    out = []
    for result in trace.steps:
        out.append((state, control, result))
        state, control = result.state, result.control
    return tuple(out)


def sweep_edits(learner, trace, episode: ExogenousEpisode, *, protocol: FutureTrainingProtocol,
                q_reference) -> tuple:
    r"""The chronological sweep, returning **one edit per visited address** with its final value.

    $$Q^{\text{work}}_{\text{override}}(q_j) \leftarrow Q^{\text{work}}_{\text{eff}}(q_j)
    + \alpha\bigl[r_j + (1 - \mathbb{1}[\text{terminal}_j]) \max_{a' \in A_{z'}(m', s')}
    Q^{\text{work}}_{\text{eff}}(q')\bigr) - Q^{\text{work}}_{\text{eff}}(q_j)\bigr]$$

    One edit per address is forced: `apply_transaction` refuses the same address twice in one
    transaction, so a per-transition write-back would raise on a repeat and a per-transition transaction
    would make the result depend on an interleaving.
    """
    overrides = dict(learner.q_overrides)
    alpha = float(protocol.alpha)
    walk = visited_order(trace, kappa=episode.kappa, phi=episode.tape.phase)
    seen = []
    for state_j, control_j, result in walk:
        q_j = QAddress(state=state_j, z=control_j.z, m=control_j.m, a=result.a_cmd)
        current = effective_value(overrides, q_reference, q_j)
        target = float(result.reward)
        if not result.terminal:
            nxt_state, nxt_control = result.state, result.control
            admissible = option_actions(nxt_control.z, nxt_control, nxt_state)
            if admissible:
                best = max(
                    effective_value(
                        overrides, q_reference,
                        QAddress(state=nxt_state, z=nxt_control.z, m=nxt_control.m, a=a))
                    for a in admissible)
                target += best
        overrides[q_j] = current + alpha * (target - current)
        if q_j not in seen:
            seen.append(q_j)
    return tuple(Edit(store=Q, address=q, value=float(overrides[q])) for q in seen)

