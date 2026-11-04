"""Statistical helpers for scoring: robust dispersion, beta-binomial rho, and FDR."""

import math
from typing import Optional, Tuple
import numpy as np


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

