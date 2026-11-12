# V0.4 v157：非法终点陷阱导致实验配置失败，完整保留

首次native退出1，不是算法通过，也不改为科学方向失败。第三场景在GOAL安装NativeTrap违反原kernel.py:443明确规则，ValueError发生在构造该mask、进入其首个主任务之前。这是实验设计错误，不是模型归因/学习失败。所有已执行源码、contract和capture原样冻结，不修不重跑。

此前TaskTD在两个合法场景已经完成12个主任务、12个原ordinaryTD和12个POST记录；实际9成功/3TRAP，e0/e2/e6失败。总12rollout/73Kstep/15TX=3checkpoint物化+12普通数值事务，无visited-D事务/来源安装/诊断/私有试验/外部观察/反馈写入。完整78canonical记录、输入before/after同、finally恢复profile；TaskTD原计划18未完成、无AGENT_FINAL，不能说整臂完成。GreedyPractice与TargetedPractice均未开始。

此处仅metadata与完整JSON解析核对，预写的v157 stored auditor未执行（它针对完整成功设计）。后续单独新版本应只执行尚未开始的两个策略和合法两场景，并对这12个完整baseline回合做新的只读stdlib审阅；不得重跑这12回合、不另换场景追非零效应、不反造旧运行时来源身份。坏C场景未产生任务，不用0结果替代。

原313和旧执行证据不改。无keys/RNG/keyderive/DP/calibration/collector/正式采集或automation变更。
