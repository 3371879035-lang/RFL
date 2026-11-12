"""Prospective owned keyed-protocol declaration, not a connected learner backend.

This version does not mint authority from the v95 no-key engineering grant,
an old F1 result, an EngineeringEpisode, a seed-shaped integer, or an issued
whole-B1 pair. All five are different objects. A future activation requires
an exact committed grant, explicitly keyed authority, source inventory,
candidate-specific predecessor receipts, and an already reserved key entry.

The order is deliberate: every authorization check precedes the protocol
factory, ExogenousEpisode.derive, and any coordinate call. A passing preflight
is not a scientific verdict. This source currently has no granted contract,
no issued permit, no allocated key, and no connector to the old nominal
CoordinateLearner/KeyedPlan/read-only-bank classes. Those classes and their
private permit registries are never modified or impersonated here.

Once an external committed grant really exists, prepare_owned_protocol binds
one exact original source-mode/pair to one shared FutureTrainingProtocol and
distinct full immediate starts. The NEW plan delegates original Xi lazily,
without prefetching the rejection domain. Attempts are consumed before the
factory/derive call; partial failure cannot create an entry or retry a key.
"""

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import inspect
import json
from pathlib import Path
import re
import subprocess
from types import MappingProxyType
from weakref import WeakKeyDictionary

import adaptive_training as A
import handoff as H
import oracle_mainline_v75 as O
from rfl_rebuild.b2 import training as T
from rfl_rebuild.env import kernel as K


GRANT_SCHEMA = "V109_COMMITTED_PAIRED_KEYED_GRANT_V1"
EXECUTION_KINDS = ("bounded-keyed-engineering", "confirmatory-collection")
ROLES = ("reference", "treatment")
REQUIRED_GATES = (
    "source_inventory_frozen", "owned_full_immediate_lineage",
    "versioned_keyed_backend_constructor_flow", "complete_entry_mutations",
    "shared_protocol_coordinate_contract", "resource_envelope",
    "seed_registry_exclusive", "collection_once_gate",
)
SCIENTIFIC_GATES = (
    "revised_backend_qualification", "whole_ruler_qualification",
    "full_family_preregistration", "final_rule_adoption",
)
SOURCE_TAGS = (
    "core", "handoff", "original_source", "training", "normal_learning",
    "normal_td", "readonly_bank", "owned_curve", "paired_protocol",
)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True, slots=True)
class ProtocolRequest:
    execution_kind: str
    mode: str
    seed: object
    expected_pair_seal: str
    reference_digest: str

    def __post_init__(self):
        A.require(type(self.execution_kind) is str and self.execution_kind in EXECUTION_KINDS,
                  "explicit keyed execution kind required")
        A.require(type(self.mode) is str and self.mode in ("dq", "patch-adaptive"),
                  "source mode must be declared, not inferred from post D")
        # None is an inert unassigned declaration, never a request to allocate.
        A.require(self.seed is None or (type(self.seed) is int and self.seed >= 0),
                  "reserved key must be a true nonnegative integer or explicitly unassigned")
        A.require(_is_sha(self.expected_pair_seal) and _is_sha(self.reference_digest),
                  "exact source-pair/reference digest declarations required")


class VerifiedGrant:
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise A.ProtocolError("requires an actual verified committed keyed grant")


class ActivationPermit:
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise A.ProtocolError("activation permits are only issued after complete preflight")


class OwnedProtocolEntry:
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise A.ProtocolError("requires successful genuine-source protocol construction")


@dataclass(slots=True)
class _GrantRecord:
    root: object
    contract_path: str
    commit: str
    document: dict
    digest: str
    pins: tuple
    attempts: dict


@dataclass(slots=True)
class _EntryRecord:
    grant: object
    permit: object
    request: object
    bound: object
    pair: object
    future: object
    protocol: object
    plan: object
    starts: tuple
    origin: dict
    digest: str
    requested_epochs: dict
    derived: dict
    exported_roles: set


_GRANTS = WeakKeyDictionary()
_PERMITS = WeakKeyDictionary()
_ENTRIES = WeakKeyDictionary()
_PLANS = WeakKeyDictionary()
_EPISODES = WeakKeyDictionary()
_KEY_ATTEMPTS = set()
_PAIR_ATTEMPTS = WeakKeyDictionary()


def _is_sha(value):
    return type(value) is str and _HEX64.fullmatch(value) is not None


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        A.require(key not in result, "duplicate JSON field is not a committed authority declaration")
        result[key] = value
    return result


def _read_json(data, what):
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise A.ProtocolError(f"invalid {what}: {error}") from error
    A.require(type(result) is dict, f"{what} must be one explicit JSON object")
    return result


def _git(root, *arguments):
    result = subprocess.run(("git", "-C", str(root), *arguments),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    A.require(result.returncode == 0, "committed grant verification failed: " +
              result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def _relative(root, path):
    A.require(type(path) is str and bool(path) and "\\" not in path,
              "artifact path must be explicit repository-relative POSIX text")
    candidate = Path(path)
    A.require(not candidate.is_absolute() and all(part not in ("", ".", "..")
                                                for part in candidate.parts),
              "grant artifact path escapes its declared repository")
    resolved = (root / candidate).resolve(strict=True)
    A.require(resolved.is_relative_to(root), "grant artifact resolves outside its repository")
    return candidate.as_posix(), resolved


def _committed_bytes(root, path, commit, expected_sha):
    A.require(_is_sha(expected_sha), "exact artifact SHA256 required")
    relative, physical = _relative(root, path)
    blob = _git(root, "show", f"{commit}:{relative}")
    current = physical.read_bytes()
    A.require(current == blob and sha256(blob).hexdigest() == expected_sha,
              f"committed/physical artifact binding failed: {relative}")
    return blob


def _verify_pin(root, pin, commit):
    A.require(type(pin) is dict and set(pin) == {"path", "sha256"},
              "artifact pin requires exact path and SHA256 fields")
    return _committed_bytes(root, pin["path"], commit, pin["sha256"])


def _verify_inventory(root, inventory, commit):
    A.require(type(inventory) is list and inventory, "full explicit candidate source inventory required")
    tags, paths, pins = [], set(), []
    for item in inventory:
        A.require(type(item) is dict and set(item) == {"tag", "path", "sha256"},
                  "source inventory has unaudited or missing fields")
        A.require(type(item["tag"]) is str and item["tag"] in SOURCE_TAGS,
                  "unknown candidate source inventory tag")
        A.require(item["path"] not in paths, "source inventory repeats a physical source")
        paths.add(item["path"])
        tags.append(item["tag"])
        _verify_pin(root, {"path": item["path"], "sha256": item["sha256"]}, commit)
        pins.append((item["path"], item["sha256"]))
    A.require(tuple(sorted(tags)) == tuple(sorted(SOURCE_TAGS)),
              "source inventory does not cover each required constructor-path source exactly once")
    by_tag = {item["tag"]: item for item in inventory}
    actual = {"core": A, "handoff": H, "original_source": O, "training": T,
              "paired_protocol": inspect.getmodule(load_committed_grant)}
    for tag, module in actual.items():
        path = Path(inspect.getsourcefile(module)).resolve(strict=True)
        relative = path.relative_to(root).as_posix()
        A.require(relative == by_tag[tag]["path"] and
                  sha256(path.read_bytes()).hexdigest() == by_tag[tag]["sha256"],
                  f"actual loaded {tag} is not its declared committed source")
    return tuple(pins)


def load_committed_grant(repository_root, contract_path, *, expected_commit, expected_sha256):
    """Read-only verification. This function never allocates a key or calls a factory.

    The authority artifact is a human decision record, not a cryptographic human
    identity service. It must be independently recorded and committed; this
    module cannot turn its own proposal or engineering success into approval.
    """
    root = Path(repository_root).resolve(strict=True)
    A.require(type(expected_commit) is str and _HEX40.fullmatch(expected_commit) is not None,
              "exact committed grant revision required")
    actual_root = Path(_git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
    A.require(actual_root == root, "grant verification requires the actual repository root")
    resolved_commit = _git(root, "rev-parse", f"{expected_commit}^{{commit}}").decode("ascii").strip()
    A.require(resolved_commit == expected_commit, "grant revision did not resolve to the exact commit")
    document = _read_json(_committed_bytes(root, contract_path, expected_commit, expected_sha256), "grant")
    required = {"schema", "grant_id", "status", "execution_kind", "modes", "authority",
                "source_inventory", "predecessor_gates", "seed_registry", "design", "budget"}
    A.require(set(document) == required and document.get("schema") == GRANT_SCHEMA,
              "existing engineering/F1/proposal records are not a keyed execution grant")
    A.require(type(document["grant_id"]) is str and bool(document["grant_id"]) and
              document["status"] == "AUTHORIZED" and document["execution_kind"] in EXECUTION_KINDS,
              "keyed grant is pending, unadopted, or lacks explicit scope")
    A.require(type(document["modes"]) is list and document["modes"] and
              len(set(document["modes"])) == len(document["modes"]) and
              all(mode in ("dq", "patch-adaptive") for mode in document["modes"]),
              "explicit unique source modes required")
    authority = _read_json(_verify_pin(root, document["authority"], expected_commit), "human decision")
    A.require(authority.get("schema") == "EXPLICIT_KEYED_RANGE_DECISION_V1" and
              authority.get("decision_origin") == "direct-human" and
              authority.get("approved") is True and authority.get("keyed_execution") is True and
              authority.get("execution_kind") == document["execution_kind"] and
              authority.get("grant_id") == document["grant_id"] and
              type(authority.get("human_message")) is str and bool(authority["human_message"]),
              "no matching direct-human keyed scope; old no-key authority cannot activate this entry")
    pins = [(contract_path, expected_sha256),
            (document["authority"]["path"], document["authority"]["sha256"])]
    pins.extend(_verify_inventory(root, document["source_inventory"], expected_commit))
    inventory_digest = A.digest(document["source_inventory"])
    required_gates = REQUIRED_GATES + (SCIENTIFIC_GATES if document["execution_kind"] ==
                                      "confirmatory-collection" else ())
    gates = document["predecessor_gates"]
    A.require(type(gates) is dict and set(gates) == set(required_gates),
              "candidate-specific predecessor gate set is incomplete or silently narrowed")
    for name in required_gates:
        receipt = _read_json(_verify_pin(root, gates[name], expected_commit), f"{name} receipt")
        A.require(receipt.get("gate") == name and receipt.get("status") == "PASS" and
                  receipt.get("grant_id") == document["grant_id"] and
                  receipt.get("execution_kind") == document["execution_kind"] and
                  receipt.get("candidate_source_inventory_sha256") == inventory_digest,
                  f"pending/stale/different-backend predecessor cannot qualify {name}")
        pins.append((gates[name]["path"], gates[name]["sha256"]))
    registry = _read_json(_verify_pin(root, document["seed_registry"], expected_commit), "reserved key registry")
    A.require(registry.get("schema") == "EXPLICIT_RESERVED_KEY_REGISTRY_V1" and
              registry.get("grant_id") == document["grant_id"] and
              registry.get("execution_kind") == document["execution_kind"] and
              registry.get("status") == "RESERVED_BEFORE_EXECUTION",
              "missing explicit already-reserved registry; this module never allocates keys")
    entries = registry.get("entries")
    A.require(type(entries) is list and entries and all(type(item) is dict and
              set(item) == {"seed", "mode", "state"} and type(item["seed"]) is int and item["seed"] >= 0 and
              item["mode"] in document["modes"] and item["state"] == "UNSPENT" for item in entries),
              "reserved registry must explicitly retain every unique unspent key/mode")
    A.require(len({item["seed"] for item in entries}) == len(entries), "reserved registry repeats a key")
    document = deepcopy(document)
    document["reserved_entries"] = deepcopy(entries)
    pins.append((document["seed_registry"]["path"], document["seed_registry"]["sha256"]))
    A.require(type(document["design"]) is dict and set(document["design"]) ==
              {"reference_digest", "alpha", "epsilon", "t_max", "grid", "evaluation_sample_sha256",
               "v_pre_hex", "lock_sha256"}, "full locked design declaration required")
    A.require(type(document["budget"]) is dict and set(document["budget"]) ==
              {"pairs", "roles_per_pair", "training_episodes_per_role", "checkpoints_per_role",
               "scenes_per_checkpoint"} and all(type(value) is int and value > 0
                                              for value in document["budget"].values()),
              "explicit finite execution extent required")
    token = object.__new__(VerifiedGrant)
    _GRANTS[token] = _GrantRecord(root, contract_path, expected_commit, document,
                                  A.digest(document), tuple(pins), {})
    return token


def _checked_grant(grant):
    A.require(type(grant) is VerifiedGrant and grant in _GRANTS,
              "no genuine committed keyed grant; protocol/derive/native remain uncalled")
    record = _GRANTS[grant]
    A.require(A.digest(record.document) == record.digest, "verified grant contents changed")
    for path, digest in record.pins:
        relative, physical = _relative(record.root, path)
        A.require(sha256(physical.read_bytes()).hexdigest() == digest,
                  f"grant/source/predecessor bytes changed after verification: {relative}")
    return record


def preflight(grant, request):
    """Pure rejection/extent check, before source cloning or a protocol factory."""
    record = _checked_grant(grant)
    A.require(type(request) is ProtocolRequest, "nominal explicit protocol request required")
    document = record.document
    A.require(request.execution_kind == document["execution_kind"] and request.mode in document["modes"],
              "request expands the explicit committed scope")
    A.require(type(request.seed) is int and request.seed >= 0,
              "request has no previously reserved key; allocation is not part of this module")
    A.require(any(item["seed"] == request.seed and item["mode"] == request.mode
                  for item in document["reserved_entries"]), "key/mode is absent from the reserved registry")
    A.require(request.seed not in _KEY_ATTEMPTS and request.seed not in record.attempts,
              "key already attempted, including failed construction; no retry")
    A.require(request.reference_digest == document["design"]["reference_digest"],
              "request uses a different common Q reference")
    A.require(len(record.attempts) < document["budget"]["pairs"], "committed finite pair budget exhausted")
    return {"grant_id": document["grant_id"], "execution_kind": request.execution_kind,
            "mode": request.mode, "grant_commit": record.commit,
            "candidate_source_inventory_sha256": A.digest(document["source_inventory"]),
            "preflight_only": True, "protocol_factory_called": False,
            "key_derivation_called": False, "native_called": False,
            "connected_learner_backend": False, "scientific_qualification": False}


class OwnedProtocolPlan:
    """NEW nominal plan; deliberately not v105 KeyedPlan or EngineeringPlan."""
    __slots__ = ("__weakref__",)

    def __new__(cls):
        raise A.ProtocolError("requires a successfully issued source-bound protocol entry")

    @property
    def protocol(self):
        A.require(type(self) is OwnedProtocolPlan and self in _PLANS, "issued nominal protocol plan required")
        return _checked_entry(_PLANS[self]).protocol

    @property
    def parameters(self):
        protocol = self.protocol
        return A.LearningParameters(protocol.alpha, protocol.epsilon)

    @property
    def evaluation_sample(self):
        return self.protocol.evaluation_sample

    @property
    def v_pre(self):
        return self.protocol.v_pre

    @property
    def t_max(self):
        return self.protocol.t_max

    @property
    def grid(self):
        return self.protocol.grid

    def episode(self, epoch, *, role):
        entry = _PLANS.get(self)
        record = _checked_entry(entry)
        A.require(type(role) is str and role in ROLES and type(epoch) is int and
                  0 <= epoch < record.protocol.t_max, "exact role/chronological episode domain required")
        attempted = record.requested_epochs[role]
        A.require(epoch == len(attempted) and epoch not in attempted,
                  "episode is not the next unattempted role epoch; no partial retry")
        attempted.add(epoch)  # BEFORE first original key derivation for this role.
        if epoch not in record.derived:
            record.derived[epoch] = T.ExogenousEpisode.derive(record.protocol.seed, epoch)
        episode = record.derived[epoch]
        A.require(type(episode) is T.ExogenousEpisode and episode.seed == record.protocol.seed and
                  episode.episode == epoch, "exact original shared Xi derivation required")
        adapter = object.__new__(ProtocolEpisode)
        adapter.plan, adapter.role, adapter.epoch, adapter._input = self, role, epoch, episode
        adapter.kappa, adapter.proposal, adapter.tape = episode.kappa, episode.proposal, episode.tape
        adapter.calls = []
        _EPISODES[adapter] = (entry, role, epoch, episode)
        return adapter


class ProtocolEpisode:
    """Exact original Xi adapter with per-actual-step lazy coordinate requests."""
    __slots__ = ("__weakref__", "plan", "role", "epoch", "_input", "kappa", "proposal", "tape", "calls")

    def __new__(cls, *args, **kwargs):
        raise A.ProtocolError("only an authorized plan can issue its actual original Xi adapter")

    def _check(self, i, j, c):
        A.require(type(self) is ProtocolEpisode and self in _EPISODES,
                  "unissued or reconstructed coordinate adapter")
        A.require(type(i) is int and 0 <= i < K.HORIZON and
                  type(j) is int and j in (0, 1) and type(c) is int and
                  0 <= c < T.MAX_REJECTION, "coordinate outside exact actual-step/rejection domain")
        record = _checked_entry(_PLANS.get(self.plan))
        A.require(_EPISODES[self] == (_PLANS[self.plan], self.role, self.epoch, self._input) and
                  record.derived.get(self.epoch) is self._input and
                  (self.kappa, self.proposal, self.tape) ==
                  (self._input.kappa, self._input.proposal, self._input.tape), "issued Xi fields changed")

    def coin(self, i):
        self._check(i, 0, 0)
        value = self._input.coin(i)
        self.calls.append((i, 0, 0, value))
        return value

    def chi(self, i, j, c):
        self._check(i, j, c)
        A.require(j == 1, "action rejection uses only j=1; coin has its distinct entry")
        value = self._input.chi(i, j, c)
        self.calls.append((i, j, c, value))
        return value


def prepare_owned_protocol(bound, pair, grant, request, *, protocol_factory=T.FutureTrainingProtocol):
    """Prospective activation only; no training/collector/backend invocation here."""
    checked = preflight(grant, request)  # MUST be first: absent authority causes zero factory/derive/native.
    A.require(protocol_factory is T.FutureTrainingProtocol, "only the original nominal protocol constructor is allowed")
    source, sd, native, declaration, pair_seal = H._checked_original_pair(bound, pair)
    A.require(source.mode == request.mode and pair_seal == request.expected_pair_seal and
              sd.reference.digest() == request.reference_digest,
              "actual source mode/pair/reference differs from explicit request")
    A.require(pair not in _PAIR_ATTEMPTS, "genuine whole pair was already attempted by this entry")
    record = _checked_grant(grant)
    permit = object.__new__(ActivationPermit)
    _PERMITS[permit] = (grant, bound, pair, request, checked)
    _KEY_ATTEMPTS.add(request.seed)
    _PAIR_ATTEMPTS[pair] = permit
    record.attempts[request.seed] = {"mode": request.mode, "pair_seal": pair_seal, "complete": False,
                                     "protocol_factory_called": False, "failure": None}
    attempt = record.attempts[request.seed]
    try:
        future = O.prepare_future_inputs(pair, source.original)
        fd, config = O._checked_future(future, source.original)
        template = O.base._checked_future(fd.native, config.native).template
        A.require(type(template) is MappingProxyType, "source has no complete original locked future template")
        design, budget = record.document["design"], record.document["budget"]
        actual_design = {"reference_digest": sd.reference.digest(), "alpha": A.wire(template["alpha"]),
                         "epsilon": A.wire(template["epsilon"]), "t_max": template["T"],
                         "grid": list(template["grid"]), "evaluation_sample_sha256": A.digest(A.wire(template["sample"])),
                         "v_pre_hex": template["v_pre"].hex(), "lock_sha256": template["lock_sha256"]}
        A.require(actual_design == design and tuple(template["grid"]) == tuple(range(template["T"] + 1)),
                  "grant does not match this exact full integer-grid shared locked design")
        A.require(budget["roles_per_pair"] == 2 and budget["training_episodes_per_role"] == template["T"] and
                  budget["checkpoints_per_role"] == template["T"] + 1 and
                  budget["scenes_per_checkpoint"] == len(template["sample"]), "declared finite extent differs from source")
        attempt["protocol_factory_called"] = True
        protocol = protocol_factory(request.seed, template["alpha"], template["epsilon"], template["T"],
                                    tuple(template["grid"]), tuple(template["sample"]), template["v_pre"])
        A.require(type(protocol) is T.FutureTrainingProtocol and protocol.seed == request.seed and
                  protocol.alpha == template["alpha"] and protocol.epsilon == template["epsilon"] and
                  protocol.t_max == template["T"] and protocol.grid == tuple(template["grid"]) and
                  protocol.evaluation_sample == tuple(template["sample"]) and
                  protocol.v_pre.hex() == template["v_pre"].hex(),
                  "original nominal protocol fields differ from the exact shared design")
        starts = tuple(O.clone_future_start(future, source.original, role=role) for role in ROLES)
        A.require(starts[0] is not starts[1] and all(start is not sd.pre and
                  all(start is not clone for clone in native.clones) and
                  A.stores(start) == A.stores(immediate) for start, immediate in zip(starts, native.clones)),
                  "distinct complete protected original immediate role starts required")
        origin = {"declaration": deepcopy(declaration), "pair_seal": pair_seal, "mode_before_arms": source.mode,
                  "future": O.future_audit(future, source.original), "initial_starts": [A.stores(s) for s in starts],
                  "protocol": A.wire(protocol), "grant_sha256": record.digest, "grant_commit": record.commit,
                  "execution_kind": request.execution_kind, "connected_learner_backend": False}
        entry, plan = object.__new__(OwnedProtocolEntry), object.__new__(OwnedProtocolPlan)
        _ENTRIES[entry] = _EntryRecord(grant, permit, request, bound, pair, future, protocol, plan, starts,
                                       deepcopy(origin), A.digest(origin), {role: set() for role in ROLES}, {}, set())
        _PLANS[plan] = entry
        _checked_entry(entry)
        attempt["complete"] = True
        return entry
    except BaseException as error:
        attempt["failure"] = {"type": type(error).__name__, "text": str(error)}
        raise


def _checked_entry(entry):
    A.require(type(entry) is OwnedProtocolEntry and entry in _ENTRIES,
              "partial/unissued/serialized entry has no shared keyed protocol")
    record = _ENTRIES[entry]
    grant = _checked_grant(record.grant)
    source, sd, native, declaration, pair_seal = H._checked_original_pair(record.bound, record.pair)
    permit_binding = _PERMITS.get(record.permit)
    A.require(type(record.permit) is ActivationPermit and type(permit_binding) is tuple and
              permit_binding[:4] == (record.grant, record.bound, record.pair, record.request) and
              _PAIR_ATTEMPTS.get(record.pair) is record.permit and record.request.seed in _KEY_ATTEMPTS,
              "activation permit/source/pair/key ownership changed")
    A.require(A.digest(record.origin) == record.digest and record.origin["declaration"] == declaration and
              record.origin["pair_seal"] == pair_seal and record.origin["mode_before_arms"] == source.mode and
              record.origin["future"] == O.future_audit(record.future, source.original) and
              record.origin["grant_sha256"] == grant.digest and A.wire(record.protocol) == record.origin["protocol"],
              "full original source/immediate/shared protocol grant binding changed")
    A.require(type(record.protocol) is T.FutureTrainingProtocol and len(record.starts) == 2 and
              record.starts[0] is not record.starts[1] and all(A.stores(start) == expected == A.stores(immediate)
                  for start, expected, immediate in zip(record.starts, record.origin["initial_starts"], native.clones)),
              "protected full original role starts changed or aliased")
    return record


def protocol_plan(entry):
    return _checked_entry(entry).plan


def clone_role_start(entry, *, role):
    """Full fresh R start only. Explicit L0 belongs to a future versioned backend."""
    record = _checked_entry(entry)
    A.require(type(role) is str and role in ROLES, "exact registered source role required")
    A.require(role not in record.exported_roles, "role start already exported; no repeat constructor")
    record.exported_roles.add(role)  # BEFORE cloning; a failed export cannot be retried.
    return record.starts[ROLES.index(role)].clone()


def grant_audit(grant):
    record = _checked_grant(grant)
    return deepcopy({"grant_id": record.document["grant_id"], "grant_commit": record.commit,
                     "grant_sha256": record.digest, "execution_kind": record.document["execution_kind"],
                     "required_predecessors": list(REQUIRED_GATES), "attempts": record.attempts,
                     "key_allocator_present": False, "connected_learner_backend": False,
                     "scientific_qualification": False})


def activation_audit(entry):
    record = _checked_entry(entry)
    return deepcopy({"origin": record.origin, "origin_sha256": record.digest,
                     "requested_epochs": {role: sorted(epochs) for role, epochs in record.requested_epochs.items()},
                     "derived_epoch_indices": sorted(record.derived), "grant": grant_audit(record.grant),
                     "exported_roles": sorted(record.exported_roles),
                     "connected_learner_backend": False, "scientific_qualification": False})
