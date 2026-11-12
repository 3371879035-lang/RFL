# V0.8当前状态

**已完成固定矩阵与分析。** V175方案的历史“尚未执行”文字保留原样，当前事实以V176为准。

- 结论与具体缺陷：[V176解释](harder_decisions_v176/result_interpretation.md)
- 九组完整结果：[结果表](harder_decisions_v176/result.md)
- 机器可读分析：[analysis.json](harder_decisions_v176/analysis.json)
- 实现、原始捕获与成本入口：[执行说明](harder_decisions_v176/README.md)
- 原方案：[V175](README.md)

9组×32独立训练seed×2镜像×3地图，1728流；每流256训练、7点各512冻结评估。含新接线共6635556真实回合、23702368步。native接线/矩阵首次0、新存储审阅两次首次0、分析首次完成，无native失败/partial/retry。

6步与10步分叉任务中，新F-R-M1相对旧FT的预定早期相对AUC差为+.09259、+.03301；共同训练步预算下也交付更多成功。6步图相对CT有正增量，10步图相对CT的早期区间仍跨0。不是所有seed或所有指标都赢。

M1确实能改变旧Q不平局时的实际选择，也会因有限事实与后继Q误改。纯反馈不普遍早于纯RL；有/无处罚继续保留并显示条件性差异。旧阶段不重跑、不继承旧科学PASS，没有恢复automation或启动下一阶段。
