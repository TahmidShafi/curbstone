"""CLI entry point to execute enumerator scoring, shrinkage, and FDR decisions."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from engine.scoring import score_enumerators


def execute_scoring_pipeline(
    features_path: Path,
    out_path: Path,
    no_shrinkage: bool = False,
    no_fdr: bool = False,
    q: float = 0.10,
    scoring_version: str = "v1",
) -> Path:
    """Execute scoring pipeline on feature table and write scores to parquet."""
    if not features_path.is_file():
        raise FileNotFoundError(f"Features file not found at: {features_path}")

    df_scores = score_enumerators(
        features=features_path,
        no_shrinkage=no_shrinkage,
        no_fdr=no_fdr,
        q=q,
        scoring_version=scoring_version,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_scores.to_parquet(out_path, engine="pyarrow", index=False)

    flagged_count = int(df_scores["flagged"].sum())
    print(f"Scored {len(df_scores)} enumerators. Flagged: {flagged_count}")
    print(f"Output saved to: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Score enumerators with shrinkage and FDR control.")
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("outputs/enumerator_features.parquet"),
        help="Path to enumerator features parquet file",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/scores.parquet"),
        help="Output path for scores parquet",
    )
    parser.add_argument(
        "--no-shrinkage",
        action="store_true",
        help="Disable empirical Bayes shrinkage (use plain binomial and robust z without n-adjustment)",
    )
    parser.add_argument(
        "--no-fdr",
        action="store_true",
        help="Disable Benjamini-Hochberg FDR control (flag if p_e < 0.05)",
    )
    parser.add_argument(
        "--q",
        type=float,
        default=0.10,
        help="FDR target rate q (default 0.10)",
    )
    parser.add_argument(
        "--v2",
        action="store_true",
        help="Use scoring v2 algorithms (post-hoc ranking and calibration)",
    )
    parser.add_argument(
        "--scoring-version",
        choices=["v1", "v2"],
        default="v1",
        help="Scoring algorithm version (default: v1)",
    )
    args = parser.parse_args()

    version = "v2" if (args.v2 or args.scoring_version == "v2") else "v1"

    execute_scoring_pipeline(
        features_path=args.features,
        out_path=args.out,
        no_shrinkage=args.no_shrinkage,
        no_fdr=args.no_fdr,
        q=args.q,
        scoring_version=version,
    )


if __name__ == "__main__":
    main()
