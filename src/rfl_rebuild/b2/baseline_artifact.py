"""CF-5 deterministic shards. Validation is separate from all design selection.

The digest covers uncompressed canonical JSONL. The index is published last;
an interrupted writer leaves incomplete shards, never a valid-looking index.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b1.tier import DQ_DOMAIN, X_DOMAIN, P_DOMAIN
from rfl_rebuild.b2.acquisition import RunMaterial, _require_seeds
from rfl_rebuild.b2.evalorder import prefix, prefix_digest
from rfl_rebuild.b2.unaffected import CHANNELS, CreditedSite, credited_domain
from rfl_rebuild.env.kernel import State, ControllerSite
from rfl_rebuild.learner.store import DecisionAddress

SCHEMA = "f0-master-incidence-v1"


def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _require(condition, message):
    if not condition:
        raise ProtocolError(message)


def _natural(value):
    return type(value) is int and value >= 0


def _site_key(site):
    if site.channel == "P":
        return [site.address]
    a, s = site.address, site.address.state
    fields = [s.x, s.y, s.t, s.kappa, s.phi]
    return fields + ([a.z, a.m] if site.channel == "D_Q" else [a.cmd])


def _site(arch, key):
    _require(type(key) is list and len(key) == {"D_Q": 7, "X": 6, "P": 1}[arch]
             and all(type(x) is int for x in key), "malformed credited-site key")
    if arch == "P":
        address = key[0]
    elif arch == "D_Q":
        address = DecisionAddress(State(*key[:5]), *key[5:])
    else:
        address = ControllerSite(State(*key[:5]), key[5])
    {"D_Q": DQ_DOMAIN, "X": X_DOMAIN, "P": P_DOMAIN}[arch].require_credited(address)
    return CreditedSite(arch, address)


@lru_cache(maxsize=2)
def _fixed_domain(arch):
    return credited_domain(arch, None)


def record_from_material(run):
    domains = {a: [_site_key(s) for s in run.domains[a]] for a in CHANNELS}
    consulted = {}
    for arch in CHANNELS:
        ordinal = {site: i for i, site in enumerate(run.domains[arch])}
        consulted[arch] = sorted([[ordinal[s], list(indices)]
                                 for s, indices in run.consulted[arch].items()])
    return {"seed": run.seed, "episode": run.episode, "levels": list(run.levels),
            "success": list(run.success), "domains": domains, "consulted": consulted,
            "uncontacted": dict(run.uncontacted), "outside_domain": dict(run.outside_domain)}


def material_from_record(record, *, seed, episode, bank_size):
    _require(type(record) is dict and set(record) == {
        "seed", "episode", "levels", "success", "domains", "consulted", "uncontacted",
        "outside_domain"}, "record field set mismatch")
    _require(_natural(record["seed"]) and _natural(record["episode"])
             and (record["seed"], record["episode"]) == (seed, episode), "record axis mismatch")
    levels, success = record["levels"], record["success"]
    _require(type(levels) is list and len(levels) == bank_size
             and all(type(v) is float and math.isfinite(v) for v in levels), "invalid level vector")
    _require(type(success) is list and len(success) == bank_size
             and all(type(v) is bool for v in success), "invalid success vector")
    for name in ("domains", "consulted", "uncontacted", "outside_domain"):
        _require(type(record[name]) is dict and set(record[name]) == set(CHANNELS),
                 f"{name} channel set mismatch")
    domains, consulted = {}, {}
    for arch in CHANNELS:
        keys = record["domains"][arch]
        _require(type(keys) is list and bool(keys), "empty or malformed credited domain")
        domain = tuple(_site(arch, k) for k in keys)
        _require(len(set(domain)) == len(domain), "duplicate credited site")
        if arch in ("D_Q", "P"):
            _require(domain == _fixed_domain(arch), "fixed credited domain was narrowed or reordered")
        incidence = record["consulted"][arch]
        _require(type(incidence) is list, "malformed incidence")
        previous, rows = -1, {}
        for pair in incidence:
            _require(type(pair) is list and len(pair) == 2, "malformed incidence pair")
            ordinal, indices = pair
            _require(_natural(ordinal) and previous < ordinal < len(domain),
                     "incidence domain ordinal out of order or bounds")
            _require(type(indices) is list and bool(indices)
                     and all(_natural(i) and i < bank_size for i in indices)
                     and indices == sorted(set(indices)), "invalid scene incidence indices")
            rows[domain[ordinal]] = tuple(indices)
            previous = ordinal
        flag = record["uncontacted"][arch]
        _require(type(flag) is bool and flag == (len(rows) < len(domain)),
                 "uncontacted flag disagrees with incidence")
        _require(_natural(record["outside_domain"][arch]), "invalid outside-domain count")
        domains[arch], consulted[arch] = domain, MappingProxyType(rows)
    return RunMaterial(seed, episode, tuple(levels), tuple(success), MappingProxyType(consulted),
                       MappingProxyType(domains), MappingProxyType(record["uncontacted"]),
                       MappingProxyType(record["outside_domain"]))


def _pair_count(run):
    return sum(len(indices) for arch in CHANNELS for indices in run.consulted[arch].values())


def _aggregate(shards):
    return digest(canonical_bytes([[r["seed"], r["sha256"]] for r in shards]))


def write_acquisition(index_path, *, plan, seeds, records, constants, execution, role):
    """Consume one record at a time, refusing existing outputs and incomplete axes."""
    path = Path(index_path)
    seeds = _require_seeds(seeds)
    bank_size = len(plan.evaluation_bank)
    _require(plan.evaluation_bank == prefix(bank_size), "artifact requires the balanced bank prefix")
    _require(type(constants) is dict and type(execution) is dict, "missing provenance objects")
    _require(role in ("OPERATIONAL_REHEARSAL", "DEVELOPMENT_BASELINE"), "unknown artifact role")
    # Validate serializability before creating anything or consuming the generator.
    canonical_bytes([constants, execution])
    if path.exists():
        raise FileExistsError(path)
    folder = path.with_suffix("")
    folder.mkdir(parents=True, exist_ok=False)
    iterator, shards = iter(records), []
    for seed in seeds:
        shard = folder / f"seed-{seed:06d}.jsonl.gz"
        sha, pairs, count = hashlib.sha256(), 0, 0
        with shard.open("xb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz:
            for episode in range(plan.acquisition_cap + 1):
                try:
                    run = next(iterator)
                except StopIteration as exc:
                    raise ProtocolError("acquisition ended before the declared axis") from exc
                record = record_from_material(run)
                checked = material_from_record(record, seed=seed, episode=episode, bank_size=bank_size)
                data = canonical_bytes(record)
                gz.write(data)
                sha.update(data)
                pairs += _pair_count(checked)
                count += 1
        shards.append({"seed": seed, "path": shard.relative_to(path.parent).as_posix(),
                       "sha256": sha.hexdigest(), "records": count, "pairs": pairs})
    sentinel = object()
    _require(next(iterator, sentinel) is sentinel, "acquisition exceeded the declared axis")
    index = {"schema": SCHEMA, "role": role, "seeds": list(seeds),
             "episodes": list(range(plan.acquisition_cap + 1)), "bank_size": bank_size,
             "bank_digest": prefix_digest(bank_size), "constants": constants, "execution": execution,
             "shards": shards, "ordered_shard_digest": _aggregate(shards),
             "records": sum(s["records"] for s in shards), "pairs": sum(s["pairs"] for s in shards)}
    with path.open("xb") as out:
        out.write(canonical_bytes(index))
    return index


def _json(data):
    def pairs_hook(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, f"duplicate JSON key {key!r}")
            result[key] = value
        return result
    try:
        value = json.loads(data, object_pairs_hook=pairs_hook)
        _require(canonical_bytes(value) == data, "noncanonical JSON bytes")
        return value
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError(f"invalid canonical JSON: {exc}") from exc


def read_index(index_path):
    """Validate index structure and path confinement, without inspecting metrics."""
    path = Path(index_path)
    index = _json(path.read_bytes())
    _require(type(index) is dict and set(index) == {
        "schema", "role", "seeds", "episodes", "bank_size", "bank_digest", "constants", "execution",
        "shards", "ordered_shard_digest", "records", "pairs"}, "index field set mismatch")
    _require(index["schema"] == SCHEMA, "unsupported baseline schema")
    _require(index["role"] in ("OPERATIONAL_REHEARSAL", "DEVELOPMENT_BASELINE"), "unknown role")
    _require(type(index["seeds"]) is list, "invalid seed list")
    seeds = _require_seeds(index["seeds"])
    episodes = index["episodes"]
    _require(type(episodes) is list and len(episodes) >= 2
             and all(_natural(e) for e in episodes)
             and episodes == list(range(len(episodes))), "incomplete episode axis")
    n = index["bank_size"]
    _require(type(n) is int and 1 <= n <= 5760, "invalid bank size")
    _require(index["bank_digest"] == prefix_digest(n), "bank digest mismatch")
    _require(type(index["constants"]) is dict and type(index["execution"]) is dict,
             "missing provenance objects")
    shards = index["shards"]
    _require(type(shards) is list and len(shards) == len(seeds), "shard count mismatch")
    for seed, shard in zip(seeds, shards):
        _require(type(shard) is dict and set(shard) == {"seed", "path", "sha256", "records", "pairs"},
                 "shard descriptor field set mismatch")
        expected = f"{path.stem}/seed-{seed:06d}.jsonl.gz"
        _require(_natural(shard["seed"]) and shard["seed"] == seed and shard["path"] == expected,
                 "shard path or ordered seed mismatch")
        resolved = (path.parent / shard["path"]).resolve()
        _require(resolved.is_relative_to(path.parent.resolve()), "shard path escapes the index directory")
        _require(_natural(shard["records"]) and shard["records"] == len(episodes)
                 and _natural(shard["pairs"]), "invalid shard counts")
        h = shard["sha256"]
        _require(type(h) is str and len(h) == 64 and all(c in "0123456789abcdef" for c in h),
                 "invalid SHA-256")
    _require(index["ordered_shard_digest"] == _aggregate(shards), "ordered-shard digest mismatch")
    for name in ("records", "pairs"):
        _require(_natural(index[name]) and index[name] == sum(s[name] for s in shards),
                 f"aggregate {name} count mismatch")
    return index


def _shard_records(path, descriptor, index):
    sha, pairs, count = hashlib.sha256(), 0, 0
    try:
        with gzip.open(path.parent / descriptor["path"], "rb") as stream:
            for episode, data in enumerate(stream):
                _require(episode < len(index["episodes"]), "extra record in shard")
                sha.update(data)
                run = material_from_record(_json(data), seed=descriptor["seed"], episode=episode,
                                           bank_size=index["bank_size"])
                count += 1
                pairs += _pair_count(run)
                yield run
    except (OSError, EOFError) as exc:
        raise ProtocolError(f"unreadable baseline shard: {exc}") from exc
    _require(count == descriptor["records"] and pairs == descriptor["pairs"], "shard counts mismatch")
    _require(sha.hexdigest() == descriptor["sha256"], "shard SHA-256 mismatch")


def verify_acquisition(index_path):
    """Full pass: every shard hash, axis and incidence must pass before selection."""
    path = Path(index_path)
    index = read_index(path)
    for descriptor in index["shards"]:
        for _run in _shard_records(path, descriptor, index):
            pass
    return index


def iter_verified_material(index_path):
    """No values are yielded until ALL shards have passed the verification pass.

    The read pass rechecks digests too. A selector must finish consumption before
    committing an output; a concurrently changed shard must abort that transaction.
    """
    path = Path(index_path)
    index = verify_acquisition(path)
    for descriptor in index["shards"]:
        yield from _shard_records(path, descriptor, index)
