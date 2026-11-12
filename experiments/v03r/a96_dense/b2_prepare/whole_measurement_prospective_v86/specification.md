# V0.3R 整组测量与未来学习候选规范

状态：供前瞻审阅的技术契约，未采用、未冻结、未执行。原 F1、生产源码、科学总体和最终判定规则不变。

当前主线仍是完整真实 Oracle credit 经合法 persistent update law 写入同一个写前状态，再检验这个更新的即时损失与未来学习。原 B1 能执行整组一次事务，但原 B2 的单位置测量入口不能自动承担整组科学结论。下面把这项扩展落实为可实现的数据契约、计算顺序、拒绝条件和资源清单；不把必要的科学决定伪装为已完成的工程检查。

## 原约束与候选扩展

A75 §62.1、§62.8、§62.9要求保留全部真实 manifestations，分别处理 T 和 P，并在独立安装的同 extensional DQ 与 literal patch 上使用公平的 context 预算和完整 k 与 shape family 及交互报告。A76 §63.10 与 A77 §65.9要求同一个 pre、整组一次事务和所有 owner 回执；同 tier NoWrite 不变。A79 §67.4要求场景在写入前构造，不能由治疗效果决定。A96仍使用已锁定的每整数回合网格、六门禁、正式 primary400 和 secondary200，以及完整最终 conjunction。

A89定义的是单位置 E(c)。本规范建议对非空完整 owner 集合 S 使用所有 E(c) 的交集，这仍是新的候选科学规则，不是原 A89 的既有授权。v23、v27的具体总体、权重、delta_joint、394项 family、固定注入和逐 instance SD95%规则均不因此生效。也不新增普通诊断算法比赛。

## 完整来源与 owner 契约

每个来源保留完整 factual raw、原配置、全部四 store、参考对象、Gamma 的 evaluator-only 来历、所有 manifestation 到 owner 的原映射，以及不属于当前架构的 residual。P不借 transient/do，T不借 P的 optimality 筛选。

S是当前架构的完整、确定顺序、去重后的 typed owner tuple，在任何 arm 开始前签定。映射前的 manifestations 不因 owner 去重而消失。Decision owner 仍是完整 DecisionAddress，而不是每个 Q scalar；Controller owner 仍含发出的 command；Process owner 仍是原 proposal。literal patch 使用自己的完整写前行为，不得借 Q-only CfEpisode 或冒充原 unaffected 的 D_Q handle。

APPLIED、EVALUABLE_NOOP、NO_VALID_ALTERNATIVE全部保留；S不能由实际 WriteSet、回执状态或最终 override 数反推。空投影、源成功、无 reflection、异常、partial、空 Collateral 区域是不同状态。完整 family 中这些状态如何影响推断分母须前瞻规定，不能补0、删场景或当成科学停止。

## 整组 Collateral 候选

令 U2 为原5760个严格 EvaluationScene，按 kappa、phase、e、r、base_option 的原字典序排列。用当前架构完整 W_pre 做 ordinary、无 transient、无 optionfault、无 do 的写前回放，定义 H_pre(u) 为实际 SUCCESS。

对每个 c∈S，Consult_pre(u,c) 使用原 A89 的真实 pre-step state、实际 option_in_force 和控制更新。Decision不看 scalar action 索引；Controller看 a_cmd而非 realized output；Process看 proposal而非提交后的 option。不得用静态安装数、未读 sentinel、mask配置或预测健康路径代替实际 consultation。

候选区域为：

    C(W_pre,S) = {u∈U2 : H_pre(u) and not any Consult_pre(u,c), c∈S}

它等于各原 E(c) 的交集。区域只依赖完整 pre、sanitized S和原 scene；不知道 arm、law、tier、Gamma标签、k、shape、ledger或 post outcome。它在所有 arms 前构造，两个 arms共享同一个严格 tuple对象及同一 pre map。不得借两个内容相同的 caller对象代替实际 shared身份。

C必须非空、proper、严格类型、无重复、原顺序。失去任一性质即保留完整反例，阻断候选仪器的资格；不取first、不删owner、不改成并集、不降级到逐地址平均或补0。这个阻断本身不是原机制反证，也不是当前冻结协议 scientificSTOP。可检查的结构压缩必须保留每个 full-pre world 的身份与原测度，不能因为行为相同就悄悄缩总体。

Collateral只测即时 B1 后的状态，不测已训练状态。对 arm a，使用原左到右分别求均值的算术：

    B_a = mean_ordered(V_pre[u], u∈C)
          - mean_ordered(V_immediate_post_a[u], u∈C)
    d_B = B_NoWrite - B_treatment

正 d_B 表示治疗的损失较低。这是候选方向约定，不是新的资格阈值。不得把两次mean改成mean(pre-post)、fsum、epsilon消零或absolute loss；有符号0和负值保留。每地址图可描述同一次整组写入，但不是单独因果效应，也不进入主标量聚合。

## 原子执行与完整输出

候选 whole runner 不修改原 singleton runner 的 guard，也不伪造单位置 ledger。未来独立 addon需要专属 owned record，其接口只消费实际 issued source和completepair；serialized seal只能验证内容，不重建运行时对象身份。

执行顺序固定为：

1. 认证来源、full pre、全部 owner/residual、原 law及同 tier NoWrite。对 cell签一次性 reservation。
2. 用该 full pre完成全部 U2写前 raw，再签定 C和一个 shared pre map。区域无资格时保存证据并停止该候选执行，不启动 arm或未来学习。
3. 对两臂分别从同一 full pre独立 clone，每臂调用原 entrypoint一次，整组针对同 pre plan，再执行原事务语义。空 plan不强造 transaction。
4. 保存原 plan、每 owner原 receipt、全部 full post和实际 scalar accounting；不按 APPLIED过滤。
5. 在各自完整即时 post上测共享 C的完整 ordered raw/post map。immediate post在整个未来训练期间保持不变。
6. 为两臂创建不同身份的完整 future start clone，绑定同一原 keyed protocol。只有训练架构契约已经闭合时才可进入学习。
7. 保存每实际训练回合的完整配置、pre/post fullstore、raw、TD edits、每 checkpoint全部100场景和有序mean；完整 EOF与native exit之后才签 complete record和发布 ordered index。

reservation在首次 native前消耗；失败、partial或不完整bank不签完成句柄，不自动 retry、重发相同 cell或重造future绕过一次性限制。observer只观察原调用一次及原 return同对象；异常原样传播，finally恢复原函数与 alias。不得用 callback、caller状态或 serialized fakehandle绕过所有权。

## 未来训练的源码缺口

这是静态源码诊断，没有新运行时实验，也不是科学 FAIL：

- training.py 350到364行的训练 greedy直接调用 snapshot.q_decision_provider；非探索分支没有 decision_provider wrapper。
- environment.py 68到97行的 ordinary评估通过 decision_provider(q_decision_provider)读取 literal patch，P和X也来自完整 snapshot。
- 因此，合法非空D、空Q的patch状态在普通评估与训练 exploitation上使用不同决策读路。v85验证的是前者，不能替后者给出资格。
- training.py 411到444及489到493行的 sweep只写Q。若某次Q写入经过原canonical后仍非空，且D仍非空，则下一次构造评估或训练provider时会遇到 store.py 254到272、320到344行正确保留的D/Q互斥guard。不能声称每次episode必然产生这种Q，也不能把这项条件推断称为已发生的native失败。

只给训练加patch wrapper不能闭合第二项写入问题。删除D、强设healthy、把literal patch转成Q、松互斥guard、指定新优先级或把某架构排除，都会改变原架构、对照或研究范围；不能作为无声修复。

正式学习前必须有明确的训练架构契约，逐架构说明动作读路、探索时patch是否可覆盖、TD目标与write store、ordinary evaluation读路、非owner声明保留和D/Q互斥如何同时满足。若需要独立基础学习状态或新后端，应写明它与原A91四store/immutability的关系、同extensional公平预算以及对六门禁和F1资格的影响，然后取得对应的前瞻范围。当前不选新机制、不实施生产修复、不启动训练。

## 仪器资格与完整统计

整组资格需要覆盖正式冻结的真实生产域 (architecture,W_pre,S)，而不是任意Python对象或只覆盖几个fixture。结构证书需给出完整声明域、合法性、原抽样测度、条件质量、owner映射、所有C的性质和反例搜索边界。无法给出完整证书时保留未知，不删高k、困难world、空质量cell、未读sentinel或不利交互。

新 ruler的校准契约必须先说明覆盖域、合法组外注入、独立完整区域预测、场景/浮点顺序和拒绝策略，之后才测量。原固定singleton canaries与F1的0.04146752410689062不能直接证明整组资格。v27所有region固定首注入必须非零及逐instance SD95%是未采用方案；其已有反例不能改址追非零，也不自动成为所有可能实现的原规范前提。

本候选不指定delta_joint数值，不选择新的weights或Holm清单。科学采用前须具体绑定阈值来源及完整family和终点conjunction，并解释原Retention及Utility资格是否因新增架构训练而需要独立闭合；不能仅凭单位置F1复用资格。原RMST1.5只为数量benchmark，T的inclusive lowerCI>=-1.5约束独立；不宣称实用等效或零伤害。

推断单位仍是独立paired seed。episode、场景、地址、owner、receipt和cell均不是新增N。primary400四个100块与secondary200两个100块不互相升级；早期块仅诊断，原最终look、mean/median/trim/sign/Wilcoxon/bootstrap/Holm/top5及完整Utility/Collateral/Retention/T合取不撤。

## 可展开的密集资源清单

下列仅为原训练循环的结构算术，不是实际耗时、磁盘、内存或完整工作负载证书。已锁T465、G为0到465共466点、N_eval100。

单个完整训练角色需465训练rollout加46600评估rollout，共47065。一个两臂cell未来部分需94130。若每个cell按原runner分别执行5760 pre eligibility census、n个shared pre测量和两臂各n个immediate post测量，则：

    R_pair(n) = 5760 + 3*n + 94130 = 99890 + 3*n
    1 <= n <= 5759
    R_pair_max = 117167
    kernel_step_upper_pair = 12 * 117167 = 1406004

单cell400 seeds仅future部分37652000 rollout，200 seeds为18826000；不是正式全研究工作量。每个真正新增训练role额外47065，alias/local/global ceiling不能伪造成独立重复治疗。以上不包括来源factual、CF builder及原validators的真实回放、装入与B1、校准、门禁、额外ceiling、统计、fullstore序列化和IO。

最终预算必须先展开每个seed的全部registered cells和实际role，按独立DQ/patch自己的pre及区域计数，另列所有上述成本与最大raw/store体积。可共享的只读测量须在执行前证明合法绑定和相同对象/顺序；不按观测结果缓存测量或只计一次多个不同角色。

完整certificate须绑定 exactextent、source inventory、fresh工程key域、worker上限、每seed串行chronology、串行mutation、磁盘/内存/时间上界、abortbound、partial保存和完整native receipts。旧F1 baseline timing与v85的600普通回合不是证书。最多16 workers仅跨独立seed/分片，不并发同seed或mutation gate。

## 前瞻闭合和权限

依赖不是重复增加状态演示，而是以下具体交付物：

- 完整k与shape生产registry、原测度及公平family/interaction，和整组C的总域资格。
- 逐架构完整训练读写契约，解决上述patch训练缺口，保留独立架构和所有原对照。
- ruler校准与阈值来源的明确候选、完整终点family及最终conjunction；科学采用需要具体前瞻范围。
- 绑定前述全部工作量的addon inventory、原全T/P/mixed/tier/error/empty/status/receipt/source/measurement门禁和资源certificate。
- 互斥fresh工程/science registry、source-bound review、完整本地预注册manifest与一次性collection gate；分配keys和启动collector需要明确授权。

候选ALL历史校准仍有153792 pending unique、125366旧refs、initialsetup/targeted26缺失的runtime/fullstore/raw，以及114714、114716、114718、114720四个postnativefullstore兼容未决。ALL闭合前不执行新nativecalibration；这条候选路线的历史对账不能变成所有独立技术接口的普遍前提。

当前collection关闭、科学UNEVALUATED、研究未完成，无有效原机制反证，非scientificSTOP。已完成v85有限链、v84纯检查、v83失败及全部旧fixture/checker/native永久保留，不重跑以增加PASS。

## 来源绑定与验证范围

当前父提交为4b0e66d09f6fd89f78d1037a805db14a4a95c80e。原条款以docs/rebuild/12-AMENDMENTS.md的A75、A76、A77、A79、A89、A91及A96为准；34-A96-DENSE-MEASUREMENT.md和05-STATISTICAL-PROTOCOL.md保留原测量及统计约束。contract.json记录具体字段、数据流门禁与未采用状态；source_review.json绑定源码SHA及静态finding。

本轮没有导入或执行RFL、旧checker、native fixture、DP、科学统计或RNG，没有分配keys、构造FutureTrainingProtocol/Curve或启动训练/collector。新的文档与JSON结构/源码只读核对属于实现层审阅，不是独立专家或科学PASS。

