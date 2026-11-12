# V0.3：真实 T/Decision₁ 完整未来学习对照

两个架构的首次完整 dense 输入流均已执行并经新存储审阅核对。

来源是健康 learner 在 T 环境的真实 transient decision fault：第 1 步强制 RIGHT，
两步发生 COLLISION，回报 −1.04；原结构责任只有 `Decision_1`，一个 owner，无残余。
普通 future 不携带这个 transient fault，不将失败归因换成 P 的最优成员规则。

| 路径 | NoWrite W0 | 原更新后 W0 | NoWrite W465 | 原更新后 W465 | 全 checkpoint 均值精确相同 |
|---|---:|---:|---:|---:|---|
| dq | 0.76420000000000077 | 0.76420000000000077 | 0.76420000000000077 | 0.76420000000000077 | 是 |
| patch-adaptive | 0.76420000000000077 | 0.76420000000000077 | 0.76420000000000077 | 0.76420000000000077 | 是 |

## 实际更新与学习

- dq 的原完整 B1：reference: {'EVALUABLE_NOOP': 1} / changed=0; treatment: {'EVALUABLE_NOOP': 1} / changed=0；实际治疗事务调用 1 次。NOOP 是 0 状态差，不等于没有事务；完整原 receipt、标量和全 store 留在 JSON。
- 该来源 factual suffix=-0x1.051eb851eb852p+0，原 Q* 的错误 RIGHT 值=-0x1.051eb851eb852p+0；精确同值=True。
- 实际 930 个 TD receipt：numeric 内容变化 0 次，literal-D 内容变化 0 次，普通训练事务调用 930 次。所有零值保留，不要求 APPLIED 或 L 非空。
- patch-adaptive 的原完整 B1：reference: {'EVALUABLE_NOOP': 1} / changed=0; treatment: {'EVALUABLE_NOOP': 1} / changed=0；实际治疗事务调用 1 次。NOOP 是 0 状态差，不等于没有事务；完整原 receipt、标量和全 store 留在 JSON。
- 该来源 factual suffix=-0x1.051eb851eb852p+0，原 Q* 的错误 RIGHT 值=-0x1.051eb851eb852p+0；精确同值=True。
- 实际 930 个 TD receipt：numeric 内容变化 0 次，literal-D 内容变化 0 次，普通训练事务调用 930 次。所有零值保留，不要求 APPLIED 或 L 非空。

这是合法真实的“反馈没有提供新的值信息”对照：原 B1 可评估而未改变持久 store，
不等于删去失败或裁剪责任。不能从此声称“内化 T 错误产生了损害”，也不能把 no-op 宣称为治疗收益。

## 执行证据与边界

- dq：native exit 0，actual={'B1': 2, 'rollout': 94131, 'step': 545424, 'transaction': 931}，完整 bank=932，wall=154.391s，CPU=152.359s；计时含 profile/记录/检查，非生产证书。
- patch-adaptive：native exit 0，actual={'B1': 2, 'rollout': 94131, 'step': 545424, 'transaction': 931}，完整 bank=932，wall=163.484s，CPU=161.359s；计时含 profile/记录/检查，非生产证书。

当前 pair 的 Collateral 没有实际测量：`NOT_MEASURED_FOR_THIS_PAIR`，值为 null；不迁移旧 P 的 whole 零值。
本次是固定 T 机制与预声明工程输入流的条件性结果，不是处罚/不处罚实验、跨架构优胜、统计等效或一般零伤害。
正收益不是 V0.3 完成前提；本个案完整也不冒充原完整 T/P/k×shape family、400/200 独立 seed 确认或最终合取已完成。
Q*、alpha、epsilon、原 ordinary 学习及 F1 字节保持；没有 keys/RNG/DP/native calibration/正式 collector，自动续接仍关闭。
旧 fixture、失败、超时和 partial 没有重跑或改成通过。数据来自当前新首 native 与新的独立 stdlib 存储审阅，非独立专家认可。

完整来源/B1/原始曲线/逐 TD/资源/哈希与真实失败信息见同目录 `result_summary.json`。
