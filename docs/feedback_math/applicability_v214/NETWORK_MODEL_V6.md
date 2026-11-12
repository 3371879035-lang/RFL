# V214：情境适用性神经模型

本文件先于源码保存。不是“历史给网络补正确答案”，而是两类预测源和条件适用性假设共同接受新结果检验。

* `RelationPredictor(nn.Module)`：完整公开关系子集的V210条件模型、结构softmax权重。原Linear/ReLU参数保持解析固定；实际事实只更新计数和假设状态。
* `ContextLift(nn.Module)`：one-hot公开字段→每个候选分组G的联合条件ReLU激活，包含空组。所有分组枚举，不向网络泄漏真实相关字段。
* `ApplicabilityGate(nn.Module)`：格内H/F的softmax、分组softmax、加权einsum；输出当前输入的历史份额lambda及结果分布p。动态权重是显式在线状态，不冒称已训练Transformer或已实现因果发现。
* `HistoricalFeedbackNet(nn.Module)`：保存原始历史、冻结H、当前F、门控、实际动作分布。一次`offer`记录预测/动作倾向，实际`Fact`匹配后才能更新。顺序固定为门控用旧H/F预测学习→F接收一次事实。评估不更新。

统一对照接口包含pooled/fresh/temporal/global_gate/conditional_gate；旧V210模块字节不修改。两门控组的H、F、初始化、gamma和动作预算相同，唯一主要区别是是否允许情境格。

历史事实不删，低门控权重不等于旧事实错误。输出显示未见完整组合、关系投影支持和两来源分歧；这些是诊断，不用人工阈值偷偷替模型挑正确动作。新组合允许通过低阶关系迁移，也可能受误导，必须用双世界和局部失效任务检验。

没有梯度优化器、模拟标签、LLM归因器、旧残差相加或自动永久采用。本轮实际学习发生在有限实验内；SLEEP/长期参数巩固不在本次通过范围。
