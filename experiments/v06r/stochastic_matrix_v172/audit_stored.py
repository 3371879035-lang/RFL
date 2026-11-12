"""Independent stdlib stored review: no experiment/learner/native imports."""
from collections import Counter
from pathlib import Path
import ast
import copy
import hashlib
import json
import random
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TERMINALS = ("SUCCESS", "COLLISION", "TIMEOUT")


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def initial(task, arm):
    if arm == "F0":
        return {"type": "FactualLearner", "task": task, "counts": {}, "history": []}
    state = {"type": "DirectQLearner" if arm.startswith("RL-") else "HybridQLearner", "task": task,
             "failure_reward": -1.0 if arm.endswith("RP") else 0.0, "q": {}, "buffer": [], "history": [],
             "ordinary": 0, "replays": 0, "models": 0, "numeric_changes": 0}
    if arm.startswith("F-"):
        state["counts"] = {}
    return state


def policy(state):
    d = state["task"]["goal"]
    actions, details = {}, []
    if state["type"] == "FactualLearner":
        future = 1.0
        for room in range(d-1, -1, -1):
            scores = []
            for action in (0, 1):
                address = f"{room}:{action}"
                n, m = state["counts"].get(address, (0, 0))
                prob = (n+1)/(n+m+2)
                score = prob * future
                scores.append(score)
                details.append({"address": address, "p_hex": prob.hex(), "value_hex": score.hex()})
            actions[room] = 0 if scores[0] >= scores[1] else 1
            future = scores[actions[room]]
        expansions = 2*d
    else:
        for room in range(d):
            values = [state["q"].get(f"{room}:{a}", 0.0) for a in (0, 1)]
            actions[room] = 0 if values[0] >= values[1] else 1
            details.extend({"address": f"{room}:{a}", "value_hex": values[a].hex()} for a in (0, 1))
        expansions = 0
    return [actions[r] for r in range(d)], details, expansions


def updates(state, obs, rewards):
    model_events, events = [], []

    def model_record():
        for step in obs["steps"]:
            address = f'{step["room"]}:{step["command"]}'
            before = list(state["counts"].get(address, (0, 0)))
            after = list(before)
            forward = step["next_room"] == step["room"]+1 and step["outcome"] in ("NEXT", "SUCCESS")
            assert forward or step["next_room"] == step["room"] and step["outcome"] == "COLLISION"
            after[0 if forward else 1] += 1
            state["counts"][address] = after
            model_events.append({"address": address, "before": before, "after": after})

    def backup(address, target):
        before = state["q"].get(address, 0.0)
        after = before + 0.5*(target-before)
        state["q"][address] = after
        state["numeric_changes"] += before != after
        return {"address": address, "before_hex": before.hex(), "target_hex": target.hex(), "after_hex": after.hex()}

    def real_backup(item, kind):
        uid, i, room, command, reward, nxt, terminal = item
        target = reward if terminal else reward + max(state["q"].get(f"{nxt}:{a}", 0.0) for a in (0, 1))
        event = {"kind": kind, "source_uid": uid, "source_step": i, "reward": reward,
                 **backup(f"{room}:{command}", target)}
        state["ordinary" if kind == "ordinary" else "replays"] += 1
        events.append(event)

    if state["type"] == "FactualLearner":
        assert rewards is None
        model_record()
    else:
        assert len(rewards) == len(obs["steps"])
        for i, (s, r) in enumerate(zip(obs["steps"], rewards)):
            item = [obs["uid"], i, s["room"], s["command"], r, s["next_room"], s["outcome"] in TERMINALS]
            state["buffer"].append(item)
            state["buffer"] = state["buffer"][-64:]
            real_backup(item, "ordinary")
        if state["type"] == "DirectQLearner":
            for item in state["buffer"][::-1][:12]:
                real_backup(item, "replay")
        else:
            model_record()
            contexts = sorted([tuple(int(v) for v in k.split(":")) for k in state["counts"]], key=lambda a: (-a[0], a[1]))
            for i in range(min(12, len(state["buffer"]))):
                room, command = contexts[i % len(contexts)]
                address = f"{room}:{command}"
                n, m = state["counts"][address]
                probability = (n+1)/(n+m+2)
                forward = 1.0 if room == state["task"]["goal"]-1 else max(state["q"].get(f"{room+1}:{a}", 0.0) for a in (0,1))
                target = probability*forward + (1.0-probability)*state["failure_reward"]
                events.append({"kind": "model", "counts": [n, m], "p_hex": probability.hex(),
                               "forward_target_hex": forward.hex(), "failure_reward": state["failure_reward"],
                               **backup(address, target)})
                state["models"] += 1
    state["history"].append(obs["uid"])
    return events, model_events


def rebuild_tapes(plan):
    blocks = []
    for seed in plan["workload"]["local_engineering_seed_ids"]:
        for mirror in (0, 1):
            a = random.Random(f"V172|{seed}|{mirror}|train_env")
            b = random.Random(f"V172|{seed}|{mirror}|train_action")
            c = random.Random(f"V172|{seed}|{mirror}|eval_env")
            blocks.append({"seed": seed, "mirror": mirror,
                           "train_env": [[a.random() for _ in range(3)] for _ in range(64)],
                           "train_action": [[[b.random(), b.random()] for _ in range(3)] for _ in range(64)],
                           "eval_env": [[c.random() for _ in range(3)] for _ in range(32)]})
    return blocks


def audit(directory):
    counts, consumed, eval_ids = Counter(), set(), set()
    results, stream_order = [], []
    previous_uid = 0
    reconstruction_draws = 0
    bank = None
    with (directory / "raw.jsonl").open(encoding="utf-8") as f:
        for seq, line in enumerate(f):
            r = json.loads(line)
            assert r["seq"] == seq
            assert json.dumps(r, sort_keys=True, separators=(",", ":"))+"\n" == line
            tag, p, ctx = r["tag"], r["payload"], r["context"]
            if tag == "RUN_START":
                assert seq == 0
                phase, plan, contract = p["phase"], p["plan"], p["contract"]
                assert plan == json.loads((ROOT / contract["plan"]).read_text(encoding="utf-8"))
                assert contract == json.loads((HERE / "contract.json").read_text(encoding="utf-8"))
                for rel, h in p["inputs"].items():
                    assert sha(ROOT / rel) == h, rel
                arms = [a["id"] for a in plan["arms"]]
                order = ([(None,None,None,a) for a in arms] if phase == "wiring" else
                         [(s,c["mirror"],prob,a) for s in plan["workload"]["local_engineering_seed_ids"]
                          for c in plan["environment"]["structural_case_sources"]
                          for prob in plan["environment"]["accidental_failure_probability"] for a in arms])
            elif tag == "TAPES":
                assert phase == "matrix" and counts["rollouts"] == 0
                blocks = rebuild_tapes(plan)
                reconstruction_draws = 5376
                assert p["blocks"] == blocks and p["sha256"] == digest(blocks) and p["PRNG_random_calls"] == 5376
                tapes = {(b["seed"], b["mirror"]): b for b in blocks}
                counts["environment_PRNG_draws"] += 2304
                counts["exploration_PRNG_draws"] += 3072
            elif tag == "STREAM_INITIAL":
                arm = ctx["arm"]
                token = (None,None,None,arm) if phase == "wiring" else (ctx["seed"],ctx["mirror"],ctx["p"],arm)
                stream_order.append(token)
                assert stream_order == order[:len(stream_order)]
                context = {k:v for k,v in ctx.items()}
                initial_counts = Counter(counts)
                case = p["case"]
                if phase == "wiring":
                    assert case == {"passable_exits":[0],"controller_mappings":[[0,0,1],[0,1,0],[4,0,1],[5,1,0]],
                                    "protected_addresses":[[4,0],[5,1]]}
                    probability = 0.1
                else:
                    assert case == next(c for c in plan["environment"]["structural_case_sources"] if c["mirror"] == ctx["mirror"])
                    probability = ctx["p"]
                    tape = tapes[ctx["seed"],ctx["mirror"]]
                depth = len(case["passable_exits"])
                source = {"doors":case["passable_exits"],"p":probability,"mappings":sorted(case["controller_mappings"]),
                          "protected":case["protected_addresses"]}
                assert p["source"] == source
                mapping = {(s,a):b for s,a,b in source["mappings"]}
                task = {"rooms":list(range(depth)),"goal":depth,"horizon":12}
                assert p["public"] == task
                state = initial(task,arm)
                assert p["learner"] == state
                counts["source_instances"] += 1
                counts["source_mapping_initializations"] += len(mapping)
                assert p["source_instances"] == counts["source_instances"]
                rows,banks,trained,owned = [],[],[],{}
                train_steps=successes=update_total=previous_policy_ns=0
                assert bank is None
            elif tag == "TRAIN_POLICY":
                assert phase == "matrix" and bank is None
                epoch=len(rows)
                assert ctx["train_epoch"] == epoch
                greedy,details,expansions=policy(state)
                coins=[[u<0.1,int(v*2)] for u,v in tape["train_action"][epoch]]
                program=[c[1] if c[0] else greedy[i] for i,c in enumerate(coins)]
                assert p == {"greedy":greedy,"program":program,"coins":coins,"readout":details,"planning_edge_expansions":expansions}
                counts["planning_edge_expansions"] += expansions
            elif tag == "FREEZE_BEGIN":
                assert bank is None
                checkpoint=2 if phase=="wiring" else len(rows)
                assert p["checkpoint"]==ctx["checkpoint"]==checkpoint
                assert checkpoint == (2 if phase=="wiring" else (0,16,32,48,64)[len(banks)])
                assert p["state"]==state and p["train_state_sha256"]==digest(state) and p["nonalias_runtime_asserted"]
                greedy,details,expansions=policy(state)
                expected_program=[1] if phase=="wiring" else greedy
                assert p["program"]==expected_program and p["greedy"]==greedy and p["readout"]==details
                assert p["scripted"]==(phase=="wiring") and p["planning_edge_expansions"]==expansions and p["policy_ns"]>=0
                counts["planning_edge_expansions"] += expansions
                bank={"start":p,"state":copy.deepcopy(state),"uids":[],"successes":0,"steps":0}
            elif tag == "EPISODE_BEGIN":
                previous_uid+=1
                assert p["uid"]==previous_uid
                mode=p["mode"]
                if mode=="eval":
                    assert bank is not None and state==bank["state"]
                    i=len(bank["uids"])
                    assert ctx["bank_item"]==i
                    expected_uniforms=[[0.8],[0.9]][i] if phase=="wiring" else tape["eval_env"][i]
                    expected_program=bank["start"]["program"]
                else:
                    assert mode=="train" and bank is None
                    if phase=="wiring":
                        assert ctx["train_epoch"]==len(trained)
                        expected_uniforms=[plan["wiring"]["scripted_environment_uniforms"][len(trained)]]
                        expected_program=[1]
                    else:
                        assert ctx["train_epoch"]==len(rows)
                        expected_uniforms=tape["train_env"][len(rows)]
                        expected_program=program
                assert p["program"]==expected_program and p["environment_uniforms"]==expected_uniforms
                counts["rollouts"]+=1
                counts[mode+"_rollouts"]+=1
            elif tag == "EPISODE_COMPLETE":
                steps,causes=[],[]
                room=0
                for t in range(12):
                    command=expected_program[room]
                    executed=mapping.get((room,command),command)
                    if executed!=source["doors"][room]:
                        nxt,outcome,cause=room,"COLLISION","BLOCKED"
                    elif expected_uniforms[room]<probability:
                        nxt,outcome,cause=room,"COLLISION","ACCIDENT"
                    else:
                        nxt=room+1
                        outcome,cause=("SUCCESS" if nxt==depth else "NEXT"),"NONE"
                    if t==11 and outcome=="NEXT":
                        outcome,cause="TIMEOUT","HORIZON"
                    steps.append({"room":room,"command":command,"executed":executed,"next_room":nxt,"outcome":outcome})
                    causes.append(cause)
                    room=nxt
                    if outcome in TERMINALS:
                        break
                obs={"uid":previous_uid,"steps":steps,"terminal":outcome}
                assert p=={"observation":obs,"audit_causes":causes,"source_unchanged":True}
                counts["steps"]+=len(steps)
                counts[mode+"_steps"]+=len(steps)
                if mode=="eval":
                    bank["uids"].append(previous_uid)
                    bank["steps"]+=len(steps)
                    bank["successes"]+=outcome=="SUCCESS"
                    eval_ids.add(previous_uid)
                else:
                    owned[previous_uid]=obs
            elif tag == "LEARN":
                assert bank is None and mode=="train" and p["uid"]==obs["uid"] and p["uid"] not in consumed
                assert p["uid"] in owned and p["packet"]["facts"]==obs
                expected_keys={"facts"} if arm=="F0" else {"facts","rewards"}
                assert set(p["packet"])==expected_keys
                rewards=None if arm=="F0" else [1.0 if s["outcome"]=="SUCCESS" else state["failure_reward"] if s["outcome"] in ("COLLISION","TIMEOUT") else 0.0 for s in obs["steps"]]
                if rewards is not None:
                    assert p["packet"]["rewards"]==rewards
                actual_updates,model_updates=updates(state,obs,rewards)
                assert p["updates"]==actual_updates and p["model_updates"]==model_updates and p["after"]==state
                assert p["update_ns"]>=0
                for u in actual_updates:
                    if u["kind"]!="model":
                        assert u["source_uid"] in owned and u["source_uid"] not in eval_ids
                        assert u["source_step"]<len(owned[u["source_uid"]]["steps"])
                assert not set(state["history"]) & eval_ids
                consumed.add(p["uid"])
                counts["observations_consumed"]+=1
                counts["history_appends"]+=1
                counts["ordinary_backups"]+=sum(u["kind"]=="ordinary" for u in actual_updates)
                counts["replay_backups"]+=sum(u["kind"]=="replay" for u in actual_updates)
                counts["model_backups"]+=sum(u["kind"]=="model" for u in actual_updates)
                counts["numeric_changes"]+=sum(u["before_hex"]!=u["after_hex"] for u in actual_updates)
                counts["fact_count_updates"]+=len(model_updates)
                update_total+=p["update_ns"]
                if phase=="wiring":
                    trained.append(obs["terminal"])
            elif tag == "TRAIN_CHECKPOINT":
                assert phase=="matrix" and bank is None
                train_steps+=len(obs["steps"])
                successes+=obs["terminal"]=="SUCCESS"
                last=obs["steps"][-1]
                expected={"epoch":len(rows)+1,"uid":obs["uid"],"terminal":obs["terminal"],"successes":successes,
                          "failures":len(rows)+1-successes,"train_steps":train_steps,
                          "ordinary_backups":counts["ordinary_backups"]-initial_counts["ordinary_backups"],
                          "replay_backups":counts["replay_backups"]-initial_counts["replay_backups"],
                          "model_backups":counts["model_backups"]-initial_counts["model_backups"],
                          "fact_count_updates":counts["fact_count_updates"]-initial_counts["fact_count_updates"],
                          "failure_at_exploratory_deviation":obs["terminal"]!="SUCCESS" and coins[last["room"]][0] and last["command"]!=greedy[last["room"]],
                          "update_ns":update_total,"state_sha256":digest(state),
                          "state_serialized_bytes":len(json.dumps(state,sort_keys=True).encode())}
                assert {k:p[k] for k in expected}==expected
                assert p["policy_ns"]>=previous_policy_ns
                previous_policy_ns=p["policy_ns"]
                rows.append(p)
            elif tag == "BOUNDARY_CHALLENGES":
                assert phase=="wiring" and trained==["SUCCESS","COLLISION"]
                assert p=={"rejected":["duplicate_consumption","copied_unissued"]+(["reward_packet_to_F0"] if arm=="F0" else []),
                           "native_delta":0,"frozen_has_no_learn":True}
                if "counts" in state:
                    assert state["counts"]=={"0:1":[1,1]}
            elif tag == "FREEZE_END":
                assert bank is not None and state==bank["state"]
                n=2 if phase=="wiring" else 1 if probability==0.0 else 32
                assert len(bank["uids"])==n
                expected={"checkpoint":bank["start"]["checkpoint"],"uids":bank["uids"],"episodes":n,
                          "successes":bank["successes"],"steps":bank["steps"],"mean_success":bank["successes"]/n,
                          "program":bank["start"]["program"],"frozen_state_sha256":digest(state),
                          "train_state_sha256_after":digest(state),"frozen_state_sha256_after":digest(state),
                          "learning_writes":0,"policy_ns":bank["start"]["policy_ns"],
                          "planning_edge_expansions":bank["start"]["planning_edge_expansions"]}
                assert p==expected
                banks.append(p)
                bank=None
            elif tag == "STREAM_FINAL":
                assert bank is None
                if phase=="wiring":
                    assert len(banks)==1 and banks[0]["successes"]==2
                    expected={"arm":arm,"trained":["SUCCESS","COLLISION"],"bank":banks[0],"final_learner":state}
                else:
                    assert len(rows)==64 and [b["checkpoint"] for b in banks]==[0,16,32,48,64]
                    expected={**context,"train_tasks":64,"train_successes":successes,"train_steps":train_steps,
                              "counts":dict(counts-initial_counts),"train_curve":rows,"eval_banks":banks,
                              "final_learner":state,"source_unchanged":True}
                assert p==expected
                results.append(p)
            elif tag == "RESULT":
                assert stream_order==order and p=={"streams":results,"counts":dict(counts)}
                assert p==json.loads((directory/"result.json").read_text(encoding="utf-8"))
            elif tag == "FINAL":
                assert p["complete"] and p["child_exit_code"]==0 and p["input_bytes_unchanged"] and p["error"] is None
                assert p["counts"]==dict(counts) and p==json.loads((directory/"exit.json").read_text())
                assert p["wall_seconds"]>=0 and p["cpu_seconds"]>=0
                receipt=p
            else:
                raise AssertionError("unexpected/failed record "+tag)
    assert tag=="FINAL" and stream_order==order
    assert counts["train_rollouts"]==counts["observations_consumed"]==len(consumed)
    assert counts["eval_rollouts"]==len(eval_ids) and not consumed & eval_ids
    for name in ("rollouts","steps"):
        assert counts[name]<=contract["phase_limits"][phase][name]
    assert counts["replay_backups"]+counts["model_backups"]<=contract["phase_limits"][phase]["extra_Q_backups"]
    assert (directory/"raw.jsonl").stat().st_size<=contract["phase_limits"][phase]["capture_bytes"]
    assert receipt["wall_seconds"]<=contract["phase_limits"][phase]["wall_seconds"]
    tree=ast.parse((HERE/"experiment.py").read_text(encoding="utf-8"))
    qclass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="DirectQLearner")
    assert not qclass.bases
    assert not {n.attr for n in ast.walk(qclass) if isinstance(n,ast.Attribute)} & {"model","counts","executed","_doors","_p"}
    fclass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="FactualLearner")
    assert not {n.attr for n in ast.walk(fclass) if isinstance(n,ast.Attribute)} & {"q","rewards","failure_reward","_doors","_p"}
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="evaluate")
    assert not {n.func.attr for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)} & {"learn","consume","record","backup"}
    return {"complete":True,"phase":phase,"records":seq+1,"streams":len(results),"counts":dict(counts),
            "all_physics_noise_coordinates_and_causes_reconciled":True,"all_categorical_counts_and_binary64_backups_reconciled":True,
            "own_real_replay_and_declared_model_prior_separated":True,"full_frozen_eval_and_training_state_protected":True,
            "eval_observations_never_learned_or_replayed":True,"all_inputs_currently_match_native_pins":True,
            "audit_PRNG_reconstruction_random_calls":reconstruction_draws,
            "raw_sha256":sha(directory/"raw.jsonl"),"runtime_identity_reconstructed_from_JSON":False,
            "old_fixture_checker_native_executed":0,"independent_expert_or_science_gate":False}


if __name__=="__main__":
    directory=Path(sys.argv[1])
    output=directory/"audit_result.json"
    assert not output.exists(),"review output already exists; do not overwrite/retry"
    started=time.perf_counter()
    try:
        result=audit(directory)
        code=0
    except BaseException as exc:
        result={"complete":False,"error":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()}
        traceback.print_exc()
        code=1
    result.update(child_exit_code=code,wall_seconds=time.perf_counter()-started)
    with output.open("x",encoding="utf-8",newline="\n") as f:
        json.dump(result,f,indent=2)
        f.write("\n")
    print(json.dumps(result))
    raise SystemExit(code)
