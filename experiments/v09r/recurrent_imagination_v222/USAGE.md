# V222 使用与训练边界

本版本保留 V221，不覆盖旧网络或旧证据。优先入口是 `src/feedback_program_v222`。

## 加载未训练初始化

```python
import sys
from pathlib import Path
import torch

root = Path(r'D:\强化反馈学习\RFL-CausalChase-v0.3-dense-20261009')
sys.path.insert(0, str(root / 'src'))
from feedback_program_v222 import RecurrentFeedbackNet, Schema, NetworkConfig

saved = torch.load(root / 'experiments/v09r/recurrent_imagination_v222/capture/untrained_seed_73.pt',
                   map_location='cpu', weights_only=True)
model = RecurrentFeedbackNet(Schema(**saved['schema']), NetworkConfig(**saved['config']))
model.load_state_dict(saved['state_dict'])
model.eval()
```

初始化文件明确标记 `UNTRAINED_INITIALIZATION`。两个文件分别对应种子 61、73；不是最佳训练权重，不应根据本次小流的成功数择优。

`NetworkConfig` 可调整 width、attention_heads、memory_layers、memory_slots、hypotheses、candidates；宽度应能被注意力头数整除。本轮使用 width=256、heads=8、slots=64、hypotheses=8、candidates=3。配置改变意味着新架构，不兼容地直接加载旧权重不是扩容训练。

## 实际运行边界

- `PracticeAgent.execute` 每次调用外部环境一次，保存真实 `Event`。
- `PracticeAgent.reflect(event, environment_callback, budget)` 仅终局失败触发；`thought_depth` 是可配置计算预算。
- 环境 callback 必须真正执行所选合法动作，并返回 `next_observation/feedback/feedback_mask/goal_met/terminal/cost`。不可把网络预测或隐藏评价器答案作为执行结果。
- 本小流可从失败前最后观察点重新实践；其他真实环境若不能合法重置到该点，必须改变外层实践接口，不能假装已经做到相同起点比较。
- `agent.bank` 只存事实；`agent.thoughts` 是模拟日志。`ThoughtNode` 不可通过 `MemoryBank.add`。
- 原有成功/非终局零额外反思行为保留。普通真实经验仍可保存并用于后续训练。

## 多步内部推演

```python
from feedback_program_v222.imagination import noise_tape

# output 来自 model.forward；codes: [1, 1 + candidates, width]。
tape = noise_tape(seed=123, depth=3, hypotheses=model.config.hypotheses,
                  observation=model.schema.observation, feedback=model.schema.feedback)
thought = model.dream(output, codes, tape)
```

保存 `tape` 可重现内部采样。`force_continue`、`fixed_action` 是定向检查用途，不用于声称模型自主选择了推演深度或行动。`thought['summary']` 可进入 `trial_logits_with_thought`；采用层仍只接真实证据。

## 训练接口，不是本轮训练结果

```python
from feedback_program_v222.losses import sequence_nll, decision_path_loss

world_parameters, decision_parameters = model.parameter_groups()
world_loss, details = sequence_nll(model, bank, contiguous_actual_event_ids)
```

每个序列的预测目标从它之前的真实前缀建立输入；共享假设贯穿片段。`sequence_nll` 中公共目标标量是即时达成信号，不是自动获得的长期回报或外部 Q*。

世界侧包含实际历史编码和递归物理预测，决策侧包含行为、候选、证据适配、思考与实践选择。两组梯度已分开；没有自动优化器调用。以后训练时不能把本轮合成梯度检查的常数目标当作任务学习目标。

`decision_path_loss` 要求真实、合理估计的 advantage 和对应当前模型的计算/行为 log-probability。不能把旧快照的冻结候选码直接当成仍连接着当前候选生成器的图；跨版本重放需要保存和重建生成前缀，当前未提供完整处理。

既有回放/蒸馏损失导出只是接口复用，不证明已经发生长期巩固。启动训练前还应处理 `RESULTS.md` 中的输出语义重复、未来反馈可见性和独立采用验证问题。

## 证据入口

- `result_summary.json`：从保存的原始结果汇总的唯一便捷入口。
- `capture/events.jsonl`：236 条原始记录，含 59 次真实调用和推演内容。
- `capture/exit.json`、`numerical_completion/capture/exit.json`：永久保留的两次检查失败。
- `remaining_checks/capture/summary.json`、`stored_audit.json`：剩余检查与全记录复核。
- `source_binding.json`：本次文件/旧输入保全索引，不是科学资格门禁。

不要重新运行原 launch 来“覆盖通过”；其 capture 是独占目录。本轮已完成的环境流不需要重跑。
