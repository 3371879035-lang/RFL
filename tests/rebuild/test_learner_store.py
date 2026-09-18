"""The learner persistent store substrate — persistence, safe reads, atomic writes.

No update law appears in this file. Where a test needs a defective store it is built
from low-level :class:`Edit` transactions, deliberately **not** through anything named
after a B1 primitive: a fixture called `SetAlternative` would be claiming a law exists
before the law has been specified.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.env import kernel as K  # noqa: E402
from rfl_rebuild.env.kernel import (  # noqa: E402
    ControllerSite, OptionViolation, SemanticTape, State,
)
from rfl_rebuild.learner.store import (  # noqa: E402
    CONTROLLER, DECISION, PROCESS, DecisionAddress, Edit, LearnerPersistentState,
    StoreTransactionError,
)

UP, DOWN, LEFT, RIGHT, WAIT = K.UP, K.DOWN, K.LEFT, K.RIGHT, K.WAIT
TAPE = SemanticTape(phase=0, error_flag=0, cause_rank=0)
Z_ALT = 2
START0 = State(x=K.START[0], y=K.START[1], t=0, kappa=0, phi=0)

# The fixtures must use an address where a LEGAL alternative exists. The `rush`
# option (z=0) has A_z = {RIGHT} at every step of its own episode, so nothing else is
# admissible there and every override would be illegal; `detour_upper` (z=1) reaches
# (1,2) at t=1 with A_z = all five actions and a command of RIGHT. Hard-coding the
# first option made four tests fail for the fixture's reason, not the store's.
DETOUR = 1
WITNESS_STATE = State(x=1, y=2, t=1, kappa=0, phi=0)
ADDR = DecisionAddress(state=WITNESS_STATE, z=DETOUR, m=0)
SITE = ControllerSite(state=WITNESS_STATE, cmd=UP)
LEGAL_ALT = DOWN


def base_provider(state, ctrl):
    """A stand-in for the reference policy, legal **by construction**.

    It returns the first admissible action, so it cannot escape its option on any
    trajectory. An earlier version returned RIGHT whenever RIGHT was admissible and
    WAIT otherwise; that is legal on the *unpatched* path but not on a path a patch
    has diverted, so the kernel correctly raised ``OptionViolation`` and two tests
    failed for the fixture's reason rather than the store's.
    """
    adm = K.option_actions(ctrl.z, ctrl, state)
    return adm[0]


def base_at(state, z, m):
    """What the stand-in base provider chooses at one context."""
    return base_provider(state, K.ControlState(z=z, m=m))


def run(state: LearnerPersistentState, base=base_provider, **kw) -> K.RolloutTrace:
    """One episode reading the state through its snapshot adapters."""
    snap = state.snapshot()
    args = dict(kappa=0, tape=TAPE, command_provider=snap.decision_provider(base),
                base_option=DETOUR, controller=snap.controller_mapping(),
                learner_process_commit=snap.process_commit_provider())
    args.update(kw)
    return K.rollout(**args)


def test_the_witness_really_admits_an_alternative():
    """Guard the fixture: if this drifts, the overrides stop being legal."""
    adm = K.option_actions(DETOUR, K.ControlState(z=DETOUR, m=0), WITNESS_STATE)
    assert LEGAL_ALT in adm, "the override value must be admissible"
    assert LEGAL_ALT != base_at(WITNESS_STATE, DETOUR, 0), "and must differ from base"
    assert SITE.cmd in adm, "the controller site's command must be admissible"
    assert LEGAL_ALT != SITE.cmd
    assert base_at(WITNESS_STATE, DETOUR, 0) == SITE.cmd, \
        "the kernel's command at the witness must be the site's cmd"


# --------------------------------------------------------------------------- #
# healthy representation
# --------------------------------------------------------------------------- #

def test_healthy_state_is_the_empty_state():
    s = LearnerPersistentState()
    assert s.healthy
    assert dict(s.decision_overrides) == {}
    assert dict(s.process_overrides) == {}
    assert dict(s.controller_overrides) == {}
    assert s.snapshot().healthy


def test_healthy_adapters_are_base_identity_identity():
    snap = LearnerPersistentState().snapshot()
    ctrl = K.ControlState(z=DETOUR, m=0)
    got = snap.decision_provider(base_provider)(WITNESS_STATE, ctrl)
    assert got == base_at(WITNESS_STATE, DETOUR, m=0)
    assert snap.process_commit_provider()(Z_ALT) == Z_ALT
    assert dict(snap.controller_mapping()) == {}
    trace = run(LearnerPersistentState())
    assert [s.a_cmd for s in trace.steps][:2] == [
        base_at(START0, DETOUR, 0), base_at(WITNESS_STATE, DETOUR, 0)]


# --------------------------------------------------------------------------- #
# snapshot immutability and clone isolation
# --------------------------------------------------------------------------- #

def test_snapshot_is_immutable_against_later_writes():
    s = LearnerPersistentState()
    before = s.snapshot()
    s.apply_transaction([Edit(DECISION, ADDR, LEGAL_ALT),
                         Edit(PROCESS, DETOUR, Z_ALT)])
    assert dict(before.decision_overrides) == {}, "old snapshot must not change"
    assert dict(before.process_overrides) == {}
    assert dict(s.snapshot().decision_overrides) == {ADDR: LEGAL_ALT}
    assert dict(s.snapshot().process_overrides) == {DETOUR: Z_ALT}


def test_clone_is_structurally_equal_but_independent():
    s = LearnerPersistentState()
    s.apply_transaction([Edit(DECISION, ADDR, LEGAL_ALT),
                         Edit(CONTROLLER, SITE, LEGAL_ALT)])
    c = s.clone()
    assert dict(c.decision_overrides) == dict(s.decision_overrides)
    assert dict(c.controller_overrides) == dict(s.controller_overrides)

    c.apply_transaction([Edit(DECISION, ADDR, None), Edit(CONTROLLER, SITE, None)])
    assert dict(s.decision_overrides) == {ADDR: LEGAL_ALT}, "original untouched"
    assert dict(s.controller_overrides) == {SITE: LEGAL_ALT}
    assert c.healthy


def test_clone_does_not_share_the_underlying_dicts():
    s = LearnerPersistentState()
    c = s.clone()
    c.apply_transaction([Edit(PROCESS, DETOUR, Z_ALT)])
    assert dict(s.process_overrides) == {}, "clone must not write through"


# --------------------------------------------------------------------------- #
# persistence across episodes
# --------------------------------------------------------------------------- #

def test_decision_patch_persists_across_two_episodes():
    s = LearnerPersistentState()
    s.apply_transaction([Edit(DECISION, ADDR, LEGAL_ALT)])
    for episode in (1, 2):
        trace = run(s)
        assert trace.steps[1].a_cmd == LEGAL_ALT, f"episode {episode}"


def test_process_override_persists_across_two_episodes():
    s = LearnerPersistentState()
    s.apply_transaction([Edit(PROCESS, DETOUR, Z_ALT)])
    for episode in (1, 2):
        assert run(s).option_in_force == Z_ALT, f"episode {episode}"


def test_controller_override_persists_across_two_episodes():
    s = LearnerPersistentState()
    s.apply_transaction([Edit(CONTROLLER, SITE, LEGAL_ALT)])
    for episode in (1, 2):
        trace = run(s)
        assert trace.steps[1].u == LEGAL_ALT, f"episode {episode}"
        assert trace.steps[1].a_realized == LEGAL_ALT, f"episode {episode}"


# --------------------------------------------------------------------------- #
# the decision patch shadows the base provider
# --------------------------------------------------------------------------- #

def test_a_decision_patch_hit_does_not_call_the_base_provider():
    calls: list[object] = []

    def spy(state, ctrl):
        calls.append(state)
        return base_provider(state, ctrl)

    s = LearnerPersistentState()
    s.apply_transaction([Edit(DECISION, ADDR, LEGAL_ALT)])
    trace = run(s, base=spy)
    assert trace.steps[1].a_cmd == LEGAL_ALT, "the patch must win"
    assert WITNESS_STATE not in calls, "a shadowed base provider must not be called"


def test_a_decision_patch_miss_falls_through_to_the_base_provider():
    calls: list[object] = []

    def spy(state, ctrl):
        calls.append(state)
        return base_provider(state, ctrl)

    s = LearnerPersistentState()
    elsewhere = DecisionAddress(state=State(x=3, y=2, t=5, kappa=0, phi=0),
                                z=DETOUR, m=0)
    s.apply_transaction([Edit(DECISION, elsewhere, WAIT)])
    trace = run(s, base=spy)
    assert trace.steps[1].a_cmd == base_at(WITNESS_STATE, DETOUR, 0)
    assert calls, "a miss must consult the base provider"


# --------------------------------------------------------------------------- #
# identity canonicalisation
# --------------------------------------------------------------------------- #

def test_process_identity_assignment_canonicalises_to_deletion():
    s = LearnerPersistentState()
    s.apply_transaction([Edit(PROCESS, DETOUR, Z_ALT)])
    assert dict(s.process_overrides) == {DETOUR: Z_ALT}
    s.apply_transaction([Edit(PROCESS, DETOUR, DETOUR)])
    assert dict(s.process_overrides) == {}, "identity must leave no entry behind"
    assert s.healthy


def test_controller_identity_assignment_canonicalises_to_deletion():
    s = LearnerPersistentState()
    s.apply_transaction([Edit(CONTROLLER, SITE, LEGAL_ALT)])
    assert dict(s.controller_overrides) == {SITE: LEGAL_ALT}
    s.apply_transaction([Edit(CONTROLLER, SITE, SITE.cmd)])
    assert dict(s.controller_overrides) == {}, "identity must leave no entry behind"
    assert s.healthy


def test_explicit_deletion_is_canonical_and_idempotent():
    s = LearnerPersistentState()
    s.apply_transaction([Edit(PROCESS, DETOUR, None), Edit(CONTROLLER, SITE, None),
                         Edit(DECISION, ADDR, None)])
    assert s.healthy, "deleting an absent override is a no-op, not an error"


# --------------------------------------------------------------------------- #
# atomicity
# --------------------------------------------------------------------------- #

def test_a_cross_store_transaction_with_one_bad_edit_changes_nothing():
    s = LearnerPersistentState()
    s.apply_transaction([Edit(PROCESS, DETOUR, Z_ALT),
                         Edit(CONTROLLER, SITE, LEGAL_ALT)])
    before = (dict(s.decision_overrides), dict(s.process_overrides),
              dict(s.controller_overrides))
    with pytest.raises(StoreTransactionError):
        # the decision edit is malformed; the other two are perfectly fine
        s.apply_transaction([Edit(DECISION, ADDR, 99),
                             Edit(PROCESS, Z_ALT, 3),
                             Edit(CONTROLLER, SITE, None)])
    after = (dict(s.decision_overrides), dict(s.process_overrides),
             dict(s.controller_overrides))
    assert after == before, "a rejected transaction must leave every store unchanged"


def test_duplicate_address_in_one_transaction_is_rejected():
    s = LearnerPersistentState()
    with pytest.raises(StoreTransactionError):
        s.apply_transaction([Edit(PROCESS, DETOUR, Z_ALT), Edit(PROCESS, DETOUR, 3)])
    assert s.healthy, "nothing may be committed"


def test_order_independence_of_non_conflicting_edits():
    seq = [Edit(DECISION, ADDR, LEGAL_ALT), Edit(PROCESS, DETOUR, Z_ALT),
           Edit(CONTROLLER, SITE, LEGAL_ALT)]
    a = LearnerPersistentState()
    a.apply_transaction(seq)
    b = LearnerPersistentState()
    b.apply_transaction(list(reversed(seq)))
    assert dict(a.decision_overrides) == dict(b.decision_overrides)
    assert dict(a.process_overrides) == dict(b.process_overrides)
    assert dict(a.controller_overrides) == dict(b.controller_overrides)


# --------------------------------------------------------------------------- #
# typing rejections — the substrate refuses to guess
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("edit", [
    Edit("nonsense", ADDR, LEGAL_ALT),
    Edit(DECISION, (WITNESS_STATE, DETOUR, 0), LEGAL_ALT),   # bare tuple, not typed key
    Edit(DECISION, ADDR, 99),                                # not an action id
    Edit(DECISION, ADDR, True),                              # compares equal to 1
    Edit(DECISION, ADDR, 1.0),                               # compares equal to 1
    Edit(PROCESS, "detour", Z_ALT),                          # not an int key
    Edit(PROCESS, True, Z_ALT),                              # bool is not an id
    Edit(PROCESS, DETOUR, 1.0),                              # not an int value
    Edit(CONTROLLER, (WITNESS_STATE, RIGHT), LEGAL_ALT),     # not a ControllerSite
    Edit(CONTROLLER, SITE, "UP"),                            # not an action id
])
def test_malformed_edits_are_rejected(edit):
    s = LearnerPersistentState()
    with pytest.raises(StoreTransactionError):
        s.apply_transaction([edit])
    assert s.healthy


def test_decision_address_is_hashable_and_typed():
    a = DecisionAddress(state=START0, z=DETOUR, m=0)
    b = DecisionAddress(state=START0, z=DETOUR, m=0)
    c = DecisionAddress(state=START0, z=DETOUR, m=1)
    assert a == b and hash(a) == hash(b)
    assert a != c
    assert len({a, b, c}) == 2


# --------------------------------------------------------------------------- #
# the decision channel's rejection type — an open question, recorded
# --------------------------------------------------------------------------- #

def test_an_illegal_decision_patch_is_rejected():
    """An illegal decision patch must not reach the world.

    NOTE the asymmetry, reported rather than silently fixed: this raises
    ``OptionViolation``, because a decision override enters the kernel as the
    ``policy`` source and the kernel's existing A36 check owns that path, whereas the
    ``C_P^L`` and ``C_X^L`` channels raise ``LearnerContractViolation``. Unifying the
    type would mean either touching the kernel's closed-version policy check or having
    the adapter pre-validate; both are semantic choices, so the current behaviour is
    asserted as-is and left for the next round.
    """
    s = LearnerPersistentState()
    # at START for `rush` the admissible set is exactly {RIGHT}, so WAIT is illegal
    bad = DecisionAddress(state=START0, z=0, m=0)
    s.apply_transaction([Edit(DECISION, bad, WAIT)])
    with pytest.raises(OptionViolation):
        K.rollout(kappa=0, tape=TAPE,
                  command_provider=s.snapshot().decision_provider(base_provider),
                  base_option=0)


# --------------------------------------------------------------------------- #
# scope guard
# --------------------------------------------------------------------------- #

def test_the_store_does_not_expose_any_update_law():
    import rfl_rebuild.learner.store as mod
    from rfl_rebuild.learner import __all__ as exported
    forbidden = ("DeleteFactualPatch", "SetAlternative", "LocalOracleRestore",
                 "FactualReturnWrite", "UpdateLedger", "APPLIED",
                 "EVALUABLE_NOOP", "NO_VALID_ALTERNATIVE", "PROTOCOL_ERROR")
    for name in forbidden:
        assert not hasattr(mod, name), f"{name} must not exist in the substrate"
        assert name not in exported, f"{name} must not be exported"
