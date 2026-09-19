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
    reach would change the fingerprint and clear ``healthy`` while being invisible."""
    s = LearnerPersistentState()
    for addr in (QAddress(state=ctx(), z=1, m=0, a=99),          # not an action id
                 QAddress(state=ctx(t=99), z=1, m=0, a=0)):      # no such context
        with pytest.raises(StoreTransactionError):
            write(s, [Edit(Q, addr, 1.0)])
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

def test_12_an_incomplete_reference_fails_at_construction_not_at_lookup():
    key = VIEW.domains[0]
    row = dict(VIEW.rows[key])
    row.pop(sorted(row)[0])
    with pytest.raises(ReferenceContractError) as ei:
        QReferenceView({key: row})
    assert "not total" in str(ei.value)


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
    key = VIEW.domains[0]
    for bad in (True, float("nan"), float("inf")):
        row = dict(VIEW.rows[key])
        row[sorted(row)[0]] = bad
        with pytest.raises(ReferenceContractError):
            QReferenceView({key: row})


def test_12d_the_reference_views_are_read_only():
    with pytest.raises(TypeError):
        VIEW.rows[VIEW.domains[0]] = {}
    with pytest.raises(TypeError):
        VIEW.rows[VIEW.domains[0]][0] = 1.0


# --------------------------------------------------------------------------- #
# 13. co-residence is refused before an adapter exists
# --------------------------------------------------------------------------- #

def test_13_p_patch_and_q_coresidence_fails_before_adapter_creation():
    s = LearnerPersistentState()
    write(s, [Edit(DECISION, A, K.UP)])
    write(s, [Edit(Q, Q0, VIEW.value(Q0) + 1.0)])
    snap = s.snapshot()
    assert snap.decision_overrides and snap.q_overrides
    with pytest.raises(LearnerStateError) as ei:
        snap.q_decision_provider(VIEW)
    assert "no priority" in str(ei.value)
    # the patch channel is likewise not a legal way to serve this state
    assert snap.healthy is False


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
