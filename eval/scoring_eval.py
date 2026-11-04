"""Evaluation script for enumerator scoring, shrinkage ablation, and FDR comparison."""

import sys
from pathlib import Path
import shutil
from typing import Dict, List, Set
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.features import build_feature_table
from engine.rules import load_rules, run_rules
from engine.scoring import score_enumerators
from generator.run import run_generation


def evaluate_scoring(seed: int = 42, prevalence: float = 0.125, n_calib_rounds: int = 20) -> None:
    eval_dir = Path("eval_scoring_data")
    eval_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print(f"EVALUATION: Enumerator Scoring Engine (Seed {seed}, Prevalence {prevalence})")
    print("=" * 80)

    # 1. Generate Seed 42 dataset
    round_dir = eval_dir / "seed42"
    truth_dir = eval_dir / "truth42"
    sub_path = run_generation(
        icc_level="medium",
        seed=seed,
        out_dir=round_dir,
        round_num=1,
        prevalence=prevalence,
        truth_dir=truth_dir,
    )
    vil_path = round_dir / "reference" / "villages.parquet"
    truth_enum_path = truth_dir / "round=1" / "labels_enumerator.parquet"
    df_truth = pd.read_parquet(truth_enum_path)

    # 2. Extract features and compute scores
    df_feat = build_feature_table(sub_path, vil_path)
    scores_full = score_enumerators(df_feat, q=0.10)
    scores_noshrink = score_enumerators(df_feat, no_shrinkage=True, q=0.10)
    scores_nofdr = score_enumerators(df_feat, no_fdr=True, q=0.10)

    # Merge truth into scores table
    truth_map = df_truth.set_index("enumerator_id")["primary_mode"].to_dict()
    share_map = df_truth.set_index("enumerator_id")["fab_share_realized"].to_dict()

    scores_full["primary_mode"] = scores_full["enumerator_id"].map(lambda e: truth_map.get(e, "honest"))
    scores_full["primary_mode"] = scores_full["primary_mode"].fillna("honest")
    scores_full["fab_share"] = scores_full["enumerator_id"].map(lambda e: share_map.get(e, 0.0)).fillna(0.0)

    # -------------------------------------------------------------
    # Table 1: Seed 42 Enumerator Scoring Table
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print("TABLE 1: Enumerator Decisions (Seed 42, Prevalence 0.125)")
    print("=" * 80)
    t1_cols = ["enumerator_id", "n_interviews", "primary_mode", "p_e", "bh_flag", "evidence"]
    t1_df = scores_full[t1_cols].copy()
    t1_df.columns = ["enumerator", "n", "mode (truth)", "p_e", "BH flag", "evidence features"]
    print(t1_df.to_string(index=False))

    # -------------------------------------------------------------
    # Table 2: Precision & Recall: Full Engine vs Ablations vs Rules Baseline
    # -------------------------------------------------------------
    # True label: fab_share >= 0.10 (as defined in evaluation plan)
    is_fab_true = scores_full["fab_share"] >= 0.10
    n_fab_total = int(is_fab_true.sum())
    n_honest_total = len(scores_full) - n_fab_total

    def get_metrics(flag_series: pd.Series) -> Dict[str, float]:
        tp = int((flag_series & is_fab_true).sum())
        fp = int((flag_series & ~is_fab_true).sum())
        fn = int((~flag_series & is_fab_true).sum())
        tn = int((~flag_series & ~is_fab_true).sum())
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        return {"TP": tp, "FP": fp, "FN": fn, "TN": tn, "Precision": prec, "Recall": rec, "F1": f1}

    m_full = get_metrics(scores_full["flagged"])
    m_noshrink = get_metrics(scores_noshrink["flagged"])
    m_nofdr = get_metrics(scores_nofdr["flagged"])

    # Compute Rules baseline on this exact dataset
    rules = load_rules(Path("rules/rules.yaml"))
    rule_hits = run_rules(sub_path, vil_path, rules=rules)
    df_sub = pd.read_parquet(sub_path)
    sub_to_enum = dict(zip(df_sub["submission_id"], df_sub["enumerator_id"]))
    flagged_enums_rules: Set[str] = set()
    for _, row in rule_hits.iterrows():
        u_id = row["unit_id"]
        if row["level"] == "submission":
            e = sub_to_enum.get(u_id)
        else:
            e = "_".join(u_id.split("_")[:2])
        if e:
            flagged_enums_rules.add(e)
    rules_flags = scores_full["enumerator_id"].isin(flagged_enums_rules)
    m_rules = get_metrics(rules_flags)

    print("\n" + "=" * 80)
    print("TABLE 2: Detection Performance: Full Engine vs Ablations vs Rules Baseline")
    print("=" * 80)
    t2_records = [
        {"Model / Method": "Full Engine (Shrinkage + BH FDR)", **m_full},
        {"Model / Method": "--no-shrinkage (Binomial + Empirical SE)", **m_noshrink},
        {"Model / Method": "--no-fdr (Unadjusted p < 0.05)", **m_nofdr},
        {"Model / Method": "Rules Baseline (12 Rules Union)", **m_rules},
    ]
    t2_df = pd.DataFrame(t2_records)
    print(t2_df.to_string(index=False, formatters={
        "Precision": "{:.4f}".format,
        "Recall": "{:.4f}".format,
        "F1": "{:.4f}".format,
    }))

    # -------------------------------------------------------------
    # Table 3: Shrinkage Benefit on Small Samples (n < 15, seeds 0..19)
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"TABLE 3: Shrinkage Benefit on Small Workload Honest Enumerators (n < 15, Seeds 0..{n_calib_rounds-1})")
    print("=" * 80)

    honest_small_total = 0
    honest_small_flagged_full = 0
    honest_small_flagged_noshrink = 0

    for s in range(n_calib_rounds):
        s_out = eval_dir / f"round_s{s}"
        s_truth = eval_dir / f"truth_s{s}"
        s_sub = run_generation(
            icc_level="medium",
            seed=s,
            out_dir=s_out,
            round_num=1,
            prevalence=prevalence,
            truth_dir=s_truth,
        )
        s_vil = s_out / "reference" / "villages.parquet"
        s_truth_enum = s_truth / "round=1" / "labels_enumerator.parquet"
        df_s_truth = pd.read_parquet(s_truth_enum)
        honest_set = set(df_s_truth[df_s_truth["primary_mode"].isna()]["enumerator_id"])

        s_feat = build_feature_table(s_sub, s_vil)
        s_scores_full = score_enumerators(s_feat, q=0.10)
        s_scores_noshrink = score_enumerators(s_feat, no_shrinkage=True, q=0.10)

        # Filter to honest enumerators with n < 15
        mask_small_honest = (s_scores_full["n_interviews"] < 15) & (s_scores_full["enumerator_id"].isin(honest_set))
        small_ids = set(s_scores_full[mask_small_honest]["enumerator_id"])
        honest_small_total += len(small_ids)

        flagged_full_ids = set(s_scores_full[s_scores_full["flagged"]]["enumerator_id"])
        flagged_noshrink_ids = set(s_scores_noshrink[s_scores_noshrink["flagged"]]["enumerator_id"])

        honest_small_flagged_full += len(small_ids & flagged_full_ids)
        honest_small_flagged_noshrink += len(small_ids & flagged_noshrink_ids)

    rate_full = honest_small_flagged_full / honest_small_total if honest_small_total > 0 else 0.0
    rate_noshrink = honest_small_flagged_noshrink / honest_small_total if honest_small_total > 0 else 0.0

    t3_df = pd.DataFrame([
        {
            "Method": "Full Engine (with Empirical Bayes Shrinkage)",
            "Honest Enumerators (n < 15)": honest_small_total,
            "False Flags": honest_small_flagged_full,
            "False-Flag Rate": f"{rate_full:.2%}",
        },
        {
            "Method": "No Shrinkage (--no-shrinkage)",
            "Honest Enumerators (n < 15)": honest_small_total,
            "False Flags": honest_small_flagged_noshrink,
            "False-Flag Rate": f"{rate_noshrink:.2%}",
        },
    ])
    print(t3_df.to_string(index=False))

    # Clean up eval dir
    shutil.rmtree(eval_dir)


if __name__ == "__main__":
    evaluate_scoring(seed=42, prevalence=0.125, n_calib_rounds=20)
