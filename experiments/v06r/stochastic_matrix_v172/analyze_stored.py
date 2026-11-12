"""Analyze only issued V172 evidence; no learner, native or RNG execution."""
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
import csv
import json
import statistics
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ARMS=("RL-RP","RL-R","F0","F-RP","F-R")
COLORS={"RL-RP":"#9b3f91","RL-R":"#cf8500","F0":"#00877c","F-RP":"#2464be","F-R":"#d14947"}


def save_json(name,value):
    with (HERE/name).open("x",encoding="utf-8",newline="\n") as f:
        json.dump(value,f,ensure_ascii=False,indent=2)
        f.write("\n")


def save_csv(name,rows):
    with (HERE/name).open("x",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def rate(bank):
    return Fraction(bank["successes"],bank["episodes"])


def auc(stream):
    banks=stream["eval_banks"]
    return sum((rate(a)+rate(b))*Fraction(b["checkpoint"]-a["checkpoint"],2) for a,b in zip(banks,banks[1:]))/64


def summarize_range(values):
    return {"mean":statistics.fmean(values),"min":min(values),"max":max(values),"values":values}


def main():
    plan=json.loads((HERE.parent/"plan_v171.json").read_text(encoding="utf-8"))
    receipts={}
    for phase in ("wiring","matrix"):
        d=HERE/("evidence_"+phase)
        native=json.loads((d/"exit.json").read_text())
        audit=json.loads((d/"audit_result.json").read_text())
        assert native["complete"] and native["child_exit_code"]==0 and audit["complete"] and audit["child_exit_code"]==0
        receipts[phase]={"native":native,"audit":audit}
    assert sum(r["native"]["wall_seconds"] for r in receipts.values())<=600
    assert sum((HERE/("evidence_"+p)/"raw.jsonl").stat().st_size for p in receipts)<=134217728
    streams=json.loads((HERE/"evidence_matrix"/"result.json").read_text())["streams"]
    assert len(streams)==80 and all(s["train_tasks"]==64 for s in streams)
    by_key={(s["seed"],s["mirror"],s["p"],s["arm"]):s for s in streams}
    groups,depth_rows,targets,online,eval_rows=[],[],[],[],[]
    all_train_contexts=defaultdict(Counter)
    observed_causes=defaultdict(Counter)
    tapes=None
    with (HERE/"evidence_matrix"/"raw.jsonl").open(encoding="utf-8") as f:
        for line in f:
            record=json.loads(line)
            tag,p,ctx=record["tag"],record["payload"],record["context"]
            if tag=="TAPES":
                tapes={(b["seed"],b["mirror"]):b for b in p["blocks"]}
            elif tag=="EPISODE_COMPLETE" and "train_epoch" in ctx:
                token=(ctx["seed"],ctx["mirror"],ctx["p"],ctx["arm"])
                for step in p["observation"]["steps"]:
                    all_train_contexts[token][(step["room"],step["command"],step["outcome"]!="COLLISION")]+=1
                observed_causes[token].update(p["audit_causes"])
    for s in streams:
        token=(s["seed"],s["mirror"],s["p"],s["arm"])
        threshold=Fraction(9,10) if s["p"]==0 else Fraction(6561,10000)
        target=next((b for b in s["eval_banks"] if rate(b)>=threshold),None)
        n=1 if s["p"]==0 else 32
        # Diagnostic only: best success fraction attainable in this fixed
        # potential-noise bank. It does NOT replace the declared threshold.
        empirical_ceiling=sum(all(u>=s["p"] for u in vector) for vector in tapes[s["seed"],s["mirror"]]["eval_env"][:n])/n
        mixed=sum(all_train_contexts[token][(r,a,True)]>0 and all_train_contexts[token][(r,a,False)]>0 for r in range(3) for a in (0,1))
        targets.append({"seed":s["seed"],"mirror":s["mirror"],"p":s["p"],"arm":s["arm"],
                        "status":"REACHED" if target else "NOT_REACHED_RIGHT_CENSORED",
                        "first_checkpoint":target["checkpoint"] if target else None,
                        "train_steps_to_target":s["train_curve"][target["checkpoint"]-1]["train_steps"] if target and target["checkpoint"] else 0 if target else None,
                        "later_below_threshold":sum(rate(b)<threshold for b in s["eval_banks"] if target and b["checkpoint"]>target["checkpoint"]) if target else None,
                        "threshold":float(threshold),"empirical_fixed_bank_ceiling":empirical_ceiling,
                        "threshold_exceeds_this_bank_ceiling":empirical_ceiling<float(threshold),"mixed_observed_contexts":mixed})
        for row in s["train_curve"]:
            online.append({"seed":s["seed"],"mirror":s["mirror"],"p":s["p"],"arm":s["arm"],**row})
        for b in s["eval_banks"]:
            eval_rows.append({"seed":s["seed"],"mirror":s["mirror"],"p":s["p"],"arm":s["arm"],
                              "checkpoint":b["checkpoint"],"episodes":b["episodes"],"successes":b["successes"],
                              "success_rate":b["mean_success"],"steps":b["steps"],"learning_writes":b["learning_writes"],
                              "empirical_bank_ceiling":empirical_ceiling})
        if "counts" in s["final_learner"]:
            for address,pair in s["final_learner"]["counts"].items():
                r,a=map(int,address.split(":"))
                assert pair==[all_train_contexts[token][(r,a,True)],all_train_contexts[token][(r,a,False)]]
    for p in (0.0,0.1):
        for arm in ARMS:
            ss=[s for s in streams if s["p"]==p and s["arm"]==arm]
            tt=[t for t in targets if t["p"]==p and t["arm"]==arm]
            counts=Counter()
            for s in ss:
                counts.update(s["counts"])
            groups.append({"p":p,"arm":arm,"seeds":4,"mirrored_streams":8,"train_tasks":512,
                           "train_successes":sum(s["train_successes"] for s in ss),
                           "early16_successes":sum(s["train_curve"][15]["successes"] for s in ss),
                           "cold32_successes":sum(s["train_curve"][31]["successes"] for s in ss),
                           "continued32_successes":sum(s["train_successes"]-s["train_curve"][31]["successes"] for s in ss),
                           "train_steps":sum(s["train_steps"] for s in ss),
                           "final_eval_successes":sum(s["eval_banks"][-1]["successes"] for s in ss),
                           "final_eval_episodes":sum(s["eval_banks"][-1]["episodes"] for s in ss),
                           "final_eval_rate":float(sum(rate(s["eval_banks"][-1]) for s in ss)/8),
                           "frozen_success_AUC":float(sum(auc(s) for s in ss)/8),
                           "target_reached_streams":sum(t["status"]=="REACHED" for t in tt),
                           "later_below_threshold_banks":sum(t["later_below_threshold"] or 0 for t in tt),
                           "mixed_observed_contexts":sum(t["mixed_observed_contexts"] for t in tt),
                           "actual_accidental_train_failures":sum(observed_causes[s["seed"],s["mirror"],s["p"],s["arm"]]["ACCIDENT"] for s in ss),
                           "ordinary_backups":counts["ordinary_backups"],"replay_backups":counts["replay_backups"],
                           "model_backups":counts["model_backups"],"fact_count_updates":counts["fact_count_updates"],
                           "planning_edge_expansions":counts["planning_edge_expansions"],"eval_steps":counts["eval_steps"],
                           "train_policy_ns":sum(s["train_curve"][-1]["policy_ns"] for s in ss),
                           "update_ns":sum(s["train_curve"][-1]["update_ns"] for s in ss),
                           "max_serialized_state_bytes":max(r["state_serialized_bytes"] for s in ss for r in s["train_curve"])})
    pairs=plan["planned_comparisons"]
    contrasts=[]
    for family,comparisons in pairs.items():
        for left,right in comparisons:
            for p in (0.0,0.1):
                seed_rows=[]
                for seed in plan["workload"]["local_engineering_seed_ids"]:
                    ls=[by_key[seed,m,p,left] for m in (0,1)]
                    rs=[by_key[seed,m,p,right] for m in (0,1)]
                    seed_rows.append({"seed":seed,"early16_rate_delta":sum(s["train_curve"][15]["successes"] for s in ls)/32-sum(s["train_curve"][15]["successes"] for s in rs)/32,
                                      "train64_rate_delta":sum(s["train_successes"] for s in ls)/128-sum(s["train_successes"] for s in rs)/128,
                                      "final_frozen_rate_delta":float((sum(rate(s["eval_banks"][-1]) for s in ls)-sum(rate(s["eval_banks"][-1]) for s in rs))/2),
                                      "frozen_AUC_delta":float((sum(auc(s) for s in ls)-sum(auc(s) for s in rs))/2),
                                      "train_step_delta":sum(s["train_steps"] for s in ls)-sum(s["train_steps"] for s in rs)})
                metrics={k:summarize_range([r[k] for r in seed_rows]) for k in seed_rows[0] if k!="seed"}
                contrasts.append({"family":family,"left":left,"right":right,"p":p,"sign":"left minus right", "seed_results":seed_rows,"summary":metrics})
    cost_rows=[]
    for comparisons in pairs.values():
        for left,right in comparisons:
            for seed in plan["workload"]["local_engineering_seed_ids"]:
                for mirror in (0,1):
                    for p in (0.0,0.1):
                        l,r=by_key[seed,mirror,p,left],by_key[seed,mirror,p,right]
                        budget=min(l["train_steps"],r["train_steps"])
                        for percent in (25,50,75,100):
                            b=budget*percent//100
                            ll=[x for x in l["train_curve"] if x["train_steps"]<=b]
                            rr=[x for x in r["train_curve"] if x["train_steps"]<=b]
                            cost_rows.append({"left":left,"right":right,"seed":seed,"mirror":mirror,"p":p,
                                              "budget_percent":percent,"train_step_budget":b,
                                              "left_successes":sum(x["terminal"]=="SUCCESS" for x in ll),
                                              "right_successes":sum(x["terminal"]=="SUCCESS" for x in rr),
                                              "left_tasks":len(ll),"right_tasks":len(rr)})
    totals=Counter()
    for rec in receipts.values():
        totals.update(rec["native"]["counts"])
    result={"status":"COMPLETE_CONDITIONAL_LOCAL_STOCHASTIC_FEEDBACK_STUDY","groups":groups,
            "paired_seed_contrasts":contrasts,"targets":targets,"combined_counts":dict(totals),"receipts":receipts,
            "all_80_streams_64_train_and_five_frozen_banks":True,
            "actual_no_controller_edits_extra_queries_formal_collection_or_automation":True,
            "target_threshold_unchanged":True,"empirical_bank_ceiling_is_diagnostic_only":True,
            "scope":"4 paired engineering seeds; mirrors and bank items are not independent N; descriptive local results, not universal superiority or equivalence."}
    save_json("analysis.json",result)
    save_csv("group_summary.csv",groups)
    save_csv("targets.csv",targets)
    save_csv("online_curves.csv",online)
    save_csv("frozen_curves.csv",eval_rows)
    save_csv("matched_train_steps.csv",cost_rows)
    seed_csv=[{"family":c["family"],"left":c["left"],"right":c["right"],"p":c["p"],**row} for c in contrasts for row in c["seed_results"]]
    save_csv("paired_seed_deltas.csv",seed_csv)
    for kind in ("frozen","online"):
        svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1060" height="430" viewBox="0 0 1060 430">',
             '<rect width="1060" height="430" fill="#fafafa"/>','<g font-family="Arial,sans-serif" fill="#222">',
             f'<text x="30" y="28" font-size="20">V0.6 {"frozen greedy success" if kind=="frozen" else "online cumulative failures per stream"}</text>']
        for j,arm in enumerate(ARMS):
            x=35+j*200
            svg += [f'<line x1="{x}" x2="{x+25}" y1="53" y2="53" stroke="{COLORS[arm]}" stroke-width="3"/>',f'<text x="{x+32}" y="58" font-size="14">{arm}</text>']
        for panel,p in enumerate((0.0,0.1)):
            left,top,width,height=65+panel*510,95,435,260
            max_y=1 if kind=="frozen" else 64
            svg.append(f'<text x="{left}" y="82" font-size="16">Accidental failure probability = {p:g}</text>')
            for j in range(5):
                y=top+height-height*j/4
                value=max_y*j/4
                svg += [f'<line x1="{left}" x2="{left+width}" y1="{y}" y2="{y}" stroke="#ddd"/>',f'<text x="{left-8}" y="{y+4}" text-anchor="end" font-size="12">{value:g}</text>']
            for e in (0,16,32,48,64):
                svg.append(f'<text x="{left+width*e/64}" y="{top+height+20}" text-anchor="middle" font-size="12">{e}</text>')
            if kind=="frozen":
                y=top+height-height*(1-p)**3
                svg.append(f'<line x1="{left}" x2="{left+width}" y1="{y}" y2="{y}" stroke="#888" stroke-dasharray="4 5"/>')
            for arm in ARMS:
                points=[]
                if kind=="frozen":
                    for e in (0,16,32,48,64):
                        v=statistics.fmean(row["success_rate"] for row in eval_rows if row["arm"]==arm and row["p"]==p and row["checkpoint"]==e)
                        points.append((left+width*e/64,top+height-height*v))
                else:
                    points.append((left,top+height))
                    for e in range(1,65):
                        v=statistics.fmean(row["failures"] for row in online if row["arm"]==arm and row["p"]==p and row["epoch"]==e)
                        points.append((left+width*e/64,top+height-height*v/64))
                pts=" ".join(f"{x:.3f},{y:.3f}" for x,y in points)
                svg.append(f'<polyline points="{pts}" fill="none" stroke="{COLORS[arm]}" stroke-width="2.4"/>')
        svg += ['<text x="30" y="407" font-size="12">Four paired seeds, two mirrors. Overlap is retained. No confidence interval or universal-equivalence claim.</text>','</g></svg>']
        text="\n".join(svg)+"\n"
        ET.fromstring(text)
        with (HERE/(kind+"_curves.svg")).open("x",encoding="utf-8",newline="\n") as f:
            f.write(text)
    print(json.dumps({"groups":groups,"combined_counts":dict(totals),
                      "not_reached":sum(t["status"]!="REACHED" for t in targets),
                      "threshold_unattainable_streams":sum(t["threshold_exceeds_this_bank_ceiling"] for t in targets)}))


if __name__=="__main__":
    main()
