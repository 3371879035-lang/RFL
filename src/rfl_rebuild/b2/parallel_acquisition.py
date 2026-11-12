"""Spawn isolated seed learners; never parallelize dependent episodes or gates.

Workers return only counts/descriptors. Full material stays in exclusive seed
shards, avoiding pickling MappingProxyType or retaining curves in the coordinator.
Any failure terminates remaining workers, preserves partial evidence, and never
falls back to serial acquisition or automatically retries a seed.
"""
from concurrent.futures import ProcessPoolExecutor, as_completed
from fractions import Fraction
import multiprocessing
import os
from pathlib import Path

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.acquisition import _require_seeds, iter_master_baseline
from rfl_rebuild.b2.baseline_artifact import canonical_bytes, publish_acquisition_index, write_seed_shard
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.temporal_initializer import temporal_initializer
from rfl_rebuild.b2.training import BaselineAcquisitionPlan
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.solve.dp import solve_reference

MAX_WORKERS = 16
EXECUTION_PROFILE = {"kind": "seed-processpool-spawn-v1", "max_workers": MAX_WORKERS,
                     "seed_internal_order": "serial", "output_order": "frozen-seed-order",
                     "gate_order": "serial", "retry": False}


def plan_for(constants, seeds):
    seeds = _require_seeds(seeds)
    return BaselineAcquisitionPlan(seeds[0], Fraction(*constants["alpha"]),
                                   Fraction(*constants["epsilon"]), constants["acquisition_cap"], prefix(1024))


def _task(plan, seed, folder=None, relative_prefix=None):
    return {"seed": seed, "alpha": (plan.alpha.numerator, plan.alpha.denominator),
            "epsilon": (plan.epsilon.numerator, plan.epsilon.denominator),
            "cap": plan.acquisition_cap, "bank_size": len(plan.evaluation_bank),
            "folder": str(folder) if folder is not None else None, "relative_prefix": relative_prefix}


def _worker_seed(task):
    seed = task["seed"]
    print(f"SEED_STARTED seed={seed} pid={os.getpid()}", flush=True)
    plan = BaselineAcquisitionPlan(seed, Fraction(*task["alpha"]), Fraction(*task["epsilon"]),
                                   task["cap"], prefix(task["bank_size"]))
    reference = reference_view_from(solve_reference())
    records = iter(iter_master_baseline(plan, seeds=(seed,), q_reference=reference,
                                        initializer=temporal_initializer))
    if task["folder"] is None:
        count = 0
        for episode in range(plan.acquisition_cap + 1):
            try:
                row = next(records)
            except StopIteration as exc:
                raise ProtocolError("smoke acquisition ended before its full envelope") from exc
            if (row.seed, row.episode) != (seed, episode):
                raise ProtocolError("smoke acquisition axis mismatch")
            count += 1
        result = {"seed": seed, "records": count}
    else:
        result = write_seed_shard(task["folder"], plan=plan, seed=seed, records=records,
                                  relative_prefix=task["relative_prefix"])
    sentinel = object()
    if next(records, sentinel) is not sentinel:
        raise ProtocolError("acquisition exceeded the declared axis")
    print(f"SEED_COMPLETED seed={seed} pid={os.getpid()} records={plan.acquisition_cap + 1}", flush=True)
    return result


def _run_tasks(tasks, *, workers=MAX_WORKERS, worker=_worker_seed):
    """Bounded spawn executor. Completion order never defines the scientific order."""
    if type(workers) is not int or not 1 <= workers <= MAX_WORKERS:
        raise ProtocolError("worker count must be a true integer in 1..16")
    executor = ProcessPoolExecutor(max_workers=min(workers, len(tasks)),
                                   mp_context=multiprocessing.get_context("spawn"))
    results = {}
    try:
        futures = {executor.submit(worker, task): task["seed"] for task in tasks}
        for future in as_completed(futures):
            seed = futures[future]
            row = future.result()
            if type(row) is not dict or type(row.get("seed")) is not int or row["seed"] != seed:
                raise ProtocolError("worker returned a mismatched seed")
            if seed in results:
                raise ProtocolError("duplicate worker result")
            results[seed] = row
    except BaseException:
        # Python 3.14 public API: no lingering running or queued seed jobs.
        executor.terminate_workers()
        raise
    else:
        executor.shutdown(wait=True)
    return [results[task["seed"]] for task in tasks]


def discard_parallel(plan, seeds, *, workers=MAX_WORKERS):
    seeds = _require_seeds(seeds)
    if plan.evaluation_bank != prefix(len(plan.evaluation_bank)):
        raise ProtocolError("parallel acquisition requires the frozen balanced bank")
    rows = _run_tasks([_task(plan, seed) for seed in seeds], workers=workers)
    if any(set(row) != {"seed", "records"} or type(row["records"]) is not int
           or row["records"] != plan.acquisition_cap + 1 for row in rows):
        raise ProtocolError("parallel smoke axis/count mismatch")
    return sum(row["records"] for row in rows)


def write_parallel(index_path, *, plan, seeds, constants, execution, role,
                   postcheck=None, workers=MAX_WORKERS):
    """One worker per independent seed; coordinator publishes the index last."""
    seeds = _require_seeds(seeds)
    if type(workers) is not int or not 1 <= workers <= MAX_WORKERS:
        raise ProtocolError("worker count must be a true integer in 1..16")
    if plan.evaluation_bank != prefix(len(plan.evaluation_bank)):
        raise ProtocolError("parallel acquisition requires the frozen balanced bank")
    if type(constants) is not dict or type(execution) is not dict:
        raise ProtocolError("missing provenance objects")
    if role not in ("OPERATIONAL_REHEARSAL", "DEVELOPMENT_BASELINE"):
        raise ProtocolError("unknown artifact role")
    canonical_bytes([constants, execution])
    path = Path(index_path)
    if path.exists():
        raise FileExistsError(path)
    folder = path.with_suffix("")
    folder.mkdir(parents=True, exist_ok=False)
    shards = _run_tasks([_task(plan, seed, folder, path.stem) for seed in seeds], workers=workers)
    for seed, row in zip(seeds, shards):
        if (set(row) != {"seed", "path", "sha256", "records", "pairs"}
                or row["path"] != f"{path.stem}/seed-{seed:06d}.jsonl.gz"
                or type(row["records"]) is not int or row["records"] != plan.acquisition_cap + 1):
            raise ProtocolError("parallel worker shard descriptor mismatch")
    if postcheck is not None:
        postcheck()
    return publish_acquisition_index(path, plan=plan, seeds=seeds, shards=shards,
                                     constants=constants, execution=execution, role=role)
