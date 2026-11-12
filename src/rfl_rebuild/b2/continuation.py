r"""A87 §75.6 — the $U_1$ continuation instrument: one core, and an entry that cannot recommit.

$$\boxed{(W,\ s,\ z,\ m,\ \text{exogenous continuation}) \;\longrightarrow\;
\text{the suffix of a kernel rollout}}$$

Three properties are **structural** here rather than documented, because each of them is something a
plausible implementation gets wrong while still passing a scalar comparison:

* **one simulator.** This module never re-implements the step loop or the trace. It calls
  `kernel.continue_rollout`, the same core that `kernel.rollout` calls once it has resolved the
  commit edge. Two implementations that agree are still two implementations, so the entry point
  exists to be *the same code path*, not a matching one;
* **no re-execution of $C_P^{L}$ (§75.6 (iv)).** The entry takes $z$ as already in force and has no
  process-commit parameter at all: `process_commit_provider()` is not called anywhere in this module,
  and a gate in `tests/rebuild/test_b2_continuation.py` refuses a version that would reach for it or
  go back through `rollout`. Without that, a continuation would manufacture the very sensitivity the
  screening is meant to test for;
* **a legal entry (§75.6 (i), (ii)).** The entry must satisfy the frozen
  `env.domain.is_decision_context`, and the exogenous continuation must agree with it --
  `tape.phase == s.phi` and `kappa == s.kappa` -- because the kernel derives the episode's phase from
  the tape, so a mismatch describes a suffix the frozen environment cannot produce;
* **a closed measurement signature.** The entry takes **no reward mode** and **no tape other than**
  $\lambda_{U_1}$. A87 §75.3 makes reward mode A part of the functional and §75.4 makes the lift part
  of the protocol, so leaving either one as an argument would reopen
  $u \mapsto V$ as a relation rather than a function -- the defect $\lambda_{U_1}$ exists to close.
  The generic kernel core keeps both freedoms on purpose; this instrument, which is the frozen B2
  measurement, does not.

$$\boxed{\text{generic kernel core} \;\neq\; \text{frozen B2 measurement instrument}}$$

`exogenous_lift` is $\lambda_{U_1}$ of §75.4: the frozen, deterministic completion that makes
$u \mapsto V$ a function instead of a relation. It is a **measurement-protocol input, not unit
identity**: it never enters $\mathcal X_D$ and never appears in a cell's name.

$\Sigma_{\text{suffix}}$ is the frozen comparison object of the equivalence gates. $V_W$ is derived
from it and is never compared in its place, since two internally different simulators can return the
same scalar.
"""

from __future__ import annotations

from dataclasses import dataclass

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.env.domain import is_decision_context
from rfl_rebuild.env.kernel import (
    ControlState,
    RolloutTrace,
    SemanticTape,
    State,
    continue_rollout,
)
from rfl_rebuild.b2.environment import learner_channels
from rfl_rebuild.learner.store import LearnerPersistentState

__all__ = [
    "ContinuationContractError",
    "SuffixSignature",
    "continuation",
    "exogenous_lift",
    "sigma_suffix",
    "suffix_from",
]


class ContinuationContractError(ProtocolError):
    """The instrument was handed an entry or an exogenous continuation it may not accept."""


def exogenous_lift(state: State, z: int, m: int) -> SemanticTape:
    r"""$\lambda_{U_1}$ — A87 §75.4's frozen lift, one complete tape assignment per context.

    $$\boxed{\lambda_{U_1}(s,z,m) := \texttt{SemanticTape}\bigl(\text{phase} = s.\phi,\
    \texttt{error\_flag} = 0,\ \texttt{cause\_rank} = 0\bigr)}$$

    $U_1$'s identity is $(s,z,m)$, so $V_W$ must be a function of $(s,z,m)$ alone while the
    continuation also consumes a complete tape. Rather than enlarge the candidate's ontology to
    $(s,z,m,e,r)$, one completion is frozen -- applied identically to the pre and post measurement.
    A86 §74.1 refuses to omit `error_flag` or `cause_rank` from $U_2$'s tape without a proof that
    neither can affect $V_W$; this module does not apply the opposite standard inside $U_1$.
    """
    if type(state) is not State:
        raise ContinuationContractError(
            f"the lift is defined on a State, got {type(state).__name__}")
    return SemanticTape(phase=state.phi, error_flag=0, cause_rank=0)


@dataclass(frozen=True, slots=True)
class SuffixSignature:
    r"""$\Sigma_{\text{suffix}} = (\texttt{steps},\ \texttt{outcome},\ \texttt{final control})$.

    The frozen comparison object: the behaviour-bearing suffix signature, compared object by object
    and field by field. `StepResult` is a frozen dataclass, so tuple equality here is a full
    per-field comparison of the trajectory -- states, controls, commands, realized actions, rewards,
    terminality and outcome -- and not a summary statistic standing in for one.
    """

    steps: tuple
    outcome: object
    control: ControlState


def sigma_suffix(trace: RolloutTrace) -> SuffixSignature:
    """The signature of a whole trace, which is the suffix of a continuation entered at $t = 0$."""
    if type(trace) is not RolloutTrace:
        raise ContinuationContractError(f"not a rollout trace: {type(trace).__name__}")
    return SuffixSignature(steps=tuple(trace.steps), outcome=trace.outcome, control=trace.control)


def suffix_from(trace: RolloutTrace, start: int) -> SuffixSignature:
    """The ordinary rollout's suffix from step ``start``: the other side of gates G1, G2 and G4."""
    if type(trace) is not RolloutTrace:
        raise ContinuationContractError(f"not a rollout trace: {type(trace).__name__}")
    if not isinstance(start, int) or isinstance(start, bool) or not 0 <= start <= len(trace.steps):
        raise ContinuationContractError(f"step index {start!r} is outside the trace")
    return SuffixSignature(
        steps=tuple(trace.steps[start:]), outcome=trace.outcome, control=trace.control)


def continuation(
    *,
    learner: LearnerPersistentState,
    state: State,
    z: int,
    m: int,
    kappa: int,
    tape: SemanticTape,
    q_reference,
) -> RolloutTrace:
    r"""Measure the learner's future from the decision context $(s,z,m)$ — §75.6's entry point.

    $$\boxed{\text{entry} \to \text{the channels of } W \to \texttt{continue\_rollout} \to
    \text{the suffix}}$$

    The option is taken as **already in force**: the commit edge is not run, and no parameter of
    this function can make it run. The four learner channels are read through the same
    `learner_channels` helper the ordinary rollout uses, so $D_Q^L$ and $C_X^L$ reach the
    continuation exactly as they reach the rollout -- an instrument that quietly used the reference
    provider would report candidate blindness that belongs to the harness.

    The measurement is closed, so that $u \mapsto V$ is a **function**:

    * ``tape`` must be exactly $\lambda_{U_1}(s,z,m)$, not merely phase-compatible. A tape that
      agrees on the phase but differs in `error_flag` or `cause_rank` is a *different* legal
      completion of the same unit, and accepting it would restore the freedom §75.4 removed. That
      `error_flag`/`cause_rank` happen not to move the current physics is deliberately not relied
      on -- if that were the argument, $\lambda_{U_1}$ would not have been needed;
    * the reward mode is fixed to ``"A"`` by §75.3 and is not an argument. A caller that could pass
      ``"B"`` could form two different scalars for one $u$.

    Rejected: a non-context entry, a state that is not strictly typed, a tape that is not the lift,
    a $\kappa$ that disagrees with the entry, and a learner that is not a persistent state.
    """
    if type(learner) is not LearnerPersistentState:
        raise ContinuationContractError(
            f"the continuation reads a learner state, got {type(learner).__name__}")
    if type(state) is not State:
        raise ContinuationContractError(f"the entry is a State, got {type(state).__name__}")
    if not is_decision_context(state, z, m):
        raise ContinuationContractError(
            f"({state}, z={z!r}, m={m!r}) is not a legal decision context: the entry must be a "
            "member of X_D by the frozen enumerator, not merely a State with an option")
    if type(kappa) is not int or type(state.kappa) is not int or kappa != state.kappa:
        raise ContinuationContractError(
            f"kappa={kappa!r} disagrees with the entry's kappa={state.kappa!r}: the exogenous "
            "continuation must be the episode the entry claims to be in")
    if type(tape) is not SemanticTape:
        raise ContinuationContractError(f"the tape is a SemanticTape, got {type(tape).__name__}")
    expected = exogenous_lift(state, z, m)
    if tape != expected:
        raise ContinuationContractError(
            f"the exogenous continuation must be lambda_U1(s,z,m); got phase={tape.phase!r}, "
            f"error_flag={tape.error_flag!r}, cause_rank={tape.cause_rank!r} but the lift is "
            f"phase={expected.phase!r}, error_flag={expected.error_flag!r}, "
            f"cause_rank={expected.cause_rank!r}. Any other completion makes u -> V a relation")

    snapshot = learner.snapshot()
    command_provider, controller = learner_channels(snapshot, q_reference)
    return continue_rollout(
        state=state,
        control=ControlState(z=z, m=m),
        tape=tape,
        command_provider=command_provider,
        # Provenance only: a continuation has no proposal distinct from the option in force, because
        # the commit edge it would have to consult is deliberately not part of this path.
        base_option=z,
        option_in_force=z,
        controller=controller,
        # §75.3: reward mode A is part of the frozen functional, so it is not a parameter here.
        reward_mode="A",
    )
