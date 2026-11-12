"""Post-hoc reporting coverage correction, no new endpoint/learner/native/RNG.

The predeclared shadow instrumentation covers only the six hybrid paths.
Its empty counters on RL/F0 must not be interpreted as observed zero errors.
Compute collision recurrence from every path's actual training history instead.
"""
from collections import Counter
from pathlib import Path
import csv
import gzip
import json

HERE=Path(__file__).resolve().parent


def save(name,x):
    with (HERE/name).open("x",encoding="utf-8",newline="\n") as f:
        json.dump(x,f,ensure_ascii=False,indent=2);f.write("\n")


def main():
    analysis=json.loads((HERE/"analysis.json").read_text(encoding="utf-8"))
    native=json.loads((HERE/"evidence_matrix/result.json").read_text(encoding="utf-8"))
    review=json.loads((HERE/"evidence_matrix/audit_result.json").read_text(encoding="utf-8"))
    assert review["exit_code"]==0
    external={x["stream"]:x["audit_only_mechanism"] for x in review["external_diagnostics"] if "audit_only_mechanism" in x}
    by_stream={s["stream"]:s for s in native["streams"]}
    rows=[];examples={};total_train=total_steps=0
    with gzip.open(HERE/"evidence_matrix/raw.jsonl.gz","rt",encoding="utf-8") as f:
        for line in f:
            if not any('"tag":"'+tag+'"' in line for tag in ("STREAM_INITIAL","TRAIN_POLICY","LEARN","STREAM_FINAL")):
                continue
            rec=json.loads(line);tag=rec["tag"];x=rec["payload"]
            if tag=="STREAM_INITIAL":
                ctx=x["context"];case=x["case"];state=x["learner"];past={};stats=Counter()
                mapping={(r,a):b for r,a,b in case["controller_mappings"]}
            elif tag=="TRAIN_POLICY":
                decision=x
            elif tag=="LEARN":
                obs=x["packet"]["facts"];total_train+=1
                for step in obs["steps"]:
                    total_steps+=1
                    room,command=step["room"],step["command"];k=f"{room}:{command}"
                    seen=past.get(k,[0,0]);forward=step["next_room"]==room+1
                    stats["actual_train_steps"]+=1
                    stats["collision_steps"]+=step["outcome"]=="COLLISION"
                    stats["repeated_collision_all_groups"]+=step["outcome"]=="COLLISION" and seen[1]>0
                    if "q" in state:
                        q=[state["q"].get(f"{room}:{a}",0.0) for a in (0,1)]
                        choices=[a for a in (0,1) if q[a]==max(q)]
                        greedy=decision["greedy"][room]
                        wrong=mapping.get((room,greedy),greedy)!=case["passable_exits"][room]
                        stats["strict_Q_wrong_greedy_visits"]+=len(choices)==1 and wrong
                    if decision["shadow"]:
                        s=decision["shadow"][room]
                        base={**ctx,"epoch":decision["epoch"]+1,"uid":obs["uid"],"step":step,"pre_readout":s,
                              "actual_greedy":decision["greedy"][room],"exploration":decision["coins"][room][0],
                              "interpretation":"actual same-state suggestions, not complete counterfactual training"}
                        if ctx["p"]==.1 and ctx["arm"]=="F-R-FT":
                            if len(s["argmax"])>1 and s["FT"]!=s["old"] and command==s["FT"] and not base["exploration"]:
                                examples.setdefault("first_noisy_FT_actual_tie_change",base)
                            a=decision["greedy"][room]
                            if len(s["argmax"])==1 and mapping.get((room,a),a)!=case["passable_exits"][room] and s["p_hat"][a]<s["p_hat"][1-a]:
                                examples.setdefault("first_noisy_FT_strict_Q_overrides_better_factual_probability",base)
                        if ctx["p"]==.1 and ctx["arm"]=="F-R" and len(s["argmax"])>1 and seen[1]>=8:
                            examples.setdefault("first_noisy_old_hybrid_repeated_zero_Q_tie",base)
                    updated=list(seen);updated[0 if forward else 1]+=1;past[k]=updated
                state=x["after"]
                if "counts" in state:assert state["counts"]==past
            elif tag=="STREAM_FINAL":
                expected=by_stream[ctx["stream"]]
                assert stats["actual_train_steps"]==expected["train_steps"]
                covered=ctx["arm"].startswith("F-")
                if covered:
                    assert stats["repeated_collision_all_groups"]==expected["mechanism"]["repeated_collision"]
                    assert stats["strict_Q_wrong_greedy_visits"]==external[ctx["stream"]]["strict_Q_wrong_greedy_visits"]
                rows.append({"seed":ctx["seed"],"mirror":ctx["mirror"],"p":ctx["p"],"arm":ctx["arm"],
                             "shadow_covered":covered,"actual_train_steps":stats["actual_train_steps"],
                             "collision_steps":stats["collision_steps"],"repeated_collision_all_groups":stats["repeated_collision_all_groups"],
                             "strict_Q_wrong_greedy_visits":stats["strict_Q_wrong_greedy_visits"] if "q" in state else None,
                             **{key:expected["mechanism"].get(key,0) if covered else None for key in
                                ("Q_ties","outcome_informative_ties","FT_diff_old","CT_diff_old","FT_diff_CT","actual_readout_overridden","actual_changed_from_old_without_exploration")}})
    assert total_train==73728 and total_steps==187237 and len(rows)==1152
    with (HERE/"mechanism_complete.csv").open("x",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
    save("mechanism_examples.json",examples)
    save("mechanism_coverage.json",{"role":"POSTHOC_REPORTING_COVERAGE_CLARIFICATION_NOT_NEW_EXPERIMENT",
         "issue":"Original mechanism.csv fills empty shadow counters with0 on RL/F0. Those cells mean not instrumented, not measured absence of repeated failures or Q mistakes.",
         "resolution":"mechanism_complete.csv explicitly marks shadow coverage and nulls. Recurrence and Q error counts are recomputed from actual pre-update training history for all applicable groups.",
         "complete_training_observations":total_train,"complete_training_steps":total_steps,
         "hybrid_native_shadow_recurrence_and_external_Q_counts_exact_match":True,
         "primary_AUC_bootstrap_targets_and_native_data_changed":False,"new_native_or_RNG_calls":0})
    matched=list(csv.DictReader((HERE/"matched_train_steps.csv").open(encoding="utf-8",newline="")))
    common=[]
    for right in ("F-R","F-R-CT","RL-R","RL-RP"):
        selected=[r for r in matched if float(r["p"])==.1 and r["left"]=="F-R-FT" and r["right"]==right and float(r["fraction"])==1]
        if selected:
            common.append({"left":"F-R-FT","right":right,"common_train_steps_sum":sum(int(r["common_train_steps"]) for r in selected),
                           "left_successes":sum(int(r["left_successes"]) for r in selected),"right_successes":sum(int(r["right_successes"]) for r in selected)})
    save("matched_cost_summary.json",common)
    lines=["# V0.7 实际结论与机制解释","",
           "**V0.7按批准的v173矩阵完成，不需要追加实验才能结案。** 原始结果见result.md与analysis.json。以下是基于完成后记录的解释；不新增训练，不改原指标或原分析字节。","",
           "## 1. 关键结果不是‘加模型必胜’，而是决策断点能被修正","",
           "随机条件下每组4096训练任务：旧仅奖励混合F-R成功1041，事实平局FT成功2034，次数平局CT成功2008。旧方法的前32训练成功358，FT为861。",
           "主指标早期冻结AUC：FT−旧=0.26472855，32配对seed bootstrap95%区间[0.22469959,0.30008698]；28个seed改善、4个相同、0个更差。这个收益不只集中在一个seed，精确环境概率版本差值0.26625586也支持不是评估运气造成。",
           "这不等于全部成本降低：FT训练10517步，旧方法7966步，因为更多任务走到了后面。共同训练步预算结果如下，不能把旧组早撞墙的少步数视为效率优势。","",
           "|共同预算对照|共同训练步数合计|FT成功|对照成功|","|---|---:|---:|---:|"]
    for x in common:lines.append(f"|FT−{x['right']}|{x['common_train_steps_sum']}|{x['left_successes']}|{x['right_successes']}|")
    lines += ["","## 2. 结果内容的额外优势尚小，简单经验利用已解释大部分收益","",
              "FT−CT的早期AUC仅0.00279236，95%区间[0,0.00837708]；32seed中1个较好、31个相同。不能说概率事实明显、普遍优于较少尝试优先，更不能把含0的区间称为统计等效。CT也在利用历史反馈。",
              "有奖惩混合组F-RP、F-RP-FT、F-RP-CT的完整64任务行为在全部128个镜像/噪声案例中相同：旧Q在这些访问位置已能区分动作，新平局规则没有额外收益。零增量完整保留。","",
              "## 3. 纯反馈与标准RL的保留对照","",
              "随机条件：纯反馈F0训练2486/4096成功，有奖惩纯RL为2443，只有奖励纯RL为941。F0与有奖惩RL末点均约72.7844%，但第8点F0已是72.7844%，RL为64.8163%，第32点追平。纯反馈的早期AUC优势为0.03263474，出现在7个seed，25个相同；这是预先列出的次要比较，不包装为全部方法的总体冠军。",
              "确定性条件F0与有奖惩RL冻结曲线相同，训练总成功3433对3432仅差1次，不夸大。反馈＋奖惩的三种读出训练2437，比直接RL2443略少，而冻结早期更好，说明探索期与冻结策略效果、成本不能只靠一个总分代替。","",
              "## 4. 仍没完全解决的具体问题：Q不平局时，事实仍可能被挡住","",
              "FT只在Q相等时介入。本轮真实记录中已见：某个动作碰撞后，Beta先验仍给非零成功概率，模型备份可将其Q推到大于未试动作的0；于是Q已不平局，事实更倾向另一动作也无法介入。mechanism_examples.json保留第一条按时间出现的这种记录，不是新反事实干预。",
              "因此FT末点约70.5322%，仍低于F0/有奖惩RL约72.7844%。这次打通了一个明确断点，未声称解决全部事实利用。没有临时扩大成概率/Q任意加权、再训练直到全胜。","",
              "## 5. 增加评估是否解决了上次标签受运气影响的问题？","",
              "本轮1152条流的观测首次达标与精确策略首次达标全部一致；1047达到、105未达到。新512回合评估与精确诊断使这轮没有再出现上次小评估集的假未达标，但这不是对未来任务的保证。32个独立训练seed和评估回合仍分别处理，不把约185万回合当独立科学N。","",
              "## 6. 一项报告口径澄清","",
              "预定shadow机制只对六个混合组安装，原自动表mechanism.csv对纯RL/F0填入的0不能解读为它们没有重复碰撞。旧表和分析源保留；mechanism_complete.csv将不适用项明确为空，并从全部73728个真实训练观测重算所有组的重复碰撞、适用Q组的严格错误排序。与混合组原核对值精确一致。该澄清不改变任何主结果、bootstrap、达标标签或native数据。","",
              "**阶段结论：让已有经验进入动作选择带来了可重复的局部效率改善；其中多数改善用简单的尝试历史规则就能实现。概率事实的独立增量较小，错误的非平局Q排序仍是明确剩余缺陷。**"]
    with (HERE/"result_interpretation.md").open("x",encoding="utf-8",newline="\n") as f:f.write("\n".join(lines)+"\n")
    print(json.dumps({"stored_training_observations":total_train,"stored_training_steps":total_steps,"new_native":0,"primary_results_changed":False,"matched_costs":common},ensure_ascii=False))


if __name__=="__main__":main()
