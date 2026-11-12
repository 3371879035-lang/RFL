# V0.7 / v174 执行入口

本目录实现已批准的 `../plan_v173.json`。此前方案的“尚未运行”为制定时点，实际状态只看本目录新产生的exit、audit、analysis及结果，不改旧文件。

- 五条基准学习/环境/ownership组件直接复用冻结的V172源文件，但不调用旧main、旧run_wiring/run_matrix或旧checker。新TieHybrid仅覆盖初始化元数据、snapshot、policy；普通TD/回放/模型更新方法继承原函数。
- 新Recorder逐条保留完整raw/原因审计/实际更新/状态，使用gzip level1流式压缩。源、seed、环境配置只记录在外层；学习器仍只获得PublicTask及自己的Observation/RewardPacket。
- 九组按32个新seed、两镜像、p=0/.10连续训练64回合。各点0/8/16/32/48/64冻结；p=.10每点512实际评估，p=0每点1次。没有按结果加样本或调参。
- 只对四条新增读出做16回合真实定向接线，不重跑旧五组已完成接线。首次运行目录独占创建；失败/partial/超时保留，不自动重试。
- 新stdlib存储核对独立重建每个物理转移、每次TD/回放/模型备份、Q/事实/历史、三个读出、访问机制、冻结评估和计数；不导入native，不从JSON恢复runtime身份，不冒称独立专家或sciencegate。
- 所有评估结果和精确环境概率只用于外部分析。只读shadow建议不是额外试验、训练轨迹或新样本。seed块配对bootstrap另行记录分析RNG，不属于native经验。
- 时间为instrumented harness，Windows工作集在native循环完成时采样，峰值字段不含随后结果序列化阶段；不是生产性能排名或Python traced heap。

在本目录使用本地Python（UTF-8、-B）依次运行：

1. `experiment.py --phase wiring --output evidence_wiring`
2. `audit_stored.py evidence_wiring`
3. `experiment.py --phase matrix --output evidence_matrix`
4. `audit_stored.py evidence_matrix`
5. `analyze_stored.py`

上述命令各只首次执行一次。实际原始捕获为各evidence目录中的raw.jsonl.gz。阶段结论接受正、零、负，不以显著或终点胜出作为完成条件。无需旧正式400/200采集、付费算力或自动任务。
