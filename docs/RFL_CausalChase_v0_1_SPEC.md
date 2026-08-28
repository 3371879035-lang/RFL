# RFL-CausalChase-v0.1：面向 GPT-5.3-Codex-Spark 的最小可复现实验修复、实现与验证规范

## Executive Summary 与快速修复清单

本规范的目标不是继续“修补旧脚本直到它能跑出漂亮数字”，而是把当前 `RFL-CausalChase-v0` **重构成一个能够回答明确科学问题、能够被单元测试锁死、能够逐阶段失败并回滚的实验系统**。

现有单文件实现已经暴露出足以使此前正式结果失效的问题：最终 50-seed 评估中所有方法任务成功率均为 0，而 AE/WUR 又在评估阶段被代码路径直接保留为初始化值；与此同时，Full-RFL 实际读取了 oracle counterfactual 结果，sequence explanatory gain 符号反向，高层和低层反事实没有按照原研究定义执行，calibration 也没有生成干净的 H/L/E 单因轨迹。此前多轮实验记录也显示，这个项目过早从“最小验证”跳到了 50-seed 正式规模。fileciteturn0file0 fileciteturn0file1 fileciteturn0file2

因此，本规范将整个项目拆成两个**逻辑独立、顺序执行**的实验：

\[
\boxed{
\text{Experiment A：先证明 RFL 会不会“正确理解反馈”}
}
\]

和

\[
\boxed{
\text{Experiment B：再证明更好的反馈归因会不会改善学习}
}
\]

Experiment A 是 **Attribution Microbenchmark**。它暂时不要求 Q-learning 学会复杂追逃，而是由实验生成器构造并验证 H-only、L-only、E-only 因果轨迹，再人为污染“诊断反馈”，比较 Immediate、PE-Seq、CF-only、Full-RFL 等方法的归因误差。它直接回答：

\[
\boxed{
\text{错误反馈存在时，}
\;
\text{Sequence Evidence + Counterfactual Verification}
\;
\text{能否减少错误归因？}
}
\]

Experiment B 是 **Integrated Tabular Learning**。只有 Experiment A 通过后，才把归因机制接回真正的：

\[
Q_H(s_H,o)
\]

和

\[
Q_L(s_L,a)
\]

并通过逐级 sanity ladder，先证明普通 Tabular Q-learning 自己能够学会环境，再测试：

\[
\boxed{
\text{更正确的归因}
\Rightarrow
\text{更少的错误模块更新}
\Rightarrow
\text{更好的长期任务学习？}
}
\]

这样就不会再次出现“所有算法任务成功率都是 0，却还在比较 RFL 好坏”的不可解释实验。

这一研究定位与已有文献的边界也更清楚。Q-learning 本身适合这里，是因为它是离散状态—动作空间的增量 action-value 方法，计算和更新位置透明；MMRL 2002 已经明确使用 prediction error 的 softmax 形成 responsibility signal，因此 **PE→responsibility 不能作为 RFL 新颖性**；Wurm 2024 已经研究隐藏 decision–outcome mapping 下多个表示并行产生 surprise、累积 evidence 并仲裁；Huh 2026 提供的是基于 pairwise firing order probability 的 sequence likelihood，而不是 causal attribution；Counterfactual Shapley 2026 已经提供更原则化的多原因因果 credit 方向；Parvin 2018 则恰好提醒我们 sensory prediction error 并不能直接代替高层责任判断。citeturn14search0turn7search2turn10view1turn10view0turn10view2turn12search0

因此，第一篇最小论文最稳妥的核心主张应限定为：

> **Feedback information 不应被默认视为 ground truth learning target；在一个完全可审计的 tabular causal environment 中，重新评估内部 sequence evidence 并主动执行受控 counterfactual verification，是否可以降低 misleading diagnostic feedback 导致的错误模块归因和错误更新。**

不是“RFL 发明了 prediction error”，不是“RFL 发明了 replay”，也不是“RFL 首次研究模块 credit”。早在 2003 年，Samejima、Doya 和 Kawato 就已经研究了 modular RL 中的 inter-module credit assignment。RFL-v0.1 真正要增加的是**反馈作为可疑证据 → 验证 → 修正责任 → 再选择性更新**这一闭环。citeturn15search1

OpenAI 对 GPT-5.3-Codex-Spark 的官方描述也恰好支持下面的工程执行方式：Spark 被定位为低延迟、实时编码模型，默认工作方式偏轻量、定向修改，而且官方明确指出它默认不会自动运行测试，除非用户要求。因此下面每一个 Spark 任务都刻意限制可修改文件，并且**强制执行 pytest 和阶段 smoke test**。citeturn7search1

**一页快速修复清单：旧代码不得直接继续跑正式实验。**

| 必修问题 | 当前后果 | v0.1 修复 |
|---|---|---|
| AE/WUR 只在 `train=True` 分支计算 | `train=False` evaluation 时 AE/WUR 伪装成 0 | 归因与 metric 计算和参数更新彻底解耦 |
| ε decay 指数只从 0 到 1 | 训练末期仍约 0.68 随机低层动作 | 显式线性 `start→end` decay |
| \(G_k\) 符号反了 | 越匹配原因模板可能得分越低 | `G[k] = ell[k] - ell_bg` |
| qseq 与 feedback 直接对概率再 softmax | 概率融合数学含义不清 | log-space Bayes-style weighted fusion |
| Full-RFL 直接读取 `oracle_delta` | learner 得到 ground truth，oracle leakage | 独立 `CounterfactualRunner`；Oracle 只在 evaluator |
| 高层 CF 换 option 但复用旧 action sequence | 没有真正测试“换计划” | 换 option 后用 frozen policy **重新生成**后续动作 |
| 低层 oracle 只查前 4 步、WAIT/EAST | “oracle”漏掉绝大多数真实干预 | Oracle exhaustive；learner 才使用窗口限制 |
| H/L/E calibration 共用危险 option | L/E 模板被 H error 污染 | 独立 scenario generator + oracle acceptance filter |
| `ROUTE_DEVIATE = 尚未到 waypoint` | 正确向 waypoint 前进也被判 deviation | 比较 action 前后 shortest-path distance |
| Timeout 当 causal failure 训练 | 探索不足也被硬归 H/L/E | v0.1 diagnostic update 只针对 COLLISION/显式因果失败 |
| task Q 在整回合后才 forward 更新 | 与原在线 Q-learning 规格不符 | 每一步 `env.step` 后立即 QL TD update |
| \(d_z\) 乘了 \(\sqrt n\) | 实际算成接近 paired-t statistic | \(d_z=\bar d/s_d\)；t 与 \(d_z\) 分开 |
| 状态包含冗余 lane/waypoint 等 | tabular 稀疏性远高于预期 | B 阶段逐级控制状态复杂度 |
| 旧 ER-5 主要重复 diagnostic update | 不是公平的 ordinary replay | B 中真正 replay task transitions，归因冻结 |
| evaluation 与 learning 共用逻辑副作用 | 指标评估可能改变 Q/sequence | `evaluate()` 保证所有模型 bitwise unchanged |

这些问题都可以从当前脚本和旧运行记录中直接对应到此前的异常结果，因此旧结果只能被保留为“故障实验的审计记录”，**不得进入论文 Results**。fileciteturn0file0

关键修复代码片段必须接近以下形式：

```python
# 错误做法：
if train and failure:
    attribution = ...
    ae = ...
    wur = ...
    apply_update(...)

# 正确做法：
if diagnostic_failure:
    attribution = attribution_engine.attribute(...)
    metrics = compute_attribution_metrics(
        responsibility=attribution.responsibility,
        oracle_r=oracle_result.responsibility,  # evaluator only
        proposed_aux_updates=proposed_aux_updates,
    )

    if train:
        update_router.apply(proposed_aux_updates)
```

```python
def linear_epsilon(
    episode: int,
    start: float = 0.20,
    end: float = 0.02,
    decay_episodes: int = 3000,
) -> float:
    frac = min(max(episode / decay_episodes, 0.0), 1.0)
    return start + frac * (end - start)
```

```python
# 正确的 explanatory gain
# E_k = -ell_k
# G_k = E_0 - E_k = ell_k - ell_0
G = {cause: ell[cause] - ell_background for cause in CAUSES}
```

```python
# 不要对 q_seq * likelihood 再做错误的 probability-space softmax。
log_q_pre = {
    c: math.log(q_seq[c] + 1e-12)
       + feedback_weight * math.log(feedback_likelihood[c] + 1e-12)
    for c in CAUSES
}
q_pre = softmax(log_q_pre, tau=1.0)
```

```python
# ROUTE_DEVIATE：比较动作前后到当前 waypoint 的最短路距离。
d_before = shortest_path_distance(agent_xy_before, waypoint)
d_after = shortest_path_distance(agent_xy_after, waypoint)

if d_after < d_before:
    emit("ROUTE_PROGRESS")
elif d_after > d_before:
    emit("ROUTE_DEVIATE")
# equal: 不发 route token
```

```python
# Cohen's dz
diff = candidate - baseline
dz = diff.mean() / diff.std(ddof=1)

# paired t statistic 如需报告，单独计算
t_stat = dz * math.sqrt(len(diff))
```

```python
# Full-RFL learner 的接口里绝对不能出现 oracle_delta / oracle_R
result = counterfactual_runner.verify(
    trace=trace,
    candidates=top2,
    policy_snapshot=policy_snapshot,
    noise_tape=trace.noise_tape,
)

# Oracle 只能由 evaluation pipeline 调用：
oracle = oracle_evaluator.evaluate_exhaustive(...)
```

## 科学问题、文献边界与可验证假设

RFL-v0.1 需要把“论文思想”和“已有方法积木”明确拆开。Options 允许 RL 把 primitive action 扩展成持续一段时间的 closed-loop action，因此我们可以合理地把上/下路线称为 `high-level option` 或 `plan-like route intention`；但不能写成“Q-learning 自然拥有类人的计划能力”。citeturn8search7turn11search0

Dyna 更早已经把 learning、planning 与 reactive execution 放入统一架构，而且执行端可以完全 reactive。因此“快反应 + 慢 planning”本身也不是 RFL-v0.1 的创新。当前版本不实现 fast/slow controller；以后真正值得研究的是 fast controller/shield 改写动作后：

\[
a_t^{proposed}\neq a_t^{executed}
\]

反馈应该如何在 policy、fast controller、environment 之间重新分配 responsibility。citeturn13search0

MMRL 2002 已经有：

\[
\text{prediction error}
\rightarrow
\text{responsibility signal}
\]

并使用该 signal 对不同模块输出以及学习进行 gating；其离散实验甚至包含 nonstationary grid-world hunting task。因此我们的 PE-Seq 必须被定位成**已有 PE/responsibility 思想的强基线或扩展**，不能被包装成原创起点。citeturn7search2

Wurm 2024 更接近我们的 structural-credit 问题：多个候选 decision–outcome representation 并行学习，各自产生 prediction error，absolute PE 被解释为 surprise，然后 surprise 差形成 evidence，并随试次积累，逐渐把 action arbitration 转向更能降低 surprise 的 representation。RFL 可以借这一原则把 sequence score 看作“候选结构证据”，但仍然需要额外验证来决定 causal responsibility。citeturn9search3

Huh 2026 的方法从主动行为期间的 pairwise firing order probabilities 构造 ordered probability matrix，再据此计算 candidate replay sequence 的 log-likelihood；Nature 原文明确说明其核心是 pairwise ordering statistics 和 sequence-likelihood replay identification。我们只迁移“低阶 pairwise sequential template”这一思想，**绝不能写成 Huh 已经提供了 causal attribution 算法**。citeturn10view0

Counterfactual Shapley 2026 针对的是更原则化的 causal credit：区分 policy skill 与 environmental stochasticity/luck，并使用 counterfactual Shapley value 分配因果贡献。RFL-v0.1 不应该一开始就实现完整 Shapley；我们采用简单 normalized counterfactual improvement 作为可审计 oracle，后续如果 v0.1 成立，再把 Oracle/ground truth 替换成 \(\phi\)-value 是自然升级路线。citeturn10view2

Parvin 2018 则提供了一个特别重要的边界条件：他们直接比较 sensory prediction error 与 agency 对“失败应该归给选择还是执行”的影响，结果没有支持 SPE 直接决定后续强化学习 choice update，而是 agency/因果信念起到更关键作用。这并不“证明 RFL”，但非常适合支持我们的设计原则：

\[
\boxed{
PredictionError
\neq
FinalCausalResponsibility
}
\]

citeturn12search0

因此论文应预注册两个核心假设。

**Experiment A 主假设**

在由相同 causal trace 生成、只改变 diagnostic feedback reliability 的条件下：

\[
AE_{\text{Full-RFL}}
<
AE_{\text{Immediate}}
\]

以及：

\[
WUR_{\text{Full-RFL}}
<
WUR_{\text{Immediate}}
\]

特别是在：

\[
p_{false}=0.4
\]

下差异应明显扩大。

这里：

\[
AE
=
\frac12
\sum_{k\in\{H,L,E\}}
|R_k-R_k^\star|
\]

是 responsibility distribution 的 total-variation/L1 attribution error。

Wrong Update Rate 定义为：

\[
WUR=
\frac{
\sum_{m\in\{H,L\}}
u_m(1-R_m^\star)
}{
\sum_{m\in\{H,L\}}u_m+\epsilon
}
\]

其中：

\[
u_m=|\Delta Q_m^{aux}|
\]

表示真正施加到内部模块上的辅助学习强度。

为防止一个算法通过“不更新任何东西”作弊，还必须同时报告：

\[
UpdateCoverage
=
P\left(
\sum_m u_m>\epsilon_u
\right)
\]

以及未归因率：

\[
AbstentionRate.
\]

**Experiment B 主假设**

只有在 Standard-HQ 本身已经学会任务以后，比较：

\[
\text{Full-RFL}
\]

与：

\[
\text{Immediate / ER-5 / PE-Seq}
\]

是否因为更低的错误模块更新而获得：

\[
AUC_{return}\uparrow
\]

\[
SuccessRate\uparrow
\]

或：

\[
EpisodesToThreshold\downarrow.
\]

这一步是：

\[
\boxed{
\text{Attribution improvement}
\rightarrow
\text{Learning improvement}
}
\]

而 Experiment A 只证明前半部分。

**必须预先接受的否证结果**也要写进规范：

如果：

\[
PESeq\approx FullRFL
\]

说明这个环境中 CF verification 没提供足够额外价值。

如果：

\[
CFOnly\approx FullRFL
\]

但 Full-RFL 需要显著更少的 CF transitions，则 sequence 的价值主要是：

\[
\boxed{\text{search prioritization}}
\]

而非提高 causal accuracy。

如果：

\[
Immediate\approx FullRFL
\]

那么当前任务不支持 RFL 核心假设。

如果 Experiment A 成立而 Experiment B 不成立，则说明：

> 更好的责任解释未必自动转化成更好的 tabular policy learning。

这本身也是重要的负结果。

## 环境、数据与数学规范

环境名称固定为：

```text
RFL-CausalChase-v0.1
```

不得在正式 confirmatory run 后修改动力学。

**空间。**

\[
x\in\{0,\ldots,8\},
\qquad
y\in\{0,\ldots,6\}
\]

即：

\[
9\times7
\]

网格。

障碍：

\[
W=
\{3,4,5\}\times\{2,3,4\}.
\]

Agent：

\[
S_A=(1,3)
\]

Goal：

\[
S_G=(7,3).
\]

Monster 初始位置：

\[
S_M=
\begin{cases}
(6,1), & lane=U\\
(6,5), & lane=L
\end{cases}
\]

且：

\[
P(U)=P(L)=0.5.
\]

高层 option：

\[
O=
\{U,L\}.
\]

上路线 waypoint：

\[
U:(2,1)\rightarrow(6,1)\rightarrow(7,3)
\]

下路线：

\[
L:(2,5)\rightarrow(6,5)\rightarrow(7,3).
\]

注意：

> waypoint 只用于 scripted controller、事件定义和 option 语义；不要把它误称为语言式 planning。

**动作：**

```python
ACTIONS = (
    "ACT_N",
    "ACT_S",
    "ACT_E",
    "ACT_W",
    "ACT_WAIT",
)
```

**reward 必须消除旧脚本的“终止奖励 + step penalty”歧义。**

定义为互斥：

\[
r_t=
\begin{cases}
+1.0 & EXIT\\
-1.0 & COLLISION\\
-0.5 & TIMEOUT\\
-0.01 & otherwise
\end{cases}
\]

不允许 EXIT 返回 `0.99`，COLLISION 返回 `-1.01` 这种隐式叠加。

最大 horizon：

\[
H=30.
\]

discount：

\[
\gamma=0.97.
\]

自定义 `step` 即使不用 Gymnasium，也必须分开：

```python
obs, reward, terminated, truncated, info = env.step(action)
```

其中：

```text
terminated = EXIT or COLLISION
truncated  = TIMEOUT
```

v0.1 的 diagnostic attribution 默认只在：

```text
terminal_type == COLLISION
```

时运行。

TIMEOUT 是 task failure，但**不是 v0.1 attribution failure**；暂时不进行 H/L/E auxiliary blame。

**Monster 动力学严格固定。**

一个 agent step 的 canonical 顺序：

```text
agent proposes action
→ agent moves
→ collision check
→ route event
→ if t % monster_move_period == 0:
      monster base move
      collision check
      optional dash move
      collision check
→ distance event
→ EXIT/TIMEOUT check
```

正式环境：

```yaml
monster_move_period: 2
monster_dash_p: 0.10
```

但 Experiment B sanity ladder 可以暂时使用：

```yaml
monster_enabled: false
```

或：

```yaml
monster_move_period: 3
monster_dash_p: 0.0
```

这些必须是**独立 config**，不能偷偷改变 confirmatory 环境。

Monster 每次使用 BFS 朝 Agent 走一步；同长最短路由 NoiseTape tie-break 决定。

**NoiseTape 是 counterfactual 合法性的核心。**

不要保存：

```python
dash_u: list[bool]
```

并在反事实中随意改它。

建议保存原始 exogenous uniform draws：

```python
@dataclass(frozen=True)
class NoiseTape:
    seed: int
    monster_start_lane: int
    tie_break_u: tuple[float, ...]
    dash_u: tuple[float, ...]
```

真实 dash：

```python
do_dash = tape.dash_u[move_idx] < p_dash
```

反事实：

```python
intervention.blocked_dash_indices
```

作为 overlay。

因此：

\[
U=
(
lane,
u^{tie}_1,\ldots,
u^{tie}_n,
u^{dash}_1,\ldots,u^{dash}_m
)
\]

在 factual 与 counterfactual 中完全相同：

\[
\tau=F(\pi,U)
\]

\[
\tau^{do(c)}=F(\pi,U,do(c)).
\]

Counterfactual Shapley 的整体方向同样强调用给定观察轨迹后的反事实世界区分 agent policy contribution 与环境随机性；v0.1 的 NoiseTape 正是为了在小型模拟器里获得一个完全可审计的简化实现。citeturn10view2

**环境接口固定：**

```python
class CausalChaseEnv:
    def reset(
        self,
        *,
        seed: int | None = None,
        noise_tape: NoiseTape | None = None,
        option: int | None = None,
    ) -> tuple[Observation, dict]:
        ...

    def step(
        self,
        action: int,
    ) -> tuple[Observation, float, bool, bool, dict]:
        ...

    def snapshot(self) -> EnvSnapshot:
        ...

    def restore(self, snapshot: EnvSnapshot) -> None:
        ...
```

`EnvSnapshot` 至少包含：

```python
@dataclass(frozen=True)
class EnvSnapshot:
    agent_xy: tuple[int, int]
    monster_xy: tuple[int, int]
    option: int
    step_index: int
    monster_move_index: int
    waypoint_index: int
    terminal_type: str
    terminated: bool
    truncated: bool
    causal_events: tuple["TraceEvent", ...]
```

所有 episode 随机数**只能从 NoiseTape 来**。调用 `restore()` 以后不能重新调用全局 `random`。

**event vocabulary：**

```text
OPT_UPPER
OPT_LOWER

ACT_N
ACT_S
ACT_E
ACT_W
ACT_WAIT

ROUTE_PROGRESS
ROUTE_DEVIATE

MONSTER_NORMAL
MONSTER_DASH

DIST_FAR
DIST_MID
DIST_NEAR

EXIT
COLLISION
TIMEOUT
```

Diagnostic feedback 独立 namespace：

```text
FEEDBACK_H
FEEDBACK_L
FEEDBACK_E
FEEDBACK_UNKNOWN
```

严禁：

\[
FEEDBACK_\*
\in
causal\_events.
\]

`ROUTE_PROGRESS` 不再等价于“到 waypoint 了”，而定义：

\[
d_{after}(agent,waypoint)
<
d_{before}(agent,waypoint).
\]

`ROUTE_DEVIATE`：

\[
d_{after}>
d_{before}.
\]

相同则无 route token。

距离事件按 **monster phase 完成后** 的 BFS distance：

\[
DIST\_NEAR:d\le2
\]

\[
DIST\_MID:3\le d\le4
\]

\[
DIST\_FAR:d\ge5.
\]

事件顺序必须 deterministically 固定，否则 sequence model 会学习日志实现细节而不是环境结构。

**Experiment A 不训练 Q。**

建立：

```python
ScenarioGenerator
```

搜索满足以下条件的单原因轨迹。

H-only：

```text
选择有问题的 high-level route
没有 low-level injected fault
禁用额外 environmental dash fault
switch option 后显著改善
low-level / environment intervention 不显著
```

L-only：

```text
选择安全 route
注入一个 primitive execution fault
删除该 fault 后显著改善
switch option / no-dash 不显著
```

E-only：

```text
安全 option
scripted low-level 正确执行
强制一个 critical dash
block dash 后显著改善
H/L intervention 不显著
```

不要凭几何直觉假设某个固定 step 必然制造干净因果样本，而是**搜索 + Oracle acceptance**：

\[
\Delta_{target}\ge\delta_{pos}
\]

且：

\[
\max_{j\neq target}\Delta_j\le\delta_{leak}.
\]

初始建议：

\[
\delta_{pos}=0.4,
\qquad
\delta_{leak}=0.1.
\]

这些阈值可以在 pilot 调整，但 confirmatory 前必须锁死。

每个 confirmatory seed 生成：

```text
30 H-only
30 L-only
30 E-only
```

即：

\[
90\ traces/seed.
\]

50 seeds：

\[
4500
\]

条**独立 base causal traces**。

false feedback condition 只改变标签，不重新生成环境轨迹，因此所有算法可在完全相同的 factual trace 上配对。

正式主条件：

```text
clean:       p_false = 0.00
symmetric:   p_false = 0.40
```

次级：

```text
symmetric_20: p_false = 0.20
adversarial_planning_blame: p_false = 0.40
```

`p_missing=0.10` 留给 secondary，不进入第一轮主检验。

**Experiment B 的 tabular state。**

高层：

\[
s_H=monster\_start\_lane
\]

\[
Q_H(s_H,o).
\]

高层每 episode 选择一次 option。

低层 final state 不沿用旧脚本的冗余定义。先使用：

\[
s_L=
(x_A,y_A,x_M,y_M,o,t\bmod2).
\]

这样去掉了已经可以由其他变量表达或仅服务日志的：

```text
monster_start_lane
waypoint_index
```

理论组合上界约为：

\[
54\times54\times2\times2
=
11664
\]

个状态，再乘五个动作约 5.8 万 Q 槽位，明显比旧版把多个冗余字段一起塞进 state 后更适合作为 tabular 原理验证。

低层在线 Q-learning：

\[
\delta_t
=
r_t+
\gamma(1-d_t)
\max_{a'}Q_L(s_{t+1},a')
-
Q_L(s_t,a_t)
\]

其中 v0.1 对：

\[
d_t=
terminated\lor truncated
\]

均不 bootstrap。

更新：

\[
Q_L(s_t,a_t)
\leftarrow
Q_L(s_t,a_t)+
\alpha_L\delta_t.
\]

Q-learning 的经典形式及其离散表示条件来自 Watkins 与 Dayan；本实验增加 auxiliary shaping 后不应声称自动继承其经典收敛证明。citeturn14search0

高层 episodic return：

\[
G_0=
\sum_{t=0}^{T-1}
\gamma^tr_t.
\]

更新：

\[
Q_H(s_H,o)
\leftarrow
Q_H(s_H,o)+
\alpha_H
[
G_0-Q_H(s_H,o)
].
\]

推荐：

```yaml
alpha_low: 0.20
alpha_high: 0.15
alpha_diag: 0.10
gamma: 0.97
```

ε：

```yaml
epsilon_start: 0.20
epsilon_end: 0.02
epsilon_decay_episodes: 3000
```

并明确：

\[
\epsilon(e)
=
\epsilon_{start}
+
\min(e/D,1)
(\epsilon_{end}-\epsilon_{start}).
\]

evaluation：

\[
\epsilon=0.
\]

evaluation **照常计算 attribution metrics，但绝不更新 Q、sequence matrix 或任何 learner state。**

**Sequence matrix。**

为原因：

\[
k\in\{H,L,E\}
\]

建立：

\[
N_{uv}^{(k)}
=
\#(u\prec v\mid C_k).
\]

对重复 token 的每一对 occurrence：

\[
i<j,\quad x_i=u,x_j=v
\]

计一次；\(u=v\) 不进入方向概率。

Beta smoothing：

\[
A_{uv}^{(k)}
=
\frac{
N_{uv}^{(k)}+\beta
}{
N_{uv}^{(k)}+
N_{vu}^{(k)}
+
2\beta
}
\]

取：

\[
\beta=1.
\]

实现时只计算一个方向，然后：

\[
A_{vu}^{(k)}
=
1-A_{uv}^{(k)}
\]

再 clip：

\[
A\in[0.01,0.99].
\]

Huh 等人的原方法确实使用 active-period pairwise firing-order probability matrix 评估候选 sequence likelihood；但是下面的 event-token scoring 是 **RFL 工程改造**，不是对其神经科学公式的逐字复现。citeturn10view0

定义局部：

\[
L_k^{local}
=
\frac1{n-1}
\sum_{i=1}^{n-1}
\log
A_{x_i,x_{i+1}}^{(k)}
\]

全局：

\[
L_k^{global}
=
\frac1{|\mathcal P|}
\sum_{i<j}
\log
A_{x_i,x_j}^{(k)}.
\]

然后：

\[
\ell_k
=
\eta
L_k^{local}
+
(1-\eta)
L_k^{global}
\]

取：

\[
\eta=0.5.
\]

背景矩阵由校准数据的 H/L/E counts 合并得到：

\[
A^{(0)}.
\]

关键符号：

\[
E_k=-\ell_k
\]

\[
G_k=E_0-E_k
\]

因此：

\[
\boxed{
G_k=\ell_k-\ell_0
}
\]

而不是旧代码中的：

\[
\ell_0-\ell_k.
\]

Sequence responsibility prior：

\[
q_{seq}(k)
=
\operatorname{softmax}
\left[
\frac{
G_k+\log\pi_k
}{
\tau_{seq}
}
\right]
\]

其中：

\[
\pi_H=\pi_L=\pi_E=\frac13,
\qquad
\tau_{seq}=0.5.
\]

它回答：

> “当前事件结构更像哪种 cause template？”

不回答：

> “哪个 cause 已经被证明？”

**diagnostic feedback fusion。**

若：

\[
d=H/L/E
\]

则：

\[
L_d(k)=
\begin{cases}
0.6 & k=d\\
0.2 & k\ne d
\end{cases}.
\]

如果：

\[
d=UNKNOWN
\]

则：

\[
L_d(k)=\frac13.
\]

使用：

\[
\log\tilde q_{pre}(k)
=
\log(q_{seq}(k)+\epsilon)
+
w_d\log L_d(k)
\]

\[
w_d=0.5
\]

再归一化：

\[
q_{pre}
=
softmax(\log\tilde q_{pre}).
\]

这实现的是：

\[
\boxed{
DiagnosticFeedback=WeakEvidence
}
\]

而不是：

\[
DiagnosticFeedback=GroundTruth.
\]

**Counterfactual semantics 必须统一。**

设 factual：

\[
J_0=J(\tau).
\]

高层：

\[
\Delta_H
=
J\left(
\tau^{do(o=o')}
\right)-J_0.
\]

重要：

> 改 option 后不能重放原 action list。

必须从初态开始：

\[
a_t'
=
\pi_L^{frozen}
(s_t',o')
\]

重新产生后续动作，同时保持：

\[
NoiseTape'=NoiseTape.
\]

低层：

\[
\Delta_L
=
\max_{t,a'\ne a_t}
J\left(
\tau^{do(a_t=a')}
\right)-J_0.
\]

在 \(t\) 处只改变该动作，之后恢复：

\[
\pi_L^{frozen}
\]

继续行动，而不是继续强制 factual future action list。

Oracle evaluator：

\[
t=0,\ldots,T-1
\]

且：

\[
a'\in A\setminus\{a_t\}.
\]

Full-RFL learner 为节约成本，只搜：

\[
t\in
\{T-W_{CF},\ldots,T-1\},
\qquad
W_{CF}=3.
\]

环境：

\[
\Delta_E
=
\max_{j\in observed\_dash}
J(\tau^{do(dash_j=0)})-J_0.
\]

阻止第 \(j\) 个 dash 时，不能重排后续 `dash_u` 或 tie-break 序列。

Oracle：

\[
\Delta_k^+
=
\max(0,\Delta_k^\star)
\]

如果：

\[
\sum_k\Delta_k^+
>
0
\]

则：

\[
R_k^\star
=
\frac{
\Delta_k^+
}{
\sum_j\Delta_j^+
}.
\]

否则：

```text
UNRESOLVED
```

而不是旧代码的：

\[
(1/3,1/3,1/3).
\]

这是非常重要的修改：**证据不足不等于三种原因等概率真实。**

对于 A 的 H/L/E isolated dataset，接受过滤器会尽量使：

\[
R^\star\approx one\_hot(cause).
\]

未来 mixed-cause 才使用 normalized \(\Delta\)。完整 Shapley 留到 v1，因为多因素 interaction 时单变量 counterfactual 并不提供 Shapley 意义上的公平联合责任分配。Counterfactual Shapley 2026 正是为更原则化的多因素 causal credit 提供路线。citeturn10view2

**Full-RFL final responsibility。**

选：

\[
TopK(q_{pre}),\quad K=2.
\]

验证到的 improvement 先缩放：

\[
\bar\Delta_k=
clip
\left(
\frac{\max(0,\Delta_k)}{2},
0,
1
\right).
\]

定义：

\[
s_k=
\log(q_{pre}(k)+\epsilon)
+
\lambda_{CF}\bar\Delta_k
-
\lambda_R
I[
verified_k
\land
\bar\Delta_k<\delta_{CF}
].
\]

推荐：

\[
\lambda_{CF}=4,
\quad
\lambda_R=2,
\quad
\delta_{CF}=0.05.
\]

最终：

\[
R_k=
\frac{
e^{s_k/\tau_R}
}{
\sum_j e^{s_j/\tau_R}
},
\qquad
\tau_R=1.
\]

注意未验证原因没有被强制设成 0，而保留原有 \(q_{pre}\) 支持；这样 Top-2 搜索失败时仍然能表现出不确定性。

**责任映射。**

原因：

\[
R=(R_H,R_L,R_E).
\]

内部功能只有 High/Low 两个：

\[
B=
\begin{bmatrix}
1&0&0\\
0&1&0
\end{bmatrix}.
\]

collision：

\[
v=-1.
\]

于是：

\[
\rho_H=-R_H,
\qquad
\rho_L=-R_L.
\]

环境 responsibility：

\[
R_E
\]

不直接产生 internal diagnostic punishment。

但环境风险仍通过**标准真实 task Q-learning**进入 value update，因此不是“怪环境就什么都不学”。

Primary B-Core 使用：

\[
Q_H(z_H)
\leftarrow
Q_H(z_H)
+
\alpha_{diag}\rho_H
\]

\[
Q_L(z_L)
\leftarrow
Q_L(z_L)
+
\alpha_{diag}\rho_L.
\]

为了避免把“模块级责任判断”和“模块内部哪个具体 time-step 更新”混成一个创新，在**主分析**中所有方法对 L 都采用同一个预注册 routing rule：

```text
last low-level decision before COLLISION
```

然后另开 secondary ablation：

```text
CF-critical-routing
```

允许 Full-RFL 用：

\[
t_L^\star
=
\arg\max_t\Delta_L(t)
\]

作为真正 update site。

这样论文能分别回答：

\[
\text{哪个模块错？}
\]

和：

\[
\text{模块内部哪一步错？}
\]

而不是一次性把两个优势叠进去。

完整训练核心伪代码：

```text
for run_seed in seeds:

    initialize QH, QL
    load frozen sequence templates

    for episode in training_episodes:

        env_seed      = seed_plan.env_seed(run_seed, episode)
        feedback_seed = seed_plan.feedback_seed(run_seed, episode)

        obs = env.reset(seed=env_seed)

        policy_snapshot = freeze(QH, QL)

        sH = obs.monster_start_lane
        eps = epsilon_schedule(episode)

        option = epsilon_greedy(QH[sH], eps)
        trace.start(option)

        while not terminated_or_truncated:

            s = low_state(obs, option)
            a = epsilon_greedy(QL[s], eps)

            obs2, r, terminated, truncated, info = env.step(a)

            s2 = low_state(obs2, option)

            # 在线真实 task learning
            target = r
            if not (terminated or truncated):
                target += gamma * max_a QL[s2, a]

            QL[s, a] += alpha_low * (target - QL[s, a])

            trace.append(...)

            obs = obs2

        G = discounted_return(trace.rewards)

        # 所有算法共有
        QH[sH, option] += alpha_high * (G - QH[sH, option])

        if trace.terminal_type != "COLLISION":
            log_and_continue()

        observed_feedback = feedback_injector.generate(
            scenario_id=trace.scenario_id,
            seed=feedback_seed,
        )

        # learner inference
        R, proposed_aux = algorithm.attribute_and_route(
            trace=trace,
            feedback=observed_feedback,
            frozen_policy=policy_snapshot,
        )

        # evaluator only；结果绝不能传回 algorithm
        oracle = oracle_evaluator.evaluate(trace, policy_snapshot)

        metrics = compute_metrics(
            R=R,
            R_star=oracle.R,
            proposed_aux_updates=proposed_aux,
        )

        apply_aux_updates_if_training(proposed_aux)

        logger.write(...)
```

evaluation：

```text
freeze QH / QL / SequenceModel
epsilon = 0
repeat paired evaluation scenarios
calculate R / metrics
DO NOT apply task update
DO NOT apply auxiliary update
assert models unchanged
```

## 工程架构、测试、日志、统计与资源规范

不要继续把 v0.1 写成一个 1000 行单文件。旧脚本保留：

```text
legacy/
└── rfl_v0_simple_experiment.py
```

只用于审计。

新结构：

```text
RFL-CausalChase-v0.1/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
│
├── docs/
│   └── RFL_CausalChase_v0_1_SPEC.md
│
├── configs/
│   ├── smoke.yaml
│   ├── pilot_a.yaml
│   ├── pilot_b.yaml
│   ├── confirmatory_a.yaml
│   └── confirmatory_b.yaml
│
├── schemas/
│   └── episode.schema.json
│
├── src/
│   └── rflcc/
│       ├── types.py
│       ├── noise.py
│       ├── env.py
│       ├── trace.py
│       ├── policies.py
│       ├── scenarios.py
│       ├── feedback.py
│       ├── sequence.py
│       ├── qtables.py
│       ├── replay.py
│       ├── counterfactual.py
│       ├── oracle.py
│       ├── attribution.py
│       ├── router.py
│       ├── metrics.py
│       ├── logging_io.py
│       ├── stats.py
│       ├── plots.py
│       │
│       └── baselines/
│           ├── standard.py
│           ├── immediate.py
│           ├── er.py
│           ├── pe_seq.py
│           ├── cf_only.py
│           ├── full_rfl.py
│           └── oracle_upper.py
│
├── scripts/
│   ├── smoke.py
│   ├── benchmark.py
│   ├── generate_calibration.py
│   ├── generate_scenarios.py
│   ├── experiment_a.py
│   ├── experiment_b.py
│   ├── run_pilot.py
│   ├── run_confirmatory.py
│   └── analyze.py
│
├── tests/
│   ├── test_noise_tape.py
│   ├── test_env_determinism.py
│   ├── test_snapshot_restore.py
│   ├── test_event_semantics.py
│   ├── test_scenario_isolation.py
│   ├── test_feedback.py
│   ├── test_sequence.py
│   ├── test_counterfactual.py
│   ├── test_oracle.py
│   ├── test_no_oracle_leakage.py
│   ├── test_metrics.py
│   ├── test_qlearning.py
│   ├── test_router.py
│   ├── test_eval_immutability.py
│   └── test_stats.py
│
└── legacy/
    └── rfl_v0_simple_experiment.py
```

依赖尽量保持：

```text
numpy
pandas
scipy
matplotlib
pyyaml
pytest
```

如果后期要直接输出 parquet，再增加：

```text
pyarrow
```

但 smoke 阶段不必增加。

**关键 pytest 必须包括实际数值断言。**

```python
def test_same_seed_same_actions_identical_trajectory():
    tape1 = NoiseTape.from_seed(123, horizon=30)
    tape2 = NoiseTape.from_seed(123, horizon=30)

    actions = [EAST, EAST, NORTH, WAIT, EAST]

    t1 = rollout(tape1, actions)
    t2 = rollout(tape2, actions)

    assert t1 == t2
```

```python
def test_snapshot_restore_is_exact():
    env = make_env(seed=7)
    env.step(EAST)
    snap = env.snapshot()

    traj_a = rollout_from_current(env, [NORTH, EAST, WAIT])

    env.restore(snap)
    traj_b = rollout_from_current(env, [NORTH, EAST, WAIT])

    assert traj_a == traj_b
```

```python
def test_dash_intervention_preserves_other_noise():
    tape = NoiseTape.from_seed(100, horizon=30)

    cf = InterventionSet(blocked_dash_indices=frozenset({3}))

    assert tape.tie_break_u == tape.tie_break_u
    assert tape.dash_u[0:3] == tape.dash_u[0:3]

    factual = rollout_with_tape(tape)
    counter = rollout_with_tape(tape, interventions=cf)

    assert factual.prefix_before_dash(3) == counter.prefix_before_dash(3)
```

```python
def test_pairwise_complement():
    model = calibrated_sequence_model()

    for cause in CAUSES:
        A = model.matrix(cause)
        for u in range(A.shape[0]):
            for v in range(u + 1, A.shape[1]):
                assert abs((A[u, v] + A[v, u]) - 1.0) < 1e-9
```

```python
def test_explanatory_gain_sign():
    model = synthetic_model_with_clear_h_template()
    trace = synthetic_h_trace()

    result = model.score(trace)

    assert result.ell["H"] > result.ell_background
    assert result.G["H"] > 0
```

```python
def test_sequence_prefers_matching_template():
    result = model.score(synthetic_h_trace())

    assert result.q_seq["H"] > result.q_seq["L"]
    assert result.q_seq["H"] > result.q_seq["E"]
```

```python
def test_feedback_never_enters_causal_sequence():
    trace = build_trace()
    trace.add_feedback("FEEDBACK_H")

    assert "FEEDBACK_H" in [e.token for e in trace.feedback_events]
    assert "FEEDBACK_H" not in [e.token for e in trace.causal_events]
```

```python
def test_false_feedback_extreme():
    injector = FeedbackInjector(p_false=1.0)

    for _ in range(100):
        d = injector.generate(true_primary="L")
        assert d != "L"
```

```python
def test_route_progress_not_deviation():
    # 从 (2,1) 向 waypoint (6,1) EAST 属于正常推进
    before = (2, 1)
    after = (3, 1)
    waypoint = (6, 1)

    event = classify_route_event(before, after, waypoint)

    assert event == "ROUTE_PROGRESS"
```

```python
def test_high_level_cf_regenerates_actions():
    runner = CounterfactualRunner(...)
    result = runner.verify_high(...)

    assert result.alternative_option != result.factual_option
    assert result.actions_regenerated is True
```

```python
def test_oracle_low_level_is_exhaustive():
    result = oracle.evaluate(trace)

    expected_candidates = (
        len(trace.transitions) * (len(ACTIONS) - 1)
    )

    assert result.low_candidates_checked == expected_candidates
```

```python
def test_counterfactual_does_not_mutate_q():
    q_before = deepcopy(agent.q_tables)

    runner.verify(...)

    assert agent.q_tables == q_before
```

最重要的 leakage test：

```python
def test_full_rfl_has_no_oracle_dependency():
    import inspect
    import rflcc.baselines.full_rfl as mod

    src = inspect.getsource(mod)

    forbidden = [
        "OracleEvaluator",
        "oracle_delta",
        "oracle_R",
        "oracle_responsibility",
    ]

    for name in forbidden:
        assert name not in src
```

更严格：

```python
def test_oracle_not_called_during_learner_inference(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("ORACLE LEAKAGE")

    monkeypatch.setattr(
        OracleEvaluator,
        "evaluate",
        explode,
    )

    # Full-RFL attribution 必须正常工作
    full_rfl.attribute(...)
```

AE train/eval bug regression test：

```python
def test_metrics_computed_when_train_false():
    result = run_episode(
        train=False,
        fixed_collision_scenario=True,
    )

    assert result.metrics.attribution_error is not None
    assert result.metrics.wur is not None
```

Evaluation immutability：

```python
def test_evaluation_is_read_only():
    before = deep_hash(
        qh,
        ql,
        sequence_model,
    )

    evaluate(...)

    after = deep_hash(
        qh,
        ql,
        sequence_model,
    )

    assert before == after
```

\(d_z\) test：

```python
def test_cohens_dz_not_t_statistic():
    diff = np.array([1.0, 2.0, 3.0, 4.0])
    expected = diff.mean() / diff.std(ddof=1)

    assert np.isclose(cohens_dz(diff), expected)
```

**日志必须把 learner information 和 evaluator-only information 分区。**

Episode JSON 示例：

```json
{
  "schema_version": "0.1.0",
  "run_id": "A-confirm-2026-08-26",
  "seed": 1042,
  "scenario_id": "H_1042_017",
  "experiment": "A",
  "algorithm": "full_rfl",
  "condition": "symmetric_0.40",

  "environment": {
    "env_seed": 817233,
    "noise_tape_hash": "sha256:...",
    "monster_start_lane": "UPPER",
    "monster_dash_p": 0.10,
    "horizon": 30
  },

  "factual": {
    "option": "UPPER",
    "terminal_type": "COLLISION",
    "discounted_return": -0.92
  },

  "feedback": {
    "observed": "H",
    "is_false": true
  },

  "learner": {
    "q_seq": {
      "H": 0.12,
      "L": 0.73,
      "E": 0.15
    },
    "G": {
      "H": -0.31,
      "L": 1.24,
      "E": 0.08
    },
    "q_pre": {
      "H": 0.25,
      "L": 0.62,
      "E": 0.13
    },
    "cf_checked": ["L", "H"],
    "cf_delta": {
      "H": 0.02,
      "L": 1.52,
      "E": null
    },
    "responsibility": {
      "H": 0.05,
      "L": 0.87,
      "E": 0.08
    },
    "rho_high": -0.05,
    "rho_low": -0.87
  },

  "evaluator_only": {
    "oracle_primary": "L",
    "oracle_R": {
      "H": 0.02,
      "L": 0.91,
      "E": 0.07
    },
    "oracle_delta": {
      "H": 0.03,
      "L": 1.61,
      "E": 0.12
    }
  },

  "metrics": {
    "attribution_l1": 0.04,
    "wur": 0.08,
    "wrong_update": false,
    "update_coverage": true,
    "false_feedback_compliance": false
  },

  "compute": {
    "real_transitions": 13,
    "cf_rollouts": 9,
    "cf_transitions": 102,
    "wall_ms": 7.2
  }
}
```

JSON schema 必须规定：

```text
additionalProperties: false
```

至少在顶层和 `learner`、`evaluator_only` 中采用，从而避免 Spark 悄悄往 learner 数据结构里塞 oracle 字段。

原始 event 单独写：

```text
logs/events.jsonl.gz
```

episode summary：

```text
logs/episodes.jsonl
```

seed-level aggregation：

```text
results/seed_metrics.csv
```

正式统计：

```text
results/statistics.csv
```

**Experiment A 对照。**

Primary：

| 方法 | Sequence | External feedback | CF | 含义 |
|---|---:|---:|---:|---|
| Immediate | × | ✓ | × | 直接相信反馈 |
| PE-Seq | ✓ | ✓ | × | sequence + weak feedback |
| CF-only | × | × | exhaustive | 纯 CF 强基线 |
| Full-RFL | ✓ | ✓ | Top-2 | 排序后选择性验证 |
| Oracle | × | × | exhaustive ground truth | 上界 |

在 Experiment A 中，ordinary experience replay 本质上没有 policy-learning transition 可改善，重复一条固定 trace 不会自然产生新的 attribution。因此 ER-5 在 A 中只能作为“Frozen-Attribution Replay”负对照，不应该被夸大成主要 baseline。

**Experiment B 对照。**

正式保留：

```text
Standard-HQ
Immediate
ER-5
PE-Seq
CF-only
Full-RFL
Oracle-upper
```

Standard-HQ：

```text
真实 task Q-learning
无 diagnostic auxiliary update
```

Immediate：

```text
task Q
+
直接 one-hot diagnostic auxiliary update
```

ER-5：

```text
task Q
+
普通 task-transition replay
+
原始 attribution 冻结
+
不重新运行 sequence/counterfactual attribution
```

为避免 ER 单纯拥有 5 倍 task update budget，在主 task-performance comparison 还应同时报告：

```text
Real transitions
Replay updates
Total Bellman updates
```

必要时增加：

```text
Matched-Update-Budget
```

对照，以排除“谁多算了几次 Bellman update 谁就赢”。

**核心 ablation。**

不要一次做几十个。

第一篇只做：

```text
Full-RFL
- Sequence
- Counterfactual Verification
- External Feedback
- Calibration
Top-1 vs Top-2 vs Exhaustive-CF
```

其中：

```text
- Counterfactual Verification
```

实际上就是 PE-Seq。

```text
- Sequence
```

使用 feedback prior + CF。

```text
- External Feedback
```

只使用 sequence + CF。

```text
- Calibration
```

退化为 uniform sequence evidence。

这里不建议声称“Diagnostic Replay 本身”有独立 ablation，因为在 v0.1 中 trace 是软件精确存储的；重新打开 trace 并计算 attribution 是架构步骤，但没有 memory corruption 时，replay 本身不是一个独立的认知变量。Huh 2026 真正有价值的 replay identity/detection 部分应留到以后故意加入 event dropout、permutation、episode mixing 的版本。citeturn10view0

**统计单位固定为 seed。**

Pilot：

\[
N_{pilot}=12
\]

可在：

\[
10\sim20
\]

范围内增加，但 pilot seeds **永久禁止进入 confirmatory**。

Confirmatory：

\[
N=50
\]

paired seeds。

\(d_z=0.4\) 作为设计假设时，简单正态近似：

\[
N
\approx
\frac{
(1.96+0.84)^2
}{
0.4^2
}
\approx49
\]

所以 50 是合理首轮规模，但必须写成**设计假设**，不是 RFL 已知 effect size。

每个方法使用完全相同的：

```text
scenario IDs
environment seeds
NoiseTapes
feedback corruption decisions
```

但不同随机流必须拆开：

```python
env_rng
exploration_rng
feedback_rng
stats_rng
```

不能因为 Full-RFL 多调用几次 random 导致下一 episode 的 monster lane 和 Immediate 不同。

Primary statistical comparisons：

Experiment A：

```text
Full-RFL vs Immediate: AE
Full-RFL vs Immediate: WUR
Full-RFL vs PE-Seq: AE
Full-RFL vs PE-Seq: WUR
```

Experiment B：

```text
Full-RFL vs Immediate: AUC_return
Full-RFL vs ER-5: AUC_return
```

使用：

```text
paired sign-flip permutation test
10,000 permutations
```

paired bootstrap：

```text
10,000 resamples
95% CI
```

effect size：

\[
d_z=
\frac{
\bar d
}{
s_d
}.
\]

多重主比较：

```text
Holm correction
```

不能按每一个 episode 当独立样本做显著性测试，因为 episode 嵌套在 seed/run 内。

**预注册门槛。**

Experiment A go：

\[
AE_{Full}-AE_{Immediate}\le-0.08
\]

且：

\[
95\%CI
\]

不跨 0。

同时：

\[
WUR_{Full}-WUR_{Immediate}\le-0.10
\]

且 CI 不跨 0。

另外：

```text
UpdateCoverage 不能比 Immediate 低超过 0.10
```

防止“完全不更新”伪造低 WUR。

Experiment B：

```text
Full-RFL mean return - Immediate mean return > -0.05
```

即至少不能明显破坏 task performance。

如果要声称任务学习改善，则还要求：

```text
AUC_return CI > 0
```

或：

```text
SuccessRate CI > 0
```

至少一个 preregistered learning metric 成立。

**Experiment B 必须经过 sanity ladder。**

```text
B0 No Monster
→ Standard tabular success >= 0.95

B1 High-level only + scripted low-level
→ correct safe option >= 0.90

B2 Controlled low-level fault
→ H/L attribution 能被区分

B3 Deterministic monster, dash=0
→ Standard-HQ success >= 0.70

B4 Full monster, dash=0.10
→ Standard-HQ 有稳定非零学习能力
→ 才运行 RFL comparison
```

任何前一级未通过：

\[
\boxed{\text{停止，不允许跑50 seeds}}
\]

**资源预算必须首先用真实 benchmark 标定。**

运行：

```bash
python scripts/benchmark.py --steps 100000
```

输出：

```text
env_steps_per_second
cf_steps_per_second
```

然后所有 wall-clock 使用：

\[
T_{wall}
\approx
\frac{
C_{real}+C_{CF}
}{
throughput
}.
\]

不要凭空说“应该几秒”。

粗预算：

Experiment A：

\[
4500
\]

base factual traces。

Full-RFL 若平均每个 failure 检查约 8–15 个 rollout，每个 rollout 10–30 steps，则大约为几百万级 CF transitions。

CF-only exhaustive 最坏：

\[
1_H
+
4T_L
+
N_{dash}
\]

个 rollouts。

若：

\[
T=30
\]

则仅 low-level 就最多：

\[
30\times4=120
\]

个 alternative rollouts。

所以 exhaustive CF 可能达到**千万级乃至数千万级模拟 transition**，必须缓存：

```text
scenario_id + intervention -> counterfactual result
```

并让不同 feedback conditions 复用 factual/oracle cache。

Experiment B 若：

```text
50 seeds
× 6 methods
× 5000 episodes
× 30 max steps
```

仅任务环境上界就是：

\[
45,000,000
\]

real simulator steps / condition。

两档条件约：

\[
90,000,000.
\]

因此 confirmatory B 不应该在单线程下盲跑。seed 是天然可并行单位。

例如**仅作算力示意**：

若 benchmark 得：

\[
20,000\ steps/s
\]

则：

\[
100M/20k\approx5000s
\approx83min.
\]

若只有：

\[
5,000\ steps/s
\]

则约：

\[
5.6h.
\]

这些只是 throughput 换算，不是对你的机器速度做预言。正式 README 必须记录实测 throughput。

## GPT-5.3-Codex-Spark 分阶段任务序列

下面所有任务必须**顺序执行**。任何阶段测试失败，不允许跳到下一阶段。

OpenAI 官方明确说明 Codex-Spark 偏向定向、轻量修改，而且默认不会自动跑测试，因此每个 prompt 中都把“运行 pytest”设为硬要求，而不是依赖模型自行决定。citeturn7search1

统一输出格式固定为：

```text
[STATUS]
PASS | FAIL

[CHANGED_FILES]
- ...

[TEST_COMMANDS]
- command
  result: PASS/FAIL
  summary: ...

[SMOKE]
- command
  result: PASS/FAIL
  key_metrics: ...

[OPEN_ISSUES]
- none
或
- ...

[NO_UNREQUESTED_CHANGES]
true | false
```

**Spark Task S00：冻结旧实验并建立新工程。**

```text
你正在实现 RFL-CausalChase-v0.1。

Task ID: S00-SCAFFOLD

目标：
建立新的模块化工程，不修补 legacy 单文件实现。
把现有 rfl_v0_simple_experiment.py 移入 legacy/ 并保持内容不变。
创建最小 pyproject、包目录、tests 与 configs 目录。
不要实现环境动力学和 RFL 算法。

允许修改/创建的文件：
- pyproject.toml
- README.md
- CHANGELOG.md
- src/rflcc/__init__.py
- configs/smoke.yaml
- tests/test_imports.py
- legacy/rfl_v0_simple_experiment.py

禁止修改：
- legacy/rfl_v0_simple_experiment.py 的文件内容
- 任何尚未列出的算法文件

实现要求：
1. Python >= 3.11。
2. 依赖只加入 numpy/pandas/scipy/matplotlib/pyyaml/pytest。
3. src layout 可 import。
4. legacy 脚本只归档，不作为新实验入口。
5. 不提前实现环境、Q-learning、RFL。

必须执行：
python -m pytest -q

验收标准：
- pytest 全通过。
- `python -c "import rflcc"` 成功。
- legacy 文件内容 hash 与移动前一致。
- 不产生正式实验结果。

最后严格按固定输出格式汇报。
```

**Spark Task S01：类型和 NoiseTape。**

```text
Task ID: S01-NOISETAPE

目标：
实现所有核心 dataclass 和完全确定性的 NoiseTape。

允许修改/创建：
- src/rflcc/types.py
- src/rflcc/noise.py
- tests/test_noise_tape.py

禁止修改：
- src/rflcc/env.py
- src/rflcc/oracle.py
- src/rflcc/counterfactual.py
- src/rflcc/baselines/*
- legacy/*

实现要求：
1. 实现 Cause = H/L/E。
2. 实现 Observation、TraceEvent、EnvSnapshot、Intervention、NoiseTape。
3. NoiseTape.from_seed(seed, horizon) 必须预采样：
   - monster_start_lane
   - tie_break_u
   - dash_u
4. NoiseTape 必须 immutable。
5. dash intervention 通过 overlay/InterventionSet 表达，禁止修改 NoiseTape。
6. 禁止使用模块级 random.random()。
7. 同 seed 必须 bitwise/structurally identical。

必须执行：
python -m pytest tests/test_noise_tape.py -q
python -m pytest -q

验收：
- same seed -> identical tape
- different seed 在统计上可产生不同 tape
- intervention 不改变原 tape
- pytest 全通过

最后严格按固定输出格式汇报。
```

**Spark Task S02：环境动力学和 snapshot/restore。**

```text
Task ID: S02-ENV

目标：
实现 9x7 CausalChase 环境，不实现任何 learning。

允许修改/创建：
- src/rflcc/env.py
- tests/test_env_determinism.py
- tests/test_snapshot_restore.py
- tests/test_event_semantics.py
- scripts/smoke.py
- configs/smoke.yaml

允许读取但禁止修改：
- src/rflcc/types.py
- src/rflcc/noise.py

禁止修改：
- sequence.py
- counterfactual.py
- oracle.py
- qtables.py
- attribution.py
- baselines/*
- legacy/*

环境规格：
- grid 9x7
- start (1,3)
- goal (7,3)
- obstacles {3,4,5} x {2,3,4}
- monster starts (6,1)/(6,5)
- upper/lower waypoint routes 按 SPEC
- horizon 30
- normal step -0.01
- EXIT +1
- COLLISION -1
- TIMEOUT -0.5
- step 返回 obs,reward,terminated,truncated,info
- monster 每两个 agent step 基础移动一次
- dash p=0.10
- 所有随机性只能来自 NoiseTape

事件：
必须实现 ACT_*, ROUTE_PROGRESS/DEVIATE,
MONSTER_NORMAL/DASH, DIST_*, EXIT/COLLISION/TIMEOUT。
feedback token 不属于 env。

ROUTE_PROGRESS/DEVIATE 必须按动作前后到当前 waypoint 的
shortest-path distance 比较，禁止使用“是否已经到 waypoint”的旧逻辑。

snapshot/restore：
恢复后相同 action list 必须得到完全相同 trajectory。

必须执行：
python -m pytest tests/test_env_determinism.py -q
python -m pytest tests/test_snapshot_restore.py -q
python -m pytest tests/test_event_semantics.py -q
python scripts/smoke.py --stage env
python -m pytest -q

验收：
- same seed + actions == identical trajectory
- snapshot->rollout->restore->rollout identical
- normal progress 不产生 ROUTE_DEVIATE
- reward terminal semantics 精确等于 +1/-1/-0.5
- 无测试失败

最后严格按固定输出格式汇报。
```

**Spark Task S03：scripted policy、Oracle 和 ScenarioGenerator。**

```text
Task ID: S03-SCENARIOS

目标：
先构造 Experiment A 的可验证 H-only/L-only/E-only 轨迹。
Oracle 只服务 scenario generation/evaluation。

允许修改/创建：
- src/rflcc/policies.py
- src/rflcc/oracle.py
- src/rflcc/scenarios.py
- tests/test_oracle.py
- tests/test_scenario_isolation.py
- scripts/generate_scenarios.py

允许读取：
- env.py
- noise.py
- types.py

禁止修改：
- baselines/*
- attribution.py
- qtables.py
- sequence.py
- legacy/*

实现要求：
1. ScriptedRouteFollower 能根据 option 和状态产生下一 primitive action。
2. H counterfactual：
   换 option 后必须重新调用 frozen/scripted policy 产生后续 action，
   禁止复用 factual action list。
3. L oracle：
   遍历 factual trace 每个 decision，
   尝试其余全部 4 actions，
   intervention 后恢复 frozen policy。
4. E oracle：
   遍历 observed dash，
   阻止一个 dash，
   其他 NoiseTape draw 不变。
5. 如果全部 positive delta = 0，返回 UNRESOLVED，
   禁止返回 uniform R。
6. ScenarioGenerator 搜索 H-only/L-only/E-only。
7. 默认 acceptance:
   target_delta >= 0.4
   max(non_target_delta) <= 0.1
8. OracleEvaluator 不能出现在 learner package API。

必须执行：
python -m pytest tests/test_oracle.py -q
python -m pytest tests/test_scenario_isolation.py -q
python scripts/generate_scenarios.py --smoke --per-cause 5
python -m pytest -q

验收：
- smoke 至少生成 5 个 accepted H/L/E 各自样本
- 每类 target intervention 明显优于非 target
- Oracle low-level candidate 数 == T*(A-1)
- high-level action 必须被重新生成
- 无 oracle learner leakage

最后严格按固定输出格式汇报。
```

**Spark Task S04：trace、calibration 和 pairwise sequence model。**

```text
Task ID: S04-SEQUENCE

目标：
实现 causal/feedback namespace、pairwise sequence probability matrix、
正确符号的 G_k 和 q_seq。

允许修改/创建：
- src/rflcc/trace.py
- src/rflcc/sequence.py
- tests/test_sequence.py
- scripts/generate_calibration.py

允许读取：
- scenarios.py
- types.py

禁止修改：
- env.py
- oracle.py
- counterfactual.py
- baselines/*
- qtables.py
- legacy/*

数学：
A_uv = (N_uv + beta)/(N_uv + N_vu + 2 beta)
beta = 1
A_vu = 1-A_uv
clip [0.01, 0.99]

ell_k = eta*local + (1-eta)*global
eta = 0.5

G_k = ell_k - ell_background

q_seq = softmax((G + log prior)/tau_seq)
tau_seq=0.5
prior H=L=E=1/3

要求：
1. calibration 数据来自 S03 accepted single-cause scenarios。
2. calibration seeds 和实验 seeds 分离。
3. causal_events 与 feedback_events 分开。
4. FEEDBACK_* 永远不能进入 pair counts。
5. sequence model primary experiment 中默认 frozen。

必须执行：
python -m pytest tests/test_sequence.py -q
python scripts/generate_calibration.py --smoke --per-cause 10
python -m pytest -q

验收：
- Auv+Avu ~= 1
- synthetic/accepted H trace 中 H score > 明显不匹配模板
- G 符号测试通过
- feedback token contamination test 通过

最后严格按固定输出格式汇报。
```

**Spark Task S05：feedback、qpre、attribution pure functions。**

```text
Task ID: S05-ATTRIBUTION

目标：
实现 external diagnostic evidence 和纯函数式 responsibility inference。
本阶段禁止 counterfactual。

允许修改/创建：
- src/rflcc/feedback.py
- src/rflcc/attribution.py
- tests/test_feedback.py
- tests/test_metrics.py

允许读取：
- sequence.py
- types.py

禁止修改：
- env.py
- oracle.py
- counterfactual.py
- qtables.py
- baselines/*
- legacy/*

反馈：
match likelihood=0.6
mismatch=0.2
unknown=1/3
feedback weight=0.5

融合必须在 log-space：
log_q_pre =
  log(q_seq+eps)
  + w*log(L_feedback+eps)

禁止：
softmax(q_seq * likelihood)

必须实现：
- Immediate responsibility
- PE-Seq responsibility
- UNKNOWN handling
- normalization tests

必须执行：
python -m pytest tests/test_feedback.py -q
python -m pytest tests/test_metrics.py -q
python -m pytest -q

验收：
- q_pre sum == 1
- false feedback 能影响但不能强制覆盖 sequence evidence
- p_false=0/1 extreme tests 通过
- 不调用 Oracle

最后严格按固定输出格式汇报。
```

**Spark Task S06：learner CounterfactualRunner 与防泄漏。**

```text
Task ID: S06-COUNTERFACTUAL

目标：
实现 Full-RFL 自己的受限 counterfactual verification。
它不能读取 OracleEvaluator 或 oracle_* 结果。

允许修改/创建：
- src/rflcc/counterfactual.py
- tests/test_counterfactual.py
- tests/test_no_oracle_leakage.py

允许读取：
- env.py
- policies.py
- types.py
- trace.py

禁止修改：
- oracle.py
- sequence.py
- qtables.py
- baselines/*
- legacy/*

实现：
Top-K causes default=2

H:
- alternative option
- frozen policy continuation
- same NoiseTape

L:
- last W_CF=3 factual decisions
- 每个 decision 尝试其余 4 actions
- intervention 后 frozen policy continuation

E:
- observed dash indices
- block dash
- other exogenous draws unchanged

返回：
- verified cause set
- delta per verified cause
- cf rollout count
- cf transition count
- critical low-level decision if found

硬约束：
任何 learner-facing function signature 都不得包含：
oracle_R
oracle_delta
OracleEvaluator

必须执行：
python -m pytest tests/test_counterfactual.py -q
python -m pytest tests/test_no_oracle_leakage.py -q
python -m pytest -q

验收：
- CF 不修改 factual env / Q / NoiseTape
- H 真正 regenerate action
- L window <= 3
- no-oracle-leakage test 通过

最后严格按固定输出格式汇报。
```

**Spark Task S07：Full-RFL、CF-only、指标与 Experiment A。**

```text
Task ID: S07-EXPERIMENT-A

目标：
完整实现 Attribution Microbenchmark。
暂时不要实现 Q-learning。

允许修改/创建：
- src/rflcc/baselines/immediate.py
- src/rflcc/baselines/pe_seq.py
- src/rflcc/baselines/cf_only.py
- src/rflcc/baselines/full_rfl.py
- src/rflcc/baselines/oracle_upper.py
- src/rflcc/metrics.py
- src/rflcc/logging_io.py
- scripts/experiment_a.py
- schemas/episode.schema.json
- tests/test_metrics.py
- tests/test_no_oracle_leakage.py

允许读取：
- 已完成的其他 src/rflcc 模块

禁止修改：
- env.py
- noise.py
- oracle.py
- qtables.py
- legacy/*

Full-RFL responsibility：
dbar=max(0,delta)/2 clipped [0,1]
score =
 log(q_pre+eps)
 + 4*dbar
 - 2*I[verified and dbar<0.05]
R = softmax(score)

指标：
AE = 0.5*sum(abs(R-Rstar))
WUR
WrongUpdate
UpdateCoverage
FFCR
CF transitions

注意：
Experiment A 不实际修改 Q，
但使用 proposed rho/update mass 计算 WUR。

必须执行：
python -m pytest tests/test_metrics.py -q
python -m pytest tests/test_no_oracle_leakage.py -q
python scripts/experiment_a.py --smoke --seeds 5
python -m pytest -q

验收：
- AE 始终 [0,1]
- R sum==1
- train/eval 概念不影响 metric 是否被计算
- Full-RFL learner 不读取 oracle
- smoke 生成真实非零 AE/WUR，不能再次全部为 0

最后严格按固定输出格式汇报。
```

**Spark Task S08：Tabular Q 与 sanity ladder。**

```text
Task ID: S08-TABULAR-Q

目标：
只证明普通 Tabular Q-learning 能在逐级环境中学习。
本任务禁止使用 RFL diagnostic update。

允许修改/创建：
- src/rflcc/qtables.py
- src/rflcc/baselines/standard.py
- scripts/experiment_b.py
- tests/test_qlearning.py
- tests/test_eval_immutability.py
- configs/pilot_b.yaml

允许读取：
- env.py
- policies.py
- types.py

禁止修改：
- Full-RFL/PE/CF baselines
- oracle.py
- sequence.py
- legacy/*

Q_L：
online Q-learning after every env.step

Q_H：
one episodic MC update

epsilon：
linear 0.20 -> 0.02 over 3000 episodes

evaluation：
epsilon=0
no Q mutation

sanity ladder：
B0 monster_enabled=false
B1 high-level Q + scripted low-level
B3 deterministic monster dash=0

暂时不要跑 full dash RFL。

必须执行：
python -m pytest tests/test_qlearning.py -q
python -m pytest tests/test_eval_immutability.py -q
python scripts/experiment_b.py --stage B0 --smoke
python scripts/experiment_b.py --stage B1 --smoke
python -m pytest -q

验收：
- B0 5 smoke seeds greedy success >= 0.95
- B1 safe option accuracy >= 0.90
- evaluation 前后 Q hash 不变
- epsilon 在 decay 结束时精确到 0.02
- 不允许通过大幅奖励 shaping 偷偷解决任务

如果 B0/B1 未通过：
STATUS=FAIL，并停止，不实现下一阶段。

最后严格按固定输出格式汇报。
```

**Spark Task S09：Router、Immediate/ER/PE/Full 集成。**

```text
Task ID: S09-INTEGRATED-RFL

目标：
把 Experiment A attribution 接入 Tabular Q，
形成 Experiment B 的 auxiliary update。

允许修改/创建：
- src/rflcc/router.py
- src/rflcc/replay.py
- src/rflcc/baselines/er.py
- src/rflcc/baselines/pe_seq.py
- src/rflcc/baselines/full_rfl.py
- scripts/experiment_b.py
- tests/test_router.py
- tests/test_replay_semantics.py

禁止修改：
- env.py
- noise.py
- oracle.py
- sequence scoring mathematics
- legacy/*

要求：
1. 所有算法始终执行相同的真实 task Q-learning。
2. diagnostic auxiliary update 只在 COLLISION。
3. rho_H=-R_H, rho_L=-R_L。
4. environment responsibility 不直接惩罚内部模块。
5. primary B-Core:
   所有方法 low-level aux update 使用同一个预注册 last-action routing。
6. CF-critical routing 只能作为 secondary flag，默认关闭。
7. ER-5：
   - replay task transitions
   - attribution frozen
   - 禁止重新调用 sequence/counterfactual inference
8. 所有 replay/update 数量必须记录。

必须执行：
python -m pytest tests/test_router.py -q
python -m pytest tests/test_replay_semantics.py -q
python scripts/experiment_b.py --stage B2 --smoke
python -m pytest -q

验收：
- E-only: rho_H==0, rho_L==0（在 oracle/control test 中）
- H/L simultaneous responsibility 被允许
- ER 不调用 CounterfactualRunner
- Standard-HQ 不使用 diagnostic feedback
- 所有测试通过

最后严格按固定输出格式汇报。
```

**Spark Task S10：完整 B3/B4 可学习性门控。**

```text
Task ID: S10-BEHAVIOR-GATE

目标：
在开始正式 RFL 比较前，证明完整 tabular baseline 可学习。

允许修改：
- configs/pilot_b.yaml
- scripts/experiment_b.py
- scripts/benchmark.py
- tests/test_qlearning.py

原则：
优先修 bug，不允许为了通过门槛随意改 reward 或地图。
超参数只能从预先列出的 pilot grid 中选择，并记录所有试验。

pilot grid 可调：
alpha_low: [0.10, 0.20, 0.30]
epsilon_decay: [2000, 3000, 5000]
training_episodes: [3000, 5000]

不可调：
reward
grid geometry
goal/start
正式 monster algorithm

阶段：
B3: dash=0
B4: dash=0.10

必须执行：
python scripts/benchmark.py --steps 100000
python scripts/experiment_b.py --stage B3 --pilot --seeds 5
python scripts/experiment_b.py --stage B4 --pilot --seeds 5
python -m pytest -q

验收：
- B3 Standard-HQ greedy success >= 0.70
- B4 必须显示稳定非零学习；目标 >=0.50，
  若低于门槛不要伪造通过。
- 输出 throughput
- 输出 visited states 数和 Q-table size
- 所有 pilot 参数完整日志化

如果 B3 不过：
停止。
如果 B3 过而 B4 不过：
保留 B3 作为第一版 integrated environment，
不要强行跑 B4 confirmatory。

最后严格按固定输出格式汇报。
```

**Spark Task S11：统计、配置锁和 pilot。**

```text
Task ID: S11-STATS-PILOT

目标：
实现 seed-level paired statistics，并运行 pilot。
不得运行正式 50-seed confirmatory。

允许修改/创建：
- src/rflcc/stats.py
- src/rflcc/plots.py
- scripts/run_pilot.py
- scripts/analyze.py
- configs/pilot_a.yaml
- configs/pilot_b.yaml
- tests/test_stats.py

禁止修改：
- 所有已锁定算法数学
- env.py
- oracle.py
- counterfactual.py
- sequence.py
- legacy/*

统计：
- unit = seed
- paired sign-flip permutation, 10000
- paired bootstrap, 10000
- Cohen dz = mean(diff)/sd(diff)
- Holm correction
- AUC return seed-level

pilot：
12 个 pilot seeds
不得与 confirmatory seeds 重合。

必须执行：
python -m pytest tests/test_stats.py -q
python scripts/run_pilot.py --experiment A
python scripts/run_pilot.py --experiment B
python scripts/analyze.py --pilot
python -m pytest -q

验收：
- dz 测试确认没有 sqrt(n)
- paired seed 数准确
- 无 episode-level pseudoreplication
- 输出 pilot 参数与 go/no-go
- 不创建 confirmatory result 文件

最后严格按固定输出格式汇报。
```

**Spark Task S12：参数冻结和 50-seed confirmatory runner。**

```text
Task ID: S12-CONFIRMATORY

目标：
冻结参数，创建可复现的 50-seed 正式入口。
只有在前面所有 gate PASS 时才允许运行。

允许修改/创建：
- configs/confirmatory_a.yaml
- configs/confirmatory_b.yaml
- scripts/run_confirmatory.py
- README.md
- CHANGELOG.md

禁止修改：
- src/rflcc/env.py
- src/rflcc/sequence.py
- src/rflcc/counterfactual.py
- src/rflcc/attribution.py
- src/rflcc/router.py
- src/rflcc/qtables.py
- src/rflcc/baselines/*
- legacy/*

要求：
1. 固定 50 个全新 seeds。
2. 保存 config hash。
3. 保存 git commit hash。
4. 如果工作区 dirty，拒绝运行 confirmatory。
5. 每个 algorithm/condition 使用 paired scenario/env seeds。
6. 中断后支持 resume，但不能重复/覆盖已完成 seed。
7. 输出 raw JSONL + seed-level CSV。
8. confirmatory 过程中禁止自动调参。

运行前必须：
python -m pytest -q

然后：
python scripts/run_confirmatory.py --experiment A
只有 Experiment A 达到预注册 go 条件时才允许：
python scripts/run_confirmatory.py --experiment B

最后：
python scripts/analyze.py --confirmatory

验收：
- 50 paired seeds
- config/commit hash 已记录
- all pytest PASS
- raw logs 可重新计算全部 summary
- 不允许在看到结果后修改指标定义

最后严格按固定输出格式汇报。
```

**Spark Task S13：最终审计与论文材料生成。**

```text
Task ID: S13-REPRO-AUDIT

目标：
不改算法，只验证项目从空 results 目录可以复现所有图表和表格。

允许修改：
- README.md
- scripts/analyze.py
- src/rflcc/plots.py
- CHANGELOG.md

禁止修改：
- 所有算法与环境源码
- configs/confirmatory_*.yaml
- raw logs

必须执行：
python -m pytest -q
python scripts/analyze.py --confirmatory --rebuild-all

检查：
1. 所有表格来自 raw logs。
2. 所有 figure 可重新生成。
3. seed 数一致。
4. AE/WUR 不含 train=False 初始化 bug。
5. Oracle fields 不进入 learner。
6. config hash 与运行时一致。
7. README 包含一条从 clone 到复现结果的完整命令序列。

最后严格按固定输出格式汇报。
```

## 运行顺序、风险、回滚与 Go/No-Go

整个工程必须执行下面的单向状态机：

```text
旧实验归档
    ↓
Deterministic Environment
    ↓
Counterfactual Ground Truth
    ↓
Sequence Calibration
    ↓
Experiment A Smoke
    ↓
Experiment A Pilot
    ↓
参数冻结
    ↓
Experiment A Confirmatory
    ↓
        GO?
       /   \
     NO     YES
     ↓       ↓
   停止    Tabular B0/B1
              ↓
          B3 learnability
              ↓
              GO?
             /   \
           NO     YES
           ↓       ↓
         停止     B4
                    ↓
                B Pilot
                    ↓
                参数冻结
                    ↓
             B Confirmatory
```

最重要的风险不是“实验没显著”，而是**再次产生不可解释的显著结果**。

当前旧代码就提供了一个典型案例：Full-RFL 能直接使用 oracle counterfactual delta 时，即使结果看起来很好，也不能被当成 learner 真正推断出的责任；AE/WUR 在 `train=False` 下没计算时，即使输出“0.000”也不是完美归因；所有 success=0 时，即使 attribution 指标有显著差异，也无法回答 RFL 是否改善任务学习。fileciteturn0file0

因此回滚原则固定如下。

**环境测试失败：**

回滚到 S01。

不要改算法。

**H/L/E scenario 无法隔离：**

回滚 S03。

允许修改 scenario search 和 acceptance threshold 的 pilot 候选，但必须重新生成全部 calibration/test dataset。

**Sequence 分不开三类：**

不要马上调温度让结果“好看”。

先检查：

```text
event semantics
calibration contamination
token frequency
pairwise matrix
```

如果 sequence 本身没有辨识力，这是一个有效结果。

**Experiment A 中 CF-only 很强而 Full-RFL 不省计算：**

结论：

> sequence ranking 没有提供价值。

不要增加 attention、HFAb 或复杂 ANN 来救。

**Experiment A 不通过：**

停止 B 的 RFL confirmatory。

可以继续把项目作为负结果/方法审计，但不能声称 RFL 获得支持。

**B0/B1 不通过：**

是 task learner/environment bug。

禁止讨论 RFL。

**B3 通过、B4 不通过：**

第一篇 Integrated Experiment 使用 B3 deterministic-monster 环境。

B4 作为 future challenge。

不要通过：

```text
改 reward
弱化怪物但不披露
增加 hidden heuristic
```

来制造成功率。

**RFL 提高 AE/WUR 但 Return 不提高：**

论文结论限制为：

> RFL improves diagnostic attribution under misleading feedback, but downstream policy-learning benefit was not established.

这是完全可以接受的科学结果。

**Full-RFL Return 更好但 AE/WUR 不好：**

不能说原因是“更正确的反馈理解”。

有可能只是 auxiliary shaping 的意外效果。

需要额外分析。

**Fast/slow 不进入 v0.1。**

Dyna 已经明确提供 learning/planning/reactive execution 的经典框架；fast/slow 本身没有必要在第一篇重复实现。以后可以增加：

```text
RFL-CausalChase-FastIntervention-v1
```

专门研究：

\[
a^{proposed}
\neq
a^{executed}
\]

后的 credit interface。citeturn13search0

**多原因 Shapley 不进入 v0.1 主实验。**

v0.1：

\[
R^\star\propto\Delta^+
\]

只是透明、可审计的 benchmark responsibility。

v1 再引入：

\[
\phi
\]

处理 interaction / skill / luck；Counterfactual Shapley 已经提供了一条直接可用的前沿基线，所以没必要现在重新发明。citeturn8search0

**Event granularity 不进入第一篇主变量。**

固定 tokenization 以后，未来单独比较：

\[
G_1=\text{primitive event}
\]

\[
G_2=\text{fixed temporal window}
\]

\[
G_3=\text{option boundary}
\]

\[
G_4=\text{prediction-error event boundary}.
\]

Options 已经提供时间抽象理论，因此未来真正新问题不是“事件可以有多个尺度”，而是：

\[
\boxed{
\text{什么 event granularity 最有利于反馈因果归因？}
}
\]

citeturn8search7

**不可复现现实环境也不进入 v0.1。**

当前 NoiseTape + exact simulator 给我们：

\[
do(c)
\]

的干净实验 ground truth。

未来用 learned world model：

\[
\hat T_\phi
\]

替代 simulator 时，责任输出必须变成：

\[
P(R_k\mid D,\hat T_\phi)
\]

并显式报告 model uncertainty，而不是继续把模拟反事实叫“真实责任”。

## 最终交付物与论文式结果结构

Spark 最终必须产出以下目录；缺少任何一项都不能称为“完成实验”。

```text
deliverables/
├── code/
│   └── 完整 src/rflcc + tests + scripts
│
├── configs/
│   ├── smoke.yaml
│   ├── pilot_a.yaml
│   ├── pilot_b.yaml
│   ├── confirmatory_a.yaml
│   └── confirmatory_b.yaml
│
├── reproducibility/
│   ├── environment.txt
│   ├── python_version.txt
│   ├── dependency_versions.txt
│   ├── git_commit.txt
│   ├── config_hashes.txt
│   ├── seed_manifest.csv
│   └── benchmark.json
│
├── calibration/
│   ├── sequence_H.npy
│   ├── sequence_L.npy
│   ├── sequence_E.npy
│   ├── sequence_background.npy
│   └── calibration_manifest.csv
│
├── scenarios/
│   ├── experiment_a_manifest.jsonl
│   └── oracle_validation.jsonl
│
├── raw/
│   ├── experiment_a.jsonl
│   ├── experiment_b.jsonl
│   └── events.jsonl.gz
│
├── results/
│   ├── seed_metrics_a.csv
│   ├── seed_metrics_b.csv
│   ├── paired_statistics.csv
│   ├── ablations.csv
│   └── compute_cost.csv
│
├── plots/
│   ├── attribution_error.png
│   ├── wur_false_feedback.png
│   ├── false_feedback_compliance.png
│   ├── compute_accuracy_pareto.png
│   ├── return_learning_curve.png
│   ├── success_learning_curve.png
│   ├── cause_confusion_matrix.png
│   └── sequence_matrices.png
│
└── README.md
```

论文 Results 最好只保留真正回答问题的图。

**主图 A：误导反馈鲁棒性**

横轴：

\[
p_{false}.
\]

纵轴：

\[
AE.
\]

显示：

```text
Immediate
PE-Seq
CF-only
Full-RFL
Oracle
```

**主图 B：Wrong Update**

横轴：

\[
p_{false}
\]

纵轴：

\[
WUR
\]

并在旁边同时报告：

\[
UpdateCoverage.
\]

否则低 WUR 可能只是 abstention。

**主图 C：Sequence ranking 的实际价值**

横轴：

\[
CF\ simulated\ transitions
\]

纵轴：

\[
AE.
\]

比较：

```text
PE-Seq
Full-RFL Top-1
Full-RFL Top-2
CF-only exhaustive
Oracle
```

如果 Full-RFL 能接近 CF-only accuracy 但大幅降低 CF cost，那么可以形成很清楚的机制结论：

\[
\boxed{
SequenceEvidence
\rightarrow
SearchPrioritization
}
\]

而不是虚假地声称 sequence likelihood 本身已经证明了因果。

**主图 D：Integrated Learning**

只有 Experiment B 通过 learnability gate 后才绘制：

```text
Return vs training episode
Success vs training episode
```

所有曲线显示 seed mean + uncertainty interval，但显著性分析仍然基于 seed-level AUC，而不是逐 episode 做 p-value。

**主图 E：一个完整 attribution episode。**

展示：

\[
q_{seq}
\rightarrow
q_{pre}
\rightarrow
CF
\rightarrow
R
\rightarrow
R^\star
\]

例如：

```text
False diagnostic says H

q_seq:
H=.14 L=.72 E=.14

q_pre:
H=.30 L=.59 E=.11

Top-2:
L,H

CF:
Delta_L=1.42
Delta_H=.02

Final:
H=.04 L=.89 E=.07

Oracle:
H=.03 L=.91 E=.06
```

这张图会非常直接地表达 RFL 的核心：

\[
\boxed{
\text{反馈先作为证据进入系统，而不是直接变成学习命令。}
}
\]

论文 Discussion 必须明确承认前人工作边界：MMRL 已经展示 prediction-error-driven responsibility；Wurm 已经展示 surprise-driven structural arbitration；Huh 提供 pairwise sequence likelihood，而非因果归因；Samejima 等已经研究 inter-module credit；Options 已经处理 temporally extended action；Dyna 已经整合 learning、planning 和 reactive execution；Counterfactual Shapley 已经提供更原则化的 causal credit。citeturn7search2turn9search3turn10view0turn15search1turn8search7turn13search0turn10view2

因此，如果 Experiment A 和 B 最终都支持假设，第一篇论文最稳健的贡献表述可以是：

> **We introduce a controlled tabular framework for reinforcement learning under potentially misleading diagnostic feedback. Rather than treating diagnostic feedback as an immediate learning target, the proposed RFL mechanism reopens the episode for attribution, combines sequence-based structural evidence with weak external diagnostic evidence, selectively performs counterfactual verification, revises graded module responsibility, and only then applies auxiliary module-specific reinforcement.**

其中最核心的数学链条是：

\[
\boxed{
\begin{aligned}
\text{Observed Feedback}
&\not\Rightarrow
\text{Immediate Parameter Update}\\
\\
\text{Observed Feedback}
&+
\text{Sequence Evidence}\\
&\rightarrow
q_{pre}(C)\\
&\rightarrow
\text{Selective Counterfactual Verification}\\
&\rightarrow
R(C)\\
&\rightarrow
(\rho_H,\rho_L)\\
&\rightarrow
\text{Selective Auxiliary Update}.
\end{aligned}
}
\]

而第一篇论文**不应该**声称：

```text
RFL 证明了人脑如何学习
RFL 首次提出 prediction-error responsibility
RFL 首次提出模块 credit assignment
RFL 首次提出 replay
RFL 首次提出 planning/execution 分离
RFL 已解决现实世界不可复现 counterfactual
```

Parvin 的实验、MMRL、Wurm、Huh、Dyna、Options 和 Counterfactual Shapley 都说明，这些单独部件已有相当明确的前人基础。RFL-v0.1 的价值在于把问题重新定义为：

\[
\boxed{
\textbf{在反馈信息本身可能错误时，}
\;
\textbf{Agent 应不应该先判断“这个反馈意味着什么”，}
\;
\textbf{再决定内部哪些功能应该被强化？}
}
\]

citeturn12search0turn7search2turn9search3turn10view0turn13search0turn8search7turn10view2

最终工程验收只有四个硬门槛：

\[
\boxed{
\text{所有 pytest 通过}
}
\]

\[
\boxed{
\text{Experiment A 无 oracle leakage 且通过预注册归因门槛}
}
\]

\[
\boxed{
\text{普通 Tabular baseline 先证明环境可学习}
}
\]

\[
\boxed{
\text{正式 50-seed 结果能从 raw logs 在冻结代码上完全重建}
}
\]

只有这四个条件全部满足，新的 50-seed 结果才第一次有资格被称为 **RFL-CausalChase-v0.1 的正式实验结果**。