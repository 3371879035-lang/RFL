# V0.5 v169：已完成的有限反馈效率原型

先看[result.md](result.md)或[analysis.json](analysis.json)。此目录已经完成首次真实运行，**查看结果不需要再次执行原命令**。两个evidence目录和首次失败审阅结果均已封存。

## 实现

- `experiment.py`包含新的二出口房间环境、真实观测发行/一次消费、共同控制器操作、事实/奖励学习器、P/S调查流程及执行入口。
- `contract.json`在首个native前固定六案例、六组、控制器源、工程坐标、两类预算和源码清单。原计划见`../plan_v168.json`。
- 一个成功出口在本抽象环境中用一个step进入下个房间；受阻出口COLLISION终止，最终出口SUCCESS。不是旧5×5地图的物理等价重放。
- `Agent`只收到PublicTask和真实Feedback；真实出口数组只在Engine中用于实际推进。全源真值记录供外部审计，不是学习特征。
- RP/R共同学习实际执行动作的物理Q值，alpha=.5/gamma=1，只有终止失败reward不同。命令→实际执行关系由带当前控制版本的事实表学习；所有真实试验的物理转移都属于同一个不变世界，可一次学习，不复制私有Q表。
- F是独立`FactLearner`类型，无Q字段，接收仅含事实的包；从条件转移学习和目标搜索选择行动，不在背后使用reward标签、旧Q*或价值树。
- P/S同通道基础学习相同，共同的`Agent.menu`与`Controller.revised`定义动作/修正权限；区别仅为固定循环还是证据导向顺序与当前来源查询索引。保护哨兵不能写。
- 源世界不因控制器修正而变化，修改的是agent的局部执行配置。这里的接口是新版本原型，不迁移旧B1/F1资格。

## 已执行命令（历史，不是待办）

在本目录，以本地Python `-X utf8 -B` 调用：

```text
experiment.py --phase wiring --output evidence_wiring
audit_stored.py evidence_wiring
experiment.py --phase matrix --output evidence_matrix
audit_stored.py evidence_matrix          # 实际exit1，错误保留
audit_stored_v2.py evidence_matrix       # 新版本存储审阅exit0，非native重试
analyze_stored.py                        # 只读实际数据，生成分析/CSV/SVG
```

原`experiment.py`、contract和首个审阅器自native开始未更改。v2审阅器与原版只有时间比例断言及输出文件名两处逻辑差异，另有生成新文件时的LF→CRLF行尾变化；两版执行字节不再格式化。若将来另做新问题，应明确新namespace/contract和预算，不覆盖这些capture、不直接重跑旧fixture。

## 结果文件

- `evidence_wiring/raw.jsonl` / `exit.json` / `audit_result.json`：6回合最小接线和真实性边界挑战。
- `evidence_matrix/raw.jsonl` / `exit.json` / `result.json`：36条完整流；主任务48次连续且不重置。
- `evidence_matrix/audit_result.json`：首次时间元数据审阅错误；`audit_result_v2.json`：完整修正审阅。
- `analysis.json`、`group_summary.csv`：分组、难度、成本、零/负结果与范围。
- `targets.csv`：全部36条达到/未达到12连胜窗口的成本，未达保留空值，不补0。
- `failure_curve.csv` / `learning_curves.svg`：每档深度的完整累计主任务失败曲线。
- `matched_cost.csv` / `cost_curve.csv` / `matched_cost_curves.svg`：相同实际环境步数范围内的成功交付。
- `completion.json` / `source_binding.json`：逐项完成证据与本轮必要文件绑定，不是科学资格证。

图中P为虚线、S为实线；主任务曲线中RP两组完全重合是实际数据，不是漏画。SVG已做XML/数据坐标校验，不宣称经过独立人工视觉评审。

## 当前边界

这是六个确定、未漂移的固定工程案例，不是六个独立seed或288个独立统计单位。S使用声明的手工调查规则加真实经验索引，不是学习了通用因果后验。纯反馈仍使用任务目标和给定拓扑；F与Q路径的比较不是只改一个数字的消融。

同效果省试验、同预算更多交付都算本阶段的实际进展，不要求最终一直领先；纯反馈S相对P少1次主任务成功和全部NOT_REACHED均保留。当前局部V0.5已完成，无须为了全胜继续增加演示。
