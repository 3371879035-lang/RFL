"""V0.6: five real learning paths, stochastic facts and isolated frozen evaluation.

Only PublicTask / Observation / RewardPacket enter learners. Cases, latent
causes, noise, seed identifiers and evaluation returns remain in the harness.
No prior RFL runtime, checkpoint or captured episode is imported.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
import argparse
import copy
import hashlib
import json
import random
import sys
import time
import traceback
import tracemalloc

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ACTIONS = (0, 1)
TERMINALS = ("SUCCESS", "COLLISION", "TIMEOUT")


def key(room, command):
    return f"{room}:{command}"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class PublicTask:
    rooms: tuple[int, ...]
    goal: int
    horizon: int = 12


@dataclass(frozen=True)
class Step:
    room: int
    command: int
    executed: int
    next_room: int
    outcome: str


@dataclass(frozen=True)
class Observation:
    uid: int
    steps: tuple[Step, ...]
    terminal: str


@dataclass(frozen=True)
class RewardPacket:
    observation: Observation
    rewards: tuple[float, ...]


class ProbabilityModel:
    def __init__(self):
        self.counts = {}

    def probability(self, room, command):
        forward, collision = self.counts.get(key(room, command), (0, 0))
        return (forward + 1) / (forward + collision + 2)

    def record(self, observation):
        receipts = []
        for s in observation.steps:
            address = key(s.room, s.command)
            before = list(self.counts.get(address, (0, 0)))
            after = list(before)
            if s.outcome == "COLLISION" and s.next_room == s.room:
                after[1] += 1
            elif s.outcome in ("NEXT", "SUCCESS") and s.next_room == s.room + 1:
                after[0] += 1
            else:
                raise ProtocolError("not a valid visible layered-room transition")
            self.counts[address] = after
            receipts.append({"address": address, "before": before, "after": after})
        return receipts


class FactualLearner:
    def __init__(self, task):
        self.task = task
        self.model = ProbabilityModel()
        self.history = []

    def snapshot(self):
        return {"type": "FactualLearner", "task": asdict(self.task),
                "counts": copy.deepcopy(self.model.counts), "history": list(self.history)}

    def policy(self):
        reach = {self.task.goal: 1.0}
        program, details = {}, []
        for room in reversed(self.task.rooms):
            values = []
            for command in ACTIONS:
                p = self.model.probability(room, command)
                value = p * reach[room + 1]
                values.append(value)
                details.append({"address": key(room, command), "p_hex": p.hex(), "value_hex": value.hex()})
            command = 0 if values[0] >= values[1] else 1
            program[room] = command
            reach[room] = values[command]
        return tuple(program[r] for r in self.task.rooms), details, 2 * len(self.task.rooms)

    def learn(self, observation):
        if type(observation) is not Observation:
            raise ProtocolError("F0 consumes factual observations, not reward packets")
        model_updates = self.model.record(observation)
        self.history.append(observation.uid)
        return [], model_updates


class DirectQLearner:
    def __init__(self, task, failure_reward):
        self.task = task
        self.failure_reward = failure_reward
        self.q = {}
        self.buffer = deque(maxlen=64)
        self.history = []
        self.ordinary = self.replays = self.models = self.numeric_changes = 0

    def snapshot(self):
        return {"type": type(self).__name__, "task": asdict(self.task), "failure_reward": self.failure_reward,
                "q": dict(self.q), "buffer": list(self.buffer), "history": list(self.history),
                "ordinary": self.ordinary, "replays": self.replays, "models": self.models,
                "numeric_changes": self.numeric_changes}

    def policy(self):
        actions, details = [], []
        for room in self.task.rooms:
            values = [self.q.get(key(room, a), 0.0) for a in ACTIONS]
            actions.append(0 if values[0] >= values[1] else 1)
            details.extend({"address": key(room, a), "value_hex": values[a].hex()} for a in ACTIONS)
        return tuple(actions), details, 0

    def backup(self, address, target):
        before = self.q.get(address, 0.0)
        after = before + 0.5 * (target - before)
        self.q[address] = after
        self.numeric_changes += after != before
        return {"address": address, "before_hex": before.hex(), "target_hex": target.hex(), "after_hex": after.hex()}

    def real_backup(self, item, kind):
        uid, index, room, command, reward, nxt, terminal = item
        target = reward if terminal else reward + max(self.q.get(key(nxt, a), 0.0) for a in ACTIONS)
        result = self.backup(key(room, command), target)
        self.ordinary += kind == "ordinary"
        self.replays += kind == "replay"
        return {"kind": kind, "source_uid": uid, "source_step": index, "reward": reward, **result}

    def ordinary_updates(self, packet):
        if type(packet) is not RewardPacket:
            raise ProtocolError("Q learner requires the explicit reward adapter")
        obs, rewards = packet.observation, packet.rewards
        assert len(rewards) == len(obs.steps)
        updates = []
        for i, (s, reward) in enumerate(zip(obs.steps, rewards)):
            item = (obs.uid, i, s.room, s.command, reward, s.next_room, s.outcome in TERMINALS)
            self.buffer.append(item)
            updates.append(self.real_backup(item, "ordinary"))
        self.history.append(obs.uid)
        return updates

    def learn(self, packet):
        updates = self.ordinary_updates(packet)
        for item in tuple(reversed(self.buffer))[:12]:
            updates.append(self.real_backup(item, "replay"))
        return updates, []


class HybridQLearner(DirectQLearner):
    def __init__(self, task, failure_reward):
        super().__init__(task, failure_reward)
        self.model = ProbabilityModel()

    def snapshot(self):
        return {**super().snapshot(), "counts": copy.deepcopy(self.model.counts)}

    def learn(self, packet):
        updates = self.ordinary_updates(packet)
        model_updates = self.model.record(packet.observation)
        contexts = sorted((tuple(map(int, address.split(":"))) for address in self.model.counts), key=lambda x: (-x[0], x[1]))
        for i in range(min(12, len(self.buffer))):
            room, command = contexts[i % len(contexts)]
            address = key(room, command)
            p = self.model.probability(room, command)
            forward = 1.0 if room == self.task.goal - 1 else max(self.q.get(key(room + 1, a), 0.0) for a in ACTIONS)
            target = p * forward + (1.0 - p) * self.failure_reward
            receipt = self.backup(address, target)
            self.models += 1
            updates.append({"kind": "model", "counts": list(self.model.counts[address]), "p_hex": p.hex(),
                            "forward_target_hex": forward.hex(), "failure_reward": self.failure_reward, **receipt})
        return updates, model_updates


class FrozenPolicy:
    """No learn method; all policy computation is read-only on a full clone."""
    def __init__(self, learner):
        self._clone = copy.deepcopy(learner)
        self._before = learner.snapshot()
        assert self._clone.snapshot() == self._before
        for name in ("q", "buffer", "history", "model"):
            if hasattr(learner, name):
                assert getattr(self._clone, name) is not getattr(learner, name)
        if hasattr(learner, "model"):
            assert self._clone.model.counts is not learner.model.counts

    def policy(self):
        return self._clone.policy()

    def snapshot(self):
        return self._clone.snapshot()


class Recorder:
    def __init__(self, output, phase, contract):
        output.mkdir(parents=True, exist_ok=False)
        self.path, self.phase, self.contract = output, phase, contract
        self.stream = (output / "raw.jsonl").open("x", encoding="utf-8", newline="\n")
        self.seq = self.uid = 0
        self.counts = Counter()
        self.context = {}
        self.started, self.cpu_started = time.perf_counter(), time.process_time()

    def emit(self, tag, payload):
        line = json.dumps({"seq": self.seq, "context": self.context, "tag": tag, "payload": payload},
                          sort_keys=True, separators=(",", ":")) + "\n"
        limit = self.contract["phase_limits"][self.phase]
        if tag not in ("FAILURE", "FINAL"):
            if self.stream.tell() + len(line.encode()) > limit["capture_bytes"] - 65536:
                raise RuntimeError("prospective capture budget exceeded")
            if time.perf_counter() - self.started > limit["wall_seconds"]:
                raise RuntimeError("prospective native time budget exceeded")
        self.stream.write(line)
        self.seq += 1

    def begin_native(self, mode):
        if self.counts["rollouts"] >= self.contract["phase_limits"][self.phase]["rollouts"]:
            raise RuntimeError("prospective rollout budget exhausted")
        self.counts["rollouts"] += 1
        self.counts[mode + "_rollouts"] += 1
        self.uid += 1
        return self.uid

    def native_step(self, mode):
        if self.counts["steps"] >= self.contract["phase_limits"][self.phase]["steps"]:
            raise RuntimeError("prospective step budget exhausted")
        self.counts["steps"] += 1
        self.counts[mode + "_steps"] += 1


class Engine:
    def __init__(self, spec, p, recorder):
        self._doors = tuple(spec["passable_exits"])
        self._mappings = {(r, a): b for r, a, b in spec["controller_mappings"]}
        self._protected = tuple(tuple(x) for x in spec["protected_addresses"])
        self._p = p
        self.public = PublicTask(tuple(range(len(self._doors))), len(self._doors))
        self.log = recorder
        self._issued, self._consumed = {}, set()
        self._initial = self.audit_snapshot()
        recorder.counts["source_instances"] += 1
        recorder.counts["source_mapping_initializations"] += len(self._mappings)

    def audit_snapshot(self):
        return {"doors": list(self._doors), "p": self._p,
                "mappings": [[r, a, b] for (r, a), b in sorted(self._mappings.items())],
                "protected": [list(x) for x in self._protected]}

    def rollout(self, program, environment_uniforms, mode):
        uid = self.log.begin_native(mode)
        self.log.emit("EPISODE_BEGIN", {"uid": uid, "mode": mode, "program": program,
                                       "environment_uniforms": environment_uniforms})
        room, steps, causes = 0, [], []
        for t in range(self.public.horizon):
            command = program[room]
            assert command in ACTIONS
            executed = self._mappings.get((room, command), command)
            self.log.native_step(mode)
            if executed != self._doors[room]:
                nxt, outcome, cause = room, "COLLISION", "BLOCKED"
            elif environment_uniforms[room] < self._p:
                nxt, outcome, cause = room, "COLLISION", "ACCIDENT"
            else:
                nxt = room + 1
                outcome, cause = ("SUCCESS" if nxt == self.public.goal else "NEXT"), "NONE"
            if t == self.public.horizon - 1 and outcome == "NEXT":
                outcome, cause = "TIMEOUT", "HORIZON"
            steps.append(Step(room, command, executed, nxt, outcome))
            causes.append(cause)
            room = nxt
            if outcome in TERMINALS:
                break
        observation = Observation(uid, tuple(steps), outcome)
        self._issued[uid] = observation
        assert self.audit_snapshot() == self._initial
        self.log.emit("EPISODE_COMPLETE", {"observation": asdict(observation), "audit_causes": causes,
                                          "source_unchanged": True})
        return observation

    def consume(self, observation):
        if type(observation) is not Observation or self._issued.get(observation.uid) is not observation:
            raise ProtocolError("not an observation issued by this source")
        if observation.uid in self._consumed:
            raise ProtocolError("already consumed")
        self._consumed.add(observation.uid)


def make_learner(task, arm):
    if arm == "F0":
        return FactualLearner(task)
    cls = DirectQLearner if arm.startswith("RL-") else HybridQLearner
    return cls(task, -1.0 if arm.endswith("RP") else 0.0)


def materialize_tapes(plan, log):
    blocks = []
    for seed in plan["workload"]["local_engineering_seed_ids"]:
        for mirror in (0, 1):
            env = random.Random(f"V172|{seed}|{mirror}|train_env")
            action = random.Random(f"V172|{seed}|{mirror}|train_action")
            evaluation = random.Random(f"V172|{seed}|{mirror}|eval_env")
            train_env = [[env.random() for _ in range(3)] for _ in range(64)]
            train_action = [[[action.random(), action.random()] for _ in range(3)] for _ in range(64)]
            eval_env = [[evaluation.random() for _ in range(3)] for _ in range(32)]
            blocks.append({"seed": seed, "mirror": mirror, "train_env": train_env,
                           "train_action": train_action, "eval_env": eval_env})
    draws = len(blocks) * (64*3 + 64*3*2 + 32*3)
    log.counts["environment_PRNG_draws"] += len(blocks) * (64*3 + 32*3)
    log.counts["exploration_PRNG_draws"] += len(blocks) * 64*3*2
    log.emit("TAPES", {"blocks": blocks, "sha256": digest(blocks), "PRNG_random_calls": draws,
                       "algorithm": "Python random.Random string seed version=2; separate phase streams"})
    return {(b["seed"], b["mirror"]): b for b in blocks}


def learn_actual(learner, observation, engine, log):
    engine.consume(observation)
    if type(learner) is FactualLearner:
        packet = observation
        wire = {"facts": asdict(observation)}
    else:
        rewards = tuple(1.0 if s.outcome == "SUCCESS" else learner.failure_reward if s.outcome in ("COLLISION", "TIMEOUT") else 0.0
                        for s in observation.steps)
        packet = RewardPacket(observation, rewards)
        wire = {"facts": asdict(observation), "rewards": rewards}
    t = time.perf_counter_ns()
    updates, model_updates = learner.learn(packet)
    elapsed = time.perf_counter_ns() - t
    log.counts["observations_consumed"] += 1
    log.counts["history_appends"] += 1
    log.counts["ordinary_backups"] += sum(u["kind"] == "ordinary" for u in updates)
    log.counts["replay_backups"] += sum(u["kind"] == "replay" for u in updates)
    log.counts["model_backups"] += sum(u["kind"] == "model" for u in updates)
    log.counts["numeric_changes"] += sum(u["before_hex"] != u["after_hex"] for u in updates)
    log.counts["fact_count_updates"] += len(model_updates)
    log.emit("LEARN", {"uid": observation.uid, "packet": wire, "updates": updates,
                       "model_updates": model_updates, "after": learner.snapshot(), "update_ns": elapsed})
    return elapsed


def evaluate(learner, engine, log, checkpoint, uniforms, scripted_program=None):
    train_before = learner.snapshot()
    frozen = FrozenPolicy(learner)
    before = frozen.snapshot()
    t = time.perf_counter_ns()
    greedy, details, expansions = frozen.policy()
    elapsed = time.perf_counter_ns() - t
    log.counts["planning_edge_expansions"] += expansions
    program = tuple(scripted_program) if scripted_program is not None else greedy
    log.emit("FREEZE_BEGIN", {"checkpoint": checkpoint, "state": before, "train_state_sha256": digest(train_before),
                              "nonalias_runtime_asserted": True, "greedy": greedy, "program": program,
                              "readout": details, "planning_edge_expansions": expansions, "policy_ns": elapsed,
                              "scripted": scripted_program is not None})
    uids, successes, steps = [], 0, 0
    for i, vector in enumerate(uniforms):
        log.context = {**log.context, "bank_item": i}
        obs = engine.rollout(program, vector, "eval")
        uids.append(obs.uid)
        successes += obs.terminal == "SUCCESS"
        steps += len(obs.steps)
    assert frozen.snapshot() == before and learner.snapshot() == train_before
    bank = {"checkpoint": checkpoint, "uids": uids, "episodes": len(uids), "successes": successes,
            "steps": steps, "mean_success": successes / len(uids), "program": program,
            "frozen_state_sha256": digest(before), "train_state_sha256_after": digest(learner.snapshot()),
            "frozen_state_sha256_after": digest(frozen.snapshot()), "learning_writes": 0,
            "policy_ns": elapsed, "planning_edge_expansions": expansions}
    log.emit("FREEZE_END", bank)
    log.context = {k: v for k, v in log.context.items() if k != "bank_item"}
    return bank


def run_wiring(plan, log):
    results = []
    source = {"passable_exits": [0], "controller_mappings": [[0,0,1],[0,1,0],[4,0,1],[5,1,0]],
              "protected_addresses": [[4,0],[5,1]]}
    for arm_spec in plan["arms"]:
        arm = arm_spec["id"]
        log.context = {"phase": "wiring", "arm": arm, "stream": "wiring_" + arm}
        engine = Engine(source, 0.1, log)
        learner = make_learner(engine.public, arm)
        log.emit("STREAM_INITIAL", {"case": source, "source": engine.audit_snapshot(), "public": asdict(engine.public),
                                    "learner": learner.snapshot(), "source_instances": log.counts["source_instances"]})
        trained = []
        for e, u in enumerate(plan["wiring"]["scripted_environment_uniforms"][:2]):
            log.context = {**log.context, "train_epoch": e}
            obs = engine.rollout((1,), (u,), "train")
            learn_actual(learner, obs, engine, log)
            trained.append(obs.terminal)
        assert trained == ["SUCCESS", "COLLISION"]
        if hasattr(learner, "model"):
            assert learner.model.counts == {"0:1": [1, 1]}
            assert learner.model.probability(0, 1) == 0.5
        rejected = []
        for name, item in (("duplicate_consumption", obs), ("copied_unissued", replace(obs))):
            try:
                engine.consume(item)
            except ProtocolError:
                rejected.append(name)
            else:
                raise AssertionError(name + " not rejected")
        if type(learner) is FactualLearner:
            try:
                learner.learn(RewardPacket(obs, (-1.0,)))
            except ProtocolError:
                rejected.append("reward_packet_to_F0")
            else:
                raise AssertionError("F0 accepted explicit rewards")
        assert not hasattr(FrozenPolicy(learner), "learn")
        log.emit("BOUNDARY_CHALLENGES", {"rejected": rejected, "native_delta": 0, "frozen_has_no_learn": True})
        log.context = {k: v for k, v in log.context.items() if k != "train_epoch"}
        log.context = {**log.context, "checkpoint": 2}
        bank = evaluate(learner, engine, log, 2, [(0.8,), (0.9,)], scripted_program=(1,))
        assert bank["successes"] == 2
        result = {"arm": arm, "trained": trained, "bank": bank, "final_learner": learner.snapshot()}
        results.append(result)
        log.emit("STREAM_FINAL", result)
    return results


def run_matrix(plan, log):
    tapes = materialize_tapes(plan, log)
    results = []
    for seed in plan["workload"]["local_engineering_seed_ids"]:
        for case in plan["environment"]["structural_case_sources"]:
            mirror = case["mirror"]
            tape = tapes[seed, mirror]
            for p in plan["environment"]["accidental_failure_probability"]:
                for arm_spec in plan["arms"]:
                    arm = arm_spec["id"]
                    context = {"phase": "matrix", "seed": seed, "mirror": mirror, "p": p, "arm": arm,
                               "stream": f"s{seed}_m{mirror}_p{p}_{arm}"}
                    log.context = context
                    initial_counts = Counter(log.counts)
                    engine = Engine(case, p, log)
                    learner = make_learner(engine.public, arm)
                    log.emit("STREAM_INITIAL", {"case": case, "source": engine.audit_snapshot(), "public": asdict(engine.public),
                                                "learner": learner.snapshot(), "source_instances": log.counts["source_instances"]})
                    rows, banks, train_steps, successes = [], [], 0, 0
                    update_ns = policy_ns = 0
                    for e in range(65):
                        if e in plan["workload"]["checkpoints"]:
                            log.context = {**context, "checkpoint": e}
                            n = 1 if p == 0.0 else 32
                            banks.append(evaluate(learner, engine, log, e, tape["eval_env"][:n]))
                        if e == 64:
                            break
                        log.context = {**context, "train_epoch": e}
                        t = time.perf_counter_ns()
                        greedy, details, expansions = learner.policy()
                        policy_ns += time.perf_counter_ns() - t
                        log.counts["planning_edge_expansions"] += expansions
                        coins = [(a < 0.1, int(b * 2)) for a, b in tape["train_action"][e]]
                        program = tuple(coins[r][1] if coins[r][0] else greedy[r] for r in engine.public.rooms)
                        log.emit("TRAIN_POLICY", {"greedy": greedy, "program": program, "coins": coins,
                                                  "readout": details, "planning_edge_expansions": expansions})
                        obs = engine.rollout(program, tape["train_env"][e], "train")
                        update_ns += learn_actual(learner, obs, engine, log)
                        train_steps += len(obs.steps)
                        successes += obs.terminal == "SUCCESS"
                        last = obs.steps[-1]
                        row = {"epoch": e+1, "uid": obs.uid, "terminal": obs.terminal,
                               "successes": successes, "failures": e+1-successes, "train_steps": train_steps,
                               "ordinary_backups": log.counts["ordinary_backups"] - initial_counts["ordinary_backups"],
                               "replay_backups": log.counts["replay_backups"] - initial_counts["replay_backups"],
                               "model_backups": log.counts["model_backups"] - initial_counts["model_backups"],
                               "fact_count_updates": log.counts["fact_count_updates"] - initial_counts["fact_count_updates"],
                               "failure_at_exploratory_deviation": obs.terminal != "SUCCESS" and coins[last.room][0] and last.command != greedy[last.room],
                               "policy_ns": policy_ns, "update_ns": update_ns,
                               "state_sha256": digest(learner.snapshot()),
                               "state_serialized_bytes": len(json.dumps(learner.snapshot(), sort_keys=True).encode())}
                        rows.append(row)
                        log.emit("TRAIN_CHECKPOINT", row)
                    result = {**context, "train_tasks": 64, "train_successes": successes, "train_steps": train_steps,
                              "counts": dict(Counter(log.counts) - initial_counts), "train_curve": rows, "eval_banks": banks,
                              "final_learner": learner.snapshot(), "source_unchanged": engine.audit_snapshot() == engine._initial}
                    results.append(result)
                    log.emit("STREAM_FINAL", result)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("wiring", "matrix"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
    plan = json.loads((ROOT / contract["plan"]).read_text(encoding="utf-8"))
    inputs = {rel: sha(ROOT / rel) for rel in contract["inputs"]}
    log = Recorder(args.output, args.phase, contract)
    tracemalloc.start()
    results, ok, error = [], False, None
    log.emit("RUN_START", {"phase": args.phase, "utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
                           "contract": contract, "plan": plan, "inputs": inputs})
    try:
        results = run_wiring(plan, log) if args.phase == "wiring" else run_matrix(plan, log)
        log.emit("RESULT", {"streams": results, "counts": dict(log.counts)})
        ok = True
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
                   "input_bytes_unchanged": unchanged, "error": error,
                   "wall_seconds": time.perf_counter()-log.started, "cpu_seconds": time.process_time()-log.cpu_started,
                   "python_heap_current_bytes": current, "python_heap_peak_bytes": peak}
        log.emit("FINAL", receipt)
        log.stream.close()
        write_json(args.output / "exit.json", receipt)
        if ok:
            write_json(args.output / "result.json", {"streams": results, "counts": dict(log.counts)})
        print(json.dumps(receipt))
    return receipt["child_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
