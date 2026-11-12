# V0.3：恢复量可观测性 canary 实验

这是针对此前初始回报已高于健康参考、恢复量无法区分的问题，事前固定的工程 canary。
设计受到既有结果启发，不是盲采样的原科学总体；0.6122/0.6506 仅为静态预期，不拿它替代实测。

| 路径/角色 | W0 平均回报 | W465 平均回报 | τ / restricted time | DeficitAUC | Retention@465 | 晚窗 387..465 |
|---|---:|---:|---|---:|---:|---:|
| dq/reference | 0.61220000000000097 | 0.76420000000000077 | 68 / 68 | 0.010821505376344076 | 0.76420000000000077 | 0.76420000000000077 |
| dq/treatment | 0.65060000000000107 | 0.76420000000000077 | 68 / 68 | 0.0092937634408601869 | 0.76420000000000077 | 0.76420000000000077 |
| patch-adaptive/reference | 0.61220000000000097 | 0.76420000000000077 | 23 / 23 | 0.0068576344086021387 | 0.76420000000000077 | 0.76420000000000077 |
| patch-adaptive/treatment | 0.65060000000000107 | 0.76420000000000077 | 23 / 23 | 0.0053298924731182652 | 0.76420000000000077 | 0.76420000000000077 |

τ 保持原 0.95×共同健康参考阈值及连续 3 个整数回合；restricted time 是本输入流的量，不叫总体 RMST。
DeficitAUC 使用原有序真实回合轴梯形和除以 465，Retention 使用原终点及晚窗 checkpoint mean。

差值方向：NoWrite−treatment 的恢复时间或 DeficitAUC 为正，表示治疗的受限恢复时间更短或缺口更小；
treatment−NoWrite 的 Retention 为正，表示治疗的终点或晚窗回报更高。零和负值同样保留，不套胜负门槛。

- dq：NoWrite−treatment restricted time=0，DeficitAUC=0.0015277419354838891；treatment−NoWrite Retention@465=0，晚窗=0。
- 同一真实 pair 的即时 wholeCollateral：C=4920 场景，B_NoWrite=0，B_treatment=0，NoWrite−treatment=0。source/完整 owner/完整 I_post 与未来初始状态链相同，不借旧 P 零值；这个局部值不是一般零伤害。
- 实际 numeric 内容变化 64 个 episode，literal-D 内容变化 0 个；counts={'B1': 2, 'rollout': 109731, 'step': 632537, 'transaction': 932}，wall=276.578s。
- patch-adaptive：NoWrite−treatment restricted time=0，DeficitAUC=0.0015277419354838735；treatment−NoWrite Retention@465=0，晚窗=0。
- 同一真实 pair 的即时 wholeCollateral：C=4920 场景，B_NoWrite=0，B_treatment=0，NoWrite−treatment=0。source/完整 owner/完整 I_post 与未来初始状态链相同，不借旧 P 零值；这个局部值不是一般零伤害。
- 实际 numeric 内容变化 0 个 episode，literal-D 内容变化 7 个；counts={'B1': 2, 'rollout': 109731, 'step': 633315, 'transaction': 996}，wall=266.640s。

NoWrite 也完整普通学习，未冻结对照。只修本事件的一个 owner，另外三个持久 canary context 保留。
patch 的 visited-existing-D 策略改进可能由已有 Q* 先验触发，即便 numeric TD 为零；
因此数值内容变化与 literal-D 策略变化分列，不把策略改进叫新数值知识或新增 B1 责任，也不据此给 DQ/patch 排名。
所有零、负、未恢复和 partial 结果按实际保留；正收益不是完成条件。
这是固定机制/工程输入流的条件性结果，不证明架构优胜、一般零伤害、处罚结论、统计等效或全 RFL。
原完整 k/shape 与独立 400/200 seed 确认仍未完成；没有 keys、正式 collector、RNG/DP/native calibration 或 F1 PASS 迁移。
v111 的真实 T/NOOP 结果保留，没有重跑、删除或当作错误试验。本次开始前，主代理实际核实 rfl-a96 每 15 分钟续接为 ACTIVE；这记录观察，不预测后续配置。实验失败不自动重试。

完整机器数值、源码/物理证据 pins、同 pair 的尺子值与限制见 `result_summary.json`；大体积原曲线/TD不在摘要重复拷贝。
