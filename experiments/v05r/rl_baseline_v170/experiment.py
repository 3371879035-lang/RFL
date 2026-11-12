"""V170 fixed-interface baseline: original factual learner vs direct Q-learning.

The V169 kernel/factual learner are reused unchanged, NOT its runner, diagnosis,
reward learner, fixtures or captured episodes. No controller edit is permitted.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import sys
import time
import traceback
import tracemalloc

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD_PATH = HERE.parent / "feedback_matrix_v169" / "experiment.py"
spec = importlib.util.spec_from_file_location("v170_reused_v169_components", OLD_PATH)
V = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = V
spec.loader.exec_module(V)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


class DirectQ:
    """Q(room, requested command), no physical-action map or diagnostic model.

    Fixed controllers make requested commands a stationary action interface.
    Each real transition gets one ordinary backup. Replay is an explicitly
    counted, bounded extra use of this learner's own recorded experience.
    """
    def __init__(self, task, channel, replay_backups):
        self.task = task
        self.channel = channel
        self.replay_backups = replay_backups
        self.q = {}
        self.history = []
        self.buffer = deque(maxlen=64)
        self.ordinary_backups = 0
        self.replay_count = 0
        self.numeric_changes = 0

    def program(self, revisions, coins):
        program = []
        for room in self.task.rooms:
            command = max(V.ACTIONS, key=lambda c: (self.q.get(V.key(room, c), 0.0), -c))
            program.append(coins[room][1] if coins[room][0] else command)
        return tuple(program)

    def backup(self, item, kind):
        uid, index, room, command, reward, nxt, terminal = item
        address = V.key(room, command)
        before = self.q.get(address, 0.0)
        target = reward if terminal else reward + max(self.q.get(V.key(nxt, c), 0.0) for c in V.ACTIONS)
        after = before + 0.5 * (target - before)
        self.q[address] = after
        self.ordinary_backups += kind == "ordinary"
        self.replay_count += kind == "replay"
        self.numeric_changes += before != after
        return {"kind": kind, "source_uid": uid, "source_step": index, "address": address,
                "reward": reward, "before_hex": before.hex(), "target_hex": target.hex(), "after_hex": after.hex()}

    def observe_reward(self, observation, rewards):
        assert len(rewards) == len(observation.steps)
        updates = []
        for i, (step, reward) in enumerate(zip(observation.steps, rewards)):
            item = (observation.uid, i, step.room, step.command, reward, step.next_room, step.outcome in V.TERMINALS)
            self.buffer.append(item)
            updates.append(self.backup(item, "ordinary"))
        self.history.append(observation.uid)
        for item in tuple(reversed(self.buffer))[:self.replay_backups]:
            updates.append(self.backup(item, "replay"))
        return updates

    def snapshot(self):
        return {"type": "DirectQ", "channel": self.channel, "replay_backups": self.replay_backups,
                "q": dict(self.q), "history": list(self.history), "buffer": list(self.buffer),
                "ordinary_backups": self.ordinary_backups, "replay_count": self.replay_count,
                "numeric_changes": self.numeric_changes}


class Recorder:
    def __init__(self, output, phase, contract):
        output.mkdir(parents=True, exist_ok=False)
        self.path, self.phase, self.contract = output, phase, contract
        self.stream = (output / "raw.jsonl").open("x", encoding="utf-8", newline="\n")
        self.seq, self.last_uid = 0, 0
        self.counts = Counter()
        self.context = {}
        self.started = time.perf_counter()
        self.cpu_started = time.process_time()

    def emit(self, tag, payload):
        line = json.dumps({"seq": self.seq, "context": self.context, "tag": tag, "payload": payload},
                          sort_keys=True, separators=(",", ":")) + "\n"
        if tag not in ("FAILURE", "FINAL"):
            if self.stream.tell() + len(line.encode()) > self.contract["capture_bytes_cap"] - 65536:
                raise RuntimeError("prospective capture cap exceeded")
            if time.perf_counter() - self.started > self.contract["wall_seconds_cap"]:
                raise RuntimeError("prospective wall cap exceeded")
        self.stream.write(line)
        self.stream.flush()
        self.seq += 1

    def native_start(self):
        if self.counts["rollouts"] >= self.contract["limits"][self.phase]["rollouts"]:
            raise RuntimeError("prospective rollout cap exceeded")
        self.counts["rollouts"] += 1
        self.last_uid += 1
        return self.last_uid

    def native_step(self):
        if self.counts["steps"] >= self.contract["limits"][self.phase]["steps"]:
            raise RuntimeError("prospective step cap exceeded")
        self.counts["steps"] += 1


def stream(spec, arm, log, contract):
    engine = V.Engine(spec["passable_exits"], log)
    controller = V.Controller({(r, c): x for r, c, x in spec["controller_mappings"]},
                              [tuple(a) for a in spec["protected_addresses"]])
    controller_before = controller.snapshot()
    learner = (V.FactLearner(engine.public) if arm == "F" else
               DirectQ(engine.public, "R" if arm == "Q-R" else "RP", 12 if arm == "Q-RP-Replay12" else 0))
    log.context = {"phase": log.phase, "case": spec["id"], "arm": arm}
    initial_counts = Counter(log.counts)
    log.counts["source_instances"] += 1
    log.counts["source_mapping_initializations"] += len(controller.mappings)
    log.emit("STREAM_INITIAL", {"case": spec, "public_task": asdict(engine.public),
                               "controller": controller_before, "learner": learner.snapshot()})
    rows = []
    started = time.perf_counter()
    plan_ns, update_ns = 0, 0
    length = 2 if log.phase == "wiring" else contract["main_tasks"]
    for episode in range(length):
        log.context = {**log.context, "main_epoch": episode}
        coins = V.coordinates(spec["index"], episode, engine.public.goal)
        rev = tuple(controller.revision(room) for room in engine.public.rooms)
        t = time.perf_counter_ns()
        greedy = learner.program(rev, tuple((False, 0) for _ in engine.public.rooms))
        program = learner.program(rev, coins)
        plan_ns += time.perf_counter_ns() - t
        log.emit("POLICY", {"episode": episode, "greedy": greedy, "program": program, "coins": coins})
        observation = engine.rollout(controller, program, coins, "main", "fixed_interface_no_diagnosis")
        engine.consume(observation)
        t = time.perf_counter_ns()
        if arm == "F":
            packet = {"facts": asdict(observation)}
            updates = learner.observe(observation)
            log.counts["fact_field_updates"] += 2 * len(observation.steps)
        else:
            rewards = V.reward_packet(observation, learner.channel)
            packet = {"facts": asdict(observation), "rewards": rewards}
            updates = learner.observe_reward(observation, rewards)
        update_ns += time.perf_counter_ns() - t
        log.counts["observations_consumed"] += 1
        log.counts["ordinary_backups"] += sum(u["kind"] == "ordinary" for u in updates)
        log.counts["replay_backups"] += sum(u["kind"] == "replay" for u in updates)
        log.counts["numeric_changes"] += sum(u["before_hex"] != u["after_hex"] for u in updates)
        assert controller.snapshot() == controller_before
        log.emit("LEARN", {"uid": observation.uid, "packet": packet, "updates": updates, "after": learner.snapshot()})
        last = observation.steps[-1]
        exploration_failure = (observation.terminal != "SUCCESS" and coins[last.room][0]
                               and last.command != greedy[last.room])
        row = {"episode": episode, "uid": observation.uid, "terminal": observation.terminal,
               "steps": log.counts["steps"] - initial_counts["steps"], "rollouts": episode + 1,
               "ordinary_backups": log.counts["ordinary_backups"] - initial_counts["ordinary_backups"],
               "replay_backups": log.counts["replay_backups"] - initial_counts["replay_backups"],
               "fact_field_updates": log.counts["fact_field_updates"] - initial_counts["fact_field_updates"],
               "failure_at_exploratory_deviation": exploration_failure,
               "plan_ns": plan_ns, "update_ns": update_ns,
               "learner_snapshot_bytes": len(json.dumps(learner.snapshot(), sort_keys=True).encode())}
        rows.append(row)
        log.emit("MAIN_CHECKPOINT", row)
        if log.phase == "wiring" and episode == 0:
            assert observation.terminal == "COLLISION"
            rejected = []
            for name, obj in (("already_consumed", observation), ("copied_not_issued", replace(observation))):
                try:
                    engine.consume(obj)
                except V.ProtocolError:
                    rejected.append(name)
                else:
                    raise AssertionError(name + " was not rejected")
            if arm == "F":
                try:
                    learner.observe({"facts": observation, "rewards": [0.0]})
                except V.ProtocolError:
                    rejected.append("reward_packet_to_F")
                else:
                    raise AssertionError("F accepted a reward packet")
            log.emit("BOUNDARY_CHALLENGES", {"rejected": rejected, "additional_native": 0})
    if log.phase == "wiring":
        assert rows[1]["terminal"] == ("COLLISION" if arm == "Q-R" else "SUCCESS")
    success = [row["terminal"] == "SUCCESS" for row in rows]
    target = next((i for i in range(11, len(rows)) if all(success[i - 11:i + 1])), None)
    result = {"case": spec["id"], "decision_points": engine.public.goal, "arm": arm, "main_tasks": len(rows),
              "main_successes": sum(success), "prefix_successes": {str(n): sum(success[:n]) for n in (12, 24, 48)},
              "cold_successes": sum(success[:24]), "continued_successes": sum(success[24:]),
              "counts": dict(Counter(log.counts) - initial_counts),
              "target": {"status": "REACHED" if target is not None else "NOT_REACHED_RIGHT_CENSORED",
                         "main_index_1based": target + 1 if target is not None else None,
                         "steps": rows[target]["steps"] if target is not None else None,
                         "later_failures": sum(not x for x in success[target + 1:]) if target is not None else None},
              "failure_at_exploratory_deviation": sum(row["failure_at_exploratory_deviation"] for row in rows),
              "plan_ns": plan_ns, "update_ns": update_ns, "wall_seconds": time.perf_counter() - started,
              "final_learner": learner.snapshot(), "final_controller": controller.snapshot(), "curve": rows}
    log.emit("STREAM_FINAL", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("wiring", "matrix"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
    inputs = {rel: sha(ROOT / rel) for rel in contract["inputs"]}
    log = Recorder(args.output, args.phase, contract)
    tracemalloc.start()
    ok, error, results = False, None, []
    log.emit("RUN_START", {"utc": datetime.now(timezone.utc).isoformat(), "phase": args.phase,
                           "contract": contract, "inputs": inputs})
    try:
        cases = [contract["wiring_case"]] if args.phase == "wiring" else contract["cases"]
        for case in cases:
            for arm in contract["arms"]:
                results.append(stream(case, arm, log, contract))
        ok = True
        log.emit("RESULT", {"streams": results, "counts": dict(log.counts)})
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        log.emit("FAILURE", error)
        traceback.print_exc()
    finally:
        unchanged = all(sha(ROOT / rel) == h for rel, h in inputs.items())
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        receipt = {"complete": ok, "child_exit_code": 0 if ok and unchanged else 1, "phase": args.phase,
                   "utc": datetime.now(timezone.utc).isoformat(), "counts": dict(log.counts),
                   "input_bytes_unchanged": unchanged, "wall_seconds": time.perf_counter() - log.started,
                   "cpu_seconds": time.process_time() - log.cpu_started,
                   "python_heap_current_bytes": current, "python_heap_peak_bytes": peak, "error": error}
        log.emit("FINAL", receipt)
        log.stream.close()
        dump(args.output / "exit.json", receipt)
        if ok:
            dump(args.output / "result.json", {"streams": results, "counts": dict(log.counts)})
        print(json.dumps(receipt))
    return receipt["child_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
