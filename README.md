# RFL-CausalChase

最小可复现表格式强化反馈学习（Reinforcement Learning from Feedback）实验系统。
完整规范见 [`docs/RFL_CausalChase_v0_1_SPEC.md`](docs/RFL_CausalChase_v0_1_SPEC.md)。

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

v0.2 保留 v0.1 的表格式环境和归因算法，不增加 DQN、Shapley 或新模型。它只检验
`R* → R → 实际 ΔQ → knowledge margin → recovery/learning` 这条链。诊断更新的冻结
语义是 `ΔQ_H=-alpha_diag*R_H`、`ΔQ_L=-alpha_diag*R_L`；每一次实际写 Q 都有
before/after/delta 收据。

新实验只写入新的 `outputs/v02_*` 目录。特别地，`outputs/confirmatory_a/` 与
`outputs/pilot_b/` 是 v0.1 历史证据，不会被 v0.2 命令覆盖或混入分析。

严格执行顺序如下。每一步失败都应保留其新输出作为审计材料，并停止下一步，而不是
删除失败 seed 或用结果调参。

```bash
# 1. 源码与有界 smoke；smoke 每次创建新的 outputs/v02_smoke_* 目录
python -m pytest -q
python scripts/smoke_v02.py --config configs/v02_smoke.yaml --stage all

# 2. pilot 之前保存可复现性封套（环境、依赖、commit、config hash、seed manifest）
python scripts/capture_v02_reproducibility.py --config configs/v02_pilot.yaml --outdir outputs/v02_reproducibility_pilot

# 3. 12-seed pilot：先 A，再 common checkpoint → shock → 真 recovery，最后 online
python scripts/experiment_a_v02.py --config configs/v02_pilot.yaml --stage all --outdir outputs/v02_pilot_current/a
python scripts/experiment_b_v02.py --config configs/v02_pilot.yaml --stage transfer --outdir outputs/v02_pilot_current/b_transfer
python scripts/experiment_b_v02.py --config configs/v02_pilot.yaml --stage online --outdir outputs/v02_pilot_current/b_online
python scripts/analyze_v02.py --dir outputs/v02_pilot_current
```

只有 pilot 的 pre-shock success/safe-option 门禁、输出完整性和 seed-level 统计都通过后，
才可把同一命令中的配置替换为 `configs/v02_confirmatory.yaml`，使用 50 个新的 seed。
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
