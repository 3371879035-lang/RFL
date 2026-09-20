r"""A80 §68.5 — $P\times\{L_1,L_3\}$: the process path and its assisted input.

$$\boxed{P_{id} \in L_1, \qquad P_{id} \notin L_0}$$

Five chains carry the cell, and the gates are grouped by them:

1. **the credit unit and the assisted input** — the static family, the nominal carrier, and the
   exact-integer-first rule at the option key;
2. **$P_{id} \notin L_0$** — the refusal is mechanical, and it holds even when the caller already
   holds a legal integer, because *address resolution* and *information delivered to the law* are
   different things;
3. **the $L_1$ envelope** — $\{z^{\text{proposal}}\}$ delivered explicitly, exactly, and agreeing
   with the credited address; a proposal that no envelope delivered is not a proposal this cell may
   use;
4. **the operation** — $\texttt{Edit}(\texttt{PROCESS}, z, z)$, one plan serving $L_1$ and the
   $L_3$ alias whose delivery is empty;
5. **the transaction** — one pre-state, one atomic commit, one receipt per resolved address.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1 import (  # noqa: E402
    APPLIED, EVALUABLE_NOOP, AssistedInput, ILL_TYPED, NoWriteRef, PId,
    PLocalOracleRestore, P_DOMAIN, P_LAWS, P_SLICE, ProcessTarget, ProtocolError, Tier,
    build_process_envelope, independent_treatment_count, law_metadata,
    require_process_option, require_process_unit, resolve_process_addresses,
    run_process_law, validate_process_envelope,
)
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    PROCESS, Edit, LearnerPersistentState, StoreTransactionError,
)

OPTIONS = K.option_ids()
Z0, Z1 = OPTIONS[0], OPTIONS[1]


def dirty_state(z, value):
    """A pre-state that already carries an override at ``z``, so a restore has something to do."""
    state = LearnerPersistentState()
    state.apply_transaction([Edit(PROCESS, z, value)])
    return state


# --------------------------------------------------------------------------- #
# 1. the credit unit and the assisted input
# --------------------------------------------------------------------------- #

def test_1_the_credit_unit_is_the_static_process_family():
    r"""A69's `ProcessCommit` is static, not indexed: one unit, its own resolver, its own input.

    Another family is another architecture's credit — a `Decision_...`, a `ControllerSite_...`, a
    `Strategy` — and admitting one here would let a credit from a different mechanism reach the
    process store through $\rho_P$.
    """
    assert resolve_process_addresses(("ProcessCommit",), AssistedInput(Z0)) == (Z0,)
    for foreign in ("Decision_0", "ControllerSite_0_2_3_1", "Strategy", "ExternalPlant",
                    "Unknown/NoWrite", "processcommit", "ProcessCommit_0", ""):
        with pytest.raises(ProtocolError) as ei:
            resolve_process_addresses((foreign,), AssistedInput(Z0))
        assert "not a process credit unit" in str(ei.value), foreign
        with pytest.raises(ProtocolError) as ei:
            require_process_unit(foreign)
        assert "not a process credit unit" in str(ei.value)
    # the type check runs before anything matches the unit
    for untyped in (["ProcessCommit"], {"ProcessCommit": 1}, 0, None, True, 1.0,
                    ("ProcessCommit",)):
        with pytest.raises(ProtocolError) as ei:
            resolve_process_addresses((untyped,), AssistedInput(Z0))
        assert "is not a string" in str(ei.value)
    # a repeat is refused, not de-duplicated; an empty population is not a run of this cell
    with pytest.raises(ProtocolError) as ei:
        resolve_process_addresses(("ProcessCommit", "ProcessCommit"), AssistedInput(Z0))
    assert "more than once" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        resolve_process_addresses((), AssistedInput(Z0))
    assert "no credited process unit" in str(ei.value)


def test_2_the_assisted_input_is_nominal():
    r"""A duck stand-in carrying `z_proposal` is refused: the proposal must be *handed over*.

    ``getattr``-style acceptance would take the assisted input from anything that looks like one,
    including an object the code under test built for itself — which is the laundering A80 §68.5
    forbids, arriving through the type system rather than through a side channel.
    """
    class StandIn:
        z_proposal = Z0

    for bad in (StandIn(), None, Z0, "ProcessCommit", (Z0,)):
        with pytest.raises(ProtocolError) as ei:
            resolve_process_addresses(("ProcessCommit",), bad)
        assert "not" in str(ei.value) and "AssistedInput" in str(ei.value), bad
    assert type(AssistedInput(Z0)) is AssistedInput


def test_3_the_option_key_is_exact_integer_first_then_domain_membership():
    r"""$$\boxed{\text{exact } int \rightarrow \text{domain membership}}$$

    `True == 1` and `1.0 == 1` with equal hashes, so a membership test alone would credit a
    boolean or a float as the option it resembles and persist it as a legal-looking key (A78
    §66.5's finding, at this store). The two failures must also stay distinguishable: a wrong type
    is a different defect from an out-of-domain integer.
    """
    assert require_process_option(Z0) == Z0
    for alias in (True, False, 1.0, 0.0, float(Z0), bool(Z0)):
        with pytest.raises(ProtocolError) as ei:
            require_process_option(alias)
        assert "not int" in str(ei.value), alias
        with pytest.raises(ProtocolError):
            resolve_process_addresses(("ProcessCommit",), AssistedInput(alias))
    for outside in (-1, max(OPTIONS) + 1, 99):
        with pytest.raises(ProtocolError) as ei:
            require_process_option(outside)
        assert "not an option id" in str(ei.value), outside
    for untyped in ("1", None, 1 + 0j, [1]):
        with pytest.raises(ProtocolError):
            require_process_option(untyped)
    # the substrate's own boundary agrees, which is why the alias must not get that far
    for alias in (True, 1.0):
        with pytest.raises(StoreTransactionError):
            LearnerPersistentState().apply_transaction([Edit(PROCESS, alias, Z1)])


# --------------------------------------------------------------------------- #
# 2. P_id is at L1, not L0
# --------------------------------------------------------------------------- #

def test_4_p_id_at_l0_is_a_protocol_error_even_with_a_legal_integer_in_hand():
    r"""$$\boxed{P_{id} \text{ at } L_0 \Longrightarrow \texttt{PROTOCOL\_ERROR}}$$

    The factual rows carry $z^{\text{in-force}}$ and never $z^{\text{proposal}}$, so $L_0$ cannot
    know the key (A76 §63.1) — the refusal is a property of the frozen cell table, not a
    convention. This gate is the anti-laundering core: the caller *does* hold a legal integer
    address, the store *is* writable, and the run is refused anyway, because a proposal the cell
    was not handed is not a proposal it may use.
    """
    class PIdAtL0(PId):
        """A real subclass declaring the L0 cell — the placement defect, as a law."""

        tier = Tier.L0_FACTUAL

    state = dirty_state(Z0, Z1)
    addresses = resolve_process_addresses(("ProcessCommit",), AssistedInput(Z0))
    assert addresses == (Z0,)
    with pytest.raises(ProtocolError) as ei:
        run_process_law(PIdAtL0, state, addresses, AssistedInput(Z0))
    assert "no substantive treatment at tier" in str(ei.value)
    # ... and the table itself is the reason, not the runner's mood
    assert P_SLICE.cells[Tier.L0_FACTUAL] is ILL_TYPED
    with pytest.raises(ProtocolError):
        P_SLICE.fields(Tier.L0_FACTUAL)
    # P_id's declared cell is L1, and the L0 cell has neither a law nor a reference
    assert PId.tier is Tier.L1_CORRECTIVE
    assert [type(x).__name__ for x in P_LAWS if isinstance(x, NoWriteRef)] == \
        ["NoWriteRef", "NoWriteRef"]
    assert [x.tier for x in P_LAWS if isinstance(x, NoWriteRef)] == \
        [Tier.L1_CORRECTIVE, Tier.L3_ORACLE]


# --------------------------------------------------------------------------- #
# 3. the L1 envelope
# --------------------------------------------------------------------------- #

def test_5_the_l1_delivery_is_the_assisted_input_and_nothing_else():
    r"""$$\boxed{\text{address resolution} \neq \text{information delivered to the law}}$$

    The cell *delivers* $\{z^{\text{proposal}}\}$ explicitly; the address is what the plan reads.
    This gate records what each cell actually hands the law, so "delivered" is observed rather
    than asserted from the field set:

    * $L_1$ hands `{z_proposal: <the assisted proposal>}`;
    * $L_3$ hands **nothing at all** — not an empty container, and not a proposal found elsewhere.
    """
    seen = []

    class Recording(PId):
        """The same operation, plus a note of what the cell delivered."""

        def plan(self, addresses, targets):
            seen.append(targets)
            return super().plan(addresses, targets)

    class RecordingL3(PLocalOracleRestore):
        def plan(self, addresses, targets):
            seen.append(targets)
            return super().plan(addresses, targets)

    addresses = (Z0,)
    run_process_law(Recording, LearnerPersistentState(), addresses, AssistedInput(Z0))
    assert len(seen) == 1 and seen[0] is not None
    delivered = seen[0][Z0]
    # the law is handed a projection over the cell's *declared* names, not the record itself
    assert dict(delivered) == {"z_proposal": Z0}
    assert set(delivered) == P_SLICE.fields(Tier.L1_CORRECTIVE)
    # ... and a record that grew a field cannot widen what a law sees: the projection is over
    # declared names, so the extra one is dropped rather than delivered
    class Wider(ProcessTarget):
        """A record that grew a field."""
        __slots__ = ()

    wide = Wider(z_proposal=Z0)
    projected = P_SLICE.deliver(Tier.L1_CORRECTIVE, addresses, {Z0: wide})
    assert dict(projected[Z0]) == {"z_proposal": Z0}
    seen.clear()
    run_process_law(RecordingL3, LearnerPersistentState(), addresses, AssistedInput(Z0))
    assert seen == [None], "the L3 delivery must be empty, not another proposal source"
    # the envelope the runner builds carries exactly the credited address and the resolved value
    envelope = build_process_envelope(addresses, AssistedInput(Z0))
    assert set(envelope) == set(addresses)
    assert envelope[Z0].z_proposal == Z0
    validate_process_envelope(addresses, envelope)


def test_6_the_envelope_must_be_exactly_the_credited_population_and_must_agree():
    r"""Missing, extra, fabricated and mistyped deliveries all fail stop.

    The agreement rule is what makes $\texttt{Edit}(\texttt{PROCESS}, z, z)$ well defined: a
    delivery that disagreed with the address would have the cell write one option while being
    credited at another.
    """
    addresses = (Z0,)
    legal = build_process_envelope(addresses, AssistedInput(Z0))
    with pytest.raises(ProtocolError) as ei:
        validate_process_envelope(addresses, {})
    assert "delivery must be exactly" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        validate_process_envelope(addresses, {Z0: ProcessTarget(Z0), Z1: ProcessTarget(Z1)})
    assert "delivery must be exactly" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        validate_process_envelope(addresses, {Z0: ProcessTarget(Z1)})
    assert "disagrees with the credited process address" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        validate_process_envelope(addresses, {Z0: Z0})
    assert "not ProcessTarget" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        validate_process_envelope(addresses, {Z0: ProcessTarget(True)})
    assert "not int" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        validate_process_envelope(addresses, {Z0: ProcessTarget(max(OPTIONS) + 9)})
    assert "not an option id" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        validate_process_envelope(addresses, None)
    assert "no envelope was supplied" in str(ei.value)
    assert legal[Z0].z_proposal == Z0


def test_7_a_run_without_a_delivered_proposal_is_refused():
    r"""No assisted input, no run: the cell may not fall back on the store or the caller's integer."""
    addresses = (Z0,)
    state = dirty_state(Z0, Z1)
    for missing in (None, Z0, "ProcessCommit"):
        with pytest.raises(ProtocolError) as ei:
            run_process_law(PId, state, addresses, missing)
        assert "AssistedInput" in str(ei.value), missing
    # the state is untouched by the refused runs
    assert dict(state.process_overrides) == {Z0: Z1}


def test_8_the_proposal_comes_from_the_assisted_input_not_from_the_store():
    r"""The laundering gate: a proposal the envelope did not deliver is not this cell's input.

    The store in this scene *already* carries an override at the credited key with a different
    legal option id — i.e. a proposal is reachable from a kernel/state object, exactly the
    situation A80 §68.5 rules out of bounds. The run must resolve, deliver and write the
    **assisted** proposal, and the identity assignment must canonicalise to a deletion, so:

    $$\text{dirty } \{z \mapsto v\} \xrightarrow{P_{id}(z)} \varnothing, \quad \texttt{APPLIED}$$

    An implementation that read the proposal from the state would either deliver $v$ (refused,
    because it disagrees with the credited address) or write $v$ (wrong store afterwards); both are
    killed here rather than by inspection.
    """
    addresses = resolve_process_addresses(("ProcessCommit",), AssistedInput(Z0))
    state = dirty_state(Z0, Z1)
    assert dict(state.process_overrides) == {Z0: Z1}
    res = run_process_law(PId, state, addresses, AssistedInput(Z0))
    assert dict(state.process_overrides) == {}, "the identity write must delete the override"
    assert set(r.status for r in res.ledger.receipts) == {APPLIED}
    assert res.ledger.store_changed
    res.ledger.check_fingerprint_invariants()
    # and the delivered field was the assisted proposal, not the stored value
    envelope = build_process_envelope(addresses, AssistedInput(Z0))
    assert envelope[Z0].z_proposal == Z0 != Z1


# --------------------------------------------------------------------------- #
# 4. the operation, and the L3 alias
# --------------------------------------------------------------------------- #

def test_9_the_operation_is_the_identity_assignment_at_the_resolved_address():
    r"""$$\boxed{P_{id}:\ \texttt{Edit}(\texttt{PROCESS}, z, z)}$$

    Read from the **address**, which is why one function serves both cells: at $L_3$ there is no
    envelope at all. The plan is also checked to be about the credited address and nothing else.
    """
    addresses = (Z0,)
    plan = PId().plan(addresses, None)
    assert plan.name == "P_id"
    assert len(plan.plans) == 1
    one = plan.plans[0]
    assert one.address == Z0
    assert len(one.edits) == 1
    edit = one.edits[0]
    assert (edit.store, edit.address, edit.value) == (PROCESS, Z0, Z0)


def test_10_the_alias_is_one_implementation_and_the_same_transformation():
    r"""$L_3$ is an **alias**, not a second delete-law.

    `PLocalOracleRestore.plan is PId.plan` — a re-implementation that happened to behave the same
    would be a different object wearing the same name (A77 §65.2's alias precedent). And on a
    **dirty** pre-state the two are equal as *state transformations*, not merely both legal:
    identical post-stores from identical pre-states.
    """
    assert PLocalOracleRestore.plan is PId.plan
    assert PLocalOracleRestore.alias_of == "P_id"
    assert PLocalOracleRestore.tier is Tier.L3_ORACLE
    addresses = resolve_process_addresses(("ProcessCommit",), AssistedInput(Z0))
    a, b = dirty_state(Z0, Z1), dirty_state(Z0, Z1)
    ra = run_process_law(PId, a, addresses, AssistedInput(Z0))
    rb = run_process_law(PLocalOracleRestore, b, addresses, AssistedInput(Z0))
    assert dict(a.process_overrides) == dict(b.process_overrides) == {}
    assert ra.ledger.fingerprint_post == rb.ledger.fingerprint_post
    assert ra.ledger.n_addressed == rb.ledger.n_addressed == 1
    assert [r.status for r in ra.ledger.receipts] == [r.status for r in rb.ledger.receipts]


def test_11_healthy_state_is_a_noop_and_the_second_run_is_idempotent():
    addresses = (Z0,)
    healthy = LearnerPersistentState()
    first = run_process_law(PId, healthy, addresses, AssistedInput(Z0)).ledger
    assert not first.store_changed
    assert set(r.status for r in first.receipts) == {EVALUABLE_NOOP}
    assert first.fingerprint_pre == first.fingerprint_post
    dirty = dirty_state(Z0, Z1)
    assert run_process_law(PId, dirty, addresses, AssistedInput(Z0)).ledger.store_changed
    second = run_process_law(PId, dirty, addresses, AssistedInput(Z0)).ledger
    assert not second.store_changed
    assert second.fingerprint_pre == second.fingerprint_post


def test_12_locality_owner_and_the_store_boundary_are_load_bearing():
    r"""`owner_P` is the identity, so an edit at another key is refused by the runner, not the law.

    The store's own boundary is asked separately: a plan that named a boolean or a float key would
    be refused by the substrate even if the runner's domain check were relaxed.
    """
    from rfl_rebuild.b1 import AddressPlan, LawPlan

    class WrongOwner(PId):
        """Writes a different (legal) option than the one it is credited at."""

        def plan(self, addresses, targets):
            return LawPlan(self.name, tuple(
                AddressPlan(z, (Edit(PROCESS, OPTIONS[-1], OPTIONS[-1]),))
                for z in addresses))

    addresses = resolve_process_addresses(("ProcessCommit",), AssistedInput(Z0))
    with pytest.raises(ProtocolError) as ei:
        run_process_law(WrongOwner, LearnerPersistentState(), addresses, AssistedInput(Z0))
    assert "owner" in str(ei.value) or "locality" in str(ei.value)
    # a plan that writes another store is refused by the domain's store rule
    class WrongStore(PId):
        """Writes the decision store from the process slice."""

        def plan(self, addresses, targets):
            from rfl_rebuild.b1 import AddressPlan, LawPlan
            from rfl_rebuild.learner.store import DECISION, DecisionAddress
            from rfl_rebuild.env.kernel import State

            addr = DecisionAddress(state=State(x=0, y=0, t=0, kappa=0, phi=0), z=Z0, m=0)
            return LawPlan(self.name, tuple(
                AddressPlan(z, (Edit(DECISION, addr, 1),)) for z in addresses))

    with pytest.raises(ProtocolError) as ei:
        run_process_law(WrongStore, LearnerPersistentState(), addresses, AssistedInput(Z0))
    assert "store" in str(ei.value)
    # the domain's store rule types the key
    for bad in (True, 1.0, "1", None, max(OPTIONS) + 5):
        with pytest.raises(ProtocolError):
            P_DOMAIN.require_store(bad)
    assert P_DOMAIN.canonical(Z0) == f"z={Z0}"
    assert P_DOMAIN.tag == "P"
    assert P_DOMAIN.canonical(Z0) != P_DOMAIN.canonical(Z1)


# --------------------------------------------------------------------------- #
# 5. the transaction
# --------------------------------------------------------------------------- #

def test_13_one_transaction_and_one_receipt_per_resolved_address():
    addresses = resolve_process_addresses(("ProcessCommit",), AssistedInput(Z0))
    state = dirty_state(Z0, Z1)
    calls = []
    original = LearnerPersistentState.apply_transaction

    def spy(self, edits, **kwargs):
        calls.append(tuple(edits))
        return original(self, edits, **kwargs)

    LearnerPersistentState.apply_transaction = spy
    try:
        res = run_process_law(PId, state, addresses, AssistedInput(Z0))
    finally:
        LearnerPersistentState.apply_transaction = original
    assert len(calls) == 1, f"one scene commits once, got {len(calls)}"
    assert res.ledger.n_addressed == len(addresses)
    assert len(res.ledger.receipts) == len(addresses)
    assert [r.canonical_form for r in res.ledger.receipts] == [f"z={Z0}"]
    res.ledger.check_fingerprint_invariants()


def test_15_the_two_l1_arms_share_one_resolution_and_one_envelope():
    r"""Same cell $\Rightarrow$ same envelope, and the same refusal for the same bad input.

    A75 §62.3's rule at this cell: the treatment and its same-tier reference are run through the
    same resolver and the same delivery, so the two cannot differ in what they were allowed to
    know. The reference writes nothing and the treatment restores, and a proposal the assisted
    input did not authorise fails **both** arms at the same boundary rather than one of them.
    """
    addresses = resolve_process_addresses(("ProcessCommit",), AssistedInput(Z0))
    ref_state, treat_state = dirty_state(Z0, Z1), dirty_state(Z0, Z1)
    ref = run_process_law(NoWriteRef(Tier.L1_CORRECTIVE), ref_state, addresses, AssistedInput(Z0))
    treat = run_process_law(PId, treat_state, addresses, AssistedInput(Z0))
    assert not ref.ledger.store_changed and ref_state.process_overrides == {Z0: Z1}
    assert treat.ledger.store_changed and treat_state.process_overrides == {}
    assert ref.ledger.n_addressed == treat.ledger.n_addressed == 1
    assert [r.address for r in ref.ledger.receipts] == [r.address for r in treat.ledger.receipts]
    # the same illegal assisted input refuses both arms, identically
    for arm in (NoWriteRef(Tier.L1_CORRECTIVE), PId):
        with pytest.raises(ProtocolError) as ei:
            run_process_law(arm, dirty_state(Z0, Z1), addresses, AssistedInput(True))
        assert "not int" in str(ei.value)
        with pytest.raises(ProtocolError):
            run_process_law(arm, dirty_state(Z0, Z1), addresses, AssistedInput(99))


def test_14_the_cell_table_is_the_frozen_one():
    r"""A76 §63.9's $P$ row, written: $L_1$ delivers, $L_3$ is empty, $L_0$/$L_2$ are ill-typed."""
    assert P_SLICE.fields(Tier.L1_CORRECTIVE) == frozenset({"z_proposal"})
    assert P_SLICE.fields(Tier.L3_ORACLE) == frozenset()
    assert P_SLICE.cells[Tier.L0_FACTUAL] is ILL_TYPED
    assert P_SLICE.cells[Tier.L2_COUNTERFACTUAL] is ILL_TYPED
    assert P_SLICE.scalar is False
    assert P_SLICE.store == PROCESS
    assert P_SLICE.name == "P"
    assert set(P_SLICE.implemented_tiers) == {Tier.L1_CORRECTIVE, Tier.L3_ORACLE}
    kinds = [k for _n, k, _a in law_metadata(P_LAWS)]
    assert kinds == ["reference", "operation", "reference", "alias"]
    assert independent_treatment_count(P_LAWS) == 1
    # the L0/L2 cells get no arm and no same-tier reference
    assert all(getattr(x, "tier", None) not in (Tier.L0_FACTUAL, Tier.L2_COUNTERFACTUAL)
               for x in P_LAWS)
