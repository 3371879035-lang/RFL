r"""B2-1 + B2-2a — the measurement view, its audited producer, and the gate layers.

$$\boxed{\text{forbidden truth} \to \text{derived feature} \to \texttt{FutureConsequenceView}
\to \text{metric}}$$

The closure is on the **dependencies of the features**, and after B2-2a it covers the whole chain
rather than one module:

$$\boxed{\text{post-update learner state} \to \text{audited producer} \to
\texttt{FutureRollout} \to \texttt{FutureConsequenceViewBuilder}}$$

| layer | mechanism |
|---|---|
| type boundary | a view field is a `FutureField`, not a bare value |
| AST / import allowlist | `assert_modules_are_closed` over **view + producer**, plus the test-only fixture module being unreachable from production |
| constructor-flow | the rollout is **sealed** (only the audited mint can build one) and the view **re-derives** every payload and the time index from that one rollout |
| mutation power | `test_6` fabricates $1[\texttt{Decision}_t \in \Gamma_P^\ast]$ and requires the other three to kill it, along five routes |

**What this arrow does *not* claim.** `same object across paired arms` is **not** a B2-1 property:
A79 requires $U_{\text{unaffected}}$ to be one object shared by both paired arms, and that object
belongs to B2-3/B2-4. Two arms' post-update states legitimately differ, so their future views may
differ too — that difference is what B2 measures. `test_9`'s `view_a == view_b` is therefore a
**deterministic fixture check**, and calling it an A79 same-object gate would be a false claim.

Everything here is a synthetic fixture: a deterministic toy environment, no sampled run, no seed,
and no development-stage quantity.
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
    FutureConsequenceViewBuilder, FutureField, FutureRollout, FutureRolloutProducer,
    LearnerEnvironment, assert_module_is_closed, assert_modules_are_closed,
    require_learner_rollout,
)
# The mint capability is private and audited: production modules may not hold it. A hostile gate
# MUST be able to reach it anyway, or it could not build the objects it exists to attack -- so the
# escalation below is deliberate, and labelled as an escalation rather than presented as a
# production route.
from rfl_rebuild.b2.producer import (  # noqa: E402
    ENVIRONMENT_INTERFACE, _ROLLOUT_SEAL, _mint_rollout,
)
from rfl_rebuild.b2.testing import toy_environment, toy_records, toy_rollout  # noqa: E402
from rfl_rebuild.learner.store import LearnerPersistentState  # noqa: E402

VIEW_MODULE = ROOT / "src" / "rfl_rebuild" / "b2" / "view.py"
PRODUCER_MODULE = ROOT / "src" / "rfl_rebuild" / "b2" / "producer.py"
PRODUCTION_MODULES = (VIEW_MODULE, PRODUCER_MODULE)


def builder(horizon: int = 3) -> FutureConsequenceViewBuilder:
    return FutureConsequenceViewBuilder(FutureRolloutProducer(toy_environment(horizon)))


def clean_view(horizon: int = 3) -> FutureConsequenceView:
    return builder(horizon).build(LearnerPersistentState())


def test_1_the_field_surface_is_closed():
    r"""A view carrying one more field is a **different view**, and the extra field is how a
    derived feature would arrive."""
    view = clean_view()
    assert set(view.fields) == set(VIEW_FIELDS)
    assert all(type(f) is FutureField for f in view.fields.values())
    for name in VIEW_FIELDS:
        assert view.fields[name].name == name
        assert type(view.fields[name].value) is tuple
    assert view.t_index == (0, 1, 2)
    legal = dict(view.fields)
    for broken in ({**legal, "fake_feature": 1},
                   {k: v for k, v in legal.items() if k != "future_rewards"},
                   {**{k: v for k, v in legal.items() if k != "future_actions"},
                    "actions": legal["future_actions"]}):
        with pytest.raises(ProtocolError) as ei:
            FutureConsequenceView(fields=broken, t_index=view.t_index)
        assert "frozen as" in str(ei.value)


def test_2_the_payload_must_be_the_projection_of_its_own_rollout():
    r"""A **clean rollout with a forged payload** was B2-1's most dangerous unclosed route: the
    shell is legitimate, every provenance check passes, and the truth-derived number travels
    inside it. The view therefore re-derives the projection instead of trusting the field."""
    view = clean_view()
    rollout = view.fields["future_rewards"].rollout
    assert type(rollout) is FutureRollout
    forged = FutureField(name="future_rewards", rollout=rollout, value=(1,))
    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(fields={**view.fields, "future_rewards": forged},
                              t_index=view.t_index)
    assert "not the projection of its own rollout" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(fields={**view.fields, "future_rewards": (1,)}, t_index=(0, 1, 2))
    assert "not FutureField" in str(ei.value)
    assert FutureField.from_rollout("future_rewards", rollout).value == (0.25, 0.5, 0.75)


def test_3_the_rollout_is_sealed_and_the_view_is_one_future():
    r"""**Provenance is a mint, not a label.** A directly constructed rollout reports where it came
    from; the seal removes that public route. Two further routes are closed in the same place:
    fields drawn from **several** futures, and a `t_index` supplied separately from the rollout it
    is supposed to belong to."""
    with pytest.raises(ProtocolError) as ei:
        FutureRollout(_seal=object(), origin=EvidenceOrigin.LEARNER_FUTURE_ROLLOUT,
                      future_rewards=(), future_outcomes=(), future_trajectories=(),
                      future_actions=(), future_observations=(), t_index=())
    assert "may only be minted" in str(ei.value)
    assert toy_rollout()._seal is _ROLLOUT_SEAL
    view = clean_view()
    clean = view.fields["future_rewards"].rollout
    records = tuple(getattr(clean, name) for name in VIEW_FIELDS)
    other_records = (((99.0,) + tuple(records[0][1:])),) + records[1:]
    other = _mint_rollout(EvidenceOrigin.LEARNER_FUTURE_ROLLOUT, other_records, clean.t_index)
    mixed = {**view.fields, "future_rewards": FutureField.from_rollout("future_rewards", other)}
    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(fields=mixed, t_index=view.t_index)
    assert "more than one rollout" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(fields=view.fields, t_index=(99,))
    assert "not its rollout's t_index" in str(ei.value)


def test_4_the_builder_consumes_the_audited_producer_not_a_callable():
    r"""B2-1 took `Callable`, so an injected lambda could close over forbidden truth and return an
    object claiming the learner's origin while the audited module's AST scan saw nothing. The
    builder now refuses everything that is not the nominal producer, and the producer's own input
    surface is a declared interface rather than whatever the caller passes."""
    calls = []

    def arbitrary(state):
        calls.append(state)
        return toy_rollout()

    for not_a_producer in (arbitrary, lambda: toy_rollout(), None, object(), toy_environment(),
                           FutureRolloutProducer):
        with pytest.raises(ProtocolError) as ei:
            FutureConsequenceViewBuilder(not_a_producer)
        assert "not FutureRolloutProducer" in str(ei.value)
    assert calls == [], "the injected callable must never be reached"

    class StandInEnvironment:
        def future_records(self, state):
            return toy_records()

    with pytest.raises(ProtocolError) as ei:
        FutureRolloutProducer(StandInEnvironment())
    assert "not a LearnerEnvironment" in str(ei.value)
    import inspect

    assert ENVIRONMENT_INTERFACE == ("future_records",)
    params = tuple(inspect.signature(FutureRolloutProducer(toy_environment()).produce).parameters)
    assert params == ("state",), params
    init_params = tuple(inspect.signature(FutureRolloutProducer.__init__).parameters)
    assert init_params == ("self", "environment"), init_params
    for not_a_state in (object(), {}, None, 1, "state", clean_view()):
        with pytest.raises(ProtocolError) as ei:
            FutureRolloutProducer(toy_environment()).produce(not_a_state)
        assert "produced from a learner state" in str(ei.value)

    class ShortEnvironment(LearnerEnvironment):
        def future_records(self, state):
            return ((), ())

    with pytest.raises(ProtocolError) as ei:
        FutureRolloutProducer(ShortEnvironment()).produce(LearnerPersistentState())
    assert "5-tuple" in str(ei.value)

    class RaggedEnvironment(LearnerEnvironment):
        def future_records(self, state):
            return ((), (), (1,), (), ())

    with pytest.raises(ProtocolError) as ei:
        FutureRolloutProducer(RaggedEnvironment()).produce(LearnerPersistentState())
    assert "must agree" in str(ei.value)


def test_5_only_the_learners_own_future_rollout_may_feed_the_view():
    r"""The dependency closure, enforced at the one door a field can come through."""
    for forbidden in (EvidenceOrigin.EVALUATOR_TRUTH, EvidenceOrigin.SCENE_ROUTING):
        with pytest.raises(ProtocolError) as ei:
            require_learner_rollout(toy_rollout(origin=forbidden))
        assert "may feed" in str(ei.value)
    # The fixture mint has its own type check, so a string origin would never reach the guard
    # below it. The rollout is therefore constructed directly with the real seal, which isolates
    # `require_learner_rollout`'s own nominal check -- otherwise this gate would pass while the
    # guard it names was inert.
    with pytest.raises(ProtocolError) as ei:
        require_learner_rollout(FutureRollout(_seal=_ROLLOUT_SEAL,
                                              origin="learner_future_rollout",
                                              future_rewards=(), future_outcomes=(),
                                              future_trajectories=(), future_actions=(),
                                              future_observations=(), t_index=()))
    assert "not an EvidenceOrigin member" in str(ei.value)
    with pytest.raises(ProtocolError):                      # and the mint refuses it too
        toy_rollout(origin="learner_future_rollout")

    class StandIn:
        origin = EvidenceOrigin.LEARNER_FUTURE_ROLLOUT

    with pytest.raises(ProtocolError) as ei:
        require_learner_rollout(StandIn())
    assert "not FutureRollout" in str(ei.value)
    assert require_learner_rollout(toy_rollout()).origin is \
        EvidenceOrigin.LEARNER_FUTURE_ROLLOUT


def tmp_path_of_this_test() -> pathlib.Path:
    import tempfile

    return pathlib.Path(tempfile.mkdtemp(prefix="b2_leak_"))


def test_6_the_fabricated_truth_feature_is_killed():
    r"""A75 62.10's named mutation, along five routes. Routes 3 and 4 are the ones B2-1 left open --
    a legitimate provenance shell around a truth-derived payload -- which is why they are the
    point of B2-2a rather than a footnote."""
    gamma_P_star = {(0, 1), (1, 2), (2, 3)}
    fake_feature = 1 if (0, 1) in gamma_P_star else 0
    assert fake_feature == 1
    view = clean_view()
    rollout = view.fields["future_rewards"].rollout
    legal = dict(view.fields)

    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(fields={**legal, "fake_feature": fake_feature},
                              t_index=view.t_index)
    assert "frozen as" in str(ei.value)

    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(fields={**legal, "future_rewards": fake_feature},
                              t_index=view.t_index)
    assert "not FutureField" in str(ei.value)

    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(
            fields={**legal, "future_rewards": FutureField(name="future_rewards", rollout=rollout,
                                                           value=(fake_feature,))},
            t_index=view.t_index)
    assert "not the projection of its own rollout" in str(ei.value)

    with pytest.raises(ProtocolError) as ei:
        FutureConsequenceView(fields=legal, t_index=(fake_feature,))
    assert "not its rollout's t_index" in str(ei.value)

    # Route 5 is the residual one, and it is stated rather than hidden: a *nominal* environment
    # whose records are themselves truth-derived is expressible, because no type can inspect where
    # a record came from. What closes it is that the production environment implementation joins
    # the same audit as the producer -- so the layer that will have to go red is the AST one, and
    # this gate shows it bites on the producer today.
    leak = tmp_path_of_this_test() / "producer_leak.py"
    leak.write_text("Gamma_P_star = 1\nvalue = Gamma_P_star\n", encoding="utf-8")
    with pytest.raises(ProtocolError) as ei:
        assert_modules_are_closed([leak])
    assert "forbidden dependency set" in str(ei.value)


def test_7_the_ast_allowlist_layer_covers_the_chain_and_is_not_vacuous(tmp_path):
    r"""The layer scans **producer and view together**, refuses a production module that imports the
    test-only fixture mint, and is shown to bite on a module that imports a non-allowlisted module
    or reads a forbidden name through a local alias."""
    assert_modules_are_closed(PRODUCTION_MODULES)
    assert_module_is_closed(VIEW_MODULE)
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
    leak_attr.write_text("def read(t):\n    return t.R_mech\n", encoding="utf-8")
    with pytest.raises(ProtocolError) as ei:
        assert_module_is_closed(leak_attr)
    assert "forbidden dependency set" in str(ei.value)
    leak_fixture = tmp_path / "leak_fixture.py"
    leak_fixture.write_text("from rfl_rebuild.b2 import testing\n", encoding="utf-8")
    with pytest.raises(ProtocolError) as ei:
        assert_modules_are_closed([leak_fixture])
    # Only the diagnostic reason matters; tmp_path's counter is not gate evidence.
    fixture_reason = str(ei.value).replace(str(leak_fixture), "<fixture>")
    assert "test-only fixture module" in fixture_reason
    assert H_FORBIDDEN == ("Z_fire", "J_L", "Gamma_T_star", "Gamma_P_star", "R_mech",
                           "R_rescue", "pi_credit")
    assert SCENE_FORBIDDEN == ("S_T_plus", "S_T_minus", "S_P_plus", "S_P_minus", "world_id",
                               "block_id")
    # ...and the production modules do not import the fixture mint. Checked through the AST
    # rather than by scanning text: a comment that mentions the pattern is not an import, and a
    # textual probe would fail on prose -- the same reason this layer is an AST one.
    import ast as _ast

    for path in PRODUCTION_MODULES:
        tree = _ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, _ast.ImportFrom):
                imported |= {f"{node.module or ''}.{a.name}" for a in node.names}
        assert not [n for n in imported if n.startswith("rfl_rebuild.b2.testing")], path


def test_8_arm_blind_by_interface_and_pre_update_by_absence():
    r"""**Arm-blindness is an interface fact**: a builder that *can* be told which arm it is in is
    one that may one day branch on it, so the parameter does not exist and the gate reads the
    parameter list. **Pre-update** here means no update metadata enters the view.
    $U_{\text{unaffected}}$'s own pre-update construction and its same-object identity across
    paired arms belong to B2-3/B2-4, and this gate deliberately does not claim them."""
    import inspect

    params = tuple(inspect.signature(builder().build).parameters)
    assert params == ("state",), params
    init_params = tuple(inspect.signature(FutureConsequenceViewBuilder.__init__).parameters)
    assert init_params == ("self", "producer"), init_params
    assert set(FutureConsequenceView.__dataclass_fields__) == {"fields", "t_index"}
    forbidden_tokens = set(H_FORBIDDEN) | set(SCENE_FORBIDDEN) | {
        "arm", "arm_id", "stratum", "n_scalar", "sum_abs_delta", "max_abs_delta",
        "fingerprint_pre", "fingerprint_post", "n_addresses", "delta_w", "ledger",
        "unaffected", "retention"}
    for cls in (FutureConsequenceView, FutureRollout, FutureField):
        assert not (set(cls.__dataclass_fields__) & forbidden_tokens), cls
    for not_a_state in (object(), {}, None, 1, "state", clean_view()):
        with pytest.raises(ProtocolError) as ei:
            builder().build(not_a_state)
        assert "built from a learner state" in str(ei.value)


def test_9_the_fixture_is_deterministic_and_no_development_quantity_is_named():
    r"""A **fixture check**, not an A79 gate: identical learner-visible states give identical views,
    so a later red gate is a real failure rather than fixture noise. It is explicitly *not* the
    same-object property, which belongs to $U_{\text{unaffected}}$ and to B2-3/B2-4."""
    state = LearnerPersistentState()
    assert builder().build(state) == builder().build(state)
    view = clean_view()
    assert view.fields["future_rewards"].value == (0.25, 0.5, 0.75)
    assert view.fields["future_trajectories"].value == ((0, 1), (1, 2), (2, 3))
    assert builder(horizon=1).build(state).t_index == (0,)
    names = set()
    for path in PRODUCTION_MODULES:
        names |= source_names(path)
    for token in ("N_eval", "N_train", "checkpoint", "Delta_min", "unaffected", "Retention",
                  "T_freeze", "RMST", "DeficitAUC"):
        assert token not in names, token


def source_names(path: pathlib.Path) -> set:
    """Every identifier a module mentions, so "absent" is checked rather than asserted."""
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


def test_10_the_mint_capability_has_exactly_one_holder_in_the_production_graph(tmp_path):
    r"""$$\boxed{\text{inside the audited production graph, only } \texttt{producer.py} \text{ may
    mint}}$$

    B2-2a's own gates could not see the hole this closes: `rollout_seal_check_removed` asks whether
    a *wrong* seal is refused, while the defect was that the *right* seal was a public API. So this
    gate asks the ownership question in both directions.

    **The escalation is real and it is labelled.** A hostile gate must be able to build the object
    it attacks, so it reaches the private path deliberately — and what it then shows is the honest
    boundary: a payload that was minted with a valid seal is *not* detectable downstream. No type
    can tell where a float came from, and the view does not pretend to. The boundary is the mint
    owner plus the audited environment.
    """
    import ast as _ast

    # The audited production chain itself, first: without this the gate would only ever inspect
    # synthetic leaks and would pass while a real production module held the capability.
    assert_modules_are_closed(PRODUCTION_MODULES)
    package = __import__("rfl_rebuild.b2", fromlist=["__all__"])
    for name in ("ROLLOUT_SEAL", "mint_rollout", "_ROLLOUT_SEAL", "_mint_rollout"):
        assert name not in package.__all__, f"{name} is exported by the package"
        assert not hasattr(package, name), f"{name} is reachable from the package"
    for name in ("_ROLLOUT_SEAL", "_mint_rollout"):
        assert name not in PRODUCER_MODULE.read_text(encoding="utf-8").split("__all__ = [")[1] \
            .split("]")[0], f"{name} is in producer.__all__"

    # (a) the escalation: a valid seal and a truth-derived payload, minted through the private path
    gamma_P_star = {(0, 1)}
    fake_feature = 1 if (0, 1) in gamma_P_star else 0
    forged = _mint_rollout(EvidenceOrigin.LEARNER_FUTURE_ROLLOUT,
                           ((fake_feature,), (0,), ((0, 1),), (0,), ((0, 0),)), (0,))
    assert type(forged) is FutureRollout
    hostile = FutureConsequenceViewBuilder(FutureRolloutProducer(
        _EnvironmentReturning(forged))).build(LearnerPersistentState())
    assert hostile.fields["future_rewards"].value == (fake_feature,), (
        "the downstream layers CANNOT detect an already-minted truth payload, and this gate says "
        "so rather than claiming otherwise")

    # (b) production reachability: the audit refuses any other production module taking the
    # capability, whether by import, by attribute, or by a bare load
    for source, why in (
        ("from rfl_rebuild.b2.producer import _mint_rollout\n", "an import"),
        ("import rfl_rebuild.b2.producer as p\nx = p._ROLLOUT_SEAL\n", "an attribute load"),
        ("x = _mint_rollout\n", "a bare load"),
    ):
        leak = tmp_path / f"leak_{abs(hash(source)) % 1000}.py"
        leak.write_text(source, encoding="utf-8")
        with pytest.raises(ProtocolError) as ei:
            assert_modules_are_closed([leak])
        assert "mint capability" in str(ei.value), why
    # the ownership rule is data, so the gate reads the same list the check enforces
    from rfl_rebuild.b2.view import CAPABILITY_OWNERS

    assert set(CAPABILITY_OWNERS) == {"_mint_rollout", "_ROLLOUT_SEAL"}
    assert set(CAPABILITY_OWNERS.values()) == {"producer.py"}
    # only the owner (and the labelled test-only fixture module) mentions the capability at all
    for path in PRODUCTION_MODULES:
        tree = _ast.parse(path.read_text(encoding="utf-8"))
        if path.name == "producer.py":
            continue
        assert not [n for n in _ast.walk(tree)
                    if isinstance(n, _ast.Name) and n.id in CAPABILITY_OWNERS]


class _EnvironmentReturning(LearnerEnvironment):
    """A labelled hostile environment: it returns records that were already minted elsewhere."""

    __slots__ = ("_rollout",)

    def __init__(self, rollout):
        self._rollout = rollout

    def future_records(self, state):
        return tuple(getattr(self._rollout, name) for name in VIEW_FIELDS)
