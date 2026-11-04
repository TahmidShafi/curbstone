"""Evaluation script for held-out enumerator ranking by risk score (seeds 400..419)."""

import argparse
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


def evaluate_ranking(
    start_seed: int = 400,
    n_seeds: int = 20,
    prevalence: float = 0.125,
    k: int = 4,
    verbose: bool = False,
) -> None:
    eval_dir = Path("eval_ranking_temp")
    eval_dir.mkdir(parents=True, exist_ok=True)

    rules = load_rules(Path("rules/rules.yaml"))

    methods = [
        "Scoring v3 (Risk Score)",
        "Scoring v3 (--no-shrinkage)",
        "Scoring v2 (Risk Score)",
        "Rules Baseline (Distinct Rules Hit)",
    ]

    metrics: Dict[str, Dict[str, List[float]]] = {
        m: {"precision": [], "recall": [], "small_honest_count": []} for m in methods
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

        # 1. Scoring v3
        scores_v3 = score_enumerators(df_feat, scoring_version="v3")
        # 2. Scoring v3 no-shrinkage
        scores_v3_noshrink = score_enumerators(df_feat, scoring_version="v3", no_shrinkage=True)
        # 3. Scoring v2
        scores_v2 = score_enumerators(df_feat, scoring_version="v2")

        # 4. Rules baseline
        rule_hits = run_rules(sub_path, vil_path, rules=rules)
        enum_rule_hits: Dict[str, Set[str]] = {e: set() for e in scores_v3["enumerator_id"]}
        for _, row in rule_hits.iterrows():
            u_id = row["unit_id"]
            e = sub_to_enum.get(u_id) if row["level"] == "submission" else "_".join(u_id.split("_")[:2])
            if e in enum_rule_hits:
                enum_rule_hits[e].add(row["rule_id"])
        rules_scores = [len(enum_rule_hits[e]) for e in scores_v3["enumerator_id"]]

        # Fixed RNG for tie-breaking in this seed
        rng = np.random.default_rng(12345 + s)
        tiebreakers = rng.uniform(0.0, 1.0, size=len(scores_v3))

        candidates = {
            "Scoring v3 (Risk Score)": scores_v3["risk_score"].values,
            "Scoring v3 (--no-shrinkage)": scores_v3_noshrink["risk_score"].values,
            "Scoring v2 (Risk Score)": scores_v2["risk_score"].values,
            "Rules Baseline (Distinct Rules Hit)": np.array(rules_scores, dtype=float),
        }

        # Evaluate top-k for each method
        for m_name, score_arr in candidates.items():
            df_eval = pd.DataFrame({
                "enumerator_id": scores_v3["enumerator_id"],
                "n_interviews": scores_v3["n_interviews"],
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
            small_honest_count = int(small_honest.sum())

            metrics[m_name]["precision"].append(prec)
            metrics[m_name]["recall"].append(rec)
            metrics[m_name]["small_honest_count"].append(small_honest_count)

    shutil.rmtree(eval_dir, ignore_errors=True)

    total_slots = n_seeds * k

    # Summarize results across seeds
    rows = []
    for m_name in methods:
        p_arr = np.array(metrics[m_name]["precision"])
        r_arr = np.array(metrics[m_name]["recall"])
        sh_total = int(np.sum(metrics[m_name]["small_honest_count"]))

        rows.append({
            "Method": m_name,
            "Precision@k (Mean)": float(np.mean(p_arr)),
            "Precision@k [10th, 90th]": f"[{np.percentile(p_arr, 10):.4f}, {np.percentile(p_arr, 90):.4f}]",
            "Recall@k (Mean)": float(np.mean(r_arr)),
            "Recall@k [10th, 90th]": f"[{np.percentile(r_arr, 10):.4f}, {np.percentile(r_arr, 90):.4f}]",
            "Top-k Small Honest (n < 15)": f"{sh_total} / {total_slots}",
        })

    df_res = pd.DataFrame(rows)
    print("\n" + "=" * 80)
    print(f"TABLE: Held-Out Enumerator Ranking Performance (Seeds {start_seed}..{start_seed + n_seeds - 1}, k={k})")
    print("=" * 80)
    print(df_res.to_string(index=False, formatters={
        "Precision@k (Mean)": "{:.4f}".format,
        "Recall@k (Mean)": "{:.4f}".format,
    }))

    # Paired bootstrap for differences in Precision@k (10,000 resamples of seeds)
    boot_rng = np.random.default_rng(42)
    B = 10000
    p_v3 = np.array(metrics["Scoring v3 (Risk Score)"]["precision"])
    p_rules = np.array(metrics["Rules Baseline (Distinct Rules Hit)"]["precision"])
    p_noshrink = np.array(metrics["Scoring v3 (--no-shrinkage)"]["precision"])

    diff_rules = p_v3 - p_rules
    diff_noshrink = p_v3 - p_noshrink

    boot_diff_rules = []
    boot_diff_noshrink = []
    for _ in range(B):
        idx = boot_rng.choice(n_seeds, size=n_seeds, replace=True)
        boot_diff_rules.append(float(np.mean(diff_rules[idx])))
        boot_diff_noshrink.append(float(np.mean(diff_noshrink[idx])))

    ci_rules = (np.percentile(boot_diff_rules, 2.5), np.percentile(boot_diff_rules, 97.5))
    ci_noshrink = (np.percentile(boot_diff_noshrink, 2.5), np.percentile(boot_diff_noshrink, 97.5))

    print("\n" + "=" * 80)
    print("PAIRED BOOTSTRAP: Difference in Precision@4 (10,000 seed resamples)")
    print("=" * 80)
    print(f"v3 - Rules:             Mean = {np.mean(diff_rules):+.4f},  95% CI = [{ci_rules[0]:+.4f}, {ci_rules[1]:+.4f}]")
    print(f"v3 - (v3 --no-shrink):  Mean = {np.mean(diff_noshrink):+.4f},  95% CI = [{ci_noshrink[0]:+.4f}, {ci_noshrink[1]:+.4f}]")

    if verbose:
        print("\n" + "=" * 80)
        print(f"PER-SEED PRECISION@{k} BREAKDOWN (Seeds {start_seed}..{start_seed + n_seeds - 1})")
        print("=" * 80)
        df_per_seed = pd.DataFrame({"Seed": list(range(start_seed, start_seed + n_seeds))})
        for m_name in methods:
            df_per_seed[m_name] = metrics[m_name]["precision"]
        print(df_per_seed.to_string(index=False, formatters={m: "{:.4f}".format for m in methods}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate enumerator ranking on held-out seeds.")
    parser.add_argument("--start-seed", type=int, default=400, help="Start seed (default: 400)")
    parser.add_argument("--n-seeds", type=int, default=20, help="Number of seeds (default: 20)")
    parser.add_argument("--prevalence", type=float, default=0.125, help="Prevalence (default: 0.125)")
    parser.add_argument("--k", type=int, default=4, help="Top-k cut (default: 4)")
    parser.add_argument("--verbose", action="store_true", help="Print per-seed breakdown")
    args = parser.parse_args()

    evaluate_ranking(
        start_seed=args.start_seed,
        n_seeds=args.n_seeds,
        prevalence=args.prevalence,
        k=args.k,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
