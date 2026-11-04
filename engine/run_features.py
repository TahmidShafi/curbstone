"""CLI entry point to execute peer-relative feature extraction for enumerators."""

import argparse
from pathlib import Path
from engine.features import build_feature_table


def execute_feature_pipeline(
    data_dir: Path,
    out_path: Path,
    round_num: int = 1,
    seed: int = 12345,
) -> Path:
    """Execute feature extraction pipeline and save output parquet."""
    sub_candidate = data_dir / f"round={round_num}" / "interviews.parquet"
    if not sub_candidate.is_file():
        sub_candidate = data_dir / "interviews.parquet"
        if not sub_candidate.is_file():
            raise FileNotFoundError(f"Could not find interviews.parquet in {data_dir}")

    vil_candidate = data_dir / "reference" / "villages.parquet"
    if not vil_candidate.is_file():
        vil_candidate = data_dir / "villages.parquet"

    df_features = build_feature_table(
        submissions=sub_candidate,
        villages=vil_candidate if vil_candidate.is_file() else None,
        seed=seed,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_features.to_parquet(out_path, engine="pyarrow", index=False)

    print(f"Extracted features for {len(df_features)} enumerators from {sub_candidate}")
    print(f"Output saved to: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Extract peer-relative features for enumerators.")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data"),
        help="Path to data directory containing round=* and reference/",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/enumerator_features.parquet"),
        help="Path to save output features Parquet",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=1,
        help="Round number to evaluate",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=12345,
        help="Engine seed for stochastic resampling nulls",
    )

    args = parser.parse_args()
    execute_feature_pipeline(
        data_dir=args.data,
        out_path=args.out,
        round_num=args.round,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()

