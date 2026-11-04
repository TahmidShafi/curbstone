"""Enumerator scoring engine: empirical Bayes shrinkage, feature hypothesis tests, and FDR control."""

import logging
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from scipy.stats import beta, betabinom, binom, norm

logger = logging.getLogger(__name__)

# Pre-registered feature testing directions (docs/dgp.md §10)
DIRECTIONS = {
    "f1": "low", "f2": "high", "f3": "high", "f4": "high", "f5": "low",
    "f6": "low", "f7": "low", "f8": "high", "f9": "two-sided", "f10": "two-sided",
}


def _mad(x: np.ndarray) -> float:
    """Median Absolute Deviation (MAD) scaled by 1.4826 for normal consistency."""
    clean = x[~np.isnan(x)]
    if len(clean) == 0:
        return 1.0
    med = float(np.median(clean))
    return float(1.4826 * np.median(np.abs(clean - med)))


def dersimonian_laird(d: np.ndarray, s: np.ndarray) -> float:
    """DerSimonian-Laird estimator of between-unit variance tau^2 with one-pass trim."""
    valid = (~np.isnan(d)) & (~np.isnan(s)) & (s > 0)
    d_v, s_v = d[valid], s[valid]
    if len(d_v) < 3:
        return 0.0
    t_stat = np.abs(d_v / s_v)
    q90 = float(np.percentile(t_stat, 90))
    trim_mask = t_stat <= q90
    d_trim, s_trim = d_v[trim_mask], s_v[trim_mask]
    K = len(d_trim)
    if K < 2:
        return 0.0
    w = 1.0 / (s_trim ** 2)
    sum_w = float(np.sum(w))
    if sum_w <= 0:
        return 0.0
    d_bar = float(np.sum(w * d_trim) / sum_w)
    Q = float(np.sum(w * (d_trim - d_bar) ** 2))
    C = float(sum_w - np.sum(w ** 2) / sum_w)
    if C <= 0:
        return 0.0
    return max(0.0, (Q - (K - 1)) / C)


def estimate_beta_binomial_rho(k: np.ndarray, n: np.ndarray, k_exp: np.ndarray) -> float:
    """Estimate overdispersion rho by method of moments across all enumerators."""
    # Note: fraud inflates rho -> conservative under the null
    denom_n = np.maximum(1, n)
    survey_p = float(np.sum(k_exp) / np.sum(denom_n))
    p0_floor = max(survey_p, 1e-4)
    p0 = np.clip(np.maximum(k_exp / denom_n, p0_floor), 1e-6, 1.0 - 1e-6)
    var_binom = n * p0 * (1.0 - p0)
    denom = np.sum(n * (n - 1) * p0 * (1.0 - p0))
    if denom <= 0:
        logger.info("Zero denominator in beta-binomial rho estimate; using floor 1e-4")
        return 1e-4
    num = np.sum((k - n * p0) ** 2 - var_binom)
    raw_rho = float(num / denom)
    if raw_rho <= 0:
        logger.info(f"Overdispersion rho estimated as {raw_rho:.6f} <= 0; using floor 1e-4")
        return 1e-4
    return min(raw_rho, 0.999)


def benjamini_hochberg(p_values: np.ndarray, q: float = 0.10) -> Tuple[np.ndarray, np.ndarray]:
    """Compute Benjamini-Hochberg flags and adjusted q-values."""
    n = len(p_values)
    if n == 0:
        return np.array([], dtype=bool), np.array([], dtype=float)
    order = np.argsort(p_values)
    sorted_p = p_values[order]
    thresholds = (np.arange(1, n + 1) / n) * q
    below = np.where(sorted_p <= thresholds)[0]
    max_idx = below.max() if len(below) > 0 else -1
    flags = np.zeros(n, dtype=bool)
    if max_idx >= 0:
        flags[order[: max_idx + 1]] = True
    q_vals = np.zeros(n, dtype=float)
    accum_q = 1.0
    for i in range(n - 1, -1, -1):
        accum_q = min(accum_q, float(sorted_p[i] * n / (i + 1)))
        q_vals[order[i]] = accum_q
    return flags, q_vals


def benjamini_yekutieli(p_values: np.ndarray, q: float = 0.10) -> np.ndarray:
    """Compute Benjamini-Yekutieli flags under arbitrary dependence."""
    n = len(p_values)
    if n == 0:
        return np.array([], dtype=bool)
    c_n = float(np.sum(1.0 / np.arange(1, n + 1)))
    order = np.argsort(p_values)
    sorted_p = p_values[order]
    thresholds = (np.arange(1, n + 1) / (n * c_n)) * q
    below = np.where(sorted_p <= thresholds)[0]
    flags = np.zeros(n, dtype=bool)
    if len(below) > 0:
        flags[order[: below.max() + 1]] = True
    return flags


def score_enumerators(
    features: Union[pd.DataFrame, str, Path],
    no_shrinkage: bool = False,
    no_fdr: bool = False,
    q: float = 0.10,
) -> pd.DataFrame:
    """Score enumerators using beta-binomial empirical Bayes shrinkage and FDR control."""
    df = pd.read_parquet(features) if isinstance(features, (str, Path)) else features.copy()
    enum_ids = [str(x) for x in df["enumerator_id"]]
    n_enums = len(df)
    n_e = df["n_e"].values.astype(int)

    # 1. Count features: F3, F4, F8, F9
    count_configs = [
        ("f3", "f3_k", "f3_n", "f3_k_exp", "high"),
        ("f4", "f4_k", "f4_n", "f4_k_exp", "high"),
        ("f8", "f8_k", "f8_n", "f8_k_exp", "high"),
        ("f9", "f9_k", "f9_n", "f9_k_exp", "two-sided"),
    ]
    p_matrix: Dict[str, np.ndarray] = {}
    est_cols: Dict[str, np.ndarray] = {}

    for f_id, k_col, n_col, exp_col, direction in count_configs:
        k = df[k_col].values.astype(int)
        n = np.maximum(1, df[n_col].values.astype(int))
        k_exp = df[exp_col].values.astype(float)
        survey_p = float(np.sum(k_exp) / np.sum(n))
        p0_floor = max(survey_p, 1e-4)
        p0 = np.clip(np.maximum(k_exp / n, p0_floor), 1e-6, 1.0 - 1e-6)

        if no_shrinkage:
            # Plain binomial (rho = 0)
            if direction == "high":
                p_vals = binom.sf(k - 1, n, p0)
            else:
                p_vals = np.minimum(1.0, 2.0 * np.minimum(binom.cdf(k, n, p0), binom.sf(k - 1, n, p0)))
            post_means = k / n
            ci_low = np.maximum(0.0, post_means - 1.645 * np.sqrt(post_means * (1 - post_means) / n))
            ci_high = np.minimum(1.0, post_means + 1.645 * np.sqrt(post_means * (1 - post_means) / n))
        else:
            # Plain binomial p for trimming (B2)
            if direction == "high":
                p_plain = binom.sf(k - 1, n, p0)
            else:
                p_plain = np.minimum(1.0, 2.0 * np.minimum(binom.cdf(k, n, p0), binom.sf(k - 1, n, p0)))

            trim_mask = p_plain >= 0.01
            if np.sum(trim_mask) >= 3:
                k_trim, n_trim, exp_trim = k[trim_mask], n[trim_mask], k_exp[trim_mask]
                rho = estimate_beta_binomial_rho(k_trim, n_trim, exp_trim)
            else:
                rho = estimate_beta_binomial_rho(k, n, k_exp)

            M = (1.0 - rho) / rho
            a_prior, b_prior = np.maximum(1e-6, p0 * M), np.maximum(1e-6, (1.0 - p0) * M)
            if direction == "high":
                p_vals = betabinom.sf(k - 1, n, a_prior, b_prior)
            else:
                p_vals = np.minimum(1.0, 2.0 * np.minimum(
                    betabinom.cdf(k, n, a_prior, b_prior),
                    betabinom.sf(k - 1, n, a_prior, b_prior),
                ))
            a_post = a_prior + k
            b_post = b_prior + n - k
            post_means = a_post / (a_post + b_post)
            ci_low = beta.ppf(0.05, a_post, b_post)
            ci_high = beta.ppf(0.95, a_post, b_post)

        p_matrix[f_id] = p_vals
        est_cols[f"{f_id}_est"] = post_means
        est_cols[f"{f_id}_ci_low"] = ci_low
        est_cols[f"{f_id}_ci_high"] = ci_high

    # 2. Continuous features: F1, F2, F5, F6, F7, F10
    # F1 duration_resid (low)
    diff_f1 = (df["f1_value"] - df["f1_peer_value"]).values
    sig_r = float(df["f1_sigma_r"].iloc[0]) if "f1_sigma_r" in df else max(_mad(diff_f1), 0.25)
    se_f1 = (1.2533 * sig_r) / np.sqrt(np.maximum(1, n_e))
    if no_shrinkage:
        mad_f1 = max(_mad(diff_f1), 1e-4)
        z_f1, se_tot_f1, shrunk_f1 = (diff_f1 - float(np.median(diff_f1))) / mad_f1, np.full(n_enums, mad_f1), diff_f1
    else:
        tau2_f1 = dersimonian_laird(diff_f1, se_f1)
        se_tot_f1 = np.sqrt(tau2_f1 + se_f1 ** 2)
        z_f1 = diff_f1 / se_tot_f1
        shrunk_f1 = diff_f1 * tau2_f1 / (tau2_f1 + se_f1 ** 2) if tau2_f1 > 0 else np.zeros_like(diff_f1)
    p_matrix["f1"] = norm.cdf(z_f1)
    est_cols["f1_est"], est_cols["f1_ci_low"], est_cols["f1_ci_high"] = shrunk_f1, shrunk_f1 - 1.645 * se_tot_f1, shrunk_f1 + 1.645 * se_tot_f1

    # F2 throughput (high)
    diff_f2 = (df["f2_value"] - df["f2_peer_value"]).values
    s_f2 = np.maximum(0.5, df["f2_value"].values / np.sqrt(np.maximum(1, n_e)))
    if no_shrinkage:
        mad_f2 = max(_mad(diff_f2), 1e-4)
        z_f2, se_tot_f2, shrunk_f2 = (diff_f2 - float(np.median(diff_f2))) / mad_f2, np.full(n_enums, mad_f2), diff_f2
    else:
        tau2_f2 = dersimonian_laird(diff_f2, s_f2)
        se_tot_f2 = np.sqrt(tau2_f2 + s_f2 ** 2)
        z_f2 = diff_f2 / se_tot_f2
        shrunk_f2 = diff_f2 * tau2_f2 / (tau2_f2 + s_f2 ** 2) if tau2_f2 > 0 else np.zeros_like(diff_f2)
    p_matrix["f2"] = norm.sf(z_f2)
    est_cols["f2_est"], est_cols["f2_ci_low"], est_cols["f2_ci_high"] = shrunk_f2, shrunk_f2 - 1.645 * se_tot_f2, shrunk_f2 + 1.645 * se_tot_f2

    # F5, F6, F7 dispersion (low)
    for f_id in ["f5", "f6", "f7"]:
        val = df[f"{f_id}_value"].values.astype(float)
        null_sd = df[f"{f_id}_null_sd"].values.astype(float) if f"{f_id}_null_sd" in df else np.full(n_enums, np.nan)
        valid_mask = (~np.isnan(val)) & (~np.isnan(null_sd)) & (null_sd > 0)
        if no_shrinkage:
            mad_val = max(_mad(val), 1e-4)
            z = np.where(valid_mask, (val - float(np.nanmedian(val))) / mad_val, np.nan)
            se, shrunk = np.full(n_enums, mad_val), val
        else:
            tau2 = dersimonian_laird(val, null_sd)
            se = np.where(valid_mask, np.sqrt(tau2 + null_sd ** 2), np.nan)
            z = np.where(valid_mask, val / se, np.nan)
            shrunk = np.where(valid_mask, val * tau2 / (tau2 + null_sd ** 2), np.nan) if tau2 > 0 else np.where(valid_mask, 0.0, np.nan)
        p_matrix[f_id] = np.where(valid_mask, norm.cdf(z), np.nan)
        est_cols[f"{f_id}_est"], est_cols[f"{f_id}_ci_low"], est_cols[f"{f_id}_ci_high"] = shrunk, shrunk - 1.645 * se, shrunk + 1.645 * se

    # F10 dur_size_coupling (two-sided)
    r10 = np.clip(df["f10_value"].values.astype(float), -0.999, 0.999)
    rp10 = np.clip(df["f10_peer_value"].values.astype(float), -0.999, 0.999)
    diff_z10 = np.arctanh(r10) - np.arctanh(rp10)
    valid_f10 = (n_e >= 5) & (~np.isnan(r10)) & (~np.isnan(rp10))
    s10 = np.where(valid_f10, np.sqrt(1.06 / np.maximum(1, n_e - 3)), np.nan)
    if no_shrinkage:
        mad_10 = max(_mad(diff_z10), 1e-4)
        z10 = np.where(valid_f10, (diff_z10 - float(np.nanmedian(diff_z10))) / mad_10, np.nan)
        p_matrix["f10"] = np.where(valid_f10, 2.0 * norm.sf(np.abs(z10)), np.nan)
        se_tot_10 = np.full(n_enums, mad_10)
        shrunk_10 = diff_z10
    else:
        tau2_10 = dersimonian_laird(diff_z10, s10)
        se_tot_10 = np.where(valid_f10, np.sqrt(tau2_10 + s10 ** 2), np.nan)
        z10 = np.where(valid_f10, diff_z10 / se_tot_10, np.nan)
        p_matrix["f10"] = np.where(valid_f10, 2.0 * norm.sf(np.abs(z10)), np.nan)
        shrunk_10 = np.where(valid_f10, diff_z10 * tau2_10 / (tau2_10 + s10 ** 2), np.nan) if tau2_10 > 0 else np.where(valid_f10, 0.0, np.nan)
    est_cols["f10_est"], est_cols["f10_ci_low"], est_cols["f10_ci_high"] = shrunk_10, shrunk_10 - 1.645 * se_tot_10, shrunk_10 + 1.645 * se_tot_10

    # 3. Enumerator decision: Bonferroni within enumerator
    all_f_ids = ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10"]
    p_e = np.ones(n_enums)
    m_e = np.zeros(n_enums, dtype=int)
    evidence_list: List[str] = []

    for i in range(n_enums):
        row_p = {f: p_matrix[f][i] for f in all_f_ids if not np.isnan(p_matrix[f][i])}
        m_e[i] = len(row_p)
        if m_e[i] > 0:
            min_p = min(row_p.values())
            p_e[i] = min(1.0, m_e[i] * min_p)
            cutoff = 0.05 / m_e[i]
            ev = [f.upper() for f, val in row_p.items() if val < cutoff]
            evidence_list.append(", ".join(ev))
        else:
            p_e[i] = 1.0
            evidence_list.append("")

    risk_score = -np.log10(np.maximum(p_e, 1e-16))

    # 4. FDR across enumerators
    if no_fdr:
        flagged = p_e < 0.05
        bh_flags = flagged
        by_flags = flagged
    else:
        bh_flags, _ = benjamini_hochberg(p_e, q=q)
        by_flags = benjamini_yekutieli(p_e, q=q)
        flagged = bh_flags

    res_dict: Dict[str, Any] = {
        "enumerator_id": enum_ids,
        "n_interviews": n_e,
        "m_e": m_e,
        "p_e": np.round(p_e, 6),
        "risk_score": np.round(risk_score, 4),
        "flagged": flagged,
        "bh_flag": bh_flags,
        "by_flag": by_flags,
        "evidence": evidence_list,
    }
    for f in all_f_ids:
        res_dict[f"{f}_p"] = np.round(p_matrix[f], 6)
        res_dict[f"{f}_est"] = np.round(est_cols[f"{f}_est"], 4)
        res_dict[f"{f}_ci_low"] = np.round(est_cols[f"{f}_ci_low"], 4)
        res_dict[f"{f}_ci_high"] = np.round(est_cols[f"{f}_ci_high"], 4)

    return pd.DataFrame(res_dict)
