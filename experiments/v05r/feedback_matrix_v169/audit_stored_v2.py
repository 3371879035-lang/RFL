"""Independent stdlib stored-data reconstruction; never imports experiment.py.

Checks actual world steps, action programs, all factual/TD updates, ownership
references, reuse, repairs, continuous state, budgets and reported metrics.
It does not reconstruct live runtime identity from serialized data.
"""
from pathlib import Path
from collections import Counter
import argparse
import ast
import hashlib
import json
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def key(*x):
    return json.dumps(x, separators=(",", ":"))


def empty(channel):
    s = {"type": "FactLearner" if channel == "F" else "RewardLearner", "edges": {},
         "commands": {}, "history": [], "fact_updates": 0}
    if channel != "F":
        s.update(q={}, numeric_changes=0, td_updates=0)
    return s


def program(s, controller, coins, depth, prefix=()):
    rev = dict(controller["revisions"])
    actions = [0] * depth
    for room in range(depth):
        version = rev.get(room, "initial")
        predictions = [s["commands"].get(key(room, version, c), c) for c in (0, 1)]
        if "q" in s:
            scores = [(s["q"].get(key(room, predictions[c]), 0.0), -c, c) for c in (0, 1)]
            chosen = max(scores)[2]
        else:
            available = []
            for c in (0, 1):
                edge = s["edges"].get(key(room, predictions[c]))
                if edge is None or edge["outcome"] != "COLLISION":
                    available.append((0 if edge else 1, c))
            if available:
                chosen = min(available)[1]
            else:
                unseen = [c for c in (0, 1) if key(room, version, c) not in s["commands"]]
                chosen = unseen[0] if unseen else 0
        actions[room] = coins[room][1] if coins[room][0] else chosen
    actions[:len(prefix)] = prefix
    return actions


def revised(ctrl, removals, witness):
    mappings = {(r, c): x for r, c, x in ctrl["mappings"]}
    protected = {tuple(x) for x in ctrl["protected"]}
    rev = dict(ctrl["revisions"])
    seen = {(s["room"], s["command"], s["executed"]) for s in witness["steps"] if s["command"] != s["executed"]}
    changes = sorted({tuple(x) for x in removals})
    for r, c in changes:
        assert (r, c) not in protected and (r, c) in mappings
        assert (r, c, mappings[r, c]) in seen
        del mappings[r, c]
    for r in {r for r, _ in changes}:
        rev[r] = digest([rev.get(r, "initial"), [c for rr, c in changes if rr == r]])
    return {"mappings": [[r, c, x] for (r, c), x in sorted(mappings.items())],
            "protected": ctrl["protected"], "revisions": [[r, v] for r, v in sorted(rev.items())]}


def catalogue(factual):
    mismatches = [[s["room"], s["command"]] for s in factual["steps"] if s["command"] != s["executed"]]
    prefix = [s["command"] for s in factual["steps"]]
    out = [{"name": "keep", "removals": [], "prefix": []}]
    if mismatches:
        out.append({"name": "remove_first", "removals": [mismatches[0]], "prefix": prefix})
        if len(mismatches) > 1:
            out.append({"name": "remove_last", "removals": [mismatches[-1]], "prefix": prefix})
            out.append({"name": "joint", "removals": [list(x) for x in sorted({tuple(x) for x in mismatches})], "prefix": prefix})
    out.append({"name": "practice_alternative", "removals": [], "prefix": prefix[:-1] + [1 - prefix[-1]]})
    return out


def improve(new, old):
    if new["terminal"] == "SUCCESS":
        return old["terminal"] != "SUCCESS"
    return old["terminal"] != "SUCCESS" and new["steps"][-1]["next_room"] > old["steps"][-1]["next_room"]


def audit(path):
    receipt = json.loads((path / "exit.json").read_text())
    assert receipt["complete"] and receipt["child_exit_code"] == 0 and receipt["input_bytes_unchanged"]
    contract = json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
    counts, stream_counts = Counter(), Counter()
    observations, consumed, query_cache, begins = {}, set(), {}, {}
    states, actors, specs, rows, cursors, menus, best, selected = {}, {}, {}, {}, {}, {}, {}, {}
    trial_per_main, lookups, source_initial = Counter(), {}, {}
    complete_streams, challenges = [], []
    seen_tags = Counter()
    main_observations, trial_totals, hits = {}, Counter(), Counter()
    phase = receipt["phase"]
    result_payload = None
    count_keys = ("rollouts", "steps", "controller_transactions", "controller_entries_removed",
                  "source_instances", "source_mapping_initializations", "fact_field_updates",
                  "history_appends", "td_updates", "numeric_changes")
    records = 0
    with (path / "raw.jsonl").open(encoding="utf-8") as f:
        for n, line in enumerate(f):
            event = json.loads(line)
            assert event["seq"] == n
            records += 1
            tag, p, ctx = event["tag"], event["payload"], event["context"]
            seen_tags[tag] += 1
            sid = (ctx.get("case"), ctx.get("arm"))
            epoch = ctx.get("main_epoch")
            channel = sid[1].split("-")[1] if sid[1] else None
            mode = sid[1].split("-")[0] if sid[1] else None
            if tag == "RUN_START":
                assert p["contract"] == contract and p["phase"] == phase
                for rel, h in p["inputs"].items():
                    assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == h
            elif tag == "STREAM_INITIAL":
                assert sid not in states
                spec = p["case"]
                assert spec in contract["cases"] if phase == "matrix" else spec == contract["wiring_case"]
                assert p["arm"] == sid[1] and spec["id"] == sid[0]
                assert p["public_task"] == {"rooms": list(range(spec["decision_points"])), "start": 0,
                                            "goal": spec["decision_points"], "horizon": 12}
                assert p["learner"] == empty(channel)
                expected_actor = {"mappings": sorted(spec["controller_mappings"]),
                                  "protected": sorted(spec["protected_addresses"]), "revisions": []}
                assert p["controller"] == expected_actor
                source_initial[sid] = expected_actor
                states[sid], actors[sid], specs[sid] = empty(channel), expected_actor, spec
                rows[sid], cursors[sid], query_cache[sid], stream_counts[sid] = [], 0, {}, Counter()
                counts["source_instances"] += 1
                counts["source_mapping_initializations"] += len(expected_actor["mappings"])
                stream_counts[sid]["source_instances"] += 1
                stream_counts[sid]["source_mapping_initializations"] += len(expected_actor["mappings"])
            elif tag == "EPISODE_BEGIN":
                assert p["uid"] not in begins
                coins = [[(epoch + 3 * r + specs[sid]["index"]) % 10 == 7,
                          (epoch // 10 + r + specs[sid]["index"]) % 2] for r in range(specs[sid]["decision_points"])]
                assert p["coins"] == coins
                if p["kind"] == "main":
                    assert epoch == len(rows[sid]) and p["candidate"] == "ordinary"
                    expected_controller, prefix = actors[sid], []
                    trial_per_main[sid] = 0
                    selected[sid] = None
                else:
                    assert p["kind"] == "trial"
                    c = next(x for x in menus[sid] if x["name"] == p["candidate"])
                    witness = main_observations[sid]
                    assert witness["terminal"] != "SUCCESS"
                    expected_controller = revised(actors[sid], c["removals"], witness) if c["removals"] else actors[sid]
                    prefix = c["prefix"]
                    trial_per_main[sid] += 1
                    trial_totals[sid] += 1
                    assert trial_per_main[sid] <= 2 and trial_totals[sid] <= 12
                assert p["controller"] == expected_controller
                assert p["program"] == program(states[sid], expected_controller, coins, specs[sid]["decision_points"], prefix)
                begins[p["uid"]] = (sid, p)
                counts["rollouts"] += 1
                stream_counts[sid]["rollouts"] += 1
            elif tag == "EPISODE_COMPLETE":
                owner, begin = begins[p["uid"]]
                assert owner == sid and p["uid"] not in observations
                assert set(p) == {"uid", "steps", "terminal"}
                room = 0
                mappings = {(r, c): x for r, c, x in begin["controller"]["mappings"]}
                rev = dict(begin["controller"]["revisions"])
                for t, s in enumerate(p["steps"]):
                    command = begin["program"][room]
                    actual = mappings.get((room, command), command)
                    nxt = room + 1 if actual == specs[sid]["passable_exits"][room] else room
                    outcome = "COLLISION" if nxt == room else "SUCCESS" if nxt == specs[sid]["decision_points"] else "NEXT"
                    if t == 11 and outcome == "NEXT":
                        outcome = "TIMEOUT"
                    assert s == {"room": room, "cell": [2 * room, 0], "revision": rev.get(room, "initial"),
                                 "command": command, "executed": actual, "next_room": nxt,
                                 "next_cell": [2 * nxt, 0], "outcome": outcome}
                    assert t < 12 and (outcome == "NEXT" or t == len(p["steps"]) - 1)
                    room = nxt
                assert p["terminal"] == p["steps"][-1]["outcome"] in ("SUCCESS", "COLLISION", "TIMEOUT")
                observations[p["uid"]] = p
                query_cache[sid][digest([begin["controller"], begin["program"], begin["coins"]])] = p["uid"]
                if begin["kind"] == "main":
                    main_observations[sid] = p
                    best[sid] = p
                counts["steps"] += len(p["steps"])
                stream_counts[sid]["steps"] += len(p["steps"])
            elif tag == "LEARN":
                uid = p["uid"]
                assert begins[uid][0] == sid and uid not in consumed
                consumed.add(uid)
                observation = observations[uid]
                state = states[sid]
                assert p["before_digest"] == digest(state)
                expected_rewards = [1.0 if s["outcome"] == "SUCCESS" else (-1.0 if channel == "RP" else 0.0)
                                    if s["outcome"] in ("COLLISION", "TIMEOUT") else 0.0 for s in observation["steps"]]
                expected_packet = {"facts": observation}
                if channel != "F":
                    expected_packet["rewards"] = expected_rewards
                assert p["packet"] == expected_packet
                for s in observation["steps"]:
                    k = key(s["room"], s["executed"])
                    old = state["edges"].get(k)
                    fact = {"next_room": s["next_room"], "outcome": s["outcome"], "count": 1 + (old["count"] if old else 0)}
                    if old:
                        assert (old["next_room"], old["outcome"]) == (s["next_room"], s["outcome"])
                    state["edges"][k] = fact
                    state["commands"][key(s["room"], s["revision"], s["command"])] = s["executed"]
                    state["fact_updates"] += 1
                state["history"].append(uid)
                changes, updates = 0, []
                if channel != "F":
                    for s, reward in zip(observation["steps"], expected_rewards):
                        address = key(s["room"], s["executed"])
                        before = state["q"].get(address, 0.0)
                        target = reward if s["outcome"] != "NEXT" else reward + max(state["q"].get(key(s["next_room"], a), 0.0) for a in (0, 1))
                        after = before + (target - before) * 0.5
                        state["q"][address] = after
                        changes += after != before
                        state["numeric_changes"] += after != before
                        state["td_updates"] += 1
                        updates.append({"address": address, "reward": reward, "before_hex": before.hex(),
                                        "target_hex": target.hex(), "after_hex": after.hex()})
                assert p["updates"] == updates and p["after"] == state
                for counter in (counts, stream_counts[sid]):
                    counter["fact_field_updates"] += 2 * len(observation["steps"])
                    counter["history_appends"] += 1
                    counter["td_updates"] += len(updates)
                    counter["numeric_changes"] += changes
            elif tag == "CANDIDATE_MENU":
                factual = main_observations[sid]
                assert p["witness"] == factual["uid"] and factual["terminal"] != "SUCCESS"
                expected = catalogue(factual)
                assert p["catalogue"] == expected and p["remaining"] == 12 - trial_totals[sid]
                if mode == "P":
                    k = cursors[sid] % len(expected)
                    cursors[sid] += 1
                    ordered = expected[k:] + expected[:k]
                else:
                    terminal = factual["steps"][-1]
                    nominal = states[sid]["edges"].get(key(terminal["room"], terminal["command"]))
                    if terminal["command"] != terminal["executed"] and (not nominal or nominal["outcome"] != "COLLISION"):
                        preferred = [c for c in expected if c["removals"] == [[terminal["room"], terminal["command"]]]]
                        ordered = preferred + [c for c in expected if c not in preferred]
                    else:
                        ordered = sorted(expected, key=lambda c: 0 if c["name"] == "keep" else 1 if c["name"] == "practice_alternative" else 2)
                assert p["order"] == [c["name"] for c in ordered]
                menus[sid] = expected
            elif tag == "QUERY_LOOKUP":
                assert mode == "S"
                c = next(c for c in menus[sid] if c["name"] == p["candidate"])
                ctrl = revised(actors[sid], c["removals"], main_observations[sid]) if c["removals"] else actors[sid]
                coins = [[(epoch + 3 * r + specs[sid]["index"]) % 10 == 7,
                          (epoch // 10 + r + specs[sid]["index"]) % 2] for r in range(specs[sid]["decision_points"])]
                expected_program = program(states[sid], ctrl, coins, specs[sid]["decision_points"], c["prefix"])
                qk = digest([ctrl, expected_program, coins])
                assert p["query_key"] == qk and p["cached_uid"] == query_cache[sid].get(qk)
                lookups[sid] = p
            elif tag == "REUSE":
                assert mode == "S" and p["new_learning"] is False
                assert p["uid"] == lookups[sid]["cached_uid"] in consumed
                assert p["query_key"] == lookups[sid]["query_key"] and begins[p["uid"]][0] == sid
                hits[sid] += 1
            elif tag == "TRIAL_ASSESS":
                obs = observations[p["uid"]]
                assert begins[p["uid"]][0] == sid and p["candidate"] in menus[sid]
                addresses = {(s["room"], s["command"]) for s in obs["steps"] if s["command"] == s["executed"]}
                supported = all(tuple(x) in addresses for x in p["candidate"]["removals"])
                preferred = improve(obs, best[sid]) and supported
                assert p["supported"] == supported and p["preferred"] == preferred and p["improves_on_uid"] == best[sid]["uid"]
                assert p["paid_this_failure"] == trial_per_main[sid] and p["used_trials"] == trial_totals[sid]
                if preferred:
                    best[sid] = obs
                    selected[sid] = (p["candidate"], obs)
            elif tag == "COMMIT":
                candidate, obs = selected[sid]
                assert candidate["removals"] and p["selected"] == obs["uid"] and p["witness"] == main_observations[sid]["uid"]
                assert p["removals"] == candidate["removals"] and p["before"] == actors[sid]
                expected = revised(actors[sid], candidate["removals"], main_observations[sid])
                assert p["after"] == expected
                actors[sid] = expected
                for counter in (counts, stream_counts[sid]):
                    counter["controller_transactions"] += 1
                    counter["controller_entries_removed"] += len(candidate["removals"])
            elif tag == "MAIN_CHECKPOINT":
                obs = main_observations[sid]
                assert p["episode"] == epoch == len(rows[sid]) and p["uid"] == obs["uid"]
                assert p["terminal"] == obs["terminal"] and p["reached"] == obs["steps"][-1]["next_room"]
                assert p["trial_delta"] == trial_per_main[sid] and p["trials_so_far"] == trial_totals[sid]
                if obs["terminal"] == "SUCCESS":
                    assert trial_per_main[sid] == 0
                assert p["learner"] == states[sid] and p["controller"] == actors[sid]
                assert p["rollouts"] == stream_counts[sid]["rollouts"] and p["steps"] == stream_counts[sid]["steps"]
                assert p["controller_transactions"] == stream_counts[sid]["controller_transactions"]
                assert p["cpu_seconds"] >= 0 and p["wall_seconds"] >= 0
                if rows[sid]:
                    assert p["cpu_seconds"] >= rows[sid][-1]["cpu_seconds"] and p["wall_seconds"] >= rows[sid][-1]["wall_seconds"]
                source_map = {(r, c): x for r, c, x in source_initial[sid]["mappings"]}
                current_map = {(r, c): x for r, c, x in actors[sid]["mappings"]}
                assert all(current_map.get(tuple(ad)) == source_map[tuple(ad)] for ad in source_initial[sid]["protected"])
                rows[sid].append({k: v for k, v in p.items() if k not in ("learner", "controller")})
            elif tag == "BOUNDARY_CHALLENGES":
                assert phase == "wiring" and p["state_unchanged"] and p["native_delta"] == 0
                expected = {"duplicate", "forged_copy", "protected_unread_edit"}
                if channel == "F":
                    expected.add("reward_packet_to_F")
                assert set(p["rejected"]) == expected
                challenges.append(sid)
            elif tag == "STREAM_FINAL":
                success = [x["terminal"] == "SUCCESS" for x in rows[sid]]
                target = next((i for i in range(11, len(success)) if all(success[i - 11:i + 1])), None)
                assert p["case"] == sid[0] and p["arm"] == sid[1] and p["main_tasks"] == len(success)
                assert p["main_successes"] == sum(success) and p["main_failures"] == len(success) - sum(success)
                assert p["prefix_successes"] == {str(n): sum(success[:n]) for n in (12, 24, 48)}
                assert p["cold_successes"] == sum(success[:24]) and p["continued_successes"] == sum(success[24:])
                assert p["trial_rollouts"] == trial_totals[sid] and p["cache_hits"] == hits[sid]
                assert p["counts"] == {k: stream_counts[sid][k] for k in count_keys}
                assert p["target"] == {"status": "REACHED" if target is not None else "NOT_REACHED_RIGHT_CENSORED",
                                       "main_index_1based": target + 1 if target is not None else None,
                                       "cost": rows[sid][target] if target is not None else None}
                assert p["later_failures"] == (sum(not v for v in success[target + 1:]) if target is not None else None)
                assert p["curve"] == rows[sid] and p["final_learner"] == states[sid] and p["final_controller"] == actors[sid]
                complete_streams.append(p)
            elif tag == "RESULT":
                assert p["complete"] and p["streams"] == complete_streams
                assert Counter(p["counts"]) == counts
                result_payload = p
            elif tag == "FINAL":
                assert p == receipt and p["records_before_final"] == n and Counter(p["counts"]) == counts
            else:
                raise AssertionError("unexpected/failed event: " + tag)
    assert consumed == set(observations) == set(begins)
    assert result_payload is not None and seen_tags["FINAL"] == seen_tags["RESULT"] == 1
    result_file = json.loads((path / "result.json").read_text())
    assert result_file == {"counts": result_payload["counts"], "streams": complete_streams}
    if phase == "wiring":
        assert len(complete_streams) == 3 and counts["rollouts"] == 6 and len(challenges) == 3
    else:
        assert len(complete_streams) == 36 and sum(x["main_tasks"] for x in complete_streams) == 1728
        assert {(x["case"], x["arm"]) for x in complete_streams} == {(c["id"], a) for c in contract["cases"] for a in contract["arms"]}
        assert all(len(rows[sid]) == 48 for sid in rows)
    assert counts["rollouts"] <= (6 if phase == "wiring" else 2160)
    assert counts["steps"] <= (72 if phase == "wiring" else 25920)
    assert (path / "raw.jsonl").stat().st_size <= contract["capture_bytes_cap"]
    assert receipt["wall_seconds"] <= contract["wall_seconds_cap"]
    source = ast.parse((HERE / "experiment.py").read_text(encoding="utf-8"))
    pure = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == "FactLearner")
    assert not any(isinstance(n, ast.Attribute) and n.attr in ("q", "reward", "rewards", "returns") for n in ast.walk(pure))
    agent = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == "Agent")
    assert not any(isinstance(n, ast.Attribute) and n.attr in ("_doors", "mappings", "spec", "engine") for n in ast.walk(agent))
    assert all(not isinstance(n, (ast.Import, ast.ImportFrom)) or "rfl" not in ast.unparse(n).lower() for n in source.body)
    return {"complete": True, "phase": phase, "records": records, "counts": dict(counts),
            "streams": len(complete_streams), "main_tasks": sum(x["main_tasks"] for x in complete_streams),
            "all_raw_physics_programs_categorical_and_binary64_TD_reconciled": True,
            "all_own_observations_consumed_once": True, "reward_free_packet_and_no_Q_verified": True,
            "continuous_full_state_no_reset": True, "common_capabilities_and_budgets": True,
            "old_RFL_or_native_calls": 0, "runtime_identity_reconstructed_from_JSON": False,
            "independent_expert_or_science_gate": False,
            "raw_sha256": hashlib.sha256((path / "raw.jsonl").read_bytes()).hexdigest()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("capture", type=Path)
    args = p.parse_args()
    target = args.capture / "audit_result_v2.json"
    if target.exists():
        raise FileExistsError("stored audit output is exclusive; do not silently rerun")
    started = time.perf_counter()
    try:
        result = audit(args.capture)
        result.update(child_exit_code=0, wall_seconds=time.perf_counter() - started)
    except BaseException as exc:
        result = {"complete": False, "child_exit_code": 1, "type": type(exc).__name__, "error": str(exc),
                  "traceback": traceback.format_exc(), "wall_seconds": time.perf_counter() - started}
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return result["child_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
