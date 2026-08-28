# 变更记录

## v0.1.0 (2026-08-28)

- 建立模块化工程骨架（src layout、configs、tests、scripts）。
- 实现完全确定性的 NoiseTape（lane / tie-break / dash 全部预采样）。
- 实现 9x7 CausalChase 环境：固定动力学、snapshot/restore、
  ROUTE_PROGRESS/DEVIATE 按 shortest-path distance 定义、事件语义。
- 实现 scripted route follower、exhaustive OracleEvaluator、
  H/L/E single-cause ScenarioGenerator（搜索 + oracle acceptance）。
- 实现 pairwise sequence model（Beta smoothing、正确符号 G_k）、
  log-space feedback fusion、q_pre、纯函数 responsibility inference。
- 实现 learner CounterfactualRunner（Top-2、W_CF=3）与防泄漏测试。
- 实现 Full-RFL / Immediate / PE-Seq / CF-only / Oracle-upper baselines
  与 Experiment A 指标（AE、WUR、UpdateCoverage、FFCR）。
- 实现 Tabular Q（Q_H 每 episode MC 更新、Q_L 在线 TD）、
  Standard-HQ、sanity ladder B0/B1/B2/B3/B4 入口。
- 实现 Router（rho_H=-R_H, rho_L=-R_L, last-action routing）、
  ER-5（task-transition replay，归因冻结）、ReplayBuffer。
- 实现 seed-level paired statistics（sign-flip permutation、
  bootstrap、Cohen d_z、Holm）、plots、analyze。
- 实现 pilot / confirmatory runner（resume、config/commit hash 记录）。
- 新增 schemas/episode.schema.json，JSONL 日志分区 learner/evaluator。
