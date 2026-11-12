"""A62 — dense reusable runtime support, with a manifest that refuses to load.

The full support is 1,038,960 canonical worlds in 547 rows-only blocks. Keeping
a million ``LatentCase`` objects, a million tuples and million-key dicts resident
is not viable, so the storage layer is dense integer arrays and a ``LatentCase``
is rebuilt on demand:

    world_id -> canonical fields -> LatentCase

Semantic layer unchanged: ``BeliefState`` is still ``{block_id: int bitset}`` and
the three frozen operations are the same, so :mod:`belief` stays the reference
implementation and this is a storage swap underneath it.

**A loader must refuse, not trust.** A cache is only valid for the exact kernel,
fire definition and DGP that produced it. Checking ``n_worlds`` alone would let a
changed environment run against a stale million-world cache and produce numbers
that look fine.

**The committed ``global_support.json`` is NOT this.** It is a stale validation
artifact; runners read the manifest-checked cache and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from array import array
from dataclasses import dataclass

SCHEMA_VERSION = 1
ATOM_SCHEMA = ("kappa", "phase", "error_flag", "cause_rank", "proposal",
               "Z_code", "p0", "p1", "p2", "p3", "p4", "block_id", "fire_code")


class SupportMismatch(Exception):
    """Raised instead of silently loading a cache that does not match."""


@dataclass(frozen=True)
class Manifest:
    schema_version: int
    n_worlds: int
    n_rows_blocks: int
    atom_schema: tuple
    dgp_fingerprint: str
    kernel_fingerprint: str
    weight_sum: float
    content_digest: str

    def to_json(self) -> dict:
        return {"schema_version": self.schema_version,
                "n_worlds": self.n_worlds,
                "n_rows_blocks": self.n_rows_blocks,
                "atom_schema": list(self.atom_schema),
                "dgp_fingerprint": self.dgp_fingerprint,
                "kernel_fingerprint": self.kernel_fingerprint,
                "weight_sum": self.weight_sum,
                "content_digest": self.content_digest}


_DENSE_FIELDS = ("kappa", "phase", "error_flag", "cause_rank", "proposal",
                 "Z_code", "p0", "p1", "p2", "p3", "p4", "block_id", "fire_code")


class DenseSupport:
    """Integer-array storage. ``world_id`` is the array index."""

    def __init__(self, *, manifest: Manifest, fields: dict, weights,
                 block_of_world, worlds_of_block, contexts):
        self.manifest = manifest
        self._f = fields
        self._w = weights
        self._block_of = block_of_world
        self._worlds_of = worlds_of_block
        self._contexts = contexts          # (context_id, Z_code, params) -> w_id

    def __len__(self) -> int:
        return self.manifest.n_worlds

    @property
    def n_blocks(self) -> int:
        return self.manifest.n_rows_blocks

    def field(self, world_id: int, name: str) -> int:
        return self._f[name][world_id]

    def weight(self, world_id: int) -> float:
        return self._w[world_id]

    def block_members(self, block_id: int) -> tuple:
        return tuple(self._worlds_of[block_id])

    def full_mask(self, block_id: int) -> int:
        return (1 << len(self._worlds_of[block_id])) - 1

    def bit_of(self, world_id: int) -> int:
        """Position of a world inside its own block."""
        return self._worlds_of[self._block_of[world_id]].index(world_id)

    def global_prior(self):
        from .belief import BeliefState
        return BeliefState(active_blocks={b: self.full_mask(b)
                                          for b in self._worlds_of})

    def rows_prior(self, block_id: int):
        from .belief import BeliefState
        return BeliefState(active_blocks={block_id: self.full_mask(block_id)})

    def build_rows_index(self, probe, sample_per_block: int = 3) -> dict:
        """``repr(factual rows) -> block_id``, derived from the cache itself.

        Needed so a method can locate its rows block from ``FactualEvidence``
        ALONE, instead of the runner handing it the true world's ``block_id``.
        Those are numerically equivalent and semantically not: the whole point of
        the dev_v1 fix is that ``H_seq`` is built from learner-visible evidence,
        not from truth.

        Costs one representative probe per block (547), not a cache rebuild --
        ``worlds_of_block`` is already on disk. ``sample_per_block`` extra worlds
        per block are checked to confirm the block really is rows-homogeneous;
        if it is not, the index is not well defined and we refuse rather than
        return a map that silently picks one.
        """
        idx: dict = {}
        for bid, members in self._worlds_of.items():
            key = None
            for wid in members[:max(1, sample_per_block)]:
                rows = probe.rows_of(self, wid)
                k = repr(rows)
                if key is None:
                    key = k
                elif k != key:
                    raise SupportMismatch(
                        f"block {bid} is not rows-homogeneous: {k} vs {key}")
            idx.setdefault(key, bid)
        if len(idx) != len(self._worlds_of):
            raise SupportMismatch(
                f"rows index collapsed {len(self._worlds_of)} blocks into "
                f"{len(idx)} signatures; the map would be ambiguous")
        return idx

    def find_world(self, context_id: int, Z_code: int, params: tuple):
        """Sample -> support lookup: bucketed by context, local binary search.

        A million-key tuple dict is what this avoids. There are only 5760
        contexts, so the bucket is small and the search is local.
        """
        bucket = self._contexts.get(context_id)
        if not bucket:
            return None
        keys, ids = bucket
        key = (Z_code,) + tuple(params)
        import bisect
        i = bisect.bisect_left(keys, key)
        if i < len(keys) and keys[i] == key:
            return ids[i]
        return None

    def marginals(self, belief) -> tuple:
        acc = [0.0] * 5
        tot = 0.0
        for bid, mask in belief.active_blocks.items():
            for bit, wid in enumerate(self._worlds_of[bid]):
                if not (mask >> bit) & 1:
                    continue
                w = self._w[wid]
                tot += w
                fc = self._f["fire_code"][wid]
                for i in range(5):
                    if (fc >> i) & 1:
                        acc[i] += w
        return tuple(0.0 for _ in range(5)) if tot <= 0 else tuple(a / tot for a in acc)

    # ---- persistence ----------------------------------------------------- #
    def save(self, path: pathlib.Path) -> None:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"manifest": self.manifest.to_json(),
                   "fields": {k: list(v) for k, v in self._f.items()},
                   "weights": list(self._w),
                   "block_of_world": list(self._block_of),
                   "worlds_of_block": {str(k): list(v)
                                       for k, v in self._worlds_of.items()},
                   "contexts": {str(k): [list(v[0]), list(v[1])]
                                for k, v in self._contexts.items()}}
        path.with_suffix(".json").write_text(json.dumps(payload), encoding="utf-8")

    @staticmethod
    def load(path: pathlib.Path, *, expected_kernel_fingerprint: str,
             expected_dgp_fingerprint: str) -> "DenseSupport":
        """Load only if the manifest matches, else REFUSE."""
        raw = json.loads(pathlib.Path(path).with_suffix(".json")
                         .read_text(encoding="utf-8"))
        m = raw["manifest"]
        if m.get("schema_version") != SCHEMA_VERSION:
            raise SupportMismatch(f"schema_version {m.get('schema_version')} != "
                                  f"{SCHEMA_VERSION}")
        if tuple(m.get("atom_schema", ())) != ATOM_SCHEMA:
            raise SupportMismatch("atom_schema mismatch")
        if m.get("kernel_fingerprint") != expected_kernel_fingerprint:
            raise SupportMismatch(
                f"kernel changed: cache {m.get('kernel_fingerprint')} vs "
                f"current {expected_kernel_fingerprint}")
        if m.get("dgp_fingerprint") != expected_dgp_fingerprint:
            raise SupportMismatch("DGP semantics changed since this cache")
        if abs(float(m.get("weight_sum", 0.0)) - 1.0) > 1e-9:
            raise SupportMismatch("weights do not sum to 1")

        man = Manifest(schema_version=m["schema_version"], n_worlds=m["n_worlds"],
                       n_rows_blocks=m["n_rows_blocks"],
                       atom_schema=tuple(m["atom_schema"]),
                       dgp_fingerprint=m["dgp_fingerprint"],
                       kernel_fingerprint=m["kernel_fingerprint"],
                       weight_sum=float(m["weight_sum"]),
                       content_digest=m["content_digest"])
        fields = {k: array("i", v) for k, v in raw["fields"].items()}
        if len(fields["Z_code"]) != man.n_worlds:
            raise SupportMismatch("field length does not match manifest n_worlds")
        w = array("d", raw["weights"])
        if len(w) != man.n_worlds:
            raise SupportMismatch("weight length does not match manifest")
        bw = array("i", raw["block_of_world"])
        wob = {int(k): tuple(v) for k, v in raw["worlds_of_block"].items()}
        if len(wob) != man.n_rows_blocks:
            raise SupportMismatch("block count does not match manifest")
        ctx = {int(k): (tuple(tuple(x) for x in v[0]), tuple(v[1]))
               for k, v in raw["contexts"].items()}
        # content digest is over the dense arrays, so a silently truncated or
        # reordered cache is caught even when every scalar field is present
        h = hashlib.sha256()
        for k in _DENSE_FIELDS:
            h.update(array("i", fields[k]).tobytes())
        if h.hexdigest()[:16] != man.content_digest:
            raise SupportMismatch("content digest mismatch")
        return DenseSupport(manifest=man, fields=fields, weights=w,
                            block_of_world=bw, worlds_of_block=wob,
                            contexts=ctx)


def content_digest(fields: dict) -> str:
    h = hashlib.sha256()
    for k in _DENSE_FIELDS:
        h.update(array("i", fields[k]).tobytes())
    return h.hexdigest()[:16]
