# V0.4：局部学习式反馈与实践原型

**当前局部阶段：已完成，结论有条件。** 原冻结完整V04R方案：未执行/未资格，不迁移PASS。当前事实入口是v124，不再把旧版本的next_work按顺序重新排入待办。

## 先看哪里

1. [阶段结论与边界](local_stage_completion_v124/completion.md)
2. [机器可读阶段状态](local_stage_completion_v124/completion.json)
3. [最终连续流与实践结果](ambiguity_practice_v123/result.md)
4. [必须保留的连续流失败](recurrent_task_stream_v122/result.md)
5. [位置迁移失败](position_transfer_v120/result.md)

当前已验证链：真实可见失败 → 普通学习 → 学到的候选价值 → 歧义时付费小实验 → keep或局部更新 → 持续学习与只读结果。成功只有普通学习。它不是完整因果后验、通用RFL或从零训练。

最终DQ同流：普通学习6/16，冻结特征选择7/16，整段清除11/16，有限实践12/16；实践另付6个回合。修订patch全部13/16，没有额外回报收益。总体推断、净算力节省与完美保留均未建立。

## 代码与数据导航

| 位置 | 作用 |
|---|---|
| `failure_only_orchestration/orchestration.py` | 成功/失败分流与原接口预算 |
| `learned_candidate_choice_v118/candidate_loop.py` | 实际回合、同轨迹普通TD、结构化局部写执行器 |
| `evidence_value_transfer_v121/evidence_selector.py` | 共享可见轨迹特征与冻结候选价值表 |
| `ambiguity_practice_v123/practice_policy.py` | 同分请求及按真实试验结果选候选的规则 |
| `ambiguity_practice_v123/workload.py` | 实际连续流、runner私有当前条件实践分支与只读检查 |
| 每版本`contract.json` | 实验前固定设计、边界和资源上限 |
| 每版本`evidence/raw.jsonl` | 首次真实执行的完整原始记录 |
| 每版本`result.json`/`stored_audit_result.json` | 结果与对应存储核对；内部核对不是sciencegate |
| `../rebuild_status_current.json` | 事实索引，非资格证明 |

这些是版本化研究实现，不是宣称可直接部署的通用API。既有`execute.py`采用独占一次capture，**不要为查看结果重跑它或旧checker**。新研究应有自己的有限问题、contract和capture；本阶段的失败、partial、零结果与全部执行源保持原样。

## 历史分支（按研究作用读，不是默认执行清单）

- v117：真实任务/普通学习/诊断执行器接线。
- v118–119：学习keep/修正及具体地址选择。
- v120：位置策略移位的真实反例。
- v121：共享轨迹特征与训练外位置验证。
- v122：重复失败与知识保留的真实缺陷。
- v123：有成本的实践消歧与新任务流结果。
- v124：选定局部阶段收口，未新增RFL执行。
