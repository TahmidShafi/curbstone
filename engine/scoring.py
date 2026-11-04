"""Enumerator scoring engine: empirical Bayes shrinkage, feature hypothesis tests, and FDR control."""

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from scipy.stats import beta, betabinom, binom, norm

logger = logging.getLogger(__name__)

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
    return float(max(1e-4, 1.4826 * np.median(np.abs(clean - med))))


def estimate_tau2(d: np.ndarray, s: np.ndarray) -> float:
    """Robust between-unit variance: tau^2 = max(0, (1.4826 * MAD(d))^2 - median(s_e^2))."""
    valid = (~np.isnan(d)) & (~np.isnan(s)) & (s > 0)
    if np.sum(valid) < 2:
        return 0.0
    mad_d = _mad(d[valid])
    med_s2 = float(np.median(s[valid] ** 2))
    return max(0.0, float(mad_d ** 2 - med_s2))


dersimonian_laird = estimate_tau2  # Alias for backward compatibility


def estimate_beta_binomial_rho(
    k: np.ndarray, n: np.ndarray, k_exp: np.ndarray, p0: Optional[np.ndarray] = None
) -> float:
    """Estimate overdispersion rho by method of moments across all enumerators."""
    denom_n = np.maximum(1, n)
    if p0 is None:
        p_s = float(np.sum(k_exp) / np.sum(denom_n))
        p0 = np.clip((k_exp + p_s) / (denom_n + 1), 1e-6, 1.0 - 1e-6)
    var_binom = denom_n * p0 * (1.0 - p0)
    denom = np.sum(denom_n * (denom_n - 1) * p0 * (1.0 - p0))
    if denom <= 0:
        return 1e-4
    raw_rho = float(np.sum((k - denom_n * p0) ** 2 - var_binom) / denom)
    return min(max(1e-4, raw_rho), 0.999)


def benjamini_hochberg(p_values: np.ndarray, q: float = 0.10) -> Tuple[np.ndarray, np.ndarray]:
    """Compute Benjamini-Hochberg flags and adjusted q-values."""
    n = len(p_values)
    if n == 0:
        return np.array([], dtype=bool), np.array([], dtype=float)
    order = np.argsort(p_values)
    sorted_p = p_values[order]
    below = np.where(sorted_p <= (np.arange(1, n + 1) / n) * q)[0]
    flags = np.zeros(n, dtype=bool)
    if len(below) > 0:
        flags[order[: below.max() + 1]] = True
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
    below = np.where(sorted_p <= (np.arange(1, n + 1) / (n * c_n)) * q)[0]
    flags = np.zeros(n, dtype=bool)
    if len(below) > 0:
        flags[order[: below.max() + 1]] = True
    return flags


def score_enumerators(
    features: Union[pd.DataFrame, str, Path],
    no_shrinkage: bool = False,
    no_fdr: bool = False,
    q: float = 0.10,
    empirical_null: bool = True,
) -> pd.DataFrame:
    """Score enumerators using empirical Bayes shrinkage and FDR control."""
    df = pd.read_parquet(features) if isinstance(features, (str, Path)) else features.copy()
    enum_ids = [str(x) for x in df["enumerator_id"]]
    n_enums = len(df)
    n_e = df["n_e"].values.astype(int)

    p_matrix: Dict[str, np.ndarray] = {}
    est_cols: Dict[str, np.ndarray] = {}

    # 1. Feature F3: near_dup (workload-matched null, beta-binomial moments)
    k3 = df["f3_k"].values.astype(int)
    n3 = np.maximum(1, df["f3_n"].values.astype(int))
    mu3 = df["f3_k_exp"].values.astype(float)
    v3 = df["f3_var"].values.astype(float) if "f3_var" in df else mu3
    p3, post3, cilo3, cihi3 = np.ones(n_enums), np.zeros(n_enums), np.zeros(n_enums), np.zeros(n_enums)
    for i in range(n_enums):
        if k3[i] == 0:
            continue
        p0 = mu3[i] / n3[i]
        vb = n3[i] * p0 * (1.0 - p0)
        if no_shrinkage or v3[i] <= vb or p0 <= 1e-6 or p0 >= 1.0 - 1e-6:
            p3[i] = binom.sf(k3[i] - 1, n3[i], max(1e-6, p0))
            pm = k3[i] / n3[i]
            se = math.sqrt(pm * (1.0 - pm) / n3[i])
            post3[i], cilo3[i], cihi3[i] = pm, max(0.0, pm - 1.645 * se), min(1.0, pm + 1.645 * se)
        else:
            rho_i = min(0.999, max(1e-4, (v3[i] - vb) / ((n3[i] - 1) * vb)))
            M_i = (1.0 - rho_i) / rho_i
            a_i, b_i = max(1e-6, p0 * M_i), max(1e-6, (1.0 - p0) * M_i)
            p3[i] = betabinom.sf(k3[i] - 1, n3[i], a_i, b_i)
            a_post, b_post = a_i + k3[i], b_i + n3[i] - k3[i]
            post3[i] = a_post / (a_post + b_post)
            cilo3[i], cihi3[i] = beta.ppf(0.05, a_post, b_post), beta.ppf(0.95, a_post, b_post)
    p_matrix["f3"], est_cols["f3_est"], est_cols["f3_ci_low"], est_cols["f3_ci_high"] = p3, post3, cilo3, cihi3

    # 2. Count features: F4, F8, F9 (smoothed p0 with trimmed rho)
    count_configs = [
        ("f4", "f4_k", "f4_n", "f4_k_exp", "high"),
        ("f8", "f8_k", "f8_n", "f8_k_exp", "high"),
        ("f9", "f9_k", "f9_n", "f9_k_exp", "two-sided"),
    ]
    for f_id, k_col, n_col, exp_col, direction in count_configs:
        k = df[k_col].values.astype(int)
        n = np.maximum(1, df[n_col].values.astype(int))
        k_exp = df[exp_col].values.astype(float)
        p_s = float(np.sum(k_exp) / np.sum(n))
        p0 = np.clip((k_exp + p_s) / (n + 1), 1e-6, 1.0 - 1e-6)

        if no_shrinkage:
            p_vals = binom.sf(k - 1, n, p0) if direction == "high" else np.minimum(1.0, 2.0 * np.minimum(binom.cdf(k, n, p0), binom.sf(k - 1, n, p0)))
            pm = k / n
            ci_low = np.maximum(0.0, pm - 1.645 * np.sqrt(pm * (1 - pm) / n))
            ci_high = np.minimum(1.0, pm + 1.645 * np.sqrt(pm * (1 - pm) / n))
        else:
            p_plain = binom.sf(k - 1, n, p0) if direction == "high" else np.minimum(1.0, 2.0 * np.minimum(binom.cdf(k, n, p0), binom.sf(k - 1, n, p0)))
            trim = p_plain >= 0.01
            rho = estimate_beta_binomial_rho(k[trim], n[trim], k_exp[trim], p0[trim]) if np.sum(trim) >= 3 else estimate_beta_binomial_rho(k, n, k_exp, p0)
            M = (1.0 - rho) / rho
            a_prior, b_prior = np.maximum(1e-6, p0 * M), np.maximum(1e-6, (1.0 - p0) * M)
            if direction == "high":
                p_vals = betabinom.sf(k - 1, n, a_prior, b_prior)
            else:
                p_vals = np.minimum(1.0, 2.0 * np.minimum(betabinom.cdf(k, n, a_prior, b_prior), betabinom.sf(k - 1, n, a_prior, b_prior)))
            a_post, b_post = a_prior + k, b_prior + n - k
            pm = a_post / (a_post + b_post)
            ci_low, ci_high = beta.ppf(0.05, a_post, b_post), beta.ppf(0.95, a_post, b_post)
        p_matrix[f_id], est_cols[f"{f_id}_est"], est_cols[f"{f_id}_ci_low"], est_cols[f"{f_id}_ci_high"] = p_vals, pm, ci_low, ci_high

    # 3. Continuous features: F1, F2, F5, F6, F7, F10
    # Helper to process continuous feature
    def process_cont(d: np.ndarray, s: np.ndarray, valid: np.ndarray, direction: str, f_id: str):
        tau2 = estimate_tau2(d, s) if not no_shrinkage else 0.0
        se = np.where(valid, np.sqrt(tau2 + s ** 2), np.nan)
        z = np.where(valid, d / se, np.nan)
        if empirical_null and not no_shrinkage:
            vz = z[valid]
            if len(vz) > 1:
                z = np.where(valid, (z - float(np.nanmedian(vz))) / _mad(vz), np.nan)
        if direction == "low":
            p = np.where(valid, norm.cdf(z), np.nan)
        elif direction == "high":
            p = np.where(valid, norm.sf(z), np.nan)
        else:
            p = np.where(valid, 2.0 * norm.sf(np.abs(z)), np.nan)
        shrunk = np.where(valid, d * tau2 / (tau2 + s ** 2), np.nan) if tau2 > 0 else (np.where(valid, d, np.nan) if no_shrinkage else np.where(valid, 0.0, np.nan))
        p_matrix[f_id] = p
        est_cols[f"{f_id}_est"] = shrunk
        est_cols[f"{f_id}_ci_low"] = shrunk - 1.645 * se
        est_cols[f"{f_id}_ci_high"] = shrunk + 1.645 * se

    # F1 duration_resid (low)
    d1 = (df["f1_value"] - df["f1_peer_value"]).values
    sig_r = float(df["f1_sigma_r"].iloc[0]) if "f1_sigma_r" in df else max(_mad(d1), 0.25)
    s1 = (1.2533 * sig_r) / np.sqrt(np.maximum(1, n_e))
    process_cont(d1, s1, np.ones(n_enums, dtype=bool), "low", "f1")

    # F2 throughput (high)
    d2 = (df["f2_value"] - df["f2_peer_value"]).values
    s2 = np.maximum(0.5, df["f2_value"].values / np.sqrt(np.maximum(1, n_e)))
    process_cont(d2, s2, np.ones(n_enums, dtype=bool), "high", "f2")

    # F5, F6, F7 dispersion (low)
    for fid in ["f5", "f6", "f7"]:
        val = df[f"{fid}_value"].values.astype(float)
        null_sd = df[f"{fid}_null_sd"].values.astype(float) if f"{fid}_null_sd" in df else np.full(n_enums, np.nan)
        valid = (~np.isnan(val)) & (~np.isnan(null_sd)) & (null_sd > 0)
        process_cont(val, null_sd, valid, "low", fid)

    # F10 dur_size_coupling (two-sided)
    r10 = np.clip(df["f10_value"].values.astype(float), -0.999, 0.999)
    rp10 = np.clip(df["f10_peer_value"].values.astype(float), -0.999, 0.999)
    d10 = np.arctanh(r10) - np.arctanh(rp10)
    valid_f10 = (n_e >= 5) & (~np.isnan(r10)) & (~np.isnan(rp10))
    s10 = np.where(valid_f10, np.sqrt(1.06 / np.maximum(1, n_e - 3)), np.nan)
    process_cont(d10, s10, valid_f10, "two-sided", "f10")

    # 4. Enumerator decision: Bonferroni within enumerator
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

    # 5. FDR across enumerators
    if no_fdr:
        bh_flags = p_e < 0.05
        by_flags = bh_flags
    else:
        bh_flags, _ = benjamini_hochberg(p_e, q=q)
        by_flags = benjamini_yekutieli(p_e, q=q)

    res_dict: Dict[str, Any] = {
        "enumerator_id": enum_ids, "n_interviews": n_e, "m_e": m_e,
        "p_e": np.round(p_e, 6), "risk_score": np.round(risk_score, 4),
        "flagged": bh_flags, "bh_flag": bh_flags, "by_flag": by_flags, "evidence": evidence_list,
    }
    for f in all_f_ids:
        res_dict[f"{f}_p"] = np.round(p_matrix[f], 6)
        res_dict[f"{f}_est"] = np.round(est_cols[f"{f}_est"], 4)
        res_dict[f"{f}_ci_low"] = np.round(est_cols[f"{f}_ci_low"], 4)
        res_dict[f"{f}_ci_high"] = np.round(est_cols[f"{f}_ci_high"], 4)

    return pd.DataFrame(res_dict)
