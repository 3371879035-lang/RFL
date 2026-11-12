"""New independent streaming review of V174 bytes. No native module imports."""
from collections import Counter
from pathlib import Path
import ast
import copy
import gzip
import hashlib
import json
import random
import sys
import time
import traceback
import stored_semantics as S

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def rebuild_tapes(plan):
    blocks=[]
    for seed in plan["workload"]["local_engineering_seed_ids"]:
        for mirror in (0,1):
            generators={p:random.Random(f"V07|{seed}|{mirror}|{p}") for p in ("train_env","train_action","eval_env")}
            blocks.append({"seed":seed,"mirror":mirror,
                           "train_env":[[generators["train_env"].random() for _ in range(3)] for _ in range(64)],
                           "train_action":[[[generators["train_action"].random(),generators["train_action"].random()] for _ in range(3)] for _ in range(64)],
                           "eval_env":[[generators["eval_env"].random() for _ in range(3)] for _ in range(512)]})
    return blocks


def visits_from(state,obs,greedy,coins):
    if "q" not in state or "counts" not in state:
        return []
    proposals=S.shadow(state);rows=[]
    for step in obs["steps"]:
        s=proposals[step["room"]]
        rows.append({**s,"command":step["command"],"greedy":greedy[step["room"]],
                     "exploration":bool(coins[step["room"]][0]),"outcome":step["outcome"],
                     "prior_collisions_chosen":s["counts"][step["command"]][1]})
    return rows


def mechanism_counts(rows):
    c=Counter()
    for r in rows:
        tied=len(r["argmax"])>1
        for k,v in {"visited":1,"Q_ties":tied,
                    "outcome_informative_ties":tied and r["p_hat"][0]!=r["p_hat"][1],
                    "FT_diff_old":r["FT"]!=r["old"],"CT_diff_old":r["CT"]!=r["old"],
                    "FT_diff_CT":r["FT"]!=r["CT"],"actual_readout_overridden":r["command"]!=r["greedy"],
                    "actual_changed_from_old_without_exploration":not r["exploration"] and r["command"]==r["greedy"] and r["greedy"]!=r["old"],
                    "repeated_collision":r["outcome"]=="COLLISION" and r["prior_collisions_chosen"]>0}.items():
            c[k]+=v
    return c


def review(directory):
    counts=Counter();results=[];stream_index=0;last_uid=0;raw_bytes=0
    bank=None;pending=None;reconstructed_draws=0;external=[]
    with gzip.open(directory/"raw.jsonl.gz","rt",encoding="utf-8",newline="") as f:
        for seq,line in enumerate(f):
            raw_bytes+=len(line.encode())
            rec=json.loads(line)
            assert rec["seq"]==seq and S.wire(rec)+"\n"==line
            tag,x=rec["tag"],rec["payload"]
            if tag=="RUN_START":
                assert seq==0
                plan,contract,phase=x["plan"],x["contract"],x["phase"]
                assert plan==json.loads((ROOT/contract["plan"]).read_text(encoding="utf-8"))
                assert contract==json.loads((HERE/"contract.json").read_text(encoding="utf-8"))
                for p,h in x["inputs"].items():
                    assert sha(ROOT/p)==h,p
                arms=[a["id"] for a in plan["arms"]]
                order=([(None,None,None,a) for a in plan["wiring"]["arms"]] if phase=="wiring" else
                       [(s,c["mirror"],p,a) for s in plan["workload"]["local_engineering_seed_ids"]
                        for c in plan["environment"]["structural_case_sources"] for p in (0.0,.1) for a in arms])
            elif tag=="TAPES":
                assert phase=="matrix" and counts["rollouts"]==0
                blocks=rebuild_tapes(plan);reconstructed_draws=135168
                assert x=={"blocks":blocks,"sha256":S.digest(blocks),"PRNG_random_calls":135168}
                tapes={(b["seed"],b["mirror"]):b for b in blocks}
                counts["environment_PRNG_draws"]+=110592
                counts["exploration_PRNG_draws"]+=24576
            elif tag=="STREAM_INITIAL":
                assert bank is None and pending is None
                ctx=x["context"];arm=ctx["arm"]
                token=(None,None,None,arm) if phase=="wiring" else (ctx["seed"],ctx["mirror"],ctx["p"],arm)
                assert token==order[stream_index];stream_index+=1
                before_counts=Counter(counts)
                case=x["case"]
                if phase=="wiring":
                    assert case=={"passable_exits":[0,0],"controller_mappings":[[0,0,1],[0,1,0],[6,0,1],[7,1,0]],"protected_addresses":[[6,0],[7,1]]}
                    probability=.1
                else:
                    assert case==next(c for c in plan["environment"]["structural_case_sources"] if c["mirror"]==ctx["mirror"])
                    probability=ctx["p"];tape=tapes[ctx["seed"],ctx["mirror"]]
                depth=len(case["passable_exits"])
                mapping={(r,a):b for r,a,b in case["controller_mappings"]}
                source={"doors":case["passable_exits"],"p":probability,"mappings":sorted(case["controller_mappings"]),"protected":case["protected_addresses"]}
                assert x["source"]==source
                task={"rooms":list(range(depth)),"goal":depth,"horizon":12}
                assert x["public"]==task
                state=S.initial(task,arm);assert x["learner"]==state
                counts["source_instances"]+=1;counts["source_mapping_initializations"]+=len(mapping)
                assert x["source_instances"]==counts["source_instances"]
                rows=[];banks=[];mechanism=Counter();consumed=set();behavior=hashlib.sha256()
                train_steps=successes=policy_total=update_total=shadow_total=0
                stream_external=Counter();pold=None;obs=None
            elif tag=="TRAIN_POLICY":
                assert bank is None and x["epoch"]==len(rows)
                greedy,details,expansions=S.policy(state)
                coins=[[False,0]]*2 if phase=="wiring" else [[u<.1,int(v*2)] for u,v in tape["train_action"][len(rows)]]
                program=[0,0] if phase=="wiring" else [c[1] if c[0] else greedy[i] for i,c in enumerate(coins)]
                shadow=S.shadow(state) if "q" in state and "counts" in state else []
                assert all(x[k]==v for k,v in {"greedy":greedy,"readout":details,"planning_edge_expansions":expansions,
                                               "coins":coins,"program":program,"shadow":shadow,
                                               "shadow_reused_policy_work":state["type"]=="TieHybrid","scripted":phase=="wiring"}.items())
                assert x["policy_ns"]>=0 and x["shadow_ns"]>=0
                counts["policy_calls"]+=1;counts["planning_edge_expansions"]+=expansions
                if shadow:
                    counts["shadow_readout_calls"]+=1;counts["shadow_candidate_scores"]+=2*depth
                if state["type"]=="TieHybrid":
                    counts["tie_readout_candidate_scores"]+=2*depth;assert x["shadow_ns"]==0
                policy_total+=x["policy_ns"];shadow_total+=x["shadow_ns"];pold=x
            elif tag=="FREEZE_BEGIN":
                assert bank is None and pending is None
                checkpoint=2 if phase=="wiring" else plan["workload"]["checkpoints"][len(banks)]
                assert x["checkpoint"]==checkpoint==len(rows)
                assert x["state"]==state and x["train_state_sha256"]==S.digest(state) and x["nonalias_runtime_asserted"]
                prog,details,expansions=S.policy(state)
                assert x["program"]==prog and x["readout"]==details and x["planning_edge_expansions"]==expansions
                assert x["policy_ns"]>=0
                counts["policy_calls"]+=1;counts["planning_edge_expansions"]+=expansions
                if state["type"]=="TieHybrid":
                    counts["tie_readout_candidate_scores"]+=2*depth
                bank={"start":x,"state":copy.deepcopy(state),"first_uid":last_uid+1,"episodes":0,"successes":0,"steps":0}
            elif tag=="EPISODE_BEGIN":
                assert pending is None and x["uid"]==last_uid+1
                last_uid+=1;mode=x["mode"]
                if mode=="eval":
                    assert bank is not None
                    i=bank["episodes"]
                    assert i < (2 if phase=="wiring" else 1 if probability==0 else 512)
                    vector=[.9,.9] if phase=="wiring" else tape["eval_env"][i]
                    program=bank["start"]["program"]
                else:
                    assert mode=="train" and bank is None and pold is not None
                    vector=[.9,.9] if phase=="wiring" else tape["train_env"][len(rows)]
                    program=pold["program"]
                assert x["environment_uniforms"]==vector and x["program"]==program
                pending=x;counts["rollouts"]+=1;counts[mode+"_rollouts"]+=1
            elif tag=="EPISODE_COMPLETE":
                assert pending is not None
                steps=[];causes=[];room=0
                for _ in range(12):
                    command=pending["program"][room];executed=mapping.get((room,command),command)
                    if executed!=case["passable_exits"][room]:
                        nxt,outcome,cause=room,"COLLISION","BLOCKED"
                    elif pending["environment_uniforms"][room]<probability:
                        nxt,outcome,cause=room,"COLLISION","ACCIDENT"
                    else:
                        nxt=room+1;outcome="SUCCESS" if nxt==depth else "NEXT";cause="NONE"
                    steps.append({"room":room,"command":command,"executed":executed,"next_room":nxt,"outcome":outcome})
                    causes.append(cause);room=nxt
                    if outcome in S.TERMINALS:
                        break
                obs={"uid":pending["uid"],"steps":steps,"terminal":outcome}
                assert x=={"observation":obs,"audit_causes":causes,"source_unchanged":True}
                counts["steps"]+=len(steps);counts[pending["mode"]+"_steps"]+=len(steps)
                if pending["mode"]=="eval":
                    assert state==bank["state"]
                    bank["episodes"]+=1;bank["successes"]+=outcome=="SUCCESS";bank["steps"]+=len(steps)
                else:
                    train_steps+=len(steps);successes+=outcome=="SUCCESS"
                    behavior.update((S.wire({"steps":steps,"terminal":outcome})+"\n").encode())
                last_mode=pending["mode"];pending=None
            elif tag=="MECHANISM_VISITS":
                assert last_mode=="train" and x["uid"]==obs["uid"]
                visits=visits_from(state,obs,pold["greedy"],pold["coins"])
                assert x["rows"]==visits
                mechanism.update(mechanism_counts(visits))
                for r in visits:
                    # This is audit-only hidden-source diagnosis, never a learner feature.
                    wrong=lambda a:mapping.get((r["room"],a),a)!=case["passable_exits"][r["room"]]
                    stream_external["strict_Q_wrong_greedy_visits"]+=len(r["argmax"])==1 and wrong(r["greedy"])
                    stream_external["FT_better_physical_exit_than_old"]+=wrong(r["old"]) and not wrong(r["FT"])
                    stream_external["FT_worse_physical_exit_than_old"]+=not wrong(r["old"]) and wrong(r["FT"])
            elif tag=="LEARN":
                assert last_mode=="train" and x["uid"]==obs["uid"] and obs["uid"] not in consumed
                consumed.add(obs["uid"])
                rewards=None if arm=="F0" else [1.0 if s["outcome"]=="SUCCESS" else state["failure_reward"] if s["outcome"] in ("COLLISION","TIMEOUT") else 0.0 for s in obs["steps"]]
                expected_packet={"facts":obs} if rewards is None else {"facts":obs,"rewards":rewards}
                assert x["packet"]==expected_packet
                events,model_events=S.updates(state,obs,rewards)
                assert x["updates"]==events and x["model_updates"]==model_events and x["after"]==state
                assert x["update_ns"]>=0;update_total+=x["update_ns"]
                counts["observations_consumed"]+=1;counts["history_appends"]+=1
                for kind,key in [("ordinary","ordinary_backups"),("replay","replay_backups"),("model","model_backups")]:
                    counts[key]+=sum(e["kind"]==kind for e in events)
                counts["numeric_changes"]+=sum(e["before_hex"]!=e["after_hex"] for e in events)
                counts["fact_count_updates"]+=len(model_events)
            elif tag=="TRAIN_CHECKPOINT":
                expected={"epoch":len(rows)+1,"uid":obs["uid"],"terminal":obs["terminal"],"successes":successes,
                          "failures":len(rows)+1-successes,"train_steps":train_steps,
                          **{k:counts[k]-before_counts[k] for k in ("ordinary_backups","replay_backups","model_backups","fact_count_updates")},
                          "policy_ns":policy_total,"update_ns":update_total,"shadow_ns":shadow_total,
                          "state_sha256":S.digest(state),"state_serialized_bytes":len(S.wire(state).encode())}
                assert x==expected
                assert state["history"][-1]==obs["uid"] and len(state["history"])==len(rows)+1
                rows.append(expected);pold=None
            elif tag=="FREEZE_END":
                assert bank is not None and state==bank["state"]
                start=bank["start"]
                assert bank["episodes"]==(2 if phase=="wiring" else 1 if probability==0 else 512)
                expected={"checkpoint":start["checkpoint"],"first_uid":bank["first_uid"],"last_uid":last_uid,
                          "episodes":bank["episodes"],"successes":bank["successes"],"steps":bank["steps"],
                          "mean_success":bank["successes"]/bank["episodes"],"program":start["program"],
                          "frozen_state_sha256":S.digest(state),"frozen_state_sha256_after":S.digest(state),
                          "train_state_sha256_after":S.digest(state),"learning_writes":0,
                          "policy_ns":start["policy_ns"],"planning_edge_expansions":start["planning_edge_expansions"]}
                assert x==expected
                viable=all(mapping.get((r,a),a)==case["passable_exits"][r] for r,a in enumerate(x["program"]))
                exact=(1-probability)**depth if viable else 0.0
                external.append({**ctx,"checkpoint":x["checkpoint"],"exact_probability":exact,"viable_program":viable,
                                 "observed_successes":x["successes"],"eval_episodes":x["episodes"]})
                banks.append(expected);bank=None
            elif tag=="STREAM_FINAL":
                assert len(rows)==(2 if phase=="wiring" else 64) and len(banks)==(1 if phase=="wiring" else 6)
                assert set(state["history"])==consumed and len(consumed)==len(rows)
                if "buffer" in state:
                    assert all(item[0] in consumed for item in state["buffer"])
                expected={**ctx,"train_tasks":len(rows),"train_successes":successes,"train_steps":train_steps,
                          "counts":dict(Counter(counts)-before_counts),"train_curve":rows,"eval_banks":banks,
                          "mechanism":dict(mechanism),"train_behavior_sha256":behavior.hexdigest(),
                          "final_learner":state,"source_unchanged":True,"inherited_updates_runtime_identical":True}
                assert x==expected
                if phase=="wiring":
                    assert [r["terminal"] for r in rows]==["COLLISION","COLLISION"]
                    assert banks[0]["program"]==[1,0] and banks[0]["successes"]==2
                results.append(x)
                external.append({**ctx,"audit_only_mechanism":dict(stream_external)})
            elif tag=="RESULT":
                assert stream_index==len(order) and x=={"streams":results,"counts":dict(counts)}
            elif tag=="FINAL":
                assert x["complete"] and x["child_exit_code"]==0 and x["input_bytes_unchanged"] and x["error"] is None
                assert x["counts"]==dict(counts) and x["wall_seconds"]>=0 and x["cpu_seconds"]>=0
                final=x
            else:
                raise AssertionError((seq,tag))
    receipt=json.loads((directory/"exit.json").read_text(encoding="utf-8"))
    assert all(receipt[k]==v for k,v in final.items())
    assert receipt["canonical_records"]==seq+1 and receipt["uncompressed_capture_bytes"]==raw_bytes
    assert receipt["compressed_capture_bytes"]==(directory/"raw.jsonl.gz").stat().st_size
    assert receipt["raw_gzip_sha256"]==sha(directory/"raw.jsonl.gz")
    assert json.loads((directory/"result.json").read_text(encoding="utf-8"))=={"streams":results,"counts":dict(counts)}
    limit=contract["phase_limits"][phase]
    assert counts["rollouts"]==limit["rollouts"] and counts["steps"]<=limit["steps"]
    assert receipt["wall_seconds"]<=limit["wall_seconds"] and receipt["compressed_capture_bytes"]<=limit["compressed_capture_bytes"]
    assert counts["model_backups"]+counts["replay_backups"]<=limit["extra_Q_backups"]
    tree=ast.parse((HERE/"experiment.py").read_text(encoding="utf-8"))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="TieHybrid")
    assert {n.name for n in cls.body if isinstance(n,ast.FunctionDef)}=={"__init__","snapshot","policy"}
    fun=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="shadow_readouts")
    assert not {"engine","source","seed","tape","probability","reward"}&{n.id for n in ast.walk(fun) if isinstance(n,ast.Name)}
    evaluate=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="evaluate")
    assert not {"learn","learn_actual","consume","record","backup"}&{n.attr for n in ast.walk(evaluate) if isinstance(n,ast.Attribute)}
    return {"status":"PASS_STORED_REVIEW_NOT_SCIENCE_GATE","phase":phase,"canonical_records":seq+1,
            "uncompressed_capture_bytes":raw_bytes,"compressed_capture_bytes":receipt["compressed_capture_bytes"],
            "counts":dict(counts),"streams":len(results),"native_input_pins":len(contract["inputs"]),
            "independent_PRNG_reconstruction_calls":reconstructed_draws,
            "external_diagnostics":external,"native_or_old_checker_calls":0,
            "runtime_identity_reconstruction_from_JSON":False,"independent_expert_review":False}


def main():
    directory=Path(sys.argv[1]);started=time.perf_counter()
    try:
        result=review(directory);result["exit_code"]=0
    except BaseException as e:
        result={"exit_code":1,"status":"FAIL_STORED_REVIEW","error":{"type":type(e).__name__,"message":str(e),"traceback":traceback.format_exc()}}
        traceback.print_exc()
    result["wall_seconds"]=time.perf_counter()-started
    with (directory/"audit_result.json").open("x",encoding="utf-8",newline="\n") as f:
        json.dump(result,f,ensure_ascii=False,indent=2);f.write("\n")
    print(S.wire({k:v for k,v in result.items() if k!="external_diagnostics"}),flush=True)
    return result["exit_code"]


if __name__=="__main__":
    raise SystemExit(main())
