# V223 加载与接口

## 加载未训练初始化

```python
import sys
from pathlib import Path
import torch

root = Path(r'D:\强化反馈学习\RFL-CausalChase-v0.3-dense-20261009')
sys.path.insert(0, str(root / 'src'))
from feedback_program_v223 import ObservableFeedbackNet, Schema, NetworkConfig, FeedbackLayout

saved = torch.load(root / 'experiments/v09r/provenance_visibility_v223/capture/untrained_seed_97.pt',
                   map_location='cpu', weights_only=True)
model = ObservableFeedbackNet(FeedbackLayout.from_dict(saved['layout']),
                               Schema(**saved['schema']), NetworkConfig(**saved['config']))
model.load_state_dict(saved['state_dict'])
model.eval()
```

种子 83 与 97 都是 `UNTRAINED_INITIALIZATION`，不是训练后的最佳模型。宽度、记忆节点、假设数、候选数和数值积分点数可以配置；扩大配置不自动兼容旧权重。

## 信息来源的声明

`FeedbackLayout` 描述外部反馈字段与公开基本量的关系：

- `View((('innovation', i, 1.),))`：新基本测量 i 的直接显示字段。
- `View((('goal_met', 0, 1.),))`：已有公开目标达成标记的副本。
- `View((('next', 0, 1.), ('observation', 0, -1.)))`：已有后继与当前观察的差值。
- 同一个测量可以有多个显示字段；只有相同基本身份才合并，不依据数值相似猜测。

这些声明来自可信数据格式，不允许为了获得期望结果随意把不同测量说成同一份。当前不包含自动文本语义解析；不支持的非线性显示关系可以暂作为单独观测建模，但不能声称已自动消除其语义重复。

`MemoryBank` 保留原始 `Event` 回执，神经视图规范化为新基本反馈与 mask。未知反馈值被忽略，不作为 0 值事实监督；显示字段里已有的后继、达成、终止不重复作为独立似然项。

## 实际实践

`PracticeAgent(model, namespace, rng, thought_depth=3)` 使用新记忆库；`execute` 调用真实外部环境，`reflect` 只在终局失败后触发。候选选取、思考停止、实践选择、采用评分都有可训练模块，不是按环境结果手写动作规则。

环境必须实际执行动作后提供观察与 mask。不能把预测结果当成实际结果，不能让模型直接读取隐藏缺失值。小流允许回到失败前最后的公开观察点进行试验；其他环境若不能这样合法重置，必须显式改变实践协议，而不是假设同起点已实现。

`agent.thoughts` 与 `agent.bank` 分开。新候选没有真实试验回执不能采用；这只是资格边界，不意味着试过一次就证明优于原行为。

## 训练接口（本轮没有执行更新）

```python
from feedback_program_v223.losses import sequence_nll
world_parameters, decision_parameters = model.parameter_groups()
world_loss, details = sequence_nll(model, bank, contiguous_actual_event_ids)
```

损失对观察连续坐标取协方差子矩阵，计算边缘密度；可见性、条件终止和达成各出现一次。假设 k 贯穿序列，目标事件不进入输入前缀。训练的合法目标来自真实结果，而不是模拟节点。

世界与决策参数梯度分离。决策损失仍需真实的改进/成本目标与对应计算路径；合成梯度检查的常数目标不是实际训练方案。跨权重版本的旧候选码必须处理生成前缀/离策略问题；来源格式变化也要显式转换数据，不能直接继承旧资格。

## 证据

- `RESULTS.md`、`result_summary.json`：结论、数量和边界。
- `capture/claim.json`、`exit.json`：事前输入与实际退出。
- `capture/events.jsonl`：184 条完整记录；`checks.json`：8 项定向检查。
- `capture/stored_audit.json`：仅标准库复核，不执行网络或旧实验。

不要重新运行已经完成的独占 capture 来覆盖结果。以后训练要新命名输出并保留本次未训练检查点及旧失败。
