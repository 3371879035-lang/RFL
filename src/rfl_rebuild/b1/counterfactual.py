r"""A77 §65.7 — $G_t^{CF}$, the counterfactual target, and `DecisionReadView_pre`.

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
``fsum``; that is a different semantic layer, and A77 now says so explicitly.)

**Why the decision read view is in the configuration.** The replay visits steps *after*
$t$, and the decision channel there consults the learner's persistent state. A replay that
omitted the pre-update view would silently fall back to the reference provider whenever an
existing learner decision defect was met, violating A76's "all targets are computed from
the same pre-update learner state" and measuring $G_t^{CF}$ against a *different learner*
than the one whose factual return it is compared with.

**The invariant, and what it is not:**

$$\boxed{\text{rows}\bigl(\text{trace}^{CF}\bigr)[0:t] =
\text{rows}\bigl(\text{trace}^{F}\bigr)[0:t] \quad\text{else }
\texttt{PROTOCOL\_ERROR}}$$

It is a real check over the learner-visible row schema (which carries $z$ and $m$, so it
subsumes the option-in-force and context equalities) — and it is a **second witness, not
the closure**. It fires only when the divergence lands in the prefix; a replay that
dropped the view but happened to revisit the defect after $t$ would pass it. What closes
that case is structural: the configuration carries the view, and the builder cannot
substitute one. The gate constructs a scene where the defect *is* met before $t$, so the
invariant is observed doing its job rather than assumed to.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
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
from rfl_rebuild.learner.store import DecisionAddress

__all__ = [
    "CounterfactualTarget",
    "CfEpisode",
    "build_counterfactual_envelope",
    "replay_with_decision_replaced",
    "validate_counterfactual_envelope",
]


@dataclass(frozen=True, slots=True)
class CfEpisode:
    r"""The factual episode's configuration, complete.

    It carries the factual ``trace`` as well, for two reasons: the $a^+$ adapter needs it
    to resolve contexts, and the builder checks that the rows it was handed are *that*
    trace's rows — so a scene cannot be half-substituted without being caught.

    ``decision_read_view_pre`` is $\texttt{DecisionReadView}_{pre}$: the complete
    pre-update decision read path, as a ``CommandProvider``. The replay uses it as its
    provider, which is what makes the counterfactual differ from the factual episode in
    exactly one thing.
    """

    trace: object
    kappa: int
    phi: int
    tape: object
    decision_read_view_pre: object
    mask: object = K.FaultMask()
    option_fault: int | None = None
    base_option: int = 1
    interventions: object = K.InterventionSet()
    controller: object = None
    learner_process_commit: object = None
    reward_mode: str = "A"


@dataclass(frozen=True, slots=True)
class CounterfactualTarget:
    r"""$L_2$'s record: the factual pair **and** the counterfactual pair.

    $a_t^+$ and $G_t^{CF}$ are both ``None`` or both present; the validator enforces that,
    because "the alternative is unknown" and "its return is unknown" are the same
    scientific fact and must not be expressible separately.
    """

    address: DecisionAddress
    a_factual: int
    g_factual: float
    a_plus: int | None
    g_cf: float | None


def replay_with_decision_replaced(episode: CfEpisode, t: int, action: int):
    r"""One full replay whose only difference from the factual episode is $do(d_t)$.

    The factual configuration is passed through unchanged, including the pre-update
    decision read view. The decision intervention at $t$ is removed before the new one is
    added, so this is a *replacement*.
    """
    members = tuple(iv for iv in episode.interventions.members
                    if not (iv.kind == "decision" and iv.t == t))
    interventions = K.InterventionSet(members + (K.Intervention.decision(t, action),))
    return K.rollout(
        kappa=episode.kappa,
        tape=episode.tape,
        command_provider=episode.decision_read_view_pre,
        base_option=episode.base_option,
        mask=episode.mask,
        option_fault=episode.option_fault,
        interventions=interventions,
        controller=episode.controller,
        learner_process_commit=episode.learner_process_commit,
        reward_mode=episode.reward_mode,
    )


def _counterfactual_facts(rows: Sequence, episode: CfEpisode, t: int, a_plus: int,
                          ) -> float:
    r"""$G_t^{CF}(a_t^+)$, with the prefix invariant enforced before the number exists."""
    cf_trace = replay_with_decision_replaced(episode, t, a_plus)
    cf_rows = learner_rows(cf_trace, episode.kappa, episode.phi)
    if len(cf_rows) <= t:
        raise ProtocolError(
            f"the counterfactual replay ended at step {len(cf_rows)} and never reached "
            f"t={t}; a counterfactual to a step the replay does not visit is undefined")
    prefix_f = rows[:t]
    prefix_cf = cf_rows[:t]
    if prefix_cf != prefix_f:
        first = next((i for i, (a, b) in enumerate(zip(prefix_cf, prefix_f)) if a != b),
                     min(len(prefix_cf), len(prefix_f)))
        raise ProtocolError(
            f"the counterfactual replay does not share the factual prefix at t={t}: "
            f"first divergence at step {first}. The two traces must agree on everything "
            "before the intervention, or the counterfactual is not counterfactual to "
            "*this* episode (A77 §65.7). A replay that dropped "
            "DecisionReadView_pre lands exactly here")
    return factual_return_to_go(cf_rows, t)


def build_counterfactual_envelope(rows: Sequence,
                                  addresses: Sequence[DecisionAddress], *,
                                  sol, episode: CfEpisode,
                                  ) -> Mapping[DecisionAddress, CounterfactualTarget]:
    r"""The $L_2$ adapter: $F_t$ and $(a_t^+, G_t^{CF})$ for every credited context.

    Two evaluator-side reads are involved and both are named: ``sol`` supplies $a_t^+$
    through the *same* adapter every other arm uses (A76 §63.3: never one $a^+$ for patch
    and another for $Q$), and ``episode`` supplies the factual configuration for the
    replay. The learner-visible half still comes from ``rows``.
    """
    index = context_index(rows)
    if learner_rows(episode.trace, episode.kappa, episode.phi) != tuple(rows):
        raise ProtocolError(
            "the rows handed to the counterfactual builder are not the rows of the "
            "episode's factual trace; a scene may not be half-substituted")
    patch = build_target_envelope(sol, addresses, episode.trace, episode.kappa,
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
        g_cf = _counterfactual_facts(rows, episode, a.state.t, alt)
        out[a] = CounterfactualTarget(a, facts.a_factual, facts.g_factual, alt, g_cf)
    validate_counterfactual_envelope(addresses, out, rows, sol=sol, episode=episode)
    return MappingProxyType(out)


def validate_counterfactual_envelope(addresses: Sequence[DecisionAddress], envelope,
                                     rows: Sequence, *, sol, episode: CfEpisode) -> None:
    r"""Structure **and** construction-path identity, for every $L_2$ field.

    Worth the second replay: a hand-made or mis-derived $G_t^{CF}$ that is "close" would
    otherwise reach a scalar write, and the whole point of freezing the fold and the
    configuration is that the number has exactly one legitimate derivation. The check
    re-derives both targets and compares bit patterns.
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
    patch = build_target_envelope(sol, addresses, episode.trace, episode.kappa,
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
                f"the factual return for {a!r} is not the frozen reverse fold of the "
                "rows")
        alt = patch[a].alternative
        if rec.a_plus != alt:
            raise ProtocolError(
                f"the alternative for {a!r} is {rec.a_plus!r} but the shared a^+ adapter "
                f"says {alt!r}; every compatible arm uses the same a^+ (A76 §63.3)")
        if alt is None:
            continue
        g_cf = _counterfactual_facts(rows, episode, a.state.t, alt)
        if float(rec.g_cf).hex() != float(g_cf).hex():
            raise ProtocolError(
                f"the counterfactual return for {a!r} is {float(rec.g_cf).hex()} but the "
                f"frozen replay-and-fold gives {float(g_cf).hex()}; the configuration and "
                "the fold are part of the target's semantics (A77 §65.7)")
