# 推荐入口：ConsistentEvidenceMemoryNet

本目录首版实验与定向修订都保留；请用一致性修订网络开始后续训练，而不是误加载首版任意逐对比较头。

```python
import sys, torch
from pathlib import Path
root = Path('D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009')
sys.path.insert(0, str(root / 'src'))
from feedback_program_v221 import Schema, MemoryBank, PracticeAgent
from feedback_program_v221.network import NetworkConfig
from feedback_program_v221.consistent_network import ConsistentEvidenceMemoryNet

file = root / 'experiments/v09r/evidence_memory_v221/consistency_revision/capture/untrained_seed_41.pt'
checkpoint = torch.load(file, map_location='cpu', weights_only=True)
model = ConsistentEvidenceMemoryNet(
    Schema(**checkpoint['schema']), NetworkConfig(**checkpoint['config']),
    comparison_rank=checkpoint['comparison_rank'])
model.load_state_dict(checkpoint['state_dict'])
model.eval()
memory = MemoryBank(model.schema)
```

文件明确标记`UNTRAINED_INITIALIZATION`，不是训练后模型。默认10093631个可训练参数，可改变宽度、注意力层、工作节点数量、预测成分与候选数量；换结构不能直接当同一checkpoint加载。

## 记忆与实践

- `MemoryBank.add(Event(...))`保留唯一原始事实；`view`与`training_example`形成前缀，不把摘要或想象写成新事实。
- `MemoryBank.evidence(groups, stop)`按实际事件id形成各做法的证据集，支持同一做法多次试验。
- `PracticeAgent.execute(...)`获取真实观察，记录行动前预测、实际结果、行为概率和上下文。
- `PracticeAgent.reflect(event, environment_callback, budget)`在终止失败后由网络选择停止/重试当前做法/尝试候选，随后选择保持或采用。成功与非终止观察不触发局外失败会话。
- 回调必须实际执行所选动作并返回公开观察；局部重置能力由环境提供，不能把模型预测冒充实际执行。
- `comparison_example`把比较目标的两条实际试验都排除在支持记忆之外，提供更晚结果作为训练目标。
- `replace_model(new_model)`在明确参数版本切换后保留事实、清除旧控制码、关闭旧会话采用资格；新候选需要新实践。不要绕过版本接口继续使用旧码。
- `imagine`仍只返回一步非事实预测；它不是多步梦境规划器。

## 学习接口

`feedback_program_v221.losses`提供事实NLL、带行为概率的策略损失、回放蒸馏和实际比较NLL。已验证梯度路径；没有自动运行优化器，也没有完成全套离线RL/元学习训练器。候选生成、选择、实践、采用跨多个阶段，后续必须正确重建生成前缀和联合行为概率，不能将冻结的旧控制码直接当成当前生成器的梯度路径。

原始事件、每步决策概率、会话候选、完整试验回执与初始权重均保存在相应capture目录。不要重跑launcher覆盖既有独占capture；后续训练另设输出目录和训练/验证切分。
