"""Build demo round data and copy robustness artifacts for website presentation."""

import sys
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime
import json
import shutil
from typing import Any, Dict, Optional
import numpy as np
import pandas as pd
import yaml

from engine.evidence import build_evidence, export_evidence_json
from engine.features import build_feature_table
from engine.rules import load_rules, run_rules
from engine.scoring import score_enumerators
from generator.run import run_generation


def build_demo(
    seed: int = 5000,
    prevalence: float = 0.125,
    icc_level: str = "medium",
    workload_range: Optional[list] = None,
    output_dir: Optional[Path] = None,
    results_dir: Optional[Path] = None,
    verbose: bool = True,
) -> Dict[str, Path]:
    """Generate demo survey round and write all site data and exports."""
    if workload_range is None:
        workload_range = [5, 60]

    project_root = Path(__file__).resolve().parent.parent
    if output_dir is None:
        output_dir = project_root / "site" / "src" / "data"
    if results_dir is None:
        results_dir = project_root / "site" / "src" / "results"

    output_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    temp_gen_dir = project_root / "temp_demo_generation"
    temp_truth_dir = temp_gen_dir / "truth"
    if temp_gen_dir.exists():
        shutil.rmtree(temp_gen_dir)

    try:
        # 1. Generate survey data
        if verbose:
            print(f"Generating demo round with seed={seed}, prevalence={prevalence}, workload={workload_range}...")
        sub_path = run_generation(
            icc_level=icc_level,
            seed=seed,
            out_dir=temp_gen_dir,
            round_num=1,
            prevalence=prevalence,
            include_holdout=False,
            workload_range=workload_range,
            truth_dir=temp_truth_dir,
            verbose=False,
        )
        vil_path = temp_gen_dir / "reference" / "villages.parquet"
        truth_path = temp_truth_dir / "round=1" / "labels_enumerator.parquet"

        df_sub = pd.read_parquet(sub_path)
        df_vil = pd.read_parquet(vil_path)
        df_truth = pd.read_parquet(truth_path)

        # Write survey submissions and reference villages
        df_sub.to_parquet(output_dir / "submissions.parquet", engine="pyarrow", index=False)
        df_vil.to_parquet(output_dir / "villages.parquet", engine="pyarrow", index=False)

        # 2. Extract features and score enumerators
        if verbose:
            print("Extracting features and computing shrinkage scores...")
        df_feat = build_feature_table(sub_path, vil_path, seed=12345)
        scores_shrinkage = score_enumerators(df_feat, scoring_version="v3", no_shrinkage=False)
        scores_noshrinkage = score_enumerators(df_feat, scoring_version="v3", no_shrinkage=True)

        scores_shrinkage.to_parquet(output_dir / "scores_shrinkage.parquet", engine="pyarrow", index=False)
        scores_noshrinkage.to_parquet(output_dir / "scores_noshrinkage.parquet", engine="pyarrow", index=False)

        # 3. Generate explanation evidence
        if verbose:
            print("Generating explanation evidence layer...")
        ev_dict = build_evidence(df_sub, df_vil, scores_shrinkage, df_feat)
        export_evidence_json(ev_dict, output_dir / "evidence.json")

        # 4. Write design parameters
        config_path = project_root / "config" / "params.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            params_yaml = yaml.safe_load(f)

        design_data: Dict[str, Any] = {
            "seed": seed,
            "round": 1,
            "prevalence": prevalence,
            "icc_level": icc_level,
            "icc_value": 0.15,
            "workload_range": workload_range,
            "workload_profile": "mixed",
            "n_enumerators": 40,
            "include_holdout": False,
            "active_fraud_modes": ["copy_paste", "straight_lining", "rushed", "invented_gps", "too_average"],
            "parameters": params_yaml,
        }
        with open(output_dir / "design.json", "w", encoding="utf-8") as f:
            json.dump(design_data, f, indent=2, sort_keys=True)

        # 5. Write ground truth labels (ensuring standard JSON null instead of NaN)
        truth_records = []
        for _, r in df_truth.iterrows():
            rec = {k: (None if pd.isna(v) else v) for k, v in r.items()}
            rec["is_fabricator"] = bool(r["n_fabricated"] > 0)
            truth_records.append(rec)
        with open(output_dir / "truth.json", "w", encoding="utf-8") as f:
            json.dump(truth_records, f, indent=2)

        # 6. Copy rules.yaml
        rules_src = project_root / "rules" / "rules.yaml"
        rules_dst = output_dir / "rules.yaml"
        shutil.copyfile(rules_src, rules_dst)

        # 7. Evaluate rules and generate flags exports (CSV and Stata DTA)
        if verbose:
            print("Evaluating DQA rules and building exports...")
        rules = load_rules(rules_src)
        rule_hits_df = run_rules(df_sub, df_vil, rules=rules)
        sub_to_enum = dict(zip(df_sub["submission_id"], df_sub["enumerator_id"]))
        enum_hits: Dict[str, int] = {str(e): 0 for e in scores_shrinkage["enumerator_id"]}
        for _, row in rule_hits_df.iterrows():
            u_id = str(row["unit_id"])
            e = sub_to_enum.get(u_id) if row["level"] == "submission" else "_".join(u_id.split("_")[:2])
            if e in enum_hits:
                enum_hits[e] += 1

        df_flags = scores_shrinkage.sort_values(
            by=["risk_score", "enumerator_id"], ascending=[False, True]
        ).reset_index(drop=True)
        df_flags["rank"] = (np.arange(len(df_flags)) + 1).astype("int32")
        df_flags["n"] = df_flags["n_interviews"].astype("int32")
        df_flags["risk_score"] = df_flags["risk_score"].clip(lower=0.0).round(4)
        df_flags["evidence"] = df_flags["evidence"].fillna("")
        df_flags["rule_hits"] = np.array([enum_hits.get(str(e), 0) for e in df_flags["enumerator_id"]], dtype="int32")

        export_cols = ["enumerator_id", "n", "risk_score", "rank", "evidence", "rule_hits"]
        df_export = df_flags[export_cols].copy()

        flags_csv_path = output_dir / "flags.csv"
        flags_dta_path = output_dir / "flags.dta"
        df_export.to_csv(flags_csv_path, index=False)
        fixed_dt = datetime(2026, 11, 1, 0, 0, 0)
        df_export.to_stata(flags_dta_path, write_index=False, time_stamp=fixed_dt)

        # 8. Copy robustness summary and figures
        rob_src_dir = project_root / "outputs" / "robustness"
        for artifact in ["summary.md", "small_n_honest.png", "detection_by_day.png"]:
            src_file = rob_src_dir / artifact
            if src_file.is_file():
                shutil.copyfile(src_file, results_dir / artifact)

        if verbose:
            print("Successfully built demo artifacts and exported to site/src/data and site/src/results.")

        return {
            "submissions": output_dir / "submissions.parquet",
            "villages": output_dir / "villages.parquet",
            "scores_shrinkage": output_dir / "scores_shrinkage.parquet",
            "scores_noshrinkage": output_dir / "scores_noshrinkage.parquet",
            "evidence": output_dir / "evidence.json",
            "design": output_dir / "design.json",
            "truth": output_dir / "truth.json",
            "rules": output_dir / "rules.yaml",
            "flags_csv": flags_csv_path,
            "flags_dta": flags_dta_path,
        }
    finally:
        if temp_gen_dir.exists():
            shutil.rmtree(temp_gen_dir)


if __name__ == "__main__":
    build_demo()
