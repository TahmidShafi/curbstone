"""CLI runner for curbstone synthetic survey generation with fraud injection."""

import argparse
from pathlib import Path
from typing import Any, Dict, Optional
import numpy as np
import yaml

from generator.geography import build_geography
from generator.enumerators import build_enumerators
from generator.interviews import generate_submissions_for_round


def load_config(config_path: Path) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_generation(
    icc_level: str,
    seed: int,
    out_dir: Path,
    round_num: int = 1,
    config_path: Optional[Path] = None,
    prevalence: Optional[float] = None,
    no_fraud: bool = False,
    truth_dir: Optional[Path] = None,
) -> Path:
    """Run survey generation with separate honest and fraud random streams (R2)."""
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config" / "params.yaml"

    config = load_config(config_path)

    # R2: Stream separation via SeedSequence
    seed_seq = np.random.SeedSequence(seed)
    honest_seq, fraud_seq = seed_seq.spawn(2)
    honest_rng = np.random.default_rng(honest_seq)
    fraud_rng = np.random.default_rng(fraud_seq)

    enable_fraud = not no_fraud
    if prevalence is not None and prevalence <= 0.0:
        enable_fraud = False

    # 1. Build geography
    geography = build_geography(config=config, rng=honest_rng)

    # 2. Build enumerators & assign villages
    village_ids = list(geography.villages.keys())
    enumerators = build_enumerators(config=config, village_ids=village_ids, rng=honest_rng)

    # 3. Generate submissions (and labels if fraud is enabled)
    df, meta = generate_submissions_for_round(
        config=config,
        geography=geography,
        enumerators=enumerators,
        icc_level=icc_level,
        round_num=round_num,
        rng=honest_rng,
        fraud_rng=fraud_rng,
        prevalence=prevalence,
        enable_fraud=enable_fraud,
    )

    # 4. Save survey submissions to Parquet partitioned by round
    round_dir = out_dir / f"round={round_num}"
    round_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = round_dir / "interviews.parquet"
    df.to_parquet(parquet_path, engine="pyarrow", index=False)

    # 5. Save ground-truth labels if fraud was active (never into data/)
    if enable_fraud and "labels_submission" in meta:
        if truth_dir is None:
            truth_dir = Path("truth")
        round_truth_dir = truth_dir / f"round={round_num}"
        round_truth_dir.mkdir(parents=True, exist_ok=True)
        meta["labels_submission"].to_parquet(
            round_truth_dir / "labels_submission.parquet",
            engine="pyarrow",
            index=False,
        )
        meta["labels_enumerator"].to_parquet(
            round_truth_dir / "labels_enumerator.parquet",
            engine="pyarrow",
            index=False,
        )

    # Log any frame expansion
    expansions = meta.get("frame_expansion_log", [])
    if expansions:
        print(f"Logged {len(expansions)} village frame expansions:")
        for entry in expansions:
            print(f"  Village {entry['village_id']}: {entry['original_size']} -> {entry['new_size']}")

    n_fab = len(meta.get("fabricator_profiles", {}))
    print(f"Generated {len(df)} submissions for Round {round_num} (ICC: {icc_level}, seed: {seed}, fabricators: {n_fab})")
    print(f"Output saved to: {parquet_path}")
    return parquet_path


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic survey data with fraud injection.")
    parser.add_argument(
        "--icc",
        type=str,
        choices=["low", "medium", "high"],
        default="medium",
        help="Village wealth effect ICC level",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random generator seed",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=1,
        help="Survey round number",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="data",
        help="Output directory path",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to params.yaml",
    )
    parser.add_argument(
        "--prevalence",
        type=float,
        default=None,
        help="Fraction of enumerators who fabricate interviews (default: from config)",
    )
    parser.add_argument(
        "--no-fraud",
        action="store_true",
        help="Disable fraud injection completely",
    )

    args = parser.parse_args()
    cfg_path = Path(args.config) if args.config else None
    out_path = Path(args.out)

    run_generation(
        icc_level=args.icc,
        seed=args.seed,
        out_dir=out_path,
        round_num=args.round,
        config_path=cfg_path,
        prevalence=args.prevalence,
        no_fraud=args.no_fraud,
    )


if __name__ == "__main__":
    main()
