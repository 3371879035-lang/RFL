# V0.3R 完整真实 credit 的 B2 测量规范草稿

供研究者审阅。V0.3R 研究的是给定分 regime 的 Oracle credit truth 后，不同合法 persistent update law 如何改变未来行为，并不要求先选定普通诊断算法。原规范要求保留同一事件的全部真实 manifestations；现有 B1 支持整组事务，而 B2 测量入口只接受单位置。本草稿提出完整 credit 的传递和整组 Collateral 测量方案，补足这一覆盖缺口，不改变研究问题。

研究者直接回复“可以”，只授权起草本草稿。以下新增接口、集合定义、判定方向和校准方案都是待审议建议，不是生效协议、实现授权、预注册、科学 PASS 或采集许可。原冻结 313 项、原 F0 和 F1 保留；本草稿不分配任何科学或 workload 工程 key。

## 原规范与新增提案的边界

| 内容 | 已有约束 | 本草稿的地位 |
|---|---|---|
| 科学对象 | Oracle credit 下的 persistent update law，分 T 和 P regime | 保留，不增加普通算法比较 |
| 真实 credit | 全部 manifestations，不选 first 或最小地址 | 保留，不缩成单点总体 |
| 干预 | 同一 pre state 上规划全部地址，一次事务，每地址一份 receipt | 保留原生 B1 语义 |
| Collateral | 原 A89 定义 E(c)，原 B2 入口绑定恰一个 c | 提议增加整组入口和 E_joint(S)，不修改旧入口 |
| 定量界限 | 原 F1 有单位置来源的 Collateral 阈值 | 不自动移作新集合的阈值 |
| 科学终判 | 按 seed 聚合，同 tier、完整 family、最终 look 与终点合取 | 保留，具体新终点声明仍待闭合 |

原依据是 A75 §62.8 和 §62.9、A76 §63.10、A77 §65.9、A79 §67.4 和 §67.7、A89 §77.4 和 §77.8。新增提案不冒充这些条款已批准的内容。

## 真实 credit 的传递

区分四个数量：安装缺陷的 k、事件实际 manifestation 数、该 architecture 解析得到的唯一 credited owner 数、内部 scalar edit 数。它们不必相等，任何一个都不是独立统计样本量。

1. 由实验生成器产生真实 factual episode，先认证终止 failure，再进入已有 failure-only correction 边界。SUCCESS 不触发 correction，普通 TD 学习仍按原规则进行。
2. evaluator 按原来源生成完整 Gamma_T 或 Gamma_P。T 只来自 transient fault 的原冻结机制描述；P 只来自 learner-owned persistent manifestations，不混入 transient mask、evaluator do 或 T truth。
3. evaluator-only Oracle 返回完整真实 credit；普通候选的 proposal expansion 不承担这条路径，也不放宽其拒绝 Oracle 的已有接口。全量 truth 留在 evaluator 审计包中，不能直接送入 B1 primitive 或 FutureConsequenceView。
4. 按 architecture 的原 rho 映射，将合法可写的 credit 解析为有序 owner 元组 S。每个 manifestation 都保留到 owner 的对应关系；不属于该 architecture 的单位保留在投影审计中，而不是偷偷删除整个真实 credit。
5. 同一事件、同 architecture、同 tier 的两臂，共享同一个声明 S。S 在两臂执行前形成，不能取 APPLIED-only、实际 WriteSet、scalar key 或某臂 ledger；NoWriteRef 也不能因不写入而把 S 清空。

D_Q 的 owner 是 DecisionAddress，整行多项 Q 编辑仍属于同一个 owner；X 是原 ControllerSite；Process channel 在单 episode 中只有静态 ProcessCommit，经原 resolver 和明确允许的 assistance 对应一个 proposal key。Process channel P 不等于 persistent regime P，不给 Process 凭空增加多地址。

manifestation 到 owner 如出现多对一，应保存所有原单位与事实行，使用原生 B1 envelope 对事实行的原聚合规则；不能通过取首个事实回报解决冲突。原规则未覆盖的映射、未知类型、非法 owner 或 assistance 来源冲突，应保持未闭合并阻断对应科学入口，不能裁剪真值集合获得可运行记录。

S 为空时不制造 singleton，也不将未定义 Collateral 填 0。空投影、无真实 credit 和 law 自身的 NO_VALID_ALTERNATIVE 是不同情况。科学总体如何涵盖前两种情况仍须事前完整声明；不能在见到结果后跳过 seed 或换事件。NO_VALID_ALTERNATIVE 和 EVALUABLE_NOOP 保留在整组 ledger，不改变原声明 S。

## 拟议的整组 B2 入口

未来实现拟放在冻结清单外的独立 addon，通过原生 B1 的各 architecture 入口执行整组计划。原 B2 singleton guard 和原候选 singleton extractor 不改；整组记录使用新的明确类型，不伪装 PairedSceneRecord 的单位置记录。

一次同 tier paired cell 的顺序拟固定为：

1. 认证 factual failure、pre state、允许的 evidence 与完整 credit 到 S 的映射。
2. 完成 full U2 的 pre census，记录每个 scene 的 pre SUCCESS 与对 S 各 owner 的 Consult incidence；冻结集合，再测量一次共同 pre map。
3. 从同一个 pre state 建立两份独立 clone。每臂用原生 B1 对全部 S 规划、lower 到同一 pre view、提交一次事务，保留全部 receipts 和 scalar 账目。
4. 保存各臂 immediate post B1 state 和指纹，并在冻结的共同集合上测量其 post map。
5. future training 使用 immediate post 的另外 clone；两臂共享同一 keyed protocol、同一 nominal reference 和锁定的有序 100 场景 bank，按 0 至 465 的每整数回合记录。future 结束后 immediate post 指纹仍须不变。
6. 保存完整 raw maps、ledger、curve、chronology 和 hashes，最后发布该 cell 的完整索引；不将部分记录当完成。

S、集合对象、共同 pre map、nominal reference 和 training protocol 不只比较内容相等，还须对实际消费者认证共同来源和共享对象。两臂 clone、post state、future state 则须认证彼此独立。

这段顺序只是一份未来接口草案，尚无新 collector 实现或运行。健康参考候选的 v_pre 为 0.7642000000000008，属于锁定 100 场景 bank；F1 的 1024 场景 master 值不能替代它。参考候选仍需未来 B2 一次提交的字节与实际消费者绑定。

## 拟议的整组 unaffected 集合

建议审议的主集合是对全部声明 owner 都无 pre consult 的健康 scene 交集，而不是逐点结果的均值：

```text
E_joint(S) = {u in full U2 : H_pre(u) and not any(Consult_pre(u,c) for c in S)}
           = intersection(E(c) for c in S), for nonempty S
C_joint(S) = E_joint(S) under the proposed eligible_all interpretation
```

这里的 H_pre 和 Consult_pre 均来自未编辑状态的真实 scene rollout，保持原 scene-level SUCCESS 及原 owner 粒度。声明 S 只是受控的 credited-site 输入；构造器不能访问 Gamma、truth tag、安装缺陷 k、arm 或 law、实际写入集合、ledger、post outcome、canary 标识，也不能根据结果重新构造集合。还必须证明上游没有把这些禁止信息编码到允许字段中；局部函数签名不等于来源认证。

这一交集建议延续“与 credited 干预无关且此前正确”的含义：一条 scene 若读了 S 的任一成员，可能承受预期局部改进，不应被记作整组干预对无关 scene 的 spillover。它是新增的集合语义，需要明确批准，不能由原 A89 单点条款或旧 F1 的 eligible_all 名字自动推出。

单点 S={c} 时集合在数学上等于原 E(c)；这只是退化一致性，不代表整组实现、校准或阈值已认证。逐点 E(c) 的并集不适合作为同一含义的主集合，因为其中的 scene 可以读其他 credited owner。

新增 totality 义务应覆盖拟议科学总体中所有可出现的合法 S 及其 pre state 来源：集合 membership 在全部 5760 U2 上闭合，非空且是 proper subset。每个 E(c) 非空不保证交集非空。拟议 jointly reachable 的生产集合范围必须由真实总体和执行来源给出，不是从工程 fixture 推断，也不是把所有地址任意 powerset 当已证明总体。

未定义、空交集、缺少 census 或无法证明 totality 时，不更换 region、不补零、不只留有利子集、不只采 singleton。当前这类未闭合是草案覆盖问题，不是已执行科学 NO_ADMISSIBLE 或原生 STOP。

## 拟议的主标量与逐点诊断

每个 arm 的整组 BehavioralCollateral 拟保留原运算结构，先按同一有序 scene 列表分别求两个均值，再相减：

```text
B_arm = sum(float(pre[u]) for u in C_joint)/len(C_joint)
      - sum(float(post_arm[u]) for u in C_joint)/len(C_joint)
d_B = B_reference - B_treatment
```

正 B_arm 表示对这些 pre 正确且无关 scene 的性能损失；正 d_B 表示 treatment 比 reference 更少损失。不得改为 abs、截断负值、max、平均 per-site B、重复 scene 加权或浮点 moment 重建。pre 和 post raw map 必须恰覆盖相同集合，保留有序 values 与 hex、压缩 SHA 和未压缩 canonical SHA。

每个 c 的原 E(c) 仍可完整输出，测量对象是同一次整组干预后的 post state。它们只作描述性诊断，并记录其中 consult 其他 credited owner 的 incidence；不能称为“只写 c 的因果效应”，也不能平均后升级为科学主标量。共同 scene 出现多次不增加统计 N。

例如 S={a,b} 时，一条 pre SUCCESS scene 不读 a 但读 b：它属于 E(a)，却不属于 E_joint(S)。整组更新后它的变化可能来自对 b 的预期干预。这个例子说明量的含义差异，不是声称旧 fixture 已出现该情况。

原 v20 工程 fixture 的 12 个 E(c) 恰好同为 5280 条有序 scene，无其他 fixture 地址的 consult，pre 和两个 post map 逐元素相等。因此该 fixture 不区分这些语义，其零值不能用来选择新 endpoint、批准新阈值或宣称收益。

## 拟议的校准与界限闭合

整组 region 改变后，需要单独来源绑定的 ruler 校准，不能继承旧 18 个单点 calibration 的 PASS。拟议校准保持 A89 的原则：先固定 S 和 E_joint；在 region 内从真实 pre trace 选一个可作合法 synthetic spillover 的 owner，该 owner 不在 S；在 persistent substrate 上按明确的预注册规则做真实上游注入；独立参考推导整个 region 的预测值，再由实际环境测量 pre 与 injected post。

不得直接编辑 values map、从 measured 值复制 reference、只核对某个 witness 的符号，或用对 S 内成员的预期编辑冒充 off-target 注入。输入出处、选址与 edit 规则、reference 的独立性、数值 tolerance、全生产域的覆盖证明和 serial mutation gate 都必须事前写明。预测 aggregate 为零或不存在可注入 owner 时，应报告 ruler 未校准，而不是换一个方便的 site 或缩窄总体。

建议审议的约束方向是“relative collateral 不劣于 reference”：在 d_B 的 paired seed CI 上检查 lower bound 不低于 -delta_joint，即在 B_treatment-B_reference 的 CI 上检查 upper bound 不高于 delta_joint。inclusive 边界也是提案，不冒充现有终判规则；是否还需要 arm 的 absolute-loss 上界必须另行明确，不能把 relative bound 说成零伤害。

delta_joint 数值、其是否沿用原统计函数及其新来源、calibration tolerance 和完整终点合取仍为待审议项。原 F1 的 P BehavioralCollateral 数值 0.04146752410689062 来自单位置 measurement envelope，不能自动用于 E_joint。不得因新 ruler 的工程零值设 delta=0，也不得用 treatment 的结果选 threshold。

草稿不重开或重采旧 F1。新 ruler 若需要独立 baseline measurement-property 数据，须在另行批准的 prospective addon 设计中规定完整输入、fresh 互斥 key、独立 native receipts 与用途；不能把旧数据重包装成 joint 校准或新增 native PASS。若不能在保持原 F1 的边界内闭合，应将具体冲突交研究者审议，不能自动重做 F1。

## 科学总体与分析连接

保持 A75 的真实 k×shape 缺陷 family 及 interaction 报告。k 数值、shape 枚举、各 cell 权重、事件生成分布和空投影处理仍需完整事前规定；本草稿不从 TrajectoryCredit 的 28 个预测或 D_Q 12 地址推定任何科学总体。Q 与 patch 对相同 extensional policy defect 独立安装，不能用一个生成另一个。

更新法和同 tier reference 继承原批准的 typed matrix：D_Q 的 L0 FactualReturnWrite、L2 CounterfactualReturnWrite 和 DualReturnWrite、L3 LocalOracleRestore 分别对各自 tier 的 NoWriteRef。Process 与 X 使用其原批准的 cell 和 alias，不新增 law 或普通算法 family。跨 tier 曲线仅解释信息 headroom，不排算法优劣。

每个 seed 先用事前固定的全部 cell 和权重聚合成一对端点值，才跨 seed 推断。site、scene、event、receipt 都不是独立 seed。primary 400 的四个 100 block 与 secondary 200 的两个 100 block 不互相升级；cumulative 与 fresh block 均按计划报告，只有最终 look 终判，不能因 interaction 反号补样本或删层。

paired CRN、完整固定 Holm family、方向和 exact sign、median、5% each-tail trim、top5/net 与删除敏感性，以及 Utility、Collateral、Retention、T 独立 harm bound 的完整合取均保留。分析候选已有的 10000 次 paired-seed bootstrap 和 RNG 960031 仍只是未冻结分析约定；本草稿不运行统计、定新 family 或宣告最终规则已批准。RMST 1.5 只作数量基准，不作实用意义、等效或零伤害结论。

## 对原 F1 的影响

本草稿不改 q=387、T=465、N_eval=100、G={0..465}、LateWindowRetention 的 H1=387 和 H2=465、K=3、0.95 健康比例、cap576、C3 layer1、alpha1/2、epsilon1/10、master bank1024、完整 U2 和原训练及 Retention 算术。

保留这些原设计字节不等于它们已批准新 endpoint 的全部消费者。是否以及如何将既有合法设计依赖绑定到新 addon，应在独立 manifest 中逐项列出；其中 joint Collateral region、ruler validation、threshold provenance 和最终 claim 是新的待闭合依赖，不能整体宣称继承原 F0 或 F1 的 collection 权限。

## 待审议事项与未来执行门槛

本次供审阅的实质提案是：完整真实 credit 到 S 的独立 Oracle 路径、整组 B2 新记录类型、交集 E_joint 的主集合语义、原双均值相减的 arm 标量、relative collateral bound 的方向。它们尚未被采用。对具体科学总体、量化阈值、新数据需求和 family 的批准不能由“允许起草”推出。

只有后续获得具体范围批准，才可实现 addon。采集仍须经过完整集成和 serial mutation gates、全回归仅原 1 skip、source-bound review、真正 dense B2 整体 workload 和资源认证、完整预注册与 addon inventory、本地提交的独立 manifest 和一次性 collection gate。旧 baseline timing、806 项候选准备测试、内部审阅或本草稿的结构核对都不是这些门禁的替代。

本次状态是草稿完成待审阅，不是科学失败、科学 NO_ADMISSIBLE、研究完成或有效 STOP。已有续接保持活动；未收到具体新方向时，不重复测试、重写观察或启动采集。

## 依据与来源

- [原规范中的 credit 与 update law](D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009/docs/rebuild/12-AMENDMENTS.md:3414)：A75 §62.8、§62.9；A76 §63.10；A77 §65.9。
- [原 Collateral 约束](D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009/docs/rebuild/12-AMENDMENTS.md:4750)：A79 §67.4、§67.7；A89 §77.4、§77.7、§77.8。
- [原生整组 B1](D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009/src/rfl_rebuild/b1/runner.py:394) 与 [原生 singleton B2](D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009/src/rfl_rebuild/b2/runner.py:299)。
- [范围纠正](D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009/experiments/v03r/a96_dense/b2_prepare/protocol_scope_audit_v21.json) 与 [完整覆盖审计](D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009/experiments/v03r/a96_dense/b2_prepare/protocol_coverage_audit_v22.json)。
- [独立草稿声明](D:/强化反馈学习/RFL-CausalChase-v0.3-dense-20261009/experiments/v03r/a96_dense/b2_prepare/whole_credit_protocol_draft_v23.json)：父提交、权限、拟议量、未闭合项及原字节 binding。
