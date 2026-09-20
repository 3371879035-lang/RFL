r"""A77 §65.6, §65.8, §65.10 — $D_Q\times L_0$: `FactualReturnWrite`.

The scientific question this step answers:

$$\boxed{\text{learner-visible factual experience} \to \text{exact factual target}
\to \text{one correctly scoped } Q\text{ update}}$$

so the gates are grouped by the four ways it can go wrong:

1. **the information source** — the builder must not be *able* to read the evaluator, and
   the law must not be handed anything beyond $\{a_t^F, G_t^F\}$;
2. **the reverse fold** — $G_t^F$ must be bit-identical to $Q_D^\ast$ on healthy support,
   because a target that merely rounds to the reference will not canonicalise to nothing;
3. **the healthy write** — it must land on the reference and therefore be a true no-op,
   leaving the store empty;
4. **the faulted write** — the observed suffix return must produce a real, non-oracle
   override carrying exactly that value.
"""

from __future__ import annotations

import ast
import math
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1 import (  # noqa: E402
    APPLIED, DQ_DOMAIN, DQ_LAWS, DQ_SLICE, EVALUABLE_NOOP, ILL_TYPED, FactualReturnWrite,
    FactualTarget,
    NoWriteRef, PATCH_SLICE, ProtocolError, SliceDescriptor, Tier,
    build_factual_envelope,
    factual_return_to_go, fingerprint, independent_treatment_count, law_metadata,
    resolve_credited_units, run_factual_return_law, run_patch_law_with_envelope,
    validate_factual_envelope,
)
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import ControlState, DecisionOverride, FaultMask, State  # noqa: E402
from rfl_rebuild.env.observation import learner_rows, walk_transition  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    LearnerPersistentState, Q, QAddress, owner_Q,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

SOL = solve_reference()
VIEW = reference_view_from(SOL)


# --------------------------------------------------------------------------- #
# scene helpers
# --------------------------------------------------------------------------- #

def healthy_scene(kappa=0, phi=0, z0=1):
    trace = K.rollout(
        kappa=kappa, tape=K.SemanticTape(phase=phi, error_flag=0, cause_rank=0),
        command_provider=lambda s, c: SOL.best_action(s, c.z, c.m), base_option=z0)
    return trace, learner_rows(trace, kappa, phi), kappa, phi


def faulted_scene(kappa=0, phi=0, z0=1, t=1):
    """A scene whose factual return is *not* the reference: a $Z_D$ injection at ``t``."""
    probe = healthy_scene(kappa, phi, z0)[0]
    ctx = list(walk_transition(probe, kappa, phi, probe.option_in_force))[t]
    s, z, m = ctx[0], ctx[1], ctx[2]
    best = SOL.best_action(s, z, m)
    allowed = [a for a in sorted(K.option_actions(z, ControlState(z=z, m=m), s))
               if a != best]
    if not allowed:
        pytest.skip("no suboptimal admissible action at this probe")   # pragma: no cover
    trace = K.rollout(
        kappa=kappa, tape=K.SemanticTape(phase=phi, error_flag=0, cause_rank=0),
        command_provider=lambda st, c: SOL.best_action(st, c.z, c.m), base_option=z0,
        mask=FaultMask(decision=DecisionOverride(t=t, action=allowed[0])))
    return trace, learner_rows(trace, kappa, phi), kappa, phi


def credited(trace, rows, kappa, phi):
    steps = sorted({row[2] for row in rows})
    return resolve_credited_units(tuple(f"Decision_{t}" for t in steps),
                                  trace, kappa, phi)


# --------------------------------------------------------------------------- #
# 1. the information source
# --------------------------------------------------------------------------- #

_FORBIDDEN_INPUTS = ("trace", "mask", "sol", "solution", "reference", "world", "block",
                     "fire", "regime", "gamma")


def test_1_the_builder_signature_admits_only_rows():
    """The input type **is** the contract: a trace cannot reach it through the signature.

    The numbers would be identical if it read the trace; the same value reached by a
    different construction path is a different information contract, and "it happens to
    compute the same number" is not the claim being made.
    """
    import inspect
    for fn in (build_factual_envelope, validate_factual_envelope, factual_return_to_go):
        params = set(inspect.signature(fn).parameters)
        bad = sorted(p for p in params if any(f in p.lower() for f in _FORBIDDEN_INPUTS))
        assert not bad, f"{fn.__name__} admits {bad}"


def test_1b_no_evaluator_identifier_appears_in_the_factual_builder_code():
    """AST-based, so the docstrings that *forbid* these names do not trip it."""
    path = ROOT / "src" / "rfl_rebuild" / "b1" / "factual.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    seen: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            seen.add(node.id)
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr)
        elif isinstance(node, ast.arg):
            seen.add(node.arg)
        elif isinstance(node, ast.ImportFrom):
            seen.add(node.module or "")
            seen.update(a.name for a in node.names)
    banned = {"sol", "solve_reference", "FaultMask", "mask", "regime", "fire_code",
              "world_id", "block_id", "RolloutTrace", "trace"}
    assert not (seen & banned), f"the builder reaches for {sorted(seen & banned)}"


def test_2_the_delivered_cell_is_exactly_the_two_factual_fields():
    r"""A77 §65.2: $D_Q\times L_0$ delivers $\{a_t^F, G_t^F\}$ and nothing else.

    $a_t^+$ and $G_t^{CF}$ are not merely unread — they are not *constructible* here:
    `FactualTarget` has no field for them, so the widening this gate forbids cannot be
    introduced by accident.
    """
    assert DQ_SLICE.fields(Tier.L0_FACTUAL) == frozenset({"a_factual", "g_factual"})
    assert set(FactualTarget.__slots__) == {"address", "a_factual", "g_factual"}
    trace, rows, kappa, phi = healthy_scene()
    envelope = build_factual_envelope(rows, credited(trace, rows, kappa, phi))
    delivered = DQ_SLICE.deliver(Tier.L0_FACTUAL, credited(trace, rows, kappa, phi),
                                 envelope)
    for _addr, fields in delivered.items():
        assert set(fields) == {"a_factual", "g_factual"}


def test_2b_semantics_and_build_state_are_two_questions():
    r"""``cells`` answers what a cell *is*; ``implemented_tiers`` answers whether this
    revision may run it.

    Conflating them is how an implementation-stage fact becomes a semantic claim:
    ``fields(D_Q, L2)`` raising "not built" would mean the executable table had stopped
    answering A77's frozen field set, and enabling L2 later would have had to redefine
    ``fields()`` while implementing the counterfactual.
    """
    # --- semantics, A77 §65.2 verbatim ---------------------------------- #
    assert DQ_SLICE.fields(Tier.L0_FACTUAL) == frozenset({"a_factual", "g_factual"})
    assert DQ_SLICE.fields(Tier.L2_COUNTERFACTUAL) == frozenset(
        {"a_factual", "g_factual", "a_plus", "g_cf"})
    assert DQ_SLICE.fields(Tier.L3_ORACLE) == frozenset()
    with pytest.raises(ProtocolError) as ei:
        DQ_SLICE.fields(Tier.L1_CORRECTIVE)
    assert "no substantive treatment" in str(ei.value), "L1 is ill-typed, not unbuilt"

    # --- build state: L3 is the cell still to come ------------------------ #
    assert DQ_SLICE.implemented_tiers == frozenset({Tier.L0_FACTUAL,
                                                    Tier.L2_COUNTERFACTUAL,
                                                    Tier.L3_ORACLE})
    for tier in (Tier.L0_FACTUAL, Tier.L2_COUNTERFACTUAL, Tier.L3_ORACLE):
        DQ_SLICE.require_implemented(tier)                 # every built cell passes

    # --- consulted in that order, through the real entry point ----------- #
    def _stub(name, tier):
        class _Stub:
            pass
        _Stub.name = name
        _Stub.alias_of = None
        _Stub.tier = tier

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import AddressPlan, LawPlan
            return LawPlan(self.name, tuple(AddressPlan(a) for a in addresses))

        _Stub.plan = plan
        return _Stub()

    trace, rows, kappa, phi = healthy_scene()
    addrs = credited(trace, rows, kappa, phi)
    with pytest.raises(ProtocolError) as ei4:
        run_factual_return_law(_stub("L1Stub", Tier.L1_CORRECTIVE),
                               LearnerPersistentState(), addrs, rows, VIEW)
    assert "no substantive treatment" in str(ei4.value)


def test_2b2_an_implemented_cell_must_be_real_and_have_extractors():
    """The default ``implemented_tiers`` is the complete-build case, and it is safe
    rather than convenient: claiming a cell implemented without extractors fails here."""
    with pytest.raises(ProtocolError) as ei:
        SliceDescriptor(name="NoExtractors", store=Q, scalar=False,
                        domain=DQ_DOMAIN, view=lambda st: {},
                        cells={Tier.L0_FACTUAL: frozenset({"missing"}),
                               Tier.L1_CORRECTIVE: ILL_TYPED,
                               Tier.L2_COUNTERFACTUAL: ILL_TYPED,
                               Tier.L3_ORACLE: frozenset()},
                        extract={})
    assert "no extractor" in str(ei.value)
    with pytest.raises(ProtocolError) as ei2:
        SliceDescriptor(name="ImplementsIllTyped", store=Q, scalar=False,
                        domain=DQ_DOMAIN, view=lambda st: {},
                        cells={Tier.L0_FACTUAL: frozenset(),
                               Tier.L1_CORRECTIVE: ILL_TYPED,
                               Tier.L2_COUNTERFACTUAL: ILL_TYPED,
                               Tier.L3_ORACLE: frozenset()},
                        extract={},
                        implemented_tiers=frozenset({Tier.L1_CORRECTIVE}))
    assert "ill-typed" in str(ei2.value)


def test_2c_a_scalar_slice_cannot_be_run_through_the_patch_entry_point():
    """Each envelope is verified against its own evidence; the patch validator would
    check a factual envelope against the wrong schema."""
    trace, rows, kappa, phi = healthy_scene()
    addrs = credited(trace, rows, kappa, phi)
    envelope = build_factual_envelope(rows, addrs)
    with pytest.raises(ProtocolError) as ei:
        run_patch_law_with_envelope(FactualReturnWrite, LearnerPersistentState(), addrs,
                                    envelope, spec=DQ_SLICE)
    assert "own entry point" in str(ei.value)
    # And the *other* half: the scalar law on the patch slice, whose L0 cell delivers
    # nothing. That used to be a bare TypeError from inside the law.
    with pytest.raises(ProtocolError) as ei2:
        run_patch_law_with_envelope(FactualReturnWrite, LearnerPersistentState(), addrs,
                                    envelope)
    assert "does not deliver the fields" in str(ei2.value)


# --------------------------------------------------------------------------- #
# 2. the reverse fold
# --------------------------------------------------------------------------- #

def test_3_the_healthy_support_is_bit_exact_278_of_278():
    r"""The measurement the fold clause exists for, re-run through the real builder.

    $$\boxed{G_t^F \text{ bit-identical to } Q_D^\ast(x_t,a_t^F) \text{ on healthy
    trajectories}}$$

    ``sum`` and ``math.fsum`` disagree with the DP on 92 of these 278 addresses; this gate
    is why the fold is normative rather than a style preference.
    """
    n = exact = 0
    for kappa in (0, 1):
        for phi in K.PHASE_DOMAIN:
            for z0 in K.option_ids():
                trace, rows, kappa, phi = healthy_scene(kappa, phi, z0)
                addrs = credited(trace, rows, kappa, phi)
                envelope = build_factual_envelope(rows, addrs)
                for a in addrs:
                    rec = envelope[a]
                    ref = VIEW.value(QAddress(state=a.state, z=a.z, m=a.m,
                                              a=rec.a_factual))
                    assert rec.g_factual.hex() == float(ref).hex(), (
                        f"G_t^F is not bit-identical to Q_D* at {a!r}: "
                        f"{rec.g_factual.hex()} vs {float(ref).hex()}")
                    n += 1
                    exact += 1
    assert n == 278, f"the census must cover the healthy support, covered {n}"
    assert exact == n


def test_3b_a_reordered_fold_is_rejected_even_though_the_numbers_are_close():
    """The validator recomputes and compares **bit patterns**, not values.

    A left-to-right ``sum`` is "the same sum" in real arithmetic and differs in the last
    bits on a third of the support. A tolerance-based check would wave it through, and the
    write would then land next to the reference instead of on it.
    """
    trace, rows, kappa, phi = healthy_scene()
    addrs = credited(trace, rows, kappa, phi)
    good = build_factual_envelope(rows, addrs)
    victim = next(a for a in addrs
                  if math.fsum(row[9] for row in rows[a.state.t:])
                  != factual_return_to_go(rows, a.state.t))
    lie = dict(good)
    lie[victim] = FactualTarget(victim, good[victim].a_factual,
                                math.fsum(row[9] for row in rows[victim.state.t:]))
    with pytest.raises(ProtocolError) as ei:
        validate_factual_envelope(addrs, lie, rows)
    assert "reverse fold" in str(ei.value)


def test_3c_a_q_star_substituted_target_is_rejected():
    r""""It equals the reference here" is not the target: the target is the observation.

    On a *healthy* scene the two coincide at every address — that is gate 3 — so the
    substitution has to be tried where they differ, on a faulted scene. There, replacing
    the observed return with $Q_D^st$ is exactly the oracle leak the clause forbids.
    """
    trace, rows, kappa, phi = faulted_scene(t=1)
    addrs = credited(trace, rows, kappa, phi)
    good = build_factual_envelope(rows, addrs)
    victim = next((a for a in addrs
                   if VIEW.value(QAddress(state=a.state, z=a.z, m=a.m,
                                          a=good[a].a_factual)) != good[a].g_factual),
                  None)
    if victim is None:
        pytest.skip("this injection did not move any credited return")  # pragma: no cover
    lie = dict(good)
    lie[victim] = FactualTarget(
        victim, good[victim].a_factual,
        VIEW.value(QAddress(state=victim.state, z=victim.z, m=victim.m,
                            a=good[victim].a_factual)))
    with pytest.raises(ProtocolError):
        validate_factual_envelope(addrs, lie, rows)


def test_3d_an_envelope_missing_or_adding_a_context_is_rejected():
    trace, rows, kappa, phi = healthy_scene()
    addrs = credited(trace, rows, kappa, phi)
    if len(addrs) < 2:
        pytest.skip("this scene has one credited context")            # pragma: no cover
    good = dict(build_factual_envelope(rows, addrs))
    partial = dict(good)
    del partial[addrs[0]]
    with pytest.raises(ProtocolError):
        validate_factual_envelope(addrs, partial, rows)


# --------------------------------------------------------------------------- #
# 3. the healthy write canonicalises to a no-op
# --------------------------------------------------------------------------- #

def test_4_a_healthy_write_leaves_the_store_empty():
    r"""$G_t^F = Q_D^\ast$ on healthy support, so the write canonicalises to a deletion.

    This is the whole point of the fold clause: a target that merely rounds to the
    reference would persist a minimal override — clearing ``healthy`` and corrupting
    $N_{\\text{scalar}}$, $\Sigma$ and the fingerprint for every healthy scene.
    """
    trace, rows, kappa, phi = healthy_scene()
    addrs = credited(trace, rows, kappa, phi)
    state = LearnerPersistentState()
    res = run_factual_return_law(FactualReturnWrite, state, addrs, rows, VIEW)
    led = res.ledger
    assert led.scalar_metrics_applicable is True
    assert dict(state.q_overrides) == {}, "a healthy factual target is not an override"
    assert state.healthy
    assert led.n_scalar == 0
    assert led.sum_abs_delta == 0.0 and led.max_abs_delta == 0.0
    assert led.fingerprint_pre == led.fingerprint_post
    assert led.n_changed_addresses == 0
    assert set(r.status for r in led.receipts) == {EVALUABLE_NOOP}
    assert ledger_invariants_hold(led)


def ledger_invariants_hold(led) -> bool:
    led.check_fingerprint_invariants()          # raises on any violation
    return True


# --------------------------------------------------------------------------- #
# 4. the faulted write produces a real, non-oracle override
# --------------------------------------------------------------------------- #

def test_5_a_faulted_target_produces_exactly_one_non_oracle_override():
    r"""$$\boxed{\text{faulted } G_t^F \neq Q_D^\ast(x_t,a_t^F)
    \;\Longrightarrow\; \text{one override carrying } G_t^F}$$

    The update's content *is* the gap between the observed return and the reference. If the
    write were replaced by $Q_D^\ast$, the store would stay empty and the arm would look
    like a no-op that secretly knows the answer.
    """
    trace, rows, kappa, phi = faulted_scene(t=1)
    addrs = credited(trace, rows, kappa, phi)
    envelope = build_factual_envelope(rows, addrs)
    # the scene must actually be non-reference at some credited context
    gaps = [a for a in addrs
            if envelope[a].g_factual != VIEW.value(
                QAddress(state=a.state, z=a.z, m=a.m, a=envelope[a].a_factual))]
    if not gaps:
        pytest.skip("this injection did not move any credited return")  # pragma: no cover

    state = LearnerPersistentState()
    res = run_factual_return_law(FactualReturnWrite, state, addrs, rows, VIEW)
    led = res.ledger
    written = dict(state.q_overrides)
    expect = {QAddress(state=a.state, z=a.z, m=a.m, a=envelope[a].a_factual):
              envelope[a].g_factual for a in gaps}
    assert written == expect, "one entry per deviating context, carrying G_t^F exactly"
    for e, v in written.items():
        assert float(v).hex() == float(expect[e]).hex()
    assert led.n_changed_addresses == len(gaps)
    assert led.n_scalar == len(gaps)
    for r in led.receipts:
        expected = APPLIED if r.address in gaps else EVALUABLE_NOOP
        assert r.status == expected, f"{r.address!r} should be {expected}"
    assert led.fingerprint_pre != led.fingerprint_post
    assert ledger_invariants_hold(led)
    # and the override is NOT the reference value
    for e in written:
        assert written[e] != VIEW.value(e)


def test_5b_the_override_persists_and_changes_the_next_decision():
    """The point of writing it: the next episode's read path must see it."""
    trace, rows, kappa, phi = faulted_scene(t=1)
    addrs = credited(trace, rows, kappa, phi)
    envelope = build_factual_envelope(rows, addrs)
    victim = next((a for a in addrs
                   if envelope[a].g_factual != VIEW.value(
                       QAddress(state=a.state, z=a.z, m=a.m,
                                 a=envelope[a].a_factual))), None)
    if victim is None:
        pytest.skip("this injection did not move any credited return")  # pragma: no cover
    state = LearnerPersistentState()
    run_factual_return_law(FactualReturnWrite, state, addrs, rows, VIEW)
    snap = state.snapshot()
    assert snap.q_overrides, "the write must persist into the next episode"
    provider = snap.q_decision_provider(VIEW)
    before = SOL.best_action(victim.state, victim.z, victim.m)
    after = provider(victim.state, ControlState(z=victim.z, m=victim.m))
    # the factual action was penalised by its own observed return, so the policy moves
    # away from it wherever the observed return is the row's worst
    row = VIEW.row(victim.state, victim.z, victim.m)
    target = envelope[victim].a_factual
    if envelope[victim].g_factual < min(v for k, v in row.items() if k != target):
        assert after != target


# --------------------------------------------------------------------------- #
# 5. the scalar ledger (§65.10) is real, on both legs
# --------------------------------------------------------------------------- #

def test_6_a_created_entry_is_measured_against_the_reference_not_against_zero():
    """$\\Delta_{\\text{create}} = |q_{\\text{post}} - Q_D^\\ast(e)|$, not $|q_{\\text{post}}|$.

    Built with a handle-made target so the leg is isolated: a value *near* the reference
    must read as a *small* edit, and one far from it as a large one.
    """
    trace, rows, kappa, phi = healthy_scene()
    addrs = credited(trace, rows, kappa, phi)
    victim = addrs[0]
    ref = VIEW.value(QAddress(state=victim.state, z=victim.z, m=victim.m,
                              a=build_factual_envelope(rows, [victim])[victim].a_factual))
    a_f = build_factual_envelope(rows, [victim])[victim].a_factual
    entry = QAddress(state=victim.state, z=victim.z, m=victim.m, a=a_f)

    near = dict(build_factual_envelope(rows, addrs))
    near[victim] = FactualTarget(victim, a_f, ref + 1e-9)
    state = LearnerPersistentState()
    led = run_factual_return_law_offline(state, addrs, near, rows)
    assert led.n_scalar == 1
    honest = abs((ref + 1e-9) - ref)          # the float subtraction, not the decimal
    assert led.sum_abs_delta == honest, \
        f"a near-reference write must read as a small edit, got {led.sum_abs_delta!r}"
    # the point made concrete: against a zero baseline this same write would have been
    # reported as |q_post|, orders of magnitude larger than the edit it actually is
    assert led.sum_abs_delta < abs(ref) / 1e5, (led.sum_abs_delta, ref)
    assert state.q_overrides[entry] == ref + 1e-9


def run_factual_return_law_offline(state, addrs, envelope, rows):
    """Run the L0 law against a hand-made envelope, still through the real runner path."""
    from rfl_rebuild.b1.runner import _law_contract, _run
    law, tier = _law_contract(FactualReturnWrite, DQ_SLICE)
    return _run(law, tier, state, addrs, envelope, DQ_SLICE, VIEW).ledger


def test_6b_a_deleted_entry_is_measured_against_the_reference_too():
    trace, rows, kappa, phi = healthy_scene()
    addrs = credited(trace, rows, kappa, phi)
    victim = addrs[0]
    a_f = build_factual_envelope(rows, [victim])[victim].a_factual
    ref = VIEW.value(QAddress(state=victim.state, z=victim.z, m=victim.m, a=a_f))
    entry = QAddress(state=victim.state, z=victim.z, m=victim.m, a=a_f)

    state = LearnerPersistentState()
    state.apply_transaction([_q_edit(entry, ref + 0.5)], q_reference=VIEW)
    before = fingerprint(state)
    # FactualReturnWrite on the healthy target sets it back to the reference => deletion
    envelope = build_factual_envelope(rows, addrs)
    led = run_factual_return_law_offline(state, addrs, envelope, rows)
    assert dict(state.q_overrides) == {}
    assert led.n_scalar == 1
    assert abs(led.sum_abs_delta - 0.5) < 1e-12, led.sum_abs_delta
    assert led.fingerprint_pre == before and led.fingerprint_post != before
    assert ledger_invariants_hold(led)


def _q_edit(entry, value):
    from rfl_rebuild.learner.store import Q, Edit
    return Edit(Q, entry, value)


def test_7_the_reference_arm_is_constructed_through_the_same_cell():
    """`NoWriteRef(L0)` must receive the same fields as the treatment (A77 §65.2).

    Otherwise the reference's population is built from a different information envelope
    than the arm it is supposed to reference, and a constructor failure would take down
    the treatment but not its baseline.
    """
    seen = {}

    class _Spy(NoWriteRef):
        name = "SpyL0"
        tier = Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import LawPlan, AddressPlan
            seen["fields"] = None if targets is None else \
                {frozenset(v) for v in targets.values()}
            return LawPlan(self.name, tuple(AddressPlan(a) for a in addresses))

    trace, rows, kappa, phi = healthy_scene()
    addrs = credited(trace, rows, kappa, phi)
    run_factual_return_law(_Spy(), LearnerPersistentState(), addrs, rows, VIEW)
    assert seen["fields"] == {frozenset({"a_factual", "g_factual"})}


def test_7b_the_registries_are_separate_and_the_counts_do_not_move():
    names = [law.name for law in DQ_LAWS]
    assert names == ["NoWrite", "FactualReturnWrite", "NoWrite",
                     "CounterfactualReturnWrite", "DualReturnWrite", "NoWrite",
                     "LocalOracleRestore"], names
    # the two references share the display name `NoWrite`; A77 §65.3 puts the
    # distinction in the CELL, not in the name, and law_metadata's shape is frozen.
    kinds = [k for _n, k, _a in law_metadata(DQ_LAWS)]
    assert kinds == ["reference", "operation", "reference", "operation", "operation",
                     "reference", "operation"]
    tiers = [getattr(law, "tier") for law in DQ_LAWS]
    assert tiers == [Tier.L0_FACTUAL, Tier.L0_FACTUAL, Tier.L2_COUNTERFACTUAL,
                     Tier.L2_COUNTERFACTUAL, Tier.L2_COUNTERFACTUAL, Tier.L3_ORACLE,
                     Tier.L3_ORACLE]
    assert independent_treatment_count(DQ_LAWS) == 4      # 4, as A76 63.8 froze
    # the D_patch registry is untouched by the D_Q work
    assert independent_treatment_count() == 3


# --------------------------------------------------------------------------- #
# 6. the ledger is order-independent, and the reference boundary is arm-uniform
# --------------------------------------------------------------------------- #

def test_8_the_ledger_canonical_is_independent_of_address_order():
    r"""A76: no result may depend on iteration or hash order.

    The deltas are chosen to **expose non-associativity** rather than hoping a real scene
    does: $10^{16} + 1 + 1$ and $1 + 1 + 10^{16}$ are different bit patterns under
    sequential accumulation, and identical under an exactly-rounded one. This is the gate
    that failed before the accounting was made deterministic.
    """
    trace, rows, kappa, phi = healthy_scene()
    addrs = credited(trace, rows, kappa, phi)
    if len(addrs) < 3:
        pytest.skip("this scene has fewer than three credited contexts")  # pragma: no cover
    picks = addrs[:3]
    envelope = dict(build_factual_envelope(rows, addrs))
    for addr, delta in zip(picks, (1e16, 1.0, 1.0)):
        entry_a = envelope[addr].a_factual
        ref = VIEW.value(QAddress(state=addr.state, z=addr.z, m=addr.m, a=entry_a))
        envelope[addr] = FactualTarget(addr, entry_a, ref + delta)

    fwd = run_factual_return_law_offline(LearnerPersistentState(), picks, envelope, rows)
    rev = run_factual_return_law_offline(LearnerPersistentState(),
                                         tuple(reversed(picks)), envelope, rows)
    assert fwd.canonical() == rev.canonical(), \
        "the ledger bytes must not depend on the order the addresses were credited in"
    deltas = sorted(
        abs(float(envelope[a].g_factual)
            - VIEW.value(QAddress(state=a.state, z=a.z, m=a.m, a=envelope[a].a_factual)))
        for a in picks)
    assert fwd.sum_abs_delta == math.fsum(deltas), \
        "the sum must be the exactly-rounded one, not a sequential accumulation"
    assert fwd.n_scalar == 3 and fwd.n_changed_addresses == 3


class _FakeReference:
    """A mutable stand-in exposing the methods a duck-typed consumer would call."""

    def __init__(self, view):
        self._view = view

    def __contains__(self, address):
        return address in self._view

    def value(self, address):
        return self._view.value(address)

    def row(self, state, z, m):
        return self._view.row(state, z, m)


def test_9_the_reference_boundary_is_the_same_for_every_arm():
    """A fake reference must fail stop on the **reference** arm too.

    `FactualReturnWrite` writes, so the store's own boundary caught a fake; `NoWriteRef(L0)`
    writes nothing, skipped the transaction, and reached only the accounting — which
    checked ``is None``. The same fake therefore completed on the reference arm and
    fail-stopped on the treatment arm of the same cell, which contradicts "same cell, same
    construction". The check now runs once, ahead of both.
    """
    trace, rows, kappa, phi = healthy_scene()
    addrs = credited(trace, rows, kappa, phi)
    fake = _FakeReference(VIEW)
    messages = []
    for arm in (NoWriteRef(Tier.L0_FACTUAL), FactualReturnWrite):
        with pytest.raises(ProtocolError) as ei:
            run_factual_return_law(arm, LearnerPersistentState(), addrs, rows, fake)
        messages.append(str(ei.value))
    assert all("QReferenceView" in m for m in messages), messages
    assert messages[0] == messages[1], \
        "the reference and the treatment must be refused identically"
