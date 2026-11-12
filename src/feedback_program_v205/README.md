# V205 一阶事实算子原型

入口：`FactNet`、`FactMemory`、`Policy`。独立于游戏和实验任务模块；使用 PyTorch CPU float64。

本版实现解析权重的差分核、过程贡献 `c + terminal*y`、实际后继混合、有限深度向量事实递推和目标读出。实际事实进入 `FactMemory`，`snapshot` 复制成冻结策略包；新旧包先实际试验，再由外层选择采用。没有优化器或梯度更新。

本轮实验目标是验证数学规格中的第一阶算子，不是全规格上线。尚无快慢专家适应、自动语义学习、一般因果识别、最优试验分配或 SLEEP 参数巩固。

## 输入

`FactNet(dim, facts=2, beta=16, gamma=1)` 的张量维度可配置。当前 `encode` / `FactMemory` 便利封装仍使用二维观测 `[离散阶段, 数值字段]` 与可配置历史窗口；第一字段是类型，不跨类型平滑。这是本轮数值接口范围，不代表任意图像/文本已能直接输入。

`FactMemory.ingest(episode)` 读取实际回合：

```
episode = {id, steps: [
  {t, observation, action, contribution, terminal_fact, known,
   terminal, successor, legal_next}, ...
]}
```

贡献和终局通道按相同事实维度定义，`known` 表示组合贡献是否已观察。样本先由旧记忆预测，再存入；预测误差本版记录而未用于检索权重。每个新候选可通过 `memory.snapshot(goal, depth)` 创建，用 `policy.act(observation, previous_observations, legal_actions)` 行动。

`mean_successor=True` 仅是本轮故意错误的消融，不建议作为正常算法。`terminal_only=True` 也是诊断变体，忽略过程事实可能明显变差。

实际结果与限制见仓库 `experiments/v09r/factual_operator_probe_v205/RESULTS.md`。旧 V204 源码和证据未修改；本目录不是自动替换旧模型的正式后端。
