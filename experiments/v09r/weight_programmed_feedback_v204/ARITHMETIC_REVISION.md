# 存储复核的实际浮点表示修正

首次 `analyze_stored.py` 执行 exit 1，原源码/日志/回执全部保留。报错在 trial kernel 权重复核：用 float64 的直接欧氏距离替代 native 的 float32 Q/K 范数展开，某条权重相差约 0.00005167，超过事前 0.00005 的绝对误差限。这个断点是比较了不同的数值程序，不能改成首次通过。

新文件 `analyze_stored_float32.py` 不放宽原误差限，而是读取同一实际检查点的 Q/K 矩阵，用明确的 float32 张量乘法、完整零 action 列及相同截断/指数规则重算 kernel；仍独立重建世界观测、原始实际结果、先前记录预测误差、采纳路由、时序与成本。float64 几何距离作为旁列差异诊断继续保留，不把它强称为位相同程序。

这不是修改模型或重跑实验。新复核不调用 learner/task 类；所有源文件、检查点、capture 和第一次失败永久保留。最终输出另存 `stored_review_float32.json` 与 `review_float32_exit.json`。复核仍不独立重演每一轮多步神经 forward，不是科学资格认证。
