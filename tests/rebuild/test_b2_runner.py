r"""B2-4 — the paired runner's instrument gates (eleven).

Each gate reads an observable: the recorder's event order, object identity, the fingerprints of the
two starting states, a signature, a dataclass field surface, or the registry a law is admitted from.
None reads an intention, and none is satisfied by a value-equal substitute.

Gate 10 is the **cross-architecture registry gate**: the ten gates exercised on the earlier draft
could not distinguish "a P law handed to an X arm" from an ordinary stand-in, so it is a separate
gate rather than a case folded into gate 9 -- the two holes are independent, and each has its own
mutation.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rfl_rebuild.b1.contract import fingerprint  # noqa: E402
from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b1.laws import P_LAWS, X_LAWS  # noqa: E402
from rfl_rebuild.b1.process import AssistedInput  # noqa: E402
from rfl_rebuild.b1.tier import Tier  # noqa: E402
from rfl_rebuild.b2.environment import KernelLearnerEnvironment, audited_modules  # noqa: E402
from rfl_rebuild.b2.runner import (  # noqa: E402
    ARCHITECTURES, EXOGENOUS_FIELDS, ArmSpec, ExogenousSetup, PairedRunner,
)
from rfl_rebuild.b2.unaffected import (  # noqa: E402
    REFINEMENTS,
    CreditedSite,
    UnaffectedSet as SceneUnaffectedSet,
)
from rfl_rebuild.b2.view import assert_modules_are_closed  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    PROCESS, Edit, LearnerPersistentState,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

RUNNER_MODULE = ROOT / "src" / "rfl_rebuild" / "b2" / "runner.py"
REFERENCE_VIEW = reference_view_from(solve_reference())
UNITS = ("ProcessCommit",)
GRID = (0, 1, 2, 3, 4, 5)


def exogenous(**overrides) -> ExogenousSetup:
    kwargs = dict(kappa=0, phi=0, tape=SemanticTape(phase=0, error_flag=0, cause_rank=0),
                  base_option=1, q_reference=REFERENCE_VIEW, checkpoints=GRID)
    kwargs.update(overrides)
    return ExogenousSetup(**kwargs)


def arm_defs():
    reference = next(x for x in P_LAWS
                     if type(x).__name__ == "NoWriteRef" and x.tier is Tier.L1_CORRECTIVE)
    treatment = next(x for x in P_LAWS if getattr(x, "name", "") == "P_id")
    return (ArmSpec("reference", "P", Tier.L1_CORRECTIVE, reference),
            ArmSpec("treatment", "P", Tier.L1_CORRECTIVE, treatment))


def runner(events=None, **overrides):
    kwargs = dict(
        environment_factory=lambda e: KernelLearnerEnvironment(
            kappa=e.kappa, phi=e.phi, tape=e.tape, base_option=e.base_option,
            q_reference=e.q_reference),
        refinement="eligible_all", q_reference=REFERENCE_VIEW, retention_form="RetentionAtH",
        retention_params={"H": 5},
        recorder=(lambda *a: events.append(a)) if events is not None else None)
    kwargs.update(overrides)
    return PairedRunner(**kwargs)


#: The pair's credited unit. A89 §77.4 defines the unaffected region relative to a credited site, so
#: the runner takes one explicitly rather than inferring it from a bare domain.
CREDIT = CreditedSite("P", 0)


def run(events=None, **overrides):
    return runner(events, **overrides).run(
        LearnerPersistentState(), arms=arm_defs(),
        evidence={"units": UNITS, "assisted": AssistedInput(1)}, exogenous=exogenous(),
        credited_site=CREDIT)


def names_of(events):
    return [e[0] for e in events]


# --------------------------------------------------------------------------- #
# temporal / pairing integrity
# --------------------------------------------------------------------------- #

def test_1_the_unaffected_set_is_built_before_the_first_arm_runs():
    r"""$$\boxed{\text{pre-update source} \to U_{\text{unaffected}} \to \text{arm updates}}$$"""
    events = []
    run(events)
    names = names_of(events)
    assert names[0] == "unaffected", names
    first_update = names.index("update_applied")
    assert names.index("unaffected") < first_update
    assert "future" not in names[:first_update], "a future existed before an arm ran"


def test_2_the_runner_owns_the_pre_update_material():
    r"""$$W_{\text{pre}} \to \text{traces} \to E(c) \to C_i(c)$$

    The runner derives the material itself, from the learner state it was handed -- not from a minted
    healthy state, and not from the superseded decision-context ontology.
    """
    params = tuple(inspect.signature(PairedRunner.run).parameters)
    assert params == ("self", "state", "arms", "evidence", "exogenous", "credited_site"), params
    built = runner().pre_update_source(LearnerPersistentState(), CREDIT)
    assert type(built) is SceneUnaffectedSet
    assert built.units and built.construction.endswith("@eligible_all")
    with pytest.raises(ProtocolError) as ei:
        runner().pre_update_source(object(), CREDIT)
    assert "learner state" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        runner().pre_update_source(LearnerPersistentState(), "P(0)")
    assert "credited unit" in str(ei.value)
    # the raw pre state, not a minted one: a state carrying an unrelated override gives different traces
    carried = LearnerPersistentState()
    carried.apply_transaction([Edit(PROCESS, 1, 2)])
    # The claim is about the *source*, not about one particular c: an override the learner carries
    # changes the episodes, and a region is a function of those episodes. Whether E(c) itself moves
    # depends on c, so the gate reads the traces.
    from rfl_rebuild.b2.unaffected import pre_update_traces, scene_domain

    # the probe must be a scene the carried override actually touches: it remaps the *proposal* 1,
    # so a base-option-0 episode is untouched by construction
    probe = next(s for s in sorted(scene_domain(), key=lambda s: s.key) if s.base_option == 1)
    with_carry = pre_update_traces(learner=carried, q_reference=REFERENCE_VIEW)
    assert with_carry.rows(probe) != pre_update_traces(learner=LearnerPersistentState(),
                                                       q_reference=REFERENCE_VIEW).rows(probe), (
        "a pre state carrying an override must produce different traces than the empty state")
    # and a well-typed credited unit outside the production extent is refused
    with pytest.raises(ProtocolError) as ei:
        runner().pre_update_source(LearnerPersistentState(),
                                  CreditedSite("X", __import__("rfl_rebuild.env.kernel",
                                                               fromlist=["ControllerSite"])
                                               .ControllerSite(state=__import__(
                                                   "rfl_rebuild.env.kernel",
                                                   fromlist=["State"]).State(x=1, y=1, t=0,
                                                                             kappa=0, phi=0),
                                                   cmd=0)))
    assert "production credited domain" in str(ei.value)


def test_3_the_arms_are_handed_one_object_not_two_equal_ones():
    r"""$$\boxed{u_{\text{ref}}\ \text{is}\ u_{\text{treat}}}$$"""
    import rfl_rebuild.b2.runner as R

    seen, events = [], []
    original = R.behavioral_collateral_scenes

    def spy(unaffected, *, values_pre, values_post):
        seen.append(id(unaffected))
        return original(unaffected, values_pre=values_pre, values_post=values_post)

    R.behavioral_collateral_scenes = spy
    try:
        run(events)
    finally:
        R.behavioral_collateral_scenes = original
    assert len(seen) == 2, "the metric runs once per arm"
    assert len(set(seen)) == 1, "the two arms' metrics saw different objects"
    built = [e[2] for e in events if e[0] == "unaffected"]
    assert len(built) == 1, "the set was constructed more than once"
    assert seen[0] == built[0], "the metric was handed a different object than the one built"


def observable_state() -> LearnerPersistentState:
    r"""A pre-state on which a writing arm's update changes the store."""
    state = LearnerPersistentState()
    state.apply_transaction([Edit(PROCESS, 1, 2)])
    return state


def writing_pair():
    r"""A pair in which **both** arms write, for the chain gate only.

    Why this fixture is necessary, measured rather than assumed: in the standard pair `arms[0]` is
    the reference `NoWriteRef`, which writes nothing, so a chain that routes the second clone through
    the first arm's post-state leaves every fingerprint identical -- `serial_arm_chain` came back
    NOT_A_GATE against a fresh state. A chain is an ordering defect, and it only becomes observable
    when the first arm's update is. The runner must not care whether a pair writes, so this is a
    legitimate instrument fixture rather than a special case in production.
    """
    treatment = next(x for x in P_LAWS if getattr(x, "name", "") == "P_id")
    return (ArmSpec("first", "P", Tier.L1_CORRECTIVE, treatment),
            ArmSpec("second", "P", Tier.L1_CORRECTIVE, treatment))


def test_4_the_arms_fork_from_one_pre_update_state():
    r"""Two independent clones of **one** state: a serial chain is not a pair.

    Checked on the **parent of each clone**, not on the resulting fingerprints, because a chain is a
    property of derivation rather than of content. Measured, after two failed attempts: with the
    standard pair `arms[0]` is a no-op, and with a writing pair `PId`'s identity write makes both
    arms converge again, so in both fixtures the chained clones end up content-equal and
    `serial_arm_chain` came back NOT_A_GATE. Recording what each clone was taken *from* is
    independent of what the arms later write.
    """
    parents, calls = [], []
    original = LearnerPersistentState.clone

    def spy(self):
        parents.append(fingerprint(self))
        calls.append(id(self))
        return original(self)

    state = observable_state()
    LearnerPersistentState.clone = spy
    try:
        record = runner().run(state, arms=writing_pair(),
                              evidence={"units": UNITS, "assisted": AssistedInput(1)},
                              exogenous=exogenous(), credited_site=CREDIT)
    finally:
        LearnerPersistentState.clone = original
    assert len(calls) == 2, f"expected one clone per arm, got {len(calls)}"
    assert set(parents) == {fingerprint(state)}, (
        "a clone was taken from a state that had already been updated: the arms are a serial chain, "
        f"not a pair (parents {parents!r}, input {fingerprint(state)!r})")
    assert len(set(record.fingerprints_pre.values())) == 1
    assert record.fingerprints_pre["first"] == record.fingerprints_pre["second"]


def test_5_the_paired_futures_share_one_exogenous_setup():
    r"""$$\boxed{\text{the arms differ in } \Delta W \text{ and in nothing else}}$$"""
    events = []
    record = run(events)
    setup_ids = [e[2] for e in events if e[0] == "exogenous"]
    assert len(setup_ids) == 2 and len(set(setup_ids)) == 1, setup_ids
    assert record.observations[0][1:] == record.observations[1][1:], record.observations
    assert record.observations[0][0] != record.observations[1][0]
    assert set(EXOGENOUS_FIELDS) == set(ExogenousSetup.__dataclass_fields__)
    with pytest.raises(TypeError):
        ExogenousSetup(kappa=0, phi=0, tape=None, base_option=1, q_reference=None,
                       checkpoints=GRID, world_id=7)
    with pytest.raises(ProtocolError) as ei:
        exogenous(checkpoints=())
    assert "no default schedule" in str(ei.value)


def test_6_no_future_exists_before_the_updates_are_applied():
    r"""$$\boxed{\text{plan/apply update} \to \text{future rollout} \to \text{metric}}$$"""
    events = []
    run(events)
    names = names_of(events)
    last_update = max(i for i, n in enumerate(names) if n == "update_applied")
    first_future = min(i for i, n in enumerate(names) if n == "future")
    assert first_future > last_update, names
    assert names.count("future") == 2 and names.count("update_applied") == 2


# --------------------------------------------------------------------------- #
# selection / dispatch integrity
# --------------------------------------------------------------------------- #

def test_7_the_candidate_names_and_horizons_are_required_and_never_defaulted():
    r"""No literal default may appear at the runner's own call sites."""
    for kwargs in ({"refinement": "", "retention_form": "RetentionAtH",
                    "retention_params": {"H": 5}},
                   {"refinement": "eligible_all", "retention_form": "",
                    "retention_params": {"H": 5}},
                   {"refinement": "eligible_all",
                    "retention_form": "RetentionAtH", "retention_params": {}},
                   {"refinement": "eligible_all",
                    "retention_form": "RetentionFraction", "retention_params": {"H": 5}},
                   {"refinement": "eligible_whatever", "retention_form": "RetentionAtH",
                    "retention_params": {"H": 5}}):
        with pytest.raises(ProtocolError):
            runner(**kwargs)
    tree = ast.parse(RUNNER_MODULE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and \
                node.func.id in ("select_form", "select_construction"):
            for arg in node.args:
                assert isinstance(arg, ast.Name), (
                    f"{node.func.id} is called with a literal at line {node.lineno}; the caller's "
                    "name must be passed through, not replaced by a hardcoded default")


def test_8_the_arms_are_nominal_and_dispatch_to_the_frozen_entry_points():
    r"""An arbitrary callable on the update side would re-open B2-1's hole where it matters most."""
    for bad in (lambda state: None, object(), "P_id", None):
        with pytest.raises(ProtocolError) as ei:
            ArmSpec("treatment", "P", Tier.L1_CORRECTIVE, bad)
        assert "not in the P registry" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        ArmSpec("treatment", "Z", Tier.L1_CORRECTIVE, P_LAWS[1])
    assert "not one of" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        ArmSpec("treatment", "P", Tier.L3_ORACLE, P_LAWS[1])       # wrong tier
    assert "declares" in str(ei.value)
    assert ARCHITECTURES == ("D_Q", "X", "P")
    assert set(ArmSpec.__dataclass_fields__) == {"name", "architecture", "tier", "law"}
    assert "apply" not in inspect.signature(PairedRunner.run).parameters
    assert "apply" not in inspect.signature(ArmSpec.__init__).parameters


def test_9_a_law_from_another_architecture_is_refused():
    r"""**The cross-architecture registry gate.**

    The ten gates exercised on the earlier draft could not tell "a P law handed to an X arm" from an
    ordinary stand-in: both are simply not in the registry. The holes are independent -- a stand-in
    is about *what a law is*, a foreign law is about *which architecture admits it* -- so this is a
    separate gate with its own mutation rather than a case folded into gate 8.
    """
    p_law = next(x for x in P_LAWS if getattr(x, "name", "") == "P_id")
    x_law = next(x for x in X_LAWS if getattr(x, "name", "") == "X_id")
    # The tier must MATCH the foreign law's own tier, or the tier check refuses the spec first and
    # the gate would be reporting a mechanism other than the one it names. Measured, not assumed:
    # with a mismatched tier the refusal message is about the tier, not about the registry.
    assert getattr(p_law, "tier", None) is Tier.L1_CORRECTIVE
    assert getattr(x_law, "tier", None) is Tier.L0_FACTUAL
    with pytest.raises(ProtocolError) as ei:
        ArmSpec("arm", "X", Tier.L1_CORRECTIVE, p_law)
    assert "not in the X registry" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        ArmSpec("arm", "P", Tier.L0_FACTUAL, x_law)
    assert "not in the P registry" in str(ei.value)
    # the two registries are genuinely disjoint, so the refusals are not one rule twice
    p_names = {getattr(x, "name", type(x).__name__) for x in P_LAWS}
    x_names = {getattr(x, "name", type(x).__name__) for x in X_LAWS}
    assert p_names & x_names == {"NoWrite", "LocalOracleRestore"}, (p_names, x_names)
    assert ArmSpec("arm", "X", Tier.L0_FACTUAL, x_law).architecture == "X"
    assert ArmSpec("arm", "P", Tier.L1_CORRECTIVE, p_law).architecture == "P"
    # and a mixed-architecture pair is refused at the runner, not only at the spec
    mixed = (ArmSpec("reference", "P", Tier.L1_CORRECTIVE,
                     next(x for x in P_LAWS if type(x).__name__ == "NoWriteRef"
                          and x.tier is Tier.L1_CORRECTIVE)),
             ArmSpec("treatment", "X", Tier.L0_FACTUAL, x_law))
    with pytest.raises(ProtocolError) as ei:
        runner().run(LearnerPersistentState(), arms=mixed,
                     evidence={"units": UNITS, "assisted": AssistedInput(1)},
                     exogenous=exogenous(), credited_site=CREDIT)
    assert "different architectures" in str(ei.value)


# --------------------------------------------------------------------------- #
# information boundary / outcome space
# --------------------------------------------------------------------------- #

def test_10_the_record_keeps_three_dimensions_and_no_composite():
    r"""$$\boxed{Y^{\text{future}} = \{\text{FutureUtility},\ \text{Collateral},\
    \text{Retention}\}}$$, with the cost view **beside** them."""
    record = run()
    assert set(record.__dataclass_fields__) == {
        "arm_names", "architecture", "unaffected_construction", "unaffected_size", "retention_form",
        "future_utility", "collateral", "retention", "ledgers", "fingerprints_pre", "observations"}
    assert record.unaffected_size > 0 and "@eligible_all" in record.unaffected_construction
    assert REFINEMENTS[0] == "eligible_all"
    forbidden = {"score", "weighted_score", "overall_utility", "composite", "primary", "verdict",
                 "p_value", "rmst", "holm", "bootstrap", "conclusion"}
    assert not (set(record.__dataclass_fields__) & forbidden)
    assert set(record.future_utility) == set(record.arm_names)
    assert set(record.retention) == set(record.arm_names)
    assert set(record.collateral) == set(record.arm_names), (
        "collateral is per arm: V_unaffected,pre - V_unaffected,post(a), not a difference between arms")
    assert "UpdateLedger" not in {type(v).__name__ for v in record.future_utility.values()}
    names = _module_names(RUNNER_MODULE)
    assert not (names & {"rmst", "RMST", "holm", "bootstrap", "verdict", "conclusion", "p_value"})


def test_11b_the_two_arms_share_one_pre_measurement():
    r"""A85 §73.2.2: the two arms' pre values are **one measurement**, not two that happen to agree.

    $$M_{\text{pre}} = \text{measure}(W_{\text{pre}}, C) \quad\text{once}$$
    $$\text{Collateral}_a = \text{BehavioralCollateral}(C, M_{\text{pre}}, M_{\text{post},a})$$

    The gate reads object identity: three measurements (one pre, one per arm) and a single pre-map
    object handed to both collateral computations.
    """
    import rfl_rebuild.b2.runner as R

    maps, pre_ids = [], []
    original_map, original_bc = R.measure_scene_map, R.behavioral_collateral_scenes

    def spy_map(learner, units, *, q_reference):
        out = original_map(learner, units, q_reference=q_reference)
        maps.append(id(out))
        return out

    def spy_bc(unaffected, *, values_pre, values_post):
        pre_ids.append(id(values_pre))
        return original_bc(unaffected, values_pre=values_pre, values_post=values_post)

    R.measure_scene_map, R.behavioral_collateral_scenes = spy_map, spy_bc
    try:
        record = run()
    finally:
        R.measure_scene_map, R.behavioral_collateral_scenes = original_map, original_bc
    assert len(maps) == 3, f"expected one pre map and one per arm, got {len(maps)}"
    assert len(set(pre_ids)) == 1 and pre_ids[0] == maps[0], (
        "both arms must be handed the same pre-map object that was measured first")
    assert set(record.collateral) == set(record.arm_names)


def test_11c_a_dq_pair_runs_through_the_b1_entry_point():
    r"""A85 §73.2.5: the measurement interface is behaviourally load-bearing for $D_Q$ too.

    B1 already ships `run_dq_law` and `DQ_LAWS`; the runner dispatches to them rather than inventing
    $D_Q$ semantics, and this gate is what says the third architecture is actually reachable.
    """
    from rfl_rebuild.b1.laws import DQ_LAWS
    from rfl_rebuild.b2.unaffected import credited_domain, pre_update_traces, scene_domain

    traces = pre_update_traces(learner=LearnerPersistentState(), q_reference=REFERENCE_VIEW)
    credit = credited_domain("D_Q", traces)[0]
    reference = next(x for x in DQ_LAWS
                     if type(x).__name__ == "NoWriteRef" and x.tier is Tier.L3_ORACLE)
    treatment = next(x for x in DQ_LAWS if getattr(x, "name", None) == "LocalOracleRestore")
    arms = (ArmSpec("reference", "D_Q", Tier.L3_ORACLE, reference),
            ArmSpec("treatment", "D_Q", Tier.L3_ORACLE, treatment))
    scene = min(scene_domain(), key=lambda s: s.key)
    record = runner().run(
        LearnerPersistentState(), arms=arms,
        evidence={"addresses": (credit.address,), "rows": traces.rows(scene)},
        exogenous=exogenous(), credited_site=credit)
    assert record.architecture == "D_Q"
    assert set(record.collateral) == {"reference", "treatment"}
    assert record.unaffected_size > 0


def test_11_the_runner_is_in_the_audited_production_chain():
    modules = audited_modules(ROOT / "src")
    assert "runner.py" in {p.name for p in modules}
    assert_modules_are_closed(modules)


def _module_names(path: pathlib.Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.arg):
            out.add(node.arg)
    return out
