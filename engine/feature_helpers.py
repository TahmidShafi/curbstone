"""Mathematical and statistical helper routines for peer-relative feature extraction."""

import math
from typing import List, Tuple
import numpy as np


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two lat/lon coordinates."""
    r_earth = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0) ** 2
    return 2.0 * r_earth * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def median_nn_distance(lats: np.ndarray, lons: np.ndarray) -> float:
    """Median nearest-neighbour haversine distance among an array of coordinates."""
    n = len(lats)
    if n <= 1:
        return 0.0
    nn_dists = []
    for i in range(n):
        min_d = float("inf")
        for j in range(n):
            if i != j:
                d = haversine_m(lats[i], lons[i], lats[j], lons[j])
                if d < min_d:
                    min_d = d
        nn_dists.append(min_d)
    return float(np.median(nn_dists))


def count_near_dups(records: List[Tuple]) -> int:
    """Count number of records that differ in <= 1 field from another record in the set."""
    n = len(records)
    if n <= 1:
        return 0
    is_nd = [False] * n
    for i in range(n):
        r1 = records[i]
        for j in range(i + 1, n):
            if sum(1 for a, b in zip(r1, records[j]) if a != b) <= 1:
                is_nd[i] = is_nd[j] = True
    return sum(is_nd)


def simulate_log_variance_null(
    p_vals: np.ndarray, n_ev: int, rng: np.random.Generator, B: int = 50
) -> Tuple[float, float]:
    """Workload-matched null for 1D variance: sample n_ev without replacement B times."""
    n_peer = len(p_vals)
    null_vals = []
    for _ in range(B):
        idx = rng.choice(n_peer, size=n_ev, replace=False)
        mask = np.zeros(n_peer, dtype=bool)
        mask[idx] = True
        s_var = float(np.var(p_vals[mask], ddof=1)) if np.sum(mask) > 1 else 0.0
        r_var = float(np.var(p_vals[~mask], ddof=1)) if np.sum(~mask) > 1 else 0.0
        null_vals.append(math.log((s_var + 0.01) / (r_var + 0.01)))
    return float(np.mean(null_vals)), float(np.std(null_vals, ddof=1))


def simulate_asset_variance_null(
    p_assets: np.ndarray, n_ev: int, rng: np.random.Generator, B: int = 50
) -> Tuple[float, float]:
    """Workload-matched null for multi-asset variance across columns."""
    n_peer = len(p_assets)
    null_vals = []
    for _ in range(B):
        idx = rng.choice(n_peer, size=n_ev, replace=False)
        mask = np.zeros(n_peer, dtype=bool)
        mask[idx] = True
        ratios = []
        for col_idx in range(p_assets.shape[1]):
            col = p_assets[:, col_idx]
            s_c = col[mask]
            s_v = s_c[s_c != -8]
            s_var = float(np.var(s_v, ddof=1)) if len(s_v) > 1 else 0.0
            r_c = col[~mask]
            r_v = r_c[r_c != -8]
            r_var = float(np.var(r_v, ddof=1)) if len(r_v) > 1 else 0.0
            ratios.append(math.log((s_var + 0.01) / (r_var + 0.01)))
        null_vals.append(float(np.mean(ratios)))
    return float(np.mean(null_vals)), float(np.std(null_vals, ddof=1))


def simulate_gps_null(
    p_lats: np.ndarray, p_lons: np.ndarray, n_ev: int, rng: np.random.Generator, B: int = 50
) -> Tuple[float, float]:
    """Workload-matched null for GPS spread: sample n_ev coordinates without replacement."""
    n_peer = len(p_lats)
    null_vals = []
    for _ in range(B):
        idx = rng.choice(n_peer, size=n_ev, replace=False)
        d = median_nn_distance(p_lats[idx], p_lons[idx])
        null_vals.append(math.log(d + 1.0))
    return float(np.mean(null_vals)), float(np.std(null_vals, ddof=1))


def aggregate_cell_nulls(cells: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Aggregate (diff, sd) pairs across cells using inverse-variance weighting."""
    if not cells:
        return 0.0, float("nan")
    weights = [1.0 / (s ** 2) for _, s in cells]
    diffs = [d for d, _ in cells]
    sds = [s for _, s in cells]
    val = float(np.average(diffs, weights=weights))
    null_sd = float(np.average(sds, weights=weights))
    return val, null_sd
