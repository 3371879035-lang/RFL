# v164：完整连续agent中的可选learned event gate

当前真实26回合任务流同时包含执行纠错、学到的调查选择、保护映射和回访。先读[结果](result.md)：普通16/26，两个反馈组都21/26；门控省一次事件调查，却多做两次后续保护对照，合计6次vs未筛选5次，不能宣称全局省成本。

## 入口构成

`workload.py`完整展示bootstrap：原v105 nominal ordinary learning、原checkpoint显式R+L数据→一次新source安装→原参数树DATA→每role一个 `PolicyQueryAgent` 连续26任务。没有外部训练依赖或安装步骤。

- 运行类冻结位于 `../policy_conditioned_query_v162/gated_agent.py`，继承 `../unified_feedback_agent_v160/unified_agent.py`。
- `query_value_model=models['policy']` 来自固定v162参数记录，经v163 `model_data.py` 的 `RecordedQueryModelPair`构造；不是从JSON恢复任何旧native证据身份。
- `event_enabled=True`，`value_gate_enabled=True/False`只切换事件门控；执行菜单和原真实atomic store/strictsource/once完全相同。`trial_budget=6`是所有分支共用总量，不是每个分支6次。
- 普通对照 `algorithm='TaskTD'` 关闭诊断而**不关闭普通TD/visited-D学习**。全部role传同source/commonQ*/参数/mainplan，分别克隆完整I/current/L。

`execute.py`/`audit_stored.py`均已首次执行并封存，exclusive capture拒绝覆盖，**不要重跑**。后续研究新namespace/事前contract，保留任何零/不利。当前结果只资格到此固定工程流，不继承旧F1/B1/science PASS；默认v160原型不因本次局部门控自动替换。
