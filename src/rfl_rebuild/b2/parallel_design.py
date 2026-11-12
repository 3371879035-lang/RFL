"""A96 source-inventoried exact per-seed selector backend with ordered joins."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor, as_completed
import math
import multiprocessing
import os
from pathlib import Path
import time
from rfl_rebuild.b2 import baseline_artifact as ba, design_lock as dl, design_selection as ds
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.f0_stages import require, source_inventory, load_manifest
from rfl_rebuild.b2.parallel_validation import verify_parallel, file_digest

MAX_WORKERS = 16
STATE_FIELDS = {"seed","records","curve","prefix","collateral","spreads","coverage"}


def summarize_records(records, *, seed, cap, sample, calibration, progress=False):
    """Identical original per-record laws and original ascending bank order."""
    n, c = ds.PrefixSelector(), ds.CollateralSelector(sample,calibration=calibration)
    curve=[]
    for e,run in enumerate(records):
        require(e <= cap and (run.seed,run.episode) == (seed,e),"seed worker axis mismatch")
        n.update(run.levels)
        c.update(run)
        curve.append(ds.mean(run.levels))
        if progress and (e+1) % 25 == 0:
            print(f"DESIGN_PROGRESS seed={seed} pid={os.getpid()} records={e+1}",flush=True)
    require(len(curve) == cap+1 and n.records == c.records == cap+1,"seed worker incomplete")
    return {"seed":seed,"records":len(curve),"curve":curve,
        "prefix":[[size,n.metrics[size]] for size in ds.SIZES],
        "collateral":[[r,c.metrics[r]] for r in ds.REFINEMENTS],
        "spreads":[[r,[[value,count] for value,count in sorted(c.spreads[r].items())]] for r in ds.REFINEMENTS],
        "coverage":[[a,r,[[base,count,multiplicity] for (base,count),multiplicity in sorted(c.coverage[a,r].items())]]
                    for a in ds.CHANNELS for r in ds.REFINEMENTS]}


def _metric(value):
    require(value is None or type(value) is float and math.isfinite(value) and value >= 0,
            "invalid selector maximum/undefined state")
    return value


def join_states(states, *, seeds, cap, sample, calibration):
    """Deterministic seed-order max/None and exact INTEGER Counter joins only."""
    seeds=tuple(seeds)
    require(len(states) == len(seeds) and len(set(seeds)) == len(seeds),"missing/duplicate seed summary")
    n,c=ds.PrefixSelector(),ds.CollateralSelector(sample,calibration=calibration)
    curves=[]
    for seed,state in zip(seeds,states):
        require(type(state) is dict and set(state) == STATE_FIELDS and type(state["seed"]) is int
                and state["seed"] == seed and type(state["records"]) is int
                and state["records"] == cap+1,"summary field/axis/count mismatch")
        curve=ds._finite(state["curve"])
        require(len(curve) == cap+1,"summary curve axis incomplete")
        require([x[0] for x in state["prefix"]] == list(ds.SIZES) and
                [x[0] for x in state["collateral"]] == list(ds.REFINEMENTS),"summary selector order mismatch")
        for size,value in state["prefix"]:
            value=_metric(value)
            n.metrics[size] = None if n.metrics[size] is None or value is None else max(n.metrics[size],value)
        for r,value in state["collateral"]:
            value=_metric(value)
            c.metrics[r] = None if c.metrics[r] is None or value is None else max(c.metrics[r],value)
        require([x[0] for x in state["spreads"]] == list(ds.REFINEMENTS),"spread family mismatch")
        for r,population in state["spreads"]:
            seen=set()
            for value,count in population:
                require(type(value) is float and math.isfinite(value) and value >= 0
                        and type(count) is int and count > 0 and value not in seen,"invalid spread multiplicity")
                seen.add(value)
                c.spreads[r][value] += count
        require([(x[0],x[1]) for x in state["coverage"]] ==
                [(a,r) for a in ds.CHANNELS for r in ds.REFINEMENTS],"coverage family mismatch")
        for a,r,population in state["coverage"]:
            seen=set()
            for base,count,multiplicity in population:
                key=(base,count)
                require(type(base) is int and type(count) is int and 0 <= count <= base <= len(sample)
                        and type(multiplicity) is int and multiplicity > 0 and key not in seen,
                        "invalid coverage multiplicity")
                seen.add(key)
                c.coverage[a,r][key] += multiplicity
        n.records += state["records"]
        c.records += state["records"]
        curves.append(list(curve))
    return n,c,curves


def select_from_states(states, *, seeds, cap, sample, pre_level, calibration):
    """Same original T/N/C/G/R ordering, rejection priority and original functions."""
    seeds,sample=tuple(seeds),tuple(sample)
    require(bool(seeds) and len(set(seeds)) == len(seeds) and all(type(s) is int and s >= 0 for s in seeds)
            and type(cap) is int and cap >= 1 and len(sample) == 1024,"invalid master design envelope")
    ds._finite((pre_level,))
    n,c,curves=join_states(states,seeds=seeds,cap=cap,sample=sample,calibration=calibration)
    return ds.select_master_curves(curves, cap=cap, pre_level=pre_level,
                                   n_result=n.result(), c_result=c.result())



def _seed_worker(path,descriptor,index,calibration,folder):
    seed=descriptor["seed"]
    started=time.perf_counter()
    print(f"DESIGN_STARTED seed={seed} pid={os.getpid()}",flush=True)
    state=summarize_records(ba._shard_records(Path(path),descriptor,index),seed=seed,
        cap=len(index["episodes"])-1,sample=prefix(1024),calibration=calibration,progress=True)
    # _shard_records has been exhausted: actual canonical hash/count/axis laws passed.
    receipt={"seed":seed,"records":descriptor["records"],"pairs":descriptor["pairs"],
        "uncompressed_shard_sha256":descriptor["sha256"],"summary_sha256":ba.digest(ba.canonical_bytes(state)),
        "pid":os.getpid(),"elapsed_s":time.perf_counter()-started,
        "parser":"original-_shard_records","arithmetic":"original-per-record-selector-updates"}
    if folder is not None:
        dl.publish_new(Path(folder) / f"seed-{seed}.completed.json",receipt)
    print(f"DESIGN_COMPLETED seed={seed} pid={os.getpid()} records={state['records']}",flush=True)
    return state,receipt


def calculate_parallel(index_path, *, seeds, cap, sample, pre_level, calibration, validator,guard,folder):
    """Fresh all-shard prevalidation, parallel computation, then ordered join.

    No worker selector runs until fresh ALL shards have passed, not merely its
    own shard. Worker reads then revalidate their hashes as in the original iterator.
    """
    guard()
    index=validator(index_path)
    require(tuple(index["seeds"]) == tuple(seeds) and index["episodes"] == list(range(cap+1)) and
            index["bank_size"] == 1024 and tuple(sample) == prefix(1024),"analysis stream envelope differs")
    ds._finite((pre_level,))
    ds.require_calibration(calibration)
    folder=Path(folder)
    folder.mkdir(exist_ok=False)
    dl.publish_new(folder / "reservation.json",{"status":"RESERVED_NOT_COMPLETE","seeds":list(seeds),
        "index_sha256":ba.digest(Path(index_path).read_bytes()),"max_workers":16,"automatic_retry":False})
    compressed={s["path"]:file_digest(Path(index_path).parent / s["path"]) for s in index["shards"]}
    index_sha=ba.digest(Path(index_path).read_bytes())
    guard()
    pool=ProcessPoolExecutor(max_workers=min(MAX_WORKERS,len(seeds)),mp_context=multiprocessing.get_context("spawn"))
    results={}
    started=time.perf_counter()
    metadata={k:index[k] for k in ("episodes","bank_size")}
    try:
        futures={pool.submit(_seed_worker,str(Path(index_path).resolve()),s,metadata,calibration,str(folder)):s
                 for s in index["shards"]}
        for future in as_completed(futures):
            s=futures[future]
            state,receipt=future.result()
            require(state["seed"] == receipt["seed"] == s["seed"] and
                    receipt["records"] == s["records"] == state["records"] and
                    receipt["pairs"] == s["pairs"] and receipt["uncompressed_shard_sha256"] == s["sha256"]
                    and receipt["summary_sha256"] == ba.digest(ba.canonical_bytes(state)),"worker summary binding differs")
            require(s["seed"] not in results,"duplicate completed analysis seed")
            results[s["seed"]]=(state,receipt)
    except BaseException:
        pool.terminate_workers()
        raise
    else:
        pool.shutdown(wait=True)
    require(set(results) == set(seeds),"incomplete analysis seed population")
    require(ba.digest(Path(index_path).read_bytes()) == index_sha and compressed ==
            {s["path"]:file_digest(Path(index_path).parent / s["path"]) for s in index["shards"]},
            "analysis input bytes changed")
    guard()
    states=[results[seed][0] for seed in seeds]
    result=select_from_states(states,seeds=seeds,cap=cap,sample=sample,pre_level=pre_level,calibration=calibration)
    guard()
    dl.publish_new(folder / "completed.json",{"status":"ALL_SEEDS_CALCULATED_ORDERED_JOIN_COMPLETE",
        "seeds":list(seeds),"records":index["records"],"pairs":index["pairs"],"index_sha256":index_sha,
        "compressed_sha256":compressed,"workers":[results[seed][1] for seed in seeds],
        "design_result_sha256":ba.digest(ba.canonical_bytes(result)),"elapsed_s":time.perf_counter()-started,
        "max_workers":16,"start_method":"spawn","join_order":"frozen-seed-order",
        "floating_moment_reduction":False,"partial_lock_published":False})
    return result

class ParallelExecutor:
    """Every full pass is fresh and receipted; no cached validation or old PASS."""
    def __init__(self, root, folder, manifest_path):
        self.root, self.folder, self.manifest_path = Path(root).resolve(), Path(folder).resolve(), Path(manifest_path).resolve()
        require(self.folder.is_relative_to(self.root), "parallel execution evidence outside checkout")
        self.folder.mkdir(parents=True, exist_ok=False)
        self.sources = source_inventory(root)
        self.manifest, self.identity = load_manifest(root, manifest_path, "design_lock")
        self.calls = 0
        dl.publish_new(self.folder / "reservation.json", {
            "measurement_profile": dl.MEASUREMENT_PROFILE, "status": "RESERVED_NOT_COMPLETE",
            "sources_digest": ba.digest(ba.canonical_bytes(self.sources)),
            "manifest_sha256": self.identity, "automatic_retry": False, "max_workers": 16})

    def guard(self):
        require(source_inventory(self.root) == self.sources, "parallel instrument source drift")
        _, identity = load_manifest(self.root, self.manifest_path, "design_lock")
        require(identity == self.identity, "parallel manifest/gate drift")

    def verify(self, index_path):
        self.guard()
        self.calls += 1
        folder = self.folder / f"validation-pass-{self.calls:03d}"
        folder.mkdir(exist_ok=False)
        dl.publish_new(folder / "reservation.json", {"status": "RESERVED_NOT_COMPLETE",
            "index_sha256": ba.digest(Path(index_path).read_bytes()), "automatic_retry": False})
        result = verify_parallel(index_path, progress_folder=folder / "workers")
        self.guard()
        dl.publish_new(folder / "completed.json", result)
        return ba.read_index(index_path)

    def derive(self, index_path, **kwargs):
        return calculate_parallel(index_path, validator=self.verify, guard=self.guard,
                                  folder=self.folder / "parallel_design", **kwargs)
