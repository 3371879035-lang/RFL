"""Real spawn equivalence and fail-closed scheduling, engineering keys only."""
import ctypes
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from fractions import Fraction

import pytest

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2 import parallel_acquisition as parallel
from rfl_rebuild.b2.acquisition import iter_master_baseline
from rfl_rebuild.b2.baseline_artifact import verify_acquisition, write_acquisition
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.temporal_initializer import temporal_initializer
from rfl_rebuild.b2.training import BaselineAcquisitionPlan
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.solve.dp import solve_reference

KEYS = (980100, 980101)
PLAN = BaselineAcquisitionPlan(KEYS[0], Fraction(1, 2), Fraction(1, 10), 2, prefix(100))


def _raise_worker(task):
    raise ProtocolError("construction injected worker failure")


def _barrier_probe(task):
    """Force sixteen simultaneous real spawn processes, not sixteen queued jobs."""
    folder = Path(task["folder"])
    (folder / str(os.getpid())).touch(exist_ok=False)
    deadline = time.monotonic() + 45
    while len(list(folder.iterdir())) < 16:
        if time.monotonic() > deadline:
            raise RuntimeError("sixteen worker barrier timeout")
        time.sleep(.02)
    if os.name == "nt":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
                "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        counter = Counters()
        counter.cb = ctypes.sizeof(counter)
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.GetCurrentProcess.restype = ctypes.c_void_p
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if not psapi.GetProcessMemoryInfo(api.GetCurrentProcess(), ctypes.byref(counter), counter.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        peak = counter.PeakWorkingSetSize
    else:
        peak = None
    return {"seed": task["seed"], "pid": os.getpid(), "peak_rss_bytes": peak}


@pytest.fixture(scope="module")
def equivalent_files(tmp_path_factory):
    folder = tmp_path_factory.mktemp("parallel-equivalence")
    kwargs = dict(plan=PLAN, seeds=KEYS, constants={"fixture": True},
                  execution={"fixture": "engineering-only"}, role="OPERATIONAL_REHEARSAL")
    reference = reference_view_from(solve_reference())
    serial = write_acquisition(folder / "serial.json", **kwargs,
        records=iter_master_baseline(PLAN, seeds=KEYS, q_reference=reference, initializer=temporal_initializer))
    spawned = parallel.write_parallel(folder / "spawned.json", **kwargs, workers=16)
    return folder, serial, spawned


def test_real_c3_full_u2_serial_spawn_records_and_gzip_exact(equivalent_files):
    folder, serial, spawned = equivalent_files
    assert serial["ordered_shard_digest"] == spawned["ordered_shard_digest"]
    assert serial["records"] == spawned["records"] == 6
    assert serial["pairs"] == spawned["pairs"]
    assert verify_acquisition(folder / "spawned.json") == spawned
    for left, right in zip(serial["shards"], spawned["shards"]):
        assert left["seed"] == right["seed"]
        assert left["sha256"] == right["sha256"]
        assert (folder / left["path"]).read_bytes() == (folder / right["path"]).read_bytes()
        assert gzip.decompress((folder / right["path"]).read_bytes()) == gzip.decompress((folder / left["path"]).read_bytes())


def test_writer_refactor_matches_preserved_parent_bytes(equivalent_files):
    """Audit against unmodified R1 code, not only two paths sharing new helpers."""
    parent = Path('D:/强化反馈学习/RFL-CausalChase-v0.3-restart-20261008')
    if not parent.exists():
        pytest.skip("preserved R1 worktree is unavailable on this host")
    folder, serial, _ = equivalent_files
    code = '''import sys
from fractions import Fraction
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "src"))
from rfl_rebuild.b2.acquisition import iter_master_baseline
from rfl_rebuild.b2.baseline_artifact import write_acquisition
from rfl_rebuild.b2.training import BaselineAcquisitionPlan
from rfl_rebuild.b2.evalorder import prefix
from rfl_rebuild.b2.temporal_initializer import temporal_initializer
from rfl_rebuild.learner.reference import reference_view_from
from rfl_rebuild.solve.dp import solve_reference
plan=BaselineAcquisitionPlan(980100,Fraction(1,2),Fraction(1,10),2,prefix(100))
records=iter_master_baseline(plan,seeds=(980100,980101),q_reference=reference_view_from(solve_reference()),initializer=temporal_initializer)
write_acquisition(sys.argv[2],plan=plan,seeds=(980100,980101),records=records,constants={"fixture":True},execution={"fixture":"engineering-only"},role="OPERATIONAL_REHEARSAL")
'''
    subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", code, str(parent), str(folder / "parent.json")],
                   check=True, timeout=180, cwd=folder)
    old = verify_acquisition(folder / "parent.json")
    assert old["ordered_shard_digest"] == serial["ordered_shard_digest"]
    for left, right in zip(old["shards"], serial["shards"]):
        assert (folder / left["path"]).read_bytes() == (folder / right["path"]).read_bytes()


def test_sixteen_actual_spawn_processes_and_bounded_memory(tmp_path):
    rows = parallel._run_tasks([{"seed": seed, "folder": str(tmp_path)} for seed in range(980100, 980116)],
                               workers=16, worker=_barrier_probe)
    assert len({row["pid"] for row in rows}) == 16
    assert [row["seed"] for row in rows] == list(range(980100, 980116))
    if os.name == "nt":
        assert all(0 < row["peak_rss_bytes"] < 256 * 1024**2 for row in rows)


def test_real_sixteen_seed_acquisition_has_complete_ordered_axes(tmp_path):
    seeds = tuple(range(980100, 980116))
    plan = BaselineAcquisitionPlan(seeds[0], Fraction(1, 2), Fraction(1, 10), 1, prefix(8))
    index = parallel.write_parallel(tmp_path / "real16.json", plan=plan, seeds=seeds,
        constants={"fixture": True}, execution={"fixture": "engineering-only"}, role="OPERATIONAL_REHEARSAL")
    assert index["seeds"] == list(seeds) and index["records"] == 32
    assert verify_acquisition(tmp_path / "real16.json") == index


@pytest.mark.parametrize("workers", [True, 0, -1, 17, 16.0, None])
def test_bad_worker_counts_refuse_before_outputs(tmp_path, workers):
    with pytest.raises(ProtocolError, match="worker count"):
        parallel.write_parallel(tmp_path / "bad.json", plan=PLAN, seeds=KEYS, constants={}, execution={},
                                role="OPERATIONAL_REHEARSAL", workers=workers)
    assert list(tmp_path.iterdir()) == []


def test_worker_exception_cancels_without_retry():
    with pytest.raises(ProtocolError, match="injected worker failure"):
        parallel._run_tasks([{"seed": seed} for seed in KEYS], worker=_raise_worker)


def test_failed_worker_keeps_partials_but_no_index(tmp_path, monkeypatch):
    def fail(tasks, **kwargs):
        (Path(tasks[0]["folder"]) / "partial-evidence").touch()
        raise ProtocolError("worker died")
    monkeypatch.setattr(parallel, "_run_tasks", fail)
    with pytest.raises(ProtocolError, match="worker died"):
        parallel.write_parallel(tmp_path / "failed.json", plan=PLAN, seeds=KEYS, constants={}, execution={},
                                role="OPERATIONAL_REHEARSAL")
    assert not (tmp_path / "failed.json").exists()
    assert (tmp_path / "failed/partial-evidence").is_file()


def test_order_is_input_order_not_completion_order(tmp_path, monkeypatch):
    monkeypatch.setattr(parallel, "_run_tasks", lambda tasks, **k: [
        {"seed": t["seed"], "path": f"ordered/seed-{t['seed']:06d}.jsonl.gz", "sha256": "a"*64,
         "records": 3, "pairs": 0} for t in tasks])
    index = parallel.write_parallel(tmp_path / "ordered.json", plan=PLAN, seeds=KEYS[::-1],
        constants={}, execution={}, role="OPERATIONAL_REHEARSAL")
    assert [s["seed"] for s in index["shards"]] == list(KEYS[::-1])


def test_postcheck_failure_never_publishes_index(tmp_path, monkeypatch):
    def result(tasks, **kwargs):
        return [{"seed": t["seed"], "path": f"post/seed-{t['seed']:06d}.jsonl.gz", "sha256": "a"*64,
                 "records": 3, "pairs": 0} for t in tasks]
    monkeypatch.setattr(parallel, "_run_tasks", result)
    def reject():
        raise ProtocolError("source changed")
    with pytest.raises(ProtocolError, match="source changed"):
        parallel.write_parallel(tmp_path / "post.json", plan=PLAN, seeds=KEYS, constants={}, execution={},
                                role="OPERATIONAL_REHEARSAL", postcheck=reject)
    assert not (tmp_path / "post.json").exists()


def test_smoke_only_counts_no_outcome_surface():
    plan = BaselineAcquisitionPlan(KEYS[0], Fraction(1, 2), Fraction(1, 10), 1, prefix(8))
    assert parallel.discard_parallel(plan, KEYS) == 4


def test_execution_profile_is_fixed_and_not_scientific_constant():
    from rfl_rebuild.b2.design_lock import CONSTANTS
    assert parallel.EXECUTION_PROFILE["max_workers"] == 16
    assert "max_workers" not in CONSTANTS
