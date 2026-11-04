"""Evaluation script for held-out enumerator ranking by risk score (seeds 200..219)."""

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


def evaluate_ranking(start_seed: int = 200, n_seeds: int = 20, prevalence: float = 0.125, k: int = 4) -> None:
    eval_dir = Path("eval_ranking_temp")
    eval_dir.mkdir(parents=True, exist_ok=True)

    rules = load_rules(Path("rules/rules.yaml"))

    methods = [
        "Scoring v1 (Risk Score)",
        "Scoring v2 (Risk Score)",
        "Scoring v2 (--no-shrinkage)",
        "Rules Baseline (Distinct Rules Hit)",
    ]

    metrics: Dict[str, Dict[str, List[float]]] = {
        m: {"precision": [], "recall": [], "small_honest_share": []} for m in methods
    }

    print("=" * 80)
    print(f"EVALUATION: Enumerator Ranking (Seeds {start_seed}..{start_seed + n_seeds - 1}, Prevalence {prevalence}, k={k})")
    print("=" * 80)

    for s in range(start_seed, start_seed + n_seeds):
        r_dir = eval_dir / f"seed_{s}"
        t_dir = eval_dir / f"truth_{s}"

        sub_path = run_generation(
            icc_level="medium",
            seed=s,
            out_dir=r_dir,
            round_num=1,
            prevalence=prevalence,
            truth_dir=t_dir,
        )
        vil_path = r_dir / "reference" / "villages.parquet"
        truth_enum_path = t_dir / "round=1" / "labels_enumerator.parquet"
        df_truth = pd.read_parquet(truth_enum_path)
        fab_share_map = df_truth.set_index("enumerator_id")["fab_share_realized"].to_dict()

        df_sub = pd.read_parquet(sub_path)
        sub_to_enum = dict(zip(df_sub["submission_id"], df_sub["enumerator_id"]))

        # Build feature table
        df_feat = build_feature_table(sub_path, vil_path)

        # 1. Scoring v1
        scores_v1 = score_enumerators(df_feat, scoring_version="v1")
        # 2. Scoring v2
        scores_v2 = score_enumerators(df_feat, scoring_version="v2")
        # 3. Scoring v2 no-shrinkage
        scores_v2_noshrink = score_enumerators(df_feat, scoring_version="v2", no_shrinkage=True)

        # 4. Rules baseline
        rule_hits = run_rules(sub_path, vil_path, rules=rules)
        enum_rule_hits: Dict[str, Set[str]] = {e: set() for e in scores_v1["enumerator_id"]}
        for _, row in rule_hits.iterrows():
            u_id = row["unit_id"]
            e = sub_to_enum.get(u_id) if row["level"] == "submission" else "_".join(u_id.split("_")[:2])
            if e in enum_rule_hits:
                enum_rule_hits[e].add(row["rule_id"])
        rules_scores = [len(enum_rule_hits[e]) for e in scores_v1["enumerator_id"]]

        # Fixed RNG for tie-breaking in this seed
        rng = np.random.default_rng(12345 + s)
        tiebreakers = rng.uniform(0.0, 1.0, size=len(scores_v1))

        candidates = {
            "Scoring v1 (Risk Score)": scores_v1["risk_score"].values,
            "Scoring v2 (Risk Score)": scores_v2["risk_score"].values,
            "Scoring v2 (--no-shrinkage)": scores_v2_noshrink["risk_score"].values,
            "Rules Baseline (Distinct Rules Hit)": np.array(rules_scores, dtype=float),
        }

        # Evaluate top-k for each method
        for m_name, score_arr in candidates.items():
            df_eval = pd.DataFrame({
                "enumerator_id": scores_v1["enumerator_id"],
                "n_interviews": scores_v1["n_interviews"],
                "score": score_arr,
                "tiebreaker": tiebreakers,
            })
            df_eval["is_fab"] = df_eval["enumerator_id"].map(lambda e: fab_share_map.get(e, 0.0) >= 0.10)

            # Sort descending by score, tiebreaker ascending
            df_sorted = df_eval.sort_values(by=["score", "tiebreaker"], ascending=[False, True])
            top_k = df_sorted.head(k)

            n_fab_total = int(df_eval["is_fab"].sum())
            tp = int(top_k["is_fab"].sum())
            prec = tp / k
            rec = tp / n_fab_total if n_fab_total > 0 else 0.0

            small_honest = (~top_k["is_fab"]) & (top_k["n_interviews"] < 15)
            small_honest_share = int(small_honest.sum()) / k

            metrics[m_name]["precision"].append(prec)
            metrics[m_name]["recall"].append(rec)
            metrics[m_name]["small_honest_share"].append(small_honest_share)

    shutil.rmtree(eval_dir, ignore_errors=True)

    # Summarize results across seeds
    rows = []
    for m_name in methods:
        p_arr = np.array(metrics[m_name]["precision"])
        r_arr = np.array(metrics[m_name]["recall"])
        sh_arr = np.array(metrics[m_name]["small_honest_share"])

        rows.append({
            "Method": m_name,
            "Precision@k (Mean)": float(np.mean(p_arr)),
            "Precision@k [10th, 90th]": f"[{np.percentile(p_arr, 10):.4f}, {np.percentile(p_arr, 90):.4f}]",
            "Recall@k (Mean)": float(np.mean(r_arr)),
            "Recall@k [10th, 90th]": f"[{np.percentile(r_arr, 10):.4f}, {np.percentile(r_arr, 90):.4f}]",
            "Share Top-k Small Honest (n < 15)": f"{float(np.mean(sh_arr)):.2%}",
        })

    df_res = pd.DataFrame(rows)
    print("\n" + "=" * 80)
    print("TABLE: Held-Out Enumerator Ranking Performance (Seeds 200..219, k=4)")
    print("=" * 80)
    print(df_res.to_string(index=False, formatters={
        "Precision@k (Mean)": "{:.4f}".format,
        "Recall@k (Mean)": "{:.4f}".format,
    }))


if __name__ == "__main__":
    evaluate_ranking(start_seed=200, n_seeds=20, prevalence=0.125, k=4)
