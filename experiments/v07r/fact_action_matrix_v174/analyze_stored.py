"""V174 predeclared analysis. Reads stored records only, no learner/native imports."""
from collections import Counter
from pathlib import Path
import csv
import html
import json
import math
import random
import statistics
import time
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def save(name,x):
    with (HERE/name).open("x",encoding="utf-8",newline="\n") as f:
        json.dump(x,f,ensure_ascii=False,indent=2);f.write("\n")


def table(name,rows):
    with (HERE/name).open("x",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        writer.writeheader();writer.writerows(rows)


def auc(banks,field="mean_success",limit=32):
    points=[b for b in banks if b["checkpoint"]<=limit]
    return sum((b["checkpoint"]-a["checkpoint"])*(a[field]+b[field])/2 for a,b in zip(points,points[1:]))/limit


def wilson(s,n):
    z=1.959963984540054
    ph=s/n;den=1+z*z/n
    center=(ph+z*z/(2*n))/den
    half=z*math.sqrt(ph*(1-ph)/n+z*z/(4*n*n))/den
    return max(0.0,center-half),min(1.0,center+half)


def percentile(values,p):
    v=sorted(values);q=(len(v)-1)*p;i=int(q);j=min(i+1,len(v)-1)
    return v[i]+(q-i)*(v[j]-v[i])


def draw_svg(name,groups,arms):
    colors=["#2456a6","#86a6cf","#232a34","#b54437","#cc8e86","#19754c","#43a871","#884ca8","#b384cc"]
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="480" viewBox="0 0 1100 480">',
           '<rect width="1100" height="480" fill="white"/>',
           '<text x="30" y="28" font-family="sans-serif" font-size="20">V0.7 frozen success curves (32 paired seeds)</text>']
    for panel,p in enumerate((0.0,.1)):
        x0=55+panel*440;y0=405;w=385;h=320
        parts.append(f'<text x="{x0}" y="60" font-family="sans-serif" font-size="17">p={p}</text>')
        for v in (0,.25,.5,.75,1):
            y=y0-v*h
            parts.append(f'<path d="M{x0},{y}h{w}" stroke="#ddd"/><text x="{x0-30}" y="{y+4}" font-size="11">{v:g}</text>')
        for e in (0,8,16,32,48,64):
            x=x0+w*e/64
            parts.append(f'<text x="{x-6}" y="{y0+20}" font-size="11">{e}</text>')
        for i,a in enumerate(arms):
            g=next(g for g in groups if g["p"]==p and g["arm"]==a)
            points=" ".join(f'{x0+w*b["checkpoint"]/64:.3f},{y0-h*b["mean_success"]:.3f}' for b in g["frozen_curve"])
            dash=' stroke-dasharray="5 3"' if a.endswith("CT") else ''
            parts.append(f'<polyline points="{points}" fill="none" stroke="{colors[i]}" stroke-width="2"{dash}/>')
    for i,a in enumerate(arms):
        y=85+30*i
        parts.append(f'<path d="M950,{y}h20" stroke="{colors[i]}" stroke-width="3"/><text x="978" y="{y+4}" font-family="sans-serif" font-size="12">{html.escape(a)}</text>')
    parts.append('<text x="390" y="460" font-family="sans-serif" font-size="13">Training episodes (evaluation never learned)</text></svg>')
    text="\n".join(parts)+"\n";ET.fromstring(text)
    with (HERE/name).open("x",encoding="utf-8",newline="\n") as f:f.write(text)


def main():
    started=time.perf_counter();plan=load(HERE.parent/"plan_v173.json")
    dirs=[HERE/"evidence_wiring",HERE/"evidence_matrix"]
    receipts=[load(d/"exit.json") for d in dirs];reviews=[load(d/"audit_result.json") for d in dirs]
    assert all(r["complete"] and r["child_exit_code"]==0 for r in receipts)
    assert all(r["exit_code"]==0 for r in reviews)
    matrix=load(dirs[1]/"result.json");streams=matrix["streams"]
    assert len(streams)==1152 and all(s["train_tasks"]==64 and len(s["eval_banks"])==6 for s in streams)
    arms=[a["id"] for a in plan["arms"]];seeds=plan["workload"]["local_engineering_seed_ids"]
    ext={(x["stream"],x["checkpoint"]):x for x in reviews[1]["external_diagnostics"] if "checkpoint" in x}
    ext_mechanism={x["stream"]:x["audit_only_mechanism"] for x in reviews[1]["external_diagnostics"] if "audit_only_mechanism" in x}
    index={(s["seed"],s["mirror"],s["p"],s["arm"]):s for s in streams}
    frozen_rows=[];online_rows=[];targets=[];mechanisms=[]
    for s in streams:
        exact_banks=[];threshold=.9 if s["p"]==0 else .6561
        for bank in s["eval_banks"]:
            exact=ext[s["stream"],bank["checkpoint"]]["exact_probability"]
            exact_banks.append({**bank,"exact_probability":exact})
            lo,hi=(None,None) if s["p"]==0 else wilson(bank["successes"],bank["episodes"])
            measurement=("DETERMINISTIC" if s["p"]==0 else "UNCERTAIN" if lo<=threshold<=hi else "ABOVE" if lo>threshold else "BELOW")
            frozen_rows.append({"seed":s["seed"],"mirror":s["mirror"],"p":s["p"],"arm":s["arm"],
                                "checkpoint":bank["checkpoint"],"successes":bank["successes"],"episodes":bank["episodes"],
                                "success_rate":bank["mean_success"],"exact_probability":exact,"sampling_error":bank["mean_success"]-exact,
                                "wilson95_low":lo,"wilson95_high":hi,"threshold":threshold,"measurement":measurement,
                                "program":json.dumps(bank["program"],separators=(",",":"))})
        s["exact_banks"]=exact_banks
        s["early_AUC"]=auc(s["eval_banks"]);s["full_AUC"]=auc(s["eval_banks"],limit=64)
        s["exact_early_AUC"]=auc(exact_banks,"exact_probability")
        observed_cross=next((b["checkpoint"] for b in exact_banks if b["mean_success"]>=threshold),None)
        exact_cross=next((b["checkpoint"] for b in exact_banks if b["exact_probability"]>=threshold),None)
        targets.append({"seed":s["seed"],"mirror":s["mirror"],"p":s["p"],"arm":s["arm"],"threshold":threshold,
                        "first_observed_crossing":observed_cross,"first_exact_crossing":exact_cross,
                        "observed_not_reached":observed_cross is None,"exact_not_reached":exact_cross is None,
                        "later_observed_drops":sum(observed_cross is not None and b["checkpoint"]>observed_cross and b["mean_success"]<threshold for b in exact_banks),
                        "later_exact_drops":sum(exact_cross is not None and b["checkpoint"]>exact_cross and b["exact_probability"]<threshold for b in exact_banks)})
        for row in s["train_curve"]:
            online_rows.append({"seed":s["seed"],"mirror":s["mirror"],"p":s["p"],"arm":s["arm"],
                                **{k:row[k] for k in ("epoch","successes","failures","train_steps","ordinary_backups","replay_backups","model_backups","fact_count_updates")}})
        mechanisms.append({"seed":s["seed"],"mirror":s["mirror"],"p":s["p"],"arm":s["arm"],
                           **{k:s["mechanism"].get(k,0) for k in ("visited","Q_ties","outcome_informative_ties","FT_diff_old","CT_diff_old","FT_diff_CT","actual_readout_overridden","actual_changed_from_old_without_exploration","repeated_collision")},
                           **{k:ext_mechanism[s["stream"]].get(k,0) for k in ("strict_Q_wrong_greedy_visits","FT_better_physical_exit_than_old","FT_worse_physical_exit_than_old")}})
    groups=[]
    costkeys=("train_rollouts","train_steps","eval_rollouts","eval_steps","ordinary_backups","replay_backups","model_backups","numeric_changes","fact_count_updates","policy_calls","planning_edge_expansions","tie_readout_candidate_scores","shadow_readout_calls","shadow_candidate_scores")
    for p in (0.0,.1):
        for a in arms:
            ss=[s for s in streams if s["p"]==p and s["arm"]==a]
            group={"p":p,"arm":a,"streams":len(ss),"train_tasks":4096,
                   "train_successes":sum(s["train_successes"] for s in ss),
                   "successes16":sum(s["train_curve"][15]["successes"] for s in ss),
                   "successes32":sum(s["train_curve"][31]["successes"] for s in ss),
                   "continued32_successes":sum(s["train_successes"]-s["train_curve"][31]["successes"] for s in ss),
                   "early_AUC":statistics.mean(s["early_AUC"] for s in ss),
                   "exact_early_AUC":statistics.mean(s["exact_early_AUC"] for s in ss),
                   "full_AUC":statistics.mean(s["full_AUC"] for s in ss),
                   **{k:sum(s["counts"].get(k,0) for s in ss) for k in costkeys},
                   "policy_ns":sum(s["train_curve"][-1]["policy_ns"] for s in ss),
                   "update_ns":sum(s["train_curve"][-1]["update_ns"] for s in ss),
                   "shadow_ns":sum(s["train_curve"][-1]["shadow_ns"] for s in ss)}
            curve=[]
            for i,e in enumerate(plan["workload"]["checkpoints"]):
                bs=[s["exact_banks"][i] for s in ss]
                curve.append({"checkpoint":e,"successes":sum(b["successes"] for b in bs),"episodes":sum(b["episodes"] for b in bs),
                              "mean_success":statistics.mean(b["mean_success"] for b in bs),
                              "mean_exact_probability":statistics.mean(b["exact_probability"] for b in bs)})
            group["frozen_curve"]=curve;groups.append(group)
    rng=random.Random("V07|analysis_bootstrap")
    bootstrap=[[rng.randrange(32) for _ in range(32)] for _ in range(10000)]
    pairs=[]
    for pair in plan["evaluation"]["primary_pairs"]+plan["evaluation"]["secondary_pairs"]:
        if pair not in pairs:pairs.append(pair)
    comparisons=[];paired_rows=[];matched=[]
    for p in (0.0,.1):
        for left,right in pairs:
            deltas=[];exact_deltas=[];train32=[]
            for seed in seeds:
                l=[index[seed,m,p,left] for m in (0,1)];r=[index[seed,m,p,right] for m in (0,1)]
                delta=statistics.mean(a["early_AUC"]-b["early_AUC"] for a,b in zip(l,r))
                exact_delta=statistics.mean(a["exact_early_AUC"]-b["exact_early_AUC"] for a,b in zip(l,r))
                d32=statistics.mean(a["train_curve"][31]["successes"]-b["train_curve"][31]["successes"] for a,b in zip(l,r))
                deltas.append(delta);exact_deltas.append(exact_delta);train32.append(d32)
                paired_rows.append({"p":p,"left":left,"right":right,"seed":seed,"early_AUC_delta":delta,
                                    "exact_early_AUC_delta":exact_delta,"train32_success_delta_per_mirror":d32,
                                    "train64_success_delta_per_mirror":statistics.mean(a["train_successes"]-b["train_successes"] for a,b in zip(l,r)),
                                    "train_step_delta_per_mirror":statistics.mean(a["train_steps"]-b["train_steps"] for a,b in zip(l,r)),
                                    "final_frozen_rate_delta":statistics.mean(a["eval_banks"][-1]["mean_success"]-b["eval_banks"][-1]["mean_success"] for a,b in zip(l,r))})
                for m,a,b in zip((0,1),l,r):
                    budget=min(a["train_steps"],b["train_steps"])
                    for fraction in (.25,.5,.75,1.0):
                        cutoff=math.floor(budget*fraction)
                        successes=lambda s:max((row["successes"] for row in s["train_curve"] if row["train_steps"]<=cutoff),default=0)
                        matched.append({"p":p,"seed":seed,"mirror":m,"left":left,"right":right,"fraction":fraction,
                                        "common_train_steps":cutoff,"left_successes":successes(a),"right_successes":successes(b)})
            resampled=[sum(deltas[i] for i in ids)/32 for ids in bootstrap]
            comparisons.append({"p":p,"left":left,"right":right,"primary":p==.1 and [left,right] in plan["evaluation"]["primary_pairs"],
                                "paired_seeds":32,"mean_early_AUC_delta":statistics.mean(deltas),"median_early_AUC_delta":statistics.median(deltas),
                                "bootstrap95_low":percentile(resampled,.025),"bootstrap95_high":percentile(resampled,.975),
                                "positive_seeds":sum(d>0 for d in deltas),"zero_seeds":sum(d==0 for d in deltas),"negative_seeds":sum(d<0 for d in deltas),
                                "mean_exact_early_AUC_delta":statistics.mean(exact_deltas),"mean_train32_success_delta_per_mirror":statistics.mean(train32)})
    combined=Counter()
    for r in receipts:combined.update(r["counts"])
    assert combined["rollouts"]==1846672 and combined["observations_consumed"]==combined["train_rollouts"]
    assert combined["environment_PRNG_draws"]+combined["exploration_PRNG_draws"]==135168
    identical=[]
    for p in (0.0,.1):
        for left,right in pairs:
            n=sum(index[s,m,p,left]["train_behavior_sha256"]==index[s,m,p,right]["train_behavior_sha256"] for s in seeds for m in (0,1))
            identical.append({"p":p,"left":left,"right":right,"identical_full_64_task_streams":n,"total_streams":64})
    result={"status":"COMPLETE_CONDITIONAL_LOCAL_FACT_TO_ACTION_STUDY","plan":"experiments/v07r/plan_v173.json",
            "actual_counts":dict(combined),"native_wall_seconds":sum(r["wall_seconds"] for r in receipts),
            "compressed_capture_bytes":sum(r["compressed_capture_bytes"] for r in receipts),
            "uncompressed_capture_bytes":sum(r["uncompressed_capture_bytes"] for r in receipts),
            "canonical_records":sum(r["canonical_records"] for r in receipts),
            "maximum_measured_peak_working_set_bytes":max(r["memory"]["peak_working_set_bytes"] for r in receipts),
            "native_local_PRNG_random_calls":135168,"review_reconstruction_random_calls":sum(r["independent_PRNG_reconstruction_calls"] for r in reviews),
            "analysis_bootstrap_randrange_calls":320000,"analysis_bootstrap_resamples":10000,
            "groups":groups,"comparisons":comparisons,"identical_training_streams":identical,
            "observed_targets_reached":sum(not t["observed_not_reached"] for t in targets),
            "exact_targets_reached":sum(not t["exact_not_reached"] for t in targets),
            "target_observed_exact_disagreements":sum(t["first_observed_crossing"]!=t["first_exact_crossing"] for t in targets),
            "no_new_native_or_old_checker_calls_from_analysis":True,"automation_changes":0,
            "statistical_unit":"32 paired independent training seed blocks; mirror-averaged, p separate; not eval episodes",
            "analysis_wall_seconds":time.perf_counter()-started}
    save("analysis.json",result)
    table("group_summary.csv",[{k:v for k,v in g.items() if k!="frozen_curve"} for g in groups])
    table("frozen_curves.csv",frozen_rows);table("online_curves.csv",online_rows);table("targets.csv",targets)
    table("mechanism.csv",mechanisms);table("paired_seed_deltas.csv",paired_rows);table("comparisons.csv",comparisons)
    table("matched_train_steps.csv",matched)
    draw_svg("frozen_curves.svg",groups,arms)
    lines=["# V0.7 已完成：让事实进入选择","", "**按v173方案完成9组、32个独立seed、两镜像和两噪声条件。** 本轮为局部机制研究，完成不要求正收益。","",
           "## 1. 实际执行","",f"共{combined['rollouts']}真实回合、{combined['steps']}步；其中训练{combined['train_rollouts']}、评估{combined['eval_rollouts']}。1152条矩阵流各64训练、6个冻结点；随机条件每点512实际评估，确定性每点1次，另16回合新读出接线。",
           f"两个native和两个独立存储核对首次exit0。原生累计{result['native_wall_seconds']:.3f}秒，压缩capture {result['compressed_capture_bytes']} bytes，完整{result['canonical_records']}条canonical记录。时间是instrumented harness，不是生产性能排名。","",
           "## 2. 主对比：事实参与选择是否带来早期改善？","",
           "主指标是p=.10、e0/8/16/32冻结实测成功率的归一化梯形AUC。每seed先平均两镜像；区间为32个seed块、10000次配对bootstrap，反映效应不确定性，不作全family胜负或等效判决。","",
           "|左−右|早期AUC差|95%区间|正/零/负seed|同指标精确环境概率差|","|---|---:|---|---|---:|"]
    for c in comparisons:
        if c["primary"]:
            lines.append(f"|{c['left']}−{c['right']}|{c['mean_early_AUC_delta']:.8f}|[{c['bootstrap95_low']:.8f}, {c['bootstrap95_high']:.8f}]|{c['positive_seeds']}/{c['zero_seeds']}/{c['negative_seeds']}|{c['mean_exact_early_AUC_delta']:.8f}|")
    lines += ["","FT是结果概率打破Q平局；CT是尝试次数较少者优先。CT的历史次数同样属于广义反馈。若CT同样好，不把任何改善只归给结果内容；零/负seed完整保留。","",
              "## 3. 全部对照，不只展示新方法","","每格64条流、4096训练；末点为冻结评估成功率。p=.10正确三步路线理论成功概率.729，不是1。","",
              "|p|组|训练成功/4096|前32成功/2048|e8冻结|e16冻结|e64冻结|早期AUC|","|---|---|---:|---:|---:|---:|---:|---:|"]
    for g in groups:
        cs=g["frozen_curve"]
        lines.append(f"|{g['p']}|{g['arm']}|{g['train_successes']}|{g['successes32']}|{cs[1]['mean_success']:.5f}|{cs[2]['mean_success']:.5f}|{cs[-1]['mean_success']:.5f}|{g['early_AUC']:.7f}|")
    lines += ["","## 4. 事实到动作的机制与剩余错误","",
              "新TieHybrid仅覆盖初始化元数据、snapshot和policy；实际learn、ordinary_updates、model.record与备份继承原V172字节不变，运行时身份断言及独立逐次binary64重建均核对。非平局时FT/CT不推翻Q。各自选择改变后经历自然不同，没有强制共享学习表或把shadow建议伪装成三个完整反事实训练。","",
              "mechanism.csv按真实访问位置列出Q平局、概率信息差异、三个建议差异、非探索导致的实际改选、重复碰撞及严格Q错误排序。真值诊断仅在审阅/评估端使用，未进入学习器；重复碰撞不自动视为浪费。","",
              "|p|组|有区分力的事实/Q平局|非探索实际改选旧命令|重复碰撞|非平局Q选错出口（外部诊断）|","|---|---|---:|---:|---:|---:|"]
    for p in (0.0,.1):
        for a in arms:
            mm=[m for m in mechanisms if m["p"]==p and m["arm"]==a]
            lines.append(f"|{p}|{a}|{sum(m['outcome_informative_ties'] for m in mm)}|{sum(m['actual_changed_from_old_without_exploration'] for m in mm)}|{sum(m['repeated_collision'] for m in mm)}|{sum(m['strict_Q_wrong_greedy_visits'] for m in mm)}|")
    lines += ["","## 5. 测量、成本及限制","",
              f"观测阈值达标{result['observed_targets_reached']}/1152，精确冻结程序达标{result['exact_targets_reached']}/1152；两种首次跨阈值不同{result['target_observed_exact_disagreements']}条。二者分列、不互相补PASS。全部null、后续回落、Wilson区间和原阈值.90/.6561保留，目标标签不作阶段完成门槛。",
              "小世界的精确概率使用实际source/固定冻结程序在外部算出，只是本环境可行的诊断，不是给学习器正确出口答案，也不能外推到无法精确求值的真实任务。512次评估提高单策略测量精度，32个seed检验训练波动；多镜像/检查点/评估回合不是新增独立seed。",
              "group_summary.csv单列训练/评估步数、TD/回放/模型更新、事实写入、规划/读出、shadow与时长；matched_train_steps.csv给出同训练步预算成功数，不能因更早失败而走路少就称更省。模型备份数量相同不等CPU成本相同；F0没有TD也有概率规划成本。",
              "本轮只测试Q精确平局读出，alpha=.5、最新优先回放、简单静态两镜像均固定。严格Q错误排序、变化环境、陌生迁移及通用品味不在已解决范围；纯RL基线不代表所有RL。",
              f"新增本地native PRNG random调用135168；审阅另外重建135168个相同值，不是新总体；bootstrap单独320000次randrange调用，也不是训练样本。没有旧fixture/checker/native重跑、正式collector、付费GPU或自动任务变动。内部审阅不是独立专家/sciencegate。","",
              "## 6. 阶段结束","",
              "按预定矩阵完成，不因终点追平、局部零或负结果再加算法/换seed。实际结果与机制表共同决定本轮能支持哪种局部解释，不把方案里的期待写成已证收益。旧V0.3—V0.6执行源码和结果不改。","",
              "数据入口：analysis.json、group_summary.csv、comparisons.csv、paired_seed_deltas.csv、matched_train_steps.csv、mechanism.csv、frozen_curves.csv、online_curves.csv、targets.csv。图为frozen_curves.svg（XML/坐标校验，不冒称人工视觉复核）。"]
    with (HERE/"result.md").open("x",encoding="utf-8",newline="\n") as f:f.write("\n".join(lines)+"\n")
    print(json.dumps({"status":result["status"],"rollouts":combined["rollouts"],"steps":combined["steps"],
                      "primary_comparisons":[c for c in comparisons if c["primary"]]},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
