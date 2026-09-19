r"""A77 §65.7, §65.8, §65.10 — $D_Q\times L_2$: the counterfactual target and its laws.

$$\boxed{\text{a verified alternative} \to \text{a replay of the right episode}
\to \text{an exact target} \to \text{writes into the learner that was observed}}$$

The gates are grouped by the ways it can be wrong:

1. **provenance** — the configuration generates the factual episode, its three learner
   channels come from one snapshot, and that snapshot is the learner the write lands in;
2. **the replay** — replace-not-add, and the prefix invariant with its honest limit;
3. **the target** — the frozen fold over the counterfactual rows and the shared $a^+$;
4. **the writes** — entry counts, the no-degeneration rule, one receipt, one transaction;
5. **the regimes** — and the measurements that bound what this arm can do at all.

**No gate in this file skips.** Where a construction needs a scene to have a property,
the helper searches the fixed support for such a scene and *asserts that one was found*;
a property that turns out to be rare is a measured fact, not a reason for a gate to
disappear.
"""

from __future__ import annotations

import dataclasses
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1 import (  # noqa: E402
    APPLIED, DQ_LAWS, DQ_SLICE, EVALUABLE_NOOP, ILL_TYPED, NO_VALID_ALTERNATIVE,
    CfEpisode, CounterfactualReturnWrite, CounterfactualTarget,
    CounterfactualUndefined, DualReturnWrite,
    FactualReturnWrite, NoWriteRef, ProtocolError, SliceDescriptor, Tier,
    build_counterfactual_envelope, build_target_envelope, fingerprint,
    independent_treatment_count, law_metadata, replay_with_decision_replaced,
    resolve_credited_units, run_dq_law, run_factual_return_law,
    validate_counterfactual_envelope,
)
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import ControlState, DecisionOverride, FaultMask  # noqa: E402
from rfl_rebuild.env.observation import (learner_rows, ROW_SCHEMA,
                                          walk_transition)  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    DecisionAddress, Edit, LearnerPersistentState, Q, QAddress, State, owner_Q,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

SOL = solve_reference()
VIEW = reference_view_from(SOL)
TAPE = lambda phi: K.SemanticTape(phase=phi, error_flag=0, cause_rank=0)  # noqa: E731


# --------------------------------------------------------------------------- #
# scene construction: the configuration generates the episode
# --------------------------------------------------------------------------- #

def make_episode(kappa, phi, z0, *, pre=None, mask=None, interventions=None, mode="A"):
    """A `CfEpisode` rooted in one frozen snapshot; the factual trace is its own."""
    return CfEpisode(kappa=kappa, tape=TAPE(phi),
                     snapshot_pre=(pre or LearnerPersistentState()).snapshot(),
                     reference=VIEW, base_option=z0, mask=mask or K.FaultMask(),
                     interventions=interventions or K.InterventionSet(),
                     reward_mode=mode)


def rows_and_addresses(episode):
    rows = learner_rows(episode.factual_trace, episode.kappa, episode.phi)
    steps = sorted({r[2] for r in rows})
    addrs = resolve_credited_units(tuple(f"Decision_{t}" for t in steps),
                                   episode.factual_trace, episode.kappa, episode.phi)
    return rows, addrs


def healthy(kappa=0, phi=0, z0=1):
    ep = make_episode(kappa, phi, z0)
    rows, addrs = rows_and_addresses(ep)
    return ep, rows, addrs, LearnerPersistentState()


#: Why a grid point has no factual faulted episode. Kept apart because they are different
#: geometries: "there is no step t", "the step exists but has no suboptimal admissible
#: action", and "the candidate is not admissible at the injected step's real context" say
#: different things about the world, and lumping them together hid that.
NO_STEP = "no_step"
NO_SUBOPTIMAL = "no_suboptimal_admissible_action"
MASK_MALFORMED = "factual_mask_malformed"
OK = "ok"


def faulted(kappa=0, phi=0, z0=1, t=1):
    """A $Z_D$ injection, or a named reason why this grid point has none."""
    probe = make_episode(kappa, phi, z0).factual_trace
    ctxs = list(walk_transition(probe, kappa, phi, probe.option_in_force))
    if len(ctxs) <= t:
        return NO_STEP, None
    ctx = ctxs[t]
    s, z, m = ctx[0], ctx[1], ctx[2]
    if s.t != t:
        return NO_STEP, None
    best = SOL.best_action(s, z, m)
    allowed = [a for a in sorted(K.option_actions(z, ControlState(z=z, m=m), s))
               if a != best]
    if not allowed:
        return NO_SUBOPTIMAL, None
    try:
        ep = make_episode(kappa, phi, z0,
                          mask=FaultMask(decision=DecisionOverride(
                              t=t, action=allowed[0])))
    except K.MalformedIntervention:
        # The probe's context is not the injected step's context, so the candidate action
        # may be inadmissible *there*.
        return MASK_MALFORMED, None
    rows, addrs = rows_and_addresses(ep)
    return OK, (ep, rows, addrs, LearnerPersistentState())


def grid_scenes():
    """The fixed probe grid with **every** infeasible point counted by category.

    A grid point can fail for two different reasons and they are not interchangeable:

    * ``mask_inadmissible`` -- the injection chosen from the probe trajectory is not
      admissible at the injected step's real context, so the *factual* episode cannot be
      built;
    * ``cf_undefined`` -- the factual episode exists, but the counterfactual has no
      definition: the diverged path reaches a later masked step in a different state,
      where the masked action escapes the option.

    Neither is a write status. Both are counted, and the caller asserts the counts, so a
    change in the grid shows up as a changed tuple rather than as a quietly smaller probe.
    """
    feasible, cf_undefined = [], 0
    reasons = {NO_STEP: 0, NO_SUBOPTIMAL: 0, MASK_MALFORMED: 0}
    for kappa in (0, 1):
        for phi in (0, 1, 2):
            for z0 in (0, 1, 2):
                for ft in (1, 2):
                    reason, built = faulted(kappa, phi, z0, t=ft)
                    if reason is not OK:
                        reasons[reason] += 1
                        continue
                    ep, rows, addrs, pre = built
                    try:
                        env = build_counterfactual_envelope(rows, addrs, sol=SOL,
                                                            episode=ep)
                    except CounterfactualUndefined:
                        cf_undefined += 1
                        continue
                    feasible.append((ep, rows, addrs, pre, env))
    return feasible, reasons, cf_undefined


def with_alternative():
    """The first scene in the fixed support that has a verified alternative at all.

    Asserted rather than skipped: if the search comes back empty then the support or the
    adapter changed, and that is a failure, not a reason for a gate to vanish.
    """
    for kappa in (0, 1):
        for phi in range(6):
            for z0 in range(4):
                reason, built = faulted(kappa, phi, z0)
                if reason is not OK:
                    continue
                ep, rows, addrs, pre = built
                env = build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
                if any(env[a].a_plus is not None for a in addrs):
                    return ep, rows, addrs, pre, env
    pytest.fail("no faulted scene in the support has a verified alternative")


def bent_scene(kappa=0, phi=0, z0=1, lift=100.0):
    r"""A scene whose **pre-update** decision policy is already off $\pi^\ast$.

    On a fresh store the counterfactual target *usually* equals the reference — the
    replay's suffix is an optimal continuation — so the L2 arms usually have nothing to
    write. Prior learning is one mechanism that gives them content: here an entry is
    lifted at a context the counterfactual replay itself visits after $t$, which moves the
    suffix off the optimal path while leaving the factual prefix untouched.

    Returns ``None`` when this grid point admits no such construction; callers count,
    because "9 of 12" is a measurement and "9 of the ones that happened to work" is not.
    """
    ep0 = make_episode(kappa, phi, z0)
    _rows0, addrs0 = rows_and_addresses(ep0)
    patch = build_target_envelope(SOL, addrs0, ep0.factual_trace, kappa, phi)
    first = next((a for a in addrs0 if patch[a].alternative is not None), None)
    if first is None:
        return None
    t0 = first.state.t
    trial = make_episode(kappa, phi, z0,
                         mask=FaultMask(decision=DecisionOverride(
                             t=t0, action=patch[first].alternative))).factual_trace
    for ctx in walk_transition(trial, kappa, phi, trial.option_in_force):
        s2, z2, m2 = ctx[0], ctx[1], ctx[2]
        if s2.t <= t0:
            continue
        row = VIEW.row(s2, z2, m2)
        best = SOL.best_action(s2, z2, m2)
        worse = [a for a, v in sorted(row.items()) if v < row[best]]
        if not worse:
            continue
        target = DecisionAddress(state=State(x=s2.x, y=s2.y, t=s2.t, kappa=s2.kappa,
                                             phi=s2.phi), z=z2, m=m2)
        entry = QAddress(state=target.state, z=z2, m=m2, a=worse[0])
        pre = LearnerPersistentState()
        pre.apply_transaction([Edit("q", entry, row[best] + lift)], q_reference=VIEW)
        ep = make_episode(kappa, phi, z0, pre=pre)
        rows, addrs = rows_and_addresses(ep)
        env = build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
        if any(env[a].a_plus is not None
               and env[a].g_cf != VIEW.value(QAddress(state=a.state, z=a.z, m=a.m,
                                                      a=env[a].a_plus))
               for a in addrs):
            return ep, rows, addrs, pre, env
    return None


def first_bent():
    for kappa in (0, 1):
        for phi in range(6):
            for z0 in range(4):
                built = bent_scene(kappa, phi, z0)
                if built is not None:
                    return built
    pytest.fail("no bent configuration in the support produced a non-reference target")


# --------------------------------------------------------------------------- #
# 1. provenance
# --------------------------------------------------------------------------- #

def test_1_the_three_learner_channels_come_from_one_snapshot():
    """A decision view from one learner cannot be mixed with another learner's
    process-commit provider, because they are not separately supplied."""
    pre = LearnerPersistentState()
    snap = pre.snapshot()
    ep = make_episode(0, 0, 1, pre=pre)
    assert ep.decision_read_view_pre is ep.decision_read_view_pre
    assert ep.process_commit_provider is ep.process_commit_provider
    assert ep.controller_mapping is ep.controller_mapping
    assert ep.controller_mapping == snap.controller_mapping()
    assert ep.process_commit_provider(1) == snap.process_commit_provider()(1)
    assert type(ep.snapshot_pre).__name__ == "LearnerSnapshot"


def test_2_the_configuration_generates_the_factual_episode():
    r"""$$\boxed{\text{config} \to \text{factual rollout}}$$ and the trace cannot be
    supplied.

    With a *supplied* trace a configuration could disagree with it in any field that
    happens to make no difference on the factual path — a different tape, mask,
    controller, or a fault that bites only after $t$ — and every factual-path check would
    pass while the replay faithfully used the wrong configuration. Here the trace is an
    ``init=False`` field, so that case is unconstructible rather than undetected.
    """
    ep0 = make_episode(0, 0, 1)
    init_fields = {f.name for f in dataclasses.fields(CfEpisode) if f.init}
    assert "factual_trace" not in init_fields
    with pytest.raises(TypeError):
        CfEpisode(kappa=0, tape=TAPE(0), snapshot_pre=ep0.snapshot_pre,
                  reference=VIEW, factual_trace=object())
    # a different configuration is a different episode, not a rename of this one
    other = make_episode(0, 1, 1)
    assert learner_rows(other.factual_trace, 0, 1) != learner_rows(ep0.factual_trace, 0, 0)
    # and rows that are not this configuration's are refused
    _rows, addrs = rows_and_addresses(ep0)
    with pytest.raises(ProtocolError) as ei:
        build_counterfactual_envelope(learner_rows(other.factual_trace, 0, 1), addrs,
                                      sol=SOL, episode=ep0)
    assert "THIS configuration's factual rollout" in str(ei.value)


def test_2d_rows_that_are_not_this_configurations_are_refused():
    r"""The *only* difference from the configuration's own rows is a field nothing reads.

    The construction matters. An earlier revision of this gate handed the builder another
    episode's rows, which a different guard rejected first (the credited address was not in
    those rows), so deleting the rows check changed only the failure's location — evidence
    that an error path moved, not that a half-substitution was accepted.

    Here the rows ARE this episode's, with one field altered that the builder never reads
    and that lies outside every exercised prefix: ``a_realized`` of a later row. Context
    keys, factual targets, counterfactual targets and the prefix are all untouched, so
    `_factual_rows` is the only thing that can notice.
    """
    ep, rows, addrs, _pre = healthy()
    late = addrs[-1]
    if late.state.t >= len(rows) - 1:
        for candidate in reversed(addrs):
            if candidate.state.t < len(rows) - 1:
                late = candidate
                break
        else:
            pytest.fail("the probe needs an address before the last step")
    tampered = [list(r) for r in rows]
    idx = ROW_SCHEMA.index("a_realized")
    row_i = late.state.t + 1
    tampered[row_i][idx] = (tampered[row_i][idx] + 1) % len(K.ACTIONS)
    tampered = tuple(tuple(r) for r in tampered)
    assert tampered != tuple(rows)
    assert tampered[:late.state.t] == tuple(rows)[:late.state.t], "prefix untouched"
    with pytest.raises(ProtocolError) as ei:
        build_counterfactual_envelope(tampered, [late], sol=SOL, episode=ep)
    assert "THIS configuration's factual rollout" in str(ei.value)


def test_2e_the_episode_the_adapter_and_the_transaction_are_one_referent():
    r"""$$\boxed{Q^\ast_{\text{episode}} = Q^\ast_{a^+} = Q^\ast_{\text{write}}}$$

    Three entry points, one referent. The learner fingerprint cannot catch a mismatch,
    because a reference is not part of the learner state, so the binding is on content:
    independently built views of the same $Q_D^\ast$ pass, a different one fails stop.
    """
    def perturbed_view(factor):
        rows = {k: dict(v) for k, v in SOL.q.items()}
        first = next(iter(rows))          # insertion order: deterministic, and State is
        a = next(iter(rows[first]))       # not orderable
        rows[first][a] = rows[first][a] * factor
        return reference_view_from(type("S", (), {"q": rows})())

    ep, rows, addrs, pre, _env = first_bent()
    # (a) a second, legal, DIFFERENT referent for the transaction
    other = perturbed_view(1.5)
    assert other.digest() != VIEW.digest()
    with pytest.raises(ProtocolError) as ei:
        run_dq_law(CounterfactualReturnWrite, pre, addrs, rows, other, sol=SOL,
                   episode=ep)
    assert "names more than one reference" in str(ei.value)
    # (b) the same, against the a^+ adapter. `reference_view_from` is duck-typed on `.q`,
    # so a stand-in solver is enough to make the adapter a different referent.
    q = {k: dict(v) for k, v in SOL.q.items()}
    first = next(iter(q))
    a = next(iter(q[first]))
    q[first][a] = q[first][a] * 1.5
    perturbed_sol = type("S", (), {"q": q})()
    with pytest.raises(ProtocolError) as ei2:
        run_dq_law(CounterfactualReturnWrite, pre, addrs, rows, VIEW,
                   sol=perturbed_sol, episode=ep)
    assert "names more than one reference" in str(ei2.value)
    # (c) an independent VIEW of the same Q_D* is the same referent
    same = reference_view_from(SOL)
    assert same is not VIEW and same.digest() == VIEW.digest()
    run_dq_law(CounterfactualReturnWrite, pre.clone(), addrs, rows, same, sol=SOL,
               episode=ep).ledger.check_fingerprint_invariants()


def test_2b_the_primary_reward_mode_is_the_only_mode():
    with pytest.raises(ProtocolError) as ei:
        make_episode(0, 0, 1, mode="B")
    assert "frozen on mode A" in str(ei.value)


def test_2c_the_pre_update_learner_must_be_a_frozen_snapshot():
    with pytest.raises(ProtocolError) as ei:
        CfEpisode(kappa=0, tape=TAPE(0),
                  snapshot_pre=LearnerPersistentState(), reference=VIEW)
    assert "must be a frozen snapshot" in str(ei.value)


def test_3_the_target_learner_and_the_updated_learner_must_be_the_same():
    r"""$$\boxed{fp(\texttt{pre\_state}) = fp(\texttt{snapshot\_pre})}$$

    Otherwise the arm observes learner $A$'s experience, computes learner $A$'s target, and
    trains learner $B$. The check runs **before** any target is built, so the failure
    cannot be reached through a partially-constructed envelope.
    """
    ep, rows, addrs, pre, _env = first_bent()
    with pytest.raises(ProtocolError) as ei:
        run_dq_law(CounterfactualReturnWrite, LearnerPersistentState(), addrs, rows, VIEW,
                   sol=SOL, episode=ep)
    assert "different pre-update learner" in str(ei.value)
    # a clone of the right learner is the same learner for every purpose the contract
    # can state
    res = run_dq_law(CounterfactualReturnWrite, pre.clone(), addrs, rows, VIEW, sol=SOL,
                     episode=ep)
    res.ledger.check_fingerprint_invariants()


def test_3b_the_binding_is_the_frozen_snapshot_not_the_live_object():
    """The snapshot is a value: mutating the learner afterwards does not move it."""
    ep, rows, addrs, pre, _env = first_bent()
    assert fingerprint(pre) == fingerprint(ep.snapshot_pre)
    assert fingerprint(LearnerPersistentState()) != fingerprint(ep.snapshot_pre)
    before = fingerprint(ep.snapshot_pre)
    probe = addrs[0]
    legal = sorted(K.option_actions(probe.z, ControlState(z=probe.z, m=probe.m),
                                    probe.state))[0]
    pre.apply_transaction([Edit("q", QAddress(state=probe.state, z=probe.z, m=probe.m,
                                              a=legal), 123.0)], q_reference=VIEW)
    assert fingerprint(ep.snapshot_pre) == before, \
        "the episode's snapshot must not follow later mutations of the live state"


# --------------------------------------------------------------------------- #
# 2. the replay
# --------------------------------------------------------------------------- #

def test_4_the_replay_is_this_configuration_and_differs_in_one_thing(monkeypatch):
    """Differing in exactly one thing is a property of the *call*, not a promise."""
    ep, rows, addrs, _pre = healthy()
    seen = {}
    original = K.rollout

    def spy(**kwargs):
        seen.update(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(K, "rollout", spy)
    probe = addrs[0]
    legal = sorted(K.option_actions(probe.z, ControlState(z=probe.z, m=probe.m),
                                    probe.state))
    replay_with_decision_replaced(ep, probe.state.t, legal[0])
    assert seen["kappa"] == ep.kappa
    assert seen["tape"] is ep.tape
    assert seen["mask"] is ep.mask
    assert seen["option_fault"] is ep.option_fault
    assert seen["base_option"] == ep.base_option
    assert seen["reward_mode"] == "A"
    assert seen["command_provider"] is ep.decision_read_view_pre
    assert seen["controller"] is ep.controller_mapping
    assert seen["learner_process_commit"] is ep.process_commit_provider


def test_5_the_decision_intervention_is_replaced_not_added():
    """A factual episode that already intervened at t keeps exactly one decision there."""
    for kappa in (0, 1):
        for phi in range(6):
            for z0 in range(4):
                reason, built = faulted(kappa, phi, z0)
                if reason is not OK:
                    continue
                ep, rows, addrs, _pre = built
                t = addrs[0].state.t
                alt = build_target_envelope(SOL, addrs, ep.factual_trace, kappa,
                                            phi)[addrs[0]].alternative
                if alt is None:
                    continue
                legal = [a for a in sorted(K.option_actions(
                    addrs[0].z, ControlState(z=addrs[0].z, m=addrs[0].m),
                    addrs[0].state)) if a != alt]
                if not legal:
                    continue
                base = make_episode(kappa, phi, z0,
                                    interventions=K.InterventionSet(
                                        (K.Intervention.decision(t, legal[0]),)))
                assert replay_with_decision_replaced(base, t, alt) is not None
                with pytest.raises(K.MalformedIntervention):
                    K.InterventionSet(base.interventions.members
                                      + (K.Intervention.decision(t, alt),))
                return
    pytest.fail("no faulted scene with an alternative was found")


def test_5b_the_factual_mask_is_held_fixed_and_do_shadows_it(monkeypatch):
    r"""$$\boxed{\text{same fault assignment} + do(d_t = a_t^+) \;>\; Z_D}$$

    A77 §65.7 puts ``mask`` inside the configuration that is identical between the factual
    and counterfactual episodes, and gives the replacement only to ``interventions``. So a
    factual world carrying $Z_D(t)$ keeps that fault and the intervention **shadows** it at
    that structural node, by the kernel's frozen precedence
    $do(d_t) > Z_D > \texttt{command\_provider}$ — a Pearl-style intervention on the node,
    not a deletion of the fault from the world.

    Both halves are asserted, because either alone is satisfied by the wrong construction:
    the mask handed to the rollout is the factual one, *and* the command at $t$ is $a_t^+$.
    An earlier revision of this gate asserted the mask entry was *removed*, which is the
    semantics this project rejects: same numbers today, different SCM.
    """
    seen = {}
    original = K.rollout

    def spy(**kwargs):
        seen.update(kwargs)
        return original(**kwargs)

    ep0 = make_episode(0, 0, 1)
    _rows, addrs = rows_and_addresses(ep0)
    probe = addrs[0]
    legal = sorted(K.option_actions(probe.z, ControlState(z=probe.z, m=probe.m),
                                    probe.state))
    mask = FaultMask(decision=DecisionOverride(t=probe.state.t, action=legal[0]))
    ep = make_episode(0, 0, 1, mask=mask)
    assert ep.mask.decision is not None, "the factual episode carries the mask entry"

    monkeypatch.setattr(K, "rollout", spy)
    ep.replay(probe.state.t, legal[-1])
    assert seen["mask"] is ep.mask, \
        "the counterfactual must run the SAME fault assignment, not a stripped one"
    assert seen["mask"].decision == ep.mask.decision

    cf_rows = learner_rows(ep.replay(probe.state.t, legal[-1]), 0, 0)
    assert cf_rows[probe.state.t][ROW_SCHEMA.index("a_cmd")] == legal[-1], \
        "do(d_t) must shadow Z_D at that node"


def test_6_the_counterfactual_prefix_is_the_factual_prefix_across_the_support():
    r"""The premise the structural provenance rests on, verified empirically.

    Because the configuration generates both rollouts, the prefix identity

    $$\boxed{\text{rows}^{CF}[0:t] = \text{rows}^{F}[0:t]}$$

    holds *by construction* — the intervention at $t$ cannot affect a step before $t$ — so
    the assertion inside the builder cannot fire and **no mutation can kill it** (an
    earlier revision carried one; it reported ``NOT_A_GATE``). What can be checked is the
    premise: that the kernel really does consume its tape and its state per step.

    This walks the healthy support and every feasible faulted grid point and asserts the
    identity at the row level.
    """
    checked = 0
    for kappa, phi, z0 in HEALTHY_WORLDS:
        ep, rows, addrs, _pre = healthy(kappa, phi, z0)
        patch = build_target_envelope(SOL, addrs, ep.factual_trace, kappa, phi)
        for a in addrs:
            alt = patch[a].alternative
            if alt is None:
                continue
            cf_rows = learner_rows(ep.replay(a.state.t, alt), kappa, phi)
            assert cf_rows[:a.state.t] == tuple(rows)[:a.state.t], (kappa, phi, z0, a)
            checked += 1
    feasible, _reasons, _undef = grid_scenes()
    for ep, rows, addrs, _pre, env in feasible:
        for a in addrs:
            rec = env[a]
            if rec.a_plus is None:
                continue
            cf_rows = learner_rows(ep.replay(a.state.t, rec.a_plus), ep.kappa, ep.phi)
            assert cf_rows[:a.state.t] == tuple(rows)[:a.state.t]
            checked += 1
    assert checked >= 32, f"too few counterfactuals exercised: {checked}"


def test_6a_an_episode_is_the_configuration_that_generated_it():
    r"""The other half: rows that are not this configuration's are refused.

    This is the *live* protection — it is what makes supplying a mismatched trace
    impossible — and it is where a replay under the wrong learner state lands.
    """
    ep0 = make_episode(0, 0, 1)
    _rows, addrs = rows_and_addresses(ep0)
    other = make_episode(0, 1, 1)
    with pytest.raises(ProtocolError) as ei:
        build_counterfactual_envelope(learner_rows(other.factual_trace, 0, 1), addrs,
                                      sol=SOL, episode=ep0)
    assert "THIS configuration's factual rollout" in str(ei.value)


def test_6b_the_view_is_live_after_t_where_the_prefix_cannot_see_it():
    r"""The invariant's limit, turned into positive evidence.

    A replay that dropped the view would diverge in the prefix only if the defect is met
    *before* $t$. So the closure is structural, and the witness that the view is live in
    the *suffix* is that the target responds to it.

    The bent scene is a **healthy** scene — no mask, no fault, no non-default option — run
    under a snapshot that carries one lifted entry. The reference policy from the
    intervention onward would realize an optimal continuation and land on
    $Q_D^\ast$; a target that differs from the reference therefore cannot be explained by
    remaining faults, and can only come from the replay following the snapshot's decision
    channel. That is the whole content of "the view is live after $t$".
    """
    ep, rows, addrs, pre, env = first_bent()
    assert pre.q_overrides, "the bent scene must carry prior learning"
    assert fingerprint(pre) != fingerprint(LearnerPersistentState())
    live = [a for a in addrs if env[a].a_plus is not None
            and env[a].g_cf != VIEW.value(QAddress(state=a.state, z=a.z, m=a.m,
                                                   a=env[a].a_plus))]
    assert live, ("a healthy scene with no remaining faults can only leave the reference "
                  "if the decision channel did it")


def test_7_a_failed_replay_is_not_a_zero():
    """A divergence is a protocol failure, never $G^{CF} = 0$."""
    ep, rows, addrs, _pre = healthy()
    rows = list(rows)
    rows[0] = tuple(rows[0][:9]) + (rows[0][9] + 0.5,)
    with pytest.raises(ProtocolError):
        build_counterfactual_envelope(tuple(rows), addrs, sol=SOL, episode=ep)


# --------------------------------------------------------------------------- #
# 3. the target
# --------------------------------------------------------------------------- #

def test_8_the_cf_target_is_the_frozen_fold_over_the_counterfactual_rows():
    """Not the factual suffix, and not a suffix simulation: the replay is full."""
    ep, rows, addrs, _pre, env = with_alternative()
    checked = 0
    for a in addrs:
        rec = env[a]
        if rec.a_plus is None:
            continue
        cf_rows = learner_rows(replay_with_decision_replaced(ep, a.state.t, rec.a_plus),
                               ep.kappa, ep.phi)
        assert cf_rows[:a.state.t] == tuple(rows)[:a.state.t], "prefix identity"
        g = 0.0
        for j in range(len(cf_rows) - 1, a.state.t - 1, -1):
            g = cf_rows[j][9] + g
        assert rec.g_cf.hex() == g.hex()
        checked += 1
    assert checked >= 1


def test_9_a_perturbed_counterfactual_return_is_rejected():
    ep, rows, addrs, _pre, good = with_alternative()
    victim = next(a for a in addrs if good[a].a_plus is not None)
    lie = dict(good)
    lie[victim] = CounterfactualTarget(victim, good[victim].a_factual,
                                       good[victim].g_factual, good[victim].a_plus,
                                       good[victim].g_cf + 1e-9)
    with pytest.raises(ProtocolError) as ei:
        validate_counterfactual_envelope(addrs, lie, rows, sol=SOL, episode=ep)
    assert "frozen replay-and-fold" in str(ei.value)


def test_9b_a_substituted_alternative_is_rejected():
    """Every compatible arm uses the same $a^+$ (A76 §63.3)."""
    ep, rows, addrs, _pre, good = with_alternative()
    victim = next(a for a in addrs if good[a].a_plus is not None)
    allowed = sorted(K.option_actions(victim.z, ControlState(z=victim.z, m=victim.m),
                                      victim.state))
    other = [a for a in allowed if a not in (good[victim].a_plus,
                                             good[victim].a_factual)]
    assert other, "the probe needs a third admissible action"
    lie = dict(good)
    lie[victim] = CounterfactualTarget(victim, good[victim].a_factual,
                                       good[victim].g_factual, other[0],
                                       good[victim].g_cf)
    with pytest.raises(ProtocolError) as ei:
        validate_counterfactual_envelope(addrs, lie, rows, sol=SOL, episode=ep)
    assert "every compatible arm uses the same a^+" in str(ei.value)


def test_10_the_alternative_is_the_same_object_the_patch_arm_uses():
    """One $a^+$ adapter for every compatible arm, not one per architecture."""
    ep, rows, addrs, _pre, env = with_alternative()
    patch = build_target_envelope(SOL, addrs, ep.factual_trace, ep.kappa, ep.phi)
    assert all(env[a].a_plus == patch[a].alternative for a in addrs)


def test_11_the_delivered_cell_is_exactly_the_four_l2_fields():
    ep, rows, addrs, _pre = healthy()
    env = build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
    delivered = DQ_SLICE.deliver(Tier.L2_COUNTERFACTUAL, addrs, env)
    for _addr, fields in delivered.items():
        assert set(fields) == {"a_factual", "g_factual", "a_plus", "g_cf"}


def test_19_the_envelope_must_be_the_exact_credited_set():
    ep, rows, addrs, _pre, good = with_alternative()
    assert len(addrs) >= 2, "the probe needs at least two credited contexts"
    partial = dict(good)
    del partial[addrs[0]]
    with pytest.raises(ProtocolError):
        validate_counterfactual_envelope(addrs, partial, rows, sol=SOL, episode=ep)
    extra = dict(good)
    extra[DecisionAddress(state=State(x=0, y=0, t=0, kappa=0, phi=0), z=1, m=0)] = \
        good[addrs[0]]
    with pytest.raises(ProtocolError):
        validate_counterfactual_envelope(addrs, extra, rows, sol=SOL, episode=ep)


def test_2f_the_referent_boundary_raises_a_protocol_error_not_a_substrate_one():
    r"""The runner's contract promises ``ProtocolError``; the substrate's type is separate.

    ``ReferenceContractError`` is deliberately a different class, and this boundary sits
    outside ``_run``, which already converts it. Without the conversion an illegal
    ``q_reference`` or a non-total ``sol.q`` would escape as a substrate exception — the
    same "the error path crashes first" defect this project keeps finding.
    """
    ep, rows, addrs, pre, _env = first_bent()
    class _Fake:
        pass

    with pytest.raises(ProtocolError) as ei:
        run_dq_law(CounterfactualReturnWrite, pre, addrs, rows, _Fake(), sol=SOL,
                   episode=ep)
    assert "referent boundary" in str(ei.value)
    # a sol whose q is not total on the domain
    partial = type("S", (), {"q": {next(iter(SOL.q)): next(iter(SOL.q.values()))}})()
    with pytest.raises(ProtocolError) as ei2:
        run_dq_law(CounterfactualReturnWrite, pre, addrs, rows, VIEW, sol=partial,
                   episode=ep)
    assert "referent boundary" in str(ei2.value)


def test_20_a_half_counterfactual_record_is_refused():
    r"""$a_t^+$ and $G_t^{CF}$ are one fact: both present or both absent.

    The witness is an address whose **shared alternative is already** ``None`` and a record
    that claims $G_t^{CF}$ anyway. With the paired-presence guard in place that record is
    refused; with the guard gone, ``alt is None`` makes the validator skip to the next
    address and the record is **accepted** — so the gate fails by ``DID NOT RAISE`` and the
    evidence says what it claims.

    An earlier witness perturbed an address that *has* an alternative, and the shared-$a^+$
    comparison rejected it whatever the pair guard did: that proved an error path existed,
    not that the guard was what stopped a half record.
    """
    ep, rows, addrs, _pre = healthy()
    env = build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
    without = next((a for a in addrs if env[a].a_plus is None), None)
    assert without is not None, "the healthy support is mostly addresses without one"
    lie = dict(env)
    lie[without] = CounterfactualTarget(without, env[without].a_factual,
                                        env[without].g_factual, None, 123.0)
    with pytest.raises(ProtocolError) as ei:
        validate_counterfactual_envelope(addrs, lie, rows, sol=SOL, episode=ep)
    assert "one fact" in str(ei.value)

    # and the mirror case, at an address that does have one
    ep2, rows2, addrs2, _pre2, good = with_alternative()
    victim = next(a for a in addrs2 if good[a].a_plus is not None)
    lie2 = dict(good)
    lie2[victim] = CounterfactualTarget(victim, good[victim].a_factual,
                                        good[victim].g_factual, good[victim].a_plus, None)
    with pytest.raises(ProtocolError) as ei2:
        validate_counterfactual_envelope(addrs2, lie2, rows2, sol=SOL, episode=ep2)
    assert "one fact" in str(ei2.value)


# --------------------------------------------------------------------------- #
# 4. the writes
# --------------------------------------------------------------------------- #

def test_12_no_valid_alternative_carries_a_status_and_writes_nothing():
    ep, rows, addrs, _pre = healthy()
    payload = {a: {"a_factual": 0, "g_factual": 1.0, "a_plus": None, "g_cf": None}
               for a in addrs}
    for law in (CounterfactualReturnWrite(), DualReturnWrite()):
        plan = law.plan(addrs, payload)
        assert all(p.edits == () for p in plan.plans), law.name
        assert all(p.status == NO_VALID_ALTERNATIVE for p in plan.plans), law.name


def test_12b_dual_does_not_degenerate_into_its_factual_half():
    r"""A76 §63.3: "a law may not degenerate at the same address — above all
    ``DualReturnWrite`` must not commit only its factual half"."""
    ep, rows, addrs, _pre = healthy()
    payload = {a: {"a_factual": 0, "g_factual": 1.0, "a_plus": None, "g_cf": None}
               for a in addrs}
    assert DualReturnWrite().plan(addrs, payload).edits == (), \
        "with no alternative, Dual writes nothing at all — not the factual entry alone"


def test_12c_dual_cannot_write_the_same_entry_twice():
    """The two entries are different actions, so one transaction cannot collide."""
    ep, rows, addrs, _pre = healthy()
    victim = addrs[0]
    with pytest.raises(ProtocolError) as ei:
        DualReturnWrite().plan([victim], {victim: {"a_factual": 3, "g_factual": 1.0,
                                                   "a_plus": 3, "g_cf": 2.0}})
    assert "not an alternative" in str(ei.value)


def test_13_dual_writes_two_entries_one_receipt_one_transaction():
    r"""$$N_{\text{scalar}} \le 2$$ at one addressed context, and exactly one receipt."""
    ep, rows, addrs, pre, _env = first_bent()
    calls = []
    original = LearnerPersistentState.apply_transaction

    def spy(self, edits, **kwargs):
        calls.append(tuple(edits))
        return original(self, edits, **kwargs)

    LearnerPersistentState.apply_transaction = spy
    try:
        res = run_dq_law(DualReturnWrite, pre, addrs, rows, VIEW, sol=SOL, episode=ep)
    finally:
        LearnerPersistentState.apply_transaction = original
    assert len(calls) == 1, f"one scene commits once, got {len(calls)}"
    assert res.ledger.n_addressed == len(addrs), "one receipt per credited context"
    per_address = {}
    for chg in pre.q_overrides:
        per_address.setdefault((chg.state, chg.z, chg.m), []).append(chg)
    assert max(len(v) for v in per_address.values()) <= 2


def test_13b_dual_commits_both_targets_from_the_same_pre_update_state():
    ep, rows, addrs, pre, env = first_bent()
    before = set(pre.q_overrides)
    run_dq_law(DualReturnWrite, pre, addrs, rows, VIEW, sol=SOL, episode=ep)
    written = {k: v for k, v in pre.q_overrides.items() if k not in before}
    assert written, "the bent probe must produce a real dual write"
    expect = {}
    for a in addrs:
        rec = env[a]
        if rec.a_plus is None:
            continue
        expect[QAddress(state=a.state, z=a.z, m=a.m, a=rec.a_factual)] = rec.g_factual
        expect[QAddress(state=a.state, z=a.z, m=a.m, a=rec.a_plus)] = rec.g_cf
    survivors = {k: v for k, v in expect.items() if float(v) != float(VIEW.value(k))}
    assert set(written) == set(survivors), (
        "the store holds exactly the two targets per context, MINUS any entry whose "
        "target is the reference value: those canonicalise to a deletion")
    for k, v in survivors.items():
        assert float(written[k]).hex() == float(v).hex()


# --------------------------------------------------------------------------- #
# 5. the regimes, and what this arm can do at all
# --------------------------------------------------------------------------- #

HEALTHY_WORLDS = tuple((k, p, z) for k in (0, 1) for p in range(6) for z in range(4))


def test_14_on_the_healthy_support_both_targets_are_the_reference():
    r"""Exhaustive over the frozen healthy support: $48$ worlds, $278$ addresses.

    | healthy support | |
    |---|---|
    | $G_t^F$ bit-equal to $Q_D^\ast(x_t,a_t^F)$ | 278/278 |
    | $G_t^{CF}$ bit-equal to $Q_D^\ast(x_t,a_t^+)$ | 32/32 |
    | addresses with a verified alternative | **32** |
    | addresses with **none** | **246** |

    The last two lines are the finding: on healthy scenes the factual action is usually
    the *unique* optimum, so most credited addresses carry ``NO_VALID_ALTERNATIVE`` and
    L2's reach there is 32 of 278. (A76's 3,600-of-431,280 figure describes the
    fault-injected support, where $a^F$ is usually *not* optimal — two different
    populations, and both statements are correct.)
    """
    n = with_alt = eq_f = eq_cf = 0
    for kappa, phi, z0 in HEALTHY_WORLDS:
        ep, rows, addrs, _pre = healthy(kappa, phi, z0)
        env = build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
        for a in addrs:
            rec = env[a]
            n += 1
            eq_f += rec.g_factual.hex() == float(VIEW.value(
                QAddress(state=a.state, z=a.z, m=a.m, a=rec.a_factual))).hex()
            if rec.a_plus is not None:
                with_alt += 1
                eq_cf += rec.g_cf.hex() == float(VIEW.value(
                    QAddress(state=a.state, z=a.z, m=a.m, a=rec.a_plus))).hex()
    assert n == 278, f"the healthy census moved: {n} addresses"
    assert eq_f == n, f"G_t^F must be the reference on healthy support ({eq_f}/{n})"
    assert eq_cf == with_alt, f"G_t^CF must be too ({eq_cf}/{with_alt})"
    assert (with_alt, n - with_alt) == (32, 246), (with_alt, n - with_alt)


def test_15_a_healthy_l2_run_changes_nothing():
    ep, rows, addrs, pre = healthy()
    for law in (CounterfactualReturnWrite, DualReturnWrite):
        state = LearnerPersistentState()
        res = run_dq_law(law, state, addrs, rows, VIEW, sol=SOL, episode=ep)
        led = res.ledger
        assert dict(state.q_overrides) == {}, law.name
        assert led.n_scalar == 0 and led.n_changed_addresses == 0, law.name
        assert led.fingerprint_pre == led.fingerprint_post, law.name
        assert set(r.status for r in led.receipts) <= {EVALUABLE_NOOP,
                                                       NO_VALID_ALTERNATIVE}, law.name
        led.check_fingerprint_invariants()


def test_16_on_a_fresh_store_the_target_USUALLY_equals_the_reference():
    r"""A probe-grid measurement, stated at the strength it actually has.

    Grid: $\kappa \in \{0,1\} \times \varphi \in \{0,1,2\} \times z_0 \in \{0,1,2\}
    \times$ fault-step $\in \{1,2\}$ — $36$ points, **not** the full
    $\kappa \times \varphi \times z_0 \times$ fault-step support — of which $15$ are
    feasible, $12$ have an inadmissible injection and $9$ have no counterfactual at all.
    Within the feasible ones, $35$ counterfactuals exist and $34$ are bit-equal to the
    reference, so the arm can act in $1$ of $35$ cases.

    $$\boxed{\text{fresh store} \Rightarrow G_t^{CF} = Q_D^\ast(x_t,a_t^+)
    \text{ is the usual case, not a theorem}}$$

    The exception is a counterexample, not a footnote: a realized suffix return equals the
    DP value only when the continuation *realizes* an optimal path, and the replay inherits
    the episode's remaining faults and tape.

    Provenance of these numbers, because they moved twice:
      $54/53$ was measured while a rejected replay was silently swallowed into
      ``NO_VALID_ALTERNATIVE``, which kept grid points alive that should have been excluded;
      $35/34$ is measured after that was removed and after ``replay`` was found to remove
      only ONE of the two channels that can inject a decision, so a counterfactual at
      $t = $ fault-step was not the replacement it claimed to be. Both defects are now
      fixed and the infeasible points are counted above.
    """
    feasible, reasons, cf_undefined = grid_scenes()
    total = equal = 0
    for ep, rows, addrs, _pre, env in feasible:
        for a in addrs:
            rec = env[a]
            if rec.a_plus is None:
                continue
            total += 1
            equal += rec.g_cf.hex() == float(VIEW.value(
                QAddress(state=a.state, z=a.z, m=a.m, a=rec.a_plus))).hex()
    assert (len(feasible), cf_undefined) == (15, 9)
    # Measured, and it corrects an earlier label: the 12 points without a factual faulted
    # episode are NOT "mask inadmissible". Two have no step t at all and ten have no
    # suboptimal admissible action to inject; a genuinely malformed mask injection occurs
    # ZERO times. Lumping them together made the grid look accounted for when only its
    # total was.
    assert reasons == {NO_STEP: 2, NO_SUBOPTIMAL: 10, MASK_MALFORMED: 0}, reasons
    assert (total, equal) == (35, 34), (total, equal)


def test_16b_no_counterfactual_is_undefined_on_the_healthy_support():
    r"""$$\boxed{N_{\text{undefined}} = 0}$$ on the healthy support.

    Healthy scenes carry no mask, so nothing can be inadmissible on a diverged path. This
    is the census that would have caught the swallowing: a nonzero value here means a
    counterfactual was silently reclassified rather than reported.
    """
    undefined = 0
    for kappa, phi, z0 in HEALTHY_WORLDS:
        ep, rows, addrs, _pre = healthy(kappa, phi, z0)
        try:
            build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
        except CounterfactualUndefined:
            undefined += 1
    assert undefined == 0, f"{undefined} healthy scenes had no counterfactual"


def test_17_prior_learning_is_ONE_mechanism_that_gives_the_arms_content():
    r"""Reachability: prior learning substantially raises L2 writability.

    Same grid as the probe above, but the pre-update store carries one entry that lifts a
    worse action at a context the counterfactual replay visits after $t$. Measured over
    the **18** grid points, exactly:

    $$\boxed{\text{9 admit the construction, and 9 of those 9 write; the other 9 admit none}}$$

    The claim is that prior learning is **an important mechanism**, not that it is the only
    one — the fresh-store probe above already exhibits a non-reference target with no prior
    learning at all. (An earlier revision of this file reported "9 of 12"; 12 was the count
    of constructions a *different* helper happened to complete, not the grid size, and the
    two numbers were never measuring the same thing.)
    """
    acts = infeasible = 0
    for kappa in (0, 1):
        for phi in (0, 1, 2):
            for z0 in (0, 1, 2):
                built = bent_scene(kappa, phi, z0)
                if built is None:
                    infeasible += 1
                    continue
                ep, rows, addrs, pre, _env = built
                res = run_dq_law(CounterfactualReturnWrite, pre, addrs, rows, VIEW,
                                 sol=SOL, episode=ep)
                res.ledger.check_fingerprint_invariants()
                acts += res.ledger.n_scalar > 0
    assert (acts, infeasible) == (9, 9), (acts, infeasible)


def test_18_a_bent_run_writes_real_entries_and_keeps_the_ledger_sound():
    ep, rows, addrs, pre, env = first_bent()
    res = run_dq_law(CounterfactualReturnWrite, pre, addrs, rows, VIEW, sol=SOL,
                     episode=ep)
    led = res.ledger
    assert led.scalar_metrics_applicable is True
    assert led.n_scalar >= 1, "the bent probe must write"
    assert led.n_changed_addresses >= 1
    assert led.fingerprint_pre != led.fingerprint_post
    written = dict(pre.q_overrides)
    for a in addrs:
        rec = env[a]
        status = next(r.status for r in led.receipts if r.address == a)
        if rec.a_plus is None:
            assert status == NO_VALID_ALTERNATIVE
        elif QAddress(state=a.state, z=a.z, m=a.m, a=rec.a_plus) in written:
            assert written[QAddress(state=a.state, z=a.z, m=a.m,
                                    a=rec.a_plus)].hex() == rec.g_cf.hex()
    led.check_fingerprint_invariants()


def test_21_the_L0_entry_point_refuses_an_L2_law():
    ep, rows, addrs, _pre = healthy()
    with pytest.raises(ProtocolError) as ei:
        run_factual_return_law(CounterfactualReturnWrite, LearnerPersistentState(),
                               addrs, rows, VIEW)
    assert "builds the L0 cell only" in str(ei.value)


def test_22_the_l2_cell_needs_the_shared_adapter_and_the_episode():
    ep, rows, addrs, _pre = healthy()
    for kwargs in ({"episode": ep}, {"sol": SOL}):
        with pytest.raises(ProtocolError) as ei:
            run_dq_law(CounterfactualReturnWrite, LearnerPersistentState(), addrs, rows,
                       VIEW, **kwargs)
        assert "shared a^+ adapter" in str(ei.value)


def test_23_an_implemented_tier_must_be_a_tier():
    r"""The build set is typed before anything reads ``.name`` (A77 §65.1)."""
    cells = {Tier.L0_FACTUAL: frozenset(), Tier.L1_CORRECTIVE: ILL_TYPED,
             Tier.L2_COUNTERFACTUAL: ILL_TYPED, Tier.L3_ORACLE: frozenset()}
    with pytest.raises(ProtocolError) as ei:
        SliceDescriptor(name="BadBuild", store=Q, scalar=False, owner=owner_Q,
                        view=lambda st: {}, cells=cells, extract={},
                        implemented_tiers=frozenset({0}))
    assert "Tier members" in str(ei.value)
    assert not isinstance(ei.value, AttributeError)


def test_24_the_registries_are_separate_and_the_counts_do_not_move():
    assert [law.name for law in DQ_LAWS] == ["NoWrite", "FactualReturnWrite", "NoWrite",
                                             "CounterfactualReturnWrite",
                                             "DualReturnWrite"]
    kinds = [k for _n, k, _a in law_metadata(DQ_LAWS)]
    assert kinds == ["reference", "operation", "reference", "operation", "operation"]
    assert independent_treatment_count(DQ_LAWS) == 3
    assert independent_treatment_count() == 3
