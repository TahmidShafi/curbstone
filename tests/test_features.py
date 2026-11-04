"""Tests for enumerator-level peer-relative feature extraction."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

from engine.features import build_feature_table
from generator.run import run_generation

ASSET_COLS = ["asset_mobile", "asset_tv", "asset_internet", "asset_radio", "asset_computer"]


def _make_fixture_sub(sub_id, enum_id, vil_id, dur, hh_sz, head_age, roster, assets, lat, lon, start_str="2026-11-01T10:00:00+06:00"):
    row = {
        "submission_id": sub_id,
        "round": 1,
        "enumerator_id": enum_id,
        "upazila_code": "UPA01",
        "village_id": vil_id,
        "start_time": start_str,
        "end_time": "2026-11-01T10:30:00+06:00",
        "duration_min": float(dur),
        "gps_lat": float(lat),
        "gps_lon": float(lon),
        "gps_accuracy": 10.0,
        "hh_size": int(hh_sz),
        "head_age": int(head_age),
        "roster_ages": roster,
    }
    for a_name, a_val in zip(ASSET_COLS, assets):
        row[a_name] = a_val
    return row


def test_fixture_f4_straight_line():
    """All-equal assets fixture produces k == n."""
    rows = []
    # enum_01 in VIL01 has all straight-line records (all 1s)
    for i in range(6):
        rows.append(_make_fixture_sub(f"s1_{i}", "enum_01", "VIL01", 30.0, 4, 40, [40, 35, 10, 5], [1, 1, 1, 1, 1], 24.50, 90.00))
    # enum_02 in VIL01 has mixed assets
    for i in range(6):
        rows.append(_make_fixture_sub(f"s2_{i}", "enum_02", "VIL01", 30.0, 4, 40, [40, 35, 10, 5], [1, 0, 1, 0, 1], 24.50, 90.00))
    df = pd.DataFrame(rows)
    feat = build_feature_table(df, seed=42)
    row_01 = feat[feat["enumerator_id"] == "enum_01"].iloc[0]
    row_02 = feat[feat["enumerator_id"] == "enum_02"].iloc[0]
    assert row_01["f4_k"] == row_01["f4_n"] == 6
    assert row_02["f4_k"] == 0


def test_fixture_f7_identical_gps():
    """Identical GPS points produce strongly negative F7 gps_spread."""
    rows = []
    # enum_01 has identical GPS points
    for i in range(6):
        rows.append(_make_fixture_sub(f"s1_{i}", "enum_01", "VIL01", 30.0, 4, 40, [40, 35, 10, 5], [1, 0, 0, 0, 0], 24.5000, 90.0000))
    # enum_02 has dispersed GPS points
    for i in range(6):
        rows.append(_make_fixture_sub(f"s2_{i}", "enum_02", "VIL01", 30.0, 4, 40, [40, 35, 10, 5], [1, 0, 0, 0, 0], 24.5000 + i * 0.005, 90.0000 + i * 0.005))
    df = pd.DataFrame(rows)
    feat = build_feature_table(df, seed=42)
    row_01 = feat[feat["enumerator_id"] == "enum_01"].iloc[0]
    assert row_01["f7_value"] < -2.0, f"Expected strongly negative F7, got {row_01['f7_value']}"


def test_fixture_f3_repeated_records():
    """Repeated near-identical records produce f3_k > f3_k_exp."""
    rows = []
    # enum_01 has near-identical duplicate submissions
    for i in range(6):
        rows.append(_make_fixture_sub(f"s1_{i}", "enum_01", "VIL01", 30.0, 4, 40, [40, 35, 10, 5], [1, 0, 0, 0, 0], 24.50 + i * 0.001, 90.00))
    # enum_02 has diverse submissions
    for i in range(12):
        rows.append(_make_fixture_sub(f"s2_{i}", "enum_02", "VIL01", 30.0, 2 + (i % 6), 25 + i * 4, [25 + i * 4], [(i + j) % 2 for j in range(5)], 24.50 + i * 0.001, 90.00))
    df = pd.DataFrame(rows)
    feat = build_feature_table(df, seed=42)
    row_01 = feat[feat["enumerator_id"] == "enum_01"].iloc[0]
    assert row_01["f3_k"] == 6
    assert row_01["f3_k"] > row_01["f3_k_exp"]


def test_fixture_f8_age_heaping():
    """All ages ending in 0 or 5 produces f8_k == f8_n."""
    rows = []
    for i in range(6):
        rows.append(_make_fixture_sub(f"s1_{i}", "enum_01", "VIL01", 30.0, 3, 40, [40, 35, 20], [1, 0, 0, 0, 0], 24.50, 90.00))
    for i in range(6):
        rows.append(_make_fixture_sub(f"s2_{i}", "enum_02", "VIL01", 30.0, 3, 43, [43, 37, 22], [1, 0, 0, 0, 0], 24.50, 90.00))
    df = pd.DataFrame(rows)
    feat = build_feature_table(df, seed=42)
    row_01 = feat[feat["enumerator_id"] == "enum_01"].iloc[0]
    assert row_01["f8_k"] == row_01["f8_n"] == 18


def test_feature_determinism(tmp_path):
    """Same engine seed produces identical feature table; different seed alters stochastic nulls."""
    p = run_generation("medium", 42, tmp_path / "data", round_num=1, no_fraud=True)
    df_feat1 = build_feature_table(p, seed=12345)
    df_feat2 = build_feature_table(p, seed=12345)
    df_feat3 = build_feature_table(p, seed=99999)

    assert df_feat1.equals(df_feat2), "Feature table must be deterministic for identical engine.seed"
    # Stochastic nulls (f3_k_exp or f7_value) differ under different seeds
    assert not df_feat1.equals(df_feat3)


@pytest.mark.slow
def test_workload_fairness_and_honest_centring(tmp_path):
    """Workload fairness (|rho| < 0.3) and honest centring across seeds 0..19."""
    records = []
    for s in range(20):
        p = run_generation("medium", s, tmp_path / f"data_{s}", round_num=1, no_fraud=True)
        feat = build_feature_table(p, seed=12345 + s)
        for _, r in feat.iterrows():
            n_e = r["n_e"]
            records.append({
                "n_e": n_e,
                "f3_diff_norm": (r["f3_k"] - r["f3_k_exp"]) / max(1, n_e),
                "f5_val": r["f5_value"],
                "f6_val": r["f6_value"],
                "f7_val": r["f7_value"],
                "f1_diff": r["f1_value"] - r["f1_peer_value"],
                "f3_k": r["f3_k"], "f3_k_exp": r["f3_k_exp"], "f3_lim": r["f3_null_limited"],
                "f4_k": r["f4_k"], "f4_k_exp": r["f4_k_exp"],
                "f8_k": r["f8_k"], "f8_k_exp": r["f8_k_exp"],
                "f9_k": r["f9_k"], "f9_k_exp": r["f9_k_exp"],
            })

    df = pd.DataFrame(records)

    # 1. Workload fairness: F5, F6, F7 target |rho| < 0.15, F3 < 0.3
    r_f3, _ = spearmanr(df["n_e"], df["f3_diff_norm"])
    r_f5, _ = spearmanr(df["n_e"], df["f5_val"])
    r_f6, _ = spearmanr(df["n_e"], df["f6_val"])
    r_f7, _ = spearmanr(df["n_e"], df["f7_val"])

    print(f"\nWorkload fairness rhos: F3={r_f3:.4f}, F5={r_f5:.4f}, F6={r_f6:.4f}, F7={r_f7:.4f}")
    assert abs(r_f3) < 0.3, f"F3 workload |rho| {abs(r_f3):.4f} >= 0.3"
    assert abs(r_f5) < 0.15, f"F5 workload |rho| {abs(r_f5):.4f} >= 0.15"
    assert abs(r_f6) < 0.15, f"F6 workload |rho| {abs(r_f6):.4f} >= 0.15"
    assert abs(r_f7) < 0.15, f"F7 workload |rho| {abs(r_f7):.4f} >= 0.15"

    # 2. Honest centring medians: F1, F5, F6, F7 within [-0.1, 0.1]
    med_f1 = float(df["f1_diff"].median())
    med_f5 = float(df["f5_val"].median())
    med_f6 = float(df["f6_val"].median())
    med_f7 = float(df["f7_val"].median())

    print(f"Honest centring medians: F1={med_f1:.4f}, F5={med_f5:.4f}, F6={med_f6:.4f}, F7={med_f7:.4f}")
    assert -0.1 <= med_f1 <= 0.1, f"F1 median {med_f1:.4f} outside [-0.1, 0.1]"
    assert -0.1 <= med_f5 <= 0.1, f"F5 median {med_f5:.4f} outside [-0.1, 0.1]"
    assert -0.1 <= med_f6 <= 0.1, f"F6 median {med_f6:.4f} outside [-0.1, 0.1]"
    assert -0.1 <= med_f7 <= 0.1, f"F7 median {med_f7:.4f} outside [-0.1, 0.1]"

    # 3. Honest centring ratios: F4, F8, F9 (and F3 un-limited) within [0.8, 1.2]
    ratio_f4 = df["f4_k"].sum() / df["f4_k_exp"].sum()
    ratio_f8 = df["f8_k"].sum() / df["f8_k_exp"].sum()
    ratio_f9 = df["f9_k"].sum() / df["f9_k_exp"].sum()
    unlim_f3 = df[~df["f3_lim"]]
    ratio_f3 = unlim_f3["f3_k"].sum() / unlim_f3["f3_k_exp"].sum()

    print(f"Honest centring ratios: F3(unlim)={ratio_f3:.4f}, F4={ratio_f4:.4f}, F8={ratio_f8:.4f}, F9={ratio_f9:.4f}")
    assert 0.8 <= ratio_f4 <= 1.2, f"F4 ratio {ratio_f4:.4f} outside [0.8, 1.2]"
    assert 0.8 <= ratio_f8 <= 1.2, f"F8 ratio {ratio_f8:.4f} outside [0.8, 1.2]"
    assert 0.8 <= ratio_f9 <= 1.2, f"F9 ratio {ratio_f9:.4f} outside [0.8, 1.2]"
    assert 0.8 <= ratio_f3 <= 1.2, f"F3 ratio {ratio_f3:.4f} outside [0.8, 1.2]"

