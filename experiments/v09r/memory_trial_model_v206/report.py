"""Post-run descriptive diagnostics only. No learner/environment imports or runs."""
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import statistics as st

P = Path(__file__).resolve().parent
review = json.loads((P/'reviewed_summary.json').read_text())
native = json.loads((P/'native_result.json').read_text())
exit_record = json.loads((P/'native_exit.json').read_text())
review_exit = json.loads((P/'review_exit.json').read_text())
assert review['status'] == 'STORED_REVIEW_MATCH' and review_exit['exit_code'] == 0
rows = [json.loads(l) for l in (P/'evidence/results.jsonl').read_text().splitlines()]
memory = [r for r in rows if r['section']=='memory']
gates = [r for r in rows if r['section']=='gate']
variants = ['full_v2', 'recent2', 'static_time', 'uniform_mix', 'fixed8']
families = ['remote_signal', 'rule_reversal', 'two_cue_xor']
names = {'full_v2':'完整 V2', 'recent2':'仅最近两条', 'static_time':'不遗忘旧统计', 'uniform_mix':'所有专家等权', 'fixed8':'固定八对试验'}
fnames = {'remote_signal':'远距离历史线索', 'rule_reversal':'规则中途反转', 'two_cue_xor':'两线索联合判断'}
average = lambda rs, f: st.mean(r[f] for r in rs)
diagnostics = dict(posthoc=True, new_environment_calls=0, new_parameter_updates=0,
                   input_summary_sha256=hashlib.sha256((P/'reviewed_summary.json').read_bytes()).hexdigest(),
                   allcycle=[], relevance=[], matched_gate_differences=[])

lines = ['# V206：记忆选择、时效性与实际试验决策——首次有限实验结果', '',
'## 结论', '',
'**两项机制有明确局部改善，但结构仍有实质断点。** 选对历史线索比平均混合更有效；多时间尺度能在规则反转后恢复。只会读单条线索的模型仍不能掌握联合关系；有限预算贝叶斯决策能省试验，但不保证少误采纳。', '',
'本轮不是把旧 V205 重跑一次，也不是完整通用算法、纯 RL 优越性或 SLEEP 的实验。三类受控二元过程使用同一个不接收任务标签/隐藏答案的学习模块。神经参数冻结；会变化的是事实统计、混合权重和经真实试验选定的部署策略。', '',
'## 执行与比较口径', '',
f'- 首次 native exit 0，{exit_record["wall_seconds"]:.3f} 秒；首次独立实现的 stdlib 存储复核 exit 0，{review_exit["wall_seconds"]:.3f} 秒。没有失败后重试或修改已执行输入。',
f'- 实际 {native["actual_episodes"]:,} 个微型回合、{native["actual_steps"]:,} 步；{native["learning_update_events"]:,} 次事实状态更新，优化器步数 **0**。回合数不是独立训练种子数。',
'- 记忆部分：3 类 × 24 个种子实例 × 5 种变体 × 4 轮。每个实例初始共享 48 个实际回合，每轮共享 8 个发现回合；每变体每轮 56 个实际试验/部署回合，再用独立的 32 对回合评估旧/新策略。已决定的部署角色直接对应其评估分支，不多跑一个重复评估分支。',
'- 采用决策部分：5 种已固定的真实概率关系 × 64 个种子 × 24/64 回合预算 × 2 方法。所有试验和随后部署都计入同一预算。',
'- 两臂独立结果噪声、相同输入情境；跨变体使用配对的随机流命名。评估从不进入学习。旧策略也会经后续合法采用而改善，不是冻结的弱对照。',
'- 同交互预算不等于同计算预算：完整方案有更多专家和 Bellman 计算。记录了运行时间，但没有把不同算力成本伪装为完全公平的等算力比较。',
'- 所有成功率是实际 held-out 结果。表中标准误按种子实例计算；循环内回合不当作独立训练样本。多条件结果是描述性小规模研究，没有作确认性多重检验或总体资格声明。', '',
'## 1. 实际部署成功率', '',
'每个单元格先对四轮等权平均、再对 24 个种子实例等权平均；± 为种子标准误（百分点），不是 95% 区间。', '',
'| 变体 | 远距离线索 | 中途反转 | 两线索联合 |',
'|---|---:|---:|---:|']
for v in variants:
    cells = []
    for f in families:
        q = [r for r in memory if r['family']==f and r['variant']==v]
        per_seed = [average([r for r in q if r['instance']==i], 'deployed_mean') for i in range(24)]
        mean, se = st.mean(per_seed), st.stdev(per_seed)/(24**.5)
        cells.append(f'{100*mean:.2f}% ± {100*se:.2f}')
        diagnostics['allcycle'].append(dict(family=f, variant=v, deployed_mean=mean, seed_se=se,
            law_mean_on_evaluated_contexts=average(q,'selected_law_mean'), active_success_rate=average(q,'active_gross')/56,
            mean_trial_pairs=average(q,'trial_pairs')))
    lines.append('| '+names[v]+' | '+' | '.join(cells)+' |')
lines += ['', '远距离线索任务中，完整方案为 **90.20%**，仅最近两条为 **51.11%**，保留全部历史但等权混合为 **59.57%**。因此不是“只要存得多就好了”：有效线索的筛选与利用有实际作用。完整方案在已评估情境上的生成律期望为 90.00%；90.20% 的实测值高于 90% 是有限噪声，不是突破噪声上限。', '',
'稳定任务中，加入时间衰减并没有额外明显收益：完整 90.20%，只用不衰减统计 90.17%；固定八对试验也达到 90.23%。不把所有新组件都宣称为有效。', '',
'## 2. 规则变了：能恢复，但第一轮仍有明显断点', '',
'| 方法 | 第1轮 | 第2轮 | 第3轮：刚反转 | 第4轮 |', '|---|---:|---:|---:|---:|']
for v in variants:
    values = [average([r for r in memory if r['family']=='rule_reversal' and r['variant']==v and r['cycle']==c], 'deployed_mean') for c in range(4)]
    lines.append('| '+names[v]+' | '+' | '.join(f'{100*x:.2f}%' for x in values)+' |')
relevance = defaultdict(list)
for line in gzip.open(P/'evidence/snapshots.jsonl.gz', 'rt', encoding='utf-8'):
    s = json.loads(line)
    family, instance, variant = s['run'].split(':')
    if variant != 'full_v2':
        continue
    i = int(instance)
    relevant = s['definitions'].index(['past', i%5, (i//5)%2])
    relevance[family, s['cycle']].append((sum(k[relevant] for k in s['weights']), [sum(k) for k in s['weights']]))
for (family, cycle), values in relevance.items():
    diagnostics['relevance'].append(dict(family=family, cycle=cycle,
        first_relevant_selector_mass=st.mean(x[0] for x in values), timescale_masses=[st.mean(x[1][k] for x in values) for k in range(3)],
        analyst_only=True, xor_has_two_relevant_selectors=(family=='two_cue_xor')))
lines += ['',
'- 第3轮候选只接触过 **8 条新规则经验**；第4轮候选已有 **72 条**。完整方案第4轮候选成功率 89.45%，但实际部署为 86.98%，因为其中一个种子没有采用该候选。候选改善不等于已部署改善。',
'- 事后只读诊断：正确历史位置的平均混合权重，第2轮为 **85.90%**，刚反转时降至 **0.88%**，下一轮回到 **88.95%**。第4轮短时间尺度专家合计权重为 **91.74%**。隐藏位置只供此诊断使用，从未传给学习模块。',
'- 这里暴露的是：**正确线索仍重要，但它原来的预测关系失效了。当前权重把“线索是否有用”和“旧关系是否仍有效”混在一起。** 数字表示预测混合权重，不是“该历史事件导致失败的因果概率”；也不是事实被物理删除。',
'- 候选/部署只在轮边界替换，是事前对照协议的一部分。因此不能把恢复延迟全部归因于模型缺少思考时间，或声称只加训练就能解决。', '',
'## 3. 两条事实要联合起来用：当前表示不够', '',
'完整方案四轮平均 **49.12%**，所有变体约 49%—50%。这次任务要求两个远处的二元线索联合确定动作，单看其中任何一个，在均匀独立输入下都不足以知道正确动作。', '',
'当前策略比较的是各单变量专家预测的加权和，等价于在这些二元线索上使用加性判别；没有可学习/可选择的交互项。以二元 XOR 为例：', '',
'```text', 'x1 XOR x2 = x1 + x2 - 2*x1*x2', '```', '',
'现有模型缺少最后的交互项。增加相同结构的经验不能把一个不能完整表达该关系的模型变成完整表达者。严格边界是“不能完美表示 XOR”，不是“任何这种策略都绝不超过 50%”：最优加性分类器可以正确区分四种输入中的三种；在本实验 0.9/0.1 的结果噪声下，对均匀全集的期望成功率至多 70%。本轮实际约 49% 是学习规则与数据共同产生的实测结果。', '',
'这是后续数学/网络建模的首要缺口：需要可组合的关系表示，而不是只增加历史长度或重复训练；不能把测试中隐藏的两条正确线索直接写给学习器冒充自主发现。', '',
'## 4. 预算决策：少试验与少误采用不是同一个目标', '',
'下表每行 64 个独立种子；“成功数”是全部实际预算回合中成功的平均次数，包含试验消耗；净效用另扣每对 0.02 的声明成本代理。该成本不是实际时间标定。', '',
'| 旧→新真实成功率 | 预算 | 方法 | 平均试验对数 | 全预算成功数 | 净效用 | 采用数/64 | 有害采用/64 | 漏掉改善/64 |',
'|---|---:|---|---:|---:|---:|---:|---:|---:|']
case_names = {'large_gain':'0.30→0.70', 'small_gain':'0.55→0.65', 'null':'0.60→0.60', 'large_harm':'0.70→0.30', 'small_harm':'0.65→0.55'}
for case, label in case_names.items():
    for budget in (24,64):
        for method in ('budget','fixed8'):
            q = [r for r in gates if r['case']==case and r['budget']==budget and r['method']==method]
            lines.append(f'| {label} | {budget} | {"预算决策" if method=="budget" else "固定八对"} | {average(q,"trial_pairs"):.2f} | {average(q,"gross"):.3f} | {average(q,"net"):.3f} | {sum(r["adopted"] for r in q)} | {sum(r["harmful_adoption"] for r in q)} | {sum(r["missed_gain"] for r in q)} |')
        q = {(r['instance'], r['method']):r for r in gates if r['case']==case and r['budget']==budget}
        for field in ('gross','net','trial_pairs','law_expected_total'):
            d = [q[i,'budget'][field]-q[i,'fixed8'][field] for i in range(64)]
            diagnostics['matched_gate_differences'].append(dict(case=case, budget=budget, field=field, n=64,
                mean=st.mean(d), se=st.stdev(d)/8))
lines += ['',
'- 大改善、24回合预算：平均只试 **2.50 对**而非8对，全预算成功 **14.609 vs 13.125**。这是少把预算耗在对照试验上的收益，不是最终策略成功率变高。',
'- 大损害、24回合预算：有害采用 **9/64 vs 3/64**。尽管整体成功数仍较高，错误采用却更多。',
'- 小损害、64回合预算：有害采用 **21/64 vs 13/64**；全预算成功 **38.953 vs 39.828**，这次完整预算决策反而更差。',
'- 小改善、24回合预算也没有净效用优势。所有负面、零差异保留；这些小样本比例不是通用错误率标定。', '',
'**原因不是 Bellman 递推算错。** 存储复核逐状态验证了全部 11,510 个状态。当前公式最大化声明先验下的有限预算期望效用，没有单独要求“有害采用概率小于某数”。期望最优与控制下行风险是不同数学问题；先验也不保证对真实环境已校准。后续如要更少误采用，必须把适用任务的错误代价/风险要求明确写进目标，再看是否值得多试，不能凭感觉套一条对所有任务都保守的门槛。', '',
'## 5. 确认了什么，仍没有确认什么', '',
'已确认：真实历史输入、预测前误差、状态更新、冻结候选、真实试验、采用/保留和后续部署闭环能工作；历史选择和时间适用性在特定任务上实际改变行为。', '',
'没有确认：一般因果归因、通用语义理解、复杂多步规划、神经参数训练、自主发明表征、SLEEP长期巩固、纯RL优越性或从本二元任务向游戏迁移。本模块仍由人设计选择器/时间尺度/候选家族；它会根据反馈选择，不等于会自行发明任意规则。', '',
'成功/失败位是目标完成监督，试验控制器也使用明确效用。没有环境标量奖励输入，不等于完全无目标、无偏好或已经完成纯反馈/纯RL四组对照。', '',
'## 下一步优先级（尚未执行）', '',
'1. 先完善可组合历史表示的数学模型与网络映射：单条、成对及更高阶关系怎样提出、何时值得加入、怎样经实际试验验证；不要把全部组合无限展开或把隐藏答案给模型。',
'2. 区分历史线索本身的可复用性与当前映射/情境的适用性，解释并减少规则切换时的暂时失效。',
'3. 在真实预算和任务代价下比较效率与错误采用，而不是要求一个期望效用公式同时保证所有风险指标。', '',
'## 产物与核对边界', '',
'- `contract.json`：首次执行前固定的条件与预算；`native_exit.json`：首次运行及8个输入文件前后SHA；`review_exit.json`：首次存储复核。',
'- `evidence/episodes.jsonl.gz`：全部真实微型回合；`updates.jsonl.gz`：事实学习记录；`snapshots.jsonl.gz`：完整候选状态；`dp_table.jsonl.gz`：假设计算状态（不是额外真实经验）。',
'- `reviewed_summary.json`：逐原始回合、全部109,440次专家更新、1,440个候选状态、全部实际选用动作、试验决策和结果的另一份stdlib实现核对；未导入原环境/网络/torch。',
'- 神经参数不变由实际 native 前后字节摘要与无优化器记录支持；stdlib审核没有加载PyTorch权重文件，不把这一项冒称独立张量重验。',
'- `per_seed_results.csv`：全部种子/轮次；`diagnostics.json`：只读事后解释数据；`report.py`：本报告生成代码。没有新环境调用。',
'- 本复核仍属于同一研究者的内部实现核对，不是外部专家评审或科学PASS。旧执行代码/失败/结果未修改；没有恢复自动任务。', '']
with (P/'diagnostics.json').open('x', encoding='utf-8') as f:
    json.dump(diagnostics, f, ensure_ascii=False, indent=2, allow_nan=False)
with (P/'RESULTS.md').open('x', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(json.dumps(dict(report='RESULTS.md', diagnostics='diagnostics.json', new_environment_calls=0, new_parameter_updates=0)))
