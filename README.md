# RFL-CausalChase v0.4 — Credit-unit and Repair Semantics

本分支是项目的**当前主线**。表格式（tabular）强化反馈学习实验系统，CPU-only，
无神经网络，全部随机性由预采样 `NoiseTape` 固定，统计单位是 **seed**（一个 seed
= 一次完整独立训练跑）。

> **默认分支 `master` 停在 v0.2。** 本分支（`v0.4`）包含 v0.3 与 v0.4 的全部工作。

---

## 结论入口

### 👉 [`docs/FROZEN_RESULTS_400.md`](docs/FROZEN_RESULTS_400.md)

**这是全项目唯一的确认性文档。** 其余所有结果文件顶部都标有 `EXPLORATORY — NOT
EVIDENCE`，只作为探索过程的记录保留（旧数字在新协议下移动了多少，本身就是结果）。

---

## 核心结论（N = 400，四个不重叠 100-seed block）

### 1. 难度扫描六档中，只有一个真发现

| setting | ΔAUC (oracle − traditional) | 判定 |
|---|---:|---|
| **`tight_h5_a03`** | **−0.08275** | **`SUPPORT_B` — 四个 block 全部为负** |
| `tight_h5_a10` | −0.01480 | `INCONCLUSIVE` |
| `base_h8_a01` | −0.00656 | `EQUIVALENT` |
| `tight_h6_a10` | +0.00477 | `EQUIVALENT` |
| `base_h8_a03` | −0.00294 | `EQUIVALENT` |
| `base_h8_a10` | +0.00265 | `EQUIVALENT`（block 间符号相反） |

Oracle 的 innocent-module KnowledgeDamage 在六档中**全部恰好为 0.00000**——这是结构性
的，任何 seed 数都改不了。

### 2. 直接修补 Q-entry 不是合适的 update primitive

| | SuccessAUC |
|---|---:|
| `CFRevalue`（Oracle site + Oracle target + 反事实价值） | **0.8509** |
| `NoCorrection`（完全不更新） | **0.9432** |

Δ = **−0.0923**。这是全项目最稳健的结果（`Contrastive − NegativeOnly` = −0.01414，
CI 宽 0.0060，Wilcoxon p = 3e−16，PoI = 0.000）。计划预注册的强否证条件成立。

### 3. 粒度消除 collateral，但代价是 within-module damage

`DecisionOracle` vs `ModuleOracle`：collateral **0.4352 → 0.0000**（结构性、精确），
编辑次数少 **2.67 倍**，但 WMD **+57.7%**（稳健：304/395 个非并列 seed 为正）。

**效用对比是 `INCONCLUSIVE`，不是"中性"**：均值 +0.00815，但 median 为 0、trimmed
mean 为 −0.00494、278 个非并列 seed 里 **191 个是负的**，均值有 **76% 来自 5 个 seed**。

---

## 方法学：为什么需要冻结协议

项目早期用的是"结论变了就加 seed"（12 → 100 → 200 → 300），**这本身就是
optional stopping**。三份文档记录了这个问题的发现与修正：

| 文档 | 内容 |
|---|---|
| [`docs/SEED_BLOCK_PROTOCOL.md`](docs/SEED_BLOCK_PROTOCOL.md) | 冻结的预注册：$N_{\max}=400$，四个不重叠 100-seed block。结论由 CI 相对 $\Delta_{\min}=0.01$ 的位置决定，**不由 $p$ 是否跨过 0.05 决定** |
| [`docs/ROBUSTNESS_AUDIT.md`](docs/ROBUSTNESS_AUDIT.md) | per-seed 配对差值是**零膨胀 + 重尾**的，均值单独不可解释。三条旧结论因此被撤回 |
| [`docs/REVERSAL_LEDGER.md`](docs/REVERSAL_LEDGER.md) | 反转账本：23 条对比里 5 次真反转、**0 次方向改变**；7 次 CI 翻转**全是 no-op** |
| [`docs/V0_4_REPRODUCIBILITY_DEFECT.md`](docs/V0_4_REPRODUCIBILITY_DEFECT.md) | `PYTHONHASHSEED` 导致同一输入下 WMD 有 **3.3 倍**波动。发现后**整套 v0.4 seed 作废并从 N=0 重跑** |

### 四分类判定规则

$$\text{SUPPORT\_A}: L > +\Delta_{\min} \quad|\quad \text{EQUIVALENT}: [L,U] \subset [-\Delta_{\min}, +\Delta_{\min}] \quad|\quad \text{SUPPORT\_B}: U < -\Delta_{\min} \quad|\quad \text{INCONCLUSIVE}: \text{其他}$$

### 两条硬规则

1. **收集 seed 期间绝不允许改算法**——否则 100/200/300/400 不再属于同一个实验分布。
2. **发现 bug 则整套 seed 作废**，修好后从 N=0 重来，不追加、不续跑、不跨变更合并。

第 1 条由 `scripts/src_fingerprint.py` **机械执行**（对 `src/` 做指纹校验，有未提交改动
即拒绝通过），记录在 `docs/PROVENANCE.json`。

---

## 目录结构

```
src/rflv04/      v0.4 实现：env / oracle / credit_units / updates / knowledge / train
src/rflnext/     v0.3 实现：env / labels / runner / metrics / gates / beta / gamma / stage4
scripts/         pilot_*.py（各 pilot）、robustness_audit.py、block_analysis.py、
                 reversal_ledger.py、src_fingerprint.py、v04_ledger.py
configs/         各 pilot 的 yaml 配置
docs/            见上方表格；FROZEN_RESULTS_400.md 是唯一确认性文档
tests/           177 passing
outputs/         每次运行独立目录，从不覆盖；历史 seed 数（6/12/100/200/300）全部保留
```

## 复现

```bash
python -m pip install -e ".[dev]"
python -m pytest -q                       # 177 passed

# 冻结协议的确认性运行（约需数小时）
python scripts/pilot_stage5.py  --config configs/stage5.yaml   --outdir outputs/v03_stage5_400 --seeds 400
python scripts/pilot_v04_alpha.py --config configs/v04_alpha.yaml --outdir outputs/v04_alpha_400 --seeds 400

# 分析
python scripts/block_analysis.py    outputs/v03_stage5_400
python scripts/robustness_audit.py  outputs/v04_alpha_400 --baseline ModuleOracle
python scripts/reversal_ledger.py
```

## Pilot Delta — 有意未运行

Delta 需要训练一个学习式归因器（`p_whole, p_plan, p_decision, p_execution, p_U`，
带独立 unknown 通道，8,000/2,000/4,000 语料）。**结果不支持跑它**：Alpha、Beta、
Gamma 三者否定的是**同一个东西**——诊断式更新本身。拿一个学习式归因器去对接一个
已被证明为净负的消费端，是在测量归因质量对着一个坏掉的消费者，正是计划自己的决策树
警告的顺序错误（*Oracle 失败时不训练更复杂 attribution model*）。

## 已知未修复缺陷

记录在 [`docs/V0_4_REPRODUCIBILITY_DEFECT.md`](docs/V0_4_REPRODUCIBILITY_DEFECT.md) §8，
留给 v0.5。最严重的一条：`scene_from_trace` 用**已实现动作**定位关键决策，导致
`WholeProcess` 占 68.4% 很可能是重构 artifact，而非真有那么多多故障回合。
