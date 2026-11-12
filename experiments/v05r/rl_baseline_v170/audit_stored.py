"""Independent stdlib replay of saved evidence; imports no experiment/kernel."""
from collections import Counter, deque
from pathlib import Path
import ast
import hashlib
import json
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TERMINALS = {"SUCCESS", "COLLISION", "TIMEOUT"}


def key(*items):
    return json.dumps(items, separators=(",", ":"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model(arm):
    if arm == "F":
        return {"type": "FactLearner", "edges": {}, "commands": {}, "history": [], "fact_updates": 0}
    return {"type": "DirectQ", "channel": "R" if arm == "Q-R" else "RP",
            "replay_backups": 12 if arm == "Q-RP-Replay12" else 0,
            "q": {}, "history": [], "buffer": [], "ordinary_backups": 0, "replay_count": 0, "numeric_changes": 0}


def policy(state, depth):
    out = []
    for room in range(depth):
        if state["type"] == "DirectQ":
            values = [state["q"].get(key(room, c), 0.0) for c in (0, 1)]
            out.append(0 if values[0] >= values[1] else 1)
        else:
            available = []
            for c in (0, 1):
                executed = state["commands"].get(key(room, "initial", c), c)
                edge = state["edges"].get(key(room, executed))
                if edge is not None and edge["outcome"] == "COLLISION":
                    continue
                available.append((edge is None, c))
            unseen = [c for c in (0, 1) if key(room, "initial", c) not in state["commands"]]
            out.append(min(available)[1] if available else unseen[0] if unseen else 0)
    return out


def update(state, raw, rewards):
    uid, steps = raw["uid"], raw["steps"]
    if state["type"] == "FactLearner":
        assert rewards is None
        for s in steps:
            address = key(s["room"], s["executed"])
            previous = state["edges"].get(address)
            if previous:
                assert (previous["next_room"], previous["outcome"]) == (s["next_room"], s["outcome"])
            state["edges"][address] = {"next_room": s["next_room"], "outcome": s["outcome"],
                                       "count": 1 + (previous["count"] if previous else 0)}
            state["commands"][key(s["room"], "initial", s["command"])] = s["executed"]
            state["fact_updates"] += 1
        state["history"].append(uid)
        return []
    events = []

    def backup(item, replay):
        ref, index, room, command, reward, nxt, terminal = item
        address = key(room, command)
        q0 = state["q"].get(address, 0.0)
        target = reward if terminal else reward + max(state["q"].get(key(nxt, c), 0.0) for c in (0, 1))
        q1 = q0 + (target - q0) / 2.0
        state["q"][address] = q1
        state["replay_count" if replay else "ordinary_backups"] += 1
        state["numeric_changes"] += q1 != q0
        events.append({"kind": "replay" if replay else "ordinary", "source_uid": ref, "source_step": index,
                       "address": address, "reward": reward, "before_hex": q0.hex(),
                       "target_hex": target.hex(), "after_hex": q1.hex()})

    for i, (s, r) in enumerate(zip(steps, rewards)):
        item = [uid, i, s["room"], s["command"], r, s["next_room"], s["outcome"] in TERMINALS]
        state["buffer"].append(item)
        state["buffer"] = state["buffer"][-64:]
        backup(item, False)
    state["history"].append(uid)
    for item in state["buffer"][::-1][:state["replay_backups"]]:
        backup(item, True)
    return events


def audit(directory):
    counts = Counter()
    results = []
    phase = None
    previous_uid = 0
    consumed = set()
    run = None
    phase_order = []
    seq = -1
    with (directory / "raw.jsonl").open(encoding="utf-8") as handle:
        for seq, line in enumerate(handle):
            record = json.loads(line)
            assert record["seq"] == seq
            assert json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" == line
            tag, p, ctx = record["tag"], record["payload"], record["context"]
            if tag == "RUN_START":
                assert seq == 0
                run = p
                phase = run["phase"]
                contract = run["contract"]
                assert contract == json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
                for rel, digest in run["inputs"].items():
                    assert sha(ROOT / rel) == digest, rel
                expected_cases = [contract["wiring_case"]] if phase == "wiring" else contract["cases"]
                expected_order = [(c["id"], arm) for c in expected_cases for arm in contract["arms"]]
            elif tag == "STREAM_INITIAL":
                spec = p["case"]
                arm = ctx["arm"]
                phase_order.append((spec["id"], arm))
                assert phase_order == expected_order[:len(phase_order)]
                assert spec == expected_cases[(len(phase_order) - 1) // 4]
                depth = spec["decision_points"]
                assert p["public_task"] == {"rooms": list(range(depth)), "start": 0, "goal": depth, "horizon": 12}
                controller = {"mappings": sorted(spec["controller_mappings"]),
                              "protected": sorted(spec["protected_addresses"]), "revisions": []}
                assert p["controller"] == controller
                mapping = {(r, c): x for r, c, x in controller["mappings"]}
                state = model(arm)
                assert state == p["learner"]
                initial_counts = Counter(counts)
                counts["source_instances"] += 1
                counts["source_mapping_initializations"] += len(mapping)
                rows, owned = [], {}
                last_plan_ns = last_update_ns = 0
            elif tag == "POLICY":
                episode = len(rows)
                assert ctx["main_epoch"] == p["episode"] == episode
                coins = [[(episode + 3*r + spec["index"]) % 10 == 7,
                          (episode // 10 + r + spec["index"]) % 2] for r in range(depth)]
                greedy = policy(state, depth)
                program = [coin[1] if coin[0] else greedy[r] for r, coin in enumerate(coins)]
                assert p == {"episode": episode, "greedy": greedy, "program": program, "coins": coins}
            elif tag == "EPISODE_BEGIN":
                previous_uid += 1
                assert p["uid"] == previous_uid
                assert p["kind"] == "main" and p["candidate"] == "fixed_interface_no_diagnosis"
                assert p["controller"] == controller and p["program"] == program and p["coins"] == coins
                counts["rollouts"] += 1
            elif tag == "EPISODE_COMPLETE":
                expected_steps = []
                room = 0
                for t in range(12):
                    command = program[room]
                    physical = mapping.get((room, command), command)
                    collision = physical != spec["passable_exits"][room]
                    nxt = room if collision else room + 1
                    outcome = "COLLISION" if collision else "SUCCESS" if nxt == depth else "NEXT"
                    if t == 11 and outcome == "NEXT":
                        outcome = "TIMEOUT"
                    expected_steps.append({"room": room, "cell": [2*room, 0], "revision": "initial",
                                           "command": command, "executed": physical, "next_room": nxt,
                                           "next_cell": [2*nxt, 0], "outcome": outcome})
                    room = nxt
                    if outcome in TERMINALS:
                        break
                assert p == {"uid": previous_uid, "steps": expected_steps, "terminal": outcome}
                raw = p
                owned[p["uid"]] = p
                counts["steps"] += len(expected_steps)
            elif tag == "LEARN":
                assert p["uid"] == raw["uid"] and p["uid"] not in consumed
                assert p["packet"]["facts"] == raw
                assert set(p["packet"]) == ({"facts"} if arm == "F" else {"facts", "rewards"})
                rewards = None if arm == "F" else [1.0 if s["outcome"] == "SUCCESS" else
                          -1.0 if arm != "Q-R" and s["outcome"] in {"COLLISION", "TIMEOUT"} else 0.0 for s in raw["steps"]]
                if rewards is not None:
                    assert p["packet"]["rewards"] == rewards
                expected_updates = update(state, raw, rewards)
                assert p["updates"] == expected_updates
                for event in expected_updates:
                    assert event["source_uid"] in owned
                    assert event["source_step"] < len(owned[event["source_uid"]]["steps"])
                assert p["after"] == state
                consumed.add(p["uid"])
                if arm == "F":
                    counts["fact_field_updates"] += 2*len(raw["steps"])
                    assert "q" not in p["after"]
                else:
                    assert "edges" not in p["after"] and "commands" not in p["after"]
                counts["observations_consumed"] += 1
                counts["ordinary_backups"] += sum(e["kind"] == "ordinary" for e in expected_updates)
                counts["replay_backups"] += sum(e["kind"] == "replay" for e in expected_updates)
                counts["numeric_changes"] += sum(e["before_hex"] != e["after_hex"] for e in expected_updates)
            elif tag == "MAIN_CHECKPOINT":
                last = raw["steps"][-1]
                expected = {"episode": len(rows), "uid": raw["uid"], "terminal": raw["terminal"],
                            "steps": counts["steps"] - initial_counts["steps"], "rollouts": len(rows)+1,
                            "ordinary_backups": counts["ordinary_backups"] - initial_counts["ordinary_backups"],
                            "replay_backups": counts["replay_backups"] - initial_counts["replay_backups"],
                            "fact_field_updates": counts["fact_field_updates"] - initial_counts["fact_field_updates"],
                            "failure_at_exploratory_deviation": raw["terminal"] != "SUCCESS" and coins[last["room"]][0] and last["command"] != greedy[last["room"]],
                            "learner_snapshot_bytes": len(json.dumps(state, sort_keys=True).encode())}
                assert {k: p[k] for k in expected} == expected
                assert p["plan_ns"] >= last_plan_ns and p["update_ns"] >= last_update_ns
                last_plan_ns, last_update_ns = p["plan_ns"], p["update_ns"]
                rows.append(p)
            elif tag == "BOUNDARY_CHALLENGES":
                assert phase == "wiring" and len(rows) == 1 and rows[0]["terminal"] == "COLLISION"
                assert p == {"additional_native": 0, "rejected": ["already_consumed", "copied_not_issued"] +
                             (["reward_packet_to_F"] if arm == "F" else [])}
            elif tag == "STREAM_FINAL":
                n = 2 if phase == "wiring" else 48
                assert len(rows) == n
                if phase == "wiring":
                    assert rows[1]["terminal"] == ("COLLISION" if arm == "Q-R" else "SUCCESS")
                successes = [r["terminal"] == "SUCCESS" for r in rows]
                target = next((i for i in range(11, n) if all(successes[i-11:i+1])), None)
                expected = {"case": spec["id"], "decision_points": depth, "arm": arm, "main_tasks": n,
                            "main_successes": sum(successes), "prefix_successes": {str(k): sum(successes[:k]) for k in (12, 24, 48)},
                            "cold_successes": sum(successes[:24]), "continued_successes": sum(successes[24:]),
                            "counts": dict(counts - initial_counts),
                            "target": {"status": "REACHED" if target is not None else "NOT_REACHED_RIGHT_CENSORED",
                                       "main_index_1based": target+1 if target is not None else None,
                                       "steps": rows[target]["steps"] if target is not None else None,
                                       "later_failures": sum(not x for x in successes[target+1:]) if target is not None else None},
                            "failure_at_exploratory_deviation": sum(r["failure_at_exploratory_deviation"] for r in rows),
                            "plan_ns": last_plan_ns, "update_ns": last_update_ns,
                            "final_learner": state, "final_controller": controller, "curve": rows}
                assert {k: p[k] for k in expected} == expected
                assert p["wall_seconds"] >= 0
                results.append(p)
            elif tag == "RESULT":
                assert phase_order == expected_order
                assert p == {"streams": results, "counts": dict(counts)}
                assert json.loads((directory / "result.json").read_text()) == p
            elif tag == "FINAL":
                assert p["complete"] and p["child_exit_code"] == 0 and p["input_bytes_unchanged"]
                assert p["counts"] == dict(counts)
                assert p == json.loads((directory / "exit.json").read_text())
                assert p["wall_seconds"] >= 0 and p["cpu_seconds"] >= 0
            else:
                raise AssertionError("unexpected/failed record " + tag)
    assert tag == "FINAL" and phase_order == expected_order
    assert counts["rollouts"] == counts["observations_consumed"] == len(consumed)
    assert counts["rollouts"] <= contract["limits"][phase]["rollouts"]
    assert counts["steps"] <= contract["limits"][phase]["steps"]
    assert counts["replay_backups"] <= contract["limits"][phase]["replay_backups"]
    tree = ast.parse((HERE / "experiment.py").read_text(encoding="utf-8"))
    qclass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DirectQ")
    assert not qclass.bases
    assert not {n.attr for n in ast.walk(qclass) if isinstance(n, ast.Attribute)} & {"edges", "commands", "executed", "_doors"}
    calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls & {"revised", "diagnose", "lookup", "run_phase", "RewardLearner"}
    return {"complete": True, "phase": phase, "records": seq+1, "streams": len(results),
            "counts": dict(counts), "native_child_exit_code": 0,
            "all_raw_physics_command_Q_and_F_states_reconciled": True,
            "own_experience_replay_order_and_binary64_backups_reconciled": True,
            "actual_no_controller_edits_or_extra_environment_trials": True,
            "F_original_component_and_reward_free_packets": True,
            "DirectQ_no_fact_inheritance_or_command_model": True,
            "ordinary_own_observation_once_with_explicit_computational_replay": True,
            "current_all_input_pins_match": True,
            "raw_sha256": sha(directory / "raw.jsonl"),
            "old_fixture_checker_native_executed": 0,
            "runtime_identity_reconstructed_from_JSON": False,
            "independent_expert_or_science_gate": False}


if __name__ == "__main__":
    destination = Path(sys.argv[1])
    output = destination / "audit_result.json"
    assert not output.exists(), "This review output already exists; no overwrite/retry"
    started = time.perf_counter()
    try:
        result = audit(destination)
        code = 0
    except BaseException as exc:
        result = {"complete": False, "error": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        traceback.print_exc()
        code = 1
    result.update(child_exit_code=code, wall_seconds=time.perf_counter()-started)
    with output.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2)
        f.write("\n")
    print(json.dumps(result))
    raise SystemExit(code)
