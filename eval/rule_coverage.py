"""Evaluation script: Rule coverage and detection breakdown across fraud modes."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import Dict, List
import pandas as pd

from engine.rules import load_rules, run_rules
from generator.run import run_generation


def run_evaluation(seed: int = 42, prevalence: float = 0.125) -> None:
    eval_dir = Path("eval_data")
    honest_dir = eval_dir / "honest"
    fraud_dir = eval_dir / "fraud"
    truth_dir = eval_dir / "truth"

    print("=" * 70)
    print("Generating data for evaluation...")
    honest_sub_path = run_generation(
        icc_level="medium",
        seed=seed,
        out_dir=honest_dir,
        round_num=1,
        no_fraud=True,
    )
    honest_vil_path = honest_dir / "reference" / "villages.parquet"

    fraud_sub_path = run_generation(
        icc_level="medium",
        seed=seed,
        out_dir=fraud_dir,
        round_num=1,
        prevalence=prevalence,
        truth_dir=truth_dir,
    )
    fraud_vil_path = fraud_dir / "reference" / "villages.parquet"
    truth_sub_path = truth_dir / "round=1" / "labels_submission.parquet"

    # Execute rules
    rules = load_rules(Path("rules/rules.yaml"))
    rule_ids = [r["id"] for r in rules]

    hits_honest = run_rules(honest_sub_path, honest_vil_path, rules=rules)
    hits_fraud = run_rules(fraud_sub_path, fraud_vil_path, rules=rules)

    # -------------------------------------------------------------
    # Table 1: rule_id × [honest round hits, fraud round hits]
    # -------------------------------------------------------------
    honest_counts = hits_honest["rule_id"].value_counts().to_dict() if not hits_honest.empty else {}
    fraud_counts = hits_fraud["rule_id"].value_counts().to_dict() if not hits_fraud.empty else {}

    t1_records = []
    for r_id in rule_ids:
        t1_records.append({
            "rule_id": r_id,
            "honest_round_hits": honest_counts.get(r_id, 0),
            "fraud_round_hits": fraud_counts.get(r_id, 0),
        })
    df_t1 = pd.DataFrame(t1_records)

    print("\n" + "=" * 70)
    print("TABLE 1: rule_id × [honest round hits, fraud round hits] (seed 42, prevalence 0.125)")
    print("=" * 70)
    print(df_t1.to_string(index=False))

    # Load submissions and truth labels
    df_sub = pd.read_parquet(fraud_sub_path)
    df_labels = pd.read_parquet(truth_sub_path)
    df_sub["date"] = df_sub["start_time"].str[:10]
    df_sub["enum_day"] = df_sub["enumerator_id"] + "_" + df_sub["date"]
    merged = pd.merge(df_sub, df_labels, on="submission_id")

    sub_hits = hits_fraud[hits_fraud["level"] == "submission"]
    sub_flagged_ids = set(sub_hits["unit_id"])

    day_hits = hits_fraud[hits_fraud["level"] == "enumerator_day"]
    day_flagged_units = set(day_hits["unit_id"])
    day_flagged_sub_ids = set(df_sub[df_sub["enum_day"].isin(day_flagged_units)]["submission_id"])

    all_flagged_ids = sub_flagged_ids | day_flagged_sub_ids

    # -------------------------------------------------------------
    # Table 2: Per fraud mode coverage
    # -------------------------------------------------------------
    fab_submissions = merged[merged["is_fabricated"] == 1]
    modes = sorted(fab_submissions["fraud_mode"].unique())

    t2_records = []
    for mode in modes:
        grp = fab_submissions[fab_submissions["fraud_mode"] == mode]
        n_fab = len(grp)
        # Submission-level caught
        sub_caught = grp[grp["submission_id"].isin(sub_flagged_ids)]
        # All rules (including day-level R12) caught
        all_caught = grp[grp["submission_id"].isin(all_flagged_ids)]

        # Rules fired
        fired_sub = sub_hits[sub_hits["unit_id"].isin(grp["submission_id"])]["rule_id"].unique().tolist()
        if any(grp["enum_day"].isin(day_flagged_units)):
            fired_sub.append("R12")
        fired_rules_str = ", ".join(sorted(set(fired_sub))) if fired_sub else "none"

        t2_records.append({
            "fraud_mode": mode,
            "n_fabricated": n_fab,
            "n_caught_sub_rules": len(sub_caught),
            "share_caught_sub": f"{len(sub_caught) / n_fab:.1%}",
            "n_caught_all_rules": len(all_caught),
            "share_caught_all": f"{len(all_caught) / n_fab:.1%}",
            "rules_fired": fired_rules_str,
        })
    df_t2 = pd.DataFrame(t2_records)

    print("\n" + "=" * 70)
    print("TABLE 2: Detection coverage by fraud mode (seed 42, prevalence 0.125)")
    print("=" * 70)
    print(df_t2.to_string(index=False))

    # -------------------------------------------------------------
    # Table 3: False positives in the fraud round
    # -------------------------------------------------------------
    honest_submissions = merged[merged["is_fabricated"] == 0]
    n_honest_total = len(honest_submissions)

    # Sub-level false positives
    fp_sub = honest_submissions[honest_submissions["submission_id"].isin(sub_flagged_ids)]
    fp_sub_hits = sub_hits[sub_hits["unit_id"].isin(fp_sub["submission_id"])]

    # Day-level false positives (honest interviews conducted on flagged days)
    fp_all = honest_submissions[honest_submissions["submission_id"].isin(all_flagged_ids)]

    print("\n" + "=" * 70)
    print("TABLE 3: False positives (honest submissions in fraud round flagged by rules)")
    print("=" * 70)
    print(f"Total honest submissions in fraud round: {n_honest_total}")
    print(f"False positives by submission-level rules (R01-R11): {len(fp_sub)} ({len(fp_sub) / n_honest_total:.2%})")
    if not fp_sub.empty:
        fp_by_rule = fp_sub_hits["rule_id"].value_counts().to_dict()
        print(f"  Breakdown by rule: {fp_by_rule}")
        print("  Note: R11 duplicate check flags all members of a duplicate pair; when a fabricator")
        print("        copies an honest survey, both the copy and the genuine source are identical.")
    print(f"Honest submissions occurring on an infeasible-workload day (R12): {len(fp_all)} ({len(fp_all) / n_honest_total:.2%})")

    # -------------------------------------------------------------
    # Table 4: Enumerator-level classification (label: fab_share >= 0.10)
    # -------------------------------------------------------------
    truth_enum_path = truth_dir / "round=1" / "labels_enumerator.parquet"
    df_enum = pd.read_parquet(truth_enum_path)

    # Map rule hits to enumerators
    sub_to_enum = dict(zip(df_sub["submission_id"], df_sub["enumerator_id"]))
    enum_hits: Dict[str, set] = {}
    for _, row in hits_fraud.iterrows():
        u_id = row["unit_id"]
        r_id = row["rule_id"]
        if row["level"] == "submission":
            e_id = sub_to_enum.get(u_id)
        else:
            e_id = "_".join(u_id.split("_")[:2])
        if e_id:
            enum_hits.setdefault(e_id, set()).add(r_id)

    df_enum["is_fab_true"] = df_enum["fab_share_realized"] >= 0.10
    df_enum["is_flagged"] = df_enum["enumerator_id"].isin(enum_hits.keys())

    tp_df = df_enum[df_enum["is_fab_true"] & df_enum["is_flagged"]]
    fp_df = df_enum[~df_enum["is_fab_true"] & df_enum["is_flagged"]]
    fn_df = df_enum[df_enum["is_fab_true"] & ~df_enum["is_flagged"]]
    tn_df = df_enum[~df_enum["is_fab_true"] & ~df_enum["is_flagged"]]

    tp, fp, fn, tn = len(tp_df), len(fp_df), len(fn_df), len(tn_df)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    print("\n" + "=" * 70)
    print("TABLE 4: Enumerator-level results (label: fab_share >= 0.10)")
    print("=" * 70)
    print(f"TP: {tp} | FP: {fp} | FN: {fn} | TN: {tn}")
    print(f"Precision: {precision:.4f} ({precision:.1%}) | Recall: {recall:.4f} ({recall:.1%})")
    print("\nFalse Positive Enumerators:")
    if not fp_df.empty:
        for _, r in fp_df.iterrows():
            e_id = r["enumerator_id"]
            rules_str = ", ".join(sorted(enum_hits[e_id]))
            print(f"  - {e_id}: rules=[{rules_str}], n_interviews={r['n_interviews']}")
    else:
        print("  None")

    # Clean up eval_data
    import shutil
    shutil.rmtree(eval_dir)


if __name__ == "__main__":
    run_evaluation()
