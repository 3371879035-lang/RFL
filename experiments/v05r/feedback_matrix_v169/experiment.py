"""V0.5: factual feedback, optional scalar reward, and a finite matched experiment.

No V03/V04 runtime, Q*, trained checkpoint or value-tree is imported here.
The immutable world is private to Engine. Agent receives only PublicTask,
issued factual observations and candidate descriptions derived from observations.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import sys
import time
import traceback
import tracemalloc
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ACTIONS = (0, 1)
TERMINALS = ("SUCCESS", "COLLISION", "TIMEOUT")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def key(*items):
    return json.dumps(items, separators=(",", ":"))


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class PublicTask:
    rooms: tuple[int, ...]
    start: int
    goal: int
    horizon: int = 12


@dataclass(frozen=True)
class Step:
    room: int
    cell: tuple[int, int]
    revision: str
    command: int
    executed: int
    next_room: int
    next_cell: tuple[int, int]
    outcome: str


@dataclass(frozen=True)
class Feedback:
    uid: int
    steps: tuple[Step, ...]
    terminal: str

    @property
    def reached(self):
        return self.steps[-1].next_room


class Controller:
    def __init__(self, mappings, protected, revisions=None):
        self.mappings = dict(mappings)
        self.protected = frozenset(protected)
        self.revisions = dict(revisions or {})

    def clone(self):
        return Controller(self.mappings, self.protected, self.revisions)

    def execute(self, room, command):
        return self.mappings.get((room, command), command)

    def revision(self, room):
        return self.revisions.get(room, "initial")

    def snapshot(self):
        return {"mappings": [[r, c, x] for (r, c), x in sorted(self.mappings.items())],
                "protected": [list(x) for x in sorted(self.protected)],
                "revisions": [[r, v] for r, v in sorted(self.revisions.items())]}

    def revised(self, removals, witness):
        seen = {(s.room, s.command, s.executed) for s in witness.steps if s.command != s.executed}
        proposed = tuple(sorted(set(removals)))
        for r, c in proposed:
            if (r, c) in self.protected or (r, c, self.execute(r, c)) not in seen:
                raise ProtocolError("edit is protected, unread, or not witnessed in this source")
            if (r, c) not in self.mappings:
                raise ProtocolError("no current remap at the witnessed address")
        result = self.clone()
        for r, c in proposed:
            del result.mappings[r, c]
        for r in {r for r, _ in proposed}:
            result.revisions[r] = digest([self.revision(r), [c for rr, c in proposed if rr == r]])
        return result


class Recorder:
    def __init__(self, output, phase, contract):
        output.mkdir(parents=True, exist_ok=False)
        self.path = output
        self.stream = (output / "raw.jsonl").open("x", encoding="utf-8", newline="\n")
        self.phase = phase
        self.contract = contract
        self.counts = Counter()
        self.seq = 0
        self.context = {}
        self.started = time.perf_counter()
        self.cpu_started = time.process_time()
        self.limit = 6 if phase == "wiring" else 2160
        self.step_limit = self.limit * 12
        self.last_uid = 0

    def emit(self, tag, payload):
        line = json.dumps({"seq": self.seq, "context": dict(self.context), "tag": tag,
                           "payload": payload}, sort_keys=True, separators=(",", ":")) + "\n"
        if tag not in ("FAILURE", "FINAL"):
            if self.stream.tell() + len(line.encode()) > self.contract["capture_bytes_cap"] - 65536:
                raise RuntimeError("prospective capture budget exceeded; terminal reserve retained")
            if time.perf_counter() - self.started > self.contract["wall_seconds_cap"]:
                raise RuntimeError("prospective wall-time budget exceeded")
        self.stream.write(line)
        self.stream.flush()
        self.seq += 1

    def native_start(self):
        if self.counts["rollouts"] >= self.limit:
            raise RuntimeError("prospective native rollout budget exhausted")
        self.counts["rollouts"] += 1
        self.last_uid += 1
        return self.last_uid

    def native_step(self):
        if self.counts["steps"] >= self.step_limit:
            raise RuntimeError("prospective native step budget exhausted")
        self.counts["steps"] += 1


class Engine:
    """Actual new simulation, not replayed stored traces. Truth stays here."""
    def __init__(self, doors, recorder):
        self._doors = tuple(doors)
        self.public = PublicTask(tuple(range(len(doors))), 0, len(doors))
        self.recorder = recorder
        self._issued = {}
        self._consumed = set()
        self._query = {}

    def query_key(self, controller, program, coins):
        return digest([controller.snapshot(), list(program), list(coins)])

    def lookup(self, controller, program, coins):
        q = self.query_key(controller, program, coins)
        return q, self._query.get(q)

    def rollout(self, controller, program, coins, kind, candidate):
        uid = self.recorder.native_start()
        self.recorder.emit("EPISODE_BEGIN", {"uid": uid, "kind": kind, "candidate": candidate,
                           "controller": controller.snapshot(), "program": list(program), "coins": list(coins)})
        room, steps = 0, []
        for t in range(self.public.horizon):
            command = program[room]
            if command not in ACTIONS:
                raise ProtocolError("non-action in task program")
            self.recorder.native_step()
            executed = controller.execute(room, command)
            if executed != self._doors[room]:
                nxt, outcome = room, "COLLISION"
            else:
                nxt = room + 1
                outcome = "SUCCESS" if nxt == self.public.goal else "NEXT"
            if t == self.public.horizon - 1 and outcome == "NEXT":
                outcome = "TIMEOUT"
            steps.append(Step(room, (2 * room, 0), controller.revision(room), command, executed,
                              nxt, (2 * nxt, 0), outcome))
            room = nxt
            if outcome in TERMINALS:
                break
        observation = Feedback(uid, tuple(steps), steps[-1].outcome)
        self._issued[uid] = observation
        self._query[self.query_key(controller, program, coins)] = observation
        self.recorder.emit("EPISODE_COMPLETE", asdict(observation))
        return observation

    def consume(self, observation):
        if not isinstance(observation, Feedback) or self._issued.get(observation.uid) is not observation:
            raise ProtocolError("observation was not issued by this current engine")
        if observation.uid in self._consumed:
            raise ProtocolError("observation already consumed")
        self._consumed.add(observation.uid)

    def assert_owned(self, observation):
        if self._issued.get(observation.uid) is not observation:
            raise ProtocolError("unissued witness")


def reward_packet(observation, channel):
    if channel not in ("RP", "R"):
        raise ProtocolError("reward adapter is not a pure-feedback adapter")
    return tuple(1.0 if s.outcome == "SUCCESS" else (-1.0 if channel == "RP" else 0.0)
                 if s.outcome in ("COLLISION", "TIMEOUT") else 0.0 for s in observation.steps)


class FactLearner:
    """Reward-free learning is categorical transition learning + goal search."""
    def __init__(self, task):
        self.task = task
        self.edges = {}
        self.commands = {}
        self.history = []
        self.fact_updates = 0

    def snapshot(self):
        return {"type": type(self).__name__, "edges": dict(self.edges), "commands": dict(self.commands),
                "history": list(self.history), "fact_updates": self.fact_updates}

    def observe(self, observation):
        if type(observation) is not Feedback:
            raise ProtocolError("F consumes factual Feedback, not a reward packet")
        for s in observation.steps:
            ek = key(s.room, s.executed)
            prior = self.edges.get(ek)
            fact = {"next_room": s.next_room, "outcome": s.outcome, "count": 1 + (prior["count"] if prior else 0)}
            if prior and (prior["next_room"], prior["outcome"]) != (s.next_room, s.outcome):
                raise ProtocolError("immutable-world evidence conflict")
            self.edges[ek] = fact
            self.commands[key(s.room, s.revision, s.command)] = s.executed
            self.fact_updates += 1
        self.history.append(observation.uid)
        return []

    def predicted_execution(self, room, revision, command):
        return self.commands.get(key(room, revision, command), command)

    def program(self, revisions, coins):
        # Backward goal search in the declared layered topology. Unknown edges
        # are hypotheses, never filled from the simulator's passable-door list.
        reachable = {self.task.goal: True}
        actions = {}
        for room in reversed(self.task.rooms):
            available = []
            for command in ACTIONS:
                executed = self.predicted_execution(room, revisions[room], command)
                edge = self.edges.get(key(room, executed))
                if edge and edge["outcome"] == "COLLISION":
                    continue
                available.append((0 if edge else 1, command))
            reachable[room] = bool(available) and reachable[room + 1]
            # If no complete path is known, retain a safe prefix to the unknown
            # frontier rather than discarding already learned earlier rooms.
            if available:
                chosen = min(available)[1]
            else:
                unseen = [c for c in ACTIONS if key(room, revisions[room], c) not in self.commands]
                chosen = unseen[0] if unseen else 0
            actions[room] = coins[room][1] if coins[room][0] else chosen
        return tuple(actions[r] for r in self.task.rooms)


class RewardLearner(FactLearner):
    def __init__(self, task):
        super().__init__(task)
        self.q = {}
        self.numeric_changes = 0
        self.td_updates = 0

    def snapshot(self):
        x = super().snapshot()
        x.update(q=dict(self.q), numeric_changes=self.numeric_changes, td_updates=self.td_updates)
        return x

    def observe_reward(self, observation, rewards):
        if len(rewards) != len(observation.steps):
            raise ProtocolError("wrong reward extent")
        super().observe(observation)
        updates = []
        for s, r in zip(observation.steps, rewards):
            address = key(s.room, s.executed)
            before = self.q.get(address, 0.0)
            target = r if s.outcome in TERMINALS else r + max(self.q.get(key(s.next_room, a), 0.0) for a in ACTIONS)
            after = before + 0.5 * (target - before)
            self.q[address] = after
            self.numeric_changes += before != after
            self.td_updates += 1
            updates.append({"address": address, "reward": r, "before_hex": before.hex(),
                            "target_hex": target.hex(), "after_hex": after.hex()})
        return updates

    def program(self, revisions, coins):
        chosen = []
        for room in self.task.rooms:
            scores = [(self.q.get(key(room, self.predicted_execution(room, revisions[room], c)), 0.0), -c, c) for c in ACTIONS]
            action = max(scores)[2]
            chosen.append(coins[room][1] if coins[room][0] else action)
        return tuple(chosen)


@dataclass(frozen=True)
class Candidate:
    name: str
    removals: tuple[tuple[int, int], ...]
    prefix: tuple[int, ...]


class Agent:
    """Only task-visible inputs; no Engine, truth case, or controller map here."""
    def __init__(self, task, mode, channel):
        self.task, self.mode, self.channel = task, mode, channel
        self.learner = FactLearner(task) if channel == "F" else RewardLearner(task)
        self.cursor = 0

    def program(self, revisions, coins, prefix=()):
        ordinary = list(self.learner.program(revisions, coins))
        for room, command in enumerate(prefix):
            ordinary[room] = command
        return tuple(ordinary)

    def menu(self, observation):
        mismatches = [(s.room, s.command) for s in observation.steps if s.command != s.executed]
        prefix = tuple(s.command for s in observation.steps)
        out = [Candidate("keep", (), ())]
        if mismatches:
            out.append(Candidate("remove_first", (mismatches[0],), prefix))
            if len(mismatches) > 1:
                out.append(Candidate("remove_last", (mismatches[-1],), prefix))
                out.append(Candidate("joint", tuple(sorted(set(mismatches))), prefix))
        alternate = prefix[:-1] + (1 - prefix[-1],)
        out.append(Candidate("practice_alternative", (), alternate))
        return tuple(out)

    def order(self, menu, observation):
        if self.mode == "P":
            start = self.cursor % len(menu)
            self.cursor += 1
            return menu[start:] + menu[:start]
        # Current terminal mismatch is a candidate cause, not a verdict. A
        # mismatch that already carried the task forward is not automatically bad.
        terminal = observation.steps[-1]
        if terminal.command != terminal.executed:
            wanted = (terminal.room, terminal.command)
            nominal_edge = self.learner.edges.get(key(terminal.room, terminal.command))
            if not nominal_edge or nominal_edge["outcome"] != "COLLISION":
                preferred = [c for c in menu if c.removals == (wanted,)]
                return tuple(preferred + [c for c in menu if c not in preferred])
        # Ordinary learning may already have changed the plan. Try it before
        # structural edits, then a discriminating alternative, then other edits.
        return tuple(sorted(menu, key=lambda c: (0 if c.name == "keep" else 1 if c.name == "practice_alternative" else 2)))


def coordinates(case_index, episode, depth):
    return tuple(((episode + 3 * r + case_index) % 10 == 7,
                  (episode // 10 + r + case_index) % 2) for r in range(depth))


def revisions(controller, task):
    return tuple(controller.revision(r) for r in task.rooms)


def better(new, old):
    # Goal predicate and a strict extension of the observed reachable prefix,
    # not an external reward or a reinforcement label for F.
    if new.terminal == "SUCCESS":
        return old.terminal != "SUCCESS"
    return old.terminal != "SUCCESS" and new.reached > old.reached


class Stream:
    def __init__(self, spec, arm, recorder):
        self.spec, self.arm, self.log = spec, arm, recorder
        mode, channel = arm.split("-")
        self.engine = Engine(spec["passable_exits"], recorder)
        self.controller = Controller({(r, c): x for r, c, x in spec["controller_mappings"]},
                                     [tuple(x) for x in spec["protected_addresses"]])
        self.agent = Agent(self.engine.public, mode, channel)
        self.used_trials = 0
        self.lookup_hits = 0
        self.commits = 0
        self.main_rows = []
        self.started = time.perf_counter()
        self.cpu_started = time.process_time()
        self.start_counts = Counter(recorder.counts)
        self.initial_protected = {k: self.controller.mappings[k] for k in self.controller.protected}
        recorder.counts["source_instances"] += 1
        recorder.counts["source_mapping_initializations"] += len(self.controller.mappings)
        self.log.emit("STREAM_INITIAL", {"case": spec, "arm": arm, "public_task": asdict(self.engine.public),
                        "controller": self.controller.snapshot(), "learner": self.agent.learner.snapshot()})

    def learn(self, observation):
        self.engine.consume(observation)
        before = digest(self.agent.learner.snapshot())
        if self.agent.channel == "F":
            packet = {"facts": asdict(observation)}
            updates = self.agent.learner.observe(observation)
        else:
            rewards = reward_packet(observation, self.agent.channel)
            packet = {"facts": asdict(observation), "rewards": list(rewards)}
            updates = self.agent.learner.observe_reward(observation, rewards)
        self.log.counts["fact_field_updates"] += 2 * len(observation.steps)
        self.log.counts["history_appends"] += 1
        self.log.counts["td_updates"] += len(updates)
        self.log.counts["numeric_changes"] += sum(x["before_hex"] != x["after_hex"] for x in updates)
        self.log.emit("LEARN", {"uid": observation.uid, "before_digest": before, "packet": packet,
                    "updates": updates, "after": self.agent.learner.snapshot()})

    def execute(self, controller, program, coins, kind, candidate):
        obs = self.engine.rollout(controller, program, coins, kind, candidate)
        self.learn(obs)
        return obs

    def diagnose(self, factual, coins):
        menu = self.agent.menu(factual)
        ordered = self.agent.order(menu, factual)
        self.log.emit("CANDIDATE_MENU", {"witness": factual.uid, "catalogue": [asdict(c) for c in menu],
                                        "order": [c.name for c in ordered], "remaining": 12 - self.used_trials})
        best, selected = factual, None
        paid = 0
        for candidate in ordered:
            if self.used_trials >= 12 or paid >= 2:
                break
            trial_controller = self.controller.revised(candidate.removals, factual) if candidate.removals else self.controller.clone()
            program = self.agent.program(revisions(trial_controller, self.engine.public), coins, candidate.prefix)
            qk, cached = self.engine.lookup(trial_controller, program, coins)
            if self.agent.mode == "S":
                self.log.emit("QUERY_LOOKUP", {"candidate": candidate.name, "query_key": qk,
                                               "cached_uid": cached.uid if cached else None})
            if self.agent.mode == "S" and cached is not None:
                observation = cached
                self.lookup_hits += 1
                self.log.emit("REUSE", {"uid": cached.uid, "query_key": qk, "new_learning": False})
            else:
                self.used_trials += 1
                paid += 1
                observation = self.execute(trial_controller, program, coins, "trial", candidate.name)
            visited = {(s.room, s.command) for s in observation.steps if s.command == s.executed}
            supported = all(address in visited for address in candidate.removals)
            accept = better(observation, best) and supported
            self.log.emit("TRIAL_ASSESS", {"uid": observation.uid, "candidate": asdict(candidate),
                           "supported": supported, "improves_on_uid": best.uid, "preferred": accept,
                           "paid_this_failure": paid, "used_trials": self.used_trials})
            if accept:
                best = observation
                selected = (candidate, trial_controller, observation)
            if observation.terminal == "SUCCESS":
                break
        if selected is not None and selected[0].removals:
            candidate, new_controller, observation = selected
            self.engine.assert_owned(factual)
            self.engine.assert_owned(observation)
            before = self.controller.snapshot()
            self.controller = new_controller
            self.commits += 1
            self.log.counts["controller_transactions"] += 1
            self.log.counts["controller_entries_removed"] += len(candidate.removals)
            self.log.emit("COMMIT", {"witness": factual.uid, "selected": observation.uid,
                         "removals": [list(x) for x in candidate.removals], "before": before,
                         "after": self.controller.snapshot()})

    def task(self, episode, *, diagnose=True):
        self.log.context.update(main_epoch=episode)
        coins = coordinates(self.spec["index"], episode, self.engine.public.goal)
        program = self.agent.program(revisions(self.controller, self.engine.public), coins)
        observation = self.execute(self.controller, program, coins, "main", "ordinary")
        trials_before = self.used_trials
        if observation.terminal != "SUCCESS" and diagnose:
            self.diagnose(observation, coins)
        for address, value in self.initial_protected.items():
            if self.controller.mappings.get(address) != value:
                raise ProtocolError("protected controller value changed")
        row = {"episode": episode, "uid": observation.uid, "terminal": observation.terminal,
               "reached": observation.reached, "trial_delta": self.used_trials - trials_before,
               "trials_so_far": self.used_trials, "rollouts": self.log.counts["rollouts"] - self.start_counts["rollouts"],
               "steps": self.log.counts["steps"] - self.start_counts["steps"],
               "wall_seconds": time.perf_counter() - self.started,
               "cpu_seconds": time.process_time() - self.cpu_started, "controller_transactions": self.commits}
        self.main_rows.append(row)
        self.log.emit("MAIN_CHECKPOINT", {**row, "learner": self.agent.learner.snapshot(),
                                           "controller": self.controller.snapshot()})
        return observation

    def challenges(self, observation):
        before = digest(self.agent.learner.snapshot())
        counts = dict(self.log.counts)
        results = {}
        for name, call in (
            ("duplicate", lambda: self.engine.consume(observation)),
            ("forged_copy", lambda: self.engine.consume(replace(observation))),
            ("protected_unread_edit", lambda: self.controller.revised((next(iter(self.controller.protected)),), observation)),
        ):
            try:
                call()
            except ProtocolError as e:
                results[name] = str(e)
            else:
                raise AssertionError("challenge was not rejected: " + name)
        if self.agent.channel == "F":
            try:
                self.agent.learner.observe({"facts": observation, "rewards": (1.0,)})
            except ProtocolError as e:
                results["reward_packet_to_F"] = str(e)
            else:
                raise AssertionError("F accepted a reward packet")
        assert digest(self.agent.learner.snapshot()) == before and dict(self.log.counts) == counts
        self.log.emit("BOUNDARY_CHALLENGES", {"rejected": results, "state_unchanged": True, "native_delta": 0})

    def finish(self):
        rows = self.main_rows
        success = [r["terminal"] == "SUCCESS" for r in rows]
        target = next((i for i in range(11, len(rows)) if all(success[i - 11:i + 1])), None)
        counts = {k: self.log.counts[k] - self.start_counts[k] for k in (
            "rollouts", "steps", "controller_transactions", "controller_entries_removed",
            "source_instances", "source_mapping_initializations", "fact_field_updates",
            "history_appends", "td_updates", "numeric_changes")}
        result = {"case": self.spec["id"], "decision_points": self.engine.public.goal, "arm": self.arm,
                  "prefix_successes": {str(n): sum(success[:n]) for n in (12, 24, 48)},
                  "main_tasks": len(rows), "main_successes": sum(success), "main_failures": len(rows) - sum(success),
                  "cold_successes": sum(success[:24]), "continued_successes": sum(success[24:]),
                  "trial_rollouts": self.used_trials, "cache_hits": self.lookup_hits, "counts": counts,
                  "target": {"status": "REACHED" if target is not None else "NOT_REACHED_RIGHT_CENSORED",
                             "main_index_1based": target + 1 if target is not None else None,
                             "cost": rows[target] if target is not None else None},
                  "later_failures": sum(not v for v in success[target + 1:]) if target is not None else None,
                  "final_learner": self.agent.learner.snapshot(), "final_controller": self.controller.snapshot(),
                  "curve": rows}
        self.log.emit("STREAM_FINAL", result)
        return result


def run_phase(recorder, contract):
    results = []
    if recorder.phase == "wiring":
        spec = contract["wiring_case"]
        for channel in ("RP", "R", "F"):
            recorder.context = {"case": spec["id"], "arm": "S-" + channel, "phase": "wiring"}
            stream = Stream(spec, "S-" + channel, recorder)
            observation = stream.task(0)
            if observation.terminal != "COLLISION" or stream.used_trials != 1 or stream.commits != 1:
                raise AssertionError("three-channel minimal failure/trial/commit wiring did not execute")
            stream.challenges(observation)
            results.append(stream.finish())
    else:
        for spec in contract["cases"]:
            for arm in contract["arms"]:
                recorder.context = {"case": spec["id"], "arm": arm, "phase": "matrix"}
                stream = Stream(spec, arm, recorder)
                for episode in range(48):
                    stream.task(episode)
                results.append(stream.finish())
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("wiring", "matrix"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
    inputs = {rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in contract["inputs"]}
    recorder = Recorder(args.output, args.phase, contract)
    tracemalloc.start()
    ok, error, results = False, None, []
    recorder.emit("RUN_START", {"phase": args.phase, "utc": datetime.now(timezone.utc).isoformat(),
                               "contract": contract, "inputs": inputs})
    try:
        results = run_phase(recorder, contract)
        recorder.emit("RESULT", {"complete": True, "counts": dict(recorder.counts), "streams": results})
        ok = True
    except BaseException as exc:
        ok = False
        error = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        recorder.emit("FAILURE", error)
        traceback.print_exc()
    finally:
        unchanged = all(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == h for rel, h in inputs.items())
        current_heap, peak_heap = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        receipt = {"complete": ok, "child_exit_code": 0 if ok and unchanged else 1, "phase": args.phase,
                   "utc": datetime.now(timezone.utc).isoformat(), "counts": dict(recorder.counts),
                   "records_before_final": recorder.seq, "input_bytes_unchanged": unchanged,
                   "wall_seconds": time.perf_counter() - recorder.started,
                   "cpu_seconds": time.process_time() - recorder.cpu_started,
                   "python_heap_current_bytes": current_heap, "python_heap_peak_bytes": peak_heap,
                   "error": error}
        recorder.emit("FINAL", receipt)
        recorder.stream.close()
        (args.output / "exit.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        if ok:
            (args.output / "result.json").write_text(json.dumps({"counts": dict(recorder.counts), "streams": results}, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: receipt[k] for k in ("complete", "child_exit_code", "phase", "counts", "wall_seconds", "error")}))
    return receipt["child_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
