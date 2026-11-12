# V0.3R 正式机制验证方案

状态：完整前瞻提案，供审阅；尚未采用、冻结、实现或启动采集。日期：2026-10-11（Asia/Shanghai）。父提交：`5f81c62ac0ce6328be074a3c378574b0ab2edfc6`。

## 要回答的问题

本研究要回答的是：**已知真实责任位置以后，一次合法的持久更新，能否让同一个学习者以后恢复得更快、效果保持得更久，同时不过度损伤原本正常的行为？** 不要求加入普通诊断算法比赛，也不以“当场修好一次”代替后续学习效果。

正式判断有四道同时满足的条件：持续缺陷下的后续收益、无关正常行为的损伤界限、后期效果保持、瞬时事故下没有过度错误内化。任意一道不满足，都不能用另一项的好成绩补偿。

直接人类回复“可以的，你负责就好了”，承接的问题仅为“补齐正式验证方案供确认；不改原冻结源码和 F1、不分配种子、不启动采集、不自动批准新判定规则”。技术提案由代理负责；这不是采集授权。本文件及配套 JSON 是完整的设计建议，不是生效预注册。旧 v23、v24–v26、所有失败记录和原 313 项均保留。

## 现有证据到哪里为止

F1 已锁定测量轴：`q=387`、`T=465`、每整数回合 `0..465`、健康参考的有序场景数 `100`、LateWindowRetention 的窗口 `387..465`。原 cap576、C3 layer1 开发初始化、普通学习 `alpha=1/2`、探索 `epsilon=1/10`、master bank1024、K3 和 0.95 健康参考保持不变。它们的来源是本次 A96，不是旧 A95。

v24–v26 的确定性检查说明：在保存的几个构造案例里，原生更新能定位并改动相应持久条目，且保留未获责任的其他缺陷。其中包括多位置 Decision credit、两种 Decision 存储的独立安装，以及 Process/Controller 的局部修正。它们没有后续训练、没有独立科学样本，也没有证明总体收益或无损伤。本提案不重跑这些案例来增加 PASS 数量。

原规范允许一次事件的全部真实责任位置；现有 B1 支持同一 pre-state 的整组一次事务，原 B2 runner 仍要求一个位置。因此，完整集合的 Collateral 入口确有覆盖缺口；这不是已经发生的科学 FAIL、NO_ADMISSIBLE 或 STOP。

## 哪些继承，哪些是待批准提案

| 继承并保持 | 本文件提出、尚未生效 |
|---|---|
| Oracle credit 下的 persistent update-law；T/P 分开；保留全部真实 manifestations | 具体持续缺陷抽样族、数量与形态权重 |
| 原生 B1 的合法 law/tier、owner 局部性、同 pre-state 原子事务 | 冻结清单外的完整 credit B2 记录与入口 |
| 原 F1 的 T465、dense grid、N_eval100、Retention 形式与原阈值记录 | 整组无关区域、整组 Collateral 新阈值的确定性来源 |
| seed 为推断单位；primary400、secondary200；同 tier CRN；最终 look | 具体完整检验 family、保持判据、空投影和退化检验约定 |
| 原门禁、完整工作负载认证、单次发布与中断保全 | 新 addon 必须另行授权实施、审查、冻结与采集 |

提案中的数值或规则不可写回原锁。原单点 Collateral 阈值 `0.04146752410689062` 不能直接批准新整组区域。原 Retention 阈值 `5.515977517224342e-05` 保留在原记录中；本提案建议如何用于已有形式的保持判断，而不是声称原锁已经规定这一判定。

## 1. 实验对象与总体

### 1.1 瞬时事故 T

初始持久学习者健康；事故仅来自原冻结 transient fault 语义。采用原 A62 的 scene DGP 和 canonical feasible support：kappa/option 的原均匀分布、SemanticTape 的原真实测度（包括 error_flag 的 0.4）、可用 cause 的 0.2 激活概率和 canonical 参数均匀分布。可行性条件在整个 world 上归一化，不能固定 context 后只重抽 fault。

首先按完整 pre-episode 的真实终止结果区分 SUCCESS 与 COLLISION/TRAP/TIMEOUT。SUCCESS 没有反思更新，普通 TD 不因此关闭。正式错误内化估计针对原生 failure-only 事件，保留全部可行失败 world，不以回报符号或是否能修好筛选。分别报告原 `S_T,+` 中 pure/mixed 和 `S_T,0` 三个条件总体及其原 DGP 质量，不计算跨三者的 whole-support 主均值。结构上质量为零的表仍报告，但没有未定义的条件均值；不得据此删掉其他正质量表。

给定 architecture 的可写投影为空，**不等于**全局 `S_T,0`：完整真实 Gamma 和其他渠道 credit 仍保留。该事件执行明确的 no-reflection/no-edit 分支；两份独立未来状态仍按相同原普通学习流程测量 Utility/Retention，不伪造效果 0。空 S 的 Collateral 是“不适用”，不是数值 0，也不进入非空 S 的 Collateral 主表。

### 1.2 持续缺陷 P：建议的受控科学族

P 的缺陷安装在 learner-owned persistent store，future 读取同一写后状态。无 transient mask、option fault 或 evaluator do 混入。安装数、实际 manifestation 数、唯一 owner 数、scalar edit 数分别记录，任何一个都不是统计 N。

以下是**新总体建议**，不是从旧 fixture 得出的原科学总体，也不批准排除原规范要求的其他真实 credit。研究结论只覆盖最终批准的这份有限族；不声称所有可能故障、真实世界发生频率或通用架构胜出。

Decision 的合法 context 池为原 `decision_contexts()` 中，存在至少一个合法且不在完整 optimal argmax 集中的动作的 context。没有通过“测试效果好”删选 context。每个 defect 是 k 个不同 context 与各自合法严格次优动作的集合。建议 k 为 `1,2,4,8`：

- `k=1 / singleton`：只有一个单点结构，不把“集中/分散”复制成两个重复单点。
- `k=2,4,8 / clustered`：所有 context 具有同一 `(kappa, phi, z, m)`，但完整 state 不同。
- `k=2,4,8 / distributed`：至少跨两个不同的 `(kappa, phi, z, m)` 组。

共七个 Decision cell，固定顺序为 singleton1、clustered2、distributed2、clustered4、distributed4、clustered8、distributed8。每 cell 对所有满足定义的 context 子集均匀，对各 context 的合法严格次优动作独立均匀。使用组合计数的 rank/unrank 与整数拒绝抽样，不靠 Python hash 或 float 累积 CDF 决定成员；空结构 cell 阻断设计，不用换 k 或 shape 获得可运行总体。

同一 extensional defect 在 D_Q 与 D_patch 独立安装并核对完整诱导策略。D_patch 写入动作 patch；D_Q 只将该次优动作项设为 `b+(b-q)`，其中 b 是该原参考 row 的最大值，q 是该动作原参考值；其他项不动。这个安装映射是提案，借用 C3 的明确数值构造，不运行开发初始化、不移动 layer、不改变 B1 full backup。两安装器只读取同一外部 defect 声明与各自的原健康参考，不读取对方安装结果。地址预算按 context 对齐，scalar 与幅度另外报告。

Controller 的建议族：从原合法 site 域中选 k 个不同 site（k=`1,2,4,8`）；每 site 的目标均匀取共同合法动作交集去掉 `a_cmd` 后的动作，保证所有原可触及 `(z,m)` 下合法。采用原 X admissibility 检查；没有合法替代动作的 site 不是 defect 候选。无额外 shape 主假设；不得把 Decision 的 shape 名字套给 X。

Process 的建议族：k=`1,2,3,4` 个不同 proposal key；每个 key 独立均匀映射至其他原合法 option。单个事件的 Process manifestation 仍只有 `ProcessCommit`，经原 rho_P 与允许的 AssistedInput 解析一个 owner；安装 k 个故障不制造 k 个事件责任位置。

每个生成的 defect state 先在完整 U2 上作原生只读 factual census，形成它的失败且真实 manifestation 非空的 trigger catalog。先抽 defect，再按原无 transient scene 测度在该 catalog 条件抽 trigger；不能按 trigger 数给 defect 额外权重。无任何合格 trigger 的 defect 仍在结构 census 中，报告其质量并称为 non-trigger world，不充作 P 更新样本。正式 P 估计明确条件于可触发的 defect 子总体；此条件化是本提案的新增总体决定，**必须审阅批准**，不自动缩减原范围。

一次 trigger 保留全部实际 Gamma_P，再按各原 rho 解析所有相关 owner。不要求 manifest 数等于安装 k；后者有意包含未触及故障。未触及条目不由局部修正顺手恢复。普通 TD 在后续成功/失败回合均保持原 A91 规则，Process/Controller/patch store 不被普通 Q 学习替换。

### 1.3 固定权重与 seed

每个 primary seed 覆盖全部七个 Decision cell 和四个 X cell，采用独立的预注册 cell stream，并对同一个 Decision defect 同时运行两种独立安装架构。secondary seed 同样覆盖全部 Decision cell 和四个 Process cell。每 cell 一个独立生成的 defect/trigger pair；同 seed 内是相关测量，统计分析前聚合。

Decision 的 family 估计按 k 等权：k1 权重 `1/4`；其余各 k 的两种 shape 各 `1/8`。X 与 Process 的四个 k 各 `1/4`。这是受控实验权重，不是真实世界流行率。全部 cell、逐 k、逐 shape、形态内与数量内变化均报告；不能在结果后改权重、去掉困难 cell 或用 APPLIED-only 子集。

T 每个正质量条件表用同一 seed 的单独 cell stream 抽一个完整 world，并在三种 primary architecture 下分别运行自己的合法 projection。各表不能被 P 或 T 的另一个表填补。有限 catalog 的条件抽样前必须冻结质量、成员 extent、权重、canonical order 与 SHA；抽不到合格事件不换 seed、不自适应追加尝试。

环境 seed 是完整独立 run 的 key。primary400=`4×100`；secondary200=`2×100`，与工程 key、所有旧种子/预约严格互斥。本文件不列出、不预约任何实际 key。未来 cell 生成使用新的独立 namespace 与显式 `(seed, regime, cell, purpose, counter)` 派生；原 A91 `ExogenousEpisode.derive(seed,e)` 不改。两臂以及同 seed 各 cell 的 future 共享原 episode-coordinate CRN；不能因轨迹长度改变 variate 对齐。analysis RNG960031 只供统计重抽样，不作环境 key。

cell 抽样器提案采用 SHA256 digest 按 big-endian 解释的无符号256位整数 variate：输入为 compact ASCII JSON 数组 `["a96-v27-population-v1",seed,regime,cell,purpose,draw_index,rejection_counter]` 加终止换行，拒绝 bool/float seed。均匀 rank M 用 `limit=2^256-(2^256 % M)`，接受首个整数 v<limit，再取 v%M；最多 `2^32` 次拒绝，M>2^256 或耗尽即操作协议错误，不取 modulo 偏差、不换 key。整数概率权重先通分约分，抽累计权重区间；按完整 canonical world/defect rank 顺序访问。此 variate 不是额外环境 seed 文件或环境未来 key；实际完整生成记录与基 key 的 lineage 必须保存。

## 2. 更新 law 与比较对象

| 正式地位提案 | architecture / tier / law | 同 tier reference | 解释 |
|---|---|---|---|
| primary400 | D_Q / L0 / FactualReturnWrite | NoWriteRef(L0) | 学习者事实信息下的主机制假设 |
| primary400 | D_patch / L0 / DeleteFactualPatch | NoWriteRef(L0) | 存储语义下的事实更新；不是改名的 Q law |
| primary400 | X / L0 / X_id | NoWriteRef(L0) | execution channel 的事实身份修正 |
| secondary200 | D_Q / L2 / CounterfactualReturnWrite | NoWriteRef(L2) | evaluator-assisted 上界 |
| secondary200 | D_Q / L2 / DualReturnWrite | NoWriteRef(L2) | 同 pre-state 双目标、一次事务的辅助上界 |
| secondary200 | D_patch / L1 / SetAlternative | NoWriteRef(L1) | corrective content 条件结果 |
| secondary200 | Process / L1 / P_id | NoWriteRef(L1) | 需要原 AssistedInput 的身份修正，不冒充 L0 |

L3 LocalOracleRestore 在对应 seed/cell 上作为 locality-matched normalization ceiling 报告，不参与普通算法“胜出”排名。D_patch/X/Process 的 L3 是已有操作别名，不能计作额外独立治疗或增加 N。GlobalOracleRestore 只作独立 constructional diagnostic ceiling，不能成为 RecoveryFraction 的分母或主比较。分母为 0 时比例未定义，保留绝对差值，不填 0 或 1。

不创造 D_Q L1、D_patch L2、Process L0 等原矩阵空格。所有 law 是原实现和原权限字段。主比较均只对自己的同 tier NoWrite；D_Q L0 与 D_patch L0 的差异只用 paired architecture interaction 描述，不从不同信息 tier 的曲线建立胜者排序。

每臂完整 S 使用原 native B1 一次规划、一次 lower、一次事务；所有目标来自同一 pre-state。保留每 owner 的 APPLIED、EVALUABLE_NOOP、NO_VALID_ALTERNATIVE 等原 receipt。别名、scalar 不适用、未触及故障、各 store 指纹都保留。不改原 runner 的 singleton guard，新增 addon 记录类型不能伪装原单点记录。

## 3. 整组 Collateral 的测量提案

### 3.1 区域与时间点

建议延续 v23 的交集定义，针对完整非空声明 S：

```text
C_joint(W_pre,S) = {u in full U2:
    outcome(W_pre,u) == SUCCESS
    and not any(Consult_pre(u,c) for c in S)}
                = intersection(E(c) for c in S)
```

每 cell 在任何 arm 执行前完成 5760 个 U2 scene 的 pre census，冻结同一个区域对象及同一份 pre map。构造器只接收 sanitized owner S、scene 字段、原 pre 轨迹和健康参考；不接收 Gamma、truth tag、k/shape、arm/law、APPLIED-only WriteSet、ledger 或 post outcome，并审查上游依赖闭包。NoWrite 也共享原 S，不能用空 S 把 reference 的集合换掉。

每 arm 的值是原顺序分别求均值再相减：

```text
B_arm = ordered_mean(pre values on C_joint)
      - ordered_mean(immediate post-B1 values on C_joint)
d_B = B_reference - B_treatment
```

Collateral 测量的是 immediate post-B1 状态被未来 scene 读取的行为，不是 future TD 训练后的状态。后续训练在独立 clone 上进行，前后检查 protected post-state 指纹。保留 signed B 和原始逐 scene 差值；不能取绝对值掩盖方向。逐点 E(c) 的诊断只描述同一次 whole update 后的地图，不声称是逐点因果效果，也不平均成主 Collateral。

### 3.2 总域、空集合与校准

生产总域是提案中每个合法 T/P defect/world 可能产生的 `(architecture, W_pre, complete S)`，包括 T 健康持久状态上的非空合法投影、P 全部正质量 trigger、多点及 NOOP/no-valid-alternative，不是地址任意 powerset，不是 v24 的两 site 构造。每个非空 S 的区域必须闭合、非空且 proper；重复实例按完整 canonical pre-state 与 owner tuple 去重，不能只靠 nominal hash 判等。

这是一个严格认证要求，**本次没有证明它可行**。组合族可能很大，Process 的某些完整非健康映射也可能没有足够正常区域；不能因为希望取得一个结果就在预期中宣称全部会通过。正式实施的第一项技术检查应先证明总域可表示/可认证及是否有合法反例，再决定这份具体提案能否原样进入冻结；发现矛盾要带完整反例修改待审阅提案，不能暗中减少总体。

必须获得覆盖全部 extent 的枚举证书，或可核查的结构证明加完整反例搜索边界；仅检查 400 个抽中事件不证明 totality。某合法实例为空时保留反例，阻断整组 ruler/正式设计；不缩 S、不改 region、不填 0、不静默跳过 world。不把尚未批准/执行的这一候选失配称为当前科学 STOP。

校准针对每个不同生产区域及相应 architecture，区域先冻结，再选其 lexicographic 首个可合法注入的组外 site：使用原 A89 的 scene/site 次序；选定后不能因效果小换地址。D_Q 的组外注入采用原 factual action row 降至 `min(Q*)-1`；X 采用原共同合法交集最小 alternative；Process 采用原最小不同 option。D_patch 另行检查 value-free patch 的原生合法组外动作覆盖，不能拿 D_Q 的校准冒充它。

独立预测器从完整 pre-state、已声明单个组外 edit 和原 step/return 语义重建整个区域的 post 行为；必须读取该 pre-state 已有全部缺陷，不能用 healthy Q* continuation 覆盖别的缺陷，也不能抄 measured map 作预测。预测与实测各自保存完整 map 和原逐步奖励顺序。比较逐 scene 和聚合标量，采用原 DP/G5 tolerance `abs(error) <= max(1e-12,1e-6*abs(predicted))`；这是数值 instrument tolerance，不是损伤容许界限。聚合 prediction 为 0 或没有合法注入 site 均属 ruler 未认证，不能换幅度或筛掉实例。D_patch 注入候选定义为该 pre 轨迹首个组外 Decision owner 上，合法且不在该 owner 原完整 optimal 集的最小动作；无此动作即校准未认证。

### 3.3 新容许损伤界限的确定性来源

建议不重新开启 F1、不读任何新治疗曲线，而在科学采集前对**完整新生产总域的 pre-only census**确定：

```text
spread(A,W_pre,S) = population_SD(pre values on C_joint(W_pre,S))
delta_joint = nearest_rank_0.95(all distinct declared (A,W_pre,S) spreads)
```

总域、实例去重和 canonical 顺序先冻结；包含 D_Q、D_patch、X、Process，所有提案 k/shape 和可出现 S，不只放方便的 calibration fixture。取每合法实例一份 spread，不按科学抽样频数复制。SD 直接读原始 values：全相等直接 0，否则先原有序 left-to-right mean，再原有序平方偏差求和、除 n、sqrt；不由 sum/sumsq 重建。rank=`ceil(0.95*M)`，不插值、不拟合。M 是全部实例数，不是统计 N。

该公式及其 pre-only 域是新增提案，**不是原 F1 阈值的授权迁移**。实际 delta_joint 数值尚未计算；本次不执行 census/calibration。若全部 spread 为零或求得 delta_joint 不有限/不为正，候选界限未定义，不造正数。总域完整计算的资源不可行时也保持未认证，不以抽样近似替代；须先报告技术可行性问题。

拟议主约束为 `lowerCI(d_B) >= -delta_joint`（inclusive）。NoWrite 的实际 B 也须保留并核查，理论零值不能替代运行；单次直接写入无关行为的 absolute loss 原图同时报告。本提案不加可被收益抵销的 composite score，也不悄悄加入 absolute-loss 第二通过门槛。

## 4. 后续训练与终点

科学 cell 的一次 initial B1 写入之后，两臂使用一个共享原 `FutureTrainingProtocol`、相同健康参考 bytes、相同有序 prefix100，对各自独立 post clone 进行完整 465 个训练回合，保存 466 个 raw checkpoint。后续不反复调用 Oracle 追加修正；否则验证的就是另一种 online policy，而不是这次初始更新 law。

健康参考候选按原 Q* 在相同 prefix100 一次准备，当前候选 `v_pre=0.7642000000000008`；未来 gate 还须绑定实际一次发布与消费者。F1 master 的 `0.7630078124999966` 不替代它。

| endpoint | 每 seed/cell 的量和方向 | 主判断提案 |
|---|---|---|
| P/RMST | 原 restricted_time；d=reference−treatment | lowerCI > 1.5；仅数量 benchmark 改善 |
| P/DeficitAUC | 原真实回合轴正缺口 trapezoid；d=reference−treatment | lowerCI > 0.01，与 RMST 一同满足 |
| P/BehavioralCollateral_joint | 上述 immediate signed B；d=reference−treatment | lowerCI >= −delta_joint |
| P/Retention | 原 checkpoint-mean 387..465；d=treatment−reference | lowerCI >= −5.515977517224342e-05 |
| T/RMST，各条件表 | 原 restricted_time；d=reference−treatment | lowerCI >= −1.5，独立 harm bound |
| T/DeficitAUC，各条件表 | 原 trapezoid；d=reference−treatment | lowerCI >= −0.01，mandatory companion |

P/Retention 的差值非劣判据是本文件给出的**新具体保持规则提案**。同时报告双方 LateWindowRetention 绝对值和对同一健康参考的水平。没有恢复的 seed 仍保留：Recovery time 右删失至 T465，Retention 仍在固定窗口定义；不只分析恢复者。

K3 是连续三个训练回合、threshold0.95 与事件起点不改。每 cell 先计算原 endpoint，再按预声明权重在同 seed 聚合 endpoint scalar；不先混合不同 cell 的曲线再重算 recovery time。中间看 100/200/300 只作 diagnostics，报告累计与 fresh100 block；secondary 的 final200 仍只支持次级命题。两组 seed 不合并成600，也不互相升级。

## 5. 完整统计 family 与退化规则

详细有序生成式见配套 JSON；不得从实际显著结果生成 family。primary contrast 次序为 D_Q-FRW、D_patch-Delete、X-id；secondary 次序为 D_Q-CF、D_Q-Dual、D_patch-Set、Process-id。每 contrast 的 P 行先 family weighted aggregate，再固定 cell 顺序；每行 endpoint 次序 RMST、DeficitAUC、Collateral_joint、Retention。T 行随后按 pure、mixed、zero 正质量表及 RMST、DeficitAUC 排序。结构零质量表的 absent status 在前瞻 census freeze 时固化，不看科学结果决定。

Decision 的 effect×k：相邻数量 `1→2,2→4,4→8` 的同 seed 改善差，k≥2 时先取该 k 两 shape 的等权平均。effect×shape：k=`2,4,8` 的 distributed−clustered 改善差。对所有 Decision contrast 的四个 P endpoints 都报告。另报 primary D_Q−D_patch 的 same-tier architecture interaction（七 cell 及 aggregate，四 endpoints）；不是跨 tier 排名。

若 T 三表均正质量，基本 endpoint 行 primary102、secondary140；Decision k/shape interaction 行 primary48、secondary72；primary architecture interaction32；合计394个正式命题。若结构零质量表存在，必须在 freeze 前按配套闭合生成式得出具体 ID 列表及数量；禁止在科学阶段删行。所有正常必需成员的缺失或不完整记录阻断完整分析。

每个命题使用完整 seed-order paired vector。95% paired-seed percentile-linear bootstrap 10000次、Python Random(960031)；原 seed 顺序、抽样索引序、算术与 quantile 方法均先绑定。每个完整 report 分别为 primary400 与 secondary200 重置该 analysis RNG，各自生成与其 N 匹配的索引矩阵；同 cohort 的所有命题共享该矩阵，不将400的索引用于200。这里是逐命题95% CI，不声称 simultaneous95%覆盖；完整 Holm 用于下述检验。不得看 future 完成顺序，也不把 bootstrap 均值为正的概率冒充 seed 改善比例。

完整394个（或 pre-freeze 结构生成的实际全部成员）组成一个 within-version multiplicity family，不用 secondary 小 family 帮 primary 降惩罚。分别对 exact-sign 与 companion conditional-exact Wilcoxon 做两份完整 Holm，alpha0.05；Wilcoxon 是强制报告的 companion，不另加未声明的显著性 gate。必须等待全部 primary400 与 secondary200 完整最终报告才作版本终判，secondary 本身不能替代主证据。

对 benefit row，检验 vector 为 `d−margin`；对 noninferiority row 为 `d+margin`；对 interaction 为未移动的 paired contrast。使用双侧 exact binomial sign（精确非零项）和 zero-wilcox/平均 tie rank 的双侧条件 exact signed-rank。每项同时报告未移动 d 的原 direction/sign/Wilcoxon 和 margin-shifted 正式检验；两者身份不同，不能混名。formal Holm 检验名单与各 offset 写入 frozen registry。

全 tie 的未移动方向诊断是 unresolved、dz/zero-net top5 share 为 null；正式全零 test vector 定义解析 p=1，标注 `DEGENERATE_NO_EVIDENCE`。这是**新的闭合统计约定提案**，不改旧候选把全 tie 记 null 的文件，不把缺少 p 的正常 record 填1。零 SD 的 CI 按真实完整 vector 的常数 bootstrap 结果报告，不造标准差或 p。

正向 finding 除 CI/margin 与 formal Holm-sign 条件外，还必须满足未移动 d 的 mean、median、双端各5% trim 同为非零改善方向；原 exact sign 经独立完整 diagnostic-sign Holm 后与改善一致；top5 同向贡献/net sum 严格 <0.50，并报告删除 top5 后均值。零 net、反号或尾部主导不能称稳定收益。

非劣界限不要求证明正收益：用其正式 `d+margin` test vector 作同样方向、trim、sign、top5 防少数值托举的检查，并检验 inclusive CI bound；未移动 d 的退化诊断如实报告。真实 constant d=0 可以符合正 margin 内的非劣标准，但只能称“未越过该 quantitative tolerance”，不能称零伤害、实际安全或实际等效。Holm diagnostic-sign 也形成全部未移动394成员的完整单独 family，零 vector 仍按上述解析 p=1报告，不删成员。

RMST 四标签保留 `MARGIN_A/MARGIN_B/WITHIN_BENCHMARK_MARGIN/INCONCLUSIVE`，不是 practical equivalence。其 T bound 是单独 inclusive 数量约束，不从标签推导。其他端点保留自身单位；不存在拟合、换门槛或看效应选设计。

## 6. 什么结果算支持机制

建议将 D_Q L0 / FactualReturnWrite 事前登记为**核心 anchor**，不是从结果挑“最好的一臂”。只在 primary final400 的完整 weighted family 上同时满足四项 P 条件及各正质量 T harm 条件、完整 multiplicity/direction/tail guards，才称“在所登记族内支持这个 learner-feasible 更新机制”。D_patch 与 X 的同规格结果各自报告；不能用 secondary 或 L3 上界救回 anchor。

这是具体版本归结方式的提案，原 A79 只规定 L0/终点合取，不自动批准选择这个 anchor。若要把另一架构设为核心，须在采集前另外明确前瞻版本规则，不能在结果后替换。

每个 k/shape cell 的结果都必须发表。任一效应出现跨 cell 反号，报告 interaction，**不宣称 universal winner**；weighted-family 支持不意味着所有 cell 都好。某 cell 的 Collateral/Retention 或 T 约束越界时，不能称“整族安全适用”，即使 family 均值通过。严格“全族每 cell 均支持”另行标为更强命题，仅当全部相应 cell 的完整判断都满足；不把该强命题偷换为 anchor 的平均命题。

若 CI 未分开或鲁棒性不满足，结论为证据不足/方向未定/尾部主导；若完整合法冻结研究得出反向或 margin 内结果，诚实报告该初始更新没有在登记条件下达到收益目标，不调参追 PASS。不把未实现 collector、未认证 ruler、协议错误或操作中断当科学负结果。

## 7. 从提案到采集的实施顺序

1. **审阅本提案**：具体确认总体条件化、有限 k/shape 和权重、joint ruler/阈值来源、保持/空投影/完整 family/anchor 归结。只批准草案不等于批准这些规则生效。
2. **另行授权 addon 实施**：只在原313外新 namespace，保留旧全部 bytes。形成可枚举 extent/重量/证书、真实 Oracle 路由、新完整集合记录、native whole-B1 和真实 keyed future collector。任何不可闭合实例先保存并说明，不擅改科学问题。
3. **完整门禁与源绑定审查**：原 full regression 仅原有1skip，全部原 B1表（含 D_patch encoding ledger）、B2 view/constructor 依赖闭包、fabricated-truth mutation、training/CRN/原calibration 等门禁按原要求串行；另加整组真假S、snapshot/atomicity、shared-object/clone、空区域、dict/hash order、错误 join、截断 raw/漏 receipt、secondary升格等挑战。恢复 mutation 后稳定边界再验 full source；旧缓存 PASS 不迁移。
4. **ruler 认证与新阈值实例化**：完成总域/calibration/pre-only census，只发布与此 proposal 的源版本和规则绑定的数值及证书。这个新增定标不重开原 F1，也不借原 F1 singleton PASS 批准它。若必须引入额外 baseline 科学数据，先提交独立前瞻变更和直接授权，不能自动分配32新seed。
5. **实际完整 dense workload/resource 认证**：另行批准且互斥的非科学 engineering keys；一次完整未来 B2 seed 的所有 cell/arm/466 checkpoint/raw maps/ceilings/序列化/I/O/worker 生命周期实际运行，证明 collector 完整。最大16仅跨独立seed/分片，smoke最多5；同seed chronology和全部mutation串行。测当前源码下的完整 stage workload 与完整 gate suite，原 bound `2×(T_suite+10×T_stage_workload)` 是 abort criterion，不是 ETA。资源、磁盘、峰值内存和实际 elapsed 记录；不拿原 baseline 或36map组件计数代替。stage workload 的确切 extent 与 benchmark stream 数在执行前资源 manifest 固化，不用小prefix外推全量认证。
6. **分阶段批准、冻结和单次 gate**：新完整 addon inventory、reference、population catalog/weights、定标证书、实际完整394成员 registry、统计/门禁/资源说明、exact fresh key files、本地 Git revision 都提交；分别明确 engineering key、science key 和 collection 权限。用户对方案的同意不跳过后面各阶段。仅全部前置闭合且一次性 collection gate 消费成功，才运行预定 primary/secondary。
7. **采集与最终分析**：按冻结 seed/cell/arm 顺序汇合整数/max/None 和浮点值；每 seed 保存完整 native worker/claim/exit、stdout/stderr、raw checkpoint/maps/ledger/actual incidence、压缩SHA和未压缩canonicalSHA、源码/gate前后绑定；所有子项齐全后 index-last 原子发布，最终统计报告另行绑定实际完整原始数据。

进程消失、操作/系统中断：保留预约与全部不完整证据，只写外部观察，不伪造 native exit，不自动重跑、不覆盖。发现采集后 bug：当前数据集保持无效证据；新冻结版本/freshkeys/重采必须另获授权，不通过自动修补替换成有效数据。只有真实最终科学结论或有效当前协议完整停止报告和唯一账本闭环，才结束现有续接。

## 8. 本次交付与下一步权限

本次交付 MD、机器可读 JSON、主代理内部审阅和只读字节核查记录。没有训练或统计试验，没有重新执行科学/F1/806/机制 fixture，没有分配 key，没有新 native 科学 receipt。

数值 delta_joint、生产 catalog digest/extent、工程资源证书、实际 seed 文件、最终 addon/collection manifest 是以后计算/执行的产物，不伪造到草案里。规则和失败处理已经提出；这些产物在前置认证完成前不能存在，更不能以草案状态冒充其完成。

下一次实质推进需要明确的“按这份方案实施独立 addon 并做工程验证”权限，仍不自动授权科学采集。用户无需逐个选择统计术语；代理应把科学问题或规则改变解释清楚后请求对应范围，而不是重复候选二选一。

## 来源

原规范事实来自 `docs/rebuild/12-AMENDMENTS.md` A75 §62.1/62.5/62.8/62.9、A76 §63.5–63.10、A79 §67、A89 §77、A91 §79；`05-STATISTICAL-PROTOCOL.md`、`15-SCENE-DGP.md`、`20-B2-DEV-PROTOCOL-FREEZE.md`、`31-FAILURE-ONLY-AND-RMST-AMENDMENT.md`、`34-A96-DENSE-MEASUREMENT.md`。实现覆盖由原 `b1/runner.py`、`b2/runner.py`、`b2/training.py`、`b2/unaffected.py`、`b2/calibration.py`、`env/domain.py`、`method/dgp.py` 和已保存 v21/v23/v26 记录交叉核对。配套 observation 保存实际文件 SHA；来源事实与本文件标明的新增提案不可混同。
