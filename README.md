# RFL-CausalChase

最小可复现表格式强化反馈学习（Reinforcement Learning from Feedback）实验系统。
完整规范见 [`docs/RFL_CausalChase_v0_1_SPEC.md`](docs/RFL_CausalChase_v0_1_SPEC.md)。

---

## 📍 版本导航与结果入口

本项目按里程碑分成若干分支，**默认分支 `master` 是 v0.2 的状态**。最新结果在 `v0.4`。

| 分支 | 内容 | 关键文档 |
|---|---|---|
| `master`（默认） | v0.1 / v0.2 | [`docs/RESULTS.md`](docs/RESULTS.md) |
| `v0.2-responsibility-update-learning` | v0.2 责任→更新→知识→学习 | — |
| `release/v02-protocol-closeout` | v0.2 协议收口 | — |
| `v0.3` | v0.3 credit / repair 语义 | `docs/V0_3_CLOSEOUT.md` |
| **`v0.4`** | **当前主线：credit-unit 与 repair 语义** | **`docs/FROZEN_RESULTS_400.md`** |

### 结论入口

**先读 [`docs/FROZEN_RESULTS_400.md`](https://github.com/3371879035-lang/RFL/blob/v0.4/docs/FROZEN_RESULTS_400.md)**（在 `v0.4` 分支上）——这是全项目**唯一**的确认性文档。

它建立在三项方法学工作之上：

- [`docs/SEED_BLOCK_PROTOCOL.md`](https://github.com/3371879035-lang/RFL/blob/v0.4/docs/SEED_BLOCK_PROTOCOL.md)
  —— 冻结的预注册：$N_{\max}=400$，四个不重叠的 100-seed block；结论由 CI 相对
  $\Delta_{\min}=0.01$ 的位置决定，而不是由 $p$ 是否跨过 0.05 决定。
- [`docs/ROBUSTNESS_AUDIT.md`](https://github.com/3371879035-lang/RFL/blob/v0.4/docs/ROBUSTNESS_AUDIT.md)
  —— 为什么需要上面的协议：本项目的 per-seed 配对差值是**零膨胀 + 重尾**的，
  均值单独不可解释。三条旧结论因此被撤回。
- [`docs/REVERSAL_LEDGER.md`](https://github.com/3371879035-lang/RFL/blob/v0.4/docs/REVERSAL_LEDGER.md)
  —— 反转账本：23 条对比里 5 次真反转、**0 次方向改变**；7 次 CI 翻转**全是 no-op**。

> ⚠️ **除 `FROZEN_RESULTS_400.md` 外的所有结果文件都标记为 EXPLORATORY**，不作为证据。
> 它们记录了探索过程，以及旧数字在新协议下移动了多少——这本身就是结果。

### v0.4 的核心结论（N=400）

- **难度扫描六档中只有一个真发现**：`tight_h5_a03`（horizon 5, α=0.03）上 Oracle
  路由**有害**，ΔAUC = −0.0828，**四个独立 block 全部为负**。
- **其余五档全部 EQUIVALENT 或 INCONCLUSIVE** —— 项目里三次"反转"都是噪声的移动。
- **粒度消除 collateral**：`DecisionOracle` vs `ModuleOracle` 是 **0.4352 → 0.0000**
  （结构性、精确），编辑次数少 2.67 倍。
- 一个复现性缺陷（`PYTHONHASHSEED` 导致 WMD 有 3.3 倍波动）被发现后，**整套 v0.4
  seed 作废并从 N=0 重跑**；见
  [`docs/V0_4_REPRODUCIBILITY_DEFECT.md`](https://github.com/3371879035-lang/RFL/blob/v0.4/docs/V0_4_REPRODUCIBILITY_DEFECT.md)。

> **⚠️ 一处 headline 已被撤回。** 早先写的 *"直接修补 Q-entry 不是合适的 update
> primitive"* **不成立**：`CFRevalue` 把反事实回报写进了**事实失败动作**的 Q-entry
> （`alt_targets` 构造后从未被读取），实际是在抬高那个导致失败的动作。它不是 spec
> 声称的 ceiling arm。详见
> [`docs/V0_4_SEMANTIC_CORRECTIONS.md`](https://github.com/3371879035-lang/RFL/blob/v0.4/docs/V0_4_SEMANTIC_CORRECTIONS.md)
> —— 同一份文档还修正了 Oracle family 比例、`DECISION`/`EXECUTION` 语义碰撞，以及
> Pilot Gamma 的统计（重算后一个判定从 `SUPPORT_B` 变为 `INCONCLUSIVE`）。

**最重要的未解问题仍然没有被回答**：更好的归因 / credit 是否导致更好的策略学习。
目前对 RFL 有利的可靠证据是 V0.1 的归因效应和 v0.3/v0.4 的 collateral 下降，
**不是** task utility 提升。

---

## 科学定位

> **Feedback information 不应被默认视为 ground truth learning target；在一个完全
> 可审计的 tabular causal environment 中，重新评估内部 sequence evidence 并主动
> 执行受控 counterfactual verification，是否可以降低 misleading diagnostic
> feedback 导致的错误模块归因和错误更新。**

- **Experiment A**：Attribution Microbenchmark —— 在 H/L/E 单原因轨迹上注入可控
  错误反馈，比较 Immediate / PE-Seq / CF-only / Full-RFL / Oracle 的归因误差（AE）
  与错误更新率（WUR）。
- **Experiment B**：Integrated Tabular Learning —— 只有 A 通过后才把归因机制接回
  Q_H(s_H,o) 与 Q_L(s_L,a)，验证"更正确的归因 ⇒ 更少的错误模块更新 ⇒ 更好的学习"。

## 环境

- 9×7 网格，起点 (1,3)，终点 (7,3)，障碍 `{3,4,5}×{2,3,4}`。
- Monster 每 2 个 agent step 基础移动一次，dash p=0.10；全部随机性来自 `NoiseTape`。
- reward 互斥：EXIT +1.0 / COLLISION -1.0 / TIMEOUT -0.5 / step -0.01；γ=0.97，H=30。
- 事件语义：`ROUTE_PROGRESS/DEVIATE` 按动作前后到 waypoint 的 shortest-path 距离；
  `DIST_*` 按 monster phase 后 BFS 距离。feedback token 与 causal events 完全分离。

## 安装与测试

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
```

## v0.2：责任 → 真实更新 → 知识 → 恢复/学习

**当前收口状态（2026-08-30）**：旧 strict 12-seed pilot 的 A 证据可保留，但其
B-transfer 的 H-L probe 把故意错误的 low-level last action 当成“正确知识”。因此它
是 `invalid_probe_semantics`，不是 H-L 的科学 FAIL；confirmatory 没有运行，完整链条
不受支持。原始文件保留在 `outputs/v02_pilot_20260830_strict/`，并由
`STATUS.json` 和 `ARTIFACT_SHA256.csv` 固定；其他占位输出在
`legacy/invalid_v02_outputs/`，不会被新入口读取。

v0.2 保留 v0.1 的表格式环境和归因算法，不增加 DQN、Shapley 或新模型。它只检验
`R* → R → 实际 ΔQ → knowledge margin → recovery/learning` 这条链。诊断更新的冻结
语义是 `ΔQ_H=-alpha_diag*R_H`、`ΔQ_L=-alpha_diag*R_L`；每一次实际写 Q 都有
before/after/delta 收据。

新实验只写入新的 `outputs/v02_*` 目录。特别地，`outputs/confirmatory_a/` 与
`outputs/pilot_b/` 是 v0.1 历史证据，不会被 v0.2 命令覆盖或混入分析。

严格执行顺序如下。每一步失败都应保留其新输出作为审计材料，并停止下一步，而不是
删除失败 seed 或用结果调参。

```bash
# 1. release worktree 中使用其 editable venv；先完整测试
python -m pytest -q

# 2. 每层只能写入一个全新的 outputs/v02_* 目录。
# 0=全通过，2=有效科学 FAIL，3=配置/probe/运行/产物无效，4=拒绝 confirmatory。
python scripts/run_v02.py --tier smoke --config configs/v02_smoke.yaml --outdir outputs/v02_smoke_fresh
python scripts/run_v02.py --tier pilot --config configs/v02_pilot.yaml --outdir outputs/v02_pilot_fresh

# 3. 只有 pilot 的四个主 gate 全部 PASS 才允许此命令。
python scripts/run_v02.py --tier confirmatory --config configs/v02_confirmatory.yaml --outdir outputs/v02_confirmatory_fresh --pilot-dir outputs/v02_pilot_fresh
```

只有 pilot 的 pre-shock success/safe-option 门禁、输出完整性和 seed-level 统计都通过后，
才可运行 `configs/v02_confirmatory.yaml`，使用 50 个新的 seed。
confirmatory 的配置一经开始不可再根据其数据修改。

v0.2 的主检验是 Full-RFL−Immediate 的 AE、actual-update F1、受保护模块的 CKD、
RecoveryEpisodes，并对四项主检验做 seed-level 10,000 次 paired sign-flip、10,000 次
paired bootstrap、Cohen d_z 和 Holm 校正。学习效用另外报告 Full-RFL−Standard 的
online AUC、EpisodesTo90 和最终成功率非劣性；绝不把 episode 当作独立 p-value 样本。

合法结论包括：AE 改善但 F1 不改善；F1 改善但 CKD 不改善；CKD/恢复改善但没有
policy utility；或完整链条均改善。前三种都是结果，不应事后改环境“跑出优势”。

## 复现命令序列（S13 审计路径）

```bash
# 1. v0.1 历史环境与场景（现有 smoke 入口已由 smoke_v02.py 替代）
python scripts/generate_scenarios.py --smoke --per-cause 5
python scripts/generate_calibration.py --smoke --per-cause 10

# 2. Experiment A：smoke -> pilot -> confirmatory
python scripts/experiment_a.py --smoke --seeds 5
python scripts/run_pilot.py --experiment A
python scripts/analyze.py --pilot --dir outputs/pilot_a
python scripts/run_confirmatory.py --experiment A
python scripts/analyze.py --confirmatory --dir outputs/confirmatory_a

# 3. Experiment B：sanity ladder -> pilot
python scripts/experiment_b.py --stage B0 --smoke
python scripts/experiment_b.py --stage B1 --smoke
python scripts/experiment_b.py --stage B2 --smoke
python scripts/benchmark.py --steps 100000
python scripts/run_pilot.py --experiment B --stage B3
python scripts/run_pilot.py --experiment B --stage B4
```

## 已记录的 pilot 期环境属性（非 bug）

1. **E-only 的 ΔL 结构性泄漏**：monster 追 agent 的几何使 dash 撞点总在 goal 前，
   agent 换任一早期低层动作即可避开 → E-only 轨迹与 L 存在固有耦合，oracle R* ≈
   (0, 0.5, 0.5)。处理：接受"E 主导"轨迹；calibration 的 E 模板按 oracle R* 加权
   软计数进入 L/E 矩阵；Experiment A 的 AE 用 oracle R*（mixed）作为 ground truth。
2. **B0/B3/B4 需要足够训练量**：tabular Q 在 3000 episodes 时 B3 仅 0.30，5000
   episodes 达 0.98；smoke/confirmatory 统一使用 pilot grid 内的 5000 episodes。
3. **sequence 模型 H 清晰、L/E 区分弱**（共享安全路线结构），CF 验证承担主要区分
   职责——这是 Experiment A 中 Full-RFL vs PE-Seq 差异的预期来源。

## 目录

```
src/rflcc/         核心库（types/noise/env/trace/policies/scenarios/feedback/
                   sequence/qtables/replay/counterfactual/oracle/attribution/
                   router/metrics/logging_io/stats/plots + baselines/*）
scripts/           smoke/benchmark/generate_*/experiment_*/run_pilot/
                   run_confirmatory/analyze
tests/             pytest 全套（含防泄漏、eval 只读、统计定义）
configs/           smoke/pilot_a/pilot_b/confirmatory_a/confirmatory_b
schemas/           episode.schema.json（additionalProperties: false）
docs/              本规范
legacy/            旧实验归档说明（附件未含旧脚本）
```
