"""A96 source-inventoried full parallel validation; original parser exhausted."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time

from rfl_rebuild.b2.baseline_artifact import _shard_records, digest, read_index
from rfl_rebuild.b2.design_lock import publish_new
from rfl_rebuild.b2.f0_stages import require

MAX_WORKERS = 16


def now():
    return datetime.now(timezone.utc).isoformat()


def file_digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _verify_one(path, descriptor, index, progress_folder):
    """No alternate parser/checks: consume the original validator to exhaustion."""
    seed, started = descriptor["seed"], time.perf_counter()
    print(f"VERIFY_STARTED seed={seed} pid={os.getpid()}", flush=True)
    count = 0
    for _run in _shard_records(Path(path), descriptor, index):
        count += 1
        if count % 25 == 0:
            print(f"VERIFY_PROGRESS seed={seed} pid={os.getpid()} records={count}", flush=True)
    require(count == descriptor["records"], "worker record count differs")
    result = {"seed": seed, "records": count, "pairs": descriptor["pairs"],
              "sha256": descriptor["sha256"], "pid": os.getpid(), "finished_at": now(),
              "elapsed_s": time.perf_counter() - started, "validator": "frozen-_shard_records"}
    if progress_folder is not None:
        publish_new(Path(progress_folder) / f"seed-{seed}.verified.json", result)
    print(f"VERIFY_COMPLETED seed={seed} pid={os.getpid()} records={count}", flush=True)
    return result


def verify_parallel(index_path, *, progress_folder=None):
    path = Path(index_path).resolve()
    before = digest(path.read_bytes())
    index = read_index(path)
    compressed = {s["path"]: file_digest(path.parent / s["path"]) for s in index["shards"]}
    if progress_folder is not None:
        Path(progress_folder).mkdir(exist_ok=False)
    started = time.perf_counter()
    # Minimal closed metadata is all the unchanged validator reads from index.
    metadata = {key: index[key] for key in ("episodes", "bank_size")}
    pool = ProcessPoolExecutor(max_workers=min(MAX_WORKERS, len(index["shards"])),
                               mp_context=multiprocessing.get_context("spawn"))
    results = {}
    try:
        futures = {pool.submit(_verify_one, str(path), shard, metadata, progress_folder): shard
                   for shard in index["shards"]}
        for future in as_completed(futures):
            shard, result = futures[future], future.result()
            require(result["seed"] == shard["seed"] and result["records"] == shard["records"]
                    and result["sha256"] == shard["sha256"] and result["pairs"] == shard["pairs"],
                    "worker descriptor mismatch")
            require(result["seed"] not in results, "duplicate verified seed")
            results[result["seed"]] = result
    except BaseException:
        pool.terminate_workers()
        raise
    else:
        pool.shutdown(wait=True)
    require(set(results) == set(index["seeds"]), "missing verified seed")
    require(digest(path.read_bytes()) == before, "index changed during verification")
    require(compressed == {s["path"]: file_digest(path.parent / s["path"]) for s in index["shards"]},
            "compressed shard changed during verification")
    require(digest(path.read_bytes()) == before, "index changed during postchecks")
    ordered = [results[seed] for seed in index["seeds"]]
    return {"status": "ALL_SHARDS_VERIFIED", "index_sha256": before,
            "compressed_sha256": compressed, "shards": ordered, "max_workers": MAX_WORKERS,
            "start_method": "spawn", "elapsed_s": time.perf_counter() - started,
            "records": sum(row["records"] for row in ordered),
            "pairs": sum(row["pairs"] for row in ordered),
            "scientific_metrics_computed": False, "validation_reduced": False}
