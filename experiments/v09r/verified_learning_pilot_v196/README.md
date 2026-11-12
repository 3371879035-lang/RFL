# V196 有真实采用判据的反馈学习小实验

**本轮已运行完成。** 四组 × 4 个既有种子 × 2 轮；旧大训练、旧实验和自动任务未重启。

先读 [结果与缺陷](D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009/experiments/v09r/verified_learning_pilot_v196/interpretation.md)。

本轮重点不是再做预测器，而是把真实失败分支试验、临时动作学习、教师实际测试、学生实际测试和持久采用连起来。出现了正、零和负结果：小型采用测试并不能可靠预测后续独立报告，F0 仍未解决。

- [事前范围/预算](D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009/experiments/v09r/verified_learning_pilot_v196/contract.json)
- [完整原始汇总](D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009/experiments/v09r/verified_learning_pilot_v196/evidence/summary.json)
- [结果核对与逐种子对比](D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009/experiments/v09r/verified_learning_pilot_v196/analysis/result.json)

原生源代码已在执行前提交；本目录执行记录不覆盖。需要新实验时另立新版本，不重复运行本目录的独占 launcher。
