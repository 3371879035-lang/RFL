# v165：执行调查价值的可选学习门控

先读[实测结果](result.md)：3新来源各6主任务，双门控保持14/18成功，将已有事件门控的7次额外试验减少到5次；K147→139，TX62→55。普通对照5/18，始终普通学习。未知反复等待仍真实试验，不默认跳过。

- 新 `execution_agent.py` 的 `ExecutionQueryAgent` 继承冻结v162 `PolicyQueryAgent`/v160统一agent；新 `execution_gate_enabled` 仅控制执行菜单是否值得进入，原纠错/once/typedsource/atomicstore不变。
- `run_observed_task` 在原native之前保留actor自己的不可变数字Q数据，mask仅原样转交原执行器；普通TD后 `ExecutionFeatureData` 投影出真实学习变化，不读隐藏原因。
- `execution_value.py`：闭合实际factual/beforeL/afterL数据与2个特征。`QueryTrainingPoint`只含特征/真实后续增益；原v162 SSE fitter新拟合执行树一次。
- `workload.py`：完整bootstrap、pinned v164全部2执行问题/TaskTD结果、真实3来源安装和9个独立6episode角色，展示两个新constructor参数 `execution_value_model`、`execution_gate_enabled`。
- 原 `value_gate_enabled` 仍控制事件分支，两个门控共用每caseagent实际试验计数。它们的标签窗口不同，不把数值当全局统一效用。

新树为局部可选实验模块，不替换默认全域策略；原v164完整连续流仍只有事件门控，不能迁移为新双门控全流证明。`execute.py`及`audit_stored.py`已运行封存，**不要重跑**；后续新namespace/事前有限contract。所有失败/zero/未知/不利保留，无正式key/collector或自动安排变更。
