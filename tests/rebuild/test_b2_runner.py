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

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b1.laws import P_LAWS, X_LAWS  # noqa: E402
from rfl_rebuild.b1.process import AssistedInput  # noqa: E402
from rfl_rebuild.b1.tier import Tier  # noqa: E402
from rfl_rebuild.b2.environment import KernelLearnerEnvironment, audited_modules  # noqa: E402
from rfl_rebuild.b2.runner import (  # noqa: E402
    ARCHITECTURES, EXOGENOUS_FIELDS, ArmSpec, ExogenousSetup, PairedRunner,
)
from rfl_rebuild.b2.view import assert_modules_are_closed  # noqa: E402
from rfl_rebuild.env.kernel import SemanticTape  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import LearnerPersistentState  # noqa: E402
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
        collateral_construction="visited_complement", retention_form="RetentionAtH",
        retention_params={"H": 5},
        recorder=(lambda *a: events.append(a)) if events is not None else None)
    kwargs.update(overrides)
    return PairedRunner(**kwargs)


def run(events=None, **overrides):
    return runner(events, **overrides).run(
        LearnerPersistentState(), arms=arm_defs(),
        evidence={"units": UNITS, "assisted": AssistedInput(1)}, exogenous=exogenous())


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
    r"""The provenance obligation B2-3 left: the runner derives `domain`/`visited` itself."""
    params = tuple(inspect.signature(PairedRunner.run).parameters)
    assert params == ("self", "state", "arms", "evidence", "exogenous"), params
    domain, visited = PairedRunner.pre_update_source(LearnerPersistentState())
    assert domain and not visited, "a fresh state has touched nothing"
    with pytest.raises(ProtocolError) as ei:
        PairedRunner.pre_update_source(object())
    assert "learner state" in str(ei.value)


def test_3_the_arms_are_handed_one_object_not_two_equal_ones():
    r"""$$\boxed{u_{\text{ref}}\ \text{is}\ u_{\text{treat}}}$$"""
    import rfl_rebuild.b2.runner as R

    seen, events = [], []
    original = R.behavioral_collateral

    def spy(unaffected, *, values_pre, values_post):
        seen.append(id(unaffected))
        return original(unaffected, values_pre=values_pre, values_post=values_post)

    R.behavioral_collateral = spy
    try:
        run(events)
    finally:
        R.behavioral_collateral = original
    assert len(seen) == 1, "the metric saw more than one object"
    built = [e[2] for e in events if e[0] == "unaffected"]
    assert len(built) == 1, "the set was constructed more than once"
    assert seen[0] == built[0], "the metric was handed a different object than the one built"


def test_4_the_arms_fork_from_one_pre_update_state():
    r"""Two independent clones of **one** state: a serial chain is not a pair."""
    calls = []
    original = LearnerPersistentState.clone

    def spy(self):
        calls.append(id(self))
        return original(self)

    LearnerPersistentState.clone = spy
    try:
        record = run()
    finally:
        LearnerPersistentState.clone = original
    assert len(calls) == 2, f"expected one clone per arm, got {len(calls)}"
    assert len(set(record.fingerprints_pre.values())) == 1
    assert record.fingerprints_pre["reference"] == record.fingerprints_pre["treatment"]


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
    for kwargs in ({"collateral_construction": "", "retention_form": "RetentionAtH",
                    "retention_params": {"H": 5}},
                   {"collateral_construction": "visited_complement", "retention_form": "",
                    "retention_params": {"H": 5}},
                   {"collateral_construction": "visited_complement",
                    "retention_form": "RetentionAtH", "retention_params": {}},
                   {"collateral_construction": "visited_complement",
                    "retention_form": "RetentionFraction", "retention_params": {"H": 5}}):
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
    assert ARCHITECTURES == ("P", "X")
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
    with pytest.raises(ProtocolError) as ei:
        ArmSpec("arm", "X", Tier.L0_FACTUAL, p_law)
    assert "not in the X registry" in str(ei.value)
    with pytest.raises(ProtocolError) as ei:
        ArmSpec("arm", "P", Tier.L1_CORRECTIVE, x_law)
    assert "not in the P registry" in str(ei.value)
    # the two registries are genuinely disjoint, so the refusals are not one rule twice
    p_names = {getattr(x, "name", type(x).__name__) for x in P_LAWS}
    x_names = {getattr(x, "name", type(x).__name__) for x in X_LAWS}
    assert p_names & x_names == {"NoWrite", "LocalOracleRestore"}, (p_names, x_names)
    assert ArmSpec("arm", "X", Tier.L0_FACTUAL, x_law).architecture == "X"
    # and a mixed-architecture pair is refused at the runner, not only at the spec
    mixed = (ArmSpec("reference", "P", Tier.L1_CORRECTIVE,
                     next(x for x in P_LAWS if type(x).__name__ == "NoWriteRef"
                          and x.tier is Tier.L1_CORRECTIVE)),
             ArmSpec("treatment", "X", Tier.L0_FACTUAL, x_law))
    with pytest.raises(ProtocolError) as ei:
        runner().run(LearnerPersistentState(), arms=mixed,
                     evidence={"units": UNITS, "assisted": AssistedInput(1)},
                     exogenous=exogenous())
    assert "different architectures" in str(ei.value)


# --------------------------------------------------------------------------- #
# information boundary / outcome space
# --------------------------------------------------------------------------- #

def test_10_the_record_keeps_three_dimensions_and_no_composite():
    r"""$$\boxed{Y^{\text{future}} = \{\text{FutureUtility},\ \text{Collateral},\
    \text{Retention}\}}$$, with the cost view **beside** them."""
    record = run()
    assert set(record.__dataclass_fields__) == {
        "arm_names", "architecture", "unaffected_construction", "retention_form",
        "future_utility", "collateral", "retention", "ledgers", "fingerprints_pre", "observations"}
    forbidden = {"score", "weighted_score", "overall_utility", "composite", "primary", "verdict",
                 "p_value", "rmst", "holm", "bootstrap", "conclusion"}
    assert not (set(record.__dataclass_fields__) & forbidden)
    assert set(record.future_utility) == set(record.arm_names)
    assert set(record.retention) == set(record.arm_names)
    assert "UpdateLedger" not in {type(v).__name__ for v in record.future_utility.values()}
    names = _module_names(RUNNER_MODULE)
    assert not (names & {"rmst", "RMST", "holm", "bootstrap", "verdict", "conclusion", "p_value"})


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
