# RFL-CausalChase — 唯一结果账本

## v0.2 协议收口（2026-08-30）

| 项目 | 状态 |
|---|---|
| 工程状态 | 0.2.1 protected-probe、严格入口、产物校验与停止码已实现；新运行必须在干净 release worktree 执行。 |
| 旧 strict pilot A | H-A / H-U / H-K 为已执行的描述性历史证据。 |
| 旧 strict pilot B H-L | `invalid_probe_semantics`：错误 low-level last action 被当成正确知识，CKD/WKR 无效。不是科学 FAIL。 |
| Confirmatory | `blocked_not_run`。没有把旧文件补字段冒充 fresh rerun。 |
| 当前科学结论 | `UNSUPPORTED_BY_CURRENT_ENVIRONMENT`：当前 checkpoint/环境无法识别 Low-protection；因此完整链条不受支持。 |

原始 strict pilot 的状态和逐文件 SHA-256 在
`outputs/v02_pilot_20260830_strict/STATUS.json` 与 `ARTIFACT_SHA256.csv`。六组不可用的
旧输出在 `legacy/invalid_v02_outputs/`，每组原因见其 README。若冻结的 300 次搜索内
无法形成每方向 10 个、初始 margin 至少 0.60 的合法 probe，正式结论是
`UNSUPPORTED_BY_CURRENT_ENVIRONMENT`，不得改变 checkpoint 覆盖率或重新定义 correct action。

### Fresh smoke：`v02_smoke_protocol_closeout_20260830_final`

工程执行层级为 smoke；preflight 通过，正确解释器解析到 release worktree 的
`src/rflcc`，完整 A-smoke 完成。真实 benchmark 为 10,000 步环境 35,390 steps/s、
一次 Oracle CF 63,375 transitions/s。B 的两个 common checkpoints 均达到
`pre_success=1.00`、`pre_safe_option=1.00`，所以不是 pretrain gate 阻断。

| experiment seed | L-dominant + false-H（保护 H） | H-dominant + false-L（保护 L） | 结果 |
|---:|---:|---:|---|
| 2,000,000 | 2/2 probes | 0/2（300 次冻结搜索耗尽） | `blocked_invalid_knowledge_probe` |
| 2,000,001 | 2/2 probes | 0/2（300 次冻结搜索耗尽） | `blocked_invalid_knowledge_probe` |

`run_v02.py` 返回 **3**。B-online、12-seed pilot、50-seed confirmatory 均未创建；
这不是科学 PASS/FAIL，而是当前 common checkpoint/环境下 Low-protection 不可识别，即
`UNSUPPORTED_BY_CURRENT_ENVIRONMENT`。完整 raw、命令、双 config hash、benchmark、
planned/actual manifests 见 `outputs/v02_smoke_protocol_closeout_20260830_final/`。

# RFL-CausalChase-v0.1 — 历史结果（截至 2026-08-28）

## Experiment A（Attribution Microbenchmark，confirmatory 50 seeds）

配置：`configs/confirmatory_a.yaml`（config_hash 见 `outputs/confirmatory_a/confirmatory_meta.json`）。
每 seed 90 条独立 base causal traces（H/L/E 各 30），clean 与 symmetric-0.40 两条件配对。

### 主统计（seed 为统计单位，paired sign-flip 10,000 / bootstrap 10,000）

| 对比 | 条件 | Δ(Full-RFL − Immediate) | Cohen d_z | p | 95% CI | 预注册门槛 |
|---|---|---|---|---|---|---|
| AE | symmetric 0.40 | **−0.272** | −5.72 | <0.001 | [−0.285, −0.260] | ≤ −0.08 且 CI 不跨 0 → **PASS** |
| WUR | symmetric 0.40 | −0.026 | −0.45 | 0.002 | [−0.043, −0.011] | ≤ −0.10 → 未达幅度 |
| AE | clean | +0.017 | +21.3 | <0.001 | [0.017, 0.017] | （clean 无门槛） |
| WUR | clean | +0.321 | +168 | <0.001 | [0.320, 0.321] | （clean 无门槛） |

### 各算法（symmetric，seed 均值）

| 算法 | AE | WUR | UpdateCoverage |
|---|---|---|---|
| Immediate | 0.478 | 0.370 | 0.67 |
| PE-Seq | 0.455 | 0.499 | 1.00 |
| CF-only | 0.000 | 0.177 | 1.00 |
| **Full-RFL** | **0.199** | 0.325 | 1.00 |
| Oracle-upper | 0.000 | 0.177 | 1.00 |

### per-cause（symmetric，Full-RFL vs Immediate 的 AE）

| cause | Immediate | Full-RFL |
|---|---|---|
| H | 0.421 | 0.023 |
| L | 0.408 | 0.082 |
| E | 0.604 | 0.492 |

### 判读

1. **主假设（错误反馈下 Sequence Evidence + Counterfactual Verification 降低错误归因）
   在 AE 上强支持**：50 seeds 上 symmetric 条件 Full-RFL 的 AE 比 Immediate 低 0.272
   （d_z=−5.7，CI 远离 0），H/L 单因轨迹上近乎完美归因（AE≈0.02–0.08）。
2. **WUR 改善幅度未达预注册 −0.10**，原因明确且被指标如实揭示：
   - E-only 轨迹的 oracle R* 固有 mixed（≈(0, 0.5, 0.5)，环境几何使 ΔL≈ΔE），
     忠实归因的 WUR 下限 ≈ 0.5；
   - Immediate 在 feedback=E 时 41% 不更新内部模块（UpdateCoverage=0.67），
     通过"不更新"逃避 WUR——这正是规范要求同时报告 UpdateCoverage 的原因。
3. **clean 条件下 Full-RFL 略差于 Immediate**（AE +0.017）：反馈 100% 正确时
   Immediate 天然最优；RFL 的价值在错误反馈下显现，与预注册假设一致。
4. CF-only 与 Oracle-upper AE=0（上界）；Full-RFL 以约 1/5 的 CF 计算量接近
   CF-only 的归因质量（CF transitions：Full-RFL ~85 vs CF-only ~390）。

## Experiment B（Integrated Tabular Learning，pilot B4 进行中）

sanity ladder：B0（No Monster success 1.00）、B1（safe option 1.00）、B2（H/L 归因可区分）、
B3（dash=0, success 0.98）、B4（dash=0.10, standard 1.00 / full_rfl 0.94）全部 PASS
（5000 episodes，pilot grid 内）。

## Experiment B pilot（B4，dash=0.10，12 seeds × 3 算法，5000 episodes）

| 算法 | 最终 success（seed 均值） | visited states | 归因次数 |
|---|---|---|---|
| Standard-HQ | 0.970 | 2876 | 0 |
| Immediate | 0.983 | 2999 | 2300 |
| Full-RFL | 0.958 | 2940 | 2187 |

**判读（预注册负结果路径）**：三算法在 B4 均学会任务（success ≥ 0.95），任务性能
差异不显著——对应规范预注册的"Experiment A 成立而 Experiment B 不成立"路径：
更好的责任解释（A 中 AE −0.272）未自动转化为更好的 tabular policy learning。
可能原因：环境本身可学会且三算法均饱和（天花板效应）、auxiliary shaping 幅度
（alpha_diag=0.10）相对 task QL 影响小、feedback 注入错误率下诊断更新不改变
长期策略收敛。这是可报告的科学负结果，不作为"RFL 无效"断言——仅限本环境/规模。
