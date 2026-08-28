"""S11 验收：d_z 定义（无 sqrt n）、paired 统计、Holm。"""

import numpy as np
import pytest

from rflcc.stats import (
    cohens_dz,
    holm_correct,
    paired_bootstrap_ci,
    paired_sign_flip_test,
    paired_t_statistic,
)


def test_cohens_dz_not_t_statistic():
    diff = np.array([1.0, 2.0, 3.0, 4.0])
    expected = diff.mean() / diff.std(ddof=1)
    assert np.isclose(cohens_dz(diff), expected)
    # 关键：d_z 不含 sqrt(n)
    assert not np.isclose(cohens_dz(diff), expected * np.sqrt(len(diff)))
    # t 统计量单独计算
    assert np.isclose(paired_t_statistic(diff), expected * np.sqrt(len(diff)))


def test_cohens_dz_zero_sd():
    assert cohens_dz(np.array([1.0, 1.0, 1.0])) == 0.0


def test_paired_sign_flip_rejects_shift():
    rng = np.random.RandomState(7)
    x = rng.normal(0, 1, 20)
    y = x + 1.0  # 恒定偏移
    p = paired_sign_flip_test(x, y, n_perm=5000, rng=rng)
    assert p < 0.01


def test_paired_sign_flip_null_pass():
    rng = np.random.RandomState(8)
    x = rng.normal(0, 1, 30)
    y = rng.normal(0, 1, 30)
    p = paired_sign_flip_test(x, y, n_perm=2000, rng=rng)
    assert p > 0.01


def test_paired_bootstrap_ci_contains_zero_for_null():
    rng = np.random.RandomState(9)
    x = rng.normal(0, 1, 50)
    y = rng.normal(0, 1, 50)
    lo, hi = paired_bootstrap_ci(x, y, n_resample=2000, rng=rng)
    assert lo <= 0.0 <= hi


def test_paired_bootstrap_ci_excludes_zero_for_shift():
    rng = np.random.RandomState(10)
    x = rng.normal(0, 1, 50)
    y = x + 0.8
    lo, hi = paired_bootstrap_ci(x, y, n_resample=2000, rng=rng)
    assert hi < 0.0


def test_holm_correction_order():
    ps = [0.01, 0.04, 0.20]
    adj = holm_correct(ps)
    # 保序
    assert adj[0] <= adj[1] <= adj[2]
    assert adj[0] == pytest.approx(0.03)
    assert adj[2] == pytest.approx(0.20)


def test_holm_single():
    assert holm_correct([0.01]) == [pytest.approx(0.01)]


def test_paired_length_mismatch():
    with pytest.raises(ValueError):
        paired_sign_flip_test(np.array([1.0]), np.array([1.0, 2.0]))
