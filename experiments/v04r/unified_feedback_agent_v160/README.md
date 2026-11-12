# UnifiedFeedbackAgent：V0.4统一连续原型

## 真实入口

- `unified_agent.py`：唯一主agent。显式接收完整普通L；执行偏差菜单与到达事件调查共用self、R+L、严格来源注册表、once消费集合和试验预算。
- `workload.py`：已执行的完整构造/依赖bootstrap、两种nominal私有计划factory和环境执行transport示例。
- `result.md` / `result.json`：本次18主任务混合流的结果/代价/边界。
- `stored_audit_result.json`：新stdlib复核，不是科学资格或独立专家认可。

## 构造接口（本轮测试patch-adaptive）

需先使用`workload.py`开头同样的normal learning/TD模块bootstrap；它只加载冻结库，不是运行旧harness。不要直接import/执行旧workload来借其全局capture。

```python
loop = UnifiedFeedbackAgent(
    source, learning_values=ordinary_L,
    mode='patch-adaptive', role='treatment', source_label=label,
    reference=common_Q_reference, plan=main_engineering_plan,
    algorithm='Unified', event_enabled=True,
    trial_budget=6,                       # 两类调查共享，不是每类各6次
    private_plan_factory=execution_plan,   # (evidence, observed_prefix, n, greedy)
    query_plan_factory=query_plan,         # (evidence, planned_arrival_spec)
    public_transition_budget=4096,
    private_context=private_context, emit=emit,
)
receipt = loop.run_observed_task(mask=current_environment_mask)
```

`source`与`ordinary_L`是原LearnerPersistentState数据，不是JSON冒充issued身份；构造器clone完整L并走原检查。`main_engineering_plan`与两种factory用原normal105 nominal EngineeringPlan/EngineeringEpisode，source context/tape/proposal/params严格绑定当前主任务。`mask`只送实际执行transport，诊断方法不接收它；不要把原因truth/案例标签塞入evidence。

`algorithm='TaskTD'`关闭诊断、普通学习照常；`algorithm='ExecutionOnly',event_enabled=False`只走执行修正。`configuration()`给出实际MRO、写限和共享预算。所有分支都在主任务普通TD之后调查，真实观察在主回执后一次吸收入当前L；成功主任务不触发诊断。

## 两条路由，不是两个独立学习器

1. 真实可见命令执行不一致：复用冻结v156 PathwiseAgent，实际比较keep/当前位置删除；真实失败试验可提出有当前见证的第二位置假设，按原store一次事务提交；不是见到偏差就自动删。
2. 无执行偏差且真实TRAP：复用冻结v159 EventHypothesisAgent，公共几何生成“换入口到同一地点/时刻”的问题，真正试验再普通学习；没有可行另入口就keep，不补假分数/假观察。
3. 其他失败：keep并保留普通学习。成功：只有普通学习。

新构造器明确恢复执行分支的两地址写权限（event-only基类原设为0），不是monkeypatch旧类。原API/guard/law-registry未改，两点试验证据规则仍是显式V04实验规则，不冒充旧whole-B1/F1资格。

## 使用边界

本文件夹capture已经首次完成，**不要重跑`execute.py`/`workload.py`覆盖或追加本数据**；新任务用自己的有限计划/contract和独占capture。正式keyed permit仍关闭，无keys/RNG/collector权限。不要把本简单固定域原型当通用规划器、世界模型或可直接部署的跨域产品。
