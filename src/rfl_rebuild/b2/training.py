r"""A91 §79 — the training-time and episode-axis instrument.

$$\boxed{\text{kernel step index} \;\neq\; \text{training episode index}}$$

This module is the executable half of A91, the amendment frozen at `rebuild@eea5466`. It replaces the
step-indexed reading the production path used to take straight off an array
(`_levels` = a rollout's `future_rewards`, `_episode_grid` = `range(len(levels))`) with the frozen
transition system:

* a **training episode** is $W_e \to$ rollout under $\Xi_e \to$ the update of §79.4 $\to W_{e+1}$, and the
  curve's index is the episode $e$, never a within-episode step;
* the **pre-step context** is reconstructed, because `StepResult` carries *post*-step state and control:
  $s_0 = \texttt{State}(\texttt{START}, t{=}0, \kappa_e, \text{Tape}_e.\texttt{phase})$ and, critically,
  $c_0 = \texttt{initial\_control}(\texttt{trace.option\_in\_force})$ --- the option **in force**, not the
  proposal, because a $P$-architecture write makes $C_P^{L}(\zeta_e) \neq \zeta_e$;
* the **update** is a chronological sweep on a local override table read through
  $Q^{\text{work}}_{\text{eff}}(q) = Q^{\text{work}}_{\text{override}}\texttt{.get}(q, Q^{*}(q))$, with
  $\gamma = 1$, the reward alone at a terminal step, the admissible set at the bootstrap, and one edit per
  visited address carrying the final effective value (the store canonicalises an equal-to-reference value
  to a deletion);
* **ordinary training writes $Q$ only** --- the process, controller and decision stores carry the initial
  B1 write and nothing else;
* **exploration** is integer-only: an exact rational coin $R_0 q < p\,2^{64}$ and a stateless keyed
  rejection draw for an exactly uniform action index, keyed by $(e, i)$ so paired arms share variates by
  coordinate rather than by consumption order;
* **checkpoint evaluation is greedy and read-only**: it makes zero calls to the draw generator, and
  $m(W; u) = \texttt{trace.return\_value}$ per scene with $V$ the evaluation-sample mean, so
  $V(W^{\varnothing}; Q^{*}) = V_{\text{pre}}$ is the same operator.

What this module deliberately does not decide: the acquisition cap, the grid, the evaluation sample's
ordering, $\alpha$ and $\varepsilon_{\text{explore}}$ --- those are $F_0$/$F_1$ quantities, and
`TrainingProtocol` carries them as declared inputs rather than inventing them here.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.env.kernel import (
    HORIZON,
    START,
    Action,
    ControlState,
    SemanticTape,
    State,
    initial_control,
    option_actions,
    option_ids,
    rollout,
)
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.learner.store import Q, Edit, LearnerPersistentState, QAddress

__all__ = [
    "M64",
    "TAGS",
    "Curve",
    "ExogenousEpisode",
    "TrainingProtocol",
    "effective_value",
    "episode_rollout",
    "is_explore",
    "key",
    "mix",
    "pre_level",
    "sweep_edits",
    "train_curve",
    "u64",
    "uniform_action",
    "visited_order",
]

M64 = (1 << 64) - 1
_G = 0x9E3779B97F4A7C15
_P = 0xD1B54A32D192ED03
_F1 = 0xBF58476D1CE4E5B9
_F2 = 0x94D049BB133111EB

#: One tag per purpose. This separates the *inputs*; the derivation is not claimed collision-free.
TAGS = {"kappa": 1, "option": 2, "tape": 3, "explore": 4}

#: The rejection loop is bounded by rule, not by probability.
MAX_REJECTION = 1 << 32


def u64(x: int) -> int:
    r"""$$\operatorname{u64}(x) = x \ \&\ (2^{64} - 1)$$"""
    return x & M64


def mix(x: int) -> int:
    r"""SplitMix64's finalizer, with every step wrapped and the shift counts written out.

    $$\operatorname{mix}(x) = \operatorname{u64}\bigl(z \oplus (z \gg 31)\bigr), \quad
    z = \operatorname{u64}\bigl((z' \oplus (z' \gg 27)) \cdot \texttt{0x94D049BB133111EB}\bigr), \quad
    z' = \operatorname{u64}\bigl((\operatorname{u64}(x) \oplus (\operatorname{u64}(x) \gg 30)) \cdot
    \texttt{0xBF58476D1CE4E5B9}\bigr)$$
    """
    z = u64(x)
    z = u64((z ^ (z >> 30)) * _F1)
    z = u64((z ^ (z >> 27)) * _F2)
    return u64(z ^ (z >> 31))


def key(seed: int, episode: int, tag: int) -> int:
    r"""$\mathsf{h}(\sigma, e, \text{tag})$, with the affine arithmetic wrapped too."""
    return mix(u64(u64(seed * _G) + u64(episode * _P) + tag))


@dataclass(frozen=True, slots=True)
class ExogenousEpisode:
    r"""$\Xi_e = (\kappa_e, \zeta_e, \text{Tape}_e)$ plus the keyed exploration variates.

    A tape is not an episode: `SemanticTape.sample` draws only the tape's three keys, so the seed's stream
    must also supply $\kappa$ and the proposal option. Both arms of a pair share $\Xi_e$ for the same
    $(\sigma, e)$.
    """

    seed: int
    episode: int
    kappa: int
    proposal: int
    tape: SemanticTape

    @staticmethod
    def derive(seed: int, episode: int) -> "ExogenousEpisode":
        if episode < 0:
            raise ProtocolError(f"a training episode index is non-negative, got {episode}")
        return ExogenousEpisode(
            seed=int(seed),
            episode=int(episode),
            kappa=key(seed, episode, TAGS["kappa"]) % 2,
            proposal=key(seed, episode, TAGS["option"]) % len(option_ids()),
            tape=SemanticTape.sample(key(seed, episode, TAGS["tape"])),
        )

    def chi(self, i: int, j: int, c: int) -> int:
        r"""$\chi_e(i, j, c)$: the 64-bit variate at coordinate $(i, j)$ under rejection counter $c$.

        $$\chi_e(i,j,c) = \operatorname{mix}\Bigl(\operatorname{u64}\bigl(\mathsf{h}(\sigma, e, 4)
        \oplus \operatorname{mix}\bigl(\operatorname{u64}\bigl(\operatorname{u64}(2i + j) \cdot
        2^{32}\bigr) + \operatorname{u64}(c)\bigr)\bigr)\Bigr)$$
        """
        if i < 0 or j not in (0, 1) or c < 0:
            raise ProtocolError(f"exploration coordinate ({i}, {j}, {c}) is outside the frozen domain")
        packed = u64(u64(u64(2 * i + j) * (1 << 32)) + u64(c))
        return mix(u64(key(self.seed, self.episode, TAGS["explore"]) ^ mix(packed)))

    def coin(self, i: int) -> int:
        return self.chi(i, 0, 0)


def is_explore(coin: int, epsilon: Fraction) -> bool:
    r"""$$\text{explore} \iff R_0 \, q < p \, 2^{64} \qquad (\varepsilon = p/q \text{ exact})$$"""
    if not isinstance(epsilon, Fraction):
        raise ProtocolError(
            f"the exploration probability must be an exact rational (F0 declares it as p/q), got "
            f"{type(epsilon).__name__}")
    if not 0 < epsilon <= 1:
        raise ProtocolError(f"eps_explore must satisfy 0 < eps <= 1, got {epsilon}")
    return coin * epsilon.denominator < epsilon.numerator * (1 << 64)


def uniform_action(episode: ExogenousEpisode, i: int, admissible: tuple) -> Action:
    r"""An **exactly uniform** draw over the admissible set by stateless keyed rejection.

    $$L = 2^{64} - (2^{64} \bmod n), \qquad \text{smallest } c \ge 0 \text{ with } R_c < L, \qquad
    a = A_{\text{sorted}}\bigl[R_c \bmod n\bigr]$$

    Dividing a 64-bit draw by $2^{64}$ and flooring is *not* this: when $n \nmid 2^{64}$ the action
    pre-image counts differ by one, and the largest draws can round to $1.0$ and index past the end.
    """
    if not admissible:
        raise ProtocolError("the admissible set is empty; exploration has nothing to draw from")
    ordered = tuple(sorted(admissible))
    if tuple(admissible) != ordered:
        raise ProtocolError("the admissible set must be presented in ascending action-id order")
    n = len(ordered)
    limit = (1 << 64) - ((1 << 64) % n)
    for c in range(MAX_REJECTION):
        r = episode.chi(i, 1, c)
        if r < limit:
            return ordered[r % n]
    raise ProtocolError("the keyed rejection loop exhausted 2**32 draws; failing closed")


def effective_value(overrides, q_reference, address: QAddress) -> float:
    r"""$$Q^{\text{eff}}(q) = \text{overrides}\texttt{.get}\bigl(q,\ Q^{*}(q)\bigr)$$

    A sparse override table is *not* a full table: an absent address has the reference's value.
    """
    stored = overrides.get(address)
    return q_reference.value(address) if stored is None else float(stored)


@dataclass(frozen=True, slots=True)
class TrainingProtocol:
    r"""The declared inputs of a training run. Design quantities arrive here; none is chosen here.

    * $\alpha$, $\varepsilon_{\text{explore}}$ --- pre-data $F_0$ constants, $\varepsilon$ as an exact
      rational;
    * `cap` --- the acquisition cap on the episode axis, which is also $T_{\max}$ for this run;
    * `grid` --- $\mathcal G_{\text{ckpt}}$ on real episode indices; A84's span contract is enforced
      ($grid[0] = 0$, $grid[-1] = cap$, strictly increasing, integers);
    * `evaluation_sample` --- the measurement sample, read only.
    """

    seed: int
    alpha: Fraction
    epsilon: Fraction
    cap: int
    grid: tuple
    evaluation_sample: tuple
    horizon: int = HORIZON

    def __post_init__(self) -> None:
        if not 0 < self.alpha <= 1:
            raise ProtocolError(f"alpha must satisfy 0 < alpha <= 1, got {self.alpha}")
        if not isinstance(self.epsilon, Fraction):
            raise ProtocolError("eps_explore must be an exact rational")
        if not 0 < self.epsilon <= 1:
            raise ProtocolError(f"eps_explore must satisfy 0 < eps <= 1, got {self.epsilon}")
        if not isinstance(self.cap, int) or isinstance(self.cap, bool) or self.cap < 1:
            raise ProtocolError(f"the acquisition cap must be a positive integer, got {self.cap!r}")
        grid = tuple(self.grid)
        if len(grid) < 3:
            raise ProtocolError(
                f"the checkpoint grid carries {len(grid)} checkpoint(s); K = 3's maintained-recovery "
                "window needs at least three")
        for t in grid:
            if not isinstance(t, int) or isinstance(t, bool):
                raise ProtocolError(f"the checkpoint grid holds {t!r}, not an integer episode index")
        if tuple(sorted(grid)) != grid or len(set(grid)) != len(grid):
            raise ProtocolError(f"the checkpoint grid must be strictly increasing, got {grid}")
        if grid[0] != 0 or grid[-1] != self.cap:
            raise ProtocolError(
                f"the curve must span the horizon (A84): grid[0] = 0 and grid[-1] = cap, got {grid} with "
                f"cap = {self.cap}")
        if not self.evaluation_sample:
            raise ProtocolError("the evaluation sample is empty; V would be a mean of nothing")
        object.__setattr__(self, "grid", grid)
        object.__setattr__(self, "evaluation_sample", tuple(self.evaluation_sample))


@dataclass(frozen=True, slots=True)
class Curve:
    r"""The training-episode curve: values on real episode indices, plus the shared pre-level."""

    values: tuple
    episodes: tuple
    pre_level: float
    t_max: int

    def __post_init__(self) -> None:
        if len(self.values) != len(self.episodes):
            raise ProtocolError("a curve needs one value per checkpoint")
        if self.episodes[-1] != self.t_max or self.episodes[0] != 0:
            raise ProtocolError(
                f"A84's span contract: episodes[0] = 0 and episodes[-1] = t_max, got "
                f"{self.episodes[0]}..{self.episodes[-1]} with t_max = {self.t_max}")


def _behaviour_provider(learner, episode: ExogenousEpisode, protocol: TrainingProtocol, q_reference):
    """The **training** behaviour policy: ε-greedy over the effective table, draws keyed by step."""
    greedy = learner.snapshot().q_decision_provider(q_reference)
    draws = {"i": 0}

    def provider(state: State, control: ControlState) -> Action:
        i = draws["i"]
        draws["i"] = i + 1
        admissible = tuple(option_actions(control.z, control, state))
        if is_explore(episode.coin(i), protocol.epsilon):
            return uniform_action(episode, i, admissible)
        return greedy(state, control)

    return provider


def episode_rollout(learner, episode: ExogenousEpisode, *, protocol: TrainingProtocol, q_reference):
    r"""One training episode, rolled out against the **frozen** learner state $W_e$.

    No update happens inside the episode, so the trace is a function of $(W_e, \Xi_e)$ alone.
    """
    snapshot = learner.snapshot()
    provider = _behaviour_provider(learner, episode, protocol, q_reference)
    return rollout(
        kappa=episode.kappa,
        tape=episode.tape,
        command_provider=provider,
        base_option=episode.proposal,
        controller=snapshot.controller_mapping(),
        learner_process_commit=snapshot.process_commit_provider(),
        reward_mode="A",
    )


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


def sweep_edits(learner, trace, episode: ExogenousEpisode, *, protocol: TrainingProtocol,
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


def pre_level(sample, *, q_reference) -> float:
    r"""$$V(W^{\varnothing}; Q^{*}) = V_{\text{pre}}: \text{ the frozen operator at the healthy state}$$"""
    healthy = LearnerPersistentState()
    return _mean_return(healthy, sample, q_reference=q_reference)


def _mean_return(learner, sample, *, q_reference) -> float:
    total = 0.0
    for scene in sample:
        trace = learned_rollout(learner, kappa=scene.kappa, tape=scene.tape,
                               base_option=scene.base_option, q_reference=q_reference)
        total += trace.return_value
    return total / len(sample)


def train_curve(learner, *, protocol: TrainingProtocol, q_reference) -> Curve:
    r"""Run $e = 0 \ldots \text{cap}$, evaluating $V(e)$ at the grid's checkpoints.

    $V(e)$ is the level of $W_e$ --- the state the learner **enters** episode $e$ with --- so the curve is
    a function of the training path and not of the measurement schedule. Evaluation is greedy and
    read-only: it never draws from the episode generator and never writes to the learner.
    """
    working = learner
    values = []
    grid = set(protocol.grid)
    for e in range(protocol.cap + 1):
        if e in grid:
            values.append(_mean_return(working, protocol.evaluation_sample, q_reference=q_reference))
        if e == protocol.cap:
            break
        episode = ExogenousEpisode.derive(protocol.seed, e)
        trace = episode_rollout(working, episode, protocol=protocol, q_reference=q_reference)
        edits = sweep_edits(working, trace, episode, protocol=protocol, q_reference=q_reference)
        if edits:
            working.apply_transaction(edits, q_reference=q_reference)
    return Curve(values=tuple(values), episodes=tuple(protocol.grid),
                 pre_level=pre_level(protocol.evaluation_sample, q_reference=q_reference),
                 t_max=protocol.cap)
