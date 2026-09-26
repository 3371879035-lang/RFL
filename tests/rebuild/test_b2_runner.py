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

from fractions import Fraction  # noqa: E402

from rfl_rebuild.b1.contract import fingerprint  # noqa: E402
from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b1.laws import P_LAWS, X_LAWS  # noqa: E402
from rfl_rebuild.b1.process import AssistedInput  # noqa: E402
from rfl_rebuild.b1.tier import Tier  # noqa: E402
from rfl_rebuild.b2.environment import audited_modules  # noqa: E402
from rfl_rebuild.b2.runner import (  # noqa: E402
    ARCHITECTURES, ArmSpec, PairedRunner,
)
import rfl_rebuild.b2.runner as runner_module  # noqa: E402
from rfl_rebuild.b2.training import FutureTrainingProtocol, pre_level  # noqa: E402
from rfl_rebuild.b2.unaffected import (  # noqa: E402
    REFINEMENTS,
    CreditedSite,
    UnaffectedSet as SceneUnaffectedSet,
    scene_domain,
)
from rfl_rebuild.b2.view import assert_modules_are_closed  # noqa: E402
from rfl_rebuild.env.kernel import ControlState, SemanticTape, option_actions  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import (  # noqa: E402
    PROCESS, Q, Edit, LearnerPersistentState,
)
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

RUNNER_MODULE = ROOT / "src" / "rfl_rebuild" / "b2" / "runner.py"
#: The frozen solve and the one artifact every dimension reads, in this file's fixture.
SOLUTION = solve_reference()
REFERENCE_VIEW = reference_view_from(SOLUTION)
UNITS = ("ProcessCommit",)
GRID = (0, 1, 2, 3, 4, 5)


def arm_defs():
    reference = next(x for x in P_LAWS
                     if type(x).__name__ == "NoWriteRef" and x.tier is Tier.L1_CORRECTIVE)
    treatment = next(x for x in P_LAWS if getattr(x, "name", "") == "P_id")
    return (ArmSpec("reference", "P", Tier.L1_CORRECTIVE, reference),
            ArmSpec("treatment", "P", Tier.L1_CORRECTIVE, treatment))


def runner(events=None, **overrides):
    kwargs = dict(
        refinement="eligible_all", q_reference=REFERENCE_VIEW, retention_form="RetentionAtH",
        retention_params={"H": 5},
        # A91: the future curve is indexed by TRAINING EPISODE, and the protocol carries the design
        # quantities. H = 5 must be a checkpoint of this grid, which is the F1 consistency the frozen
        # retention estimator enforces by refusing a horizon the curve does not contain. v_pre is the
        # LOCKED shared measurement (A85 §73.1): the production path injects it rather than re-measuring
        # it per arm, so it is built here through the seedless construction helper.
        training=FutureTrainingProtocol(
            seed=11, alpha=Fraction(1, 2), epsilon=Fraction(1, 4), t_max=6, grid=(0, 1, 2, 5, 6),
            evaluation_sample=scene_domain()[:2],
            v_pre=pre_level(scene_domain()[:2], q_reference=REFERENCE_VIEW)),
        recorder=(lambda *a: events.append(a)) if events is not None else None)
    kwargs.update(overrides)
    return PairedRunner(**kwargs)


#: The pair's credited unit. A89 §77.4 defines the unaffected region relative to a credited site, and
#: the runner now binds it to the unit B1 will actually credit: rho_P(ProcessCommit, AssistedInput(1))
#: is (1,), so the region is E(P(1)) rather than E(P(0)).
CREDIT = CreditedSite("P", 1)


def run(events=None, **overrides):
    return runner(events, **overrides).run(
        LearnerPersistentState(), arms=arm_defs(),
        evidence={"units": UNITS, "assisted": AssistedInput(1)},
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
    assert params == ("self", "state", "arms", "evidence", "credited_site"), params
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
    object_count = len(set(seen))
    assert object_count == 1, "the two arms' metrics saw different objects"
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
                              credited_site=CREDIT)
    finally:
        LearnerPersistentState.clone = original
    assert len(calls) == 4, f"expected two arm clones and two future clones, got {len(calls)}"
    pre = fingerprint(state)
    from_pre = [parent for parent in parents if parent == pre]
    assert len(from_pre) == 2, (
        "the two ARM clones must be taken from the one pre-update state: a clone from an already "
        f"updated state makes the arms a serial chain rather than a pair (parents {parents!r})")
    assert len(set(record.fingerprints_pre.values())) == 1
    assert record.fingerprints_pre["first"] == record.fingerprints_pre["second"]
    # A91: the future runs on a CLONE of each arm's immediate post-B1 state, so the extra two clones
    # parent on the post states -- never on the pre state, which would train the wrong object
    post = set(record.fingerprints_post.values())
    assert sorted(parents.count(p) for p in post) == [1, 1] or len(post) == 1, parents
    assert all(parent in post or parent == pre for parent in parents), parents


def test_5_the_paired_futures_share_one_training_stream():
    r"""$$\boxed{\text{the arms differ in } \Delta W \text{ and in nothing else}}$$

    The shared object that matters is now A91's **training protocol**: both arms must consume the same
    keyed episode stream, so the gate reads the protocol identity rather than the old single-episode
    exogenous setup (which no longer feeds the future at all).
    """
    events = []
    record = run(events)
    protocol_ids = [e[2] for e in events if e[0] == "training_protocol"]
    assert len(protocol_ids) == 2 and len(set(protocol_ids)) == 1, (
        f"the paired arms did not consume ONE training protocol: {protocol_ids}")
    assert record.observations[0][1:] == record.observations[1][1:], (
        f"the arms' recorded provenance must describe the one protocol both consumed: "
        f"{record.observations}")
    assert record.observations[0][0] != record.observations[1][0]
    # the recorded provenance is the TRAINING one, because that is what now decides the future: the old
    # single-episode (kappa, phi, tape, base_option, checkpoints) tuple described a retired object
    assert record.observations[0][1] == record.observations[1][1] == 11  # the shared seed
    assert record.observations[0][2] == 6                                # the locked t_max
    assert record.observations[0][3] == (0, 1, 2, 5, 6)                  # the locked grid


def test_5b_the_collateral_measures_the_immediate_post_b1_state():
    r"""$$\boxed{V_{\text{unaffected,post}} = \text{the arm's own immediate post-B1 state}}$$

    A91's future training learns in place, so this is the integration bug the review found: if the
    future consumed the arm's own post state instead of a clone, the collateral would measure a *trained*
    learner and every collateral number would silently describe a different object.
    """
    events = []
    record = run(events)
    measured = {name: value for _, name, value in
                [(e[0], e[1], e[2]) for e in events if e[0] == "collateral_state"]}
    assert len(measured) == 2, events
    for arm in record.arm_names:
        assert measured[arm] == record.fingerprints_post[arm], (
            f"arm {arm!r}: the collateral measured {measured[arm]!r} but the arm's immediate post-B1 "
            f"state was {record.fingerprints_post[arm]!r}")


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
                     credited_site=CREDIT)
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
        "future_utility", "collateral", "retention", "ledgers", "fingerprints_pre",
        "fingerprints_post", "observations"}
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
    map_count = len(maps)
    assert map_count == 3, f"expected one pre map and one per arm, got {map_count}"
    assert len(set(pre_ids)) == 1 and pre_ids[0] == maps[0], (
        "both arms must be handed the same pre-map object that was measured first")
    assert set(record.collateral) == set(record.arm_names)


def test_11c_a_dq_pair_runs_through_the_b1_entry_point():
    r"""A85 §73.2.5: the $D_Q$ dispatch is **load-bearing**, not merely nameable.

    The pair runs on a raw pre state that already carries a $Q$ override at the credited row: the
    reference law keeps it and `LocalOracleRestore` restores the row, i.e. deletes the override by
    A77 §65.4's canonicalisation. The gate reads the two post states the instrument measured -- so a
    dispatch that was quietly turned into a no-op would leave them identical and turn this red.
    """
    from rfl_rebuild.b1.laws import DQ_LAWS
    from rfl_rebuild.b2.unaffected import credited_domain, pre_update_traces, scene_domain
    from rfl_rebuild.learner.store import QAddress

    traces = pre_update_traces(learner=LearnerPersistentState(), q_reference=REFERENCE_VIEW)
    credit = credited_domain("D_Q", traces)[0]
    address = credit.address
    # the row must be one the read path can reach: a Q entry outside the reference domain is refused
    # by the store, because a row the read path never consults would move the fingerprint while being
    # invisible in behaviour
    allowed = sorted(option_actions(address.z, ControlState(z=address.z, m=address.m), address.state))
    assert allowed, "the credited decision context must have an admissible action"
    row = QAddress(state=address.state, z=address.z, m=address.m, a=allowed[0])
    state = LearnerPersistentState()
    state.apply_transaction([Edit(Q, row, SOLUTION.q_value(address.state, address.z, address.m,
                                                           allowed[0]) - 1.0)],
                            q_reference=REFERENCE_VIEW)
    assert state.q_overrides, "the gate needs a credited row that already carries an override"

    reference = next(x for x in DQ_LAWS
                     if type(x).__name__ == "NoWriteRef" and x.tier is Tier.L3_ORACLE)
    treatment = next(x for x in DQ_LAWS if getattr(x, "name", None) == "LocalOracleRestore")
    arms = (ArmSpec("reference", "D_Q", Tier.L3_ORACLE, reference),
            ArmSpec("treatment", "D_Q", Tier.L3_ORACLE, treatment))
    scene = next(s for s in sorted(scene_domain(), key=lambda s: s.key) if s.base_option == 1)

    import rfl_rebuild.b2.runner as R
    learners = []
    original = R.measure_scene_map

    def spy(learner, units, *, q_reference):
        learners.append(learner)
        return original(learner, units, q_reference=q_reference)

    R.measure_scene_map = spy
    try:
        record = runner().run(state, arms=arms,
                              evidence={"addresses": (address,), "rows": traces.rows(scene)},
                              credited_site=credit)
    finally:
        R.measure_scene_map = original

    assert record.architecture == "D_Q"
    assert set(record.collateral) == {"reference", "treatment"}
    assert len(learners) == 3, "one pre measurement and one per arm"
    pre_learner, post_ref, post_treat = learners
    assert pre_learner.q_overrides, "the pre measurement must read the state it was handed"
    assert post_ref.q_overrides == pre_learner.q_overrides, (
        "NoWriteRef must leave the credited row alone")
    assert not post_treat.q_overrides, (
        "LocalOracleRestore must have deleted the override: a no-op dispatch would keep it")
    assert fingerprint(post_ref) != fingerprint(post_treat), (
        "the two arms' post states must differ, or the DQ dispatch is not load-bearing")
    assert record.unaffected_size > 0


def test_11d_a_legal_but_unrelated_credited_unit_is_refused():
    r"""$$\boxed{\text{resolved B1 credit} = \text{the runner's credited site}}$$

    Membership in the credited domain is not enough: a legal $c$ that is not the unit this pair writes
    would define the region for a different pair. `ProcessCommit` with `AssistedInput(1)` resolves to
    $P(1)$, so $P(0)$ must fail stop.
    """
    with pytest.raises(ProtocolError) as ei:
        runner().run(LearnerPersistentState(), arms=arm_defs(),
                     evidence={"units": UNITS, "assisted": AssistedInput(1)},
                     credited_site=CreditedSite("P", 0))
    assert "resolves to (1,)" in str(ei.value)


def test_11e_a_second_reference_object_is_refused():
    r"""A89 §77.8 freezes **one** nominal reference artifact, and the gate reads the consumers.

    The retired `ExogenousSetup` used to be the place this was checked, by handing the runner a
    value-equal second view and refusing it. That check guarded a field the future no longer reads, so
    it proved nothing about the real path. What is asserted now is the identity of the object each
    consumer actually receives: eligibility, the collateral maps and the training instrument must all be
    handed `self._q_reference` itself.
    """
    seen = {}
    original = {
        "pre_update_traces": runner_module.pre_update_traces,
        "measure_scene_map": runner_module.measure_scene_map,
        "train_curve": runner_module.train_curve,
    }

    def spy(name, inner):
        def wrapper(*args, **kwargs):
            seen.setdefault(name, set()).add(id(kwargs.get("q_reference")))
            return inner(*args, **kwargs)
        return wrapper

    try:
        for name, inner in original.items():
            setattr(runner_module, name, spy(name, inner))
        run()
    finally:
        for name, inner in original.items():
            setattr(runner_module, name, inner)

    assert set(seen) == set(original), f"a consumer was never reached: {sorted(seen)}"
    for name, ids in seen.items():
        assert ids == {id(REFERENCE_VIEW)}, (
            f"{name} was handed {ids}, not the runner's one reference artifact "
            f"({id(REFERENCE_VIEW)})")


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
