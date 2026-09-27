"""Quantitative margin claims cannot be laundered into practical equivalence."""
import copy
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.design_lock import CONSTANTS, prepare_inputs
from rfl_rebuild.b2.f0_stages import validate_contract


def policy_module():
    return importlib.import_module("rfl_rebuild.b2.rmst_policy")


def test_bare_rationale_cannot_authorize_a_design_lock(tmp_path):
    manifest_path = tmp_path / "f0.json"
    manifest_path.write_text(json.dumps({
        "schema": "f0-c3-design-v1", "status": "VALID",
        "currently_authorises": ["design_lock"], "constants": CONSTANTS,
        "rmst_policy": {"ratified": True, "value": 1.5,
                        "rationale": "Claim that the old number is practically meaningful"},
    }))
    with pytest.raises(ProtocolError, match="benchmark RMST policy"):
        prepare_inputs(tmp_path, design_path=tmp_path / "absent.json", manifest_path=manifest_path)


def test_bare_rationale_cannot_authorize_an_f0_manifest():
    path = Path(__file__).resolve().parents[2] / "scripts/f0_manifest_selfcheck.py"
    spec = importlib.util.spec_from_file_location("policy_f0_fixture", path)
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    manifest = check.fixture()
    legacy = {"ratified": True, "value": 1.5, "rationale": "Practically meaningful"}
    manifest["rmst_policy"] = legacy
    manifest["review"]["rmst_policy"] = copy.deepcopy(legacy)
    with pytest.raises(ProtocolError, match="benchmark RMST policy"):
        validate_contract(manifest)


def test_proposal_is_non_authorizing_and_ratification_keeps_the_scoped_claim():
    module = policy_module()
    proposal = module.benchmark_rmst_policy()
    with pytest.raises(ProtocolError, match="not ratified"):
        module.validate_rmst_policy(proposal)
    policy = module.benchmark_rmst_policy(ratified=True)
    assert module.validate_rmst_policy(policy) == policy
    assert policy["value"] == 1.5
    assert policy["practical_meaning_claimed"] is False
    assert policy["equivalence_claimed"] is False
    assert policy["zero_harm_claimed"] is False
    # A modified caller copy cannot change future policies or the validation contract.
    policy["value"] = 0
    assert module.benchmark_rmst_policy()["value"] == 1.5


@pytest.mark.parametrize("field,value", [
    ("kind", "practical-sesoi"), ("value", 0), ("value", 1.0),
    ("value", True), ("value", float("nan")), ("value", float("inf")),
    ("statistic", "DeficitAUC"), ("estimand", "episodewise-recovery"),
    ("units", "checkpoints"), ("difference", "treatment-minus-reference"),
    ("claim", "practical-benefit"), ("practical_meaning_claimed", True),
    ("practical_meaning_claimed", 0), ("equivalence_claimed", True),
    ("zero_harm_claimed", True), ("rationale", ""),
    ("rationale", "A nonempty string is not a scientific justification"),
    ("ratified", 1), ("extra_unreviewed_claim", True),
])
def test_changed_scope_or_number_requires_a_new_policy(field, value):
    module = policy_module()
    policy = module.benchmark_rmst_policy(ratified=True)
    policy[field] = value
    with pytest.raises(ProtocolError, match="benchmark RMST policy"):
        module.validate_rmst_policy(policy)


@pytest.mark.parametrize("lower,upper,expected", [
    (1.6, 2.0, "MARGIN_A"), (-2.0, -1.6, "MARGIN_B"),
    (-1.5, 1.5, "WITHIN_BENCHMARK_MARGIN"), (0.2, 0.8, "WITHIN_BENCHMARK_MARGIN"),
    (0., 0., "WITHIN_BENCHMARK_MARGIN"), (1.5, 1.5, "WITHIN_BENCHMARK_MARGIN"),
    (1.5, 2.0, "INCONCLUSIVE"), (-2.0, -1.5, "INCONCLUSIVE"),
    (-2., 2., "INCONCLUSIVE"), (1.0, 2.0, "INCONCLUSIVE"),
])
def test_interval_decisions_have_no_practical_equivalence_semantics(lower, upper, expected):
    module = policy_module()
    assert module.rmst_margin_decision(lower, upper, policy=module.benchmark_rmst_policy(ratified=True)) == expected


@pytest.mark.parametrize("lower,upper", [(2., 1.), (True, 2.), (0., float("nan")), (-float("inf"), 1.)])
def test_interval_decision_rejects_invalid_or_non_finite_bounds(lower, upper):
    module = policy_module()
    with pytest.raises(ProtocolError, match="interval"):
        module.rmst_margin_decision(lower, upper, policy=module.benchmark_rmst_policy(ratified=True))


@pytest.mark.parametrize("lower,upper,expected", [
    (-1., 3., True), (-1.5, 4., True), (-1.5000001, 4., False),
    (-2., -1.6, False), (0., 0., True), (2., 3., True),
])
def test_t_harm_bound_uses_the_inclusive_lower_limit_independently(lower, upper, expected):
    module = policy_module()
    policy = module.benchmark_rmst_policy(ratified=True)
    assert module.rmst_harm_bound_met(lower, upper, policy=policy) is expected
    if (lower, upper) == (-1., 3.):
        assert module.rmst_margin_decision(lower, upper, policy=policy) == "INCONCLUSIVE"


@pytest.mark.parametrize("lower,upper", [(2., 1.), (True, 2.), (0., float("nan")), (-float("inf"), 1.)])
def test_t_harm_bound_rejects_invalid_or_non_finite_bounds(lower, upper):
    module = policy_module()
    with pytest.raises(ProtocolError, match="interval"):
        module.rmst_harm_bound_met(lower, upper, policy=module.benchmark_rmst_policy(ratified=True))


def test_t_harm_bound_rejects_an_unratified_policy():
    module = policy_module()
    with pytest.raises(ProtocolError, match="not ratified"):
        module.rmst_harm_bound_met(-1., 3., policy=module.benchmark_rmst_policy())
