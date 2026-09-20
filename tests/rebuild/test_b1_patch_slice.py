"""A76 §63.9-63.13 — the D_patch vertical slice.

Fourteen gates, including the three that guard against a *plausible* wrong
implementation rather than an obviously broken one: one transaction per scene, a
missing target record that must not masquerade as a verified absence, and a law that
must not be able to write outside its credited addresses.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.addressing import AddressDomain  # noqa: E402
from rfl_rebuild.b1 import (  # noqa: E402
    APPLIED, EVALUABLE_NOOP, ILL_TYPED, LAWS, NO_VALID_ALTERNATIVE, PATCH_SLICE,
    PROTOCOL_ERROR, AddressPlan, DeleteFactualPatch, LocalOracleRestore, NoWrite,
    NoWriteRef, ProtocolError, SetAlternative, SliceDescriptor, TargetRecord, Tier,
    fingerprint, independent_treatment_count, law_metadata,
    run_patch_law_with_envelope,
)
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import State  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    DECISION, PROCESS, DecisionAddress, Edit, LearnerPersistentState, StoreTransactionError,
)

UP, DOWN, LEFT, RIGHT, WAIT = K.UP, K.DOWN, K.LEFT, K.RIGHT, K.WAIT

A = DecisionAddress(state=State(x=1, y=2, t=1, kappa=0, phi=0), z=1, m=0)
B = DecisionAddress(state=State(x=2, y=2, t=2, kappa=0, phi=0), z=1, m=0)
C = DecisionAddress(state=State(x=3, y=2, t=3, kappa=0, phi=0), z=1, m=0)
ADDRESSES = (A, B, C)


def envelope(*, a_alt=UP, b_alt=None, c_alt=DOWN):
    """A TOTAL envelope: every credited address has a record."""
    return {A: TargetRecord(A, a_alt, RIGHT),
            B: TargetRecord(B, b_alt, RIGHT),
            C: TargetRecord(C, c_alt, RIGHT)}


def state_with(*pairs):
    """``state_with((A, DOWN), (C, UP))`` — addresses are not keyword names."""
    s = LearnerPersistentState()
    edits = [Edit(DECISION, a, v) for a, v in pairs]
    if edits:
        s.apply_transaction(edits)
    return s


def statuses(result):
    return {r.address: r.status for r in result.ledger.receipts}


# --------------------------------------------------------------------------- #
# 1. NoWrite
# --------------------------------------------------------------------------- #

def test_1_nowrite_plans_no_edit_and_every_address_is_evaluable_noop():
    s = state_with((A, DOWN))          # even with a patch present
    plan = NoWrite().plan(ADDRESSES, envelope())
    assert plan.edits == (), "NoWrite must create no edit at all"
    res = run_patch_law_with_envelope(NoWrite, s, ADDRESSES, envelope())
    assert set(statuses(res).values()) == {EVALUABLE_NOOP}
    assert res.ledger.n_changed_addresses == 0
    assert res.ledger.fingerprint_pre == res.ledger.fingerprint_post


# --------------------------------------------------------------------------- #
# 2. DeleteFactualPatch
# --------------------------------------------------------------------------- #

def test_2_delete_present_is_applied_absent_is_evaluable_noop():
    s = state_with((A, DOWN))          # a patch exists only at A
    res = run_patch_law_with_envelope(DeleteFactualPatch, s, ADDRESSES, envelope())
    st = statuses(res)
    assert st[A] == APPLIED, "deleting a present patch changes the store"
    assert st[B] == EVALUABLE_NOOP and st[C] == EVALUABLE_NOOP
    assert dict(res.post_state.decision_overrides) == {}


# --------------------------------------------------------------------------- #
# 3. SetAlternative
# --------------------------------------------------------------------------- #

def test_3_set_alternative_new_is_applied_already_equal_is_noop():
    s = state_with((A, UP))            # A already holds the target
    res = run_patch_law_with_envelope(SetAlternative, s, ADDRESSES, envelope())
    st = statuses(res)
    assert st[A] == EVALUABLE_NOOP, "writing the value it already holds is a no-op"
    assert st[C] == APPLIED
    assert dict(res.post_state.decision_overrides)[A] == UP
    assert dict(res.post_state.decision_overrides)[C] == DOWN

    s2 = LearnerPersistentState()
    res2 = run_patch_law_with_envelope(SetAlternative, s2, ADDRESSES, envelope())
    assert statuses(res2)[A] == APPLIED


def test_3b_a_change_of_value_is_applied():
    s = state_with((A, LEFT))
    res = run_patch_law_with_envelope(SetAlternative, s, ADDRESSES, envelope())
    assert statuses(res)[A] == APPLIED
    assert dict(res.post_state.decision_overrides)[A] == UP


# --------------------------------------------------------------------------- #
# 4. verified absence of an alternative
# --------------------------------------------------------------------------- #

def test_4_verified_absence_is_no_valid_alternative_and_deletes_nothing():
    s = state_with((B, LEFT))          # a patch sits at the very address
    res = run_patch_law_with_envelope(SetAlternative, s, ADDRESSES, envelope())
    st = statuses(res)
    assert st[B] == NO_VALID_ALTERNATIVE
    assert dict(res.post_state.decision_overrides)[B] == LEFT, \
        "an unavailable alternative must not delete the existing patch"
    assert B in st, "the address stays in the ledger and in the population"


# --------------------------------------------------------------------------- #
# 5. a MISSING target record is not a verified absence
# --------------------------------------------------------------------------- #

def test_5_missing_target_record_is_a_protocol_error():
    partial = envelope()
    del partial[B]
    with pytest.raises(ProtocolError) as ei:
        run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                    ADDRESSES, partial)
    assert PROTOCOL_ERROR in str(ei.value) or "missing record" in str(ei.value)


def test_5b_missing_record_is_distinguishable_from_a_verified_absence():
    """The two must not collapse: one is a fact, the other is a broken generator."""
    verified = envelope()                       # B has a record with alternative=None
    res = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                      ADDRESSES, verified)
    assert statuses(res)[B] == NO_VALID_ALTERNATIVE
    partial = envelope()
    del partial[B]
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                    ADDRESSES, partial)


# --------------------------------------------------------------------------- #
# 6. one unavailable address does not cancel the others
# --------------------------------------------------------------------------- #

def test_6_an_unavailable_address_does_not_cancel_the_others():
    s = LearnerPersistentState()
    res = run_patch_law_with_envelope(SetAlternative, s, ADDRESSES, envelope())
    st = statuses(res)
    assert st[B] == NO_VALID_ALTERNATIVE
    assert st[A] == APPLIED and st[C] == APPLIED, "A and C still commit"
    assert dict(res.post_state.decision_overrides) == {A: UP, C: DOWN}
    assert res.ledger.n_addressed == 3, "all three addresses remain addressed"


# --------------------------------------------------------------------------- #
# 7. exactly one transaction per scene
# --------------------------------------------------------------------------- #

def test_7_one_scene_commits_in_exactly_one_transaction(monkeypatch):
    calls = []
    original = LearnerPersistentState.apply_transaction

    def spy(self, edits, **kwargs):
        calls.append(tuple(edits))
        return original(self, edits, **kwargs)

    monkeypatch.setattr(LearnerPersistentState, "apply_transaction", spy)
    run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                ADDRESSES, envelope())
    assert len(calls) == 1, f"expected one transaction, got {len(calls)}"
    assert len(calls[0]) == 2, "only A and C form edits; B is skipped"


def test_7b_no_edits_means_no_transaction_at_all(monkeypatch):
    calls = []
    original = LearnerPersistentState.apply_transaction

    def spy(self, edits, **kwargs):
        calls.append(tuple(edits))
        return original(self, edits, **kwargs)

    monkeypatch.setattr(LearnerPersistentState, "apply_transaction", spy)
    run_patch_law_with_envelope(NoWrite, LearnerPersistentState(), ADDRESSES,
                                envelope())
    assert calls == [], "NoWrite must not open a transaction"


# --------------------------------------------------------------------------- #
# 8. locality: a law may not write outside its credited addresses
# --------------------------------------------------------------------------- #

class _OutOfLocalityLaw:
    name = "MaliciousOutOfLocality"
    alias_of = None
    tier = Tier.L0_FACTUAL

    def plan(self, addresses, targets):
        from rfl_rebuild.b1.laws import AddressPlan, LawPlan
        rogue = DecisionAddress(state=State(x=0, y=2, t=0, kappa=0, phi=0), z=0, m=0)
        return LawPlan(self.name, (AddressPlan(rogue, (Edit(DECISION, rogue, UP),)),))


def test_8_a_law_writing_outside_its_credited_addresses_fails_stop():
    s = LearnerPersistentState()
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_OutOfLocalityLaw(), s, ADDRESSES, envelope())
    assert s.healthy, "the rogue write must not have landed"


class _LaunderingLaw:
    """Names a **credited** address in the plan but edits a rogue one.

    The earlier runner checked ``w.address in credited`` and ``w.edit.store ==
    DECISION`` but never ``w.edit.address == w.address``, so this passed the locality
    gate and actually wrote ``ROGUE`` — an address that was never credited.
    """

    name = "MaliciousLaundering"
    alias_of = None
    tier = Tier.L0_FACTUAL

    def __init__(self, rogue):
        self._rogue = rogue

    def plan(self, addresses, targets):
        from rfl_rebuild.b1.laws import AddressPlan, LawPlan
        return LawPlan(self.name, tuple(
            AddressPlan(a, (Edit(DECISION, self._rogue, UP),)) for a in addresses))


def test_8b_laundering_a_credited_address_into_a_rogue_edit_fails_stop():
    rogue = DecisionAddress(state=State(x=0, y=2, t=0, kappa=0, phi=0), z=0, m=0)
    s = LearnerPersistentState()
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_LaunderingLaw(rogue), s, ADDRESSES, envelope())
    assert s.healthy, "the laundered write must not have landed"


def test_8c_a_plan_that_omits_a_credited_address_fails_stop():
    class _OmitOne:
        name, alias_of, tier = "MaliciousOmit", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import AddressPlan, LawPlan
            return LawPlan(self.name,
                           tuple(AddressPlan(a) for a in addresses[:-1]))

    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_OmitOne(), LearnerPersistentState(),
                                    ADDRESSES, envelope())


def test_8d_a_plan_that_double_names_an_address_fails_stop():
    class _Double:
        name, alias_of, tier = "MaliciousDouble", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import AddressPlan, LawPlan
            return LawPlan(self.name,
                           tuple(AddressPlan(a) for a in addresses)
                           + (AddressPlan(addresses[0]),))

    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_Double(), LearnerPersistentState(),
                                    ADDRESSES, envelope())


def test_8e_an_illegal_plan_shape_fails_stop():
    class _BadShape:
        name, alias_of, tier = "MaliciousShape", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import AddressPlan, LawPlan
            # edit AND status together: not one of the three legal shapes
            return LawPlan(self.name, tuple(
                AddressPlan(a, (Edit(DECISION, a, None),), APPLIED)
                for a in addresses))

    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_BadShape(), LearnerPersistentState(),
                                    ADDRESSES, envelope())


def test_8f_declaring_applied_without_an_edit_fails_stop():
    class _StatusNoEdit:
        name, alias_of, tier = "MaliciousStatus", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import AddressPlan, LawPlan
            return LawPlan(self.name, tuple(
                AddressPlan(a, (), APPLIED) for a in addresses))

    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_StatusNoEdit(), LearnerPersistentState(),
                                    ADDRESSES, envelope())


def test_8g_a_law_that_does_not_declare_its_tier_fails_stop():
    class _NoTier:
        name, alias_of = "Undeclared", None

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import AddressPlan, LawPlan
            return LawPlan(self.name,
                           tuple(AddressPlan(a) for a in addresses))

    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_NoTier(), LearnerPersistentState(),
                                    ADDRESSES, envelope())


def test_8h_a_real_subclass_that_forgets_its_tier_fails_stop():
    """The canary 8g was *not*.

    ``_NoTier`` does not inherit ``_Law``, so it tripped the ``hasattr`` branch while
    the case that actually matters — a genuine ``_Law`` subclass that forgets to
    declare its tier and silently inherits the base value — was never exercised. With
    the old base value ``False`` this law ran happily as an $L_0$ arm.
    """
    from rfl_rebuild.b1.laws import _Law

    class _ForgotTier(_Law):
        name = "ForgotTier"

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import AddressPlan, LawPlan
            return LawPlan(self.name,
                           tuple(AddressPlan(a) for a in addresses))

    assert _Law.tier is None, \
        "the base tier must be the NOT-DECLARED sentinel, not False"
    assert "tier" not in _ForgotTier.__dict__, \
        "this canary is only meaningful while the subclass really does not declare it"
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_ForgotTier(), LearnerPersistentState(),
                                    ADDRESSES, envelope())


@pytest.mark.parametrize("bad_tier", [None, 0, 1, "yes", "False", []])
def test_8i_a_tier_that_is_not_a_real_bool_fails_stop(bad_tier):
    """``bool("no") is True`` and ``bool(None) is False``: coercion is not a tier.

    The assertion is on **which** rejection fires, not merely that one did, and that is
    load-bearing rather than fussy. The cell table is keyed by :class:`Tier` members, so
    a non-member is refused by the lookup as well — if this test only asserted
    ``ProtocolError`` it would still pass with the type test deleted, and the mutation
    would report ``NOT_A_GATE``. Two distinct failures are being separated: "this is not
    a tier at all" (here) and "this architecture has no cell for this tier" (8m).
    Additionally, ``[]`` shows why the type test is not merely cosmetic: without it the
    lookup would raise ``TypeError: unhashable type`` out of ``dict.get`` instead of the
    ``PROTOCOL_ERROR`` the contract promises.
    """
    class _BadTier:
        name, alias_of = "BadTier", None

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import AddressPlan, LawPlan
            return LawPlan(self.name,
                           tuple(AddressPlan(a) for a in addresses))

    _BadTier.tier = bad_tier
    with pytest.raises(ProtocolError) as ei:
        run_patch_law_with_envelope(_BadTier(), LearnerPersistentState(),
                                    ADDRESSES, envelope())
    assert "not a Tier member" in str(ei.value), \
        f"the wrong rejection fired for tier={bad_tier!r}: {ei.value}"


def test_8j_a_law_cannot_re_acquire_a_store_handle():
    """Deleting the ``snapshot`` argument closes nothing unless it cannot come back.

    A law that declares a valid tier but declares ``plan(self, addresses, targets,
    snapshot)`` would otherwise be called with two arguments and raise a bare
    ``TypeError`` — a crash on the error path, and a silent invitation to re-add the
    full learner snapshot (all three stores) to the law API.

    The assertion is on **which** rejection fires, and that became load-bearing when the
    runner started wrapping the ``plan`` call: an unexpected ``TypeError`` from inside a
    law is now converted into a ``PROTOCOL_ERROR`` too, so the two failures are
    distinguishable only by their messages — "the law API is exactly …" (the declared
    signature contract) versus "failed while planning …" (a law/slice mismatch). With
    both collapsing into "it raised ProtocolError", deleting the signature check would
    leave this gate green and the mutation would report ``NOT_A_GATE``.
    """
    class _ReacquiresSnapshot:
        name, alias_of, tier = "Sneaky", None, Tier.L1_CORRECTIVE

        def plan(self, addresses, targets, snapshot):
            from rfl_rebuild.b1.laws import LawPlan
            return LawPlan(self.name, tuple())

    with pytest.raises(ProtocolError) as ei:
        run_patch_law_with_envelope(_ReacquiresSnapshot(), LearnerPersistentState(),
                                    ADDRESSES, envelope())
    assert "the law API is exactly" in str(ei.value), \
        f"the wrong rejection fired: {ei.value}"


def test_8k_the_registered_law_api_is_exactly_addresses_and_targets():
    """The whole law API, checked rather than documented.

    Bound to an instance, because that is the callable the runner inspects:
    ``inspect.signature`` drops ``self`` there, so the check is on the argument list a
    law actually receives.
    """
    import inspect
    for law_cls in LAWS:
        law = law_cls()
        params = tuple(inspect.signature(law.plan).parameters)
        assert params == ("addresses", "targets"), f"{law.name}.plan takes {params}"


def test_8l_the_snapshot_is_not_even_constructed_for_a_law_run(monkeypatch):
    """A law run must not build a learner snapshot it does not hand to anyone.

    Weaker than the signature check and kept as a second, independent witness: with the
    argument deleted but the snapshot still taken, the leak would be one call away.
    """
    calls = []
    original = LearnerPersistentState.snapshot

    def spy(self):
        calls.append(1)
        return original(self)

    monkeypatch.setattr(LearnerPersistentState, "snapshot", spy)
    run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                ADDRESSES, envelope())
    assert calls == [], "the runner built a learner snapshot during a law run"


# --------------------------------------------------------------------------- #
# 8m-8q. the generic slice structures A77 froze (the refactor's own claims)
# --------------------------------------------------------------------------- #

class _CellSpy:
    """Records exactly what the runner delivered, and returns an all-no-op plan."""

    name = "CellSpy"
    alias_of = None
    tier = Tier.L1_CORRECTIVE
    seen: dict = {}

    def plan(self, addresses, targets):
        from rfl_rebuild.b1.laws import LawPlan
        _CellSpy.seen["targets"] = targets
        return LawPlan(self.name, tuple(AddressPlan(a) for a in addresses))


def test_8m_a_law_declared_in_an_ill_typed_cell_is_rejected():
    """A77 §65.2's table becomes executable.

    $L_2$ is ill-typed on a value-free store because every value target is ill-typed
    there (A76 §63.6). If that cell were declared as an empty field set instead, an
    $L_2$ law would be accepted as though it were $L_0$ — silently, and with the wrong
    information contract.
    """
    class _DeclaresL2:
        name, alias_of, tier = "WrongCell", None, Tier.L2_COUNTERFACTUAL

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import LawPlan
            return LawPlan(self.name, tuple(AddressPlan(a) for a in addresses))

    assert PATCH_SLICE.cells[Tier.L2_COUNTERFACTUAL] is ILL_TYPED, \
        "this gate is about the ill-typed cell; the table must still say so"
    with pytest.raises(ProtocolError) as ei:
        run_patch_law_with_envelope(_DeclaresL2(), LearnerPersistentState(),
                                    ADDRESSES, envelope())
    assert "ill-typed" in str(ei.value)


def test_8n_the_delivered_object_is_exactly_the_cells_field_set():
    """The inner half of A77 §65.2's exactness, and it is **not** vacuous.

    ``fields(D_patch, L1) = {alternative}``. The evaluator-side record also carries
    ``factual_command``, which exists for validation and is not delivered content, so a
    law that received the record would see a field its cell excludes.
    """
    _CellSpy.seen = {}
    run_patch_law_with_envelope(_CellSpy(), LearnerPersistentState(), ADDRESSES,
                                envelope())
    delivered = _CellSpy.seen["targets"]
    assert delivered is not None
    assert set(delivered) == set(ADDRESSES), "the outer domain is the credited set"
    for a in ADDRESSES:
        assert set(delivered[a]) == {"alternative"}, \
            f"{a!r} was delivered {sorted(delivered[a])}"
        assert "factual_command" not in delivered[a], \
            "the validator's field leaked into the law's delivery"
    assert delivered[A]["alternative"] == UP


def test_8n2_an_empty_cell_delivers_no_object_at_all():
    """Not an empty container: ``None``. A law with no fields is handed nothing."""
    _CellSpy.seen = {}
    _CellSpy.tier = Tier.L0_FACTUAL
    try:
        run_patch_law_with_envelope(_CellSpy(), LearnerPersistentState(), ADDRESSES,
                                    envelope())
    finally:
        _CellSpy.tier = Tier.L1_CORRECTIVE
    assert _CellSpy.seen["targets"] is None


def test_8o_owner_locality_degenerates_to_identity_on_this_architecture():
    """The generic rule must reduce to the old one, not replace it (A77 §65.9).

    ``owner_patch = id``, so "credited = plan = edit" is the special case. If the
    refactor had instead dropped the old check without this degeneration, the laundering
    gate would keep passing for the wrong reason.
    """
    for a in ADDRESSES + (State(x=0, y=2, t=0, kappa=0, phi=0),):
        addr = a if isinstance(a, DecisionAddress) else DecisionAddress(a, 0, 0)
        assert PATCH_SLICE.owner(addr) == addr, "owner_patch must be the identity"
    assert PATCH_SLICE.scalar is False
    assert PATCH_SLICE.store == DECISION


def test_8p_two_entry_edits_in_one_address_plan_are_rejected():
    """New machinery, new failure mode: last-write-wins inside one plan.

    On $D_{patch}$ this is also what bounds an address-plan at one entry, which is how
    the generic structure reproduces the old "one write per credited address" rule
    without a special case.
    """
    class _TwoEntries:
        name, alias_of, tier = "TwoEntries", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import LawPlan
            return LawPlan(self.name, tuple(
                AddressPlan(a, (Edit(DECISION, a, UP), Edit(DECISION, a, DOWN)))
                for a in addresses))

    s = LearnerPersistentState()
    with pytest.raises(ProtocolError) as ei:
        run_patch_law_with_envelope(_TwoEntries(), s, ADDRESSES, envelope())
    assert "same entry twice" in str(ei.value)
    assert s.healthy, "the rejected plan must not have touched the store"


def test_8q_the_frozen_cell_table_is_what_is_declared():
    """A77 §65.2's $D_{patch}$ row, pinned as data.

    $L_0$ and $L_3$ declare nothing, $L_1$ declares exactly the alternative, $L_2$ is
    ill-typed. A future edit that widens a cell — for instance by giving $L_0$ a field
    "because it is convenient" — has to change this test, which is the point.
    """
    assert PATCH_SLICE.fields(Tier.L0_FACTUAL) == frozenset()
    assert PATCH_SLICE.fields(Tier.L1_CORRECTIVE) == frozenset({"alternative"})
    assert PATCH_SLICE.fields(Tier.L3_ORACLE) == frozenset()
    with pytest.raises(ProtocolError):
        PATCH_SLICE.fields(Tier.L2_COUNTERFACTUAL)
    assert set(PATCH_SLICE.cells) == set(Tier), \
        "every tier must be declared, ill-typed cells included"


_Z0, _Z1 = K.option_ids()[0], K.option_ids()[1]


def _test_domain(tag, owner, store_type=DecisionAddress):
    """A test-local address domain: strict about its own type, like a real architecture.

    These slices are deliberately not $D_Q$ or $D_{patch}$ -- they exist to reach plan shapes
    the real architectures cannot -- so they bring their own domain rather than borrowing one
    (A80 68.2: the shared layer carries an architecture's domain, it does not supply one).
    """
    def require_credited(value):
        if type(value) is not DecisionAddress:
            raise ProtocolError(
                f"the {tag} domain credits DecisionAddress, got {type(value).__name__}")

    def require_store(value):
        if type(value) is not store_type:
            raise ProtocolError(
                f"the {tag} store is keyed by {store_type.__name__}, got "
                f"{type(value).__name__}")

    def canonical(value):
        s = value.state
        return f"{s.x},{s.y},{s.t},{s.kappa},{s.phi},{value.z},{value.m}"

    return AddressDomain(tag=tag, require_credited=require_credited,
                         require_store=require_store, owner=owner, canonical=canonical)


def _two_entry_slice():
    """A slice whose owner map collapses two PROCESS entries onto one context.

    Deliberately not $D_Q$: the point is the **generic** rule, and a descriptor is the
    only way to reach $k>1$ without inventing a science object. ``extract`` is empty
    because every cell declares no field.
    """
    return SliceDescriptor(
        name="TestTwoEntry",
        store=PROCESS,
        scalar=False,
        domain=_test_domain("TestTwoEntry", lambda address: A, store_type=int),
        view=lambda state: dict(state.process_overrides),
        cells={t: (ILL_TYPED if t is Tier.L2_COUNTERFACTUAL else frozenset())
               for t in Tier},
        extract={},
    )


class _TwoEntryLaw:
    """One address-plan, two entries: the first writes the identity, the second changes.

    This is the shape the generic contract claims to support and the receipt rule has to
    honour. With a first-entry-only rule the receipt says "unchanged" while the
    fingerprint moves, and the ledger invariant kills the run instead of reporting
    ``APPLIED`` — the old behaviour, pinned by this gate.
    """

    name = "TwoEntry"
    alias_of = None
    tier = Tier.L0_FACTUAL

    def plan(self, addresses, targets):
        from rfl_rebuild.b1.laws import LawPlan
        return LawPlan(self.name, tuple(
            AddressPlan(a, (Edit(PROCESS, _Z0, _Z0), Edit(PROCESS, _Z1, _Z0)))
            for a in addresses))


def test_8s_a_multi_entry_address_plan_reports_applied_from_any_entry():
    """$k>1$ must be real, not a renamed $k\\le1$ (A77 §65.9).

    Entry 1 writes the identity, which canonicalises to a deletion and changes nothing;
    entry 2 creates an override. One credited context, therefore **one** receipt, and it
    must be ``APPLIED`` with ``store_changed=True`` because *some* entry changed.
    """
    s = LearnerPersistentState()
    res = run_patch_law_with_envelope(_TwoEntryLaw(), s, (A,), envelope(),
                                      spec=_two_entry_slice())
    assert res.ledger.n_addressed == 1, "two entries is still one addressed context"
    r = res.ledger.receipts[0]
    assert r.address == A
    assert r.store_changed is True, "entry 2 changed the store"
    assert r.status == APPLIED, \
        "a changed entry must make the receipt APPLIED, not EVALUABLE_NOOP"
    assert res.ledger.n_changed_addresses == 1
    assert res.ledger.fingerprint_pre != res.ledger.fingerprint_post
    assert dict(s.process_overrides) == {_Z1: _Z0}, \
        "only the second entry should have landed"


def test_8s2_a_multi_entry_plan_that_changes_nothing_is_still_a_noop():
    """The other side of the same rule: ``any`` over an all-no-op plan is false."""
    class _BothIdentity(_TwoEntryLaw):
        name = "TwoEntryNoop"

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import LawPlan
            return LawPlan(self.name, tuple(
                AddressPlan(a, (Edit(PROCESS, _Z0, _Z0), Edit(PROCESS, _Z1, _Z1)))
                for a in addresses))

    s = LearnerPersistentState()
    res = run_patch_law_with_envelope(_BothIdentity(), s, (A,), envelope(),
                                      spec=_two_entry_slice())
    r = res.ledger.receipts[0]
    assert r.store_changed is False and r.status == EVALUABLE_NOOP
    assert res.ledger.fingerprint_pre == res.ledger.fingerprint_post


def test_8t_a_descriptor_missing_an_extractor_fails_at_construction():
    """The contract boundary, not the read path.

    With ``cells[L1] = {"alternative"}`` and no extractor, ``deliver`` used to raise a
    bare ``KeyError: alternative`` from inside the projection. A descriptor is built once
    and used for every scene, so the failure belongs where it is constructed.
    """
    with pytest.raises(ProtocolError) as ei:
        SliceDescriptor(
            name="Broken", store=DECISION, scalar=False,
            domain=_test_domain("TestIdentity", lambda address: address),
            view=lambda state: dict(state.decision_overrides),
            cells={t: (frozenset({"alternative"}) if t is Tier.L1_CORRECTIVE
                       else (ILL_TYPED if t is Tier.L2_COUNTERFACTUAL
                             else frozenset()))
                   for t in Tier},
            extract={})
    assert "extractor" in str(ei.value)


def test_8t2_a_descriptor_must_declare_every_tier():
    """An undeclared cell would be discovered only when a law first ran in it."""
    with pytest.raises(ProtocolError) as ei:
        SliceDescriptor(
            name="Partial", store=DECISION, scalar=False,
            domain=_test_domain("TestIdentity", lambda address: address),
            view=lambda state: dict(state.decision_overrides),
            cells={Tier.L0_FACTUAL: frozenset()},
            extract={})
    assert "every tier" in str(ei.value)


def test_8t3_a_non_bool_scalar_flag_is_rejected():
    with pytest.raises(ProtocolError) as ei:
        SliceDescriptor(
            name="Coerced", store=DECISION, scalar=0, domain=_test_domain("Coerced", lambda a: a),
            view=lambda state: dict(state.decision_overrides),
            cells={t: (ILL_TYPED if t is Tier.L2_COUNTERFACTUAL else frozenset())
                   for t in Tier},
            extract={})
    assert "not a bool" in str(ei.value)


def test_8u_the_cell_table_and_extractors_are_read_only():
    """``frozen=True`` freezes the binding, not the dicts behind it.

    Editing the cells in place would edit the frozen information contract at runtime,
    which is exactly what making the table executable was meant to prevent.
    """
    with pytest.raises(TypeError):
        PATCH_SLICE.cells[Tier.L0_FACTUAL] = frozenset({"rogue"})
    with pytest.raises(TypeError):
        PATCH_SLICE.extract["rogue"] = lambda record: None
    assert PATCH_SLICE.fields(Tier.L0_FACTUAL) == frozenset(), \
        "the mutation attempt must not have landed"


def test_8v_tier_has_no_truth_value():
    """A77 §65.1's "no truthiness inference", mechanically.

    ``type(tier) is Tier`` stops another value posing as a tier, but every enum member is
    truthy by default, so ``if tier:`` would silently collapse all four. Raising turns a
    silent wrong branch into a fail-stop.
    """
    for tier in Tier:
        with pytest.raises(ProtocolError):
            bool(tier)
    with pytest.raises(ProtocolError):
        if Tier.L0_FACTUAL:                          # pragma: no cover
            pass
    assert (Tier.L0_FACTUAL is Tier.L0_FACTUAL) is True, "identity still works"
    assert Tier.L0_FACTUAL != Tier.L1_CORRECTIVE, "comparison still works"


def test_8r_the_reference_mechanism_shares_one_plan_and_is_not_a_treatment():
    """A77 §65.3: references are objects in a cell, and never counted as treatments."""
    l0, l3 = NoWriteRef(Tier.L0_FACTUAL), NoWriteRef(Tier.L3_ORACLE)
    assert l0.plan.__func__ is l3.plan.__func__, \
        "instances must share one no-op plan function object"
    assert l0.tier is Tier.L0_FACTUAL and l3.tier is Tier.L3_ORACLE
    assert NoWrite().tier is Tier.L0_FACTUAL, \
        "the registered reference keeps the tier its class declares"
    assert NoWriteRef().tier is None, \
        "an instance with no declared tier keeps the NOT-DECLARED sentinel"
    assert independent_treatment_count() == 3, \
        "instantiating references must not move the frozen count"
    assert law_metadata()[0] == ("NoWrite", "reference", None)


# --------------------------------------------------------------------------- #
# 9. a failed transaction invalidates the whole run
# --------------------------------------------------------------------------- #

def test_9_a_substrate_rejection_is_a_fail_stop_with_identical_state():
    """A legitimate law over a credited address the substrate refuses.

    The plan is well-formed — ``DeleteFactualPatch`` names every credited address
    exactly once — so the failure comes from the substrate, which is the path this
    gate is about. The earlier version used a law that planned one address twice,
    which the tightened plan-totality check now catches *earlier*; that case is gate
    8d and this is a genuinely different failure.
    """
    malformed = DecisionAddress(state="oops", z=1, m=0)
    credited = (A, malformed)
    s = state_with((A, DOWN), (C, LEFT))
    fp_before = fingerprint(s)
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(DeleteFactualPatch, s, credited, envelope())
    assert fingerprint(s) == fp_before, "a rejected transaction leaves the store identical"
    assert dict(s.decision_overrides) == {A: DOWN, C: LEFT}, \
        "the good address's delete must not land either"


def test_9b_a_law_that_plans_the_same_address_twice_fails_stop():
    class _DoubleEdit:
        name, alias_of, tier = "MaliciousDuplicate", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import AddressPlan, LawPlan
            return LawPlan(self.name,
                           (AddressPlan(A, (Edit(DECISION, A, UP),)),
                            AddressPlan(A, (Edit(DECISION, A, DOWN),))))

    s = LearnerPersistentState()
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_DoubleEdit(), s, (A,), envelope())
    assert s.healthy


def test_9c_protocol_error_is_a_separate_hierarchy():
    from rfl_rebuild.method.credit import ProtocolError as CreditProtocolError
    from rfl_rebuild.learner.store import StoreTransactionError
    assert not issubclass(ProtocolError, CreditProtocolError)
    assert not issubclass(ProtocolError, StoreTransactionError)


# --------------------------------------------------------------------------- #
# 10-11. the L3 alias
# --------------------------------------------------------------------------- #

def test_10_alias_is_indistinguishable_from_its_target():
    s1 = state_with((A, DOWN), (C, UP))
    s2 = state_with((A, DOWN), (C, UP))
    r_plain = run_patch_law_with_envelope(DeleteFactualPatch, s1, ADDRESSES,
                                          envelope())
    r_alias = run_patch_law_with_envelope(LocalOracleRestore, s2, ADDRESSES,
                                          envelope())
    assert dict(r_plain.post_state.decision_overrides) == \
        dict(r_alias.post_state.decision_overrides)
    assert [r.canon() for r in r_plain.ledger.receipts] == \
        [r.canon() for r in r_alias.ledger.receipts]
    assert r_plain.ledger.canonical().replace('"', "") != ""      # sanity
    assert (r_plain.ledger.n_scalar, r_plain.ledger.sum_abs_delta,
            r_plain.ledger.max_abs_delta) == \
        (r_alias.ledger.n_scalar, r_alias.ledger.sum_abs_delta,
         r_alias.ledger.max_abs_delta)
    assert r_plain.ledger.fingerprint_pre == r_alias.ledger.fingerprint_pre
    assert r_plain.ledger.fingerprint_post == r_alias.ledger.fingerprint_post


def test_10b_the_alias_shares_the_implementation():
    assert issubclass(LocalOracleRestore, DeleteFactualPatch)
    assert LocalOracleRestore.plan is DeleteFactualPatch.plan, \
        "the alias must not be a second implementation"
    assert DeleteFactualPatch.name == "DeleteFactualPatch", \
        "registering the alias must not mutate the target"


def test_11_alias_is_not_an_independent_treatment():
    md = dict((n, (kind, target)) for n, kind, target in law_metadata())
    assert md["LocalOracleRestore"] == ("alias", "DeleteFactualPatch")
    assert md["NoWrite"][0] == "reference"
    assert md["DeleteFactualPatch"][0] == "operation"
    assert md["SetAlternative"][0] == "operation"
    assert independent_treatment_count() == 3, "3 independent treatments, not 4"
    assert len(LAWS) == 4, "four registered arms"


# --------------------------------------------------------------------------- #
# 12. the write is actually persistent
# --------------------------------------------------------------------------- #

def test_12_the_next_episode_reads_the_persistent_effect():
    s = LearnerPersistentState()
    run_patch_law_with_envelope(SetAlternative, s, ADDRESSES, envelope())
    # a NEW snapshot, as the next episode would take
    snap = s.snapshot()
    assert snap.decision_overrides[A] == UP
    adapter = snap.decision_provider(lambda st, c: WAIT)
    assert adapter(A.state, K.ControlState(z=A.z, m=A.m)) == UP, \
        "the patch must win over the base provider in the next episode"


def test_12b_a_rolled_back_run_leaves_no_persistent_effect():
    class _DoubleEdit:
        name, alias_of, tier = "MaliciousDuplicate", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import AddressPlan, LawPlan
            return LawPlan(self.name,
                           (AddressPlan(A, (Edit(DECISION, A, UP),)),
                            AddressPlan(A, (Edit(DECISION, A, DOWN),))))

    s = LearnerPersistentState()
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(_DoubleEdit(), s, (A,), envelope())
    assert s.snapshot().decision_provider(lambda st, c: WAIT)(
        A.state, K.ControlState(z=A.z, m=A.m)) == WAIT


# --------------------------------------------------------------------------- #
# 13. the law layer has no independent handle on regime, truth or identity
# --------------------------------------------------------------------------- #
#
# SCOPE OF THIS CLAIM, stated precisely. What is checked is that a law has no
# independent ``regime`` / ``fire_code`` / ``Gamma*`` / ``world_id`` / ``block_id`` /
# ``phase`` / ``kappa`` parameter or attribute, and that those identifiers do not
# appear in the law CODE.
#
# It does NOT follow that a law is semantically blind to kappa and phi: it receives
# ``DecisionAddress(state, z, m)`` and ``state`` carries ``kappa`` and ``phi``, so
# ``address.state.kappa`` is readable. That is not an A76 violation -- rho_D is
# *defined* to include the full s_t -- but this gate must not be reported as proving
# more than it does. An earlier revision listed phase/kappa here without that caveat.

_FORBIDDEN = ("regime", "fire_code", "Gamma", "world_id", "block_id", "S_T",
              "S_P", "phase", "kappa")


@pytest.mark.parametrize("law", LAWS)
def test_13_law_plan_signature_has_no_forbidden_parameters(law):
    import inspect
    params = set(inspect.signature(law.plan).parameters)
    assert not (params & set(_FORBIDDEN)), f"{law.name}.plan exposes {params}"


@pytest.mark.parametrize("law", LAWS)
def test_13b_law_objects_carry_no_forbidden_attributes(law):
    for name in _FORBIDDEN:
        assert not hasattr(law, name), f"{law.name} carries {name}"


def test_13c_no_forbidden_identifier_appears_in_the_law_CODE():
    """AST-based, so the docstrings that *forbid* these names do not trip it."""
    path = ROOT / "src" / "rfl_rebuild" / "b1" / "laws.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            seen.add(node.id)
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr)
        elif isinstance(node, ast.arg):
            seen.add(node.arg)
    bad = sorted(n for n in seen if n in _FORBIDDEN)
    assert not bad, f"forbidden identifiers in law code: {bad}"


def test_13d_the_gate_is_about_handles_not_semantic_blindness():
    """Recorded so the gate is not read as proving more than it checks.

    A law *can* read ``address.state.kappa``; rho_D is defined to include the full
    ``s_t``, so this is expected rather than a leak. What must not exist is an
    independent channel carrying regime, truth or scenario identity.
    """
    assert A.state.kappa == 0 and hasattr(A.state, "phi")
    with pytest.raises(ProtocolError):
        # and there is no way to hand a law such a channel: the tier check is the
        # only thing the runner consults besides the addresses and the envelope
        import rfl_rebuild.b1.runner as runner
        runner._tier(type("NoTier", (), {"name": "x"})())


# --------------------------------------------------------------------------- #
# 14. order independence, including the ledger bytes
# --------------------------------------------------------------------------- #

def test_14_input_order_does_not_change_state_or_ledger_bytes():
    fwd = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                      ADDRESSES, envelope())
    rev = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                      tuple(reversed(ADDRESSES)), envelope())
    assert dict(fwd.post_state.decision_overrides) == \
        dict(rev.post_state.decision_overrides)
    assert fwd.ledger.fingerprint_post == rev.ledger.fingerprint_post
    assert fwd.ledger.canonical() == rev.ledger.canonical(), \
        "the ledger serialization must be order-independent"


def test_14b_a_shuffled_target_mapping_is_irrelevant():
    base = envelope()
    shuffled = dict(reversed(list(base.items())))
    r1 = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                     ADDRESSES, base)
    r2 = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                     ADDRESSES, shuffled)
    assert r1.ledger.canonical() == r2.ledger.canonical()


# --------------------------------------------------------------------------- #
# 15. information-tier isolation: L0 must not be delivered L1 content
# --------------------------------------------------------------------------- #

def test_15_the_tier_is_declared_by_every_registered_arm():
    expect = {"NoWrite": Tier.L0_FACTUAL, "DeleteFactualPatch": Tier.L0_FACTUAL,
              "SetAlternative": Tier.L1_CORRECTIVE,
              "LocalOracleRestore": Tier.L3_ORACLE}
    for law in LAWS:
        assert getattr(law, "tier", None) is expect[law.name], \
            f"{law.name} declares the wrong information tier"


def test_15b_l0_arms_survive_a_broken_target_generator(monkeypatch):
    """The canary: make the envelope builder explode, and the L0 arms must not care."""
    import rfl_rebuild.b1.runner as runner

    def boom(*a, **kw):
        raise AssertionError("the target envelope must not be built for this arm")

    monkeypatch.setattr(runner, "build_target_envelope", boom)
    for law in (NoWrite, DeleteFactualPatch, LocalOracleRestore):
        res = runner.run_patch_law(law, LearnerPersistentState(), (),
                                   trace=None, kappa=0, phi=0, sol=None)
        assert res.ledger.n_addressed == 0


def test_15c_the_l1_arm_does_require_the_envelope(monkeypatch):
    import rfl_rebuild.b1.runner as runner

    def boom(*a, **kw):
        raise AssertionError("the L1 arm does need the envelope")

    monkeypatch.setattr(runner, "build_target_envelope", boom)
    with pytest.raises(AssertionError):
        runner.run_patch_law(SetAlternative, LearnerPersistentState(), (),
                             trace=None, kappa=0, phi=0, sol=None)


def test_15d_an_l0_law_never_receives_a_non_none_envelope():
    seen = {}

    class _Spy:
        name, alias_of, tier = "SpyL0", None, Tier.L0_FACTUAL

        def plan(self, addresses, targets):
            from rfl_rebuild.b1.laws import LawPlan
            seen["targets"] = targets
            return LawPlan(self.name, tuple())

    run_patch_law_with_envelope(_Spy(), LearnerPersistentState(), (), envelope())
    assert seen["targets"] is None, \
        "an L0 law must not even be handed the envelope object"


def test_15e_a_missing_record_cannot_fail_an_l0_arm():
    """A broken envelope must not take down an arm that needs no target."""
    s = state_with((A, DOWN))
    res = run_patch_law_with_envelope(DeleteFactualPatch, s, ADDRESSES, {})
    assert res.ledger.n_addressed == 3
    assert dict(res.post_state.decision_overrides) == {}


# --------------------------------------------------------------------------- #
# 16. duplicate credited units fail stop rather than being de-duplicated
# --------------------------------------------------------------------------- #

def test_16_duplicate_credited_units_fail_stop():
    """The earlier guard sat behind a filter that had already removed every duplicate,
    so it could never fire and two ``Decision_3`` entries silently became one address
    — changing N_addressed and the budget."""
    from rfl_rebuild.b1 import resolve_credited_units

    class _T:
        option_in_force = 0
        steps = ()

    with pytest.raises(ProtocolError):
        resolve_credited_units(("Decision_0", "Decision_0"), _T(), 0, 0)


def test_16b_a_duplicated_unit_is_not_silently_collapsed_on_a_real_trace():
    from rfl_rebuild.b1 import resolve_credited_units
    trace, kappa, phi = _real_trace()
    units = ("Decision_0", "Decision_1", "Decision_0")
    with pytest.raises(ProtocolError):
        resolve_credited_units(units, trace, kappa, phi)
    ok = resolve_credited_units(("Decision_0", "Decision_1"), trace, kappa, phi)
    assert len(ok) == 2


@pytest.mark.parametrize("bad_unit", [["Decision_0"], {"Decision_0": 1}, 0, None,
                                      True, 1.0, ("Decision_0",)])
def test_16c_a_non_string_credit_unit_is_a_protocol_error_not_a_crash(bad_unit):
    """The duplicate guard hashed the unit *before* checking its type.

    ``["Decision_0"]`` therefore raised ``TypeError: unhashable type: 'list'`` out of
    ``u in seen_units``, and a plain ``0`` raised ``TypeError`` out of ``re.match`` —
    both instead of the ``PROTOCOL_ERROR`` this module's contract promises. Note the
    list and the dict are the interesting cases: they are the ones a real caller would
    produce by forgetting to unpack a unit.
    """
    from rfl_rebuild.b1 import resolve_credited_units, resolve_decision_address

    class _T:
        option_in_force = 0
        steps = ()

    with pytest.raises(ProtocolError):
        resolve_credited_units((bad_unit,), _T(), 0, 0)
    with pytest.raises(ProtocolError):
        resolve_decision_address(bad_unit, _T(), 0, 0)


def test_16d_the_type_check_precedes_the_duplicate_check():
    """Ordering, not just presence: an unhashable unit must not reach the set."""
    import inspect
    from rfl_rebuild.b1 import targets as targets_mod
    src = inspect.getsource(targets_mod.resolve_credited_units)
    assert src.index("_require_unit(u)") < src.index("u in seen_units"), \
        "the type check must run before the duplicate guard hashes the unit"


# --------------------------------------------------------------------------- #
# 17. envelope structural integrity
# --------------------------------------------------------------------------- #

def test_17_a_record_keyed_by_one_address_but_describing_another_fails_stop():
    env = dict(envelope())
    rec = env[A]
    env[A] = TargetRecord(address=B, alternative=rec.alternative,
                          factual_command=rec.factual_command)
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                    ADDRESSES, env)


RUSH0 = DecisionAddress(state=State(x=0, y=2, t=0, kappa=0, phi=0), z=0, m=0)
RESTRICTIVE = (RUSH0,)


def restrictive_envelope(alt):
    return {RUSH0: TargetRecord(RUSH0, alt, RIGHT)}


@pytest.mark.parametrize("bad_value", [WAIT, UP, DOWN, LEFT, 99, True, 1.0, "UP"])
def test_17b_an_inadmissible_or_non_action_target_fails_stop(bad_value):
    """A store would accept it and the runner would report APPLIED; the breach would
    only surface in a later episode's decision adapter."""
    # rush at START admits only RIGHT, so every other action id is inadmissible
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                    RESTRICTIVE, restrictive_envelope(bad_value))


def test_17c_a_target_equal_to_the_factual_command_fails_stop():
    bad = dict(envelope())
    bad[A] = TargetRecord(A, RIGHT, RIGHT)
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                    ADDRESSES, bad)


def _real_trace():
    """A genuine factual trace for tests that need real contexts."""
    from rfl_rebuild.env.kernel import SemanticTape
    from rfl_rebuild.solve.dp import solve_reference
    sol = solve_reference()
    provider = lambda s, c: sol.best_action(s, c.z, c.m)   # noqa: E731
    tr = K.rollout(kappa=0, tape=SemanticTape(phase=0, error_flag=0, cause_rank=0),
                   command_provider=provider, base_option=1)
    return tr, 0, 0


def test_17d_the_builder_rejects_an_address_that_is_not_the_factual_context():
    from rfl_rebuild.b1 import build_target_envelope
    from rfl_rebuild.solve.dp import solve_reference
    trace, kappa, phi = _real_trace()
    real = DecisionAddress(state=A.state, z=1, m=0)     # the actual (z, m) at t=1
    good = build_target_envelope(solve_reference(), (real,), trace, kappa, phi)
    assert real in good
    liar = DecisionAddress(state=A.state, z=3, m=7)     # same t, wrong z/m
    with pytest.raises(ProtocolError):
        build_target_envelope(solve_reference(), (liar,), trace, kappa, phi)


ROGUE = DecisionAddress(state=State(x=0, y=2, t=0, kappa=0, phi=0), z=0, m=0)


def test_17e_an_extra_non_credited_key_fails_stop():
    """Containment is not exactness.

    ``{A, B, C, ROGUE}`` satisfies "every credited address has a record", so the earlier
    check accepted it and handed the $L_1$ law corrective content for an address that
    was never credited. That ``SetAlternative`` does not currently read the extra key is
    not the point — the information was delivered.
    """
    env = dict(envelope())
    env[ROGUE] = TargetRecord(ROGUE, DOWN, RIGHT)
    assert set(env) > set(ADDRESSES), "the test envelope must be a strict superset"
    with pytest.raises(ProtocolError) as ei:
        run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                    ADDRESSES, env)
    assert "non-credited key" in str(ei.value)


def test_17f_a_none_envelope_is_a_protocol_error_not_a_typeerror():
    """``a not in targets`` with ``targets=None`` raised ``TypeError: argument of type
    'NoneType' is not iterable`` where the contract promises ``PROTOCOL_ERROR``."""
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                    ADDRESSES, None)
    for bad in ([], "targets", 0, TargetRecord(A, UP, RIGHT)):
        with pytest.raises(ProtocolError):
            run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                        ADDRESSES, bad)


@pytest.mark.parametrize("bad_factual", [None, -1, 99, True, "RIGHT", 1.0])
def test_17g_a_bogus_factual_command_fails_stop(bad_factual):
    """``a^+ != a^F`` is meaningless against a factual command that is not an action."""
    bad = dict(envelope())
    bad[A] = TargetRecord(A, UP, bad_factual)
    with pytest.raises(ProtocolError):
        run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                    ADDRESSES, bad)


def test_17h_the_structural_check_does_not_claim_to_ground_the_factual_command():
    """Recorded so 17g is not read as proving more than it checks.

    A *legal but false* factual command still passes: nothing in a trace-free structural
    check can tell it from the true one. Grounding is the builder's job, and this gate
    pins both halves — the hole that remains, and the guarantee that closes it on the
    only path an envelope for a real scene can take.
    """
    lie = dict(envelope())
    lie[A] = TargetRecord(A, UP, DOWN)          # DOWN is a legal action, but not a^F
    run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                ADDRESSES, lie)     # deliberately accepted

    from rfl_rebuild.b1 import build_target_envelope
    from rfl_rebuild.env.observation import walk_transition
    from rfl_rebuild.solve.dp import solve_reference
    from rfl_rebuild.b1 import resolve_credited_units
    trace, kappa, phi = _real_trace()
    rows = list(walk_transition(trace, kappa, phi, trace.option_in_force))
    by_t = {s.t: (z, m, a_cmd) for (s, z, m, a_cmd, _ar, _rw) in rows}
    addresses = resolve_credited_units(
        tuple(f"Decision_{t}" for t in sorted(by_t)), trace, kappa, phi)
    assert len(addresses) >= 3, "the probe needs a few real decision contexts"
    built = build_target_envelope(solve_reference(), addresses, trace, kappa, phi)
    for addr in addresses:
        _z, _m, a_cmd = by_t[addr.state.t]
        assert built[addr].factual_command == a_cmd, \
            "the builder must record the TRACE's factual command"


# --------------------------------------------------------------------------- #
# 18. per-receipt ledger invariant, not just the aggregate
# --------------------------------------------------------------------------- #

def test_18_a_locally_wrong_receipt_is_caught_even_when_the_global_digest_moved():
    """A wrote, B did not, and B is mislabelled ``APPLIED, store_changed=False``.

    The earlier check branched on the GLOBAL fingerprint first, so with A's change
    present it took the ``else`` branch and never looked at B.
    """
    from rfl_rebuild.b1 import DecisionWriteReceipt, UpdateLedger
    good = DecisionWriteReceipt(address=A, status=APPLIED, store_changed=True)
    bad = DecisionWriteReceipt(address=B, status=APPLIED, store_changed=False)
    led = UpdateLedger(receipts=(good, bad), fingerprint_pre="p", fingerprint_post="q")
    with pytest.raises(ProtocolError):
        led.check_fingerprint_invariants()


def test_18b_a_non_applied_receipt_whose_address_changed_is_caught():
    from rfl_rebuild.b1 import DecisionWriteReceipt, UpdateLedger
    bad = DecisionWriteReceipt(address=A, status=EVALUABLE_NOOP, store_changed=True)
    led = UpdateLedger(receipts=(bad,), fingerprint_pre="p", fingerprint_post="q")
    with pytest.raises(ProtocolError):
        led.check_fingerprint_invariants()


def test_18c_protocol_error_is_never_a_receipt_status():
    from rfl_rebuild.b1 import DecisionWriteReceipt, UpdateLedger
    bad = DecisionWriteReceipt(address=A, status=PROTOCOL_ERROR, store_changed=False)
    led = UpdateLedger(receipts=(bad,), fingerprint_pre="p", fingerprint_post="p")
    with pytest.raises(ProtocolError):
        led.check_fingerprint_invariants()


def test_18d_an_unknown_receipt_status_is_rejected():
    from rfl_rebuild.b1 import DecisionWriteReceipt, UpdateLedger
    bad = DecisionWriteReceipt(address=A, status="MAYBE", store_changed=False)
    led = UpdateLedger(receipts=(bad,), fingerprint_pre="p", fingerprint_post="p")
    with pytest.raises(ProtocolError):
        led.check_fingerprint_invariants()


def test_18e_the_aggregate_must_agree_with_the_per_address_changes():
    from rfl_rebuild.b1 import DecisionWriteReceipt, UpdateLedger
    r = DecisionWriteReceipt(address=A, status=EVALUABLE_NOOP, store_changed=False)
    led = UpdateLedger(receipts=(r,), fingerprint_pre="p", fingerprint_post="q")
    with pytest.raises(ProtocolError):
        led.check_fingerprint_invariants()


# --------------------------------------------------------------------------- #
# ledger shape
# --------------------------------------------------------------------------- #

def test_ledger_reports_zero_scalar_metrics_and_marks_them_inapplicable():
    res = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                      ADDRESSES, envelope())
    led = res.ledger
    assert led.scalar_metrics_applicable is False
    assert (led.n_scalar, led.sum_abs_delta, led.max_abs_delta) == (0, 0.0, 0.0)
    assert led.n_addressed == 3
    assert led.n_changed_addresses == 2
    assert led.status_counts[APPLIED] == 2
    assert led.status_counts[NO_VALID_ALTERNATIVE] == 1
    assert led.n_changed_addresses > 0 and led.n_scalar == 0, \
        "APPLIED with zero scalar delta must not read as a no-op"


def test_receipts_carry_no_truth_or_scenario_identity():
    res = run_patch_law_with_envelope(SetAlternative, LearnerPersistentState(),
                                      ADDRESSES, envelope())
    for r in res.ledger.receipts:
        for name in _FORBIDDEN:
            assert not hasattr(r, name)
        assert not hasattr(r, "gamma_star")
        # `canonical_form` is the domain's encoding of the receipt's own address, so it is a
        # function of the address and of nothing else -- not truth, not a regime, not a fire
        # pattern, not a scenario identity. It is a field rather than a method because the
        # receipt no longer knows what kind of address it holds (A80 68.2).
        assert set(r.__slots__) == {"address", "status", "store_changed",
                                    "canonical_form"}


def test_no_write_run_still_produces_a_full_ledger():
    res = run_patch_law_with_envelope(NoWrite, LearnerPersistentState(),
                                      ADDRESSES, envelope())
    assert res.ledger.n_addressed == 3
    assert res.ledger.status_counts[EVALUABLE_NOOP] == 3
