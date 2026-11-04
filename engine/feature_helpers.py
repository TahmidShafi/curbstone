"""Mathematical and statistical helper routines for peer-relative feature extraction."""

import math
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd


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
        return float("nan"), float("nan")
    weights = [1.0 / (s ** 2) for _, s in cells]
    diffs = [d for d, _ in cells]
    sds = [s for _, s in cells]
    val = float(np.average(diffs, weights=weights))
    null_sd = float(np.average(sds, weights=weights))
    return val, null_sd


def compute_shrunk_peer_rate(k_peer: float, n_peer: float, p_s: float, M: float = 50.0) -> float:
    """Shrink cell peer rate toward survey rate: (k_peer + M * p_s) / (n_peer + M)."""
    return float((k_peer + M * p_s) / max(1.0, n_peer + M))


def compute_f1_duration_resid(df: pd.DataFrame, enum_ids: List[str]) -> Tuple[Dict[str, Tuple[float, float, int]], float]:
    log_dur = np.log(df["duration_min"].clip(lower=1.0))
    if len(df) < 2 or df["hh_size"].nunique() < 2:
        slope, intercept = 0.0, float(np.mean(log_dur)) if len(df) > 0 else 0.0
    else:
        slope, intercept = np.polyfit(df["hh_size"], log_dur, 1)
    df_temp = df[["enumerator_id", "village_id"]].copy()
    resids = log_dur - (intercept + slope * df["hh_size"])
    df_temp["resid"] = resids
    sigma_r = float(1.4826 * np.median(np.abs(resids - np.median(resids)))) if len(resids) > 0 else 0.25

    res: Dict[str, Tuple[float, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df_temp[df_temp["enumerator_id"] == e_id]
        val = float(e_rows["resid"].median()) if len(e_rows) > 0 else 0.0
        weights, peer_meds = [], []
        for vid, ev_rows in e_rows.groupby("village_id"):
            p_rows = df_temp[(df_temp["village_id"] == vid) & (df_temp["enumerator_id"] != e_id)]
            if len(p_rows) > 0:
                weights.append(len(ev_rows))
                peer_meds.append(float(p_rows["resid"].median()))
        peer_val = float(np.average(peer_meds, weights=weights)) if weights else val
        res[e_id] = (round(val, 4), round(peer_val, 4), len(e_rows))
    return res, sigma_r


def compute_f2_throughput(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[float, float, int]]:
    start_dt = pd.to_datetime(df["start_time"], utc=True, format="ISO8601")
    dates = (start_dt + pd.Timedelta(hours=6)).dt.date
    df_temp = pd.DataFrame({"enumerator_id": df["enumerator_id"], "work_date": dates})
    daily = df_temp.groupby(["enumerator_id", "work_date"]).size().reset_index(name="counts")
    means = daily.groupby("enumerator_id")["counts"].mean().to_dict()
    counts = df_temp.groupby("enumerator_id").size().to_dict()

    res: Dict[str, Tuple[float, float, int]] = {}
    for e_id in enum_ids:
        val = means.get(e_id, 0.0)
        others = [means[o] for o in means if o != e_id]
        peer_val = float(np.median(others)) if others else val
        res[e_id] = (round(val, 4), round(peer_val, 4), counts.get(e_id, 0))
    return res

