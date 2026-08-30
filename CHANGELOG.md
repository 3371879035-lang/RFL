# 变更记录

## v0.2.0 (进行中)

- 将 diagnostic auxiliary Q update 冻结为缩放的 additive 语义，并为每个实际 Q 写入
  记录 `AppliedUpdate(before, after, delta_q)` 收据。
- 新增 actual-update precision/recall/F1、actual WUR、CKD、WKR、三 checkpoint
  RecoveryEpisodes，以及四类 acceptance-filtered knowledge shocks。
- 新增 A-v0.2 attribution/update 入口：每个方法从同一 Q snapshot 开始，shock 阶段
  禁用 task Q update；Oracle-Update 明确只作为 evaluator-side upper bound。
- 新增 B-v0.2 common checkpoint、哈希 clone、pre-shock success/safe-option 硬门禁、
  真正 task-reward recovery 和从头 online 曲线（含 episode 0）。
- 新增严格 smoke、输出完整性验证、可复现性封套、seed manifest 与按 seed 续跑保护；
  新结果只写入新的 `outputs/v02_*` 路径。
- 新增 seed-level v0.2 分析入口；主终点使用 paired sign-flip、bootstrap、Cohen d_z、
  Holm，而非 episode-level p-value。

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

## 运行记录（2026-08-28）

- Experiment A pilot（12 seeds）：symmetric AE Full-RFL−Immediate = −0.279 (p<0.001)。
- Experiment A confirmatory（50 seeds）：symmetric AE diff = −0.272 (dz=−5.72, p<0.001,
  CI 不跨 0)，预注册 AE 门槛 PASS；WUR diff = −0.026（幅度未达 −0.10，E-only mixed R*
  稀释 + Immediate 不更新逃避，见 outputs/RESULTS.md）。
- Experiment B sanity ladder：B0/B1/B2/B3/B4 全部 PASS（5000 episodes）。
- 修复：confirmatory 多 seed 日志追加、seed_idx 绝对索引、yaml utf-8 编码、BFS 距离
  预计算（env 55k steps/s、cf 101k steps/s）。
