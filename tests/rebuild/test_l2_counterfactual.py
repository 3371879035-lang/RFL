r"""A77 §65.7, §65.8, §65.10 — $D_Q\times L_2$: the counterfactual target and its laws.

The step's scientific question:

$$\boxed{\text{a verified alternative} \to \text{one correctly configured replay}
\to \text{an exact counterfactual target} \to \text{the right writes}}$$

and the gates are grouped by the ways it can be wrong:

1. **the configuration** — the replay must differ from the factual episode in exactly one
   thing, and in particular must carry $\texttt{DecisionReadView}_{pre}$;
2. **the prefix invariant** — and what it can and cannot catch, demonstrated rather than
   asserted;
3. **the target** — the frozen fold over the *counterfactual* rows, and the same $a^+$ the
   other arms use;
4. **the writes** — two arms, their entry counts, the no-degeneration rule, and the
   healthy and faulted ledger behaviour.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1 import (  # noqa: E402
    APPLIED, DQ_LAWS, DQ_SLICE, EVALUABLE_NOOP, NO_VALID_ALTERNATIVE, CfEpisode,
    CounterfactualReturnWrite, CounterfactualTarget, DualReturnWrite,
    FactualReturnWrite, ILL_TYPED, NoWriteRef, ProtocolError, SliceDescriptor, Tier,
    build_counterfactual_envelope,
    build_target_envelope, independent_treatment_count,
    law_metadata, replay_with_decision_replaced, resolve_credited_units,
    run_dq_law, run_factual_return_law, validate_counterfactual_envelope,
)
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import ControlState, DecisionOverride, FaultMask  # noqa: E402
from rfl_rebuild.env.observation import learner_rows, walk_transition  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    Edit, LearnerPersistentState, Q, QAddress, owner_Q,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

SOL = solve_reference()
VIEW = reference_view_from(SOL)
REFERENCE_PROVIDER = lambda s, c: SOL.best_action(s, c.z, c.m)      # noqa: E731


# --------------------------------------------------------------------------- #
# scene construction
# --------------------------------------------------------------------------- #

def episode_for(trace, kappa, phi, provider, z0, mask=None):
    return CfEpisode(trace=trace, kappa=kappa, phi=phi,
                     tape=K.SemanticTape(phase=phi, error_flag=0, cause_rank=0),
                     decision_read_view_pre=provider, base_option=z0,
                     mask=mask or K.FaultMask())


def roll(kappa=0, phi=0, z0=1, mask=None, provider=None):
    return K.rollout(kappa=kappa, tape=K.SemanticTape(phase=phi, error_flag=0,
                                                      cause_rank=0),
                     command_provider=provider or REFERENCE_PROVIDER,
                     base_option=z0, mask=mask or K.FaultMask())


def addresses(trace, kappa, phi):
    rows = learner_rows(trace, kappa, phi)
    steps = sorted({r[2] for r in rows})
    return rows, resolve_credited_units(tuple(f"Decision_{t}" for t in steps),
                                        trace, kappa, phi)


def healthy(kappa=0, phi=0, z0=1):
    trace = roll(kappa, phi, z0)
    rows, addrs = addresses(trace, kappa, phi)
    return trace, rows, addrs, episode_for(trace, kappa, phi, REFERENCE_PROVIDER, z0)


def faulted(kappa=0, phi=0, z0=1, t=1):
    """A $Z_D$ injection, so the factual trajectory is not the reference one."""
    probe = roll(kappa, phi, z0)
    ctx = list(walk_transition(probe, kappa, phi, probe.option_in_force))[t]
    s, z, m = ctx[0], ctx[1], ctx[2]
    best = SOL.best_action(s, z, m)
    allowed = [a for a in sorted(K.option_actions(z, ControlState(z=z, m=m), s))
               if a != best]
    if not allowed:
        pytest.skip("no suboptimal admissible action at this probe")   # pragma: no cover
    mask = FaultMask(decision=DecisionOverride(t=t, action=allowed[0]))
    trace = roll(kappa, phi, z0, mask=mask)
    rows, addrs = addresses(trace, kappa, phi)
    return trace, rows, addrs, episode_for(trace, kappa, phi, REFERENCE_PROVIDER, z0,
                                           mask=mask)


# --------------------------------------------------------------------------- #
# 1. the configuration
# --------------------------------------------------------------------------- #

def test_1_the_replay_passes_the_factual_configuration_through_unchanged(monkeypatch):
    """Differing in exactly one thing is a property of the *call*, not of a promise."""
    trace, rows, addrs, ep = healthy()
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
    assert seen["controller"] is ep.controller
    assert seen["learner_process_commit"] is ep.learner_process_commit
    assert seen["reward_mode"] == "A"
    assert seen["command_provider"] is ep.decision_read_view_pre, \
        "the replay must run the pre-update decision read path, not a fresh reference"


def test_2_the_decision_intervention_is_replaced_not_added():
    """A factual episode that already intervened at t keeps exactly one decision there."""
    trace, rows, addrs, ep = healthy()
    full = build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
    picked = next((a for a in addrs if full[a].a_plus is not None), None)
    if picked is None:
        pytest.skip("this scene has no alternative")                  # pragma: no cover
    t = picked.state.t
    a_plus = full[picked].a_plus
    base = CfEpisode(trace=ep.trace, kappa=ep.kappa, phi=ep.phi, tape=ep.tape,
                     decision_read_view_pre=ep.decision_read_view_pre,
                     base_option=ep.base_option,
                     interventions=K.InterventionSet(
                         (K.Intervention.decision(t, a_plus),)))
    cf = replay_with_decision_replaced(base, t, a_plus)
    assert cf is not None
    assert len(base.interventions.members) == 1
    # adding rather than replacing would raise MalformedIntervention from InterventionSet
    with pytest.raises(K.MalformedIntervention):
        K.InterventionSet(base.interventions.members
                          + (K.Intervention.decision(t, a_plus),))


# --------------------------------------------------------------------------- #
# 2. the prefix invariant: demonstrated, including what it cannot catch
# --------------------------------------------------------------------------- #

def test_3_a_replay_that_drops_the_pre_update_view_is_caught_by_the_prefix():
    r"""The gate the whole clause exists for.

    An earlier episode's update sits at a context the factual episode meets **before** $t$.
    Replaying with the reference provider instead of $\texttt{DecisionReadView}_{pre}$
    diverges there, and the prefix equality fails stop — it must never be absorbed into a
    $G^{CF}$ of zero.
    """
    s = LearnerPersistentState()
    first = learner_rows(roll(0, 0, 1), 0, 0)[0]
    ctx0 = (first[0], first[1], first[2], first[3], first[4])          # x, y, t, kappa, phi
    from rfl_rebuild.learner.store import DecisionAddress, State
    addr0 = DecisionAddress(state=State(x=ctx0[0], y=ctx0[1], t=ctx0[2], kappa=ctx0[3],
                                        phi=ctx0[4]), z=first[5], m=first[6])
    base_a = REFERENCE_PROVIDER(addr0.state, ControlState(z=addr0.z, m=addr0.m))
    other = [a for a in sorted(K.option_actions(addr0.z, ControlState(z=addr0.z, m=addr0.m),
                                                addr0.state)) if a != base_a]
    if not other:
        pytest.skip("the first context admits only one action")       # pragma: no cover
    s.apply_transaction(
        [Edit("q", QAddress(state=addr0.state, z=addr0.z, m=addr0.m, a=other[0]),
              VIEW.value(QAddress(state=addr0.state, z=addr0.z, m=addr0.m,
                                  a=other[0])) + 0.25)],
        q_reference=VIEW)
    view_pre = s.snapshot().q_decision_provider(VIEW)

    trace = roll(0, 0, 1, provider=view_pre)
    rows, addrs = addresses(trace, 0, 0)
    if len(addrs) < 2:
        pytest.skip("this scene has one credited context")            # pragma: no cover
    late = addrs[-1]
    assert late.state.t > 0, "the probe needs an address after the overridden context"

    # correct configuration: the pre-update view, so the factual prefix is reproduced
    good = episode_for(trace, 0, 0, view_pre, 1)
    build_counterfactual_envelope(rows, addrs, sol=SOL, episode=good)

    # wrong configuration: a fresh reference provider, i.e. the drop this guards against
    wrong = episode_for(trace, 0, 0, REFERENCE_PROVIDER, 1)
    with pytest.raises(ProtocolError) as ei:
        build_counterfactual_envelope(rows, addrs, sol=SOL, episode=wrong)
    assert "does not share the factual prefix" in str(ei.value), ei.value


def test_3b_the_view_is_live_after_t_as_well_where_the_prefix_cannot_see_it():
    r"""The invariant's honest limit, turned into positive evidence.

    A replay that dropped the view would diverge in the prefix **only if** the defect is
    met before $t$. So the closure is structural, and the witness that the view is live in
    the *suffix* is that the target value responds to it: an override at a context visited
    after $t$ changes $G_t^{CF}$ while leaving the prefix identical.
    """
    s = LearnerPersistentState()
    trace0 = roll(0, 0, 1)
    rows0, addrs0 = addresses(trace0, 0, 0)
    if len(addrs0) < 2:
        pytest.skip("this scene has one credited context")            # pragma: no cover
    target_ctx = addrs0[-1]
    base_a = REFERENCE_PROVIDER(target_ctx.state,
                               ControlState(z=target_ctx.z, m=target_ctx.m))
    allowed = sorted(K.option_actions(target_ctx.z,
                                      ControlState(z=target_ctx.z, m=target_ctx.m),
                                      target_ctx.state))
    other = [a for a in allowed if a != base_a]
    if not other:
        pytest.skip("the last context admits only one action")        # pragma: no cover
    entry = QAddress(state=target_ctx.state, z=target_ctx.z, m=target_ctx.m, a=other[0])
    s.apply_transaction([Edit("q", entry, VIEW.value(entry) + 0.25)], q_reference=VIEW)
    view_pre = s.snapshot().q_decision_provider(VIEW)

    trace = roll(0, 0, 1, provider=view_pre)
    rows, addrs = addresses(trace, 0, 0)
    early = [a for a in addrs if a.state.t < target_ctx.state.t]
    assert early, "need a credited context strictly before the override"

    with_view = build_counterfactual_envelope(
        rows, addrs, sol=SOL, episode=episode_for(trace, 0, 0, view_pre, 1))
    without = build_counterfactual_envelope(
        rows, addrs, sol=SOL,
        episode=episode_for(trace, 0, 0, REFERENCE_PROVIDER, 1))
    compared = 0
    for a in early:
        if with_view[a].a_plus is None or without[a].a_plus is None:
            continue
        assert with_view[a].a_plus == without[a].a_plus, "the alternative is a property " \
            "of the context, not of the view"
        compared += 1
        if with_view[a].g_cf != without[a].g_cf:
            return
    assert compared, "no comparable counterfactual in this probe"   # pragma: no cover
    pytest.fail("the suffix return must respond to the pre-update view somewhere; "
                "otherwise the view is decorative")


# --------------------------------------------------------------------------- #
# 3. the target
# --------------------------------------------------------------------------- #

def test_4_the_cf_target_is_the_frozen_fold_over_the_counterfactual_rows():
    """Not the factual suffix, and not a suffix simulation: the replay is full."""
    trace, rows, addrs, ep = faulted()
    env = build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
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
    assert checked >= 1, "the faulted probe must expose at least one counterfactual"


def test_5_a_perturbed_counterfactual_return_is_rejected():
    """The validator re-derives and compares bit patterns, not values."""
    trace, rows, addrs, ep = faulted()
    good = dict(build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep))
    victim = next((a for a in addrs if good[a].a_plus is not None), None)
    if victim is None:
        pytest.skip("no alternative in this probe")                   # pragma: no cover
    lie = dict(good)
    lie[victim] = CounterfactualTarget(victim, good[victim].a_factual,
                                       good[victim].g_factual, good[victim].a_plus,
                                       good[victim].g_cf + 1e-9)
    with pytest.raises(ProtocolError) as ei:
        validate_counterfactual_envelope(addrs, lie, rows, sol=SOL, episode=ep)
    assert "frozen replay-and-fold" in str(ei.value)


def test_5b_a_substituted_alternative_is_rejected():
    """Every compatible arm uses the same $a^+$ (A76 §63.3)."""
    trace, rows, addrs, ep = faulted()
    good = dict(build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep))
    victim = next((a for a in addrs if good[a].a_plus is not None), None)
    if victim is None:
        pytest.skip("no alternative in this probe")                   # pragma: no cover
    allowed = sorted(K.option_actions(victim.z, ControlState(z=victim.z, m=victim.m),
                                      victim.state))
    other = [a for a in allowed if a not in (good[victim].a_plus,
                                             good[victim].a_factual)]
    if not other:
        pytest.skip("no third admissible action here")                # pragma: no cover
    lie = dict(good)
    lie[victim] = CounterfactualTarget(victim, good[victim].a_factual,
                                       good[victim].g_factual, other[0],
                                       good[victim].g_cf)
    with pytest.raises(ProtocolError) as ei:
        validate_counterfactual_envelope(addrs, lie, rows, sol=SOL, episode=ep)
    assert "every compatible arm uses the same a^+" in str(ei.value)


def test_6_the_alternative_is_the_same_object_the_patch_arm_uses():
    """One $a^+$ adapter for every compatible arm, not one per architecture."""
    trace, rows, addrs, ep = faulted()
    env = build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
    patch = build_target_envelope(SOL, addrs, trace, ep.kappa, ep.phi)
    assert all(env[a].a_plus == patch[a].alternative for a in addrs)


def test_7_the_delivered_cell_is_exactly_the_four_l2_fields():
    trace, rows, addrs, ep = healthy()
    env = build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
    delivered = DQ_SLICE.deliver(Tier.L2_COUNTERFACTUAL, addrs, env)
    for _addr, fields in delivered.items():
        assert set(fields) == {"a_factual", "g_factual", "a_plus", "g_cf"}


# --------------------------------------------------------------------------- #
# 4. the writes
# --------------------------------------------------------------------------- #

def bent_scene(kappa=0, phi=0, z0=1, lift=100.0):
    r"""A scene whose **pre-update** decision policy is already off $\pi^\ast$.

    On a fresh store the counterfactual target equals the reference — the replay's suffix
    is an optimal continuation — so the L2 arms have nothing to write. They acquire
    content exactly when prior learning has bent the policy: here one entry is lifted at a
    context the *counterfactual replay itself* visits after $t$, which moves the suffix off
    the optimal path while leaving the factual prefix untouched.

    The context has to be one the replay reaches, and which contexts those are depends on
    the intervention, so candidates are tried in a deterministic order and the first one
    that yields a non-reference counterfactual is taken. If none does, the helper **fails**
    rather than skips: a silently skipped probe is a gate that stopped looking.
    """
    base = roll(kappa, phi, z0)
    rows, addrs = addresses(base, kappa, phi)
    patch = build_target_envelope(SOL, addrs, base, kappa, phi)
    first = next((a for a in addrs if patch[a].alternative is not None), None)
    if first is None:
        pytest.skip("this scene has no alternative anywhere")         # pragma: no cover
    t0 = first.state.t
    trial = roll(kappa, phi, z0,
                 mask=FaultMask(decision=DecisionOverride(t=t0,
                                                          action=patch[first].alternative)))
    from rfl_rebuild.learner.store import DecisionAddress, State
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
        view_pre = pre.snapshot().q_decision_provider(VIEW)
        trace = roll(kappa, phi, z0, provider=view_pre)
        rows2, addrs2 = addresses(trace, kappa, phi)
        ep = episode_for(trace, kappa, phi, view_pre, z0)
        env = build_counterfactual_envelope(rows2, addrs2, sol=SOL, episode=ep)
        for a in addrs2:
            rec = env[a]
            if rec.a_plus is None:
                continue
            if rec.g_cf != VIEW.value(QAddress(state=a.state, z=a.z, m=a.m,
                                               a=rec.a_plus)):
                return trace, rows2, addrs2, ep, pre
    pytest.fail("no lift at a replayed context moved the counterfactual off the "
                "reference in this scene")


def make_envelope(addresses_, *, a_plus=None, g_factual=1.0, g_cf=2.0):
    """A minimal delivered payload, for exercising the laws' own rules."""
    return {a: {"a_factual": 0, "g_factual": g_factual, "a_plus": a_plus, "g_cf": g_cf}
            for a in addresses_}


def test_8_no_valid_alternative_carries_a_status_and_writes_nothing():
    trace, rows, addrs, ep = healthy()
    payload = make_envelope(addrs, a_plus=None)
    for law in (CounterfactualReturnWrite(), DualReturnWrite()):
        plan = law.plan(addrs, payload)
        assert all(p.edits == () for p in plan.plans), law.name
        assert all(p.status == NO_VALID_ALTERNATIVE for p in plan.plans), law.name


def test_8b_dual_does_not_degenerate_into_its_factual_half():
    r"""A76 §63.3: "a law may not degenerate at the same address — above all
    ``DualReturnWrite`` must not commit only its factual half"."""
    trace, rows, addrs, ep = healthy()
    payload = make_envelope(addrs, a_plus=None, g_factual=1.0)
    plan = DualReturnWrite().plan(addrs, payload)
    assert plan.edits == (), \
        "with no alternative, Dual writes nothing at all — not the factual entry alone"


def test_9_counterfactual_writes_one_entry_per_context():
    trace, rows, addrs, ep = healthy()
    victim = addrs[0]
    env = {a: {"a_factual": 0, "g_factual": 1.0, "a_plus": 2, "g_cf": 2.0}
           for a in addrs}
    plan = CounterfactualReturnWrite().plan(addrs, env)
    assert all(len(p.edits) == 1 for p in plan.plans)
    assert plan.plans[0].edits[0].address.a == 2


def test_10_dual_writes_two_entries_one_receipt_one_transaction():
    r"""$$N_{\text{scalar}} \le 2$$ at one addressed context, and exactly one receipt.

    Run on a bent pre-update policy, because on a fresh store the L2 targets are the
    reference values and the arms legitimately write nothing — a test of the write path
    has to be a test of a run that writes.
    """
    trace, rows, addrs, ep, _pre = bent_scene()
    calls = []
    original = LearnerPersistentState.apply_transaction

    def spy(self, edits, **kwargs):
        calls.append(tuple(edits))
        return original(self, edits, **kwargs)

    LearnerPersistentState.apply_transaction = spy
    try:
        state = LearnerPersistentState()
        res = run_dq_law(DualReturnWrite, state, addrs, rows, VIEW, sol=SOL, episode=ep)
    finally:
        LearnerPersistentState.apply_transaction = original
    assert len(calls) == 1, f"one scene commits once, got {len(calls)}"
    assert res.ledger.n_addressed == len(addrs), "one receipt per credited context"
    assert res.ledger.n_scalar <= 2 * len(addrs)
    per_address = {}
    for chg in state.q_overrides:
        per_address.setdefault((chg.state, chg.z, chg.m), []).append(chg)
    assert max(len(v) for v in per_address.values()) <= 2


def test_10b_dual_commits_both_targets_from_the_same_pre_update_state():
    """The two written values are the two envelope targets, not a sequential pair."""
    trace, rows, addrs, ep, _pre = bent_scene()
    env = build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
    state = LearnerPersistentState()
    run_dq_law(DualReturnWrite, state, addrs, rows, VIEW, sol=SOL, episode=ep)
    written = dict(state.q_overrides)
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
        "the store must hold exactly the two targets per context, MINUS any entry whose "
        "target is the reference value: those canonicalise to a deletion, and their "
        "absence is the same discipline L0 relies on")
    for k, v in survivors.items():
        assert float(written[k]).hex() == float(v).hex()


# --------------------------------------------------------------------------- #
# 5. the ledger on both regimes
# --------------------------------------------------------------------------- #

def test_11_on_the_healthy_support_both_l2_targets_are_the_reference():
    r"""A measured property, and a surprising one.

    On a healthy trajectory $a_t^F$ is optimal, so **both** targets land exactly on the
    reference: $G_t^F = Q_D^\ast(x_t,a_t^F)$ and $G_t^{CF} = Q_D^\ast(x_t,a_t^+)$. L2 is
    therefore a complete no-op on healthy scenes, by the same canonicalisation that makes
    L0 one — and the census also measures how often the cell can act at all:

    | healthy support (48 worlds, 278 addresses) | |
    |---|---|
    | $G_t^F$ bit-equal to $Q_D^\ast(x_t,a_t^F)$ | 278/278 |
    | $G_t^{CF}$ bit-equal to $Q_D^\ast(x_t,a_t^+)$ | 32/32 |
    | addresses with **no** alternative | **246/278** |

    The last line is the finding: on healthy scenes the factual action is usually the
    *unique* optimum, so most credited addresses carry ``NO_VALID_ALTERNATIVE``. L2's
    reach in the healthy regime is 32 of 278 addresses, not all of them.
    """
    n = with_alt = eq_f = eq_cf = 0
    for kappa in (0, 1):
        for phi in K.PHASE_DOMAIN:
            for z0 in K.option_ids():
                trace = roll(kappa, phi, z0)
                rows, addrs = addresses(trace, kappa, phi)
                ep = episode_for(trace, kappa, phi, REFERENCE_PROVIDER, z0)
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
    assert n == 278, f"the census must cover the healthy support, covered {n}"
    assert eq_f == n, f"G_t^F must be the reference on healthy support ({eq_f}/{n})"
    assert eq_cf == with_alt, f"G_t^CF must be too ({eq_cf}/{with_alt})"
    assert with_alt == 32, f"the healthy reach of L2 moved: {with_alt}/278"
    assert n - with_alt == 246


def test_11b_a_healthy_l2_run_changes_nothing():
    trace, rows, addrs, ep = healthy()
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


def test_11c_on_a_fresh_store_the_counterfactual_target_is_the_reference():
    r"""The measurement that decides what the L2 arms can do at all.

    With an empty store the pre-update view *is* $\pi^\ast$, so the replay takes an optimal
    action at $t$ and then an optimal continuation: the realized suffix return lands on
    $Q_D^\ast(x_t,a_t^+)$, the write canonicalises to a deletion, and the arm is a no-op.

    Measured over $\kappa\times\varphi\times z_0\times$ fault-step (35 counterfactuals that
    exist at all):

    $$\boxed{34/35 \text{ bit-equal to the reference} \quad\Longrightarrow\quad
    \text{the arm can act in } 1/35}$$

    The exception is the point rather than noise: a realized suffix return equals the DP
    value only when the continuation *realizes* an optimal path, and the replay inherits
    the factual episode's remaining faults and tape.
    """
    total = equal = 0
    for kappa in (0, 1):
        for phi in (0, 1, 2):
            for z0 in (0, 1, 2):
                base = roll(kappa, phi, z0)
                for ft in (1, 2):
                    try:
                        ctxs = list(walk_transition(base, kappa, phi,
                                                    base.option_in_force))
                        if len(ctxs) <= ft:
                            continue
                        ctx = ctxs[ft]
                        s, z, m = ctx[0], ctx[1], ctx[2]
                        if s.t != ft:
                            continue
                        allowed = [a for a in sorted(
                            K.option_actions(z, ControlState(z=z, m=m), s))
                            if a != SOL.best_action(s, z, m)]
                        if not allowed:
                            continue
                        mask = FaultMask(decision=DecisionOverride(t=ft,
                                                                   action=allowed[0]))
                        trace = roll(kappa, phi, z0, mask=mask)
                        rows, addrs = addresses(trace, kappa, phi)
                        ep = episode_for(trace, kappa, phi, REFERENCE_PROVIDER, z0,
                                         mask=mask)
                        env = build_counterfactual_envelope(rows, addrs, sol=SOL,
                                                            episode=ep)
                    except (K.MalformedIntervention, ProtocolError):
                        continue
                    for a in addrs:
                        rec = env[a]
                        if rec.a_plus is None:
                            continue
                        total += 1
                        equal += rec.g_cf.hex() == float(VIEW.value(
                            QAddress(state=a.state, z=a.z, m=a.m,
                                     a=rec.a_plus))).hex()
    assert total == 35, f"the faulted census moved: {total} counterfactuals"
    assert equal == 34, f"the fresh-store identity moved: {equal}/{total}"


def test_11d_prior_learning_is_what_gives_the_l2_arms_content():
    r"""Reachability, not construction: the arm acts only on an already-bent policy.

    Same scenes as the census, but the pre-update store carries one entry that lifts a
    worse action at a context the replay meets after $t$. The suffix then leaves the
    optimal path, $G_t^{CF} < Q_D^\ast(x_t,a_t^+)$, and both L2 arms write. Measured: 9 of
    12 constructed scenes act, and the three that do not are ones where the lifted entry
    never changes the chosen action.
    """
    acts = tried = 0
    for kappa in (0, 1):
        for phi in (0, 1, 2):
            for z0 in (0, 1, 2):
                try:
                    trace, rows, addrs, ep, _pre = bent_scene(kappa, phi, z0)
                except Exception:
                    continue
                tried += 1
                state = LearnerPersistentState()
                res = run_dq_law(CounterfactualReturnWrite, state, addrs, rows, VIEW,
                                 sol=SOL, episode=ep)
                res.ledger.check_fingerprint_invariants()
                if res.ledger.n_scalar > 0:
                    acts += 1
                    for a in addrs:
                        if any(k.state == a.state and k.z == a.z and k.m == a.m
                               for k in state.q_overrides):
                            break
    assert tried >= 9, f"the bent probe shrank: {tried} scenes"
    assert acts >= 9, f"the CF arm lost its reach: acts in {acts}/{tried}"


def test_11e_a_bent_run_writes_real_entries_and_keeps_the_ledger_sound():
    trace, rows, addrs, ep, _pre = bent_scene()
    env = build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep)
    state = LearnerPersistentState()
    res = run_dq_law(CounterfactualReturnWrite, state, addrs, rows, VIEW, sol=SOL,
                     episode=ep)
    led = res.ledger
    assert led.scalar_metrics_applicable is True
    assert led.n_scalar >= 1, "the bent probe must write"
    assert led.n_changed_addresses >= 1
    assert led.fingerprint_pre != led.fingerprint_post
    written = dict(state.q_overrides)
    for a in addrs:
        rec = env[a]
        if rec.a_plus is not None and QAddress(state=a.state, z=a.z, m=a.m,
                                               a=rec.a_plus) in written:
            assert written[QAddress(state=a.state, z=a.z, m=a.m,
                                    a=rec.a_plus)].hex() == rec.g_cf.hex()
        status = next(r.status for r in led.receipts if r.address == a)
        if rec.a_plus is None:
            assert status == NO_VALID_ALTERNATIVE
    led.check_fingerprint_invariants()


def test_12_the_L0_entry_point_refuses_an_L2_law():
    trace, rows, addrs, ep = healthy()
    with pytest.raises(ProtocolError) as ei:
        run_factual_return_law(CounterfactualReturnWrite, LearnerPersistentState(),
                               addrs, rows, VIEW)
    assert "builds the L0 cell only" in str(ei.value)


def test_13_the_l2_cell_needs_the_shared_adapter_and_the_episode():
    trace, rows, addrs, ep = healthy()
    for kwargs in ({"episode": ep}, {"sol": SOL}):
        with pytest.raises(ProtocolError) as ei:
            run_dq_law(CounterfactualReturnWrite, LearnerPersistentState(), addrs, rows,
                       VIEW, **kwargs)
        assert "shared a^+ adapter" in str(ei.value)


def test_14_a_half_counterfactual_record_is_refused():
    r"""$a_t^+$ and $G_t^{CF}$ are one fact: both present or both absent.

    Expressible separately, "the alternative is unknown" and "its return is unknown" would
    become different states of the envelope, and a law could act on one without the other.
    """
    trace, rows, addrs, ep = faulted()
    good = dict(build_counterfactual_envelope(rows, addrs, sol=SOL, episode=ep))
    victim = next((a for a in addrs if good[a].a_plus is not None), None)
    if victim is None:
        pytest.skip("no alternative in this probe")                   # pragma: no cover
    for bad in (CounterfactualTarget(victim, good[victim].a_factual,
                                     good[victim].g_factual, None, good[victim].g_cf),
                CounterfactualTarget(victim, good[victim].a_factual,
                                     good[victim].g_factual, good[victim].a_plus, None)):
        lie = dict(good)
        lie[victim] = bad
        with pytest.raises(ProtocolError) as ei:
            validate_counterfactual_envelope(addrs, lie, rows, sol=SOL, episode=ep)
        assert "one fact" in str(ei.value)


def test_15_a_dual_plan_cannot_write_the_same_entry_twice():
    """The two entries are different actions, so one transaction cannot collide.

    Without the guard, an alternative equal to the factual command would put two edits on
    one address; the store's last-write-wins would then decide the value by list order, and
    the same plan would mean different things depending on how it was built.
    """
    trace, rows, addrs, ep = healthy()
    victim = addrs[0]
    payload = {a: {"a_factual": 3, "g_factual": 1.0, "a_plus": 3, "g_cf": 2.0}
               for a in [victim]}
    with pytest.raises(ProtocolError) as ei:
        DualReturnWrite().plan([victim], payload)
    assert "not an alternative" in str(ei.value)


def test_16_an_implemented_tier_must_be_a_tier():
    r"""The build set is typed before anything reads ``.name`` (A77 §65.1).

    ``implemented_tiers={0}`` used to reach an ``AttributeError`` from inside the
    validation that exists to catch exactly this kind of malformed descriptor.
    """
    cells = {Tier.L0_FACTUAL: frozenset(), Tier.L1_CORRECTIVE: ILL_TYPED,
             Tier.L2_COUNTERFACTUAL: ILL_TYPED, Tier.L3_ORACLE: frozenset()}
    with pytest.raises(ProtocolError) as ei:
        SliceDescriptor(name="BadBuild", store=Q, scalar=False, owner=owner_Q,
                        view=lambda st: {}, cells=cells, extract={},
                        implemented_tiers=frozenset({0}))
    assert "not\nTier members" in str(ei.value).replace("\n", " ") or \
        "Tier members" in str(ei.value)
    assert not isinstance(ei.value, AttributeError)
