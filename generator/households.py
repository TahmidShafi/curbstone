"""Household generator: size, demographics, and asset ownership with village random effects.

Latent-Variable Asset Model (dgp §2.2 & §3.2):
    logit P(own asset k) = alpha_k + u_v + beta * z_h
    where:
        u_v ~ Normal(0, sigma_u^2) is the village-level wealth effect (shared across all assets)
        z_h ~ Normal(0, 1) is the household-level latent factor
        beta = 0.8 (weight of household factor)
    Latent-scale Intra-Class Correlation (ICC):
        ICC = sigma_u^2 / (sigma_u^2 + beta^2 + pi^2 / 3)
        => sigma_u^2 = ICC * (beta^2 + pi^2 / 3) / (1 - ICC)

Numerical Calibration of Intercepts (dgp §3.2):
    Marginal probability across the population:
        P_bar(alpha_k) = E_{u_v, z_h}[ logistic(alpha_k + u_v + beta * z_h) ]
    Since Y = u_v + beta * z_h ~ Normal(0, sigma_u^2 + beta^2),
    alpha_k is numerically calibrated using Gauss-Hermite quadrature and Brent's method
    (scipy.optimize.brentq) so that P_bar(alpha_k) matches the target marginal rate.

Household Size Model (dgp §3.1):
    hh_size = 1 + Poisson(lambda_v), truncated at 15
    lambda_v = 3.30 * exp(w_v - sigma_w^2 / 2)
    where:
        w_v ~ Normal(0, sigma_w^2), with sigma_w = 0.15
        The -sigma_w^2 / 2 term keeps the population mean unchanged at ~4.3.
"""

import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from scipy import optimize, special


# Pre-compute Gauss-Hermite quadrature nodes for fast 1D numerical integration
_GH_NODES, _GH_WEIGHTS = special.roots_hermite(50)
_SQRT_PI = math.sqrt(math.pi)

# Cache for calibrated alpha intercepts keyed by (icc_float, beta, tuple_of_asset_targets)
_CALIBRATED_ALPHA_CACHE: Dict[Tuple[float, float, Tuple[Tuple[str, float], ...]], Dict[str, float]] = {}


def compute_sigma_u(icc: float, beta: float = 0.8) -> float:
    """Derive village effect standard deviation sigma_u from latent ICC.

    Formula:
        ICC = sigma_u^2 / (sigma_u^2 + beta^2 + pi^2 / 3)
        sigma_u = sqrt(ICC * (beta^2 + pi^2 / 3) / (1 - ICC))
    """
    if not 0.0 < icc < 1.0:
        raise ValueError(f"ICC must be in (0, 1), got {icc}")
    residual_variance = (beta ** 2) + (math.pi ** 2) / 3.0
    sigma_u_sq = icc * residual_variance / (1.0 - icc)
    return math.sqrt(sigma_u_sq)


def _marginal_asset_prob(alpha: float, sigma_y: float) -> float:
    """Evaluate population marginal probability E[expit(alpha + Y)] where Y ~ N(0, sigma_y^2)."""
    # Change of variables for Gauss-Hermite: y = sqrt(2) * sigma_y * x
    y_nodes = math.sqrt(2.0) * sigma_y * _GH_NODES
    probs = 1.0 / (1.0 + np.exp(-(alpha + y_nodes)))
    return float(np.sum(_GH_WEIGHTS * probs) / _SQRT_PI)


def calibrate_alpha_k(target_prob: float, sigma_u: float, beta: float = 0.8) -> float:
    """Numerically calibrate intercept alpha_k so marginal ownership matches target_prob."""
    if not 0.0 < target_prob < 1.0:
        raise ValueError(f"target_prob must be in (0, 1), got {target_prob}")
    sigma_y = math.hypot(sigma_u, beta)
    func = lambda a: _marginal_asset_prob(a, sigma_y) - target_prob
    # Brent's method over wide interval [-15, 15]
    alpha_calibrated = optimize.brentq(func, -15.0, 15.0, xtol=1e-12)
    return float(alpha_calibrated)


def get_calibrated_alphas(
    asset_targets: Dict[str, float],
    icc: float,
    beta: float = 0.8,
) -> Dict[str, float]:
    """Retrieve or compute calibrated intercepts alpha_k for each asset at given ICC level."""
    sigma_u = compute_sigma_u(icc, beta=beta)
    cache_key = (
        round(icc, 6),
        round(beta, 6),
        tuple(sorted((k, round(v, 6)) for k, v in asset_targets.items())),
    )
    if cache_key in _CALIBRATED_ALPHA_CACHE:
        return _CALIBRATED_ALPHA_CACHE[cache_key]

    alphas: Dict[str, float] = {}
    for name, target_prob in asset_targets.items():
        alphas[name] = calibrate_alpha_k(target_prob, sigma_u, beta=beta)

    _CALIBRATED_ALPHA_CACHE[cache_key] = alphas
    return alphas


def generate_village_effects(
    village_ids: List[str],
    sigma_u: float,
    sigma_w: float,
    rng: np.random.Generator,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Draw independent wealth effect u_v and household-size effect w_v for each village."""
    u_vals = rng.normal(0.0, sigma_u, size=len(village_ids))
    w_vals = rng.normal(0.0, sigma_w, size=len(village_ids))
    u_dict = {vid: float(u) for vid, u in zip(village_ids, u_vals)}
    w_dict = {vid: float(w) for vid, w in zip(village_ids, w_vals)}
    return u_dict, w_dict


def generate_household_size(
    w_v: float,
    sigma_w: float,
    rng: np.random.Generator,
    lambda_base: float = 3.30,
    max_size: int = 15,
) -> int:
    """Generate household size according to dgp §3.1: 1 + Poisson(lambda_v), truncated at 15."""
    lambda_v = lambda_base * math.exp(w_v - (sigma_w ** 2) / 2.0)
    size = 1 + int(rng.poisson(lam=lambda_v))
    return min(max_size, max(1, size))


def generate_household_assets(
    u_v: float,
    alphas: Dict[str, float],
    beta: float,
    rng: np.random.Generator,
) -> Tuple[Dict[str, int], float]:
    """Generate binary asset ownership for a household according to latent model dgp §2.2.

    Returns:
        (asset_dict, z_h)
    """
    z_h = float(rng.normal(0.0, 1.0))
    assets: Dict[str, int] = {}
    for asset_name, alpha in alphas.items():
        logit_p = alpha + u_v + beta * z_h
        prob = 1.0 / (1.0 + math.exp(-logit_p))
        assets[asset_name] = 1 if rng.uniform(0.0, 1.0) < prob else 0
    return assets, z_h


def generate_age_roster(
    hh_size: int,
    care_effect: float,
    rng: np.random.Generator,
    head_age_min: int = 25,
    head_age_max: int = 70,
    heaping_base_prob: float = 0.10,
    fixed_head_age: Optional[int] = None,
) -> Tuple[int, List[int]]:
    """Generate age roster and apply honest terminal-digit heaping (dgp §3.3).

    Returns:
        (head_age, roster_ages)
    """
    if fixed_head_age is not None:
        head_age_raw = fixed_head_age
    else:
        head_age_raw = int(rng.integers(head_age_min, head_age_max + 1))
    raw_ages: List[int] = [head_age_raw]

    if hh_size >= 2:
        # Spouse age = head age + Normal(-5, 3^2)
        spouse_age_raw = int(round(head_age_raw + rng.normal(-5.0, 3.0)))
        spouse_age_raw = max(18, min(95, spouse_age_raw))
        raw_ages.append(spouse_age_raw)

    for _ in range(hh_size - len(raw_ages)):
        max_child_age = max(0, head_age_raw - 15)
        child_age = int(rng.integers(0, max_child_age + 1)) if max_child_age > 0 else 0
        raw_ages.append(child_age)

    # Heaping probability h_e = 0.10 * exp(c_e)
    h_e = min(1.0, max(0.0, heaping_base_prob * math.exp(care_effect)))

    roster_ages: List[int] = []
    for idx, age in enumerate(raw_ages):
        if idx == 0 and fixed_head_age is not None:
            roster_ages.append(fixed_head_age)
        elif rng.uniform(0.0, 1.0) < h_e:
            heaped_age = int(round(age / 5.0) * 5)
            roster_ages.append(heaped_age)
        else:
            roster_ages.append(age)

    return roster_ages[0], roster_ages


def apply_item_nonresponse(
    assets: Dict[str, int],
    care_effect: float,
    rng: np.random.Generator,
    base_rate: float = 0.01,
) -> Dict[str, int]:
    """Apply item non-response (-8) with probability 0.01 * exp(-c_e) (dgp §3.4)."""
    p_nr = min(1.0, max(0.0, base_rate * math.exp(-care_effect)))
    out_assets = dict(assets)
    for k in out_assets:
        if rng.uniform(0.0, 1.0) < p_nr:
            out_assets[k] = -8
    return out_assets

