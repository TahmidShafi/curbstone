"""Common configurations, definitions, and metrics for the robustness study."""

from datetime import date
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

WORKING_DAYS = [
    date(2026, 11, 1),
    date(2026, 11, 2),
    date(2026, 11, 3),
    date(2026, 11, 4),
    date(2026, 11, 5),
    date(2026, 11, 8),
    date(2026, 11, 9),
    date(2026, 11, 10),
    date(2026, 11, 11),
    date(2026, 11, 12),
]

ACTIVE_MODES = ["copy_paste", "straight_lining", "rushed", "invented_gps", "too_average"]
ALL_MODES = ACTIVE_MODES + ["partial_section"]

WORKLOAD_MAP = {
    "low": [5, 15],
    "mixed": [5, 60],
    "high": [40, 60],
}

SHARE_MAP = {
    "low": [0.20, 0.40],
    "high": [0.60, 1.00],
}


def build_grid_configs() -> List[Dict[str, Any]]:
    """Build full factorial 72-configuration grid (dgp §7 & §13)."""
    prevalences = [0.02, 0.05, 0.10, 0.20]
    workloads = ["low", "mixed", "high"]
    iccs = ["low", "medium", "high"]
    shares = ["low", "high"]

    configs = []
    cfg_id = 0
    for prev in prevalences:
        for wl in workloads:
            for icc in iccs:
                for sh in shares:
                    configs.append({
                        "config_id": cfg_id,
                        "prevalence": prev,
                        "workload_name": wl,
                        "workload_range": WORKLOAD_MAP[wl],
                        "icc_name": icc,
                        "share_name": sh,
                        "share_range": SHARE_MAP[sh],
                    })
                    cfg_id += 1
    return configs


def compute_average_precision(scores: np.ndarray, is_fab: np.ndarray, tiebreakers: np.ndarray) -> float:
    """Compute average precision (PR-AUC) from risk score ranking."""
    n_fab = int(np.sum(is_fab))
    if n_fab == 0:
        return 0.0

    df_rank = pd.DataFrame({"score": scores, "tiebreaker": tiebreakers, "is_fab": is_fab})
    df_rank = df_rank.sort_values(by=["score", "tiebreaker"], ascending=[False, True])

    y_sorted = df_rank["is_fab"].values.astype(int)
    cum_tp = np.cumsum(y_sorted)
    ranks = np.arange(1, len(y_sorted) + 1)
    precisions = cum_tp / ranks
    ap = float(np.sum(precisions * y_sorted) / n_fab)
    return ap


def compute_mode_average_precision(
    scores: np.ndarray,
    is_fab: np.ndarray,
    primary_modes: List[Optional[str]],
    target_mode: str,
    tiebreakers: np.ndarray,
) -> float:
    """Compute one-vs-honest average precision for a specific fraud mode."""
    target_mask = np.array([
        (not fab) or (mode == target_mode)
        for fab, mode in zip(is_fab, primary_modes)
    ])
    sub_scores = scores[target_mask]
    sub_is_fab = np.array([
        fab and (mode == target_mode)
        for fab, mode in zip(is_fab[target_mask], np.array(primary_modes)[target_mask])
    ])
    sub_tie = tiebreakers[target_mask]

    if np.sum(sub_is_fab) == 0:
        return float("nan")
    return compute_average_precision(sub_scores, sub_is_fab, sub_tie)

