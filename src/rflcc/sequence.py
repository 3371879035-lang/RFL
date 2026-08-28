"""Pairwise sequence model：原因模板概率矩阵、正确符号的 G_k、q_seq（S04）。

数学（SPEC）：
    N_uv^(k) = #(u 先于 v | C_k)
    A_uv = (N_uv + beta) / (N_uv + N_vu + 2 beta),  beta = 1
    A_vu = 1 - A_uv,  clip [0.01, 0.99]
    ell_k = eta * local + (1-eta) * global,  eta = 0.5
    local  = 1/(n-1) sum_i log A[x_i, x_{i+1}]
    global = 1/|P| sum_{i<j} log A[x_i, x_j]
    G_k = ell_k - ell_background
    q_seq = softmax((G + log prior) / tau_seq),  tau_seq = 0.5, prior = 1/3

feedback token 严禁进入 pair counts（causal/feedback namespace 分离）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .trace import EpisodeTrace
from .types import CAUSES, softmax


@dataclass
class SequenceResult:
    ell: dict[str, float] = field(default_factory=dict)
    local: dict[str, float] = field(default_factory=dict)
    global_: dict[str, float] = field(default_factory=dict)
    ell_background: float = 0.0
    G: dict[str, float] = field(default_factory=dict)
    q_seq: dict[str, float] = field(default_factory=dict)


class SequenceModel:
    def __init__(
        self,
        *,
        beta: float = 1.0,
        probability_floor: float = 0.01,
        eta: float = 0.5,
        tau_seq: float = 0.5,
        prior: dict[str, float] | None = None,
        vocab: list[str] | None = None,
    ) -> None:
        self.beta = beta
        self.floor = probability_floor
        self.eta = eta
        self.tau_seq = tau_seq
        self.prior = prior if prior is not None else {c: 1 / 3 for c in CAUSES}
        self._vocab = list(vocab) if vocab is not None else []
        self._idx: dict[str, int] = {t: i for i, t in enumerate(self._vocab)}
        self._A: dict[str, np.ndarray] = {}  # cause -> (V, V) 概率矩阵
        self._N: dict[str, np.ndarray] = {}  # cause -> (V, V) 计数矩阵
        self._bg_A: np.ndarray | None = None

    # ------------------------------------------------------------------
    # calibration
    # ------------------------------------------------------------------

    @property
    def vocab(self) -> list[str]:
        return self._vocab

    @property
    def calibrated(self) -> bool:
        return len(self._A) == len(CAUSES) and self._bg_A is not None

    def calibrate(
        self,
        traces_by_cause: dict[str, list[EpisodeTrace]],
    ) -> None:
        """从 accepted single-cause 轨迹构建模板。

        H/L 轨迹按 true_primary 全量计数；E 轨迹按 oracle R* 加权软计数
        （环境几何使 E 与 L 存在固有耦合，R* 记录于 trace.env_meta['r_star']）。
        """
        counts: dict[str, np.ndarray] = {c: None for c in CAUSES}
        bg: np.ndarray | None = None
        # pass 1：收集完整 vocab
        for cause, traces in traces_by_cause.items():
            for tr in traces:
                for tok in (e.token for e in tr.causal_events):
                    if tok not in self._idx:
                        self._idx[tok] = len(self._vocab)
                        self._vocab.append(tok)
        # pass 2：计数
        for cause, traces in traces_by_cause.items():
            for tr in traces:
                tokens = self._tokens(tr)
                if len(tokens) < 2:
                    continue
                counts_mat = self._pair_counts(tokens)
                if bg is None:
                    bg = counts_mat.copy()
                else:
                    bg = bg + counts_mat
                if cause in ("H", "L"):
                    counts[cause] = (
                        counts_mat.copy()
                        if counts[cause] is None
                        else counts[cause] + counts_mat
                    )
                elif cause == "E":
                    r = tr.env_meta.get("r_star")
                    w_l = r.get("L", 0.5) if r else 0.5
                    w_e = r.get("E", 0.5) if r else 0.5
                    counts["L"] = (
                        counts_mat * w_l
                        if counts["L"] is None
                        else counts["L"] + counts_mat * w_l
                    )
                    counts["E"] = (
                        counts_mat * w_e
                        if counts["E"] is None
                        else counts["E"] + counts_mat * w_e
                    )
                else:
                    raise ValueError(cause)

        self._vocab = [t for t in self._vocab]  # 保持顺序
        self._A = {c: self._normalize(counts[c]) for c in CAUSES}
        self._bg_A = self._normalize(bg)

    # ------------------------------------------------------------------
    # scoring
    # ------------------------------------------------------------------

    def score(self, trace: EpisodeTrace) -> SequenceResult:
        if not self.calibrated:
            raise RuntimeError("SequenceModel not calibrated")
        tokens = self._tokens(trace)
        n = len(tokens)
        res = SequenceResult(ell_background=0.0)
        bg = self._bg_A
        for c in CAUSES:
            A = self._A[c]
            if n < 2:
                local = 0.0
                global_ = 0.0
            else:
                local = self._local_score(tokens, A, n)
                global_ = self._global_score(tokens, A, n)
            ell = self.eta * local + (1 - self.eta) * global_
            res.local[c] = local
            res.global_[c] = global_
            res.ell[c] = ell
        # 背景
        if n >= 2:
            res.ell_background = self.eta * self._local_score(
                tokens, bg, n
            ) + (1 - self.eta) * self._global_score(tokens, bg, n)
        for c in CAUSES:
            res.G[c] = res.ell[c] - res.ell_background
        logits = {
            c: (res.G[c] + np.log(self.prior[c])) / self.tau_seq for c in CAUSES
        }
        res.q_seq = softmax(logits, tau=1.0)
        return res

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _tokens(self, trace: EpisodeTrace) -> list[str]:
        toks = [e.token for e in trace.causal_events]
        if self._idx:
            return [t for t in toks if t in self._idx]
        self._vocab = sorted({t for t in toks})
        self._idx = {t: i for i, t in enumerate(self._vocab)}
        return toks

    def _pair_counts(self, tokens: list[str]) -> np.ndarray:
        V = len(self._vocab)
        N = np.zeros((V, V), dtype=float)
        for i in range(len(tokens)):
            for j in range(i + 1, len(tokens)):
                u, v = tokens[i], tokens[j]
                if u == v:
                    continue
                iu, iv = self._idx[u], self._idx[v]
                N[iu, iv] += 1.0
        return N

    def _normalize(self, counts: np.ndarray | None) -> np.ndarray:
        V = len(self._vocab)
        if counts is None:
            counts = np.zeros((V, V))
        N = counts + counts.T  # 对称计数用于方向概率
        A = np.full((V, V), 0.5)
        for u in range(V):
            for v in range(V):
                if u == v:
                    continue
                n_uv = counts[u, v]
                n_vu = counts[v, u]
                A[u, v] = (n_uv + self.beta) / (n_uv + n_vu + 2 * self.beta)
        # 下三角由对称性补全（A_vu = 1 - A_uv），并 clip
        for u in range(V):
            for v in range(u + 1, V):
                A[v, u] = 1.0 - A[u, v]
        A = np.clip(A, self.floor, 1.0 - self.floor)
        return A

    def _local_score(self, tokens: list[str], A: np.ndarray, n: int) -> float:
        s = 0.0
        for i in range(n - 1):
            u, v = tokens[i], tokens[i + 1]
            if u == v:
                continue
            s += np.log(max(A[self._idx[u], self._idx[v]], 1e-12))
        return s / (n - 1)

    def _global_score(self, tokens: list[str], A: np.ndarray, n: int) -> float:
        s = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                u, v = tokens[i], tokens[j]
                if u == v:
                    continue
                s += np.log(max(A[self._idx[u], self._idx[v]], 1e-12))
        pairs = n * (n - 1) / 2
        return s / pairs
