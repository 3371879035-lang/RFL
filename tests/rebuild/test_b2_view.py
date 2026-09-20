r"""B2-1 — the measurement view and its constructor gate (A75 §62.10, A83 §71.1).

$$\boxed{\text{forbidden truth} \to \text{derived feature} \to \texttt{FutureConsequenceView}
\to \text{metric}}$$

These gates cover the four layers §62.10 lists — type boundary, AST/import allowlist,
constructor-flow, mutation power — and the four properties B2-1 must make mechanical:

$$\boxed{\text{truth-blind} + \text{arm-blind} + \text{pre-update} + \text{same object across
paired arms}}$$

Everything here is a **synthetic fixture**: a deterministic toy future rollout, no sampled run, no
seed, and no development-stage quantity. The one thing a fixture cannot stand in for is the
fabricated-feature mutation of `test_5`, which is A75 §62.10's named attack.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2 import (  # noqa: E402
    H_FORBIDDEN, SCENE_FORBIDDEN, VIEW_FIELDS, EvidenceOrigin, FutureConsequenceView,
    FutureConsequenceViewBuilder, FutureField, FutureRollout, assert_module_is_closed,
    require_learner_rollout,
)
from rfl_rebuild.learner.store import LearnerPersistentState  # noqa: E402

VIEW_MODULE = ROOT / "src" / "rfl_rebuild" / "b2" / "view.py"


def toy_rollout(horizon: int = 3, origin: EvidenceOrigin = EvidenceOrigin.LEARNER_FUTURE_ROLLOUT):
    """A deterministic toy future: this is a fixture, not a sampled run."""
    return FutureRollout(
        origin=origin,
        future_rewards=tuple(0.25 * (i + 1) for i in range(horizon)),
        future_outcomes=tuple(i % 2 for i in range(horizon)),
        future_trajectories=tuple((i, i + 1) for i in range(horizon)),
        future_actions=tuple(i % 3 for i in range(horizon)),
        future_observations=tuple((i, i * i) for i in range(horizon)),
        t_index=tuple(range(horizon)),
    )


def builder(horizon: int = 3) -> FutureConsequenceViewBuilder:
    return FutureConsequenceViewBuilder(lambda state: toy_rollout(horizon))


# --------------------------------------------------------------------------- #
# 1. the type boundary and the field surface
# --------------------------------------------------------------------------- #

def test_1_the_field_surface_is_closed():
    r"""A view carrying one more field is a **different view**, and the extra field is how a
    derived feature would arrive."""
    view = builder().build(LearnerPersistentState())
    assert set(view.fields) == set(VIEW_FIELDS)
    assert all(type(f) is FutureField for f in view.fields.values())
    for name in VIEW_FIELDS:
        assert view.fields[name].name == name
        assert type(view.fields[name].value) is tuple
    assert view.t_index == (0, 1, 2)
    # an extra field, a missing field and a renamed one are all refused
    legal = dict(view.fields)
    for broken in ({**legal, "fake_feature": 1},
                   {k: v for k, v in legal.items() if k != "future_rewards"},
                   {**{k: v for k, v in legal.items() if k != "future_actions"},
                    "actions": legal["future_actions"]}):
        with pytest.raises(ProtocolError) as ei:
            FutureConsequenceView(fields=broken, t_index=view.t_index)
        assert "frozen as" in str(ei.value)


def test_2_a_field_is_its_dependency_not_just_a_value():
    r"""A bare float can satisfy a type boundary and still be
    $1[\texttt{Decision}_t \in \Gamma_P^\ast]$ — the truth would have been consumed one step
    earlier by whoever computed it. So a value is admitted only together with the rollout it came
    from."""
    view = builder().build(LearnerPersistentState())
    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(fields={**view.fields, "future_rewards": 0.5}, t_index=(0,))
    assert "not FutureField" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(fields={**view.fields, "future_rewards": FutureField(
            name="future_outcomes", rollout=view.fields["future_rewards"].rollout, value=(1,))},
            t_index=(0,))
    assert "carries the name" in str(ei.value)
    # the only constructor projects a *declared* name off a vetted rollout
    with pytest.raises(ProtocolError) as ei:
        FutureField.from_rollout("fake_feature", toy_rollout())
    assert "not a declared view field" in str(ei.value)
    assert FutureField.from_rollout("future_rewards", toy_rollout()).value == (0.25, 0.5, 0.75)


# --------------------------------------------------------------------------- #
# 2. the constructor-flow layer: only the learner's own future rollout
# --------------------------------------------------------------------------- #

def test_3_only_the_learners_own_future_rollout_may_feed_the_view():
    r"""$$\mathrm{Deps}(F) \cap \mathcal H_{\text{forbidden}} = \varnothing$$ — enforced at the
    only door a field can come through."""
    for forbidden in (EvidenceOrigin.EVALUATOR_TRUTH, EvidenceOrigin.SCENE_ROUTING):
        with pytest.raises(ProtocolError) as ei:
            require_learner_rollout(toy_rollout(origin=forbidden))
        assert "only" in str(ei.value) and "may feed" in str(ei.value)
        leaking = FutureConsequenceViewBuilder(lambda s, o=forbidden: toy_rollout(origin=o))
        with pytest.raises(ProtocolError):
            leaking.build(LearnerPersistentState())
        with pytest.raises(ProtocolError):
            FutureField.from_rollout("future_rewards", toy_rollout(origin=forbidden))
    # a stand-in is not a rollout, and an untyped origin is not an origin
    class StandIn:
        origin = EvidenceOrigin.LEARNER_FUTURE_ROLLOUT

    with pytest.raises(ProtocolError) as ei:
        require_learner_rollout(StandIn())
    assert "not FutureRollout" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        require_learner_rollout(toy_rollout(origin="learner_future_rollout"))
    assert "not an EvidenceOrigin member" in str(ei.value), "the guard must not crash first"
    assert require_learner_rollout(toy_rollout()).origin is \
        EvidenceOrigin.LEARNER_FUTURE_ROLLOUT


# --------------------------------------------------------------------------- #
# 3. arm-blindness, pre-update, and the same object across paired arms
# --------------------------------------------------------------------------- #

def test_4_arm_blind_by_signature_and_pre_update_by_absence():
    r"""**Arm-blindness is a signature fact, not an intention**: a builder that *can* be told which
    arm it is in is one that may one day branch on it, so the parameter does not exist and the gate
    checks the parameter list.

    **Pre-update** here means what B2-1 can make mechanical: no update metadata enters the view.
    $U_{\text{unaffected}}$'s own pre-update construction belongs to B2-3 and is not decided by
    this arrow.
    """
    import inspect

    params = tuple(inspect.signature(builder().build).parameters)
    assert params == ("state",), params
    init_params = tuple(inspect.signature(FutureConsequenceViewBuilder.__init__).parameters)
    assert init_params == ("self", "future_rollout"), init_params
    # no member of either object names an arm, a stratum, a world/block id, or an update quantity
    members = set(FutureConsequenceView.__dataclass_fields__)
    assert members == {"fields", "t_index"}, members
    forbidden_tokens = set(H_FORBIDDEN) | set(SCENE_FORBIDDEN) | {
        "arm", "arm_id", "stratum", "n_scalar", "sum_abs_delta", "max_abs_delta",
        "fingerprint_pre", "fingerprint_post", "n_addresses", "delta_w", "ledger"}
    for cls in (FutureConsequenceView, FutureRollout, FutureField):
        assert not (set(cls.__dataclass_fields__) & forbidden_tokens), cls
    # the update's own object is not a learner state, so "what was written" cannot enter
    for not_a_state in (object(), {}, None, 1, "state", builder().build(LearnerPersistentState())):
        with pytest.raises(ProtocolError) as ei:
            builder().build(not_a_state)
        assert "built from a learner state" in str(ei.value)
    # the same learner-visible state gives the same view, whatever produced it
    state_a, state_b = LearnerPersistentState(), LearnerPersistentState()
    assert builder().build(state_a) == builder().build(state_b)


def test_5_the_fabricated_truth_feature_is_killed():
    r"""A75 §62.10's named mutation, and the only layer that makes the other three non-vacuous:

    $$fake\_feature = 1[\texttt{Decision}_t \in \Gamma_P^\ast]$$

    The gate must kill it. Every attempt below is a real route by which an already-computed
    truth-derived scalar would enter the view, and each is answered by a different layer —
    the field surface, the nominal field type, or the evidence origin.
    """
    gamma_P_star = {(0, 1), (1, 2), (2, 3)}                 # synthetic forbidden truth
    fake_feature = 1 if (0, 1) in gamma_P_star else 0       # the fabricated feature itself
    assert fake_feature == 1
    view = builder().build(LearnerPersistentState())
    legal = dict(view.fields)

    # route 1: as an extra field (the field-surface layer)
    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(fields={**legal, "fake_feature": fake_feature},
                              t_index=view.t_index)
    assert "frozen as" in str(ei.value)

    # route 2: inside a declared field, as a bare value (the nominal field type)
    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(fields={**legal, "future_rewards": fake_feature},
                              t_index=view.t_index)
    assert "not FutureField" in str(ei.value)

    # route 3: wrapped in a FutureField whose rollout is evaluator truth (the origin layer)
    with pytest.raises(ProtocolError):
        FutureField.from_rollout("future_rewards",
                                 toy_rollout(origin=EvidenceOrigin.EVALUATOR_TRUTH))

    # route 4: by rendering it through the builder, with the rollout's provenance mislabelled as
    # the learner's own -- the type says where the evidence came from, and this is what that is for
    smuggler = FutureConsequenceViewBuilder(
        lambda s: FutureRollout(origin=EvidenceOrigin.SCENE_ROUTING,
                                future_rewards=(fake_feature,), future_outcomes=(),
                                future_trajectories=(), future_actions=(),
                                future_observations=(), t_index=(0,)))
    with pytest.raises(ProtocolError) as ei:
        smuggler.build(LearnerPersistentState())
    assert "originates from" in str(ei.value)


# --------------------------------------------------------------------------- #
# 4. the AST / import allowlist layer, and the two views
# --------------------------------------------------------------------------- #

def test_6_the_ast_allowlist_layer_is_not_vacuous(tmp_path):
    r"""The layer checks this module's own source, and the check is shown to **bite**: a module that
    imports a non-allowlisted module, or reads a forbidden name through a local alias, is refused.
    Importing nothing forbidden while reading `truth.gamma_P_star` is the exact hole a pure
    import scan leaves open.
    """
    assert_module_is_closed(VIEW_MODULE)                      # the real module is closed
    leak_import = tmp_path / "leak_import.py"
    leak_import.write_text("from rfl_rebuild.method import credit\n", encoding="utf-8")
    with pytest.raises(ProtocolError) as ei:
        assert_module_is_closed(leak_import)
    assert "not on the allowlist" in str(ei.value)
    leak_name = tmp_path / "leak_name.py"
    leak_name.write_text("J_L = 1\nvalue = J_L\n", encoding="utf-8")
    with pytest.raises(ProtocolError) as ei:
        assert_module_is_closed(leak_name)
    assert "forbidden dependency set" in str(ei.value)
    leak_attr = tmp_path / "leak_attr.py"
    leak_attr.write_text("class T:\n    pass\n\n\ndef read(t):\n    return t.R_mech\n",
                         encoding="utf-8")
    with pytest.raises(ProtocolError) as ei:
        assert_module_is_closed(leak_attr)
    assert "forbidden dependency set" in str(ei.value)
    # the forbidden sets themselves are the frozen ones, and the two views stay separate objects
    assert H_FORBIDDEN == ("Z_fire", "J_L", "Gamma_T_star", "Gamma_P_star", "R_mech",
                           "R_rescue", "pi_credit")
    assert SCENE_FORBIDDEN == ("S_T_plus", "S_T_minus", "S_P_plus", "S_P_minus", "world_id",
                               "block_id")
    source = VIEW_MODULE.read_text(encoding="utf-8")
    assert "UpdateLedger" not in {*FutureConsequenceView.__dataclass_fields__}
    assert "class UpdateLedger" not in source


def test_7_the_view_is_deterministic_and_carries_the_declared_shapes():
    r"""Instrument first: the toy fixture must be reproducible before any gate can be trusted, and
    the shapes it produces are the ones `VIEW_FIELDS` declares."""
    state = LearnerPersistentState()
    first, second = builder().build(state), builder().build(state)
    assert first == second
    assert first.fields["future_rewards"].value == (0.25, 0.5, 0.75)
    assert first.fields["future_trajectories"].value == ((0, 1), (1, 2), (2, 3))
    assert builder(horizon=1).build(state).t_index == (0,)
    # no development-stage quantity is named by this arrow's module: the choices A83 71.4 keeps
    # open must not be silently fixed in code
    for token in ("N_eval", "N_train", "checkpoint", "Delta_min", "unaffected",
                  "Retention", "T_freeze"):
        assert token not in source_names(VIEW_MODULE), token


def source_names(path: pathlib.Path) -> set:
    """Every identifier the module mentions, so "absent" is checked rather than asserted."""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    return names
