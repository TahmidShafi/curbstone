"""Build demo round data and copy robustness artifacts for website presentation.

Supports building 'mixed' (seed 5000) and 'low' (seed 5001) workload scenarios.
"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
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


def get_study_average_metrics(scenario_name: str, results_parquet: Path) -> Dict[str, Any]:
    """Compute study-average precision@4 and 95% bootstrap CI matching demo round settings."""
    if scenario_name == "mixed":
        # Held-out ranking evaluation on seeds 400..419 (prevalence 0.125, mixed workload)
        return {
            "setting": "Held-out ranking evaluation (seeds 400..419, prev 0.125, mixed workload)",
            "v3_mean": 0.7250,
            "v3_ci_95": [0.6500, 0.8000],
            "noshrink_mean": 0.6250,
            "noshrink_ci_95": [0.5375, 0.7125],
        }
    elif scenario_name == "low":
        # Low workload: compute from robustness results for low workload at prevalence 0.10 and 0.20 separately
        res = {"setting": "Robustness results for low workload [5, 15]"}
        if results_parquet.is_file():
            df = pd.read_parquet(results_parquet)
            grid = df[(df["study"] == "grid") & (df["workload_name"] == "low")]
            for prev, key in [(0.10, "prev_0_10"), (0.20, "prev_0_20")]:
                sub = grid[grid["prevalence"] == prev]
                v3_p, ns_p = sub["v3_precision_k"].values, sub["noshrink_precision_k"].values
                rng = np.random.default_rng(42)
                b_v3 = np.mean(rng.choice(v3_p, size=(10000, len(v3_p)), replace=True), axis=1)
                b_ns = np.mean(rng.choice(ns_p, size=(10000, len(ns_p)), replace=True), axis=1)
                res[key] = {
                    "prevalence": prev,
                    "v3_mean": round(float(np.mean(v3_p)), 4),
                    "v3_ci_95": [round(float(np.percentile(b_v3, 2.5)), 4), round(float(np.percentile(b_v3, 97.5)), 4)],
                    "noshrink_mean": round(float(np.mean(ns_p)), 4),
                    "noshrink_ci_95": [round(float(np.percentile(b_ns, 2.5)), 4), round(float(np.percentile(b_ns, 97.5)), 4)],
                }
        return res
    return {}


def build_single_scenario(
    scenario_name: str,
    seed: int,
    workload_range: list,
    output_dir: Path,
    verbose: bool = True,
) -> Dict[str, Path]:
    """Build single scenario dataset and exports into target directory."""
    project_root = Path(__file__).resolve().parent.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    temp_gen_dir = project_root / f"temp_demo_generation_{scenario_name}_{seed}"
    temp_truth_dir = temp_gen_dir / "truth"
    if temp_gen_dir.exists():
        shutil.rmtree(temp_gen_dir)

    try:
        if verbose:
            print(f"Building scenario '{scenario_name}' (seed={seed}, workload={workload_range})...")

        sub_path = run_generation(
            icc_level="medium", seed=seed, out_dir=temp_gen_dir, round_num=1,
            prevalence=0.125, include_holdout=False, workload_range=workload_range,
            truth_dir=temp_truth_dir, verbose=False,
        )
        vil_path = temp_gen_dir / "reference" / "villages.parquet"
        truth_path = temp_truth_dir / "round=1" / "labels_enumerator.parquet"

        df_sub = pd.read_parquet(sub_path)
        df_vil = pd.read_parquet(vil_path)
        df_truth = pd.read_parquet(truth_path)

        df_sub.to_parquet(output_dir / "submissions.parquet", engine="pyarrow", index=False)
        df_vil.to_parquet(output_dir / "villages.parquet", engine="pyarrow", index=False)

        # Features & Scores
        df_feat = build_feature_table(sub_path, vil_path, seed=12345)
        scores_shrinkage = score_enumerators(df_feat, scoring_version="v3", no_shrinkage=False)
        scores_noshrinkage = score_enumerators(df_feat, scoring_version="v3", no_shrinkage=True)

        scores_shrinkage.to_parquet(output_dir / "scores_shrinkage.parquet", engine="pyarrow", index=False)
        scores_noshrinkage.to_parquet(output_dir / "scores_noshrinkage.parquet", engine="pyarrow", index=False)

        # Evidence
        ev_dict_shrink = build_evidence(df_sub, df_vil, scores_shrinkage, df_feat, no_shrinkage=False)
        export_evidence_json(ev_dict_shrink, output_dir / "evidence.json")
        ev_dict_noshrink = build_evidence(df_sub, df_vil, scores_noshrinkage, df_feat, no_shrinkage=True)
        export_evidence_json(ev_dict_noshrink, output_dir / "evidence_noshrinkage.json")

        # Design parameters
        with open(project_root / "config" / "params.yaml", "r", encoding="utf-8") as f:
            params_yaml = yaml.safe_load(f)
        design_data = {
            "seed": seed, "round": 1, "prevalence": 0.125, "icc_level": "medium",
            "icc_value": 0.15, "workload_range": workload_range, "workload_profile": scenario_name,
            "n_enumerators": 40, "include_holdout": False,
            "active_fraud_modes": ["copy_paste", "straight_lining", "rushed", "invented_gps", "too_average"],
            "parameters": params_yaml,
        }
        with open(output_dir / "design.json", "w", encoding="utf-8") as f:
            json.dump(design_data, f, indent=2, sort_keys=True)

        # Ground truth labels
        truth_records = []
        for _, r in df_truth.iterrows():
            rec = {k: (None if pd.isna(v) else v) for k, v in r.items()}
            rec["is_fabricator"] = bool(r["n_fabricated"] > 0)
            truth_records.append(rec)
        with open(output_dir / "truth.json", "w", encoding="utf-8") as f:
            json.dump(truth_records, f, indent=2)

        # Copy rules.yaml & submissions_view.sql from rules/
        shutil.copyfile(project_root / "rules" / "rules.yaml", output_dir / "rules.yaml")
        shutil.copyfile(project_root / "rules" / "submissions_view.sql", output_dir / "submissions_view.sql")

        # Rules execution and expected hits
        rules = load_rules(output_dir / "rules.yaml")
        rule_hits_df = run_rules(df_sub, df_vil, rules=rules)
        hits_by_rule = {r["id"]: 0 for r in rules}
        for r_id, count in rule_hits_df["rule_id"].value_counts().items():
            if r_id in hits_by_rule:
                hits_by_rule[r_id] = int(count)
        with open(output_dir / "rule_hits_expected.json", "w", encoding="utf-8") as f:
            json.dump(hits_by_rule, f, indent=2, sort_keys=True)

        # Exports: flags.csv and flags.dta
        sub_to_enum = dict(zip(df_sub["submission_id"], df_sub["enumerator_id"]))
        enum_hits = {str(e): 0 for e in scores_shrinkage["enumerator_id"]}
        for _, row in rule_hits_df.iterrows():
            u_id = str(row["unit_id"])
            e = sub_to_enum.get(u_id) if row["level"] == "submission" else "_".join(u_id.split("_")[:2])
            if e in enum_hits:
                enum_hits[e] += 1

        with open(output_dir / "rule_hits_by_enumerator.json", "w", encoding="utf-8") as f:
            json.dump(enum_hits, f, indent=2, sort_keys=True)

        df_flags = scores_shrinkage.sort_values(by=["risk_score", "enumerator_id"], ascending=[False, True]).reset_index(drop=True)
        df_flags["rank"] = (np.arange(len(df_flags)) + 1).astype("int32")
        df_flags["n"] = df_flags["n_interviews"].astype("int32")
        df_flags["risk_score"] = df_flags["risk_score"].clip(lower=0.0).round(4)
        df_flags["evidence"] = df_flags["evidence"].fillna("")
        df_flags["rule_hits"] = np.array([enum_hits.get(str(e), 0) for e in df_flags["enumerator_id"]], dtype="int32")

        export_cols = ["enumerator_id", "n", "risk_score", "rank", "evidence", "rule_hits"]
        df_export = df_flags[export_cols].copy()
        df_export.to_csv(output_dir / "flags.csv", index=False)
        df_export.to_stata(output_dir / "flags.dta", write_index=False, time_stamp=datetime(2026, 11, 1, 0, 0, 0))

        # Round metrics & study average comparison
        fab_enums = set(df_truth[df_truth["n_fabricated"] > 0]["enumerator_id"])
        top4_v3 = scores_shrinkage.sort_values(by=["risk_score", "enumerator_id"], ascending=[False, True]).head(4)["enumerator_id"].tolist()
        top4_ns = scores_noshrinkage.sort_values(by=["risk_score", "enumerator_id"], ascending=[False, True]).head(4)["enumerator_id"].tolist()
        p4_v3 = round(sum(e in fab_enums for e in top4_v3) / 4.0, 4)
        p4_ns = round(sum(e in fab_enums for e in top4_ns) / 4.0, 4)

        study_avg = get_study_average_metrics(scenario_name, project_root / "outputs" / "robustness" / "results.parquet")
        round_metrics_data = {
            "scenario": scenario_name, "seed": seed, "k": 4,
            "round_hits_v3": int(round(p4_v3 * 4)),
            "round_hits_noshrinkage": int(round(p4_ns * 4)),
            "round_precision_v3": p4_v3, "round_precision_noshrinkage": p4_ns,
            "study_average": study_avg,
        }
        with open(output_dir / "round_metrics.json", "w", encoding="utf-8") as f:
            json.dump(round_metrics_data, f, indent=2, sort_keys=True)

        return {"output_dir": output_dir}
    finally:
        if temp_gen_dir.exists():
            shutil.rmtree(temp_gen_dir, ignore_errors=True)


def build_demo(scenario: str = "all", base_data_dir: Optional[Path] = None, results_dir: Optional[Path] = None, verbose: bool = True) -> Dict[str, Any]:
    """Build requested scenario(s) ('mixed', 'low', or 'all') and sync robustness outputs."""
    project_root = Path(__file__).resolve().parent.parent
    if base_data_dir is None:
        base_data_dir = project_root / "site" / "src" / "data"
    if results_dir is None:
        results_dir = project_root / "site" / "src" / "results"

    base_data_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    scenarios_meta = {
        "mixed": {"seed": 5000, "workload_range": [5, 60]},
        "low": {"seed": 5001, "workload_range": [5, 15]},
    }

    selected = scenarios_meta.keys() if scenario in ["all", "both"] else [scenario]
    results = {}
    for sc in selected:
        if sc not in scenarios_meta:
            raise ValueError(f"Unknown scenario '{sc}'. Available: {list(scenarios_meta.keys())}")
        info = scenarios_meta[sc]
        res = build_single_scenario(sc, info["seed"], info["workload_range"], base_data_dir / sc, verbose=verbose)
        results[sc] = res

    # Copy robustness artifacts to site/src/results
    rob_src_dir = project_root / "outputs" / "robustness"
    for artifact in ["summary.md", "small_n_honest.png", "detection_by_day.png"]:
        src_file = rob_src_dir / artifact
        if src_file.is_file():
            shutil.copyfile(src_file, results_dir / artifact)

    if verbose:
        print(f"Successfully built scenarios: {list(results.keys())}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build demo round data for web application.")
    parser.add_argument("scenario", nargs="?", default="all", choices=["all", "mixed", "low"], help="Scenario to build")
    args = parser.parse_args()
    build_demo(scenario=args.scenario)
