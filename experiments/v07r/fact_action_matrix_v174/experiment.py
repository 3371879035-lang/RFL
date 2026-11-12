"""V0.7 new-seed experiment. Reuse frozen V172 learning/kernel, not its runner.

The only learner overrides are hybrid initialization metadata, snapshot and
policy. No inherited TD, model, replay, observation or ownership code is patched.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import argparse
import ctypes
import gzip
import hashlib
import importlib.util
import json
import random
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE_PATH = ROOT / "experiments/v06r/stochastic_matrix_v172/experiment.py"
spec = importlib.util.spec_from_file_location("v174_frozen_v172_components", BASE_PATH)
B = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = B
spec.loader.exec_module(B)


def wire(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"))


def digest(x):
    return hashlib.sha256(wire(x).encode()).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, x):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(x, f, ensure_ascii=False, indent=2)
        f.write("\n")


def shadow_readouts(learner):
    """Task-visible current state only. No environment, seed or evaluation input."""
    rows = []
    for room in learner.task.rooms:
        q = [learner.q.get(B.key(room, a), 0.0) for a in (0, 1)]
        counts = [list(learner.model.counts.get(B.key(room, a), (0, 0))) for a in (0, 1)]
        probabilities = [(n+1)/(n+m+2) for n, m in counts]
        candidates = [a for a in (0, 1) if q[a] == max(q)]
        old = min(candidates)
        ft = min(candidates, key=lambda a: (-probabilities[a], a))
        ct = min(candidates, key=lambda a: (sum(counts[a]), a))
        rows.append({"room": room, "q": q, "counts": counts, "p_hat": probabilities,
                     "argmax": candidates, "old": old, "FT": ft, "CT": ct})
    return rows


class TieHybrid(B.HybridQLearner):
    def __init__(self, task, failure_reward, tie_mode):
        super().__init__(task, failure_reward)
        self.tie_mode = tie_mode

    def snapshot(self):
        return {**super().snapshot(), "tie_mode": self.tie_mode}

    def policy(self):
        details = shadow_readouts(self)
        return tuple(r[self.tie_mode] for r in details), details, 0


def make_learner(task, arm_spec):
    arm = arm_spec["id"]
    if arm == "F0":
        return B.FactualLearner(task)
    reward = float(arm_spec["reward_failure"])
    if arm.endswith(("-FT", "-CT")):
        return TieHybrid(task, reward, arm[-2:])
    cls = B.DirectQLearner if arm.startswith("RL-") else B.HybridQLearner
    return cls(task, reward)


class Recorder:
    """Lossless compact records; context is stored once per stream, not per step."""
    def __init__(self, output, phase, contract):
        output.mkdir(parents=True, exist_ok=False)
        self.path, self.phase, self.contract = output, phase, contract
        self.raw_file = (output / "raw.jsonl.gz").open("xb", buffering=1024*1024)
        self.stream = gzip.GzipFile(filename="", mode="wb", compresslevel=1, fileobj=self.raw_file, mtime=0)
        self.seq = self.uid = self.uncompressed_bytes = 0
        self.counts, self.context = Counter(), {}
        self.started, self.cpu_started = time.perf_counter(), time.process_time()

    def emit(self, tag, payload):
        data = (wire({"seq": self.seq, "tag": tag, "payload": payload})+"\n").encode()
        self.stream.write(data)
        self.uncompressed_bytes += len(data)
        self.seq += 1
        if self.seq % 4096 == 0 and tag not in ("FAILURE", "FINAL"):
            limit = self.contract["phase_limits"][self.phase]
            if self.raw_file.tell() > limit["compressed_capture_bytes"]-65536:
                raise RuntimeError("prospective compressed capture budget exhausted")
            if time.perf_counter()-self.started > limit["wall_seconds"]:
                raise RuntimeError("prospective native time budget exhausted")

    def begin_native(self, mode):
        if self.counts["rollouts"] >= self.contract["phase_limits"][self.phase]["rollouts"]:
            raise RuntimeError("prospective rollout budget exhausted")
        self.counts["rollouts"] += 1
        self.counts[mode+"_rollouts"] += 1
        self.uid += 1
        return self.uid

    def native_step(self, mode):
        if self.counts["steps"] >= self.contract["phase_limits"][self.phase]["steps"]:
            raise RuntimeError("prospective step budget exhausted")
        self.counts["steps"] += 1
        self.counts[mode+"_steps"] += 1


def materialize_tapes(plan, log):
    blocks = []
    for seed in plan["workload"]["local_engineering_seed_ids"]:
        for mirror in (0, 1):
            env = random.Random(f"V07|{seed}|{mirror}|train_env")
            action = random.Random(f"V07|{seed}|{mirror}|train_action")
            evaluation = random.Random(f"V07|{seed}|{mirror}|eval_env")
            blocks.append({"seed": seed, "mirror": mirror,
                           "train_env": [[env.random() for _ in range(3)] for _ in range(64)],
                           "train_action": [[[action.random(), action.random()] for _ in range(3)] for _ in range(64)],
                           "eval_env": [[evaluation.random() for _ in range(3)] for _ in range(512)]})
    log.counts["environment_PRNG_draws"] += len(blocks)*(64*3+512*3)
    log.counts["exploration_PRNG_draws"] += len(blocks)*64*3*2
    log.emit("TAPES", {"blocks": blocks, "sha256": digest(blocks), "PRNG_random_calls": 135168})
    return {(b["seed"], b["mirror"]): b for b in blocks}


def evaluate(learner, engine, log, checkpoint, uniforms):
    original = learner.snapshot()
    frozen = B.FrozenPolicy(learner)
    before = frozen.snapshot()
    t = time.perf_counter_ns()
    program, details, expansions = frozen.policy()
    elapsed = time.perf_counter_ns()-t
    log.counts["policy_calls"] += 1
    log.counts["planning_edge_expansions"] += expansions
    if isinstance(learner, TieHybrid):
        log.counts["tie_readout_candidate_scores"] += 2*learner.task.goal
    log.emit("FREEZE_BEGIN", {"checkpoint": checkpoint, "state": before, "train_state_sha256": digest(original),
                              "nonalias_runtime_asserted": True, "program": program, "readout": details,
                              "planning_edge_expansions": expansions, "policy_ns": elapsed})
    first_uid = log.uid+1
    successes = steps = 0
    for vector in uniforms:
        obs = engine.rollout(program, vector, "eval")
        successes += obs.terminal == "SUCCESS"
        steps += len(obs.steps)
    assert frozen.snapshot() == before and learner.snapshot() == original
    bank = {"checkpoint": checkpoint, "first_uid": first_uid, "last_uid": log.uid,
            "episodes": len(uniforms), "successes": successes, "steps": steps,
            "mean_success": successes/len(uniforms), "program": program,
            "frozen_state_sha256": digest(before), "frozen_state_sha256_after": digest(frozen.snapshot()),
            "train_state_sha256_after": digest(learner.snapshot()), "learning_writes": 0,
            "policy_ns": elapsed, "planning_edge_expansions": expansions}
    log.emit("FREEZE_END", bank)
    return bank


def policy_for_training(learner, coins, log, epoch, scripted=None):
    t = time.perf_counter_ns()
    greedy, details, expansions = learner.policy()
    elapsed = time.perf_counter_ns()-t
    log.counts["policy_calls"] += 1
    log.counts["planning_edge_expansions"] += expansions
    shadow, shadow_ns, reused = [], 0, False
    if hasattr(learner, "q") and hasattr(learner, "model"):
        if isinstance(learner, TieHybrid):
            shadow, reused = details, True
            log.counts["tie_readout_candidate_scores"] += 2*learner.task.goal
        else:
            t = time.perf_counter_ns()
            shadow = shadow_readouts(learner)
            shadow_ns = time.perf_counter_ns()-t
        log.counts["shadow_readout_calls"] += 1
        log.counts["shadow_candidate_scores"] += 2*learner.task.goal
    program = tuple(scripted) if scripted is not None else tuple(coins[r][1] if coins[r][0] else greedy[r] for r in learner.task.rooms)
    log.emit("TRAIN_POLICY", {"epoch": epoch, "greedy": greedy, "program": program, "coins": coins,
                              "readout": details, "planning_edge_expansions": expansions,
                              "policy_ns": elapsed, "shadow": shadow, "shadow_ns": shadow_ns,
                              "shadow_reused_policy_work": reused, "scripted": scripted is not None})
    return program, greedy, shadow, elapsed, shadow_ns


def mechanism_visits(obs, greedy, shadow, coins):
    rows = []
    for step in obs.steps:
        if not shadow:
            continue
        s = shadow[step.room]
        counts = s["counts"][step.command]
        rows.append({**s, "command": step.command, "greedy": greedy[step.room],
                     "exploration": bool(coins[step.room][0]), "outcome": step.outcome,
                     "prior_collisions_chosen": counts[1]})
    return rows


def add_mechanism(counter, visits):
    for r in visits:
        tied = len(r["argmax"]) > 1
        counter["visited"] += 1
        counter["Q_ties"] += tied
        counter["outcome_informative_ties"] += tied and r["p_hat"][0] != r["p_hat"][1]
        counter["FT_diff_old"] += r["FT"] != r["old"]
        counter["CT_diff_old"] += r["CT"] != r["old"]
        counter["FT_diff_CT"] += r["FT"] != r["CT"]
        counter["actual_readout_overridden"] += r["command"] != r["greedy"]
        counter["actual_changed_from_old_without_exploration"] += not r["exploration"] and r["command"] == r["greedy"] and r["greedy"] != r["old"]
        counter["repeated_collision"] += r["outcome"] == "COLLISION" and r["prior_collisions_chosen"] > 0


def run_stream(plan, arm_spec, source, probability, context, log, tape=None):
    before_counts = Counter(log.counts)
    engine = B.Engine(source, probability, log)
    learner = make_learner(engine.public, arm_spec)
    log.emit("STREAM_INITIAL", {"context": context, "case": source, "source": engine.audit_snapshot(),
                                "public": asdict(engine.public), "learner": learner.snapshot(),
                                "source_instances": log.counts["source_instances"]})
    rows, banks, mechanism = [], [], Counter()
    train_steps = successes = policy_total = update_total = shadow_total = 0
    behavior = hashlib.sha256()
    wiring = context["phase"] == "wiring"
    limit = 2 if wiring else 64
    for e in range(limit+1):
        if e == 2 and wiring:
            banks.append(evaluate(learner, engine, log, e, [[.9,.9],[.9,.9]]))
            assert banks[-1]["program"] == (1, 0) and banks[-1]["successes"] == 2
        elif not wiring and e in plan["workload"]["checkpoints"]:
            banks.append(evaluate(learner, engine, log, e, tape["eval_env"][:1 if probability == 0 else 512]))
        if e == limit:
            break
        coins = [(False, 0)]*2 if wiring else [(u < .1, int(v*2)) for u, v in tape["train_action"][e]]
        program, greedy, shadow, pt, st = policy_for_training(learner, coins, log, e, [0,0] if wiring else None)
        obs = engine.rollout(program, [.9,.9] if wiring else tape["train_env"][e], "train")
        visits = mechanism_visits(obs, greedy, shadow, coins)
        add_mechanism(mechanism, visits)
        log.emit("MECHANISM_VISITS", {"uid": obs.uid, "rows": visits})
        # Exact same ordinary TD/model/replay implementation and input adapters as V172.
        update_total += B.learn_actual(learner, obs, engine, log)
        policy_total += pt
        shadow_total += st
        behavior.update((wire({"steps": asdict(obs)["steps"], "terminal": obs.terminal})+"\n").encode())
        train_steps += len(obs.steps)
        successes += obs.terminal == "SUCCESS"
        if wiring:
            assert obs.terminal == "COLLISION"
        row = {"epoch": e+1, "uid": obs.uid, "terminal": obs.terminal, "successes": successes,
               "failures": e+1-successes, "train_steps": train_steps,
               "ordinary_backups": log.counts["ordinary_backups"]-before_counts["ordinary_backups"],
               "replay_backups": log.counts["replay_backups"]-before_counts["replay_backups"],
               "model_backups": log.counts["model_backups"]-before_counts["model_backups"],
               "fact_count_updates": log.counts["fact_count_updates"]-before_counts["fact_count_updates"],
               "policy_ns": policy_total, "update_ns": update_total, "shadow_ns": shadow_total,
               "state_sha256": digest(learner.snapshot()), "state_serialized_bytes": len(wire(learner.snapshot()).encode())}
        rows.append(row)
        log.emit("TRAIN_CHECKPOINT", row)
    assert TieHybrid.learn is B.HybridQLearner.learn and TieHybrid.ordinary_updates is B.DirectQLearner.ordinary_updates
    result = {**context, "train_tasks": limit, "train_successes": successes, "train_steps": train_steps,
              "counts": dict(Counter(log.counts)-before_counts), "train_curve": rows, "eval_banks": banks,
              "mechanism": dict(mechanism), "train_behavior_sha256": behavior.hexdigest(),
              "final_learner": learner.snapshot(), "source_unchanged": engine.audit_snapshot() == engine._initial,
              "inherited_updates_runtime_identical": True}
    log.emit("STREAM_FINAL", result)
    return result


def run(plan, log):
    results = []
    if log.phase == "wiring":
        source = {"passable_exits": [0,0], "controller_mappings": [[0,0,1],[0,1,0],[6,0,1],[7,1,0]],
                  "protected_addresses": [[6,0],[7,1]]}
        for a in plan["arms"]:
            if a["id"] in plan["wiring"]["arms"]:
                results.append(run_stream(plan, a, source, .1, {"phase":"wiring", "arm":a["id"], "stream":"wiring_"+a["id"]}, log))
    else:
        tapes = materialize_tapes(plan, log)
        for seed in plan["workload"]["local_engineering_seed_ids"]:
            for source in plan["environment"]["structural_case_sources"]:
                m = source["mirror"]
                for p in (0.0, .1):
                    for a in plan["arms"]:
                        ctx = {"phase":"matrix", "seed":seed, "mirror":m, "p":p, "arm":a["id"],
                               "stream":f"s{seed}_m{m}_p{p}_{a['id']}"}
                        results.append(run_stream(plan, a, source, p, ctx, log, tapes[seed,m]))
            print(wire({"completed_seed":seed,"streams":len(results),"rollouts":log.counts["rollouts"]}), flush=True)
    return results


def process_memory():
    class PMC(ctypes.Structure):
        _fields_ = [("cb",ctypes.c_ulong),("PageFaultCount",ctypes.c_ulong)]+[(k,ctypes.c_size_t) for k in
                    ("PeakWorkingSetSize","WorkingSetSize","QuotaPeakPagedPoolUsage","QuotaPagedPoolUsage",
                     "QuotaPeakNonPagedPoolUsage","QuotaNonPagedPoolUsage","PagefileUsage","PeakPagefileUsage")]
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    info = PMC(); info.cb = ctypes.sizeof(info)
    getinfo = ctypes.windll.psapi.GetProcessMemoryInfo
    getinfo.argtypes = [ctypes.c_void_p,ctypes.POINTER(PMC),ctypes.c_ulong]
    assert getinfo(kernel.GetCurrentProcess(),ctypes.byref(info),info.cb)
    return {"working_set_bytes":info.WorkingSetSize,"peak_working_set_bytes":info.PeakWorkingSetSize,
            "kind":"Windows process working set; not Python traced heap"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase",choices=("wiring","matrix"),required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    contract = json.loads((HERE/"contract.json").read_text(encoding="utf-8"))
    plan = json.loads((ROOT/contract["plan"]).read_text(encoding="utf-8"))
    inputs = {p:file_sha(ROOT/p) for p in contract["inputs"]}
    log = Recorder(args.output,args.phase,contract)
    ok, error, results = False, None, []
    log.emit("RUN_START",{"phase":args.phase,"utc":datetime.now(timezone.utc).isoformat(),"python":sys.version,
                          "contract":contract,"plan":plan,"inputs":inputs})
    try:
        results = run(plan,log)
        log.emit("RESULT",{"streams":results,"counts":dict(log.counts)})
        ok = True
    except BaseException as exc:
        error = {"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}
        log.emit("FAILURE",error)
        traceback.print_exc()
    finally:
        unchanged = all(file_sha(ROOT/p)==h for p,h in inputs.items())
        receipt = {"complete":ok,"child_exit_code":0 if ok and unchanged else 1,"phase":args.phase,
                   "utc":datetime.now(timezone.utc).isoformat(),"counts":dict(log.counts),"error":error,
                   "input_bytes_unchanged":unchanged,"wall_seconds":time.perf_counter()-log.started,
                   "cpu_seconds":time.process_time()-log.cpu_started,"memory":process_memory(),
                   "memory_scope":"sampled after native loops, before capture finalization/result serialization"}
        log.emit("FINAL",receipt)
        receipt["canonical_records"] = log.seq
        receipt["uncompressed_capture_bytes"] = log.uncompressed_bytes
        log.stream.close();log.raw_file.close()
        receipt["compressed_capture_bytes"] = (args.output/"raw.jsonl.gz").stat().st_size
        receipt["raw_gzip_sha256"] = file_sha(args.output/"raw.jsonl.gz")
        limit = contract["phase_limits"][args.phase]
        assert receipt["compressed_capture_bytes"] <= limit["compressed_capture_bytes"]
        assert receipt["wall_seconds"] <= limit["wall_seconds"]
        write_json(args.output/"exit.json",receipt)
        if ok:
            write_json(args.output/"result.json",{"streams":results,"counts":dict(log.counts)})
        print(wire(receipt),flush=True)
    return receipt["child_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
