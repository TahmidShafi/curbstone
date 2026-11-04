"""Enumerator scoring engine: empirical Bayes shrinkage, feature hypothesis tests, and FDR control.

Supports Scoring v1 (pre-registered), Scoring v2 (post-hoc ranking), and Scoring v3 (cell-shrunk peer expectations).
"""

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from scipy.stats import beta, betabinom, binom, norm, t

from engine.scoring_helpers import (
    _mad,
    benjamini_hochberg,
    benjamini_yekutieli,
    dersimonian_laird,
    estimate_beta_binomial_rho,
    estimate_tau2,
)

logger = logging.getLogger(__name__)


def score_enumerators(
    features: Union[pd.DataFrame, str, Path],
    no_shrinkage: bool = False,
    no_fdr: bool = False,
    q: float = 0.10,
    empirical_null: bool = True,
    scoring_version: str = "v1",
) -> pd.DataFrame:
    """Score enumerators using empirical Bayes shrinkage and FDR control (v1, v2, or v3)."""
    df = pd.read_parquet(features) if isinstance(features, (str, Path)) else features.copy()
    enum_ids = [str(x) for x in df["enumerator_id"]]
    n_enums, n_e = len(df), df["n_e"].values.astype(int)
    ver_str = str(scoring_version).lower()
    is_v2, is_v3 = ver_str in ["v2", "2"], ver_str in ["v3", "3"]

    p_matrix: Dict[str, np.ndarray] = {}
    est_cols: Dict[str, np.ndarray] = {}

    # 1. Feature F3: near_dup
    k3 = df["f3_k"].values.astype(int)
    n3 = np.maximum(1, df["f3_n"].values.astype(int))
    p3, post3, cilo3, cihi3 = np.ones(n_enums), np.zeros(n_enums), np.zeros(n_enums), np.zeros(n_enums)

    if is_v3:
        mu3 = df["f3_k_exp_v3"].values.astype(float) if "f3_k_exp_v3" in df else df["f3_k_exp"].values.astype(float)
        v3 = df["f3_var_v3"].values.astype(float) if "f3_var_v3" in df else df["f3_var"].values.astype(float)
        p0_3 = np.clip(mu3 / n3, 1e-6, 1.0 - 1e-6)
        vb_3 = n3 * p0_3 * (1.0 - p0_3)
        veff_3 = np.maximum(v3, vb_3)
        for i in range(n_enums):
            if k3[i] == 0:
                continue
            if no_shrinkage or veff_3[i] <= vb_3[i] + 1e-9:
                p3[i] = binom.sf(k3[i] - 1, n3[i], p0_3[i])
                pm = k3[i] / n3[i]
                se = math.sqrt(pm * (1.0 - pm) / n3[i])
                post3[i], cilo3[i], cihi3[i] = pm, max(0.0, pm - 1.645 * se), min(1.0, pm + 1.645 * se)
            else:
                rho_i = min(0.999, max(1e-4, (veff_3[i] - vb_3[i]) / ((n3[i] - 1) * vb_3[i])))
                M_i = (1.0 - rho_i) / rho_i
                a_i, b_i = max(1e-6, p0_3[i] * M_i), max(1e-6, (1.0 - p0_3[i]) * M_i)
                p3[i] = betabinom.sf(k3[i] - 1, n3[i], a_i, b_i)
                a_post, b_post = a_i + k3[i], b_i + n3[i] - k3[i]
                post3[i] = a_post / (a_post + b_post)
                cilo3[i], cihi3[i] = beta.ppf(0.05, a_post, b_post), beta.ppf(0.95, a_post, b_post)
    elif is_v2:
        mu3 = df["f3_k_exp"].values.astype(float)
        v3 = df["f3_var"].values.astype(float) if "f3_var" in df else mu3
        p_s3 = float(np.sum(mu3) / np.sum(n3))
        p0_3 = np.clip((mu3 + p_s3) / (n3 + 1), 1e-6, 1.0 - 1e-6)
        vb_3 = n3 * p0_3 * (1.0 - p0_3)
        veff_3 = np.maximum(v3, vb_3)
        for i in range(n_enums):
            if k3[i] == 0:
                continue
            if no_shrinkage or veff_3[i] <= vb_3[i] + 1e-9:
                p3[i] = binom.sf(k3[i] - 1, n3[i], p0_3[i])
                pm = k3[i] / n3[i]
                se = math.sqrt(pm * (1.0 - pm) / n3[i])
                post3[i], cilo3[i], cihi3[i] = pm, max(0.0, pm - 1.645 * se), min(1.0, pm + 1.645 * se)
            else:
                rho_i = min(0.999, max(1e-4, (veff_3[i] - vb_3[i]) / ((n3[i] - 1) * vb_3[i])))
                M_i = (1.0 - rho_i) / rho_i
                a_i, b_i = max(1e-6, p0_3[i] * M_i), max(1e-6, (1.0 - p0_3[i]) * M_i)
                p3[i] = betabinom.sf(k3[i] - 1, n3[i], a_i, b_i)
                a_post, b_post = a_i + k3[i], b_i + n3[i] - k3[i]
                post3[i] = a_post / (a_post + b_post)
                cilo3[i], cihi3[i] = beta.ppf(0.05, a_post, b_post), beta.ppf(0.95, a_post, b_post)
    else:
        # v1 code path
        mu3 = df["f3_k_exp"].values.astype(float)
        v3 = df["f3_var"].values.astype(float) if "f3_var" in df else mu3
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

    # 2. Count features: F4, F8, F9
    count_configs = [
        ("f4", "f4_k", "f4_n", "f4_k_exp", "high"),
        ("f8", "f8_k", "f8_n", "f8_k_exp", "high"),
        ("f9", "f9_k", "f9_n", "f9_k_exp", "two-sided"),
    ]
    for f_id, k_col, n_col, exp_col, direction in count_configs:
        k = df[k_col].values.astype(int)
        n = np.maximum(1, df[n_col].values.astype(int))

        if is_v3:
            v3_exp = f"{f_id}_k_exp_v3"
            k_exp = df[v3_exp].values.astype(float) if v3_exp in df else df[exp_col].values.astype(float)
            p0 = np.clip(k_exp / n, 1e-6, 1.0 - 1e-6)
            rho = estimate_beta_binomial_rho(k, n, k_exp, p0)
        else:
            k_exp = df[exp_col].values.astype(float)
            p_s = float(np.sum(k_exp) / np.sum(n))
            p0 = np.clip((k_exp + p_s) / (n + 1), 1e-6, 1.0 - 1e-6)
            if is_v2:
                rho = estimate_beta_binomial_rho(k, n, k_exp, p0)
            else:
                p_plain = binom.sf(k - 1, n, p0) if direction == "high" else np.minimum(1.0, 2.0 * np.minimum(binom.cdf(k, n, p0), binom.sf(k - 1, n, p0)))
                trim = p_plain >= 0.01
                rho = estimate_beta_binomial_rho(k[trim], n[trim], k_exp[trim], p0[trim]) if np.sum(trim) >= 3 else estimate_beta_binomial_rho(k, n, k_exp, p0)

        if no_shrinkage:
            p_vals = binom.sf(k - 1, n, p0) if direction == "high" else np.minimum(1.0, 2.0 * np.minimum(binom.cdf(k, n, p0), binom.sf(k - 1, n, p0)))
            pm = k / n
            ci_low = np.maximum(0.0, pm - 1.645 * np.sqrt(pm * (1 - pm) / n))
            ci_high = np.minimum(1.0, pm + 1.645 * np.sqrt(pm * (1 - pm) / n))
        else:
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
    def process_cont(d: np.ndarray, s: np.ndarray, valid: np.ndarray, direction: str, f_id: str):
        tau2 = estimate_tau2(d, s) if not no_shrinkage else 0.0
        se = np.where(valid, np.sqrt(tau2 + s ** 2), np.nan)
        z = np.where(valid, d / se, np.nan)

        if is_v2 or is_v3:
            df_t = max(1, int(np.sum(valid)) - 1)
            if direction == "low":
                p = np.where(valid, t.cdf(z, df=df_t), np.nan)
            elif direction == "high":
                p = np.where(valid, t.sf(z, df=df_t), np.nan)
            else:
                p = np.where(valid, 2.0 * t.sf(np.abs(z), df=df_t), np.nan)
        else:
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

    d1 = (df["f1_value"] - df["f1_peer_value"]).values
    sig_r = float(df["f1_sigma_r"].iloc[0]) if "f1_sigma_r" in df else max(_mad(d1), 0.25)
    s1 = (1.2533 * sig_r) / np.sqrt(np.maximum(1, n_e))
    process_cont(d1, s1, np.ones(n_enums, dtype=bool), "low", "f1")

    d2 = (df["f2_value"] - df["f2_peer_value"]).values
    s2 = np.maximum(0.5, df["f2_value"].values / np.sqrt(np.maximum(1, n_e)))
    process_cont(d2, s2, np.ones(n_enums, dtype=bool), "high", "f2")

    for fid in ["f5", "f6", "f7"]:
        val = df[f"{fid}_value"].values.astype(float)
        null_sd = df[f"{fid}_null_sd"].values.astype(float) if f"{fid}_null_sd" in df else np.full(n_enums, np.nan)
        valid = (~np.isnan(val)) & (~np.isnan(null_sd)) & (null_sd > 0)
        process_cont(val, null_sd, valid, "low", fid)

    r10 = np.clip(df["f10_value"].values.astype(float), -0.999, 0.999)
    rp10 = np.clip(df["f10_peer_value"].values.astype(float), -0.999, 0.999)
    d10 = np.arctanh(r10) - np.arctanh(rp10)
    valid_f10 = (n_e >= 5) & (~np.isnan(r10)) & (~np.isnan(rp10))
    s10 = np.where(valid_f10, np.sqrt(1.06 / np.maximum(1, n_e - 3)), np.nan)
    process_cont(d10, s10, valid_f10, "two-sided", "f10")

    # 4. Enumerator decision & risk score
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
            evidence_list.append(", ".join([f.upper() for f, val in row_p.items() if val < cutoff]))
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
