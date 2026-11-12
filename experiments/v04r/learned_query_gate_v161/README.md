# v161 learned query gate（实验扩展，非默认）

先读 [实际结论](result.md)。已完成首次真实实验：正确省掉一次无收益调查，也误跳过一次有用调查，主任务19/24，低于always20/24，高于普通18/24。不要把native/audit0误称模型泛化通过。

- `query_value.py`：显式recorded DATA/真实live投影、两float特征、只从历史真实后续回报训练的冻结回归树。
- `gated_agent.py`：`QueryValueGatedAgent`继承v160同一个完整agent；需传`query_value_model`和`value_gate_enabled`；未知不等零，预算内真试验。默认入口仍为v160，勿无条件开启筛选。
- `workload.py`：v105显式普通学习bootstrap与原checkpoint/严格trial来源接线，三role各24任务，无情境重置，无新key。
- `contract.json`：固定A/B/C/D挑战和有限预算，首native前已有D的策略变化挑战，不是失败后改测例。
- `evidence/`、`stored_audit_result.json`：完整首运行证据与新stdlib stored review。

`execute.py`和`audit_stored.py`均已执行并封存，exclusive capture拒绝覆盖，**不要重跑**。后续修改用新版本/namespace，旧source/runtime身份不能由JSON伪造恢复。没有外部依赖安装，无正式collector或自动安排启动。
