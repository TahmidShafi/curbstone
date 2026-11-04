"""Evaluation script for Scoring acceptance checks (honest-only calibration).

Supports both Scoring v1 (seeds 0..19) and Scoring v2 (seeds 100..119).
"""

import argparse
import sys
from pathlib import Path
import shutil
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.features import build_feature_table
from engine.scoring import score_enumerators
from generator.run import run_generation

FEATURE_IDS = ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10"]


def run_acceptance_check(
    start_seed: int = 100,
    n_seeds: int = 20,
    scoring_version: str = "v2",
    empirical_null: bool = False,
) -> Tuple[pd.DataFrame, int]:
    """Run honest null calibration across held-out seeds."""
    eval_dir = Path("eval_acceptance_temp")
    eval_dir.mkdir(parents=True, exist_ok=True)

    pooled_p: Dict[str, List[float]] = {f: [] for f in FEATURE_IDS}
    rounds_flagged = 0

    for s in range(start_seed, start_seed + n_seeds):
        r_dir = eval_dir / f"seed_{s}"
        sub_path = run_generation(
            icc_level="medium",
            seed=s,
            out_dir=r_dir,
            round_num=1,
            no_fraud=True,
        )
        vil_path = r_dir / "reference" / "villages.parquet"
        df_feat = build_feature_table(sub_path, vil_path)
        scores = score_enumerators(
            df_feat,
            q=0.10,
            empirical_null=empirical_null,
            scoring_version=scoring_version,
        )

        n_fl = int(scores["flagged"].sum())
        if n_fl >= 1:
            rounds_flagged += 1

        for f in FEATURE_IDS:
            col = f"{f}_p"
            pooled_p[f].extend(scores[col].dropna().tolist())

    shutil.rmtree(eval_dir, ignore_errors=True)

    rows = []
    for f in FEATURE_IDS:
        arr = np.array(pooled_p[f])
        n_tests = len(arr)
        p05 = float(np.mean(arr < 0.05)) if n_tests > 0 else 0.0
        p01 = float(np.mean(arr < 0.01)) if n_tests > 0 else 0.0
        p001 = float(np.mean(arr < 0.001)) if n_tests > 0 else 0.0
        pass_05 = p05 <= 0.08
        pass_01 = p01 <= 0.02
        pass_001 = p001 <= 0.004
        all_passed = pass_05 and pass_01 and pass_001
        rows.append({
            "Feature": f.upper(),
            "Non-NaN Tests": n_tests,
            "Share p < 0.05": p05,
            "Share p < 0.01": p01,
            "Share p < 0.001": p001,
            "Status": "PASS" if all_passed else "FAIL",
        })

    return pd.DataFrame(rows), rounds_flagged


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate scoring calibration on honest-only seeds.")
    parser.add_argument("--v2", action="store_true", default=True, help="Evaluate Scoring v2 (default: True)")
    parser.add_argument("--v1", action="store_true", help="Evaluate Scoring v1")
    parser.add_argument("--seeds-start", type=int, default=None, help="Start seed (default: 100 for v2, 0 for v1)")
    parser.add_argument("--n-seeds", type=int, default=20, help="Number of seeds (default: 20)")
    args = parser.parse_args()

    scoring_ver = "v1" if args.v1 else "v2"
    start_seed = args.seeds_start if args.seeds_start is not None else (0 if scoring_ver == "v1" else 100)

    print("=" * 80)
    print(f"ACCEPTANCE CHECK: Scoring {scoring_ver.upper()} (Seeds {start_seed}..{start_seed + args.n_seeds - 1}, honest-only)")
    print("=" * 80)

    df_res, rounds_fl = run_acceptance_check(
        start_seed=start_seed,
        n_seeds=args.n_seeds,
        scoring_version=scoring_ver,
    )

    print(df_res.to_string(index=False, formatters={
        "Share p < 0.05": "{:.4f}".format,
        "Share p < 0.01": "{:.4f}".format,
        "Share p < 0.001": "{:.4f}".format,
    }))
    print(f"\nRounds with >= 1 BH flag: {rounds_fl} / {args.n_seeds} (Target <= 4)")
    decision = "ACCEPT" if rounds_fl <= 4 and (df_res["Status"] == "PASS").all() else "REJECT"
    print(f"Decision: {decision}")


if __name__ == "__main__":
    main()
