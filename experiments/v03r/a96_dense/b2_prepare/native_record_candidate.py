"""Source-isolated B2 record bridge, NOT a collection entry point or gate.

Only already supplied nominal records/recorder events are inspected. No rollout,
training, seed draw, reservation, file publication or scientific verdict occurs.
Nominal Python objects can be constructed by tests: their types and input digest
are NOT proof of acquisition origin. Factual population, collection receipts,
raw collateral maps and whole B2 authorization must be supplied by a later gate.
"""
from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
import hashlib
import json
import math

import readiness as ready
from rfl_rebuild.b1.contract import DecisionWriteReceipt, EVALUABLE_NOOP, UpdateLedger
from rfl_rebuild.b1.laws import law_metadata
from rfl_rebuild.b1.tier import DQ_SLICE, P_SLICE, X_SLICE, Tier
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.retention import select_form
from rfl_rebuild.b2.runner import ArmSpec, LAW_REGISTRIES, PairedSceneRecord
from rfl_rebuild.b2.training import FutureTrainingProtocol
from rfl_rebuild.b2.unaffected import CreditedSite, EvaluationScene, UnaffectedSet
from rfl_rebuild.b2.utility import FutureUtility
from rfl_rebuild.env.kernel import Outcome

SLICES = {"D_Q": DQ_SLICE, "X": X_SLICE, "P": P_SLICE}
TIER_LABELS = {Tier.L0_FACTUAL: "L0", Tier.L1_CORRECTIVE: "L1",
               Tier.L2_COUNTERFACTUAL: "L2", Tier.L3_ORACLE: "L3"}
STATISTICS = ("RMST", "DeficitAUC", "BehavioralCollateral", "Retention")


def require(ok, message):
    if not ok:
        raise ready.ProtocolError(message)


def sha(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def finite(value, name):
    require(type(value) in (int, float), f"{name}: finite real required")
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    require(valid, f"{name}: finite representable real required")
    return value


def frozen_matrix():
    """Enumerate inherited *available* pairs, not selected populations/families.

    Alias rows remain aliases. Same-tier comparisons only; L2/L3 cannot support
    a learner-feasible L0 ranking. Registration order is inherited, not sorted
    after observing results. No new law/tier/parameter is introduced.
    """
    rows = []
    for architecture in ("D_Q", "X", "P"):
        registry = LAW_REGISTRIES[architecture]
        metadata = law_metadata(registry)
        for entry, (name, kind, alias) in zip(registry, metadata):
            if kind == "reference":
                continue
            tier = entry.tier
            descriptor = SLICES[architecture]
            descriptor.require_implemented(tier)
            fields = sorted(descriptor.fields(tier))
            refs = [r for r, m in zip(registry, metadata)
                    if m[1] == "reference" and r.tier is tier]
            require(len(refs) == 1, "exactly one inherited reference in each substantive cell")
            label = TIER_LABELS[tier]
            rows.append({"architecture": architecture, "tier": label,
                         "tier_value": tier.value, "reference_law": refs[0].name,
                         "treatment_law": name, "treatment_kind": kind,
                         "alias_of": alias, "delivery_fields": fields,
                         "reference_arm": f"{architecture}/{label}/{refs[0].name}",
                         "treatment_arm": f"{architecture}/{label}/{name}",
                         "learner_feasible_L0": tier is Tier.L0_FACTUAL,
                         "ceiling_not_algorithm_ranking": tier in
                             (Tier.L2_COUNTERFACTUAL, Tier.L3_ORACLE)})
    return rows


def registered_pair(architecture, tier, treatment_law):
    require(type(architecture) is str and architecture in SLICES and type(tier) is Tier
            and type(treatment_law) is str, "closed architecture/opaque Tier/law required")
    matches = [m for m in frozen_matrix() if m["architecture"] == architecture
               and m["tier_value"] == tier.value and m["treatment_law"] == treatment_law]
    require(len(matches) == 1, "not an inherited substantive same-tier treatment")
    m = matches[0]
    entries = [e for e in LAW_REGISTRIES[architecture] if e.tier is tier]
    ref = next(e for e in entries if e.name == m["reference_law"])
    treat = next(e for e in entries if e.name == treatment_law)
    return (ArmSpec(m["reference_arm"], architecture, tier, ref),
            ArmSpec(m["treatment_arm"], architecture, tier, treat))


def validate_pair(arms):
    require(type(arms) is tuple and len(arms) == 2 and all(type(a) is ArmSpec for a in arms),
            "exact ordered reference/treatment ArmSpecs required")
    ref, treat = arms
    require(ref.architecture == treat.architecture and ref.tier is treat.tier,
            "reference/treatment must be in the same architecture and information tier")
    expected = registered_pair(treat.architecture, treat.tier, getattr(treat.law, "name", None))
    # This candidate requires the actual inherited singleton/class references.
    # It does not widen the native type/tier admission rule or change native laws.
    for arm, registered in zip(arms, expected):
        require(arm.name == registered.name and arm.law is registered.law,
                "arm role/name/law must match the inherited registry binding")
    return next(m for m in frozen_matrix() if m["treatment_arm"] == treat.name)


class TraceCapture:
    """Passive callback for the original runner's ten events; never executes it.

    Live ids only check in-process sharing/order. They are not portable hashes or
    authentication and are intentionally absent from the exported input digest.
    """
    __slots__ = ("_events",)

    def __init__(self):
        self._events = []

    def __call__(self, *event):
        self._events.append(tuple(event))

    @property
    def events(self):
        return tuple(self._events)


def validate_ledger(ledger, architecture, site, pre, post, *, reference):
    require(type(ledger) is UpdateLedger and type(ledger.receipts) is tuple and
            len(ledger.receipts) == 1, "one native ledger and exactly one credited receipt required")
    require(type(ledger.scalar_metrics_applicable) is bool and
            ledger.scalar_metrics_applicable == (architecture == "D_Q") and
            type(ledger.n_scalar) is int and ledger.n_scalar >= 0, "typed ledger accounting differs")
    require(ledger.fingerprint_pre == pre and ledger.fingerprint_post == post,
            "ledger fingerprints do not bind the immediate pre/post states")
    receipt = ledger.receipts[0]
    require(type(receipt) is DecisionWriteReceipt and type(receipt.store_changed) is bool and
            receipt.address == site.address, "receipt is not for this pair's credited address")
    domain = SLICES[architecture].domain
    domain.require_credited(receipt.address)
    require(receipt.canonical_form == domain.canonical(receipt.address), "address canonical identity differs")
    for name in ("sum_abs_delta", "max_abs_delta"):
        require(finite(getattr(ledger, name), name) >= 0, "negative ledger magnitude")
    ledger.check_fingerprint_invariants()
    if architecture != "D_Q" or reference:
        require(ledger.n_scalar == 0 and ledger.sum_abs_delta == ledger.max_abs_delta == 0,
                "value-free or reference ledger has spurious scalar cost")
    if reference:
        require(receipt.status == EVALUABLE_NOOP and pre == post and not receipt.store_changed,
                "NoWrite reference changed the state")
    return ledger.canonical()


def extract_paired_record(record, capture, arms, protocol, parent, reference, *,
                          seed, cell_id, regime, credited_site, factual_outcome):
    """Pure extraction/recalculation into already-measured seed/cell scalar rows.

    Requires full native utility/Retention curves, one shared protocol and ledger
    binding. NoReflection/SUCCESS is refused, not zero-filled or silently dropped.
    The later preregistered factual population must define its success routing.
    Collateral raw maps are not emitted by the native recorder: its scalar and
    state/set metadata are checked, but raw collateral recomputation is NOT claimed.
    """
    require(type(seed) is int and seed >= 0 and type(cell_id) is str and cell_id
            and regime in ("T", "P"), "explicit seed/cell and separate T/P required")
    require(type(factual_outcome) is str and factual_outcome in
            (Outcome.COLLISION, Outcome.TRAP, Outcome.TIMEOUT), "actual failure branch required, never SUCCESS")
    require(type(record) is PairedSceneRecord, "complete PairedSceneRecord required; no NO_REFLECTION imputation")
    require(type(capture) is TraceCapture, "complete original-runner event capture required")
    m = validate_pair(arms)
    d = ready.validate_design(parent["lock"])
    v_pre = ready.validate_reference(reference, parent)
    require(type(protocol) is FutureTrainingProtocol and type(protocol.seed) is int and
            protocol.seed == seed and type(protocol.alpha) is Fraction and
            type(protocol.epsilon) is Fraction and protocol.alpha == Fraction(1, 2) and
            protocol.epsilon == Fraction(1, 10), "typed shared protocol seed/constants differ")
    require(type(protocol.t_max) is int and protocol.t_max == d["T"] and
            type(protocol.grid) is tuple and all(type(e) is int for e in protocol.grid) and
            protocol.grid == tuple(d["grid"]) and
            type(protocol.evaluation_sample) is tuple and
            protocol.evaluation_sample == prefix(d["N_eval"]) and protocol.v_pre == v_pre,
            "shared horizon/full dense grid/ordered bank/B2 healthy reference differ")
    # Read-only strict checks also catch value-equal bool/float scene aliases;
    # calling protocol.__post_init__ would rebind fields on an existing input.
    for scene in protocol.evaluation_sample:
        require(type(scene) is EvaluationScene, "nominal ordered evaluation scenes required")
        scene.__post_init__()
    names = tuple(a.name for a in arms)
    require(type(record.arm_names) is tuple and record.arm_names == names and
            record.architecture == m["architecture"], "record arm role/order or architecture differs")
    require(type(credited_site) is CreditedSite and credited_site.channel == m["architecture"],
            "nominal matching credited site required")
    SLICES[m["architecture"]].domain.require_credited(credited_site.address)
    construction = f"E1(c={credited_site.render()})@{d['refinement']}"
    require(record.unaffected_construction == construction and type(record.unaffected_size) is int
            and record.unaffected_size > 0 and record.retention_form == d["retention"]["form"],
            "locked credited unaffected/Retention design differs")
    for field in ("future_utility", "collateral", "retention", "ledgers", "fingerprints_pre", "fingerprints_post"):
        values = getattr(record, field)
        require(isinstance(values, Mapping) and tuple(values) == names, f"{field}: full ordered two-arm map required")
    for field in (record.fingerprints_pre, record.fingerprints_post):
        require(all(type(h) is str and len(h) == 64 and all(c in "0123456789abcdef" for c in h)
                    for h in field.values()), "state fingerprint must be canonical SHA256")
    require(len(set(record.fingerprints_pre.values())) == 1, "arms do not share one pre-update state")
    expected_observations = tuple((n, seed, d["T"], tuple(d["grid"]), d["N_eval"], v_pre) for n in names)
    require(type(record.observations) is tuple and len(record.observations) == 2, "full two-arm provenance required")
    for got, expected in zip(record.observations, expected_observations):
        require(type(got) is tuple and len(got) == 6 and type(got[1]) is type(got[2]) is
                type(got[4]) is int and type(got[3]) is tuple and all(type(e) is int for e in got[3])
                and type(got[5]) is float and got == expected, "curve observation provenance differs")

    events = capture.events
    require(len(events) == 10, "partial/duplicate recorder sequence refused")
    u, pm = events[:2]
    require(len(u) == 3 and u[0] == "unaffected" and type(u[1]) is UnaffectedSet and
            type(u[2]) is int and u[2] == id(u[1]), "one nominal unaffected object event required")
    unaffected = u[1]
    unaffected.__post_init__()
    require(unaffected.construction == construction and unaffected.size == record.unaffected_size,
            "recorder/record unaffected set differs")
    require(len(pm) == 3 and pm[0] == "pre_map" and type(pm[1]) is int and pm[1] > 0 and
            type(pm[2]) is int and pm[2] == unaffected.size, "one complete pre-map observation required")
    for event, name in zip(events[2:4], names):
        require(len(event) == 3 and event[:2] == ("update_applied", name) and
                type(event[2]) is int and event[2] > 0, "updates must precede both futures in arm order")
    require(events[2][2] != events[3][2], "two independent immediate post-update clones required")
    curves, scalar_values, ledger_text = {}, {}, {}
    for i, name in enumerate(names):
        pe, fe, ce = events[4+2*i], events[5+2*i], events[8+i]
        require(len(pe) == 3 and pe[:2] == ("training_protocol", name) and
                type(pe[2]) is int and pe[2] == id(protocol), "ONE shared protocol event required")
        require(len(fe) == 3 and fe[:2] == ("future", name) and type(fe[2]) is tuple and len(fe[2]) == 2,
                "full raw future event required in native order")
        values, episodes = fe[2]
        require(type(values) is tuple and type(episodes) is tuple and len(values) == d["T"] + 1
                and all(type(t) is int for t in episodes) and episodes == protocol.grid,
                "full ordered integer-episode curve required; never a prefix or step curve")
        for value in values:
            finite(value, "curve level")
        utility = record.future_utility[name]
        require(type(utility) is FutureUtility and type(utility.recovered) is bool and
                type(utility.restricted_time) is type(utility.t_max) is int and
                (utility.tau is None or type(utility.tau) is int), "typed native FutureUtility required")
        finite(utility.deficit_auc, "DeficitAUC")
        expected_utility = FutureUtility.from_curve(values, episodes, pre_level=v_pre, t_max=d["T"])
        require(utility == expected_utility and type(utility.deficit_auc) is float and
                utility.deficit_auc.hex() == expected_utility.deficit_auc.hex(),
                "native utility differs from original full-curve recomputation")
        retained = select_form(d["retention"]["form"])(values, episodes, **d["retention"]["parameters"])
        require(type(finite(record.retention[name], "Retention")) is float and
                record.retention[name].hex() == retained.hex(),
                "Retention differs from original locked checkpoint-mean arithmetic")
        collateral = finite(record.collateral[name], "BehavioralCollateral")
        pre, post = record.fingerprints_pre[name], record.fingerprints_post[name]
        ledger_text[name] = validate_ledger(record.ledgers[name], m["architecture"], credited_site,
                                            pre, post, reference=i == 0)
        require(len(ce) == 3 and ce == ("collateral_state", name, post),
                "collateral was not bound to the immediate post-B1 state")
        if i == 0:
            require(type(collateral) is float and collateral.hex() == (0.).hex(),
                    "NoWrite reference must have the original exact zero behavioral loss")
        curves[name] = {"episodes": list(episodes), "levels_hex": [float(v).hex() for v in values]}
        scalar_values[name] = {"RMST": utility.restricted_time, "DeficitAUC": utility.deficit_auc,
                               "BehavioralCollateral": collateral, "Retention": retained,
                               "tau": utility.tau, "recovered": utility.recovered}
    statistics = STATISTICS if regime == "P" else STATISTICS[:2]
    rows = [{"seed": seed, "cell_id": cell_id, "regime": regime, "statistic": s,
             "reference": scalar_values[names[0]][s], "treatment": scalar_values[names[1]][s]}
            for s in statistics]
    payload = {"seed": seed, "cell_id": cell_id, "regime": regime, "factual_outcome": factual_outcome,
               "law_binding": m, "lock_sha256": parent["lock_sha256"],
               "parent_sources_digest": parent["sources_digest"],
               "healthy_reference_canonical_payload_sha256": sha(reference),
               "evaluation_sample_sha256": reference["evaluation_sample_sha256"],
               "unaffected_construction": construction, "unaffected_unit_keys": [list(v.key) for v in unaffected.units],
               "ledger_canonical": ledger_text, "curves": curves, "values": scalar_values,
               "alpha": [1, 2], "epsilon": [1, 10], "v_pre_hex": v_pre.hex()}
    return {"role": "VALIDATED_IN_MEMORY_INPUT_NOT_AUTHENTICATED_ACQUISITION", "input_sha256": sha(payload),
            "input_payload": payload, "scalar_rows": rows, "utility_retention_recomputed": True,
            "raw_collateral_maps_recomputed": False, "actual_factual_failure_origin_authenticated": False,
            "unaffected_eligibility_from_prestate_recomputed": False,
            "population_seed_registry_and_collection_gate_authenticated": False,
            "collection_authorized": False, "scientific_claim_authorized": False, "research_complete": False}
