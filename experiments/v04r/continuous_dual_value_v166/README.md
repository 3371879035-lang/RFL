# v166：当前完整双门控连续研究原型

[先看真实结果](result.md)：四个真实独立full-state agent各34主任务、不重置。三反馈组同用6次试验；未筛选20/34、事件门控21/34、双门控28/34。普通16/34。双门控把预算留给后面模型仍unknown的失败，修正及回访都实际成功。

## 实际入口

完整可运行接线已在 `workload.py` 的 `experiment()` 首次执行：

1. 原v105 ordinary learner bootstrap与固定Q*只读引用；显式ordinary checkpoint DATA物化，不恢复旧issued身份。
2. 原API一次安装新22edit完整source；四role各自clone完整I/current/L。
3. `read_models()`读取原v162事件参数，`read_execution_model()`读取原v165执行参数，经v163 `RecordedQueryModelPair`仅构造immutable模型参数DATA；两种fit均0。
4. 使用冻结 `../learned_execution_value_v165/execution_agent.py` 的 `ExecutionQueryAgent`，底层v162/v160/v156/v153真实source/ordinary/atomicexecutor/once。

关键constructor参数与本次实际调用一致：

- `learning_values=values`、`reference=REFERENCE`、`plan=main_plan()`，保留完整R+L，不只复制Q或只训治疗组。
- `event_enabled=True`、`query_value_model=models['policy']`、`value_gate_enabled=True`。
- `execution_value_model=execution_model`、`execution_gate_enabled=True`。
- `trial_budget=6`：两个分支共用单一实际counter/ordinal/once，不是各6次。
- `private_plan_factory=execution_plan`、`query_plan_factory=query_plan`、`private_context=private_context` 与 `emit`，实际函数均在同文件，不用旧类伪装新协议。
- `run_observed_task(mask=mask)`只由外层native执行器接收当时环境；新门控仅使用实际可见prefix和自己的L/D，不读取mask字段决定调查。

切换对照只改固定开关：Ungated两门控false、EventOnly仅事件true；TaskTD诊断false但普通TD/visitedD仍开启。成功主任务不调用诊断。

## 查看与后续开发

`execute.py`/`audit_stored.py`和capture已经封存，exclusive目录存在，**不要为了查看结果再次运行**。查看 `result.json`/`stored_audit_result.json`/原始 `evidence/raw.jsonl` 即可，无需重建runtime身份或重跑银行。

新研究使用新namespace/有限contract和真实来源，复用本类/参数不冒称旧F1/B1/science资格。这是CPU tabular局部研究原型，不是从零学习或可直接部署的通用RFL API；事件/执行标签窗口不同，不把预测幅度当同一全局效用。所有失败与成本视角保留。
