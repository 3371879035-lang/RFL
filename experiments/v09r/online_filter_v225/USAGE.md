# V225加载与连续实际历史接口

## 未训练检查点

```python
from pathlib import Path
import sys
import torch

root = Path(r'D:\强化反馈学习\RFL-CausalChase-v0.3-dense-20261009')
sys.path.insert(0, str(root/'src'))
from feedback_program_v225 import FilteredFeedbackNet, Schema, NetworkConfig, FeedbackLayout

saved = torch.load(root/'experiments/v09r/online_filter_v225/capture/untrained_seed149.pt',
                   map_location='cpu', weights_only=True)
model = FilteredFeedbackNet(FeedbackLayout.from_dict(saved['layout']),
                           Schema(**saved['schema']), NetworkConfig(**saved['config']))
model.load_state_dict(saved['state_dict'])
model.eval()
```

137与149均为新未训练初始化，不是择优训练成果。参数尺寸沿用V224，行为语义包含新的过滤版本身份，不能只因张量尺寸相同就迁移旧session资格。

## 实际运行

`PracticeAgent`保持原实际环境callback接口：

- `execute(..., episode=..., step=0, previous_id=None)`：新episode/新试验分支。
- 同一连续任务下一步传入同一个episode、下一step以及**实际前一个Event.id**。代理使用实际缓存状态预测，拿到外部结果后才更新一次。
- `reflect(failure_event, actual_trial_callback, budget)`：失败后可选思考和实际试验；试验有自己的episode，不继续已终止状态。
- `replace_model`清空旧缓存并使旧live session失效，事实节点保留。

这里新分支可以合法复位到失败前公开状态。若真实环境不支持此复位，须另立实践协议，不能让预测假冒真实复位试验。

## 离线预测的条件必须明确

```python
from feedback_program_v225 import MemoryBank

# bank.forecast_view(previous_event_id, stop) 根据实际连续前驱链拆分参考和本段证据。
memory = bank.forecast_view(event.previous_id, stop=bank.index[event.id])
out = model(obs_tensor, goal_tensor, actions_tensor, memory)
```

`bank.view(stop)`不指定连续前驱，含义是**新根/新分支**。不要把它用于连续任务的每一步，然后以为网络会通过观察相似性自动猜中episode关系。

`forecast_view`不支持隐藏地略过穿插事件、改变目标、跨终止继续或引入目标事件之后的数据。当前单个`BeliefState`对应一条实际链；多条独立链可分别维护，不是全局共享一个隐状态。

事实银行、当前段状态和想象节点分开。96个工作槽位不是历史容量上限；节点ID用于原始身份去重，不是自动识别人类描述语义重复的功能。

## 后续训练接口（此处不执行优化）

```python
from feedback_program_v225.losses import sequence_nll
world_loss, details = sequence_nll(model, bank, actual_event_ids)
```

完整或中段都使用相同的真实递推。中段起点前的实际前驱用于构造条件状态，目标事件不进入初始输入。参考实现不截断先前条件状态的梯度，长段训练需另外安排内存/截断预算。

**不要调用旧V223 `sequence_nll`来训练V225的中段**，否则又回到不同初始化条件。

实际候选信用接口：

```python
from feedback_program_v225.learning import evaluate_trace
credit = evaluate_trace(model, closed_trace, mode='on_policy')
# credit['policy_losses'] / ['critic_losses'] 各为三个分别报告的目标，不默认合成总分。
```

它从记录的候选创建前缀和每个动作的真实前驱重建。旧V224 trace不能仅改版本字符串冒充V225采样轨迹。同世界的完整路径重要性采样接口仍在，仍有高方差限制；本轮新增实验重点是同快照重建，不冒称再次验证了全部跨策略域。

数学上，后验改变是状态推断，不是参数训练。采用目标/成本策略损失进行参数优化属于RL风格目标优化，不自动成为严格无奖励的纯反馈训练。SLEEP蒸馏和训练后保留能力均尚未执行。

## 本轮数据

`RESULTS.md`列出结果及缺陷；`capture/trace_seed*.json`保存真实轨迹和75次在线状态吸收；`capture/checks_seed*.json`保存一致性和梯度结果；`capture/diagnostic_seed*.json`明确区分额外只读想象。

独占capture已完成，不覆盖或重跑旧实验。下一次参数训练使用新的输出位置、明确预算并保留这些未训练检查点。
