# V224 使用入口

## 加载未训练网络

```python
from pathlib import Path
import sys
import torch

root = Path(r'D:\强化反馈学习\RFL-CausalChase-v0.3-dense-20261009')
sys.path.insert(0, str(root/'src'))
from feedback_program_v224 import FeedbackCreditNet, Schema, NetworkConfig, FeedbackLayout

saved = torch.load(root/'experiments/v09r/real_credit_v224/capture/untrained_seed127.pt',
                   map_location='cpu', weights_only=True)
model = FeedbackCreditNet(FeedbackLayout.from_dict(saved['layout']),
                          Schema(**saved['schema']), NetworkConfig(**saved['config']))
model.load_state_dict(saved['state_dict'])
model.eval()
```

这里两个检查点都不是训练成果，不存在“较好的 seed”选择。宽度、槽位、候选数等可配置，改变尺寸需要新初始化/显式转换。网络无游戏规则导入；真实观察和动作通过 `Schema`/`FeedbackLayout` 提供。当前是结构化数值接口，不是任意文本输入的现成通用模型。

## 实际行为与事实记忆

`PracticeAgent(model, namespace, random.Random(seed))` 执行真实环境 callback。

- `execute(..., purpose='source'|'post_choice')`：普通任务实际动作与回执；回执保存行为概率，神经记忆不把该概率当事实特征。
- `reflect(failure_event, actual_trial_callback, budget)`：只在实际终止失败后产生 session；想象单独保存，不可冒充真实试验。
- 候选/停止/试验/采用由未训练或已训练网络抽样。没有真实试验的候选不能采用；有回执不保证候选好。
- 新版本 `replace_model` 使旧 live session 失效并重置当前控制，不能用重要性重放的训练数据复活旧运行资格。

当前试验 callback 回到失败前的同一个公开起点。若某环境不能合法重置到这个起点，必须改变实验协议，不能假装已具备对应实践能力。

`MemoryBank` 的真实历史不被 96 个工作槽位截断。工作槽位是可学习计算资源，原始事件节点和想象节点不同。来源投影继续使用 V223 的已知 schema 声明，不凭数值相似或自己的预测去认定重复事实。

## 真实结果训练接口（这里只演示计算损失，不执行更新）

```python
import json
from feedback_program_v224.learning import evaluate_trace

trace = json.loads((root/'experiments/v09r/real_credit_v224/capture/trace_seed127.json').read_text())
credit = evaluate_trace(model, trace, mode='on_policy')
policy_losses = credit['policy_losses']    # 三个目标分别输出
critic_losses = credit['critic_losses']
targets = credit['targets']              # 实际后续目标/环境成本/思考行数
```

该接口重建候选创建前缀的可微计算，**不重新运行环境、不重建 live issued handles、不使用当前完整历史冒充创建时历史**。它现在要求从空初始记忆开始的完整闭合轨迹；尚不支持只截取任意中段却宣称全路径 off-policy 无偏。

`mode='same_world_IS'` 仅允许世界参数/物理抽样语义相同的另一策略，返回完整路径重要性权重；值可能高方差。改变世界后，这条旧想象策略接口会拒绝，但仍可使用真实序列：

```python
from feedback_program_v223.losses import sequence_nll
from feedback_program_v224 import MemoryBank
bank = MemoryBank.from_json(json.dumps(trace['memory']))
world_loss, details = sequence_nll(model, bank, trace['episodes'][-1]['source_ids'])
```

世界似然只训练世界参数；策略损失不进入世界；critic 输入对策略断梯度。未来调用方须分别选择训练参数组和目标权衡。本轮没有 optimizer，也没有默认三目标权重。

`diagnostic_detach_candidates=True` 仅供反向断点诊断：前向值相同、候选生成梯度切断。不要把该诊断算子称作另一个实际运行模型或训练方案。

若以后优化目标达成/成本 score-function 损失，它属于 RL 风格目标优化，不是严格无奖励纯反馈组的自动替代。SLEEP 蒸馏、参数更新后保留能力和真实收益仍未执行。

## 结果与复现边界

参见 `RESULTS.md` 和 `result_summary.json`。独占 `capture` 已完成，不覆盖重跑。下一次真实训练应使用新的输出位置、明确训练预算并保留本轮未训练初始化与所有历史失败。
