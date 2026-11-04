"""Stage A Diagnostics: Per-feature null calibration, fabricator p-values, skipped cells, and floor triggers."""

import sys
from pathlib import Path
import shutil
from typing import Dict, List, Set, Tuple
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.features import build_feature_table
from engine.scoring import estimate_beta_binomial_rho, score_enumerators
from generator.run import run_generation


def run_diagnostics():
    diag_dir = Path("eval_diag_temp")
    diag_dir.mkdir(parents=True, exist_ok=True)

    features = ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10"]
    count_features = [
        ("f3", "f3_k", "f3_n", "f3_k_exp"),
        ("f4", "f4_k", "f4_n", "f4_k_exp"),
        ("f8", "f8_k", "f8_n", "f8_k_exp"),
        ("f9", "f9_k", "f9_n", "f9_k_exp"),
    ]

    print("=" * 80)
    print("STAGE A: CALIBRATION DIAGNOSTICS")
    print("=" * 80)

    # -------------------------------------------------------------
    # A1. Per-feature null calibration: seeds 0..19, --no-fraud
    # -------------------------------------------------------------
    print("\n--- A1. Per-Feature Null Calibration (Seeds 0..19, --no-fraud) ---")
    pooled_p: Dict[str, List[float]] = {f: [] for f in features}
    f567_computable: Dict[str, List[bool]] = {"f5": [], "f6": [], "f7": []}

    for s in range(20):
        out_dir = diag_dir / f"honest_s{s}"
        p_sub = run_generation(
            icc_level="medium",
            seed=s,
            out_dir=out_dir,
            round_num=1,
            no_fraud=True,
        )
        p_vil = out_dir / "reference" / "villages.parquet"
        df_feat = build_feature_table(p_sub, p_vil)
        df_scores = score_enumerators(df_feat)

        for f in features:
            col = f"{f}_p"
            vals = df_scores[col].dropna().tolist()
            pooled_p[f].extend(vals)

        for f in ["f5", "f6", "f7"]:
            comp = (~df_feat[f"{f}_null_sd"].isna()) & (df_feat[f"{f}_null_sd"] > 0)
            f567_computable[f].extend(comp.tolist())

    a1_rows = []
    for f in features:
        arr = np.array(pooled_p[f])
        n_valid = len(arr)
        p05 = float(np.mean(arr < 0.05)) if n_valid > 0 else 0.0
        p01 = float(np.mean(arr < 0.01)) if n_valid > 0 else 0.0
        a1_rows.append({
            "feature": f.upper(),
            "n_valid": n_valid,
            "share_p_lt_0.05": f"{p05:.4f} ({p05:.1%})",
            "share_p_lt_0.01": f"{p01:.4f} ({p01:.1%})",
            "calibrated_status": "Well-calibrated" if (0.02 <= p05 <= 0.08) else "MISCALIBRATED",
        })
    df_a1 = pd.DataFrame(a1_rows)
    print(df_a1.to_string(index=False))

    # -------------------------------------------------------------
    # A2. Seed 42, prevalence 0.125: Fabricators p-values and rho
    # -------------------------------------------------------------
    print("\n--- A2. Seed 42 (Prevalence 0.125): Fabricator Feature P-Values & Rho ---")
    s42_dir = diag_dir / "seed42"
    s42_truth = diag_dir / "truth42"
    p_sub42 = run_generation(
        icc_level="medium",
        seed=42,
        out_dir=s42_dir,
        round_num=1,
        prevalence=0.125,
        truth_dir=s42_truth,
    )
    p_vil42 = s42_dir / "reference" / "villages.parquet"
    df_truth42 = pd.read_parquet(s42_truth / "round=1" / "labels_enumerator.parquet")
    df_feat42 = build_feature_table(p_sub42, p_vil42)
    df_scores42 = score_enumerators(df_feat42)

    fab_df = df_truth42[df_truth42["primary_mode"].notna()].copy()
    fab_ids = set(fab_df["enumerator_id"])

    # P-value table for the 5 fabricators
    merged_fabs = df_scores42[df_scores42["enumerator_id"].isin(fab_ids)].copy()
    merged_fabs["primary_mode"] = merged_fabs["enumerator_id"].map(
        dict(zip(fab_df["enumerator_id"], fab_df["primary_mode"]))
    )
    merged_fabs["fab_share"] = merged_fabs["enumerator_id"].map(
        dict(zip(fab_df["enumerator_id"], fab_df["fab_share_realized"]))
    )

    a2_cols = ["enumerator_id", "primary_mode", "fab_share"] + [f"{f}_p" for f in features]
    df_a2_pvals = merged_fabs[a2_cols].copy()
    df_a2_pvals.columns = ["enumerator", "mode", "share"] + [f.upper() for f in features]
    print("\nFabricator Feature P-Values:")
    print(df_a2_pvals.to_string(index=False))

    # Rho estimation (full vs honest-only)
    rho_records = []
    honest_mask = ~df_feat42["enumerator_id"].isin(fab_ids)

    for fid, k_col, n_col, exp_col in count_features:
        k_all = df_feat42[k_col].values.astype(int)
        n_all = np.maximum(1, df_feat42[n_col].values.astype(int))
        k_exp_all = df_feat42[exp_col].values.astype(float)
        rho_all = estimate_beta_binomial_rho(k_all, n_all, k_exp_all)

        k_hon = df_feat42.loc[honest_mask, k_col].values.astype(int)
        n_hon = np.maximum(1, df_feat42.loc[honest_mask, n_col].values.astype(int))
        k_exp_hon = df_feat42.loc[honest_mask, exp_col].values.astype(float)
        rho_hon = estimate_beta_binomial_rho(k_hon, n_hon, k_exp_hon)

        rho_records.append({
            "feature": fid.upper(),
            "rho_all_enumerators": round(rho_all, 6),
            "rho_honest_only (fabs excluded)": round(rho_hon, 6),
            "inflation_ratio (all / honest)": round(rho_all / max(rho_hon, 1e-6), 2),
        })
    df_rho = pd.DataFrame(rho_records)
    print("\nOverdispersion Rho Estimation Comparison:")
    print(df_rho.to_string(index=False))

    # -------------------------------------------------------------
    # A3. F5/F6/F7 Skipped cells and computability
    # -------------------------------------------------------------
    print("\n--- A3. F5/F6/F7 Skipped Cell Representation & Computable Share ---")
    # In seed 42
    s42_comp = {
        f: float(np.mean((~df_feat42[f"{f}_null_sd"].isna()) & (df_feat42[f"{f}_null_sd"] > 0)))
        for f in ["f5", "f6", "f7"]
    }
    # In pooled 0..19
    pooled_comp = {
        f: float(np.mean(f567_computable[f]))
        for f in ["f5", "f6", "f7"]
    }
    # Inspect how skipped cells are stored
    sample_skipped = df_feat42[df_feat42["f5_null_sd"].isna()][["enumerator_id", "f5_value", "f5_null_sd", "f6_value", "f6_null_sd", "f7_value", "f7_null_sd"]]
    print(f"How skipped cells are stored in df_feat:\n{sample_skipped.head(3)}")

    a3_df = pd.DataFrame([
        {"feature": "F5 asset_dispersion", "seed42_computable_share": f"{s42_comp['f5']:.1%}", "pooled_0_19_computable_share": f"{pooled_comp['f5']:.1%}"},
        {"feature": "F6 hhsize_dispersion", "seed42_computable_share": f"{s42_comp['f6']:.1%}", "pooled_0_19_computable_share": f"{pooled_comp['f6']:.1%}"},
        {"feature": "F7 gps_spread", "seed42_computable_share": f"{s42_comp['f7']:.1%}", "pooled_0_19_computable_share": f"{pooled_comp['f7']:.1%}"},
    ])
    print("\nComputable Share:")
    print(a3_df.to_string(index=False))

    # -------------------------------------------------------------
    # A4. Survey-wide baseline floor triggers in Seed 42
    # -------------------------------------------------------------
    print("\n--- A4. Survey-Wide Baseline Floor Documentation & Seed 42 Triggers ---")
    floor_records = []
    for fid, k_col, n_col, exp_col in count_features:
        k = df_feat42[k_col].values.astype(int)
        n = np.maximum(1, df_feat42[n_col].values.astype(int))
        k_exp = df_feat42[exp_col].values.astype(float)
        survey_p = float(np.sum(k_exp) / np.sum(n))
        p_floor = max(survey_p, 1e-4)

        raw_p0 = k_exp / n
        triggered = raw_p0 < p_floor
        zero_exp = k_exp == 0.0

        floor_records.append({
            "feature": fid.upper(),
            "survey_mean_rate (floor)": round(p_floor, 6),
            "n_enumerators_triggered (p0 < floor)": int(np.sum(triggered)),
            "n_enumerators_zero_peer_exp (k_exp == 0)": int(np.sum(zero_exp)),
            "total_enumerators": len(df_feat42),
        })
    df_floor = pd.DataFrame(floor_records)
    print(df_floor.to_string(index=False))

    shutil.rmtree(diag_dir, ignore_errors=True)


if __name__ == "__main__":
    run_diagnostics()
