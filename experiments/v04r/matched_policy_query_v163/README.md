# v163：当前策略条件化的查询价值，局部可选扩展

先读 [实测结果](result.md)。同一对新任务来源：普通9/12成功；始终/仅数值/策略感知都10/12，策略感知只付1次试验而不是2次。该试验自身失败，但避免后续一次主任务失败；另一冗余试验被正确省掉。

- `workload.py`：真实ordinarycheckpoint→两原合法source各1Dedit→每case4fullR+L/I角色各6任务→真实失败调查/严格owned experience once→后续普通任务，无within-case reset。
- `model_data.py`：`RecordedQueryModelPair`只恢复已审学习参数DATA；不是恢复source/pair/receipt/native identity。来源pins与构造流见contract/新审阅。
- 冻结复用 `../policy_conditioned_query_v162/query_value.py` 与 `gated_agent.py` 的 `PolicyQueryAgent`。新source可传`query_value_model`及`value_gate_enabled=True`选择开启；也保留numeric同数据消融和ungated对照。Q*、ordinary alpha/epsilon与原环境不变。
- 参数的历史6点来自真实后续回报，不是手写收益；当前策略特征和换入口问题语法仍是人工给定。未知仍返回None，预算内真试验，不默认拒绝行动。

`execute.py`和`audit_stored.py`已首次执行并封存，**不要重跑**；后续试验新namespace/事前有限contract，所有失败和零值保留。默认生产/通用策略没有更改，无科学资格/全域成本最优宣称。V0.4当前导航见 `../CURRENT.md`。
