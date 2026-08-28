# RFL-CausalChase-v0.1

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

## 复现命令序列（S13 审计路径）

```bash
# 1. 环境与场景
python scripts/smoke.py --stage env
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
