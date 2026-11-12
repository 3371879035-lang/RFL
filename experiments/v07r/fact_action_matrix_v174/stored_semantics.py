"""Independent stored-data arithmetic, no native/learner/experiment imports.
Baseline update arithmetic copied from V172 stored review, never runs old review.
"""
import hashlib
import json

TERMINALS = ("SUCCESS", "COLLISION", "TIMEOUT")

def wire(x):
    return json.dumps(x,sort_keys=True,separators=(",", ":"))

def digest(x):
    return hashlib.sha256(wire(x).encode()).hexdigest()

def initial(task,arm):
    if arm == "F0":
        return {"type":"FactualLearner","task":task,"counts":{},"history":[]}
    mode = arm[-2:] if arm.endswith(("-FT","-CT")) else None
    base = arm[:-3] if mode else arm
    state = {"type":"TieHybrid" if mode else "DirectQLearner" if arm.startswith("RL-") else "HybridQLearner",
             "task":task,"failure_reward":-1.0 if base.endswith("RP") else 0.0,
             "q":{},"buffer":[],"history":[],"ordinary":0,"replays":0,"models":0,"numeric_changes":0}
    if arm.startswith("F-"):
        state["counts"]={}
    if mode:
        state["tie_mode"]=mode
    return state

def shadow(state):
    result=[]
    for room in state["task"]["rooms"]:
        values=[state["q"].get(f"{room}:{a}",0.0) for a in (0,1)]
        counts=[list(state["counts"].get(f"{room}:{a}",[0,0])) for a in (0,1)]
        probs=[(v[0]+1)/(sum(v)+2) for v in counts]
        maxima=[a for a in range(2) if values[a]==max(values)]
        ft=sorted(maxima,key=lambda a:(-probs[a],a))[0]
        ct=sorted(maxima,key=lambda a:(sum(counts[a]),a))[0]
        result.append({"room":room,"q":values,"counts":counts,"p_hat":probs,"argmax":maxima,
                       "old":maxima[0],"FT":ft,"CT":ct})
    return result

def policy(state):
    d=state["task"]["goal"]
    if state["type"]=="TieHybrid":
        details=shadow(state)
        return [x[state["tie_mode"]] for x in details],details,0
    actions,details={},[]
    if state["type"]=="FactualLearner":
        future=1.0
        for room in range(d-1,-1,-1):
            scores=[]
            for a in (0,1):
                k=f"{room}:{a}"; n,m=state["counts"].get(k,(0,0));prob=(n+1)/(n+m+2)
                value=prob*future;scores.append(value)
                details.append({"address":k,"p_hex":prob.hex(),"value_hex":value.hex()})
            actions[room]=0 if scores[0]>=scores[1] else 1
            future=scores[actions[room]]
        return [actions[r] for r in range(d)],details,2*d
    for room in range(d):
        values=[state["q"].get(f"{room}:{a}",0.0) for a in (0,1)]
        actions[room]=0 if values[0]>=values[1] else 1
        details.extend({"address":f"{room}:{a}","value_hex":values[a].hex()} for a in (0,1))
    return [actions[r] for r in range(d)],details,0

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


