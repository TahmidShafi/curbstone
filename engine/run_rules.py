"""CLI entry point to execute rule engine against survey submissions and reference tables."""

import argparse
from pathlib import Path
import pandas as pd

from engine.rules import load_rules, run_rules


def execute_rule_pipeline(
    data_dir: Path,
    out_path: Path,
    rules_path: Path,
    round_num: int = 1,
) -> Path:
    """Execute rule pipeline for given round and save results."""
    # Locate submissions parquet
    sub_candidate = data_dir / f"round={round_num}" / "interviews.parquet"
    if not sub_candidate.is_file():
        # Fallback to direct path or data_dir / "interviews.parquet"
        sub_candidate = data_dir / "interviews.parquet"
        if not sub_candidate.is_file():
            raise FileNotFoundError(
                f"Could not find interviews.parquet in {data_dir / f'round={round_num}'} or {data_dir}"
            )

    # Locate reference villages parquet
    vil_candidate = data_dir / "reference" / "villages.parquet"
    if not vil_candidate.is_file():
        vil_candidate = data_dir / "villages.parquet"
        if not vil_candidate.is_file():
            raise FileNotFoundError(
                f"Could not find villages.parquet in {data_dir / 'reference'} or {data_dir}"
            )

    rules = load_rules(rules_path)
    hits_df = run_rules(
        submissions=sub_candidate,
        villages=vil_candidate,
        rules=rules,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    hits_df.to_parquet(out_path, engine="pyarrow", index=False)

    print(f"Executed {len(rules)} rules on {sub_candidate}")
    print(f"Total rule hits detected: {len(hits_df)}")
    print(f"Output saved to: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Run DQA rules on survey data.")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data"),
        help="Path to data directory containing round=* and reference/",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/rule_hits.parquet"),
        help="Path to save output rule hits Parquet",
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=Path("rules/rules.yaml"),
        help="Path to rules YAML configuration",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=1,
        help="Round number to evaluate",
    )

    args = parser.parse_args()
    execute_rule_pipeline(
        data_dir=args.data,
        out_path=args.out,
        rules_path=args.rules,
        round_num=args.round,
    )


if __name__ == "__main__":
    main()

