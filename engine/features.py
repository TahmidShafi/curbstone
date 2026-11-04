"""Enumerator-level peer-relative feature extraction (dgp-aligned)."""

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
import yaml

from engine.feature_helpers import (
    aggregate_cell_nulls,
    count_near_dups,
    median_nn_distance,
    simulate_asset_variance_null,
    simulate_gps_null,
    simulate_log_variance_null,
)

ASSET_COLS = ["asset_mobile", "asset_tv", "asset_internet", "asset_radio", "asset_computer"]


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


def compute_f3_near_dup(df: pd.DataFrame, enum_ids: List[str], rng: np.random.Generator, B: int = 50) -> Dict[str, Tuple[int, float, int, bool]]:
    recs = [
        (row["hh_size"], row["head_age"], tuple(row["roster_ages"].tolist() if hasattr(row["roster_ages"], "tolist") else row["roster_ages"]), *[row[a] for a in ASSET_COLS])
        for _, row in df.iterrows()
    ]
    df_temp = df[["enumerator_id", "village_id"]].copy()
    df_temp["rec"] = recs

    res: Dict[str, Tuple[int, float, int, bool]] = {}
    for e_id in enum_ids:
        e_rows = df_temp[df_temp["enumerator_id"] == e_id]
        k_sum, k_exp_sum, null_limited = 0, 0.0, False
        for vid, ev_rows in e_rows.groupby("village_id"):
            n_ev = len(ev_rows)
            k_sum += count_near_dups(ev_rows["rec"].tolist())
            p_rows = df_temp[(df_temp["village_id"] == vid) & (df_temp["enumerator_id"] != e_id)]
            n_peer, p_recs = len(p_rows), p_rows["rec"].tolist()
            if n_peer < n_ev:
                null_limited = True
                k_exp_sum += count_near_dups(p_recs)
            else:
                sims = [count_near_dups([p_recs[i] for i in rng.choice(n_peer, size=n_ev, replace=False)]) for _ in range(B)]
                k_exp_sum += float(np.mean(sims))
        res[e_id] = (k_sum, round(k_exp_sum, 4), len(e_rows), null_limited)
    return res


def compute_f4_straight_line(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[int, float, int]]:
    valid_mask = ~(df[ASSET_COLS] == -8).any(axis=1)
    df_v = df[valid_mask].copy()
    df_v["straight"] = (df_v[ASSET_COLS].nunique(axis=1) == 1).astype(int)

    res: Dict[str, Tuple[int, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df_v[df_v["enumerator_id"] == e_id]
        k_sum = int(e_rows["straight"].sum()) if len(e_rows) > 0 else 0
        k_exp_sum = 0.0
        for vid, ev_rows in e_rows.groupby("village_id"):
            p_rows = df_v[(df_v["village_id"] == vid) & (df_v["enumerator_id"] != e_id)]
            rate = float(p_rows["straight"].mean()) if len(p_rows) > 0 else 0.0
            k_exp_sum += len(ev_rows) * rate
        res[e_id] = (k_sum, round(k_exp_sum, 4), len(e_rows))
    return res


def compute_f5_asset_dispersion(
    df: pd.DataFrame, enum_ids: List[str], rng: Optional[np.random.Generator] = None, B: int = 50
) -> Dict[str, Tuple[float, float, float, int]]:
    if rng is None:
        rng = np.random.default_rng(12345)
    res: Dict[str, Tuple[float, float, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df[df["enumerator_id"] == e_id]
        cells = []
        for vid, ev_rows in e_rows.groupby("village_id"):
            n_ev = len(ev_rows)
            if n_ev < 3:
                continue
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            if len(p_rows) < n_ev + 2:
                continue
            ratios = []
            for a in ASSET_COLS:
                ev_a, pv_a = ev_rows[ev_rows[a] != -8][a], p_rows[p_rows[a] != -8][a]
                ve = float(ev_a.var(ddof=1)) if len(ev_a) > 1 else 0.0
                vp = float(pv_a.var(ddof=1)) if len(pv_a) > 1 else 0.0
                ratios.append(math.log((ve + 0.01) / (vp + 0.01)))
            obs = float(np.mean(ratios))
            m_null, s_null = simulate_asset_variance_null(p_rows[ASSET_COLS].values, n_ev, rng=rng, B=B)
            cells.append((obs - m_null, max(s_null, 0.05)))
        val, null_sd = aggregate_cell_nulls(cells)
        res[e_id] = (round(val, 4), 0.0, round(null_sd, 4) if not math.isnan(null_sd) else float("nan"), len(e_rows))
    return res


def compute_f6_hhsize_dispersion(
    df: pd.DataFrame, enum_ids: List[str], rng: Optional[np.random.Generator] = None, B: int = 50
) -> Dict[str, Tuple[float, float, float, int]]:
    if rng is None:
        rng = np.random.default_rng(12345)
    res: Dict[str, Tuple[float, float, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df[df["enumerator_id"] == e_id]
        cells = []
        for vid, ev_rows in e_rows.groupby("village_id"):
            n_ev = len(ev_rows)
            if n_ev < 3:
                continue
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            if len(p_rows) < n_ev + 2:
                continue
            ve = float(ev_rows["hh_size"].var(ddof=1)) if len(ev_rows) > 1 else 0.0
            vp = float(p_rows["hh_size"].var(ddof=1)) if len(p_rows) > 1 else 0.0
            obs = math.log((ve + 0.01) / (vp + 0.01))
            m_null, s_null = simulate_log_variance_null(p_rows["hh_size"].values, n_ev, rng=rng, B=B)
            cells.append((obs - m_null, max(s_null, 0.05)))
        val, null_sd = aggregate_cell_nulls(cells)
        res[e_id] = (round(val, 4), 0.0, round(null_sd, 4) if not math.isnan(null_sd) else float("nan"), len(e_rows))
    return res


def compute_f7_gps_spread(
    df: pd.DataFrame, enum_ids: List[str], rng: Optional[np.random.Generator] = None, B: int = 50
) -> Dict[str, Tuple[float, float, float, int]]:
    if rng is None:
        rng = np.random.default_rng(12345)
    res: Dict[str, Tuple[float, float, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df[df["enumerator_id"] == e_id]
        cells = []
        for vid, ev_rows in e_rows.groupby("village_id"):
            n_ev = len(ev_rows)
            if n_ev < 3:
                continue
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            n_peer = len(p_rows)
            if n_peer < 3:
                continue
            obs_nn = median_nn_distance(ev_rows["gps_lat"].values, ev_rows["gps_lon"].values)
            p_lats, p_lons = p_rows["gps_lat"].values, p_rows["gps_lon"].values
            if n_peer >= n_ev:
                m_null, s_null = simulate_gps_null(p_lats, p_lons, n_ev, rng=rng, B=B)
                s_cell = max(s_null, 0.05)
            else:
                m_null = math.log(median_nn_distance(p_lats, p_lons) * math.sqrt(n_peer / n_ev) + 1.0)
                s_cell = 0.20
            cells.append((math.log(obs_nn + 1.0) - m_null, s_cell))
        val, null_sd = aggregate_cell_nulls(cells)
        res[e_id] = (round(val, 4), 0.0, round(null_sd, 4) if not math.isnan(null_sd) else float("nan"), len(e_rows))
    return res


def compute_f8_age_heaping(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[int, float, int]]:
    res: Dict[str, Tuple[int, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df[df["enumerator_id"] == e_id]
        k_sum, n_sum, k_exp_sum = 0, 0, 0.0
        for vid, ev_rows in e_rows.groupby("village_id"):
            ev_ages = [age for roster in ev_rows["roster_ages"] for age in roster if age >= 20]
            k_sum += sum(1 for a in ev_ages if a % 5 == 0)
            n_sum += len(ev_ages)
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            p_ages = [age for roster in p_rows["roster_ages"] for age in roster if age >= 20]
            p_rate = (sum(1 for a in p_ages if a % 5 == 0) / len(p_ages)) if len(p_ages) > 0 else 0.20
            k_exp_sum += len(ev_ages) * p_rate
        res[e_id] = (k_sum, round(k_exp_sum, 4), n_sum)
    return res


def compute_f9_nonresponse(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[int, float, int]]:
    res: Dict[str, Tuple[int, float, int]] = {}
    for e_id in enum_ids:
        e_rows = df[df["enumerator_id"] == e_id]
        k_sum = int((e_rows[ASSET_COLS] == -8).sum().sum())
        n_sum = len(e_rows) * len(ASSET_COLS)
        k_exp_sum = 0.0
        for vid, ev_rows in e_rows.groupby("village_id"):
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            p_rate = float((p_rows[ASSET_COLS] == -8).sum().sum()) / (len(p_rows) * len(ASSET_COLS)) if len(p_rows) > 0 else 0.01
            k_exp_sum += len(ev_rows) * len(ASSET_COLS) * p_rate
        res[e_id] = (k_sum, round(k_exp_sum, 4), n_sum)
    return res


def compute_f10_dur_size_coupling(df: pd.DataFrame, enum_ids: List[str]) -> Dict[str, Tuple[float, float, int]]:
    corrs = {}
    counts = {}
    for e_id in enum_ids:
        e_rows = df[df["enumerator_id"] == e_id]
        counts[e_id] = len(e_rows)
        if len(e_rows) >= 5 and e_rows["hh_size"].nunique() > 1 and e_rows["duration_min"].nunique() > 1:
            r, _ = spearmanr(e_rows["duration_min"], e_rows["hh_size"])
            corrs[e_id] = float(r) if not math.isnan(r) else float("nan")
        else:
            corrs[e_id] = float("nan")

    res: Dict[str, Tuple[float, float, int]] = {}
    for e_id in enum_ids:
        val = corrs.get(e_id, float("nan"))
        e_rows = df[df["enumerator_id"] == e_id]
        weights, peer_corrs = [], []
        for vid, ev_rows in e_rows.groupby("village_id"):
            p_rows = df[(df["village_id"] == vid) & (df["enumerator_id"] != e_id)]
            valid_peers = [corrs[p] for p in p_rows["enumerator_id"].unique() if not math.isnan(corrs.get(p, float("nan")))]
            if valid_peers:
                weights.append(len(ev_rows))
                peer_corrs.append(float(np.median(valid_peers)))
        peer_val = float(np.average(peer_corrs, weights=weights)) if weights else float("nan")
        res[e_id] = (round(val, 4) if not math.isnan(val) else float("nan"), round(peer_val, 4) if not math.isnan(peer_val) else float("nan"), counts.get(e_id, 0))
    return res


def build_feature_table(
    submissions: Union[pd.DataFrame, str, Path],
    villages: Optional[Union[pd.DataFrame, str, Path]] = None,
    seed: Optional[int] = None,
    config_path: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """Build peer-relative feature table with one row per enumerator."""
    df = pd.read_parquet(submissions) if isinstance(submissions, (str, Path)) else submissions.copy()
    if seed is None:
        cfg_file = config_path or (Path(__file__).resolve().parent.parent / "config" / "params.yaml")
        if Path(cfg_file).is_file():
            with open(cfg_file, "r", encoding="utf-8") as f:
                seed = int(yaml.safe_load(f).get("engine", {}).get("seed", 12345))
        else:
            seed = 12345

    rng = np.random.default_rng(seed)
    enum_ids = sorted([str(x) for x in df["enumerator_id"].unique()])
    (f1, sigma_r), f2 = compute_f1_duration_resid(df, enum_ids), compute_f2_throughput(df, enum_ids)
    f3 = compute_f3_near_dup(df, enum_ids, rng=rng)
    f4 = compute_f4_straight_line(df, enum_ids)
    f5 = compute_f5_asset_dispersion(df, enum_ids, rng=rng)
    f6 = compute_f6_hhsize_dispersion(df, enum_ids, rng=rng)
    f7 = compute_f7_gps_spread(df, enum_ids, rng=rng)
    f8, f9 = compute_f8_age_heaping(df, enum_ids), compute_f9_nonresponse(df, enum_ids)
    f10 = compute_f10_dur_size_coupling(df, enum_ids)

    rows = []
    for e in enum_ids:
        rows.append({
            "enumerator_id": e, "n_e": f1[e][2], "f1_sigma_r": round(sigma_r, 4),
            "f1_value": f1[e][0], "f1_peer_value": f1[e][1], "f1_n": f1[e][2],
            "f2_value": f2[e][0], "f2_peer_value": f2[e][1], "f2_n": f2[e][2],
            "f3_k": f3[e][0], "f3_k_exp": f3[e][1], "f3_n": f3[e][2], "f3_null_limited": f3[e][3],
            "f4_k": f4[e][0], "f4_k_exp": f4[e][1], "f4_n": f4[e][2],
            "f5_value": f5[e][0], "f5_peer_value": f5[e][1], "f5_null_sd": f5[e][2], "f5_n": f5[e][3],
            "f6_value": f6[e][0], "f6_peer_value": f6[e][1], "f6_null_sd": f6[e][2], "f6_n": f6[e][3],
            "f7_value": f7[e][0], "f7_peer_value": f7[e][1], "f7_null_sd": f7[e][2], "f7_n": f7[e][3],
            "f8_k": f8[e][0], "f8_k_exp": f8[e][1], "f8_n": f8[e][2],
            "f9_k": f9[e][0], "f9_k_exp": f9[e][1], "f9_n": f9[e][2],
            "f10_value": f10[e][0], "f10_peer_value": f10[e][1], "f10_n": f10[e][2],
        })
    return pd.DataFrame(rows)
