r"""A77 §65.4, §65.5 — the $Q$ store and the $D_Q$ read substrate.

Step 3 answers exactly one question:

$$\boxed{Q_D^L\text{ can be persisted and can correctly drive a decision}}$$

and **not** what should be written into it. So there is no $F_t$, no $G_t^F$, no
$G_t^{CF}$ and no update law here; those are step 4, and the last gate in this file
asserts their absence from the substrate rather than trusting the commit boundary.

The gates are the ones A77 §65.4/§65.5 owe: typed keys, a finite-scalar value domain,
identity canonicalisation, the 13,824-context policy census, tie-breaking, persistence
across episodes, snapshot immutability, clone isolation, cross-store atomicity, domain
closure at the transaction boundary, a reference that fails stop instead of raising
``KeyError``, co-residence refused before an adapter exists, and a fingerprint that is
order-independent and uses ``float.hex()``.
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
    APPLIED, EVALUABLE_NOOP, DecisionWriteReceipt, ProtocolError, UpdateLedger,
    fingerprint,
)
from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import State  # noqa: E402
from rfl_rebuild.env.observation import walk_transition  # noqa: E402
from rfl_rebuild.learner.reference import (  # noqa: E402
    QReferenceView, ReferenceContractError, reference_view_from,
)
from rfl_rebuild.learner.store import (  # noqa: E402
    DECISION, PROCESS, Q, ControllerSite, DecisionAddress, Edit,
    LearnerPersistentState, LearnerStateError, QAddress, StoreTransactionError,
    owner_Q,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

SOL = solve_reference()
VIEW = reference_view_from(SOL)


def ctx(t: int = 1, kappa: int = 0, phi: int = 0) -> State:
    return State(x=1, y=2, t=t, kappa=kappa, phi=phi)


A = DecisionAddress(state=ctx(), z=1, m=0)
Q0 = QAddress(state=ctx(), z=1, m=0, a=0)
Q1 = QAddress(state=ctx(), z=1, m=0, a=1)


def write(state, edits):
    state.apply_transaction(edits, q_reference=VIEW)


# --------------------------------------------------------------------------- #
# 1-2. typed keys and a finite-scalar value domain
# --------------------------------------------------------------------------- #

def test_1_a_q_key_must_be_a_typed_q_address():
    s = LearnerPersistentState()
    for bad in ["q", 0, A, None, ("s", 1, 0, 0)]:
        with pytest.raises(StoreTransactionError):
            write(s, [Edit(Q, bad, 1.0)])
    with pytest.raises(StoreTransactionError):
        write(s, [Edit(Q, QAddress(state="oops", z=1, m=0, a=0), 1.0)])
    with pytest.raises(StoreTransactionError):
        write(s, [Edit(Q, QAddress(state=ctx(), z=99, m=0, a=0), 1.0)])
    with pytest.raises(StoreTransactionError):
        write(s, [Edit(Q, QAddress(state=ctx(), z=1, m=0, a=99), 1.0)])
    assert s.healthy, "no rejected edit may have landed"


def test_1b_a_state_with_non_integer_fields_cannot_key_the_q_store():
    """The shortest path from a type error to a stored value.

    ``_require_q_address`` used to stop at ``isinstance(addr.state, State)``, so
    ``State(x=1.0, ...)`` was a legal key; ``e.address in q_reference`` then compared by
    value, folded ``1.0 == 1``, hit a **legal reference row** and the entry persisted.

    The first case is built from a **real** reference row with an action that is
    genuinely admissible there, and it asserts only that the write raises. That shape is
    deliberate: it is what makes the corresponding mutation *semantic*. A version built
    from a context that is not in the domain at all would still be rejected by the domain
    lookup even with the typing guard removed, so the "mutation" would reopen nothing and
    the gate could only fail on a changed message — evidence that the error path moved,
    not that the vulnerability was reachable.
    """
    # (1) value-preserving float substitution on a row that really exists, with a real
    #     admissible action: only strict typing can refuse this.
    key = VIEW.domains[0]
    legal_state, z, m = key
    a = sorted(VIEW.rows[key])[0]
    folded = State(x=float(legal_state.x), y=legal_state.y, t=legal_state.t,
                   kappa=legal_state.kappa, phi=legal_state.phi)
    assert folded == legal_state, "the substitution must be value-preserving"
    assert QAddress(state=folded, z=z, m=m, a=a) == QAddress(state=legal_state, z=z,
                                                             m=m, a=a), \
        "and it must fold onto the legal key, which is what makes it dangerous"
    s = LearnerPersistentState()
    with pytest.raises(StoreTransactionError):
        write(s, [Edit(Q, QAddress(state=folded, z=z, m=m, a=a),
                       VIEW.value(QAddress(state=legal_state, z=z, m=m, a=a)) + 1.0)])
    assert s.healthy, "the folded key must not have persisted"

    # (2) the same for a bool field, and for the other four fields.
    for st in (State(x=1, y=2, t=3.0, kappa=0, phi=1),
               State(x=1, y=2, t=3, kappa=False, phi=1),
               State(x=1, y=2, t=3, kappa=0, phi=1.0)):
        with pytest.raises(StoreTransactionError):
            write(s, [Edit(Q, QAddress(state=st, z=1, m=0, a=0), 1.0)])
    # (3) and the non-State fields.
    with pytest.raises(StoreTransactionError):
        write(s, [Edit(Q, QAddress(state=ctx(), z=True, m=0, a=0), 1.0)])
    with pytest.raises(StoreTransactionError):
        write(s, [Edit(Q, QAddress(state=ctx(), z=1, m=0.0, a=0), 1.0)])
    with pytest.raises(StoreTransactionError):
        write(s, [Edit(Q, QAddress(state=ctx(), z=1, m=0, a=3.0), 1.0)])
    assert s.healthy


@pytest.mark.parametrize("bad", [True, False, "1.0", None.__class__, float("nan"),
                                 float("inf"), float("-inf"), [1.0]])
def test_2_a_q_value_must_be_a_finite_real(bad):
    """``bool`` is an ``int`` subclass, so without the exclusion ``True`` passes for
    ``1.0`` and the fingerprint carries a type the value domain does not have. NaN and
    infinities would make ``fp_pre == fp_post`` depend on comparison semantics."""
    s = LearnerPersistentState()
    with pytest.raises(StoreTransactionError):
        write(s, [Edit(Q, Q0, bad)])
    assert s.healthy


def test_2b_an_integer_value_is_accepted_and_stored_as_float():
    """Not hostile: ``1`` and ``1.0`` are the same real, and the store canonicalises to
    ``float`` so the ``float.hex()`` accounting is unambiguous."""
    s = LearnerPersistentState()
    write(s, [Edit(Q, Q0, 7)])
    assert type(s.q_overrides[Q0]) is float
    assert s.q_overrides[Q0] == 7.0


# --------------------------------------------------------------------------- #
# 3. identity canonicalisation
# --------------------------------------------------------------------------- #

def test_3_writing_the_reference_value_canonicalises_to_deletion():
    r"""$$Q_D^L(e) \leftarrow Q_D^\ast(e) \Longrightarrow \text{delete } e$$

    A stored entry equal to the reference would make the store non-canonical, and with
    ``float.hex()`` accounting it would appear as a changed entry whose delta is zero —
    the case the whole canonicalisation rule exists to exclude.
    """
    s = LearnerPersistentState()
    ref = VIEW.value(Q0)
    write(s, [Edit(Q, Q0, ref)])
    assert dict(s.q_overrides) == {}, "a reference-valued write is a deletion"
    assert s.healthy
    # and from an overridden state, the same write restores the healthy state
    write(s, [Edit(Q, Q0, ref + 1.0)])
    assert Q0 in s.q_overrides
    write(s, [Edit(Q, Q0, ref)])
    assert dict(s.q_overrides) == {}


def test_3b_an_explicit_none_deletes_too():
    s = LearnerPersistentState()
    write(s, [Edit(Q, Q0, VIEW.value(Q0) + 0.5)])
    write(s, [Edit(Q, Q0, None)])
    assert dict(s.q_overrides) == {}


# --------------------------------------------------------------------------- #
# 4-6. the read path
# --------------------------------------------------------------------------- #

def test_4_the_empty_store_reproduces_the_reference_policy_on_every_context():
    r"""The full census, not a smoke test: all 13,824 contexts.

    $$\boxed{Q_D^L = \varnothing \;\Rightarrow\; a_Q(s,z,m) = \pi_D^\ast(s,z,m)}$$
    """
    provider = LearnerPersistentState().snapshot().q_decision_provider(VIEW)
    n = 0
    for (state, z, m) in VIEW.domains:
        assert provider(state, K.ControlState(z=z, m=m)) == SOL.best_action(state, z, m), \
            f"empty Q store disagreed with pi_D* at ({state!r}, z={z}, m={m})"
        n += 1
    assert n == 13824, f"the census must cover every reference row, covered {n}"


def multi_action_context():
    """The first context with a genuine choice, found rather than assumed.

    These two gates used to ``skip`` when ``VIEW.domains[0]`` happened to have a
    one-action admissible set. A skipped gate is a gate that did not look, so the
    context is selected for the property the test needs. 2,592 of the 13,824 rows are
    singletons, so the search is short and the property is not scarce.
    """
    for key in VIEW.domains:
        if len(VIEW.rows[key]) >= 2:
            return key
    raise AssertionError("no context in the reference has more than one action")


def test_5_one_overridden_entry_changes_the_argmax_when_it_should():
    """A single override must be able to flip the choice, and only where it can."""
    state, z, m = multi_action_context()
    row = VIEW.row(state, z, m)
    base = SOL.best_action(state, z, m)
    target = [a for a in sorted(row) if a != base][0]
    s = LearnerPersistentState()
    write(s, [Edit(Q, QAddress(state=state, z=z, m=m, a=target),
                   max(row.values()) + 1.0)])
    provider = s.snapshot().q_decision_provider(VIEW)
    got = provider(state, K.ControlState(z=z, m=m))
    assert got == target, f"the overridden action must win here, got {got}"
    # an override at an unrelated context must not change this one
    other_ctx = VIEW.domains[1]
    other_a = sorted(VIEW.rows[other_ctx])[0]      # admissible there, not assumed
    s2 = LearnerPersistentState()
    write(s2, [Edit(Q, QAddress(state=other_ctx[0], z=other_ctx[1], m=other_ctx[2],
                                a=other_a), 99.0)])
    provider2 = s2.snapshot().q_decision_provider(VIEW)
    assert provider2(state, K.ControlState(z=z, m=m)) == base


def test_6_ties_still_break_to_the_lowest_action_id():
    """The frozen tie-break, on a row where two actions are made exactly equal."""
    state, z, m = multi_action_context()
    row = VIEW.row(state, z, m)
    a_lo, a_hi = sorted(row)[0], sorted(row)[1]
    s = LearnerPersistentState()
    write(s, [Edit(Q, QAddress(state=state, z=z, m=m, a=a_hi),
                   VIEW.value(QAddress(state=state, z=z, m=m, a=a_lo)))])
    provider = s.snapshot().q_decision_provider(VIEW)
    got = provider(state, K.ControlState(z=z, m=m))
    assert got == a_lo, f"a tie must resolve to the lowest id, got {got}"


def test_6b_the_tie_break_matches_dp_py_by_construction():
    """``dp.py`` uses ``max(row, key=lambda a: (row[a], -a))``: value, then lowest id."""
    state, z, m = multi_action_context()
    row = VIEW.row(state, z, m)
    assert SOL.best_action(state, z, m) == max(row, key=lambda a: (row[a], -a))


# --------------------------------------------------------------------------- #
# 7-9. persistence, snapshot, clone
# --------------------------------------------------------------------------- #

def test_7_a_q_override_persists_into_the_next_episode():
    s = LearnerPersistentState()
    val = VIEW.value(Q0) + 0.25
    write(s, [Edit(Q, Q0, val)])
    snap = s.snapshot()                       # the next episode's view
    assert snap.q_overrides[Q0] == val
    assert snap.healthy is False
    assert snap.decision_provider(lambda st, c: K.WAIT)(ctx(), K.ControlState(z=1, m=0)) \
        == K.WAIT, "a Q override must not leak into the patch channel"


def test_8_an_old_snapshot_does_not_see_a_later_q_write():
    s = LearnerPersistentState()
    before = s.snapshot()
    write(s, [Edit(Q, Q0, VIEW.value(Q0) + 1.0)])
    assert dict(before.q_overrides) == {}, "the snapshot is immutable"
    assert Q0 in s.snapshot().q_overrides


def test_9_clone_isolates_the_q_store():
    s = LearnerPersistentState()
    write(s, [Edit(Q, Q0, VIEW.value(Q0) + 1.0)])
    c = s.clone()
    assert dict(c.q_overrides) == dict(s.q_overrides)
    write(c, [Edit(Q, Q1, VIEW.value(Q1) + 2.0)])
    assert Q1 not in s.q_overrides, "the clone's write must not reach the original"
    write(s, [Edit(Q, Q0, None)])
    assert Q0 in c.q_overrides, "the original's write must not reach the clone"


# --------------------------------------------------------------------------- #
# 10-11. atomicity and domain closure
# --------------------------------------------------------------------------- #

def test_10_an_illegal_q_edit_rolls_back_d_p_and_x_too():
    s = LearnerPersistentState()
    good_d = Edit(DECISION, A, K.UP)
    good_p = Edit(PROCESS, 0, 1)
    good_x = Edit("controller", ControllerSite(state=ctx(), cmd=K.UP), K.DOWN)
    bad_q = Edit(Q, QAddress(state=ctx(), z=1, m=0, a=99), 1.0)   # inadmissible action
    fp_before = fingerprint(s)
    with pytest.raises(StoreTransactionError):
        write(s, [good_d, good_p, good_x, bad_q])
    assert s.healthy, "one illegal Q edit must void the planned D/P/X edits"
    assert fingerprint(s) == fp_before


def test_11_an_entry_outside_the_reference_domain_is_rejected_at_the_boundary():
    """The $Q$ version of ``P_override[99] = 1``: a stored entry the read path can never
    reach would change the fingerprint and clear ``healthy`` while being invisible.

    The third case is the one that carries this gate since strict typing arrived. A bad
    action id and a bad context are now both refused by ``_require_q_address`` before the
    domain lookup runs, so the first two cases no longer reach the check this gate is
    named for. An action that is a **valid id but inadmissible at that context** is what
    only the reference domain can decide — and without it the membership check had no
    witness, which the mutation self-check reported as ``NOT_A_GATE`` until it existed.
    """
    s = LearnerPersistentState()
    for addr in (QAddress(state=ctx(), z=1, m=0, a=99),          # not an action id
                 QAddress(state=ctx(t=99), z=1, m=0, a=0)):      # no such context
        with pytest.raises(StoreTransactionError):
            write(s, [Edit(Q, addr, 1.0)])
    key = next(k for k in VIEW.domains if len(VIEW.rows[k]) < len(K.ACTIONS))
    allowed = set(VIEW.rows[key])
    inadmissible = next(a for a in range(len(K.ACTIONS)) if a not in allowed)
    with pytest.raises(StoreTransactionError) as ei:
        write(s, [Edit(Q, QAddress(state=key[0], z=key[1], m=key[2], a=inadmissible),
                       1.0)])
    assert "outside the reference domain" in str(ei.value)
    assert s.healthy


def test_11b_a_q_edit_requires_the_injected_reference():
    s = LearnerPersistentState()
    with pytest.raises(StoreTransactionError) as ei:
        s.apply_transaction([Edit(Q, Q0, 1.0)])            # no q_reference supplied
    assert "reference" in str(ei.value)
    assert s.healthy


# --------------------------------------------------------------------------- #
# 12. an incomplete reference fails stop
# --------------------------------------------------------------------------- #

def test_12_a_row_that_is_not_total_on_a_z_is_rejected():
    """Row totality, isolated: the **full** domain is supplied, one row loses one action.

    The domain check runs first and would otherwise fire, so this case has to be built on
    a complete set of contexts to test what it is named for.
    """
    key = VIEW.domains[0]
    rows = {k: dict(VIEW.rows[k]) for k in VIEW.domains}
    rows[key].pop(sorted(rows[key])[0])
    with pytest.raises(ReferenceContractError) as ei:
        QReferenceView(rows)
    assert "not total" in str(ei.value)


def test_12e_a_reference_missing_a_whole_legal_context_is_rejected():
    """Domain totality, the direction row-totality cannot see.

    A77 §65.5 states the domain as an **equality**. A cardinality check would let a
    missing context and an invented one cancel, so the comparison is against the shared
    enumerator itself.
    """
    rows = {k: dict(VIEW.rows[k]) for k in VIEW.domains}
    dropped = rows.pop(VIEW.domains[0])
    with pytest.raises(ReferenceContractError) as ei:
        QReferenceView(rows)
    msg = str(ei.value)
    assert "not exactly the frozen decision domain" in msg
    assert "1 of 13824 legal contexts missing" in msg, msg


def test_12f_a_reference_carrying_an_illegal_context_is_rejected():
    """An invented context, even when every row it does carry is internally total.

    Which check fires is now the **typing** one, not the domain equality: strict context
    membership runs first, so by the time the equality is evaluated no surplus key can
    exist. That is the intended order (typing before value comparison), and the equality's
    remaining content is "no legal context is missing", which 12e pins.
    """
    from rfl_rebuild.env.kernel import State as _State
    goal = _State(x=K.GOAL[0], y=K.GOAL[1], t=0, kappa=0, phi=0)   # never a decision point
    rows = {k: dict(VIEW.rows[k]) for k in VIEW.domains}
    rows[(goal, 1, 0)] = dict(VIEW.rows[VIEW.domains[0]])
    with pytest.raises(ReferenceContractError) as ei:
        QReferenceView(rows)
    assert "not a legal decision context" in str(ei.value)
    # m = 2 is outside the automaton-state domain
    rows2 = {k: dict(VIEW.rows[k]) for k in VIEW.domains}
    rows2[(VIEW.domains[0][0], VIEW.domains[0][1], 2)] = dict(VIEW.rows[VIEW.domains[0]])
    with pytest.raises(ReferenceContractError) as ei2:
        QReferenceView(rows2)
    assert "not a legal decision context" in str(ei2.value)


def test_12g_one_complete_row_is_not_a_reference():
    """The case that motivated domain totality: row-total, and still 1/13824 of a view."""
    key = VIEW.domains[0]
    with pytest.raises(ReferenceContractError) as ei:
        QReferenceView({key: dict(VIEW.rows[key])})
    assert "legal contexts missing" in str(ei.value)


def test_12h_the_reference_domain_is_the_shared_enumerator():
    """The view's keys and ``env.domain``'s contexts are the same set, exhaustively."""
    from rfl_rebuild.env.domain import decision_contexts
    assert set(VIEW.rows) == decision_contexts()
    assert len(VIEW.rows) == 13824


def test_12i0_the_folding_premise_these_gates_rest_on():
    """Why strict typing is needed at all: **a set comparison is not a typed comparison**.

    Python folds ``True == 1``, ``1.0 == 1`` and ``False == 0`` with equal hashes, and
    ``State`` is a frozen dataclass, so it inherits that folding. A domain *equality*
    therefore cannot by itself reject a value-preserving type substitution. This test
    pins the premise: if a future Python changed the folding, the gates below would stop
    being about anything and this would say so.
    """
    from rfl_rebuild.env.kernel import State as _S
    assert {3.0} == {3}
    assert (True == 1) and (1.0 == 1) and (False == 0)
    assert _S(x=1, y=2, t=3, kappa=0, phi=1) == _S(x=1.0, y=2, t=3, kappa=0, phi=1)
    assert hash(_S(x=1, y=2, t=3, kappa=0, phi=1)) == \
        hash(_S(x=1.0, y=2, t=3, kappa=0, phi=1))


@pytest.mark.parametrize("field,sub", [
    ("z", lambda k: True if k[1] == 1 else False),      # bool for int
    ("z", lambda k: float(k[1])),                        # float for int
    ("m", lambda k: float(k[2])),
    ("x", lambda k: float(k[0].x)),
    ("t", lambda k: float(k[0].t)),
    ("kappa", lambda k: False if k[0].kappa == 0 else k[0].kappa),
    ("phi", lambda k: float(k[0].phi)),
])
def test_12i_value_preserving_type_substitutions_are_rejected(field, sub):
    """Every one of these passed construction before the strict typing step existed.

    The substituted key is *equal* to a legal context under Python's numeric folding, so
    the domain equality accepted it and the view stored a key whose type the contract does
    not have — and whose action ids the read path would then hand to a kernel that
    requires true integer ids.
    """
    from rfl_rebuild.env.kernel import State as _S
    k = next(kk for kk in VIEW.domains if kk[1] == 1 and kk[2] == 0)
    rows = {kk: dict(VIEW.rows[kk]) for kk in VIEW.domains}
    row = rows.pop(k)
    if field in ("z", "m"):
        new_key = (k[0], sub(k) if field == "z" else k[1],
                   sub(k) if field == "m" else k[2])
    else:
        s = k[0]
        new_key = (_S(x=sub(k) if field == "x" else s.x,
                      y=s.y,
                      t=sub(k) if field == "t" else s.t,
                      kappa=sub(k) if field == "kappa" else s.kappa,
                      phi=sub(k) if field == "phi" else s.phi), k[1], k[2])
    assert new_key == k, "the substitution must be value-preserving to be adversarial"
    rows[new_key] = row
    with pytest.raises(ReferenceContractError):
        QReferenceView(rows)


def test_12j_a_float_action_key_is_rejected():
    """``{3.0} == {3}``, so row totality alone accepts a float action id."""
    k = VIEW.domains[0]
    rows = {kk: dict(VIEW.rows[kk]) for kk in VIEW.domains}
    a = sorted(rows[k])[0]
    rows[k][float(a)] = rows[k].pop(a)
    with pytest.raises(ReferenceContractError) as ei:
        QReferenceView(rows)
    assert "true int" in str(ei.value)


def test_12k_the_domain_predicate_is_type_strict():
    """``is_decision_context`` types before it ranges, because ``in`` is a value test."""
    from rfl_rebuild.env.domain import is_decision_context
    legal = VIEW.domains[0]
    assert is_decision_context(*legal)
    assert not is_decision_context(legal[0], True if legal[1] == 1 else False, legal[2])
    assert not is_decision_context(legal[0], float(legal[1]), legal[2])
    assert not is_decision_context(
        State(x=float(legal[0].x), y=legal[0].y, t=legal[0].t,
              kappa=legal[0].kappa, phi=legal[0].phi), legal[1], legal[2])


def test_12b_out_of_domain_lookups_are_contract_errors_not_keyerrors():
    view = VIEW
    unknown_ctx = QAddress(state=ctx(t=99), z=1, m=0, a=0)
    with pytest.raises(ReferenceContractError):
        view.value(unknown_ctx)
    with pytest.raises(ReferenceContractError):
        view.row(ctx(t=99), 1, 0)
    assert unknown_ctx not in view
    assert "not a QAddress" in str(
        pytest.raises(ReferenceContractError, lambda: view.value(A)).value)


def test_12c_a_non_finite_or_boolean_reference_value_is_rejected():
    for bad in (True, float("nan"), float("inf")):
        rows = {k: dict(VIEW.rows[k]) for k in VIEW.domains}
        key = VIEW.domains[0]
        rows[key][sorted(rows[key])[0]] = bad
        with pytest.raises(ReferenceContractError):
            QReferenceView(rows)


def test_12d_the_reference_views_are_read_only():
    with pytest.raises(TypeError):
        VIEW.rows[VIEW.domains[0]] = {}
    with pytest.raises(TypeError):
        VIEW.rows[VIEW.domains[0]][0] = 1.0


class _FakeReference:
    """A mutable stand-in exposing exactly the two methods the substrate calls.

    Duck typing would accept it. It carries none of the totality, finiteness or
    read-only guarantees, and it can be edited between a store write and a read — which
    is the whole reason the reference is a frozen object rather than a protocol.
    """

    def __init__(self, view):
        self._view = view
        self.edits = 0

    def __contains__(self, address):
        return address in self._view

    def value(self, address):
        return self._view.value(address)

    def row(self, state, z, m):
        return self._view.row(state, z, m)

    def tamper(self):
        self.edits += 1


def test_18_a_duck_typed_fake_reference_is_refused_at_both_boundaries():
    fake = _FakeReference(VIEW)
    s = LearnerPersistentState()
    with pytest.raises(ReferenceContractError) as ei:
        s.snapshot().q_decision_provider(fake)
    assert "QReferenceView" in str(ei.value)
    with pytest.raises(ReferenceContractError) as ei2:
        s.apply_transaction([Edit(Q, Q0, VIEW.value(Q0) + 1.0)], q_reference=fake)
    assert "QReferenceView" in str(ei2.value)
    assert s.healthy, "a refused reference must not have allowed a write"
    fake.tamper()
    assert fake.edits == 1, "the fake was mutable the whole time"


# --------------------------------------------------------------------------- #
# 13. co-residence is refused before an adapter exists
# --------------------------------------------------------------------------- #

def test_13_p_patch_and_q_coresidence_fails_before_adapter_creation():
    """Both entry points, because the rule is symmetric.

    The first version guarded only the $Q$ adapter, so a co-resident snapshot could still
    be served by ``decision_provider`` — which ignored $Q_D^L$ and thereby *implemented*
    the undefined $P_D^L > Q_D^L$ priority the rule exists to refuse.
    """
    s = LearnerPersistentState()
    write(s, [Edit(DECISION, A, K.UP)])
    write(s, [Edit(Q, Q0, VIEW.value(Q0) + 1.0)])
    snap = s.snapshot()
    assert snap.decision_overrides and snap.q_overrides
    with pytest.raises(LearnerStateError) as ei:
        snap.q_decision_provider(VIEW)
    assert "no priority" in str(ei.value)
    with pytest.raises(LearnerStateError) as ei2:
        snap.decision_provider(lambda st, c: K.WAIT)
    assert "no priority" in str(ei2.value)
    assert snap.healthy is False


def test_13b_the_guard_is_shared_not_duplicated():
    """One implementation, so the two entry points cannot drift apart again."""
    import inspect
    src = inspect.getsource(type(LearnerPersistentState().snapshot()))
    assert src.count("def _require_decision_store_exclusive(self)") == 1, \
        "expected exactly one definition"
    assert src.count("self._require_decision_store_exclusive()") == 2, \
        "expected one call in each adapter constructor"
    assert src.count("self._decision and self._q") == 1, \
        "the condition must exist once, in the shared guard"


# --------------------------------------------------------------------------- #
# 14-15. fingerprint
# --------------------------------------------------------------------------- #

def test_14_the_q_fingerprint_is_order_independent_and_hex_exact():
    s1, s2 = LearnerPersistentState(), LearnerPersistentState()
    edits = [Edit(Q, QAddress(state=ctx(t=t), z=1, m=0, a=0), float(t) + 0.5)
             for t in (1, 2, 3)]
    write(s1, edits)
    write(s2, list(reversed(edits)))
    assert fingerprint(s1) == fingerprint(s2), "insertion order must not matter"
    assert dict(s1.q_overrides) == dict(s2.q_overrides)

    # float.hex() is exact and distinguishes the two zeros, which repr of a rounded
    # decimal would not
    s3 = LearnerPersistentState()
    write(s3, [Edit(Q, Q0, 0.1)])
    assert float(0.1).hex() == "0x1.999999999999ap-4"
    from rfl_rebuild.b1.contract import _canon_q
    assert _canon_q(s3.q_overrides).endswith("|0x1.999999999999ap-4")

    # a Q write moves the fingerprint, and a reference-valued write does not
    s4 = LearnerPersistentState()
    fp_empty = fingerprint(s4)
    write(s4, [Edit(Q, Q0, VIEW.value(Q0))])          # canonicalises to a deletion
    assert fingerprint(s4) == fp_empty
    write(s4, [Edit(Q, Q0, VIEW.value(Q0) + 1.0)])
    assert fingerprint(s4) != fp_empty


def test_14b_the_ledger_canary_still_holds_with_a_q_store():
    """The canary with a scalar store in play, in both directions.

    Note what is *not* a no-op: writing the reference value over an existing override
    **deletes** the entry, so the store changes and the digest moves. The unchanged case
    is re-writing the value that is already there.
    """
    s = LearnerPersistentState()
    val = VIEW.value(Q0) + 1.0
    write(s, [Edit(Q, Q0, val)])
    fp_a = fingerprint(s)
    write(s, [Edit(Q, Q0, val)])           # same value again: the store is unchanged
    fp_b = fingerprint(s)
    assert fp_a == fp_b, "re-writing the same override must change nothing"
    UpdateLedger(receipts=(DecisionWriteReceipt(A, EVALUABLE_NOOP, False),),
                 fingerprint_pre=fp_a, fingerprint_post=fp_b
                 ).check_fingerprint_invariants()      # consistent, must not raise

    write(s, [Edit(Q, Q0, None)])          # a canonicalising write is a real change
    fp_c = fingerprint(s)
    assert fp_c != fp_b
    with pytest.raises(ProtocolError):
        UpdateLedger(receipts=(DecisionWriteReceipt(A, EVALUABLE_NOOP, False),),
                     fingerprint_pre=fp_b, fingerprint_post=fp_c
                     ).check_fingerprint_invariants()


# --------------------------------------------------------------------------- #
# 16. the empty Q store leaves the WORLD observables alone
# --------------------------------------------------------------------------- #

def test_16_driving_the_world_through_an_empty_q_store_changes_no_observation():
    r"""A77 §65.12's own distinction: this is **not** "the learner fingerprint bytes are
    unchanged" — they are not, the encoding moved. It is that an empty $Q_D^L$ produces
    the same *world* as the plain reference policy, row for row.
    """
    provider = LearnerPersistentState().snapshot().q_decision_provider(VIEW)
    n_worlds = 0
    for kappa in (0, 1):
        for phi in K.PHASE_DOMAIN:
            for z0 in K.option_ids():
                tape = K.SemanticTape(phase=phi, error_flag=0, cause_rank=0)
                baseline = K.rollout(
                    kappa=kappa, tape=tape,
                    command_provider=lambda s, c: SOL.best_action(s, c.z, c.m),
                    base_option=z0)
                through_q = K.rollout(kappa=kappa, tape=tape,
                                      command_provider=provider, base_option=z0)
                assert list(walk_transition(through_q, kappa, phi,
                                            through_q.option_in_force)) == \
                    list(walk_transition(baseline, kappa, phi,
                                         baseline.option_in_force)), \
                    f"the Q read path changed the world at kappa={kappa}, " \
                    f"phi={phi}, z0={z0}"
                n_worlds += 1
    assert n_worlds == 48


# --------------------------------------------------------------------------- #
# 17. the substrate carries no update-law semantics
# --------------------------------------------------------------------------- #

_FORBIDDEN_IN_SUBSTRATE = (
    "solve_reference", "FactualReturnWrite", "CounterfactualReturnWrite",
    "DualReturnWrite", "RestoreRow", "LocalOracleRestore", "G_t", "F_t",
    "build_target_envelope", "run_patch_law",
)

_LEARNER = ROOT / "src" / "rfl_rebuild" / "learner"


def _identifiers_and_imports(path: pathlib.Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    seen: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            seen.add(node.id)
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            seen.add(node.module or "")
            seen.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            seen.update(a.name for a in node.names)
    return seen


def test_17_the_learner_substrate_has_no_solver_or_update_law_reference():
    """A77 §65.4's rule enforced by the import graph, not by a comment.

    ``solve_reference`` must not be reachable from the substrate, and no update-law or
    target name may appear — step 4's objects, deliberately absent here.
    """
    files = sorted(_LEARNER.glob("*.py"))
    assert files, "the learner package must have modules"
    for path in files:
        seen = _identifiers_and_imports(path)
        bad = sorted(n for n in seen if any(f in n for f in _FORBIDDEN_IN_SUBSTRATE))
        assert not bad, f"{path.name} reaches for {bad}"


def test_17b_owner_q_is_the_address_projection_only():
    assert owner_Q(Q0) == DecisionAddress(state=ctx(), z=1, m=0)
    assert owner_Q(Q0) == owner_Q(Q1), "one context owns a whole row"
