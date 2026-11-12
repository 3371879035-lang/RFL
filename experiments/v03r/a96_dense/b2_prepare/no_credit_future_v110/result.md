# V0.3：真实 T 空责任投影的普通未来分支

此前缺失的分支现在完成了有限真实执行：失败来源确实为 T/TRAP，完整责任是 `Unknown/NoWrite`，
D_Q 与 D_patch 的责任投影均为空。保留失败和全部残余责任，不制造 B1 写入、回执或零 Collateral。

实际新增两个独立健康 owned 来源、两次 factual；两个来源各产生两个独立 no-edit 普通学习角色。
每角色执行 3 个训练回合，在 checkpoint 0、1、2、3 先评估原锁完整 100 场景。
首 native 的 4 个方法全部完成：1614 次 rollout、9322 步、
12 次普通 TD 事务，耗时 89.609 秒。
来源安装事务、B1 调用、law plan、owner 回执和治疗事务均为 0。事务调用并不等于学到新价值。

| 路径 | 记账角色 | checkpoint 0、1、2、3 平均回报 | 每点精确等于共同健康参考 |
|---|---|---|---|
| dq | reference | 0.76420000000000077, 0.76420000000000077, 0.76420000000000077, 0.76420000000000077 | 是 |
| dq | treatment | 0.76420000000000077, 0.76420000000000077, 0.76420000000000077, 0.76420000000000077 | 是 |
| patch-adaptive | reference | 0.76420000000000077, 0.76420000000000077, 0.76420000000000077, 0.76420000000000077 | 是 |
| patch-adaptive | treatment | 0.76420000000000077, 0.76420000000000077, 0.76420000000000077, 0.76420000000000077 | 是 |

实际 12 个完整 TD receipt 中，
numeric 内容变化 0 次，
literal-D 内容变化 0 次。所有真实零响应均保留，
没有要求 L 必须非空，也没有把无编辑角色的一致轨迹称为架构等效或反馈治疗收益。

**本分支结论：没有归到该架构的责任，不应杜撰持久修正；但真实失败及残余责任仍保留，普通后续学习继续。**
Transient trap 仅属于 factual 来源，后续普通环境不携带该 trap。因而普通表现不是证明“从该失败学会了规避 trap”，
也不是处罚/不处罚实验、零一般伤害或独立种子总体结论。

完整原始轨迹、TD、来源/模式/角色/I/R+L 绑定与 null/N/A、19 个真实无额外 native 门禁拒绝及闭合外部投影，
已由新的 stdlib 存储审阅核对；运行时身份由实际新入口验证，存储审阅不重建身份，也不是独立专家认可。

首次存储审阅实际 exit 1：最终 wall_seconds 的 native float 与 binary64 wire marker 比较不一致。
原失败源码、完整 920 字节 stderr 和 capture 全部保留；新的定向 wire 修订审阅实际 exit 0，
只解码该计时元数据，未改数值状态 marker，也没有重跑 native 或把第一次审阅改为通过。

这补齐一个真实未完成的工程分支，不要求正收益才允许收口。原完整 T/P 条件族及 400/200 种子确认研究仍未完成。
未启动 keys、正式 keyed Protocol/Curve/train_curve、RNG/DP/native calibration 或 collector。
v109 仅为未执行的前瞻源码，没有已连接的正式学习后端、已激活 permit 或正式采集进展。
旧失败、超时和 partial 记录未修改或重跑；自动续接仍关闭。

入口：`result_summary.json`、`evidence/exit.json`、`stored_audit_wire_result.json`、`evidence_stored_audit_wire/exit.json`。
首次审阅失败原件：`audit_stored.py`、`execute_audit.py`、`evidence_stored_audit/`。
