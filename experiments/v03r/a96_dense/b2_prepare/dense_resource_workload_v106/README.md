# V106 — full-scale declared engineering workload

本轮实际结果：DQ 两个角色各完成 465 个训练回合和 466 个检查点，完整入口退出 0；patch 对照完成 465 回合，治疗完成 415 回合后在最后已完整执行的 bank 边界触发事前 2400 秒上限，退出 1。整体是 **partial**，不是完整通过，也不是机制方向被反驳。

共记录 183,212 次环境执行、1,081,759 个步骤、1,810 个训练回执及 1,814 个完整原始检查点 bank。检查点反复评估同一锁定的 100 个场景，这些执行次数不是独立科学样本量。DQ 的两条完整曲线及外部投影已经验证；patch 没有完整 pair 曲线句柄，不能用已记录 bank 冒充它。

新存储核验最终退出 0，精确重算物理轨迹、动作、TD、canonical 写入、有序均值和预算停止边界。前两次核验脚本失败分别是来源 tag 分派遗漏、把原 kernel 的 `float(sum(...))` 单回合回报误写成逐项 `+=`；失败源码和回执全部保留，新版本只恢复原读路，没有放宽精度或重跑 native 实验。

当前下一技术件是版本化只读 bank 的性能实现与路径/保护语义验证，针对每场景重复的全状态转换。学习规则、原冻结 API、原始结果及科学判定不改；本次失败不重跑追通过。自动续接没有重新开启。

Status: `PARTIAL_DECLARED_ENGINEERING_WORKLOAD_NATIVE_FAILURE_PRESERVED_STORED_VERIFIED`.

The planned extent is T=465, all integer checkpoints 0–465, and all 100 locked evaluation scenes. DQ and patch-adaptive run serially on the fixed deterministic engineering input; both NoWrite and treatment continue learning.

| Mode | Native exit | Complete banks | TD episodes | Wall seconds | CPU seconds | Peak working set MiB | Gzip MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dq | 0 | 932 | 930 | 2299.609 | 2260.422 | 567.88 | 12.42 |
| patch-adaptive | 1 | 882 | 880 | 2402.063 | 2361.750 | 287.03 | 9.56 |

Actual recorded totals: 183212 rollouts, 1081759 steps, 4 B1 calls, 1872 transaction calls, 2 complete role curves.

Additional fresh source capture/install work is explicitly counted in `result_summary.json`; these are not additional scientific seeds or a new scientific population.

Read `result_summary.json` for actual resource totals and curve diagnostics; `stored_audit_kernel_return_revised_result.json` retains all complete ordered curves, raw-content validation and sampled resources; `source_binding.json` links original native/audit receipts and exact input pins.

The first stored audit exited 1 on an ORIGINAL_SOURCE tag-dispatch error. The separate dispatch audit also exited 1 because its naive episode-return fold differed from the original kernel float(sum(...)) semantics. Both sources and complete failure captures remain unchanged. The kernel-return revision restores the exact original calculation without tolerance; chronological TD/B1 reversed folds and ordered bank addition are unchanged. This separate audit version/capture is not a native workload retry. Any partial or failure is retained without retry. Instrumented timing is not production timing. This is a full-scale execution/resource check for the exact declared stream, not F1 transfer, keyed-domain qualification, full-family scientific validation or a final V0.3 result. No new keys, RNG, DP, calibration, formal keyed stream or scientific collection were run. Automation remains disabled.
