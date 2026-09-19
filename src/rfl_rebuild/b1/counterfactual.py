r"""A77 §65.7 — $G_t^{CF}$, the counterfactual target, and its provenance.

**Not a suffix simulator.** One full-episode replay from $t = 0$ under the factual
episode's own configuration, differing in **exactly one** thing:

$$\boxed{\text{config}^{CF} = \bigl(\kappa, \tau, \text{mask}, z^{\text{fault}}, z_0,
\text{controller}, C_P^L, \texttt{DecisionReadView}_{pre}, \text{mode A}\bigr)
\equiv \text{config}^{F}}$$

$$\boxed{\text{interventions}^{CF} = \bigl(\text{interventions}^{F} \setminus
\{do(d_t{=}\cdot)\}\bigr) \cup \{do(d_t = a_t^+)\}}$$

so an existing decision intervention at $t$ is **replaced**, never doubled
(`InterventionSet` refuses two members on one structural node). Then

$$\boxed{G_t^{CF}(a_t^+) = \sum_{j=t}^{T_{CF}-1} r_j^{CF}}$$

by the same **frozen reverse Bellman fold** as $G_t^F$ — ``sum``, ``math.fsum``,
reordering and epsilon are all prohibited here. (The ledger's $\Sigma$ *may* use
``fsum``; that is a different semantic layer, and A77 says so explicitly.)

**Provenance is structural, not checked.** The direction is

$$\boxed{\text{config} \to \text{factual rollout} \to \text{same config} +
\text{replace } do(d_t) \to \text{CF rollout}}$$

and *not* "here is a trace, and here is a configuration filled in afterwards that is
supposed to match it". The difference is not stylistic. With a supplied trace, a
configuration can disagree with it in any field that happens to make no difference on the
*factual* path — a different tape, a different mask, a different controller, a fault that
bites only after $t$ — and every check written against the factual path passes while the
replay faithfully uses the wrong configuration. That is not hypothetical here: the one
non-reference counterfactual measured on a fresh store is exactly a suffix-realization
effect, so suffix-only differences are a live category rather than a pedantic one.

So ``factual_trace`` is an ``init=False`` field: it is *produced by* the configuration in
``__post_init__`` and cannot be supplied. The hostile case is not detected — it is
**unconstructible**.

**The learner channels come from one snapshot.** $(\texttt{DecisionReadView}_{pre},
C_P^L, C_X^L)$ are all derived from a single frozen ``LearnerSnapshot`` rather than
accepted as three unrelated callables, so a decision view from one learner cannot be
mixed with a process-commit provider from another. And the snapshot is bound to the state
the write lands in: :func:`~rfl_rebuild.b1.runner.run_dq_law` requires

$$\boxed{fp(\texttt{pre\_state}) = fp(\texttt{episode.snapshot\_pre})}$$

before constructing any L2 target. A clone passes; a *different learner* is a protocol
error — otherwise the arm would observe learner $A$'s experience, compute learner $A$'s
target, and train learner $B$.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Mapping, Sequence

from rfl_rebuild.b1.contract import ProtocolError
from rfl_rebuild.b1.factual import (
    context_index,
    facts_for,
    factual_return_to_go,
    is_finite_real,
)
from rfl_rebuild.b1.targets import build_target_envelope, validate_envelope
from rfl_rebuild.env import kernel as K
from rfl_rebuild.env.observation import learner_rows
from rfl_rebuild.learner.store import LearnerSnapshot, require_q_reference

__all__ = [
    "CfEpisode",
    "CounterfactualUndefined",
    "CounterfactualTarget",
    "build_counterfactual_envelope",
    "replay_with_decision_replaced",
    "validate_counterfactual_envelope",
]


@dataclass(frozen=True, slots=True)
class CfEpisode:
    r"""The factual episode's configuration, from which the factual episode is generated.

    ``snapshot_pre`` is the pre-update learner **as a frozen snapshot**: the object whose
    policy the factual episode ran under and whose successor this arm is about to update.
    ``reference`` is the injected $Q_D^\ast$ view, needed because the decision channel of
    a $D_Q$ learner is defined against it.
    """

    kappa: int
    tape: object
    snapshot_pre: object
    reference: object
    mask: object = K.FaultMask()
    option_fault: int | None = None
    base_option: int = 1
    interventions: object = K.InterventionSet()
    reward_mode: str = "A"

    # Derived, and deliberately not constructible: see the module docstring.
    decision_read_view_pre: object = field(default=None, init=False, repr=False,
                                           compare=False)
    process_commit_provider: object = field(default=None, init=False, repr=False,
                                            compare=False)
    controller_mapping: object = field(default=None, init=False, repr=False,
                                        compare=False)
    factual_trace: object = field(default=None, init=False, repr=False, compare=False)

    @property
    def phi(self) -> int:
        r"""$\\varphi$, **derived** from the tape rather than accepted beside it.

        $$\\boxed{\\texttt{episode.phi} := \\texttt{tape.phase}}$$

        The kernel schedules from ``tape.phase`` while ``learner_rows`` labels rows from the
        episode's ``phi``. Two fields would let a caller run in one phase and label the
        evidence with another, and ``_factual_rows`` could not notice, because it would
        reconstruct with the same wrong field. A checked pair is weaker than one source, so
        there is one source.
        """
        return self.tape.phase

    def __post_init__(self) -> None:
        if self.reward_mode != "A":
            # A76 freezes the primary B1 on reward mode A. A secondary mode is a separate
            # study; accepting the string here would silently move the target's meaning.
            raise ProtocolError(
                f"reward_mode={self.reward_mode!r}; the primary B1 is frozen on mode A "
                "(A76), and a target built under another mode is a different quantity")
        require_q_reference(self.reference)
        if type(self.snapshot_pre) is not LearnerSnapshot:
            raise ProtocolError(
                f"snapshot_pre is {type(self.snapshot_pre).__name__}, not a "
                "LearnerSnapshot; the pre-update learner must be a frozen snapshot so that "
                "the three learner channels come from one state")
        # One snapshot, three channels.
        object.__setattr__(self, "decision_read_view_pre",
                           self.snapshot_pre.q_decision_provider(self.reference))
        object.__setattr__(self, "process_commit_provider",
                           self.snapshot_pre.process_commit_provider())
        object.__setattr__(self, "controller_mapping",
                           self.snapshot_pre.controller_mapping())
        # config -> factual rollout. The trace is this configuration's, by construction.
        object.__setattr__(self, "factual_trace", self.replay())

    def replay(self, t: int | None = None, action: int | None = None):
        r"""A full rollout under this configuration.

        With ``t``/``action`` given, the decision at $t$ is **replaced** by
        $do(d_t = \text{action})$; with neither, this is the factual episode.

        **The mask is held fixed.** A77 §65.7 lists ``mask`` inside the configuration that
        is identical between the factual and counterfactual episodes, and only
        ``interventions`` gets the replacement. So a factual world with
        $\text{mask.decision} = Z_D(t)$ keeps that fault assignment, and the counterfactual
        is

        $$\boxed{\text{same fault assignment} + do(d_t = a_t^+)}$$

        with the kernel's frozen precedence

        $$\boxed{do(d_t) \;>\; Z_D \;>\; \texttt{command\_provider}}$$

        shadowing the fault's effect **at that structural node** — a Pearl-style
        intervention on the node, not a deletion of the fault from the world. Removing the
        mask entry instead would make $\text{mask}^{CF} \neq \text{mask}^{F}$: the same
        numbers today, because the shadowing already produces them, but a different SCM and
        therefore a different experiment.

        An earlier revision of this module did exactly that removal, reasoning that
        "exactly one thing differs" should be structural rather than dependent on a
        precedence rule. The reasoning was wrong in its premise: the precedence is frozen
        kernel semantics, and holding the fault assignment fixed is what the clause
        requires. The counterfactual trace is what verifies both halves — the mask is the
        factual one *and* the command at $t$ is $a_t^+$.
        """
        interventions = self.interventions
        if t is not None:
            members = tuple(iv for iv in interventions.members
                            if not (iv.kind == "decision" and iv.t == t))
            interventions = K.InterventionSet(
                members + (K.Intervention.decision(t, action),))
        return K.rollout(
            kappa=self.kappa,
            tape=self.tape,
            command_provider=self.decision_read_view_pre,
            base_option=self.base_option,
            mask=self.mask,
            option_fault=self.option_fault,
            interventions=interventions,
            controller=self.controller_mapping,
            learner_process_commit=self.process_commit_provider,
            reward_mode=self.reward_mode,
        )


@dataclass(frozen=True, slots=True)
class CounterfactualTarget:
    r"""$L_2$'s record: the factual pair **and** the counterfactual pair.

    $a_t^+$ and $G_t^{CF}$ are both ``None`` or both present; the validator enforces that,
    because "the alternative is unknown" and "its return is unknown" are the same
    scientific fact and must not be expressible separately.
    """

    address: object
    a_factual: int
    g_factual: float
    a_plus: int | None
    g_cf: float | None


def replay_with_decision_replaced(episode: CfEpisode, t: int, action: int):
    r"""The counterfactual rollout: this configuration, one intervention replaced."""
    return episode.replay(t, action)


def _counterfactual_facts(episode: CfEpisode, rows: Sequence, t: int,
                          a_plus: int) -> float:
    r"""$G_t^{CF}(a_t^+)$, with the prefix invariant enforced before the number exists."""
    cf_rows = learner_rows(episode.replay(t, a_plus), episode.kappa, episode.phi)
    if len(cf_rows) <= t:
        raise ProtocolError(
            f"the counterfactual replay ended at step {len(cf_rows)} and never reached "
            f"t={t}; a counterfactual to a step the replay does not visit is undefined")
    prefix_f = tuple(rows)[:t]
    prefix_cf = cf_rows[:t]
    if prefix_cf != prefix_f:
        # An INVARIANT ASSERTION rather than a live detector, and said so plainly: because
        # the configuration generates both rollouts, and the intervention at t cannot
        # affect a step before t, this equality holds by construction. Deleting the check
        # is therefore undetectable by any test -- an earlier revision carried a mutation
        # for it, and that mutation is now NOT_A_GATE, which is how this became visible.
        # It is kept because the argument rests on the kernel consuming its tape and its
        # state per step; `test_6` verifies the premise empirically across the support, so
        # a future change that breaks it is caught there rather than here.
        first = next((i for i, (a, b) in enumerate(zip(prefix_cf, prefix_f)) if a != b),
                     min(len(prefix_cf), len(prefix_f)))
        raise ProtocolError(
            f"the counterfactual replay does not share the factual prefix at t={t}: "
            f"first divergence at step {first}. The two traces must agree on everything "
            "before the intervention, or the counterfactual is not counterfactual to "
            "*this* episode (A77 §65.7)")
    return factual_return_to_go(cf_rows, t)


def _factual_rows(episode: CfEpisode, rows: Sequence) -> tuple:
    """The configuration's own factual rows, with the supplied rows checked against them.

    This is the check a *supplied* trace could never make meaningful: the trace here is
    generated by the configuration, so equality means the caller is working on this
    episode rather than on a trace that merely resembles it on the factual path.
    """
    own = learner_rows(episode.factual_trace, episode.kappa, episode.phi)
    if own != tuple(rows):
        raise ProtocolError(
            "the rows handed to the counterfactual builder are not the rows of THIS "
            "configuration's factual rollout: the configuration generates the factual "
            "episode, so the caller is working on a different episode's evidence")
    return own


class CounterfactualUndefined(ProtocolError):
    r"""This configuration has no counterfactual at this address.

    Raised when the counterfactual replay is refused because a **later decision
    intervention** is inadmissible on the diverged path: the factual episode's own mask was
    verified at the factual context, but the counterfactual reaches that later step in a
    different state, where the masked action escapes the option in force.

    That is not a $D_Q$ write status, and it is deliberately not reported as one. A76's
    four statuses describe what an arm *did*; this describes a scene in which the
    counterfactual **has no definition**, so the whole envelope is a protocol failure
    rather than a verified absence at one address — the same rule as a missing record.

    A ``ProtocolError`` subclass, so callers that treat every protocol failure alike keep
    working, while an experiment can exclude such scenes *by name and count*.
    """


def _apply_or_fail(episode: CfEpisode, rows: Sequence, t: int, alt: int) -> float:
    r"""$G_t^{CF}(a_t^+)$, or a failure that names its cause.

    Two different refusals can come out of the kernel, and conflating them is what an
    earlier revision of this file got wrong:

    * **the verified $a_t^+$ itself.** The shared adapter established
      $a_t^+ \in A_z(m_t, s_t)$ at the factual context (A76 §63.3 selects from the
      option-admissible row, and ``validate_envelope`` re-checks membership), and the
      counterfactual reaches step $t$ with the same context because the prefix is
      identical. A refusal here means an invariant has been violated, so it is a bare
      ``ProtocolError``.
    * **a later decision intervention.** The factual episode's own mask is verified only at
      the *factual* context, and the diverged path reaches that later step in a different
      state → :class:`CounterfactualUndefined`.

    They are separated by re-running the replay with the other decision interventions
    removed: if it still fails, the fault is $a_t^+$'s.

    This is also why the earlier "swallow it and report ``NO_VALID_ALTERNATIVE``" reading
    was rejected. It invented a fifth meaning for a frozen status, and it would have turned
    the shared adapter's $a_t^+ \neq \bot$ into an $L_2$ envelope's $a_t^+ = \bot$, so the
    patch architecture would see an alternative the $Q$ architecture did not — breaking
    "$a^+$ identical across architectures".
    """
    try:
        return _counterfactual_facts(episode, rows, t, alt)
    except K.MalformedIntervention as exc:
        # DIAGNOSTIC ONLY. This stripped re-run exists to answer one question -- was the
        # refusal about a_t^+ itself, or about a later decision entry on the diverged path?
        # -- and it is never the counterfactual: the counterfactual is defined by the
        # factual configuration, mask included, with one do intervention. Removing the
        # fault assignments here does not change what is measured; it only separates two
        # error causes.
        stripped = replace(
            episode,
            mask=replace(episode.mask, decision=None),
            interventions=K.InterventionSet(
                tuple(iv for iv in episode.interventions.members
                      if iv.kind != "decision")))
        try:
            stripped.replay(t, alt)
        except K.MalformedIntervention:
            raise ProtocolError(
                f"the verified alternative a_t^+={alt!r} at t={t} was refused by the "
                f"kernel as an intervention: {exc}. The shared adapter established that it "
                "is admissible at the factual context and the counterfactual shares that "
                "prefix, so this is an invariant violation rather than a no-write state "
                "(A76 §63.3)") from exc
        raise CounterfactualUndefined(
            f"the counterfactual of this configuration has no definition at t={t}: a "
            f"later decision intervention is inadmissible on the diverged path ({exc}). "
            "The factual mask is verified at the factual context, and the counterfactual "
            "reaches that step in a different state. A scene-level protocol failure, not "
            "a write status (A76 §63.3): the envelope is invalid as a whole, because a "
            "missing counterfactual is not a verified absence") from exc


def build_counterfactual_envelope(rows: Sequence, addresses: Sequence, *,
                                  sol, episode: CfEpisode,
                                  ) -> Mapping:
    r"""The $L_2$ adapter: $F_t$ and $(a_t^+, G_t^{CF})$ for every credited context.

    Two evaluator-side reads are involved and both are named: ``sol`` supplies $a_t^+$
    through the *same* adapter every other arm uses (A76 §63.3), and ``episode`` supplies
    the factual configuration for the replay. The learner-visible half still comes from
    ``rows``.
    """
    index = context_index(rows)
    _factual_rows(episode, rows)
    patch = build_target_envelope(sol, addresses, episode.factual_trace, episode.kappa,
                                  episode.phi)
    validate_envelope(addresses, patch)
    out: dict = {}
    for a in addresses:
        facts = facts_for(rows, index, a)
        alt = patch[a].alternative
        if alt is None:
            # A76 §63.3's live guard: no verified alternative exists, so this address has
            # no counterfactual. `DualReturnWrite` must NOT fall back to writing only its
            # factual half -- "a law may not degenerate at the same address".
            out[a] = CounterfactualTarget(a, facts.a_factual, facts.g_factual, None, None)
            continue
        out[a] = CounterfactualTarget(a, facts.a_factual, facts.g_factual, alt,
                                      _apply_or_fail(episode, rows, a.state.t, alt))
    validate_counterfactual_envelope(addresses, out, rows, sol=sol, episode=episode)
    return MappingProxyType(out)


def validate_counterfactual_envelope(addresses: Sequence, envelope, rows: Sequence, *,
                                     sol, episode: CfEpisode) -> None:
    r"""Structure **and** construction-path identity, for every $L_2$ field.

    Worth the second replay: a hand-made or mis-derived $G_t^{CF}$ that is "close" would
    otherwise reach a scalar write, and the whole point of freezing the fold and the
    configuration is that the number has exactly one legitimate derivation.
    """
    if not isinstance(envelope, Mapping):
        raise ProtocolError(
            f"the counterfactual envelope is {envelope!r}, not a mapping")
    credited = set(addresses)
    if set(envelope) != credited:
        raise ProtocolError(
            "the counterfactual envelope is not exactly the credited address set: "
            f"missing {sorted(map(repr, credited - set(envelope)))} — a missing record is "
            "a protocol failure — and non-credited key(s) "
            f"{sorted(map(repr, set(envelope) - credited))}")
    index = context_index(rows)
    _factual_rows(episode, rows)
    patch = build_target_envelope(sol, addresses, episode.factual_trace, episode.kappa,
                                  episode.phi)
    for a in addresses:
        rec = envelope[a]
        if not isinstance(rec, CounterfactualTarget):
            raise ProtocolError(
                f"the counterfactual target for {a!r} is {rec!r}, not a "
                "CounterfactualTarget")
        if rec.address != a:
            raise ProtocolError(
                f"the counterfactual record for {a!r} carries address {rec.address!r}")
        if (rec.a_plus is None) != (rec.g_cf is None):
            raise ProtocolError(
                f"the counterfactual record for {a!r} has a_plus={rec.a_plus!r} and "
                f"g_cf={rec.g_cf!r}; the alternative and its return are one fact, both "
                "present or both absent")
        if rec.g_cf is not None and not is_finite_real(rec.g_cf):
            raise ProtocolError(
                f"the counterfactual return for {a!r} is {rec.g_cf!r}; the value domain "
                "is the finite reals")
        expected = facts_for(rows, index, a)
        if rec.a_factual != expected.a_factual:
            raise ProtocolError(
                f"the factual action for {a!r} is {rec.a_factual!r} but the rows say "
                f"{expected.a_factual!r}")
        if float(rec.g_factual).hex() != float(expected.g_factual).hex():
            raise ProtocolError(
                f"the factual return for {a!r} is not the frozen reverse fold of the rows")
        alt = patch[a].alternative
        if rec.a_plus != alt:
            raise ProtocolError(
                f"the alternative for {a!r} is {rec.a_plus!r} but the shared a^+ adapter "
                f"says {alt!r}; every compatible arm uses the same a^+ (A76 §63.3)")
        if alt is None:
            continue
        g_cf = _counterfactual_facts(episode, rows, a.state.t, alt)
        if float(rec.g_cf).hex() != float(g_cf).hex():
            raise ProtocolError(
                f"the counterfactual return for {a!r} is {float(rec.g_cf).hex()} but the "
                f"frozen replay-and-fold gives {float(g_cf).hex()}; the configuration and "
                "the fold are part of the target's semantics (A77 §65.7)")
