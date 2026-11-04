"""Helper script to check village frame enlargement across seeds and workload profiles."""

import copy
from pathlib import Path
import numpy as np
import yaml

from generator.geography import build_geography
from generator.enumerators import build_enumerators
from generator.interviews import generate_submissions_for_round


def check_profile(config_path: Path, seed: int = 42, workload: list = None):
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if workload is not None:
        cfg["enumerators"]["workload"] = workload

    rng = np.random.default_rng(seed)
    geo = build_geography(cfg, rng)
    enums = build_enumerators(cfg, list(geo.villages.keys()), rng)
    df, meta = generate_submissions_for_round(cfg, geo, enums, "medium", 1, rng)

    log = meta.get("frame_expansion_log", [])
    workload_str = str(cfg["enumerators"]["workload"])
    print(f"Seed {seed} (workload {workload_str}): {len(log)} villages enlarged.")
    if log:
        for entry in log:
            diff = entry["new_size"] - entry["original_size"]
            print(f"  Village {entry['village_id']}: {entry['original_size']} -> {entry['new_size']} (+{diff})")
    else:
        print("  Log is empty (no enlargement needed).")
    return len(log), log


if __name__ == "__main__":
    cfg_path = Path(__file__).resolve().parent.parent / "config" / "params.yaml"
    print("Checking default workload [5, 60]:")
    check_profile(cfg_path, seed=42)
    print("\nChecking high workload [40, 60]:")
    check_profile(cfg_path, seed=42, workload=[40, 60])

