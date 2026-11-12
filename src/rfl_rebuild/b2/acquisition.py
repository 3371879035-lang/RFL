r"""$F_0$ §3's master acquisition, and the artifact its contract requires.

$$\boxed{\texttt{BaselineAcquisitionPlan} \;\longrightarrow\; \texttt{acquire\_master\_baseline}
\;\longrightarrow\; \left\{V_{\sigma,e,u}\right\} \cup \text{sufficient A89 pre-update eligibility
material}}$$

**What the artifact holds, and why in this form.** §3 freezes the sufficiency requirement rather than the
shape: *"the per-$(A, \sigma, e, c, r)$ sufficient statistics --- $\lvert C\rvert$, $\sum V$, $\sum V^2$ ---
are the minimum, and the full incidence form ($\textit{Consult}$ and $H_{\text{pre}}$ per unit) is equally
acceptable."* This module stores the incidence form, and the choice is measured rather than preferred:

* $c$ ranges over each architecture's **production credited domain** of A89 §77.4 ---
  $\lvert \mathcal D^{\text{credit}}_{D_Q}\rvert = 13824$, $\lvert \mathcal D^{\text{credit}}_{X}\rvert = 229$
  and $\lvert \mathcal D^{\text{credit}}_{P}\rvert = 4$ on a fresh learner, all three measured --- so the
  finished statistics are $14057 \times 6 \times 32 \times 41 = 1.1 \times 10^8$ triples on the frozen
  envelope, while the incidence that generates them is $12892 \times 32 \times 41 = 1.7 \times 10^7$ pairs.
  The "minimum" is the larger object here, by a factor of about $6.5$, and the permitted alternative is the
  one an artifact can carry;
* and it is the honest one: incidence is what the run's own episodes produced, while the statistics are a
  derivation, so a derivation error is a *recoverable* defect rather than a corrupted record.

**Nothing here is invented, and nothing is selected.** Eligibility is read from $W_{\sigma,e}$'s own unedited
episodes ($\texttt{pre\_update\_traces}$), the architecture domains come from A89's own enumerator
($\texttt{credited\_domain}$), and the refinement predicate is the instrument's ($\texttt{unaffected.\_slice}$,
imported rather than restated so that one definition exists). This module chooses no $\alpha$, no
$\varepsilon$, no cap and no bank: they arrive through the plan. It runs no treatment arm: this is the $S_2$
baseline path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import NamedTuple

from rfl_rebuild.b1.errors import ProtocolError
from rfl_rebuild.b2.numerics import standard_error, sufficient_statistics
from rfl_rebuild.b2.training import (
    BaselineAcquisitionPlan,
    ExogenousEpisode,
    episode_rollout,
    sweep_edits,
)
from rfl_rebuild.b2.unaffected import (
    CHANNELS,
    REFINEMENTS,
    CreditedSite,
    _slice as refinement_membership,   # the instrument's one definition of A89 §77.4's $S_i$
    credited_domain,
    pre_update_traces,
)
from rfl_rebuild.learner.store import LearnerPersistentState

__all__ = ["MasterBaseline", "RunMaterial", "Sufficient", "acquire_master_baseline",
           "iter_master_baseline", "sufficient_error"]


class Sufficient(NamedTuple):
    r"""$\left(\lvert C\rvert,\ \sum_{u \in C} V_{\sigma,e,u},\ \sum_{u \in C}
    V_{\sigma,e,u}^2\right)$ --- §3's and §4.0's declared minimum."""

    n: int
    total: float
    total_sq: float


def sufficient_error(sufficient: Sufficient) -> float | None:
    r"""Diagnostic expansion only; forbidden as authoritative SE by rev-4 CF-1.

    $$\mathrm{se} = \sqrt{\frac{1}{n}\left(\frac{\sum V^2}{n} -
    \left(\frac{\sum V}{n}\right)^2\right)}$$

    `None` means the set is empty --- §4.0's "missing values are never imputed" and §4.4's "an empty set has
    no mean", so this is inadmissible rather than zero. $n = 1$ gives $0$, as §4.0 freezes.
    """
    n, total, total_sq = sufficient
    if n <= 0:
        return None
    mean = total / n
    variance = max(total_sq / n - mean * mean, 0.0)   # a negative round-off is clamped, not kept
    return math.sqrt(variance / n)


def _accumulated_mean(values) -> float:
    r"""$\mathrm{mean}_u V_{\sigma,e,u}$, summed **in A91's order**.

    `train_curve`'s `_mean_return` accumulates left to right with `total += value` and divides once at the end,
    and CPython's `sum()` is Neumaier-compensated, so the two differ by an ulp on values like these. The
    quantity is the same one $f_T$, $f_G$ and $f_R$ read, so the acquisition reproduces A91's accumulation
    rather than a second, marginally more accurate mean: agreement with the frozen instrument is worth more
    here than the last bit, and `test_5` makes the agreement exact rather than approximate.
    """
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


@dataclass(frozen=True, slots=True)
class RunMaterial:
    r"""One $(\sigma, e)$'s slice of $D^{\text{master}}$: the matrix column and the eligibility material."""

    seed: int
    episode: int
    levels: tuple           # $V_{\sigma,e,u}$, aligned with `MasterBaseline.sample`
    success: tuple          # $H_{\text{pre}}(u)$, aligned with `MasterBaseline.sample`
    consulted: object       # channel -> {site: (bank indices whose episode consults it)}
    domains: object         # channel -> the run's $\mathcal D^{\text{credit}}_A(W_{\sigma,e})$
    uncontacted: object     # channel -> does that domain hold a site no bank episode consults?
    outside_domain: object  # channel -> consulted sites the run's own domain excludes (audited)
    _memo: dict = field(default_factory=dict, compare=False, repr=False)

    def mean(self) -> float:
        return _accumulated_mean(self.levels)

    def credit_set(self, arch: str) -> frozenset:
        r"""$\mathcal D^{\text{credit}}_A(W_{\sigma,e})$ as a membership test, built once."""
        cached = self._memo.get(("credit_set", arch))
        if cached is None:
            cached = frozenset(self.domains[arch])
            self._memo[("credit_set", arch)] = cached
        return cached


@dataclass(frozen=True, slots=True)
class MasterBaseline:
    r"""$\left\{V_{\sigma,e,u}\right\} \cup$ incidence --- the one acquisition before $F_1$."""

    seeds: tuple
    episodes: tuple
    sample: tuple           # the master bank $\mathcal S^{\text{master}}_{\text{eval}}$
    runs: object            # (seed, episode) -> RunMaterial
    _memo: dict = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not self.seeds or not self.episodes:
            raise ProtocolError("an acquisition without seeds or without episodes is not an acquisition")
        for sigma in self.seeds:
            for e in self.episodes:
                if (sigma, e) not in self.runs:
                    raise ProtocolError(f"the acquisition is missing the run ({sigma}, {e})")
                run = self.runs[(sigma, e)]
                if len(run.levels) != len(self.sample) or len(run.success) != len(self.sample):
                    raise ProtocolError(
                        f"run ({sigma}, {e}) is not aligned with the master bank: "
                        f"{len(run.levels)} levels for {len(self.sample)} scenes")

    # --- the matrix, and its derived view -----------------------------------------------------------

    def material(self, seed: int, episode: int) -> RunMaterial:
        return self.runs[(seed, episode)]

    def levels(self, seed: int, episode: int) -> tuple:
        r"""$V_{\sigma,e,u}$ over the master bank --- the matrix column §3 freezes."""
        return self.runs[(seed, episode)].levels

    def mean_curve(self, seed: int) -> tuple:
        r"""$V_\sigma(e) = \mathrm{mean}_u V_{\sigma,e,u}$ --- a **view** of the matrix (§3)."""
        return tuple(self.runs[(seed, e)].mean() for e in self.episodes)

    # --- the eligibility material -------------------------------------------------------------------

    def domain(self, arch: str, seed: int, episode: int) -> tuple:
        r"""$\mathcal D^{\text{credit}}_A(W_{\sigma,e})$ for that run, as A89 §77.4 enumerates it."""
        self._checked_arch(arch)
        return self.runs[(seed, episode)].domains[arch]

    def consulted(self, arch: str, seed: int, episode: int) -> dict:
        """The incidence: each site of that run's domain that a bank episode consults, and where."""
        self._checked_arch(arch)
        return self.runs[(seed, episode)].consulted[arch]

    def uncontacted(self, arch: str, seed: int, episode: int) -> bool:
        r"""Does the run's domain hold a site **no** bank episode consults?

        Such a site's $C_r(c)$ is $H_{\text{pre}} \cap S_r$ whatever the site is, so its metric is the
        family's one shared value. Whether that value is *attained* is a property of the domain, which is
        why it is recorded rather than assumed.
        """
        self._checked_arch(arch)
        return self.runs[(seed, episode)].uncontacted[arch]

    def slice_indices(self, arch: str, seed: int, episode: int, site, name: str) -> tuple:
        r"""$C^{\,A,\sigma,e}_{\text{name}}(c)$ as explicit bank indices --- the definitional form.

        $$C_r^{A,\sigma,e}(c) = E_{W_{\sigma,e}}(c) \cap S_r = \{u \in \mathcal S^{\text{master}}_{\text{eval}}:
        \neg\textit{Consult}_{W_{\sigma,e}}(u,c) \wedge H_{\text{pre}}(u) \wedge u \in S_r\}$$
        """
        run = self._checked_site(arch, seed, episode, site)
        slices = self._slices()
        if name not in slices:
            raise ProtocolError(f"unknown refinement {name!r}; the six names are frozen")
        excluded = set(run.consulted[arch].get(site, ()))
        return tuple(i for i in slices[name]
                     if run.success[i] and i not in excluded)

    def sufficient(self, arch: str, seed: int, episode: int, site, name: str) -> Sufficient:
        r"""§3's triple, recovered from the incidence **mechanically and exactly as defined**."""
        run = self._checked_site(arch, seed, episode, site)
        indices = self.slice_indices(arch, seed, episode, site, name)
        levels = run.levels
        return Sufficient(*sufficient_statistics(levels[i] for i in indices))

    def error(self, arch: str, seed: int, episode: int, site, name: str) -> float | None:
        r"""Authoritative SE from the slice's values in ascending bank order (CF-1)."""
        run = self._checked_site(arch, seed, episode, site)
        indices = self.slice_indices(arch, seed, episode, site, name)
        return standard_error(run.levels[i] for i in indices)

    def generic_sufficient(self, seed: int, episode: int, name: str) -> Sufficient:
        r"""The triple every **uncontacted** site of any domain shares, for one $(\sigma, e, r)$."""
        return Sufficient(*sufficient_statistics(self._generic_values(seed, episode, name)))

    def generic_error(self, seed: int, episode: int, name: str) -> float | None:
        """Authoritative SE shared by uncontacted sites; no triple expansion."""
        return standard_error(self._generic_values(seed, episode, name))

    def _generic_values(self, seed: int, episode: int, name: str) -> tuple:
        run = self.runs[(seed, episode)]
        slices = self._slices()
        if name not in slices:
            raise ProtocolError(f"unknown refinement {name!r}; the six names are frozen")
        indices = tuple(i for i in slices[name] if run.success[i])
        return tuple(run.levels[i] for i in indices)

    # --- internals ----------------------------------------------------------------------------------

    def _checked_arch(self, arch: str) -> bool:
        if arch not in CHANNELS:
            raise ProtocolError(f"{arch!r} is not one of the frozen channels {CHANNELS!r}")
        return True

    def _checked_site(self, arch: str, seed: int, episode: int, site) -> RunMaterial:
        self._checked_arch(arch)
        if type(site) is not CreditedSite:
            raise ProtocolError(f"a credited site is a CreditedSite, got {type(site).__name__}")
        if site.channel != arch:
            raise ProtocolError(f"site {site.render()} belongs to {site.channel}, not to {arch}")
        run = self.runs[(seed, episode)]
        if site not in run.credit_set(arch):
            raise ProtocolError(
                f"{site.render()} is not in {arch}'s credited domain for seed {seed} episode {episode}: "
                "§4.4 maximises over the run's own domains, so the acquisition must not widen or narrow them")
        return run

    def _slices(self) -> dict:
        r"""$S_r$ over the master bank --- static, so computed once and shared by every query."""
        cached = self._memo.get("slices")
        if cached is None:
            cached = {name: tuple(i for i, unit in enumerate(self.sample)
                                  if refinement_membership(name, unit))
                      for name in REFINEMENTS}
            self._memo["slices"] = cached
        return cached


def _require_seeds(seeds) -> tuple:
    seeds = tuple(seeds)
    if not seeds:
        raise ProtocolError("the seed set is empty; an acquisition needs at least one run")
    if any(isinstance(s, bool) or not isinstance(s, int) for s in seeds):
        raise ProtocolError(f"the seed set must be true integers, got {seeds!r}")
    if len(set(seeds)) != len(seeds):
        raise ProtocolError(f"the seed set repeats a seed: {seeds!r}; a seed is one run")
    if any(s < 0 for s in seeds):
        raise ProtocolError("acquisition seeds must be non-negative")
    return seeds


def _run_material(learner, *, seed: int, episode: int, sample: tuple, q_reference) -> RunMaterial:
    r"""One $(\sigma, e)$: the matrix column, $H_{\text{pre}}$, and the incidence, from **one** trace pass.

    The traces are the full $U_2$ rather than the bank, because A89's $\mathcal D^{\text{credit}}_X$ is
    "the sites the $W_{\text{pre}}$ episodes **of $U_2$** construct"; the bank's own episodes are a subset,
    and a domain read off the subset would be the acquisition quietly narrowing a frozen domain. One rollout
    per scene serves both the levels and the eligibility material, which is also what
    `PreUpdateTraces`' one-object-one-rollout contract is for.
    """
    traces = pre_update_traces(learner=learner, q_reference=q_reference)
    levels = tuple(traces.trace(unit).return_value for unit in sample)
    success = tuple(traces.successful(unit) for unit in sample)

    consulted, domains, uncontacted, outside = {}, {}, {}, {}
    for arch in CHANNELS:
        domain = credited_domain(arch, traces)
        universe = set(domain)
        inversion, dropped = {}, 0
        for index, unit in enumerate(sample):
            for site in traces.consulted(arch, unit):
                if site in universe:
                    inversion.setdefault(site, []).append(index)
                else:
                    dropped += 1
        consulted[arch] = MappingProxyType({site: tuple(where) for site, where in inversion.items()})
        domains[arch] = domain
        uncontacted[arch] = len(inversion) < len(domain)
        outside[arch] = dropped

    return RunMaterial(
        seed=seed, episode=episode, levels=levels, success=success,
        consulted=MappingProxyType(consulted), domains=MappingProxyType(domains),
        uncontacted=MappingProxyType(uncontacted), outside_domain=MappingProxyType(outside),
    )


def iter_master_baseline(plan, *, seeds, q_reference, initializer=None):
    r"""Run the $S_2$ master acquisition: `ACQUISITION_CAP` episodes per seed, on the master bank.

    The plan is the **envelope** of §3 --- $\alpha$, $\varepsilon$, the cap and the bank. A run's key is not
    a plan field: it is the seed, and the run's own plan is the envelope carrying it
    (`dataclasses.replace`), so the training machinery is handed a protocol whose `seed` is the key that
    generated its episodes. That is A91's shape (`train_curve` derives $\Xi_e$ from `protocol.seed`), and it
    is why this function is not `train_curve`: `train_curve` additionally needs $T^{*}$, the locked grid,
    $\mathcal S_{\text{eval}}^{*}$ and $V_{\text{pre}}^{*}$, none of which exists before $F_1$.
    """
    if not isinstance(plan, BaselineAcquisitionPlan):
        raise ProtocolError(
            f"the acquisition takes BaselineAcquisitionPlan, got {type(plan).__name__}; the post-F1 "
            "FutureTrainingProtocol has no T* to give before the lock")
    seeds = _require_seeds(seeds)
    sample = plan.evaluation_bank
    # The legacy API default is healthy for existing instrument fixtures. Stage runners
    # must pass their named initializer explicitly. Keep each object alive until the
    # end so accidental reuse by a caller's factory is detectable without id recycling.
    learners = []
    for seed in seeds:
        learner = LearnerPersistentState() if initializer is None else initializer(q_reference)
        if type(learner) is not LearnerPersistentState:
            raise ProtocolError("the acquisition initializer must return a full persistent learner")
        if any(learner is previous for previous in learners):
            raise ProtocolError("the initializer reused a learner across seeds")
        learners.append(learner)
        protocol = replace(plan, seed=seed)
        for episode in range(plan.acquisition_cap + 1):
            yield _run_material(learner, seed=seed, episode=episode, sample=sample,
                                q_reference=q_reference)
            if episode == plan.acquisition_cap:
                break
            exogenous = ExogenousEpisode.derive(seed, episode)
            trace = episode_rollout(learner, exogenous, protocol=protocol, q_reference=q_reference)
            edits = sweep_edits(learner, trace, exogenous, protocol=protocol, q_reference=q_reference)
            if edits:
                learner.apply_transaction(edits, q_reference=q_reference)


def acquire_master_baseline(plan, *, seeds, q_reference, initializer=None) -> MasterBaseline:
    """In-memory convenience view over the same streaming acquisition.

    An omitted initializer retains the healthy instrument-fixture behaviour. The
    C3 stage entry explicitly passes temporal_initializer; this API selects nothing.
    """
    seeds = _require_seeds(seeds)
    runs = {(run.seed, run.episode): run for run in iter_master_baseline(
        plan, seeds=seeds, q_reference=q_reference, initializer=initializer)}
    return MasterBaseline(seeds=seeds, episodes=tuple(range(plan.acquisition_cap + 1)),
                          sample=plan.evaluation_bank, runs=MappingProxyType(runs))
