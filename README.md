# RFL-Rebuild — frozen research specification

本分支（`rebuild`）是**重构系列**。表格式（tabular）强化反馈学习实验系统，CPU-only，
单进程，无神经网络，全部随机性由预采样 `NoiseTape` 固定。

> ## 🚧 规范已冻结，实现尚未开始
>
> **本目录里没有任何结果，只有设计。** 实现顺序与门禁见
> [`docs/rebuild/00-INDEX.md`](docs/rebuild/00-INDEX.md)。

## 为什么要重构

旧系列（v0.1–v0.4）完整保留在 tag 下，没有删除。它最大的实验设计错误是：

$$\boxed{\text{一次实验同时混进了好几层问题}}$$

归因准不准、责任单位对不对、更新位置对不对、更新目标对不对、训练够不够、策略有没有变好——
全部压进一个 AUC。结果坏了不知道哪一层坏；结果好了也不知道该归功于哪一层。三条结论被迫
撤回，其中一条是 headline。

重构的核心是**每版只攻一箭**：

$$\boxed{\text{V0.1R}:\ \text{证据} \to \text{原因推断}}$$
$$\boxed{\text{V0.2R}:\ \text{原因真值} \to \text{credit 表示}}$$
$$\boxed{\text{V0.3R}:\ \text{credit 真值} \to \text{repair primitive}}$$
$$\boxed{\text{V0.4R}:\ \text{学习式 RFL} \to \text{端到端学习}}$$

每一版都以上一版通过门禁为前提，且**失败只有一种解释**。

## 规范入口

| # | 文档 | 冻结的内容 |
|---|---|---|
| 00 | [`docs/rebuild/00-INDEX.md`](docs/rebuild/00-INDEX.md) | 总览、门禁链、四版链条、决策对照表 |
| 01 | [`01-OBSERVATION-MODEL.md`](docs/rebuild/01-OBSERVATION-MODEL.md) | $a^{policy}\to a^{cmd}\to a^{realized}$；观测什么、隐藏什么 |
| 02 | [`02-SCM.md`](docs/rebuild/02-SCM.md) | 五个潜因、$\lvert\mathcal Z\rvert=4$、干预格、只许前向生成 |
| 03 | [`03-IDENTIFIABILITY.md`](docs/rebuild/03-IDENTIFIABILITY.md) | 可识别性矩阵、Gate E / Gate L |
| 04 | [`04-SEMANTIC-INVARIANTS.md`](docs/rebuild/04-SEMANTIC-INVARIANTS.md) | 不变量 I1–I6、用例套件 C0–C8 |
| 05 | [`05-STATISTICAL-PROTOCOL.md`](docs/rebuild/05-STATISTICAL-PROTOCOL.md) | 分层、block、四分类判定、$T$ 冻结、RMST |
| 06–09 | [`06-V01R.md`](docs/rebuild/06-V01R.md) · [`07-V02R.md`](docs/rebuild/07-V02R.md) · [`08-V03R.md`](docs/rebuild/08-V03R.md) · [`09-V04R.md`](docs/rebuild/09-V04R.md) | 每版唯一主假设、arms、终点、go/no-go |
| 10 | [`10-REPRODUCIBILITY-AND-OPS.md`](docs/rebuild/10-REPRODUCIBILITY-AND-OPS.md) | 确定性、指纹、运行时校准、产物布局 |

## 四条最重要的规则

$$\boxed{\text{1. 收集 seed 期间绝不改算法}}$$
$$\boxed{\text{2. 收集后发现 bug，整套 seed 作废，从 } N=0 \text{ 重来}}$$
$$\boxed{\text{3. contrast 的分层在收集前冻结，之后不得升级}}$$
$$\boxed{\text{4. 先看 per-seed 分布，再看均值}}$$

## 旧系列的定位

旧工作以 annotated tag 保留：`legacy-v0.1` / `legacy-v0.2` / `legacy-v0.3` /
`legacy-v0.4.1`。其中三份文档在新系列里仍然准确且必要：
`docs/ROBUSTNESS_AUDIT.md`、`docs/REVERSAL_LEDGER.md`、
`docs/V0_4_SEMANTIC_CORRECTIONS.md`。

$$\boxed{\text{旧系列真正的产出，是"该怎么测"的规范。}}$$

---

<details>
<summary>旧 v0.4 分支的 README（历史，作为探索记录保留）</summary>

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

### 2. ~~直接修补 Q-entry 不是合适的 update primitive~~ —— 已撤回

| | SuccessAUC |
|---|---:|
| `CFRevalue`（**如当前实现**） | **0.8509** |
| `NoCorrection`（完全不更新） | **0.9432** |

Δ = **−0.0923**，数字是真的。**但从它推出的结论不成立。**

`train.py:355-366` 把反事实回报写进了**事实站点**——也就是那个导致失败的动作——而不是
备选动作：`alt_targets` 构造出来后在该路径上**从未被读取**。由于 `env.py:236` 在修补
成功时给出 `return_value = +1.0`，这个 arm 实际做的是

$$Q(s, a_{\text{bad}}) \leftarrow Q(s, a_{\text{bad}}) + \alpha\,(1.0 - Q(s, a_{\text{bad}}))$$

**它在抬高那个导致失败的动作**，而且恰好发生在修补成功的那些 episode 上。

所以 `CFRevalue` 不是 spec 声称的 ceiling arm，而是 `NegativeOnly` 加上一个符号反转。
**幸存的说法**：把反事实回报写进事实失败动作是有害的。**不成立的说法**：任何关于
*瞄准正确* 的 Q-entry 修补的断言——v0.4 里没有任何 arm 实现它。计划预注册的强否证
条件**没有触发**，ceiling 问题仍然开放。

详见 [`docs/V0_4_SEMANTIC_CORRECTIONS.md`](docs/V0_4_SEMANTIC_CORRECTIONS.md)。

> **同一份收口文档里的另外三处：** `DECISION`/`EXECUTION` 名字不同但写**同一张 Q 表**，
> 所以 Pilot Alpha 不是干净的 credit-unit 分解；Oracle 的 `WholeProcess` 占 68.4%
> 主要是**重构 artifact**（`scene_from_trace` 用 realized 而非 intent 定位决策故障）；
> Pilot Gamma 的 interaction 统计**把每个观测放进去两遍**、CI 窄了 2.2–2.5 倍，按 seed
> 重算后 `NegativeOnly: reward B−A` 从 `SUPPORT_B` 变为 **`INCONCLUSIVE`**。

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

---

**以上为历史内容。** 这些缺陷不会在旧代码上打补丁 —— 它们已经被写进
[`docs/rebuild/`](docs/rebuild/00-INDEX.md) 的规范里，由新系列从零实现：
`scene_from_trace` 那类"从轨迹反推原因"的做法在新 SCM 中被结构性禁止
（`02-SCM.md` §6，只许前向生成），`DECISION`/`EXECUTION` 共写同一张表被提升为全局
不变量 I1（`04-SEMANTIC-INVARIANTS.md`），而那个错误的 CFRevalue 被
`08-V03R.md` §3.2 的 `CFTarget` 取代 —— 反事实回报只能写到真正产生它的动作上。

</details>

