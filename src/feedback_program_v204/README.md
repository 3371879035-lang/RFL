# 可直接导入的权重编程反馈核心 V204

核心不依赖游戏、任务模拟器或 `experiments` 下的旧模型。所需依赖为 PyTorch；把本仓库 `src` 加入 Python 模块路径后，导入 `feedback_program_v204` 即可。

这是**通用数值接口的基础反馈算法**，不是能理解任意输入的预训练模型。情境、动作和事实描述需要具有稳定的数值语义。目标通过公开事实通道的线性偏好给出，不通过隐藏正确答案给出。

## 最小接口

```python
import torch
from feedback_program_v204 import Config, FeedbackNet, write_initial_weights

# 维度可以配置；下面仅示范接口，不是新的性能实验。
net = write_initial_weights(FeedbackNet(Config(
    context_dim=4, action_dim=3, fact_dim=2,
    capacity=384, planning_depth=6,
))).eval().requires_grad_(False)

actions = torch.eye(3)                 # 公开的合法动作描述
goal = torch.tensor([1., 0.])          # 希望提高第一个结果通道
before = net.prepare(actions, goal)   # 冻结旧策略；不调用环境
scores = net(torch.tensor([.2, .4, .1, .7]), before)['scores']

# 只有实际执行后才写入对应观测；此处数值是接口示例输入。
net.observe_transition(
    context=[.2, .4, .1, .7], action=[1., 0., 0.],
    successor=[.3, .5, .2, .8], terminal=True,
    facts=[.6, .4], known=[True, True],
)
candidate = net.prepare(actions, goal)
```

实际采用闭环：先冻结 `before` 与 `candidate`，在相同公开初始条件上分别实际运行，收集真实结果。调用：

```python
evidence = net.assess_local_trials(
    trial_initial_contexts, actual_candidate_outcomes,
    actual_before_outcomes, goal, candidate,
)
verdict = net.trial_decision(next_initial_context, evidence)
selected_whole_policy = candidate if verdict['adopt'] else before
```

上述 `trial_*` 和 `actual_*` 是调用方实际采集的数据，不得用模型自己的预测代替。整个回合采用一个完整冻结策略。试验批次全部结束后，才把这批真实转移写入未来记忆；外部评估不进入学习。这是实验中采用的时序，不是参数训练。

## 状态与权重分开

- `write_initial_weights` 直接编写参数；实验运行中不更新参数。
- `observe_transition` 更新真实经验和样本前预测误差。
- `prepare` 生成冻结的记忆/策略快照，之后新经验不会修改旧快照。
- `forward` 给出目标分数、事实矩值、专家概率和不确定性代理。
- `memory_state` / `restore_memory` 保存和恢复经验状态，不把经验伪称为权重学习。

只保存初始权重不会保存运行中积累的经验。需要跨进程继续时，可以显式 `torch.save(net.memory_state(), path)`，然后把读回的状态传给 `restore_memory`。参数检查点和经验状态应分别保存。

## 已知范围

当前事实结果按有界 `[0,1]` 通道建模，中性先验为 .5；未知通道用 mask，不是失败。目标读出与多步传播针对终局结果，尚未实现任意逐步代价的累积。Q/K 采用数值距离；没有自动语义特征训练、隐藏混杂下因果识别或 SLEEP 参数巩固。

采纳依赖邻近条件具有相近效果的假设；试验有限时可能误采纳。快慢经验尺度按样本前误差选择，仍然不能提前知道环境何时变化。`capacity` 与 `planning_depth` 是显式计算配置，不是任意长程能力保证。

正式实验入口为 `experiments/v09r/weight_programmed_feedback_v204`；结果与局限按该目录的真实记录说明，不把基础接口可导入等同通用模型目标已经全部完成。
