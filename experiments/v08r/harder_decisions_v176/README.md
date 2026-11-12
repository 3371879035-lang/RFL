# V176：V0.8真实执行与存储分析

本目录执行`../plan_v175.json`的固定九组矩阵；旧方案及已经执行的V175纯算例字节保持不动。当前结果入口是`result.md`、`analysis.json`与解释文件`result_interpretation.md`；阶段导航见`../CURRENT.md`。

## 实现

- `world.py`：新的显式PublicTask/Observation/RewardPacket与有向无环分叉图。成功后继可公开，可靠性与随机数只在外部Engine中。
- `learning.py`：将原TD/真实回放/事实计数/有限模型备份方程移植到任意公开DAG后继，不再假设`room+1`。FT/CT/M1共用同一个Hybrid.learn；M1导入冻结的V175候选函数，没有改它的公式。
- `experiment.py`：完整普通学习、每点完整冻结副本、外生配对随机带和独占压缩捕获。训练成功与失败都普通学习；没有额外归因、调查或控制器改写。
- `stored_review.py`：独立的stdlib字典/数组算术重建，不导入native模块、不调用旧runner/checker。检查完整EOF/CRC/canonical记录、随机带、所有真实步、学习更新、策略和冻结银行。无法从JSON重建运行时身份，也不是独立专家资格。
- `analyze.py`：存储分析与外部小图精确策略值；没有环境调用或学习更新。相对最优值、真值动作质量仅在这个外部分析层计算。

## 执行口径

接线与矩阵分别首次执行一次，均native exit0，没有失败、partial或自动retry。接线为新图上的九组36回合；不是重跑旧fixture。矩阵为1728条学习流、442368训练、6193152冻结评估回合。连同接线合计6635556回合、23702368步。

记录保留全部实际访问与学习状态。完整Q、counts、buffer和history在LEARN后保存；每次训练前保存只读选择及适用的FT/CT/M1影子建议；不适用项明确为null。冻结银行保留完整状态、策略及每一个实际raw回合，不把精确值替代真实评估记录。

两份镜像是同一seed内的配对结构，不是新增独立训练N。主推断单位仍为32个seed块；约664万回合不是约664万个独立训练样本。九组在每个案例中拥有相同主任务数量和环境权限；额外模型/读出计算另计，并不声称全部计算成本相同。

native进程的矩阵仪器化墙钟约254.06秒；接线约.0077秒。它包括捕获与诊断工作，不含整项实现/审阅/报告时间，也不是生产算法速度基准。Windows工作集只是在native循环结束后、capture最终关闭和result.json序列化前采样，不声称覆盖最终全进程峰值。

## 数据与分析入口

- `evidence_wiring/`、`evidence_matrix/`：首次raw、exit、result与新存储审阅回执。
- `group_summary.csv`：九组×三地图的完整结果和成本。
- `comparisons.csv`、`paired_seed_deltas.csv`：全部预定比较及32个配对seed差值、bootstrap区间。
- `frozen_curves.csv`、`online_curves.csv`：每个冻结点和逐训练任务轨迹。
- `targets.csv`：实测与精确首次达标分列，null/退步保留。
- `matched_cost_summary.csv`、`matched_train_steps.csv`：每案例共同训练步预算下的已交付成功任务数。
- `mechanism.csv`、`mechanism_examples.json`：实际访问、覆盖标记、改变选择的正负例。影子建议不是完成过另一条训练流。
- `frozen_curves.svg`：主要方法的均值曲线展示，完整九组和区间仍以CSV/JSON为准。

新图仍是固定、已知拓扑的小任务；不检验未知拓扑、漂移、迁移或通用品味，也不代表全部强化学习方法。新阶段不重开V0.3旧400/200计划，不继承旧科学PASS，不变更automation。
