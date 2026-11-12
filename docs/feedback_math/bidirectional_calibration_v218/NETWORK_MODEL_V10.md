# V218 神经网络模型（先于源码）

新建IdentityCalibrationHead与BidirectionalFeedbackNet。基座使用完整V216，不采用V217单向收缩。公共ContextLift接收(x,a)；网络用乘法基函数产生五种有界预测，先验softmax与事实log似然比生成条件/分组权重，最后用p+A v+B u及原效用读出执行。

* nn.Parameter：prior_logits[group,map]，初值log(.5,.125,.125,.125,.125)或温度形三项。计算上使用与固定base_prior相加的零残差参数，以支持未来训练。
* buffers：log_ratio[cell,map]、visits[cell]、固定分组先验/编码、固定基函数方向。
* 真实事件顺序：保存基座/校准行动前预测→执行行动→原API验证并让基座同一事实普通学习一次→校准层使用缓存的行动前预测记一次likelihood ratio（不重新预测）。评估不observe。
* 输出同时保留base_prediction、calibration_coefficients[A,B]、map_weights及模型内分歧。不可把历史份额或校准权重当原因概率。
* 网络整体可微预测NLL连接到80个先验参数；有限差分/非零梯度检查，不做optimizer。现阶段输入与输出为有限类别/二元结果，非完整多步/高维通用模型。
* 原方法的真实历史及当前事实身份保留；重复导入幂等，重复observe拒绝，replay只读。新代码不修改旧基座。

恒等起点必须检查逐位原样，而不只测试宽松接近；合法概率、双向修正、全局排序保持、条件分别升降、似然因子一次、独立标量、评估只读及参数接口均为本轮针对性检查。
