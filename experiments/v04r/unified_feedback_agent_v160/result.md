# V0.4 v160：两类反馈进入同一个连续agent

## 本轮不是再拼两个独立案例

新`UnifiedFeedbackAgent`把v156执行偏差/联合修正与v159无偏差TRAP问题生成，接入**同一个self、完整R+L、保护I、原来源注册表、once消费集合与总试验预算**。显式构造参数`learning_values`一次clone完整普通L，不在阶段转换时换模型或重置数值状态。新入口和使用例见`README.md`、`unified_agent.py`、`workload.py`。

构造器的真实MRO经过capture与新review核对；原event-only基类把写限设0，新构造器明确恢复启用角色的两地址语法，TaskTD仍0。不是对旧API/源码monkeypatch，也不是把旧serialized receipt反造运行时来源。

## 三个新角色、同一段18主任务混合流

| 方法 | 主成功/18 | 主回报均值 | 实际私有试验 | 总回合 | K.step | 非共享store TX |
|---|---:|---:|---:|---:|---:|---:|
| TaskTD：正常学习、无诊断 | 9 | -.0866666666666667 | 0 | 18 | 78 | 28 |
| ExecutionOnly：只执行偏差修正 | 13 | .33111111111111113 | 5 | 23 | 121 | 46 |
| **Unified：两类反馈统一** | **14** | **.43777777777777777** | **6** | **24** | **128** | **48** |

三个角色均新的独立source clone和完整普通学习；没有冻结NoWrite来制造差异。共同Q*、alpha1/2、epsilon1/10不改；现有visited-D先验策略改善与真正numeric学习区分。不是从零训练、旧313 unchanged架构的假资格迁移或独立seed总体推断。

## 实际经历了哪些情况

### A：复合执行错误（4任务，再回访2任务）

源中START的WAIT被X错误实现为RIGHT，触发真实起点右侧Trap；修正第一处后，实际试验又暴露(1,2,t2)的UP被X实现为RIGHT，进入危险格。当前真实见证才允许第二位置联合假设，最终一个原store事务删两个X地址。

两反馈组均用3个真实试验（keep、first、joint）。只是结果等价时复用当前keep/first标量结果，不伪造按新坐标执行过的native记录或多计样本。TaskTD源中两种起点命令都被当前执行机制导向Trap，单做正常Q学习不能在此源里绕开；6个A主任务全失败。两反馈组初始4任务2成功、回访2/2成功，共4/6。

这主要是修好既有执行机制，不把所有进步冒称新增价值知识。普通TD和B1式局部修正分开记。

### B：新phase的无执行偏差Trap（6任务，再回访2任务）

k0phi4、Trap(2,1)@action-step2为本轮固定的混合流场景。普通组与仅执行修正组在初始6任务均4成功；统一组经一次新的“另一入口到同地点/时刻”实际失败试验，初始6任务5成功。三组回访均2/2成功。

因此统一组相对仅执行修正多了一次主成功：不是因为重跑旧v159数据、按case标签指定分支或删掉零效应场景。路由只用当前可见`cmd!=realized`和任务终局；新事件问题仍是人工给定语法+公共几何，不是学出通用世界模型。该失败试验只与局部假说在一个新入口一致，不直接写入全局禁令。

### C：动作有偏差，但X其实在保护（4任务）

START命令RIGHT被X实现为WAIT，正好避开step0的Trap；真正导致首次COLLISION的是稍后一个错误D。三组普通学习均修复了visited-D选择。两反馈组真实比较keep的SUCCESS与删保护X的TRAP后，均选择keep，**没有误删保护**。

全局epoch11还给三组相同的事前固定ordinary探索坐标，强制命令RIGHT；实际都由保护X实现为WAIT并成功，证明不只是“后来没再读到它”。三组C都是3/4成功，不能把普通学习修复D的收益归功反馈写入。

## 预算、来源与学习真正共享

Unified实际来源序号连续为：A keep1/first2/joint3 → B alternate-entry4 → C keep5/first6。它不是给每个组件各6次，实际合计正好6次。ExecutionOnly用5/6。6是事前有限集成资源边界，不是优化出来的科学阈值；预算不足保留原keep语义，本轮没靠超额试验补结果。

A在联合修正后的下一次主任务还有无执行偏差TRAP；此时一动作深度不存在不同入口，公共枚举产生`specification=null/no_legal_alternate_entry`，**0真实额外试验**、无假观察/假分数，正常TD继续。这个空分支和所有失败保留，不是科学STOP。

11个原生来源观察全部一次进入同一个相应主agent的batch；5个被当前机制兼容检查接收，6个保留但拒绝TD。Unified接收joint SUCCESS、B新TRAP、C keep SUCCESS；删除保护的失败不能当作当前有保护机制下的同一动作失败去惩罚。任何source的最终L都没有复制回主模型，全部从当前L按原chronological binary64 TD更新。

每阶段/回访无reset/reinstall，三组各18个epoch连续；完整I/P与unread sentinel保持。普通learning可写visited-existing-D，不按反馈owner过滤；反馈只在A各一次原子2地址TX，C无反馈写。全部主任务SUCCESS零诊断/零查询/零诊断写，普通学习保留。

## 成功进步和完整代价同时报告

统一组相对普通组多5个主成功，也多6个环境回合、50K步、20个非共享store事务；相对执行修正组多1个主成功，同时多1试验/7K步/2事务。另有18次显式公共几何前向推演（A空分支3+B问题15），不是免费计算，也不声称总CPU/RAM/IO或净算力优胜。普通组步数低，一部分是更多任务提前死亡，不能直接据此排名效率。

全交互失败次数：普通9，执行修正8，统一8。若把试验与主任务原环境回报同价简单相加（附加核算，不是新采用的aggregate效用权重）：普通约-1.56、执行修正约4.58、统一约5.44。统一相对执行修正约+.86，但这仍是固定损坏源/有限流上的结果，不是总体最终收益或成本最优查询器。旧v159里试验同价总回报不如普通学习的结果仍原样保留，没有被本新混合流覆盖。

当前B调查有用，C调查只确认保护且未增加主成功；无可行问题时keep。是否值得付每次调查费用、何时选问题，仍不由本有限例子证明普遍最优。没有因为一次失败判整套方案死刑，也没有额外全局处罚；原负环境回报不变，不是有无处罚消融。

## 首次执行、记录与资格边界

新native首次exit0（2.859秒instrumented harness），新stdlib reviewer首次exit0。实际65rollout/327step/126TX/511canonical records：54主任务+11私有任务；共享4TX=3次原完整普通checkpoint物化+1次新7-edit来源安装，另外65数值TX+40普通D策略TX+5外来观察数值TX+4外来D策略TX+6私有候选X事务+2主反馈X事务。新来源额外工作完整计数。

349完整declared input native前后同，344历史完整文件physical=实际父Gitblob；新review覆盖整个混合流raw、原episode/coin/chi、运动/危险/终止/回报、全部TD/canonical/有序值比较、shared来源序号/once消费、两路dispatch、protective读路和回访。不是只看MRO/签名或组件旧PASS，也不从字节重建运行时身份，不是独立专家/sciencegate或全13GB tracked审计。

原313/API/guard/law-registry、旧执行源与全部失败/partial/zero/不利证据、98旧账本值/266provenance不改；新事实索引只append，CURRENT是可变导航、旧字节在父Git保留。未运行旧fixture/checker/native/bank，未开启keys/RNG/keyderive/参考DP/nativecalibration/formalProtocol-Curve/collector/确认采集/自动安排。

这是已能实际贯通的V0.4统一连续研究原型，仍为patch-adaptive/给定Q*/有限操作与问题语法的测试域；不是通用强化反馈学习、任意环境的因果识别或旧400/200完整确认完成。
