# V217 网络模型（先于实现）

保留V215的效用读出、公共ContextLift、H/F容量和epsilon=.2；新建SharedEvidenceGate与PriorUncertaintyNet，不修改旧源码。

* NeuralPrior：可训练theta[group,rate,reliability]，解析零初始化，无随机初始化；softmax生成先验。
* 事实状态：log_sources[cell,rate,reliability,source]、log_likelihood[cell,rate,reliability]、visits[cell]，均为buffer。来源预测->均匀收缩->来源混合->局部或共享证据归一化->分组混合->原效用读出。
* observe只接一次实际事实；source更新和log_likelihood使用同一份行动前缓存；不另存反复相乘的分组posterior。
* 额外输出：速率/可靠性权重、within/between不确定性；均非真实原因概率。
* 历史按稳定id规范化；重放已记录事实不改变权重、计数和访问数。完整checkpoint需保存archive身份，不能仅凭state_dict重建事实账本。
* forward保留prior参数梯度，predictive_loss支持后续支持/查询训练。此轮检查非零有限梯度和有限差分一致，不运行优化器；参数hash必须前后同。

实验：原V216局部无收缩记录为reference；新增共享无收缩、局部可靠性混合、共享可靠性混合三臂，区分两个改动的作用。概率退化、方差恒等式、累计似然只计一次、重复导入/重放、参数与状态分离均在首轮有限检查覆盖，不用检查通过冒充科学效果。
