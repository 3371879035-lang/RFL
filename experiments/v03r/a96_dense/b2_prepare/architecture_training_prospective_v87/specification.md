# V0.3R 逐架构未来训练契约草案

状态：技术前瞻提案，未采用、未冻结、未实现。新增普通学习状态及其与补丁的组合需要明确批准；本草案不改变原四 store、互斥 guard、F1、科学规则或采集权限。

要保留补丁架构并真正评估未来学习，必须同时定义补丁怎样参与动作、普通学习写到哪里，以及训练后的状态怎样被评估。当前源码不能用一个读取包装闭合这三件事。本草案建议：DQ继续使用原Q学习路径；literal patch保留完整B1后四store，并增加显式、独立的普通学习表。探索在架构贪心读取之前发生，补丁只覆盖非探索的贪心分支。这是一项新的状态和组合语义提案，不是原A77已经允许的D与Q优先级。

## 原契约的条件性冲突

A91 §79.2和§79.3规定跨回合状态只有原四store，§79.4规定普通训练只写Q，D/P/X保持B1后字节不变。A77 §65.4又规定非空D和非空Q不能同时服务任何决策读路，未定义优先级。

设某个合法B1后的补丁状态D非空、Q空。若一个训练回合的原TD sweep产生至少一个经过原canonical规则后仍存在的Q override，原transaction保留D并写入Q，下一次构造provider就会被正确的互斥guard拒绝。这个推论不需要认定每个回合都产生Q，也不声称本轮发生过native失败。对允许这种TD输出的完整训练域而言，以下四项不能由原单状态接口同时保证：

- 跨回合只有原四store。
- 非空补丁D保持不变。
- 原普通Q学习及其非canonical输出继续写回该状态。
- 每次provider构造都满足D/Q互斥。

此外，training.py的非探索分支直接读q_decision_provider，而ordinary评估读decision_provider(q_decision_provider)，因此补丁命中的非探索训练动作与评估动作不一致。只有完整普通bank不能证明未来训练资格。

本结论是原条款与实际源码的条件性兼容性分析，不是原update-law机制的实验反证。不能为避开条件而禁止所有非零TD输出、只保留空D世界、删sentinel或缩减family。

## 推荐的显式状态提案

保留每臂完整即时B1后状态I_a，永不训练它。未来状态由I_a的独立owned clone开始。决策模式在来源签发时固定为DQ或literal patch；不能根据治疗后D是否为空、law、receipt、Gamma、regime或效果切换模式。X和P cell也沿用其来源的决策模式，不因为本cell投影在另一store就丢弃原D/Q/P/X残余。

| 来源决策模式 | 未来可变学习状态 | 贪心命令 | 普通训练写入 | 保持不变的声明 |
| --- | --- | --- | --- | --- |
| DQ | 原四store clone中的Q_e | 原effective Q argmax，最小action id打破并列 | 只写该Q_e | D为空，P/X保持I_a值 |
| literal patch | R_a为完整B1后四store；另有显式学习表L_e | D命中时取D，否则取L_e覆盖Q*后的argmax | 只写L_e，R_a的Q仍空 | R_a全部D/P/X及空Q不变 |
| X cell | 按来源的DQ或patch模式 | 同来源完整读路，再读X | 同来源学习表 | B1后的P/X/D声明保留 |
| P cell | 按来源的DQ或patch模式 | 原proposal经P提交后，在实际in-force option决策 | 同来源学习表 | B1后的P/X/D声明保留 |
| NoWrite与ceiling角色 | 与本cell治疗使用同一种模式 | 各自完整post，不借其他角色 | 同一模式及TD规则 | 不因空plan、alias或no-op重置 |

对patch模式，L_0为空，缺值取同一个注入Q*；R_a必须本来就满足Q为空，不能删除非法输入的Q来“修正”它。R_a保留独立安装的literal defect、所有owner和nonowner声明。对DQ模式，Q_0是该臂实际完整B1后Q，不另外叠加一个不可学习的Q反思层，也不healthyreset。

L_e不是B1的新架构治疗，不接收credit、owner集合、tier envelope、ledger或健康target。它只是候选普通学习的显式状态，仍必须被列入完整未来state的类型、指纹、序列化和所有权；不能藏在callback、闭包、cache或第三方backend里。DQ的B1成本仍按原scalar ledger，patch的B1成本仍value-free；L_e的TD工作另记，不能冒充补丁的B1 scalar成本。

这个表示保留了原每个LearnerPersistentState对象的互斥规则，但整个patch未来系统已同时持有D与学习Q值，并明确让D覆盖贪心基础表。因此它实质改变A91的“四store且无其他状态”和A77的逻辑组合边界。把数据放进两个对象不能声称已经满足原科学契约；必须新修订、审阅和批准后才可能实施。原guard本身不改。

## 动作读取与探索顺序

每个训练episode先固定完整未来state snapshot，整回合不更新。原P读取proposal产生实际option_in_force，再初始化control；X读取实际pre-state与发出的a_cmd site，保留原kernel所有合法性和shadow规则。训练和checkpoint均无来源的transient mask、optionfault或do；T来源故障只封存在factual证据中，不进入ordinary未来。

训练第i个实际kernel决策步骤固定如下：

1. 从实际pre-state、in-force z和m取完整合法动作集A，按原action id排序。
2. 在原共享episode对象的坐标i取精确有理epsilon coin；两臂不以命中次数、provider调用次数或拒绝次数重新编号。在无fault/do的完整从t0开始训练中，每步恰一次policy调用，i等于实际step index。
3. 若探索，则按原整数keyed rejection从A均匀取a_cmd，不调用任何贪心provider，也不读取补丁命中来改动作。补丁在这一分支被探索策略覆盖；P和X仍按原kernel执行。
4. 若非探索，DQ读Q_e贪心；patch先读D，命中则检查合法性并返回D，基础表provider不调用，未命中才读L_e贪心。
5. 原kernel处理命令、X、plant和control更新；保存完整pre/post状态、a_cmd、u、realized action与reward。

这对应“epsilon在greedy外层”，而不是在D的fallback里面加epsilon。后者在D命中时不探索，并让用fallback调用次数作为i的实现错位，不符合本提案保留的A91每步epsilon分布。另一方面，贪心patch命中时不调用基础provider，保留原shadow纪律；coin属于外层训练策略，不是被shadow基础provider的隐含副作用。

在greedy checkpoint没有coin或任何训练draw调用。patch仍D优先，DQ仍Q贪心，实际P/X完整读取。非法patch仅在该分支真正被读取时由原合法性语义拒绝，不为了验证隐藏路径而抢先调用被shadow provider。完整provider构造的状态/类型/互斥检查与访问时动作检查是不同门禁，均不可取消。

新的R/L复合state不能冒充原LearnerPersistentState传入environment.learned_rollout，原入口实际要求严格类型。未来需要一个显式、受审计的addon评估/训练适配入口，并把它纳入完整source inventory与constructor-flow/mutation门禁；不松旧入口类型检查，不伪造旧handle，也不在旧runner上临时替换provider。

## TD目标与普通写入

普通TD保持原A91公式、alpha1/2、gamma1、二进制浮点运算顺序。DQ用自身Q_e的mutable working copy；patch用L_e的mutable working copy。缺值始终取注入Q*，不是0。对真实raw按chronological顺序重建pre-step，step0必须用trace.option_in_force，后续用上一StepResult的post-state/control。

地址q_j包含实际pre-state、in-force z、m和实际a_cmd，而非realized action、proposal或下一state。每步先读current，target先赋reward；非terminal时再加合法next actions中working effective Q的最大值；最后执行原current + float(alpha) * (target-current)。terminal和HORIZON终止只用reward，不引入折扣或patch动作值。

这里的bootstrap是原off-policy Q目标，在patch模式也对L的完整合法next action集取max，不把D映射当作新target约束、不改成SARSA或给a+额外奖励。它可能学习到一个被固定补丁在greedy时覆盖的更好动作；这正是固定patch架构的性质，不可据此自动删除patch或宣称两个架构未来等价。该bootstrap与新复合行为策略的关系需要在架构修订中明确批准，不能单凭公式相同取得科学资格。

episode结束后一次写回，一地址只保留最后effective value，顺序按首次出现的原地址顺序；等于Q*按原exact equality canonical删除。DQ只更新原Q；patch只更新显式L，所有R_a条目逐字保持。非法domain、NaN/Inf、duplicate、错误类型整事务失败，不部分提交。这个proposal不实施新的事务类。

B1的nonowner、不触及sentinel和residual保持是即时更新边界。之后普通Q或L学习允许改变真实训练访问的非owner Q地址，这是A91普通学习而非扩张credit；不得把普通TD改写说成B1越界，也不得借此训练D/P/X。每臂的初始完整I_a和每回合R_a不变必须分开验证。

## 完整回合和评估chronology

在e=0先从完整未来state得到V(0)，不是重测健康v_pre。e=0到464各完成一个frozen-snapshot rollout及一个TD sweep/atomic write，进入下一state；在每个整数e=0到465先做锁定100场景的greedy只读evaluation。e=465只评估，不再训练。完整curve共466点，真实训练465回合；保留原ordered mean、所有raw和完整store/L快照。

两臂使用同一个原shared protocol与同一坐标Xi_e；共享的是对象和键映射，不是提前选择两臂实际相同动作。相同seed内全部chronology串行，提前终止不为另一臂移动坐标。评估不得派发derive/coin/chi/uniform，不更新任何store/L、reference或episode index。

未来完整指纹须包含固定模式、R或W的全部四store、L全部typed QAddress/value.hex、父source/post/reference/role绑定及其版本。审计metadata不进入policy或TD；不能把scientific seed、Gamma、owner、law或已测V作为学习feature。I_a、source和其他role对象独立且不变；一个空D角色不能借另一个角色的L或shared mutable table。

异常或partial保存实际raw/TD候选/前后store和完整traceback；未完成的episode、checkpoint、curve或pair不签complete handle，不填mean、补0或自动retry。一次性reservation在首native之前消费，checkpoint的只读缓存必须事前证明合法，否则不复用。

## 独立架构和公平预算

独立DQ与patch安装必须仍由相同extensional defect descriptor各自生成，不从另一架构的post或Q训练表翻译。初始所有declared contexts、非eligible、未读sentinel、完整k与shape和world测度保留。预算以DecisionAddress context计，不以scalar数或L条目数凑相等。

未来两架构各自NoWrite与本tier治疗共享自己的full pre、全部owner/residual、训练规则和protocol；跨架构不复用issued handle或Q-only CF。双方同alpha/epsilon、episode数量、evaluation bank、grid、reference、原TD formula与合法动作域，并完整报告实际访问及TD成本。不同初始幅度、patch覆盖和未来learning轨迹可能导致成本和效果不同，不能强制同轨迹、补空更新或按效果调整预算。

patch的学习表是newstate proposal，不是证明架构比较已经公平。公平性须在完整family、原两轴interaction及所有source决策模式下审阅；不能排除残存D的NoWrite、X/P角色来消除困难。local/global ceiling的原alias不算新的独立治疗；每个真正额外trained role仍完整计资源。

## F1和门禁影响

原313冻结源码、dev_lock和所有历史F1 bytes原样保留。六项锁定T/P threshold记录仍在，不能以本草案沿用数值就称新架构已被F1覆盖。T465、N_eval100、G0到465、LateWindow387到465只作为现有锁，不能擅重算或放宽。

DQ候选路径要求与原训练的逐动作、TD、canonical store、ordered checkpoints完全相同。patch在D为空、L映射与原Q一致的受限域上有可写出的逐回合归纳等价条件；目前只是证明义务，不是新运行或任意合法state证书。F1 C3初始化中的Q状态若需映射到L，必须另作显式受限证明；不能把C3直接加进生产patch的L_0，也不能拿旧32 baselines自动批准新state。

以下原A91六项mutation目标不变：pre-step地址、actual in-force option、整数rejection探索、训练不能改变即时Collateral状态、不能每臂重测v_pre、两臂必须同shared training stream。原脚本和已完成receipt不重跑、不覆盖；未来若新增addon需自己的源码绑定门禁，不能迁移旧PASS。

新增门禁须覆盖D存在但training exploit绕过、epsilon被patch抑制、step坐标按fallback重新编号、隐藏L/跨角色alias、TD改写D/P/X、bootstrap偷用patch或truth、Q-reference canonical漂移、empty-D自动换模式、checkpoint误读R忽略L、checkpoint副作用、episode内写入、partial伪完成和非法R含Q。全部串行；必要域由本完整架构契约定义，不靠更多已完成状态展示。

FutureUtility/Retention必须读取新复合state的实际未来曲线，不能读只含R的旧environment入口然后忽略L。原K3恢复、real-axis trapezoid、Retention mean/sum、完整最终family/Holm/direction/tail/top5与Utility/Collateral/Retention/T合取不改。新学习态对F1资格的transfer能否成立须source-bound完整证明；若不能，必须提出新的资格范围并取得授权，不能自动重开F1、换key或追阈值。

整组Collateral仍只读取I_a，不读取训练后的W或R/L。v86交集区域、方向、delta_joint、校准与完整family仍未采用；本训练提案不替它们取得科学资格。

## 实施范围和下一步

建议请求的最小范围是：批准在冻结清单外起草并实现显式patch未来学习state addon，采用上述外层epsilon、D优先greedy、独立L的原TD规则，同时起草A77/A91相关新修订并做新的无key、隔离、有限工程验证。原生产模块、guard、B1 law、registry与已执行证据一律不改；新实现不能先接入scientific collector。

这是一项涉及状态定义和组合读路的实质范围，当前没有该具体批准。本草案只提出它，不将其实施。即便得到这一范围，也不自动授权新whole ruler、阈值/family生效、F1重采、工程/science keys、完整密集资源运行或正式采集；这些需要各自完整前瞻闭环。

新表每完整role不会凭空增加episode数量：原465训练加46600 evaluation仍47065 rollout，两臂future94130。新增L会增加store/IO和适配验证成本；这些未实际计时，完整工作负载仍须展开source、CF、B1、whole region、calibration、ceilings、全部gates和原正式400/200。旧F1 timing或v85 bank不能替代资源certificate。

收到具体批准前不做provider wrapper“先修一半”、不创建新backend、不新增native例子、key或训练。可继续与该新state无关、确有必要的原完整family和ruler依赖审阅；没有新的可行动变化时不重复范围报告。当前UNEVALUATED、collection关闭、研究未完成，无有效原机制反证，非scientificSTOP。

来源父提交4151c42ad7bad80999cbecc71fd736c552ba5db7。contract.json记录机器可审阅的顺序和权限，source_review.json绑定原条款、实际源码及条件推论。本草案的实现层内部审阅不是独立专家或科学PASS。

