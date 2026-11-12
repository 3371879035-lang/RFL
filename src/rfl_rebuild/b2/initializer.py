r"""$F_0$ §3's baseline initializer, and the construction gate that admits it.

$$\boxed{I_{\text{baseline}} = I_{D_Q} = W^{\varnothing} + \Delta W^{\text{cal}}_{D_Q}}$$

Approved by the rev-4 review as the $F_0$ choice. The gap it closes is that rev 3 never named the baseline
run's initial state, and the healthy state is a **fixed point** of A91's update: its effective table *is*
$Q^{*}$, and $r_j + \max_{a'} Q^{*}(s', a') = Q^{*}(s_j, a^{\text{cmd}}_j)$ holds at every action, so every
edit the chronological sweep computes equals the reference value and `apply_transaction` canonicalises it
away. Every baseline curve would then be exactly constant, and §4.5's zero-variance rule would make both
Retention forms inadmissible --- `NO_ADMISSIBLE_RETENTION` by construction, hence no design lock and no
confirmatory stage.

**Why the $D_Q$ canary and not the other two.** A91 §79.4 freezes that ordinary training writes $Q_D^{L}$
**only** (`sweep_edits` emits $Q$ edits and nothing else). Of A87 §75.2's three frozen canaries,
$\Delta W^{\text{cal}}_{D_Q}$ is a $Q$-store write, while $\Delta W^{\text{cal}}_{X}$ writes `CONTROLLER` and
$\Delta W^{\text{cal}}_{P}$ writes `PROCESS` --- so a run starting from either of those carries a defect no
episode can touch, and its curve would be flat *at the defective level*: still a constant curve, still the
same failure. The initializer must live in the store the learner writes, and exactly one frozen canary does.

**Semantics, exactly.** $I_{D_Q}$ is a synthetic, pre-data defect used to define the development baseline's
dynamics. It is **not** a B2 treatment, **not** a claim to represent any real distribution of persistent
defects, **not** A87's calibration result, and **not** a winner selected by benchmark performance; and
$-0.14$ is **not** claimed to be a practically meaningful defect magnitude. Its legitimacy is the frozen
canonical canary's provenance.

**The gate is fail-closed and it never selects.** $\mathcal B_{\text{bench}}$ keys drive it (§1 permits
pre-specified binary construction-validity checks), and none of its five propositions reads $f_T$, $f_N$,
$f_G$, $f_C$, $f_R$, a threshold, a ranking or an effect estimate. It does **not** promise that the
scientific stage will succeed: a formal `dev32` run may still return `NO_ADMISSIBLE_RETENTION`, and that
would be a legal scientific failure. Its claim is exact and narrow --- that outcome is no longer guaranteed
by the initializer's mathematics.

$$\boxed{\text{(a) canary present at } e = 0 \qquad \text{(a$'$) } \exists(\beta,e): Q_D^{L}(W_{\beta,e+1})
\neq Q_D^{L}(W_{\beta,e}) \qquad \text{(b1) } \exists\beta, e_1 \neq e_2: V_\beta(e_1) \neq V_\beta(e_2)}$$

$$\boxed{\text{(b2) } \exists\beta_1 \neq \beta_2:\ \text{curve}(\beta_1) \neq \text{curve}(\beta_2) \qquad
\text{(c) } \exists\beta, e \le \texttt{ACQUISITION\_CAP}:\ \text{the canary override is canonicalised back}}$$
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.environment import learned_rollout
from rfl_rebuild.b2.numerics import mean
from rfl_rebuild.b2.screening import canary_edit, learner_prestate
from rfl_rebuild.b2.training import (
    BaselineAcquisitionPlan,
    ExogenousEpisode,
    episode_rollout,
    sweep_edits,
    visited_order,
)
from rfl_rebuild.learner.store import Q, QAddress, LearnerPersistentState

__all__ = ["BaselineGateEvidence", "baseline_gate", "baseline_initializer", "canary_address",
           "INITIALIZER_ARCH"]

#: The one canary A87 §75.2 freezes in the store ordinary learning writes.
INITIALIZER_ARCH = "D_Q"


def canary_address() -> QAddress:
    r"""$\texttt{QAddress}(\texttt{State}(x^{*}), z = 1, m = 0, a = 3)$ --- A87 §75.2's address."""
    edit = canary_edit(INITIALIZER_ARCH)
    if edit.store != Q or type(edit.address) is not QAddress:
        raise ProtocolError(
            "the $D_Q$ canary is no longer a Q-store write; the initializer's justification is that "
            "ordinary training writes Q only (A91 §79.4), so this must be re-derived rather than adapted")
    return edit.address


def baseline_initializer(*, q_reference) -> LearnerPersistentState:
    r"""$W^{\varnothing} + \Delta W^{\text{cal}}_{D_Q}$: the state every baseline run starts from."""
    return learner_prestate(INITIALIZER_ARCH, q_reference=q_reference)


def canary_override_present(state: LearnerPersistentState) -> bool:
    r"""(a) and (c)'s observable: is the canary address carrying an override, or is it back at the reference?"""
    if type(state) is not LearnerPersistentState:
        raise ProtocolError(f"a learner state is a LearnerPersistentState, got {type(state).__name__}")
    return canary_address() in state.q_overrides


@dataclass(frozen=True, slots=True)
class BaselineGateEvidence:
    r"""The five propositions of §3's gate, their witnesses, and the fail-closed verdict."""

    keys: tuple
    cap: int
    bank_size: int
    overrides_by_episode: object   # key -> tuple of bool, aligned with e = 0..cap
    curves: object                 # key -> tuple of per-episode bank means, aligned with e = 0..cap
    canary_visited: object         # key -> tuple of bool, aligned with e = 0..cap-1 (a DIAGNOSTIC)
    q_overrides_by_episode: object  # key -> immutable Q-store snapshots, aligned with e = 0..cap

    # --- the five propositions ----------------------------------------------------------------------

    def canary_at_entry(self) -> bool:
        r"""(a) the initializer really applies the canary, for every key."""
        return all(flags[0] for flags in self.overrides_by_episode.values())

    def left_the_fixed_point(self) -> bool:
        r"""(a$'$) some episode moved $Q_D^{L}$ --- the direct falsification of the healthy-start mechanism."""
        return any(any(a != b for a, b in zip(flags, flags[1:]))
                   for flags in self.q_overrides_by_episode.values())

    def curve_moves(self) -> bool:
        r"""(b1) some key's bank curve is not constant in $e$."""
        return any(len(set(curve)) > 1 for curve in self.curves.values())

    def curves_separate(self) -> bool:
        r"""(b2) two keys whose whole curves differ: the design no longer forces one series for all seeds."""
        distinct = {curve for curve in self.curves.values()}
        return len(distinct) > 1

    def repaired_within_cap(self) -> bool:
        r"""(c) at least one key returns the canary address to the reference --- repairable *at all*.

        One key is enough: 32/32 is explicitly not required, because censoring is part of the design.
        """
        return any(flags[0] and any(not present for present in flags[1:])
                   for flags in self.overrides_by_episode.values())

    # --- the verdict --------------------------------------------------------------------------------

    def failures(self) -> tuple:
        checks = (("a_canary_at_entry", self.canary_at_entry()),
                  ("a_prime_left_the_fixed_point", self.left_the_fixed_point()),
                  ("b1_curve_moves", self.curve_moves()),
                  ("b2_curves_separate", self.curves_separate()),
                  ("c_repaired_within_cap", self.repaired_within_cap()))
        return tuple(name for name, ok in checks if not ok)

    def admissible(self) -> bool:
        return not self.failures()

    def canary_ever_visited(self) -> int:
        r"""**A diagnostic, never a criterion**: how many training episodes would write the canary address.

        It is not one of §3's five propositions and it never decides the verdict. It answers the *mechanism*
        question a failed gate raises --- whether ordinary training can reach the defected address at all ---
        without substituting a different corruption or touching the cap.
        """
        return sum(1 for hits in self.canary_visited.values() for hit in hits if hit)

    def witnesses(self) -> dict:
        r"""The evidence, as data --- episode indices, never a curve or a metric."""
        moved, repaired = {}, {}
        for key, flags in self.overrides_by_episode.items():
            snapshots = self.q_overrides_by_episode[key]
            first = next((e for e in range(1, len(snapshots))
                          if snapshots[e] != snapshots[e - 1]), None)
            if first is not None:
                moved[key] = first
            back = next((e for e in range(1, len(flags)) if not flags[e]), None)
            if flags[0] and back is not None:
                repaired[key] = back
        return {"moved_at": moved, "repaired_at": repaired}


def baseline_gate(plan, *, keys, q_reference) -> BaselineGateEvidence:
    r"""Run the gate: the envelope's `ACQUISITION_CAP` episodes per key, on the envelope's own master bank.

    The levels are the bank means --- A87 §75.3's functional, read greedily and read-only, exactly as §3's
    matrix reads them --- and the override flags are read off the **frozen object**, the learner's own
    $Q_D^{L}$, rather than recomputed from anything. The training path is §3's: the envelope carrying the
    run's key, A91's episode generator and its chronological sweep.
    """
    if not isinstance(plan, BaselineAcquisitionPlan):
        raise ProtocolError(
            f"the gate drives the pre-F1 envelope, got {type(plan).__name__}; a post-F1 protocol has no "
            "T* before the lock and would measure a different workload than the acquisition")
    keys = tuple(keys)
    if not keys:
        raise ProtocolError("the gate needs at least one operational key")
    if any(isinstance(k, bool) or not isinstance(k, int) for k in keys):
        raise ProtocolError(f"the gate's keys must be true integers, got {keys!r}")
    bank = plan.evaluation_bank

    overrides, curves, visited, q_snapshots = {}, {}, {}, {}
    for key in keys:
        learner = baseline_initializer(q_reference=q_reference)
        protocol = replace(plan, seed=key)
        flags, levels, hits, snapshots = [], [], [], []
        for episode in range(plan.acquisition_cap + 1):
            flags.append(canary_override_present(learner))
            snapshots.append(MappingProxyType(dict(learner.q_overrides)))
            levels.append(mean(tuple(learned_rollout(learner, kappa=unit.kappa, tape=unit.tape,
                                                     base_option=unit.base_option,
                                                     q_reference=q_reference).return_value
                                      for unit in bank)))
            if episode == plan.acquisition_cap:
                break
            exogenous = ExogenousEpisode.derive(key, episode)
            trace = episode_rollout(learner, exogenous, protocol=protocol, q_reference=q_reference)
            hits.append(_writes_canary(trace, exogenous))
            edits = sweep_edits(learner, trace, exogenous, protocol=protocol, q_reference=q_reference)
            if edits:
                learner.apply_transaction(edits, q_reference=q_reference)
        overrides[key] = tuple(flags)
        curves[key] = tuple(levels)
        visited[key] = tuple(hits)
        q_snapshots[key] = tuple(snapshots)

    return BaselineGateEvidence(keys=keys, cap=plan.acquisition_cap, bank_size=len(bank),
                                overrides_by_episode=MappingProxyType(overrides),
                                curves=MappingProxyType(curves),
                                canary_visited=MappingProxyType(visited),
                                q_overrides_by_episode=MappingProxyType(q_snapshots))


def _writes_canary(trace, episode) -> bool:
    r"""Would this episode's chronological sweep write the canary's address?

    Read from A91's own `visited_order`, which is the address set `sweep_edits` emits edits for --- so this
    is the mechanism question, not a statistic: an episode can only repair the defect by visiting it.
    """
    address = canary_address()
    for state, control, result in visited_order(trace, kappa=episode.kappa, phi=episode.tape.phase):
        if QAddress(state=state, z=control.z, m=control.m, a=result.a_cmd) == address:
            return True
    return False
