# 使用V220基础网络

依赖：当前本地Python环境`D:/强化反馈学习/.venv-v09/Scripts/python.exe`与PyTorch。代码与数据在同一仓库；以下是接口示例，不会自动触发训练。

```python
import sys, torch
from pathlib import Path
root = Path('D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009')
sys.path.insert(0, str(root / 'src'))
from feedback_program_v220 import LearnableFeedbackNet, NetworkConfig, Schema, MemoryBank

checkpoint = torch.load(
    root / 'experiments/v09r/learnable_memory_v220/capture/untrained_seed_7.pt',
    map_location='cpu', weights_only=True)
model = LearnableFeedbackNet(Schema(**checkpoint['schema']), NetworkConfig(**checkpoint['config']))
model.load_state_dict(checkpoint['state_dict'])
model.eval()
memory = MemoryBank(model.schema)
with torch.no_grad():
    output = model(torch.zeros(1,16), torch.ones(1,8), torch.randn(1,3,8), memory.view())
print(output['policy'])  # 随机初始网络，不是已训练策略。
```

## 学习接口

- `MemoryBank.add(Event(...))`：追加一个有来源的实际事实，重复同id同内容返回False；不同内容同id拒绝。
- `MemoryBank.training_example(event_id)`：返回目标事件之前的记忆输入与该事件，避免未来泄漏。
- `factual_nll`：实际后继、已观测反馈、可选公共目标值的联合混合NLL。
- `off_policy_loss`：传入记录的行为概率与有来源的优势值，适用于Actor/TrialManager/Adopter；不是完整离线RL算法。
- `replay_distillation_loss`：教师分布停止梯度；必须选择有来源且经过验证的教师。
- `PracticeAgent.execute`：唯一实际环境调用；采样动作、记录概率与实际结果。
- `PracticeAgent.reflect`：失败后的候选→网络选择是否实际试验→有实践来源的采用判断。成功不反思。
- `PracticeAgent.imagine`：一步预测与模型方差，返回独立对象；不能加入事实库。

环境执行器需要接收实际动作索引，返回`next_observation,feedback,feedback_mask,goal_met,terminal,cost`；不得把隐藏最优动作或未执行动作的结果伪装为事实。

当前`launch.py`使用独占capture路径，不要重跑覆盖本轮证据。后续训练或新实验应使用新输出目录和明确训练/验证切分。载入的三份checkpoint都是**未训练初始化**，没有把这轮记忆或梯度偷偷写入权重。
