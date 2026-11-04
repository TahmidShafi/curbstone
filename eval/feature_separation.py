"""Evaluation script: Feature separation across honest and fabricator modes."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Dict, List
import pandas as pd

from engine.features import build_feature_table
from generator.run import run_generation


def run_feature_separation(seed: int = 42, prevalence: float = 0.125) -> pd.DataFrame:
    eval_dir = Path("eval_data_sep")
    data_dir = eval_dir / "data"
    truth_dir = eval_dir / "truth"

    run_generation(
        icc_level="medium",
        seed=seed,
        out_dir=data_dir,
        round_num=1,
        prevalence=prevalence,
        truth_dir=truth_dir,
    )

    sub_path = data_dir / "round=1" / "interviews.parquet"
    truth_enum_path = truth_dir / "round=1" / "labels_enumerator.parquet"

    df_feat = build_feature_table(sub_path, seed=12345)
    df_enum = pd.read_parquet(truth_enum_path)

    merged = pd.merge(df_feat, df_enum, on="enumerator_id")
    merged["group"] = merged["primary_mode"].fillna("honest")

    feature_metrics: Dict[str, pd.Series] = {
        "F1 duration_resid (val - peer)": merged["f1_value"] - merged["f1_peer_value"],
        "F2 throughput (val - peer)": merged["f2_value"] - merged["f2_peer_value"],
        "F3 near_dup ((k - k_exp)/n)": (merged["f3_k"] - merged["f3_k_exp"]) / merged["f3_n"],
        "F4 straight_line ((k - k_exp)/n)": (merged["f4_k"] - merged["f4_k_exp"]) / merged["f4_n"],
        "F5 asset_dispersion (val)": merged["f5_value"],
        "F6 hhsize_dispersion (val)": merged["f6_value"],
        "F7 gps_spread (val)": merged["f7_value"],
        "F8 age_heaping ((k - k_exp)/n)": (merged["f8_k"] - merged["f8_k_exp"]) / merged["f8_n"],
        "F9 nonresponse ((k - k_exp)/n)": (merged["f9_k"] - merged["f9_k_exp"]) / merged["f9_n"],
        "F10 dur_size_coupling (val - peer)": merged["f10_value"] - merged["f10_peer_value"],
    }

    groups = ["honest", "copy_paste", "straight_lining", "rushed", "invented_gps", "too_average"]

    rows = []
    for f_name, series in feature_metrics.items():
        row: Dict[str, Any] = {"feature": f_name}
        for g in groups:
            sub = series[merged["group"] == g]
            med = float(sub.median()) if len(sub) > 0 else float("nan")
            row[g] = round(med, 4)
        rows.append(row)

    df_sep = pd.DataFrame(rows)
    print(df_sep.to_string(index=False))

    import shutil
    shutil.rmtree(eval_dir)
    return df_sep


if __name__ == "__main__":
    run_feature_separation()

