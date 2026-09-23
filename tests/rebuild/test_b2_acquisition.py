r"""$F_0$ §3's master acquisition and its artifact, gated.

$$\boxed{\texttt{BaselineAcquisitionPlan} \;\longrightarrow\; \texttt{acquire\_master\_baseline}
\;\longrightarrow\; \left\{V_{\sigma,e,u}\right\} \cup \text{sufficient A89 pre-update eligibility
material}}$$

These tests run on **fixtures and an operational benchmark key only** ($\mathcal B_{\text{bench}}$), never on
$\mathcal S_{\text{smoke}}$ or $\mathcal S_{\text{dev}}$: construction builds and gates the harness, it does
not draw a scientific seed. $\mathcal S_{\text{dev}}$ is what §2 calls "a development seed the unit of an
evaluation sample" to *avoid*, so using one here would be the defect the ordering exists to prevent.

The central test is **sufficiency itself**: the stored incidence must reproduce, mechanically, the same
$C_r^{A,\sigma,e}(c)$ the frozen instrument computes by asking $W_{\sigma,e}$ directly.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fractions import Fraction  # noqa: E402
from types import MappingProxyType  # noqa: E402

from rfl_rebuild.b1.errors import ProtocolError  # noqa: E402
from rfl_rebuild.b2.acquisition import (  # noqa: E402
    MasterBaseline,
    RunMaterial,
    Sufficient,
    acquire_master_baseline,
    sufficient_error,
)
from rfl_rebuild.b2.evalorder import prefix  # noqa: E402
from rfl_rebuild.b2.training import (  # noqa: E402
    BaselineAcquisitionPlan,
    FutureTrainingProtocol,
    train_curve,
)
from rfl_rebuild.b2.unaffected import (  # noqa: E402
    CHANNELS,
    REFINEMENTS,
    ControllerSite,
    CreditedSite,
    EvaluationScene,
    pre_update_traces,
    refinement,
)
from rfl_rebuild.env.kernel import State  # noqa: E402
from rfl_rebuild.learner.reference import reference_view_from  # noqa: E402
from rfl_rebuild.learner.store import LearnerPersistentState  # noqa: E402
from rfl_rebuild.solve.dp import solve_reference  # noqa: E402

REFERENCE = reference_view_from(solve_reference())
KEY = 900001                    # an operational benchmark key, not a scientific seed
KEY2 = 900002
BANK = prefix(8)
OUTSIDE = CreditedSite("X", ControllerSite(state=State(x=3, y=3, t=5, kappa=1, phi=3), cmd=1))


def _plan(**overrides) -> BaselineAcquisitionPlan:
    fields = dict(seed=KEY, alpha=Fraction(1, 2), epsilon=Fraction(1, 4), acquisition_cap=1,
                  evaluation_bank=BANK)
    fields.update(overrides)
    return BaselineAcquisitionPlan(**fields)


@pytest.fixture(scope="module")
def master() -> MasterBaseline:
    return acquire_master_baseline(_plan(), seeds=(KEY, KEY2), q_reference=REFERENCE)


# --- the numerical recovery -------------------------------------------------------------------------

def test_1_the_population_standard_error_is_recovered_from_the_triple():
    # values (0.1, 0.3): mean 0.2, population variance 0.01, se = sqrt(0.01 / 2)
    assert sufficient_error(Sufficient(2, 0.4, 0.10)) == pytest.approx((0.01 / 2) ** 0.5)
    assert sufficient_error(Sufficient(1, 0.0, 0.0)) == 0.0    # a constant set at the origin is exact
    assert sufficient_error(Sufficient(0, 0.0, 0.0)) is None   # empty is inadmissible, never zero
    assert sufficient_error(Sufficient(-1, 0.0, 0.0)) is None


def test_2_the_triple_recovery_is_not_bit_exact_on_a_constant_set():
    r"""**A measured caveat, recorded rather than smoothed over.**

    §4.0 says the triple "recover[s] this form exactly". In float64 it does not, for a set whose values are
    equal but not representable exactly: $\sum V^2/n - (\sum V/n)^2$ is a difference of two nearly equal
    numbers, so the population variance of a constant set comes back as round-off instead of $0$ --- here
    $0.49 - 0.7^2 = 5.55 \times 10^{-17}$, hence $7.45 \times 10^{-9}$ rather than $0$. It is small and it is
    *not* zero, which matters because §4.4's zero-case rules are exact comparisons on this quantity. The
    definitional route --- §4.0's own two-pass form over the set's values, which the artifact also stores ---
    returns exactly $0$; both are pinned here so the difference cannot pass unnoticed.
    """
    rounded = sufficient_error(Sufficient(1, 0.7, 0.49))
    assert rounded == pytest.approx(7.450580596923828e-09, rel=1e-3)
    assert rounded != 0.0
    levels = [0.7]
    two_pass = (sum((v - sum(levels) / len(levels)) ** 2 for v in levels) / len(levels)) ** 0.5
    assert two_pass == 0.0


def test_3_a_negative_variance_from_round_off_is_clamped_not_kept():
    # 2.9999999999999996/3 - 1.0 < 0: the true variance is 0, and the sqrt of a negative is not a number
    assert sufficient_error(Sufficient(3, 3.0, 2.9999999999999996)) == 0.0


# --- the matrix ------------------------------------------------------------------------------------

def test_8_the_matrix_carries_one_level_per_seed_episode_and_scene(master):
    assert master.seeds == (KEY, KEY2) and master.episodes == (0, 1)
    assert master.sample == BANK, "the envelope's bank is the master bank, in the order it was declared"
    for sigma in master.seeds:
        for e in master.episodes:
            assert len(master.levels(sigma, e)) == len(BANK)
        assert len(master.mean_curve(sigma)) == len(master.episodes)
        # the mean curve is a view of the matrix, not a second computation
        for e in master.episodes:
            assert master.mean_curve(sigma)[e] == pytest.approx(
                sum(master.levels(sigma, e)) / len(BANK))


def test_4_the_episode_axis_is_the_cap_not_a_measurement_choice():
    for cap in (1, 2):
        small = acquire_master_baseline(_plan(acquisition_cap=cap), seeds=(KEY,), q_reference=REFERENCE)
        assert small.episodes == tuple(range(cap + 1))
        assert len(small.levels(KEY, cap)) == len(BANK)


def test_5_the_acquisition_trains_through_a91_s_own_path():
    r"""**The wiring gate**: the acquisition's curve is `train_curve`'s curve.

    `acquire_master_baseline` does its own evaluation gathering (it must: `train_curve` takes the post-$F_1$
    protocol that does not exist before the lock), so the risk this test closes is that the two disagree about
    what a training episode is. Same seed, same $\alpha$, same $\varepsilon$, same bank, one grid = the whole
    axis, and the two curves must agree exactly.
    """
    single = acquire_master_baseline(_plan(acquisition_cap=2), seeds=(KEY,), q_reference=REFERENCE)
    protocol = FutureTrainingProtocol(seed=KEY, alpha=Fraction(1, 2), epsilon=Fraction(1, 4), t_max=2,
                                      grid=(0, 1, 2), evaluation_sample=BANK, v_pre=0.5)
    curve = train_curve(LearnerPersistentState(), protocol=protocol, q_reference=REFERENCE)
    assert tuple(curve.episodes) == single.episodes
    for value, episode in zip(curve.values, single.episodes):
        assert value == single.mean_curve(KEY)[episode], f"e = {episode}"


def test_5b_the_mean_uses_a91_s_accumulation_order_not_python_s_compensated_sum():
    r"""The mean is the quantity $f_T$, $f_G$ and $f_R$ read, and CPython's `sum()` is Neumaier-compensated.

    On these values the two aggregations differ by one ulp ($0.885$ against $0.8849999999999999$), which is
    why the acquisition reproduces A91's left-to-right accumulation. This test is what keeps a later
    "cleanup" from quietly substituting `sum(values) / len(values)` and moving every curve by an ulp.
    """
    values = (0.9199999999999999, 0.88, 0.9, 0.84, 0.9199999999999999, 0.88, 0.9, 0.84)
    total = 0.0
    for value in values:
        total += value
    assert total / len(values) != sum(values) / len(values)   # the two orders really do differ here
    run = RunMaterial(seed=KEY, episode=0, levels=values, success=(True,) * len(values),
                      consulted=MappingProxyType({arch: MappingProxyType({}) for arch in CHANNELS}),
                      domains=MappingProxyType({arch: () for arch in CHANNELS}),
                      uncontacted=MappingProxyType({arch: False for arch in CHANNELS}),
                      outside_domain=MappingProxyType({arch: 0 for arch in CHANNELS}))
    assert run.mean() == total / len(values) != sum(values) / len(values)


def test_6_a_healthy_baseline_run_is_the_reference_s_fixed_point(master):
    r"""A91's own test_15 asserts that a healthy learner neither moves nor gains overrides; this is what that
    means for the envelope, recorded here because every rule of §4 reads these curves.

    The baseline run starts at $W_0$ = healthy, whose effective table **is** $Q^{*}$, and A91's update is the
    Bellman operator evaluated at $Q^{*}$ --- so every edit it computes equals the reference value and is
    canonicalised away. The consequence is that the envelope's baseline matrix is constant in $e$: $f_T$'s
    windows are all exactly flat, and the `FlipRate` constant-window exception of `05` §6.1 is the case that
    is reached, for every seed. That is a property of the frozen instrument, not of this module; it is
    surfaced to the reviewer rather than adjusted here.
    """
    for seed in master.seeds:
        first = master.levels(seed, 0)
        for episode in master.episodes:
            assert master.levels(seed, episode) == first, (seed, episode)
            assert master.material(seed, episode).success == master.material(seed, 0).success
    assert master.levels(KEY, 0) == master.levels(KEY2, 0), "W_0 is one state, not one per seed"


def test_7_the_run_key_is_the_seed_and_not_a_plan_field(master):
    r"""The envelope carries no run identity: the run's own protocol is the envelope *carrying* the key."""
    other = acquire_master_baseline(_plan(seed=KEY2), seeds=(KEY,), q_reference=REFERENCE)
    assert other.levels(KEY, 0) == master.levels(KEY, 0)
    assert other.levels(KEY, 1) == master.levels(KEY, 1)


# --- the eligibility material ----------------------------------------------------------------------

def test_9_the_run_s_own_credited_domains_are_recorded(master):
    for sigma in master.seeds:
        for e in master.episodes:
            counts = {arch: len(master.domain(arch, sigma, e)) for arch in CHANNELS}
            # D_Q and P are learner-independent (A89 §77.4 enumerates them without a trace)
            assert counts["D_Q"] == 13824 and counts["P"] == 4, counts
            assert counts["X"] > 0
            for arch in CHANNELS:
                assert master.material(sigma, e).outside_domain[arch] == 0, (
                    f"{arch}: a bank episode consulted a site the run's own domain excludes")
                assert set(master.consulted(arch, sigma, e)) <= set(master.domain(arch, sigma, e))


def test_10_whether_a_domain_holds_an_uncontacted_site_is_recorded_not_assumed(master):
    r"""$P$ is the case that makes this load-bearing: all four sites are consulted by any full bank, so
    the shared uncontacted value is *not* attained there and a metric that added it would overstate the
    maximum."""
    assert master.uncontacted("P", KEY, 0) is False
    assert master.uncontacted("D_Q", KEY, 0) is True
    assert len(master.consulted("P", KEY, 0)) == 4
    for sigma in master.seeds:
        for e in master.episodes:
            for arch in CHANNELS:
                if master.uncontacted(arch, sigma, e):
                    assert len(master.consulted(arch, sigma, e)) < len(master.domain(arch, sigma, e))
                else:
                    assert len(master.consulted(arch, sigma, e)) == len(master.domain(arch, sigma, e))


@pytest.mark.parametrize("arch", CHANNELS)
def test_11_the_material_reproduces_the_instrument_s_own_eligibility(master, arch):
    r"""**The sufficiency claim of §3, verified rather than asserted.**

    The stored incidence is asked for $C_r^{A,\sigma,e}(c)$ and the frozen instrument is asked the same
    question of the same learner, through `eligibility`/`refinement` and the run's own unedited episodes. If
    the artifact were insufficient --- if, say, $H_{\text{pre}}$ or a consulted scene were missing --- these
    two answers would differ.
    """
    learner = LearnerPersistentState()
    traces = pre_update_traces(learner=learner, q_reference=REFERENCE, domain=master.sample)
    sites = [site for site in master.domain(arch, KEY, 0)
             if site in master.consulted(arch, KEY, 0)][:4]
    assert sites, f"{arch} consults nothing on this bank, so the test would be vacuous"
    for site in sites:
        for name in REFINEMENTS:
            mine = master.slice_indices(arch, KEY, 0, site, name)
            theirs = tuple(i for i, unit in enumerate(master.sample)
                           if unit in refinement(site, traces, name, domain=master.sample))
            assert mine == theirs, (arch, site.render(), name)
            triple = master.sufficient(arch, KEY, 0, site, name)
            direct = [master.levels(KEY, 0)[i] for i in mine]
            assert triple == Sufficient(len(direct), sum(direct), sum(v * v for v in direct))
            assert master.error(arch, KEY, 0, site, name) == sufficient_error(triple)


@pytest.mark.parametrize("arch", CHANNELS)
def test_12_a_site_no_episode_consults_shares_the_generic_value(master, arch):
    r"""The other half of the recovery: for a site the bank never consults, $C_r(c) = H_{\text{pre}} \cap
    S_r$ whatever the site is, so every such site of the domain carries the *same* triple --- which is why
    the artifact can serve the whole $13824$-site $D_Q$ domain without storing $13824$ triples per run."""
    if not master.uncontacted(arch, KEY, 0):
        pytest.skip(f"{arch}'s domain is fully consulted on this bank: there is no shared value")
    traces = pre_update_traces(learner=LearnerPersistentState(), q_reference=REFERENCE,
                               domain=master.sample)
    sites = [s for s in master.domain(arch, KEY, 0) if s not in master.consulted(arch, KEY, 0)][:3]
    assert sites, "uncontacted was recorded but the domain holds none"
    for site in sites:
        for name in REFINEMENTS:
            mine = master.slice_indices(arch, KEY, 0, site, name)
            theirs = tuple(i for i, unit in enumerate(master.sample)
                           if unit in refinement(site, traces, name, domain=master.sample))
            assert mine == theirs, (arch, site.render(), name)
            assert master.sufficient(arch, KEY, 0, site, name) == master.generic_sufficient(KEY, 0, name)
        assert master.error(arch, KEY, 0, site, "eligible_all") == sufficient_error(
            master.generic_sufficient(KEY, 0, "eligible_all"))


# --- refusals ---------------------------------------------------------------------------------------

def test_13_the_acquisition_refuses_a_post_f1_protocol():
    post = FutureTrainingProtocol(seed=KEY, alpha=Fraction(1, 2), epsilon=Fraction(1, 4), t_max=2,
                                  grid=(0, 1, 2), evaluation_sample=BANK, v_pre=0.5)
    with pytest.raises(ProtocolError, match="BaselineAcquisitionPlan"):
        acquire_master_baseline(post, seeds=(KEY,), q_reference=REFERENCE)


def test_14_the_acquisition_refuses_a_seed_set_that_is_not_a_set():
    for bad in ((), (True,), (KEY, "900002"), (KEY, KEY)):
        with pytest.raises(ProtocolError, match="true integers|repeats a seed|is empty"):
            acquire_master_baseline(_plan(), seeds=bad, q_reference=REFERENCE)


def test_15_a_site_outside_the_run_s_own_domain_is_refused(master):
    r"""§4.4 maximises over the run's credited domain: widening it by hand is inventing eligibility."""
    with pytest.raises(ProtocolError, match="not in X's credited domain"):
        master.slice_indices("X", KEY, 0, OUTSIDE, "eligible_all")
    with pytest.raises(ProtocolError, match="belongs to"):
        master.slice_indices("D_Q", KEY, 0, CreditedSite("P", 0), "eligible_all")
    with pytest.raises(ProtocolError, match="CreditedSite"):
        master.slice_indices("D_Q", KEY, 0, "not-a-site", "eligible_all")
    with pytest.raises(ProtocolError, match="frozen channels"):
        master.slice_indices("Q_star", KEY, 0, OUTSIDE, "eligible_all")
    with pytest.raises(ProtocolError, match="unknown refinement"):
        master.slice_indices("P", KEY, 0, master.domain("P", KEY, 0)[0], "eligible_everything")


def test_16_the_artifact_refuses_a_matrix_that_is_not_aligned_with_the_bank():
    run = RunMaterial(seed=KEY, episode=0, levels=(0.5,), success=(True,),
                      consulted=MappingProxyType({arch: MappingProxyType({}) for arch in CHANNELS}),
                      domains=MappingProxyType({arch: () for arch in CHANNELS}),
                      uncontacted=MappingProxyType({arch: False for arch in CHANNELS}),
                      outside_domain=MappingProxyType({arch: 0 for arch in CHANNELS}))
    with pytest.raises(ProtocolError, match="not aligned"):
        MasterBaseline(seeds=(KEY,), episodes=(0,), sample=BANK, runs=MappingProxyType({(KEY, 0): run}))
    with pytest.raises(ProtocolError, match="missing the run"):
        MasterBaseline(seeds=(KEY,), episodes=(0,), sample=BANK, runs=MappingProxyType({}))


def test_17_the_smoke_bank_would_be_a_prefix_of_the_same_order():
    r"""A scene-level guard on the other half of §3: the bank is a prefix, and the prefix is balanced."""
    for n in (100, 256):
        bank = prefix(n)
        assert len(bank) == n and len(set(bank)) == n
        assert {u.kappa for u in bank} == {0, 1}
        assert len({u.cause_rank for u in bank}) == 60
        assert type(bank[0]) is EvaluationScene
