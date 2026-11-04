"""Tests for DGP mechanisms, design-based calibration, and seed robustness."""

from datetime import datetime, time
import math
import numpy as np
import pytest

from generator.geography import build_geography
from generator.enumerators import build_enumerators
from generator.households import (
    apply_item_nonresponse,
    compute_sigma_u,
    generate_age_roster,
    generate_household_size,
    generate_village_effects,
    get_calibrated_alphas,
)
from generator.interviews import generate_submissions_for_round
from tests.conftest import compute_anova_icc


def test_icc_mechanism_a_deterministic_sigma_u():
    """Requirement 7a: Deterministic sigma_u matches dgp §2.2 table to 3 decimal places."""
    expected = {0.05: 0.455, 0.15: 0.833, 0.30: 1.298}
    for target_icc, exp_sigma in expected.items():
        computed_sigma = compute_sigma_u(target_icc, beta=0.8)
        assert round(computed_sigma, 3) == exp_sigma


def test_icc_mechanism_b_c_d_large_sample():
    """Requirements 7b, 7c, 7d: Village variance, design-based marginal rates, and ANOVA ICC."""
    rng = np.random.default_rng(2026)
    n_villages, n_hh = 2000, 100
    N = n_villages * n_hh
    beta = 0.8
    groups = np.repeat(np.arange(n_villages), n_hh)

    targets = {
        "asset_mobile": 0.974,
        "asset_tv": 0.568,
        "asset_internet": 0.381,
        "asset_radio": 0.128,
        "asset_computer": 0.087,
    }
    levels = [("low", 0.05), ("medium", 0.15), ("high", 0.30)]
    observed_anova_iccs = {}

    for level_name, target_icc in levels:
        sigma_u = compute_sigma_u(target_icc, beta=beta)
        sigma_u_sq = sigma_u ** 2

        # 7b: Sample variance within 10%
        vil_ids = [f"V_{i}" for i in range(n_villages)]
        u_v_dict, _ = generate_village_effects(vil_ids, sigma_u=sigma_u, sigma_w=0.15, rng=rng)
        u_vals = np.array(list(u_v_dict.values()))
        sample_var = float(np.var(u_vals, ddof=1))
        assert abs(sample_var - sigma_u_sq) / sigma_u_sq < 0.10

        # 7c: Marginal rates within design-based tolerance tol = 4 * sqrt(p(1-p)/N * deff)
        alphas = get_calibrated_alphas(targets, icc=target_icc, beta=beta)
        u_expanded = np.repeat(u_vals, n_hh)
        z_h = rng.normal(0.0, 1.0, size=N)

        observed_anova_iccs[level_name] = {}
        for asset_name, p in targets.items():
            alpha = alphas[asset_name]
            logit_p = alpha + u_expanded + (beta * z_h)
            probs = 1.0 / (1.0 + np.exp(-logit_p))
            draws = (rng.uniform(0.0, 1.0, size=len(probs)) < probs).astype(int)

            marginal_rate = float(np.mean(draws))
            icc_val = compute_anova_icc(draws, groups)
            observed_anova_iccs[level_name][asset_name] = icc_val

            # Design-based bound
            deff = 1.0 + (n_hh - 1) * max(0.0, icc_val)
            tol = 4.0 * math.sqrt((p * (1.0 - p) / N) * deff)
            print(f"Tol [{level_name:6s}][{asset_name:15s}]: tol={tol:.5f} (obs={marginal_rate:.4f}, p={p:.3f}, deff={deff:.2f})")
            assert abs(marginal_rate - p) <= tol

    # 7d: Monotonically increasing ANOVA ICC
    for asset_name in ["asset_tv", "asset_internet", "asset_radio", "asset_computer"]:
        icc_low = observed_anova_iccs["low"][asset_name]
        icc_med = observed_anova_iccs["medium"][asset_name]
        icc_high = observed_anova_iccs["high"][asset_name]
        assert icc_low < icc_med < icc_high


def test_mean_household_size_large_sample():
    """Mean hh_size is within design-based tolerance of 4.30 across 2000 villages."""
    rng = np.random.default_rng(2026)
    n_villages, m = 2000, 100
    N = n_villages * m
    groups = np.repeat(np.arange(n_villages), m)

    w_v = rng.normal(0.0, 0.15, size=n_villages)
    w_expanded = np.repeat(w_v, m)
    sizes = np.array([
        generate_household_size(w, sigma_w=0.15, rng=rng)
        for w in w_expanded
    ])

    mean_size = float(np.mean(sizes))
    var_size = float(np.var(sizes, ddof=1))
    icc_hh = compute_anova_icc(sizes, groups)
    deff_hh = 1.0 + (m - 1) * max(0.0, icc_hh)
    tol_hh = 4.0 * math.sqrt((var_size / N) * deff_hh)
    assert abs(mean_size - 4.30) <= tol_hh


def test_honest_age_heaping_share_large_sample():
    """Honest age-heaping share (ending 0 or 5) matches expected value implied by h_e."""
    # Compute expected reference share via Monte Carlo with a separate seed
    rng_ref = np.random.default_rng(77777)
    ref_n = 40000
    heaped_ref, total_ref = 0, 0
    for _ in range(ref_n):
        ce = float(rng_ref.normal(0.0, 0.30))
        sz = int(rng_ref.integers(1, 10))
        _, roster = generate_age_roster(sz, care_effect=ce, rng=rng_ref)
        for age in roster:
            total_ref += 1
            if age % 5 == 0:
                heaped_ref += 1
    p_expected = heaped_ref / total_ref

    # Generate test sample
    rng = np.random.default_rng(2026)
    test_n = 40000
    heaped_test, total_test = 0, 0
    n_enums = 200
    enum_care = rng.normal(0.0, 0.30, size=n_enums)
    for i in range(test_n):
        ce = enum_care[i % n_enums]
        sz = int(rng.integers(1, 10))
        _, roster = generate_age_roster(sz, care_effect=ce, rng=rng)
        for age in roster:
            total_test += 1
            if age % 5 == 0:
                heaped_test += 1

    p_observed = heaped_test / total_test
    tol = 4.0 * math.sqrt((p_expected * (1.0 - p_expected) / total_test) * 2.5)
    assert abs(p_observed - p_expected) <= tol


def test_item_nonresponse_share_large_sample():
    """Share of -8 per asset is within design-based tolerance of 0.01 * E[exp(-c_e)]."""
    rng = np.random.default_rng(2026)
    sigma_c = 0.30
    p_expected = 0.01 * math.exp((sigma_c ** 2) / 2.0)

    n_enums, m_per_enum = 2000, 100
    N = n_enums * m_per_enum
    enum_cares = rng.normal(0.0, sigma_c, size=n_enums)
    enum_groups = np.repeat(np.arange(n_enums), m_per_enum)

    nr_indicators = []
    for ce in np.repeat(enum_cares, m_per_enum):
        out = apply_item_nonresponse({"asset_1": 1}, care_effect=ce, rng=rng)
        nr_indicators.append(1 if out["asset_1"] == -8 else 0)

    nr_arr = np.array(nr_indicators)
    p_observed = float(np.mean(nr_arr))
    icc_nr = compute_anova_icc(nr_arr, enum_groups)
    deff_nr = 1.0 + (m_per_enum - 1) * max(0.0, icc_nr)
    tol_nr = 4.0 * math.sqrt((p_expected * (1.0 - p_expected) / N) * deff_nr)
    assert abs(p_observed - p_expected) <= tol_nr


@pytest.mark.slow
@pytest.mark.parametrize("seed", range(20))
def test_seed_robustness(config, seed):
    """Seed robustness across seeds 0..19: scheduler, marginal rates, and ICC monotonicity."""
    rng = np.random.default_rng(seed)
    geo = build_geography(config, rng)
    village_ids = list(geo.villages.keys())
    enums = build_enumerators(config, village_ids, rng)

    village_to_enums = {vid: [] for vid in village_ids}
    for e_id, enum in enums.items():
        assert 1 <= len(enum.assigned_villages) <= 3
        for vid in enum.assigned_villages:
            village_to_enums[vid].append(e_id)

    for vid, e_list in village_to_enums.items():
        assert len(e_list) >= 2

    # 1. Round generation & timing checks
    df, _ = generate_submissions_for_round(config, geo, enums, "medium", 1, rng)
    assert len(df) > 0
    assert (df["duration_min"] > 0).all()

    work_start, work_end = time(9, 0, 0), time(17, 0, 0)
    for enum_id, group in df.groupby("enumerator_id"):
        prev_end = None
        for _, row in group.iterrows():
            start_dt = datetime.fromisoformat(row["start_time"])
            end_dt = datetime.fromisoformat(row["end_time"])
            assert start_dt < end_dt
            assert start_dt.time() >= work_start and end_dt.time() <= work_end
            assert start_dt.weekday() not in (4, 5) and end_dt.weekday() not in (4, 5)
            if prev_end is not None:
                assert start_dt >= prev_end
            prev_end = end_dt

    # 2. Large-scale marginal-rate and ICC-monotonicity check (1,000 villages x 100 households)
    n_v, m = 1000, 100
    N = n_v * m
    groups = np.repeat(np.arange(n_v), m)
    targets = {
        "asset_mobile": 0.974,
        "asset_tv": 0.568,
        "asset_internet": 0.381,
        "asset_radio": 0.128,
        "asset_computer": 0.087,
    }
    levels = [("low", 0.05), ("medium", 0.15), ("high", 0.30)]
    observed_iccs = {}

    for level_name, target_icc in levels:
        sigma_u = compute_sigma_u(target_icc, beta=0.8)
        vil_ids = [f"V_{i}" for i in range(n_v)]
        u_v_dict, _ = generate_village_effects(vil_ids, sigma_u=sigma_u, sigma_w=0.15, rng=rng)
        u_vals = np.array(list(u_v_dict.values()))
        alphas = get_calibrated_alphas(targets, icc=target_icc, beta=0.8)
        u_expanded = np.repeat(u_vals, m)
        z_h = rng.normal(0.0, 1.0, size=N)

        observed_iccs[level_name] = {}
        for asset_name, p in targets.items():
            alpha = alphas[asset_name]
            logit_p = alpha + u_expanded + (0.8 * z_h)
            probs = 1.0 / (1.0 + np.exp(-logit_p))
            draws = (rng.uniform(0.0, 1.0, size=len(probs)) < probs).astype(int)

            marginal_rate = float(np.mean(draws))
            icc_val = compute_anova_icc(draws, groups)
            observed_iccs[level_name][asset_name] = icc_val

            deff = 1.0 + (m - 1) * max(0.0, icc_val)
            tol = 4.0 * math.sqrt((p * (1.0 - p) / N) * deff)
            assert abs(marginal_rate - p) <= tol, f"Seed {seed} [{level_name}][{asset_name}]: diff > tol"

    for asset_name in ["asset_tv", "asset_internet", "asset_radio", "asset_computer"]:
        assert observed_iccs["low"][asset_name] < observed_iccs["medium"][asset_name] < observed_iccs["high"][asset_name]

