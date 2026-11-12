"""Unallocated B2 seed-plan validation; no reservation or acquisition entry.

Plans are nominal proposals, not credentials. Known exclusions and canonical
64-bit seed representatives are necessary but insufficient for actual freshness.
No environment generator, trainer, native protocol, worker or writer is called.
The final population/family, historical usage audit, engineering workload,
resource certification and separately committed collection gate remain owed.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import readiness as ready
import native_record_candidate as bridge
from rfl_rebuild.b2 import training

_PARENT = ready.load_parent()
_REGISTRY_PATH = ready.ROOT / "docs/rebuild/a96_seed_registry.json"
_DRAFT_PATH = ready.ROOT / ready.FOLDER / "b2_prepare/contract_draft.json"
_REGISTRY = ready.read_json(_REGISTRY_PATH)
_DRAFT = ready.read_json(_DRAFT_PATH)
_REGISTRY_PAYLOAD_SHA = bridge.sha(_REGISTRY)
_DRAFT_PAYLOAD_SHA = bridge.sha(_DRAFT)
_PARENT_IDENTITY = (_PARENT["sources_digest"], _PARENT["lock_sha256"])
_CODE_PATHS = tuple(Path(m.__file__) for m in (ready, bridge, training)) + (
    Path(__file__), _REGISTRY_PATH, _DRAFT_PATH,
    ready.ROOT / ready.FOLDER / "dev_lock.json")
_CODE_BINDING = tuple(ready.file_hash(p) for p in _CODE_PATHS)
_PLAN_SCHEMA = "a96-unallocated-B2-seed-plan-proposal-v14"
_PLAN_ROLE = "NOMINAL_PROPOSAL_NOT_RESERVATION"
_PLAN_KEYS = {"schema", "role", "primary_blocks", "secondary_blocks", "engineering_keys"}
_REGISTRY_KEYS = {"schema", "profile", "role", "scientific", "engineering",
                  "permanent_exclusions", "audit", "automatic_retry"}
_M64 = (1 << 64) - 1


def _seed(x):
    # A91 seed products wrap modulo2**64. Distinct unbounded integers can drive
    # exactly the same keyed stream. Never normalize/truncate an input key.
    ready.require(type(x) is int and 0 <= x <= _M64,
                  "key must be a canonical true nonnegative 64-bit integer")
    return x


def _keys(values, what, *, count=None):
    ready.require(type(values) is list and bool(values) and
                  (count is None or len(values) == count), f"{what} shape/count differs")
    result = tuple(_seed(x) for x in values)
    ready.require(len(set(result)) == len(result), f"{what} repeats a key")
    return result


def _registry_intervals(registry):
    ready.require(type(registry) is dict and set(registry) == _REGISTRY_KEYS and
        registry["schema"] == "rfl-a96-seed-registry-v1" and
        registry["profile"] == ready.PROFILE and
        registry["role"] == "PROSPECTIVE_EXCLUSIVE_RESERVATION_NOT_EXECUTED" and
        registry["automatic_retry"] is False, "known parent registry contract differs")
    scientific, engineering = registry["scientific"], registry["engineering"]
    exclusions = registry["permanent_exclusions"]
    ready.require(type(scientific) is dict and
        set(scientific) == {"smoke", "dev_baseline", "treatment", "confirmatory"} and
        scientific["treatment"] is None and scientific["confirmatory"] is None and
        type(engineering) is dict and set(engineering) == {"smoke", "dev_baseline"} and
        type(exclusions) is dict and set(exclusions) == {
            "old_scientific", "old_engineering_ranges", "operational_fixture_ranges"},
        "parent stages/exclusion identities differ")
    intervals = []
    for values, name, count in (
        (scientific["smoke"], "parent science smoke", 5),
        (scientific["dev_baseline"], "parent science development", 32),
        (engineering["smoke"], "parent engineering smoke", 5),
        (engineering["dev_baseline"], "parent engineering development", 32),
        (exclusions["old_scientific"], "old science exclusions", None)):
        intervals.extend((x, x) for x in _keys(values, name, count=count))
    for category in ("old_engineering_ranges", "operational_fixture_ranges"):
        rows = exclusions[category]
        ready.require(type(rows) is list and bool(rows), "missing known exclusion ranges")
        for row in rows:
            ready.require(type(row) is list and len(row) == 2,
                          "exclusion range needs both inclusive endpoints")
            lo, hi = (_seed(x) for x in row)
            ready.require(lo <= hi, "reversed exclusion range")
            intervals.append((lo, hi))
    # Canonical interval union; no per-key expansion of potentially huge ranges.
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return tuple(merged)


def _guard():
    ready.require((_PARENT["sources_digest"], _PARENT["lock_sha256"]) == _PARENT_IDENTITY,
                  "loaded frozen parent identity changed")
    ready.require(training.M64 == _M64 and
        tuple(ready.file_hash(p) for p in _CODE_PATHS) == _CODE_BINDING,
        "seed-plan/dependency/parent-registry/draft/lock bytes changed")
    ready.require(bridge.sha(_REGISTRY) == _REGISTRY_PAYLOAD_SHA and
        bridge.sha(_DRAFT) == _DRAFT_PAYLOAD_SHA, "loaded registry/draft payload changed")
    ready.require(ready.file_hash(ready.ROOT / ready.FOLDER / "dev_lock.json") ==
                  _PARENT["lock_sha256"], "current lock binding differs")
    ready.require(bridge.sha(_PARENT["lock"]) == bridge.sha(ready.read_json(
        ready.ROOT / ready.FOLDER / "dev_lock.json")), "loaded lock payload changed")
    analysis_rng = _DRAFT["analysis_procedure_candidate"]["bootstrap"]["algorithm_seed"]
    _seed(analysis_rng)
    return _registry_intervals(_REGISTRY), analysis_rng


def inspect_seed_plan(proposal):
    """Check a complete nominal proposal; never allocate even its valid keys.

    A plan has exactly four primary100 blocks and two secondary100 blocks.
    All proposed independent-seed and workload key identities are disjoint.
    This does not assign T/P cells, contrasts, method tiers, faults or populations.
    Caller-supplied authorizations/exclusion overrides and partial blocks cannot
    enlarge the API. No key is inferred from completion order or auto-replaced.
    """
    intervals, analysis_rng = _guard()
    ready.require(type(proposal) is dict and set(proposal) == _PLAN_KEYS and
        type(proposal["schema"]) is str and type(proposal["role"]) is str and
        proposal["schema"] == _PLAN_SCHEMA and proposal["role"] == _PLAN_ROLE,
        "closed unallocated proposal required, not receipt/authorization")
    try:
        before = bridge.sha(proposal)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ready.ProtocolError("proposal is not a finite canonical JSON construction") from exc
    blocks = []
    for category, block_count in (("primary_blocks", 4), ("secondary_blocks", 2)):
        stage = proposal[category]
        ready.require(type(stage) is list and len(stage) == block_count,
                      f"{category} requires complete declared100 blocks")
        blocks.append(tuple(_keys(b, category, count=100) for b in stage))
    engineering = _keys(proposal["engineering_keys"], "unallocated engineering")
    science = tuple(x for stage in blocks for block in stage for x in block)
    combined = science + engineering
    ready.require(len(set(combined)) == len(combined),
                  "proposed keys overlap within/across science tiers or engineering")
    for x in combined:
        ready.require(x != analysis_rng and not any(lo <= x <= hi for lo, hi in intervals),
                      "proposed key conflicts with known reserved/spent/fixture/analysis role")
    after_intervals, after_rng = _guard()
    ready.require(after_intervals == intervals and after_rng == analysis_rng and
                  bridge.sha(proposal) == before, "input/known exclusions moved during validation")
    payload = {"proposal": deepcopy(proposal), "proposal_payload_sha256": before,
        "known_exclusion_intervals_inclusive": [list(p) for p in intervals],
        "analysis_rng_role_exclusion": analysis_rng,
        "parent_registry_file_sha256": ready.file_hash(_REGISTRY_PATH),
        "parent_registry_payload_sha256": _REGISTRY_PAYLOAD_SHA,
        "parent_sources_digest": _PARENT["sources_digest"],
        "lock_sha256": _PARENT["lock_sha256"],
        "ordered_primary_keys": list(science[:400]),
        "ordered_secondary_keys": list(science[400:]),
        "ordered_engineering_keys": list(engineering)}
    return deepcopy({"schema": "a96-unallocated-B2-seed-plan-inspection-v14",
        "role": "KNOWN_EXCLUSION_AND_SHAPE_PREPARATION_NOT_COMPLETE_FRESHNESS_OR_GATE",
        "input_payload": payload, "input_payload_sha256": bridge.sha(payload),
        "primary_proposed_keys": 400, "secondary_proposed_keys": 200,
        "engineering_proposed_keys": len(engineering),
        "keys_are_canonical_unique_disjoint_from_known_exclusions": True,
        "complete_historical_usage_freshness_audit": False,
        "population_T_P_and_same_tier_family_registered": False,
        "engineering_workload_shape_or_count_authorized": False,
        "keys_allocated_or_reserved": False, "environment_key_draws": 0,
        "native_protocol_or_training_started": False,
        "collection_authorized": False, "scientific_claim_authorized": False,
        "research_complete": False})
