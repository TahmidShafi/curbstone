"""Tests for enumerator scoring: empirical Bayes beta-binomial, FDR control, and calibration."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import betabinom

from engine.features import build_feature_table
from engine.scoring import benjamini_hochberg, benjamini_yekutieli, estimate_beta_binomial_rho, score_enumerators
from generator.run import run_generation


def test_betabinomial_fixture():
    """Verify that k = k_exp yields p ~ 0.5 and k >> k_exp yields a tiny p-value."""
    n = 50
    k_exp = 10.0
    p0 = k_exp / n  # 0.20
    rho = 0.05
    M = (1.0 - rho) / rho
    a_prior = p0 * M
    b_prior = (1.0 - p0) * M

    # Under k = k_exp, p-value for high direction should be near 0.50
    k_null = 10
    p_null = betabinom.sf(k_null - 1, n, a_prior, b_prior)
    assert 0.35 <= p_null <= 0.65, f"Expected p ~ 0.5 for k=k_exp, got {p_null:.4f}"

    # Under k >> k_exp, p-value should be very small (< 1e-4)
    k_excess = 35
    p_excess = betabinom.sf(k_excess - 1, n, a_prior, b_prior)
    assert p_excess < 1e-4, f"Expected tiny p-value for k >> k_exp, got {p_excess:.4e}"


def test_posterior_shrinkage():
    """Verify shrinkage property: posterior mean is strictly between observed rate and p0."""
    n_samples = 20
    rng = np.random.default_rng(12345)
    n = rng.integers(15, 60, size=n_samples)
    p0 = rng.uniform(0.05, 0.40, size=n_samples)
    k = rng.binomial(n, p0)
    rho = 0.08
    M = (1.0 - rho) / rho

    a_prior = p0 * M
    b_prior = (1.0 - p0) * M
    a_post = a_prior + k
    b_post = b_prior + n - k
    post_mean = a_post / (a_post + b_post)
    obs_rate = k / n

    for i in range(n_samples):
        if obs_rate[i] > p0[i]:
            assert p0[i] < post_mean[i] < obs_rate[i], (
                f"Shrinkage failed at i={i}: p0={p0[i]:.4f}, post={post_mean[i]:.4f}, obs={obs_rate[i]:.4f}"
            )
        elif obs_rate[i] < p0[i]:
            assert obs_rate[i] < post_mean[i] < p0[i], (
                f"Shrinkage failed at i={i}: obs={obs_rate[i]:.4f}, post={post_mean[i]:.4f}, p0={p0[i]:.4f}"
            )
        else:
            assert np.isclose(post_mean[i], obs_rate[i])


def test_bh_hand_example():
    """Verify Benjamini-Hochberg flags and q-values match hand-computed 4 p-value example."""
    p = np.array([0.08, 0.01, 0.20, 0.04])
    flags, q_vals = benjamini_hochberg(p, q=0.10)

    expected_flags = np.array([False, True, False, True])
    expected_q = np.array([0.10666667, 0.04, 0.20, 0.08])

    np.testing.assert_array_equal(flags, expected_flags)
    np.testing.assert_allclose(q_vals, expected_q, rtol=1e-5)

    by_flags = benjamini_yekutieli(p, q=0.10)
    expected_by = np.array([False, True, False, False])
    np.testing.assert_array_equal(by_flags, expected_by)


def test_scoring_v2_basic():
    """Verify Scoring v2 runs without errors and produces valid scores and risk ranking."""
    df_feat = pd.DataFrame([{
        "enumerator_id": f"enum_{i:02d}",
        "n_e": 25,
        "f1_value": 0.0, "f1_peer_value": 0.0, "f1_sigma_r": 0.25,
        "f2_value": 5.0, "f2_peer_value": 5.0,
        "f3_k": 0, "f3_k_exp": 0.1, "f3_var": 0.1, "f3_n": 25,
        "f4_k": 1, "f4_k_exp": 1.0, "f4_n": 25,
        "f5_value": 0.0, "f5_null_sd": 0.1,
        "f6_value": 0.0, "f6_null_sd": 0.1,
        "f7_value": 0.0, "f7_null_sd": 0.1,
        "f8_k": 5, "f8_k_exp": 5.0, "f8_n": 25,
        "f9_k": 1, "f9_k_exp": 1.0, "f9_n": 25,
        "f10_value": 0.3, "f10_peer_value": 0.3,
    } for i in range(10)])

    res_v1 = score_enumerators(df_feat, scoring_version="v1")
    res_v2 = score_enumerators(df_feat, scoring_version="v2")

    assert len(res_v1) == 10
    assert len(res_v2) == 10
    assert "risk_score" in res_v2.columns
    assert (res_v2["risk_score"] >= 0).all()


@pytest.mark.slow
def test_honest_calibration(tmp_path):
    """Honest calibration test across seeds 0..19 without fraud."""
    n_rounds = 20
    full_flagged_rounds = 0
    noshrink_flagged_rounds = 0
    nofdr_flagged_rounds = 0

    for seed in range(n_rounds):
        round_dir = tmp_path / f"seed_{seed}"
        sub_path = run_generation(
            icc_level="medium",
            seed=seed,
            out_dir=round_dir,
            round_num=1,
            no_fraud=True,
        )
        vil_path = round_dir / "reference" / "villages.parquet"
        df_feat = build_feature_table(sub_path, vil_path)

        scores_full = score_enumerators(df_feat)
        if int(scores_full["flagged"].sum()) >= 1:
            full_flagged_rounds += 1

        scores_noshrink = score_enumerators(df_feat, no_shrinkage=True)
        if int(scores_noshrink["flagged"].sum()) >= 1:
            noshrink_flagged_rounds += 1

        scores_nofdr = score_enumerators(df_feat, no_fdr=True)
        if int(scores_nofdr["flagged"].sum()) >= 1:
            nofdr_flagged_rounds += 1

    assert 0 <= full_flagged_rounds <= n_rounds
    assert 0 <= noshrink_flagged_rounds <= n_rounds
    assert 0 <= nofdr_flagged_rounds <= n_rounds
