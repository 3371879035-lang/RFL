# V216 神经网络模型：条件证据持续性层

2026-11-11；先于源码保存。

复用V215的`DecisionSeparatedNet`及固定效用读出，只替换条件适用性门控。新增`PersistenceGate`和`PersistenceFeedbackNet`。

每个公开分组格保存：

* log_sources[cell, rate, source]：该速率下的H/F权重；
* log_rates[cell, rate]：该格的速率解释权重；
* log_partitions[group]：原条件划分权重；
* visits[cell]：真实事实次数。

Linear/ReLU公开条件编码不变。source softmax -> 再开放 -> H/F einsum -> rate softmax混合 -> group softmax混合 -> 原V215效用读出。三个softmax都来自真实预序贯更新，不使用场景类别、真值原因或变化时刻。

新输出为当前条件下的速率混合权重与加权平均速率，明确标为预测持续性诊断，不标为真实环境变化概率。原预测、历史份额、H/F、动作效用、预计margin和事实接口保留。

R=1、gamma=.02时应退化为原门控；R=1、gamma=0为消融；R=4为新模型。神经Parameters解析固定，无随机初始化、梯度优化器或SLEEP巩固。新增的是有限统计假设状态和计算量，不假称没有成本。

输入事实->门控用旧预测更新->F计数一次的顺序不变，历史不删除，评估不学习。公式层的标量复算和R=1退化检查先于有限环境执行。这个模型仍没有完成多因素因果归因、概率校准或连续高维编码。
