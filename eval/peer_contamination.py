"""Evaluation script: Peer contamination study across fraud prevalences."""

import shutil
import sys
from pathlib import Path
from typing import Dict, List
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.features import build_feature_table
from generator.run import run_generation


def run_peer_contamination(
    seeds: List[int] = list(range(20)),
    prevalences: List[float] = [0.0, 0.125, 0.20],
    tmp_base: Path = Path("eval_contamination_tmp"),
) -> pd.DataFrame:
    """Evaluate peer contamination on honest enumerators across seeds and prevalences."""
    results_by_prev: Dict[float, Dict[str, List[float]]] = {p: {} for p in prevalences}

    features_list = [
        "F1 duration_resid (val - peer)",
        "F2 throughput (val - peer)",
        "F3 near_dup ((k - k_exp)/n)",
        "F4 straight_line ((k - k_exp)/n)",
        "F5 asset_dispersion (val - null)",
        "F6 hhsize_dispersion (val - null)",
        "F7 gps_spread (val - null)",
        "F8 age_heaping ((k - k_exp)/n)",
        "F9 nonresponse ((k - k_exp)/n)",
        "F10 dur_size_coupling (val - peer)",
    ]

    for p in prevalences:
        for f in features_list:
            results_by_prev[p][f] = []

    for prev in prevalences:
        for s in seeds:
            out_dir = tmp_base / f"data_p{prev}_s{s}"
            truth_dir = tmp_base / f"truth_p{prev}_s{s}"

            p_sub = run_generation(
                icc_level="medium",
                seed=s,
                out_dir=out_dir,
                round_num=1,
                prevalence=prev,
                truth_dir=truth_dir,
            )

            df_feat = build_feature_table(p_sub, seed=12345 + s)

            if prev == 0.0:
                # All enumerators are honest
                honest_feat = df_feat.copy()
            else:
                truth_path = truth_dir / "round=1" / "labels_enumerator.parquet"
                df_labels = pd.read_parquet(truth_path)
                honest_ids = set(df_labels[df_labels["primary_mode"].isna()]["enumerator_id"])
                honest_feat = df_feat[df_feat["enumerator_id"].isin(honest_ids)].copy()

            f1_diff = honest_feat["f1_value"] - honest_feat["f1_peer_value"]
            f2_diff = honest_feat["f2_value"] - honest_feat["f2_peer_value"]
            f3_rate = (honest_feat["f3_k"] - honest_feat["f3_k_exp"]) / honest_feat["f3_n"].clip(lower=1)
            f4_rate = (honest_feat["f4_k"] - honest_feat["f4_k_exp"]) / honest_feat["f4_n"].clip(lower=1)
            f5_val = honest_feat["f5_value"]
            f6_val = honest_feat["f6_value"]
            f7_val = honest_feat["f7_value"]
            f8_rate = (honest_feat["f8_k"] - honest_feat["f8_k_exp"]) / honest_feat["f8_n"].clip(lower=1)
            f9_rate = (honest_feat["f9_k"] - honest_feat["f9_k_exp"]) / honest_feat["f9_n"].clip(lower=1)
            f10_diff = honest_feat["f10_value"] - honest_feat["f10_peer_value"]

            results_by_prev[prev]["F1 duration_resid (val - peer)"].extend(f1_diff.tolist())
            results_by_prev[prev]["F2 throughput (val - peer)"].extend(f2_diff.tolist())
            results_by_prev[prev]["F3 near_dup ((k - k_exp)/n)"].extend(f3_rate.tolist())
            results_by_prev[prev]["F4 straight_line ((k - k_exp)/n)"].extend(f4_rate.tolist())
            results_by_prev[prev]["F5 asset_dispersion (val - null)"].extend(f5_val.tolist())
            results_by_prev[prev]["F6 hhsize_dispersion (val - null)"].extend(f6_val.tolist())
            results_by_prev[prev]["F7 gps_spread (val - null)"].extend(f7_val.tolist())
            results_by_prev[prev]["F8 age_heaping ((k - k_exp)/n)"].extend(f8_rate.tolist())
            results_by_prev[prev]["F9 nonresponse ((k - k_exp)/n)"].extend(f9_rate.tolist())
            results_by_prev[prev]["F10 dur_size_coupling (val - peer)"].extend(f10_diff.tolist())

            shutil.rmtree(out_dir, ignore_errors=True)
            shutil.rmtree(truth_dir, ignore_errors=True)

    rows = []
    for f in features_list:
        row = {"feature": f}
        for prev in prevalences:
            vals = pd.Series(results_by_prev[prev][f]).dropna()
            med = float(vals.median()) if len(vals) > 0 else float("nan")
            row[f"prev={prev}"] = round(med, 4)
        rows.append(row)

    df_out = pd.DataFrame(rows)
    print("\nPeer Contamination Study (Median over Honest Enumerators across Seeds 0..19):")
    print(df_out.to_string(index=False))

    shutil.rmtree(tmp_base, ignore_errors=True)
    return df_out


if __name__ == "__main__":
    run_peer_contamination()
