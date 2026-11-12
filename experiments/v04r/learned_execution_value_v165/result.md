# V0.4 v165：学到执行调查的边际价值，省掉两次无额外收益试验

## 本轮交付

新增 `ExecutionQueryAgent`：在实际主任务普通TD之后，由历史真实后续收益预测是否还值得支付执行纠错keep/first菜单。不是给保护性动作写“免调查”规则，也不是预算剩多少就花多少。

三种新完整来源，每种各3个独立fullR+L/I角色连续6任务；表中合计18主任务，**不是同一个18回合连续agent或18个独立seed**。

|组|主任务成功|额外试验|总环境回合|K步|非共享TX|公共推演|
|---|---:|---:|---:|---:|---:|---:|
|只普通学习|5/18|0|18|116|36|0|
|已有事件价值筛选，执行菜单照常调查|14/18|7|25|147|62|3|
|事件+新增执行价值筛选|14/18|**5**|**23**|**139**|**55**|3|

共享checkpoint3TX、3个新来源各1TX（edits4/4/14共22）另计。普通TD/visited-D学习所有role都开启；原共同Q*、alpha1/2、epsilon1/10、完整R+L/保护I保留。无额外处罚。

## 三个实际判断

### A：保留有收益的复合纠错

新来源k0phi3中，D_START=WAIT、X_WAIT→RIGHT使首次主任务TRAP，另一未被该factual咨询的X_UP→RIGHT造成后续复合问题。模型看到(first mismatched-command TD delta=−.94, visible mismatch sites=1)，预测每付一次试验后续增益约1.253333，仍实际跑keep/first/joint三试验，真实失败first揭示第二位置，再由原一次原子TX删除两处映射。

两个反馈组都是4/6成功；普通组0/6。失败与当前路径reuse/对照均完整保留，不把单删第一处的−1.06掩盖成改善。

### P：普通学习已经改善，跳过冗余执行调查

新保护来源也是k0phi3，但source中RIGHT→WAIT避免t0trap，后续另一个D动作造成首次COLLISION。普通TD已经修好后续D策略。新模型输入(−.010000000000000009,1)，预测额外未来收益0，直接keep，不新建私有来源、不诊断写入；三组此来源都5/6成功。

原执行菜单组仍跑两试验：keepSUCCESS+.86、删除保护映射TRAP−1.02，最终同样keep。新增门控省掉两试验/8K步/7TX，后续主任务回报逐项相同。local epoch1真正强制RIGHT挑战仍实际执行为WAIT，保护性X与I都没有误删。

### W：新型反复等待不被误当零收益

新来源k0phi0声明12个不同时间的START-X_RIGHT→WAIT。首次TIMEOUT，模型第一TD变化与P相同，但实际可见不同偏离位置数12超出训练支持1；输出**None/unknown**，而不是0，预算内实际比较keep与first。

keep真实TIMEOUT−1.24，删除第一处映射真实SUCCESS+.88。两个反馈组各只删除t0实际偏离的一处，其他11处原值保留，不叫12份新知识；后五主任务全成功，各5/6。普通组6次TIMEOUT，0/6。

这里普通TD按声明不改controller通道；在RIGHT都被映成WAIT时，Q/D学习无法让动作真正离开起点，反馈有合法controller修正空间。这是指定写空间下的条件性收益，不是“一般强化学习做不到”或通用算法优越。

**未知情况仍然行动试验**。W上的正确行为来自已有unknown→budgeted test规则，不是声称模型已学准这类新失败的收益，更没有执行一个first-feature-only消融来证明其失败。

## 训练数据和真实边界

从v164已封存记录只读使用PolicyUnified全部2个实际执行问题（e0/e16），与同轮TaskTD比较。首次factual raw、同activecontext D/P/X/Q及普通L之前状态精确对应；其他情境因先前修正而不同，未假称完整R相同。标签固定为其后3个主任务原始回报和增量/实际全部私有回合数：3.76/3≈1.253333与0/2=0。Policy32+TaskTD26共58个历史已付交互，只读复用不等免费样本或新科学N。

闭合 `ExecutionFeatureData` 仅含真实可见prefix、actor自己的普通L_before/L_after。输入两数是首个偏离命令的实际TD内容变化和不同可见偏离位置数量。SSE树由这两真实标签拟合，首个新K前冻结，不读情境名、角色、mask、真值、成本/责任账本或未来结果作特征；外层原mask参数仅原样转交native执行器。特征和问题语法仍为人工给定，不是自动发现表征/世界模型。

训练只有两点，不能推出阈值普遍可靠。执行标签窗口3主任务、原事件模型窗口5主任务，**两种预测值不作统一跨分支数值排序/总体预算最优比较**。本轮只按正/零/未知决定是否进入原真实调查。

简单同价累加主任务+试验原始回报：普通−10.32，已有事件门控6.06，双门控6.22；全部交互失败次数13/8/7。这个描述口径也改善，但未采用新的全局成本价格/权重/family。成功试验仍会正常学习，成功主任务不新增归因诊断。

## 原生执行与产物

首次native0，instrumented4.219秒；首次新stdlib stored review0，约.469秒。总66 rollout/402 step/159TX，另6公共推演、1次新执行树fit、5次执行特征计算（2训练+3在线），事件模型fit0。545完整canonical记录，360输入native前后相同。全部raw movement/terminal/reward/坐标、原chronological binary64 TD、D改进、whole atomic写、严格源/当前机制/once、模型拟合/构造/门控/保护/预算按存储字节核对；内部审阅不是独立专家/sciencegate。

每份私有observation实际新签发并执行；A/P/W共6/2/4份都一次消费，符合当前机制者才进入消费者ordinaryTD，失配者保留并拒绝迁移。完整I/R+L、原哨兵/未读值保留；不从历史JSON恢复issued对象，不复制私有训练L。354复用完整文件17,362,016字节与父Git/nativepins同、原313 manifest SHA同；不是全13GB审计。

原v164“门控省事件试验却多做保护菜单”的不利成本结果永久保留，不重跑或改成这轮结果。所有旧失败/partial/零/不利/266prov保留。无新keys/RNG/keyderive/DP/calibration/正式collector/确认采集/自动安排。

[机器结果](result.json) · [新存储审阅](stored_audit_result.json) · [首次native](evidence/exit.json) · [精确绑定](source_binding.json) · [接口说明](README.md)。本轮闭合执行调查边际价值的新接口与三个新来源有限验证，不冒充新双门控已做完整连续26流、全域资格或整个V0.4已完成；旧fixture/checker/native/bank不重跑。
