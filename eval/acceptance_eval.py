"""Evaluation script for Amendment 2 acceptance checks (honest-only, seeds 0..19)."""

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


def run_acceptance_comparison(n_seeds: int = 20) -> Tuple[pd.DataFrame, int, pd.DataFrame, int]:
    """Run honest null calibration across seeds 0..n_seeds-1 for both base and fallback."""
    eval_dir = Path("eval_acceptance_temp")
    eval_dir.mkdir(parents=True, exist_ok=True)

    pooled_base: Dict[str, List[float]] = {f: [] for f in FEATURE_IDS}
    pooled_fb: Dict[str, List[float]] = {f: [] for f in FEATURE_IDS}
    rounds_flagged_base = 0
    rounds_flagged_fb = 0

    for s in range(n_seeds):
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

        scores_base = score_enumerators(df_feat, q=0.10, empirical_null=False)
        scores_fb = score_enumerators(df_feat, q=0.10, empirical_null=True)

        if int(scores_base["flagged"].sum()) >= 1:
            rounds_flagged_base += 1
        if int(scores_fb["flagged"].sum()) >= 1:
            rounds_flagged_fb += 1

        for f in FEATURE_IDS:
            col = f"{f}_p"
            pooled_base[f].extend(scores_base[col].dropna().tolist())
            pooled_fb[f].extend(scores_fb[col].dropna().tolist())

    shutil.rmtree(eval_dir, ignore_errors=True)

    def summarize(pooled: Dict[str, List[float]]) -> pd.DataFrame:
        rows = []
        for f in FEATURE_IDS:
            arr = np.array(pooled[f])
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
        return pd.DataFrame(rows)

    return summarize(pooled_base), rounds_flagged_base, summarize(pooled_fb), rounds_flagged_fb


def main() -> None:
    df_base, rounds_base, df_fb, rounds_fb = run_acceptance_comparison(n_seeds=20)

    print("=" * 80)
    print("ACCEPTANCE CHECK: Amendment 2 Baseline (empirical_null=False)")
    print("=" * 80)
    print(df_base.to_string(index=False, formatters={
        "Share p < 0.05": "{:.4f}".format,
        "Share p < 0.01": "{:.4f}".format,
        "Share p < 0.001": "{:.4f}".format,
    }))
    print(f"\nRounds with >= 1 BH flag: {rounds_base} / 20 (Target <= 4)")
    print(f"Decision: {'ACCEPT' if rounds_base <= 4 and (df_base['Status'] == 'PASS').all() else 'REJECT'}")

    print("\n" + "=" * 80)
    print("ACCEPTANCE CHECK: Amendment 2 + Empirical-Null Fallback (empirical_null=True)")
    print("=" * 80)
    print(df_fb.to_string(index=False, formatters={
        "Share p < 0.05": "{:.4f}".format,
        "Share p < 0.01": "{:.4f}".format,
        "Share p < 0.001": "{:.4f}".format,
    }))
    print(f"\nRounds with >= 1 BH flag: {rounds_fb} / 20 (Target <= 4)")
    print(f"Decision: {'ACCEPT' if rounds_fb <= 4 and (df_fb['Status'] == 'PASS').all() else 'REJECT'}")


if __name__ == "__main__":
    main()
