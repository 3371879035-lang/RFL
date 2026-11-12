# V0.4 v154：修复试验证据跨情境混用，并接回完整agent

## 这轮是已定位缺口的实际修复，不是另做一轮收益示例

v153已经明确记下：新联合修正准入依赖受控private-plan工厂保证情境一致，公开入口未完整核对。现在用真正执行的新外情境来源复现，再新增StrictWitnessLoop，并提供可用的StrictTrialDerivedAgent组合入口。原v153执行源码/capture不修改、不重跑。

### 1. 旧问题真实存在

主任务是kappa1/phi0。旧接口收到一份同数值根、同引用/参数/角色，但实际执行在phi3的owned试验。试验确实运行了原kernel，确实签发EvidenceTrialObservation，不是JSON伪造。

旧v153随后真的产生并通过了一个含phi3位置的联合修正授权，将另一情境的见证挂在当前phi0主诊断下。为保存反例而不写坏模型，旧路径最后返回keep，**0外情境live写入**；不能因此说旧准入正确。

外情境反馈本身并非没有价值；它可以支持对应条件的学习或迁移假设，但不能冒充“同一当前主任务条件”的联合修正证据。

### 2. 新入口在两个地方拒绝混用

- 创建分支前，检查source episode0与当前真实main epoch的kappa、完整SemanticTape、proposal和参数；错误计划在任何原source事务/K调用之前拒绝，登记来源0，rollout/step/TX增量全0。
- 对故意通过旧基类工厂登记、然后真正执行的外情境来源，新的witness门禁仍拒绝。没有mint新联合权限、没有live写入，增量也全0。这个调用是明确的legacy-registration兼容性负向挑战，不是monkeypatch或重试旧fixture。

见证检查同时绑定实际EpisodeAdapter/issuer plan/epoch0/原literal input、观察id/注册表/source I和完整native trace情境。原有ref/mode/role/chrono/数值根约束保留。没有新增奖励、修改TD或扩大候选地址法则。

### 3. 修复不是把正常研究入口关掉

第一份新capture中，同情境phi0的真实第一修正试验失败，形成第二位置联合假设；同输入baseline−1.02、joint+.86，严格入口允许原store一次原子2写，并让适用的联合观察进入普通TD。

随后另立事前有限integration contract，实际运行新的`StrictTrialDerivedAgent(StrictWitnessLoop, TrialDerivedAgent)`完整策略：当前phi3，真实5个private任务完成初步失败→第二位置假设→匹配菜单→联合选择→一次原子2写→适用观察学习。MRO实际记录并检查，不只是写了一个未执行包装类。

这两次都只验证准入/完整接线，不新增未来曲线或总体收益结论。

### 4. 错误输入的完整agent保持真实partial

第二份capture另有一个fresh agent，主任务phi3、private-plan工厂故意返回phi0。实际发生：

1. 主kernel已经运行，普通TD已经提交；
2. 新private factory在任何private source/TX/K之前拒绝；
3. 保存TASK_PARTIAL、ordinary_committed=true；
4. agent关闭，没有完整main receipt、登记来源或修正授权；
5. 没有重试、补0、回滚已发生TD或把partial改成成功。

外层验证harness退出0表示观察到了预期拒绝，不表示这个故意错误的任务完整完成。

## 实际工作与证据

两份新的独占capture，分别事前固定问题/预算，不是自动重跑：

| 新capture | 实际rollout | K步 | store事务 | 新存储审阅 |
|---|---:|---:|---:|---|
| v154外情境反例/严格拒绝/同情境联合正向 |8|16|27|首次0|
| 完整bound-agent集成/故意错误计划partial |7|17|24|首次0|
| 合计 |15|33|51|均首次完成|

总5个真实main rollout（4完整receipt、1预期协议partial）+10个private rollout，167条完整canonical记录。额外原始来源安装2TX/8edits，明确记录两次checkpoint materialization各3TX；17数值事务、17普通策略事务、7private候选事务、2live修正事务/4地址。两个场景都实际保留全部I；没有private-L复制或serialized issued对象恢复。

两份新stdlib审阅检查所有实际raw命令/坐标/物理移动/hazard/trap/终止回报、binary64 chronologicalTD、fullR/L/I、真实源/见证记录流、拒绝0增量、匹配菜单、原子写与partial后状态；不从字节恢复运行时身份，也不是独立专家/sciencegate。新native各首次0，旧路径的错误授权仍作为真实反例保存，不被native0包装为PASS。

原v153同情境数值结论不被此反例推翻：原capture中的kappa/phi实际都匹配。旧源码/证据不动，原313/API/guard/law-registry/F1与92旧账本字段/266provenance保留。新keys/RNG/keyderive/DP/calibration/正式collector/采集0，旧fixture/checker/native/bank重跑0，automation未触碰。导航CURRENT可更新，旧导航完整blob及旧账本hash保留于parent Git；它不是native输入或科学gate。

## 入口与边界

- `strict_witness.py`：只收紧原v153的source/witness准入。
- `bound_agent.py`：本轮实际集成执行的`StrictTrialDerivedAgent`，复用原v153候选/试验策略。
- `integration/workload.py`：当前完整使用示例、真实positive与partial。

这是具体跨phase0/3缺口的修复与有限正向检查，不是所有kappa/proposal/tape组合、partial/异常、keyed或原完整B1资格全通过。未新测Retention/Collateral、未来Utility或总体收益。旧v153实验性两位置见证法则仍为显式新法则，不被此包装继承成原冻结law PASS。
