# V0.6 v172：概率事实、五组学习与冻结评估

本目录按`../plan_v171.json`实现。此文件在首次native之前固定，实际状态和结论另写`result.md`，不得把本文件当成已运行结果。

- 新stdlib kernel与三种真实学习类型：FactualLearner、DirectQLearner、HybridQLearner。五组由这三种学习路径及两个reward通道组成，不导入旧RFL运行时、Q*或checkpoint。
- Observation只含uid、实际步骤和任务可见terminal。随机数、真门、概率、seed、失败原因与role/cost均由外层保留；奖励仅经RewardPacket进入四个Q组。
- ProbabilityModel接纳同一命令的成功与碰撞，维护两个计数；F0按Beta(1,1)平滑概率规划，混合组做预定顺序的模型期望Q备份。模型先验不是新真实观测。
- 训练64回合连续、epsilon=.1；e=0/16/32/48/64全量clone、greedy评估，不更新训练或冻结状态。FrozenPolicy没有learn入口；评估结果只在外层记录，不参与训练/停止。
- PRNG用`random.Random('V172|seed|mirror|phase')`，三个独立phase为train_env/train_action/eval_env。8个(seed,mirror)区块在首个矩阵回合前全部物化，原生`.random()`共5376次；路径只索引，不临时补抽。独立存储审阅会重建同一随机带，属于核对而非新环境采样，另行计数。
- wiring20回合只使用批准的固定外生数值，前2训练/后2冻结评估；它不是总体样本。matrix80流/5120训练/6600评估，按计划不增样本。
- 600秒/128MiB总预算事前分配为wiring30秒/4MiB、matrix570秒/124MiB，原生上限分别20/11720回合。第一次错误/partial原样保存，不覆盖已有目录或自动重试。
- `audit_stored.py`只读新证据，独立重建物理、随机带、模型/Q更新、own-real回放、冻结/训练隔离、曲线与计数；不导入实验代码，不重跑旧checker或native。
- `analyze_stored.py`只读实际证据，报告每seed成对差值、在线与冻结曲线、全部成本、null/回退；不把32个银行回合当独立seed，不做总体PASS/等效声称。
- 预先保留一个测量诊断：固定32回合银行的偶然失败可能使最优策略的观测成功率也低于0.6561。只从已存外生坐标计算该银行的经验上界，另列“阈值在本银行不可达”标记，不改原阈值、不补0、不换随机带或加回合。这不是学习特征或新的主要效果指标。

预定执行入口（在此目录，以Python `-X utf8 -B`）：

```text
experiment.py --phase wiring --output evidence_wiring
audit_stored.py evidence_wiring
experiment.py --phase matrix --output evidence_matrix
audit_stored.py evidence_matrix
analyze_stored.py
```

动作/控制映射全程只读。运行时issued identity门禁与冻结clone检查由真实调用支撑，存储审阅不假称从JSON重建对象身份；团队内部核对不是独立专家或sciencegate。
