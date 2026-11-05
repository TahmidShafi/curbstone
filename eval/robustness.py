"""Robustness evaluation runner across 72 factorial configs, held-out mode, and detection days."""

import argparse
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from engine.features import build_feature_table
from engine.rules import load_rules, run_rules
from engine.scoring import score_enumerators
from eval.robustness_common import (
    ACTIVE_MODES,
    ALL_MODES,
    WORKING_DAYS,
    build_grid_configs,
    compute_average_precision,
    compute_mode_average_precision,
)
from generator.run import run_generation


def process_single_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Execute survey generation, feature extraction, and multi-method scoring for one task."""
    study = task["study"]
    cfg_id = task["config_id"]
    seed = task["seed"]
    day = task.get("day", 10)
    prev = task["prevalence"]
    wl_range = task["workload_range"]
    icc = task["icc_name"]
    sh_range = task["share_range"]
    inc_holdout = task.get("include_holdout", False)

    pid = os.getpid()
    temp_dir = Path(f"eval_temp_{study}_{cfg_id}_{seed}_{day}_{pid}")
    r_dir = temp_dir / "round"
    t_dir = temp_dir / "truth"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        sub_path = run_generation(
            icc_level=icc,
            seed=seed,
            out_dir=r_dir,
            round_num=1,
            prevalence=prev,
            truth_dir=t_dir,
            include_holdout=inc_holdout,
            workload_range=wl_range,
            share_range=sh_range,
            verbose=False,
        )
        vil_path = r_dir / "reference" / "villages.parquet"
        truth_enum_path = t_dir / "round=1" / "labels_enumerator.parquet"

        df_sub = pd.read_parquet(sub_path)
        df_truth = pd.read_parquet(truth_enum_path)

        # For detection-time runs: filter submissions up to end of working day d
        if study == "detection_time" and day < 10:
            start_dt = pd.to_datetime(df_sub["start_time"], format="ISO8601")
            cutoff_date = WORKING_DAYS[day - 1]
            df_sub = df_sub[start_dt.dt.date <= cutoff_date].copy()
            # Overwrite parquet for rule engine
            df_sub.to_parquet(sub_path, engine="pyarrow", index=False)

        fab_map = df_truth.set_index("enumerator_id")["fab_share_realized"].to_dict()
        mode_map = df_truth.set_index("enumerator_id")["primary_mode"].to_dict()
        sub_to_enum = dict(zip(df_sub["submission_id"], df_sub["enumerator_id"]))

        # Build feature table and score enumerators
        df_feat = build_feature_table(sub_path, vil_path)
        sc_v3 = score_enumerators(df_feat, scoring_version="v3")
        sc_noshrink = score_enumerators(df_feat, scoring_version="v3", no_shrinkage=True)

        rules = load_rules(Path("rules/rules.yaml"))
        rule_hits = run_rules(sub_path, vil_path, rules=rules)
        enum_rule_hits: Dict[str, Set[str]] = {e: set() for e in sc_v3["enumerator_id"]}
        for _, row in rule_hits.iterrows():
            u_id = row["unit_id"]
            e = sub_to_enum.get(u_id) if row["level"] == "submission" else "_".join(u_id.split("_")[:2])
            if e in enum_rule_hits:
                enum_rule_hits[e].add(row["rule_id"])
        rules_scores = np.array([len(enum_rule_hits[e]) for e in sc_v3["enumerator_id"]], dtype=float)

        enum_ids = list(sc_v3["enumerator_id"])
        n_interviews = sc_v3["n_interviews"].values
        is_fab = np.array([fab_map.get(e, 0.0) >= 0.10 for e in enum_ids], dtype=bool)
        p_modes = [mode_map.get(e) for e in enum_ids]

        rng = np.random.default_rng(12345 + seed)
        tiebreakers = rng.uniform(0.0, 1.0, size=len(enum_ids))

        methods = {
            "v3": sc_v3["risk_score"].values,
            "noshrink": sc_noshrink["risk_score"].values,
            "rules": rules_scores,
        }

        row_res: Dict[str, Any] = {
            "study": study,
            "config_id": cfg_id,
            "seed": seed,
            "day": day,
            "prevalence": prev,
            "workload_name": task.get("workload_name", "mixed"),
            "icc_name": icc,
            "share_name": task.get("share_name", "mixed"),
            "include_holdout": inc_holdout,
        }

        k = 4
        n_fab_total = int(np.sum(is_fab))

        modes_list = ALL_MODES if inc_holdout else ACTIVE_MODES

        for m_name, scores in methods.items():
            df_m = pd.DataFrame({
                "enumerator_id": enum_ids,
                "score": scores,
                "tiebreaker": tiebreakers,
                "is_fab": is_fab,
                "n_interviews": n_interviews,
                "mode": p_modes,
            })
            df_sorted = df_m.sort_values(by=["score", "tiebreaker"], ascending=[False, True])
            top_k = df_sorted.head(k)

            tp = int(top_k["is_fab"].sum())
            prec = tp / k
            rec = tp / n_fab_total if n_fab_total > 0 else 0.0
            sh_honest = int(((~top_k["is_fab"]) & (top_k["n_interviews"] < 15)).sum())
            ap_overall = compute_average_precision(scores, is_fab, tiebreakers)

            row_res[f"{m_name}_precision_k"] = prec
            row_res[f"{m_name}_recall_k"] = rec
            row_res[f"{m_name}_small_honest"] = sh_honest
            row_res[f"{m_name}_ap"] = ap_overall

            for mod in modes_list:
                mod_fabs = [e for e, f, m in zip(enum_ids, is_fab, p_modes) if f and m == mod]
                if mod_fabs:
                    mod_tp = int(top_k["enumerator_id"].isin(mod_fabs).sum())
                    row_res[f"{m_name}_recall_{mod}"] = mod_tp / len(mod_fabs)
                    row_res[f"{m_name}_ap_{mod}"] = compute_mode_average_precision(scores, is_fab, p_modes, mod, tiebreakers)
                else:
                    row_res[f"{m_name}_recall_{mod}"] = float("nan")
                    row_res[f"{m_name}_ap_{mod}"] = float("nan")

        return row_res
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def build_all_tasks() -> List[Dict[str, Any]]:
    """Assemble all task definitions across grid, holdout, and detection-time studies."""
    tasks = []
    # 1. 72 grid configs × 20 seeds (1000..1019)
    for cfg in build_grid_configs():
        for s in range(1000, 1020):
            t = dict(cfg)
            t.update({"study": "grid", "seed": s, "day": 10, "include_holdout": False})
            tasks.append(t)

    # 2. Held-out mode run: mixed workload, medium ICC, prevalence 0.10, 20 seeds (2000..2019)
    for s in range(2000, 2020):
        tasks.append({
            "study": "holdout",
            "config_id": 1000,
            "seed": s,
            "day": 10,
            "prevalence": 0.10,
            "workload_name": "mixed",
            "workload_range": [5, 60],
            "icc_name": "medium",
            "share_name": "mixed",
            "share_range": [0.30, 0.90],
            "include_holdout": True,
        })

    # 3. Detection-time run: mixed workload, medium ICC, prevalence 0.10, 20 seeds (3000..3019)
    for s in range(3000, 3020):
        for d in [2, 4, 6, 8, 10]:
            tasks.append({
                "study": "detection_time",
                "config_id": 2000,
                "seed": s,
                "day": d,
                "prevalence": 0.10,
                "workload_name": "mixed",
                "workload_range": [5, 60],
                "icc_name": "medium",
                "share_name": "mixed",
                "share_range": [0.30, 0.90],
                "include_holdout": False,
            })
    return tasks


def run_robustness_study(
    output_path: Path,
    n_workers: int = 4,
    batch_size: int = 50,
) -> None:
    """Run all study tasks resumably, saving results incrementally to results.parquet."""
    from multiprocessing import Pool

    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_tasks = build_all_tasks()

    done_keys: Set[Tuple[str, int, int, int]] = set()
    existing_rows: List[Dict[str, Any]] = []

    if output_path.exists():
        df_exist = pd.read_parquet(output_path)
        existing_rows = df_exist.to_dict(orient="records")
        for r in existing_rows:
            done_keys.add((str(r["study"]), int(r["config_id"]), int(r["seed"]), int(r["day"])))
        print(f"Loaded {len(done_keys)} previously completed tasks from {output_path}")

    pending_tasks = [
        t for t in all_tasks
        if (t["study"], t["config_id"], t["seed"], t["day"]) not in done_keys
    ]
    print(f"Total tasks: {len(all_tasks)}, Pending: {len(pending_tasks)}, Workers: {n_workers}")

    if not pending_tasks:
        print("All tasks already completed!")
        return

    start_time = time.time()
    completed_rows = list(existing_rows)

    with Pool(processes=n_workers) as pool:
        for i in range(0, len(pending_tasks), batch_size):
            batch = pending_tasks[i: i + batch_size]
            results = pool.map(process_single_task, batch)
            completed_rows.extend(results)

            df_save = pd.DataFrame(completed_rows)
            df_save.to_parquet(output_path, engine="pyarrow", index=False)

            elapsed = time.time() - start_time
            done_count = len(completed_rows) - len(existing_rows)
            rate = done_count / max(1.0, elapsed)
            remaining_s = (len(pending_tasks) - done_count) / max(0.01, rate)
            print(f"Progress: {len(completed_rows)}/{len(all_tasks)} tasks done. Rate: {rate:.1f} tasks/s. Est. remaining: {remaining_s/60:.1f} min.")

    total_time = time.time() - start_time
    print(f"Robustness study run completed in {total_time:.1f} s ({total_time/60:.2f} min).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run robustness study across configs and seeds.")
    parser.add_argument("--out", type=str, default="outputs/robustness/results.parquet", help="Output results parquet")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 4, help="Number of parallel worker processes")
    args = parser.parse_args()

    run_robustness_study(Path(args.out), n_workers=args.workers)


if __name__ == "__main__":
    main()
